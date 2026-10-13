"""This repository's own test-module map, docs/goals/modules.json (S-7 T8).

The map loads with no problems, covers every tracked file, and selects the modules that consume a
write; verify.sh --no-suites leaves its two unittest suites to the modules that run them.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "install" / "skills" / "execution-methodology" / "scripts"))
import modmap  # noqa: E402

ALL = ["modmap", "gate", "goal", "guard", "rules", "install", "repository"]


class RepositoryMapTest(unittest.TestCase):
    def setUp(self):
        self.map = modmap.load(REPO)

    def test_map_loads_with_no_problems(self):
        self.assertIsNotNone(self.map)
        self.assertEqual(modmap.problems(self.map), [])
        self.assertEqual(list(self.map["modules"]), ALL)
        self.assertEqual(self.map["replaces"], "cd install && ./install.sh --dry-run && ./verify.sh")

    def test_every_tracked_file_is_covered(self):
        files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                               check=True).stdout.splitlines()
        self.assertTrue(files)
        self.assertEqual(modmap.unmapped(self.map, files), [])

    def test_selection_includes_repository_and_docs_consumers(self):
        for write, want in (("install/tests/link_check.py", ["install", "repository"]),
                            ("install/skills/execution-methodology/scripts/docs.py", ["goal", "install", "repository"]),
                            ("AGENTS.md", ALL),
                            ("install/verify.sh", ["install", "repository"])):
            self.assertEqual(modmap.select(self.map, [write]), want, write)

    def test_no_suites_skips_both_run_suite_lines(self):
        text = (REPO / "install" / "verify.sh").read_text(encoding="utf-8")
        calls = [l for l in text.splitlines() if "run_suite " in l and not l.lstrip().startswith("#")]
        self.assertEqual(len(calls), 2, calls)
        for line in calls:
            self.assertRegex(line, r'\[ "\$SUITES" -eq 0 \] \|\| run_suite ', line)
        self.assertIn("--no-suites", text.split("set -uo pipefail", 1)[0], "the help text names the option")


if __name__ == "__main__":
    unittest.main()
