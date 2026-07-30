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
  validate_card.py CARD --repo PATH          # exit 1 on any ERROR
  validate_card.py CARD --repo PATH --strict # exit 1 on any WARNING too (for gates)
  validate_card.py CARD --repo PATH --quiet  # findings only, no summary header

Exit codes: 0 clean, 1 findings, 2 the card or repository could not be read.

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

Nesting is parsed structurally, but the checks below consume flat lists of strings, so `as_list`
projects a nested value down to its scalar leaves. That projection is lossless for the shapes a
card actually uses: a mapping entry whose value is a scalar is rendered back as `"key: value"`
(so an unquoted `- event: fees.payment.recorded` item reads exactly as it did when the parser
treated it as a string), and a mapping used purely to *group* lists — `validation:` split by
module, say — contributes every command in every group. What a grouping key never does is vanish
a value: every leaf reaches the checks.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shlex
import sys
from pathlib import Path

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
# `--tests 'x'`, `--tests "x"`, `--tests x`. Gradle also accepts `--tests=x`.
TESTS_FILTER_RE = re.compile(r"--tests[=\s]+(?:'([^']*)'|\"([^\"]*)\"|(\S+))")
GRADLE_TASK_RE = re.compile(r"(?<![\w.-])(?::([A-Za-z0-9_.\-]+))?:?([A-Za-z0-9_]*[Tt]est\w*|check)\b")
MIGRATION_FILE_RE = re.compile(r"(?:^|/)V(\d+)__[^/]*\.sql$")
MIGRATION_MENTION_RE = re.compile(r"\bV(\d{1,5})\b")
MIGRATION_PATH_MENTION_RE = re.compile(r"(?:^|[/\s])V(\d+)__[^/\s]*\.sql\b")
PYTEST_SELECTOR_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py)::"
    r"(?P<test>test[A-Za-z0-9_]*)"
)
PYTEST_DECLARATION_RE = re.compile(r"(Retain|Create) (.+\.py::\S+)")
PYTEST_INVOCATION_RE = re.compile(
    r"(?:^|(?:;|&&|\|\||\|)\s*)"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]+\s+)*"
    r"(?:"
    r"(?:[^\s;&|]*/)?pytest"
    r"|(?:[^\s;&|]*/)?python(?:3(?:\.\d+)?)?\s+-m\s+pytest"
    r")(?=\s|$)"
)
RERUN_TOKENS = ("--rerun-tasks", "--rerun", "cleanTest", "clean ")

REQUIRED_FIELDS = ("id", "goal", "persona", "exclusive_writes", "context_acquisition",
                   "validation", "stop_conditions", "commit_subject")
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

ERROR = "ERROR"
WARNING = "WARNING"


class CardError(Exception):
    """The card could not be read. Never raised for a card that is merely wrong."""


# --------------------------------------------------------------------------------------------- #
# YAML subset parser
# --------------------------------------------------------------------------------------------- #

def strip_comment(line: str) -> str:
    """Remove a trailing `#` comment, respecting quotes.

    A validation command legitimately contains `#` inside its quoted string
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
        self.by_simple_name: dict[str, list[str]] = {}
        for path in self.files:
            m = SOURCE_ROOT_RE.match(path)
            if not m:
                continue
            fqcn = m.group("pkg").replace("/", ".")
            self.classes.setdefault(fqcn, path)
            self.by_simple_name.setdefault(fqcn.rsplit(".", 1)[-1], []).append(path)

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
    construct (`validation:` split by module), so its keys are labels and only the leaves are
    yielded; the alternative — injecting `comms` into the path or command set — invents findings.
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
    """D. A card missing one of these cannot be dispatched."""
    resolved = dict(card)
    for old, new in DEPRECATED_ALIASES.items():
        if old in card:
            f.add(WARNING, old,
                  f"`{old}` is the former name of `{new}` — rename the field; it is still accepted "
                  "so that a card already in flight does not hard-fail")
            resolved.setdefault(new, card[old])
    for field in REQUIRED_FIELDS:
        if field not in resolved:
            f.add(ERROR, field, "required field is missing")
        elif (not as_list(resolved[field])
              or not any(str(v).strip() for v in as_list(resolved[field]))):
            f.add(ERROR, field, "required field is present but empty")
    persona = str(resolved.get("persona", "")).strip()
    if persona and persona not in VALID_PERSONAS:
        f.add(ERROR, "persona", f"must be one of {' | '.join(VALID_PERSONAS)}, got {persona!r}")


def check_obsolete_fields(card: dict[str, object], f: Findings) -> None:
    """D'. Fields the card no longer has. Never an error — an old card still runs."""
    for field, why in OBSOLETE_FIELDS.items():
        if field in card:
            f.add(WARNING, field,
                  f"`{field}` is no longer part of the card and is ignored — {why}. Delete it.")


