#!/usr/bin/env python3
"""One read-only judge call: build the review packet, run the judge's CLI, write the verdict.

  review.py --kind acceptance --milestone M1 [--partition P] [--subject PATH ...]
  review.py --kind security|boundary|data --task T4 [--diff RANGE] [--subject PATH ...]
  review.py --kind design|plan --subject PATH ...
  review.py --kind advisor --item T5 --note QUESTION [--subject PATH ...]
  review.py --kind council --item T5 --member 1|2|3 --note QUESTION [--subject PATH ...]
  common: [--plan P | --goal G] [--chief claude|codex] [--vendor claude|codex] [--note TEXT] [--dry-run]
          [--founder-grant TEXT | --closed-by TEST ...]

The judge comes from the other vendor than the chief (--chief, else $GOAL_HARNESS), and falls back to
the chief's vendor only when the other vendor reports exhausted quota. A subject is keyed on its kind
and plan ids, never on free text, and gets at most two rounds (one review, one scoped rereview);
advisor and council members get one. Only --founder-grant, naming the founder's decision, admits one
more round, once per subject at its cap. --closed-by admits one uncounted confirmation per subject
after a BLOCK when every named test changed since that round (review/<key>-r<n>.files.json). A review
holds verdicts/<key>.lock throughout, so one round per subject is in flight; a round is counted only
when its verdict is written, under verdicts/rounds.lock. Verdicts go to .runs/<goal>/verdicts/<key>.md.
Exit codes: 0 PASS or advice written, 1 BLOCK, invalid judge output or refused round, 2 usage/error;
--closed-by: not admitted → 1, nothing consumed (parsing, context, checks, comparison, preparation).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILL.parent / "agent-personas" / "scripts"))
import goal  # noqa: E402
import sync_personas  # noqa: E402
from gate import dirty_paths, git  # noqa: E402

VENDORS = ("claude", "codex")
KINDS = ("design", "plan", "acceptance", "security", "boundary", "data", "advisor", "council")
TASK_KINDS = ("security", "boundary", "data")
CAP = {"advisor": 1, "council": 1}  # every other kind: 2 rounds
QUOTA_RE = re.compile(r"usage limit|rate[ _-]?limit|quota|limit reached|too many requests|\b429\b"
                      r"|exceeded your|try again (?:at|in|later)", re.I)
VERDICT_RE = re.compile(r"^[\s*_`#>]*VERDICT:\s*\**\s*(PASS|BLOCK|ADVICE)\b", re.M)
JUDGE_SETTINGS = json.dumps({"disableAllHooks": True})
GIT_TIMEOUT = 60  # seconds for each git call behind a --closed-by comparison
ID_RE = {"milestone": r"M\d+", "task": r"T\d+", "item": r"[TMQ]\d+", "partition": r"[a-z0-9][\w-]*"}


class ReviewError(Exception):
    pass


Unmade = ReviewError  # a --closed-by comparison that cannot be made; closure_refusal() refuses it


def other(vendor):
    return VENDORS[1 - VENDORS.index(vendor)]


def judge_command(vendor, model, effort, packet, root):
    """The one-shot judge call, read-only by construction and with user integrations excluded."""
    if vendor == "codex":
        return ["codex", "exec", "-s", "read-only", "--ignore-user-config", "--ignore-rules",
                "-m", model, "-c", f"model_reasoning_effort={effort}", "--json", "-C", str(root), packet]
    # disableAllHooks: no project or local hook (SessionStart, Stop, ...) runs inside the judge.
    return ["claude", "-p", "--model", model, "--effort", effort, "--tools", "Read,Grep,Glob",
            "--strict-mcp-config", "--setting-sources", "project,local", "--settings", JUDGE_SETTINGS,
            "--output-format", "json", packet]


def parse_output(vendor, out):
    """(final message, usage summary, error text) from a CLI's JSON or JSONL stdout."""
    if vendor == "claude":
        data = {}
        for line in reversed(out.strip().splitlines()):
            try:
                data = json.loads(line)
                break
            except ValueError:
                continue
        u = data.get("usage") or {}
        tokens = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                   "cache_creation_input_tokens"))
        usage = (f"claude in={tokens} out={int(u.get('output_tokens') or 0)}"
                 f" cost=${float(data.get('total_cost_usd') or 0):.4f}") if data else "claude —"
        text = str(data.get("result") or "")
        err = text or data.get("subtype", "error") if data.get("is_error") or not data else ""
        return text, usage, err
    text, err, tin, tcached, tout = "", "", 0, 0, 0
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        item = ev.get("item") or {}
        if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text") or text
        elif ev.get("type") == "turn.completed":
            u = ev.get("usage") or {}
            tin += int(u.get("input_tokens") or 0)
            tcached += int(u.get("cached_input_tokens") or 0)
            tout += int(u.get("output_tokens") or 0) + int(u.get("reasoning_output_tokens") or 0)
        elif ev.get("type") in ("error", "turn.failed"):
            err = str(ev.get("message") or (ev.get("error") or {}).get("message") or ev)
    return text, f"codex in={tin} cached={tcached} out={tout}", err


