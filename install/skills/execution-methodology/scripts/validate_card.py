#!/usr/bin/env python3
"""Machine-check a task card against the repository it will be executed in.

The methodology claims cards are "generated from the plan, machine-checked". Nothing checked them.
On the first live run one card was wrong three ways and every error survived to cost real work:

  1. `validation` named `com.acme.app.TenantIsolationTest`, a class that does not exist. Gradle
     runs the `--tests` filters that match, silently ignores the one that does not, and reports
     BUILD SUCCESSFUL with exit 0. That line reported green while executing zero tests.
  2. `validation` omitted the one test proving the card's own RLS invariant.
  3. `exclusive_writes` permitted a manifest but not the test pinning that manifest's cardinality,
     so the card could not be satisfied as written.

Defect 1 is the reason this script exists: a card that reports a false green is worse than a card
that fails. Every check below is severity-ranked on that axis — a finding that makes the card
unexecutable or lets it report green without proving anything is an ERROR; staleness and style are
WARNINGs.

Usage:
  validate_card.py CARD --repo PATH                     # pre-implementation; exit 1 on ERROR
  validate_card.py CARD --repo PATH --strict            # exit 1 on WARNING too, except [siblings]
  validate_card.py CARD --repo PATH --strict --phase post # require declared Create tests now exist
  validate_card.py CARD --repo PATH --quiet             # findings only, no summary header

Exit codes: 0 clean, 1 findings, 2 the card or repository could not be read.

The card is checked against the repository AND against the other cards in its own directory: `id`
and `title` must be unique among them. That check exists because two controllers once minted a card
numbered TC-60 minutes apart and one silently overwrote the other. A sibling that cannot be read or
parsed is skipped with a WARNING naming it and counted separately in the header — it is a gap in
the check, never a pass, and never a reason to fail the card being validated. That last clause is
enforced rather than merely asserted: `[siblings]` is the one field `--strict` does not promote to a
non-zero exit, because it reports on a file the card's author did not write and cannot fix. Every
other warning still fails under `--strict`.

## What the YAML parser does and does not handle

PyYAML is not in the stdlib and this script takes no dependencies, so the card format is parsed by
hand. It handles the subset a task card plausibly uses:

  handled      `key: value` scalars; folded/literal block scalars (`>` `|`, with the `-` and `+`
               chomping suffixes); block lists of `- ` items, quoted or bare, each of which may
               wrap across lines; block mappings nested to any depth; block lists whose items are
               mappings (`- key: value` plus aligned continuation keys); single-line flow lists
               `[a, b]` and flow mappings `{a: b}` with quote-aware comma splitting; `#` comments
               outside quotes; blank lines.
  NOT handled  anchors and aliases (`&x` / `*x`), tags (`!Foo`, `!!str`), merge keys (`<<:`),
               complex keys (`? `), multi-document files (`---` / `...`), flow collections that
               span lines or nest inside one another, and quoted-string escapes beyond \\" and \\\\.

Anything in the second list raises CardError and the script exits 2. It never skips a field it
could not read — a silently dropped field is how a validator starts lying about a card.

Nesting is parsed structurally. General prose-oriented checks use `as_list` to project their fields
to scalar leaves without silently dropping values. Fields with an exact structural contract are
decoded separately: in particular, `validation` accepts only a non-empty sequence of mappings with
exactly `cwd` and `argv`; it is never flattened into command text.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple, Optional

# Directories that hold generated or vendored output. Walking them is slow and, worse, wrong: the
# defect-1 class was findable under backend/app/build/classes as a stale .class file, and an index
# that includes build output would have "resolved" the missing test and reported the card clean.
SKIP_DIRS = frozenset({
    ".git", ".gradle", ".idea", ".mypy_cache", ".next", ".pytest_cache", ".ruff_cache",
    ".svn", ".terraform", ".tox", ".venv", "__pycache__", "build", "coverage", "dist",
    "graphify-out", "node_modules", "out", "target", "venv",
})

SOURCE_ROOT_RE = re.compile(
    r"(?P<module>.*)/src/(?P<sourceset>[A-Za-z0-9_]+)/(?P<lang>java|kotlin)/(?P<pkg>.+)\.(java|kt)$"
)
KEY_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_.\-]*):(?P<rest>.*)$")
BLOCK_SCALAR_RE = re.compile(r"^[>|][-+]?$")
# `&anchor` / `*alias`: the sigil must be followed by a YAML anchor name. This deliberately does
# NOT match `*.sql`, which is a glob a card legitimately writes as a bare list item.
ANCHOR_RE = re.compile(r"^[&*][A-Za-z_][A-Za-z0-9_.\-]*(?:\s|$)")
TAG_RE = re.compile(r"^!!?[A-Za-z_]")
GRADLE_TASK_TOKEN_RE = re.compile(
    r"^(?::(?P<module>[A-Za-z0-9_.\-]+))?:?(?P<task>[A-Za-z0-9_]*[Tt]est\w*|check)$"
)
MIGRATION_FILE_RE = re.compile(r"(?:^|/)V(\d+)__[^/]*\.sql$")
MIGRATION_MENTION_RE = re.compile(r"\bV(\d{1,5})\b")
MIGRATION_PATH_MENTION_RE = re.compile(r"(?:^|[/\s])V(\d+)__[^/\s]*\.sql\b")
PYTEST_SELECTOR_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py)::"
    r"(?P<test>test[A-Za-z0-9_]*)"
)
PYTEST_DECLARATION_RE = re.compile(r"(Retain|Create) (.+\.py::\S+)")
JAVA_DECLARATION_RE = re.compile(
    r"(?P<kind>Retain|Create):\s+(?P<path>[^\s:]+\.java)\s+::\s+"
    r"(?P<fqcn>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)"
)
PYTHON_EXECUTABLE_RE = re.compile(r"^python(?:3(?:\.\d+)?)?$")
SHELL_EXECUTABLES = frozenset((
    "sh", "bash", "dash", "zsh", "ksh", "mksh", "csh", "tcsh", "fish", "ash",
    "pwsh", "powershell", "cmd", "cmd.exe",
))

ERROR = "ERROR"
WARNING = "WARNING"

# Fields whose WARNINGs do not raise the `--strict` exit code. Exactly one, and it is not a
# convenience: a `[siblings]` finding reports on a NEIGHBOURING file the card's author did not write
# and cannot fix. Failing a perfect card because someone else's sealed card is unreadable is failing
# closed on the wrong file, which is the promise the module docstring already made and this makes
# true. The finding is still printed and still counted in the warning total — only the exit is
# exempt. Do not add a second entry here without the same argument: that the author of the card
# under test could not have prevented the finding.
STRICT_EXEMPT_FIELDS = ("siblings",)

CURRENT_FIELDS = (
    "id", "title", "goal", "persona", "prerequisites", "exclusive_writes",
    "forbidden_paths", "context_acquisition", "frozen_values", "invariants", "instructions",
    "tests", "gate_risk", "validation", "stop_conditions", "handoff", "commit_subject",
)
REQUIRED_NONEMPTY_FIELDS = frozenset({
    "id", "title", "goal", "persona", "exclusive_writes", "context_acquisition",
    "invariants", "instructions", "tests", "gate_risk", "validation", "stop_conditions",
    "handoff", "commit_subject",
})
# A required field whose ABSENCE carries a compatibility note.
# `title` was added after ~50 cards had already been sealed, and none of them carry one. Failing
# those is failing closed on history that cannot be edited. `--strict` does exit 1 on this warning,
# so a caller that wants a titleless card refused has an invocation that refuses it — but nothing in
# this toolchain runs `--strict` on a caller's behalf, so absence is a warning a controller is
# expected to READ, not a barrier that stops a dispatch. Do not describe it as one.
# A title that is present and blank is not history; it is a card being written now, wrongly,
# and stays an ERROR.
MISSING_FIELD_NOTE = {
    "title": " — every card needs a one-line name; warned rather than failed only because cards "
             "sealed before this rule have none, and --strict still fails it",
}
# 72 characters: the git subject-line convention, which is where a title most often ends up quoted,
# and what still fits on an 80-column line after an id prefix and two spaces. The bound exists so a
# title stays a name; a sentence belongs in `goal`.
TITLE_MAX_CHARS = 72
# What counts as a sibling card when scanning the directory. Deliberately not "every file".
CARD_SUFFIXES = (".yaml", ".yml")
VALID_PERSONAS = ("developer", "senior-developer")
# `tier` was the old name for `persona`. It collided with the unrelated rollout-tier concept, so it
# was renamed; a card still using it validates and is warned rather than failed.
DEPRECATED_ALIASES = {"tier": "persona"}
# Fields the card format used to carry and no longer does. Present on a card, they are ignored —
# but silently ignoring a field is how a card starts meaning something other than it reads.
OBSOLETE_FIELDS = {
    "allowed_reads": "an implementer has to read to orient, so this was never enforceable and the "
                     "validator could only ever warn about it",
    "adversarial_probes": "the reviewer and validator personas do this by role, on the diff, with "
                          "more context than the planner had",
}
# Files whose content is a shared ledger of what exists — the class of artifact that always has a
# test somewhere asserting its shape or cardinality.
BOOKKEEPING_SUFFIXES = (".tsv", ".csv", ".json", ".yaml", ".yml", ".properties")
TEST_DIR_MARKERS = ("/src/test/", "/src/integrationTest/", "/src/testFixtures/", "/tests/", "/test/")
TEXT_SUFFIXES = (".java", ".kt", ".kts", ".py", ".ts", ".tsx", ".js", ".sql", ".sh", ".groovy")


class CardError(Exception):
    """The card could not be read. Never raised for a card that is merely wrong."""


class ValidationCommand(NamedTuple):
    """One directly executed validation process. Private to this validator."""

    cwd: str
    argv: tuple[str, ...]


# --------------------------------------------------------------------------------------------- #
# YAML subset parser
# --------------------------------------------------------------------------------------------- #

def strip_comment(line: str) -> str:
    """Remove a trailing `#` comment, respecting quotes.

    A card scalar legitimately contains `#` inside its quoted string
    (`"./scripts/contracts.sh verify   # only if a DTO changed"`) and truncating there would make
    the command unparseable, so quote state is tracked rather than assumed.
    """
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def unquote(text: str, where: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        body = text[1:-1]
        if text[0] == '"':
            body = body.replace('\\"', '"').replace("\\\\", "\\")
        return body
    if text[:1] in "\"'":
        raise CardError(f"{where}: unterminated quoted string -> {text!r}")
    return text


def fold(parts: list[str]) -> str:
    """Fold continuation lines the way YAML folds a plain or `>` scalar: a blank line is a
    paragraph break, everything else joins with a single space."""
    paragraphs: list[str] = []
    current: list[str] = []
    for part in parts:
        if part.strip():
            current.append(part.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs).strip()


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def is_key_line(text: str) -> bool:
    """True when `text` opens a mapping entry.

    YAML requires `: ` or a colon at end of line, and that rule is what keeps `https://example.com`
    and `V188__x.sql:foo` out — the character after the colon decides, not the presence of one.
    This is the sole discriminator between a `- key: value` mapping item and a bare scalar item, so
    it has to be exactly the YAML rule rather than a heuristic with an `http` special case.
    """
    m = KEY_RE.match(text)
    return bool(m) and (not m.group("rest") or m.group("rest")[:1].isspace())


def reject_exotic(value: str, where: str) -> None:
    """Refuse the YAML the parser cannot represent, loudly.

    Extending the parser to nesting deliberately did NOT extend it to these: an alias resolved
    wrongly, or a tag ignored, changes what the card means without changing how it reads. Failing
    is the only honest answer.
    """
    v = value.strip()
    if not v:
        return
    if ANCHOR_RE.match(v):
        raise CardError(f"{where}: YAML anchors/aliases are not supported by this parser -> {v!r}")
    if TAG_RE.match(v):
        raise CardError(f"{where}: YAML tags are not supported by this parser -> {v!r}")
    if v.startswith("? "):
        raise CardError(f"{where}: complex mapping keys (`? `) are not supported -> {v!r}")


def split_flow(body: str, where: str) -> list[str]:
    """Split a single-line flow collection on commas outside quotes.

    A naive `.split(",")` corrupts `[a, "b, c"]` into three items. Nested flow collections are
    detected here and refused rather than mis-split.
    """
    parts: list[str] = []
    buf: list[str] = []
    in_single = in_double = False
    for ch in body:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "," and not in_single and not in_double:
            parts.append("".join(buf))
            buf = []
            continue
        elif ch in "[{" and not in_single and not in_double:
            raise CardError(f"{where}: nested flow collections are not supported -> {body!r}")
        buf.append(ch)
    if in_single or in_double:
        raise CardError(f"{where}: unterminated quoted string in flow collection -> {body!r}")
    parts.append("".join(buf))
    return [p for p in parts if p.strip()]


def parse_flow(inline: str, where: str) -> list[str] | dict[str, object]:
    """Parse a single-line flow collection: `[a, b]` or `{a: b}`."""
    closer = "]" if inline[0] == "[" else "}"
    kind = "sequences" if closer == "]" else "mappings"
    if not inline.endswith(closer):
        raise CardError(f"{where}: multi-line flow {kind} are not supported")
    parts = split_flow(inline[1:-1], where)
    if closer == "]":
        return [_scalar(p, where) for p in parts]
    flow: dict[str, object] = {}
    for part in parts:
        if not is_key_line(part.strip()):
            raise CardError(f"{where}: flow mapping entry is not `key: value` -> {part!r}")
        k, _, v = part.strip().partition(":")
        if k in flow:
            raise CardError(f"{where}: duplicate key `{k}` in flow mapping")
        flow[k] = _scalar(v, where)
    return flow


def _body_end(lines: list[str], i: int, indent: int) -> int:
    """Index one past the last line belonging to a key opened at `indent`: indented, or blank."""
    n = len(lines)
    while i < n and (not lines[i].strip() or indent_of(lines[i]) > indent):
        i += 1
    return i


def _first_content(lines: list[str], start: int, end: int) -> int | None:
    for j in range(start, end):
        if lines[j].strip() and not lines[j].lstrip().startswith("#"):
            return j
    return None


def parse_card(text: str, name: str = "card") -> dict[str, object]:
    """Return a nested {key: str | list | dict}. Order preserved. CardError on unsupported syntax."""
    lines = text.splitlines()
    if any(line.strip() in ("---", "...") for line in lines[1:]):
        raise CardError(f"{name}: multi-document YAML is not supported by this parser")
    doc, i = _parse_mapping(lines, 0, 0, name)
    # At column zero there is nothing to dedent to, so anything left is syntax the loop refused to
    # consume. Reporting it beats returning a partial document.
    j = _first_content(lines, i, len(lines))
    if j is not None:
        raise CardError(f"{name}:{j + 1}: could not continue parsing here -> {lines[j].strip()!r}")
    return doc


def _parse_mapping(lines: list[str], i: int, indent: int, name: str) -> tuple[dict[str, object], int]:
    """Parse consecutive `key:` entries at exactly `indent`. Stops at the first dedent."""
    doc: dict[str, object] = {}
    n = len(lines)
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        ind = indent_of(raw)
        if ind < indent:
            break
        if ind > indent:
            raise CardError(f"{name}:{i + 1}: unexpected indentation with no key above it")
        stripped = raw.strip()
        if stripped.startswith(("- ", "-\t")) or stripped == "-":
            raise CardError(f"{name}:{i + 1}: a `- ` item where a `key:` was expected "
                            f"-> {stripped!r}")
        if stripped.startswith(("? ", ": ")) or stripped in ("?", ":"):
            raise CardError(f"{name}:{i + 1}: complex mapping keys (`? `) are not supported "
                            f"-> {stripped!r}")
        if stripped.startswith("<<:"):
            raise CardError(f"{name}:{i + 1}: merge keys (`<<:`) are not supported "
                            f"-> {stripped!r}")
        m = KEY_RE.match(stripped)
        if not m:
            raise CardError(f"{name}:{i + 1}: not a `key:` line -> {stripped!r}")
        key = m.group("key")
        rest = m.group("rest")
        if rest and not rest[:1].isspace():
            raise CardError(f"{name}:{i + 1}: `{key}:` needs a space after the colon")
        if key in doc:
            raise CardError(f"{name}:{i + 1}: duplicate key `{key}`")
        where = f"{name}:{i + 1}"
        inline = strip_comment(rest).strip()
        doc[key], i = _parse_value(lines, i + 1, indent, inline, where, key, name)
    return doc, i


def _parse_value(lines: list[str], i: int, indent: int, inline: str,
                 where: str, key: str, name: str) -> tuple[object, int]:
    """Parse the value of a key whose `key:` line sat at `indent` and ended at line index `i - 1`."""
    end = _body_end(lines, i, indent)

    if BLOCK_SCALAR_RE.match(inline):
        body = lines[i:end]
        while body and not body[-1].strip():
            body.pop()
        margin = min((indent_of(x) for x in body if x.strip()), default=0)
        stripped = [b[margin:] for b in body]
        literal = inline[0] == "|"
        return ("\n".join(stripped) if literal else fold(stripped)).strip(), end

    if inline.startswith(("[", "{")):
        # Parse before rejecting stray body: a flow collection wrapped onto the next line looks
        # like "a flow value with indented content", and the accurate message is the other one.
        value = parse_flow(inline, where)
        _reject_stray_body(lines[i:end], where, key)
        return value, end

    if inline:
        reject_exotic(inline, where)
        parts = [inline]
        for b in lines[i:end]:
            b_clean = strip_comment(b).strip()
            if b_clean.startswith("- "):
                raise CardError(f"{where}: `{key}` has both an inline value and list items")
            if is_key_line(b_clean):
                raise CardError(f"{where}: `{key}` has an inline value and a nested mapping under "
                                f"it -> {b_clean!r}")
            parts.append(b_clean)
        return unquote(fold(parts), where), end

    j = _first_content(lines, i, end)
    if j is None:
        return "", end
    child = indent_of(lines[j])
    head = strip_comment(lines[j]).strip()
    if head == "-" or head.startswith("- "):
        return _parse_sequence(lines, j, child, key, name)
    return _parse_mapping(lines, j, child, name)


def _parse_sequence(lines: list[str], i: int, indent: int,
                    key: str, name: str) -> tuple[list[object], int]:
    """Parse `- ` items at exactly `indent`. An item is a mapping, or a scalar that may wrap."""
    items: list[object] = []
    n = len(lines)
    patched: list[str] | None = None
    while i < n:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        ind = indent_of(raw)
        if ind < indent:
            break
        clean = strip_comment(raw).strip()
        if ind > indent:
            raise CardError(f"{name}:{i + 1}: `{key}` list item is over-indented -> {clean!r}")
        if clean != "-" and not clean.startswith("- "):
            raise CardError(f"{name}:{i + 1}: `{key}` expected a `- ` item -> {clean!r}")
        where = f"{name}:{i + 1}"
        head = clean[2:].strip() if clean.startswith("- ") else ""

        if head.startswith(("[", "{")):
            # `- [a, b]`. The previous parser folded this into the string "[a, b]"; treating it as
            # the collection it is also makes the nested-flow refusal reachable from a list item.
            value = parse_flow(head, where)
            end = _body_end(lines, i + 1, indent)
            _reject_stray_body(lines[i + 1:end], where, key)
            items.append(value)
            i = end
            continue

        if head and is_key_line(head):
            # A mapping item. Blank out the dash in place and let _parse_mapping run from the
            # item's own column, so the first key and its aligned siblings parse as one mapping
            # and every CardError still carries the real line number.
            if patched is None:
                patched = list(lines)
            dash = raw.index("-")
            patched[i] = raw[:dash] + " " + raw[dash + 1:]
            value, i = _parse_mapping(patched, i, indent_of(patched[i]), name)
            items.append(value)
            continue

        end = _body_end(lines, i + 1, indent)
        if not head:
            j = _first_content(lines, i + 1, end)
            if j is not None:
                child = indent_of(lines[j])
                sub = strip_comment(lines[j]).strip()
                if sub == "-" or sub.startswith("- "):
                    value, i = _parse_sequence(lines, j, child, key, name)
                else:
                    value, i = _parse_mapping(lines, j, child, name)
                items.append(value)
                continue

        # A scalar item, possibly wrapping across the lines indented under it. Continuations are
        # folded verbatim — they are prose or a long command, not structure.
        reject_exotic(head, where)
        parts = [head]
        for b in lines[i + 1:end]:
            parts.append(strip_comment(b).strip() if b.strip() else "")
        items.append(unquote(fold(parts), where))
        i = end
    return items, i


def _scalar(text: str, where: str) -> str:
    reject_exotic(text, where)
    return unquote(text, where)


def _reject_stray_body(body: list[str], where: str, key: str) -> None:
    if any(b.strip() for b in body):
        raise CardError(f"{where}: `{key}` has a flow value and indented content")


# --------------------------------------------------------------------------------------------- #
# Repository index
# --------------------------------------------------------------------------------------------- #

def _translate_java_unicode_escapes(source: str) -> str:
    """Apply Java's pre-lexical Unicode translation to eligible raw backslashes."""
    out: list[str] = []
    index = 0
    trailing_backslashes = 0
    previous_was_translated = False
    escape_re = re.compile(r"\\u+([0-9A-Fa-f]{4})")
    while index < len(source):
        if source[index] != "\\":
            out.append(source[index])
            index += 1
            trailing_backslashes = 0
            previous_was_translated = False
            continue

        eligible = (trailing_backslashes == 0 or previous_was_translated
                    or trailing_backslashes % 2 == 0)
        match = escape_re.match(source, index) if eligible else None
        if match is not None:
            translated = chr(int(match.group(1), 16))
            out.append(translated)
            index = match.end()
            trailing_backslashes = trailing_backslashes + 1 if translated == "\\" else 0
            previous_was_translated = True
        else:
            out.append("\\")
            index += 1
            trailing_backslashes += 1
            previous_was_translated = False
    return "".join(out)


