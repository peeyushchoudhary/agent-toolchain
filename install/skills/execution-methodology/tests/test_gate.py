"""Tests for gate.py: count parsing, the failure rules, baselines and receipts.

Parsing is tested directly on canned runner output. The failure rules and receipts are tested by
running gate.py against a throwaway repository whose `emit.py` prints canned output chosen by an
environment variable, so one command string can pass, fail, or lie about its result.
"""
from __future__ import annotations

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

    def test_receipt_omits_removed_load_rerun_metadata(self):
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertFalse({"load", "partial", "cause", "rerun_command"} & r.keys(), r)

    def test_every_record_and_receipt_carries_load_readings(self):
        readings = {"started_at", "load_before", "load_peak", "cpus"}
        self.assertGate(self.check(), "PASS")
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertLessEqual(readings, r.keys(), r)
        res = self.repo.gate("baseline", "--goal", "F-9", "--cmd", EMIT, GATE_FIXTURE_MODE="base")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.repo.write("dirty.txt", "x")
        self.assertIn("receipt refused", self.receipt().stdout)
        lines = [json.loads(line) for line in self.repo.read(".runs/F-9/checks.jsonl").splitlines()]
        self.assertEqual([x["label"] for x in lines], ["check", "receipt", "baseline", "receipt"])
        for x in lines:
            self.assertLessEqual(readings, x.keys(), x)
            self.assertIsInstance(x["load_before"], float)
            self.assertEqual(x["cpus"], os.cpu_count())
        self.assertEqual(lines[-1]["load_peak"], lines[-1]["load_before"])

    def test_load_peak_is_at_least_load_before(self):
        self.assertGate(self.receipt(), "PASS")
        (r,) = self.receipts()
        self.assertGreaterEqual(r["load_peak"], r["load_before"])
        self.assertEqual(r["load_before"], round(r["load_before"], 2))
        *_, readings = gate.run(self.repo.dir, "true", "F-9", "check", load_before=1e6)
        self.assertEqual((readings["load_before"], readings["load_peak"]), (1e6, 1e6))

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


class RefusalTest(GateCase):
    def test_receipt_refusals_record_verdict_and_end_with_budget(self):
        self.repo.write("dirty.txt", "x")
        res = self.receipt(EMIT)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("receipt refused: the working tree is not clean", res.stdout)
        self.assertTrue(res.stdout.splitlines()[-1].startswith("budget: ok"), res.stdout)
        last = json.loads(self.repo.read(".runs/F-9/checks.jsonl").splitlines()[-1])
        self.assertEqual((last["label"], last["command"], last["verdict"]), ("receipt", EMIT, "REFUSED"))


def module_cmd(name, prefix=""):
    """A module test command: the fixture emitter in the mode the test wrote to .runs/mode-<name>."""
    return f"{prefix}GATE_FIXTURE_MODE=$(cat .runs/mode-{name} 2>/dev/null || echo ok) {EMIT}"