def subject_key(a, ctx):
    """Stable subject key from the kind and plan ids; it is also the verdict's file name."""
    needs = {"acceptance": ["milestone"], "advisor": ["item"], "council": ["item", "member"],
             **{k: ["task"] for k in TASK_KINDS}}.get(a.kind, [])
    for field in needs:
        if getattr(a, field) is None:
            raise ReviewError(f"--kind {a.kind} needs --{field}")
    for field, pattern in ID_RE.items():
        value = getattr(a, field)
        if value is not None and not re.fullmatch(pattern, value):
            raise ReviewError(f"--{field} {value!r} is not a valid id")
    if a.kind == "acceptance":
        m = goal.milestone(ctx.plan, a.milestone)
        part = a.partition or (m["acceptance"][0] if len(m["acceptance"]) == 1 else None)
        if part not in m["acceptance"]:
            raise ReviewError(f"{a.milestone} declares acceptance {m['acceptance']}; pass one as --partition")
        return f"{a.milestone}-acceptance" + ("" if part == "all" else f"-{part}")
    if a.kind in TASK_KINDS:
        goal.task_of(ctx.plan, a.task)
        return f"{a.task}-{a.kind}"
    if a.kind == "advisor":
        return f"{a.item}-advisor"
    if a.kind == "council":
        return f"{a.item}-council-{a.member}"
    return a.kind


def persona_for(a):
    if a.kind == "security":
        return "security-reviewer", None
    if a.kind == "advisor" or (a.kind == "council" and a.member != 3):
        return "advisor", None
    return "reviewer", "acceptance" if a.kind == "acceptance" else None


def pick_vendor(a):
    chief = a.chief or os.environ.get("GOAL_HARNESS")
    if a.vendor:
        return a.vendor, chief
    if chief not in VENDORS:
        raise ReviewError("name the chief's harness with --chief or GOAL_HARNESS, or pass --vendor")
    # A council spans both vendors: members 1 and 3 from the other vendor, member 2 from the chief's.
    return (chief if a.kind == "council" and a.member == 2 else other(chief)), chief


def spec_rows(ctx, ids):
    """Spec table rows for the given criteria, with their continuation rows."""
    spec = goal.file_at(ctx.root, None, str(ctx.plan["meta"].get("spec", ""))) or ""
    rows, keep = [], False
    for line in spec.splitlines():
        m = re.match(r"^\|\s*(AC-\d+)?\s*\|", line)
        keep = (m.group(1) in ids if m.group(1) else keep) if m else False
        if keep:
            rows.append(line)
    return rows


