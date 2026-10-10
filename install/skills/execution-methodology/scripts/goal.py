#!/usr/bin/env python3
"""Goal state computed from docs/goals/<id>/plan.md and git: lint, status, next, resume, packet, done, cost.

The plan is --plan, else docs/goals/<--goal>/plan.md, else the one plan whose last milestone is not
tagged goal/<id>/<Mn>. `cost` sums the harness transcripts' tokens; it records, never enforces.
Exit codes: 0 ok or done, 1 finding or not done, 2 usage or internal error.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import git, receipt_path  # noqa: E402

KEYS = ("goal", "title", "gate", "full_gate", "milestones", "touches", "protected")
TOUCHES = ("none", "data", "auth", "external", "interface", "ui")
SPEC_HEADINGS = ("Users and problem", "What changes for the user", "Acceptance criteria", "Non-goals", "Constraints")
TASK_RE = re.compile(r"^###\s+\[([ x!])\]\s+(T\d+)\s+[—–-]+\s*(.*)$")
FIELD_RE = re.compile(r"^(writes|tests-may-change|reads):\s*(.*)$")
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)src/test/|(^|/)test_[^/]*\.py$"
                     r"|_(test|spec)\.[^/.]+$|\.(test|spec)\.[^/]+$|Tests?\.(java|kt|cs|swift)$")
SKIP_RE = re.compile(r"\bunittest\.(skip\w*|expectedFailure)\b|@(skip|skipIf|skipUnless)\s*\(|@expectedFailure\b"
                     r"|\.skipTest\s*\(|\bpytest\.(skip|xfail)\s*\("
                     r"|\bpytest\.mark\.(skip|skipif|xfail)\b|\.only\s*\(|\b(it|describe|test)\.skip\s*\("
                     r"|\bx(it|describe)\(|@Disabled\b|@Ignore\b")
# A bare skip(...) call counts only in a file that imports skip from pytest or unittest: a word
# match everywhere would also flag earlier commits' strings, and an import is what makes it a skip.
SKIP_IMPORT_RE = re.compile(r"^\s*from\s+(pytest|unittest)\s+import\s+(\([^)]*|[^\n]*)\bskip\b", re.M)
BARE_SKIP_RE = re.compile(r"(?<![\w.])skip\s*\(")
# A JUnit method closes a finding under one of these annotations, bare or qualified by a JUnit package
# (org.junit. is JUnit 4, whose only one is Test); no other qualifier counts.
JUNIT_TEST_ANNOTATIONS = ("Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate")
JUNIT_PACKAGES = ("org.junit.jupiter.api.", "org.junit.jupiter.params.", "org.junit.")
RUNTIME_PIN = "docs/agents/execution/runtime.json"
MIGRATE_NOTICE = (f"this project still carries the v5.1 runtime pin ({RUNTIME_PIN}); "
                  "migrate it first, following docs/runbooks/migrate-v5.md")

class PlanError(Exception):
    pass

class SeveralPlans(PlanError):
    pass

def flow(text: str):
    """Parse a YAML-ish flow value: {k: v, ...}, [a, b], "quoted" or a bare scalar. ValueError when a
    bracket is left open or text follows the value, so `"true" && false` is not read as `true`."""
    def value(i):
        while text[i:i + 1].isspace():
            i += 1
        ch = text[i:i + 1]
        if ch and ch in "[{":
            close, out, i = "]" if ch == "[" else "}", [] if ch == "[" else {}, i + 1
            while True:
                while text[i:i + 1] in (" ", ","):
                    i += 1
                if text[i:i + 1] == "":
                    raise ValueError(f"unterminated {ch} in: {text}")
                if text[i:i + 1] == close:
                    return out, i + 1
                if close == "]":
                    item, i = value(i)
                    out.append(item)
                else:
                    key, colon, _ = text[i:].partition(":")
                    if not colon:
                        raise ValueError(f"no ':' after {key.strip()!r} in: {text}")
                    item, i = value(i + len(key) + 1)
                    out[key.strip()] = item
        if ch and ch in "\"'":
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
    out, end = value(0)
    if text[end:].strip():
        raise ValueError(f"text after the value: {text}")
    return out

def parse_plan(text: str) -> dict:
    """Frontmatter, sections, tasks (with writes, tests-may-change and reads), Decisions and Parked."""
    plan = {"meta": {}, "milestones": {}, "sections": {}, "tasks": {}, "errors": []}
    lines = (text or "").splitlines()
    if lines and lines[0].strip() == "---" and "---" in [l.strip() for l in lines[1:]]:
        end = 1 + [l.strip() for l in lines[1:]].index("---")
        key = None
        for n, line in enumerate(lines[1:end], 2):
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            try:
                if m:
                    key, val = m.group(1), m.group(2).strip()
                    plan["meta"][key] = flow(val) if val and val[0] in "[{\"'" else val if val else {}
                elif key == "milestones" and line.strip():
                    mid, _, val = line.strip().partition(":")
                    plan["meta"].setdefault(key, {})[mid.strip()] = {}  # stays empty if malformed
                    plan["meta"][key][mid.strip()] = flow(val.strip())
            except ValueError as exc:  # a malformed key stays unset; lint names the line
                plan["errors"].append(f"line {n}: {exc}")
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
                    "writes": [], "tests-may-change": [], "reads": []}
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
    """The plan with ticks normalised, Decisions/Parked bodies dropped, and writes/tests-may-change/reads
    lines dropped only where parse_plan reads them: under a task header in Tasks."""
    out, skip, section, task = [], False, None, False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            section, task = line[3:].strip().split(" (")[0].strip(), False
            skip = section in ("Decisions", "Parked")
        elif skip or (task and FIELD_RE.match(line)):
            continue
        task = task or (section == "Tasks" and bool(TASK_RE.match(line)))
        out.append(re.sub(r"^(###\s+)\[[ x!]\]", r"\1[ ]", line))
    return "\n".join(out).rstrip()

def widenings(old, new):
    """['T5 tests-may-change: a -> a, b'] for every writes/tests-may-change/reads field that differs."""
    return [f"{tid} {k}: {', '.join(old['tasks'].get(tid, {}).get(k, [])) or '(none)'} -> {', '.join(t[k]) or '(none)'}"
            for tid, t in new["tasks"].items() for k in ("writes", "tests-may-change", "reads")
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

def goal_has(ctx, name):
    """docs/goals/<id>/<name> when it is in the working tree or at the approval tag, else None."""
    rel = (Path(ctx.plan_rel).parent / name).as_posix()
    return rel if (ctx.root / rel).is_file() or file_at(ctx.root, ctx.tag("approved"), rel) is not None else None

def protected_entries(plan, ctx=None):
    """The plan's protected entries plus a v7.1 goal's unlisted defaults: spec.md whole, and
    design.md's Interfaces and Data touched sections when the page exists."""
    out = [p for p in plan["meta"].get("protected") or [] if isinstance(p, str)]
    if getattr(ctx, "root", None) is not None and (spec := goal_has(ctx, "spec.md")):
        design = goal_has(ctx, "design.md")
        out += [spec] + ([f"{design}#interfaces", f"{design}#data-touched"] if design else [])
    return list(dict.fromkeys(out))

