#!/usr/bin/env python3
"""Tests for milestone_seal.py — the evidence a milestone seal is gated on.

Run: python3 -m unittest tests.test_milestone_seal   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

Every behaviour is exercised in BOTH directions, because a one-sided test on an evidence checker is
worth almost nothing: a `verify` that returns 1 unconditionally passes every block-side assertion
and gates nothing, and a `verify` that returns 0 unconditionally passes every pass-side assertion
and gates nothing either. The pairs below are what separate the two.

The receipt directory is redirected with `XDG_STATE_HOME` in every test, so nothing here reads or
writes the state of the machine it runs on, and a developer's real receipts can neither satisfy nor
fail an assertion.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "milestone_seal.py"

sys.path.insert(0, str(SCRIPTS))

import milestone_seal  # noqa: E402  — the path insertion above has to happen first

MILESTONE = """---
milestone: M1
title: Launch
status: building
updated: 2026-01-01
---

# M1 — Launch

## Why now
Two features are only useful together.

## Cross-feature validation
The journeys no single feature's suite can prove.
Gate: sh gate.sh
"""


class SealFixture(unittest.TestCase):
    """A real git repository, a real gate script, and a receipt directory of our own."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state"
        self.root = self.tmp / "repo"
        (self.root / "docs" / "product" / "milestones").mkdir(parents=True)
        self.git("init", "-q", "-b", "feature")
        self.git("config", "user.email", "seal@example.invalid")
        self.git("config", "user.name", "seal")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True,
                              check=True).stdout

    def write(self, relative: str, text: str, *, executable: bool = False) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def commit(self, message: str = "c") -> None:
        self.git("add", ".")
        self.git("commit", "-qm", message)

    def milestone(self, text: str = MILESTONE, *, gate_exit: int = 0) -> None:
        self.write("docs/product/milestones/M1-launch.md", text)
        self.write("gate.sh", f"#!/bin/sh\nexit {gate_exit}\n", executable=True)
        self.commit("milestone")

    def env(self) -> dict:
        # HOME is pinned as well as XDG_STATE_HOME: the fallback inside `receipt_dir` is
        # `Path.home()`, so a test that pinned only the variable it expects to be read would still
        # reach the real machine on the day someone changes which one wins.
        return {**os.environ, "XDG_STATE_HOME": str(self.state), "HOME": str(self.tmp / "home"),
                "PYTHONDONTWRITEBYTECODE": "1"}

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=self.env())

    def tree(self) -> str:
        return self.git("rev-parse", "HEAD^{tree}").strip()

    def receipts(self) -> list[Path]:
        directory = self.state / "execution-methodology" / "milestone-seals"
        return sorted(directory.glob("*.json")) if directory.is_dir() else []