class ModulesTest(GateCase):
    """Three modules over the fixture emitter: b needs a, c is a count-none module."""

    def setUp(self):
        super().setUp()
        self.write_map({"a": module_cmd("a"), "b": module_cmd("b"), "c": module_cmd("c")})

    def write_map(self, cmds):
        self.repo.write("docs/goals/modules.json", json.dumps({"modules": {
            "a": {"paths": ["src/a/**"], "test": cmds["a"]},
            "b": {"paths": ["src/b/**"], "needs": ["a"], "test": cmds["b"]},
            "c": {"paths": ["docs/**"], "test": cmds["c"], "count": "none"}}}, indent=2))
        self.repo.commit("module map")
        self.cmds = cmds

    def mode(self, name, mode):
        self.repo.write(f".runs/mode-{name}", mode)

    def modules(self, action, which="all"):
        return self.repo.gate(action, "--goal", "F-9", "--modules", which)

    def module_receipt(self, name):
        return gate.read_receipt(gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(),
                                                   f"module:{name}\n" + self.cmds[name]))

    def logs(self):
        return len(list(self.repo.path(".runs/F-9/logs").glob("*.log")))

    def test_modules_run_each_command_and_pass_only_when_all_pass(self):
        self.mode("c", "zero")
        res = self.modules("check")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        for name in ("a", "b", "c"):
            self.assertIn(f"module {name}: gate: PASS", res.stdout)
        self.assertEqual(res.stdout.splitlines()[-2], "modules: PASS 3 of 3")
        self.assertRegex(res.stdout.splitlines()[-1], r"^budget: ok \(\d+ s of 600 s\)$")
        self.assertEqual(self.logs(), 3)
        self.mode("a", "crash")
        res = self.modules("check")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("module a: gate: FAIL", res.stdout)
        self.assertIn("module c: gate: PASS", res.stdout)  # every module runs after a failure
        self.assertEqual(res.stdout.splitlines()[-2], "modules: FAIL 1 of 3 (a)")
        res = self.modules("check", "c,b")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("module a:", res.stdout)
        self.assertLess(res.stdout.index("module b:"), res.stdout.index("module c:"))  # map order
        self.assertIn("modules: PASS 2 of 2", res.stdout)
        res = self.modules("receipt", "a,x")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("gate.py: no module x in docs/goals/modules.json", res.stderr)
        self.repo.git("rm", "-q", "docs/goals/modules.json")
        self.repo.commit("no map")
        res = self.modules("check", "a")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("gate.py: no module a in docs/goals/modules.json", res.stderr)

    def test_receipt_keeps_passed_modules_on_the_same_tree(self):
        res = self.modules("receipt")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("modules: PASS 3 of 3", res.stdout)
        a = self.module_receipt("a")
        self.assertEqual((a["verdict"], a["name"], a["module"], a["command"], a["tree"]),
                         ("PASS", "module", "a", self.cmds["a"], self.repo.tree()))
        res = self.modules("receipt")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        for name in ("a", "b", "c"):
            self.assertIn(f"module {name}: PASS on this tree (kept)", res.stdout)
        self.assertIn("modules: PASS 3 of 3", res.stdout)
        self.assertEqual(self.logs(), 3)
        lines = [json.loads(x) for x in self.repo.read(".runs/F-9/checks.jsonl").splitlines()]
        self.assertEqual([(x["label"], x["module"]) for x in lines],
                         [("receipt", "a"), ("receipt", "b"), ("receipt", "c")])
        self.assertEqual(len({x["load_before"] for x in lines}), 1)  # one reading per invocation

    def test_failed_module_is_retried_once_then_refused(self):
        self.mode("b", "crash")
        self.assertEqual(self.modules("receipt", "b").returncode, 1)
        self.assertEqual(self.module_receipt("b")["verdict"], "FAIL")
        self.mode("b", "ok")
        res = self.modules("receipt", "b")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("module b: retry after a failure on this tree", res.stdout)
        b = self.module_receipt("b")
        self.assertEqual((b["verdict"], b["retry_of"]["verdict"]), ("PASS", "FAIL"))
        self.mode("a", "crash")  # a fails, fails again on its retry, and is then refused
        self.assertEqual(self.modules("receipt", "a").returncode, 1)
        res = self.modules("receipt", "a")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("module a: retry after a failure on this tree", res.stdout)
        self.assertEqual(self.module_receipt("a")["retry_of"]["verdict"], "FAIL")
        logs = self.logs()
        res = self.modules("receipt")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("module a failed twice on this tree; diagnose and commit a fix", res.stdout)
        self.assertIn("module b: PASS on this tree (kept)", res.stdout)
        self.assertIn("module c: gate: PASS", res.stdout)  # the other modules still run
        self.assertEqual(res.stdout.splitlines()[-2], "modules: FAIL 1 of 3 (a)")
        self.assertEqual(self.logs(), logs + 1)
        refused = json.loads(self.repo.read(".runs/F-9/checks.jsonl").splitlines()[-2])
        self.assertEqual((refused["module"], refused["verdict"]), ("a", "REFUSED"))
        self.assertEqual(refused["load_peak"], refused["load_before"])

    def test_module_receipts_do_not_alias_commands_or_other_modules(self):
        self.assertEqual(self.modules("receipt", "a").returncode, 0)
        self.mode("a", "crash")
        self.assertGate(self.receipt(self.cmds["a"]), "FAIL", "nonzero exit 1")
        self.assertGate(self.check(self.cmds["a"]), "FAIL", "nonzero exit 1")
        self.assertEqual(self.module_receipt("a")["verdict"], "PASS")
        paths = {gate.receipt_path(self.repo.dir, "F-9", self.repo.tree(), key) for key in
                 (self.cmds["a"], "module:a\n" + self.cmds["a"], "module:b\n" + self.cmds["b"])}
        self.assertEqual(len(paths), 3)

    def test_check_modules_writes_no_new_module_receipt(self):
        self.assertEqual(self.modules("check").returncode, 0)
        self.mode("b", "crash")
        self.assertEqual(self.modules("check").returncode, 1)
        self.assertEqual(self.receipts(), [])
        lines = [json.loads(x) for x in self.repo.read(".runs/F-9/checks.jsonl").splitlines()]
        self.assertEqual({x["label"] for x in lines}, {"check"})
        self.assertEqual([x["module"] for x in lines], ["a", "b", "c"] * 2)

    def test_failed_check_invalidates_pass_without_reopening_retry(self):
        self.assertEqual(self.modules("receipt", "a").returncode, 0)
        self.mode("a", "crash")
        res = self.modules("check", "a")
        self.assertIn("receipt superseded:", res.stdout)
        a = self.module_receipt("a")
        self.assertEqual((a["verdict"], a["superseded"]["verdict"], a["module"]), ("FAIL", "PASS", "a"))
        self.mode("a", "ok")  # the contradicted PASS no longer counts: a reruns as its retry
        res = self.modules("receipt", "a")
        self.assertIn("module a: retry after a failure on this tree", res.stdout)
        self.assertEqual(self.module_receipt("a")["verdict"], "PASS")
        self.mode("a", "crash")  # a retried PASS contradicted by a check keeps its spent retry
        self.assertIn("receipt superseded:", self.modules("check", "a").stdout)
        a = self.module_receipt("a")
        self.assertEqual((a["verdict"], a["retry_of"]["verdict"]), ("FAIL", "FAIL"))
        self.mode("a", "ok")
        res = self.modules("receipt", "a")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("module a failed twice on this tree; diagnose and commit a fix", res.stdout)

    def test_module_receipt_accepts_gradle_rerun(self):
        self.write_map({"a": module_cmd("a", "echo ./gradlew test --rerun >/dev/null; "),
                        "b": module_cmd("b", "echo ./gradlew test --rerun-tasks >/dev/null; "),
                        "c": module_cmd("c", "echo ./gradlew test >/dev/null; ")})
        res = self.modules("receipt")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("module a: gate: PASS", res.stdout)
        self.assertIn("module b: gate: PASS", res.stdout)
        self.assertIn("module c: gate: FAIL", res.stdout)
        self.assertIn("gradle command without --rerun or --rerun-tasks may report cached results", res.stdout)
        self.assertGate(self.receipt(self.cmds["a"]), "FAIL", "gradle command without --rerun-tasks")

    def test_a_new_tree_reruns_every_module(self):
        self.assertEqual(self.modules("receipt").returncode, 0)
        self.repo.write("src/a/x.py", "A = 1\n")
        self.repo.commit("change a")
        res = self.modules("receipt")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("(kept)", res.stdout)
        for name in ("a", "b", "c"):
            self.assertIn(f"module {name}: gate: PASS", res.stdout)
        self.assertEqual((self.logs(), len(self.receipts())), (6, 6))


