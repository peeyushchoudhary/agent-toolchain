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
  W1  a `needs` edge to a task id no block in the plan declares
  W2  a cycle, named as the shortest one found
  W3  the same task id declared twice in one plan
  W4  two tasks in the SAME computed wave whose `writes` globs can match one path
  W5  size: more than 5 write globs, `covers` empty, or more than 12 full-lane tasks in a feature

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

Usage:  plan_waves.py [--root DIR] [--json]
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

Task = NamedTuple("Task", [("ident", str), ("line", int), ("lane", str), ("needs", list),
                           ("writes", list), ("covers", list), ("where", dict)])
Plan = NamedTuple("Plan", [("rel", str), ("tasks", list), ("waves", list), ("stuck", list)])


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
                values["covers"], at)


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

def check_edges(doc: Doc, tasks: Sequence[Task], f: Findings) -> None:
    known = {task.ident for task in tasks}
    for task in tasks:
        for need in task.needs:
            if need not in known:
                f.add(doc, task.where.get("needs", task.line), "W1",
                      f"`{task.ident}` needs `{need}`, which no task block in this plan declares; "
                      "the edge orders nothing and the task will dispatch in the first wave")
            elif need == task.ident:
                f.add(doc, task.where.get("needs", task.line), "W1",
                      f"`{task.ident}` needs itself")


def check_size(doc: Doc, tasks: Sequence[Task], f: Findings) -> None:
    for task in tasks:
        if len(task.writes) > MAX_WRITES:
            f.add(doc, task.where.get("writes", task.line), "W5",
                  f"`{task.ident}` writes {len(task.writes)} globs; more than {MAX_WRITES} is two "
                  "tasks wearing one id, and it is the pair that collides with everything")
        if not task.covers:
            f.add(doc, task.line, "W5", f"`{task.ident}` covers no acceptance criterion, so "
                                        "nothing states what finishing it would prove")
    full = [task.ident for task in tasks if task.lane == "full"]
    if len(full) > MAX_FULL_LANE:
        f.add(doc, tasks[0].line, "W5",
              f"{len(full)} full-lane tasks in one feature (the limit is {MAX_FULL_LANE}): this is "
              "two features, and no wave plan repairs a feature that is too big")


def check_wave_writes(doc: Doc, tasks: Sequence[Task], waves: Sequence[Sequence[str]],
                      f: Findings) -> None:
    """W4. Tasks in one wave run at the same time, so their write sets must be disjoint.

    Reported, never repaired: naming the pair sends the planner back to the decomposition, while
    quietly moving one task down a wave would report a green schedule for a plan that still says
    two agents own one file.
    """
    index = {task.ident: task for task in tasks}
    for number, wave in enumerate(waves, start=1):
        for left, right in combinations(wave, 2):
            one, two = index[left], index[right]
            hit = next(((a, b) for a in one.writes for b in two.writes if overlap(a, b)), None)
            if hit is None:
                continue
            f.add(doc, two.where.get("writes", two.line), "W4",
                  f"`{left}` and `{right}` are both in wave {number} and their write sets meet: "
                  f"`{hit[0]}` and `{hit[1]}` can match one path. Re-cut the tasks so the write "
                  f"sets are disjoint, or add `needs: [{left}]` to `{right}` and own the "
                  "serialisation — this is not resolved automatically")


def run(root: Path) -> tuple[Findings, list[Plan]]:
    """Every plan under `docs/product/plans/`. A repository without that directory is silent: a
    checker that shouts at a repository which never adopted the layout gets switched off."""
    f, plans = Findings(), []
    directory = root / "docs" / "product" / "plans"
    for path in sorted(directory.glob("F-*.md")) if directory.is_dir() else []:
        if not path.is_file():
            continue
        doc = Doc(path, root)
        tasks = read_plan(doc, f)
        if not tasks:
            continue
        check_edges(doc, tasks, f)
        check_size(doc, tasks, f)
        waves, stuck = schedule(tasks)
        if stuck:
            cycle = shortest_cycle(tasks, stuck)
            f.add(doc, next(t.line for t in tasks if t.ident == (cycle or stuck)[0]), "W2",
                  f"cycle: {' -> '.join(cycle) if cycle else ' -> '.join(stuck)}. "
                  f"{len(stuck)} task(s) cannot be scheduled until one of those edges is removed")
        check_wave_writes(doc, tasks, waves, f)
        plans.append(Plan(doc.rel, tasks, waves, stuck))
    return f, plans


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        found, plans = run(root.resolve())
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = sorted(found)
    code = 1 if findings else 0
    if args.json:
        json.dump({"root": str(root.resolve()), "count": len(findings), "exit": code,
                   "plans": [{"path": plan.rel, "tasks": len(plan.tasks),
                              "waves": [{"wave": number, "width": len(wave), "tasks": list(wave)}
                                        for number, wave in enumerate(plan.waves, start=1)],
                              "unscheduled": plan.stuck} for plan in plans],
                   "findings": [item._asdict() for item in findings]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return code
    if findings:
        width = max(len(f"{item.path}:{item.line}") for item in findings[:PRINT_CAP])
        for item in findings[:PRINT_CAP]:
            print(f"{item.path}:{item.line}".ljust(width) + f"  {item.rule}  {item.message}")
        if len(findings) > PRINT_CAP:
            print(f"... and {len(findings) - PRINT_CAP} more finding(s); fix these and run again")
        print()
    print_plans(plans)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
