"""Tests for goal.py: plan lint, guards, completion, the stop hook and evidence.

Each test builds a throwaway repository (fixtures/goal_fixture.py) and drives goal.py as a
subprocess, the way the chief and the hooks call it. The cases follow the ways a run could fake
progress: edits outside the task, tampered tests, edited frozen inputs, stale or mismatched
receipts and verdicts, and a session that keeps stopping without finishing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import E2E, FULL, GOAL, PROOF3, Repo, plan_text, task  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
import goal  # noqa: E402

REAL_ROOT = Path(__file__).resolve().parents[4]
REAL_PLAN = REAL_ROOT / "docs/product/plans/F-3-lean-execution.md"
# Marker spellings are assembled so this file does not itself add the markers the guard rejects.
SKIP_DECORATOR = "@unittest." + "skip('later')"


class RepoCase(unittest.TestCase):
    plan = None

    def setUp(self):
        self.repo = Repo(self.plan)
        self.addCleanup(self.repo.cleanup)

    def assertPasses(self, res):
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    def assertFinding(self, res, text, code=1):
        self.assertEqual(res.returncode, code, res.stdout + res.stderr)
        self.assertIn(text, res.stdout + res.stderr)


class ParseTest(unittest.TestCase):
    def test_frontmatter_values(self):
        self.assertEqual(goal.scalar("[a, b]"), ["a", "b"])
        self.assertEqual(goal.scalar("{network: true, session_hours: 3}"),
                         {"network": True, "session_hours": 3})
        self.assertEqual(goal.scalar("make test            # per-task check"), "make test")
        raw = 'rc=0; for d in a b; do [ -d x/$d ] || continue; echo "$# # kept"; done; exit $rc'
        self.assertEqual(goal.scalar(raw), raw)
        self.assertEqual(goal.scalar("[ -f x ] && make"), "[ -f x ] && make")

    def test_tests_may_change_except_clause(self):
        inc, exc = goal.parse_tmc("tests/test_*.py except test_goal.py and test_gate.py (note, here)")
        self.assertEqual((inc, exc), (["tests/test_*.py"], ["test_goal.py", "test_gate.py"]))
        t = {"tests-may-change": inc, "tmc_exclude": exc}
        self.assertTrue(goal.tmc_allows(t, "tests/test_rules.py"))
        self.assertFalse(goal.tmc_allows(t, "tests/test_goal.py"))

    def test_globs(self):
        self.assertTrue(goal.matches("a/b/c/d.py", ["a/**"]))
        self.assertTrue(goal.matches("a/d.py", ["a/**/d.py"]))
        self.assertFalse(goal.matches("a/b/d.py", ["a/*.py"]))
        self.assertTrue(goal.matches(".gitignore", [".gitignore"]))
        self.assertTrue(goal.overlap(["src/a/**"], ["src/a/util.py"]))
        self.assertFalse(goal.overlap(["src/a/**"], ["src/b/**"]))
        self.assertFalse(goal.overlap(["tests/test_a.py"], ["tests/test_b*.py"]))

    def test_real_plan_lints(self):
        res = subprocess.run([sys.executable, str(GOAL), "lint", "--plan", str(REAL_PLAN)],
                             cwd=REAL_ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("lint: PASS", res.stdout)
        plan = goal.parse_plan(REAL_PLAN.read_text())
        self.assertEqual([m["id"] for m in plan["milestones"]], ["M3", "M4"])
        self.assertEqual(plan["milestones"][0]["acceptance"], ["tooling", "retirement"])
        self.assertTrue(plan["meta"]["gate"].endswith("exit $rc"))
        self.assertEqual(plan["tasks"]["T2"]["tmc_exclude"], ["test_goal.py", "test_gate.py"])


class LintTest(RepoCase):
    def test_fixture_lints(self):
        self.assertEqual(self.repo.goal("lint").returncode, 0)

    def test_structural_findings(self):
        bad = plan_text(extra_m1=task("T1", "dup", "src/z/**", "AC-9", needs="T77")
                        + task("T4", "nocover", "src/q/**", "—"))
        bad = bad.replace("- AC-2: manual — founder looks at it\n", "").replace("e2e: ", "e2e_x: ")
        bad = bad.replace("- AC-1: full_gate", "- AC-1: e2e")
        self.repo.write("docs/plan.md", bad)
        res = self.repo.goal("lint")
        for text in ("duplicate task id T1", "covers AC-9, which is not in the spec",
                     "needs T77", "T4: covers is empty", "criterion AC-2 has no proof",
                     "proof token e2e has no frontmatter command"):
            self.assertFinding(res, text)


class GuardTest(RepoCase):
    def guard(self, tid="T1"):
        return self.repo.goal("guard", "--task", tid)

    def test_in_scope_change_and_checkbox_tick_pass(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        self.repo.tick("T1")
        self.assertPasses(self.guard())

    def test_out_of_scope_edit_fails(self):
        self.repo.write("src/b/y.py", "B = 1\n")
        self.assertFinding(self.guard(), "scope: src/b/y.py is outside T1 writes")

    def test_decisions_and_queue_append_admitted(self):
        self.repo.edit("docs/plan.md", "- 2026-01-01: fixture decision.\n",
                       "- 2026-01-01: fixture decision.\n- 2026-01-02 T1: chose X (default).\n")
        self.repo.edit("docs/plan.md", "## Queue\n", "## Queue\n- [blocks T3] which way?\n")
        self.assertEqual(self.guard().returncode, 0)

    def test_other_plan_edit_fails(self):
        self.repo.edit("docs/plan.md", "- writes: src/a/**, tests/**", "- writes: src/**, tests/**")
        res = self.guard()
        self.assertFinding(res, "scope: docs/plan.md changed outside checkboxes")
        self.assertIn("frozen: docs/plan.md", res.stdout)

    def test_hidden_section_header_is_not_metadata(self):
        self.repo.edit("docs/plan.md", "## M2 — second", "## Decisions\n### [ ] T9 — new\n## M2 — second")
        self.assertFinding(self.guard(), "frozen: docs/plan.md")

    def test_deleted_test_fails_without_permission_and_passes_with_it(self):
        self.repo.path("tests/test_a.py").unlink()
        self.assertFinding(self.guard("T1"), "existing test tests/test_a.py deleted")
        self.assertEqual(self.guard("T2").returncode, 0)

    def test_weakened_assertion(self):
        self.repo.edit("tests/test_a.py", "self.assertEqual(1 + 1, 2)", "self.assertTrue(True)")
        self.assertFinding(self.guard("T1"), "existing test tests/test_a.py modified")
        self.assertEqual(self.guard("T2").returncode, 0)

    def test_added_skip_fails_unless_allowed(self):
        self.repo.write("tests/test_new.py", f"import unittest\n\n\n{SKIP_DECORATOR}\nclass N(unittest.TestCase):\n    pass\n")
        self.assertFinding(self.guard("T1"), "tests/test_new.py adds a skip/only/xfail marker")
        self.repo.path("tests/test_new.py").unlink()
        self.repo.edit("tests/test_a.py", "    def test_flag", f"    {SKIP_DECORATOR}\n    def test_flag")
        self.assertEqual(self.guard("T2").returncode, 0)
        self.assertFinding(self.guard("T1"), "adds a skip/only/xfail marker")

    def test_new_test_file_without_markers_passes(self):
        self.repo.write("tests/test_more.py", "import unittest\n")
        self.assertEqual(self.guard("T1").returncode, 0)

    def test_edited_spec_after_approval_fails(self):
        self.repo.edit("docs/spec.md", "| AC-1 | first |", "| AC-1 | first, relaxed |")
        self.repo.commit("F-9: sneak")
        self.repo.write("src/a/x.py", "A = 1\n")
        self.assertFinding(self.guard(), "frozen: docs/spec.md changed since goal/F-9/approved")


class DoneTest(RepoCase):
    M1 = [FULL, E2E]
    M2 = [FULL, E2E, PROOF3]

    def done(self, *args):
        return self.repo.goal("done", *args)

    def test_done_after_receipts_and_verdict(self):
        res = self.done()
        self.assertFinding(res, "T1 unchecked")
        self.assertIn("no full_gate receipt", res.stdout)
        self.repo.finish_m1()
        self.repo.close("M1", self.M1)
        self.assertPasses(self.done())

    def test_stale_receipt_replaced_by_failing_rerun(self):
        self.repo.finish_m1()
        self.repo.close("M1", self.M1)
        self.assertEqual(self.done().returncode, 0)
        self.assertEqual(self.repo.receipt(FULL, FIXTURE_FAIL="1").returncode, 1)
        self.assertFinding(self.done(), "full_gate receipt is FAIL")

    def test_receipt_for_other_command_does_not_count(self):
        self.repo.finish_m1()
        self.repo.close("M1", [E2E, FULL + " -v"])
        self.assertFinding(self.done(), "no full_gate receipt for the candidate tree")

    def test_receipt_for_older_tree_does_not_count(self):
        self.repo.finish_m1()
        self.repo.close("M1", self.M1)
        self.repo.edit("docs/plan.md", "## Queue\n", "## Queue\n- [blocks T3] later?\n")
        self.repo.commit("F-9: queue a question")
        res = self.done()
        self.assertFinding(res, "no full_gate receipt for the candidate tree")
        self.assertIn("stale acceptance verdict", res.stdout)

    def test_commit_rules(self):
        self.repo.finish_m1()
        self.repo.write("src/a/z.py", "Z = 1\n")
        self.repo.commit("tidy without a task")
        self.repo.write("src/a/w.py", "W = 1\n")
        self.repo.commit("[T1][T2] two tasks")
        self.repo.write("src/b/q.py", "Q = 1\n")
        self.repo.commit("[T1] reach into b")
        self.repo.close("M1", self.M1)
        res = self.done()
        self.assertFinding(res, "names no task and is not a plan-metadata commit")
        self.assertIn("names several tasks: T1, T2", res.stdout)
        self.assertIn("[T1]: scope: src/b/q.py is outside T1 writes", res.stdout)

    def test_controller_metadata_commit_allowed(self):
        self.repo.finish_m1()
        self.repo.edit("docs/plan.md", "## Queue\n", "## Queue\n- [blocks T3] later?\n")
        self.repo.commit("F-9: queue a question")
        self.repo.close("M1", self.M1)
        self.assertPasses(self.done())

    def test_later_milestone_with_earlier_verified_by_tag(self):
        self.repo.finish_m1()
        self.repo.close("M1", self.M1)
        self.repo.git("tag", "goal/F-9/M1")
        self.repo.write("src/c/z.py", "C = 1\n")
        self.repo.tick("T3")
        self.repo.commit("[T3] gamma")
        self.repo.close("M2", self.M2, partitions=("acceptance-alpha", "acceptance-beta"))
        self.assertIn("M2: DONE", self.assertPasses(self.done()).stdout)
        res = self.done("--milestone", "M1")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn(self.repo.tree("goal/F-9/M1"), res.stdout)

    def test_acceptance_partitions_are_a_conjunction(self):
        self.repo.finish_m1()
        self.repo.close("M1", self.M1)
        self.repo.git("tag", "goal/F-9/M1")
        self.repo.write("src/c/z.py", "C = 1\n")
        self.repo.tick("T3")
        self.repo.commit("[T3] gamma")
        self.repo.close("M2", self.M2, partitions=("acceptance-alpha",))
        self.assertFinding(self.done(), "no acceptance verdict (beta)")
        self.repo.verdict("M2-acceptance-beta", "BLOCK")
        self.assertFinding(self.done(), "a BLOCK acceptance verdict (beta)")
        self.repo.verdict("M2-acceptance-beta", "PASS")
        self.assertEqual(self.done().returncode, 0)

    def test_untagged_earlier_milestone_blocks_later(self):
        self.assertFinding(self.done("--milestone", "M2"), "M1 is not tagged yet")

    def test_evidence_record(self):
        self.repo.finish_m1()
        self.repo.edit("docs/plan.md", "- 2026-01-01: fixture decision.\n",
                       "- 2026-01-01: fixture decision.\n- 2026-01-02 T2: advisor chose X.\n")
        self.repo.commit("F-9: log a decision")
        self.repo.close("M1", self.M1)
        self.repo.write(".runs/F-9/progress.md", "x T1 done\nx usage: claude 1.2M tok\n")
        res = self.repo.goal("evidence", "--milestone", "M1")
        self.assertEqual(res.returncode, 0, res.stderr)
        text = self.repo.read(".runs/F-9/M1-evidence.md")
        self.assertTrue(text.startswith("M1 — READY"), text)
        for part in ("AC-1 → " + FULL + " → PASS", "AC-2 → manual", "Guard: scope 0 escapes",
                     "Security: not triggered", "Decisions taken: 1 (0 default, 1 advisor", "product +2/−0",
                     "usage: claude 1.2M tok", "all: PASS · codex fixture high · rounds 1"):
            self.assertIn(part, text)


class StopHookTest(RepoCase):
    def hook(self, payload=None, **extra):
        payload = payload if payload is not None else {"cwd": str(self.repo.dir), "session_id": "s1",
                                                       "stop_hook_active": False}
        return self.repo.run(GOAL, "stop-hook", stdin=json.dumps(payload) if isinstance(payload, dict)
                             else payload, **extra)

    def assertAllowed(self, res):
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_inactive_allows(self):
        self.assertAllowed(self.hook())

    def test_blocks_with_reanchor_text(self):
        self.repo.activate()
        res = self.hook()
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("Goal F-9: Fixture outcome. Not done: T1 unchecked"))
        self.assertTrue(out["reason"].endswith("Next ready: T1 (covers AC-1)."), out["reason"])

    def test_judge_exempt(self):
        self.repo.activate()
        self.assertAllowed(self.hook(GOAL_ROLE="judge"))
        self.assertIn("block", self.hook(GOAL_ROLE="chief").stdout)

    def test_stall_cap(self):
        self.repo.activate()
        for _ in range(3):
            self.assertIn('"block"', self.hook().stdout)
        self.assertAllowed(self.hook())
        self.assertIn("STALLED", self.repo.read(".runs/F-9/progress.md"))

    def test_progress_resets_stall_count(self):
        self.repo.activate()
        for _ in range(3):
            self.hook()
        self.repo.tick("T1")
        self.assertIn('"block"', self.hook().stdout)

    def test_envelope_expiry_allows(self):
        self.repo.activate()
        self.repo.write(".runs/F-9/session.json", json.dumps({"started_at": time.time() - 7200, "hours": 1}))
        self.assertAllowed(self.hook())
        self.repo.write(".runs/F-9/session.json", json.dumps({"started_at": "2020-01-01T00:00:00Z", "hours": 3}))
        self.assertAllowed(self.hook())
        self.repo.write(".runs/F-9/session.json", json.dumps({"started_at": time.time(), "hours": 3}))
        self.assertIn('"block"', self.hook().stdout)

    def test_all_parked_allows(self):
        self.repo.activate()
        self.repo.tick("T1", "!")
        self.repo.tick("T2", "!")
        self.assertAllowed(self.hook())

    def test_done_milestone_allows(self):
        self.repo.finish_m1()
        self.repo.close("M1", DoneTest.M1)
        self.repo.activate()
        self.assertAllowed(self.hook())

    def test_internal_error_allows(self):
        self.repo.activate()
        res = self.hook("{not json")
        self.assertAllowed(res)
        self.assertIn("allowing stop", res.stderr)


class RunStateTest(RepoCase):
    def test_attempts_persist(self):
        self.assertEqual(self.repo.goal("attempt", "--task", "T1").stdout.strip(), "1")
        self.assertEqual(self.repo.goal("attempt", "--task", "T1").stdout.strip(), "2")
        self.assertEqual(json.loads(self.repo.read(".runs/F-9/attempts.json")), {"T1": 2})
        self.assertEqual(self.repo.goal("attempt", "--task", "T1", "--get").stdout.strip(), "2")
        self.assertEqual(self.repo.goal("attempt", "--task", "T1", "--reset").stdout.strip(), "0")

    def test_start_status_stop(self):
        res = self.repo.run(GOAL, "start", "--goal", "F-9", "--plan", "docs/plan.md")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(self.repo.run(GOAL, "status", "--json").stdout)
        self.assertEqual((data["active"], data["next"]), ("M1", ["T1"]))
        self.repo.run(GOAL, "stop")
        self.assertFalse(self.repo.path(".runs/active").exists())

    def test_unmigrated_project_refused(self):
        self.repo.write("docs/agents/execution/runtime.json", "{}")
        self.assertFinding(self.repo.goal("status"), "migrate it to v6 first", code=2)


class NextTest(RepoCase):
    plan = plan_text(extra_m1=task("T4", "util", "src/a/util.py", "AC-1")
                     + task("T5", "docs", "docs/notes.md", "AC-2"))

    def test_next_respects_needs_parking_and_overlap(self):
        res = self.repo.goal("next", "--limit", "3")
        ids = [line.split()[0] for line in res.stdout.splitlines()]
        self.assertEqual(ids, ["T1", "T5"])
        self.repo.tick("T1", "!")
        ids = [line.split()[0] for line in self.repo.goal("next", "--limit", "3").stdout.splitlines()]
        self.assertEqual(ids, ["T4", "T5"])
        res = self.repo.goal("next", "--running", "T4", "--running", "T5")
        self.assertFinding(res, "no ready task")


if __name__ == "__main__":
    unittest.main()
