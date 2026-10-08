"""The seam between the bytes that admit a --closed-by confirmation and the bytes a round records.

M1 acceptance round 1 found that comparison() read a named test before the round's snapshot was
taken, so a restore in between left both drift snapshots equal and consumed a confirmation for an
unchanged test. One snapshot now comes first: comparison() checks the test against it, record()
stores it, and the drift check compares the post-judge state with it. Stub judge only, no real CLI.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_closure import PASS, TASK, ClosureCase, review  # noqa: E402


class SnapshotSeamTest(ClosureCase):
    def setUp(self):
        super().setUp()
        self.change_test(n=1)  # the bytes round 1 records
        self.assertEqual(self.run_review(*TASK), 1)
        self.last = self.repo.read("tests/test_a.py")
        self.change_test(n=2)  # the correction: a changed test, so a confirmation is admissible
        self.reply = PASS

    def state(self):
        runs = self.ctx.runs
        paths = [*runs.glob("verdicts/*.md"), *runs.glob("verdicts/history/*"), *runs.glob("verdicts/rounds.json"),
                 *runs.glob("review/*.files.json")]
        return {str(q.relative_to(runs)): q.read_bytes() for q in paths}

    def restore(self):
        self.repo.write("tests/test_a.py", self.last)

    def assert_nothing_consumed(self, before):
        self.assertEqual(self.state(), before)  # no verdict, history, count, confirmation or digest
        self.assertEqual(self.rounds(), {"T1-boundary": 1})

    def test_a_restore_after_the_comparison_admits_it_is_drift_and_records_nothing(self):
        # The finding's trigger: comparison() accepts the changed test, then it is restored to its
        # last-round bytes. The snapshot was taken before the comparison, so it holds the changed
        # bytes; the restore shows up after the judge as drift (exit 2), not as a recorded round.
        real = review.closure_refusal

        def then_restore(*a, **kw):
            refusal = real(*a, **kw)
            if refusal is None:
                self.restore()
            return refusal
        before, calls = self.state(), len(self.packets)
        with mock.patch.object(review, "closure_refusal", then_restore):
            self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 2, self.out + self.err)
        self.assertIn("files changed while the judge ran; nothing recorded — rerun", self.err)
        self.assertEqual(len(self.packets), calls + 1)
        self.assert_nothing_consumed(before)
        # Now the test equals its last-round bytes, so the next try is refused, not admitted.
        self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="unchanged since round 1")

    def test_a_restore_between_the_snapshot_and_the_comparison_is_a_refusal(self):
        # The snapshot holds the changed bytes; the comparison then reads different bytes, so the
        # bytes that would admit the test are not the snapshot's: refused before admission (exit 1).
        real, calls = review.digests, []

        def then_restore(*a, **kw):
            files = real(*a, **kw)
            if not calls:
                self.restore()
            calls.append(1)
            return files
        with mock.patch.object(review, "digests", then_restore):
            self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="changed after this round's snapshot")
        self.assertEqual(self.rounds(), {"T1-boundary": 1})

    def test_controls_an_edit_after_the_snapshot_is_drift_and_no_edit_is_admitted(self):
        before, calls = self.state(), len(self.packets)
        self.during = lambda: self.change_test(n=3)  # edited while the judge runs
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 2)
        self.assertIn("files changed while the judge ran", self.err)
        self.assertEqual(len(self.packets), calls + 1)
        self.assert_nothing_consumed(before)
        self.during = None
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 0, self.out + self.err)
        self.assertEqual(self.rounds(), {"T1-boundary": 1, "confirmations": {"T1-boundary": 2}})


if __name__ == "__main__":
    unittest.main()