def _java_source_without_comments_or_strings(source: str) -> str:
    """Blank Java comments and literals without interpreting delimiters inside them."""
    source = _translate_java_unicode_escapes(source)
    out: list[str] = []
    index = 0
    state = "code"
    while index < len(source):
        if state == "code":
            if source.startswith("//", index):
                out.extend((" ", " "))
                index += 2
                state = "line-comment"
            elif source.startswith("/*", index):
                out.extend((" ", " "))
                index += 2
                state = "block-comment"
            elif source.startswith('"""', index):
                out.extend((" ", " ", " "))
                index += 3
                state = "text-block"
            elif source[index] == '"':
                out.append(" ")
                index += 1
                state = "string"
            elif source[index] == "'":
                out.append(" ")
                index += 1
                state = "char"
            else:
                out.append(source[index])
                index += 1
            continue

        if state == "line-comment":
            if source[index] in "\r\n":
                out.append(source[index])
                index += 1
                state = "code"
            else:
                out.append(" ")
                index += 1
            continue

        if state == "block-comment":
            if source.startswith("*/", index):
                out.extend((" ", " "))
                index += 2
                state = "code"
            else:
                out.append(source[index] if source[index] in "\r\n" else " ")
                index += 1
            continue

        if state == "text-block" and source.startswith('"""', index):
            out.extend((" ", " ", " "))
            index += 3
            state = "code"
            continue
        terminator = '"' if state == "string" else "'" if state == "char" else None
        if source[index] == "\\" and index + 1 < len(source):
            out.extend((" ", " "))
            index += 2
        elif terminator is not None and source[index] == terminator:
            out.append(" ")
            index += 1
            state = "code"
        else:
            out.append(source[index] if source[index] in "\r\n" else " ")
            index += 1
    return "".join(out)


