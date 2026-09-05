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

  W0  a task block that cannot be admitted: unknown key, missing or malformed `task`, missing or
      unknown lane, or an empty write boundary
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

WHERE THE WORK ACTUALLY IS, DERIVED FROM GIT AND NEVER FROM A LEDGER. `--since <REV>` reads
`<REV>..HEAD`, resolves each commit subject to a task by the SAME rule `--commit` uses, and prints
per task `done | duplicate | in-flight | ready | blocked-on <ids>`. A ledger is a claim written by
the same agent it would bind; a commit is a fact. It is the resume primitive after a context loss,
and the milestone-completion check, and it costs zero model calls — against a ledger read that has
been measured at ~188,000 tokens for one 745 KB file.

`--ready` then emits the DISPATCHABLE SET: every task whose `needs` are done, whose `writes` meet
nothing in flight, and none of whose `serialises` partners is in flight. `--in-flight` supplies what
is already running, so the question answered is "what may I start NOW, given these". The wave list
is a LEGALITY CERTIFICATE, not a dispatch schedule: `schedule()` is Kahn LEVELS, so wave N+1 waits
on all of wave N even where a task needs one predecessor. Because W4/W6 compare EVERY pair rather
than same-wave pairs, a continuous ready set carries the identical guarantee with no barrier.

  MEASURED, on the 51-task cross-feature graph reconstructed from a real fleet plan set (rounds to
  finish, unit tasks, K workers): barrier 27/19/15/12/11/10/9 for K=2..8 against ready-set
  26/17/13/11/9/8/7. The ready set is never slower, and 4% to 22% faster across that band. ORDER IS
  PART OF THE RESULT: dispatching the ready set in id order instead of most-unlocked-first gives
  27/19/15/13/11/10/9 — at K=5 that is SLOWER than the barrier it replaced. So the set is ordered by
  how many tasks sit transitively downstream of each, and that ordering is not decoration.

  THERE IS NO BUILT-IN CONCURRENCY CAP, and that is an argument rather than an omission.
   - It cannot be a safety number. Legality is re-derived against the ACTUAL in-flight set at every
     dispatch, so the set is disjoint at any size; a cap can neither make a colliding pair safe nor
     make a disjoint pair unsafe.
   - The measured stray — 4 of 83 committed files outside the declaring task's `writes`, all four
     inside ANOTHER task's set, i.e. 1 to 4 of 16 cards — is a per-task probability, and running
     fewer tasks at once does not lower it. What catches it is W7 at commit time, which runs at any
     size. At the top of that measured range the chance no in-flight task is straying is 0.75^K:
     56% at two writers and 42% at three. No K on that curve is comfortable, which is the proof
     that throttling is the wrong control for it.
   - It can only be a throughput number, and that number belongs to the graph, not to this script.
     On the same 51-task graph worker utilisation is 1.00 at K=3, 0.98 at K=4 and 0.93 at K=5, and
     adding writers stops buying anything at K=11, where the dispatch bottoms out at 5 rounds
     against a 4-level critical path. A constant compiled in here would be right for that milestone
     and wrong for the next one.
  So `--limit` exists, takes the operator's own bound, and DEFAULTS TO NONE; the deferred tasks are
  printed with the reason, so a cap that is costing throughput is visible rather than assumed.

Usage:  plan_waves.py [--root DIR] [--milestone M<n>] [--json] [--commit REV]
                      [--since REV [--in-flight ID,...] [--ready] [--limit N]]
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
from spec_check import (PRINT_CAP, Doc, Findings, SpecError, FENCE_RE, criteria, git,
                        parse_front_matter)

TASK_KEYS = (("task",), ("title", "lane", "needs", "writes", "covers", "serialises"))
LANES = ("light", "full")
LIST_KEYS = ("needs", "writes", "covers", "serialises")
TASK_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
MAX_WRITES = 5        # (P5) one green commit's worth of files in one module.
MAX_FULL_LANE = 12    # (P5) above this it is two features, and no wave plan repairs that.

FEATURE_ID_RE = re.compile(r"^F-\d+[A-Z]?$")
QUALIFY = "/"                                 # `F-12/T1`: the feature, then its plan-local task id
# The optional criterion priority tag, read from the END of a criterion: `... no second refund. [P1]`
# It is read through spec_check's OWN `criteria()` fold, never through a second `AC-<n>` pattern —
# that pattern has been recorded as too strict against the real corpus four times, and a private
# copy here would be the fifth without anyone measuring it.
PRIORITY_TAG_RE = re.compile(r"\[P([1-9])\]\s*$")
UNRANKED = 99         # every unmarked task, and every task in a feature that marks nothing
MILESTONE_RE = re.compile(r"^M\d+$")
# ONE PATTERN, NOT TWO. This was `^F-\d+$` while `FEATURE_ID_RE` beside it accepted a suffix
# letter, so a spec with `id: F-9A` and `milestone: M2` was dropped from its own milestone in
# SILENCE — exit 0, one feature reported where two declared membership, no finding anywhere. The
# split arrived when the suffix letter was added to the spec checker and this half was not, and it
# survived because the sort key below would raise on `F-9A` and nobody wanted the traceback.
# Reproduced on a two-spec fixture before this line changed.
FEATURE_RE = FEATURE_ID_RE

