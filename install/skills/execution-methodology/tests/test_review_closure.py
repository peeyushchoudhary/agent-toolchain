"""Tests for review.py's closure rules (F-4): the --closed-by confirmation, per-round file digests,
the rereview family instruction, and the acceptance diff and its coverage line.

review() runs in-process with a stub judge in place of run_judge, as in test_review.py's
ConcurrentRoundTest: no real CLI is called. Each refusal is checked to consume nothing.
"""
from __future__ import annotations

import argparse
import builtins
import contextlib
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import GOAL, Repo, TEST_A  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
sys.path.insert(0, str(GOAL.parents[2] / "agent-personas" / "scripts"))
import goal  # noqa: E402
import review  # noqa: E402

PASS = "VERDICT: PASS\n- [other] src/a/x.py — trigger: none — consequence: naming only"
BLOCK = "VERDICT: BLOCK\n- [correctness] src/a/x.py — trigger: empty input — consequence: crash"
TASK = ("--kind", "boundary", "--task", "T1")
PLAN = ("--kind", "plan", "--subject", "docs/plan.md")


class ClosureCase(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.ctx = goal.find_ctx(argparse.Namespace(plan="docs/plan.md", goal=None), cwd=str(self.repo.dir))
        self.vdir = self.ctx.runs / "verdicts"
        self.packets, self.reply = [], BLOCK
        for patcher in (mock.patch.object(review, "run_judge", self.judge),
                        mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    during = None  # a callable the stub judge runs mid-call, e.g. editing a file

    def judge(self, vendor, persona, variant, packet, root, timeout):
        self.packets.append(packet)
        if self.during:
            self.during()
        if "FAIL" in packet:
            return {"model": "m", "effort": "e"}, "", "", "judge crashed", False
        return {"model": "m", "effort": "e"}, self.reply, "stub", "", False

    def run_review(self, *args):
        a = review.parser().parse_args(["--chief", "claude", *args])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = review.review(a, self.ctx)
        self.out, self.err = out.getvalue(), err.getvalue()
        return code

    def rounds(self):
        return goal.read_json(self.vdir / "rounds.json")

    def head(self, key):
        return goal.read_verdict(self.vdir / f"{key}.md")[2]

    def history(self, key):
        return sorted(p.name for p in (self.vdir / "history").glob(f"{key}-r*.md"))

    def change_test(self, rel="tests/test_a.py", n=1):
        self.repo.write(rel, TEST_A + f"\n# reproduces finding {n}\n")

    def assert_refused(self, *args, why=""):
        before = (self.rounds(), len(self.packets), self.history("*"))
        self.assertEqual(self.run_review(*args), 1, self.out)
        self.assertIn("refused", self.out)
        self.assertIn(why, self.out)
        self.assertEqual((self.rounds(), len(self.packets), self.history("*")), before)


class ConfirmationTest(ClosureCase):
    def test_admitted_at_the_cap_uncounted_and_recorded_in_rounds_and_header(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertEqual([self.run_review(*TASK) for _ in range(2)], [1, 1])
        self.assert_refused(*TASK, why="already had 2 round(s)")
        self.change_test()
        self.reply = PASS
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py::A.test_value"), 0, self.out)
        self.assertEqual(self.rounds(), {"T1-boundary": 2, "confirmations": {"T1-boundary": 3}})
        head = self.head("T1-boundary")
        self.assertEqual((head["round"], head["confirmation"]), ("3", "closed-by tests/test_a.py::A.test_value"))
        packet = self.packets[-1]
        self.assertIn("test-closed confirmation", packet)
        self.assertIn("tests/test_a.py::A.test_value", packet)
        self.assertIn("round 3 of 3", packet)
        files = goal.read_json(self.ctx.runs / "review" / "T1-boundary-r3.files.json")
        self.assertIn("tests/test_a.py", files)
        self.assert_refused(*TASK, why="already had 2 round(s)")

    def test_refused_without_a_verdict_after_a_pass_and_a_second_time(self):
        self.change_test()
        self.assert_refused(*PLAN, "--closed-by", "tests/test_a.py", why="needs a BLOCK verdict")
        self.reply = PASS
        self.assertEqual(self.run_review(*PLAN), 0)
        self.change_test(n=2)
        self.assert_refused(*PLAN, "--closed-by", "tests/test_a.py", why="has PASS")
        self.reply = BLOCK
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test(n=3)
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py"), 1)  # BLOCK again
        self.change_test(n=4)
        self.assert_refused(*PLAN, "--closed-by", "tests/test_a.py", why="already used its confirmation (round 3)")

    def test_an_invalid_last_verdict_is_not_a_block(self):
        self.reply = "Looks fine."
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        self.assert_refused(*PLAN, "--closed-by", "tests/test_a.py", why="has INVALID")

    def test_refused_with_a_founder_grant_and_for_advice_kinds(self):
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        self.assert_refused(*PLAN, "--closed-by", "tests/test_a.py", "--founder-grant", "D9", why="never with")
        self.assert_refused("--kind", "advisor", "--item", "T2", "--note", "q", "--closed-by", "tests/test_a.py",
                            why="capped kind")
        self.assertEqual(self.rounds(), {"plan": 1})

    def test_the_closed_by_refusal_wins_over_every_argument_check(self):
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        why = "--closed-by applies to a capped kind and never with --founder-grant"
        for args in ((*PLAN, "--founder-grant", ""), (*PLAN, "--founder-grant", " "),  # round 4's two calls
                     ("--kind", "advisor", "--item", "T2", "--note", "q", "--founder-grant", "Decisions D9"),
                     ("--kind", "advisor"),  # no --item: the subject key would raise
                     ("--kind", "advisor", "--item", "not-an-id"), ("--kind", "council", "--item", "T2"),
                     ("--kind", "acceptance", "--milestone", "M1", "--diff", "HEAD", "--founder-grant", "D9"),
                     ("--kind", "boundary", "--task", "T99", "--founder-grant", "D9")):
            with self.subTest(args=args):
                self.assert_refused(*args, "--closed-by", "tests/test_a.py", why=why)
        self.assertEqual(self.rounds(), {"plan": 1})  # no founder grant recorded
        with mock.patch.dict(os.environ):  # no chief named: the vendor check would raise
            os.environ.pop("GOAL_HARNESS", None)
            a = review.parser().parse_args(["--kind", "council", "--item", "T2", "--member", "1",
                                            "--closed-by", "tests/test_a.py"])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(review.review(a, self.ctx), 1)
            self.assertIn(why, out.getvalue())
        cwd = os.getcwd()
        os.chdir(self.repo.dir)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                code = review.main(["--plan", "docs/plan.md", "--chief", "claude", *PLAN, "--founder-grant", "",
                                    "--closed-by", "tests/test_a.py"])
        finally:
            os.chdir(cwd)
        self.assertEqual((code, len(self.packets), self.rounds()), (1, 1, {"plan": 1}))

    def test_unchanged_since_the_last_round_is_refused_even_while_uncommitted(self):
        # The test was edited before round 1 and stays uncommitted: the verdict tree still differs,
        # so only the round's digest shows it is unchanged.
        self.change_test()
        self.assertEqual(self.run_review(*TASK), 1)
        self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="unchanged since round 1")
        self.change_test(n=2)
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 1)
        self.assertEqual(self.rounds()["confirmations"], {"T1-boundary": 2})

    def test_an_unchanged_tracked_test_outside_the_last_diff_is_refused(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertEqual(self.run_review(*TASK), 1)
        self.assertIn("tests/test_a.py", goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json"))
        self.assert_refused(*TASK, "--closed-by", "tests/test_a.py::A.test_flag", why="unchanged since round 1")

    def test_untracked_tests_new_counts_unchanged_does_not(self):
        self.repo.write("tests/test_old.py", TEST_A)
        self.assertEqual(self.run_review(*TASK), 1)
        self.assert_refused(*TASK, "--closed-by", "tests/test_old.py", why="unchanged since round 1")
        self.repo.write("tests/test_new.py", TEST_A)
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_new.py", "tests/test_old.py"), 1,
                         self.out)  # refused on test_old: every named test must have changed
        self.assertIn("tests/test_old.py is unchanged", self.out)
        self.assertEqual(self.run_review(*TASK, "--closed-by", "./tests/test_new.py"), 1)
        self.assertEqual(self.rounds(), {"T1-boundary": 1, "confirmations": {"T1-boundary": 2}})

    def test_paths_that_are_not_a_regular_repository_file_are_refused(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertEqual(self.run_review(*TASK), 1)
        outside = self.repo.dir.parent / f"{self.repo.dir.name}-outside.py"
        outside.write_text("x = 1\n")
        self.addCleanup(outside.unlink)
        (self.repo.dir / "tests/link.py").symlink_to("test_a.py")
        self.repo.write("__pycache__/test_ignored.py", "x = 1\n")
        self.repo.path("tests/test_e2e_flow.py").unlink()  # a test deleted since the last round
        for test in ("tests/missing.py", "tests/test_e2e_flow.py", f"../{outside.name}", str(outside),
                     str(self.repo.dir / "src/a/x.py"), "tests/link.py", "__pycache__/test_ignored.py",
                     "tests", "TESTS/test_a.py", "tests/*.py", "::A.test_value", ""):
            with self.subTest(test=test):
                self.assert_refused(*TASK, "--closed-by", test, why="not a regular")

    def test_a_deleted_path_is_recorded_as_null_and_the_review_completes(self):
        self.repo.path("tests/test_e2e_flow.py").unlink()
        self.assertEqual(self.run_review(*TASK), 1)
        self.assertEqual(self.head("T1-boundary")["round"], "1")
        files = goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json")
        self.assertIsNone(files["tests/test_e2e_flow.py"])

    def test_numbering_stays_sequential_and_one_counted_round_is_left(self):
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py"), 1)
        self.assertEqual(self.rounds(), {"plan": 1, "confirmations": {"plan": 2}})
        self.assertEqual(self.run_review(*PLAN), 1)
        self.assertIn("round 3 of 3", self.packets[-1])
        self.assertEqual(self.rounds(), {"plan": 2, "confirmations": {"plan": 2}})
        self.assert_refused(*PLAN, why="already had 2 round(s)")
        self.assertEqual(self.history("plan"), ["plan-r1.md", "plan-r2.md", "plan-r3.md"])
        self.assertEqual([self.head("plan")["round"], len(self.packets)], ["3", 3])  # cap + 1 judge calls

    def test_the_founder_grant_still_admits_exactly_one_round_after_a_confirmation(self):
        self.assertEqual([self.run_review(*PLAN) for _ in range(2)], [1, 1])
        self.change_test()
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py"), 1)
        self.assert_refused(*PLAN, why="already had 2 round(s)")
        self.assertEqual(self.run_review(*PLAN, "--founder-grant", "Decisions D9"), 1)
        self.assertEqual(self.head("plan")["round"], "4")
        self.assertEqual(self.rounds(), {"plan": 3, "confirmations": {"plan": 3},
                                         "founder_grants": {"plan": "Decisions D9"}})
        self.assertIn("round 4 of 4", self.packets[-1])
        self.assert_refused(*PLAN, "--founder-grant", "Decisions D10", why="already used its founder grant")
        self.assert_refused(*PLAN)
        self.assertEqual(self.history("plan"), [f"plan-r{n}.md" for n in (1, 2, 3, 4)])

    def test_a_confirmation_after_a_granted_round_counts_the_grant_in_its_limit(self):
        self.assertEqual([self.run_review(*PLAN) for _ in range(2)], [1, 1])
        self.assertEqual(self.run_review(*PLAN, "--founder-grant", "Decisions D9"), 1)
        self.assertIn("round 3 of 3", self.packets[-1])
        self.change_test()
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py"), 1)
        self.assertIn("round 4 of 4", self.packets[-1])  # every judge call this subject may reach
        self.assert_refused(*PLAN)

    def test_untracked_files_are_recorded_however_the_range_is_spelled(self):
        subjects = (("T1-boundary", "--kind", "boundary", "--task", "T1", "--diff", "HEAD~0"),
                    ("T1-security", "--kind", "security", "--task", "T1", "--diff", "goal/F-9/approved"),
                    ("T1-data", "--kind", "data", "--task", "T1"), ("plan", *PLAN), ("design", "--kind", "design"))
        for i, (key, *args) in enumerate(subjects):
            with self.subTest(args=args):
                self.repo.write(f"tests/test_u{i}.py", TEST_A)  # untracked, unchanged since its round
                self.assertEqual(self.run_review(*args), 1)
                files = goal.read_json(self.ctx.runs / "review" / f"{key}-r1.files.json")
                self.assertIn(f"tests/test_u{i}.py", files)
                self.assert_refused(*args, "--closed-by", f"tests/test_u{i}.py", why="unchanged since round 1")

    def oracle_same(self, path):
        """git's own answer: does path differ from the last verdict's tree? (exit 0 means no)"""
        tree = goal.read_verdict(self.vdir / "T1-boundary.md")[1]
        return subprocess.run(["git", "diff", "--quiet", tree, "--", path], cwd=self.repo.dir).returncode == 0

    def test_a_recorded_test_compares_raw_bytes_even_where_git_sees_no_change(self):
        # The full snapshot records every tracked test, so AC-3's first tier, raw-byte SHA-256, decides.
        self.repo.git("config", "core.autocrlf", "true")
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertEqual(self.run_review(*TASK), 1)
        self.repo.path("tests/test_e2e_flow.py").chmod(0o755)  # a mode change: the bytes are the same
        self.assertFalse(self.oracle_same("tests/test_e2e_flow.py"))  # git reports it; the digest does not
        self.assert_refused(*TASK, "--closed-by", "tests/test_e2e_flow.py", why="unchanged since round 1")
        self.repo.path("tests/test_a.py").write_bytes(TEST_A.replace("\n", "\r\n").encode())  # CRLF only
        self.assertTrue(self.oracle_same("tests/test_a.py"))  # git sees no change; the bytes differ
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 1, self.out)
        self.assertEqual(self.rounds()["confirmations"], {"T1-boundary": 2})

    def differs_from_tree(self, key):
        """git's own list of paths whose working-tree content differs from key's verdict tree."""
        tree = goal.read_verdict(self.vdir / f"{key}.md")[1]
        return self.repo.git("diff", "--name-only", tree).splitlines()

    def test_uncommitted_staged_and_deleted_tests_are_recorded_under_every_range_spelling(self):
        self.change_test()  # a tracked test with uncommitted edits
        self.repo.write("tests/test_staged.py", TEST_A)
        self.repo.git("add", "tests/test_staged.py")  # staged, never committed
        gone = self.repo.read("tests/test_e2e_flow.py")
        self.repo.path("tests/test_e2e_flow.py").unlink()  # deleted in the working tree
        subjects = (("T1-boundary", "--kind", "boundary", "--task", "T1", "--diff", "HEAD..HEAD"),
                    ("T1-security", "--kind", "security", "--task", "T1", "--diff", "HEAD~0"),
                    ("T1-data", "--kind", "data", "--task", "T1"), ("plan", *PLAN), ("design", "--kind", "design"))
        for key, *args in subjects:
            with self.subTest(args=args):
                self.assertEqual(self.run_review(*args), 1)
                files = goal.read_json(self.ctx.runs / "review" / f"{key}-r1.files.json")
                for path in ("tests/test_a.py", "tests/test_staged.py", "tests/test_e2e_flow.py"):
                    self.assertIn(path, self.differs_from_tree(key))  # the oracle
                    self.assertIn(path, files)
                self.assertIsNone(files["tests/test_e2e_flow.py"])
                for path in ("tests/test_a.py", "tests/test_staged.py"):
                    self.assert_refused(*args, "--closed-by", path, why="unchanged since round 1")
        self.repo.write("tests/test_e2e_flow.py", gone)  # restored: absent at the round, present now
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_e2e_flow.py"), 1, self.out)
        self.assertEqual(self.rounds()["confirmations"], {"plan": 2})

    def round_then_change(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertEqual(self.run_review(*TASK), 1)
        self.change_test()  # recorded at round 1, changed now: admitted when the comparison can be made

    def test_a_missing_verdict_tree_refuses(self):
        self.round_then_change()
        bogus = "1" * 40
        self.assertNotEqual(subprocess.run(["git", "cat-file", "-e", f"{bogus}^{{tree}}"], cwd=self.repo.dir,
                                           capture_output=True).returncode, 0)  # the oracle: git cannot read it
        verdict = self.vdir / "T1-boundary.md"
        verdict.write_text(verdict.read_text().replace(goal.read_verdict(verdict)[1], bogus))
        self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="cannot be made")

    def test_a_missing_or_malformed_digest_refuses(self):
        self.round_then_change()
        digest = self.ctx.runs / "review" / "T1-boundary-r1.files.json"
        for text in ("not json", "[]", '{"tests/x.py": 7}', None):
            with self.subTest(text=text):
                digest.unlink(missing_ok=True)
                if text is not None:
                    digest.write_text(text)
                self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="cannot be made")

    def test_a_git_timeout_refuses(self):
        self.round_then_change()
        real = subprocess.run

        def slow(cmd, *a, **kw):
            if list(cmd[:3]) == ["git", "cat-file", "-e"]:
                raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 0)
            return real(cmd, *a, **kw)
        with mock.patch.object(subprocess, "run", slow):
            self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="cannot be made")
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 1, self.out)  # once git answers

    def test_a_failing_ls_files_that_printed_the_path_refuses(self):
        self.round_then_change()
        real = subprocess.run

        def failing(cmd, *a, **kw):
            proc = real(cmd, *a, **kw)
            if list(cmd[:2]) == ["git", "ls-files"] and "--cached" in cmd:
                proc.returncode = 1  # the path is printed, but git reports failure
            return proc
        with mock.patch.object(subprocess, "run", failing):
            self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="cannot be made")

    def test_an_unreadable_recorded_test_refuses(self):
        self.change_test()
        self.assertEqual(self.run_review(*TASK), 1)  # tests/test_a.py is recorded
        self.change_test(n=2)
        target = self.repo.path("tests/test_a.py")
        target.chmod(0)
        self.addCleanup(target.chmod, 0o644)
        self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="cannot be made")

    def inject(self, fail_at, *args):
        """Run a --closed-by review whose fail_at-th probe() call fails; any raw git call or file
        read made by closure_refusal outside probe() fails the test. Returns the probe-call count."""
        state = {"n": 0, "inside": 0, "closure": 0}
        real_probe, real_closure = review.probe, review.closure_refusal

        def probe(*a, **kw):  # counts the comparison's calls only, not the snapshot's
            if not state["closure"]:
                return real_probe(*a, **kw)
            state["n"] += 1
            if state["n"] == fail_at:
                raise review.Unmade("injected")
            state["inside"] += 1
            try:
                return real_probe(*a, **kw)
            finally:
                state["inside"] -= 1

        def closure(*a, **kw):
            state["closure"] += 1
            try:
                return real_closure(*a, **kw)
            finally:
                state["closure"] -= 1

        def guard(owner, name):
            real = getattr(owner, name)

            def call(*a, **kw):
                if state["closure"] and not state["inside"]:
                    raise AssertionError(f"closure_refusal called {name} outside probe()")
                return real(*a, **kw)
            return mock.patch.object(owner, name, call)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(review, "probe", probe))
            stack.enter_context(mock.patch.object(review, "closure_refusal", closure))
            for owner, name in ((subprocess, "Popen"), (os, "listdir"), (os, "scandir"), (os, "lstat"),
                                (os, "stat"), (io, "open"), (builtins, "open")):
                stack.enter_context(guard(owner, name))
            self.code = self.run_review(*args)
        return state["n"]

    def test_every_git_call_and_file_read_of_the_comparison_fails_closed(self):
        # A test new since the round (ls-tree finds it absent) and a recorded one (bytes): every probe point.
        for recorded, points in ((False, 8), (True, 8)):
            with self.subTest(recorded=recorded):
                self.repo = Repo()
                self.addCleanup(self.repo.cleanup)
                self.ctx = goal.find_ctx(argparse.Namespace(plan="docs/plan.md", goal=None), cwd=str(self.repo.dir))
                self.vdir = self.ctx.runs / "verdicts"
                if recorded:
                    self.change_test()
                    self.assertEqual(self.run_review(*TASK), 1)
                    self.change_test(n=2)
                else:
                    self.assertEqual(self.run_review(*TASK), 1)
                    self.repo.write("tests/test_a.py" if recorded else "tests/test_fresh.py", TEST_A)
                args = (*TASK, "--closed-by", "tests/test_a.py" if recorded else "tests/test_fresh.py")
                k = 1
                while True:
                    before = (self.rounds(), len(self.packets))
                    n = self.inject(k, *args)
                    if n < k:  # no point left to fail: the comparison completed and was admitted
                        break
                    self.assertEqual(self.code, 1, self.out)
                    self.assertIn("cannot be made: injected", self.out)
                    self.assertEqual((self.rounds(), len(self.packets)), before)
                    k += 1
                self.assertEqual((k - 1, n), (points, points))  # injection points = calls of a success
                self.assertEqual(self.rounds()["confirmations"], {"T1-boundary": 2})

    def test_a_staged_rename_records_its_source_as_null_so_a_restore_counts(self):
        self.repo.git("mv", "tests/test_a.py", "tests/test_r.py")
        tree = self.repo.tree()
        self.assertNotIn("tests/test_a.py", self.repo.git("diff", "--name-only", tree).splitlines())  # the oracle
        self.assertIn("tests/test_a.py", self.repo.git("diff", "--name-only", "--no-renames", tree).splitlines())
        self.assertEqual(self.run_review(*TASK), 1)
        files = goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json")
        self.assertIsNone(files["tests/test_a.py"])
        self.assertIn("tests/test_r.py", files)
        self.assert_refused(*TASK, "--closed-by", "tests/test_r.py", why="unchanged since round 1")
        self.repo.git("mv", "tests/test_r.py", "tests/test_a.py")  # restored with its original bytes
        self.assertEqual(self.run_review(*TASK, "--closed-by", "tests/test_a.py"), 1, self.out)
        self.assertEqual(self.rounds()["confirmations"], {"T1-boundary": 2})

    def test_index_flags_cannot_hide_an_edited_test(self):
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.repo = Repo()
                self.addCleanup(self.repo.cleanup)
                self.ctx = goal.find_ctx(argparse.Namespace(plan="docs/plan.md", goal=None), cwd=str(self.repo.dir))
                self.vdir = self.ctx.runs / "verdicts"
                self.repo.git("update-index", f"--{flag}", "tests/test_a.py")
                self.change_test()  # edited while the flag hides it from git diff
                self.assertNotIn("tests/test_a.py", self.repo.git("diff", "--name-only", "HEAD").splitlines())
                self.assertEqual(self.run_review(*TASK), 1)
                files = goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json")
                self.assertEqual(files["tests/test_a.py"], hashlib.sha256(self.repo.path("tests/test_a.py").read_bytes()).hexdigest())
                self.repo.git("update-index", f"--no-{flag}", "tests/test_a.py")  # the bytes are unchanged
                self.assert_refused(*TASK, "--closed-by", "tests/test_a.py", why="unchanged since round 1")

    def test_a_git_rm_path_in_the_verdict_tree_is_recorded_as_null(self):
        self.repo.git("rm", "-q", "tests/test_e2e_flow.py")
        self.assertNotIn("tests/test_e2e_flow.py", self.repo.git("ls-files", "--cached").splitlines())
        self.assertEqual(self.run_review(*TASK), 1)
        self.assertIsNone(goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json")["tests/test_e2e_flow.py"])

    def state(self):
        runs = self.ctx.runs
        paths = [*runs.glob("verdicts/*.md"), *runs.glob("verdicts/history/*"), *runs.glob("verdicts/rounds.json"),
                 *runs.glob("review/*.files.json")]
        return {str(q.relative_to(runs)): q.read_bytes() for q in paths}

    def test_a_file_changed_while_the_judge_ran_records_nothing(self):
        self.assertEqual([self.run_review(*PLAN) for _ in range(2)], [1, 1])  # at the cap
        self.during = lambda: self.change_test(n=len(self.packets) + 10)  # every judge call edits a test
        for args in ((*PLAN, "--founder-grant", "Decisions D9"), (*PLAN, "--closed-by", "tests/test_a.py"),
                     ("--kind", "design")):
            with self.subTest(args=args):
                before = self.state()
                self.assertEqual(self.run_review(*args), 2)
                self.assertIn("files changed while the judge ran; nothing recorded — rerun", self.err)
                self.assertEqual(self.state(), before)  # no verdict, history, count, grant, confirmation, digest
        self.assertEqual(self.rounds(), {"plan": 2})
        self.during = None  # the no-drift control: the same calls are now recorded
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py"), 1)
        self.assertEqual(self.run_review(*PLAN, "--founder-grant", "Decisions D9"), 1)
        self.assertEqual(self.run_review("--kind", "design"), 1)
        self.assertEqual(self.rounds(), {"plan": 3, "design": 1, "confirmations": {"plan": 3},
                                         "founder_grants": {"plan": "Decisions D9"}})

    def test_a_force_tracked_test_under_runs_is_refused_like_the_snapshot_excludes_it(self):
        self.repo.write(".runs/t/test_x.py", TEST_A)
        self.repo.git("add", "-f", ".runs/t/test_x.py")
        self.repo.commit("force-track a test under .runs/")
        self.repo.write(".runs/t/test_x.py", TEST_A + "# edited before the round\n")
        self.assertEqual(self.run_review(*TASK), 1)
        self.assertNotIn(".runs/t/test_x.py", goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json"))
        self.assert_refused(*TASK, "--closed-by", ".runs/t/test_x.py", why="not a regular")

    def test_a_tracked_directory_replaced_by_a_file_records_its_children_as_null(self):
        self.repo.write("pkg/test_p.py", TEST_A)
        self.repo.commit("a tracked directory")
        for child in self.repo.path("pkg").iterdir():
            child.unlink()
        self.repo.path("pkg").rmdir()
        self.repo.write("pkg", "now a file\n")
        self.assertEqual(self.run_review(*TASK), 1)  # the ordinary round completes
        files = goal.read_json(self.ctx.runs / "review" / "T1-boundary-r1.files.json")
        self.assertIsNone(files["pkg/test_p.py"])
        self.assertIsNotNone(files["pkg"])
        self.assert_refused(*TASK, "--closed-by", "pkg/test_p.py", why="not a regular")

    def test_a_failed_confirmation_call_consumes_nothing(self):
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py", "--note", "FAIL"), 2)
        self.assertEqual((self.rounds(), self.history("plan")), ({"plan": 1}, ["plan-r1.md"]))
        self.assertFalse((self.ctx.runs / "review" / "plan-r2.files.json").exists())
        self.assertEqual(self.run_review(*PLAN, "--closed-by", "tests/test_a.py"), 1)
        self.assertEqual(self.rounds(), {"plan": 1, "confirmations": {"plan": 2}})

    def test_confirmation_runs_under_the_subject_lock(self):
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        held = review.subject_lock(self.vdir, "plan")
        self.addCleanup(held.close)
        self.assert_refused(*PLAN, "--closed-by", "tests/test_a.py", why="already being reviewed")

    def test_history_that_disagrees_with_rounds_is_not_overwritten(self):
        self.assertEqual(self.run_review(*PLAN), 1)
        self.change_test()
        stray = self.vdir / "history" / "plan-r2.md"
        stray.write_text("VERDICT: PASS\n")
        with self.assertRaises(review.ReviewError):
            self.run_review(*PLAN, "--closed-by", "tests/test_a.py")
        self.assertEqual((stray.read_text(), self.rounds(), len(self.packets)), ("VERDICT: PASS\n", {"plan": 1}, 1))

    def test_an_acceptance_confirmation_needs_a_committed_changed_test(self):
        self.repo.finish_m1()
        self.assertEqual(self.run_review("--kind", "acceptance", "--milestone", "M1"), 1)
        self.assert_refused("--kind", "acceptance", "--milestone", "M1", "--closed-by", "tests/test_a.py",
                            why="unchanged since round 1")
        self.change_test()
        self.repo.commit("[T2] test reproducing the finding")
        self.reply = PASS
        self.assertEqual(self.run_review("--kind", "acceptance", "--milestone", "M1", "--closed-by",
                                         "tests/test_a.py"), 0, self.out)
        self.assertEqual(self.rounds(), {"M1-acceptance": 1, "confirmations": {"M1-acceptance": 2}})


class AcceptanceRangeTest(ClosureCase):
    def test_no_flag_but_a_declared_partition_narrows_the_acceptance_range(self):
        self.repo.finish_m1()
        for diff in ("HEAD..HEAD", "", "goal/F-9/approved..HEAD"):  # even the default range is refused
            with self.subTest(diff=diff), self.assertRaisesRegex(review.ReviewError, "never applies to acceptance"):
                self.run_review("--kind", "acceptance", "--milestone", "M1", "--diff", diff)
        self.repo.git("tag", "goal/F-9/M1")
        with self.assertRaisesRegex(review.ReviewError, "declares acceptance"):
            self.run_review("--kind", "acceptance", "--milestone", "M2", "--partition", "gamma")
        self.assertEqual((self.packets, self.rounds()), ([], {}))
        cwd = os.getcwd()
        os.chdir(self.repo.dir)
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = review.main(["--plan", "docs/plan.md", "--chief", "claude", "--kind", "acceptance",
                                    "--milestone", "M1", "--diff", "HEAD..HEAD"])
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 2, err.getvalue())
        self.assertEqual((self.packets, self.rounds()), ([], {}))


class Injected(Exception):
    pass


class AdmissionContractTest(ClosureCase):
    """Through main(): an invocation carrying --closed-by is admitted (one judge call), a dry run, or
    refused with exit 1, one refusal line, no judge call and the review state unchanged."""
    V = ("--closed-by", "tests/test_a.py")

    def setUp(self):
        super().setUp()
        self.assertEqual([self.run_review(*TASK), self.run_review(*PLAN)], [1, 1])
        self.change_test()  # T1-boundary and plan are each confirmable with tests/test_a.py

    def state(self):
        runs = self.ctx.runs
        paths = [*runs.glob("verdicts/*.md"), *runs.glob("verdicts/history/*"), *runs.glob("verdicts/rounds.json"),
                 *runs.glob("review/*.files.json")]
        return {str(q.relative_to(runs)): q.read_bytes() for q in paths}

    def invoke(self, *argv, chief=True, patches=()):
        cwd, out, err = os.getcwd(), io.StringIO(), io.StringIO()
        os.chdir(self.repo.dir)
        try:
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.dict(os.environ))
                os.environ.pop("GOAL_HARNESS", None)
                stack.enter_context(contextlib.redirect_stdout(out))
                stack.enter_context(contextlib.redirect_stderr(err))
                for patch in patches:
                    stack.enter_context(patch)
                code = review.main(["--plan", "docs/plan.md", *(("--chief", "claude") if chief else ()), *argv])
        finally:
            os.chdir(cwd)
        return code, out.getvalue(), err.getvalue()

    def assert_not_admitted(self, *argv, **kw):
        before, calls = self.state(), len(self.packets)
        code, out, err = self.invoke(*argv, **kw)
        self.assertEqual(code, 1, out + err)
        self.assertEqual([l for l in out.splitlines() if l.startswith("review: refused — ")], out.splitlines())
        self.assertEqual(len(out.splitlines()), 1, out)
        self.assertEqual((len(self.packets), self.state()), (calls, before))

    def test_every_invalid_combination_is_refused_whatever_the_order_of_checks(self):
        V = self.V
        grid = (("--kind", "boundary", *V),  # no --task
                ("--kind", "boundary", "--task", "T99", *V), ("--kind", "boundary", "--task", "bad", *V),
                ("--plan", "docs/nope.md", "--kind", "boundary", "--task", "T1", *V),
                ("--kind", "acceptance", "--milestone", "M1", "--diff", "HEAD..HEAD", *V),
                ("--kind", "acceptance", "--milestone", "M1", *V),  # a dirty tree
                ("--kind", "acceptance", "--milestone", "M9", *V),
                ("--kind", "plan", "--closed-by"), ("--kind", "plan", "--closed-by", "--dry-run"),
                ("--kind", "nope", *V), ("--kind", "boundary", "--closed", "tests/test_a.py"),
                ("--kind", "boundary", "--closed-by=tests/test_a.py"), ("--kind", "design", *V),
                ("--kind", "plan", "--closed-by", "tests/test_e2e_flow.py"), ("--kind", "plan", *V, "--founder-grant", ""),
                ("--kind", "advisor", "--item", "T2", *V), ("--kind", "council", "--member", "2", "--founder-grant", " ", *V),
                ("--kind", "acceptance", "--milestone", "M9", "--partition", "zz", "--diff", "", "--founder-grant", "", *V),
                ("--kind", "boundary", "--task", "T99", "--item", "bad", "--diff", "HEAD..HEAD", "--member", "4", *V),
                ("--goal", "F-0", "--plan", "docs/nope.md", "--kind", "boundary", *V))
        for argv in grid:
            with self.subTest(argv=argv):
                self.assert_not_admitted(*argv)
        with self.subTest("no chief and no harness"):
            self.assert_not_admitted("--kind", "plan", *V, chief=False)

    def test_context_and_preparation_failures_are_refused(self):
        stray = self.vdir / "history" / "plan-r2.md"
        stray.write_text("VERDICT: PASS\n")  # the history guard in admit()
        self.assert_not_admitted("--kind", "plan", *self.V)
        stray.unlink()
        self.repo.write("docs/agents/execution/runtime.json", "{}")  # an unmigrated project
        self.assert_not_admitted("--kind", "plan", *self.V)
        self.repo.path("docs/agents/execution/runtime.json").unlink()
        self.repo.git("checkout", "tests/test_a.py")
        self.repo.finish_m1()
        self.repo.git("tag", "goal/F-9/M1")
        self.assertEqual(self.run_review("--kind", "acceptance", "--milestone", "M2", "--partition", "alpha"), 1)
        self.change_test()
        self.repo.commit("[T3] test reproducing the finding")
        self.repo.git("tag", "-d", "goal/F-9/M1")  # the milestone base tag is gone
        self.assert_not_admitted("--kind", "acceptance", "--milestone", "M2", "--partition", "alpha", *self.V)

    def test_a_fault_at_any_call_before_the_judge_is_a_refusal_then_the_confirmation_is_admitted(self):
        calls = {"n": 0, "fail_at": 0, "fired": False}

        def judge(*a, **kw):
            calls["judging"] = True
            return self.judge(*a, **kw)

        def faulty(owner, name):
            real = getattr(owner, name)

            def call(*a, **kw):
                if not calls.get("judging"):
                    calls["n"] += 1
                    if calls["n"] == calls["fail_at"]:
                        calls["fired"] = True
                        raise Injected(f"{name} #{calls['n']}")
                return real(*a, **kw)
            return mock.patch.object(owner, name, call)
        targets = ((subprocess, "Popen"), (io, "open"), (builtins, "open"), (os, "open"), (os, "stat"), (os, "lstat"),
                   (os, "listdir"), (os, "scandir"), (os, "mkdir"), (os, "getcwd"), (os, "replace"), (os, "unlink"),
                   (fcntl, "flock"))
        k = 0
        while True:
            k += 1
            calls.update(n=0, fail_at=k, fired=False, judging=False)
            patches = [mock.patch.object(review, "run_judge", judge), *(faulty(o, n) for o, n in targets)]
            before, judged = self.state(), len(self.packets)
            code, out, err = self.invoke(*TASK, *self.V, patches=patches)
            if not calls["fired"]:  # k passed every call before the judge: this run was admitted
                break
            with self.subTest(fault=k):
                self.assertEqual((code, len(self.packets), self.state()), (1, judged, before), out + err)
                self.assertTrue(out.startswith("review: refused — "), out)
        self.assertGreater(k, 20)  # a real enumeration of subprocess, open and os calls
        self.points = k - 1
        self.assertEqual((code, len(self.packets) - judged), (1, 1))  # admitted: one judge call, BLOCK
        head = self.head("T1-boundary")
        self.assertEqual((head["round"], head["confirmation"]), ("2", "closed-by tests/test_a.py"))
        self.assertEqual(self.history("T1-boundary"), ["T1-boundary-r1.md", "T1-boundary-r2.md"])
        self.assertEqual(self.rounds()["confirmations"], {"T1-boundary": 2})  # the admitted BLOCK consumed it
        self.assert_not_admitted(*TASK, *self.V)

    def test_controls_dry_run_judge_failure_and_admitted_pass(self):
        before = self.state()
        code, out, _ = self.invoke("--kind", "plan", *self.V, "--dry-run")
        self.assertEqual((code, len(self.packets), self.state()), (0, 2, before))
        self.assertIn("test-closed confirmation", out)
        code, _, err = self.invoke("--kind", "plan", *self.V, "--note", "FAIL")  # admitted; the judge fails
        self.assertEqual((code, len(self.packets), self.state()), (2, 3, before), err)
        self.reply = PASS
        code, out, _ = self.invoke("--kind", "plan", *self.V)
        self.assertEqual((code, len(self.packets)), (0, 4), out)
        self.assertEqual(self.rounds(), {"T1-boundary": 1, "plan": 1, "confirmations": {"plan": 2}})
        self.assertEqual(self.head("plan")["confirmation"], "closed-by tests/test_a.py")


