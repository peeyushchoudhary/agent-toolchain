from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hermetic import reaches_home


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


promoter = load_module("promote_lesson_test", SCRIPTS / "promote_lesson.py")


FLEET_HEADER = """# Fleet lessons

Corrections that hold in every project.

## Entry schema

Four fields.

---

"""


def fleet_entry(title: str) -> str:
    return (
        f"## {title}\n\n"
        "**Scope:** universal\n"
        "**Learned:** Believed one thing. Actually another.\n"
        "**Cost:** Two gate runs.\n"
        "**Enforced by:** a test.\n\n"
    )


class SweepHarness(unittest.TestCase):
    """Synthetic lessons trees under a temp dir. Never a real project."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "fleet"
        self.root.mkdir()
        self.fleet_lessons = self.tmp / "fleet-lessons.md"
        self.fleet_lessons.write_text(FLEET_HEADER, encoding="utf-8")

    def tearDown(self) -> None:
        for path in self.tmp.rglob("*"):
            try:
                if path.is_file():
                    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        self._tmp.cleanup()

    def make_project(self, name: str, lessons: str | None, *, routed: bool = True) -> Path:
        project = self.root / name
        (project / ".git").mkdir(parents=True)
        if routed:
            agents = project / "docs" / "agents"
            agents.mkdir(parents=True)
            if lessons is not None:
                (agents / "lessons.md").write_text(lessons, encoding="utf-8")
        return project

    def set_fleet_entries(self, *titles: str) -> None:
        self.fleet_lessons.write_text(
            FLEET_HEADER + "".join(fleet_entry(t) for t in titles), encoding="utf-8"
        )

    def run_sweep(self) -> tuple[int, str]:
        out = io.StringIO()
        code = promoter.sweep(self.root, self.fleet_lessons, out=out)
        return code, out.getvalue()


FLAT_NO_SCOPE = """# Lessons

Durable corrections learned the expensive way.

## Tooling that works in your shell but not in scripts

**Believed:** a command that resolves interactively is available to scripts.

**Actually:** `rg` is a shell function, not a binary.

## A filtered e2e run on a fresh database proves less than it appears to

**Believed:** a filter reproduces the full gate.

**Actually true:** a focused run starts empty.

## Never launch the release gate under a detach wrapper

Ignored signal dispositions are inherited across fork and exec.
"""

ROUTED_NO_SCOPE = """<!-- progressive-disclosure standard v1.0 -->
# Route lessons

Things that misled an agent working in this repository.

## How to append

Newest first, two lines each.

```
### YYYY-MM-DD — short title
**Misleading:** what the docs implied.
**Actual:** what turned out to be true.
```

## Lessons

### 2026-07-27 — per-area coverage cannot find a cross-area defect
**Misleading:** each test covered its own area thoroughly.
**Actual:** nothing anywhere spanned the two areas.

### 2026-07-26 — know which claim your evidence supports
**Misleading:** three fixtures agreed.
**Actual:** they shared one author's premise.