def _java_type_chains(source: str) -> set[str]:
    """Return exact top-level/member type chains, excluding local types."""
    clean = _java_source_without_comments_or_strings(source)
    token_re = re.compile(
        r"[{};]|\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
    )
    stack: list[tuple[str, Optional[str]]] = []
    pending: Optional[tuple[str, bool]] = None
    chains: set[str] = set()
    for token in token_re.finditer(clean):
        value = token.group(0)
        declared = token.group(1)
        if declared:
            # A member type can only be declared directly in top-level/type scope. A declaration
            # below a method/initializer block is local and must not satisfy a class selector.
            pending = (declared, all(kind == "type" for kind, _ in stack))
        elif value == "{":
            if pending is not None and pending[1]:
                name = pending[0]
                parents = [part for kind, part in stack if kind == "type" and part]
                chains.add(".".join([*parents, name]))
                stack.append(("type", name))
            else:
                stack.append(("block", None))
            pending = None
        elif value == "}":
            if stack:
                stack.pop()
            pending = None
        else:  # semicolon: a declaration without a body cannot own a nested chain
            pending = None
    return chains

class Repo:
    """A one-pass index of the working tree. Everything downstream reads this, not the disk."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            rel_dir = os.path.relpath(dirpath, root)
            prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
            for f in sorted(filenames):
                self.files.append(prefix + f)
        self.file_set = frozenset(self.files)

        self.classes: dict[str, str] = {}          # fqcn -> repo-relative path
        self.java_types: dict[str, str] = {}       # exact source-declared top/member fqcn -> path
        self.by_simple_name: dict[str, list[str]] = {}
        for path in self.files:
            m = SOURCE_ROOT_RE.match(path)
            if not m:
                continue
            fqcn = m.group("pkg").replace("/", ".")
            self.classes.setdefault(fqcn, path)
            self.by_simple_name.setdefault(fqcn.rsplit(".", 1)[-1], []).append(path)
            if path.endswith(".java"):
                try:
                    source = (root / path).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                package, _, _ = fqcn.rpartition(".")
                for chain in _java_type_chains(source):
                    declared = f"{package}.{chain}" if package else chain
                    self.java_types.setdefault(declared, path)

    def class_path(self, fqcn: str) -> Optional[str]:
        """Resolve a normalized exact top-level or Java member type to its containing source."""
        return self.java_types.get(fqcn) or self.classes.get(fqcn)

    def module_label(self, path: str) -> str:
        """`acme-api/backend/core/src/test/java/...` -> `backend/core`, for the suggestion."""
        m = SOURCE_ROOT_RE.match(path)
        base = m.group("module") if m else str(Path(path).parent)
        return "/".join(base.split("/")[-2:]) if base else base

    def module_dir(self, name: str) -> str | None:
        """Locate a Gradle module directory by its project name."""
        for build_file in ("build.gradle.kts", "build.gradle"):
            hits = [p for p in self.files
                    if p.endswith(f"/{name}/{build_file}") or p == f"{name}/{build_file}"]
            if hits:
                return str(Path(hits[0]).parent)
        return None

    def highest_migration(self) -> tuple[int, str] | None:
        best: tuple[int, str] | None = None
        for path in self.files:
            m = MIGRATION_FILE_RE.search(path)
            if m and "/db/migration/" in f"/{path}":
                version = int(m.group(1))
                if best is None or version > best[0]:
                    best = (version, path)
        return best


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a card path glob to a regex over repo-relative posix paths.

    A pattern with no wildcard and no suffix is treated as covering its subtree, because
    `acme-api/backend/comms` in a card means the module, not a file named `comms`.
    """
    pattern = pattern.strip().rstrip("/")
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    body = "".join(out)
    if "*" not in pattern and "?" not in pattern:
        body += "(?:/.*)?"       # a bare path also covers its subtree
    return re.compile(f"^{body}$")


def literal_prefix(pattern: str) -> str:
    """The longest wildcard-free directory prefix of a glob, used to compare two globs that match
    nothing today but would collide on a file either of them creates."""
    head = re.split(r"[*?]", pattern.strip().rstrip("/"), maxsplit=1)[0]
    if "*" in pattern or "?" in pattern:
        head = head.rsplit("/", 1)[0] if "/" in head else ""
    return head.rstrip("/")


class PathSpec:
    def __init__(self, pattern: str, repo: Repo) -> None:
        self.pattern = pattern
        self.regex = glob_to_regex(pattern)
        self.matches = frozenset(p for p in repo.files if self.regex.match(p))

    def covers(self, path: str) -> bool:
        return bool(self.regex.match(path))

    def touches_dir(self, directory: str) -> bool:
        """Could this glob write anything inside `directory`, including a file not yet created?"""
        if any(p.startswith(directory + "/") or p == directory for p in self.matches):
            return True
        prefix = literal_prefix(self.pattern)
        return bool(prefix) and (prefix == directory or prefix.startswith(directory + "/"))


def is_normalized_safe_literal(pattern: str) -> bool:
    """True for an exact repository-relative path with no glob, escape, or shell metacharacters."""
    parts = pattern.split("/")
    return (
        not pattern.endswith("/")
        and not Path(pattern).is_absolute()
        and not re.match(r"^[A-Za-z]:", pattern)
        and not any(ch in pattern for ch in "*?[]{}\\;&|$`()!")
        and all(part not in ("", ".", "..") for part in parts)
        and bool(parts[-1])
    )


