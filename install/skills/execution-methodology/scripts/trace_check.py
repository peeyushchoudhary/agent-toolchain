#!/usr/bin/env python3
"""Diff what a feature REQUIRES, what its plan DECLARES and what actually EXECUTED, and report the
gaps. This script writes nothing, ever.

WHAT IT PROVES, AND THE LIMIT THAT NEVER LEAVES THIS PAGE: it proves a test CARRYING A CRITERION ID
RAN AND PASSED inside a run `verify_junit.py` already certified fresh and green. It does NOT prove
the test asserts anything — `void ac2() {}` passes, and this counts it. Nothing printed here may be
read as "the criterion is met", only as "a test claiming it ran"; that gap is closed by the plan's
`assert` and `and_not` fields and by a reviewer, never here.

THE CARRIER IS THE TEST'S OWN NAME, because nothing else survives: over 51,604 real result files
and 267,943 testcases, `<property>` elements number ZERO while `name=` and `classname=` are always
there, and BOTH are read — 3.0% of those cases are parameterised, so `name=` holds `[2] 2026-12-31`
and the method name is gone. A testcase carrying no id at all is COUNTED AND PRINTED every run: it
is not a pass, it is a test this cannot see. references/junit-evidence.md has the measurements.

    <behaviour>__F<feature>_AC<n>    resendsInWindow__F7_AC2; one test, many ids: `_AC2_AC4`
    F-7/AC-2                         the same id in prose: a coverage row or a `covers:`
    a bare `AC-4` in a test name     refused by T4, never guessed at; a plan's `feature:` qualifies

  T0  an unreadable input: an approved spec with no criteria, a plan with no `feature:`, a
      coverage row with an unknown level — a checker silent on those reports a false green
  T1  a criterion with no coverage row      T4  a test citing an id no spec declares
  T2  a row naming no criterion             T5  the coverage map and the absence claim disagreeing
  T3  a criterion no executed test carries  T6  a test citing an id retired in `withdrawn:`
  T7  (--commit only) an id that ARRIVED in the range on a test whose BODY the range never touched

T7 EXISTS BECAUSE T3 IS SATISFIABLE BY A RENAME. Across four real repositories 0 of 5,866 `@Test`
methods carry a criterion id today, so every one of them is one `sed` away from making T3 green, and
that rename is the cheapest green this toolchain offers. `--commit RANGE` adds the second half of
the claim: the test that carries a newly-arrived id must ALSO have had body lines added or changed
inside that range. A rename writes one signature line and no body line, so T7 fires on it.

WHAT T7 DOES NOT PROVE, and this line stays here: it does not prove the body ASSERTS anything — a
body changed to `{ /* TODO */ }` satisfies T7 exactly as a real assertion does, because that is all
"the body changed" can mean. It does not judge an id that already existed before RANGE: those are
COUNTED AND PRINTED as "not new in the range", never silently passed. It is deliberately not a Java
check — it matches the executed test's own name against changed line ranges in a diff and parses no
language — so a project whose tests are Python or TypeScript gets the same rule and the same limit.

Usage:  trace_check.py [--root DIR] [--evidence FILE ...] [--commit RANGE] [--json]
Exit codes: 0 clean or an input was absent AND IS NAMED, 1 findings, 2 the arguments or the evidence
could not be read: evidence that cannot be re-read is not evidence, and "traced clean" must never
print the same way as "traced nothing". A `--commit RANGE` git cannot resolve is 2 for that reason.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from plan_waves import fenced_blocks
from spec_check import (PRINT_CAP, Doc, Finding, Findings, SpecError, criteria, git,
                        parse_front_matter)

LIVE = ("approved", "building", "shipped")   # "approved or later": a draft spec binds nobody yet
LEVELS = ("unit", "integration", "e2e", "none")
# One regex reads both spellings; `_AC4` chained after `F7_AC2` inherits the feature to its left.
CITE_RE = re.compile(r"(?<![A-Za-z0-9])(?:F-?(\d+[A-Z]?)[_/])?AC-?(\d+[A-Z]?)(?![A-Za-z0-9])")
COVERAGE_RE = re.compile(r"^#{2,6}\s+coverage map\b", re.IGNORECASE)
ABSENCE_RE = re.compile(r"^#{2,6}\s+not tested\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s")
# A finding out of XML has no line to cite and says so rather than inventing a plausible one.
XML_SOURCE, NO_LINE = "(executed tests)", 0

Key = NamedTuple("Key", [("feature", str), ("number", str)])
Stats = NamedTuple("Stats", [("files", int), ("cases", int), ("by_name", int), ("by_class", int),
                             ("unattributable", int)])
# T7's own denominator, printed every run so an inert T7 cannot read like a clean one.
Bodies = NamedTuple("Bodies", [("green", int), ("arrived", int), ("worked", int), ("stale", int)])
Spec = NamedTuple("Spec", [("doc", Doc), ("live", bool), ("numbers", dict), ("withdrawn", dict)])
Plan = NamedTuple("Plan", [("doc", Doc), ("feature", str), ("rows", dict), ("covers", list),
                           ("absent", dict)])


def normalise(part: str) -> str:
    """`F-007` is `F007` and `AC-08A` is `AC-8A`: a method name cannot hold a hyphen, so both
    spellings coexist by construction and must compare equal."""
    digits = part.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return (digits.lstrip("0") or "0") + part[len(digits):]


def cites(text: str, feature: str | None = None) -> list[Key]:
    """Every criterion id in one string, bound to the nearest feature qualifier to its left, or to
    `feature`, the plan's own. `""` means unqualified, which T4 refuses rather than guesses at."""
    found = []
    for match in CITE_RE.finditer(text or ""):
        feature = normalise(match.group(1)) if match.group(1) else feature
        found.append(Key(feature or "", normalise(match.group(2))))
    return found