### Older lessons
Entries from earlier live in the archive.
"""


class HonestEmptyTest(SweepHarness):
    def test_entries_without_scope_markers_are_reported_as_unclassified_with_counts(
        self,
    ) -> None:
        self.make_project("alpha", FLAT_NO_SCOPE)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        # The counts are the point: three entries were parsed, and the zero in the
        # candidates column cannot be mistaken for a file that was never read.
        self.assertRegex(
            text,
            r"alpha\s+docs/agents/lessons\.md\s+entries\s+3\s+universal\s+0\s+unclassified\s+3"
            r"\s+other-scope\s+0\s+candidates\s+0",
        )
        self.assertIn("entries parsed 3", text)
        self.assertIn("unclassified 3", text)
        self.assertIn("unclassified - entries carrying no `Scope` field at all: 3", text)
        self.assertIn("Tooling that works in your shell but not in scripts", text)
        self.assertIn("proposed promotions: 0", text)
        self.assertIn("listed 3 unclassified", text)

    def test_a_truly_empty_fleet_says_zero_entries_were_parsed(self) -> None:
        self.make_project("alpha", "# Lessons\n\nNothing yet.\n")

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("entries parsed 0", text)
        self.assertIn("Zero entries were parsed", text)

    def test_a_well_formed_file_with_an_empty_lessons_section_is_empty_not_malformed(
        self,
    ) -> None:
        # The real fleet has two of these. Reporting them as MALFORMED would
        # manufacture a finding against a file that is doing nothing wrong.
        self.make_project(
            "alpha",
            "<!-- progressive-disclosure standard v1.0 -->\n# Route lessons\n\n"
            "## How to append\n\nNewest first.\n\n## Lessons\n",
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("files this sweep could not fully parse: 0", text)
        self.assertIn("files read and well formed but holding no lessons yet: 1", text)
        self.assertIn("EMPTY", text)
        self.assertIn("nothing recorded yet", text)
        self.assertNotIn("MALFORMED", text)

    def test_routed_standard_shape_parses_h3_entries_and_skips_scaffolding(self) -> None:
        self.make_project("beta", ROUTED_NO_SCOPE)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("entries parsed 2", text)
        # `## How to append`, `## Lessons` and `### Older lessons` are structure.
        self.assertNotIn("How to append", text)
        self.assertNotIn("Older lessons", text)
        # The fenced template under "How to append" is an example, not an entry.
        self.assertNotIn("short title", text)
        self.assertIn("2026-07-27 — per-area coverage cannot find a cross-area defect", text)


class ProposalTest(SweepHarness):
    UNIVERSAL = (
        "# Lessons\n\n"
        "## A tool that resolves in your shell may not exist to a script\n\n"
        "**Scope:** universal\n"
        "**Learned:** Believed an interactive command is on a script's PATH. "
        "Actually it can be a shell function.\n"
        "**Cost:** Two gate failures.\n\n"
    )

    def test_a_universal_entry_absent_from_the_fleet_file_is_proposed(self) -> None:
        self.make_project("alpha", self.UNIVERSAL)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("proposed promotions: 1", text)
        self.assertIn("## A tool that resolves in your shell may not exist to a script", text)
        self.assertIn("**Scope:** universal", text)
        self.assertIn("**Learned:** Believed an interactive command", text)
        self.assertIn("**Cost:** Two gate failures.", text)
        # The field that matters is always emitted, always for a human to fill in.
        self.assertIn("**Enforced by:** TODO", text)
        self.assertIn("lessons.md:3", text)
        self.assertRegex(text, r"alpha\s+docs/agents/lessons\.md\s+entries\s+1\s+universal\s+1\s+unclassified\s+0"
                               r"\s+other-scope\s+0\s+candidates\s+1")

    def test_an_entry_without_learned_or_cost_still_proposes_every_field(self) -> None:
        self.make_project(
            "alpha",
            "# Lessons\n\n## Detach wrappers are inputs to the test\n\n"
            "**Scope:** universal\n\n"
            "Ignored dispositions are inherited across fork and exec.\n",
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("**Learned:** TODO", text)
        self.assertIn("**Cost:** TODO", text)
        self.assertIn("**Enforced by:** TODO", text)

    def test_the_same_entry_is_not_proposed_once_the_fleet_file_carries_it(self) -> None:
        self.make_project("alpha", self.UNIVERSAL)
        self.set_fleet_entries(
            "1. A tool that resolves in your shell may not exist to a script"
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("proposed promotions: 0", text)
        self.assertIn("already in the fleet file, not proposed again: 1", text)
        self.assertRegex(text, r"alpha\s+docs/agents/lessons\.md\s+entries\s+1\s+universal\s+1\s+unclassified\s+0"
                               r"\s+other-scope\s+0\s+candidates\s+0")

    def test_a_near_match_is_held_back_separately_rather_than_collapsed(self) -> None:
        self.make_project(
            "alpha",
            "# Lessons\n\n## Tooling that works in your shell but not in scripts\n\n"
            "**Scope:** universal\n**Cost:** one gate run.\n",
        )
        self.set_fleet_entries(
            "1. A tool that resolves in your shell may not exist to a script"
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("near-matches held back for a human decision: 1", text)
        self.assertIn("proposed promotions: 0", text)
        self.assertIn("already in the fleet file, not proposed again: 0", text)
        self.assertIn("held back 1 near-match", text)
        # And the limit of title matching is stated rather than implied.
        self.assertIn("Deduplication is by title only", text)

    def test_a_non_universal_scope_is_neither_proposed_nor_called_unclassified(
        self,
    ) -> None:
        self.make_project(
            "alpha",
            "# Lessons\n\n## Our gradle module boundaries\n\n**Scope:** project\n",
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertRegex(text, r"alpha\s+docs/agents/lessons\.md\s+entries\s+1\s+universal\s+0\s+unclassified\s+0"
                               r"\s+other-scope\s+1\s+candidates\s+0")
        self.assertIn("proposed promotions: 0", text)
        self.assertIn("no `Scope` field at all: 0", text)


class DegradeHonestlyTest(SweepHarness):
    GOOD = (
        "# Lessons\n\n## A universal correction\n\n"
        "**Scope:** universal\n**Cost:** one gate run.\n"
    )

    def test_missing_unreadable_and_malformed_files_are_named_and_the_sweep_continues(
        self,
    ) -> None:
        self.make_project("a-missing", None)
        unreadable = self.make_project("b-unreadable", "# Lessons\n\n## X\n\n**Scope:** universal\n")
        (unreadable / "docs" / "agents" / "lessons.md").chmod(0o000)
        self.make_project("c-malformed", "no headings at all, just prose\n")
        self.make_project("d-scaffolding", "# Route lessons\n\n## How to append\n\nrules\n")
        self.make_project("e-good", self.GOOD)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("MISSING: no docs/agents/lessons.md", text)
        self.assertIn("UNREADABLE", text)
        self.assertIn("b-unreadable", text)
        self.assertIn("no markdown headings found", text)
        self.assertIn("every one of them is scaffolding", text)
        self.assertIn("files this sweep could not fully parse: 4", text)
        self.assertIn("none was skipped in silence", text)
        # The sweep did not abort: the good project after them was still swept.
        self.assertIn("proposed promotions: 1", text)
        self.assertIn("## A universal correction", text)

    def test_an_unrecognised_scope_value_is_reported_and_not_proposed(self) -> None:
        self.make_project(
            "alpha", "# Lessons\n\n## Odd one\n\n**Scope:** everywhere-ish\n"
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("unrecognised Scope value", text)
        self.assertIn("not proposed", text)
        self.assertIn("proposed promotions: 0", text)

    def test_a_git_repo_without_a_route_is_reported_not_silently_dropped(self) -> None:
        self.make_project("unrouted", None, routed=False)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("NOT-ROUTED: no docs/agents route", text)

    def test_a_directory_that_is_not_a_project_is_counted_as_skipped(self) -> None:
        (self.root / "scratch").mkdir()
        self.make_project("alpha", self.GOOD)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("skipped 1 director", text)
        self.assertIn("scratch", text)


ARCHIVE_POINTER = """<!-- progressive-disclosure standard v1.0 -->
# Route lessons