# Each task carries the document it was read from, so one set of checks serves both scopes: the
# per-plan run passes tasks from one file and the milestone run passes tasks from several, and a
# finding is charged to the right file either way without a second copy of any check.
Task = NamedTuple("Task", [("ident", str), ("line", int), ("lane", str), ("needs", list),
                           ("writes", list), ("covers", list), ("serialises", list),
                           ("where", dict), ("doc", Doc)])
Plan = NamedTuple("Plan", [("rel", str), ("tasks", list), ("waves", list), ("stuck", list)])
Milestone = NamedTuple("Milestone", [("name", str), ("rel", str), ("features", list),
                                     ("unplanned", list), ("tasks", list), ("waves", list),
                                     ("stuck", list)])


# --- reading the plan ---------------------------------------------------------------------------

def task_blocks(doc: Doc) -> list[tuple[int, list[str]]]:
    """Every ```task block, by way of the shared reader below."""
    return fenced_blocks(doc, "task")


def fenced_blocks(doc: Doc, label: str) -> list[tuple[int, list[str]]]:
    """Every ```<label> block as (the 1-based line of its opening fence, the lines inside it).

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
        if text[run:].strip() == label:
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
    lane = data.get("lane")
    if lane is None:
        f.add(doc, fence, "W0", "task block has no explicit `lane:`; every governed task must "
                                "declare `light` or `full` before dispatch")
        lane = "light"
    elif not isinstance(lane, str) or lane not in LANES:
        f.add(doc, at.get("lane", fence), "W0",
              f"lane `{lane}` is not one of {' | '.join(LANES)}")
        lane = "light"
    # A scalar where a list belongs is the commonest hand-edit; read it as the one-element list it
    # obviously is rather than dropping the value, which is how a checker starts lying.
    values = {key: [data[key]] if isinstance(data.get(key), str) and data[key] else
                   list(data.get(key) or []) for key in LIST_KEYS}
    if not values["writes"]:
        f.add(doc, at.get("writes", fence), "W0",
              "task block has no non-empty `writes:` boundary; light and full tasks must both "
              "declare the paths they may change before dispatch")
    elif any(isinstance(path, str) and not path.strip() for path in values["writes"]):
        f.add(doc, at.get("writes", fence), "W0",
              "task block has a blank member in `writes:`; every listed path must name part of "
              "the task's change boundary")
    return Task(ident, at.get("task", fence), lane, values["needs"], values["writes"],
                values["covers"], values["serialises"], at, doc)


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

    EVERY colliding pair is compared, not only same-wave pairs, because the wave-scoped version was
    defeated by its own advice: it told the planner to add a `needs` edge, and doing so moved the
    pair into different waves and silenced the finding while both tasks still owned one file. On a
    real 51-task graph, 41 such edges silenced all 37 collisions. A pair held apart by a dependency
    is reported as W6 until `serialises:` states that the shared ownership is deliberate — which
    turns a silent workaround into a declaration a reader can audit.
    """
    index = {task.ident: task for task in tasks}
    wave_of = {ident: number for number, wave in enumerate(waves, start=1) for ident in wave}
    for left, right in combinations(sorted(index), 2):
        one, two = index[left], index[right]
        hit = next(((a, b) for a in one.writes for b in two.writes if overlap(a, b)), None)
        if hit is None:
            continue
        same = wave_of.get(left) == wave_of.get(right)
        if same:
            f.add(two.doc, two.where.get("writes", two.line), "W4",
                  f"`{left}` and `{right}` are both in wave {wave_of[left]} and their write sets "
                  f"meet: `{hit[0]}` and `{hit[1]}` can match one path. Re-cut the tasks so the "
                  f"write sets are disjoint, or order them with `needs: [{left}]` on `{right}` and "
                  f"declare `serialises: [{left}]` so the shared ownership is stated")
        elif left not in two.serialises and right not in one.serialises:
            f.add(two.doc, two.where.get("writes", two.line), "W6",
                  f"`{left}` and `{right}` write the same paths (`{hit[0]}` and `{hit[1]}`) and are "
                  f"held apart only by a dependency edge. Declare `serialises: [{left}]` on "
                  f"`{right}` so the shared ownership is stated, or re-cut the write sets")


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


