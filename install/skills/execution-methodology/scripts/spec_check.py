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

Usage:  spec_check.py [--root DIR] [--json] [--warn-only]
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

PRINT_CAP = 40   # Findings printed before the rest are only counted; forty is about a screen.

DATED_HEADING_RE = re.compile(r"^#{2,3} .*\d{4}-\d{2}-\d{2}")
HISTORY_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*\b(changelog|change log|history|revisions?|what changed)\b", re.IGNORECASE)

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
             ("depends", "withdrawn", "decisions", "edge_cases"))
PRD_KEYS = (("title", "status", "updated"), ("reach",))
AC_RE = re.compile(r"^\s*\*\*AC-(-?\d+)\*\*\s*(.*)$")
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
ID_RE = re.compile(r"^F-\d+$")
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
        value = value.strip()
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
    def is_prd(self) -> bool:
        return self.rel == "docs/product/prd.md"

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


Criterion = NamedTuple("Criterion", [("number", int), ("line", int), ("trigger", str),
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
    identifier = at = 0
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
            identifier, at, parts = int(match.group(1)), number, [match.group(2).strip()]
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


def check_current_state(doc: Doc, f: Findings) -> None:
    for number, text in doc.body():
        if DATED_HEADING_RE.match(text):
            f.add(doc, number, "A1", "dated heading: the document is being appended to rather "
                                     "than brought up to date")
        if HISTORY_HEADING_RE.match(text):
            f.add(doc, number, "A2", "changelog section: what changed is in git log, and why it "
                                     "changed belongs in a decision record")
        match = SELF_REFERENTIAL_RE.search(text)
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
    target = doc.scalar("prd")
    if target and not any(p.is_file() for p in (root / target, doc.path.parent / target)):
        f.add(doc, doc.at("prd"), "D3",
              f"`prd: {target}` does not resolve to a file, so this spec has no parent")
    withdrawn: set[int] = set()
    raw = doc.front.get("withdrawn") or []
    for item in ([raw] if isinstance(raw, str) else raw):
        if item.isdigit() and int(item) > 0:
            withdrawn.add(int(item))
        else:
            f.add(doc, doc.at("withdrawn"), "B5",
                  f"withdrawn entry {item!r} is not a positive criterion number")
    check_criteria(doc, withdrawn, f)


def check_criteria(doc: Doc, withdrawn: set[int], f: Findings) -> None:
    numbers: dict[int, int] = {}
    pairs: dict[tuple[str, str], int] = {}
    for item in criteria(doc):
        if not item.shaped:
            f.add(doc, item.line, "C1", "criterion is not of the form `**AC-<n>** When <trigger>, "
                                        "given <precondition>, <observable result>`")
        if item.number <= 0:
            f.add(doc, item.line, "C3", f"criterion number {item.number} must be greater than 0")
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


def run(root: Path) -> Findings:
    f = Findings()
    product = root / "docs" / "product"
    paths = sorted(path for path in product.glob("**/*.md") if path.is_file())
    if not paths:
        return f
    # Paths with uncommitted edits are exempt from A4: they have no commit date to agree with.
    status = git(root, "status", "--porcelain") or ""
    dirty = {line[3:].strip().split(" -> ", 1)[-1].strip('"') for line in status.splitlines()}
    documents = [Doc(path, root) for path in paths]
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
    return f



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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--json", action="store_true", help="machine-readable findings on stdout")
    parser.add_argument("--warn-only", action="store_true", help="print findings but exit 0")
    parser.add_argument("--questions", action="store_true",
                        help="list every open decision across the product definition and exit 0")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2
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
    try:
        findings = sorted(run(root.resolve()))
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    code = 0 if (args.warn_only or not findings) else 1
    if args.json:
        json.dump({"root": str(root.resolve()), "count": len(findings), "exit": code,
                   "findings": [item._asdict() for item in findings]},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif findings:
        width = max(len(f"{item.path}:{item.line}") for item in findings[:PRINT_CAP])
        for item in findings[:PRINT_CAP]:
            print(f"{item.path}:{item.line}".ljust(width) + f"  {item.rule}  {item.message}")
        if len(findings) > PRINT_CAP:
            print(f"... and {len(findings) - PRINT_CAP} more finding(s); fix these and run again")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