## Lessons

### 2026-07-28 — a live entry
**Misleading:** one thing.
**Actual:** another.

### Older lessons
Entries from 2026-07-26 and earlier live in [lessons-archive.md](lessons-archive.md).
"""

# The real archive shape, reduced: an h1 title that does NOT normalise to
# "lessons", h3 entries, and no `## Lessons` wrapper anywhere.
ARCHIVE_SHARD = """# Route lessons — archive

Entries from 2026-07-26 and earlier.

### 2026-07-26 — when you narrow a guard, enumerate what still runs inside it
**Misleading:** narrowing a guard narrows only what it blocks.
**Actual:** it also narrows what it checks.

### 2026-07-26 — a controller that writes then re-reads returns its own stale write
**Misleading:** a re-read sees the write.
**Actual:** it sees the cache.

### 2026-07-26 — a results directory can fabricate a gate, two ways
**Misleading:** a results file means the gate ran.
**Actual:** a stale file means nothing ran.
"""


class ShardedLessonsTest(SweepHarness):
    """A project whose lessons live in more than one file.

    `lessons.md` says 'entries from 2026-07-26 and earlier live in
    lessons-archive.md'. Reading only `lessons.md` followed that pointer to a file
    it never opened, discarded the pointer heading as scaffolding, and printed a
    count that omitted every archived lesson -- silently, and in a tool whose stated
    purpose is that under-reporting must be visible.
    """

    def make_sharded(self, name: str) -> Path:
        project = self.make_project(name, ARCHIVE_POINTER)
        (project / "docs" / "agents" / "lessons-archive.md").write_text(
            ARCHIVE_SHARD, encoding="utf-8"
        )
        return project

    def test_an_archive_shard_beside_lessons_md_is_read_not_silently_skipped(self) -> None:
        self.make_sharded("alpha")

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        # One coverage row per shard, each naming the file it counted.
        self.assertRegex(text, r"alpha\s+docs/agents/lessons\.md\s+entries\s+1\b")
        self.assertRegex(text, r"alpha\s+docs/agents/lessons-archive\.md\s+entries\s+3\b")
        # 1 live + 3 archived. Reading lessons.md alone would have said 1.
        self.assertIn("lessons files read 2", text)
        self.assertIn("entries parsed 4", text)
        # One project, two files: the project count must not inflate with shards.
        self.assertIn("totals: projects 1,", text)
        # The relpath searched and the siblings found are both printed.
        self.assertIn("searched docs/agents/lessons*.md", text)
        self.assertIn("siblings: alpha keeps its lessons in 2 files", text)
        self.assertIn("lessons-archive.md", text)
        # And the archived entries are individually reachable, not just counted.
        self.assertIn("a controller that writes then re-reads returns its own stale write", text)

    def test_an_archive_shard_with_no_lessons_wrapper_is_parsed_not_called_malformed(
        self,
    ) -> None:
        # `# Route lessons — archive` normalises to "route lessons archive", not
        # "lessons", so nothing anchors the entry level. Falling back to h2 would
        # report a well formed file holding 3 lessons as MALFORMED -- turning a
        # silent miss into a false finding against a compliant project.
        self.make_project("alpha", ARCHIVE_SHARD)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertNotIn("MALFORMED", text)
        self.assertIn("files this sweep could not fully parse: 0", text)
        self.assertIn("entries parsed 3", text)

    def test_the_modal_fallback_still_prefers_a_real_lessons_anchor(self) -> None:
        # Modal counting alone would pick h3 here (3 headings) over the anchored
        # h2 rule; the anchor must still win, or `## How to append` stops being
        # scaffolding in files that do declare their shape.
        self.make_project("alpha", ROUTED_NO_SCOPE)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("entries parsed 2", text)
        self.assertNotIn("How to append", text)

    def test_a_multi_word_lessons_tail_is_a_different_document_and_is_not_swept(
        self,
    ) -> None:
        # The regex is deliberately tight, and the tightness is load-bearing: a
        # bare `lessons-*` prefix would swallow an ordinary guide and report its
        # section headings as lessons.
        project = self.make_project("alpha", "# Lessons\n\n## A real one\n\nbody\n")
        (project / "docs" / "agents" / "lessons-and-onboarding-guide.md").write_text(
            "# Onboarding\n\n## Step one\n\n## Step two\n", encoding="utf-8"
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("lessons files read 1", text)
        self.assertIn("entries parsed 1", text)
        self.assertNotIn("Step one", text)

    def test_a_project_with_no_lessons_file_of_any_name_is_still_reported_missing(
        self,
    ) -> None:
        self.make_project("alpha", None)

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("MISSING", text)
        self.assertIn("no docs/agents/lessons.md", text)


class EnforcedByMarkerTest(SweepHarness):
    def test_the_proposal_spells_the_marker_with_the_destinations_em_dash(self) -> None:
        # docs/fleet-lessons.md writes `none — prose only` with U+2014 in all four
        # occurrences, and says at :27 that those entries ARE the backlog. Telling a
        # human to write the ASCII-hyphen form -- while asserting the words are
        # exact -- hands them a string the backlog grep cannot find.
        self.make_project(
            "alpha", "# Lessons\n\n## A universal correction\n\n**Scope:** universal\n"
        )

        code, text = self.run_sweep()

        self.assertEqual(code, 0)
        self.assertIn("proposed promotions: 1", text)
        self.assertIn("`none — prose only`", text)
        self.assertNotIn("`none - prose only`", text)

    @reaches_home(
        "READS THE REAL MACHINE, deliberately: the claim under test is about the em dash in the "
        "INSTALLED ~/.claude/docs/fleet-lessons.md, and a fixture copy would only pin this test's "
        "memory of it. It already skips when the file is absent, which is what a replica sees.")
    def test_the_destination_file_really_spells_it_that_way(self) -> None:
        # Pins the claim above to the destination rather than to this test's
        # memory of it. Skipped, not failed, if the real file is not installed:
        # the fleet file is not this suite's fixture to depend on.
        destination = Path.home() / ".claude" / "docs" / "fleet-lessons.md"
        if not destination.is_file():
            self.skipTest("docs/fleet-lessons.md not installed")
        body = destination.read_text(encoding="utf-8")
        self.assertIn("none — prose only", body)


class ReadOnlyTest(unittest.TestCase):
    SOURCE = (SCRIPTS / "promote_lesson.py").read_text(encoding="utf-8")

    def test_the_source_contains_no_write_primitive_at_all(self) -> None:
        # This list IS the read-only guarantee. It was previously an enumeration of
        # the write calls someone thought of, and an enumeration is only ever as
        # good as its author's imagination: it named `.mkdir(` but not `makedirs`,
        # and `os.remove` but not bare `os`, so three lines
        # (`import os` / `os.makedirs(project / ".sweep-cache", exist_ok=True)`)
        # wrote a directory into every swept project with the suite still green.
        #
        # So it now forbids the MODULES, not the calls. `os` and `tempfile` are the
        # two gateways to a filesystem write that `pathlib` does not cover, this
        # module imports neither, and the whole program needs neither -- so the rule
        # costs nothing today and fails loudly the day someone adds one, whatever
        # call they reach for through it.
        forbidden = [
            r"\bos\b",                     # includes makedirs, mkdir, open, remove...
            r"\btempfile\b",
            r"\bshutil\b",
            r"\bsubprocess\b",
            # Bare `open(` outright, not just a write-mode one. The old pattern
            # `open\([^)]*['"][rbt]*[wax]` cannot cross a `)`, so `open(str(p), "w")`
            # slipped straight through it. This module reads via `Path.read_text`
            # and never needs `open` in any mode, so no mode-sniffing is required.
            r"\bopen\(",
            r"\.write_text\(",
            r"\.write_bytes\(",
            r"\.mkdir\(",
            r"\.makedirs\(",
            r"\.unlink\(",
            r"\.rmdir\(",
            r"\.rename\(",
            r"\.replace\(\s*[A-Za-z_]*[Pp]ath",   # Path.replace is a rename
            r"\.touch\(",
            r"\.chmod\(",
            r"\.symlink_to\(",
            r"""['"]git['" ]""",           # no git command is ever invoked
            r"add_argument\([^)]*apply",   # no --apply flag is ever offered
        ]
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                found = [
                    line
                    for line in self.SOURCE.splitlines()
                    if re.search(pattern, line) and not line.lstrip().startswith("#")
                ]
                self.assertEqual(found, [], f"write primitive {pattern} in source")

    def test_a_sweep_mutates_nothing_under_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fleet"
            agents = root / "alpha" / "docs" / "agents"
            agents.mkdir(parents=True)
            lessons = agents / "lessons.md"
            lessons.write_text(
                "# Lessons\n\n## A universal correction\n\n**Scope:** universal\n",
                encoding="utf-8",
            )
            fleet_lessons = Path(tmp) / "fleet-lessons.md"
            fleet_lessons.write_text(FLEET_HEADER, encoding="utf-8")

            before = fingerprint(root) + [fingerprint_one(fleet_lessons)]
            promoter.sweep(root, fleet_lessons, out=io.StringIO())
            after = fingerprint(root) + [fingerprint_one(fleet_lessons)]

            self.assertEqual(before, after)


