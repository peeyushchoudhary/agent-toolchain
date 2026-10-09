"""Tests for goal.py and run.sh: the plan parser, lint, the eight done rows, the stop hook, run.sh.

Each case builds a throwaway repository (fixtures/goal_fixture.py) holding goal F-9, tagged
goal/F-9/approved, and plants one way a run could fake progress; the matching done row must name it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import E2E, FULL, GATE, GOAL, Repo, env, plan_text  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
import goal  # noqa: E402
from gate import receipt_path  # noqa: E402

REAL_PLAN = Path(__file__).resolve().parents[4] / "docs" / "goals" / "S-1" / "plan.md"
RUN_SH = GOAL.parent / "run.sh"
PLAN = "docs/goals/F-9/plan.md"
# Assembled so this file does not itself add the marker that row 5 rejects.
SKIP_DECORATOR = "    @unittest." + "skip('later')\n"


class ParseTest(unittest.TestCase):
    def test_parses_this_repositorys_s1_plan(self):
        plan = goal.parse_plan(REAL_PLAN.read_text())
        self.assertEqual(sorted(plan["tasks"], key=lambda t: int(t[1:])), [f"T{n}" for n in range(1, 10)])
        self.assertEqual(plan["milestones"], {
            "M1": {"tasks": ["T1", "T2", "T3", "T4", "T5"], "e2e": "install/tests/e2e_install.sh"},
            "M2": {"tasks": ["T6", "T7", "T8", "T9"],
                   "e2e": "install/skills/execution-methodology/tests/e2e_run.sh"}})
        self.assertEqual(plan["meta"]["protected"], ["docs/decisions/decisions.md#D1-D19"])
        self.assertEqual(plan["meta"]["full_gate"], "cd install && ./install.sh --dry-run && ./verify.sh")
        self.assertIn("install/README.md", plan["tasks"]["T2"]["writes"])
        self.assertIn("install/tests/test_install.py", plan["tasks"]["T2"]["tests-may-change"])
        self.assertEqual(goal.lint(type("C", (), {"plan": plan})()), [])

    def test_flow_values(self):
        self.assertEqual(goal.flow('{tasks: [T1, T2], e2e: "a, b: c"}'), {"tasks": ["T1", "T2"], "e2e": "a, b: c"})
        self.assertEqual(goal.flow("[none]"), ["none"])

    def test_quoted_command_round_trip(self):
        intended = 'true "ignored" && false'
        text = (plan_text().replace(f"gate: {FULL} -q", r'gate: "true \"ignored\" && false"')
                .replace(f'M1: {{tasks: [T1, T2], e2e: "{E2E}"}}',
                         r'M1: {tasks: [T1, T2], e2e: "true \"ignored\" && false"}'))
        plan = goal.parse_plan(text)
        self.assertEqual(plan["meta"]["gate"], intended)
        self.assertEqual(plan["milestones"]["M1"]["e2e"], intended)
        self.assertEqual(plan["milestones"]["M2"]["e2e"], E2E)
        self.assertEqual(goal.flow(r'"a \\ b"'), "a \\ b")
        self.assertEqual(goal.flow("'it''s'"), "it's")
        self.assertEqual(subprocess.run(intended, shell=True).returncode, 1)

    def test_rejects_unconsumed_and_unterminated_flow_values(self):
        for bad in ('"true" && false', "[T1, T2", '{tasks: [T1, T2], e2e: "x"', '{tasks: [T1], e2e: "x" junk}',
                    "[T1] tail"):
            with self.assertRaises(ValueError, msg=bad):
                goal.flow(bad)
        text = (plan_text().replace(f"gate: {FULL} -q", 'gate: "true" && false')
                .replace(f'M1: {{tasks: [T1, T2], e2e: "{E2E}"}}', 'M1: {tasks: [T1, T2], e2e: "true" && false}')
                .replace(f'M2: {{tasks: [T3], e2e: "{E2E}"}}', "M2: {tasks: [T3]"))
        plan = goal.parse_plan(text)
        self.assertNotIn("gate", plan["meta"])
        self.assertEqual(plan["milestones"]["M1"], {"tasks": [], "e2e": ""})
        errs = goal.lint(type("C", (), {"plan": plan})())
        for n in (4, 7, 8):
            self.assertTrue(any(e.startswith(f"line {n}: ") for e in errs), (n, errs))


class RepoCase(unittest.TestCase):
    plan = None

    def setUp(self):
        self.repo = Repo(self.plan)
        self.addCleanup(self.repo.cleanup)

    def done(self):
        res = self.repo.goal("done")
        return res.returncode, {line.split(":")[0].split(" ok")[0]: line for line in res.stdout.splitlines()
                                if line.startswith("row ")}, res

    def assertRow(self, n, text=None):
        code, rows, res = self.done()
        self.assertEqual(code, 1, res.stdout + res.stderr)
        self.assertNotIn("ok", rows[f"row {n}"].split(":")[0], res.stdout)
        if text:
            self.assertIn(text, rows[f"row {n}"], res.stdout)

    def assertRowOk(self, n):
        _code, rows, res = self.done()
        self.assertEqual(rows[f"row {n}"], f"row {n} ok", res.stdout + res.stderr)

    def fix(self, path, text, subject):
        self.repo.write(path, text)
        return self.repo.commit(subject)


class LintTest(RepoCase):
    plan = (plan_text().replace("  M2: {tasks: [T3], e2e: \"" + E2E + "\"}", "  M2: {tasks: [T9]}")
            .replace("touches: [none]\n", "").replace("writes: src/c/**", "writes: docs/**"))

    def test_lint_names_each_planted_defect(self):
        self.repo.edit(PLAN, "writes: src/a/**, tests/**\n", "")
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        for text in ("T3: in no milestone", "M2: names missing task T9", "M2: no e2e", "T1: no writes",
                     "frontmatter: touches is missing", "T3: writes intersect protected"):
            self.assertIn(text, res.stdout)

    def test_the_fixture_plan_lints_clean(self):
        self.repo.write(PLAN, plan_text())
        self.assertEqual(self.repo.goal("lint").returncode, 0)


class DoneTest(RepoCase):
    def test_all_green_prints_done(self):
        self.repo.close()
        code, rows, res = self.done()
        self.assertEqual(code, 0, res.stdout + res.stderr)
        self.assertEqual(list(rows.values()), [f"row {n} ok" for n in range(1, 9)])
        self.assertIn(f"DONE M1 on tree {self.repo.tree()}", res.stdout)

    def test_unticked_tasks_and_a_dirty_tree(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertRow(1, "T1 is not [x]")
        self.assertRow(2, "uncommitted")

    def test_parked_task_needs_a_parked_line(self):
        self.repo.tick("T2", "!")
        self.repo.commit("F-9: park T2")
        self.assertRow(1, "T2 is parked without a Parked line")
        self.repo.edit(PLAN, "## Parked\n", "## Parked\n\n- T2: needs the founder.\n")
        self.repo.commit("F-9: park T2 with a line")
        _c, rows, _r = self.done()
        self.assertNotIn("T2", rows["row 1"])

    def test_row3_accepts_a_plan_only_tick_and_rejects_a_prose_edit(self):
        self.repo.tick("T1")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- later.\n")
        self.repo.commit("F-9: tick T1, a decision")
        self.assertRowOk(3)
        self.repo.edit(PLAN, "Do the beta work.", "Do the beta work differently.")
        self.repo.commit("F-9: reword T2")
        self.assertRow(3, "not plan-only")
        self.assertRow(6)

    def test_row4_judges_writes_at_the_parent_despite_a_later_widening(self):
        sha = self.fix("src/b/z.py", "Z = 1\n", "[T1] alpha, reaching into src/b")
        self.repo.edit(PLAN, "writes: src/a/**, tests/**", "writes: src/a/**, src/b/**, tests/**")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- widen T1.\n")
        self.repo.commit("F-9: widen T1 writes")
        self.assertRowOk(3)
        self.assertRow(4, f"{sha[:10]} [T1] src/b/z.py outside writes")

    def test_temporary_widening_cannot_authorize_protected_edits(self):
        self.repo.edit(PLAN, "writes: src/a/**, tests/**", "writes: src/a/**, docs/design.md, tests/**")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- widen T1.\n")
        self.repo.commit("F-9: widen T1 to the design")
        sha = self.fix("docs/design.md", "# design, rewritten\n", "[T1] alpha rewrites the design")
        self.repo.edit(PLAN, "writes: src/a/**, docs/design.md, tests/**", "writes: src/a/**, tests/**")
        self.repo.edit(PLAN, "- widen T1.\n", "- widen T1.\n- narrow T1 again.\n")
        self.repo.commit("F-9: narrow T1 again")
        self.assertRowOk(3)
        self.assertRow(4, f"{sha[:10]} [T1] changes protected docs/design.md")

    def test_plan_only_cannot_expand_test_permissions(self):
        self.repo.edit(PLAN, "tests-may-change: tests/test_a.py", "tests-may-change: **")
        sha = self.repo.commit("F-9: let T2 change every test")
        self.assertRow(3, f"{sha[:10]} changes writes or tests-may-change without adding a Decisions line")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.repo.edit(PLAN, "tests-may-change: tests/test_a.py", "tests-may-change: **")
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n",
                       "- 2026-01-01: fixture decision.\n- T2 may change every test.\n")
        sha = self.repo.commit("F-9: let T2 change every test, with a decision")
        self.assertRowOk(3)
        self.repo.goal("packet")
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertIn(f"{sha[:10]} T2 tests-may-change: tests/test_a.py -> **", packet)
        self.assertIn("Widenings", packet)

    def test_row5_names_an_added_skip_marker(self):
        text = self.repo.read("tests/test_a.py").replace("    def test_flag", SKIP_DECORATOR + "    def test_flag")
        self.fix("tests/test_a.py", text, "[T2] beta")  # T2 may change tests/test_a.py
        self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")

    def test_row5_rejects_imported_skip_and_spaced_only(self):
        at = "@"  # assembled so this file does not itself add the markers row 5 rejects
        for line in (f"{at}skip('later')", f"{at}skipIf(True, 'x')", f"{at}skipUnless (False, 'x')",
                     f"{at}expectedFailure", "test.only" + " ('case', fn)", "it.skip" + " ('case', fn)",
                     "describe.only" + "\t('suite', fn)"):
            self.assertTrue(goal.SKIP_RE.search(line), line)
        for line in ("def skipper(self):", "only = 1", "x.onlyone(1)"):
            self.assertFalse(goal.SKIP_RE.search(line), line)
        text = ("from unittest import " + "skip\n" + self.repo.read("tests/test_a.py")
                .replace("    def test_flag", f"    {at}skip('later')\n    def test_flag"))
        self.fix("tests/test_a.py", text, "[T2] beta")
        self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")

    def test_row5_rejects_spaced_and_imported_skip_calls(self):
        # Each call is assembled so this file does not itself add the marker row 5 rejects.
        for line in ("pytest.skip" + ' ("later")', "self.skipTest" + ' ("later")', "pytest.xfail" + "\t('x')"):
            self.assertTrue(goal.SKIP_RE.search(line), line)
        base = self.repo.read("tests/test_a.py")
        for head, call in (("", "pytest.skip" + ' ("later")'), ("", "self.skipTest" + ' ("later")'),
                           ("from pytest import " + "skip\n", "skip" + '("later")'),
                           ("from unittest import (\n    " + "skip,\n)\n", "skip" + ' ("later")')):
            text = head + base.replace("        self.assertFalse", f"        {call}\n        self.assertFalse")
            self.fix("tests/test_a.py", text, "[T2] beta")
            self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")
            self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.fix("tests/test_a.py", base.replace("    def test_flag", "    def skip(self):\n        pass\n\n"
                                                 "    def test_flag"), "[T2] beta, a helper named like a skip")
        self.assertRowOk(5)

    def test_row5_names_a_test_modified_outside_tests_may_change(self):
        self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T1] alpha")
        self.assertRow(5, "modifies test tests/test_a.py")

    def test_row6_names_an_outcome_edit(self):
        self.repo.edit(PLAN, "The fixture does two things.", "The fixture does one thing.")
        self.repo.commit("[T1] alpha")
        self.assertRow(6, "changed outside ticks")

    def test_outcome_field_like_lines_remain_frozen(self):
        self.repo.edit(PLAN, "The fixture does two things.\n",
                       "The fixture does two things.\nwrites: must preserve customer records\n")
        self.repo.commit("F-9: approve an outcome with a field-like line")
        self.repo.git("tag", "-f", "goal/F-9/approved")
        self.repo.edit(PLAN, "writes: must preserve", "writes: may erase")
        sha = self.repo.commit("F-9: reword the outcome")
        self.assertRow(3, f"{sha[:10]} names 0 tasks and is not plan-only")
        self.assertRow(6, "changed outside ticks")
        before = goal.frozen_view(plan_text())
        self.assertEqual(goal.frozen_view(plan_text().replace("writes: src/a/**", "writes: src/a/**, src/z/**")),
                         before)

    def test_row7_receipt_must_name_heads_tree(self):
        self.repo.close()
        path = receipt_path(self.repo.dir, "F-9", self.repo.tree(), FULL)
        good = path.read_text()
        path.write_text(json.dumps({**json.loads(good), "tree": "0" * 40}))
        self.assertRow(7, "no PASS full_gate receipt")
        path.write_text(good)
        self.assertRowOk(7)


RECORD = ("# Record\n\n## D1 — first\n\nOne.\n\n### detail\n\nInside D1.\n\n## D2 — second\n\nTwo.\n\n"
          "## D3 — third\n\nThree.\n")


class ProtectedSectionTest(RepoCase):
    plan = (plan_text().replace("protected: [docs/design.md]", "protected: [docs/design.md, docs/record.md#D1-D2]")
            .replace("writes: src/a/**, tests/**", "writes: src/a/**, docs/record.md, tests/**"))

    def setUp(self):
        self.repo = Repo(self.plan, files={"docs/record.md": RECORD})
        self.addCleanup(self.repo.cleanup)

    def test_protected_section_edit_is_rejected(self):
        self.assertEqual(self.repo.goal("lint").returncode, 0)
        self.fix("docs/record.md", RECORD.replace("Three.", "Three, revised."), "[T1] outside the range")
        self.assertRowOk(4)
        sha = self.fix("docs/record.md", self.repo.read("docs/record.md").replace("Inside D1.", "Changed."),
                       "[T1] inside D1")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected docs/record.md#D1-D2")
        self.assertEqual(goal.protected_text(RECORD, "D2"), "## D2 — second\n\nTwo.\n")
        self.assertEqual(goal.protected_text(RECORD, "whole"), RECORD.rstrip("\n"))


class ReviewRowTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.repo.close()

    def test_a_non_fix_commit_after_reviewed_is_named(self):
        sha = self.fix("src/b/w.py", "W = 1\n", "[T2] more beta")
        self.assertRow(8, f"{sha[:10]} after reviewed: is neither a fix commit")

    def test_row8_accepts_plan_only_commit_after_review(self):
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- reviewed.\n")
        self.repo.commit("F-9: record the review verdict")
        self.assertRowOk(8)
        self.repo.edit(PLAN, "- reviewed.\n", "- reviewed.\n- again.\n")
        self.repo.write("docs/design.md", "# design, edited\n")
        sha = self.repo.commit("F-9: a decision and a design edit")
        self.assertRow(8, f"{sha[:10]} after reviewed: is neither a fix commit named by a closed finding nor plan-only")

    def test_checked_blocker_requires_closure(self):
        self.repo.review("- [x] BLOCKING R1 defect still present\n")
        self.assertRow(8, "R1: checked BLOCKING without a resolved-by or removed-by closure")
        self.repo.write("tests/test_b_value.py", "import unittest\n\n\nclass V(unittest.TestCase):\n"
                        "    def test_beta_value(self):\n        self.assertTrue(True)\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix the beta value")
        self.repo.review(f"- [x] BLOCKING R1 defect fixed\n"
                         f"- [x] R1 resolved-by {sha} closes tests/test_b_value.py::test_beta_value\n", "HEAD~1")
        self.assertRowOk(8)

    def test_a_fix_without_a_changed_closing_test_is_named(self):
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix the beta value")
        self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/test_a.py::test_value\n", "HEAD~1")
        self.assertRow(8, "R1: closes tests/test_a.py::test_value")

    def test_a_fix_whose_closing_test_changed_in_it_passes(self):
        self.repo.write("tests/test_b_value.py", "import unittest\n\n\nclass V(unittest.TestCase):\n"
                        "    def test_beta_value(self):\n        self.assertTrue(True)\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix the beta value")
        self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/test_b_value.py::test_beta_value\n", "HEAD~1")
        self.assertRowOk(8)

    def test_closure_rejects_non_test_text(self):
        self.repo.write("README.md", "# test_security is still TODO\n")
        self.repo.write("tests/test_notes.py", "# test_security is still TODO\n")
        self.repo.write("tests/test_c.js", "test('security holds', () => {});\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] claim a fix")
        for target in ("README.md::test_security", "tests/test_notes.py::test_security"):
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRow(8, f"R1: closes {target}")
        self.repo.review(f"- [x] R1 resolved-by {sha} closes tests/test_c.js::security\n", "HEAD~1")
        self.assertRow(8, "R1: closes tests/test_c.js::security")

    def test_closure_requires_an_exact_discoverable_test(self):
        self.repo.write("tests/test_c.js", "test('security holds', () => {});\n")
        self.repo.write("tests/test_e.js", 'it("exact", () => {});\n')
        self.repo.write("tests/test_d.py", "import unittest\n\n\ndef helper_check():\n    pass\n\n\n"
                        "class Guard(unittest.TestCase):\n    def test_guard(self):\n        helper_check()\n\n\n"
                        "class Other(unittest.TestCase):\n    async def test_other(self):\n        pass\n")
        sha = self.fix("src/b/y.py", "B = 2\n", "[T2][R1] fix with tests")
        for target in ("tests/test_c.js::security", "tests/test_d.py::helper_check",
                       "tests/test_d.py::Other.test_guard", "tests/test_d.py::Guard.test_missing"):
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRow(8, f"R1: closes {target}")
        for target in ("tests/test_e.js::exact", "tests/test_d.py::test_guard", "tests/test_d.py::Guard.test_guard",
                       "tests/test_d.py::Other::test_other"):
            self.repo.review(f"- [x] R1 resolved-by {sha} closes {target}\n", "HEAD~1")
            self.assertRowOk(8)

    def test_closure_requires_a_post_review_ancestor_fix(self):
        old = self.repo.git("rev-parse", "goal/F-9/approved")  # it added tests/test_a.py::test_value
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {old} closes tests/test_a.py::test_value\n")
        self.assertRow(8, f"R1: {old} is not a fix made after reviewed:")
        self.repo.git("checkout", "-q", "-b", "side")
        side = self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T2][R1] fix on a side branch")
        self.repo.git("checkout", "-q", "main")
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {side} closes tests/test_a.py::test_value\n")
        self.assertRow(8, f"R1: {side} is not a fix made after reviewed:")
        head = self.repo.git("rev-parse", "HEAD")
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {head} closes tests/test_a.py::test_value\n")
        self.assertRow(8, f"R1: {head} is not a fix made after reviewed:")
        fix = self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T2][R1] fix after the review")
        self.repo.review(f"- [x] BLOCKING R1 defect\n- [x] R1 resolved-by {fix} closes tests/test_a.py::test_value\n",
                         "HEAD~1")
        self.assertRowOk(8)

    def test_removed_by_passes_when_the_paths_are_deleted(self):
        self.repo.git("rm", "-q", "src/b/y.py")
        sha = self.repo.commit("[T2][R1] remove the beta file")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/y.py\n", "HEAD~1")
        self.assertRowOk(8)
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/a/x.py\n", "HEAD~1")
        self.assertRow(8, "does not remove or change")

    def test_removed_by_rejects_addition_only_modification(self):
        sha = self.fix("src/b/y.py", "B = 1\nUNRELATED = 1\n", "[T2][R1] add beside the defect")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/y.py\n", "HEAD~1")
        self.assertRow(8, f"R1: {sha[:8]} does not remove or change the finding's paths")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        sha = self.fix("src/b/y.py", "", "[T2][R1] remove the defective line")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/*.py\n", "HEAD~1")
        self.assertRowOk(8)

    def test_an_open_blocking_finding_is_named(self):
        self.repo.review("- [ ] BLOCKING R2 the beta value is wrong\n")
        self.assertRow(8, "open - [ ] BLOCKING")

    def test_a_missing_review_is_named(self):
        (self.repo.dir / ".runs/F-9/review.md").unlink()
        self.assertRow(8, "no .runs/F-9/review.md")


class StopHookTest(RepoCase):
    def hook(self, cwd=None, session="s1", args=()):
        return subprocess.run([sys.executable, str(GOAL), *args, "stop-hook"], cwd=cwd or self.repo.dir, env=env(),
                              input=json.dumps({"session_id": session}), capture_output=True, text=True)

    def test_stop_hook_honors_explicit_goal_with_multiple_plans(self):
        self.repo.write("docs/goals/G-2/plan.md", plan_text().replace("goal: F-9", "goal: G-2"))
        self.repo.commit("F-9: a second open goal")
        for args, gid in ((("--goal", "F-9"), "F-9"), (("--goal", "G-2"), "G-2"), (("--plan", PLAN), "F-9")):
            block = json.loads(self.hook(args=args).stdout)
            self.assertEqual(block["decision"], "block")
            self.assertIn(f"Goal {gid} is not done", block["reason"])
        first, second = self.hook(session="s9"), self.hook(session="s9")
        self.assertEqual(json.loads(first.stdout), {
            "decision": "block", "reason": "several open plans; register the hook with --goal <id>"})
        self.assertEqual((second.returncode, second.stdout), (0, ""))
        settings = RUN_SH.read_text()
        self.assertIn("--goal %s stop-hook", settings)

    def test_blocks_three_times_then_allows(self):
        outs = [self.hook() for _ in range(4)]
        for res in outs[:3]:
            block = json.loads(res.stdout)
            self.assertEqual(block["decision"], "block")
            self.assertIn("row 1: T1 is not [x]", block["reason"])
        self.assertEqual((outs[3].returncode, outs[3].stdout), (0, ""))
        self.assertIn("block", self.hook(session="s2").stdout)

    def test_allows_where_there_is_no_plan(self):
        bare = Path(tempfile.mkdtemp(prefix="goal-bare-"))
        self.addCleanup(shutil.rmtree, bare, True)
        subprocess.run(["git", "init", "-q"], cwd=bare, check=True)
        res = self.hook(cwd=bare)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))

    def test_allows_when_done(self):
        self.repo.close()
        self.assertEqual(self.hook().stdout, "")


FAKE_HARNESS = """import pathlib, re, subprocess, sys
plan = pathlib.Path("docs/goals/F-9/plan.md")
text = plan.read_text()
tid = re.search(r"^### \\[ \\] (T[12]) ", text, re.M).group(1)
pathlib.Path(f"src/{tid}.py").parent.mkdir(exist_ok=True)
pathlib.Path(f"src/{tid}.py").write_text("x = 1\\n")
plan.write_text(text.replace(f"### [ ] {tid} ", f"### [x] {tid} "))
subprocess.run(["git", "add", "-A"], check=True)
subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", f"[{tid}] work"], check=True)
if tid == "T2":
    for cmd, name in ((%r, "full_gate"), (%r, "e2e")):
        subprocess.run([sys.executable, %r, "receipt", "--goal", "F-9", "--cmd", cmd, "--name", name],
                       check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    pathlib.Path(".runs/F-9/review.md").write_text("reviewed: " + head + "\\nNo findings.\\n")
"""


LATE_REVIEW = """import pathlib
calls = pathlib.Path(".runs/F-9/calls")
n = int(calls.read_text()) + 1 if calls.exists() else 1
calls.write_text(str(n))
if n == 2:
    pathlib.Path(".runs/F-9/review.saved").rename(".runs/F-9/review.md")
"""


class RunShTest(RepoCase):
    plan = plan_text().replace("src/a/**, tests/**", "src/**").replace("src/b/**, tests/**", "src/**")

    def run_sh(self, harness_cmd):
        return subprocess.run(["bash", str(RUN_SH), "F-9", "--harness", "claude", "--sessions", "4"],
                              cwd=self.repo.dir, capture_output=True, text=True, timeout=300,
                              env=env(RUN_HARNESS_CMD=harness_cmd, RUN_NO_NOTIFY="1"))

    def test_done_after_two_sessions_and_stalled_with_a_no_op(self):
        fake = self.repo.dir.parent / f"{self.repo.dir.name}-fake.py"
        self.addCleanup(lambda: fake.unlink(missing_ok=True))
        fake.write_text(FAKE_HARNESS % (FULL, E2E, str(GATE)))
        res = self.run_sh(f"{sys.executable} {fake}")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip().splitlines()[-1], "DONE")
        progress = self.repo.read(".runs/F-9/progress.md")
        self.assertEqual(progress.count(" session "), 2, progress)
        self.assertIn("DONE M1", self.repo.read(".runs/F-9/packet.md"))
        self.assertTrue(os.access(RUN_SH, os.X_OK))

        other = Repo(self.plan)
        self.addCleanup(other.cleanup)
        res = subprocess.run(["bash", str(RUN_SH), "F-9", "--harness", "codex"], cwd=other.dir, timeout=300,
                             capture_output=True, text=True, env=env(RUN_HARNESS_CMD="true", RUN_NO_NOTIFY="1"))
        self.assertEqual((res.returncode, res.stdout.strip()), (3, "STALLED"), res.stderr)

    def test_done_takes_precedence_over_stalled(self):
        self.repo.close()  # ticks, commits, receipts: done holds except for the review
        self.repo.path(".runs/F-9/review.md").rename(self.repo.path(".runs/F-9/review.saved"))
        fake = self.repo.dir.parent / f"{self.repo.dir.name}-late.py"
        self.addCleanup(lambda: fake.unlink(missing_ok=True))
        fake.write_text(LATE_REVIEW)  # session 1 does nothing; session 2 only lands the review
        res = self.run_sh(f"{sys.executable} {fake}")
        self.assertEqual((res.returncode, res.stdout.strip().splitlines()[-1]), (0, "DONE"), res.stdout + res.stderr)
        self.assertEqual(self.repo.read(".runs/F-9/progress.md").count(" session "), 2)
        self.assertIn("DONE M1", self.repo.read(".runs/F-9/packet.md"))


if __name__ == "__main__":
    unittest.main()