def read_specs(root: Path, f: Findings) -> dict[str, Spec]:
    """Every spec by normalised feature id, drafts included: only T1/T3 need approved-or-later."""
    directory, specs = root / "docs" / "product" / "specs", {}
    for path in sorted(directory.glob("F-*.md")) if directory.is_dir() else []:
        doc = Doc(path, root)
        identifier = doc.scalar("id")
        if doc.front_error or not identifier:
            continue     # spec_check owns that finding; a second copy of it would be printed twice
        numbers, live = {item.number: item.line for item in criteria(doc)}, doc.scalar("status")
        raw = doc.front.get("withdrawn") or []
        if live in LIVE and not numbers:
            f.add(doc, 1, "T0", "an approved-or-later spec whose body parses to no acceptance "
                                "criteria; every check below would pass this feature in silence")
        specs[normalise(identifier.lstrip("F-"))] = Spec(doc, live in LIVE, numbers, {
            normalise(item): doc.at("withdrawn")
            for item in ([raw] if isinstance(raw, str) else raw) if item.strip()})
    return specs


def read_plans(root: Path, f: Findings) -> list[Plan]:
    """Every feature plan: the table under `### Coverage map`, the `covers:` of each ```test block,
    and the criteria `### Not tested, and why` gives up on. NOTHING ELSE IN THE FILE DECLARES
    ANYTHING — a criterion named in prose is not a claim that a test exists — and a row whose level
    is unreadable is T0 rather than skipped, since skipping it would exempt it from T3 silently."""
    directory, plans = root / "docs" / "product" / "plans", []
    for path in sorted(directory.glob("F-*.md")) if directory.is_dir() else []:
        doc = Doc(path, root)
        identifier = doc.scalar("feature")
        if doc.front_error:
            continue     # plan_waves owns the unreadable-plan finding, for the same reason
        if not identifier:
            f.add(doc, 1, "T0", "the plan declares no `feature:`, so a bare `AC-4` in its coverage "
                                "map names no criterion in particular and nothing here can be read")
            continue
        feature, rows, absent, inside = normalise(identifier.lstrip("F-")), {}, {}, ""
        for number, text in doc.body():
            if HEADING_RE.match(text):
                inside = ("rows" if COVERAGE_RE.match(text)
                          else "absent" if ABSENCE_RE.match(text) else "")
            elif inside == "absent":
                absent.update({key.number: number for key in cites(text, feature)})
            elif inside == "rows" and text.strip().startswith("|"):
                cells = [cell.strip() for cell in text.strip().strip("|").split("|")]
                found = cites(cells[0], feature)
                if len(found) != 1 or not cells[0].upper().startswith(("AC", "F")):
                    continue     # the header row and the `|---|` rule
                level = (cells[1] if len(cells) > 1 else "").lower()
                if level in LEVELS:
                    rows[found[0].number] = (level, number)
                else:
                    f.add(doc, number, "T0", f"coverage row for AC-{found[0].number} has level "
                          f"{level or '(empty)'!r}, not one of {' | '.join(LEVELS)}; an unreadable "
                          "level exempts that criterion from T3 in silence")
        covers = []
        for fence, block in fenced_blocks(doc, "test"):
            try:
                data, where, _ = parse_front_matter(["---"] + block + ["---"])
            except SpecError:
                continue     # an unparseable ```test block is one finding, and it is plan_waves'
            raw = data.get("covers") or []
            covers += [(key, fence + where.get("covers", 1) - 1)
                       for item in ([raw] if isinstance(raw, str) else raw)
                       for key in cites(item, feature)]
        plans.append(Plan(doc, feature, rows, covers, absent))
    return plans