def path_protected(plan, ctx=None):
    # An entry with a '#section' anchor protects part of a file, which a path glob cannot judge;
    # lint and the HEAD writes check compare only whole-path entries. Row 4 also judges every entry,
    # whole or anchored (protected_text), commit by commit against the plan at the commit's parent.
    return [p for p in protected_entries(plan, ctx) if "#" not in p]

def slug(heading: str) -> str:
    """The GitHub heading anchor; its one home is docs.py, which imports this module, so the import is late."""
    from docs import slug as rule
    return rule(heading)

def protected_text(text, anchor):
    """The sections of text that anchor names: D1-D19 spans ## D1 … ## D19; a heading slug spans that
    heading to the next heading of the same or a higher level; an anchor naming no heading, the file."""
    m = re.match(r"^([A-Za-z]+)(\d+)(?:-(?:\1)?(\d+))?$", anchor)
    out, keep, fence = [], 0, None
    lines = (text or "").splitlines()
    for line in lines:
        s = line.lstrip()  # a ``` or ~~~ fence hides headings until its own marker closes it
        fence = (None if s.startswith(fence) else fence) if fence else (s[:3] if s.startswith(("```", "~~~")) else None)
        if m:
            h = None if fence else re.match(r"^#{1,2}\s+(.*)$", line)
            n = h and re.match(rf"{re.escape(m.group(1))}(\d+)\b", h.group(1))
            keep = (bool(n) and int(m.group(2)) <= int(n.group(1)) <= int(m.group(3) or m.group(2))) if h else keep
        else:  # keep is the open section's heading level, 0 outside it
            h = None if fence else re.match(r"^(#{1,6})\s+(.*?)\s*#*$", line)
            if h and (not keep or len(h.group(1)) <= keep):
                keep = len(h.group(1)) if slug(h.group(2)) == anchor else 0
        if keep:
            out.append(line)
    return "\n".join(out if out or m else lines)

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
        if overlap(t["writes"], path_protected(plan, ctx)):
            errs.append(f"{t['id']}: writes intersect protected")
    return errs + (spec_lint(ctx) if getattr(ctx, "root", None) is not None else [])

