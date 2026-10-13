"""Tests for gate.py: count parsing, the failure rules, baselines and receipts.

Parsing is tested directly on canned runner output. The failure rules and receipts are tested by
running gate.py against a throwaway repository whose `emit.py` prints canned output chosen by an
environment variable, so one command string can pass, fail, or lie about its result.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import GATE, Repo, env  # noqa: E402

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

    def test_failing_check_on_a_clean_tree_supersedes_the_pass_receipt(self):
        self.assertGate(self.receipt(), "PASS")
        res = self.check(mode="crash")
        self.assertGate(res, "FAIL", "nonzero exit 1")
        self.assertIn("receipt superseded:", res.stdout)
        (r,) = self.receipts()
        self.assertEqual((r["verdict"], r["tree"], r["name"], r["reruns"]), ("FAIL", self.repo.tree(), "full_gate", 0))
        self.assertEqual(r["superseded"]["verdict"], "PASS")
        self.assertEqual(r["reasons"], ["nonzero exit 1", "zero tests executed"])
        # Row 7 no longer accepts the tree: only a fresh `receipt` can certify it again.
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertEqual((r["verdict"], r["rerun_of"], r["reruns"]),
                         ("PASS", ["reason: nonzero exit 1", "reason: zero tests executed"], 1))

    def test_check_never_deletes_a_fail_receipt(self):
        self.assertGate(self.receipt(mode="base"), "FAIL")
        self.assertGate(self.check(), "PASS")
        self.assertGate(self.check(mode="crash"), "FAIL")
        (r,) = self.receipts()
        self.assertEqual(r["verdict"], "FAIL")
        self.assertNotIn("superseded", r)
        self.assertEqual(r["failures"], [KNOWN])

    def test_check_on_a_dirty_tree_leaves_receipts_alone(self):
        self.assertGate(self.receipt(), "PASS")
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertGate(self.check(mode="crash"), "FAIL", "nonzero exit 1")
        (r,) = self.receipts()
        self.assertEqual(r["verdict"], "PASS")

    def test_check_accepts_rerun_and_counts_only_tests_that_ran(self):
        self.assertGate(self.check("echo ./gradlew test --rerun >/dev/null; " + EMIT), "PASS")
        self.assertGate(self.check("echo ./gradlew test --rerun-tasks >/dev/null; " + EMIT), "PASS")
        self.assertGate(self.check("echo ./gradlew test >/dev/null; " + EMIT), "FAIL",
                        "gradle command without --rerun or --rerun-tasks may report cached results")
        xml = ('<testsuite><testcase classname="a.B" name="ok"/><testcase classname="a.B" name="two"/>'
               '</testsuite>')
        self.repo.write(".runs/junit/old.xml", xml)
        old = time.time() - 600
        os.utime(self.repo.path(".runs/junit/old.xml"), (old, old))
        res = self.check("echo ./gradlew test --rerun >/dev/null; " + EMIT, "--junit", ".runs/junit/*.xml")
        self.assertGate(res, "PASS", "3 run / 0 failed / 0 skipped")
        cmd = (f"echo ./gradlew test --rerun >/dev/null; printf '%s' '{xml}' > .runs/junit/r.xml; "
               "echo '4 actionable tasks: 1 executed, 3 from cache'")
        res = self.check(cmd, "--junit", ".runs/junit/*.xml")
        self.assertGate(res, "FAIL", "0 run / 0 failed / 0 skipped")
        self.assertIn("test results restored from the build cache did not run; add --no-build-cache", res.stdout)

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
        self.assertEqual((r["rerun_of"], r["reruns"]), ([], 0))

    def test_rerun_history_accumulates_across_receipts_and_checks(self):
        self.assertGate(self.receipt(mode="base"), "FAIL", "failures not in baseline: " + KNOWN)
        res = self.receipt()
        self.assertGate(res, "PASS")
        self.assertIn(f"rerun: replaces 1 earlier receipt(s); seen failing: {KNOWN}", res.stdout)
        (r,) = self.receipts()
        self.assertEqual((r["rerun_of"], r["reruns"]), ([KNOWN], 1))
        self.assertGate(self.check(mode="crash"), "FAIL")  # supersedes the PASS, keeps the history
        (r,) = self.receipts()
        self.assertEqual((r["verdict"], r["rerun_of"], r["reruns"]), ("FAIL", [KNOWN], 1))
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        crash = [KNOWN, "reason: nonzero exit 1", "reason: zero tests executed"]
        self.assertEqual((r["rerun_of"], r["reruns"]), (crash, 2))
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertEqual((r["rerun_of"], r["reruns"]), (crash, 3))

    def test_fail_without_a_test_id_is_remembered_by_its_reason(self):
        self.assertGate(self.receipt(mode="zero"), "FAIL", "zero tests executed")
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertEqual(r["rerun_of"], ["reason: zero tests executed"])

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
        self.assertEqual((r["verdict"], r["rerun_of"], r["reruns"]), ("FAIL", [], 1))
        self.assertEqual(list(self.repo.path(".runs/F-9/receipts").glob("*.tmp")), [])

    def test_gate_that_dirties_the_tree_gets_a_failing_receipt(self):
        res = self.receipt(EMIT + " && echo x >> docs/design.md")
        self.assertGate(res, "FAIL", "changed the working tree")
        self.assertEqual(self.receipts()[0]["verdict"], "FAIL")

    def test_gate_that_commits_gets_a_failing_receipt(self):
        res = self.receipt(EMIT + " && git commit -q --allow-empty -m sneak")
        self.assertGate(res, "FAIL", "the run changed the tree")
        self.assertEqual(self.receipts()[0]["verdict"], "FAIL")

    def test_receipt_and_baseline_require_rerun_tasks(self):
        rerun, rerun_tasks = ("echo ./gradlew test --rerun >/dev/null; " + EMIT,
                              "echo ./gradlew test --rerun-tasks >/dev/null; " + EMIT)
        self.assertGate(self.receipt(rerun), "FAIL", "gradle command without --rerun-tasks may report cached results")
        self.assertGate(self.receipt(rerun_tasks), "PASS")
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", rerun)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("baseline refused: gradle command without --rerun-tasks", res.stdout)
        self.assertFalse(self.repo.path(".runs/F-9/baseline.json").exists())
        self.assertNotIn('"baseline"', self.repo.read(".runs/F-9/checks.jsonl"))
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", rerun_tasks)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(self.repo.path(".runs/F-9/baseline.json").is_file())


class RecordTest(GateCase):
    def records(self):
        path = self.repo.path(".runs/F-9/checks.jsonl")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []

    def test_every_run_appends_to_the_checks_record(self):
        self.assertGate(self.check(), "PASS")
        self.assertGate(self.receipt(mode="crash"), "FAIL")
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", EMIT, GATE_FIXTURE_MODE="base")
        self.assertEqual(res.returncode, 0, res.stderr)
        records = self.records()
        tree = self.repo.tree()
        self.assertEqual([(r["label"], r["command"], r["tree"], r["verdict"]) for r in records],
                         [("check", EMIT, tree, "PASS"), ("receipt", EMIT, tree, "FAIL"),
                          ("baseline", EMIT, tree, "RECORDED")])
        for r in records:
            self.assertIsInstance(r["duration_s"], (int, float))
            self.assertIn("finished_at", r)
        self.assertGate(self.repo.gate("check", "--cmd", EMIT), "PASS")  # no goal: no record
        self.assertEqual(len(self.records()), 3)
        self.assertFalse(self.repo.path(".runs/_check/checks.jsonl").exists())

    def test_every_command_ends_with_the_budget_line(self):
        self.assertEqual(gate.budget_line("check", 12.4), "budget: ok (12 s of 600 s)")
        self.assertEqual(gate.budget_line("check", 700), "budget: 700 s over 600 s")
        self.assertEqual(gate.budget_line("receipt", 700), "budget: ok (700 s of 1800 s)")
        self.assertEqual(gate.budget_line("baseline", 1900), "budget: 1900 s over 1800 s")
        check, other = re.compile(r"^budget: ok \(\d+ s of 600 s\)$"), re.compile(r"^budget: ok \(\d+ s of 1800 s\)$")
        self.assertRegex(self.check().stdout.splitlines()[-1], check)
        self.assertGate(self.receipt(), "PASS")
        res = self.receipt()  # a replacing receipt
        self.assertIn("receipt:", res.stdout.splitlines()[-2])
        self.assertRegex(res.stdout.splitlines()[-1], other)
        res = self.check(mode="crash")  # a superseding check
        self.assertIn("receipt superseded:", res.stdout.splitlines()[-2])
        self.assertRegex(res.stdout.splitlines()[-1], check)
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", EMIT, GATE_FIXTURE_MODE="base")
        self.assertIn("baseline:", res.stdout.splitlines()[-2])
        self.assertRegex(res.stdout.splitlines()[-1], other)

    def test_runs_flag_records_a_linked_worktree_run_in_the_named_directory(self):
        wt = Path(os.path.realpath(tempfile.mkdtemp(prefix="goalfx-wt-"))) / "wt"
        self.addCleanup(shutil.rmtree, wt.parent, True)
        self.repo.git("worktree", "add", "-q", "-b", "side", str(wt))
        (wt / "src").mkdir()
        (wt / "src/w.py").write_text("W = 1\n")
        self.repo.git("-C", str(wt), "add", "-A")
        self.repo.git("-C", str(wt), "commit", "-q", "-m", "side work")
        tree = self.repo.git("-C", str(wt), "rev-parse", "HEAD^{tree}")
        self.assertNotEqual(tree, self.repo.tree())
        main_runs = self.repo.path(".runs")

        def in_worktree(*args):
            return subprocess.run([sys.executable, str(GATE), "receipt", "--goal", "F-9", "--cmd", EMIT,
                                   "--name", "full_gate", *args], cwd=wt, env=env(GATE_FIXTURE_MODE="ok"),
                                  capture_output=True, text=True, timeout=120)

        self.assertGate(in_worktree("--runs", str(main_runs)), "PASS")
        (r,) = self.receipts()
        self.assertEqual((r["tree"], r["command"]), (tree, EMIT))
        self.assertTrue(gate.receipt_path(self.repo.dir, "F-9", tree, EMIT).is_file())
        self.assertEqual([(x["label"], x["tree"]) for x in self.records()], [("receipt", tree)])
        self.assertEqual(len(list(main_runs.glob("F-9/logs/*.log"))), 1)
        self.assertFalse((wt / ".runs").exists())
        self.assertGate(in_worktree(), "PASS")  # without the flag nothing moves
        self.assertEqual(len(list(wt.glob(".runs/F-9/receipts/*.json"))), 1)
        self.assertEqual((len(self.receipts()), len(self.records())), (1, 1))


SLOW = "mod.Case.test_slow"


def failing(*block):
    """A gate command whose run fails one test, test_slow, with block printed under its FAIL header."""
    lines = ("FAIL: test_slow (mod.Case.test_slow)", *block, "----", "Ran 3 tests in 0.01s", "", "FAILED (failures=1)")
    return "printf '%s\\n' " + " ".join(f"'{line}'" for line in lines) + "; exit 1"


TIMED_OUT = failing("subprocess.TimeoutExpired: Command timed out after 120 seconds")
BUSY = {"load": [6.0, 5.5, 4.0], "cpus": 4}  # the failed run's planted load, at or above its CPU count
IDLE = {"load": [0.5, 0.5, 0.5], "cpus": 8}


class RerunFailedTest(GateCase):
    def rerun(self, subset=EMIT + " " + SLOW, cause="timeout under load; passes alone", cmd=TIMED_OUT, mode="ok"):
        extra = ["--cause", cause] if cause else []
        return self.repo.gate("receipt", "--goal", "F-9", "--cmd", cmd, "--name", "full_gate",
                              "--rerun-failed", subset, *extra, GATE_FIXTURE_MODE=mode)

    def complete(self, cmd, executed=3):
        """An earlier PASS receipt of cmd on another tree: a run that executed `executed` tests."""
        path = self.repo.path(f".runs/F-9/receipts/{'0' * 40}-{gate.cmd_hash(cmd)}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"command": cmd, "verdict": "PASS", "executed": executed,
                                    "finished_at": "2026-01-01T00:00:00+00:00", "tree": "0" * 40}))

    def failed(self, cmd=TIMED_OUT, mode="ok", complete=3, **plant):
        """A FAIL receipt for cmd, with plant (load, cpus) written over what this machine measured, after
        an earlier complete run of cmd that executed `complete` tests (None: no earlier run)."""
        if complete is not None:
            self.complete(cmd, complete)
        self.assertGate(self.receipt(cmd, mode=mode), "FAIL", "failures not in baseline: ")
        path = gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(), cmd)
        r = {**json.loads(path.read_text()), **plant}
        path.write_text(json.dumps(r))
        return r

    def assertRefused(self, res, why):
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("receipt refused: ", res.stdout)
        self.assertIn(why, res.stdout)
        self.assertNotIn("gate: ", res.stdout)

    def test_rerun_failed_completes_a_load_failed_receipt(self):
        failed = self.failed(**BUSY)
        self.assertEqual(failed["new_failures"], [SLOW])
        subset = EMIT + " " + SLOW
        res = self.rerun(subset)
        self.assertGate(res, "PASS", "3 run / 0 failed / 0 skipped")
        self.assertIn("  - partial: reran 1 failed test(s) after a load failure; cause: timeout under load; "
                      "passes alone", res.stdout)
        self.assertTrue(res.stdout.splitlines()[-1].startswith("budget: ok"))
        r = json.loads(gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(), TIMED_OUT).read_text())
        self.assertEqual((r["verdict"], r["command"], r["tree"], r["name"], r["rerun_command"], r["cause"]),
                         ("PASS", TIMED_OUT, self.repo.tree(), "full_gate", subset, "timeout under load; passes alone"))
        self.assertEqual(r["partial"], failed)
        self.assertNotEqual(r["log"], failed["log"])
        self.assertTrue(Path(r["log"]).is_file())
        self.assertEqual((len(r["load"]), r["cpus"]), (3, os.cpu_count()))
        self.assertEqual((r["rerun_of"], r["reruns"]), ([SLOW], 1))
        last = json.loads(self.repo.read(".runs/F-9/checks.jsonl").splitlines()[-1])
        self.assertEqual((last["label"], last["command"], last["verdict"]), ("receipt", subset, "PASS"))
        self.assertEqual(set(last), {"label", "command", "tree", "duration_s", "verdict", "finished_at"})

    def test_rerun_rejects_failure_ids_only_in_comments_or_echo(self):
        self.failed(**BUSY)
        plain = "the --rerun-failed command must be one plain test command"
        for subset in (EMIT + " # " + SLOW, "echo " + SLOW, EMIT + "; echo " + SLOW, EMIT + " && echo " + SLOW,
                       EMIT + " | grep " + SLOW, EMIT + " $(echo " + SLOW + ")", EMIT + " > " + SLOW):
            with self.subTest(subset=subset):
                self.assertRefused(self.rerun(subset), plain)
        res = self.rerun(EMIT + " " + SLOW, mode="zero")  # names it, runs nothing
        self.assertGate(res, "FAIL", "executed 0 test(s), fewer than the 1 it must rerun")

    def test_rerun_rejects_assertion_with_timeout_in_traceback_name(self):
        not_load = SLOW + ": not a timeout or resource error"
        for block in (('Traceback (most recent call last):', '  File "mod.py", line 5, in test_timeout_policy',
                       '    self.assertEqual(timeout_after(1), 2)', 'AssertionError: 1 != 2'),
                      ('AssertionError: request timed out after 3 s was expected',),
                      ('  File "mod.py", line 9, in wait_timeout', '    raise ValueError("x")', 'ValueError: x')):
            with self.subTest(block=block[-1]):
                cmd = failing(*block)
                self.failed(cmd, **BUSY)
                self.assertRefused(self.rerun(cmd=cmd), not_load)
        self.assertTrue(gate.timeout_evidence("\nsubprocess.TimeoutExpired: Command 'x' timed out after 120 seconds"))
        self.assertTrue(gate.timeout_evidence(" - Failed: Timeout >5.0s"))
        self.assertTrue(gate.timeout_evidence("\njava.util.concurrent.TimeoutException\n\tat a.B.c(B.java:3)"))

    def test_rerun_binds_pytest_timeout_evidence_to_full_node_id(self):
        lines = ("____ test_x ____", ">       assert 1 == 2", "E       assert 1 == 2", "tests/a.py:2: AssertionError",
                 "____ test_x ____", ">       time.sleep(10)", "E       Failed: Timeout >5.0s", "tests/b.py:2: Failed",
                 "=== short test summary info ===", "FAILED tests/a.py::test_x - assert 1 == 2",
                 "FAILED tests/b.py::test_x - Failed: Timeout >5.0s", "=== 2 failed, 1 passed in 6.0s ===")
        cmd = "printf '%s\\n' " + " ".join(f"'{line}'" for line in lines) + "; exit 1"
        failed = self.failed(cmd, **BUSY)
        self.assertEqual(failed["new_failures"], ["tests/a.py::test_x", "tests/b.py::test_x"])
        self.assertRefused(self.rerun(EMIT + " tests/a.py::test_x tests/b.py::test_x", cmd=cmd),
                           "tests/a.py::test_x: not a timeout or resource error")

    def test_rerun_cannot_complete_a_short_circuited_suite(self):
        # `unittest a && unittest b` whose first suite times out: b never ran, so 3 of a complete run's 5.
        self.failed(complete=5, **BUSY)
        self.assertRefused(self.rerun(), "executed 3 test(s), fewer than the 5 of the last complete run")
        other = failing("subprocess.TimeoutExpired: Command timed out after 60 seconds")
        self.failed(other, complete=None, **BUSY)
        self.assertRefused(self.rerun(cmd=other), "no earlier PASS receipt of this command")

    def test_interrupted_subset_consumes_the_single_attempt(self):
        failed = self.failed(**BUSY)
        killed = self.rerun("kill -KILL $PPID " + SLOW)  # the receipt process dies during the subset run
        self.assertEqual(killed.returncode, -9, killed.stdout + killed.stderr)
        r = json.loads(gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(), TIMED_OUT).read_text())
        self.assertEqual((r["verdict"], r["new_failures"]), (failed["verdict"], failed["new_failures"]))
        self.assertIn("rerun_started", r)
        self.assertRefused(self.rerun(), "already completed once with --rerun-failed")

    def test_receipt_refusals_record_verdict_and_end_with_budget(self):
        def refused(res, why):
            self.assertRefused(res, why)
            self.assertTrue(res.stdout.splitlines()[-1].startswith("budget: ok"), res.stdout)
            last = json.loads(self.repo.read(".runs/F-9/checks.jsonl").splitlines()[-1])
            self.assertEqual((last["label"], last["command"], last["verdict"]), ("receipt", TIMED_OUT, "REFUSED"))
        refused(self.rerun(cause=""), "--rerun-failed and --cause go together")
        refused(self.rerun(), "needs a FAIL receipt for this tree and command")
        self.repo.write("dirty.txt", "x")
        refused(self.rerun(), "the working tree is not clean")

    def test_rerun_failed_accepts_a_gradle_tests_filter(self):
        subset = "./gradlew test --continue --rerun-tasks --tests '*FooTest.bar'"
        self.assertTrue(gate.failure_named("com.example.FooTest.bar()", subset))
        self.assertTrue(gate.failure_named("test_goal.CostTest.test_x", "python3 -m unittest test_goal.CostTest.test_x"))
        self.assertFalse(gate.failure_named("com.example.FooTest.baz()", subset))
        self.assertFalse(gate.failure_named("tests/a.py::test_x", "pytest tests/b.py::test_x"))

    def test_rerun_failed_refuses_what_it_cannot_prove(self):
        subset = EMIT + " " + KNOWN
        self.assertRefused(self.rerun(subset, cmd=EMIT), "needs a FAIL receipt for this tree and command")
        self.assertGate(self.receipt(mode="crash"), "FAIL")
        self.assertRefused(self.rerun(subset, cmd=EMIT), "only reason is failures not in baseline")
        self.failed(EMIT, mode="base", **BUSY)
        self.assertRefused(self.rerun(EMIT + " mod.Case", cmd=EMIT), "does not name " + KNOWN)
        self.assertRefused(self.rerun(subset, cause="", cmd=EMIT), "--rerun-failed and --cause go together")
        not_load = ": not a timeout or resource error; a test that fails in the suite and passes alone may " \
                   "depend on another test, so run the full gate"
        self.assertRefused(self.rerun(subset, cmd=EMIT), KNOWN + not_load)  # a block with no timeout
        asserted = failing("AssertionError: 1 != 2")
        self.failed(asserted, **BUSY)
        self.assertRefused(self.rerun(cmd=asserted), SLOW + not_load)
        failed = self.failed(**IDLE)
        self.assertRefused(self.rerun(), "no recorded load during the failed run")
        ended = datetime.datetime.fromisoformat(failed["finished_at"]) + datetime.timedelta(seconds=60)
        with open(self.repo.path(".runs/F-9/checks.jsonl"), "a") as fh:  # another run spanning it
            fh.write(json.dumps({"label": "check", "command": "other", "tree": self.repo.tree(), "duration_s": 3600,
                                 "verdict": "PASS", "finished_at": ended.isoformat(timespec="seconds")}) + "\n")
        self.assertGate(self.rerun(mode="crash"), "FAIL", "nonzero exit 1")  # a subset that fails stays FAIL
        r = json.loads(gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(), TIMED_OUT).read_text())
        self.assertEqual((r["verdict"], r["partial"]["verdict"], r["rerun_command"]), ("FAIL", "FAIL", EMIT + " " + SLOW))
        self.assertRefused(self.rerun(), "already completed once with --rerun-failed")
        self.failed(**BUSY)  # a fresh full run may be completed once
        self.assertGate(self.rerun(), "PASS")
        self.assertRefused(self.rerun(), "already completed once with --rerun-failed")
        gradle = "echo ./gradlew test --rerun-tasks >/dev/null; " + TIMED_OUT
        self.failed(gradle, **BUSY)
        self.assertRefused(self.rerun(cmd=gradle), "gradle command without --continue")
        gradle = "echo ./gradlew test --rerun-tasks --continue >/dev/null; " + TIMED_OUT
        self.failed(gradle, **BUSY)
        self.assertGate(self.rerun(f"{EMIT} --tests {SLOW}", cmd=gradle), "PASS")


if __name__ == "__main__":
    unittest.main()
