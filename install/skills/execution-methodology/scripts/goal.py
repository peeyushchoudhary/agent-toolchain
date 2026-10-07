#!/usr/bin/env python3
"""Goal state computed from plan.md and git: lint, status, next, guard, done, stop-hook, evidence.

The plan is found from --plan, else .runs/active, else docs/product/goals/<goal>/plan.md.
Exit codes: 0 ok, 1 finding (not done, guard or lint failure), 2 usage or internal error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import git, receipt_path  # noqa: E402

TASK_FIELDS = ("writes", "needs", "covers", "risk", "builder", "tests-may-change")
TOKENS = ("gate", "full_gate", "e2e")
EMPTY = ("", "—", "–", "-")
TASK_RE = re.compile(r"^###\s+\[([ x!])\]\s+(T\d+)\s+[—–-]+\s*(.*)$")
MILESTONE_RE = re.compile(r"^##\s+(M\d+)\s+[—–-]+\s*(.*)$")
PROOF_RE = re.compile(r"^-\s+(AC-\d+(?:\s*,\s*AC-\d+)*)\s*:\s*(.+)$")
AC_ROW_RE = re.compile(r"^\|\s*(AC-\d+)\s*\|", re.M)
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)src/test/|(^|/)test_[^/]*\.py$"
                     r"|_(test|spec)\.[^/.]+$|\.(test|spec)\.[^/]+$|Tests?\.(java|kt|cs|swift)$")
SKIP_RE = re.compile(r"\bunittest\.(skip\w*|expectedFailure)\b|\.skipTest\(|\bpytest\.(skip|xfail)\("
                     r"|\bpytest\.mark\.(skip|skipif|xfail)\b|\.only\(|\b(it|describe|test)\.skip\("
                     r"|\bx(it|describe)\(|@Disabled\b|@Ignore\b")
RUNTIME_PIN = "docs/agents/execution/runtime.json"
MIGRATE_NOTICE = (f"this project still carries the v5.1 runtime pin ({RUNTIME_PIN}); "
                  "migrate it to v6 first, following references/migrate.md")

class PlanError(Exception):
    pass

def strip_comment(value: str) -> str:
    """Drop a trailing comment: an unquoted '#' preceded by whitespace, as the shell reads it."""
    quote = None
    for i, ch in enumerate(value):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and i > 0 and value[i - 1] in " \t":
            return value[:i].rstrip()
    return value.strip()

def scalar(value: str):
    """Parse a frontmatter value: [list], {map}, true/false, integer, or the raw string."""
    v = strip_comment(value).strip()
    if v.startswith("[") and v.endswith("]"):
        return [scalar(x) for x in v[1:-1].split(",") if x.strip()]
    if v.startswith("{") and v.endswith("}"):
        pairs = [p.split(":", 1) for p in v[1:-1].split(",") if ":" in p]
        return {k.strip(): scalar(x) for k, x in pairs}
    if v in ("true", "false"):
        return v == "true"
    return int(v) if re.fullmatch(r"-?\d+", v) else v

def split_list(value: str) -> list:
    v = strip_comment(value).strip()
    return [] if v in EMPTY else [x.strip() for x in v.split(",") if x.strip()]

def parse_tmc(value: str):
    """tests-may-change: 'globs[, ...] [except a, b and c] [(note)]' -> (include, exclude)."""
    v = re.sub(r"\s*\([^)]*\)\s*$", "", strip_comment(value).strip())
    if v in EMPTY:
        return [], []
    inc, _, exc = v.partition(" except ")
    split = lambda s: [x.strip() for x in re.split(r",|\s+and\s+", s) if x.strip()]  # noqa: E731
    return split(inc), split(exc)

def parse_plan(text: str) -> dict:
    """Parse plan.md into frontmatter, milestones, tasks, decisions and queue."""
    plan = {"meta": {}, "milestones": [], "tasks": {}, "decisions": [], "queue": [], "errors": []}
    body = text.splitlines()
    marks = [k for k, line in enumerate(body) if line.strip() == "---"]
    if len(marks) > 1 and marks[0] == 0:
        for line in body[1:marks[1]]:
            key, sep, val = line.partition(":")
            if sep and re.fullmatch(r"[A-Za-z_][\w-]*", key.strip()):
                plan["meta"][key.strip()] = scalar(val)
        body = body[marks[1] + 1:]
    section, ms, task, proofs = None, None, None, False
    for line in body:
        if line.startswith("## "):
            m, name, task, proofs = MILESTONE_RE.match(line), line[3:].strip(), None, False
            section = "milestone" if m else name.lower() if name in ("Decisions", "Queue") else None
            ms = m and {"id": m.group(1), "title": m.group(2).strip(), "criteria": [],
                        "acceptance": ["all"], "proofs": [], "tasks": []}
            if ms:
                plan["milestones"].append(ms)
        elif line.startswith("### "):
            m, task, proofs = TASK_RE.match(line), None, False
            if m and ms:
                task = {"id": m.group(2), "state": m.group(1), "title": m.group(3).strip(),
                        "milestone": ms["id"], **{f: [] for f in TASK_FIELDS}, "tmc_exclude": []}
                if task["id"] in plan["tasks"]:
                    plan["errors"].append(f"duplicate task id {task['id']}")
                plan["tasks"][task["id"]] = task
                ms["tasks"].append(task)
            elif re.match(r"^###\s+\[", line):
                plan["errors"].append(f"malformed task header: {line.strip()}")
        elif section in ("decisions", "queue"):
            if line.strip():
                plan[section].append(line.rstrip())
        elif task is not None:
            m = re.match(r"^-\s+([\w-]+):\s*(.*)$", line)
            field = m and m.group(1)
            if field == "tests-may-change":
                task[field], task["tmc_exclude"] = parse_tmc(m.group(2))
            elif field in ("risk", "builder"):
                task[field] = strip_comment(m.group(2)).strip()
            elif field in TASK_FIELDS:
                task[field] = split_list(m.group(2))
        elif ms is not None:
            key, sep, val = line.partition(":")
            m = PROOF_RE.match(line)
            if sep and key in ("criteria", "acceptance", "proofs"):
                proofs = key == "proofs"
                if key != "proofs":
                    ms[key] = val if isinstance(val := scalar(val), list) else split_list(str(val))
            elif proofs and m:
                body = strip_comment(m.group(2))
                manual = re.match(r"manual\b", body)
                cmd = plan["meta"].get(body) if body in TOKENS else None if manual else body
                ms["proofs"].append({"acs": split_list(m.group(1)), "body": body, "cmd": cmd,
                                     "kind": "manual" if cmd is None and body not in TOKENS else "run"})
            elif line.strip() and not line.startswith("- "):
                proofs = False
    return plan

def milestone(plan, mid):
    found = [m for m in plan["milestones"] if m["id"] == mid]
    if not found:
        raise PlanError(f"no milestone {mid} in the plan")
    return found[0]

def task_of(plan, tid):
    if tid not in plan["tasks"]:
        raise PlanError(f"no task {tid} in the plan")
    return plan["tasks"][tid]

def glob_re(pattern: str):
    """'**' spans directories, '*' and '?' stay within one segment, anything else is literal."""
    if pattern.endswith("/"):
        pattern += "**"
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")

def matches(path, patterns):
    return any(glob_re(pattern).match(path) for pattern in patterns)

def overlap(a_globs, b_globs) -> bool:
    """True when two write sets could name a common path (conservative for two globs)."""
    def static(p):
        segs = p.split("/")
        k = next((i for i, s in enumerate(segs) if "*" in s or "?" in s), len(segs))
        return segs[:k], k == len(segs)
    for a in a_globs:
        for b in b_globs:
            (sa, ea), (sb, eb) = static(a), static(b)
            if ea and eb:
                hit = a == b
            elif ea or eb:
                hit = bool(glob_re(b).match(a) if ea else glob_re(a).match(b))
            else:
                n = min(len(sa), len(sb))
                hit = sa[:n] == sb[:n]
            if hit:
                return True
    return False

is_test = TEST_RE.search

def tmc_allows(task, path):
    if not matches(path, task["tests-may-change"]):
        return False
    base = path.rsplit("/", 1)[-1]
    return not any(glob_re(p).match(path if "/" in p else base) for p in task["tmc_exclude"])

def rev_exists(root, rev):
    return bool(git(root, "rev-parse", "-q", "--verify", f"{rev}^{{commit}}", check=False))

def file_at(root, rev, path):
    """File text at a commit, or in the working tree when rev is None; None when absent."""
    if rev is None:
        p = Path(root) / path
        return p.read_text(errors="replace") if p.is_file() else None
    proc = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=root, capture_output=True)
    return proc.stdout.decode(errors="replace") if proc.returncode == 0 else None

def changes(root, base, head=None):
    """[(status, path)] from base to head, or to the working tree plus untracked files."""
    out = git(root, "diff", "--name-status", "--no-renames", "-z", base, *([head] if head else []))
    parts = out.split("\0")
    res = [(parts[k][0], parts[k + 1]) for k in range(0, len(parts) - 1, 2) if parts[k]]
    if head is None:
        res += [("A", p) for p in git(root, "ls-files", "--others", "--exclude-standard", "-z")
                .split("\0") if p]
    return res

def added_lines(root, base, head, path, status):
    if head is None and status == "A":
        text = file_at(root, None, path) or ""
        return text.splitlines()
    out = git(root, "diff", "-U0", base, *([head] if head else []), "--", path)
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]

def frozen_view(text):
    """Plan text with checkbox marks normalised and Decisions/Queue bodies dropped."""
    out, skip = [], False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            skip = line[3:].strip() in ("Decisions", "Queue")
            out.append(line)
            continue
        if not skip:
            out.append(re.sub(r"^(###\s+)\[[ x!]\]", r"\1[ ]", line))
    return "\n".join(out).rstrip()

class Ctx:
    """The repository root, the plan path and its parsed working-tree contents."""

    def __init__(self, root, plan_path):
        self.root, plan_abs = Path(root), Path(os.path.realpath(plan_path))
        if not plan_abs.is_file() or self.root not in plan_abs.parents:
            raise PlanError(f"plan not found inside the repository: {plan_path}")
        self.plan_rel = plan_abs.relative_to(self.root).as_posix()
        self.plan = parse_plan(plan_abs.read_text())
        self.goal = str(self.plan["meta"].get("goal", ""))
        if not self.goal:
            raise PlanError("plan frontmatter has no goal")
        self.runs = self.root / ".runs" / self.goal

    def tag(self, name):
        return f"goal/{self.goal}/{name}"

    def plan_at(self, rev):
        text = file_at(self.root, rev, self.plan_rel)
        if text is None:
            raise PlanError(f"{self.plan_rel} is not committed at {rev}")
        return parse_plan(text)

    def tagged(self, mid):
        return rev_exists(self.root, self.tag(mid))

    def active(self, plan=None):
        for m in (plan or self.plan)["milestones"]:
            if not self.tagged(m["id"]):
                return m["id"]
        return None

def find_ctx(args, cwd=None):
    root = Path(os.path.realpath(git(cwd or os.getcwd(), "rev-parse", "--show-toplevel")))
    if args.plan:
        return Ctx(root, Path(cwd or os.getcwd()) / args.plan)
    active = root / ".runs" / "active"
    if active.is_file():
        return Ctx(root, root / json.loads(active.read_text())["plan"])
    if args.goal:
        return Ctx(root, root / "docs/product/goals" / args.goal / "plan.md")
    raise PlanError("no plan: pass --plan, run 'goal.py start', or pass --goal")

def lint(ctx):
    plan, meta, errs = ctx.plan, ctx.plan["meta"], list(ctx.plan["errors"])
    for key in ("goal", "title", "spec", "design", "gate", "full_gate", "e2e"):
        if not meta.get(key):
            errs.append(f"frontmatter: {key} is missing")
    spec = file_at(ctx.root, None, str(meta.get("spec", ""))) if meta.get("spec") else None
    acs = set(AC_ROW_RE.findall(spec or ""))
    if meta.get("spec") and spec is None:
        errs.append(f"spec not found: {meta['spec']}")
    ids = [m["id"] for m in plan["milestones"]]
    errs += [f"duplicate milestone id {i}" for i in sorted(set(ids)) if ids.count(i) > 1]
    for m in plan["milestones"]:
        if not m["criteria"]:
            errs.append(f"{m['id']}: no criteria")
        if not m["acceptance"]:
            errs.append(f"{m['id']}: empty acceptance partitions")
        proved = {ac for p in m["proofs"] for ac in p["acs"]}
        for ac in m["criteria"]:
            if spec is not None and ac not in acs:
                errs.append(f"{m['id']}: criterion {ac} is not in the spec")
            if ac not in proved:
                errs.append(f"{m['id']}: criterion {ac} has no proof")
        for p in m["proofs"]:
            if p["kind"] == "run" and not p["cmd"]:
                errs.append(f"{m['id']}: proof token {p['body']} has no frontmatter command")
        if not m["tasks"]:
            errs.append(f"{m['id']}: no tasks")
    for t in plan["tasks"].values():
        for field in ("writes", "covers"):
            if not t[field]:
                errs.append(f"{t['id']}: {field} is empty")
        for n in t["needs"]:
            if n not in plan["tasks"] or n == t["id"]:
                errs.append(f"{t['id']}: needs {n}, which is not another task in the plan")
        for ac in t["covers"]:
            if spec is not None and ac not in acs:
                errs.append(f"{t['id']}: covers {ac}, which is not in the spec")
        for field, allowed in (("risk", ("none", "boundary", "data", "safety")),
                               ("builder", ("routine", "judgement", "mechanical"))):
            if t[field] not in allowed:
                errs.append(f"{t['id']}: {field} must be one of {', '.join(allowed)}")
    return errs

def frozen_findings(ctx, head):
    tag = ctx.tag("approved")
    if not rev_exists(ctx.root, tag):
        return [f"frozen: tag {tag} not found"]
    out = []
    for key in ("spec", "design"):
        path = ctx.plan["meta"].get(key)
        if path and file_at(ctx.root, tag, path) != file_at(ctx.root, head, path):
            out.append(f"frozen: {path} changed since {tag}")
    old, new = file_at(ctx.root, tag, ctx.plan_rel), file_at(ctx.root, head, ctx.plan_rel)
    if old is None or new is None or frozen_view(old) != frozen_view(new):
        out.append(f"frozen: {ctx.plan_rel} changed outside checkboxes, Decisions and Queue since {tag}")
    return out

def guard(ctx, task, base, head=None):
    """Scope, test-integrity and frozen-input findings for base..head (or the working tree)."""
    out = []
    for status, path in changes(ctx.root, base, head):
        if path == ctx.plan_rel:
            if frozen_view(file_at(ctx.root, base, path)) != frozen_view(file_at(ctx.root, head, path)):
                out.append(f"scope: {path} changed outside checkboxes, Decisions and Queue")
            continue
        if not matches(path, task["writes"]):
            out.append(f"scope: {path} is outside {task['id']} writes")
        if not is_test(path) or tmc_allows(task, path):
            continue
        if status in "MDT":
            verb = "deleted" if status == "D" else "modified"
            out.append(f"tests: existing test {path} {verb} outside tests-may-change")
        if status != "D":
            hit = next((l for l in added_lines(ctx.root, base, head, path, status)
                        if SKIP_RE.search(l)), None)
            if hit is not None:
                out.append(f"tests: {path} adds a skip/only/xfail marker: {hit.strip()[:80]}")
    return out + frozen_findings(ctx, head)

def controller_only(ctx, parent, commit):
    """A commit whose diff is nothing, or plan.md checkbox/Decisions/Queue edits only."""
    ch = changes(ctx.root, parent, commit)
    return all(p == ctx.plan_rel for _s, p in ch) and frozen_view(
        file_at(ctx.root, parent, ctx.plan_rel)) == frozen_view(file_at(ctx.root, commit, ctx.plan_rel))

def task_commits(ctx, base, cand, mid, plan):
    """Check every commit in base..cand; return (findings, guard results per task commit)."""
    out, guards = [], []
    for c in git(ctx.root, "rev-list", "--reverse", f"{base}..{cand}").split():
        subject = git(ctx.root, "log", "-1", "--format=%s", c)
        parent = git(ctx.root, "rev-parse", f"{c}^1")
        tids = sorted(set(re.findall(r"\[(T\d+)\]", subject)))
        if len(tids) == 1 and plan["tasks"].get(tids[0], {}).get("milestone") == mid:
            found = guard(ctx, plan["tasks"][tids[0]], parent, c)
            guards.append((c, tids[0], found))
            out += [f"commit {c[:10]} [{tids[0]}]: {f}" for f in found]
        elif len(tids) == 1:
            out.append(f"commit {c[:10]} names {tids[0]}, which is not a task of {mid}")
        elif tids:
            out.append(f"commit {c[:10]} names several tasks: {', '.join(tids)}")
        elif not (subject.startswith(f"{ctx.goal}:") and controller_only(ctx, parent, c)):
            out.append(f"commit {c[:10]} names no task and is not a plan-metadata commit")
    return out, guards

def verdict_file(ctx, mid, part):
    name = f"{mid}-acceptance.md" if part == "all" else f"{mid}-acceptance-{part}.md"
    return ctx.runs / "verdicts" / name

def read_verdict(path):
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None, None, {}
    head = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:20]) if _}
    verdict = lines[0].partition(":")[2].strip() if lines and lines[0].startswith("VERDICT:") else None
    return verdict, head.get("tree"), head

def required_commands(plan, m):
    """(label, command) for full_gate, e2e and every automatic proof, each command once."""
    cmds = [(n, plan["meta"].get(n)) for n in ("full_gate", "e2e")]
    cmds += [("proof " + ", ".join(p["acs"]), p["cmd"]) for p in m["proofs"] if p["kind"] == "run"]
    first = {}
    for label, cmd in cmds:
        first.setdefault(cmd, label)
    return [(label, cmd) for cmd, label in first.items()]

def load_receipt(ctx, tree, cmd):
    r = read_json(receipt_path(ctx.root, ctx.goal, tree, cmd))
    return r if r.get("tree") == tree and r.get("command") == cmd else None

def done(ctx, mid=None):
    """Return (unmet, info) for a milestone; unmet is empty when it is done.

    Every earlier milestone is re-verified against its own tag. With no milestone and every
    milestone tagged, all of them are re-verified and info["milestone"] is None.
    """
    head_plan = ctx.plan_at("HEAD")
    order = [m["id"] for m in head_plan["milestones"]]
    mid = mid or ctx.active(head_plan)
    if mid is not None:
        milestone(head_plan, mid)
    idx = order.index(mid) if mid is not None else len(order)
    unmet = []
    for earlier in order[:idx]:
        if not ctx.tagged(earlier):
            unmet.append(f"{earlier} is not tagged yet")
        else:
            unmet += [f"{earlier} (tag {ctx.tag(earlier)}): {u}" for u in verify(ctx, earlier, order)[0]]
    if mid is None:
        return unmet, {"milestone": None}
    found, info = verify(ctx, mid, order)
    return unmet + found, info

def verify(ctx, mid, order):
    """(unmet, info) for one milestone on its candidate: its tag when tagged, else HEAD."""
    idx = order.index(mid)
    unmet = []
    cand = ctx.tag(mid) if ctx.tagged(mid) else "HEAD"
    commit = git(ctx.root, "rev-parse", f"{cand}^{{commit}}")
    tree = git(ctx.root, "rev-parse", f"{commit}^{{tree}}")
    plan = ctx.plan_at(commit)
    m = milestone(plan, mid)
    base = ctx.tag(order[idx - 1]) if idx else ctx.tag("approved")
    info = {"milestone": mid, "commit": commit, "tree": tree, "base": base, "plan": plan,
            "guards": [], "receipts": {}}
    unmet += [f"{t['id']} {'parked' if t['state'] == '!' else 'unchecked'}"
              for t in m["tasks"] if t["state"] != "x"]
    if not rev_exists(ctx.root, base):
        unmet.append(f"milestone base {base} not found")
    else:
        found, info["guards"] = task_commits(ctx, base, commit, mid, plan)
        unmet += found
    for label, cmd in required_commands(plan, m):
        if not cmd:
            unmet.append(f"no {label} command in the plan")
            continue
        r = info["receipts"][cmd] = load_receipt(ctx, tree, cmd)
        if r is None:
            unmet.append(f"no {label} receipt for the candidate tree")
        elif r.get("verdict") != "PASS":
            unmet.append(f"{label} receipt is {r.get('verdict')}: {'; '.join(r.get('reasons', []))}")
    for part in m["acceptance"]:
        verdict, vtree, _ = read_verdict(verdict_file(ctx, mid, part))
        if verdict != "PASS" or vtree != tree:
            what = "no" if verdict is None else ("a stale" if verdict == "PASS" else f"a {verdict}")
            unmet.append(f"{what} acceptance verdict ({part}) for tree {tree[:10]}")
    return unmet, info

def ready(plan, mid, running=(), limit=1):
    """Ready tasks of a milestone: todo, needs done, writes disjoint from running and each other."""
    done_ids = {t["id"] for t in plan["tasks"].values() if t["state"] == "x"}
    busy = [task_of(plan, r)["writes"] for r in running]
    out = []
    for t in milestone(plan, mid)["tasks"] if mid else []:
        if len(out) >= limit:
            break
        if t["state"] != " " or t["id"] in running or any(n not in done_ids for n in t["needs"]):
            continue
        if any(overlap(t["writes"], w) for w in busy):
            continue
        out.append(t)
        busy.append(t["writes"])
    return out

def progress_score(ctx):
    return (sum(t["state"] == "x" for t in ctx.plan["tasks"].values())
            + sum(ctx.tagged(m["id"]) for m in ctx.plan["milestones"]))

def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}

def envelope_expired(ctx):
    data = read_json(ctx.runs / "session.json")
    if not data:
        return False
    began = data.get("started_at")
    if not isinstance(began, (int, float)):
        when = dt.datetime.fromisoformat(str(began).replace("Z", "+00:00"))
        began = (when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)).timestamp()
    return dt.datetime.now().timestamp() > float(began) + float(data.get("hours", 0)) * 3600

def cmd_lint(ctx, args):
    errs = lint(ctx)
    tasks, ms = len(ctx.plan["tasks"]), len(ctx.plan["milestones"])
    print("".join(f"lint: {e}\n" for e in errs)
          + f"lint: {'FAIL' if errs else 'PASS'} · {ms} milestone(s), {tasks} task(s), {len(errs)} finding(s)")
    return 1 if errs else 0

def cmd_status(ctx, args):
    active = ctx.active()
    data = {"goal": ctx.goal, "title": ctx.plan["meta"].get("title", ""), "plan": ctx.plan_rel,
            "active": active, "next": [t["id"] for t in ready(ctx.plan, active)],
            "milestones": [{"id": m["id"], "title": m["title"], "tagged": ctx.tagged(m["id"]),
                            "tasks": [{k: t[k] for k in ("id", "state", "title", "needs", "covers")}
                                      for t in m["tasks"]]} for m in ctx.plan["milestones"]]}
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"Goal {data['goal']}: {data['title']}  ({data['plan']})")
    for m in data["milestones"]:
        n = sum(t["state"] == "x" for t in m["tasks"])
        state = "tagged" if m["tagged"] else ("active" if m["id"] == data["active"] else "pending")
        print(f"{m['id']} — {m['title']}  [{state}, {n}/{len(m['tasks'])} done]")
        for t in m["tasks"]:
            print(f"  [{t['state']}] {t['id']} — {t['title']}  (covers {', '.join(t['covers'])})")
    print(f"Next ready: {', '.join(data['next']) or 'none'}")
    return 0

def cmd_next(ctx, args):
    tasks = ready(ctx.plan, ctx.active(), args.running or (), args.limit)
    for t in tasks:
        print(f"{t['id']} — {t['title']}  (covers {', '.join(t['covers'])})")
    if not tasks:
        print("no ready task")
    return 0 if tasks else 1

def cmd_guard(ctx, args):
    found = guard(ctx, task_of(ctx.plan, args.task), args.base or "HEAD")
    for f in found:
        print(f"guard: {f}")
    print(f"guard {args.task}: {'FAIL' if found else 'PASS'} · {len(found)} finding(s)")
    return 1 if found else 0

def cmd_done(ctx, args):
    unmet, info = done(ctx, args.milestone)
    for u in unmet:
        print(f"not done: {u}")
    if info["milestone"] is None:
        print(f"goal {ctx.goal}: {'NOT DONE' if unmet else 'DONE'}; every milestone is tagged"
              + (", but re-verification against the tags failed" if unmet else " and verified"))
        return 1 if unmet else 0
    print(f"{info['milestone']}: {'NOT DONE' if unmet else 'DONE'} on tree {info['tree']}")
    return 1 if unmet else 0

def cmd_stop_hook(args):
    """Block a chief's stop while the active milestone is unfinished; never break the host."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        if os.environ.get("GOAL_ROLE", "chief") not in ("", "chief"):
            return 0
        root = Path(os.path.realpath(git(event.get("cwd") or os.getcwd(), "rev-parse", "--show-toplevel")))
        if not (root / ".runs" / "active").is_file() or (root / RUNTIME_PIN).exists():
            return 0
        ctx = find_ctx(argparse.Namespace(plan=None, goal=None), cwd=str(root))
        state_path = ctx.runs / "stop_state.json"
        mid = ctx.active()
        # With every milestone tagged, done() re-verifies them all against their tags, as the driver does.
        unmet = done(ctx, mid)[0]
        remaining = [t for t in (milestone(ctx.plan, mid)["tasks"] if mid else []) if t["state"] != "x"]
        if not unmet or (remaining and all(t["state"] == "!" for t in remaining)) \
                or envelope_expired(ctx):
            state_path.unlink(missing_ok=True)
            return 0
        score, state = progress_score(ctx), read_json(state_path)
        session = event.get("session_id")
        if state.get("session_id") != session or score > state.get("progress", -1):
            state = {"session_id": session, "blocks": 0, "progress": score}
        if state["blocks"] >= 3:
            with open(ctx.runs / "progress.md", "a") as fh:
                fh.write(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ} STALLED {mid or 'goal'}: "
                         "3 stop-hook blocks without progress\n")
            state_path.unlink(missing_ok=True)
            return 0
        state["blocks"] += 1
        ctx.runs.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state) + "\n")
        nxt = [f"{t['id']} (covers {', '.join(t['covers'])})" for t in ready(ctx.plan, mid)] or ["none"]
        reason = (f"Goal {ctx.goal}: {ctx.plan['meta'].get('title', '')}. "
                  f"Not done: {'; '.join(unmet[:3])}. Next ready: {nxt[0]}.")
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    except Exception as exc:  # the hook must never take the host session down
        print(f"goal.py stop-hook: allowing stop after internal error: {exc!r}", file=sys.stderr)
        return 0