def spec_lint(ctx):
    """A goal with docs/goals/<id>/spec.md in the working tree is a v7.1 goal: every task with writes
    has reads, touches is valid and backed by design.md, the spec is in shape and its ACn are traced.
    A goal with neither a spec nor an approval tag is a new goal without its spec."""
    plan, goal_dir = ctx.plan, ctx.root / Path(ctx.plan_rel).parent
    spec_rel = str(Path(ctx.plan_rel).parent / "spec.md")
    if not (goal_dir / "spec.md").is_file():  # approved with a spec: it stays required (Interface 1)
        if not rev_ok(ctx.root, ctx.tag("approved")):
            return ["no spec.md and no approval tag: a new goal needs a spec"]
        return [f"{spec_rel}: in the approved commit, missing from the tree"] if file_at(
            ctx.root, ctx.tag("approved"), spec_rel) is not None else []
    text, errs = (goal_dir / "spec.md").read_text(), []
    errs += [f"{t['id']}: writes and no reads" for t in plan["tasks"].values() if t["writes"] and not t["reads"]]
    touches = plan["meta"].get("touches")
    if touches is not None and not isinstance(touches, (list, str)):
        errs.append(f"touches: {touches!r} is not a list")
    touches = touches if isinstance(touches, list) else [touches] if isinstance(touches, str) and touches else []
    errs += [f"touches: unknown value {v!r}" for v in touches if v not in TOUCHES]
    if any(v != "none" for v in touches) and not (goal_dir / "design.md").is_file():
        errs.append(f"touches: [{', '.join(map(str, touches))}] without design.md")
    words, plain = len(text.split()), text.replace("*", "")
    errs += [f"spec.md: {words} words, over 400"] if words > 400 else []
    short = re.search(r"^What changes for the user:\s*nothing\b", plain, re.M)
    if not short:
        errs += [f"spec.md: no {h} heading" for h in SPEC_HEADINGS if not re.search(rf"^(#+\s*)?{h}\b", plain, re.M)]
    elif not plain[short.end():].strip(" .\t\n"):  # the two-line form names the goal's tests on line two
        errs.append("spec.md: two-line form with no criteria line")
    tasks = plan["sections"].get("Tasks", [])
    body = "\n".join(tasks[next((k for k, l in enumerate(tasks) if TASK_RE.match(l)), len(tasks)):])
    errs += [f"{ac}: in no task" for ac in re.findall(r"^\s*[-*]\s+(AC\d+)\b", text, re.M)
             if not re.search(rf"\b{ac}\b", body)]
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
        entries = protected_entries(plan, ctx)
        for status, path in ch:
            for entry in entries:
                ppath, _, anchor = entry.partition("#")  # whole file, or only the anchored sections
                if glob_re(ppath).match(path) and (not anchor or protected_text(
                        file_at(ctx.root, parent, path) if parent else "", anchor)
                        != protected_text(file_at(ctx.root, c, path), anchor)):
                    rows[4].append(f"{short} [{tids[0]}] changes protected {entry}")
            if path == ctx.plan_rel and plan_same:
                continue  # ticks and writes lines; the frozen view is row 6's to judge
            if not matches(path, task["writes"]):
                rows[4].append(f"{short} [{tids[0]}] {path} outside writes")
            if TEST_RE.search(path) and status in "MDT" and not matches(path, task["tests-may-change"]):
                rows[5].append(f"{short} {'deletes' if status == 'D' else 'modifies'} test {path}")
            if TEST_RE.search(path) and status != "D":
                diff = git(ctx.root, "diff", "-U0", parent or "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                           c, "--", path)
                bare = SKIP_IMPORT_RE.search(file_at(ctx.root, c, path) or "")
                if any(l.startswith("+") and (SKIP_RE.search(l) or bare and BARE_SKIP_RE.search(l))
                       for l in diff.splitlines()):
                    rows[5].append(f"{short} adds a skip/only/xfail marker in {path}")
    if overlap([w for t in ctx.plan_at("HEAD")["tasks"].values() for w in t["writes"]],
               path_protected(ctx.plan_at("HEAD"), ctx)):
        rows[4].append("a writes glob at HEAD intersects protected")
    return rows

def balanced(code, i):
    """The index after the ')' that closes the '(' at code[i], or None when it stays open."""
    depth = 0
    for j in range(i, len(code)):
        depth += {"(": 1, ")": -1}.get(code[j], 0)
        if depth == 0:
            return j + 1
    return None

def annotation_run(text):
    """(text's annotation names, text without them and their argument lists); None when a list stays open."""
    names, rest, i = [], [], 0
    while a := re.compile(r"@([\w$]+(?:\.[\w$]+)*)(\s*\()?").search(text, i):
        names.append(a.group(1))
        rest.append(text[i:a.start()] + " ")
        i = balanced(text, a.end() - 1) if a.group(2) else a.end()
        if i is None:
            return None
    return names, "".join(rest) + text[i:]

def disabling(names):
    return any((s := n.rpartition(".")[2]).startswith("Disabled") or s == "Ignore" for n in names)

def class_annotations(head):
    """The annotations on head when the '{' after it opens a class body, else None: an interface, enum,
    record, object, method or lambda body is not a class."""
    run = annotation_run(head)
    words = set(re.findall(r"[\w$]+", re.split(r"[(:=]", run[1])[0])) if run else set()
    return run[0] if "class" in words and not words & {"interface", "enum", "record", "object"} else None

def junit_method(code, start, i, kotlin) -> bool:
    """code[start:i] is the declaration text before a name that a '(' follows: an annotation run with a
    JUnit test annotation, no disabling one and no private or static, then (Kotlin) fun or (Java) a
    return type; and a body follows the parameters and any throws clause."""
    run = annotation_run(code[start:i])
    shape = (r"\s*(?:[a-z]+\s+)*fun\s*(?:<[^;{}()]*>\s*)?" if kotlin else
             r"\s*(?:[a-z]+\s+)*(?:<[^;{}()]*>\s*)?[\w$]+(?:\.[\w$]+)*(?:\s*<[^;{}()]*>)?(?:\s*\[\s*\])*\s*")
    if not run or not re.fullmatch(shape, run[1]) or re.search(r"\b(private|static)\b", run[1]) or disabling(run[0]):
        return False
    if not any((s := n.rpartition(".")[2]) in JUNIT_TEST_ANNOTATIONS and (
            (q := n[:len(n) - len(s)]) == "" or q in JUNIT_PACKAGES and (q != "org.junit." or s == "Test"))
            for n in run[0]):
        return False
    end = balanced(code, code.index("(", i))
    after = end and re.match(r"\s*(?:throws\s+[\w$.]+(?:\s*,\s*[\w$.]+)*\s*)?(\{|=(?!=))", code[end:])
    return bool(after) and (after.group(1) == "{" or kotlin)

def defines_junit(body, name, kotlin) -> bool:
    """A bare name that a top-level class, or classes marked @Nested within it, declares as a runnable
    JUnit method (junit_method), with no disabling annotation on any of those classes."""
    if re.search(r"\.|::", name):
        return False
    # Comments, text blocks (Kotlin: raw strings), strings and characters become spaces, newlines kept.
    # Kotlin block comments nest, so one ends at the */ that brings its depth back to zero.
    raw = r'""".*?(?:"{3,}|\Z)' if kotlin else r'"""(?:\\.|.)*?(?:"""|\Z)'
    blank = re.compile(rf"//[^\n]*|/\*.*?(?:\*/|\Z)|{raw}|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", re.S)
    code, i = [], 0
    while m := blank.search(body, i):
        end, depth = m.end(), 0
        if kotlin and m.group(0).startswith("/*"):
            for t in re.finditer(r"/\*|\*/|\Z", body[m.start():]):
                depth += {"/*": 1, "*/": -1}.get(t.group(0), -depth)  # an unclosed comment runs to the end
                if depth <= 0:
                    end = m.start() + t.end()
                    break
        code += [body[i:m.start()], re.sub(r"[^\n]", " ", body[m.start():end])]
        i = end
    code = "".join(code) + body[i:]
    hits = {m.start() for m in re.finditer(rf"(?<![\w$]){re.escape(name)}(?![\w$])\s*\(", code)}
    stack, depth, start = [], 0, 0  # one entry per open '{': its class's annotations, or None
    for i, ch in enumerate(code):
        if i in hits and depth == 0 and stack and None not in stack and not any(map(disabling, stack)) and all(
                {"Nested", "org.junit.jupiter.api.Nested"} & set(s) for s in stack[1:]) and junit_method(
                code, start, i, kotlin):
            return True
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth:  # inside parentheses, or past an unbalanced ')': nothing declares here
            continue
        if ch == "{":
            stack.append(class_annotations(code[start:i]))
        elif ch == "}" and stack:
            stack.pop()
        # A declaration starts after ; { } and, in Kotlin, after a line that is more than annotations and modifiers.
        if ch in "{};" or ch == "\n" and kotlin and not re.fullmatch(r"[a-z\s]*", (annotation_run(code[start:i])
                                                                                   or ("", "x"))[1]):
            start = i + 1
    return False

def defines_test(body, name, path) -> bool:
    """A runnable test. In a .java or .kt file, only a JUnit method (defines_junit). Elsewhere JS
    it/test('<name>') with exactly that name, or a Python def/async def whose name starts with test
    (what unittest and pytest discover), inside class C for 'C.test_x'."""
    if body is None:
        return False
    if path.endswith((".java", ".kt")):
        return defines_junit(body, name, path.endswith(".kt"))
    if re.search(rf"\b(it|test)\(\s*(?P<q>['\"`]){re.escape(name)}(?P=q)", body):
        return True
    *cls, fn = re.split(r"\.|::", name)
    if not fn.startswith("test") or len(cls) > 1:
        return False
    if cls:  # the class body: from its header to the next line that starts in column 0
        m = re.search(rf"^class {re.escape(cls[0])}\b.*?(?=^\S|\Z)", body, re.M | re.S)
        body = m.group(0) if m else ""
    return bool(re.search(rf"^\s*(async\s+)?def {re.escape(fn)}\(", body, re.M))

def review_findings(ctx):
    path = ctx.runs / "review.md"
    if not path.is_file():
        return [f"no {path.relative_to(ctx.root)}"]
    text, out = path.read_text(), []
    m = re.search(r"^reviewed:\s*(\S+)", text, re.M)
    if not m or not rev_ok(ctx.root, m.group(1)) or subprocess.run(
            ["git", "merge-base", "--is-ancestor", m.group(1), "HEAD"], cwd=ctx.root).returncode:
        return ["review.md has no reviewed: <sha> that is HEAD or its ancestor"]
    reviewed = git(ctx.root, "rev-parse", f"{m.group(1)}^{{commit}}")
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
        if full == reviewed or any(subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ctx.root)
                                   .returncode for a, b in ((reviewed, full), (full, "HEAD"))):
            out.append(f"{rid}: {sha} is not a fix made after reviewed: {m.group(1)}")
            continue
        ch = changes(ctx.root, git(ctx.root, "rev-parse", "-q", "--verify", f"{full}^1", check=False), full)
        if kind == "resolved":
            test, name = f.group(4), f.group(5)
            body = file_at(ctx.root, "HEAD", test) if test else None
            if not (test and TEST_RE.search(test) and defines_test(body, name, test) and test in [p for _s, p in ch]):
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
    print("".join(f"{t['id']} reads: {', '.join(t['reads'])}\n" for t in ctx.plan["tasks"].values() if t["reads"])
          + "".join(f"lint: {e}\n" for e in errs) + f"lint: {'FAIL' if errs else 'PASS'} · "
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

def html_blocks(text):
    """Each blank-line-separated block of text as an escaped <p>, its `- ` lines (and their indented
    continuations) as <li>; no Markdown beyond that."""
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        para, items = [], []
        for line in block.splitlines():
            if line.strip().startswith("- "):
                items.append(line.strip()[2:])
            elif items and line[:1].isspace():
                items[-1] += " " + line.strip()
            else:
                para.append(line.strip())
        out += [f"<p>{html.escape(' '.join(para))}</p>"] if para else []
        out += ["<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"] if items else []
    return out

def approval_page(ctx):
    """.runs/<id>/approval.html from the working tree: the spec, the design's Structure and Interfaces,
    the task table, touches and protected, and the Parked - Q: lines."""
    plan, goal_dir, e = ctx.plan, ctx.root / Path(ctx.plan_rel).parent, html.escape
    read = lambda name: (goal_dir / name).read_text() if (goal_dir / name).is_file() else ""  # noqa: E731
    design = read("design.md")
    bodies, tid = {}, None  # a task's prose: the lines under its header that are not fields
    for line in plan["sections"].get("Tasks", []):
        tid = m.group(2) if (m := TASK_RE.match(line)) else tid
        if tid and not m and not FIELD_RE.match(line):
            bodies.setdefault(tid, []).append(line)
    rows = []
    for t in plan["tasks"].values():  # the test the prose names (a file's stem is not a name), else its files
        prose = " ".join(bodies.get(t["id"], []))
        named = re.search(r"(?<=::)test_\w+", prose) or re.search(r"\btest_\w+\b(?!\.py)", prose)
        shown = named.group(0) if named else ", ".join(t["tests-may-change"]) or "—"
        rows.append(f"<tr><td>{e(t['id'] + ' ' + t['title'])}</td><td>{e(', '.join(t['writes']))}</td>"
                    f"<td>{e(', '.join(t['reads']))}</td><td>{e(shown)}</td></tr>")
    meta = lambda k: ", ".join(map(str, v)) if isinstance(v := plan["meta"].get(k), list) else str(v or "none")  # noqa: E731
    questions = [l.strip()[2:] for l in plan["parked"] if l.strip().startswith("- Q:")]
    out = ["<!doctype html>", '<html><head><meta charset="utf-8">',
           "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}"
           "table{border-collapse:collapse;width:100%}"
           "th,td{border:1px solid #999;padding:.3rem .5rem;text-align:left;vertical-align:top}</style>",
           f"<title>{e(ctx.goal)} approval</title></head><body>",
           f"<h1>{e(ctx.goal)}: {e(str(plan['meta'].get('title', '')))}</h1>", "<h2>spec.md</h2>",
           *(html_blocks(read("spec.md")) or ["<p>none</p>"])]
    for name in ("Structure", "Interfaces"):  # protected_text returns the whole file for an absent heading
        if re.search(rf"^## {name}\s*$", design, re.M):
            out += [f"<h2>design.md: {name}</h2>",
                    *html_blocks(re.sub(r"^## .*\n?", "", protected_text(design, slug(name)), count=1))]
    out += ["<h2>Tasks</h2>", "<table><tr><th>Task</th><th>Writes</th><th>Reads</th><th>Named test</th></tr>",
            *rows, "</table>", f"<p>touches: {e(meta('touches'))}</p>", f"<p>protected: {e(meta('protected'))}</p>",
            "<h2>Questions</h2>", "<ul>" + "".join(f"<li>{e(q)}</li>" for q in questions or ["none"]) + "</ul>",
            "</body></html>"]
    ctx.runs.mkdir(parents=True, exist_ok=True)
    path = ctx.runs / "approval.html"
    path.write_text("\n".join(out) + "\n")
    print(path)
    return 0

def cause_counts(text):
    """The cause: tags on the closure lines of closed BLOCKING findings only."""
    blocking = set(re.findall(r"^\s*- \[x\] BLOCKING (R\d+)\b", text, re.M))
    tags = Counter(c for rid, c in re.findall(r"^\s*- \[x\] (R\d+) (?:resolved|removed)-by .*\bcause: (\w+)",
                                             text, re.M) if rid in blocking)
    return f"cause: context {tags['context']}, logic {tags['logic']}, spec {tags['spec']}"

def cmd_packet(ctx, a):
    if a.approval:
        return approval_page(ctx)
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
           "Receipts:", *(receipts or ["none"]), "", "Review findings:", *(found or ["none"]),
           cause_counts(review.read_text() if review.is_file() else ""), "",
           "Decisions:", *plan["decisions"], "", "Parked:", *(plan["parked"] or ["none"]), "",
           "Reads:", *([f"{t['id']} reads: {', '.join(t['reads'])}" for t in plan["tasks"].values() if t["reads"]]
                       or ["none"]), "",
           "Widenings (writes, tests-may-change and reads):", *(fields or ["none"]), "",
           "Plan-only commits (widenings, ticks, decisions):", *(widen or ["none"]), "",
           "Cost:", *cost_lines(ctx)]
    ctx.runs.mkdir(parents=True, exist_ok=True)
    (ctx.runs / "packet.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0

def when(stamp):
    """An ISO-8601 time (git %cI, or a transcript's `...Z`) as an aware datetime; None when unreadable."""
    try:
        t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None

def records(path):
    """The JSON objects of one .jsonl transcript; unreadable lines and files are skipped."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    yield r
    except OSError:
        return

def claude_usage(root, start):
    """Claude Code: every *.jsonl under $HOME/.claude/projects/<slug>/ and <slug>-*/ (a session opened
    in a subdirectory or a worktree under the root), the session transcripts and the subagent ones in
    <session>/subagents/; <slug> is the root with every character but a letter or digit as `-`. Record: {"type": "assistant", "timestamp": "...Z", "message": {"id",
    "usage": {"input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
    "output_tokens"}}}; input is the three input fields. One response is written as one record per
    content block, each repeating message.id and its usage, so an id counts once across all files."""
    slug, projects = re.sub(r"[^A-Za-z0-9]", "-", str(root)), Path.home() / ".claude" / "projects"
    dirs = [d for d in (sorted(projects.iterdir()) if projects.is_dir() else [])
            if d.name == slug or d.name.startswith(slug + "-")]
    usage, files = {}, 0
    for path in sorted(p for d in dirs for p in d.rglob("*.jsonl")):
        hit = False
        for n, r in enumerate(records(path)):
            m = r.get("message")
            u = m.get("usage") if isinstance(m, dict) else None
            t = when(r.get("timestamp"))
            if isinstance(u, dict) and t and t >= start:
                usage[m.get("id") or (str(path), n)] = u
                hit = True
        files += hit
    tin = sum(u.get(k) or 0 for u in usage.values()
              for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    tout = sum(u.get("output_tokens") or 0 for u in usage.values())
    return (tin, tout, files) if files else None

def codex_usage(root, start):
    """Codex: $CODEX_HOME/sessions/**/*.jsonl (default ~/.codex), kept when the first {"type":
    "session_meta", "payload": {"cwd"}} names the root or a directory under it. Record: {"type": "event_msg", "timestamp":
    "...Z", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens",
    "output_tokens", ...}, "last_token_usage": {...}}}}. Codex repeats a token_count record with
    unchanged numbers, so a session counts the growth of its running total_token_usage between
    records in the window (a repeat adds nothing), never the sum of last_token_usage. Codex's
    input_tokens already includes its cached_input_tokens."""
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    tin = tout = files = 0
    for path in sorted((home / "sessions").rglob("*.jsonl")):
        rs = list(records(path))  # the whole transcript: session_meta need not come first
        meta = next((r for r in rs if r.get("type") == "session_meta"), None)
        cwd = ((meta or {}).get("payload") or {}).get("cwd")
        if not isinstance(cwd, str) or not (os.path.realpath(cwd) == str(root)
                                            or os.path.realpath(cwd).startswith(str(root) + os.sep)):
            continue
        totals = [(t >= start, p["info"]["total_token_usage"]) for r in rs if r.get("type") == "event_msg"
                  and isinstance(p := r.get("payload"), dict) and p.get("type") == "token_count"
                  and isinstance(p.get("info"), dict) and isinstance(p["info"].get("total_token_usage"), dict)
                  and (t := when(r.get("timestamp")))]
        if not any(inside for inside, _u in totals):
            continue
        files += 1
        last = {"input_tokens": 0, "output_tokens": 0}  # the running total before the window
        for inside, u in totals:
            if inside:
                tin += max(0, (u.get("input_tokens") or 0) - last["input_tokens"])
                tout += max(0, (u.get("output_tokens") or 0) - last["output_tokens"])
            last = {k: u.get(k) or 0 for k in last}
    return (tin, tout, files) if files else None

def cost_lines(ctx, since=None):
    """One line per harness: tokens in this repository's transcripts since the ref's commit time."""
    start = when(git(ctx.root, "log", "-1", "--format=%cI", since or ctx.tag("approved"), check=False))
    out = []
    for name, usage in (("claude", claude_usage), ("codex", codex_usage)):
        got = usage(ctx.root, start) if start else None
        out.append(f"{name}: input {got[0]} output {got[1]} ({got[2]} transcripts)" if got else f"{name}: unknown")
    return out

def cmd_cost(ctx, a):
    print("\n".join(cost_lines(ctx, a.since)))
    return 0

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    [common.add_argument(opt, default=argparse.SUPPRESS) for opt in ("--plan", "--goal")]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[common])
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("lint", "status", "next", "resume", "packet", "done", "cost"):
        p = sub.add_parser(name, parents=[common])
        if name in ("done", "packet"):
            p.add_argument("--milestone")
        if name == "packet":
            p.add_argument("--approval", action="store_true", help="write .runs/<id>/approval.html instead")
        if name == "cost":
            p.add_argument("--since", help="git ref whose commit time starts the sum (default goal/<id>/approved)")
    a = ap.parse_args(argv)
    try:
        ctx = find_ctx(getattr(a, "plan", None), getattr(a, "goal", None))
        return globals()["cmd_" + a.action](ctx, a)
    except (PlanError, RuntimeError, OSError, ValueError) as exc:
        print(f"goal.py: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