def read_evidence(paths: list[Path]) -> tuple[dict[Key, list[str]], Stats]:
    """Every `(classname, name)` pair from the XML each receipt certified, re-read from disk.
    THE RECEIPT IS NOT TAKEN AT ITS WORD, and it is not re-verified either: `verify_junit.py`
    performed the single write and consumed the nonce, so this re-applies that run's own boundary
    to the files it named — mtime and ctime after the start, mtime NOT AFTER the moment
    verification finished, and the file count, class set and testcase total still matching. The
    upper bound is what stops the cheapest attack the receipt alone allows: a second, narrower
    `--tests '*AC4*'` run fired after the green gate satisfies "newer than the start" perfectly."""
    executed: dict[Key, list[str]] = {}
    files = cases = by_name = by_class = unattributable = 0
    for path in paths:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            results, total = Path(receipt["result_directory"]), int(receipt["tests"])
            started, declared = int(receipt["started_at_unix_ns"]), int(receipt["result_file_count"])
            classes = set(receipt["distinct_classes"])
            ceiling = int(datetime.fromisoformat(
                receipt["verified_at_utc"].replace("Z", "+00:00")).timestamp() * 1_000_000_000)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
            raise SpecError(f"{path} is not a verify_junit evidence receipt: {exc}") from exc
        found = sorted(results.glob("*.xml")) if results.is_dir() else []
        drift = f"{path.name}: the result set changed after the gate"
        if len(found) != declared:
            raise SpecError(f"{drift}: {results} holds {len(found)} XML file(s), not {declared}")
        seen = 0
        for xml in found:
            stat = xml.stat()
            if not (started < stat.st_mtime_ns <= ceiling and stat.st_ctime_ns > started):
                raise SpecError(f"{xml.name} sits outside the window {path.name} certifies: a "
                                "result from an earlier tree, or one written after the gate went "
                                "green, is not part of the verified run and proves nothing")
            try:
                root = ET.parse(xml).getroot()
            except (ET.ParseError, OSError) as exc:
                raise SpecError(f"unreadable XML result file {xml.name}: {exc}") from exc
            for case in root.iter("testcase"):
                seen += 1
                fqcn, name = (case.get("classname") or "").strip(), (case.get("name") or "").strip()
                if fqcn not in classes:
                    raise SpecError(f"{drift}: {xml.name} runs class {fqcn!r}, which it did not")
                if len(case) and any(kid.tag in ("failure", "error", "skipped") for kid in case):
                    continue     # verify_junit refuses these; a re-read one still proves nothing
                ids = cites(name)
                by_name += bool(ids)
                if not ids:
                    ids = cites(fqcn)
                    by_class += bool(ids)
                    unattributable += not ids
                for key in ids:
                    executed.setdefault(key, []).append(f"{fqcn}#{name or '(no name)'}")
        if seen != total:
            raise SpecError(f"{drift}: {seen} testcase(s) are on disk, and it certified {total}")
        files, cases = files + len(found), cases + seen
    return executed, Stats(files, cases, by_name, by_class, unattributable)

