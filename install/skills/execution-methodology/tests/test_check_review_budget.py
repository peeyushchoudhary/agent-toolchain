#!/usr/bin/env python3
"""Tests for check_review_budget.py — the methodology v3.0 review-budget gate.

Run: python3 -m unittest tests.test_check_review_budget  (from the skill root)
  or python3 tests/test_check_review_budget.py
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_review_budget.py"


def run(workspace: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(workspace), "--json", *extra],
        capture_output=True, text=True,
    )


def findings(proc: subprocess.CompletedProcess) -> dict:
    return json.loads(proc.stdout)


class CheckReviewBudgetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, rel: str, content: str = "x\n"):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_clean_workspace_passes(self):
        self.touch("ledger.md")
        self.touch("cards/T1.yaml")
        self.touch("reviews/T1-review.md")
        self.touch("reviews/T1-r2-rereview.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = findings(proc)
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["warnings"], [])

    def test_round_three_is_refused(self):
        self.touch("reviews/T1-r3-rereview.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        kinds = {e["kind"] for e in findings(proc)["errors"]}
        self.assertIn("ROUND_CAP", kinds)

    def test_round_two_is_allowed(self):
        self.touch("reviews/T1-r2-rereview.md")
        self.assertEqual(run(self.ws).returncode, 0)

    def test_round_markers_group_under_one_subject(self):
        """r-, round-, fixround-, attempt- spellings of one artifact are one subject."""
        self.touch("reviews/T9-round4.md")
        self.touch("reviews/T9-fixround3.md")
        self.touch("reviews/T9-attempt5-rereview.md")
        errors = findings(run(self.ws))["errors"]
        cap = [e for e in errors if e["kind"] == "ROUND_CAP"]
        self.assertEqual(len(cap), 1, errors)
        self.assertEqual(cap[0]["round"], 5)

    def test_round_marker_in_any_filename_trips_the_cap(self):
        """A high round number is caught wherever it appears, whatever the surrounding name."""
        self.touch("reviews/M1-01-spotless-r15.yaml")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(cap[0]["round"], 15)

    def test_next_subject_with_spent_budget_is_refused_before_dispatch(self):
        """The pre-dispatch refusal: two rounds on record means the third is refused."""
        self.touch("reviews/T1-r1-review.md")
        self.touch("reviews/T1-r2-rereview.md")
        proc = run(self.ws, "--next", "T1")
        self.assertEqual(proc.returncode, 1)
        refused = [e for e in findings(proc)["errors"]
                   if e["kind"] == "ROUND_BUDGET_EXHAUSTED"]
        self.assertEqual(len(refused), 1, proc.stdout)
        self.assertEqual(refused[0]["subject"], "t1")

    def test_next_subject_with_budget_remaining_is_allowed(self):
        self.touch("reviews/T1-r1-review.md")
        self.assertEqual(run(self.ws, "--next", "T1").returncode, 0)
        self.assertEqual(run(self.ws, "--next", "T2").returncode, 0)

    def test_version_suffix_is_not_a_round(self):
        """v3, schema-v1 and similar version tokens are not review rounds."""
        self.touch("cards/v3-stage2-plan.md")
        self.touch("reports/schema-v1-notes.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_diff_snapshots_are_banned_in_every_spelling(self):
        for name in ("reports/T1-final.diff", "reports/T1.patch", "reports/T2.diff.txt"):
            self.touch(name)
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        banned = [e for e in findings(proc)["errors"] if e["kind"] == "BANNED_CLASS"]
        self.assertEqual(len(banned), 3, proc.stdout)

    def test_meta_artifacts_are_banned_in_every_spelling(self):
        for name in ("reports/T2-correction-packet.md", "reports/T2_correction_packet.md",
                     "reports/packet.md", "reviews/gate2-plan-review-invalid-attempt.md",
                     "reviews/T3-authority-review-no-verdict.md",
                     "reviews/T4-second-replacement-no-progress.md"):
            self.touch(name)
        errors = findings(run(self.ws))["errors"]
        self.assertEqual(len([e for e in errors if e["kind"] == "BANNED_CLASS"]), 6)

    def test_escalation_brief_is_permitted(self):
        """The founder-facing escalation brief is mandated by the methodology, not banned."""
        self.touch("reports/gate2-escalation-brief.md")
        self.assertEqual(run(self.ws).returncode, 0)

    def test_max_round_is_configurable(self):
        self.touch("reviews/T1-r3.md")
        self.assertEqual(run(self.ws, "--max-round", "3").returncode, 0)
        self.assertEqual(run(self.ws, "--max-round", "2").returncode, 1)

    def test_workspace_budget_warns_but_does_not_block(self):
        for i in range(60):
            self.touch(f"reports/T{i}-report.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0)
        data = findings(proc)
        self.assertEqual([w["kind"] for w in data["warnings"]], ["WORKSPACE_BUDGET"])

    def test_missing_workspace_is_a_usage_error(self):
        proc = run(self.ws / "nope")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