def diff_split(ctx, base, commit):
    split = {k: [0, 0] for k in ("product", "tests", "docs")}
    for line in git(ctx.root, "diff", "--numstat", base, commit).splitlines():
        add, rem, path = line.split("\t", 2)
        kind = "tests" if is_test(path) else ("docs" if path.endswith(".md") or path.startswith("docs/")
                                              else "product")
        split[kind][0] += int(add) if add.isdigit() else 0
        split[kind][1] += int(rem) if rem.isdigit() else 0
    return " · ".join(f"{k} +{a:,}/−{r:,}" for k, (a, r) in split.items())

def cmd_evidence(ctx, args):
    unmet, info = done(ctx, args.milestone)
    plan, mid, tree, base = info["plan"], info["milestone"], info["tree"], info["base"]
    m, meta, guards = milestone(plan, mid), plan["meta"], info["guards"]

    def run_text(cmd):
        r = info["receipts"].get(cmd)
        known = f" (baseline {len(r['baseline_failures'])})" if r and r.get("baseline_failures") else ""
        return "no receipt" if r is None else (f"{r['verdict']} · exit {r['exit']} · {r['executed']:,} run"
                                               f" / {r['failed']} failed / {r['skipped']} skipped{known}")
    count = lambda kind: sum(f.startswith(kind) for _c, _t, fs in guards for f in fs)  # noqa: E731
    reviews = []
    for part in m["acceptance"]:
        verdict, vtree, head = read_verdict(verdict_file(ctx, mid, part))
        who = " ".join(head.get(k, "") for k in ("vendor", "model", "effort")).strip() or "—"
        reviews.append(f"{part}: {verdict or 'none'}{'' if vtree == tree else ' (other tree)'} · {who}"
                       f" · rounds {head.get('round', '—')}")
    sec = [f"{t['id']} {read_verdict(ctx.runs / 'verdicts' / (t['id'] + '-security.md'))[0] or 'none'}"
           for t in m["tasks"] if t["risk"] == "safety"]
    before = set(ctx.plan_at(base)["decisions"]) if rev_exists(ctx.root, base) else set()
    dec = [d for d in plan["decisions"] if d.startswith("- ") and d not in before]
    kinds = {k: sum(k in d.lower() for d in dec) for k in ("advisor", "council")}
    usage = [u.strip() for u in (file_at(ctx.runs, None, "progress.md") or "").splitlines() if "usage:" in u]
    base_sha = git(ctx.root, "rev-parse", f"{base}^{{commit}}", check=False) or base
    lines = [
        f"{mid} — {'NOT READY' if unmet else 'READY'}        base {base_sha[:10]} → tree {tree[:10]}",
        "Criteria: " + " · ".join(f"{', '.join(p['acs'])} → " + (
            f"{p['cmd']} → {run_text(p['cmd'])}" if p["kind"] == "run" else "manual") for p in m["proofs"]),
        f"Gate: {meta.get('full_gate')} → {run_text(meta.get('full_gate'))}",
        f"E2E: {meta.get('e2e')} → {run_text(meta.get('e2e'))}",
        f"Guard: scope {count('scope')} escapes · tests {count('tests')} unapproved edits · frozen "
        f"inputs {'changed' if count('frozen') else 'unchanged'} ({len(guards)} task commits)",
        "Review: " + " | ".join(reviews),
        "Security: " + (", ".join(sec) if sec else "not triggered"),
        f"Decisions taken: {len(dec)} ({len(dec) - kinds['advisor'] - kinds['council']} default, "
        f"{kinds['advisor']} advisor, {kinds['council']} council)",
        "Diff: " + diff_split(ctx, base, info["commit"]),
        "Usage: " + (" · ".join(usage) if usage else "—"),
    ]
    lines += (["", "Unmet:"] + [f"- {u}" for u in unmet]) * bool(unmet)
    lines += (["", "Decisions:"] + dec) * bool(dec)
    out = ctx.runs / f"{mid}-evidence.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"evidence: {out}")
    return 0