def check_validation_tests(card: dict[str, object], repo: Repo, f: Findings) -> None:
    """A. The headline check: every `--tests` filter must resolve to a real class.

    Gradle treats a `--tests` pattern that matches nothing in the target source set as satisfied
    when other patterns on the same command do match, so a typo'd or wrong-module FQCN produces
    BUILD SUCCESSFUL having run zero of the tests the card claims prove it.
    """
    for command in as_list(card.get("validation")):
        for m in TESTS_FILTER_RE.finditer(command):
            raw = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            fqcn = raw.split("#", 1)[0].split("::", 1)[0]
            if not fqcn:
                continue
            if "*" in fqcn or "?" in fqcn:
                f.add(WARNING, "validation",
                      f"{raw} is a wildcard filter; existence cannot be verified — "
                      "prefer an exact class so a typo cannot pass silently")
                continue
            lookup = fqcn.replace("$", ".")
            if lookup in repo.classes:
                continue
            # An outer class named with a nested-class suffix still resolves.
            outer = ".".join(lookup.split(".")[:-1])
            if outer in repo.classes and lookup.split(".")[-1][:1].isupper():
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


def check_pytest_selectors(card: dict[str, object], repo: Repo,
                           writes: list[PathSpec], f: Findings) -> None:
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

    for command in as_list(card.get("validation")):
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = list(lexer)
        except ValueError as exc:
            if PYTEST_INVOCATION_RE.search(command):
                f.add(ERROR, "validation",
                      f"cannot parse command invoking pytest: {exc}")
            elif ".py::" in command:
                f.add(ERROR, "validation",
                      f"cannot parse command containing a pytest selector: {exc}")
            continue
        controls = frozenset((";", "&&", "||", "|"))
        segments: list[list[str]] = [[]]
        for token in tokens:
            if token in controls:
                segments.append([])
            else:
                segments[-1].append(token)

        pytest_segments: list[tuple[list[str], int]] = []
        for segment in segments:
            for i, token in enumerate(segment):
                if token == "pytest" or token.rsplit("/", 1)[-1] == "pytest":
                    pytest_segments.append((segment, i))
        if pytest_segments:
            selector_tokens = []
            for segment, pytest_index in pytest_segments:
                arguments = segment[pytest_index + 1:]
                response_files = [token for token in arguments if token.startswith("@")]
                for token in response_files:
                    f.add(ERROR, "validation",
                          f"{token} is a pytest response-file argument; response files are "
                          "unsupported and are not opened or expanded")
                dynamic = [token for token in arguments if "$" in token or "`" in token]
                for token in dynamic:
                    f.add(ERROR, "validation",
                          f"{token} is a dynamic pytest selector argument; shell expansion is "
                          "unsupported, so use an exact path/to/test_file.py::test_name")
                selector_tokens.extend(token for token in arguments
                                       if "::" in token and token not in dynamic)
        else:
            selector_tokens = []

        for selector in selector_tokens:
            match = PYTEST_SELECTOR_RE.fullmatch(selector)
            if not match or any(part in (".", "..") for part in selector.split("::", 1)[0].split("/")):
                f.add(ERROR, "validation",
                      f"{selector} is an unsupported pytest selector; use exactly "
                      "path/to/test_file.py::test_name")
                continue

            path = match.group("path")
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

            declaration = declarations.get(selector, set())
            if "Retain" in declaration:
                f.add(ERROR, "tests",
                      f"Retain {selector} does not exist as a top-level test function")
            elif "Create" in declaration:
                if any(spec.covers(path) for spec in writes):
                    f.add(WARNING, "tests",
                          f"Create {selector} is still absent; permitted before implementation "
                          "because its file is covered by exclusive_writes")
                else:
                    f.add(ERROR, "tests",
                          f"Create {selector} is outside exclusive_writes and cannot be satisfied")
            else:
                f.add(ERROR, "validation",
                      f"{selector} does not exist as a top-level test function and is not declared "
                      f"exactly as Retain {selector} or Create {selector}")