def fingerprint_one(path: Path) -> tuple:
    """One entry's identity: what it is, and for a file, its exact bytes.

    Directories are fingerprinted too, and that is the whole point. The first
    version filtered `if p.is_file()`, which made a CREATED DIRECTORY invisible:
    `os.makedirs(project / ".sweep-cache", exist_ok=True)` wrote into every swept
    project and this assertion still passed. Leading the tuple with a kind also
    catches a file replaced by a directory of the same name, which a bytes-only
    comparison would raise on rather than report.
    """
    info = path.lstat()
    if path.is_symlink():
        return (str(path), "symlink", os.readlink(path), info.st_mtime_ns)
    if path.is_dir():
        # A directory's mtime moves the moment a child is created inside it, so
        # this catches the creation even before the child itself is listed.
        return (str(path), "dir", None, info.st_mtime_ns)
    return (str(path), "file", path.read_bytes(), info.st_mtime_ns)


def fingerprint(root: Path) -> list[tuple]:
    """EVERY entry under root - files, directories, symlinks, hidden or not.

    `rglob("*")` does list dot-entries; what dropped them before was the
    `is_file()` filter, not the glob.
    """
    return [fingerprint_one(p) for p in sorted(root.rglob("*"))]


class CommandLineTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        """HOME IS PINNED TO AN EMPTY DIRECTORY, and that is what these cases are about.

        `promote_lesson.py`'s two defaults are `~/Documents/Claude/Projects` and
        `~/.claude/docs/fleet-lessons.md`, so the argument-handling cases below — no arguments, a
        bad flag, `--help` — were answering against whatever fleet happened to exist on the machine
        running them. None of them asserts anything about a fleet, so redirecting HOME does not
        change what any of them verifies; it removes a dependency they never wanted. The cases that
        DO need a tree pass `--sweep` and `--fleet-lessons` explicitly and are unaffected.
        """
        empty_home = Path(tempfile.mkdtemp(prefix="pd-promote-home-"))
        self.addCleanup(shutil.rmtree, empty_home, True)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "promote_lesson.py"), *args],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "HOME": str(empty_home)},
        )

    def test_help_exits_zero(self) -> None:
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--sweep", result.stdout)
        # No --apply option is offered; the help text may say so in prose.
        self.assertIsNone(re.search(r"^\s+--apply\b", result.stdout, re.M))
        self.assertIn("deliberately no `--apply`", result.stdout)

    def test_no_arguments_is_a_usage_error(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("There is no --apply", result.stderr)

    def test_an_apply_flag_does_not_exist(self) -> None:
        result = self.run_script("--apply")
        self.assertEqual(result.returncode, 2)

    def test_a_missing_root_is_an_environment_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script("--sweep", str(Path(tmp) / "nope"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("fleet root is not a directory", result.stderr)

    def test_a_missing_fleet_lessons_file_is_an_environment_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(
                "--sweep", tmp, "--fleet-lessons", str(Path(tmp) / "nope.md")
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("fleet lessons file not found", result.stderr)

    def test_finding_a_candidate_still_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agents = Path(tmp) / "fleet" / "alpha" / "docs" / "agents"
            agents.mkdir(parents=True)
            (agents / "lessons.md").write_text(
                "# Lessons\n\n## A universal correction\n\n**Scope:** universal\n",
                encoding="utf-8",
            )
            fleet_lessons = Path(tmp) / "fleet-lessons.md"
            fleet_lessons.write_text(FLEET_HEADER, encoding="utf-8")

            result = self.run_script(
                "--sweep", str(Path(tmp) / "fleet"),
                "--fleet-lessons", str(fleet_lessons),
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("proposed promotions: 1", result.stdout)


class TitleNormalisationTest(unittest.TestCase):
    def test_numbering_dates_and_markup_do_not_defeat_deduplication(self) -> None:
        same = [
            "1. Read the gate's own verdict line",
            "Read the gate's own verdict line",
            "2026-07-27 — Read the gate's own verdict line",
            "Read the gate's **own** `verdict` line",
        ]
        keys = {promoter.normalise_title(t) for t in same}
        self.assertEqual(len(keys), 1, keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