def specs_for(card: dict[str, object], key: str, repo: Repo) -> list[PathSpec]:
    return [PathSpec(p, repo) for p in as_list(card.get(key)) if p.strip()]


def as_list(value: object) -> list[str]:
    """Project a parsed value down to the flat list of strings the checks consume.

    Every check below reads strings, so a nested value has to be flattened somewhere. Doing it here
    rather than in the parser keeps the parsed document faithful, and keeps one rule for how
    nesting is seen: *no leaf is ever dropped*.

    A mapping entry whose value is a scalar is rendered back as `"key: value"`. That is not
    cosmetic — it is what makes an unquoted `- event: fees.payment.recorded` item, which the
    previous parser handed to the checks as that exact string, keep reaching them as that exact
    string now that it parses as a mapping. A mapping whose values are collections is a grouping
    construct for prose-oriented fields, so its keys are labels and only the leaves are yielded;
    the alternative — injecting `comms` into a path or prose set — invents findings. Exact-shape
    fields are decoded separately.
    """
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            out.extend(as_list(v))
        return out
    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            if isinstance(v, str):
                # An empty value contributes nothing, exactly as a bare `key:` at top level always
                # has. Yielding the key instead would let `validation:` full of headings and no
                # commands satisfy the required-field check — the precise shape of "reports green
                # having proved nothing" this script exists to catch.
                if v.strip():
                    out.append(f"{k}: {v}")
            else:
                out.extend(as_list(v))
        return out
    return [str(value)]


# --------------------------------------------------------------------------------------------- #
# Sibling cards
# --------------------------------------------------------------------------------------------- #

class SiblingScan:
    """The other cards in this card's directory, and the ones that could not be read.

    Kept as two lists rather than one, because "no sibling uses this id" and "one sibling could not
    be parsed, so nobody knows" are different answers and the second must never be printed as the
    first. `compared` and `skipped` are both reported in the header for exactly that reason.
    """

    def __init__(self, directory: str, cards: list[tuple[str, dict[str, object]]],
                 skipped: list[tuple[str, str]]) -> None:
        self.directory = directory
        self.cards = cards
        self.skipped = skipped


def index_siblings(card_path: Path) -> SiblingScan:
    """Parse every OTHER card file in `card_path`'s own directory.

    Three properties this has to hold, each of which was a way to get the check wrong:

      * The card never collides with itself. Identity is the resolved path, not the string it was
        spelled with — `dir/./card.yaml` and a symlink beside it are the same file.
      * A malformed sibling is a skip WITH A NOTE, never a failure of the card under test and never
        a silent omission. Failing card A because card B is unparseable is failing closed on the
        wrong file; dropping B quietly turns a gap into a green.
      * A sibling that parses but is missing `id` or `title` simply contributes no value for that
        key. It is not warned about here — its own validation run reports its own missing fields,
        and warning once per untitled sealed card would bury the finding that matters.
    """
    directory = card_path.parent
    try:
        this = card_path.resolve()
    except OSError:                                        # pragma: no cover - defensive
        this = card_path.absolute()
    cards: list[tuple[str, dict[str, object]]] = []
    skipped: list[tuple[str, str]] = []
    try:
        entries = sorted(directory.iterdir())
    except OSError as exc:
        return SiblingScan(directory.name,
                           [], [(directory.name, f"could not be listed: {exc}")])
    for entry in entries:
        if entry.suffix.lower() not in CARD_SUFFIXES:
            continue
        try:
            if entry.resolve() == this:
                continue
            if not entry.is_file():
                skipped.append((entry.name, "is not a readable file"))
                continue
            cards.append((entry.name,
                          parse_card(entry.read_text(encoding="utf-8"), entry.name)))
        except CardError as exc:
            skipped.append((entry.name, f"could not be parsed: {exc}"))
        except (OSError, UnicodeError) as exc:
            skipped.append((entry.name, f"could not be read: {exc}"))
    return SiblingScan(directory.name, cards, skipped)


# --------------------------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------------------------- #

class Findings:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, severity: str, field: str, message: str) -> None:
        self.rows.append((severity, field, message))

    @property
    def errors(self) -> int:
        return sum(1 for s, _, _ in self.rows if s == ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for s, _, _ in self.rows if s == WARNING)


def check_required_fields(card: dict[str, object], f: Findings) -> None:
    """D. Enforce the complete v1.5 schema without making sealed history unreadable."""
    resolved = dict(card)
    for old, new in DEPRECATED_ALIASES.items():
        if old in card:
            f.add(WARNING, old,
                  f"`{old}` is the former name of `{new}` — rename the field; it is still accepted "
                  "so that a card already in flight does not hard-fail")
            resolved.setdefault(new, card[old])
    known = set(CURRENT_FIELDS) | set(DEPRECATED_ALIASES) | set(OBSOLETE_FIELDS)
    for field in card:
        if field not in known:
            f.add(WARNING, field,
                  "unknown field is not part of the current task-card schema and is ignored")

    # A title marks a card authored under the current schema. Older sealed cards have no title;
    # they retain warning-level compatibility, while --strict still refuses every omission.
    current_card = "title" in card
    for field in CURRENT_FIELDS:
        if field == "validation":
            # decode_validation is the sole authority for this exact-structure field. Flattening
            # it here creates duplicate roots and lets literal argv trigger generic prose checks.
            continue
        if field not in resolved:
            if field == "title":
                f.add(WARNING, field,
                      "required field is missing" + MISSING_FIELD_NOTE.get(field, ""))
            elif current_card:
                f.add(ERROR, field, "required field is missing from the current schema")
            else:
                severity = ERROR if field in REQUIRED_NONEMPTY_FIELDS else WARNING
                f.add(severity, field, "current schema field is missing")
        elif field in REQUIRED_NONEMPTY_FIELDS and not any(
                str(v).strip() for v in as_list(resolved[field])):
            f.add(ERROR, field, "required field is present but empty")
    persona = str(resolved.get("persona", "")).strip()
    if persona and persona not in VALID_PERSONAS:
        f.add(ERROR, "persona", f"must be one of {' | '.join(VALID_PERSONAS)}, got {persona!r}")

    for field, value in card.items():
        if field in ("exclusive_writes", "forbidden_paths", "validation"):
            continue
        for item in as_list(value):
            if re.fullmatch(r"[^\s]*[/\\][^\s]*[*?][^\s]*", item.strip()):
                f.add(WARNING, field,
                      f"path glob {item!r} is outside exclusive_writes/forbidden_paths; "
                      "it is not an enforceable path constraint")


def squash(text: str) -> str:
    """Reduce a name to the characters that carry it: lowercase alphanumerics only.

    Used for the "does this title merely restate the id" test, so that `TC-60`, `tc 60`, `TC-60:`
    and `[TC-60]` are all recognised as the same non-answer.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def name_key(text: str) -> str:
    """The form two names are compared in: case-folded, internal whitespace collapsed.

    Two titles differing only in case or spacing are the same name to every reader of a status
    report, so they must collide here too.
    """
    return re.sub(r"\s+", " ", text.strip()).casefold()


def check_title(card: dict[str, object], f: Findings) -> None:
    """F. The card's name.

    Two controllers minted a card numbered TC-60 minutes apart and one silently overwrote the
    other. A bare integer collides without a sound and carries no meaning: a report listing
    `TC-52, TC-53, TC-54, TC-55` needs a translation table every time it is read, and shows backlog
    volume where four names would have shown four distinct problems. The id remains the stable key;
    the title is what prose and dispatches lead with.

    Absence is handled by check_required_fields (a WARNING, for sealed history). Everything here is
    about a title that is present and wrong, which is always a card being authored now.
    """
    if "title" not in card:
        return
    raw = card["title"]
    if not isinstance(raw, str):
        f.add(ERROR, "title", "must be a single line of text, not a list or a mapping")
        return
    title = raw.strip()
    if not title:
        return                          # already reported as "present but empty"
    if "\n" in title:
        f.add(ERROR, "title", "must be a single line — a card's name is a name, not a paragraph; "
                              "put the explanation in `goal`")
        return
    if len(title) > TITLE_MAX_CHARS:
        f.add(ERROR, "title",
              f"is {len(title)} characters; the bound is {TITLE_MAX_CHARS}, the git subject-line "
              "convention a title usually ends up quoted inside — shorten it, or move the detail "
              "into `goal`")
    card_id = str(card.get("id") or "").strip()
    if card_id and squash(title) == squash(card_id):
        f.add(ERROR, "title",
              f"{title!r} restates the id and names nothing — the id is already the key; the title "
              "is the half a reader can understand without a translation table")


def check_cross_card_uniqueness(card: dict[str, object], scan: SiblingScan, f: Findings) -> None:
    """G. Both `id` and `title` must be unique among the cards sitting beside this one.

    The scope is the card's own directory and is not recursive, because that directory is the
    plan's scratch workspace — the one unit two concurrent controllers share, and therefore the
    only scope in which a collision can actually clobber anything. `TC-60` in another plan's
    workspace is a different, legitimate card and must not be reported.

    Every value compared against is read out of a sibling FILE, never out of the card under test or
    out of anything the card declares (`prerequisites`, a manifest, a ledger). A uniqueness check
    whose denominator comes from the same place as its numerator reports a clean count and proves
    nothing; that has shipped here before.
    """
    for name, why in scan.skipped:
        f.add(WARNING, "siblings",
              f"{name} {why} — id and title uniqueness could NOT be checked against it. A sibling "
              "this validator cannot read is a gap in the check, not a pass")

    card_id = str(card.get("id") or "").strip()
    title = card["title"].strip() if isinstance(card.get("title"), str) else ""

    for field, mine, why in (
        ("id", card_id,
         "two controllers minting the same id independently is how one card silently overwrites "
         "another; renumber before dispatch"),
        ("title", title,
         "two cards with the same name cannot be told apart in a dispatch, a report, or a commit "
         "subject"),
    ):
        if not mine:
            continue                   # nothing to collide with; absence is reported elsewhere
        clashes = sorted(
            name for name, sibling in scan.cards
            if isinstance(sibling.get(field), str)
            and name_key(str(sibling[field])) == name_key(mine)
        )
        if clashes:
            f.add(ERROR, field, f"{mine} is also used by {', '.join(clashes)} in "
                                f"{scan.directory}/ — {why}")


def check_obsolete_fields(card: dict[str, object], f: Findings) -> None:
    """D'. Fields the card no longer has. Never an error — an old card still runs."""
    for field, why in OBSOLETE_FIELDS.items():
        if field in card:
            f.add(WARNING, field,
                  f"`{field}` is no longer part of the card and is ignored — {why}. Delete it.")


