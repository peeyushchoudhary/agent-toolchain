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
        self.repo.commit("F-9: widen T1 writes")
        self.assertRowOk(3)
        self.assertRow(4, f"{sha[:10]} [T1] src/b/z.py outside writes")

    def test_row5_names_an_added_skip_marker(self):
        text = self.repo.read("tests/test_a.py").replace("    def test_flag", SKIP_DECORATOR + "    def test_flag")
        self.fix("tests/test_a.py", text, "[T2] beta")  # T2 may change tests/test_a.py
        self.assertRow(5, "adds a skip/only/xfail marker in tests/test_a.py")

    def test_row5_names_a_test_modified_outside_tests_may_change(self):
        self.fix("tests/test_a.py", self.repo.read("tests/test_a.py") + "\n", "[T1] alpha")
        self.assertRow(5, "modifies test tests/test_a.py")

    def test_row6_names_an_outcome_edit(self):
        self.repo.edit(PLAN, "The fixture does two things.", "The fixture does one thing.")
        self.repo.commit("[T1] alpha")
        self.assertRow(6, "changed outside ticks")

    def test_row7_receipt_must_name_heads_tree(self):
        self.repo.close()
        path = receipt_path(self.repo.dir, "F-9", self.repo.tree(), FULL)
        good = path.read_text()
        path.write_text(json.dumps({**json.loads(good), "tree": "0" * 40}))
        self.assertRow(7, "no PASS full_gate receipt")
        path.write_text(good)
        self.assertRowOk(7)


class ReviewRowTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.repo.close()

    def test_a_non_fix_commit_after_reviewed_is_named(self):
        sha = self.fix("src/b/w.py", "W = 1\n", "[T2] more beta")
        self.assertRow(8, f"{sha[:10]} after reviewed: is not a fix commit")

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

    def test_removed_by_passes_when_the_paths_are_deleted(self):
        self.repo.git("rm", "-q", "src/b/y.py")
        sha = self.repo.commit("[T2][R1] remove the beta file")
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/b/y.py\n", "HEAD~1")
        self.assertRowOk(8)
        self.repo.review(f"- [x] R1 removed-by {sha[:8]}\n  paths: src/a/x.py\n", "HEAD~1")
        self.assertRow(8, "does not remove or change")

    def test_an_open_blocking_finding_is_named(self):
        self.repo.review("- [ ] BLOCKING R2 the beta value is wrong\n")
        self.assertRow(8, "open - [ ] BLOCKING")

    def test_a_missing_review_is_named(self):
        (self.repo.dir / ".runs/F-9/review.md").unlink()
        self.assertRow(8, "no .runs/F-9/review.md")


class StopHookTest(RepoCase):
    def hook(self, cwd=None, session="s1"):
        return subprocess.run([sys.executable, str(GOAL), "stop-hook"], cwd=cwd or self.repo.dir, env=env(),
                              input=json.dumps({"session_id": session}), capture_output=True, text=True)

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


if __name__ == "__main__":
    unittest.main()