def path_to_fqcn(path: str) -> str:
    m = SOURCE_ROOT_RE.match(path)
    return m.group("pkg").replace("/", ".") if m else path


def check_validation_module_placement(card: dict[str, object], repo: Repo, f: Findings) -> None:
    """A'. A class that exists but lives outside the module whose test task runs is the same
    silent-green failure wearing a different hat: it is not on that source set, so the filter
    matches nothing."""
    for command in as_list(card.get("validation")):
        modules = {m.group(1) for m in GRADLE_TASK_RE.finditer(command) if m.group(1)}
        if len(modules) != 1:
            continue
        module = modules.pop()
        module_dir = repo.module_dir(module)
        if not module_dir:
            continue
        for m in TESTS_FILTER_RE.finditer(command):
            raw = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            fqcn = raw.split("#", 1)[0].replace("$", ".")
            path = repo.classes.get(fqcn)
            if path and not path.startswith(module_dir + "/"):
                f.add(WARNING, "validation",
                      f"{fqcn} lives in {repo.module_label(path)} but the command runs :{module}:test; "
                      "a filter that names no class in the target source set matches nothing")


def check_validation_cacheable(card: dict[str, object], repo: Repo,
                               writes: list[PathSpec], f: Findings) -> None:
    """B. A Gradle test command with no rerun can report UP-TO-DATE, BUILD SUCCESSFUL, zero tests.

    Severity depends on whether the task can dirty the module at all. If the module is inside
    `exclusive_writes` the task's own edits will normally invalidate the cache, so this is a
    WARNING. If the command verifies a module the task is not permitted to write, nothing can
    invalidate it and the line is structurally incapable of running — that is an ERROR.
    """
    for command in as_list(card.get("validation")):
        if "gradlew" not in command and "gradle " not in command:
            continue
        tasks = list(GRADLE_TASK_RE.finditer(command))
        if not tasks:
            continue
        if any(token in command for token in RERUN_TOKENS):
            continue
        modules = sorted({m.group(1) for m in tasks if m.group(1)})
        label = ", ".join(f":{m}" for m in modules) or "the root project"
        untouchable = []
        for module in modules:
            module_dir = repo.module_dir(module)
            if module_dir and not any(spec.touches_dir(module_dir) for spec in writes):
                untouchable.append(module)
        if untouchable:
            f.add(ERROR, "validation",
                  f"{', '.join(':' + m for m in untouchable)} test task has neither --rerun-tasks "
                  "nor cleanTest, and exclusive_writes cannot dirty that module — the task will be "
                  "UP-TO-DATE and report BUILD SUCCESSFUL without executing a test")
        else:
            f.add(WARNING, "validation",
                  f"{label} test task has neither --rerun-tasks nor cleanTest; if the task's edits "
                  "do not invalidate it, it can report BUILD SUCCESSFUL having run nothing")