# --- T7: the id arrived, the body did not ---------------------------------------------------------
# T3 asks "did a test carrying this id run and pass". Renaming an already-green test answers it in
# full and writes no product. Measured on the four sibling repositories this methodology runs on:
# 1,073 Java test files, 5,866 `@Test` methods, and ZERO of them carrying a criterion id — so the
# migration T3 asks for IS a bulk rename, and the cheapest way to finish it is to make no other
# change at all. T7 reads the same commit range `plan_waves.py --commit` reads and asks the second
# question: did the body of that test change here?
#
# It matches a NAME against LINE NUMBERS and parses no language. The carrier is the executed test's
# own `name=` (or `classname=` when the id lives there), which is the same carrier the rest of this
# file already trusts, so nothing here has to know what a method looks like in Java, Python or
# TypeScript. The body is bounded by INDENTATION: from the line the id arrived on, forward until a
# non-blank line indented no further. Java closes on `}` at the signature's own indent and Python on
# the next `def`, and both land on the same span without either being named.
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
PARAMETERISED_RE = re.compile(r"\s*\[[^\]]*\]\s*$")     # `resends__F7_AC2[2]` -> `resends__F7_AC2`
TOKEN_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
# The empty tree. A range whose left side is a root commit has nothing to its left, and diffing
# against the WORKING TREE — which is what a bare `git diff <root>` does — would read uncommitted
# edits as if they were in the range. That is the one git default this must not inherit.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def range_ends(root: Path, rev_range: str) -> tuple[str, str, str]:
    """`(left, right, tip)` for a range spelled `A..B`, `A...B` or a single commit.

    A single commit means that commit against its parent, and a ROOT commit against the empty tree
    rather than against the working tree. Anything git cannot resolve raises: a `--commit` that
    silently degraded to "no diff" would report every claim as pre-existing and find nothing.
    """
    def commit(rev: str) -> str:
        resolved = git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if not resolved or not resolved.strip():
            raise SpecError(f"--commit {rev_range}: git cannot resolve {rev!r} in {root}")
        return resolved.strip()

    if ".." in rev_range:
        left, _, right = rev_range.partition("..")
        right = right.lstrip(".")
        if not left.strip() or not right.strip():
            raise SpecError(f"--commit {rev_range}: a range needs both ends, `A..B`")
        return commit(left), commit(right), right.strip()
    tip = commit(rev_range)
    parents = (git(root, "rev-list", "--parents", "-n", "1", tip) or "").split()
    return (parents[1] if len(parents) > 1 else EMPTY_TREE), tip, rev_range


def added_lines(root: Path, left: str, right: str) -> tuple[dict[str, dict[int, str]],
                                                              dict[str, set[int]]]:
    """Per file: post-image line number -> text for every line the range ADDS, and the post-image
    numbers a pure DELETION sits between.

    Deletions are read because the claim T7 makes is "the range never touched this body", and a
    body someone emptied was touched. Measured on a real repository, the one and only disagreement
    in 581 judgeable methods was this: a commit renamed a test AND moved eight of its assertion
    lines into a new test, so the body changed by subtraction and nothing was added to it. Ignoring
    deletions would have called that honest refactor a free coverage claim. It costs the rename
    check nothing — renaming deletes the SIGNATURE line, never a body line.

    `--unified=0` because context is not evidence of work, and `--find-renames` because a moved
    file whose contents did not change adds nothing and must keep adding nothing here.
    """
    diff = git(root, "-c", "core.quotePath=false", "diff", "--unified=0", "--find-renames",
               "--no-color", left, right)
    if diff is None:
        raise SpecError(f"`git diff {left[:12]} {right[:12]}` failed in {root}")
    added: dict[str, dict[int, str]] = {}
    removed: dict[str, set[int]] = {}
    path, number = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else target[2:] if target[1:2] == "/" else target
        elif line.startswith("--- ") or line.startswith("diff --git "):
            continue
        elif line.startswith("@@"):
            match = HUNK_RE.match(line)
            number = int(match.group(1)) if match else 0
            # `@@ -139,8 +138,0 @@` deletes with nothing to put in its place, so it owns no line of
            # the post image and sits in the seam between 138 and 139. Both are marked touched.
            if path and match and match.group(2) == "0":
                removed.setdefault(path, set()).update((number, number + 1))
        elif path and number and line.startswith("+"):
            added.setdefault(path, {})[number] = line[1:]
            number += 1
        elif path and number and line.startswith(" "):
            number += 1
    return added, removed