class CoverageTest(GateCase):
    """The map replaces a full gate that runs a's and b's tests; c is a count-none module."""

    def setUp(self):
        super().setUp()
        self.full = f"{module_cmd('a')} && {module_cmd('b')}"
        self.repo.write("docs/goals/modules.json", json.dumps({"replaces": self.full, "modules": {
            "a": {"paths": ["src/a/**"], "test": module_cmd("a")},
            "b": {"paths": ["src/b/**"], "test": module_cmd("b")},
            "c": {"paths": ["docs/**"], "test": module_cmd("c"), "count": "none"}}}, indent=2))
        self.repo.commit("module map")
        self.repo.write(".runs/mode-c", "zero")

    def coverage(self, *args):
        return self.repo.gate("coverage", "--goal", "F-9", *args)

    def modules(self, which):
        res = self.repo.gate("receipt", "--goal", "F-9", "--modules", which)
        self.assertIn("modules: PASS", res.stdout, res.stdout + res.stderr)

    def test_coverage_reports_equal_counts(self):
        self.assertGate(self.receipt(self.full), "PASS", "6 run")
        self.modules("all")
        before = (sorted(self.repo.path(".runs").rglob("*")), self.repo.read(".runs/F-9/checks.jsonl"))
        res = self.coverage()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), "coverage: 6 = 6")
        self.assertEqual((sorted(self.repo.path(".runs").rglob("*")), self.repo.read(".runs/F-9/checks.jsonl")),
                         before)  # runs nothing, writes nothing
        self.repo.write("dirty.txt", "x")
        res = self.coverage()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("coverage refused: the working tree is not clean; commit first:", res.stdout)
        self.repo.path("dirty.txt").unlink()
        self.repo.write("docs/goals/modules.json", json.dumps({"modules": {
            "a": {"paths": ["src/a/**"], "test": module_cmd("a")}}}))
        self.repo.commit("map without replaces")
        res = self.coverage()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("gate.py: coverage needs --cmd or a replaces command in docs/goals/modules.json", res.stderr)

    def test_coverage_names_missing_module_receipts_and_short_sums(self):
        res = self.coverage()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), f"coverage: no PASS receipt for {self.full} on tree {self.repo.tree()}")
        self.assertGate(self.receipt(self.full), "PASS")
        self.modules("a")
        self.repo.write(".runs/mode-b", "crash")
        self.repo.gate("receipt", "--goal", "F-9", "--modules", "b")  # a FAIL receipt is no PASS
        res = self.coverage()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), "coverage: full 6, modules 3; b missing")
        self.repo.write(".runs/mode-b", "ok")
        self.modules("b")  # its one retry
        wider = f"{self.full} && {EMIT}"
        self.assertGate(self.receipt(wider), "PASS", "9 run")
        res = self.coverage("--cmd", wider)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), "coverage: full 9, modules 6")

    def test_coverage_skips_count_none_modules(self):
        self.assertGate(self.receipt(self.full), "PASS")
        self.modules("a,b")  # c has no receipt
        res = self.coverage()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), "coverage: 6 = 6")
        self.modules("c")  # a count-none module adds nothing
        self.assertEqual(self.coverage().stdout.strip(), "coverage: 6 = 6")


if __name__ == "__main__":
    unittest.main()