def feature_order(ident: str) -> tuple:
    """Sort key for a feature id. ONE implementation, because there were two and only one was fixed.

    The suffix letter sorts WITH its number — F-9, F-9A, F-9B, F-10 — where the raw string would put
    F-10 before F-9. `int(ident[2:])` raises outright on a suffix, and when the membership filter was
    widened to accept `F-9A` this second copy inside the printer was missed: the milestone then
    resolved both features and died with a ValueError while printing them. A derived rule written
    twice is a rule that drifts on the first edit.
    """
    digits = "".join(ch for ch in ident[2:] if ch.isdigit())
    return (int(digits) if digits else 0, ident)


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
    return sorted(set(members), key=feature_order)


def qualify(feature: str, tasks: Sequence[Task]) -> list[Task]:
    """Plan-local ids become `F-<id>/T<n>`, so `T1` in two features is two tasks and not one.

    A `needs` entry that already carries a feature is left exactly as written — that is the
    explicit cross-feature edge — and every other entry is read against THIS feature, which keeps
    the plan-local default intact in both scopes.

    `serialises` IS QUALIFIED BY THE SAME RULE, and it was not. The reference page documents
    `serialises: [T1]`, every reader of that key compares it against an id that is qualified here,
    and so the documented form matched nothing in the only scope where cross-feature collisions are
    visible: measured on a 51-task graph rebuilt from real fleet plans, declaring the documented
    `serialises: [T6]` on the pair that really collides left the W6 finding standing, while the
    undocumented `serialises: [F-1/T6]` silenced it. A key that works only when written the way the
    documentation does not say is a key that does nothing.
    """
    def resolve(entry: str) -> str:
        return entry if QUALIFY in entry else f"{feature}{QUALIFY}{entry}"
    return [task._replace(ident=f"{feature}{QUALIFY}{task.ident}",
                          needs=[resolve(need) for need in task.needs],
                          serialises=[resolve(partner) for partner in task.serialises])
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
        features = sorted({ident.split(QUALIFY)[0] for ident in wave}, key=feature_order)
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
            # `serialises` was the one key this interface omitted, and it is the one key a
            # dispatcher cannot do without: it is the declared mutex between two tasks that share a
            # write set on purpose. Without it a consumer reading this JSON can compute "their
            # `writes` overlap" but not "the overlap is deliberate and they must not run together",
            # so the interface described itself as the dispatch interface while withholding the
            # only thing that makes concurrent dispatch decidable.
            "tasks": {task.ident: {"feature": task.ident.split(QUALIFY)[0],
                                   "lane": task.lane, "needs": list(task.needs),
                                   "writes": list(task.writes), "covers": list(task.covers),
                                   "serialises": list(task.serialises),
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



# --- W7: what a commit actually wrote ------------------------------------------------------------
# The declared write set is the parallelism contract, and until now nothing compared it to reality.
# Measured on 16 sealed cards against their real commits: 4 of 83 files landed OUTSIDE the declaring
# task's set, and all four sat inside ANOTHER task's set — which is precisely the collision the
# wave check exists to prevent, happening at commit time where no check was looking. W4 and W6 read
# intent; this reads the tree.

# A subject reference is `F-12/T3` or a bare `T3`. Splitting the subject into bare words could not
# see the qualified form at all — `F-12/T3` tokenised to `F-12` and `T3` as separate words, so under
# a milestone (where every id carries its feature) NO subject ever resolved and W7 reported nothing.
# Measured on a two-feature fixture: a commit subject `F-7/T1` writing into F-8/T1's declared set —
# the exact defect W7 exists to catch — exited 0 with no findings.
COMMIT_TASK_RE = re.compile(r"(?<![\w/-])(?P<task>(?:F-\d+[A-Z]?/)?T[A-Za-z0-9._-]+)(?![\w/-])")

# WHICH UNRESOLVED REFERENCE IS WORTH A FINDING — measured, because the answer above was wrong.
# Over 2,672 real commit subjects in eight repositories the shape above matches 198 references and
# 136 of them (69%) are ordinary English: `TLS`, `TOTP`, `TTL`, `TDD`, `TOCTOU`, `Task`, `Tasks`,
# `TaskStop`, `Terraform`, `Telegram`, `Twilio`, `Timeline`, `Transport`, `TypeScript`,
# `THE_INVARIANT`, `Tier-1`, `TRS-C4`. Each one made W7 report "the card and the plan disagree"
# about a commit that never claimed a task. Every one of the 62 REAL references in that same corpus
# — `T1`..`T11`, `T1a`, `T1b`, `T-4`, `T-1b`, `T-FE1`, `T-DOCS`, `T-STEPUP` — carries a DIGIT OR A
# HYPHEN immediately after the `T`, and not one English word does. A qualified `F-9/...` reference
# is admitted whatever follows, because nothing writes that shape by accident.
# This gates the FINDING only. A plan that declares `task: TOTP` still resolves, because resolution
# is driven by the ids the scope actually declares and this pattern never gets to veto them.
COMMIT_ID_RE = re.compile(r"^(?:F-\d+[A-Z]?/)?T[0-9-]")

# `Implement TRS-C11 moderation backend T1-T5.` is a real subject. The trailing separator belongs to
# the sentence and not to the id, and carrying it made `T5.` resolve to nothing and then report
# itself as a card that had drifted.
REF_TAIL = "._-"


def plan_feature(doc: Doc) -> list[str]:
    """Every id this plan answers to, for resolving a qualified commit reference.

    Three spellings exist in the wild and depending on one of them is how this check came to read
    nothing: the template writes `feature:`, older plans wrote `id:`, and the filename carries the
    id under the same `F-12-slug.md` rule the milestone loader already uses. Any of the three
    qualifying the same task is unambiguous, so all three are accepted rather than one enforced —
    enforcing here would report a naming finding from the scheduler, which is the spec checker's
    job and would be reported twice.
    """
    names = []
    for key in ("feature", "id"):
        value = doc.front.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    stem = Path(doc.rel).stem
    head = stem.split("-")[0] + "-" + stem.split("-")[1] if stem.count("-") >= 1 else stem
    if FEATURE_ID_RE.match(head):
        names.append(head)
    return list(dict.fromkeys(names))


def commit_paths(root: Path, commit: str) -> list[str]:
    """Files a commit touched. A merge has no single author's write set, so it is skipped."""
    parents = git(root, "rev-list", "--parents", "-n", "1", commit) or ""
    if len(parents.split()) > 2:
        return []
    listed = git(root, "show", "--name-only", "--pretty=format:", commit) or ""
    return [line.strip() for line in listed.splitlines() if line.strip()]


def task_index(tasks: Sequence[Task]) -> tuple[dict, dict]:
    """The two lookups a commit reference resolves against: qualified ids, and bare-id buckets.

    ONE copy, used by `--commit` and by `--since` alike. A second copy of this is exactly how W7
    came to match a bare `T1` and never the qualified `F-7/T1` this methodology tells people to
    write: two readers of the same id drift the moment one of them is fixed.
    """
    index = {task.ident: task for task in tasks}
    # A bare `T1` is unambiguous inside one plan and ambiguous across a milestone, where two
    # features may each own a `T1`. Resolve it only when exactly one task answers to it.
    bare: dict[str, list[Task]] = {}
    for task in tasks:
        bare.setdefault(task.ident.split(QUALIFY)[-1], []).append(task)
        # Per-plan scope carries bare idents, so a correctly-written `F-7/T1` subject would not have
        # resolved there either. The plan's own `feature:` supplies the qualifier.
        if QUALIFY not in task.ident:
            for qualifier in plan_feature(task.doc):
                index.setdefault(f"{qualifier}{QUALIFY}{task.ident}", task)
    return index, bare


def resolve_subject(subject: str, index: dict, bare: dict) -> tuple[list, list]:
    """The tasks one commit subject names, and the task-shaped ids that resolved to nothing."""
    named, unresolved = [], []
    for ref in COMMIT_TASK_RE.findall(subject):
        ref = ref.rstrip(REF_TAIL)
        if ref in index:
            named.append(index[ref])
        elif QUALIFY not in ref and len(bare.get(ref, [])) == 1:
            named.append(bare[ref][0])
        elif COMMIT_ID_RE.match(ref):
            unresolved.append(ref)
    return named, unresolved


def check_commit_writes(root: Path, commit: str, tasks: Sequence[Task], f: Findings,
                        subject: str | None = None) -> int:
    """W7, for the task the commit subject names. Returns the number of files checked.

    The task is taken from the commit SUBJECT, which is where this methodology already puts the id
    (`commit_subject` is a full-card field and an inline light-dispatch field). A commit naming no
    known task is not a finding: ordinary repository commits may sit outside governed execution,
    and inventing a violation for them would make the check fire until somebody removed it.

    `subject` is passed in by `--since`, which has already read the whole log in one call; leaving
    it None reads the one commit here, which is what `--commit REV` needs.
    """
    if subject is None:
        subject = git(root, "log", "-1", "--format=%s", commit) or ""
    index, bare = task_index(tasks)
    named, unresolved = resolve_subject(subject, index, bare)
    # Silence here was the second half of the same defect. A subject naming NO task did not claim
    # governed work and stays silent, but a subject that names a task-shaped id which does not
    # resolve is a card that has drifted from its plan, and reporting nothing let it push clean.
    if not named and unresolved:
        doc = tasks[0].doc if tasks else None
        if doc is not None:
            f.add(doc, tasks[0].line, "W7",
                  f"commit subject names {', '.join(sorted(set(unresolved)))}, which no task in "
                  "scope declares — the card and the plan disagree about what this work is")
        return 0
    if len(named) != 1:
        return 0
    task = named[0]
    stray = [path for path in commit_paths(root, commit)
             if not any(overlap(path, glob) for glob in task.writes)]
    for path in stray:
        owner = next((other.ident for other in tasks if other.ident != task.ident
                      and any(overlap(path, glob) for glob in other.writes)), None)
        f.add(task.doc, task.where.get("writes", task.line), "W7",
              f"`{task.ident}` wrote `{path}`, which its `writes` does not cover"
              + (f" — `{owner}` declares it, so the two tasks shared a file the plan said they "
                 "did not" if owner else "; widen the write set or split the task"))
    return len(stray)


# --- derived state: where the milestone actually is ----------------------------------------------
# A LEDGER IS A CLAIM AND GIT IS THE FACT. The agent that keeps the ledger is the agent the ledger
# would bind, and no in-process control binds its own operator; so status is RE-DERIVED from
# (plans, `git log <base>..HEAD`) on every run and held nowhere. That is also what makes a context
# loss survivable: the loop recomputes instead of trusting a recollection, and a task dropped by a
# replan surfaces as an unresolved commit rather than vanishing.

LOG_SEP = "\x1f"     # a subject may contain anything a shell allows, including tabs; \x1f may not

Status = NamedTuple("Status", [("ident", str), ("state", str), ("blocked_on", list),
                               ("commits", list)])
STATES = ("done", "duplicate", "in-flight", "ready", "blocked")


def commit_log(root: Path, rev: str) -> list[tuple[str, str]] | None:
    """`(sha, subject)` for `<rev>..HEAD`, oldest first, or None when the range cannot be read.

    None rather than an empty list, and the caller turns it into exit 2. An unreadable revision
    that answered "no commits" would read exactly like "nothing has been done yet", which is the
    one answer a resume primitive must never give by accident.
    """
    out = git(root, "log", "--reverse", f"--format=%H{LOG_SEP}%s", f"{rev}..HEAD")
    if out is None:
        return None
    rows = []
    for line in out.splitlines():
        sha, _, subject = line.partition(LOG_SEP)
        if sha.strip():
            rows.append((sha.strip(), subject.strip()))
    return rows


def derive_status(root: Path, rev: str, tasks: Sequence[Task], in_flight: Sequence[str],
                  f: Findings) -> tuple[list, list]:
    """Per-task state out of `<rev>..HEAD`, and the commits that named no task in scope.

    `done` is "a commit in the range resolves to this task", by the SAME resolution `--commit`
    uses — not a checkbox, not a ledger line. W7 runs over every commit in the range as a side
    effect, so a resume also re-audits what the finished work actually wrote.

    `duplicate` is REPORTED AND NOT FAILED. Two commits naming one task is a follow-up fix as often
    as it is a re-dispatch, and a rule that fires on the ordinary case gets switched off. It counts
    as done for every dependency, because the work landed either way.

    `in-flight` is the one ADVISORY input here, and it is an argument rather than a file: what is
    running is the only thing git cannot say, and writing it down would recreate the ledger this
    exists to replace.
    """
    log = commit_log(root, rev)
    if log is None:
        raise SpecError(f"cannot read the commit range `{rev}..HEAD`; --since takes a revision "
                        "this repository can resolve")
    index, bare = task_index(tasks)
    landed: dict[str, list[str]] = {task.ident: [] for task in tasks}
    unclaimed: list[dict] = []
    for sha, subject in log:
        named, unresolved = resolve_subject(subject, index, bare)
        for task in named:
            landed[task.ident].append(sha)
        if not named and unresolved:
            unclaimed.append({"commit": sha, "subject": subject,
                              "names": sorted(set(unresolved))})
        # The finding for both cases — a stray path, and a task-shaped id that resolves to nothing
        # — belongs to W7 and is raised there, so this loop never grows a second copy of it.
        check_commit_writes(root, sha, tasks, f, subject=subject)
    known = {task.ident for task in tasks}
    done = {ident for ident, shas in landed.items() if shas}
    running = set(in_flight)
    states = []
    for task in tasks:
        shas = landed[task.ident]
        # Only edges this scope can resolve block anything; a dangling edge is W1's finding, and
        # counting it as a blocker here would report the same defect twice and wedge the dispatcher.
        blocked = sorted(need for need in task.needs
                         if need in known and need != task.ident and need not in done)
        if len(shas) > 1:
            state = "duplicate"
        elif shas:
            state = "done"
        elif task.ident in running:
            state = "in-flight"
        elif blocked:
            state = "blocked"
        else:
            state = "ready"
        states.append(Status(task.ident, state, blocked, shas))
    return states, unclaimed


def criterion_priorities(root: Path) -> dict[str, dict[str, int]]:
    """`{feature id: {criterion number: 1|2|3}}`, read from the OPTIONAL `[P<n>]` tag on a criterion.

    The tag is read through `spec_check.criteria()`, so it is read out of the same fold, with the
    same fence rule, as every criterion check — a criterion wrapped over three lines carries its tag
    on the last of them, and a line-at-a-time reader here would have missed every wrapped one.

    A spec that marks nothing contributes nothing, which is the common case and has to stay free:
    measured across two real repositories, 0 of 995 criteria carry a tag today.
    """
    directory = root / "docs" / "product" / "specs"
    table: dict[str, dict[str, int]] = {}
    for path in sorted(directory.glob("F-*.md")) if directory.is_dir() else []:
        if not path.is_file():
            continue
        doc = Doc(path, root)
        identifier = doc.scalar("id")
        if doc.front_error or not FEATURE_RE.match(identifier):
            continue
        marked: dict[str, int] = {}
        for item in criteria(doc):
            tag = PRIORITY_TAG_RE.search(item.result.rstrip())
            if tag:
                # The BEST of the values on one criterion. Two tags on one criterion is an authoring
                # slip, not a dispatch question, and refusing to order the task over it would make
                # the operator fix a document to get a schedule back.
                value = int(tag.group(1))
                marked[item.number] = min(value, marked.get(item.number, value))
        if marked:
            table[identifier] = marked
    return table


def task_priorities(tasks: Sequence[Task], table: dict[str, dict[str, int]]) -> dict[str, int]:
    """The rank each task inherits from the criteria it covers: the BEST one it carries.

    A task takes the priority of the most important criterion in its `covers:` because the task has
    to run for that criterion to close at all; the criterion's rank is the task's floor, and taking
    the worst instead would bury a P1 behind whatever else the task happened to also satisfy.
    """
    ranks: dict[str, int] = {}
    for task in tasks:
        feature = task.ident.split(QUALIFY)[0]
        marked = table.get(feature)
        if not marked:
            continue
        values = [marked[reference[3:]] for reference in task.covers
                  if reference.startswith("AC-") and reference[3:] in marked]
        if values:
            ranks[task.ident] = min(values)
    return ranks


def unlocks(tasks: Sequence[Task]) -> dict:
    """How many tasks sit transitively downstream of each id — the dispatch priority.

    Removing the barrier is only half the gain. Measured on the reconstructed 51-task graph, a ready
    set dispatched in id order is no faster than the waves it replaced and at five writers is
    SLOWER; ordered by this count it is 11%-22% faster across two to eight writers. Longest-chain
    first is the standard list-scheduling heuristic and this is its cheapest usable proxy.
    """
    forward: dict[str, set] = {task.ident: set() for task in tasks}
    for task in tasks:
        for need in task.needs:
            if need in forward:
                forward[need].add(task.ident)
    counts = {}
    for start in forward:
        seen, stack = set(), list(forward[start])
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(forward.get(node, ()))
        counts[start] = len(seen)
    return counts


def dispatch_block(task: Task, running: Sequence[Task]) -> str | None:
    """Why this task may not start beside those, or None. The wave certificate, applied to a SET.

    `serialises` is tested before the write sets so the message names the DECLARED mutex rather
    than the overlap that implies it: a pair that serialises always overlaps, and reporting the
    overlap would tell the reader to fix something that is already deliberate.
    """
    for other in running:
        if other.ident == task.ident:
            continue
        if other.ident in task.serialises or task.ident in other.serialises:
            return f"serialises with `{other.ident}`, which is in flight"
    for other in running:
        if other.ident == task.ident:
            continue
        hit = next(((a, b) for a in task.writes for b in other.writes if overlap(a, b)), None)
        if hit is not None:
            return (f"writes `{hit[0]}`, which meets `{hit[1]}` in `{other.ident}`, "
                    "which is in flight")
    return None


def ready_set(tasks: Sequence[Task], states: Sequence[Status], in_flight: Sequence[str],
              limit: int | None = None,
              priority: dict[str, int] | None = None) -> tuple[list, list]:
    """The tasks that may start NOW, and the ones deferred with the reason they were.

    Each admitted task JOINS the in-flight set for the candidates after it, so the emitted set is
    legal against itself and not only against what was already running. That matters because the
    milestone need not be clean: on a graph that still has W4 findings this still hands back a set
    no two members of which collide, instead of a set that is only safe if the plan was.

    CRITERION PRIORITY IS THE TIEBREAK AND NEVER THE PRIMARY KEY. `unlocks` is a measured throughput
    ordering — 11%-22% faster than id order, which was itself SLOWER than the barrier at five
    writers — and a P1 leaf dispatched ahead of a P3 task that unlocks twenty hands that back. What
    priority replaces is the LAST key, `task.ident`, which is alphabetical and which the operator
    has been overriding from memory.

    It is inserted AFTER the feature, so it can only reorder tasks WITHIN one feature. Ids are
    qualified `F-<id>/T<n>` and `/` sorts below every digit and letter that can follow a feature id,
    so ordering by feature-then-ident is exactly ordering by ident: this key is today's key with one
    slot opened inside each feature. A spec that marks nothing is dispatched bit-for-bit as before.
    Priority is deliberately NOT compared across features. A spec author ranks their own criteria
    and has ranked nobody else's, so a global priority key would let the first feature to adopt the
    notation demote every feature that had not — unprioritised reading as last, which is the same
    inversion as unprioritised reading as all-P1, arriving through the dispatcher instead of a
    checker. Across features the milestone already decides, and it decides by id.
    """
    index = {task.ident: task for task in tasks}
    rank = unlocks(tasks)
    ranked = priority or {}
    running = [index[ident] for ident in in_flight if ident in index]
    candidates = sorted((index[s.ident] for s in states if s.state == "ready" and s.ident in index),
                        key=lambda task: (-rank.get(task.ident, 0), task.ident.split(QUALIFY)[0],
                                          ranked.get(task.ident, UNRANKED), task.ident))
    chosen, deferred = [], []
    for task in candidates:
        reason = dispatch_block(task, running)
        if reason is None and limit is not None and len(chosen) >= limit:
            reason = f"--limit {limit} reached"
        if reason is None:
            chosen.append(task)
            running.append(task)
        else:
            deferred.append({"task": task.ident, "reason": reason})
    return chosen, deferred


def status_json(states: Sequence[Status], unclaimed: Sequence[dict], chosen: Sequence[Task],
                deferred: Sequence[dict], rev: str, in_flight: Sequence[str],
                limit: int | None, priority: dict[str, int] | None = None) -> dict:
    """The `--since`/`--ready` half of the dispatch interface.

    `complete` is a KEY AND NOT AN EXIT CODE. Exit 1 means findings; a milestone that is merely
    half-built has no findings, and overloading exit 1 with "not finished yet" would make the
    resume primitive fail on every run until the last one — which is the shape of a check that
    gets switched off.
    """
    return {"since": rev, "in_flight": list(in_flight), "limit": limit,
            "complete": all(s.state in ("done", "duplicate") for s in states) and bool(states),
            "counts": {name: sum(1 for s in states if s.state == name) for name in STATES},
            "status": {s.ident: {"state": s.state, "blocked_on": list(s.blocked_on),
                                 "commits": list(s.commits)} for s in states},
            "unclaimed_commits": [dict(item) for item in unclaimed],
            "ready": [task.ident for task in chosen],
            # EVERY task that inherited one, not only the dispatched ones. The key is here so the
            # tiebreak is visible rather than inferred from an order: an empty object says the
            # milestone's specs marked nothing and `ready` is in plain id order, which is a
            # different statement from "priority was read and changed nothing".
            "priority": {ident: f"P{value}" for ident, value in sorted((priority or {}).items())},
            "deferred": [dict(item) for item in deferred]}


def print_status(payload: dict, states: Sequence[Status]) -> None:
    counts = payload["counts"]
    print(f"since {payload['since']}  " + "  ".join(f"{counts[name]} {name}" for name in STATES)
          + ("  MILESTONE COMPLETE" if payload["complete"] else ""))
    for state in states:
        detail = ""
        if state.state == "blocked":
            detail = "  <- " + ", ".join(state.blocked_on)
        elif state.commits:
            detail = "  " + " ".join(sha[:9] for sha in state.commits)
        print(f"  {state.state:<9} {state.ident}{detail}")
    for item in payload["unclaimed_commits"]:
        print(f"  UNCLAIMED {item['commit'][:9]}  names {', '.join(item['names'])}  "
              f"{item['subject']}")
    if payload["ready"]:
        print(f"  READY {len(payload['ready'])}  {', '.join(payload['ready'])}")
    for item in payload["deferred"]:
        print(f"  DEFERRED  {item['task']}  {item['reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--milestone", metavar="M<n>",
                        help="schedule every feature whose spec declares this milestone as ONE "
                             "graph, with qualified `F-<id>/T<n>` task ids")
    parser.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    parser.add_argument("--commit", metavar="REV",
                        help="also check that this commit wrote only what its task declared")
    parser.add_argument("--since", metavar="REV",
                        help="derive per-task status from the commits in REV..HEAD, and run the "
                             "commit-versus-declaration check over every one of them")
    parser.add_argument("--in-flight", metavar="ID[,ID...]", default="",
                        help="qualified ids already running; the one thing git cannot tell this "
                             "script, and an argument rather than a file on purpose")
    parser.add_argument("--ready", action="store_true",
                        help="also emit the dispatchable set: needs done, writes disjoint from "
                             "everything in flight, no `serialises` partner in flight")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="the operator's own cap on the dispatchable set (default: none; the "
                             "module docstring argues why no number is compiled in)")
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
    # Refused rather than answered across plans. Task ids are plan-local, so `T1` names a different
    # task in every feature; a merged status view over the per-plan scope would resolve no bare
    # subject at all and report the whole fleet as `ready`, which is the most dangerous wrong answer
    # this script could give. The milestone is the scope where the ids are qualified.
    if (args.since or args.ready) and not args.milestone:
        print("ERROR: --since and --ready need --milestone M<n>; task ids are plan-local, so "
              "status across plans would fuse every feature's `T1` into one task", file=sys.stderr)
        return 2
    if args.ready and not args.since:
        print("ERROR: --ready needs --since REV; the dispatchable set is derived from what is "
              "already done, and there is no other source for that", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        print(f"ERROR: --limit takes a positive count, not {args.limit}", file=sys.stderr)
        return 2
    in_flight = [item.strip() for item in args.in_flight.split(",") if item.strip()]
    status_payload, states = None, []
    try:
        if args.milestone:
            found, milestone = run_milestone(root.resolve(), args.milestone)
            # This call was absent, which made `--milestone M<n> --commit REV` accept the flag and
            # silently never check it — the milestone view is the ONLY one that can see a commit
            # landing in another FEATURE's declared set, since a per-plan run never loads the other
            # plan. The scope that mattered most was the scope that was not wired.
            if args.commit and milestone is not None and milestone.tasks:
                check_commit_writes(root.resolve(), args.commit, milestone.tasks, found)
            if args.since:
                if milestone is None or not milestone.tasks:
                    print(f"ERROR: nothing to derive status for: milestone {args.milestone} has no "
                          "task in any plan", file=sys.stderr)
                    return 2
                known = {task.ident for task in milestone.tasks}
                # An in-flight id naming no task is exit 2 and not a finding. It means the caller
                # and the plan disagree about what exists — usually a replan that dropped the task
                # — and continuing would compute a ready set against a mutex that is not there.
                unknown = [ident for ident in in_flight if ident not in known]
                if unknown:
                    print(f"ERROR: --in-flight names {', '.join(sorted(unknown))}, which no task "
                          f"in {args.milestone} declares; ids are qualified, as `F-9/T1`",
                          file=sys.stderr)
                    return 2
                states, unclaimed = derive_status(root.resolve(), args.since, milestone.tasks,
                                                  in_flight, found)
                # Read only for `--ready`: it is the only mode that orders anything, and a `--since`
                # status view that opened every spec to compute a key it never uses would be paying
                # for a schedule nobody asked for.
                ranked = (task_priorities(milestone.tasks, criterion_priorities(root.resolve()))
                          if args.ready else {})
                chosen, deferred = (ready_set(milestone.tasks, states, in_flight, args.limit,
                                              ranked) if args.ready else ([], []))
                status_payload = status_json(states, unclaimed, chosen, deferred, args.since,
                                             in_flight, args.limit, ranked)
        else:
            found, plans = run(root.resolve())
            if args.commit:
                every = [task for plan in plans for task in plan.tasks]
                check_commit_writes(root.resolve(), args.commit, every, found)
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = sorted(found)
    code = 1 if findings else 0
    if args.milestone:
        if args.json or args.ready:
            # `--ready` emits JSON whether or not `--json` was asked for: the dispatchable set
            # exists to be consumed by a program, and a caller that had to parse a printed line
            # would rebuild the id join this interface is here to hand over.
            payload = milestone_json(root.resolve(), milestone, findings, code)
            if status_payload is not None:
                payload.update(status_payload)
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return code
        print_findings(findings)
        if milestone is not None:
            print_milestone(milestone)
        if status_payload is not None:
            print_status(status_payload, states)
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