def owns(path: str, fqcn: str) -> bool:
    """Whether this file is where the executed test's class lives, by NAME rather than by parsing.

    A method name is not unique across a repository — `classRegistryIsComplete` exists in several
    suites in one real project — and a global token search let an unrelated file's added body
    answer for this one. Comparing the file's stem to the last two segments of `classname` is the
    weakest rule that stops it and stays language-agnostic: `com.x.FooIT` lives in `FooIT.*` and
    `tests.test_gate.Cases` lives in `test_gate.*`. When no file matches, T7 declines and counts
    itself as declining rather than passing on a name collision.
    """
    return Path(path).stem in [part for part in re.split(r"[.$]", fqcn) if part][-2:]


def carrier(key: Key, executed_test: str) -> str | None:
    """The identifier in the source that carries `key` for one `classname#name` entry.

    The method name first, its class second — the same order `read_evidence` attributed them in. A
    parameterised case renders `name="[2] 2026-12-31"` and holds no identifier at all, so it falls
    to the class, and a name that is not a bare identifier is refused rather than searched for as a
    substring: `AC-2 rejects a blank` is a real JUnit display name and matches nothing in a diff.
    """
    fqcn, _, name = executed_test.partition("#")
    for token in (PARAMETERISED_RE.sub("", name).strip(), fqcn.rsplit(".", 1)[-1].strip()):
        if TOKEN_RE.match(token or "") and any(
                found.number == key.number and found.feature in ("", key.feature)
                for found in cites(token)):
            return token
    return None


def body_span(lines: list[str], index: int) -> range:
    """Post-image line numbers of the body opened on `lines[index]`, by indentation alone."""
    depth = len(lines[index]) - len(lines[index].lstrip())
    end = index + 1
    while end < len(lines) and (not lines[end].strip()
                                or len(lines[end]) - len(lines[end].lstrip()) > depth):
        end += 1
    return range(index + 2, end + 1)


def body_worked(root: Path, left: str, right: str, added: dict[str, dict[int, str]],
                removed: dict[str, set[int]], token: str, fqcn: str) -> bool | None:
    """True when the range touched the body under `token`, False when only its own line moved, and
    None when the id did not ARRIVE in this range at all — that last case is counted and printed,
    never passed.

    "Arrived" is decided against the LEFT side of the range, not against the added lines: a token
    is new here only when the file it lands in did not already contain it. Deciding it on "the name
    appears on an added line" was wrong against the real corpus and wrong in a specific, repeatable
    way — one project keeps a pinned-defect registry that names its own test methods in string
    literals, so editing the registry made every long-standing test look newly named, and 18 of 494
    judgeable methods (3.6%) fired for a rename that never happened. Reading the left side takes
    the same class of accident out of the rule instead of tuning a threshold until it hides.

    A line that merely CALLS the test is not a declaration, and it does not have to be told apart
    from one: a call sits alone at its own indent, so the span below it is empty and it can never
    satisfy the check by itself. Only files the token appears in are read back, which is why this
    costs two `git show` calls per hit file and not a pass over the tree.
    """
    word = re.compile(rf"(?<![A-Za-z0-9_$]){re.escape(token)}(?![A-Za-z0-9_$])")
    hits: list[tuple[str, int]] = []
    for path, lines in sorted(added.items()):
        if not owns(path, fqcn) or not any(word.search(text) for text in lines.values()):
            continue
        before = git(root, "show", f"{left}:{path}")
        if before is not None and word.search(before):
            continue     # the id was already here before the range: nothing arrived, so no opinion
        hits += [(path, number) for number, text in sorted(lines.items()) if word.search(text)]
    if not hits:
        return None
    for path, number in hits:
        content = git(root, "show", f"{right}:{path}")
        if content is None:
            continue     # deleted by the tip, or unreadable: it proves nothing either way
        lines = content.splitlines()
        if not 0 < number <= len(lines):
            continue
        touched = set(added.get(path, {})) | removed.get(path, set())
        if touched.intersection(body_span(lines, number - 1)):
            return True
    return False


