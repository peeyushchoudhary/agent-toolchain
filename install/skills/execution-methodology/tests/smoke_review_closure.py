#!/usr/bin/env python3
"""End-to-end proof of the test-closed confirmation with the real cross-vendor judge (two judge calls).

  smoke_review_closure.py [--chief claude|codex] [--keep]

It builds a throwaway git repository holding a one-task goal whose code has one planted defect, and
runs a boundary review of the task: round 1 must BLOCK. It then applies the fix and a test that
reproduces the defect, and runs the rereview with --closed-by naming that test. It asserts that the
confirmation is recorded in rounds.json and in the verdict header without counting toward the cap,
and that the packet the judge received named the test. The judge comes from the other vendor than
--chief (default claude, so codex judges); when that vendor's CLI is not on PATH the tests skip and
say so. The summary line is unittest's, so gate.py counts it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import goal  # noqa: E402
import review  # noqa: E402

CHIEF = "claude"
KEEP = False
KEY = "T1-boundary"
TEST = "tests/test_divide.py::Divide.test_zero_divisor_returns_none"
SPEC = """# S-2 spec

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | `calc.divide(a, b)` returns `a / b`, and returns `None` instead of raising when `b` is 0 | unit tests |
"""
PLAN = """---
goal: S-2
title: Safe division, reviewed by the closure smoke run
spec: docs/spec.md
design: docs/design.md
gate: python3 -m unittest discover -s tests -t tests
full_gate: python3 -m unittest discover -s tests -t tests
e2e: python3 -m unittest discover -s tests -t tests
run: {network: true, session_hours: 1}
grants: [local-commit]
---

# S-2 plan

## M1 — safe division
criteria: AC-1
proofs:
- AC-1: full_gate

### [ ] T1 — divide
- writes: src/calc.py, tests/test_divide.py
- needs: —
- covers: AC-1
- risk: boundary
- builder: routine
- tests-may-change: —
Implement `divide(a, b)` in `src/calc.py` with its unit test.

## Decisions

## Queue
"""
DEFECT = "def divide(a, b):\n    return a / b\n"
FIX = "def divide(a, b):\n    if b == 0:\n        return None\n    return a / b\n"
TEST_BEFORE = """import sys, unittest
sys.path.insert(0, "src")
import calc


class Divide(unittest.TestCase):
    def test_divides(self):
        self.assertEqual(calc.divide(6, 3), 2)
"""
TEST_AFTER = TEST_BEFORE + """
    def test_zero_divisor_returns_none(self):  # reproduces round 1's finding: divide(1, 0) raised
        self.assertIsNone(calc.divide(1, 0))
"""


def fixture_git(root, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Smoke", "GIT_AUTHOR_EMAIL": "smoke@example.invalid",
           "GIT_COMMITTER_NAME": "Smoke", "GIT_COMMITTER_EMAIL": "smoke@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, env=env, check=True,
                   capture_output=True)


def build(root: Path):
    for rel, text in ((".gitignore", "/.runs/\n__pycache__/\n"), ("docs/spec.md", SPEC),
                      ("docs/design.md", "# design\n\n`divide` guards a zero divisor.\n"),
                      ("docs/plan.md", PLAN)):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    fixture_git(root, "init", "-q", "-b", "main")
    fixture_git(root, "add", "-A")
    fixture_git(root, "commit", "-qm", "S-2: approved goal")
    fixture_git(root, "tag", "goal/S-2/approved")
    # The task's work stays uncommitted, as in a real task review.
    (root / "src").mkdir()
    (root / "src/calc.py").write_text(DEFECT)
    (root / "tests").mkdir()
    (root / "tests/test_divide.py").write_text(TEST_BEFORE)


class Run:
    root: Path = None
    codes: list = []
    packets: list = []


def one_round(*extra):
    original = review.run_judge

    def recording(vendor, persona, variant, packet, root, timeout):
        Run.packets.append(packet)
        return original(vendor, persona, variant, packet, root, timeout)
    review.run_judge = recording
    args = review.parser().parse_args(["--kind", "boundary", "--task", "T1", "--chief", CHIEF,
                                       "--subject", "src/calc.py", "tests/test_divide.py", *extra])
    cwd = os.getcwd()
    os.chdir(Run.root)
    try:
        return review.review(args, goal.Ctx(Run.root, Run.root / "docs/plan.md"), timeout=900)
    finally:
        os.chdir(cwd)
        review.run_judge = original


def setup_run():
    Run.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="closure-smoke-")))
    build(Run.root)
    Run.codes.append(one_round())
    if Run.codes[0] != 1:
        return
    (Run.root / "src/calc.py").write_text(FIX)
    (Run.root / "tests/test_divide.py").write_text(TEST_AFTER)
    Run.codes.append(one_round("--closed-by", TEST))


class SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.judge = review.other(CHIEF)
        if not shutil.which(cls.judge):
            raise unittest.SkipTest(f"the {cls.judge} CLI is not on PATH; this proof needs the real "
                                    f"cross-vendor judge for a {CHIEF} chief")
        setup_run()

    def vdir(self):
        return Run.root / ".runs" / "S-2" / "verdicts"

    def test_round_1_blocks_on_the_planted_defect(self):
        self.assertEqual(Run.codes[0], 1, "round 1 must BLOCK: divide(1, 0) raises")
        verdict, _tree, head = goal.read_verdict(self.vdir() / "history" / f"{KEY}-r1.md")
        self.assertEqual((verdict, head.get("vendor")), ("BLOCK", self.judge))

    def test_the_confirmation_is_recorded_uncounted(self):
        self.assertEqual(len(Run.codes), 2, "the confirmation round did not run")
        self.assertIn(Run.codes[1], (0, 1), "the confirmation's judge call failed")
        rounds = goal.read_json(self.vdir() / "rounds.json")
        self.assertEqual(rounds, {KEY: 1, "confirmations": {KEY: 2}})
        verdict, _tree, head = goal.read_verdict(self.vdir() / f"{KEY}.md")
        self.assertIn(verdict, ("PASS", "BLOCK"))
        self.assertEqual((head["round"], head["confirmation"]), ("2", f"closed-by {TEST}"))
        self.assertTrue((Run.root / ".runs/S-2/review" / f"{KEY}-r2.files.json").is_file())

    def test_the_judge_saw_the_named_tests(self):
        self.assertEqual(len(Run.packets), 2)
        self.assertNotIn("test-closed confirmation", Run.packets[0])
        self.assertIn("test-closed confirmation", Run.packets[1])
        self.assertIn(TEST, Run.packets[1])
        self.assertIn("family: same as", Run.packets[1])


def main():
    global CHIEF, KEEP
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chief", choices=review.VENDORS, default=CHIEF)
    ap.add_argument("--keep", action="store_true", help="keep the fixture repository for inspection")
    a = ap.parse_args()
    CHIEF, KEEP = a.chief, a.keep
    os.environ.pop("GOAL_HARNESS", None)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SmokeTest))
    if Run.root is not None:
        print(f"smoke: fixture {Run.root} · round exits {Run.codes}", flush=True)
        if not KEEP and result.wasSuccessful():
            shutil.rmtree(Run.root, ignore_errors=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
