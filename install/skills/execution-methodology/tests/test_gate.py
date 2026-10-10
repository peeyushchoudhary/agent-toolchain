"""Tests for gate.py: count parsing, the failure rules, baselines and receipts.

Parsing is tested directly on canned runner output. The failure rules and receipts are tested by
running gate.py against a throwaway repository whose `emit.py` prints canned output chosen by an
environment variable, so one command string can pass, fail, or lie about its result.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import GATE, Repo  # noqa: E402

sys.path.insert(0, str(GATE.parent))
import gate  # noqa: E402

EMIT = "python3 emit.py"
KNOWN = "mod.Case.test_known"


class ParseTest(unittest.TestCase):
    def test_unittest_summaries_are_summed(self):
        out = ("Ran 4 tests in 0.1s\n\nOK (skipped=1)\n"
               "FAIL: test_known (mod.Case.test_known)\nRan 5 tests in 0.1s\n\n"
               "FAILED (failures=1, errors=1, skipped=2)\n")
        c = gate.parse_counts(out)
        self.assertEqual((c["executed"], c["failed"], c["skipped"]), (6, 2, 3))
        self.assertEqual(c["failures"], [KNOWN])

    def test_older_unittest_id_format(self):
        c = gate.parse_counts("ERROR: test_x (pkg.mod.Case)\nRan 1 test in 0.0s\n\nFAILED (errors=1)\n")
        self.assertEqual(c["failures"], ["pkg.mod.Case.test_x"])

    def test_stray_ok_line_before_a_summary_is_ignored(self):
        c = gate.parse_counts("OK\nRan 2 tests in 0.0s\n\nOK (skipped=1)\n")
        self.assertEqual((c["executed"], c["skipped"]), (1, 1))

    def test_pytest(self):
        out = ("FAILED tests/test_x.py::test_y - assert 1 == 2\n"
               "=========== 1 failed, 4 passed, 2 skipped in 0.31s ===========\n"
               "3 passed in 0.10s\n")
        c = gate.parse_counts(out)
        self.assertEqual((c["executed"], c["failed"], c["skipped"]), (8, 1, 2))
        self.assertEqual(c["failures"], ["tests/test_x.py::test_y"])

    def test_playwright(self):
        out = ("Running 6 tests using 1 worker\n\n"
               "  1 failed\n"
               "    [chromium] › e2e/a.spec.ts:3:1 › signs in ─────────────────────\n"
               "  1 flaky\n"
               "    [chromium] › e2e/b.spec.ts:9:1 › retries once ──────────────────\n"
               "  1 skipped\n"
               "  1 did not run\n"
               "  2 passed (4.9m)\n")
        c = gate.parse_counts(out)
        self.assertEqual((c["executed"], c["failed"], c["skipped"]), (4, 1, 2))
        self.assertEqual(c["failures"], ["[chromium] › e2e/a.spec.ts:3:1 › signs in"])

    def test_playwright_pass_line_needs_the_summary_shape(self):
        self.assertEqual(gate.parse_counts("  1 passed (4.9m)\n")["executed"], 1)
        for out in ("1 passed (4.9m)\n", "  3 passed, 1 failed\n",
                    "    2 passed (3s)\n", "  1 passed (a while)\n"):
            self.assertEqual(gate.parse_counts(out)["executed"], 0, out)

    def test_gradle(self):
        c = gate.parse_counts("FooTest > bar() FAILED\n12 tests completed, 2 failed, 1 skipped\n")
        self.assertEqual(c["gradle"], {"executed": 11, "failed": 2, "skipped": 1})
        self.assertEqual(c["failures"], ["FooTest.bar()"])

    def test_fail_verdict_lines_are_recognised_and_pass_output_is_not(self):
        for out in ("verify: FAIL (1 checks)", "FAIL: test_x", "  FAIL: lint (verify.checks)",
                    "FAILED tests/test_x.py::test_y", "result: FAILED"):
            self.assertTrue(gate.VERDICT_FAIL.search(f"Ran 1 test in 0.0s\n\nOK\n{out}\n"), out)
        for out in ("verify: PASS", "gate: PASS · exit 0 · 3 run / 0 failed / 0 skipped", "FAIL_FAST=1",
                    "FAIL: 0", "no FAIL here", "PASS: 3  FAIL: 0", "test_fail_lines ... ok", "OK (skipped=1)"):
            self.assertFalse(gate.VERDICT_FAIL.search(f"Ran 1 test in 0.0s\n\nOK\n{out}\n"), out)


class GateCase(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def check(self, cmd=EMIT, *args, mode="ok"):
        return self.repo.gate("check", "--goal", "F-9", "--cmd", cmd, *args, GATE_FIXTURE_MODE=mode)

    def receipt(self, cmd=EMIT, mode="ok", name="full_gate"):
        return self.repo.receipt(cmd, name, GATE_FIXTURE_MODE=mode)

    def receipts(self):
        d = self.repo.path(".runs/F-9/receipts")
        return [json.loads(p.read_text()) for p in d.glob("*.json")] if d.is_dir() else []

    def assertGate(self, res, verdict, reason=""):
        self.assertEqual(res.returncode, 0 if verdict == "PASS" else 1, res.stdout + res.stderr)
        self.assertIn(f"gate: {verdict}", res.stdout)
        self.assertIn(reason, res.stdout)


class CheckTest(GateCase):
    def test_pass_writes_log_and_no_receipt(self):
        self.assertGate(self.check(), "PASS", "3 run / 0 failed / 0 skipped")
        self.assertEqual(len(list(self.repo.path(".runs/F-9/logs").glob("*.log"))), 1)
        self.assertEqual(self.receipts(), [])

    def test_exit_zero_with_failure_verdict_fails(self):
        self.assertGate(self.check(mode="lie"), "FAIL", "exit/verdict mismatch")

    def test_zero_executed_fails_unless_declared(self):
        self.assertGate(self.check(mode="zero"), "FAIL", "zero tests executed")
        self.assertGate(self.check(EMIT, "--count", "none", mode="zero"), "PASS")

    def test_nonzero_exit_without_ids_fails(self):
        self.assertGate(self.check(mode="crash"), "FAIL", "nonzero exit 1")

    def test_baseline_failure_passes_and_new_failure_fails(self):
        self.assertGate(self.check(mode="base"), "FAIL", "failures not in baseline: " + KNOWN)
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", EMIT, GATE_FIXTURE_MODE="base")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertGate(self.check(mode="base"), "PASS", "(baseline 1)")
        self.assertGate(self.check(mode="new"), "FAIL", "failures not in baseline: mod.Case.test_new")
        self.assertGate(self.check(EMIT + " ", mode="base"), "FAIL", "not in baseline")

    def test_multi_suite_counts_with_baseline(self):
        self.repo.gate("baseline", "--goal", "F-9", "--cmd", EMIT, GATE_FIXTURE_MODE="base")
        self.assertGate(self.check(mode="two"), "PASS", "6 run / 1 failed / 3 skipped (baseline 1)")

    def test_gate_that_dirties_the_tree_fails(self):
        self.assertGate(self.check(EMIT + " && echo x >> docs/design.md"), "FAIL", "changed the working tree")
        self.repo.git("checkout", "docs/design.md")
        self.assertGate(self.check(EMIT + " && touch stray.txt"), "FAIL", "changed the working tree")

    def test_nonzero_exit_needs_the_baselines_exit_code(self):
        cmd = EMIT + "; rc=$?; exit ${GATE_EXIT:-$rc}"
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", cmd, GATE_FIXTURE_MODE="base")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(self.repo.read(".runs/F-9/baseline.json"))[gate.cmd_hash(cmd)]["exit"], 1)
        self.assertGate(self.check(cmd, mode="base"), "PASS", "(baseline 1)")
        res = self.repo.gate("check", "--goal", "F-9", "--cmd", cmd, GATE_FIXTURE_MODE="base", GATE_EXIT="127")
        self.assertGate(res, "FAIL", "nonzero exit 127 is not explained by the baseline (exit 1)")

    def test_baseline_without_a_recorded_exit_does_not_explain_a_nonzero_exit(self):
        self.repo.write(".runs/F-9/baseline.json", json.dumps({gate.cmd_hash(EMIT): {"command": EMIT,
                                                                                    "failures": [KNOWN]}}))
        self.assertGate(self.check(mode="base"), "FAIL", "nonzero exit 1 is not explained by the baseline "
                                                         "(no recorded exit)")

    def test_exit_zero_with_a_verify_fail_line_fails(self):
        cmd = "printf 'Ran 2 tests in 0.0s\\n\\nOK\\nverify: FAIL (1 checks)\\n'"
        self.assertGate(self.check(cmd), "FAIL", "exit/verdict mismatch")

    def test_exit_zero_with_a_baselined_junit_failure_fails(self):
        xml = ('<testsuite><testcase classname="a.B" name="ok"/><testcase classname="a.B" name="bad">'
               '<failure/></testcase></testsuite>')
        cmd = f"mkdir -p .runs/junit && printf '%s' '{xml}' > .runs/junit/r.xml"
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", cmd, "--junit", ".runs/junit/*.xml")
        self.assertEqual(res.returncode, 0, res.stderr)
        res = self.repo.gate("check", "--goal", "F-9", "--cmd", cmd, "--junit", ".runs/junit/*.xml")
        self.assertGate(res, "FAIL", "exit 0 with 1 counted failure(s) (exit/verdict mismatch)")
        self.assertIn("(baseline 1)", res.stdout)

    def test_gate_that_commits_fails(self):
        self.assertGate(self.check(EMIT + " && git commit -q --allow-empty -m sneak"), "FAIL",
                        "the run changed the tree")
        cmd = EMIT + " && echo x >> docs/design.md && git commit -qam sneak"
        self.assertGate(self.check(cmd), "FAIL", "the run changed the tree")
        self.assertEqual(self.repo.git("status", "--porcelain"), "")

    def test_check_on_a_clean_tree_replaces_the_stale_receipt(self):
        self.assertGate(self.receipt(), "PASS")
        self.assertGate(self.check(mode="crash"), "FAIL", "nonzero exit 1")
        self.assertEqual(self.receipts(), [])

    def test_check_on_a_dirty_tree_leaves_receipts_alone(self):
        self.assertGate(self.receipt(), "PASS")
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertGate(self.check(mode="crash"), "FAIL", "nonzero exit 1")
        (r,) = self.receipts()
        self.assertEqual(r["verdict"], "PASS")

    def test_gradle_needs_rerun_tasks(self):
        self.assertGate(self.check("echo ./gradlew test >/dev/null; " + EMIT), "FAIL", "--rerun-tasks")
        self.assertGate(self.check("echo ./gradlew test --rerun-tasks >/dev/null; " + EMIT), "PASS")

    def test_junit_xml_counts(self):
        xml = ('<testsuite><testcase classname="a.B" name="ok"/><testcase classname="a.B" name="bad">'
               '<failure/></testcase><testcase classname="a.B" name="later"><skipped/></testcase></testsuite>')
        cmd = f"mkdir -p .runs/junit && printf '%s' '{xml}' > .runs/junit/r.xml"
        res = self.repo.gate("check", "--goal", "F-9", "--cmd", cmd, "--junit", ".runs/junit/*.xml")
        self.assertGate(res, "FAIL", "2 run / 1 failed / 1 skipped")
        self.assertIn("a.B.bad", res.stdout)


class ReceiptTest(GateCase):
    def test_receipt_bound_to_tree_and_command(self):
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertEqual((r["tree"], r["command"], r["name"], r["verdict"], r["executed"]),
                         (self.repo.tree(), EMIT, "full_gate", "PASS", 3))
        expected = gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(), EMIT)
        self.assertTrue(expected.is_file())
        for key in ("exit", "failed", "skipped", "failures", "new_failures", "baseline_failures",
                    "started_at", "finished_at", "reasons"):
            self.assertIn(key, r)

    def test_refused_on_dirty_tree(self):
        self.repo.write("docs/design.md", "# changed\n")
        res = self.receipt()
        self.assertEqual(res.returncode, 1)
        self.assertIn("receipt refused", res.stdout)
        self.assertEqual(self.receipts(), [])
        self.repo.git("checkout", "docs/design.md")
        self.repo.write("untracked.txt", "x\n")
        self.assertIn("receipt refused", self.receipt().stdout)

    def test_rerun_replaces_the_previous_receipt(self):
        self.assertGate(self.receipt(), "PASS")
        self.assertGate(self.receipt(mode="crash"), "FAIL")
        (r,) = self.receipts()
        self.assertEqual(r["verdict"], "FAIL")

    def test_gate_that_dirties_the_tree_gets_a_failing_receipt(self):
        res = self.receipt(EMIT + " && echo x >> docs/design.md")
        self.assertGate(res, "FAIL", "changed the working tree")
        self.assertEqual(self.receipts()[0]["verdict"], "FAIL")

    def test_gate_that_commits_gets_a_failing_receipt(self):
        res = self.receipt(EMIT + " && git commit -q --allow-empty -m sneak")
        self.assertGate(res, "FAIL", "the run changed the tree")
        self.assertEqual(self.receipts()[0]["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