def check_bodies(root: Path, rev_range: str, specs: dict[str, Spec], plans: list[Plan],
                 executed: dict[Key, list[str]], f: Findings) -> Bodies:
    """T7 over every criterion T3 reports green. Returns the denominator, which main() prints."""
    left, right, _ = range_ends(root, rev_range)
    added, removed = added_lines(root, left, right)
    green, arrived, worked, stale = 0, 0, 0, 0
    for plan in plans:
        numbers = specs[plan.feature].numbers if plan.feature in specs else {}
        for number, (level, line) in sorted(plan.rows.items()):
            key = Key(plan.feature, number)
            if level == "none" or number not in numbers or key not in executed:
                continue     # T1, T2 and T3 own those; a second finding here would print twice
            green += 1
            verdicts = {}
            for test in executed[key]:
                token = carrier(key, test)
                if token is not None:
                    verdicts[test] = body_worked(root, left, right, added, removed, token,
                                                 test.partition("#")[0])
            if all(verdict is None for verdict in verdicts.values()):
                stale += 1
                continue     # the id predates the range: T7 has no opinion and says so in the count
            arrived += 1
            if any(verdict for verdict in verdicts.values()):
                worked += 1
                continue
            renamed = sorted(test for test, verdict in verdicts.items() if verdict is False)
            f.add(plan.doc, line, "T7", f"F-{plan.feature}/AC-{number} is newly carried by "
                  f"{renamed[0]}{f' and {len(renamed) - 1} more' if len(renamed) > 1 else ''}, and "
                  f"{rev_range} changed no line of that test's body — the id arrived without the "
                  "work, which is what renaming an already-green test looks like")
    return Bodies(green, arrived, worked, stale)


