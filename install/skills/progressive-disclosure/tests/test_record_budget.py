"""The record class: which accreting documents are exempt from the routed-guide word budget.

WHY THIS FILE EXISTS. `RECORD_NAME` has now been widened three times, each time by someone who had
just hit the wall with one particular file. The comment beside it says so. Nothing held the rule,
so each widening was a memory of the last one rather than a check on it.

WHAT IS ACTUALLY PINNED. Two behaviours a future editor can break without noticing:

  1. A routed record over the guide budget produces NO `over-budget` warning. That is the whole
     point of the class: a record grows because entries accrete, and the honest remedy for a full
     one is archiving old entries, not deleting true ones.
  2. A routed NON-record of the same size still warns. Without this half, "widen the class" and
     "delete the budget" look identical from the outside.

The word budget and the entry-count note are deliberately tested together, because the class trades
one for the other: dropping the budget without the note would make a record unbounded, and that was
never the deal.

Run: python3 skills/progressive-disclosure/tests/test_record_budget.py
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL / "scripts" / "validate_disclosure.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_disclosure_record_test", VALIDATOR)


def run(root: Path, *flags: str) -> tuple[int, str]:
    """The real CLI, with HOME redirected.

    `installed_methodology_version()` reads `~/.claude`, so a suite that left HOME alone would
    change its answer when an unrelated skill was installed on the machine running it.
    """
    home = Path(tempfile.mkdtemp(prefix="pd-record-home-"))
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(root), *flags],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return proc.returncode, proc.stdout + proc.stderr


class RecordNameTest(unittest.TestCase):
    """The names, unit level. Cheap, and it says which spellings are in the class."""

    ACCRETING = (
        "measurements.md", "benchmarks.md", "decisions.md", "adr.md", "rulings.md",
        "improvements.md", "changelog.md", "history.md",
    )

    def test_every_accreting_name_is_a_record(self):
        for name in self.ACCRETING:
            with self.subTest(name=name):
                self.assertTrue(validator.is_record_file(name))

    def test_one_suffix_is_allowed_so_a_record_can_be_sharded_by_topic(self):
        self.assertTrue(validator.is_record_file("improvements-weekly.md"))
        self.assertTrue(validator.is_record_file("decisions_2026.md"))

    def test_an_ordinary_guide_is_not_a_record(self):
        for name in ("onboarding-a-project.md", "operating-model.md", "readme.md",
                     "improvement.md", "the-changelog.md"):
            with self.subTest(name=name):
                self.assertFalse(validator.is_record_file(name))

    def test_matching_is_case_insensitive_on_the_caller_side(self):
        """`is_record_file` lowercases its argument, so `CHANGELOG.md` counts."""
        self.assertTrue(validator.is_record_file("CHANGELOG.md"))


class RecordBudgetTest(unittest.TestCase):
    """End to end, because the exemption is applied at a call site the unit test cannot see."""

    LONG = " ".join(["word"] * 2000)

    def repo(self, doc_name: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pd-record-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "AGENTS.md").write_text(
            f"# Fixture contract\n\n[index](docs/agents/README.md) [doc](docs/agents/{doc_name})\n",
            encoding="utf-8")
        (root / "docs" / "agents" / "README.md").write_text(
            '# Agents index\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n',
            encoding="utf-8")
        (root / "docs" / "agents" / doc_name).write_text(
            f"# Doc\n\n## One\n\n{self.LONG}\n", encoding="utf-8")
        return root

    def test_a_long_record_is_not_over_budget(self):
        rc, out = run(self.repo("improvements-weekly.md"))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("over-budget", out)

    def test_a_long_ordinary_guide_still_is(self):
        """The control. Without it, widening the class and removing the budget look the same."""
        rc, out = run(self.repo("improvement-notes.md"))
        self.assertIn("over-budget", out)

    def test_a_record_past_the_entry_threshold_is_still_observed(self):
        """No budget is not no limit: accretion is reported as an entry count."""
        root = Path(tempfile.mkdtemp(prefix="pd-record-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "AGENTS.md").write_text(
            "# Fixture contract\n\n[index](docs/agents/README.md) "
            "[rec](docs/agents/changelog.md)\n", encoding="utf-8")
        (root / "docs" / "agents" / "README.md").write_text(
            '# Agents index\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n',
            encoding="utf-8")
        entries = "".join(f"## Entry {i}\n\nbody\n\n"
                          for i in range(validator.LESSONS_ENTRY_NOTE_AT + 2))
        (root / "docs" / "agents" / "changelog.md").write_text(
            f"# Record\n\n{entries}", encoding="utf-8")
        rc, out = run(root)
        self.assertEqual(rc, 0, out)
        self.assertIn("record-entries", out)


class ThisRepositoryTest(unittest.TestCase):
    """The file the widening was made for, checked against the repository that ships it.

    A rule justified by one document and then not applied to it is the failure this class of edit
    keeps producing.
    """

    def test_the_weekly_improvement_record_is_recognised(self):
        # TWO LAYOUTS, ONE DOCUMENT. The repository that ships this skill moved its documents under
        # the shared structure standard, so the record now sits in `docs/product/`; the installed
        # layer still holds it flat. Both are listed because a single hardcoded path resolves in one
        # of them and SILENTLY SKIPS in the other — and this class exists precisely to stop a rule
        # from going unapplied to the document that justified it. A skip here would have been that
        # failure wearing an honest label.
        root = SKILL.parents[2]
        candidates = (root / "docs" / "product" / "improvements-weekly.md",
                      root / "docs" / "improvements-weekly.md")
        record = next((c for c in candidates if c.is_file()), None)
        if record is None:
            self.skipTest("vendored copy: the repository's docs/ is not present beside the skill")
        self.assertTrue(validator.is_record_file(record.name))


if __name__ == "__main__":
    unittest.main()
