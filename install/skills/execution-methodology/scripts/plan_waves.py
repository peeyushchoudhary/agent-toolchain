#!/usr/bin/env python3
"""Compute the wave plan for every feature plan and refuse a wave that collides with itself.
This script writes nothing, ever.

A feature plan at `docs/product/plans/F-<id>-<slug>.md` carries one fenced ```task block per task:

    task: T3
    title: persist the reminder schedule
    lane: light | full
    needs: [T1]                  # dependency edges, ids declared in THIS plan
    writes: [backend/x/**]       # the exclusive write set
    covers: [AC-4, AC-7]         # acceptance criteria this task satisfies

WAVES ARE COMPUTED, NEVER WRITTEN. A wave list in the prose is a second copy of the edges, and the
two disagree the first time a task moves; an index that can only derive cannot drift. So the plan
declares edges and write sets, and this script derives the schedule from them on every run.

  W0  a task block that cannot be read: unknown key, missing or malformed `task`, unknown lane
  W1  a `needs` edge to a task id no block in the scope declares
  W2  a cycle, named as the shortest one found
  W3  the same task id declared twice in one plan
  W4  two tasks in the SAME computed wave whose `writes` globs can match one path
  W5  size: more than 5 write globs, `covers` empty, or more than 12 full-lane tasks in a feature
  W6  the milestone is not a usable scope: an edge leaving it, or two files claiming its id

THE DEFAULT SCOPE IS ONE PLAN, AND THAT IS NOT WHERE THE PARALLELISM IS. Task ids are plan-local,
so `T1` means a different task in every feature and one merged graph would fuse all of them. Per
plan, therefore, two features that dispatch at the same time are never compared, and the write
collision BETWEEN two features — the one that actually costs a parallel run, because nobody was
looking — is the collision this script could not see.

`--milestone M2` is that second scope. Membership DERIVES: every feature spec under
`docs/product/specs/` that declares `milestone: M2` is in, and the milestone document at
`docs/product/milestones/M<n>-<slug>.md` carries no feature list to disagree with the specs. The
key is OPTIONAL on a spec — a feature with no milestone is specified and waiting, which is a
legitimate state and is never a finding. Every check above then runs over the MERGED graph with
QUALIFIED ids (`F-12/T1`), so W4 finally compares two features against each other.

  `needs:` STAYS PLAN-LOCAL BY DEFAULT. `needs: [T1]` means this feature's T1, in both scopes; the
  qualified form `needs: [F-11/T4]` is the explicit cross-feature edge. A qualified edge is ignored
  by the per-plan scope, which has no way to resolve it, and an edge naming a feature OUTSIDE the
  milestone is W6 rather than a silent drop: the milestone claims to be schedulable on its own and
  that edge says it is not.

  A MEMBER FEATURE WITH NO PLAN IS REPORTED, NOT FAILED. It is printed and carried in the JSON as
  `unplanned`, because a spec is approved before its plan is written and failing that state would
  make the check fire through the whole normal life of a milestone — and a check that fires all the
  time is switched off. Silently omitting it would be worse: the orchestrator would dispatch a
  milestone it believed was complete.

W4 IS WHY THIS EXISTS, and it FAILS rather than serialising the pair. Measured on a real corpus of
51 tasks: 164 colliding write-set pairs, 37 of them between tasks that land in the same computed
wave, and 4 `needs` edges naming ids that are declared nowhere. Every one of those tasks passed the
validation it was given, because nothing compared one task against another. Auto-serialising a
collision would turn that corpus green while dispatching the same 37 pairs onto shared files: the
collision is a decomposition defect, and the planner has to see it and re-cut the tasks, or add an
explicit `needs:` edge and OWN the serialisation.

GLOB OVERLAP IS DECIDED WITHOUT TOUCHING THE FILESYSTEM. Two tasks collide over files that do not
exist yet — that is the normal case for a plan — so expanding globs against the tree would answer a
question nobody asked. Instead two patterns are tested for a non-empty intersection directly, by a
dynamic program over path segments with a second one over the characters inside a segment.

  THE SUBSET SUPPORTED: `**` as a whole segment, `*` and `?` inside a segment, character classes
  `[abc]`, `[a-z]`, `[!abc]` and `[^abc]`, and literal segments. A leading `./`, a repeated `/` and
  a trailing `/` are normalised away.

  THE LIMITS, AND WHICH WAY EACH ONE ERRS. When unsure this REPORTS the overlap: a false conflict
  costs one serialised wave, a missed one corrupts a parallel run.
   - `**` matches ZERO or more segments, so `a/**` overlaps `a` itself. Deliberately generous.
   - Either pattern may name a directory, so `a/b` is also tested as `a/b/**`. A path and a
     directory of the same name are therefore conflated, which over-reports and never under-reports.
   - Brace expansion is NOT implemented: a segment containing `{` or `}` is treated as `*`, which
     covers every expansion of it and more.
   - A leading `!` is a literal character, not a negation. `writes:` is a positive set of paths;
     nothing here subtracts from one.
   - Comparison is case-sensitive and symlink-blind. On a case-insensitive filesystem `A/x` and
     `a/x` are one file and this reports no overlap. Naming both is a plan defect of its own.

  WHAT THE CONSERVATISM COSTS, MEASURED RATHER THAN ASSERTED. Over 14,706 random pattern pairs,
  each checked against every concrete path four segments deep that both patterns match: ZERO missed
  overlaps, and 26% of pairs reported with no witness in that depth. Dropping only the directory
  rule takes the second number to 1.2% and is the whole of the difference — so that one rule is
  where the caution is spent, and it is spent on the pattern a planner actually writes by hand.

Usage:  plan_waves.py [--root DIR] [--milestone M<n>] [--json]
Exit codes: 0 clean, 1 findings, 2 the arguments or the tree could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Callable, NamedTuple, Sequence

# One parser, one fence rule, one finding shape, one print cap — never a second copy of any of them.
from spec_check import PRINT_CAP, Doc, Findings, SpecError, FENCE_RE, parse_front_matter

TASK_KEYS = (("task",), ("title", "lane", "needs", "writes", "covers"))
LANES = ("light", "full")
LIST_KEYS = ("needs", "writes", "covers")
TASK_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
MAX_WRITES = 5        # (P5) one green commit's worth of files in one module.
MAX_FULL_LANE = 12    # (P5) above this it is two features, and no wave plan repairs that.

QUALIFY = "/"                                 # `F-12/T1`: the feature, then its plan-local task id
MILESTONE_RE = re.compile(r"^M\d+$")
FEATURE_RE = re.compile(r"^F-\d+$")

# Each task carries the document it was read from, so one set of checks serves both scopes: the
# per-plan run passes tasks from one file and the milestone run passes tasks from several, and a
# finding is charged to the right file either way without a second copy of any check.
Task = NamedTuple("Task", [("ident", str), ("line", int), ("lane", str), ("needs", list),
                           ("writes", list), ("covers", list), ("where", dict), ("doc", Doc)])
Plan = NamedTuple("Plan", [("rel", str), ("tasks", list), ("waves", list), ("stuck", list)])
Milestone = NamedTuple("Milestone", [("name", str), ("rel", str), ("features", list),
                                     ("unplanned", list), ("tasks", list), ("waves", list),
                                     ("stuck", list)])


# --- reading the plan ---------------------------------------------------------------------------

def task_blocks(doc: Doc) -> list[tuple[int, list[str]]]:
    """Every ```task block as (the 1-based line of its opening fence, the lines inside it).

    A fence closes only on a run of the SAME character at least as long as the one that opened it,
    which is what lets a document show this template inside a ````markdown wrapper without the
    example being read as a real task. The alternative — a bare toggle — makes the reference page
    describing a plan unparseable the moment it quotes one.
    """
    found, index, lines = [], 0, doc.lines
    while index < len(lines):
        opening = FENCE_RE.match(lines[index])
        if not opening:
            index += 1
            continue
        marker, text = opening.group(1)[0], lines[index].strip()
        run = len(text) - len(text.lstrip(marker))
        close = index + 1
        while close < len(lines):
            candidate = lines[close].strip()
            if candidate and set(candidate) == {marker} and len(candidate) >= run:
                break
            close += 1
        if text[run:].strip() == "task":
            found.append((index + 1, lines[index + 1:close]))
        index = close + 1
    return found


def parse_task(doc: Doc, fence: int, block: list[str], f: Findings) -> Task | None:
    """One task block, or None with a W0 finding. The block is `key: value` lines — exactly the
    front-matter subset — so it is handed to the front-matter parser between two `---` markers
    rather than to a second parser that would drift from the first."""
    try:
        data, where, _ = parse_front_matter(["---"] + block + ["---"])
    except SpecError as exc:
        offset = re.sub(r"^line (\d+): ", lambda m: f"line {fence + int(m.group(1)) - 1}: ",
                        str(exc))
        f.add(doc, fence, "W0", f"task block does not parse: {offset}")
        return None
    at = {key: fence + number - 1 for key, number in where.items()}
    required, optional = TASK_KEYS
    for key in data:
        if key not in required and key not in optional:
            f.add(doc, at[key], "W0", f"unknown key `{key}` in a task block; a task takes "
                                      f"{', '.join(required + optional)}")
    ident = data.get("task")
    if not isinstance(ident, str) or not TASK_ID_RE.match(ident):
        f.add(doc, fence, "W0", f"task block has no readable `task:` id (got {ident!r}); every "
                                "other task's `needs` names this id, so the block cannot be used")
        return None
    lane = data.get("lane", "light")
    if not isinstance(lane, str) or lane not in LANES:
        f.add(doc, at.get("lane", fence), "W0",
              f"lane `{lane}` is not one of {' | '.join(LANES)}")
        lane = "light"
    # A scalar where a list belongs is the commonest hand-edit; read it as the one-element list it
    # obviously is rather than dropping the value, which is how a checker starts lying.
    values = {key: [data[key]] if isinstance(data.get(key), str) and data[key] else
                   list(data.get(key) or []) for key in LIST_KEYS}
    return Task(ident, at.get("task", fence), lane, values["needs"], values["writes"],
                values["covers"], at, doc)


def read_plan(doc: Doc, f: Findings) -> list[Task]:
    """The tasks of one plan, with W3 charged to the SECOND declaration of a repeated id."""
    tasks: list[Task] = []
    seen: dict[str, int] = {}
    for fence, block in task_blocks(doc):
        task = parse_task(doc, fence, block, f)
        if task is None:
            continue
        if task.ident in seen:
            f.add(doc, task.line, "W3", f"task id `{task.ident}` is already declared on line "
                                        f"{seen[task.ident]}; a `needs` edge naming it would be "
                                        "an edge to two different tasks")
            continue
        seen[task.ident] = task.line
        tasks.append(task)
    return tasks


# --- the graph ----------------------------------------------------------------------------------

def schedule(tasks: Sequence[Task]) -> tuple[list[list[str]], list[str]]:
    """Kahn levels: wave N is every task whose prerequisites all land in an earlier wave. Returns
    the waves and the ids that never scheduled, which is exactly the set inside or downstream of a
    cycle. Ids are sorted so a wave prints the same way twice."""
    known = {task.ident for task in tasks}
    edges = {task.ident: {need for need in task.needs if need in known and need != task.ident}
             for task in tasks}
    waves, placed = [], set()
    while True:
        wave = sorted(ident for ident, needs in edges.items()
                      if ident not in placed and needs <= placed)
        if not wave:
            break
        waves.append(wave)
        placed.update(wave)
    return waves, sorted(known - placed)


def shortest_cycle(tasks: Sequence[Task], stuck: Sequence[str]) -> list[str]:
    """The shortest cycle among the tasks that never scheduled, as a walk that returns to its start.

    Naming ONE cycle is the point. A plan with a knot in it produces a long list of unschedulable
    ids, and the reader has to find the loop by hand; the shortest loop is the smallest edit that
    can break it. Breadth-first from each stuck id, and the first return is the shortest.
    """
    residue = set(stuck)
    out = {task.ident: [need for need in sorted(task.needs) if need in residue]
           for task in tasks if task.ident in residue}
    best: list[str] = []
    for start in sorted(residue):
        queue, came = [start], {start: None}
        while queue:
            node = queue.pop(0)
            for nxt in out.get(node, ()):
                if nxt == start:
                    path, step = [start], node
                    while step is not None:
                        path.append(step)
                        step = came[step]
                    if not best or len(path) < len(best):
                        best = path[::-1]
                    queue = []
                    break
                if nxt not in came:
                    came[nxt] = node
                    queue.append(nxt)
    return best


# --- glob intersection, with no filesystem anywhere near it -------------------------------------

STAR = "*"                      # a whole path segment, or a run of `*` inside one
ANY = (True, frozenset())       # `?`: excludes nothing, so it matches any single character


def segments(pattern: str) -> tuple[str, ...]:
    text = re.sub(r"^(?:\./)+", "", pattern.strip().replace("\\", "/"))
    text = re.sub(r"/{2,}", "/", text).lstrip("/")
    if text.endswith("/"):
        text += "**"            # a trailing slash names a directory, which owns everything under it
    return tuple(part for part in text.split("/") if part not in ("", "."))


@lru_cache(maxsize=None)
def tokens(segment: str) -> tuple:
    """One segment as single-character matchers and STARs. A matcher is (negated, characters)."""
    if "{" in segment or "}" in segment:
        return (STAR,)          # brace expansion is unimplemented; `*` covers every expansion of it
    out, index = [], 0
    while index < len(segment):
        char = segment[index]
        if char == "*":
            while index < len(segment) and segment[index] == "*":
                index += 1
            out.append(STAR)
        elif char == "?":
            out.append(ANY)
            index += 1
        elif char == "[" and segment.find("]", index + 2) != -1:
            close = segment.find("]", index + 2)
            body = segment[index + 1:close]
            negated = body[:1] in ("!", "^")
            body, chars, cursor = body[negated:], set(), 0
            while cursor < len(body):
                if cursor + 2 < len(body) and body[cursor + 1] == "-":
                    chars.update(chr(code) for code
                                 in range(ord(body[cursor]), ord(body[cursor + 2]) + 1))
                    cursor += 3
                else:
                    chars.add(body[cursor])
                    cursor += 1
            out.append((negated, frozenset(chars)))
            index = close + 1
        else:
            out.append((False, frozenset(char)))
            index += 1
    return tuple(out)


def characters_meet(left, right) -> bool:
    """Can one character satisfy both matchers? Two negated classes always share one, because the
    alphabet a path segment draws on is far larger than anything a class enumerates."""
    (left_negated, left_chars), (right_negated, right_chars) = left, right
    if not left_negated and not right_negated:
        return bool(left_chars & right_chars)
    if not left_negated:
        return bool(left_chars - right_chars)
    if not right_negated:
        return bool(right_chars - left_chars)
    return True


def meets(left: Sequence, right: Sequence, wild, unit: Callable) -> bool:
    """Is there a string both sequences match? One dynamic program, used at both levels: over path
    segments with `**` as the wildcard, and over the characters of one segment with `*` as it. Cell
    (i, j) answers the question for the tails, so a wildcard is `absorb nothing` or `absorb one`."""
    height, width = len(left), len(right)
    table = [[False] * (width + 1) for _ in range(height + 1)]
    table[height][width] = True
    for column in range(width - 1, -1, -1):
        table[height][column] = right[column] == wild and table[height][column + 1]
    for row in range(height - 1, -1, -1):
        table[row][width] = left[row] == wild and table[row + 1][width]
        for column in range(width - 1, -1, -1):
            if left[row] == wild or right[column] == wild:
                table[row][column] = table[row + 1][column] or table[row][column + 1]
            else:
                table[row][column] = (unit(left[row], right[column])
                                      and table[row + 1][column + 1])
    return table[0][0]


@lru_cache(maxsize=None)
def overlap(left: str, right: str) -> bool:
    """Can one path match both globs? Each side is also tested as a directory it might name, which
    is the conservative direction: an unnecessary serialisation costs a wave, a missed collision
    costs the run."""
    first, second = segments(left), segments(right)
    if not first or not second:
        return False
    both = ((first, second), (first, second + ("**",)), (first + ("**",), second))
    return any(meets(a, b, "**", lambda x, y: meets(tokens(x), tokens(y), STAR, characters_meet))
               for a, b in both)


# --- the checks ---------------------------------------------------------------------------------

def check_edges(tasks: Sequence[Task], f: Findings, members: Sequence[str] | None = None) -> None:
    """W1, and W6 when a milestone is the scope.

    `members is None` is the per-plan scope, and there a QUALIFIED edge is skipped rather than
    reported: `F-11/T4` names a task in another file, which this scope cannot resolve either way,
    and calling every legitimate cross-feature edge dangling would make the default run unusable
    for any plan that has one. The milestone scope is where that edge is resolved, and where an
    edge pointing out of the milestone becomes W6.
    """
    known = {task.ident for task in tasks}
    scope = "the milestone" if members is not None else "this plan"
    for task in tasks:
        for need in task.needs:
            at = task.where.get("needs", task.line)
            if members is not None and need.split(QUALIFY)[0] not in members:
                f.add(task.doc, at, "W6",
                      f"`{task.ident}` needs `{need}`, whose feature is not in this milestone; the "
                      "milestone cannot be dispatched on its own until that feature joins it or "
                      "the edge goes")
            elif members is None and QUALIFY in need:
                continue      # a cross-feature edge: out of scope here, resolved by --milestone
            elif need not in known:
                f.add(task.doc, at, "W1",
                      f"`{task.ident}` needs `{need}`, which no task block in {scope} declares; "
                      "the edge orders nothing and the task will dispatch in the first wave")
            elif need == task.ident:
                f.add(task.doc, at, "W1", f"`{task.ident}` needs itself")


def check_size(tasks: Sequence[Task], f: Findings) -> None:
    for task in tasks:
        if len(task.writes) > MAX_WRITES:
            f.add(task.doc, task.where.get("writes", task.line), "W5",
                  f"`{task.ident}` writes {len(task.writes)} globs; more than {MAX_WRITES} is two "
                  "tasks wearing one id, and it is the pair that collides with everything")
        if not task.covers:
            f.add(task.doc, task.line, "W5", f"`{task.ident}` covers no acceptance criterion, so "
                                             "nothing states what finishing it would prove")
    full = [task.ident for task in tasks if task.lane == "full"]
    if len(full) > MAX_FULL_LANE:
        f.add(tasks[0].doc, tasks[0].line, "W5",
              f"{len(full)} full-lane tasks in one feature (the limit is {MAX_FULL_LANE}): this is "
              "two features, and no wave plan repairs a feature that is too big")


def check_wave_writes(tasks: Sequence[Task], waves: Sequence[Sequence[str]],
                      f: Findings) -> None:
    """W4. Tasks in one wave run at the same time, so their write sets must be disjoint.

    Reported, never repaired: naming the pair sends the planner back to the decomposition, while
    quietly moving one task down a wave would report a green schedule for a plan that still says
    two agents own one file.

    Over a milestone the ids are qualified and the pair may sit in two different files, which is
    the collision the per-plan scope could not see at all. The finding is charged to the second
    task's own plan, and both qualified ids name the features involved.
    """
    index = {task.ident: task for task in tasks}
    for number, wave in enumerate(waves, start=1):
        for left, right in combinations(wave, 2):
            one, two = index[left], index[right]
            hit = next(((a, b) for a in one.writes for b in two.writes if overlap(a, b)), None)
            if hit is None:
                continue
            f.add(two.doc, two.where.get("writes", two.line), "W4",
                  f"`{left}` and `{right}` are both in wave {number} and their write sets meet: "
                  f"`{hit[0]}` and `{hit[1]}` can match one path. Re-cut the tasks so the write "
                  f"sets are disjoint, or add `needs: [{left}]` to `{right}` and own the "
                  "serialisation — this is not resolved automatically")


def check_cycle(tasks: Sequence[Task], stuck: Sequence[str], f: Findings) -> None:
    """W2, charged to the first task of the named cycle wherever that task's plan happens to be."""
    if not stuck:
        return
    cycle = shortest_cycle(tasks, stuck)
    head = next(task for task in tasks if task.ident == (cycle or stuck)[0])
    f.add(head.doc, head.line, "W2",
          f"cycle: {' -> '.join(cycle) if cycle else ' -> '.join(stuck)}. "
          f"{len(stuck)} task(s) cannot be scheduled until one of those edges is removed")


def plan_paths(root: Path) -> list[Path]:
    directory = root / "docs" / "product" / "plans"
    return [path for path in sorted(directory.glob("F-*.md"))
            if path.is_file()] if directory.is_dir() else []


def run(root: Path) -> tuple[Findings, list[Plan]]:
    """Every plan under `docs/product/plans/`, one graph per file. A repository without that
    directory is silent: a checker that shouts at a repository which never adopted the layout gets
    switched off."""
    f, plans = Findings(), []
    for path in plan_paths(root):
        doc = Doc(path, root)
        tasks = read_plan(doc, f)
        if not tasks:
            continue
        check_edges(tasks, f)
        check_size(tasks, f)
        waves, stuck = schedule(tasks)
        check_cycle(tasks, stuck, f)
        check_wave_writes(tasks, waves, f)
        plans.append(Plan(doc.rel, tasks, waves, stuck))
    return f, plans


# --- the milestone scope -------------------------------------------------------------------------

def milestone_docs(root: Path, name: str, f: Findings) -> Doc | None:
    """The milestone document declaring `milestone: <name>`, or None.

    None is SILENT, and deliberately: a repository with no milestone of that name has not adopted
    the layout or has not written that milestone yet, and neither is a defect this script may
    charge to it. Two documents claiming one id IS a defect — membership derives from the specs, so
    the pair does not make the graph ambiguous, but it makes the milestone unaddressable by name.
    """
    directory = root / "docs" / "product" / "milestones"
    found = []
    for path in sorted(directory.glob("M*.md")) if directory.is_dir() else []:
        if not path.is_file():
            continue
        doc = Doc(path, root)
        if not doc.front_error and doc.scalar("milestone") == name:
            found.append(doc)
    for extra in found[1:]:
        f.add(extra, extra.at("milestone"), "W6",
              f"`milestone: {name}` is also declared by {found[0].rel}; one milestone is one "
              "document, and `--milestone` cannot choose between two")
    return found[0] if found else None


def milestone_features(root: Path, name: str) -> list[str]:
    """The feature ids whose spec declares this milestone, in id order.

    MEMBERSHIP DERIVES FROM THE SPECS and the milestone document holds no list to disagree with
    them. A spec with no `milestone:` key is skipped in silence: it is specified and waiting, which
    is the normal state of most of a backlog, and reading that as an omission would turn the whole
    backlog into findings. A spec whose front matter does not parse is skipped too — the spec
    checker owns that finding and a second copy of it here would be reported twice.
    """
    directory = root / "docs" / "product" / "specs"
    members = []
    for path in sorted(directory.glob("F-*.md")) if directory.is_dir() else []:
        if not path.is_file():
            continue
        doc = Doc(path, root)
        if doc.front_error or doc.scalar("milestone") != name:
            continue
        identifier = doc.scalar("id")
        if FEATURE_RE.match(identifier):
            members.append(identifier)
    return sorted(set(members), key=lambda ident: (int(ident[2:]), ident))


def qualify(feature: str, tasks: Sequence[Task]) -> list[Task]:
    """Plan-local ids become `F-<id>/T<n>`, so `T1` in two features is two tasks and not one.

    A `needs` entry that already carries a feature is left exactly as written — that is the
    explicit cross-feature edge — and every other entry is read against THIS feature, which keeps
    the plan-local default intact in both scopes.
    """
    return [task._replace(ident=f"{feature}{QUALIFY}{task.ident}",
                          needs=[need if QUALIFY in need else f"{feature}{QUALIFY}{need}"
                                 for need in task.needs])
            for task in tasks]


def run_milestone(root: Path, name: str) -> tuple[Findings, Milestone | None]:
    """One wave plan across every feature of one milestone. Returns None when there is nothing to
    schedule — no such milestone, or no feature has joined it yet."""
    f = Findings()
    doc = milestone_docs(root, name, f)
    if doc is None:
        return f, None
    members = milestone_features(root, name)
    if not members:
        return f, None
    available = plan_paths(root)
    tasks: list[Task] = []
    unplanned: list[str] = []
    for feature in members:
        # The same filename rule the spec checker uses for `id`: `F-12-slug.md`, or bare `F-12.md`.
        path = next((p for p in available
                     if p.name.startswith(feature + "-") or p.stem == feature), None)
        local = read_plan(Doc(path, root), f) if path is not None else []
        if not local:
            unplanned.append(feature)
            continue
        check_size(local, f)
        tasks.extend(qualify(feature, local))
    if not tasks:
        return f, Milestone(name, doc.rel, members, unplanned, [], [], [])
    check_edges(tasks, f, members)
    waves, stuck = schedule(tasks)
    check_cycle(tasks, stuck, f)
    check_wave_writes(tasks, waves, f)
    return f, Milestone(name, doc.rel, members, unplanned, tasks, waves, stuck)


# --- output -------------------------------------------------------------------------------------

def print_plans(plans: Sequence[Plan]) -> None:
    for plan in plans:
        print(f"{plan.rel}  {len(plan.tasks)} task(s), {len(plan.waves)} wave(s), "
              f"critical path {len(plan.waves)}")
        for number, wave in enumerate(plan.waves, start=1):
            print(f"  wave {number}  width {len(wave)}  {', '.join(wave)}")
        if plan.stuck:
            print(f"  UNSCHEDULED  {len(plan.stuck)}  {', '.join(plan.stuck)}  (in or after a "
                  "cycle)")


def print_milestone(m: Milestone) -> None:
    """Qualified ids, and the features each wave touches — the wave width alone does not say
    whether the parallelism is inside one feature or across three, and only the second kind is
    what a milestone is dispatched for."""
    print(f"{m.rel}  milestone {m.name}  {len(m.features)} feature(s), {len(m.tasks)} task(s), "
          f"{len(m.waves)} wave(s), critical path {len(m.waves)}")
    for number, wave in enumerate(m.waves, start=1):
        features = sorted({ident.split(QUALIFY)[0] for ident in wave},
                          key=lambda ident: (int(ident[2:]), ident))
        print(f"  wave {number}  width {len(wave)}  {', '.join(wave)}"
              f"   [{', '.join(features)}]")
    if m.stuck:
        print(f"  UNSCHEDULED  {len(m.stuck)}  {', '.join(m.stuck)}  (in or after a cycle)")
    if m.unplanned:
        print(f"  UNPLANNED  {len(m.unplanned)}  {', '.join(m.unplanned)}  (in the milestone, no "
              "plan file yet — not scheduled and not a finding)")


def milestone_json(root: Path, m: Milestone | None, findings: Sequence, code: int) -> dict:
    """The dispatch interface, shaped for a program rather than a reader.

    `waves` is a list of lists of qualified ids and nothing else, so an orchestrator dispatches
    `waves[n]` directly; everything a runner needs per task — the lane it runs in, the paths it may
    write, the criteria it settles — hangs off `tasks` under the same qualified id, so no consumer
    has to parse a printed line or join two shapes on a name it built itself.
    """
    return {"root": str(root), "milestone": m.name if m else None,
            "path": m.rel if m else None, "count": len(findings), "exit": code,
            "features": list(m.features) if m else [],
            "unplanned": list(m.unplanned) if m else [],
            "waves": [list(wave) for wave in m.waves] if m else [],
            "unscheduled": list(m.stuck) if m else [],
            "tasks": {task.ident: {"feature": task.ident.split(QUALIFY)[0],
                                   "lane": task.lane, "needs": list(task.needs),
                                   "writes": list(task.writes), "covers": list(task.covers),
                                   "plan": task.doc.rel} for task in (m.tasks if m else [])},
            "findings": [item._asdict() for item in findings]}


def print_findings(findings: Sequence) -> None:
    if not findings:
        return
    width = max(len(f"{item.path}:{item.line}") for item in findings[:PRINT_CAP])
    for item in findings[:PRINT_CAP]:
        print(f"{item.path}:{item.line}".ljust(width) + f"  {item.rule}  {item.message}")
    if len(findings) > PRINT_CAP:
        print(f"... and {len(findings) - PRINT_CAP} more finding(s); fix these and run again")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--milestone", metavar="M<n>",
                        help="schedule every feature whose spec declares this milestone as ONE "
                             "graph, with qualified `F-<id>/T<n>` task ids")
    parser.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2
    # Rejected rather than answered with silence: `--milestone 2` would match no document, and an
    # empty exit-0 run reads exactly like "that milestone is clean".
    if args.milestone is not None and not MILESTONE_RE.match(args.milestone):
        print(f"ERROR: --milestone takes M<number>, not {args.milestone!r}", file=sys.stderr)
        return 2
    try:
        if args.milestone:
            found, milestone = run_milestone(root.resolve(), args.milestone)
        else:
            found, plans = run(root.resolve())
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = sorted(found)
    code = 1 if findings else 0
    if args.milestone:
        if args.json:
            json.dump(milestone_json(root.resolve(), milestone, findings, code), sys.stdout,
                      indent=2)
            sys.stdout.write("\n")
            return code
        print_findings(findings)
        if milestone is not None:
            print_milestone(milestone)
        return code
    if args.json:
        json.dump({"root": str(root.resolve()), "count": len(findings), "exit": code,
                   "plans": [{"path": plan.rel, "tasks": len(plan.tasks),
                              "waves": [{"wave": number, "width": len(wave), "tasks": list(wave)}
                                        for number, wave in enumerate(plan.waves, start=1)],
                              "unscheduled": plan.stuck} for plan in plans],
                   "findings": [item._asdict() for item in findings]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return code
    print_findings(findings)
    print_plans(plans)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