class PacketTest(ClosureCase):
    def test_the_family_instruction_appears_from_round_2(self):
        self.assertEqual([self.run_review(*PLAN) for _ in range(2)], [1, 1])
        self.assertNotIn("family: same as", self.packets[0])
        self.assertNotIn("test-closed confirmation", self.packets[0])
        self.assertIn("`family: same as <finding path>`", self.packets[1])

    def changed(self, rng):
        return len([p for p in self.repo.git("diff", "--name-only", rng).splitlines() if p])

    def test_single_partition_acceptance_reads_subject_paths_but_diffs_the_whole_milestone(self):
        self.repo.finish_m1()
        self.assertEqual(self.run_review("--kind", "acceptance", "--milestone", "M1", "--subject", "src/a/x.py"), 1)
        diff = (self.ctx.runs / "review" / "M1-acceptance-r1.diff").read_text()
        self.assertIn("src/b/y.py", diff)
        m = self.changed("goal/F-9/approved..HEAD")
        self.assertIn(f"diff covers {m} of {m} files changed in M1", self.packets[0])
        self.assertIn("- src/a/x.py", self.packets[0])

    def test_multi_partition_acceptance_filters_to_the_partition_and_counts_it(self):
        self.repo.finish_m1()
        self.repo.git("tag", "goal/F-9/M1")
        self.repo.write("src/c/z.py", "C = 1\n")
        self.repo.write("src/d/w.py", "D = 1\n")
        self.repo.commit("[T3] gamma")
        args = ("--kind", "acceptance", "--milestone", "M2", "--partition")
        self.assertEqual(self.run_review(*args, "alpha", "--subject", "src/c"), 1)
        diff = (self.ctx.runs / "review" / "M2-acceptance-alpha-r1.diff").read_text()
        self.assertIn("src/c/z.py", diff)
        self.assertNotIn("src/d/w.py", diff)
        self.assertIn("diff covers 1 of 2 files changed in M2", self.packets[-1])
        self.assertEqual(self.run_review(*args, "beta", "--subject", "src/none"), 1)  # an empty diff
        self.assertIn("diff covers 0 of 2 files changed in M2", self.packets[-1])

    def test_dry_run_states_coverage_and_writes_no_digest(self):
        self.repo.finish_m1()
        a = review.parser().parse_args(["--chief", "claude", "--kind", "acceptance", "--milestone", "M1", "--dry-run"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(review.review(a, self.ctx), 0)
        m = self.changed("goal/F-9/approved..HEAD")
        self.assertIn(f"diff covers {m} of {m} files changed in M1", out.getvalue())
        self.assertFalse((self.ctx.runs / "review" / "M1-acceptance-r1.files.json").exists())
        self.assertEqual(json.dumps(self.rounds()), "{}")


if __name__ == "__main__":
    unittest.main()