def java_declarations(card: dict[str, object]) -> list[tuple[str, str, str]]:
    declarations = []
    for item in as_list(card.get("tests")):
        match = JAVA_DECLARATION_RE.fullmatch(item.strip())
        if match:
            declarations.append((match.group("kind"), match.group("path"),
                                 match.group("fqcn").replace("$", ".")))
    return declarations


def _repository_executable_reason(cwd: str, argv0: str, repo: Repo) -> Optional[str]:
    """Validate direct repository-relative executables; PATH and absolute names keep v2 rules."""
    if "/" not in argv0 or Path(argv0).is_absolute():
        return None
    cwd_root = repo.root if cwd == "." else repo.root / cwd
    candidate = cwd_root / argv0
    try:
        resolved = candidate.resolve()
        resolved.relative_to(repo.root.resolve())
    except ValueError:
        return f"repository executable {argv0!r} resolves outside the repository"
    except (OSError, RuntimeError) as exc:
        return f"repository executable {argv0!r} cannot be resolved: {exc}"
    if candidate.is_symlink() and not candidate.exists():
        return f"repository executable {argv0!r} is a broken symlink"
    if not candidate.exists():
        # Lexical escapes are rejected even when the target happens not to exist.
        try:
            candidate.absolute().relative_to(repo.root.absolute())
        except ValueError:
            return f"repository executable {argv0!r} escapes the repository"
        return f"repository executable {argv0!r} does not exist"
    if not candidate.is_file():
        return f"repository executable {argv0!r} is not a regular file"
    if not os.access(candidate, os.X_OK):
        return f"repository executable {argv0!r} is not executable"
    try:
        with candidate.open("rb") as stream:
            header = stream.read(4096)
    except OSError as exc:
        return f"repository executable {argv0!r} cannot be read: {exc}"
    if header.startswith(b"#!") or b"\0" in header:
        return None
    return (f"repository executable {argv0!r} is text or empty and lacks a byte-zero #! shebang")


def _validation_cwd_reason(cwd: object, repo: Repo) -> Optional[str]:
    if not isinstance(cwd, str):
        return "cwd must be a string"
    if cwd != ".":
        if (not cwd or cwd.endswith("/") or Path(cwd).is_absolute()
                or re.match(r"^[A-Za-z]:", cwd) or "\\" in cwd
                or any(part in ("", ".", "..") for part in cwd.split("/"))):
            return "cwd must be `.` or a normalized repository-relative directory"
    target = repo.root if cwd == "." else repo.root / cwd
    if cwd != ".":
        cursor = repo.root
        for component in cwd.split("/"):
            cursor = cursor / component
            if cursor.is_symlink():
                return f"cwd {cwd!r} contains symlink component {component!r}"
    if not target.is_dir():
        return f"cwd {cwd!r} is not an existing directory"
    try:
        target.resolve().relative_to(repo.root.resolve())
    except (OSError, ValueError):
        return f"cwd {cwd!r} resolves outside the repository"
    return None


def decode_validation(value: object, repo: Repo, f: Findings) -> Optional[tuple[ValidationCommand, ...]]:
    """Decode the validation field once; return no partial commands when any item is invalid."""
    if value is None:
        f.add(ERROR, "validation", "required field is missing from the current schema")
        return None
    if value == "" or value == []:
        f.add(ERROR, "validation", "required field is present but empty")
        return None
    if not isinstance(value, list):
        f.add(ERROR, "validation",
              "must be a non-empty sequence of mappings with exactly `cwd` and `argv`")
        return None

    commands: list[ValidationCommand] = []
    invalid = False
    for index, item in enumerate(value, 1):
        reason: Optional[str] = None
        if not isinstance(item, dict):
            reason = ("legacy scalar commands are unsupported; migrate to "
                      "`- cwd: .` with an `argv:` sequence")
        elif set(item) != {"cwd", "argv"}:
            reason = "must be a mapping with exactly `cwd` and `argv`"
        else:
            reason = _validation_cwd_reason(item["cwd"], repo)
            argv = item["argv"]
            if reason is None and (not isinstance(argv, list) or not argv):
                reason = "argv must be a non-empty sequence of strings"
            elif reason is None:
                for position, argument in enumerate(argv):
                    if not isinstance(argument, str) or argument == "":
                        reason = f"argv[{position}] must be a non-empty string"
                        break
                    if any(control in argument for control in ("\0", "\r", "\n")):
                        reason = f"argv[{position}] contains NUL, CR, or LF"
                        break
                if reason is None and not argv[0].strip():
                    reason = "argv[0] must name a non-blank executable"
                if reason is None and Path(argv[0]).name in SHELL_EXECUTABLES:
                    reason = "shell interpreters are unsupported; name the direct executable"
                if reason is None and Path(argv[0]).name in ("gradle", "gradlew"):
                    for position, argument in enumerate(argv):
                        if argument == "--tests":
                            if position + 1 >= len(argv) or argv[position + 1].startswith("-"):
                                reason = "--tests requires one non-empty non-option operand"
                                break
                        elif argument == "--tests=":
                            reason = "--tests= requires a non-empty operand"
                            break
                if reason is None:
                    reason = _repository_executable_reason(str(item["cwd"]), argv[0], repo)
        if reason is not None:
            invalid = True
            f.add(ERROR, "validation", f"item {index} {reason}")
            continue
        commands.append(ValidationCommand(str(item["cwd"]), tuple(item["argv"])))
    return None if invalid else tuple(commands)


def is_gradle_command(command: ValidationCommand) -> bool:
    return Path(command.argv[0]).name in ("gradle", "gradlew")


def command_test_filters(command: ValidationCommand) -> list[str]:
    filters: list[str] = []
    for index, token in enumerate(command.argv):
        if token == "--tests" and index + 1 < len(command.argv):
            filters.append(command.argv[index + 1])
        elif token.startswith("--tests="):
            filters.append(token.partition("=")[2])
    return filters


def command_has_rerun(command: ValidationCommand) -> bool:
    return "--rerun-tasks" in command.argv


def command_gradle_tasks(command: ValidationCommand) -> list[re.Match[str]]:
    return [match for token in command.argv
            for match in [GRADLE_TASK_TOKEN_RE.fullmatch(token)] if match]


def gradle_commands(commands: tuple[ValidationCommand, ...]) -> tuple[ValidationCommand, ...]:
    return tuple(command for command in commands if is_gradle_command(command))


def check_validation_tests(card: dict[str, object], repo: Repo, phase: str,
                           parsed_gradle: tuple[ValidationCommand, ...],
                           f: Findings) -> None:
    """A. The headline check: every `--tests` filter must resolve to a real class.

    Gradle treats a `--tests` pattern that matches nothing in the target source set as satisfied
    when other patterns on the same command do match, so a typo'd or wrong-module FQCN produces
    BUILD SUCCESSFUL having run zero of the tests the card claims prove it.
    """
    declared_creates = {fqcn for kind, _, fqcn in java_declarations(card) if kind == "Create"}
    for command in parsed_gradle:
        for raw in command_test_filters(command):
            raw = raw.strip()
            fqcn = raw.split("#", 1)[0].split("::", 1)[0]
            if not fqcn:
                continue
            if "*" in fqcn or "?" in fqcn:
                f.add(WARNING, "validation",
                      f"{raw} is a wildcard filter; existence cannot be verified — "
                      "prefer an exact class so a typo cannot pass silently")
                continue
            lookup = fqcn.replace("$", ".")
            if repo.class_path(lookup) is not None:
                continue
            if phase == "pre" and lookup in declared_creates:
                continue
            simple = fqcn.rsplit(".", 1)[-1]
            elsewhere = repo.by_simple_name.get(simple, [])
            if elsewhere:
                suggestions = ", ".join(
                    f"{path_to_fqcn(p)} ({repo.module_label(p)})" for p in sorted(elsewhere)[:3]
                )
                f.add(ERROR, "validation",
                      f"{fqcn} not found; did you mean {suggestions}? "
                      "Gradle ignores a non-matching --tests filter and still reports "
                      "BUILD SUCCESSFUL, so this line proves nothing")
            else:
                f.add(ERROR, "validation",
                      f"{fqcn} not found anywhere in the repository, and no class named "
                      f"{simple} exists — this --tests filter runs zero tests and still exits 0")


