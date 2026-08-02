#!/usr/bin/env python3
"""Propose project lessons for promotion into the fleet lessons file.

    promote_lesson.py --sweep [DIR]     # read the fleet, propose on stdout
    promote_lesson.py --help

READ-ONLY, ABSOLUTELY. This script walks project repositories that are read-only
by founder decision. It opens nothing for writing, creates no branch, and runs no
git command at all. `--sweep` prints a proposal on stdout; a human reads it and
decides. There is deliberately no `--apply`.

Why it exists: a lesson recorded in one project and unreachable from another has
not been learned, it has been filed. Three of the first five entries in
`~/.claude/docs/fleet-lessons.md` were already written down in a project's
`docs/agents/lessons.md`, and were rediscovered at full cost anyway.

What it reports, and why the shape matters:

  * candidates    -- entries marked `Scope: universal` that fleet-lessons.md does
                     not already carry, rendered in the destination's own schema.
  * near-matches  -- an entry whose title closely resembles a fleet entry's. That
                     is a judgement call, so it is held out of the proposals and
                     shown separately rather than silently collapsed.
  * unclassified  -- entries carrying NO `Scope` field at all. No project lessons
                     file carries a Scope marker today, so a sweep matching only
                     an explicit marker would print nothing, and printing nothing
                     must never be indistinguishable from finding nothing (that
                     is fleet lesson 4). These are shown with counts, clearly
                     labelled as NOT candidates.
  * coverage      -- files read, entries parsed, candidates found, per file. A
                     zero-entry parse can then never read as a zero-candidate
                     fleet. One row per lessons SHARD, not per project: a project
                     that archives its older entries into `lessons-archive.md` is
                     read whole, and the shards it holds are named.

Exit codes: 0 the sweep ran (proposals are not failures), 1 a usage or
environment error.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_FLEET_ROOT = Path.home() / "Documents" / "Claude" / "Projects"
DEFAULT_FLEET_LESSONS = Path.home() / ".claude" / "docs" / "fleet-lessons.md"

LESSONS_DIR = Path("docs") / "agents"

# A project's lessons are not always in one file. One project's `lessons.md` routes
# to `lessons-archive.md`, and the archive holds MORE entries than the
# live file (8 vs 4). Reading only `lessons.md` and following none of that pointer
# under-reported that project by two thirds, silently -- in a tool whose whole
# thesis is that under-reporting must be visible.
#
# This regex is `validate_disclosure.py:89`'s `LESSONS_NAME`, adopted verbatim
# rather than re-derived, so one skill has one answer to "is this a lessons file".
# Its tightness is deliberate and documented there: `lessons.md`, or `lessons` plus
# one separator plus a single unbroken token (`lessons-archive.md`,
# `lessons_2026.md`). A multi-word tail (`lessons-and-onboarding-guide.md`) is a
# different document and is not swept.
LESSONS_NAME = re.compile(r"^lessons(?:[-_][a-z0-9]+)?\.md$")

# The default shard, named on its own so the "missing" message can point at it.
PRIMARY_LESSONS = "lessons.md"

# Headings that structure a lessons file without being lessons. Matched on the
# normalised title, so `## Lessons` and `### Older lessons` are scaffolding in
# every shape the fleet actually uses.
NON_ENTRY_TITLES = {
    "lessons",
    "route lessons",
    "fleet lessons",
    "how to append",
    "entry schema",
    "older lessons",
    "older entries",
    "archive",
}

# Titles differ in wording far more than they differ by accident. Measured on the
# real fleet: the closest genuine restatement of a fleet entry scored 0.72 and the
# loudest false neighbour scored 0.38, so anything in between is a human's call.
NEAR_MATCH_THRESHOLD = 0.70

FIELD_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*\*|__)?\s*(?P<name>[A-Za-z][A-Za-z ]{0,24}?)\s*"
    r"(?:\*\*|__)?\s*:\s*(?:\*\*|__)?\s*(?P<value>.*?)\s*(?:\*\*|__)?\s*$"
)
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(?P<fence>```+|~~~+)")
NUMBER_PREFIX_RE = re.compile(r"^\s*\d+[.)]\s+")
DATE_PREFIX_RE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s*[—–-]+\s*")

KNOWN_SCOPES = {"universal", "project", "local", "repo", "repository"}


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def is_lessons_file(name: str) -> bool:
    """Same predicate as `validate_disclosure.is_lessons_file`, same regex."""
    return bool(LESSONS_NAME.match(name.lower()))


def lessons_files(agents_dir: Path) -> list[Path]:
    """Every lessons shard in a project's route directory, `lessons.md` first.

    Sorted so the live file leads and archives follow in name order, which is the
    order a human reads them in.
    """
    try:
        found = [p for p in agents_dir.iterdir() if p.is_file() and is_lessons_file(p.name)]
    except OSError:
        return []
    return sorted(found, key=lambda p: (p.name.lower() != PRIMARY_LESSONS, p.name.lower()))


def normalise_title(title: str) -> str:
    """Comparable form of a heading: no numbering, no date prefix, no markup."""
    text = title.strip()
    text = NUMBER_PREFIX_RE.sub("", text)
    text = DATE_PREFIX_RE.sub("", text)
    text = text.replace("`", " ").replace("*", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return " ".join(text.split())


@dataclass
class Entry:
    title: str
    line: int
    level: int
    body: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return normalise_title(self.title)

    @property
    def scope(self) -> str | None:
        raw = self.fields.get("scope")
        if raw is None:
            return None
        cleaned = re.sub(r"[^a-z0-9 -]+", " ", raw.lower()).strip()
        return cleaned.split()[0] if cleaned.split() else ""

    def field_text(self, name: str) -> str | None:
        return self.fields.get(name)


@dataclass
class Heading:
    level: int
    title: str
    line: int


def scan_headings(lines: Sequence[str]) -> list[Heading]:
    """Headings outside fenced code. A fenced template is an example, not an entry."""
    headings: list[Heading] = []
    fence: str | None = None
    for number, raw in enumerate(lines, start=1):
        opened = FENCE_RE.match(raw)
        if fence is not None:
            if opened and raw.strip().startswith(fence):
                fence = None
            continue
        if opened:
            fence = opened.group("fence")[0] * 3
            continue
        matched = HEADING_RE.match(raw)
        if matched:
            headings.append(
                Heading(len(matched.group("hashes")), matched.group("title"), number)
            )
    return headings


def entry_level(headings: Sequence[Heading]) -> tuple[int, bool]:
    """Which heading level holds the lessons in this file's shape, and whether
    that level was anchored on a real `Lessons` heading rather than assumed.

    Two shapes carry an explicit anchor and both are handled by one rule: find the
    deepest heading titled exactly "lessons" and take the level below it. In the
    flat shape that heading is the `# Lessons` document title, so entries are h2.
    In the routed-standard shape it is a `## Lessons` section under a `# Route
    lessons` title, so entries are h3 and `## How to append` is not an entry.

    A third shape has no anchor at all: an archive shard is `# Route lessons —
    archive` with h3 entries and no `## Lessons` wrapper. Assuming h2 there reports
    a perfectly well formed file holding 8 lessons as MALFORMED. So when nothing
    anchors, take the level used most often, ties broken toward the deeper level --
    the same modal rule `validate_disclosure.lessons_entry_count` uses, for the same
    reason: a wrapper is always shallower and rarer than the entries it wraps.

    The two rules disagree about scaffolding on purpose, and the disagreement is
    the point of this tool. `validate_disclosure` counts headings at the modal
    level, so `### Older lessons` counts as an entry (it reports 5 for that
    project's `docs/agents/lessons.md`); this tool then drops NON_ENTRY_TITLES and
    reports 4, because it has to render each survivor as a promotable lesson and a
    pointer heading is not one. 5 is an upper bound on accretion; 4 is the count of
    lessons. Neither is wrong; they answer different questions.
    """
    candidates = [h for h in headings if normalise_title(h.title) == "lessons"]
    if candidates:
        return max(h.level for h in candidates) + 1, True
    levels: dict[int, int] = {}
    for head in headings:
        levels[head.level] = levels.get(head.level, 0) + 1
    if not levels:
        return 2, False
    return max(levels.items(), key=lambda kv: (kv[1], kv[0]))[0], False


def parse_entries(text: str) -> tuple[list[Entry], list[tuple[str, str]]]:
    """Return (entries, complaints).

    A complaint is (kind, text): `malformed` for a shape this parser does not
    recognise, `empty` for a file that is perfectly well formed and simply has no
    lessons in it yet. Conflating the two would report an empty file as broken and
    a broken file as empty, and both readings are wrong in the same direction.
    """
    complaints: list[tuple[str, str]] = []
    lines = text.splitlines()
    headings = scan_headings(lines)
    if not headings:
        return [], [("malformed", "no markdown headings found")]

    level, anchored = entry_level(headings)
    starts = [h for h in headings if h.level == level]
    if not starts:
        kind = "empty" if anchored else "malformed"
        detail = (
            f"the Lessons section holds no level-{level} entries - nothing recorded yet"
            if anchored
            else f"no level-{level} entry headings under this file's shape "
            f"(headings seen: {sorted({h.level for h in headings})})"
        )
        return [], [(kind, detail)]

    boundaries = {h.line for h in headings if h.level <= level}
    entries: list[Entry] = []
    for head in starts:
        if normalise_title(head.title) in NON_ENTRY_TITLES:
            continue
        body: list[str] = []
        for number in range(head.line + 1, len(lines) + 1):
            if number in boundaries:
                break
            body.append(lines[number - 1])
        entry = Entry(title=head.title.strip(), line=head.line, level=level, body=body)
        entry.fields = parse_fields(body)
        entries.append(entry)

    if not entries:
        complaints.append(
            (
                "empty" if anchored else "malformed",
                "headings found but every one of them is scaffolding",
            )
        )
    return entries, complaints


def parse_fields(body: Sequence[str]) -> dict[str, str]:
    """Field lines an entry carries: `**Scope:** universal`, `Cost: ...`, etc."""
    found: dict[str, str] = {}
    fence: str | None = None
    for raw in body:
        opened = FENCE_RE.match(raw)
        if fence is not None:
            if opened and raw.strip().startswith(fence):
                fence = None
            continue
        if opened:
            fence = opened.group("fence")[0] * 3
            continue
        matched = FIELD_RE.match(raw)
        if not matched:
            continue
        name = " ".join(matched.group("name").lower().split())
        if name and name not in found:
            found[name] = matched.group("value").strip()
    return found


# --------------------------------------------------------------------------
# fleet lessons (the deduplication source)
# --------------------------------------------------------------------------


def read_text(path: Path) -> str:
    """The only file access in this program, and it is read-only by construction."""
    return path.read_text(encoding="utf-8", errors="replace")


def load_fleet_titles(path: Path) -> list[tuple[str, str]]:
    text = read_text(path)
    lines = text.splitlines()
    titles: list[tuple[str, str]] = []
    for head in scan_headings(lines):
        if head.level != 2:
            continue
        key = normalise_title(head.title)
        if not key or key in NON_ENTRY_TITLES:
            continue
        titles.append((head.title.strip(), key))
    return titles


# --------------------------------------------------------------------------
# sweep
# --------------------------------------------------------------------------


@dataclass
class FileReport:
    project: str
    path: Path
    relpath: str = ""  # the shard's path inside its project, for the coverage row
    state: str = "read"  # read | missing | unreadable | not-routed
    detail: str = ""
    entries: int = 0
    universal: int = 0
    unclassified: int = 0
    other_scope: int = 0
    candidates: int = 0
    complaints: list[tuple[str, str]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.project}  {self.relpath}" if self.relpath else self.project

    @property
    def malformed(self) -> list[str]:
        return [text for kind, text in self.complaints if kind == "malformed"]

    @property
    def empty(self) -> list[str]:
        return [text for kind, text in self.complaints if kind == "empty"]


@dataclass
class Finding:
    project: str
    path: Path
    entry: Entry


def discover_projects(root: Path) -> tuple[list[Path], list[Path]]:
    """(projects, skipped). A project has a routed docs/agents or a git dir."""
    projects: list[Path] = []
    skipped: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        routed = (child / "docs" / "agents").is_dir()
        versioned = (child / ".git").exists()
        (projects if (routed or versioned) else skipped).append(child)
    return projects, skipped


def sweep(root: Path, fleet_lessons: Path, out=sys.stdout) -> int:
    say = lambda text="": print(text, file=out)  # noqa: E731

    try:
        fleet_titles = load_fleet_titles(fleet_lessons)
    except OSError as exc:  # the dedup source is not optional: fail loudly
        print(f"ERROR cannot read fleet lessons {fleet_lessons}: {exc}", file=sys.stderr)
        return 1

    say(f"lesson sweep: {root}")
    say("  read-only: this sweep opens nothing for writing and proposes on stdout only.")
    say(f"  fleet lessons: {fleet_lessons} ({len(fleet_titles)} entries)")
    say()

    projects, skipped = discover_projects(root)

    reports: list[FileReport] = []
    candidates: list[Finding] = []
    near: list[tuple[Finding, str, float]] = []
    present: list[tuple[Finding, str]] = []
    unclassified: list[Finding] = []

    shards: dict[str, list[str]] = {}

    for project in projects:
        agents = project / LESSONS_DIR
        if not agents.is_dir():
            reports.append(
                FileReport(
                    project=project.name,
                    path=project / LESSONS_DIR,
                    state="not-routed",
                    detail=f"no {LESSONS_DIR.as_posix()} route",
                )
            )
            continue

        found = lessons_files(agents)
        if not found:
            reports.append(
                FileReport(
                    project=project.name,
                    path=agents / PRIMARY_LESSONS,
                    relpath=(LESSONS_DIR / PRIMARY_LESSONS).as_posix(),
                    state="missing",
                    detail=f"no {(LESSONS_DIR / PRIMARY_LESSONS).as_posix()} and no "
                    f"{(LESSONS_DIR / 'lessons-*.md').as_posix()} shard beside it",
                )
            )
            continue
        shards[project.name] = [p.name for p in found]

        for path in found:
            report = FileReport(
                project=project.name,
                path=path,
                relpath=(LESSONS_DIR / path.name).as_posix(),
            )
            try:
                text = read_text(path)
            except OSError as exc:
                report.state = "unreadable"
                report.detail = str(exc)
                reports.append(report)
                continue

            entries, complaints = parse_entries(text)
            report.entries = len(entries)
            report.complaints = complaints

            for entry in entries:
                finding = Finding(project=project.name, path=path, entry=entry)
                scope = entry.scope
                if scope is None:
                    report.unclassified += 1
                    unclassified.append(finding)
                    continue
                if scope not in KNOWN_SCOPES:
                    report.other_scope += 1
                    report.complaints.append(
                        (
                            "malformed",
                            f"line {entry.line}: unrecognised Scope value "
                            f"{entry.fields.get('scope')!r} - not proposed",
                        )
                    )
                    continue
                if scope != "universal":
                    report.other_scope += 1
                    continue
                report.universal += 1
                exact = next((t for t, k in fleet_titles if k == entry.key), None)
                if exact is not None:
                    present.append((finding, exact))
                    continue
                best_title, best_score = closest(entry.key, fleet_titles)
                if best_title is not None and best_score >= NEAR_MATCH_THRESHOLD:
                    near.append((finding, best_title, best_score))
                    continue
                report.candidates += 1
                candidates.append(finding)
            reports.append(report)

    render_coverage(say, reports, skipped, len(projects), shards)
    render_problems(say, reports)
    render_candidates(say, candidates)
    render_near(say, near)
    render_present(say, present)
    render_unclassified(say, unclassified, fleet_titles)
    render_verdict(say, reports, candidates, near, unclassified)
    return 0


def closest(key: str, fleet_titles: Sequence[tuple[str, str]]) -> tuple[str | None, float]:
    best_title: str | None = None
    best_score = 0.0
    for title, other in fleet_titles:
        score = difflib.SequenceMatcher(None, key, other).ratio()
        if score > best_score:
            best_title, best_score = title, score
    return best_title, best_score


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_coverage(
    say,
    reports: Sequence[FileReport],
    skipped: Sequence[Path],
    project_count: int,
    shards: dict[str, list[str]] | None = None,
) -> None:
    shards = shards or {}
    say("coverage")
    say(
        f"  searched {(LESSONS_DIR / 'lessons*.md').as_posix()} in every project "
        f"- name pattern {LESSONS_NAME.pattern} - so an archive shard"
    )
    say("  (lessons-archive.md, lessons_2026.md) is read, not silently skipped.")
    if not reports:
        say("  (no projects found under this root)")
    width = max([len(r.label) for r in reports], default=10)
    for report in reports:
        if report.state == "read":
            say(
                f"  {report.label.ljust(width)}  entries {report.entries:>3}"
                f"  universal {report.universal:>3}"
                f"  unclassified {report.unclassified:>3}"
                f"  other-scope {report.other_scope:>3}"
                f"  candidates {report.candidates:>3}"
            )
        else:
            say(f"  {report.label.ljust(width)}  {report.state.upper()}: {report.detail}")
    multi = {name: names for name, names in shards.items() if len(names) > 1}
    if multi:
        for name in sorted(multi):
            say(
                f"  siblings: {name} keeps its lessons in {len(multi[name])} files "
                f"- {', '.join(multi[name])}"
            )
    else:
        say("  siblings: no project keeps a second lessons*.md file beside lessons.md.")
    read = [r for r in reports if r.state == "read"]
    say(
        f"  totals: projects {project_count}, lessons files read {len(read)}, "
        f"entries parsed {sum(r.entries for r in read)}, "
        f"universal {sum(r.universal for r in read)}, "
        f"unclassified {sum(r.unclassified for r in read)}, "
        f"candidates {sum(r.candidates for r in read)}"
    )
    if skipped:
        say(
            f"  skipped {len(skipped)} director(ies) with neither a git dir nor a "
            f"docs/agents route: {', '.join(p.name for p in skipped)}"
        )
    say()


def render_problems(say, reports: Sequence[FileReport]) -> None:
    problems = [
        r for r in reports if r.state in {"missing", "unreadable"} or r.malformed
    ]
    say(f"files this sweep could not fully parse: {len(problems)}")
    for report in problems:
        if report.state != "read":
            say(f"  {report.state.upper()}  {report.path}  ({report.detail})")
        for complaint in report.malformed:
            say(f"  MALFORMED  {report.path}  ({complaint})")
    if not problems:
        say("  (none)")
    say("  each is named and the sweep continued; none was skipped in silence.")
    say()

    empty = [r for r in reports if r.empty]
    say(f"files read and well formed but holding no lessons yet: {len(empty)}")
    for report in empty:
        for complaint in report.empty:
            say(f"  EMPTY  {report.path}  ({complaint})")
    if not empty:
        say("  (none)")
    say("  These are not broken. An empty lessons file is a project that has not")
    say("  recorded a correction yet, and it is reported so it cannot be confused")
    say("  with a file this sweep failed to understand.")
    say()


def propose(finding: Finding) -> list[str]:
    """Render one proposal in the destination file's own four-field schema."""
    entry = finding.entry
    lines = [f"## {entry.title}", ""]
    lines.append("**Scope:** universal")
    learned = entry.field_text("learned")
    if learned:
        lines.append(f"**Learned:** {learned}")
    else:
        believed = entry.field_text("believed") or entry.field_text("misleading")
        actual = (
            entry.field_text("actually true")
            or entry.field_text("actually")
            or entry.field_text("actual")
        )
        if believed or actual:
            lines.append(
                f"**Learned:** Believed {believed or 'TODO'} "
                f"Actually {actual or 'TODO'}"
            )
        else:
            lines.append(
                "**Learned:** TODO - what was believed, and what was actually true. "
                "Both halves; the source entry states them as prose, see below."
            )
    cost = entry.field_text("cost")
    lines.append(
        f"**Cost:** {cost}" if cost else
        "**Cost:** TODO - gate runs, outages, hours. Not inferable from the source entry."
    )
    # The destination spells this marker with a U+2014 em dash in all four of its
    # occurrences, and fleet-lessons.md:27 says the `none — prose only` entries ARE
    # the backlog. Telling a human to write the ASCII-hyphen form would hand them a
    # string that a future grep for the backlog marker cannot match -- while
    # asserting the words are exact. Copy the destination's spelling, byte for byte.
    lines.append(
        "**Enforced by:** TODO - the test, validator, hook or linter that makes "
        "recurrence impossible; or `none — prose only`, in exactly those words "
        "and with that em dash, which is how docs/fleet-lessons.md spells it."
    )
    lines.append("")
    lines.append(f"<!-- source: {finding.path}:{entry.line} ({finding.project}) -->")
    return lines


def render_candidates(say, candidates: Sequence[Finding]) -> None:
    say(f"proposed promotions: {len(candidates)}")
    if not candidates:
        say("  (none - no entry is marked `Scope: universal` and absent from the fleet file)")
        say()
        return
    say("  Copy into docs/fleet-lessons.md by hand. This sweep writes nothing.")
    say()
    for finding in candidates:
        say(f"  --- from {finding.project}: {finding.path}:{finding.entry.line}")
        for line in propose(finding):
            say(f"  {line}" if line else "")
        say()


def render_near(say, near: Sequence[tuple[Finding, str, float]]) -> None:
    say(f"near-matches held back for a human decision: {len(near)}")
    for finding, title, score in near:
        say(
            f"  {finding.project}: {finding.entry.title!r} "
            f"~{score:.2f} vs fleet {title!r}"
        )
        say(f"    {finding.path}:{finding.entry.line}")
    if not near:
        say("  (none)")
    say("  Not proposed and not treated as duplicates - same lesson or not is your call.")
    say()


def render_present(say, present: Sequence[tuple[Finding, str]]) -> None:
    say(f"already in the fleet file, not proposed again: {len(present)}")
    for finding, title in present:
        say(f"  {finding.project}: {finding.entry.title!r} == fleet {title!r}")
    if not present:
        say("  (none)")
    say()


def render_unclassified(
    say, unclassified: Sequence[Finding], fleet_titles: Sequence[tuple[str, str]]
) -> None:
    say(f"unclassified - entries carrying no `Scope` field at all: {len(unclassified)}")
    say("  NOT candidates. Shown because no project lessons file carries a Scope marker")
    say("  today, so a sweep matching only `Scope: universal` would print an empty page")
    say("  that reads exactly like a fleet with nothing to promote.")
    say()
    for finding in unclassified:
        title, score = closest(finding.entry.key, fleet_titles)
        note = ""
        if title is not None and score >= NEAR_MATCH_THRESHOLD:
            note = f"  [resembles fleet {title!r} ~{score:.2f}]"
        say(f"  {finding.project}: {finding.entry.title}{note}")
        say(f"    {finding.path}:{finding.entry.line}")
    if not unclassified:
        say("  (none)")
    say()


def render_verdict(
    say,
    reports: Sequence[FileReport],
    candidates: Sequence[Finding],
    near: Sequence[tuple[Finding, str, float]],
    unclassified: Sequence[Finding],
) -> None:
    read = [r for r in reports if r.state == "read"]
    parsed = sum(r.entries for r in read)
    say(
        f"verdict: read {len(read)} lessons file(s), parsed {parsed} entr(ies), "
        f"proposed {len(candidates)}, held back {len(near)} near-match(es), "
        f"listed {len(unclassified)} unclassified."
    )
    if parsed == 0:
        say(
            "  Zero entries were parsed. That is not the same as a fleet with nothing "
            "to promote - check the files named above before concluding anything."
        )
    say(
        "  Deduplication is by title only. A lesson rewritten under a different title "
        "will not be detected as a duplicate at all; near-matching narrows that gap, "
        "it does not close it."
    )
    say("  Nothing was written. No file under the fleet root was opened for writing.")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promote_lesson.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sweep",
        nargs="?",
        const=str(DEFAULT_FLEET_ROOT),
        default=None,
        metavar="DIR",
        help=f"walk every project under DIR (default {DEFAULT_FLEET_ROOT}) and "
        "propose promotions on stdout. Read-only.",
    )
    parser.add_argument(
        "--fleet-lessons",
        default=str(DEFAULT_FLEET_LESSONS),
        metavar="PATH",
        help=f"the promotion destination, read for deduplication only "
        f"(default {DEFAULT_FLEET_LESSONS})",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.sweep is None:
        parser.print_usage(sys.stderr)
        print(
            "promote_lesson.py: nothing to do. Pass --sweep [DIR]. "
            "There is no --apply: this tool proposes, a human decides.",
            file=sys.stderr,
        )
        return 1

    root = Path(args.sweep).expanduser()
    if not root.is_dir():
        print(f"ERROR fleet root is not a directory: {root}", file=sys.stderr)
        return 1
    fleet_lessons = Path(args.fleet_lessons).expanduser()
    if not fleet_lessons.is_file():
        print(
            f"ERROR fleet lessons file not found: {fleet_lessons} - without it "
            "nothing can be deduplicated, so the sweep would propose everything.",
            file=sys.stderr,
        )
        return 1

    return sweep(root.resolve(), fleet_lessons.resolve())


if __name__ == "__main__":
    sys.exit(main())