def check(specs: dict[str, Spec], plans: list[Plan], executed: dict[Key, list[str]],
          f: Findings) -> None:
    for plan in plans:
        spec = specs.get(plan.feature)
        numbers, retired = (spec.numbers, spec.withdrawn) if spec else ({}, {})
        for number, line in sorted(numbers.items()):
            if spec.live and number not in plan.rows:
                f.append(Finding(spec.doc.rel, line, "T1", f"AC-{number} has no row in the "
                                 f"coverage map of {plan.doc.rel}; a criterion nobody planned to "
                                 "test is read by everyone downstream as covered"))
        for key, line in ([(Key(plan.feature, number), line)
                           for number, (_, line) in sorted(plan.rows.items())] + plan.covers):
            if key.number not in numbers and key.feature == plan.feature:
                f.add(plan.doc, line, "T2", f"the plan declares F-{key.feature}/AC-{key.number}, "
                      + ("retired in the spec's `withdrawn:`" if key.number in retired else
                         "which its spec does not declare") + "; plan and spec disagree about what "
                      "this feature promises")
        for number, (level, line) in sorted(plan.rows.items()):
            if number in plan.absent and level != "none":
                f.add(plan.doc, line, "T5", f"AC-{number} is covered at level `{level}` here and "
                      f"claimed untested on line {plan.absent[number]}: two answers, one criterion")
            if level != "none" and number in numbers and Key(plan.feature, number) not in executed:
                f.add(plan.doc, line, "T3", f"no executed test carries F-{plan.feature}/AC-"
                      f"{number}; the plan declares a `{level}` test and the verified run has none")
    for key, tests in sorted(executed.items()):
        spec = specs.get(key.feature)
        where = f"{tests[0]}{f' and {len(tests) - 1} more' if len(tests) > 1 else ''}"
        if spec and key.number in spec.withdrawn:
            f.append(Finding(spec.doc.rel, spec.withdrawn[key.number], "T6",
                             f"{where} cites retired AC-{key.number}: the test may still be right "
                             "and the id is not, so cite the criterion that replaced it — deleting "
                             "a passing test is not the cheapest green here"))
        elif not key.feature:
            f.append(Finding(XML_SOURCE, NO_LINE, "T4", f"{where} cites AC-{key.number} with no "
                             "feature; most specs have an AC-4, so it names no criterion"))
        elif not spec or key.number not in spec.numbers:
            f.append(Finding(XML_SOURCE, NO_LINE, "T4", f"{where} cites F-{key.feature}/"
                             f"AC-{key.number}, which no feature spec declares"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--evidence", action="append", default=[], metavar="FILE",
                        help="a verify_junit.py evidence receipt; repeat for more than one run")
    parser.add_argument("--commit", metavar="RANGE",
                        help="also check that the body of each newly-carried test changed in this "
                             "commit or `A..B` range; without it T7 does not run and says so")
    parser.add_argument("--json", action="store_true", help="machine-readable findings on stdout")
    args = parser.parse_args()
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2
    root, findings, missing, stats = root.resolve(), Findings(), "", Stats(0, 0, 0, 0, 0)
    specs, plans, bodies = {}, [], None
    try:
        specs, plans = read_specs(root, findings), read_plans(root, findings)
        if not plans:
            missing = ("no feature plan under docs/product/plans/: nothing in this repository "
                       "declares which test proves which criterion, so nothing was traced")
        elif not args.evidence:
            missing = ("no --evidence given: this run read no verified JUnit result, so no test "
                       "was proven to have run and nothing was traced")
        else:
            executed, stats = read_evidence([Path(item).expanduser() for item in args.evidence])
            check(specs, plans, executed, findings)
            # Called on the ONE path that can call it, and printed either way. A flag accepted and
            # never acted on is how the last check in this toolchain came to be inert.
            if args.commit:
                bodies = check_bodies(root, args.commit, specs, plans, executed, findings)
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = sorted(findings)
    code = 1 if findings and not missing else 0
    approved = [spec for spec in specs.values() if spec.live]
    report = (f"{sum(len(spec.numbers) for spec in approved)} criterion/criteria required by "
              f"{len(approved)} approved spec(s), {sum(len(plan.rows) for plan in plans)} declared "
              f"by {len(plans)} plan(s), {stats.cases} testcase(s) read from {stats.files} XML "
              f"file(s): {stats.by_name} carried an id in the test name, {stats.by_class} in the "
              f"class name, {stats.unattributable} in neither. An executed id proves a test with "
              "that id ran and passed, not that it asserts anything.")
    if bodies is not None:
        report += (f" Of {bodies.green} criterion/criteria a test carries, {bodies.arrived} had "
                   f"that id ARRIVE inside {args.commit} and {bodies.worked} of those also had "
                   f"body lines change there; {bodies.stale} carried the id before the range, so "
                   "T7 judged none of them. A changed body is work, not an assertion.")
    elif args.commit:
        note = (f" T7 did not run: --commit {args.commit} judges tests a verified run executed, "
                "and this run named none.")
        report, missing = report + note, (missing + note if missing else missing)
    if args.json:
        json.dump({"root": str(root), "count": len(findings), "exit": code, "missing": missing,
                   "testcases": stats.cases, "unattributable": stats.unattributable,
                   "commit": args.commit, "t7": bodies._asdict() if bodies else None,
                   "summary": report,
                   "findings": [item._asdict() for item in findings]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif missing:
        print(missing)
    else:
        width = max([len(f"{item.path}:{item.line}") for item in findings[:PRINT_CAP]] or [0])
        for item in findings[:PRINT_CAP]:
            print(f"{item.path}:{item.line}".ljust(width) + f"  {item.rule}  {item.message}")
        if len(findings) > PRINT_CAP:
            print(f"... and {len(findings) - PRINT_CAP} more finding(s); fix these and run again")
        print(report)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
