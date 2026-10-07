#!/usr/bin/env python3
"""One read-only judge call: build the review packet, run the judge's CLI, write the verdict.

  review.py --kind acceptance --milestone M1 [--partition P] [--subject PATH ...]
  review.py --kind security|boundary|data --task T4 [--diff RANGE] [--subject PATH ...]
  review.py --kind design|plan --subject PATH ...
  review.py --kind advisor --item T5 --note QUESTION [--subject PATH ...]
  review.py --kind council --item T5 --member 1|2|3 --note QUESTION [--subject PATH ...]
  common: [--plan P | --goal G] [--chief claude|codex] [--vendor claude|codex] [--note TEXT] [--dry-run]

The judge comes from the other vendor than the chief (--chief, else $GOAL_HARNESS), and falls back
to the chief's vendor only when the other vendor reports exhausted quota. A subject is keyed on its
kind and plan ids, never on free text, and gets at most two rounds (one review, one scoped
rereview); advisor and council members get one. Verdicts go to .runs/<goal>/verdicts/<key>.md.
Exit codes: 0 PASS or advice written, 1 BLOCK, invalid judge output or refused round, 2 usage/error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
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
ID_RE = {"milestone": r"M\d+", "task": r"T\d+", "item": r"[TMQ]\d+", "partition": r"[a-z0-9][\w-]*"}


class ReviewError(Exception):
    pass


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


def build_packet(a, ctx, key, rnd, cap, persona, tree, diff_path):
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
        f"Diff under review: {diff_path}" if diff_path else "",
        "Criteria:\n" + "\n".join(criteria) if criteria else "",
        f"Question or rereview scope from the chief:\n{a.note}" if a.note else "",
        (lens.group(0) if lens else "") + "\n\n## Findings\n" + section(rules, "Findings"),
        f"Reply with first line {reply}.",
    ]
    return "\n\n".join(p for p in parts if p)


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
    key = subject_key(a, ctx)
    persona, variant = persona_for(a)
    vendor, chief = pick_vendor(a)
    vdir = ctx.runs / "verdicts"
    rounds_path = vdir / "rounds.json"
    rounds = goal.read_json(rounds_path)
    cap = CAP.get(a.kind, 2)
    rnd = int(rounds.get(key, 0)) + 1
    if rnd > cap:
        print(f"review: refused — {key} already had {cap} round(s); a subject still blocked after its "
              "rereview goes to the founder with the advisor's recommendation (references/review.md)")
        return 1
    if a.kind == "acceptance":
        dirty = dirty_paths(ctx.root)
        if dirty:
            # The verdict names HEAD's tree, so the judge must not read uncommitted files.
            raise ReviewError("acceptance refused: the working tree is not clean; commit first:\n  "
                              + "\n  ".join(dirty[:10]))
    tree = git(ctx.root, "rev-parse", "HEAD^{tree}")
    diff_path = None
    if a.kind == "acceptance" or a.kind in TASK_KINDS or a.diff:
        order = [m["id"] for m in ctx.plan["milestones"]]
        mid = a.milestone or (goal.task_of(ctx.plan, a.task)["milestone"] if a.task else None)
        idx = order.index(mid) if mid in order else 0
        base = ctx.tag(order[idx - 1]) if idx else ctx.tag("approved")
        if a.kind == "acceptance" and not a.diff and not goal.rev_exists(ctx.root, base):
            raise ReviewError(f"milestone base {base} not found; tag the earlier milestone first")
        rng = a.diff or (f"{base}..HEAD" if a.kind == "acceptance" else "HEAD")
        paths = [p for p in a.subject if not p.startswith(".runs/")]
        diff = git(ctx.root, "diff", *rng.split(), "--", *paths) if not a.dry_run else ""
        if rng == "HEAD":
            untracked = git(ctx.root, "ls-files", "--others", "--exclude-standard")
            diff += "\n# untracked files (read them directly):\n" + untracked if untracked else ""
        diff_path = ctx.runs / "review" / f"{key}-r{rnd}.diff"
        if not a.dry_run:
            diff_path.parent.mkdir(parents=True, exist_ok=True)
            diff_path.write_text(diff + "\n")
        diff_path = diff_path.relative_to(ctx.root)
    packet = build_packet(a, ctx, key, rnd, cap, persona, tree, diff_path)
    if a.dry_run:
        route = sync_personas.routing(sync_personas.load(persona)[0], variant)[vendor]
        print(json.dumps({"key": key, "round": rnd, "vendor": vendor, "persona": persona,
                          "command": judge_command(vendor, route["model"], route["effort"], "<packet>",
                                                   ctx.root)}, indent=2))
        print(packet)
        return 0
    route, text, usage, err, quota = run_judge(vendor, persona, variant, packet, ctx.root, timeout)
    fallback = "explicitly requested same vendor as the chief" if a.vendor and a.vendor == chief else ""
    if quota and not a.vendor and a.kind != "council":
        fallback = f"{vendor} quota exhausted ({err.splitlines()[0][:120] if err else 'quota'}); same vendor, fresh context"
        vendor = other(vendor)
        route, text, usage, err, quota = run_judge(vendor, persona, variant, packet, ctx.root, timeout)
    if err:
        print(f"review.py: judge call failed ({vendor}): {err}", file=sys.stderr)
        return 2
    m = VERDICT_RE.search(text)
    verdict = m.group(1) if m else "INVALID"
    if verdict == "ADVICE" and a.kind not in ("advisor", "council") or \
            verdict != "ADVICE" and a.kind in ("advisor", "council"):
        verdict = "INVALID"
    body = (text[:m.start()] + text[m.end():]).strip() if m else text.strip()
    head = {"tree": tree, "vendor": vendor, "model": route["model"], "effort": route["effort"],
            "round": rnd, "subject": key, "persona": persona, "fallback": fallback, "usage": usage}
    out = f"VERDICT: {verdict}\n" + "".join(f"{k}: {v}\n" for k, v in head.items() if v) + "\n" + body + "\n"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{key}.md").write_text(out)
    (vdir / "history").mkdir(exist_ok=True)
    shutil.copy(vdir / f"{key}.md", vdir / "history" / f"{key}-r{rnd}.md")
    rounds[key] = rnd
    rounds_path.write_text(json.dumps(rounds, indent=2) + "\n")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(ctx.runs / "progress.md", "a") as fh:
        fh.write(f"{stamp} review {key} r{rnd} {verdict} verdicts/{key}.md · usage: {usage}\n")
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
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        root = Path(os.path.realpath(git(os.getcwd(), "rev-parse", "--show-toplevel")))
        if (root / goal.RUNTIME_PIN).exists():
            print(f"review.py: {goal.MIGRATE_NOTICE}", file=sys.stderr)
            return 2
        try:
            ctx = goal.find_ctx(argparse.Namespace(plan=a.plan, goal=a.goal))
        except goal.PlanError:
            if a.kind in ("acceptance", *TASK_KINDS) or not a.goal or a.diff:
                raise
            ctx = argparse.Namespace(root=root, goal=a.goal, runs=root / ".runs" / a.goal,
                                     plan={"meta": {}, "milestones": [], "tasks": {}})
        return review(a, ctx)
    except (ReviewError, goal.PlanError, sync_personas.PersonaError, RuntimeError, OSError) as exc:
        print(f"review.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