def check_java_tests(card: dict[str, object], repo: Repo, writes: list[PathSpec],
                     phase: str, parsed_gradle: tuple[ValidationCommand, ...],
                     f: Findings) -> None:
    """Require declarations to bind an exact Java path, FQCN, source, and Gradle filter."""
    declarations = java_declarations(card)
    for item in as_list(card.get("tests")):
        stripped = item.strip()
        if (stripped.startswith(("Create:", "Retain:")) and ".java" in stripped
                and not JAVA_DECLARATION_RE.fullmatch(stripped)):
            f.add(ERROR, "tests",
                  f"malformed Java test declaration {stripped!r}; use exactly "
                  "Create: repo/relative/Test.java :: fully.qualified.Test or Retain: ...")

    exact_filter_counts: Counter[str] = Counter()
    for command in parsed_gradle:
        for raw in command_test_filters(command):
            raw = raw.strip()
            if raw and "*" not in raw and "?" not in raw and "#" not in raw and "::" not in raw:
                exact_filter_counts[raw.replace("$", ".")] += 1

    declaration_counts = Counter(fqcn for _, _, fqcn in declarations)
    for fqcn, count in sorted(declaration_counts.items()):
        if count != 1:
            f.add(ERROR, "tests",
                  f"{fqcn} is declared {count} times; Java Create:/Retain: declarations are "
                  "one-to-one with exact Gradle --tests filters")
    for fqcn, count in sorted(exact_filter_counts.items()):
        source_path = repo.class_path(fqcn)
        is_java = bool(source_path and source_path.endswith(".java")) or fqcn in declaration_counts
        if not is_java:
            continue
        if declaration_counts[fqcn] == 0:
            f.add(ERROR, "tests",
                  f"exact Java --tests filter {fqcn} has no matching Create:/Retain: Java "
                  "declaration; prose in tests cannot prove the path/FQCN contract")
        if count != 1:
            f.add(ERROR, "validation",
                  f"{fqcn} is selected by {count} exact Gradle --tests filters; the Java "
                  "declaration/filter mapping must be one-to-one")

    declared_fqcns = set(declaration_counts)
    for command in parsed_gradle:
        selected = {raw.replace("$", ".") for raw in command_test_filters(command)}
        if selected & declared_fqcns and not command_has_rerun(command):
            f.add(ERROR, "validation",
                  "declared Java validation must include exact --rerun-tasks in the same direct "
                  "Gradle argv")

    for kind, path, fqcn in declarations:
        if path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/")):
            f.add(ERROR, "tests", f"{kind}: {path} must be a normalized repository-relative path")
            continue
        mapped = path_to_fqcn(path)
        if mapped == path:
            f.add(ERROR, "tests",
                  f"{path} is not under a Java/Kotlin source-set path and cannot map to an FQCN")
        elif fqcn != mapped and not fqcn.startswith(mapped + "."):
            f.add(ERROR, "tests", f"{path} maps to {mapped}, not declared {fqcn}")
        if not any(marker in f"/{path}" for marker in TEST_DIR_MARKERS):
            f.add(ERROR, "tests", f"{path} is not in a test source set")

        actual_path = repo.class_path(fqcn)
        if actual_path is not None and actual_path != path:
            f.add(ERROR, "tests", f"{fqcn} exists at {actual_path}, not declared {path}")
        exists_exact = actual_path == path
        if kind == "Create" and phase == "pre" and exists_exact:
            f.add(ERROR, "tests",
                  f"Create: {path} :: {fqcn} already exists before implementation")
        elif kind == "Retain" and not exists_exact:
            f.add(ERROR, "tests", f"Retain: {path} :: {fqcn} does not exist exactly")
        elif kind == "Create" and not exists_exact:
            if not any(spec.covers(path) for spec in writes):
                f.add(ERROR, "tests", f"Create: {path} is outside exclusive_writes")
            elif phase == "post":
                f.add(ERROR, "tests",
                      f"Create: {path} :: {fqcn} is still absent after implementation")

        if exists_exact:
            try:
                source = (repo.root / path).read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                f.add(ERROR, "tests", f"{path} cannot be inspected: {exc}")
            else:
                # Comments and string literals cannot turn an empty class into a test merely by
                # mentioning `@Test` in prose. This is intentionally a lexical check, not a Java
                # parser; compilation still owns syntax and type correctness.
                source = _java_source_without_comments_or_strings(source)
                annotation = re.compile(
                    r"@(?:org\.junit\.jupiter\.(?:api\.)?)?"
                    r"(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b"
                )
                if not annotation.search(source):
                    f.add(ERROR, "tests",
                          f"{path} contains no JUnit test declaration; a class shell proves nothing")
                if phase == "post":
                    package_match = re.search(
                        r"\bpackage\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;", source)
                    actual_package = package_match.group(1) if package_match else None
                    expected_package, _, expected_class = mapped.rpartition(".")
                    if actual_package != expected_package:
                        label = actual_package or "no package"
                        f.add(ERROR, "tests",
                              f"{path} declares package {label}, not {expected_package} required "
                              f"by {fqcn}")
                    depth = 0
                    top_level: list[str] = []
                    token_re = re.compile(
                        r"[{}]|\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
                    )
                    for token in token_re.finditer(source):
                        if token.group(0) == "{":
                            depth += 1
                        elif token.group(0) == "}":
                            depth = max(0, depth - 1)
                        elif depth == 0 and token.group(1):
                            top_level.append(token.group(1))
                    if expected_class not in top_level:
                        label = ", ".join(top_level) if top_level else "no top-level class"
                        f.add(ERROR, "tests",
                              f"{path} declares top-level class {label}, not {expected_class} "
                              f"required by {fqcn}")

        if exact_filter_counts[fqcn] == 0:
            f.add(ERROR, "tests",
                  f"{kind}: {path} :: {fqcn} has no exact non-wildcard Gradle --tests filter")


def pytest_arguments(command: ValidationCommand) -> Optional[tuple[str, ...]]:
    executable = Path(command.argv[0]).name
    if executable == "pytest":
        return command.argv[1:]
    if (PYTHON_EXECUTABLE_RE.fullmatch(executable)
            and len(command.argv) >= 3
            and command.argv[1:3] == ("-m", "pytest")):
        return command.argv[3:]
    return None


def check_pytest_selectors(card: dict[str, object], repo: Repo,
                           writes: list[PathSpec],
                           commands: tuple[ValidationCommand, ...], f: Findings) -> None:
    """Resolve exact pytest node IDs without importing candidate modules.

    The supported form is intentionally one repository-relative Python path followed by one
    top-level test function. Pytest accepts much broader node IDs, but pretending to prove nested,
    parametrized, absolute, or traversal selectors would recreate the false-green failure this
    validator exists to prevent.
    """
    declarations: dict[str, set[str]] = {}
    for item in as_list(card.get("tests")):
        match = PYTEST_DECLARATION_RE.fullmatch(item.strip())
        if match:
            declarations.setdefault(match.group(2), set()).add(match.group(1))

    for command in commands:
        arguments = pytest_arguments(command)
        if arguments is None:
            continue
        for token in arguments:
            if token.startswith("@"):
                f.add(ERROR, "validation",
                      f"{token} is a pytest response-file argument; response files are "
                      "unsupported and are not opened or expanded")
        selector_tokens = [token for token in arguments if "::" in token]

        for selector in selector_tokens:
            match = PYTEST_SELECTOR_RE.fullmatch(selector)
            if not match or any(part in (".", "..") for part in selector.split("::", 1)[0].split("/")):
                f.add(ERROR, "validation",
                      f"{selector} is an unsupported pytest selector; use exactly "
                      "path/to/test_file.py::test_name")
                continue

            relative_path = match.group("path")
            path = relative_path if command.cwd == "." else f"{command.cwd}/{relative_path}"
            test_name = match.group("test")
            exists = False
            if path in repo.file_set:
                try:
                    module = ast.parse((repo.root / path).read_text(encoding="utf-8"), filename=path)
                except (OSError, SyntaxError, UnicodeError) as exc:
                    f.add(ERROR, "validation",
                          f"{selector} cannot be verified by AST: {exc}")
                    continue
                exists = any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == test_name
                    for node in module.body
                )
            if exists:
                continue

            resolved_selector = f"{path}::{test_name}"
            declaration = declarations.get(resolved_selector, set())
            if "Retain" in declaration:
                f.add(ERROR, "tests",
                      f"Retain {resolved_selector} does not exist as a top-level test function")
            elif "Create" in declaration:
                if any(spec.covers(path) for spec in writes):
                    f.add(WARNING, "tests",
                          f"Create {resolved_selector} is still absent; permitted before implementation "
                          "because its file is covered by exclusive_writes")
                else:
                    f.add(ERROR, "tests",
                          f"Create {resolved_selector} is outside exclusive_writes and cannot be satisfied")
            else:
                f.add(ERROR, "validation",
                      f"{selector} does not exist as a top-level test function and is not declared "
                      f"exactly as Retain {resolved_selector} or Create {resolved_selector}")


def path_to_fqcn(path: str) -> str:
    m = SOURCE_ROOT_RE.match(path)
    return m.group("pkg").replace("/", ".") if m else path


def check_validation_module_placement(
        card: dict[str, object], repo: Repo,
        parsed_gradle: tuple[ValidationCommand, ...], f: Findings) -> None:
    """A'. A class that exists but lives outside the module whose test task runs is the same
    silent-green failure wearing a different hat: it is not on that source set, so the filter
    matches nothing."""
    for command in parsed_gradle:
        modules = {m.group("module") for m in command_gradle_tasks(command) if m.group("module")}
        if len(modules) != 1:
            continue
        module = modules.pop()
        module_dir = repo.module_dir(module)
        if not module_dir:
            continue
        for raw in command_test_filters(command):
            fqcn = raw.split("#", 1)[0].replace("$", ".")
            path = repo.class_path(fqcn)
            if path and not path.startswith(module_dir + "/"):
                f.add(WARNING, "validation",
                      f"{fqcn} lives in {repo.module_label(path)} but the command runs :{module}:test; "
                      "a filter that names no class in the target source set matches nothing")


