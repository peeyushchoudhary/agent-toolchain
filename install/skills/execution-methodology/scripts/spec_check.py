#!/usr/bin/env python3
"""Lint product-definition documents for CURRENT STATE. This script writes nothing, ever.

A specification says what is TRUE NOW. It never says what it used to say. History lives in git,
the reason for a decision lives in a decision record, and the one genuinely append-only part — the
numbers of retired acceptance criteria — lives in structured front matter where a machine reads it,
never in prose a reader has to interpret at runtime.

That rule answers a measured failure, not a preference: documents appended to rather than updated
accumulate conflicting decisions, and each reader then works out which of four statements is
current from memory, differently. The checks are structural — they cannot tell a good requirement
from a bad one, only a document that describes its own past from one that does not.

WHAT THIS DELIBERATELY IS NOT: a gate that produces artifacts. Every file a process spawns is a
cost paid forever, so this one reads, prints and exits — no receipt, no index, no cache, ever.

Discovery is `docs/product/**/*.md`, the PRD at `docs/product/prd.md`, feature specs at
`docs/product/specs/F-*.md`. A repository with none of those exits 0 in silence — a linter that
shouts at every repository it does not apply to gets deleted.

  A  no dated heading, no changelog section, no self-referential prose, `updated:` = commit date
  B  front matter parses, keys, id matches the filename and is unique, status enum, and a
     withdrawn criterion number that is never live in the body
  C  criterion shape, no two live criteria over one situation, unique positive numbers, and a
     result that some input can make false
  D  PRD front matter, one feature-index marker at most, references that resolve both ways, and
     no open-question marker once approved
  E  milestone `## Deferred` register: entries parse, `found_by` names a feature in this milestone,
     `threatens` names a live criterion, an unowned or already-shipped-owner entry fails at seal
  F  persona binding: this repo's `docs/agents/personas/*.md` pool reads, `reviewed_by:` is shaped,
     a validator owning a horizontal concern the document says it MOVES is named in `reviewed_by:`,
     and a `covers:` that matches no concern in the corpus is a finding rather than a silence
  S  --surfaces only: a route added in a git range that no approved spec names under `## Surface`

Usage:  spec_check.py [--root DIR] [--json] [--warn-only] [--deferred] [--personas]
                      [--questions] [--surfaces (--range R | --since D)]
Exit codes: 0 clean, 1 findings, 2 the arguments or the tree could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from ratio_meter import CODE_SUFFIXES, is_excluded  # one shared list, never a second copy of it

PRINT_CAP = 40   # Findings printed before the rest are only counted; forty is about a screen.

DATED_HEADING_RE = re.compile(r"^#{2,3} .*\d{4}-\d{2}-\d{2}")
# The heading must BE a history section, not merely mention one. `# Run history` is a real screen
# in a real product — an audit log the user reads — and the previous pattern matched anywhere in the
# line, so a feature about history was told to stop being a changelog. Third instance of the same
# collision after `receipt`/`cards` in the classifier and `superseded` in the prose rule: process
# vocabulary is product vocabulary too, and a rule that matches a word rather than a structure will
# keep finding the product.
HISTORY_HEADING_RE = re.compile(
    r"^#{1,6}\s+(?:the\s+)?(changelog|change log|change history|revision log|revision history|"
    r"version history|history of changes|history|revisions?|what changed[\w\s]*)\s*:?\s*$",
    re.IGNORECASE)

# NARROW ON PURPOSE, AND THE NARROWNESS IS A MEASUREMENT RATHER THAN A PREFERENCE. A broad
# history-vocabulary pattern (superseded|deprecated|formerly|no longer|replaced|revised|…) was run
# over a real corpus: 1057 hits across 164 files, and almost every one was domain vocabulary rather
# than a document discussing itself — "superseded campaign" and "corrected snapshot" are things a
# product does, not things a spec used to say. The pattern below hit 9 lines in 4 files on the same
# corpus and every hit was genuinely self-referential. A lint that fires a thousand times is
# switched off, and a switched-off lint checks nothing, so this one fires only when a sentence
# names THIS document or an earlier version of it. Widening it is a decision to be made against a
# re-measured false-positive count, never on the argument that a word sounds historical.
SELF_REFERENTIAL_RE = re.compile(
    r"an earlier version of (this|the)"
    r"|this (document|spec|section|line|file) (previously|used to|once)"
    r"|previously (said|stated|read)"
    r"|earlier drafts?"
    r"|was (previously )?(wrong|backwards)",
    re.IGNORECASE)

# A result built out of these cannot fail, so it cannot be tested, so it gets implemented as
# whatever the implementer happened to think — a decision delegated downstream by nobody.
VAGUE_WORDS = ("gracefully", "appropriately", "correctly", "properly", "as needed",
               "if necessary", "reasonable", "reasonably")
VAGUE_RE = re.compile(r"\b(" + "|".join(VAGUE_WORDS) + r")\b", re.IGNORECASE)

STATUSES = ("draft", "approved", "building", "shipped", "dropped")
SPEC_KEYS = (("id", "title", "prd", "status", "updated"),
             ("depends", "withdrawn", "decisions", "edge_cases", "milestone", "reviewed_by"))
# `reviewed_by:` is OPTIONAL on both, and the optionality is the design. Required, it would produce
# a finding on all 89 real specs on the day it shipped, and a checker that opens with ninety
# findings is switched off before it reports a true one. It is demanded a name at a time, by rule
# F3, and only where the document's OWN horizontals say the concern moves.
PRD_KEYS = (("title", "status", "updated"), ("reach", "reviewed_by"))
# Both authored forms, because the real corpus uses both: 221 criteria write `**AC-1** When ...`
# and 195 write `**AC-1 — a short title:** When ...`. The stricter pattern shipped first and matched
# 0 of 416 real criteria, so every criterion check was silently inert on every existing spec — a
# checker that passes because it recognises nothing is worse than no checker, since it reports green.
# The suffix letter is real too: AC-8A/8B/8C split one criterion into variants after the fact, which
# is how a spec grows a case without renumbering the ones a test already cites.
AC_RE = re.compile(r"^\s*[-*]?\s*\*\*AC-(-?\d+[A-Z]?)\s*(?:[—–-][^*]*?)?\*\*:?\s*(.*)$")
# The precondition is OPTIONAL, deliberately. EARS itself has five patterns and only some carry a
# state clause, and a mandatory slot manufactures filler to fill it: the first spec written against
# a required `given` produced "given any outcome", which constrains nothing and trains the reader to
# skip the clause on every criterion after it. A criterion with no meaningful precondition should
# say so by omission.
EARS_RE = re.compile(
    r"^when\s+(?P<trigger>.+?)\s*,\s*(?:given\s+(?P<pre>.+?)\s*,\s*)?(?P<result>\S.*)$",
    re.IGNORECASE)
FEATURE_MARKER = "<!-- features: docs/product/specs/F-*.md -->"
FEATURE_REF_RE = re.compile(r"\bF-\d+\b")
# A suffix letter is a real feature id, not a typo. When a feature turns out to be several — the
# recorded case split one into ten — renumbering the survivors would repoint every test that already
# cites them, so the split takes letters and the original number is spent. Same rule the criteria
# already follow with AC-8A.
ID_RE = re.compile(r"^F-\d+[A-Z]?$")
# `milestone:` is OPTIONAL, and its absence carries meaning: the feature is specified and waiting.
# Most of a healthy backlog is in that state, so requiring the key would turn the backlog into
# findings and teach the reader to fill it in with whatever milestone is nearest.
MILESTONE_RE = re.compile(r"^M\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
QUOTED_RE = re.compile(r"^(['\"])(.*)\1$")


class SpecError(Exception):
    """Something could not be READ. Not a finding: it ends the run with exit 2."""


# Field order IS report order: sorting these sorts by path, then line, then rule.
Finding = NamedTuple("Finding", [("path", str), ("line", int), ("rule", str), ("message", str)])


def parse_front_matter(lines: list[str]) -> tuple[dict[str, object], dict[str, int], int]:
    """Parse the leading `---` block: a YAML SUBSET, deliberately, not YAML.

    Handled: `key: value` scalars, optionally quoted; `key: [a, b]` flow lists; `#` comments; blank
    lines. Anything else — nested mappings, block lists, anchors, block scalars, multi-document
    files — raises, because a parser that silently drops a field it could not read is how a checker
    starts lying. Returns the mapping, each key's 1-based line, and the closing `---` index.
    """
    def unquote(raw: str) -> str:
        match = QUOTED_RE.match(raw.strip())
        return match.group(2) if match else raw.strip()

    def strip_comment(raw: str) -> str:
        """Drop a trailing `# ...` from an UNQUOTED value, the way YAML does.

        The docstring above always claimed comments were handled; only whole-line comments were.
        A trailing one survived into the value, so the shipped templates — which annotate optional
        keys inline — produced spurious findings when copied verbatim: `withdrawn: [3, 9] # optional`
        parsed the comment as part of the list. The rule is YAML's: whitespace followed by `#`
        starts a comment, so `title: fix the #3 bug` truncates to `fix the` exactly as it would in
        YAML — quote the value to keep it. A `#` with no space before it, as in `id: F-12#a`, is
        part of the value.
        """
        return re.split(r"\s#", raw, maxsplit=1)[0] if re.search(r"\s#", raw) else raw

    if not lines or lines[0].strip() != "---":
        raise SpecError("no `---` front matter block at the top of the file")
    data: dict[str, object] = {}
    where: dict[str, int] = {}
    for index in range(1, len(lines)):
        raw, stripped = lines[index], lines[index].strip()
        if stripped == "---":
            return data, where, index
        if not stripped or stripped.startswith("#"):
            continue
        # The key is matched UNSTRIPPED, so an indented line — a nested mapping or a block list —
        # fails the shape test and raises rather than being silently flattened into a flat key.
        key, separator, value = raw.partition(":")
        # The comment goes before anything looks at the value's shape. Stripping it inside unquote
        # was too late: `withdrawn: [3, 9]  # optional` no longer ended in `]`, so it never reached
        # the flow-list branch and arrived as a string that every list check then mis-read.
        value = strip_comment(value).strip() if not QUOTED_RE.match(value.strip()) else value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise SpecError(f"line {index + 1}: not a `key: value` line -> {stripped!r}")
        if key in data:
            raise SpecError(f"line {index + 1}: duplicate front-matter key {key!r}")
        if value.startswith("[") and value.endswith("]"):
            data[key] = [unquote(part) for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = unquote(value)
        where[key] = index + 1
    raise SpecError("front matter block is never closed by a second `---`")


class Doc:
    """One product document: its lines, its front matter, and where each of those begins."""

    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.rel = path.relative_to(root).as_posix()
        try:
            self.lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise SpecError(f"cannot read {path}: {exc}") from exc
        self.front, self.where, self.body_start, self.front_error = {}, {}, 0, None
        try:
            self.front, self.where, end = parse_front_matter(self.lines)
            self.body_start = end + 1
        except SpecError as exc:
            self.front_error = str(exc)

    @property
    def is_spec(self) -> bool:
        """A feature spec, by path. Schema rules bind only here and on the PRD."""
        return self.path.match("docs/product/specs/F-*.md")

    @property
    def looks_like_a_spec(self) -> bool:
        """A document that sits where specs sit but does not match the bound name.

        NOT a rule and never a finding: a repository may legitimately name its specs another way,
        and this checker has no standing to demand `F-<n>-<slug>.md`. It exists so the SILENCE is
        visible. One real repository writes every spec as `specs/<slug>/spec.md`, which meant 274
        documents — 130 of them carrying the `## Horizontals` section rule F reads — were scanned,
        bound by nothing, and reported as a clean exit 0. A checker that inspects none of a
        repository's specs and prints no findings is indistinguishable from one that inspected
        them all and approved.
        """
        if self.is_spec or self.is_prd or self.is_milestone:
            return False
        return "docs/product/specs/" in self.rel

    @property
    def is_prd(self) -> bool:
        return self.rel == "docs/product/prd.md"

    @property
    def is_milestone(self) -> bool:
        """A milestone document, by path — the same `docs/product/milestones/M<n>-<slug>.md` rule
        `plan_waves.py` and the push guard already resolve milestones by."""
        return self.path.match("docs/product/milestones/M*.md")

    def at(self, key: str) -> int:
        return self.where.get(key, 1)

    def scalar(self, key: str) -> str:
        value = self.front.get(key)
        return value if isinstance(value, str) else ""

    def body(self) -> list[tuple[int, str]]:
        """Body lines as (1-based number, text), fenced blocks removed: a template inside a fence
        legitimately holds a dated heading, and flagging it would make every document that shows
        its own shape unlintable."""
        out: list[tuple[int, str]] = []
        fenced = False
        for index in range(self.body_start, len(self.lines)):
            if FENCE_RE.match(self.lines[index]):
                fenced = not fenced
            elif not fenced:
                out.append((index + 1, self.lines[index]))
        return out


Criterion = NamedTuple("Criterion", [("number", str), ("line", int), ("trigger", str),
                                     ("precondition", str), ("result", str), ("shaped", bool)])


class Findings(list):
    """A list of Finding whose only added behaviour is folding a message onto one line."""
    def add(self, doc: Doc, line: int, rule: str, message: str) -> None:
        self.append(Finding(doc.rel, line, rule, " ".join(message.split())))


def criteria(doc: Doc) -> list[Criterion]:
    """Every `**AC-<n>** …` line, with its wrapped continuation lines folded back onto it: specs
    are written to a column width, and a parser reading only the first line would call half a real
    corpus shapeless. A blank line, a heading, a bullet and a table row all close the fold."""
    found: list[Criterion] = []
    parts: list[str] = []
    identifier, at = "", 0
    for number, text in doc.body() + [(0, "")]:
        match = AC_RE.match(text)
        if parts and (match or not text.strip() or text.lstrip()[:1] in "#-*|>"):
            shape = EARS_RE.match(" ".join(parts))
            # `pre` is None when the criterion carries no precondition, which is allowed. It
            # normalises to "" so the duplicate-pair check below compares like with like: two
            # criteria that share a trigger and BOTH omit the precondition are still a collision.
            groups = ((shape.group("trigger"), shape.group("pre") or "", shape.group("result"))
                      if shape else ("", "", " ".join(parts)))
            found.append(Criterion(identifier, at, *groups, shape is not None))
            parts = []
        if match:
            # The id is a STRING, not an int: `AC-8A` is a real form in the corpus, and int()
            # raised on it. Numeric ordering is not needed anywhere — uniqueness and citation are.
            identifier, at, parts = match.group(1), number, [match.group(2).strip()]
        elif parts and text.strip():
            parts.append(text.strip())
    return found


def git(root: Path, *args: str) -> str | None:
    """git stdout, or None when git is unusable. Never fatal: no git, a fresh clone and a shallow
    CI checkout must all produce silence rather than noise."""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


# Documents whose PURPOSE is to record a change, and which are therefore append-only by design.
# The current-state rule does not reach them: a change request exists to say "this was X, make it
# Y", and a ruling inside one is dated because the date is the point. Measured on a real
# repository, 9 of 12 findings were this category error — the same shape as demanding front matter
# from every README, and the same remedy: a rule binds the documents it was written for.
# A screen specification with a changelog section is NOT exempt. It states current behaviour, and
# the section is exactly the drift this rule exists to stop.
RECORD_SEQUENCES = ("/change-requests/", "/decisions/", "/adr/", "/rulings/")
RECORD_NAMES = ("changelog.md", "history.md")


def is_record(doc: Doc) -> bool:
    """A document that records a change rather than stating current state."""
    lowered = "/" + doc.rel.lower()
    return (any(part in lowered for part in RECORD_SEQUENCES)
            or lowered.rsplit("/", 1)[-1] in RECORD_NAMES)


def check_current_state(doc: Doc, f: Findings) -> None:
    if is_record(doc):
        return
    register = deferred_lines(doc) if doc.is_milestone else set()
    for number, text in doc.body():
        if DATED_HEADING_RE.match(text):
            f.add(doc, number, "A1", "dated heading: the document is being appended to rather "
                                     "than brought up to date")
        if HISTORY_HEADING_RE.match(text):
            f.add(doc, number, "A2", "changelog section: what changed is in git log, and why it "
                                     "changed belongs in a decision record")
        match = None if number in register else SELF_REFERENTIAL_RE.search(text)
        if match:
            f.add(doc, number, "A3", f"self-referential history prose ({match.group(0)!r}): state "
                                     "the current requirement, not the document's past")


def check_updated(doc: Doc, root: Path, dirty: set[str], f: Findings) -> None:
    updated = doc.scalar("updated")
    if not updated:
        return
    if not DATE_RE.match(updated):
        f.add(doc, doc.at("updated"), "A4", f"`updated: {updated}` is not a YYYY-MM-DD date")
        return
    if doc.rel in dirty:
        return  # An uncommitted edit has no commit date yet; comparing would fail every author.
    log = git(root, "log", "-1", "--format=%ad", "--date=short", "--", doc.rel)
    committed = (log or "").strip()
    if committed and committed != updated:
        f.add(doc, doc.at("updated"), "A4",
              f"`updated: {updated}` disagrees with the last commit touching this file "
              f"({committed}); a stale date makes a current document look older than it is")


def check_keys(doc: Doc, keys: tuple[tuple[str, ...], ...], rule: str, enum_rule: str,
               f: Findings) -> None:
    required, optional = keys
    for key in required:
        if key not in doc.front:
            f.add(doc, 1, rule, f"front matter is missing the required key `{key}`")
    for key in doc.front:
        if key not in required and key not in optional:
            f.add(doc, doc.at(key), rule, f"unknown front-matter key `{key}`; this document "
                                          f"takes {', '.join(required + optional)}")
    status = doc.scalar("status")
    if status and status not in STATUSES:
        f.add(doc, doc.at("status"), enum_rule, f"status `{status}` is not one of "
                                                f"{' | '.join(STATUSES)}")


def check_spec(doc: Doc, root: Path, seen: dict[str, str], f: Findings) -> None:
    check_keys(doc, SPEC_KEYS, "B2", "B4", f)
    identifier = doc.scalar("id")
    if identifier and not ID_RE.match(identifier):
        f.add(doc, doc.at("id"), "B3", f"id `{identifier}` is not of the form F-<number>")
    elif identifier and not (doc.path.name.startswith(identifier + "-")
                             or doc.path.stem == identifier):
        f.add(doc, doc.at("id"), "B3",
              f"id `{identifier}` does not match the filename `{doc.path.name}`")
    if identifier in seen:
        f.add(doc, doc.at("id"), "B3", f"id `{identifier}` is already used by {seen[identifier]}; "
                                       "ids are unique across the corpus and are never reused")
    elif identifier:
        seen[identifier] = doc.rel
    milestone = doc.scalar("milestone")
    if milestone and not MILESTONE_RE.match(milestone):
        f.add(doc, doc.at("milestone"), "B3",
              f"milestone `{milestone}` is not of the form M<number>; the schedule collects "
              "features by an exact match on this value, so a near miss is silently unscheduled")
    target = doc.scalar("prd")
    if target and not any(p.is_file() for p in (root / target, doc.path.parent / target)):
        f.add(doc, doc.at("prd"), "D3",
              f"`prd: {target}` does not resolve to a file, so this spec has no parent")
    # Criterion ids are STRINGS throughout: `AC-8A` is a real form and int() raised on it. The
    # withdrawn ledger holds the same string form so the two sets compare directly.
    withdrawn: set[str] = set()
    raw = doc.front.get("withdrawn") or []
    # `3` retires a number outright. `3>11` retires it INTO a successor, which is the difference
    # between "this requirement is gone" and "this requirement moved". A test still citing a plain
    # retirement is a test of something nobody wants; a test citing a superseded one needs
    # repointing, and only the spec knows where to. Without the notation both looked identical and
    # a tracer could only say the id was dead.
    successors: dict[str, str] = {}
    for item in ([raw] if isinstance(raw, str) else raw):
        head, arrow, tail = item.partition(">")
        head, tail = head.strip(), tail.strip()
        if not (re.fullmatch(r"\d+[A-Z]?", head) and head.lstrip("0")[:1] not in ("", "0")):
            f.add(doc, doc.at("withdrawn"), "B5",
                  f"withdrawn entry {item!r} is not a positive criterion number")
            continue
        if arrow and not re.fullmatch(r"\d+[A-Z]?", tail):
            f.add(doc, doc.at("withdrawn"), "B5",
                  f"withdrawn entry {item!r} names no successor after `>`; write `3>11`, or `3` "
                  "alone if the requirement is gone rather than moved")
            continue
        withdrawn.add(head)
        if arrow:
            successors[head] = tail
    for retired, successor in successors.items():
        if successor in withdrawn:
            f.add(doc, doc.at("withdrawn"), "B5",
                  f"AC-{retired} is superseded by AC-{successor}, which is itself withdrawn; the "
                  "chain has to end at a criterion that exists")
    check_criteria(doc, withdrawn, f)


def check_criteria(doc: Doc, withdrawn: set[str], f: Findings) -> None:
    numbers: dict[str, int] = {}
    pairs: dict[tuple[str, str], int] = {}
    for item in criteria(doc):
        if not item.shaped:
            f.add(doc, item.line, "C1", "criterion is not of the form `**AC-<n>** When <trigger>, "
                                        "given <precondition>, <observable result>`")
        if not re.fullmatch(r"[1-9]\d*[A-Z]?", item.number):
            f.add(doc, item.line, "C3", f"criterion number {item.number} must be a positive number, "
                                        f"optionally with a single suffix letter")
        elif item.number in numbers:
            f.add(doc, item.line, "C3", f"criterion number {item.number} is already used on line "
                                        f"{numbers[item.number]}")
        else:
            numbers[item.number] = item.line
        if item.number in withdrawn:
            f.add(doc, item.line, "B5", f"AC-{item.number} is in `withdrawn:` but live in the "
                                        "body; a retired number is never reused")
        if not item.shaped:
            continue
        pair = tuple(" ".join(part.lower().split()).rstrip(".")
                     for part in (item.trigger, item.precondition))
        if pair in pairs:
            f.add(doc, item.line, "C2", f"this trigger and precondition already appear on line "
                                        f"{pairs[pair]}; one situation, two answers")
        else:
            pairs[pair] = item.line
        vague = VAGUE_RE.search(item.result)
        if vague:
            f.add(doc, item.line, "C4", f"the result rests on {vague.group(0)!r}, which no input "
                                        "can make false, so the criterion cannot fail a test")


def check_prd(doc: Doc, spec_ids: dict[str, str], f: Findings) -> None:
    check_keys(doc, PRD_KEYS, "D1", "D1", f)
    markers = 0
    for number, text in doc.body():
        markers += FEATURE_MARKER in text
        if markers > 1 and FEATURE_MARKER in text:
            f.add(doc, number, "D2", "the feature-index marker appears more than once; two "
                                     "indexes in one document are two answers to one question")
        for reference in FEATURE_REF_RE.findall(text):
            if reference not in spec_ids:
                f.add(doc, number, "D3", f"{reference} is referenced here but no "
                                         f"docs/product/specs/{reference}-*.md declares that id")


# --- E: the deferral register ---------------------------------------------------------------------

# Principle 6 says "deferrals live in a register that a milestone can fail against". Until now
# `defer` appeared in exactly two scripts in this toolchain and neither of them was a gate, so no
# milestone could fail against anything and the promise was prose.
#
# MEASURED, on a real project that built its own register rather than waiting for one:
# 205 rows, 178 open, 27 closed, 17 with no owner, and 423 KB of file — an average of 2,046
# characters PER ROW. That register works (its gate catches an open row owned by a milestone whose
# tag already exists) and it costs about ten times what it needs to, because a row is free-form
# prose with no shape a reader can skim. The six keys below are the same information at about
# seven short lines.
#
# THE REGISTER HOLDS OPEN ITEMS ONLY. The real one keeps its 27 closed rows and they are 13% of its
# weight; a closed deferral is history, history lives in git, and a product document that describes
# its own past is exactly what rule A forbids. Closing an entry deletes it.
#
# NO NUMERIC CAP, and this was considered rather than skipped. A ceiling the seal refuses to grow
# past would have bound that real register at around row 40 of 205, and the pressure would land on
# RECORDING the finding rather than on fixing it — the register would go quiet while the findings
# went on happening, which is the state that existed before the register. What a cap is FOR is a
# number somebody looks at, so the number is printed instead: `--deferred` lists the register with
# its counts, and E5 fails a milestone that ships while an entry it owns has no owner.
DEFERRED_HEADING_RE = re.compile(r"^#{2,3}\s+Deferred\s*$", re.IGNORECASE)
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+")
DEFERRED_ITEM_RE = re.compile(r"^\s*[-*]\s*\*\*(?P<id>D-\d+)\*\*\s*(?P<what>.*)$")
# INDENT SEPARATES A KEY FROM A CONTINUATION, and the depth is not a style preference. Read as
# "any indent, then `word:`", this parser was run over 178 rows of a REAL deferral register and
# called 22 of them malformed — 12% — because a wrapped line of ordinary prose began `known:`,
# `design:`, `confirmed:`, `verbatim:`. A key sits at 1-3 spaces; anything at 4 or more is
# continuation text and is never read as a key, whatever it starts with. Same failure as matching a
# WORD rather than a STRUCTURE, caught this time by running it against a real corpus first.
DEFERRED_KEY_RE = re.compile(r"^ {1,3}(?P<key>[a-z_]+):\s*(?P<value>.*)$")
DEFERRED_KEYS = ("found_by", "site", "threatens", "trigger", "owner", "raised")
# `F-11/T3` and a bare `T3`, the two spellings `plan_waves.py` already resolves. Nothing else: an
# entry whose finder cannot be named is an entry nobody can ask about.
FOUND_BY_RE = re.compile(r"^(?:(?P<feature>F-\d+[A-Z]?)/)?T[A-Za-z0-9._-]+$")
CRITERION_REF_RE = re.compile(r"^AC-(?P<number>\d+[A-Z]?)$")


DeferredItem = NamedTuple("DeferredItem", [("ident", str), ("line", int), ("what", str),
                                           ("keys", dict), ("at", dict)])


def deferred_items(doc: Doc, f: Findings) -> list[DeferredItem]:
    """Parse `## Deferred`. Shape findings are E1; everything cross-referential is E2 upward.

    A continuation line folds onto the key above it, the same way `criteria()` folds a wrapped
    criterion: a `trigger` holding a command and its output does not fit in 100 columns, and a
    parser that made the author choose between a legible file and a parseable one would get the
    illegible file.
    """
    lines = doc.body()
    start = next((index for index, (_, text) in enumerate(lines)
                  if DEFERRED_HEADING_RE.match(text)), None)
    if start is None:
        return []
    items: list[DeferredItem] = []
    current: DeferredItem | None = None
    last_key = ""
    for number, text in lines[start + 1:]:
        if ANY_HEADING_RE.match(text):
            break
        item = DEFERRED_ITEM_RE.match(text)
        if item:
            current = DeferredItem(item.group("id"), number, item.group("what").strip(), {}, {})
            items.append(current)
            last_key = ""
            continue
        if current is None:
            continue                      # A lead paragraph under the heading is not an entry.
        key = DEFERRED_KEY_RE.match(text)
        if key:
            name, value = key.group("key"), key.group("value").strip()
            if name in current.keys:
                f.add(doc, number, "E1", f"`{current.ident}` repeats `{name}:`; one entry holds "
                                         "one value per key and a second copy is a second answer")
            current.keys[name] = value
            current.at[name] = number
            last_key = name
        elif text.strip() and last_key:
            current.keys[last_key] = (current.keys[last_key] + " " + text.strip()).strip()
        elif text.strip():
            f.add(doc, number, "E1",
                  f"`{current.ident}` carries a line before its first key: {text.strip()[:60]!r}; "
                  f"an entry is its headline and then {', '.join(DEFERRED_KEYS)}")
    return items


def deferred_lines(doc: Doc) -> set[int]:
    """The body line numbers inside `## Deferred`, so rule A can stand back from them.

    A3 forbids a document describing its own past. A deferral entry describes A DEFECT's past — "the
    original sweep missed the fourth site", "the earlier value was wrong" — and that is the entry's
    CONTENT, about code, not about this document. Measured: A3 fired on 7 of 178 real register rows
    on exactly that reading. A1 and A2 still apply here: a dated heading or a changelog section
    inside the register is a register being appended to, which is the thing rule A is for.
    """
    lines = doc.body()
    start = next((index for index, (_, text) in enumerate(lines)
                  if DEFERRED_HEADING_RE.match(text)), None)
    if start is None:
        return set()
    inside = set()
    for number, text in lines[start + 1:]:
        if ANY_HEADING_RE.match(text):
            break
        inside.add(number)
    return inside


def check_deferred(doc: Doc, milestones: dict, specs: dict, f: Findings) -> list[DeferredItem]:
    """Rule E. `doc` is a milestone document; `milestones` maps M<n> to its document, `specs` maps
    M<n> to the feature specs declaring it."""
    name = doc.scalar("milestone")
    items = deferred_items(doc, f)
    seen: dict[str, int] = {}
    members = {spec.scalar("id"): spec for spec in specs.get(name, [])}
    live: dict[str, str] = {}
    for spec in specs.get(name, []):
        for criterion in criteria(spec):
            live[f"AC-{criterion.number}"] = spec.rel
    for item in items:
        if item.ident in seen:
            f.add(doc, item.line, "E2", f"`{item.ident}` is already used at line {seen[item.ident]}"
                                        "; two findings under one id is one of them lost")
        seen.setdefault(item.ident, item.line)
        if not item.what:
            f.add(doc, item.line, "E1", f"`{item.ident}` says nothing after its id — the entry has "
                                        "to state WHAT WAS FOUND, in one line a reader can triage")
        for key in DEFERRED_KEYS:
            if key not in item.keys:
                f.add(doc, item.line, "E1", f"`{item.ident}` has no `{key}:`; all six of "
                                            f"{', '.join(DEFERRED_KEYS)} are required, and "
                                            "`none` is a legal value for threatens, trigger "
                                            "and owner")
        for key in item.keys:
            if key not in DEFERRED_KEYS:
                f.add(doc, item.at[key], "E1", f"`{item.ident}` carries an unknown key `{key}:`; "
                                               f"the register holds {', '.join(DEFERRED_KEYS)}")
        found_by = item.keys.get("found_by", "")
        if found_by:
            match = FOUND_BY_RE.match(found_by)
            if not match:
                f.add(doc, item.at["found_by"], "E3",
                      f"`{item.ident}` found_by `{found_by}` is not a task id; write `F-11/T3`, or "
                      "a bare `T3` when the milestone holds one feature")
            elif match.group("feature") and match.group("feature") not in members:
                f.add(doc, item.at["found_by"], "E3",
                      f"`{item.ident}` was found by `{found_by}`, but no spec in {name} declares "
                      f"`{match.group('feature')}` — the finding is filed against a milestone that "
                      "did not do the work, so nobody here can answer for it")
        if not item.keys.get("site", "").strip():
            f.add(doc, item.at.get("site", item.line), "E1",
                  f"`{item.ident}` has an empty `site:`; WHERE it was found is what makes the "
                  "entry actionable a milestone later, and `unknown` is a legal answer")
        threatens = item.keys.get("threatens", "")
        reference = CRITERION_REF_RE.match(threatens)
        if reference and threatens not in live:
            f.add(doc, item.at["threatens"], "E4",
                  f"`{item.ident}` threatens `{threatens}`, which no live criterion in {name} "
                  "declares — it was renumbered, withdrawn, or belongs to another milestone")
        owner = item.keys.get("owner", "")
        if owner and owner != "none":
            if not MILESTONE_RE.match(owner):
                f.add(doc, item.at["owner"], "E5",
                      f"`{item.ident}` owner `{owner}` is not M<number> or `none`")
            elif owner not in milestones:
                f.add(doc, item.at["owner"], "E5",
                      f"`{item.ident}` is owned by `{owner}`, which has no milestone document — "
                      "an owner that does not exist cannot close anything")
            elif milestones[owner].scalar("status") == "shipped":
                f.add(doc, item.at["owner"], "E5",
                      f"`{item.ident}` is still open and owned by `{owner}`, which has already "
                      "shipped — the milestone closed and the deferral did not, which is the one "
                      "outcome a register exists to make impossible")
        raised = item.keys.get("raised", "")
        if raised and not DATE_RE.match(raised):
            f.add(doc, item.at["raised"], "E6",
                  f"`{item.ident}` raised `{raised}` is not a YYYY-MM-DD date; an undated deferral "
                  "cannot be aged, and age is the only thing that distinguishes a decision from a "
                  "thing everybody stopped looking at")
        if doc.scalar("status") == "shipped" and item.keys.get("owner", "") == "none":
            f.add(doc, item.at.get("owner", item.line), "E5",
                  f"{name} is `status: shipped` and `{item.ident}` has no owner — sealing here "
                  "drops the finding on the floor; assign a milestone or close the entry")
    return items


# --- F: binding the domain validators to the product definition ----------------------------------

# MEASURED, across four real repositories: a repository's domain invariants are not written in this
# methodology's vocabulary. They are written as PERSONAS. Those four ship 15 custom validator
# personas between them (4, 5, 4, 2) in `docs/agents/personas/` — a tenancy isolation validator, a
# clinical safety validator, a financial integrity validator, a plane boundary validator. Each is a
# domain invariant with a reader attached. Counted by WHERE they are cited: review 100, task card
# 83, ledger 10, plan 7, feature spec 5, PRD and milestone 0. The invariant arrives at review and
# execution time and essentially never while the product is being DEFINED, which is the most
# expensive possible moment to discover it.
#
# `reviewed_by:` records which personas actually read the artifact. Rule F makes that list earn its
# keep: a validator that owns a concern this document says it moves must be on it.
#
# WHAT THE BINDING IS, AND WHY IT IS NOT ONE OF THE CHEAPER THINGS IT COULD HAVE BEEN:
#
#   * NOT the persona's `description:`. Every persona already has one — "Use when a change adds or
#     alters a tenant table, a migration, a native SQL site, a grant ..." — so matching it needs
#     zero new authoring, which is why it is tempting. It is a free-text grep over prose. This
#     toolchain has flagged real product as process three separate times for matching a WORD rather
#     than a STRUCTURE (`receipt`/`cards`, `superseded`, `history`). Declined on that record.
#   * NOT the criterion tags `[authz] [audit] [money] [pii] [a11y]` that `references/specs.md`
#     already publishes. Counted over the same four repositories: ZERO occurrences, in any spec, in
#     any repository. A rule built on an unadopted carrier reports green because it recognises
#     nothing, which is the exact failure the AC pattern already made once here.
#   * NOT path globs. A glob binds a validator to CODE, and at product-definition time there is no
#     code yet. That binding already exists one stage later as the task card's `exclusive_writes` —
#     and being one stage later is the whole problem this rule exists to get in front of.
#
# The carrier is the HORIZONTALS section, because it is already written and already structured:
# `## Horizontals` appears in 89 specs across three of the four repositories and carries 805
# labelled concern rows drawn from a vocabulary of nine labels — the same nine
# `references/specs.md` names. So a persona declares which concerns it owns, in one key, once:
#
#     covers: [tenancy, money handling]
#
# New authoring is ONE line per persona a repository chooses to bind. Nothing on the 14 base
# personas, which own no domain. Nothing new in a spec beyond the `reviewed_by:` list itself.
#
# THE POOL IS READ FROM THE REPOSITORY, never from `~/.claude/agents` or any other machine-global
# directory. A checker whose verdict depends on the laptop it runs on is not a checker.

PERSONA_DIR = ("docs", "agents", "personas")
HORIZONTALS_HEADING_RE = re.compile(r"^#{2,3}\s+Horizontals\s*$", re.IGNORECASE)
# The two AUTHORED shapes, both measured in the corpus: a `| concern | disposition |` table row
# (805 rows) and a `- **Concern:** disposition` bullet. Free prose under the heading is a third
# shape and it is deliberately NOT parsed — deciding from a sentence whether a concern "moves" is
# the word-not-a-structure trap again. Unparsable sections are COUNTED AND PRINTED instead, the way
# `ratio_meter` prints `unattributable` and `trace_check` prints its own limit every run.
HZ_ROW_RE = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<disposition>[^|]*?)\s*\|\s*$")
HZ_BULLET_RE = re.compile(r"^\s*[-*]\s+\*\*(?P<label>[^*]+?)\*\*\s*:?\s*(?P<disposition>.*)$")
# A row is EXEMPT only when it opens by declaring itself inapplicable. Measured: no row in 805
# writes a bare `N/A` — every one of the 45 real exemptions is a prefix, `N/A — invites are free.`
# or `Not applicable because this feature performs no money ...`. Matching the phrase anywhere in
# the cell instead would let a passing mention mid-sentence buy silence, so the declaration has to
# be the first thing in the cell, where a reader sees it too.
NOT_APPLICABLE_RE = re.compile(r"^\**\s*(?:n/?a|not applicable|none)\b", re.IGNORECASE)
# Dropped before two labels are compared, so `Money handling` and `Money` are the same concern and
# `Tenancy / isolation` and `tenancy` are the same concern. Comparison is on TOKEN SETS and never
# on substrings: `cost` must not match `costume`, and `audit` must not match `auditorium`.
LABEL_STOPWORDS = frozenset({"and", "or", "the", "a", "an", "of", "for", "to"})
PERSONA_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

Persona = NamedTuple("Persona", [("name", str), ("rel", str), ("covers", tuple),
                                 ("line", int), ("error", str)])
Concern = NamedTuple("Concern", [("line", int), ("label", str), ("live", bool)])


class Binding:
    """What rule F actually looked at, so that checking nothing is never mistaken for a pass.

    This is the anti-inertness apparatus and it is not decoration. Seven checkers in this
    toolchain's history passed their own tests and were inert against the real corpus; the most
    recent matched a bare `T1` while the methodology tells people to write `F-7/T1`. Every one of
    them would have been caught in a minute by a run that said out loud how many things it had
    matched. So rule F counts its own reach and prints it whenever a persona pool exists.
    """

    def __init__(self) -> None:
        self.personas: list[Persona] = []
        self.pool_dir = ""
        self.unbound_specs = 0
        self.product_docs = 0     # every `docs/product/**/*.md` read
        self.documents = 0        # ... of those, the specs, PRD and milestones F binds
        self.no_front_matter = 0  # ... of those, ones with no `---` block to hold `reviewed_by:`
        self.with_section = 0     # ... of those, ones carrying a `## Horizontals` heading
        self.unreadable = 0       # ... of those, ones whose section yielded no labelled row
        self.rows = 0             # labelled concern rows read
        self.live_rows = 0        # ... of those, ones not declared inapplicable
        self.labels: dict[str, int] = {}
        self.demands = 0          # (document, persona) pairs the binding actually required
        self.matched_bindings = 0  # `covers:` tokens that matched at least one concern label

    @property
    def bound(self) -> list[Persona]:
        return [p for p in self.personas if p.covers]

    def unbound_line(self) -> str:
        """Said only when there is something to say, so a clean repository stays quiet."""
        if not self.unbound_specs:
            return ""
        return (f"note: {self.unbound_specs} document(s) under docs/product/specs/ are not named "
                "`F-<n>-<slug>.md`, so no schema rule and no persona binding read them. That is a "
                "naming choice, not a defect — but this run inspected none of them, and an exit 0 "
                "cannot tell you which of the two happened.")

    def note(self) -> str:
        """One line, printed on every run that has a pool. It says what was checked, or that
        nothing was — never nothing at all, which is what exit 0 alone would say."""
        head = (f"persona binding: {len(self.personas)} persona(s) in {self.pool_dir}, "
                f"{len(self.bound)} with `covers:`")
        if not self.personas:
            return self.unbound_line()
        
        reach = (f"{self.documents} spec/PRD/milestone document(s) of {self.product_docs} under "
                 f"docs/product, {self.with_section} with a `## Horizontals` section, "
                 f"{self.rows} labelled concern row(s), {self.live_rows} live")
        why = []
        if self.unreadable:
            why.append(f"{self.unreadable} `## Horizontals` section(s) are prose rather than a "
                       "labelled table or bullet list, and prose is not read")
        if self.no_front_matter:
            why.append(f"{self.no_front_matter} document(s) carry no `---` block, so no "
                       "`reviewed_by:` can be read from them")
        if self.documents and not self.product_docs:
            why.append("no document under docs/product matches the spec, PRD or milestone paths")
        if self.unbound_specs:
            # The loudest silence there is: documents sitting in the specs directory that no rule
            # reads. Reported here rather than as a finding because the naming is the repository's
            # choice, not a defect this checker may charge it with.
            why.append(f"{self.unbound_specs} document(s) under docs/product/specs/ are not named "
                       "`F-<n>-<slug>.md`, so NOTHING here read them")
        suffix = ("; " + "; ".join(why)) if why else ""
        if not self.bound:
            return (f"{head}, {reach} -- RULE F CHECKED NOTHING. No persona in this repository "
                    "declares which horizontal concerns it owns, so no spec, PRD or milestone can "
                    "be held to one. Add `covers: [<concern>, ...]` to the validator personas"
                    + suffix + ".")
        if not self.live_rows:
            return (f"{head}, {reach} -- RULE F CHECKED NOTHING. There is no live concern row for "
                    "a declared `covers:` to bind to" + suffix + ".")
        return f"{head}, {reach}, {self.demands} review demand(s){suffix}."


def label_tokens(label: str) -> frozenset:
    """A concern label reduced to the words that identify it. `Tenancy / isolation` and
    `**Money handling:**` become `{tenancy, isolation}` and `{money, handling}`."""
    words = re.findall(r"[a-z0-9]+", label.lower())
    return frozenset(word for word in words if word not in LABEL_STOPWORDS)


def concern_match(declared: str, label: str) -> bool:
    """Does a `covers:` token name this concern label?

    Containment in EITHER direction over token sets, so `covers: [tenancy]` reaches
    `Tenancy / isolation` and `covers: [money handling]` reaches a row headed just `Money`. Never
    substring containment: that is how `cost` starts matching `costume`, and this toolchain has
    already shipped three rules that matched a word where they meant a structure.
    """
    left, right = label_tokens(declared), label_tokens(label)
    if not left or not right:
        return False
    return left <= right or right <= left


def read_persona_overlay(path: Path) -> Persona:
    """Read `name:` and `covers:` out of one persona overlay. Reads nothing else, on purpose.

    A persona's front matter is owned by the persona skill and carries keys this parser has no
    business ruling on — `claude.model`, `codex.sandbox`, a dotted key `parse_front_matter` would
    reject outright. So this scans the block for the two keys it needs and stays silent about the
    rest. Adjudicating another skill's schema from here would make one file fail two checkers with
    two opinions.
    """
    name = path.stem
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return Persona(name, path.name, (), 1, f"cannot read: {exc}")
    if not lines or lines[0].strip() != "---":
        return Persona(name, path.name, (), 1, "no `---` front matter block at the top of the file")
    covers: tuple = ()
    at = 1
    for index in range(1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "---":
            break
        key, separator, value = lines[index].partition(":")
        if not separator or key.strip().lower() != "covers":
            continue
        at, raw = index + 1, re.split(r"\s#", value, maxsplit=1)[0].strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        covers = tuple(part.strip().strip("'\"") for part in raw.split(",") if part.strip())
        if not covers:
            return Persona(name, path.name, (), at,
                           "`covers:` is present but empty; delete the key or name a concern")
    return Persona(name, path.name, covers, at, "")


def persona_pool(root: Path, f: Findings) -> tuple[list[Persona], str]:
    """This REPOSITORY's persona pool, or an empty one.

    Absence is silence: most repositories have no `docs/agents/personas/`, and a rule that shouts
    at every repository it does not apply to gets deleted. A file inside it that cannot be read is
    NOT silence — that is a pool the rule half-read, and half-reading is how it goes inert.
    """
    directory = root.joinpath(*PERSONA_DIR)
    if not directory.is_dir():
        return [], ""
    rel = "/".join(PERSONA_DIR)
    personas = [read_persona_overlay(path) for path in sorted(directory.glob("*.md"))]
    for persona in personas:
        if persona.error:
            f.append(Finding(f"{rel}/{persona.rel}", persona.line, "F1",
                             f"persona overlay could not be read for its binding: {persona.error}"))
        elif not PERSONA_NAME_RE.match(persona.name):
            f.append(Finding(f"{rel}/{persona.rel}", 1, "F1",
                             f"persona filename `{persona.rel}` is not a persona slug, so no "
                             "`reviewed_by:` entry can name it"))
    return personas, rel


def horizontals(doc: Doc) -> tuple[list[Concern], bool, bool]:
    """The concern rows of `## Horizontals`, whether the section exists, and whether it was read.

    Returns rows in the two authored shapes only. A section that yields no row is reported as
    unreadable rather than as clean — a spec whose horizontals are a paragraph has genuinely not
    been checked, and saying so is the difference between this rule and an inert one.
    """
    rows: list[Concern] = []
    inside = False
    present = False
    for number, text in doc.body():
        if ANY_HEADING_RE.match(text):
            inside = bool(HORIZONTALS_HEADING_RE.match(text))
            present = present or inside
            continue
        if not inside or not text.strip():
            continue
        match = HZ_ROW_RE.match(text.strip()) or HZ_BULLET_RE.match(text)
        if not match:
            continue
        # A bullet writes `- **Money handling:** ...`, a table writes `| Money handling |`. The
        # trailing colon belongs to the bullet syntax, not to the concern, and leaving it on split
        # one label into two in a real corpus reading.
        label = match.group("label").strip().strip("*").rstrip(":").strip()
        # The table's own header and its `|---|---|` separator are not concerns.
        if not label_tokens(label) or set(label) <= set("-: "):
            continue
        if label.lower() in ("concern", "horizontal", "area"):
            continue
        disposition = match.group("disposition").strip()
        rows.append(Concern(number, label, not NOT_APPLICABLE_RE.match(disposition)))
    return rows, present, bool(rows)


def check_reviewed_by(doc: Doc, f: Findings) -> list[str]:
    """F2: the shape of `reviewed_by:`. Returns the names, whatever their shape.

    NO CLOSED ROSTER, and that is a measured decision rather than laziness. `VALID_PERSONAS` in
    `validate_card.py` is exactly ("developer", "senior-developer"); real cards in these
    repositories already declare `test-judge`, `docs-steward` and `chief-of-staff`, so five real
    cards fail validation today for naming personas that exist. A hardcoded roster here would
    repeat that, and would additionally make a project unable to name its OWN validator. The shape
    is checked; the membership is not.
    """
    raw = doc.front.get("reviewed_by")
    if raw is None:
        return []
    names = [raw] if isinstance(raw, str) else list(raw)
    at = doc.at("reviewed_by")
    if not names:
        f.add(doc, at, "F2", "`reviewed_by:` is present but empty; a document nobody has reviewed "
                             "should omit the key rather than claim an empty review")
    seen: set[str] = set()
    for name in names:
        if not PERSONA_NAME_RE.match(name):
            f.add(doc, at, "F2", f"`reviewed_by:` entry {name!r} is not a persona name; entries "
                                 "are the slugs of `docs/agents/personas/<name>.md`")
        elif name in seen:
            f.add(doc, at, "F2", f"`reviewed_by:` names {name!r} twice")
        seen.add(name)
    return names


def check_binding(doc: Doc, personas: list[Persona], binding: Binding, f: Findings) -> None:
    """F3: a validator that owns a concern this document says it MOVES must have read it."""
    names = set(check_reviewed_by(doc, f))
    rows, present, readable = horizontals(doc)
    binding.documents += 1
    binding.no_front_matter += bool(doc.front_error)
    binding.with_section += present
    binding.unreadable += present and not readable
    binding.rows += len(rows)
    binding.live_rows += sum(1 for row in rows if row.live)
    for row in rows:
        binding.labels[row.label] = binding.labels.get(row.label, 0) + 1
    if not [p for p in personas if p.covers]:
        return
    for persona in personas:
        if not persona.covers or persona.name in names:
            continue
        for row in rows:
            if not row.live or not any(concern_match(c, row.label) for c in persona.covers):
                continue
            binding.demands += 1
            f.add(doc, row.line, "F3",
                  f"this document says it moves `{row.label}`, which `{persona.name}` owns, but "
                  f"`reviewed_by:` does not name it. The validator that holds this invariant is "
                  f"reading the change at review time; the definition is where it is cheap to fix.")
            break


def check_bindings_reach(binding: Binding, f: Findings) -> None:
    """F4: a `covers:` token that matches no concern label anywhere in this product corpus.

    This is the trap the last seven checkers fell into, closed at the only place it can be closed:
    a binding that cannot match is a defect in the binding, and it is invisible from the document
    side because the document simply never gets a demand. So the check runs from the PERSONA side,
    over the labels the corpus actually contains, and fires where the fix is.
    """
    if not binding.labels:
        return
    for persona in binding.personas:
        for declared in persona.covers:
            if any(concern_match(declared, label) for label in binding.labels):
                binding.matched_bindings += 1
                continue
            f.append(Finding(f"{binding.pool_dir}/{persona.rel}", persona.line, "F4",
                             f"`covers: {declared}` matches none of the "
                             f"{len(binding.labels)} concern label(s) in this repository's "
                             f"`## Horizontals` sections ("
                             f"{', '.join(sorted(binding.labels)[:6])}), so this persona is bound "
                             f"to nothing and rule F is silent for it"))


def binding_payload(binding: Binding) -> dict:
    """What rule F reached, for a machine. The counts are the point: a consumer that sees
    `"live_rows": 0` knows the rule was silent rather than satisfied."""
    return {"pool": binding.pool_dir,
            "personas": len(binding.personas),
            "bound": len(binding.bound),
            "product_documents": binding.product_docs,
            "documents": binding.documents,
            "no_front_matter": binding.no_front_matter,
            "with_horizontals": binding.with_section,
            "unreadable_horizontals": binding.unreadable,
            "concern_rows": binding.rows,
            "live_rows": binding.live_rows,
            "demands": binding.demands,
            "checked_nothing": not (binding.bound and binding.live_rows),
            "concerns": dict(sorted(binding.labels.items())),
            "covers": {p.name: list(p.covers) for p in binding.bound}}


def print_personas(binding: Binding) -> None:
    """`--personas`: the pool, what each persona owns, and what the corpus offers it to own.

    It exists so that "nothing fired" is answerable without reading the source. The three questions
    a silent rule F raises — is there a pool, does anything declare `covers:`, does the corpus have
    concerns to match — are the three blocks below, in that order.
    """
    if not binding.personas:
        print("no `docs/agents/personas/` in this repository: rule F does not apply here")
        return
    width = max(len(p.name) for p in binding.personas)
    print(f"pool: {binding.pool_dir} ({len(binding.personas)} persona(s))")
    for persona in binding.personas:
        owns = ", ".join(persona.covers) if persona.covers else "-- declares no `covers:`"
        print(f"  {persona.name.ljust(width)}  {owns}")
    print(f"\nconcern labels found in `## Horizontals` across {binding.documents} "
          f"product document(s):")
    if binding.labels:
        for label, count in sorted(binding.labels.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {str(count).rjust(4)}  {label}")
    else:
        print("  none. No spec, PRD or milestone here writes a `| concern | disposition |` row or "
              "a `- **Concern:** ...` bullet under `## Horizontals`.")
    print()
    print(binding.note() or "rule F has nothing to report")


def run(root: Path) -> Findings:
    """The findings alone, for callers that only gate. `analyse` also returns what F reached."""
    return analyse(root)[0]


def analyse(root: Path) -> tuple[Findings, Binding]:
    f = Findings()
    binding = Binding()
    product = root / "docs" / "product"
    paths = sorted(path for path in product.glob("**/*.md") if path.is_file())
    if not paths:
        # No product definition at all. The persona pool is still READ and still reported, because
        # "this repository has validators and nothing for them to review" is a true thing to say
        # and exiting 0 in silence says the opposite.
        binding.personas, binding.pool_dir = persona_pool(root, f)
        return f, binding
    # Paths with uncommitted edits are exempt from A4: they have no commit date to agree with.
    status = git(root, "status", "--porcelain") or ""
    dirty = {line[3:].strip().split(" -> ", 1)[-1].strip('"') for line in status.splitlines()}
    documents = [Doc(path, root) for path in paths]
    binding.unbound_specs = sum(1 for doc in documents if doc.looks_like_a_spec)
    for doc in documents:
        # The current-state rules apply to every product document — a market study or an
        # architecture note goes stale the same way a spec does, and A1-A3 need no schema.
        check_current_state(doc, f)
        # Everything below is a SCHEMA rule, and a schema only binds the two documents that
        # declare one: the PRD and a feature spec. Applied to the whole tree it fired on every
        # README, market study and test plan in three real repositories — twenty-odd findings on
        # first run, none of them actionable, which is how a checker gets switched off before it
        # ever reports something true.
        if not (doc.is_prd or doc.is_spec):
            continue
        if doc.front_error:
            f.add(doc, 1, "B1", f"front matter does not parse: {doc.front_error}")
            continue
        check_updated(doc, root, dirty, f)
        # An open question is legitimate until approval; approving one with the marker still in it
        # approves the question, which is how an undecided thing becomes a requirement.
        for number, text in (doc.body() if doc.scalar("status") == "approved" else []):
            if "[NEEDS CLARIFICATION:" in text:
                f.add(doc, number, "D4", "an approved document still carries a "
                                         "[NEEDS CLARIFICATION: ...] marker")
    seen: dict[str, str] = {}
    for doc in documents:
        if doc.is_spec and not doc.front_error:
            check_spec(doc, root, seen, f)
    for doc in documents:
        if doc.is_prd and not doc.front_error:
            check_prd(doc, seen, f)
    milestones, members = milestone_index(documents)
    for doc in milestones.values():
        check_deferred(doc, milestones, members, f)
    binding.personas, binding.pool_dir = persona_pool(root, f)
    binding.product_docs = len(documents)
    # F runs over specs, the PRD and milestones alike: the carrier is the `## Horizontals` section,
    # not the path, so no document type needs a special case and none can be forgotten into one.
    #
    # AND IT RUNS ON DOCUMENTS WHOSE FRONT MATTER DID NOT PARSE. Every other schema rule here skips
    # those, and copying that habit was caught in validation as the eighth inert checker of this
    # session: measured, ZERO of the 23 feature specs across the four real repositories carry a
    # `---` block at all, so a rule gated on `not doc.front_error` would have run on nothing,
    # anywhere, while passing every fixture written for it. `## Horizontals` is BODY, and body is
    # readable with or without front matter. The unreadable `reviewed_by:` is counted and printed.
    for doc in documents:
        if doc.is_spec or doc.is_prd or doc.is_milestone:
            check_binding(doc, binding.personas, binding, f)
    check_bindings_reach(binding, f)
    return f, binding


def milestone_index(documents: list[Doc]) -> tuple[dict, dict]:
    """`M<n>` -> its milestone document, and `M<n>` -> the specs declaring it.

    MEMBERSHIP DERIVES FROM THE SPECS and the milestone holds no list to disagree with them — the
    same rule `plan_waves.milestone_features` already applies, restated here rather than imported
    because that one walks the disk and this one is handed documents already read.
    """
    docs: dict[str, Doc] = {}
    members: dict[str, list[Doc]] = {}
    for doc in documents:
        if doc.is_milestone and not doc.front_error:
            name = doc.scalar("milestone")
            if MILESTONE_RE.match(name):
                docs.setdefault(name, doc)
        if doc.is_spec and not doc.front_error:
            name = doc.scalar("milestone")
            if MILESTONE_RE.match(name):
                members.setdefault(name, []).append(doc)
    return docs, members



# --- the decision queue -------------------------------------------------------------------------
# The one view a rendered explainer would have added over the markdown, delivered without a renderer.
# A council reviewing the design killed the HTML because a stdlib markdown parser is ~540 lines to
# render ~240 lines of prose that is deleted on sight, and because a rendered single spec adds
# nothing over the file. What it could not do in markdown was AGGREGATE: every open question across
# a PRD and a dozen specs, counted, in one place. That is thirty lines against the documents the
# checker already parses, and it writes nothing.
OPEN_MARKER_RE = re.compile(r"\[NEEDS CLARIFICATION:\s*(?P<question>[^\]]*)\]", re.IGNORECASE)

# A bare TBD is the same decision, written by someone who did not know the convention. It is listed
# in the queue and NEVER treated as a finding: a repository that has not adopted the marker is not
# thereby non-compliant, and inventing a violation for it is how a checker gets switched off. Real
# repositories carry sixty of these today, which is the argument for reading them rather than
# demanding they be rewritten first.
LOOSE_MARKER_RE = re.compile(r"(?<![\w-])(TBD|TODO|\?\?\?)(?![\w-])")


def decision_queue(root: Path) -> list[tuple[str, int, str, str]]:
    """Every open decision in the product definition, as (path, line, status, question).

    Ordered so the ones blocking approval come first: a question in an approved document is a
    contradiction the gate already refuses, and a question in a `building` spec is being coded
    around right now. Draft questions are ordinary and sort last.
    """
    order = {"approved": 0, "shipped": 0, "building": 1, "draft": 2, "dropped": 3, "": 2}
    rows: list[tuple[str, int, str, str]] = []
    product = root / "docs" / "product"
    for path in sorted(product.glob("**/*.md")):
        if not path.is_file():
            continue
        doc = Doc(path, root)
        status = doc.scalar("status")
        # Markers wrap. Documents are hard-wrapped at a column width, so a per-line scan misses any
        # question long enough to be worth asking — which is most of them. Fold the body into one
        # string, remembering where each line began, and map every hit back to its opening line.
        body = doc.body()
        joined, starts = "", []
        for number, text in body:
            starts.append((len(joined), number))
            joined += text + " "
        for match in OPEN_MARKER_RE.finditer(joined):
            number = next((n for offset, n in reversed(starts) if offset <= match.start()), 1)
            question = " ".join(match.group("question").split()) or "(unstated)"
            rows.append((doc.rel, number, status, question))
        for match in LOOSE_MARKER_RE.finditer(joined):
            number = next((n for offset, n in reversed(starts) if offset <= match.start()), 1)
            context = " ".join(joined[match.start():match.start() + 110].split())
            rows.append((doc.rel, number, status, f"{context}  (unmarked — {match.group(1)})"))
    rows.sort(key=lambda row: (order.get(row[2], 2), row[0], row[1]))
    return rows


def print_queue(rows: list[tuple[str, int, str, str]]) -> None:
    if not rows:
        print("decision queue: empty — no open questions in the product definition")
        return
    print(f"decision queue: {len(rows)} open question(s)\n")
    for path, line, status, question in rows:
        flag = "  <- blocks approval" if status in ("approved", "shipped") else ""
        print(f"  {path}:{line}  [{status or 'no status'}]{flag}")
        print(f"      {question}")
# S1 — NEWLY EXPOSED SURFACE MUST BE NAMED IN A FEATURE SPEC. Measured failure, not a worry: a PRD
# section headed "Out of scope for v1" named eight modules, all eight were built anyway — 229
# endpoints, none reachable, because no role that could use them is assignable. ONLY ADDED LINES ARE
# READ: moving a route exposes nothing new, and a check that fires on a refactor is off in a week.
# Below is the coverage AND ITS LIMITS. Only code files are read and an annotation must open its
# line: without those two rules a real 200-commit range gave 604 route lines, 280 of them markdown
# quoting Java and one a `Map.get` on a variable called `app`; with them, 324 and one miss. Routes
# built from constants, concatenation or a registry stay uncovered — the only side this may fail on.
ROUTE_PATTERNS = (
    ("spring", re.compile(r'^\s*@(?:Get|Post|Put|Patch|Delete)Mapping\s*\(\s*'
                          r'(?:[A-Za-z]+\s*=\s*)?\{?\s*"(?P<route>[^"]*)"')),
    ("js", re.compile(r'(?<![@\w.])(?:app|router)\s*\.\s*(?:get|post|put|patch|delete|all)'
                      r'\s*\(\s*["\'`](?P<route>/[^"\'`]*)')),
    ("python", re.compile(r'^\s*@\s*\w+\s*\.\s*(?:get|post|put|patch|delete|route)\s*\(\s*'
                          r'["\'](?P<route>/[^"\']*)')),
    ("cli", re.compile(r'(?:\badd_parser|@\s*\w+\s*\.\s*command)\s*\(\s*["\'](?P<route>[^"\']+)')),
)
# A bare @RequestMapping is a CLASS PREFIX, not a route: it prefixes the methods declared below.
SPRING_PREFIX_RE = re.compile(r'^\s*@RequestMapping\s*\(\s*(?:[A-Za-z]+\s*=\s*)?\{?\s*"([^"]*)"')
PARAM_RE = re.compile(r"\{[^{}]*\}|<[^<>]*>|(?<=/):[^/]+")
DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")
DIFF_HUNK_RE = re.compile(r"^@@ -\S+ \+(\d+)")
TEST_PATH_RE = re.compile(r"(^|/)([Tt]ests?|__tests__|testing|fixtures?|mocks?)/|(^|/)test_[^/]+$"
                          r"|[._](test|spec)\.[A-Za-z]+$|[a-z0-9]Tests?\.[A-Za-z]+$")
SURFACE_TOKEN_RE = re.compile(r"`([^`]+)`|(?<![\w`])(/[^\s`,;)\]]*)")


def deferral_queue(root: Path) -> list[tuple[str, str, int, str, str, str, str]]:
    """Every open deferral in the corpus, milestone by milestone. Shape findings are discarded:
    this is a LIST, not a gate, and `run()` is where a malformed entry is reported."""
    product = root / "docs" / "product"
    paths = sorted(path for path in product.glob("**/*.md") if path.is_file())
    documents = [Doc(path, root) for path in paths]
    rows = []
    for name, doc in sorted(milestone_index(documents)[0].items()):
        for item in deferred_items(doc, Findings()):
            rows.append((name, doc.rel, item.line, item.ident,
                         item.keys.get("owner", "") or "none",
                         item.keys.get("raised", "") or "undated", item.what))
    return rows


def print_deferred(rows: list[tuple[str, str, int, str, str, str, str]]) -> None:
    """The count is the point. A register nobody counts is a register that only grows."""
    if not rows:
        print("no deferral register found, or every register is empty")
        return
    width = max(len(row[3]) for row in rows)
    for name in sorted({row[0] for row in rows}):
        owned = [row for row in rows if row[0] == name]
        unowned = [row for row in owned if row[4] == "none"]
        print(f"{name}  {len(owned)} open, {len(unowned)} with no owner")
        for _, path, line, ident, owner, raised, what in owned:
            print(f"  {ident.ljust(width)}  {owner:<6} {raised:<10} {what[:70]}")
            print(f"  {' ' * width}  {path}:{line}")
    print(f"{len(rows)} open deferral(s) across "
          f"{len({row[0] for row in rows})} milestone(s)")


def normalise_route(text: str) -> str:
    """One shape for both sides: lower case, no trailing slash, `{id}`, `:id`, `<int:id>` and
    `<id>` all collapsed to `*`, and only the last field kept so a verb never decides a match."""
    fields = text.strip().split()
    return "/" + PARAM_RE.sub("*", fields[-1].lower() if fields else "").strip("/")


def surface_match(route: str, surface: str) -> bool:
    """Equal, or one a suffix of the other. SUFFIX MATCHING IS REQUIRED, not leniency: a class-level
    Spring prefix usually sits outside the hunk adding the method, so the extractor sees `/{id}`
    where the spec names `/api/orders/{id}`. Both start with `/`, so `endswith` needs a boundary."""
    return route == surface or route.endswith(surface) or surface.endswith(route)


def diff_added_lines(root: Path, rev_range: str | None, since: str | None):
    """(path, line, added text, the line above it) for the range. One context line is asked for
    because a `spec-exempt:` comment usually sits on an unchanged line above the route."""
    out = git(root, "log", "-p", "--format=", "--unified=1", "--no-color",
              rev_range or f"--since={since}", "--")
    if out is None:
        raise SpecError("git could not read the requested range")
    path, number, previous = "", 0, ""
    for line in out.splitlines():
        if line.startswith("+++ "):
            header = DIFF_FILE_RE.match(line)   # `+++ /dev/null` clears it: a deletion adds nothing
            path, number, previous = (header.group(1) if header else ""), 0, ""
        elif hunk := DIFF_HUNK_RE.match(line):
            number, previous = int(hunk.group(1)), ""
        elif path and line[:1] in ("+", " "):
            if line.startswith("+"):
                yield path, number, line[1:], previous
            previous, number = line[1:], number + 1


def approved_surfaces(root: Path) -> list[str]:
    """Every route under `## Surface` in a spec that is approved or later. AN EMPTY LIST MEANS
    SILENCE, and that guard is why this can be switched on at all: a repository with no
    `docs/product/specs/`, or none past draft, never agreed to the rule."""
    surfaces, directory = [], root / "docs" / "product" / "specs"
    for path in sorted(directory.glob("F-*.md")) if directory.is_dir() else []:
        doc = Doc(path, root)
        if doc.front_error or doc.scalar("status") not in ("approved", "building", "shipped"):
            continue
        inside = False
        for _, text in doc.body():
            if text.startswith("## "):
                inside = text.strip().lower() == "## surface"
            elif inside and text.strip():
                surfaces += [normalise_route(a or b) for a, b in SURFACE_TOKEN_RE.findall(text)]
    return surfaces


def check_surfaces(root: Path, rev_range: str | None, since: str | None) -> tuple[Findings, int]:
    """Findings for added routes no approved spec names, and the count skipped by an exemption. The
    exemption is not a flag on purpose: a flag is set once and forgotten, while `spec-exempt:
    <reason>` is read by whoever opens the file next, and a counted total is a decision, not a
    hole."""
    f, surfaces = Findings(), approved_surfaces(root)
    if not surfaces:
        return f, 0
    prefixes, exempt = {}, 0
    for path, number, text, previous in diff_added_lines(root, rev_range, since):
        if is_excluded(path) or TEST_PATH_RE.search(path) or not path.endswith(CODE_SUFFIXES):
            continue
        found = list(dict.fromkeys(match.group("route") for _, pattern in ROUTE_PATTERNS
                                   for match in pattern.finditer(text)))
        if not found:
            prefix = SPRING_PREFIX_RE.search(text)
            prefixes[path] = prefix.group(1) if prefix else prefixes.get(path, "")
        elif "spec-exempt:" in text or "spec-exempt:" in previous:
            exempt += len(found)
        else:
            for route in found:
                full = (prefixes.get(path, "").rstrip("/") if route[:1] == "/" else "") + route
                if not any(surface_match(normalise_route(full), s) for s in surfaces):
                    f.append(Finding(path, number, "S1", f"{full} is not named in the Surface "
                                     "section of any approved feature spec"))
    return f, exempt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--json", action="store_true", help="machine-readable findings on stdout")
    parser.add_argument("--warn-only", action="store_true", help="print findings but exit 0")
    parser.add_argument("--questions", action="store_true",
                        help="list every open decision across the product definition and exit 0")
    parser.add_argument("--deferred", action="store_true",
                        help="list every milestone's deferral register with its counts, exit 0")
    parser.add_argument("--personas", action="store_true",
                        help="show this repo's persona pool, what each `covers:`, and what rule F "
                             "could match against; exit 0")
    parser.add_argument("--surfaces", action="store_true", help="check routes added in a range")
    parser.add_argument("--range", dest="revision_range", help="a git range, e.g. main..HEAD")
    parser.add_argument("--since", help="a date git log accepts, e.g. 2026-08-14")
    args = parser.parse_args()

    if args.surfaces and not (args.revision_range or args.since):
        parser.error("--surfaces needs a scope: --range <range> or --since <date>")
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2
    if args.deferred:
        try:
            rows = deferral_queue(root.resolve())
        except SpecError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json:
            json.dump({"root": str(root.resolve()), "count": len(rows),
                       "deferred": [{"milestone": m, "path": p, "line": n, "id": i,
                                     "owner": o, "raised": r, "what": w}
                                    for m, p, n, i, o, r, w in rows]}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print_deferred(rows)
        return 0
    if args.personas:
        try:
            _, binding = analyse(root.resolve())
        except SpecError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json:
            json.dump({"root": str(root.resolve()), **binding_payload(binding)},
                      sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print_personas(binding)
        return 0
    if args.questions:
        try:
            rows = decision_queue(root.resolve())
        except SpecError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.json:
            json.dump({"root": str(root.resolve()), "count": len(rows),
                       "questions": [{"path": p, "line": n, "status": s, "question": q}
                                     for p, n, s, q in rows]}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print_queue(rows)
        return 0
    binding = Binding()
    try:
        if args.surfaces:
            found, exempt = check_surfaces(root.resolve(), args.revision_range, args.since)
        else:
            found, binding = analyse(root.resolve())
            exempt = 0
        findings = sorted(found)
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    code = 0 if (args.warn_only or not findings) else 1
    if args.json:
        json.dump({"root": str(root.resolve()), "count": len(findings), "exit": code,
                   "exempt": exempt, "findings": [item._asdict() for item in findings],
                   **({"binding": binding_payload(binding)} if binding.personas else {})},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif findings:
        width = max(len(f"{item.path}:{item.line}") for item in findings[:PRINT_CAP])
        for item in findings[:PRINT_CAP]:
            print(f"{item.path}:{item.line}".ljust(width) + f"  {item.rule}  {item.message}")
        if len(findings) > PRINT_CAP:
            print(f"... and {len(findings) - PRINT_CAP} more finding(s); fix these and run again")
    if exempt and not args.json:
        print(f"{exempt} route(s) exempt")
    # PRINTED ON EVERY RUN THAT HAS A POOL, findings or none. `trace_check.py` prints its own limit
    # every run for the same reason: the failure mode of this toolchain is not a wrong finding, it
    # is a green exit from a rule that matched nothing, and only a run that reports its own reach
    # can be caught at it. Repositories with no `docs/agents/personas/` print nothing at all.
    note = binding.note()
    if note and not args.json:
        print(note)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