def section(text, title):
    m = re.search(rf"^## {title}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def build_packet(a, ctx, key, rnd, cap, persona, tree, diff_path, cover=""):
    rules = (SKILL / "references" / "review.md").read_text()
    lens = re.search(r"\*\*Lenses\.\*\*.*?(?=\n\n)", rules, re.S)
    criteria = []
    if a.kind == "acceptance":
        m = goal.milestone(ctx.plan, a.milestone)
        criteria = spec_rows(ctx, m["criteria"]) + [f"proof {', '.join(p['acs'])}: {p['body']}"
                                                    for p in m["proofs"]]
        evidence = ctx.runs / f"{a.milestone}-evidence.md"
        if evidence.is_file():
            a.subject.append(str(evidence.relative_to(ctx.root)))
    elif a.kind in TASK_KINDS:
        criteria = spec_rows(ctx, goal.task_of(ctx.plan, a.task)["covers"])
    advice = a.kind in ("advisor", "council")
    reply = ("`VERDICT: ADVICE`, then the lines `recommendation: <option>`, `confidence: high|medium|low`"
             " and `reversible: yes|no`, then your reasoning" if advice else
             "`VERDICT: PASS` or `VERDICT: BLOCK`, then one finding per line: "
             "`- [correctness|safety|requirement|other] <path> — trigger: <...> — consequence: <...>`")
    parts = [
        f"You are the {persona} for goal {ctx.goal}, judging read-only in a fresh context. "
        f"Lens: {a.kind}. Subject: {key}, round {rnd} of {cap}.",
        f"Repository root: {ctx.root}. Tree under review: {tree}. You cannot and must not change any file.",
        "Read these paths yourself; they are not pasted:\n" + "\n".join(f"- {p}" for p in a.subject or ["(none)"]),
        f"Diff under review: {diff_path}" if diff_path else "", cover,
        "Criteria:\n" + "\n".join(criteria) if criteria else "",
        f"Question or rereview scope from the chief:\n{a.note}" if a.note else "",
        f"This round is a test-closed confirmation, not counted toward the cap. The chief names these "
        f"tests as closing every blocking finding under rereview: {' '.join(a.closed_by)}. Check that "
        "each finding is reproduced by a named test; a finding no named test reproduces still blocks."
        if a.closed_by else "",
        "Mark each blocking finding that is a new instance of a finding under rereview (the same "
        "mechanism on a different path) with `family: same as <finding path>`." if rnd > 1 else "",
        (lens.group(0) if lens else "") + "\n\n## Findings\n" + section(rules, "Findings"),
        f"Reply with first line {reply}.",
    ]
    return "\n\n".join(p for p in parts if p)


@contextlib.contextmanager
def rounds_lock(vdir):
    """Hold the global lock on rounds.json briefly; closing the file releases it."""
    vdir.mkdir(parents=True, exist_ok=True)
    with open(vdir / "rounds.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield vdir / "rounds.json"


def subject_lock(vdir, key):
    """The open lock file held for a whole review of key, or None when another review holds it."""
    vdir.mkdir(parents=True, exist_ok=True)
    fh = open(vdir / f"{key}.lock", "a")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    return fh


def changed(root, rng, *paths):
    return [p for p in git(root, "diff", "--name-only", "-z", *rng.split(), "--", *paths).split("\0") if p]


def probe(root, what, *args, ok=(0,), missing=Unmade):
    """The one door for every git call and file read of a --closed-by comparison ("git", or "text", "bytes",
    "json", "list", "lstat" of a path); any failure raises Unmade, and an expected-absent file returns missing=."""
    try:
        if what == "git":
            proc = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=GIT_TIMEOUT)
            if proc.returncode not in ok:
                raise Unmade(f"git {args[0]} exited {proc.returncode}")
            return proc.returncode, proc.stdout.decode()
        path = root / args[0]
        if what == "text":
            return path.read_bytes().decode()
        return {"bytes": Path.read_bytes, "list": os.listdir, "lstat": os.lstat,
                "json": lambda q: json.loads(q.read_bytes())}[what](path)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:  # ValueError: bad JSON or UTF-8
        if isinstance(exc, (FileNotFoundError, NotADirectoryError)) and missing is not Unmade:  # absent
            return missing
        raise Unmade(f"{what} {args[0]}: {exc}") from exc


def digests(root, tree):
    """Full snapshot: {path: sha256 of its working-tree bytes, or None when not a regular file} for every
    path git lists (cached, or untracked and unignored) and every path in the verdict tree."""
    names = {p for p in (probe(root, "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard")[1] + "\0"
                         + probe(root, "git", "ls-tree", "-r", "-z", "--name-only", tree)[1]).split("\0")
             if p and p.split("/")[0] != ".runs"}  # comparison() refuses exactly these .runs/ names
    regular = {p for p in names if stat.S_ISREG(getattr(probe(root, "lstat", p, missing=None), "st_mode", 0))}
    return {p: hashlib.sha256(probe(root, "bytes", p)).hexdigest() if p in regular else None for p in sorted(names)}


def closure_refusal(vdir, key, last, tests, root):
    """Why --closed-by is refused for key after round last, or None when every named test changed."""
    try:
        return comparison(vdir, key, last, tests, root)
    except Unmade as exc:
        return f"the comparison with round {last} cannot be made: {exc}"


def comparison(vdir, key, last, tests, root):
    lines = probe(root, "text", vdir / f"{key}.md", missing="").splitlines()
    head = dict(l.split(":", 1) for l in lines[1:20] if ":" in l)
    verdict = lines[0][8:].strip() if lines and lines[0].startswith("VERDICT:") else None
    tree = head.get("tree", "").strip()
    if verdict != "BLOCK" or not tree:
        return f"--closed-by needs a BLOCK verdict naming its tree; {key} has {verdict or 'none'}"
    before = probe(root, "json", vdir.parent / "review" / f"{key}-r{last}.files.json", missing=None)
    if not isinstance(before, dict) or not all(isinstance(v, (str, type(None))) for v in before.values()):
        raise Unmade(f"review/{key}-r{last}.files.json is missing or malformed")
    probe(root, "git", "cat-file", "-e", f"{tree}^{{tree}}")
    for test in tests:
        p = os.path.normpath(test.split("::")[0])
        if os.path.isabs(p) or p.split("/")[0] in ("..", ".runs"):  # outside, or never in the snapshot
            return f"{test} is not a regular, tracked or new unignored file in the working tree"
        known = probe(root, "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", p)[1]
        # Each part as stored on disk: on a case-insensitive filesystem git lists TESTS/x.py as untracked.
        parts = Path(p).parts
        exact = p in known.split("\0") and all(n in probe(root, "list", Path(*parts[:i]), missing=())
                                          for i, n in enumerate(parts))
        if not exact or not stat.S_ISREG(probe(root, "lstat", p).st_mode):
            return f"{test} is not a regular, tracked or new unignored file in the working tree"
        if p in before:
            same = before[p] == hashlib.sha256(probe(root, "bytes", p)).hexdigest()
        else:  # an unrecorded path equalled the round's tree; absent when the tree lists nothing for it
            listed = probe(root, "git", "ls-tree", "-z", tree, "--", p)[1]
            same = bool(listed) and probe(root, "git", "diff", "--quiet", tree, "--", p, ok=(0, 1))[0] == 0
        if same:
            return f"{test} is unchanged since round {last}; a confirmation needs a test the correction changed"
    return None


def admit(vdir, key, cap, grant=None, closed=None, root=None):
    """Check the cap, the founder grant or a confirmation, reserving nothing: (round, limit, None) or
    (None, None, refusal). A confirmation is numbered in sequence but not counted in rounds[key]."""
    with rounds_lock(vdir) as path:
        rounds = goal.read_json(path)
    used, grants = int(rounds.get(key, 0)), rounds.get("founder_grants", {})
    confirmed = rounds.get("confirmations", {})
    rnd = used + (key in confirmed) + 1
    refusal = closed and (f"{key} already used its confirmation (round {confirmed[key]})" if key in confirmed
                          else closure_refusal(vdir, key, rnd - 1, closed, root))
    if refusal:
        return None, None, refusal
    if not closed and grant is None and used >= cap:
        return None, None, (f"{key} already had {used} round(s); a subject still blocked after its rereview "
                            "goes to the founder with the advisor's recommendation (references/review.md)")
    if grant is not None and key in grants:
        return None, None, f"{key} already used its founder grant ({grants[key]})"
    if grant is not None and used < cap:
        return None, None, f"{key} has used {used} of {cap} round(s); a founder grant applies only at the cap"
    if (vdir / "history" / f"{key}-r{rnd}.md").exists():
        raise ReviewError(f"history/{key}-r{rnd}.md already exists but rounds.json says {rnd - 1}; "
                          "refusing to overwrite it")
    return rnd, cap + (grant is not None or key in grants) + bool(closed or key in confirmed), None


def record(vdir, key, rnd, out, grant=None, confirmation=False, files=None):
    """Write the round's digests, history, the current verdict and the count together; other subjects'
    counts are reread. A confirmation is recorded under confirmations and leaves rounds[key] alone."""
    with rounds_lock(vdir) as path:
        rounds = goal.read_json(path)
        if files is not None:
            (vdir.parent / "review").mkdir(parents=True, exist_ok=True)
            (vdir.parent / "review" / f"{key}-r{rnd}.files.json").write_text(json.dumps(files, indent=2) + "\n")
        (vdir / "history").mkdir(exist_ok=True)
        with open(vdir / "history" / f"{key}-r{rnd}.md", "x") as fh:  # history is never overwritten
            fh.write(out)
        (vdir / f"{key}.md").write_text(out)
        if confirmation:
            rounds["confirmations"] = {**rounds.get("confirmations", {}), key: rnd}
        else:
            rounds[key] = int(rounds.get(key, 0)) + 1
        if grant is not None:
            rounds["founder_grants"] = {**rounds.get("founder_grants", {}), key: grant}
        path.write_text(json.dumps(rounds, indent=2) + "\n")


def run_judge(vendor, persona, variant, packet, root, timeout):
    route = sync_personas.routing(sync_personas.load(persona)[0], variant)[vendor]
    cmd = judge_command(vendor, route["model"], route["effort"], packet, root)
    env = {**os.environ, "GOAL_ROLE": "judge"}
    try:
        proc = subprocess.run(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
    except FileNotFoundError:
        return route, "", "", f"{vendor} CLI not found", False
    except subprocess.TimeoutExpired:
        return route, "", "", f"{vendor} judge timed out after {timeout}s", False
    text, usage, err = parse_output(vendor, proc.stdout)
    failed = proc.returncode != 0 or bool(err) or not text
    err = (err or proc.stderr.strip()[-400:] or f"exit {proc.returncode}") if failed else ""
    quota = failed and bool(QUOTA_RE.search(err + proc.stderr + proc.stdout[-2000:]))
    return route, text, usage, err, quota


def review(a, ctx, timeout=3600):
    # Before every other argument check: --closed-by with an incompatible argument is a refusal.
    if a.closed_by and (a.kind in ("advisor", "council") or a.founder_grant is not None):
        print("review: refused — --closed-by applies to a capped kind and never with --founder-grant")
        return 1
    key = subject_key(a, ctx)
    persona, variant = persona_for(a)
    vendor, chief = pick_vendor(a)
    vdir = ctx.runs / "verdicts"
    cap = CAP.get(a.kind, 2)
    grant = a.founder_grant
    if grant is not None and (not grant.strip() or a.kind in ("advisor", "council")):
        raise ReviewError("--founder-grant needs non-empty text naming the founder's decision"
                          if not grant.strip() else f"--kind {a.kind} is never eligible for a founder grant")
    if a.kind == "acceptance" and a.diff is not None:
        raise ReviewError("--diff never applies to acceptance: its range is the milestone's; only a "
                          "declared partition narrows it")
    if a.kind == "acceptance":
        dirty = dirty_paths(ctx.root)
        if dirty:
            # The verdict names HEAD's tree, so the judge must not read uncommitted files.
            raise ReviewError("acceptance refused: the working tree is not clean; commit first:\n  "
                              + "\n  ".join(dirty[:10]))
    tree = git(ctx.root, "rev-parse", "HEAD^{tree}")
    lock = subject_lock(vdir, key)
    if lock is None:
        print(f"review: refused — {key} is already being reviewed")
        return 1
    with lock:  # held for admission, the judge call and the writes: one round of key in flight
        rnd, limit, refusal = admit(vdir, key, cap, grant, a.closed_by, ctx.root)
        if refusal:
            print(f"review: refused — {refusal}")
            return 1
        return judge_round(a, ctx, key, rnd, limit, persona, variant, vendor, chief, tree, vdir, timeout)


def judge_round(a, ctx, key, rnd, cap, persona, variant, vendor, chief, tree, vdir, timeout):
    """Run round rnd of key; a failed judge call writes and consumes nothing."""
    diff_path, cover, rng = None, "", "HEAD"
    if a.kind == "acceptance" or a.kind in TASK_KINDS or a.diff:
        order = [m["id"] for m in ctx.plan["milestones"]]
        mid = a.milestone or (goal.task_of(ctx.plan, a.task)["milestone"] if a.task else None)
        idx = order.index(mid) if mid in order else 0
        base = ctx.tag(order[idx - 1]) if idx else ctx.tag("approved")
        if a.kind == "acceptance" and not goal.rev_exists(ctx.root, base):
            raise ReviewError(f"milestone base {base} not found; tag the earlier milestone first")
        rng = a.diff or (f"{base}..HEAD" if a.kind == "acceptance" else "HEAD")
        # Acceptance narrows the diff only to a declared partition; otherwise --subject is reading context.
        narrow = a.kind != "acceptance" or len(goal.milestone(ctx.plan, a.milestone)["acceptance"]) > 1
        paths = [p for p in a.subject if not p.startswith(".runs/")] if narrow else []
        diff = git(ctx.root, "diff", *rng.split(), "--", *paths) if not a.dry_run else ""
        if a.kind == "acceptance":
            cover = (f"diff covers {len(changed(ctx.root, rng, *paths))} of {len(changed(ctx.root, rng))}"
                     f" files changed in {a.milestone}")
        if rng == "HEAD":
            untracked = git(ctx.root, "ls-files", "--others", "--exclude-standard")
            diff += "\n# untracked files (read them directly):\n" + untracked if untracked else ""
        diff_path = ctx.runs / "review" / f"{key}-r{rnd}.diff"
        if not a.dry_run:
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text(diff + "\n")
        diff_path = diff_path.relative_to(ctx.root)
    packet = build_packet(a, ctx, key, rnd, cap, persona, tree, diff_path, cover)
    if a.dry_run:
        route = sync_personas.routing(sync_personas.load(persona)[0], variant)[vendor]
        print(json.dumps({"key": key, "round": rnd, "vendor": vendor, "persona": persona,
                          "command": judge_command(vendor, route["model"], route["effort"], "<packet>",
                                                   ctx.root)}, indent=2))
        print(packet)
        return 0
    files = digests(ctx.root, tree)  # a full snapshot before the judge call; compared again after it
    a.admitted = True  # main(): from here a --closed-by invocation is admitted, not refused
    route, text, usage, err, quota = run_judge(vendor, persona, variant, packet, ctx.root, timeout)
    fallback = "explicitly requested same vendor as the chief" if a.vendor and a.vendor == chief else ""
    if quota and not a.vendor and a.kind != "council":
        fallback = f"{vendor} quota exhausted ({err.splitlines()[0][:120] if err else 'quota'}); same vendor, fresh context"
        vendor = other(vendor)
        route, text, usage, err, quota = run_judge(vendor, persona, variant, packet, ctx.root, timeout)
    if err or digests(ctx.root, tree) != files:  # drift: the judge may have read bytes files lacks
        print(f"review.py: judge call failed ({vendor}): {err}" if err else
              "review: files changed while the judge ran; nothing recorded — rerun", file=sys.stderr)
        return 2
    m = VERDICT_RE.search(text)
    verdict = m.group(1) if m else "INVALID"
    if verdict == "ADVICE" and a.kind not in ("advisor", "council") or \
            verdict != "ADVICE" and a.kind in ("advisor", "council"):
        verdict = "INVALID"
    body = (text[:m.start()] + text[m.end():]).strip() if m else text.strip()
    head = {"tree": tree, "vendor": vendor, "model": route["model"], "effort": route["effort"],
            "round": rnd, "founder-grant": a.founder_grant,
            "confirmation": a.closed_by and "closed-by " + " ".join(a.closed_by), "subject": key,
            "persona": persona, "fallback": fallback, "usage": usage}
    out = f"VERDICT: {verdict}\n" + "".join(f"{k}: {v}\n" for k, v in head.items() if v) + "\n" + body + "\n"
    record(vdir, key, rnd, out, a.founder_grant, bool(a.closed_by), files)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:  # best-effort: the round is already recorded and is never undone
        with open(ctx.runs / "progress.md", "a") as fh:
            fh.write(f"{stamp} review {key} r{rnd} {verdict} verdicts/{key}.md · usage: {usage}\n")
    except OSError as exc:
        print(f"review.py: warning: progress.md not updated: {exc}", file=sys.stderr)
    print(f"review: {verdict} · {key} round {rnd} · {vendor} {route['model']} {route['effort']}"
          f" · {vdir / (key + '.md')}")
    return 0 if verdict in ("PASS", "ADVICE") else 1


def parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", required=True, choices=KINDS)
    for opt in ("--plan", "--goal", "--milestone", "--partition", "--task", "--item", "--note", "--diff"):
        ap.add_argument(opt)
    ap.add_argument("--member", type=int, choices=(1, 2, 3))
    ap.add_argument("--subject", nargs="*", default=[])
    ap.add_argument("--chief", choices=VENDORS)
    ap.add_argument("--vendor", choices=VENDORS, help="force the judge's vendor")
    ap.add_argument("--dry-run", action="store_true", help="print the command and packet; run nothing")
    ap.add_argument("--founder-grant", metavar="TEXT",
                    help="the founder's decision admitting one round past the cap, once per subject")
    ap.add_argument("--closed-by", nargs="+", metavar="TEST",
                    help="path[::name] of tests closing the last BLOCK: one uncounted confirmation per subject")
    return ap


def main(argv=None):
    argv, a = sys.argv[1:] if argv is None else argv, None
    closing = any(len(t := x.split("=")[0]) > 3 and "--closed-by".startswith(t) for x in argv)
    try:
        a = parser().parse_args(argv)
        root = Path(os.path.realpath(git(os.getcwd(), "rev-parse", "--show-toplevel")))
        if (root / goal.RUNTIME_PIN).exists():
            raise ReviewError(goal.MIGRATE_NOTICE)
        try:
            ctx = goal.find_ctx(argparse.Namespace(plan=a.plan, goal=a.goal))
        except goal.PlanError:
            if a.kind in ("acceptance", *TASK_KINDS) or not a.goal or a.diff:
                raise
            ctx = argparse.Namespace(root=root, goal=a.goal, runs=root / ".runs" / a.goal,
                                     plan={"meta": {}, "milestones": [], "tasks": {}})
        return review(a, ctx)
    except (Exception, SystemExit) as exc:  # the one admission boundary for --closed-by
        if closing and not getattr(a, "admitted", False) and getattr(exc, "code", 2) != 0:
            print("review: refused —", ("invalid arguments (usage above)" if isinstance(exc, SystemExit)
                                        else str(exc) or repr(exc)).splitlines()[0])
            return 1
        if not isinstance(exc, (ReviewError, goal.PlanError, sync_personas.PersonaError, RuntimeError, OSError)):
            raise
        print(f"review.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