class GateDeclarationTest(SealFixture):
    """Which line is the gate, and which line is prose that happens to look like one."""

    def test_a_declared_gate_is_read_from_the_named_section(self) -> None:
        self.assertEqual(milestone_seal.gate_command(MILESTONE), "sh gate.sh")

    def test_a_gate_line_outside_the_section_is_not_a_gate(self) -> None:
        """The pass-side half. A `Gate:` under some other heading is prose, and reading it would
        execute a command nobody declared."""
        text = MILESTONE.replace("## Cross-feature validation", "## Notes")
        self.assertIsNone(milestone_seal.gate_command(text))

    def test_a_section_with_no_gate_line_declares_nothing(self) -> None:
        text = MILESTONE.replace("Gate: sh gate.sh", "Still being decided.")
        self.assertIsNone(milestone_seal.gate_command(text))

    def test_the_last_gate_line_in_the_section_wins(self) -> None:
        text = MILESTONE.replace("Gate: sh gate.sh",
                                 "It used to be `Gate: sh old.sh`.\nGate: sh gate.sh")
        self.assertEqual(milestone_seal.gate_command(text), "sh gate.sh")

    def test_a_later_section_closes_the_gate_section(self) -> None:
        text = MILESTONE + "\n## Off-repo blockers\nGate: rm -rf /\n"
        self.assertEqual(milestone_seal.gate_command(text), "sh gate.sh")

    def test_gate_prints_the_command_and_exits_zero(self) -> None:
        self.milestone()
        result = self.run_cli("--gate", "M1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "sh gate.sh")

    def test_a_milestone_with_no_gate_cannot_be_recorded(self) -> None:
        """Exit 2, not 1. "It has no gate" is not "its gate failed": the remedy is an edit to the
        document, and reporting it as a failure sends the operator to re-run nothing."""
        self.milestone(MILESTONE.replace("Gate: sh gate.sh", "Undecided."))
        result = self.run_cli("--record", "M1")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Cross-feature validation", result.stderr)
        self.assertEqual(self.receipts(), [])


class RecordTest(SealFixture):
    """A receipt exists if and only if the gate ran and passed against a committed tree."""

    def test_a_passing_gate_writes_a_receipt_naming_the_tree(self) -> None:
        self.milestone(gate_exit=0)
        result = self.run_cli("--record", "M1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        written = self.receipts()
        self.assertEqual(len(written), 1, result.stdout)
        receipt = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["tree"], self.tree())
        self.assertEqual(receipt["command"], "sh gate.sh")
        self.assertEqual(receipt["exit"], 0)

    def test_a_failing_gate_writes_nothing(self) -> None:
        """The block-side twin of the test above, and the one that matters: a recorder that wrote
        the receipt first and checked the exit status afterwards would pass every other test here
        while certifying failures."""
        self.milestone(gate_exit=3)
        result = self.run_cli("--record", "M1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.receipts(), [])

    def test_the_receipt_is_written_outside_the_repository(self) -> None:
        """Not merely git-ignored. A receipt that can travel in a clone lets one machine's run seal
        another machine's push, and it is one `git add -f` from being committed."""
        self.milestone()
        self.assertEqual(self.run_cli("--record", "M1").returncode, 0)
        written = self.receipts()[0].resolve()
        self.assertFalse(str(written).startswith(str(self.root.resolve())), written)
        self.assertEqual(self.git("status", "--porcelain").strip(), "")

    def test_a_dirty_worktree_is_refused(self) -> None:
        """HEAD's tree describes what is COMMITTED. With an uncommitted edit the command runs
        against content the tree sha does not name, so the receipt would certify something that was
        never tested."""
        self.milestone()
        self.write("gate.sh", "#!/bin/sh\nexit 0\n# edited\n", executable=True)
        result = self.run_cli("--record", "M1")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not clean", result.stderr)
        self.assertEqual(self.receipts(), [])

    def test_an_absent_milestone_document_is_not_a_pass(self) -> None:
        self.milestone()
        result = self.run_cli("--record", "M9")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(self.receipts(), [])

    def test_two_documents_claiming_one_id_are_refused_rather_than_guessed(self) -> None:
        self.milestone()
        self.write("docs/product/milestones/M1-launch-old.md", MILESTONE)
        self.commit("a second M1")
        result = self.run_cli("--record", "M1")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("claim M1", result.stderr)

    def test_a_milestone_id_that_is_not_M_number_is_rejected(self) -> None:
        self.milestone()
        result = self.run_cli("--record", "1")
        self.assertEqual(result.returncode, 2, result.stdout)


class VerifyTest(SealFixture):
    """What `verify` accepts, and the four ways a receipt fails to answer the question asked."""

    def record(self) -> str:
        self.milestone()
        self.assertEqual(self.run_cli("--record", "M1").returncode, 0)
        return self.tree()

    def verify(self, tree: str, command: str = "sh gate.sh") -> subprocess.CompletedProcess:
        return self.run_cli("--verify", "--tree", tree, "--command", command)

    def test_a_recorded_pass_verifies(self) -> None:
        self.assertEqual(self.verify(self.record()).returncode, 0)

    def test_no_receipt_at_all_does_not_verify(self) -> None:
        self.milestone()
        result = self.verify(self.tree())
        self.assertEqual(result.returncode, 1)
        self.assertIn("no gate receipt", result.stdout)

    def test_a_receipt_for_another_tree_does_not_verify(self) -> None:
        """The stale-receipt case, which is the whole reason the tree names the file. Recorded, then
        one character changes, and the evidence stops applying."""
        self.record()
        self.write("gate.sh", "#!/bin/sh\nexit 0\n# a real edit\n", executable=True)
        self.commit("edit")
        result = self.verify(self.tree())
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_a_receipt_for_another_command_does_not_verify(self) -> None:
        self.assertEqual(self.verify(self.record(), "sh other.sh").returncode, 1)

    def test_a_receipt_whose_body_disagrees_with_its_name_does_not_verify(self) -> None:
        """The filename holds a 12-hex-digit digest, which is a lookup key and not a proof. A
        `verify` that trusted the name would accept this."""
        tree = self.record()
        path = self.receipts()[0]
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["command"] = "sh something-else.sh"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(self.verify(tree).returncode, 1)

    def test_a_receipt_recording_a_nonzero_exit_does_not_verify(self) -> None:
        tree = self.record()
        path = self.receipts()[0]
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["exit"] = 1
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(self.verify(tree).returncode, 1)

    def test_an_unreadable_receipt_is_exit_2_and_never_exit_1(self) -> None:
        """"There is no valid receipt" and "I could not find out" are different sentences. The
        first sends the operator to run the gate; the second would send them to run it pointlessly."""
        tree = self.record()
        self.receipts()[0].write_text("{ not json", encoding="utf-8")
        result = self.verify(tree)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_verify_needs_both_a_tree_and_a_command(self) -> None:
        self.assertEqual(self.run_cli("--verify", "--tree", "abc").returncode, 2)


if __name__ == "__main__":
    unittest.main()