def check_gate_risk_covered(card: dict[str, object], f: Findings) -> None:
    """Every artifact named in gate_risk should be exercised by a validation command."""
    commands = " ".join(as_list(card.get("validation")))
    # `verifyBackendTestTaxonomy` is the verifier for `test-taxonomy.tsv`; a literal filename match
    # would miss it and warn about an artifact the card already covers. Compare on alphanumerics.
    squashed = re.sub(r"[^a-z0-9]", "", commands.lower())
    for artifact in as_list(card.get("gate_risk")):
        name = artifact.strip()
        if not name or name.lower() in ("none", "n/a"):
            continue
        stem = Path(name).stem
        token = re.sub(r"[^a-z0-9]", "", stem.lower())
        if stem and token not in squashed and Path(name).name not in commands:
            f.add(WARNING, "gate_risk",
                  f"{name} is named as at risk but no validation command mentions it — "
                  "its cheap verifier is what stops this failing an hour into a full gate")


def check_path_coherence(card: dict[str, object], repo: Repo,
                         writes: list[PathSpec],
                         forbidden: list[PathSpec], f: Findings) -> None:
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
            f.add(WARNING, "forbidden_paths",
                  f"{spec.pattern} matches nothing in the tree — probably stale or a typo")
    for spec in writes:
        if not spec.matches:
            # NEVER an error: naming a file the task will create is the normal case.
            f.add(WARNING, "exclusive_writes",
                  f"{spec.pattern} matches nothing in the tree — fine if this task creates it, "
                  "stale otherwise")


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


def check_frozen_migration(card: dict[str, object], repo: Repo, f: Findings) -> None:
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
    if not mentioned:
        return
    # The version the card will CREATE is the one its exclusive_writes glob claims. frozen_values
    # legitimately mentions others — the current highest, or the stale number the plan used — so
    # taking the maximum mention as the intent misreads a card that is documenting its own
    # correction. Fall back to the maximum only when the write set names no migration.
    declared = {int(m.group(1))
                for pattern in as_list(card.get("exclusive_writes"))
                for m in re.finditer(r"(?:^|/)V(\d+)__", pattern)}
    intended = max(declared) if declared else max(mentioned)

    highest = repo.highest_migration()
    if highest is None:
        f.add(WARNING, "frozen_values",
              f"names migration V{intended} but no db/migration directory was found")
        return
    top, top_path = highest
    ahead = sorted(v for v in mentioned if v > intended)
    if ahead and declared:
        f.add(WARNING, "frozen_values",
              f"also names {', '.join('V' + str(v) for v in ahead)}, above the V{intended} this "
              "card creates — confirm that is a documented correction and not a stale plan value")
    if intended <= top:
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


# --------------------------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------------------------- #

def validate(card_path: Path, repo_root: Path) -> tuple[dict[str, object], Repo, Findings]:
    card = parse_card(card_path.read_text(encoding="utf-8"), card_path.name)
    repo = Repo(repo_root)
    f = Findings()

    writes = specs_for(card, "exclusive_writes", repo)
    forbidden = specs_for(card, "forbidden_paths", repo)

    check_validation_tests(card, repo, f)
    check_pytest_selectors(card, repo, writes, f)
    check_validation_module_placement(card, repo, f)
    check_validation_cacheable(card, repo, writes, f)
    check_path_coherence(card, repo, writes, forbidden, f)
    check_write_set_satisfiable(card, repo, writes, f)
    check_required_fields(card, f)
    check_obsolete_fields(card, f)
    check_frozen_migration(card, repo, f)
    check_gate_risk_covered(card, f)
    check_context_acquisition(card, f)
    return card, repo, f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", help="path to the task card YAML")
    ap.add_argument("--repo", required=True, help="repository the card will be executed in")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings as well as errors")
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
        card, repo, findings = validate(card_path, repo_root)
    except CardError as e:
        print(f"  ERROR   {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"cannot read: {e}", file=sys.stderr)
        return 2

    card_id = str(card.get("id") or card_path.stem)
    if not args.quiet:
        print(f"card {card_id}: {len(card)} field(s) parsed, "
              f"{len(repo.files)} file(s) indexed in {repo_root.name}")
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
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