def check_validation_cacheable(card: dict[str, object], repo: Repo,
                               writes: list[PathSpec],
                               parsed_gradle: tuple[ValidationCommand, ...],
                               f: Findings) -> None:
    """B. A Gradle test command with no rerun can report UP-TO-DATE, BUILD SUCCESSFUL, zero tests.

    Severity depends on whether the task can dirty the module at all. If the module is inside
    `exclusive_writes` the task's own edits will normally invalidate the cache, so this is a
    WARNING. If the command verifies a module the task is not permitted to write, nothing can
    invalidate it and the line is structurally incapable of running — that is an ERROR.
    """
    for command in parsed_gradle:
        tasks = command_gradle_tasks(command)
        if not tasks:
            continue
        if command_has_rerun(command):
            continue
        modules = sorted({m.group("module") for m in tasks if m.group("module")})
        label = ", ".join(f":{m}" for m in modules) or "the root project"
        untouchable = []
        for module in modules:
            module_dir = repo.module_dir(module)
            if module_dir and not any(spec.touches_dir(module_dir) for spec in writes):
                untouchable.append(module)
        if untouchable:
            f.add(ERROR, "validation",
                  f"{', '.join(':' + m for m in untouchable)} test task has no exact "
                  "--rerun-tasks, and exclusive_writes cannot dirty that module — the task will be "
                  "UP-TO-DATE and report BUILD SUCCESSFUL without executing a test")
        else:
            f.add(WARNING, "validation",
                  f"{label} test task has no exact --rerun-tasks; if the task's edits "
                  "do not invalidate it, it can report BUILD SUCCESSFUL having run nothing")


def check_gate_risk_covered(card: dict[str, object],
                            commands: tuple[ValidationCommand, ...], f: Findings) -> None:
    """Every artifact named in gate_risk should be exercised by a validation command."""
    arguments = tuple(argument for command in commands for argument in command.argv)
    # `verifyBackendTestTaxonomy` is the verifier for `test-taxonomy.tsv`; a literal filename match
    # would miss it and warn about an artifact the card already covers. Compare on alphanumerics.
    squashed = "".join(re.sub(r"[^a-z0-9]", "", argument.lower())
                       for argument in arguments)
    for artifact in as_list(card.get("gate_risk")):
        name = artifact.strip()
        if not name or name.lower() in ("none", "n/a"):
            continue
        stem = Path(name).stem
        token = re.sub(r"[^a-z0-9]", "", stem.lower())
        if stem and token not in squashed and Path(name).name not in arguments:
            f.add(WARNING, "gate_risk",
                  f"{name} is named as at risk but no validation command mentions it — "
                  "its cheap verifier is what stops this failing an hour into a full gate")


def check_path_coherence(card: dict[str, object], repo: Repo,
                         writes: list[PathSpec],
                         forbidden: list[PathSpec], phase: str, f: Findings) -> None:
    """C. The path fields must describe a task that can actually be completed."""
    for w in writes:
        for b in forbidden:
            shared = w.matches & b.matches
            prefix_clash = (literal_prefix(w.pattern).startswith(literal_prefix(b.pattern)) or
                            literal_prefix(b.pattern).startswith(literal_prefix(w.pattern)))
            if shared:
                sample = ", ".join(sorted(shared)[:2])
                f.add(ERROR, "exclusive_writes",
                      f"{w.pattern} and forbidden_paths {b.pattern} both match {sample} — "
                      "the card permits and forbids the same file")
            elif prefix_clash and literal_prefix(b.pattern) and literal_prefix(w.pattern):
                f.add(WARNING, "exclusive_writes",
                      f"{w.pattern} overlaps forbidden_paths {b.pattern} by prefix; "
                      "nothing matches today, but a new file under it would be both")

    for spec in forbidden:
        if not spec.matches:
            if is_normalized_safe_literal(spec.pattern):
                # An exact forbidden literal is an assertion of absence. Existing boundaries are
                # also valid and are checked above solely for overlap with exclusive_writes.
                continue
            f.add(WARNING, "forbidden_paths",
                  f"{spec.pattern} matches nothing in the tree and is not a safe exact absence "
                  "literal; globs, absolute/escaping paths, and metacharacters are not proofs")
    for spec in writes:
        pattern = spec.pattern
        normalized_literal = is_normalized_safe_literal(pattern)
        if normalized_literal and (repo.root / pattern).is_dir():
            f.add(ERROR, "exclusive_writes",
                  f"{pattern} is an existing directory; exclusive_writes must name files or "
                  "explicit matching patterns, not rely on bare-directory subtree semantics")
            continue
        if not spec.matches:
            if phase == "pre" and normalized_literal:
                # Absence is the assertion for a new exact file. A typo is indistinguishable here
                # and is deliberately caught by the mandatory post-phase existence check.
                continue
            if phase == "post":
                f.add(ERROR, "exclusive_writes",
                      f"{pattern} must exist in post phase but matches nothing in the tree")
            else:
                f.add(WARNING, "exclusive_writes",
                      f"{pattern} matches nothing in the tree and is not a safe exact new-file "
                      "literal; globs, directories, absolute/escaping paths, and metacharacters "
                      "cannot use the pre-phase creation exception")


def mentions_in_code(body: str, needle: str) -> bool:
    """True when `needle` appears on a line that is not a comment.

    Necessary, not fussiness. Two javadoc paragraphs in this repository mention manifest filenames
    purely to explain themselves, and a naive substring match reports both as coupled tests. A
    validator with obvious false positives gets switched off, so the mention has to look like code.
    """
    for line in body.splitlines():
        if needle not in line:
            continue
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*", "#", "<!--")):
            continue
        return True
    return False


_UNREAD = object()


def scan_for(root: Path, paths: list[str], needles: set[str],
             cache: dict[str, bytes | None]) -> dict[str, set[str]]:
    """-> {path: the needles that appear on a non-comment line of it}.

    The cost this replaces was not the directory walk (21 ms) — it was decoding ~16 MB of source
    and re-splitting every file into lines once per needle. Here each file is read as bytes at most
    once, and a bytes-level substring test rejects it before anything is decoded or split. On a
    mid-sized monorepo that precheck clears >99.9% of candidates, so decode and line-scan are paid
    by the two files that can actually be findings.

    Reading is still O(bytes), which is the floor for a content search that cannot be narrowed by
    filename — `data-retention-manifest.tsv` is loaded by a class whose name does not contain it,
    which is the whole reason the check has two hops. Shelling out to `grep -rlF` was measured at
    ~680 ms on this tree, an order of magnitude worse, because grep re-walks the directories
    SKIP_DIRS exists to prune.
    """
    if not needles:
        return {}
    probes = [(n, n.encode("utf-8")) for n in needles]
    hits: dict[str, set[str]] = {}
    for path in paths:
        raw = cache.get(path, _UNREAD)
        if raw is _UNREAD:
            try:
                raw = (root / path).read_bytes()
            except OSError:
                raw = None
            cache[path] = raw          # type: ignore[assignment]
        if raw is None:
            continue
        candidates = [n for n, probe in probes if probe in raw]      # type: ignore[operator]
        if not candidates:
            continue
        body = raw.decode("utf-8", "replace")                        # type: ignore[union-attr]
        found = {n for n in candidates if mentions_in_code(body, n)}
        if found:
            hits[path] = found
    return hits


def check_write_set_satisfiable(card: dict[str, object], repo: Repo,
                                writes: list[PathSpec], f: Findings) -> None:
    """C (defect 3). A card that may write a bookkeeping artifact must also be able to write the
    tests that pin that artifact, or the task is unsatisfiable as specified.

    The real failure: `exclusive_writes` permitted the school data-export manifest but not the
    tests asserting its contents. Adding an exported table requires both. The implementer correctly
    refused to widen its own scope and the task stalled until a human ruling amended the card.

    Coupling is found in two hops, because a manifest is rarely named by the test that pins it:
    first the main-source class that loads the artifact by name, then the tests that exercise that
    class. One hop only finds tests that hardcode the filename, which is the minority.
    """
    artifacts = sorted({p for spec in writes for p in spec.matches
                        if p.endswith(BOOKKEEPING_SUFFIXES)})
    if not artifacts:
        return

    basenames = {artifact: Path(artifact).name for artifact in artifacts}
    cache: dict[str, bytes | None] = {}

    # Hop 1: the main-source classes that load an artifact by name.
    main_paths = [p for p in repo.files
                  if p.endswith(TEXT_SUFFIXES) and "/src/main/" in f"/{p}"]
    owners: dict[str, set[str]] = {}
    for path, found in scan_for(repo.root, main_paths, set(basenames.values()), cache).items():
        for needle in found:
            owners.setdefault(needle, set()).add(Path(path).stem)

    # Hop 2: the tests that exercise those classes. A test the card may already write can never be
    # a finding, so it is excluded before it is read rather than after — the write set is known
    # from the index, and on a card like AUT-M1-06 that is most of the module under test.
    test_paths = [p for p in repo.files
                  if p.endswith(TEXT_SUFFIXES)
                  and any(marker in f"/{p}" for marker in TEST_DIR_MARKERS)
                  and not any(spec.covers(p) for spec in writes)]
    needles = set(basenames.values()) | {stem for s in owners.values() for stem in s}
    test_hits = scan_for(repo.root, test_paths, needles, cache)

    for artifact in artifacts:
        basename = basenames[artifact]
        artifact_owners = owners.get(basename, set())
        for test_path in test_paths:                 # repo order, so findings stay stable
            found = test_hits.get(test_path)
            if not found:
                continue
            if basename in found:
                why = f"names {basename}"
            else:
                shared = sorted(found & artifact_owners)
                if not shared:
                    continue
                why = f"exercises {shared[0]}, which loads {basename}"
            f.add(ERROR, "exclusive_writes",
                  f"unsatisfiable write set: the card may write {artifact} but not {test_path}, "
                  f"which {why} — those two change together or not at all")


