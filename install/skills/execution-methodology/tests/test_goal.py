"""Tests for goal.py: the plan parser, lint, the eight done rows, the packet, cost from planted transcripts.

Each case builds a throwaway repository (fixtures/goal_fixture.py) holding goal F-9, tagged
goal/F-9/approved, and plants one way a run could fake progress; the matching done row must name it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import DESIGN, E2E, FULL, GOAL, SPEC, V71_FILES, Repo, env, plan_text  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
import goal  # noqa: E402
from gate import receipt_path  # noqa: E402

REAL_PLAN = Path(__file__).resolve().parents[4] / "docs" / "goals" / "S-1" / "plan.md"
S2_PLAN = REAL_PLAN.parents[1] / "S-2" / "plan.md"
PLAN = "docs/goals/F-9/plan.md"
SPEC_PATH, DESIGN_PATH = "docs/goals/F-9/spec.md", "docs/goals/F-9/design.md"
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

    def test_parses_this_repositorys_s2_plan(self):
        plan = goal.parse_plan(S2_PLAN.read_text())
        self.assertEqual(sorted(plan["tasks"], key=lambda t: int(t[1:])), [f"T{n}" for n in range(1, 12)])
        self.assertEqual(sorted(plan["milestones"]), ["M1", "M2"])
        self.assertEqual([t for t, task in plan["tasks"].items() if not task["reads"]], [])
        self.assertIn("docs/goals/S-2/spec.md", plan["tasks"]["T2"]["reads"])
        self.assertEqual(goal.lint(goal.find_ctx(goal="S-2", cwd=S2_PLAN.parent)), [])

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


class SpecLintTest(RepoCase):
    """A v7.1 goal: the fixture goal with spec.md and design.md, T1 may write the design."""
    plan = plan_text(v71=True).replace("writes: src/a/**, tests/**", f"writes: src/a/**, {DESIGN_PATH}, tests/**")

    def setUp(self):
        self.repo = Repo(self.plan, files=V71_FILES)
        self.addCleanup(self.repo.cleanup)

    def assertLint(self, code, *texts):
        res = self.repo.goal("lint")
        self.assertEqual(res.returncode, code, res.stdout + res.stderr)
        for text in texts:
            self.assertIn(text, res.stdout)
        return res.stdout

    def test_the_v71_fixture_lints_clean_and_prints_reads(self):
        self.assertLint(0, f"T1 reads: {DESIGN_PATH}#interfaces", f"T3 reads: {DESIGN_PATH}#interfaces")

    def test_a_task_without_reads_fails_lint(self):
        self.repo.edit(PLAN, f"writes: src/c/**\nreads: {DESIGN_PATH}#interfaces\n", "writes: src/c/**\n")
        out = self.assertLint(1, "T3: writes and no reads")
        self.assertNotIn("T1: writes and no reads", out)

    def test_a_new_goal_without_a_spec_fails_lint(self):
        self.repo.path(SPEC_PATH).unlink()
        self.repo.git("tag", "-d", "goal/F-9/approved")
        self.assertLint(1, "no spec.md and no approval tag")

    def test_deleting_an_approved_spec_fails_lint(self):
        self.repo.path(SPEC_PATH).unlink()
        self.assertLint(1, f"{SPEC_PATH}: in the approved commit, missing from the tree")

    def test_a_401_word_spec_fails_lint(self):
        pad = " word" * (400 - len(SPEC.split()))
        self.repo.write(SPEC_PATH, SPEC.replace("Standard-library Python.", "Standard-library Python." + pad))
        self.assertLint(0)
        self.repo.write(SPEC_PATH, SPEC.replace("Standard-library Python.", "Standard-library Python. word" + pad))
        self.assertLint(1, "spec.md: 401 words, over 400")

    def test_a_spec_missing_non_goals_fails_lint(self):
        self.repo.write(SPEC_PATH, SPEC.replace("**Non-goals.** Gamma.\n\n", ""))
        out = self.assertLint(1, "spec.md: no Non-goals heading")
        self.assertNotIn("no Constraints heading", out)
        criteria = SPEC[SPEC.index("- AC1"):SPEC.index("\n\n**Non-goals")]
        self.repo.write(SPEC_PATH, f"What changes for the user: nothing\n{criteria}\n")
        self.assertLint(0)

    def test_abbreviated_spec_without_tests_fails_lint(self):
        self.repo.write(SPEC_PATH, "What changes for the user: nothing.\n")
        self.assertLint(1, "spec.md: two-line form with no criteria line")
        self.repo.write(SPEC_PATH, "What changes for the user: nothing\nAcceptance criteria: tests/test_a.py::test_alpha\n")
        self.assertLint(0)

    def test_touches_an_interface_without_a_design_fails_lint(self):
        self.repo.path(DESIGN_PATH).unlink()
        self.assertLint(1, "touches: [interface] without design.md")
        self.repo.edit(PLAN, "touches: [interface]", "touches: [none]")
        self.assertLint(0)
        self.repo.edit(PLAN, "touches: [none]", "touches: [none, sideways]")
        self.assertLint(1, "touches: unknown value 'sideways'")

    def test_mapping_touches_fails_lint(self):
        self.repo.edit(PLAN, "touches: [interface]", "touches: {kind: interface}")
        self.assertLint(1, "touches: {'kind': 'interface'} is not a list")

    def test_an_untraced_ac_fails_lint(self):
        self.repo.write(SPEC_PATH, SPEC.replace("\n\n**Non-goals.**", "\n- AC3 WHEN gamma runs THE SYSTEM SHALL do it."
                                                "\n\n**Non-goals.**"))
        out = self.assertLint(1, "AC3: in no task")
        self.assertNotIn("AC1: in no task", out)

    def test_a_reads_change_in_a_plan_only_commit_needs_a_decision(self):
        old, new = f"reads: {DESIGN_PATH}#interfaces", f"reads: {DESIGN_PATH}#interfaces, src/b/**"
        self.repo.edit(PLAN, old, new)  # the first reads: line is T1's
        sha = self.repo.commit("F-9: T1 reads beta")
        self.assertRow(3, f"{sha[:10]} changes writes or tests-may-change without adding a Decisions line")
        self.repo.git("reset", "-q", "--hard", "HEAD~1")
        self.repo.edit(PLAN, old, new)
        self.repo.edit(PLAN, "- 2026-01-01: fixture decision.\n", "- 2026-01-01: fixture decision.\n- T1 reads beta.\n")
        sha = self.repo.commit("F-9: T1 reads beta, with a decision")
        self.assertRowOk(3)
        self.repo.goal("packet")
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertIn(f"{sha[:10]} T1 reads: {DESIGN_PATH}#interfaces -> {DESIGN_PATH}#interfaces, src/b/**", packet)
        self.assertIn(f"T1 reads: {DESIGN_PATH}#interfaces, src/b/**\n", packet)

    def test_row4_reports_a_spec_edit_that_protected_does_not_list(self):
        self.assertEqual(goal.parse_plan(self.plan)["meta"]["protected"], ["docs/design.md"])
        sha = self.fix(SPEC_PATH, SPEC.replace("Gamma.", "Gamma and delta."), "[T1] alpha edits the spec")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {SPEC_PATH}")

    def test_row4_protects_the_designs_interfaces_and_data_touched_sections_only(self):
        self.fix(DESIGN_PATH, DESIGN.replace("One file.", "Two files."), "[T1] outside the protected sections")
        self.assertRowOk(4)
        sha = self.fix(DESIGN_PATH, self.repo.read(DESIGN_PATH).replace("Inside the Interfaces", "Inside, changed,"),
                       "[T1] inside a subsection of Interfaces")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {DESIGN_PATH}#interfaces")
        self.assertNotIn("#data-touched", self.done()[1]["row 4"])
        self.assertEqual(goal.protected_text(DESIGN, "data-touched"), "## Data touched\n\nNothing in a store.\n")
        self.assertEqual(goal.protected_text(DESIGN, "interfaces"), DESIGN[DESIGN.index("## Interfaces"):
                                                                          DESIGN.index("## Data")].rstrip("\n") + "\n")


    def test_slug_is_docs_pys_rule(self):
        import docs
        self.assertEqual(goal.slug("D18: Other, thing!"), docs.slug("D18: Other, thing!"))
        self.assertNotIn('re.sub(r"[`*_~]"', Path(goal.__file__).read_text(encoding="utf-8"))

    def test_row4_protects_interfaces_after_fenced_heading(self):
        design = DESIGN.replace("1. **alpha.** One function.\n",
                                "1. **alpha.** One function.\n\n~~~\n## Example\n~~~\n\nContract text.\n")
        self.assertIn("Contract text.", goal.protected_text(design, "interfaces"))
        self.fix(DESIGN_PATH, design, "[T1] a fenced example inside Interfaces")
        sha = self.fix(DESIGN_PATH, design.replace("Contract text.", "Changed contract."),
                       "[T1] edits the text after the fenced heading")
        self.assertRow(4, f"{sha[:10]} [T1] changes protected {DESIGN_PATH}#interfaces")


    def test_approval_page_renders_spec_design_tasks_and_questions(self):
        self.repo.write(PLAN, self.plan + "\n- Q: Should gamma <wait> for beta?\n")
        res = self.repo.goal("packet", "--approval")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout.strip(), str(self.repo.path(".runs/F-9/approval.html")))
        self.assertFalse(self.repo.path(".runs/F-9/packet.md").exists())
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertIn("<title>F-9 approval</title>", page)
        self.assertIn("The fixture user has two problems.", page)
        self.assertIn("<li>AC1 WHEN alpha runs THE SYSTEM SHALL do the alpha work.</li>", page)
        self.assertIn("1. **alpha.** One function.", page)
        self.assertIn("Inside the Interfaces section.", page)
        self.assertNotIn("Nothing in a store.", page)
        for tid in ("T1", "T2", "T3"):
            self.assertRegex(page, rf"<tr><td>{tid} [^\n]*{re.escape(DESIGN_PATH)}#interfaces")
        self.assertRegex(page, r"<tr><td>T2 [^\n]*<td>tests/test_a.py</td></tr>")  # no test named: its files
        self.assertIn("touches: interface", page)
        self.assertIn("protected: docs/design.md", page)
        self.assertIn("<li>Q: Should gamma &lt;wait&gt; for beta?</li>", page)
        self.assertNotIn("<wait>", page)


    def test_approval_page_preserves_explicit_named_tests(self):
        plan = self.plan.replace("Do the alpha AC1 work.", "`tests/test_a.py` gains `test_alpha_adds_the_module`.")
        plan = plan.replace("Do the gamma work.", "Named test: tests/test_a.py::ATest.test_gamma_wires_it; see tests/test_b.py.")
        self.repo.write(PLAN, plan)
        res = self.repo.goal("packet", "--approval")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        page = self.repo.read(".runs/F-9/approval.html")
        self.assertRegex(page, r"<tr><td>T1 [^\n]*<td>test_alpha_adds_the_module</td></tr>")
        self.assertRegex(page, r"<tr><td>T3 [^\n]*<td>test_gamma_wires_it</td></tr>")
        self.assertNotRegex(page, r"<td>test_a</td>|<td>test_b</td>")


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


    def test_packet_counts_causes_over_closed_blocking_findings(self):
        sha = self.repo.git("rev-parse", "HEAD")
        self.repo.review(f"- [x] BLOCKING R1 the alpha value is wrong\n"
                         f"- [x] R1 resolved-by {sha} closes tests/test_a.py::test_value cause: logic\n"
                         f"- [x] BLOCKING R2 the beta file is unneeded\n"
                         f"- [x] R2 removed-by {sha} cause: context\n  paths: src/b/y.py\n"
                         f"- [x] R3 a naming nit\n"
                         f"- [x] R3 resolved-by {sha} closes tests/test_a.py::test_flag cause: spec\n", "HEAD~1")
        res = self.repo.goal("packet")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("cause: context 1, logic 1, spec 0\n", self.repo.read(".runs/F-9/packet.md"))


def jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


class CostTest(RepoCase):
    """Transcripts planted under a scratch HOME and CODEX_HOME; the numbers are synthetic."""

    def setUp(self):
        super().setUp()
        self.home = Path(tempfile.mkdtemp(prefix="goal-home-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.codex = self.home / "codex"
        approved = datetime.fromisoformat(self.repo.git("log", "-1", "--format=%cI", "goal/F-9/approved"))
        self.before, self.after = (
            (approved + timedelta(hours=h)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") for h in (-24, 1))

    def cost(self, *args):
        return self.repo.goal(*args, HOME=str(self.home), CODEX_HOME=str(self.codex))

    def plant(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.dir))
        usage = lambda i, c, r, o: {"input_tokens": i, "cache_creation_input_tokens": c,  # noqa: E731
                                    "cache_read_input_tokens": r, "output_tokens": o}
        msg = lambda t, mid, u: {"type": "assistant", "timestamp": t, "message": {"id": mid, "usage": u}}  # noqa: E731
        jsonl(self.home / ".claude" / "projects" / slug / "s1.jsonl", [
            {"type": "user", "timestamp": self.after, "message": {"role": "user"}},
            msg(self.before, "m0", usage(1000, 1000, 1000, 1000)),
            msg(self.after, "m1", usage(10, 20, 30, 5)),
            msg(self.after, "m1", usage(10, 20, 30, 5)),  # the same response's next content block
            msg(self.after, "m2", usage(1, 2, 3, 4))])
        jsonl(self.home / ".claude" / "projects" / slug / "s1" / "subagents" / "agent-x.jsonl", [
            msg(self.after, "m3", usage(100, 200, 300, 40)),
            msg(self.after, "m2", usage(1, 2, 3, 4))])  # the top-level file's m2 again: counted once
        jsonl(self.home / ".claude" / "projects" / "-elsewhere" / "s2.jsonl", [msg(self.after, "m9", usage(7, 7, 7, 7))])
        meta = lambda cwd: {"type": "session_meta", "timestamp": self.before, "payload": {"cwd": cwd}}  # noqa: E731
        self.count = lambda t, i, o, tin, tout: {"type": "event_msg", "timestamp": t, "payload": {  # noqa: E731
            "type": "token_count", "info": {"last_token_usage": {"input_tokens": i, "cached_input_tokens": 1,
                                                                 "output_tokens": o},
                                            "total_token_usage": {"input_tokens": tin, "output_tokens": tout}}}}
        self.meta, count = meta, self.count
        jsonl(self.codex / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl", [
            meta(str(self.repo.dir)), count(self.before, 500, 500, 500, 500), count(self.after, 100, 7, 600, 507),
            count(self.after, 200, 8, 800, 515)])
        jsonl(self.codex / "sessions" / "2026" / "01" / "02" / "rollout-b.jsonl", [
            meta(str(self.home)), count(self.after, 9, 9, 9, 9)])

    def test_sums_planted_transcripts_since_the_approval(self):
        self.plant()
        res = self.cost("cost")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["claude: input 666 output 49 (2 transcripts)",
                                                   "codex: input 300 output 15 (1 transcripts)"])
        early = subprocess.run(["git", "commit-tree", "HEAD^{tree}", "-m", "early"], cwd=self.repo.dir, check=True,
                               env=env(GIT_COMMITTER_DATE="2000-01-01T00:00:00Z"), capture_output=True, text=True)
        res = self.cost("cost", "--since", early.stdout.strip())
        self.assertEqual(res.stdout.splitlines(), ["claude: input 3666 output 1049 (2 transcripts)",
                                                   "codex: input 800 output 515 (1 transcripts)"])

    def test_repeated_codex_usage_notifications_count_once(self):
        self.plant()
        path = self.codex / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        rows += [rows[-1], rows[-1]]  # Codex re-emits a token_count whose totals have not moved
        jsonl(path, rows)
        res = self.cost("cost")
        self.assertEqual(res.stdout.splitlines()[1], "codex: input 300 output 15 (1 transcripts)", res.stderr)

    def test_repository_cost_includes_subdirectory_and_worktree_sessions(self):
        self.plant()
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.dir))
        usage = {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}
        for sub in ("install", ".claude/worktrees/agent-1"):  # a session opened in a subdirectory, a builder's worktree
            jsonl(self.home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.dir / sub)) / "s.jsonl",
                  [{"type": "assistant", "timestamp": self.after, "message": {"id": f"m-{sub}", "usage": usage}}])
            jsonl(self.codex / "sessions" / "2026" / "01" / "03" / f"rollout-{len(sub)}.jsonl",
                  [self.meta(str(self.repo.dir / sub)), self.count(self.after, 1, 1, 1, 1)])
        jsonl(self.home / ".claude" / "projects" / f"{slug}2" / "s.jsonl",  # a sibling: its slug is not <slug>-…
              [{"type": "assistant", "timestamp": self.after, "message": {"id": "m-sibling", "usage": usage}}])
        jsonl(self.codex / "sessions" / "2026" / "01" / "03" / "rollout-sibling.jsonl",
              [self.meta(str(self.repo.dir) + "2"), self.count(self.after, 1, 1, 1, 1)])
        res = self.cost("cost")
        self.assertEqual(res.stdout.splitlines(), ["claude: input 668 output 51 (4 transcripts)",
                                                   "codex: input 302 output 17 (3 transcripts)"], res.stderr)

    def test_nothing_planted_prints_unknown_for_each_harness(self):
        res = self.cost("cost")
        self.assertEqual((res.returncode, res.stdout), (0, "claude: unknown\ncodex: unknown\n"), res.stderr)

    def test_packet_reports_the_cost(self):
        self.plant()
        self.cost("packet")
        packet = self.repo.read(".runs/F-9/packet.md")
        self.assertIn("\nCost:\nclaude: input 666 output 49 (2 transcripts)\ncodex: input 300 output 15 (1 transcripts)\n",
                      packet)


if __name__ == "__main__":
    unittest.main()