def cmd_attempt(ctx, args):
    path = ctx.runs / "attempts.json"
    data = read_json(path)
    task_of(ctx.plan, args.task)
    if not args.get:
        data[args.task] = 0 if args.reset else data.get(args.task, 0) + 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
    print(data.get(args.task, 0))
    return 0

def cmd_start(args):
    root = Path(os.path.realpath(git(os.getcwd(), "rev-parse", "--show-toplevel")))
    ctx = Ctx(root, Path(os.getcwd()) / args.plan)
    if ctx.goal != args.goal:
        raise PlanError(f"plan goal is {ctx.goal}, not {args.goal}")
    (root / ".runs").mkdir(exist_ok=True)
    (root / ".runs" / "active").write_text(json.dumps({"goal": ctx.goal, "plan": ctx.plan_rel}) + "\n")
    print(f"active: {ctx.goal} ({ctx.plan_rel})")
    return 0

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)  # --plan/--goal before or after the subcommand
    for opt in ("--plan", "--goal"):
        common.add_argument(opt, default=argparse.SUPPRESS)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[common])
    sub = ap.add_subparsers(dest="action", required=True)
    p = {name: sub.add_parser(name, parents=[] if name == "start" else [common]) for name in (
        "lint", "status", "next", "guard", "done", "stop-hook", "evidence", "attempt", "start", "stop")}
    p["status"].add_argument("--json", action="store_true")
    p["next"].add_argument("--limit", type=int, default=1)
    p["next"].add_argument("--running", action="append")
    for name in ("guard", "attempt"):
        p[name].add_argument("--task", required=True)
    p["guard"].add_argument("--base")
    p["done"].add_argument("--milestone")
    p["evidence"].add_argument("--milestone", required=True)
    p["attempt"].add_argument("--reset", action="store_true")
    p["attempt"].add_argument("--get", action="store_true")
    for opt in ("--goal", "--plan"):
        p["start"].add_argument(opt, required=True)
    args = ap.parse_args(argv)
    args.plan, args.goal = getattr(args, "plan", None), getattr(args, "goal", None)
    if args.action == "stop-hook":
        return cmd_stop_hook(args)
    try:
        root = Path(git(os.getcwd(), "rev-parse", "--show-toplevel"))
        if (root / RUNTIME_PIN).exists():
            print(f"goal.py: {MIGRATE_NOTICE}", file=sys.stderr)
            return 2
        if args.action == "start":
            return cmd_start(args)
        if args.action == "stop":
            (root / ".runs" / "active").unlink(missing_ok=True)
            print("active goal cleared")
            return 0
        ctx = find_ctx(args)
        return globals()["cmd_" + args.action.replace("-", "_")](ctx, args)
    except (PlanError, RuntimeError, OSError, ValueError) as exc:
        print(f"goal.py: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