def check_frozen_migration(card: dict[str, object], repo: Repo,
                           writes: list[PathSpec], phase: str,
                           commands: tuple[ValidationCommand, ...], f: Findings) -> None:
    """E. Heuristic, deliberately narrow: if frozen_values names a V<n> migration, compare it with
    the repository's actual highest. Plans go stale between writing and dispatch because migration
    numbers allocate in commit order, not plan order."""
    mentioned: set[int] = set()
    for value in as_list(card.get("frozen_values")):
        mentioned.update(int(m.group(1))
                         for m in MIGRATION_PATH_MENTION_RE.finditer(value))
        version_mentions = list(MIGRATION_MENTION_RE.finditer(value))
        if re.search(r"\bmigration\b", value, re.IGNORECASE):
            unrelated_labels = {
                int(match.group(1))
                for match in re.finditer(
                    r"\bunrelated\s+V(\d+)\b[^.]{0,48}\b(?:design|package|label)\b",
                    value,
                    re.IGNORECASE,
                )
            }
            for match in version_mentions:
                if int(match.group(1)) not in unrelated_labels:
                    mentioned.add(int(match.group(1)))
    forbidden_versions = {
        int(match.group(1))
        for pattern in as_list(card.get("forbidden_paths"))
        if is_normalized_safe_literal(pattern)
        for match in [MIGRATION_FILE_RE.search(pattern)]
        if match
    }
    # A higher version repeated only in frozen_values and fenced by an exact forbidden migration
    # path is evidence that this card must NOT create it, not a stale intended migration. Operational
    # mentions remain active even when the same version is fenced.
    active_mentions = mentioned - forbidden_versions
    operational_mentions = {
        int(match.group(1))
        for value in (as_list(card.get("instructions"))
                      + as_list(card.get("tests"))
                      + [argument for command in commands for argument in command.argv])
        for match in MIGRATION_PATH_MENTION_RE.finditer(value)
    }
    # The version the card will CREATE is the one its exclusive_writes glob claims. frozen_values
    # legitimately mentions others — the current highest, or the stale number the plan used — so
    # taking the maximum mention as the intent misreads a card that is documenting its own
    # correction. Fall back to the maximum only when the write set names no migration.
    declared = {int(m.group(1))
                for pattern in as_list(card.get("exclusive_writes"))
                for m in re.finditer(r"(?:^|/)V(\d+)__", pattern)}
    if not declared and not active_mentions:
        return
    intended = max(declared) if declared else max(active_mentions)

    highest = repo.highest_migration()
    if highest is None:
        f.add(WARNING, "frozen_values",
              f"names migration V{intended} but no db/migration directory was found")
        return
    top, top_path = highest
    owns_top = any(
        any(int(match.group(1)) == intended
            for match in re.finditer(r"(?:^|/)V(\d+)__", spec.pattern))
        and spec.covers(top_path)
        for spec in writes
    )
    ahead = sorted(v for v in (active_mentions | operational_mentions) if v > intended)
    if ahead and declared:
        f.add(WARNING, "frozen_values",
              f"also names {', '.join('V' + str(v) for v in ahead)}, above the V{intended} this "
              "card creates — confirm that is a documented correction and not a stale plan value")
    if intended <= top and not (phase == "post" and intended == top and owns_top):
        f.add(ERROR, "frozen_values",
              f"names V{intended} but V{top} already exists ({top_path}) — "
              f"the next free version is V{top + 1}")
    elif intended > top + 1:
        f.add(WARNING, "frozen_values",
              f"names V{intended} but the repository's highest is V{top} ({top_path}); "
              f"the next free version is V{top + 1} — the plan's version is probably stale")


def check_context_acquisition(card: dict[str, object], f: Findings) -> None:
    """Style, WARNING only. The closing instruction is what stops an agent reading the plan."""
    steps = as_list(card.get("context_acquisition"))
    if steps and not any("read nothing else" in s.lower() for s in steps):
        f.add(WARNING, "context_acquisition",
              "no closing 'Read nothing else unless this card names it' step — without it the "
              "agent arrives at the work with a full context window")


CARD_LINE_BUDGET = 150
FROZEN_INLINE_BUDGET = 10


def check_size_budget(text: str, f: Findings) -> None:
    """Methodology v3.0 size budget. WARNING severity, so --strict — the gate mode — fails it.

    A card past 150 lines is describing a task the plan failed to decompose; it returns to the
    plan, not to a bigger card. Comment lines count — the largest card on record grew mostly by
    preamble. A `frozen_values` entry past ten raw lines is a payload that belongs in a committed
    contract file the card names by path, where one authority serves every card; inlined, each
    card carries its own paraphrase.
    """
    lines = text.splitlines()
    if len(lines) > CARD_LINE_BUDGET:
        f.add(WARNING, "size",
              f"card is {len(lines)} lines, over the {CARD_LINE_BUDGET}-line budget — decompose "
              "the task in the plan and regenerate; do not grow the card")

    # Measure the raw frozen_values block: folding in the parser hides line structure, and the
    # constraint is about what a reader must scroll past, not about parsed semantics.
    start = None
    for i, line in enumerate(lines):
        if indent_of(line) == 0 and strip_comment(line).strip().startswith("frozen_values"):
            start = i
            break
    if start is None:
        return
    block: list[tuple[int, str]] = []
    for line in lines[start + 1:]:
        stripped = strip_comment(line).strip()
        if stripped and indent_of(line) == 0:
            break
        block.append((indent_of(line), line))
    content = [(ind, ln) for ind, ln in block if strip_comment(ln).strip()]
    if not content:
        return
    item_indent = min(ind for ind, _ in content)
    item_lines = 0
    item_head = ""
    for ind, line in content:
        stripped = strip_comment(line).strip()
        starts_item = ind == item_indent and (stripped.startswith("- ") or is_key_line(stripped))
        if starts_item:
            if item_lines > FROZEN_INLINE_BUDGET:
                f.add(WARNING, "frozen_values",
                      f"inline entry {item_head!r} spans {item_lines} lines, over the "
                      f"{FROZEN_INLINE_BUDGET}-line budget — move it to a committed contract or "
                      "interface file and freeze the path and commit instead")
            item_lines = 1
            item_head = stripped[:60]
        elif item_lines:
            item_lines += 1
        else:
            item_lines = 1
            item_head = stripped[:60]
    if item_lines > FROZEN_INLINE_BUDGET:
        f.add(WARNING, "frozen_values",
              f"inline entry {item_head!r} spans {item_lines} lines, over the "
              f"{FROZEN_INLINE_BUDGET}-line budget — move it to a committed contract or "
              "interface file and freeze the path and commit instead")


# --------------------------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------------------------- #

def validate(card_path: Path, repo_root: Path,
             phase: str = "pre") -> tuple[dict[str, object], Repo, SiblingScan, Findings]:
    text = card_path.read_text(encoding="utf-8")
    card = parse_card(text, card_path.name)
    repo = Repo(repo_root)
    scan = index_siblings(card_path)
    f = Findings()
    check_size_budget(text, f)

    writes = specs_for(card, "exclusive_writes", repo)
    forbidden = specs_for(card, "forbidden_paths", repo)
    commands = decode_validation(card.get("validation"), repo, f)

    if commands is not None:
        parsed_gradle = gradle_commands(commands)
        check_validation_tests(card, repo, phase, parsed_gradle, f)
        check_java_tests(card, repo, writes, phase, parsed_gradle, f)
        check_pytest_selectors(card, repo, writes, commands, f)
        check_validation_module_placement(card, repo, parsed_gradle, f)
        check_validation_cacheable(card, repo, writes, parsed_gradle, f)
    check_path_coherence(card, repo, writes, forbidden, phase, f)
    check_write_set_satisfiable(card, repo, writes, f)
    check_required_fields(card, f)
    check_title(card, f)
    check_cross_card_uniqueness(card, scan, f)
    check_obsolete_fields(card, f)
    check_frozen_migration(card, repo, writes, phase, commands or (), f)
    if commands is not None:
        check_gate_risk_covered(card, commands, f)
    check_context_acquisition(card, f)
    return card, repo, scan, f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", help="path to the task card YAML")
    ap.add_argument("--repo", required=True, help="repository the card will be executed in")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings as well as errors")
    ap.add_argument("--phase", choices=("pre", "post"), default="pre",
                    help="pre permits declared Create tests to be absent; post requires them")
    ap.add_argument("--quiet", action="store_true", help="print findings only")
    args = ap.parse_args()

    card_path = Path(args.card).expanduser()
    repo_root = Path(args.repo).expanduser().resolve()
    if not card_path.is_file():
        print(f"not a file: {card_path}", file=sys.stderr)
        return 2
    if not repo_root.is_dir():
        print(f"not a directory: {repo_root}", file=sys.stderr)
        return 2

    try:
        card, repo, scan, findings = validate(card_path, repo_root, args.phase)
    except CardError as e:
        print(f"  ERROR   {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"cannot read: {e}", file=sys.stderr)
        return 2

    card_id = str(card.get("id") or card_path.stem)
    title = card["title"].strip() if isinstance(card.get("title"), str) else ""
    if not args.quiet:
        # The sibling counts are printed whether or not anything collided: the denominator of a
        # uniqueness check is part of its result, and "0 compared" and "3 compared" are very
        # different clean runs. `not read` is never folded into `compared`.
        print(f"card {card_id}" + (f' "{title}"' if title else "") + f": {len(card)} field(s) "
              f"parsed, {len(repo.files)} file(s) indexed in {repo_root.name}, "
              f"{len(scan.cards)} sibling card(s) compared, {len(scan.skipped)} not read")
    for severity, field, message in findings.rows:
        print(f"  {severity:<7} [{field}] {message}")

    if not findings.rows:
        if not args.quiet:
            print("  no findings")
        return 0
    if not args.quiet:
        print(f"  {findings.errors} error(s), {findings.warnings} warning(s)")
    if findings.errors:
        return 1
    if args.strict and any(field not in STRICT_EXEMPT_FIELDS for _, field, _ in findings.rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
