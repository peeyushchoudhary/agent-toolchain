#!/usr/bin/env python3
"""Goal state computed from docs/goals/<id>/plan.md and git: lint, status, next, resume, packet, done.

The plan is --plan, else docs/goals/<--goal>/plan.md, else the one plan whose last milestone is not
tagged goal/<id>/<Mn>. `stop-hook` is the harness Stop hook; it never fails the host session.
Exit codes: 0 ok or done, 1 finding or not done, 2 usage or internal error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import git, receipt_path  # noqa: E402

KEYS = ("goal", "title", "gate", "full_gate", "milestones", "touches", "protected")
TASK_RE = re.compile(r"^###\s+\[([ x!])\]\s+(T\d+)\s+[—–-]+\s*(.*)$")
FIELD_RE = re.compile(r"^(writes|tests-may-change):\s*(.*)$")
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)src/test/|(^|/)test_[^/]*\.py$"
                     r"|_(test|spec)\.[^/.]+$|\.(test|spec)\.[^/]+$|Tests?\.(java|kt|cs|swift)$")
SKIP_RE = re.compile(r"\bunittest\.(skip\w*|expectedFailure)\b|@(skip|skipIf|skipUnless)\s*\(|@expectedFailure\b"
                     r"|\.skipTest\(|\bpytest\.(skip|xfail)\("
                     r"|\bpytest\.mark\.(skip|skipif|xfail)\b|\.only\s*\(|\b(it|describe|test)\.skip\s*\("
                     r"|\bx(it|describe)\(|@Disabled\b|@Ignore\b")
RUNTIME_PIN = "docs/agents/execution/runtime.json"
MIGRATE_NOTICE = (f"this project still carries the v5.1 runtime pin ({RUNTIME_PIN}); "
                  "migrate it first, following references/migrate.md")

class PlanError(Exception):
    pass

class SeveralPlans(PlanError):
    pass

def flow(text: str):
    """Parse a YAML-ish flow value: {k: v, ...}, [a, b], "quoted" or a bare scalar."""
    def value(i):
        while text[i:i + 1].isspace():
            i += 1
        ch = text[i:i + 1]
        if ch in "[{":
            close, out, i = "]" if ch == "[" else "}", [] if ch == "[" else {}, i + 1
            while True:
                while text[i:i + 1] in (" ", ","):
                    i += 1
                if text[i:i + 1] in (close, ""):
                    return out, i + 1
                if close == "]":
                    item, i = value(i)
                    out.append(item)
                else:
                    key, _, _ = text[i:].partition(":")
                    item, i = value(i + len(key) + 1)
                    out[key.strip()] = item
        if ch in "\"'":
            # "..." takes \" and \\ escapes; '...' takes '' for a quote. Anything else is literal.
            out, i = [], i + 1
            while i < len(text):
                c = text[i]
                if ch == '"' and c == "\\" and text[i + 1:i + 2] in ('"', "\\"):
                    out.append(text[i + 1])
                    i += 2
                elif c == ch and ch == "'" and text[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                elif c == ch:
                    return "".join(out), i + 1
                else:
                    out.append(c)
                    i += 1
            raise ValueError(f"unterminated quoted value: {text}")
        m = re.match(r"[^,\]}]*", text[i:])
        return m.group(0).strip(), i + m.end()
    return value(0)[0]

def parse_plan(text: str) -> dict:
    """Frontmatter, sections, tasks (with writes and tests-may-change), Decisions and Parked."""
    plan = {"meta": {}, "milestones": {}, "sections": {}, "tasks": {}, "errors": []}
    lines = (text or "").splitlines()
    if lines and lines[0].strip() == "---" and "---" in [l.strip() for l in lines[1:]]:
        end = 1 + [l.strip() for l in lines[1:]].index("---")
        key = None
        for line in lines[1:end]:
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                plan["meta"][key] = flow(val) if val[:1] in "[{\"'" else val if val else {}
            elif key == "milestones" and line.strip():
                mid, _, val = line.strip().partition(":")
                plan["meta"][key][mid.strip()] = flow(val.strip())
        lines = lines[end + 1:]
    for mid, spec in (plan["meta"].get("milestones") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        plan["milestones"][mid] = {"tasks": list(spec.get("tasks") or []), "e2e": spec.get("e2e") or ""}
    section, task = None, None
    for line in lines:
        if line.startswith("## "):
            section, task = line[3:].strip().split(" (")[0].strip(), None
            plan["sections"].setdefault(section, [])
            continue
        if section is None:
            continue
        plan["sections"][section].append(line)
        m = TASK_RE.match(line)
        if section == "Tasks" and m:
            task = {"id": m.group(2), "state": m.group(1), "title": m.group(3).strip(),
                    "writes": [], "tests-may-change": []}
            if task["id"] in plan["tasks"]:
                plan["errors"].append(f"duplicate task id {task['id']}")
            plan["tasks"][task["id"]] = task
        elif section == "Tasks" and line.startswith("### "):
            plan["errors"].append(f"malformed task header: {line.strip()}")
        elif task is not None and (f := FIELD_RE.match(line)):
            task[f.group(1)] = [x.strip() for x in f.group(2).split(",") if x.strip()]
    for name in ("Decisions", "Parked"):
        plan[name.lower()] = [l for l in plan["sections"].get(name, []) if l.strip()]
    return plan

def frozen_view(text) -> str:
    """The plan with ticks normalised, writes/tests-may-change lines and Decisions/Parked bodies dropped."""
    out, skip = [], False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            skip = line[3:].strip() in ("Decisions", "Parked")
        elif skip or FIELD_RE.match(line):
            continue
        out.append(re.sub(r"^(###\s+)\[[ x!]\]", r"\1[ ]", line))
    return "\n".join(out).rstrip()

def widenings(old, new):
    """['T5 tests-may-change: a -> a, b'] for every writes/tests-may-change field that differs."""
    return [f"{tid} {k}: {', '.join(old['tasks'].get(tid, {}).get(k, [])) or '(none)'} -> {', '.join(t[k]) or '(none)'}"
            for tid, t in new["tasks"].items() for k in ("writes", "tests-may-change")
            if t[k] != old["tasks"].get(tid, {}).get(k, [])]

def adds_decision(old, new) -> bool:
    return bool(Counter(new["decisions"]) - Counter(old["decisions"]))

def glob_re(pattern: str):
    """'**' spans directories, '*' and '?' stay within one segment, anything else is literal."""
    tr = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", pattern + ("**" if pattern.endswith("/") else ""))
    return re.compile("".join(tr.get(p, re.escape(p)) for p in parts) + r"\Z")

def matches(path, patterns):
    return any(glob_re(p).match(path) for p in patterns)

def overlap(a_globs, b_globs) -> bool:
    """True when two write sets could name a common path (conservative for two globs)."""
    def static(p):
        segs = p.split("/")
        k = next((i for i, s in enumerate(segs) if "*" in s or "?" in s), len(segs))
        return segs[:k], k == len(segs)
    for a in a_globs:
        for b in b_globs:
            (sa, ea), (sb, eb) = static(a), static(b)
            n = min(len(sa), len(sb))
            if (a == b if ea and eb else bool(glob_re(b if ea else a).match(a if ea else b)) if ea or eb
                    else sa[:n] == sb[:n]):
                return True
    return False

def path_protected(plan):
    # An entry with a '#section' anchor protects part of a file, which a path glob cannot judge;
    # lint and the writes check compare only whole-path entries, and row 4 compares anchored
    # entries' sections commit by commit (anchored_protected, protected_text).
    return [p for p in plan["meta"].get("protected") or [] if isinstance(p, str) and "#" not in p]

def anchored_protected(plan):
    """[(path, anchor)] for protected entries like 'docs/x.md#D1-D19' or 'docs/x.md#D4'."""
    return [tuple(p.split("#", 1)) for p in plan["meta"].get("protected") or [] if isinstance(p, str) and "#" in p]

def protected_text(text, anchor):
    """The '## ' sections of text that anchor names (D1-D19 spans ## D1 … ## D19); an anchor of
    any other shape protects the whole file."""
    m = re.match(r"^([A-Za-z]+)(\d+)(?:-(?:\1)?(\d+))?$", anchor)
    out, keep = [], m is None
    for line in (text or "").splitlines():
        h = re.match(r"^#{1,2}\s+(.*)$", line)
        if h and m:
            n = re.match(rf"{re.escape(m.group(1))}(\d+)\b", h.group(1))
            keep = bool(n) and int(m.group(2)) <= int(n.group(1)) <= int(m.group(3) or m.group(2))
        if keep:
            out.append(line)
    return "\n".join(out)

def file_at(root, rev, path):
    proc = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=root, capture_output=True)
    return proc.stdout.decode(errors="replace") if proc.returncode == 0 else None

def rev_ok(root, rev):
    return bool(git(root, "rev-parse", "-q", "--verify", f"{rev}^{{commit}}", check=False))

def changes(root, parent, commit):
    """[(status, path)] for one commit (a root commit diffs against the empty tree)."""
    out = git(root, "diff-tree", "-r", "--root", "--no-commit-id", "--name-status", "--no-renames",
              "-z", *([parent, commit] if parent else [commit]))
    parts = out.split("\0")
    return [(parts[k][0], parts[k + 1]) for k in range(0, len(parts) - 1, 2) if parts[k]]

class Ctx:
    def __init__(self, root: Path, plan_path: Path):
        if not plan_path.is_file():
            raise PlanError(f"plan not found: {plan_path}")
        self.root = root
        self.plan_rel = plan_path.resolve().relative_to(root).as_posix()
        self.plan = parse_plan(plan_path.read_text())
        self.goal = str(self.plan["meta"].get("goal") or "")
        if not self.goal:
            raise PlanError(f"{self.plan_rel}: frontmatter has no goal")
        self.runs = root / ".runs" / self.goal

    def tag(self, name):
        return f"goal/{self.goal}/{name}"

    def active(self):
        return next((m for m in self.plan["milestones"] if not rev_ok(self.root, self.tag(m))), None)

    def plan_at(self, rev):
        return parse_plan(file_at(self.root, rev, self.plan_rel) or "")

def find_ctx(plan=None, goal=None, cwd=None) -> Ctx:
    root = Path(os.path.realpath(git(cwd or os.getcwd(), "rev-parse", "--show-toplevel")))
    if (root / RUNTIME_PIN).exists():
        raise PlanError(MIGRATE_NOTICE)
    if plan:
        return Ctx(root, Path(cwd or os.getcwd()) / plan)
    if goal:
        return Ctx(root, root / "docs" / "goals" / goal / "plan.md")
    open_ = [c for c in (Ctx(root, p) for p in sorted(root.glob("docs/goals/*/plan.md")))
             if c.active() is not None]
    if len(open_) != 1:
        raise (SeveralPlans if open_ else PlanError)(f"{len(open_)} open plans under docs/goals/; pass --goal or --plan")
    return open_[0]

def lint(ctx):
    plan, errs = ctx.plan, list(ctx.plan["errors"])
    errs += [f"frontmatter: {k} is missing" for k in KEYS if k not in plan["meta"]]
    named = {t for m in plan["milestones"].values() for t in m["tasks"]}
    errs += [f"{t}: in no milestone" for t in plan["tasks"] if t not in named]
    for mid, m in plan["milestones"].items():
        errs += [f"{mid}: names missing task {t}" for t in m["tasks"] if t not in plan["tasks"]]
        errs += [f"{mid}: no e2e"] if not m["e2e"] else []
    for t in plan["tasks"].values():
        errs += [f"{t['id']}: no writes"] if not t["writes"] else []
        if overlap(t["writes"], path_protected(plan)):
            errs.append(f"{t['id']}: writes intersect protected")
    return errs

def plan_only(ctx, subject, ch, plan_same) -> bool:
    """Row 3's plan-only commit: subject '<id>:', only plan.md changed, its frozen view unchanged."""
    return subject.startswith(f"{ctx.goal}:") and plan_same and all(p == ctx.plan_rel for _s, p in ch)

def commit_plan_only(ctx, c):
    parent = git(ctx.root, "rev-parse", "-q", "--verify", f"{c}^1", check=False)
    same = frozen_view(file_at(ctx.root, parent, ctx.plan_rel) if parent else "") == \
        frozen_view(file_at(ctx.root, c, ctx.plan_rel))
    return plan_only(ctx, git(ctx.root, "log", "-1", "--format=%s", c), changes(ctx.root, parent, c), same)

def commit_findings(ctx, base):
    """Rows 3, 4 and 5 over every commit in base..HEAD."""
    rows = {3: [], 4: [], 5: []}
    for c in git(ctx.root, "rev-list", "--reverse", f"{base}..HEAD").split():
        subject, short = git(ctx.root, "log", "-1", "--format=%s", c), c[:10]
        parent = git(ctx.root, "rev-parse", "-q", "--verify", f"{c}^1", check=False)
        ch = changes(ctx.root, parent, c)
        plan_same = frozen_view(file_at(ctx.root, parent, ctx.plan_rel) if parent else "") == \
            frozen_view(file_at(ctx.root, c, ctx.plan_rel))
        tids = sorted(set(re.findall(r"\[(T\d+)\]", subject)))
        before = ctx.plan_at(parent) if parent and file_at(ctx.root, parent, ctx.plan_rel) else None
        if before and widenings(before, ctx.plan_at(c)) and not adds_decision(before, ctx.plan_at(c)):
            rows[3].append(f"{short} changes writes or tests-may-change without adding a Decisions line")
        if len(tids) != 1:
            if not plan_only(ctx, subject, ch, plan_same):
                rows[3].append(f"{short} names {len(tids)} tasks and is not plan-only")
            continue
        # Writes are judged at the parent, so a later widening cannot excuse an earlier escape. The
        # one exception: a commit whose parent has no plan (the commit that adds it) is read at itself.
        plan = before or ctx.plan_at(c)
        task = plan["tasks"].get(tids[0])
        if task is None:
            rows[4].append(f"{short} names {tids[0]}, which its parent's plan does not have")
            continue
        for status, path in ch:
            for ppath, anchor in anchored_protected(plan):
                if glob_re(ppath).match(path) and protected_text(file_at(ctx.root, parent, path) if parent else "",
                                                                 anchor) != protected_text(file_at(ctx.root, c, path), anchor):
                    rows[4].append(f"{short} [{tids[0]}] changes protected {ppath}#{anchor}")
            if path == ctx.plan_rel and plan_same:
                continue  # ticks and writes lines; the frozen view is row 6's to judge
            if not matches(path, task["writes"]):
                rows[4].append(f"{short} [{tids[0]}] {path} outside writes")
            if TEST_RE.search(path) and status in "MDT" and not matches(path, task["tests-may-change"]):
                rows[5].append(f"{short} {'deletes' if status == 'D' else 'modifies'} test {path}")
            if TEST_RE.search(path) and status != "D":
                diff = git(ctx.root, "diff", "-U0", parent or "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                           c, "--", path)
                if any(l.startswith("+") and SKIP_RE.search(l) for l in diff.splitlines()):
                    rows[5].append(f"{short} adds a skip/only/xfail marker in {path}")
    if overlap([w for t in ctx.plan_at("HEAD")["tasks"].values() for w in t["writes"]],
               path_protected(ctx.plan_at("HEAD"))):
        rows[4].append("a writes glob at HEAD intersects protected")
    return rows

def review_findings(ctx):
    path = ctx.runs / "review.md"
    if not path.is_file():
        return [f"no {path.relative_to(ctx.root)}"]
    text, out = path.read_text(), []
    m = re.search(r"^reviewed:\s*(\S+)", text, re.M)
    if not m or not rev_ok(ctx.root, m.group(1)) or subprocess.run(
            ["git", "merge-base", "--is-ancestor", m.group(1), "HEAD"], cwd=ctx.root).returncode:
        return ["review.md has no reviewed: <sha> that is HEAD or its ancestor"]
    out += ["an open - [ ] BLOCKING finding"] if re.search(r"^\s*- \[ \] BLOCKING\b", text, re.M) else []
    closed = {}  # commit sha -> finding id, for every closure that holds
    lines = text.splitlines()
    for k, line in enumerate(lines):
        f = re.match(r"^\s*- \[x\] (R\d+) (resolved|removed)-by (\S+)(?: closes (\S+?)::(\S+))?", line)
        if not f:
            continue
        rid, kind, sha = f.group(1), f.group(2), f.group(3)
        full = git(ctx.root, "rev-parse", "-q", "--verify", f"{sha}^{{commit}}", check=False)
        if not full:
            out.append(f"{rid}: {sha} is not a commit")
            continue
        ch = changes(ctx.root, git(ctx.root, "rev-parse", "-q", "--verify", f"{full}^1", check=False), full)
        if kind == "resolved":
            test, name = f.group(4), f.group(5)
            body = file_at(ctx.root, "HEAD", test) if test else None
            defines = body is not None and re.search(
                rf"^\s*(async\s+)?def {re.escape(name)}\(|\b(it|test)\(\s*['\"]{re.escape(name)}", body, re.M)
            if not (test and TEST_RE.search(test) and defines and test in [p for _s, p in ch]):
                out.append(f"{rid}: closes {test}::{name}, which is absent at HEAD or not changed by {sha}")
                continue
        else:
            listed = next((l.split(":", 1)[1] for l in lines[k + 1:k + 6] if l.strip().startswith("paths:")), "")
            listed = [p.strip() for p in listed.split(",") if p.strip()]
            parent = git(ctx.root, "rev-parse", "-q", "--verify", f"{full}^1", check=False)

            def removes(s, q):  # deleted, or modified with lines removed and none added
                num = git(ctx.root, "diff", "--numstat", parent, full, "--", q).split() if s == "M" and parent else []
                return s == "D" or (len(num) >= 2 and num[0] == "0" and num[1] not in ("0", "-"))
            hits = {p: [(s, q) for s, q in ch if glob_re(p).match(q)] for p in listed}
            if not listed or not all(hits[p] and all(removes(s, q) for s, q in hits[p]) for p in listed):
                out.append(f"{rid}: {sha} does not remove or change the finding's paths")
                continue
        closed[full] = rid
    for rid in re.findall(r"^\s*- \[x\] BLOCKING (R\d+)\b", text, re.M):
        if rid not in closed.values():
            out.append(f"{rid}: checked BLOCKING without a resolved-by or removed-by closure that holds")
    for c in git(ctx.root, "rev-list", "--reverse", f"{m.group(1)}..HEAD").split():
        subject = git(ctx.root, "log", "-1", "--format=%s", c)
        fix = re.search(r"\[T\d+\]\[(R\d+)\]", subject)
        if (not fix or closed.get(c) != fix.group(1)) and not commit_plan_only(ctx, c):
            out.append(f"{c[:10]} after reviewed: is neither a fix commit named by a closed finding nor plan-only")
    return out

def done_rows(ctx, mid):
    """{row: [reasons]} for milestone mid on HEAD; every list empty means done."""
    plan, head = ctx.plan_at("HEAD"), "HEAD"
    m, approved = plan["milestones"].get(mid), ctx.tag("approved")
    if m is None:
        raise PlanError(f"no milestone {mid} in the plan at HEAD")
    rows = {n: [] for n in range(1, 9)}
    parked = "\n".join(plan["parked"])
    for tid in m["tasks"]:
        state = plan["tasks"].get(tid, {}).get("state")
        if state != "x" and not (state == "!" and re.search(rf"\b{tid}\b", parked)):
            rows[1].append(f"{tid} is {'parked without a Parked line' if state == '!' else 'not [x]'}")
    dirty = [l for l in git(ctx.root, "status", "--porcelain", "--untracked-files=all").splitlines()
             if not l[3:].startswith(".runs/")]
    rows[2] += [f"{len(dirty)} uncommitted path(s), first {dirty[0][3:]}"] if dirty else []
    if not rev_ok(ctx.root, approved):
        rows.update({n: [f"tag {approved} not found"] for n in (3, 4, 5, 6)})
    else:
        rows.update(commit_findings(ctx, approved))
        if frozen_view(file_at(ctx.root, approved, ctx.plan_rel)) != frozen_view(file_at(ctx.root, head, ctx.plan_rel)):
            rows[6].append(f"{ctx.plan_rel} changed outside ticks, writes, Decisions and Parked")
    tree = git(ctx.root, "rev-parse", "HEAD^{tree}")
    for label, cmd in (("full_gate", plan["meta"].get("full_gate")), ("e2e", m["e2e"])):
        path = receipt_path(ctx.root, ctx.goal, tree, cmd or "")
        r = json.loads(path.read_text()) if cmd and path.is_file() else {}
        if not (r.get("tree") == tree and r.get("command") == cmd and r.get("verdict") == "PASS"):
            rows[7].append(f"no PASS {label} receipt for tree {tree[:10]}")
    rows[8] = review_findings(ctx)
    return rows, tree

def milestone_arg(ctx, mid):
    mid = mid or ctx.active()
    if mid is None:
        raise PlanError("every milestone is tagged")
    return mid

def cmd_done(ctx, a):
    rows, tree = done_rows(ctx, mid := milestone_arg(ctx, a.milestone))
    for n, why in rows.items():
        print(f"row {n} ok" if not why else f"row {n}: {'; '.join(why[:5])}")
    print(f"DONE {mid} on tree {tree}" if not any(rows.values()) else f"NOT DONE {mid}")
    return 1 if any(rows.values()) else 0

def cmd_lint(ctx, a):
    errs = lint(ctx)
    print("".join(f"lint: {e}\n" for e in errs) + f"lint: {'FAIL' if errs else 'PASS'} · "
          f"{len(ctx.plan['milestones'])} milestone(s), {len(ctx.plan['tasks'])} task(s)")
    return 1 if errs else 0

def status_lines(ctx):
    active = ctx.active()
    for mid, m in ctx.plan["milestones"].items():
        state = "tagged" if rev_ok(ctx.root, ctx.tag(mid)) else "active" if mid == active else "pending"
        ticks = " ".join(f"[{ctx.plan['tasks'].get(t, {}).get('state', '?')}]{t}" for t in m["tasks"])
        yield f"{mid} {state}: {ticks}"

def cmd_status(ctx, a):
    return print(f"{ctx.goal}: {ctx.plan['meta'].get('title', '')}\n" + "\n".join(status_lines(ctx))) or 0

def next_task(ctx):
    mid = ctx.active()
    tasks = [ctx.plan["tasks"][t] for t in ctx.plan["milestones"].get(mid, {}).get("tasks", [])
             if t in ctx.plan["tasks"]]
    return next((t for t in tasks if t["state"] == " "), None)

def cmd_next(ctx, a):
    t = next_task(ctx)
    print(f"{t['id']} — {t['title']}" if t else "no open task in the active milestone")
    return 0 if t else 1

def cmd_resume(ctx, a):
    outcome = " ".join(l.strip() for l in ctx.plan["sections"].get("Outcome", []) if l.strip())
    t, first = next_task(ctx), re.split(r"(?<=[.!?])\s", outcome, maxsplit=1)[0]
    head = (f"Continue goal {ctx.goal}: {ctx.plan['meta'].get('title', '')}. Read {ctx.plan_rel} and the "
            f"execution-methodology skill. Next: {t['id'] + ' — ' + t['title'] if t else 'close the milestone'}. "
            "Per task: work inside its writes, run the gate, commit as [Tn] with its tick; park [!] with a "
            "Parked line when blocked. Stop when `goal.py done` prints DONE.\n"
            f"Outcome: {first}\n" + "\n".join(status_lines(ctx)))
    log = ctx.runs / "progress.md"
    tail = log.read_text().splitlines()[-20:] if log.is_file() else []
    while tail and len((head + "\n" + "\n".join(tail)).split()) > 150:
        tail.pop(0)
    text = head + ("\nProgress:\n" + "\n".join(tail) if tail else "")
    print(" ".join(text.split(" ")[:150]) if len(text.split()) > 150 else text)
    return 0

def cmd_packet(ctx, a):
    rows, tree = done_rows(ctx, mid := milestone_arg(ctx, a.milestone))
    approved, plan = ctx.tag("approved"), ctx.plan_at("HEAD")
    stat = git(ctx.root, "diff", "--stat", f"{approved}..HEAD", check=False)
    widen = [c for c in git(ctx.root, "log", "--format=%h %s", f"{approved}..HEAD", "--", ctx.plan_rel,
                            check=False).splitlines() if c.split(" ", 1)[1].startswith(f"{ctx.goal}:")]
    fields = [f"{c[:10]} {w}" for c in git(ctx.root, "rev-list", "--reverse", f"{approved}..HEAD", "--",
                                           ctx.plan_rel, check=False).split()
              if file_at(ctx.root, f"{c}^", ctx.plan_rel) for w in widenings(ctx.plan_at(f"{c}^"), ctx.plan_at(c))]
    receipts = sorted(p.name for p in (ctx.runs / "receipts").glob(f"{tree}-*.json"))
    review = ctx.runs / "review.md"
    found = [l.strip() for l in (review.read_text().splitlines() if review.is_file() else [])
             if re.match(r"^\s*- \[[ x]\] ", l)]
    out = [f"{ctx.goal}: {'DONE' if not any(rows.values()) else 'NOT DONE'} {mid} on tree {tree}", "",
           "Outcome:", *[l for l in plan["sections"].get("Outcome", []) if l.strip()], "",
           f"Diff {approved}..HEAD:", stat, "", "Done:",
           *[f"row {n} ok" if not w else f"row {n}: {'; '.join(w[:3])}" for n, w in rows.items()], "",
           "Receipts:", *(receipts or ["none"]), "", "Review findings:", *(found or ["none"]), "",
           "Decisions:", *plan["decisions"], "", "Parked:", *(plan["parked"] or ["none"]), "",
           "Widenings (writes and tests-may-change):", *(fields or ["none"]), "",
           "Plan-only commits (widenings, ticks, decisions):", *(widen or ["none"])]
    ctx.runs.mkdir(parents=True, exist_ok=True)
    (ctx.runs / "packet.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0

def stop_hook(plan=None, goal=None):
    """Block a stop while done is unmet, at most three times per session; never raise. With several
    open plans and no --goal or --plan, block once per session asking for the hook to name one."""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        try:
            ctx = find_ctx(plan, goal, cwd=event.get("cwd") or None)
        except SeveralPlans:
            root = Path(git(event.get("cwd") or os.getcwd(), "rev-parse", "--show-toplevel"))
            state_path, sid = root / ".runs" / "stop_state.json", "several:" + str(event.get("session_id", ""))
            state = json.loads(state_path.read_text()) if state_path.is_file() else {}
            if not state.get(sid):
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps({**state, sid: 1}) + "\n")
                print(json.dumps({"decision": "block",
                                  "reason": "several open plans; register the hook with --goal <id>"}))
            return 0
        rows, _ = done_rows(ctx, milestone_arg(ctx, None))
        unmet = [f"row {n}: {w[0]}" for n, w in rows.items() if w]
        state_path = ctx.runs / "stop_state.json"
        state = json.loads(state_path.read_text()) if state_path.is_file() else {}
        sid = str(event.get("session_id", ""))
        if unmet and state.get(sid, 0) < 3:
            state[sid] = state.get(sid, 0) + 1
            ctx.runs.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state) + "\n")
            print(json.dumps({"decision": "block", "reason": f"Goal {ctx.goal} is not done: "
                              + "; ".join(unmet) + ". Continue, or park the task [!] with a Parked line."}))
    except PlanError:
        pass  # no open goal here, or an unmigrated project: allow silently
    except Exception as exc:  # noqa: BLE001 — any failure allows the stop
        print(f"goal.py stop-hook: allowing stop ({exc!r})", file=sys.stderr)
    return 0

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    [common.add_argument(opt, default=argparse.SUPPRESS) for opt in ("--plan", "--goal")]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[common])
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("lint", "status", "next", "resume", "packet", "done", "stop-hook"):
        p = sub.add_parser(name, parents=[common])
        if name in ("done", "packet"):
            p.add_argument("--milestone")
    a = ap.parse_args(argv)
    if a.action == "stop-hook":
        return stop_hook(getattr(a, "plan", None), getattr(a, "goal", None))
    try:
        ctx = find_ctx(getattr(a, "plan", None), getattr(a, "goal", None))
        return globals()["cmd_" + a.action](ctx, a)
    except (PlanError, RuntimeError, OSError, ValueError) as exc:
        print(f"goal.py: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
