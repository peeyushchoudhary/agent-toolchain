"""Tests for review.py: judge commands, vendor choice, verdict files, the round cap and fallback.

The judge CLIs are the fake from test_run_goal.py on PATH, so the tests assert the exact command
each vendor receives (read-only by construction, user integrations excluded, GOAL_ROLE=judge,
model and effort from persona frontmatter) and that goal.py reads the verdict the wrapper writes.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import E2E, FULL, GOAL, Repo, plan_text  # noqa: E402
from test_run_goal import FakeHarness, clean_env  # noqa: E402

sys.path.insert(0, str(GOAL.parent))
sys.path.insert(0, str(GOAL.parents[2] / "agent-personas" / "scripts"))
import goal  # noqa: E402
import sync_personas  # noqa: E402

REVIEW = GOAL.parent / "review.py"
PASS = "VERDICT: PASS\n- [other] src/a/x.py — trigger: none — consequence: naming only"
BLOCK = "VERDICT: BLOCK\n- [correctness] src/a/x.py — trigger: empty input — consequence: crash"
ADVICE = "VERDICT: ADVICE\nrecommendation: A\nconfidence: high\nreversible: yes\nA is smaller."


def route(persona, vendor, variant=None):
    return sync_personas.routing(sync_personas.load(persona)[0], variant)[vendor]


class ReviewCase(unittest.TestCase):
    plan = None

    def setUp(self):
        self.repo = Repo(self.plan)
        self.fake = FakeHarness()
        self.addCleanup(self.repo.cleanup)
        self.addCleanup(self.fake.cleanup)

    def review(self, *args, text=PASS, **envs):
        return subprocess.run([sys.executable, str(REVIEW), "--plan", "docs/plan.md", *args],
                              cwd=self.repo.dir, env=clean_env(**self.fake.env(FAKE_TEXT=text, **envs)),
                              capture_output=True, text=True, timeout=120)

    def verdict(self, name):
        return goal.read_verdict(self.repo.dir / ".runs/F-9/verdicts" / f"{name}.md")


class CommandTest(ReviewCase):
    def test_codex_judges_acceptance_for_a_claude_chief_and_done_accepts_it(self):
        self.repo.finish_m1()
        for cmd, name in ((FULL, "full_gate"), (E2E, "e2e")):
            self.assertEqual(self.repo.receipt(cmd, name).returncode, 0)
        res = self.review("--kind", "acceptance", "--milestone", "M1", "--chief", "claude")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        (call,) = self.fake.calls()
        r = route("reviewer", "codex", "acceptance")
        self.assertEqual(call["name"], "codex")
        self.assertEqual(call["argv"][:-1], ["exec", "-s", "read-only", "--ignore-user-config", "--ignore-rules",
                                             "-m", r["model"], "-c", f"model_reasoning_effort={r['effort']}",
                                             "--json", "-C", str(self.repo.dir)])
        self.assertEqual(call["role"], "judge")
        packet = call["argv"][-1]
        self.assertIn("| AC-1 | first | tests |", packet)
        self.assertIn(".runs/F-9/review/M1-acceptance-r1.diff", packet)
        self.assertIn("never blocks", packet)  # the finding classes come from references/review.md
        verdict, tree, head = self.verdict("M1-acceptance")
        self.assertEqual((verdict, tree), ("PASS", self.repo.tree()))
        self.assertEqual((head["vendor"], head["model"], head["effort"], head["round"]),
                         ("codex", r["model"], r["effort"], "1"))
        self.assertIn("src/a/x.py", self.repo.read(".runs/F-9/review/M1-acceptance-r1.diff"))
        done = self.repo.goal("done", "--milestone", "M1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_claude_judges_a_safety_task_for_a_codex_chief(self):
        self.repo.write("src/a/x.py", "A = 1\n")
        res = self.review("--kind", "security", "--task", "T1", text=BLOCK, GOAL_HARNESS="codex")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        (call,) = self.fake.calls()
        r = route("security-reviewer", "claude")
        self.assertEqual(call["name"], "claude")
        self.assertEqual(call["argv"][:-1], ["-p", "--model", r["model"], "--effort", r["effort"], "--tools",
                                             "Read,Grep,Glob", "--strict-mcp-config", "--setting-sources", "project,local",
                                             "--output-format", "json"])
        self.assertIn("security-reviewer", call["argv"][-1])
        self.assertIn("src/a/x.py", self.repo.read(".runs/F-9/review/T1-security-r1.diff"))
        self.assertEqual(self.verdict("T1-security")[0], "BLOCK")

    def test_block_acceptance_keeps_the_milestone_not_done(self):
        self.repo.finish_m1()
        self.review("--kind", "acceptance", "--milestone", "M1", "--chief", "claude", text=BLOCK)
        self.assertIn("a BLOCK acceptance verdict", self.repo.goal("done", "--milestone", "M1").stdout)

    def test_advisor_and_council_members(self):
        res = self.review("--kind", "advisor", "--item", "T2", "--note", "A or B?", "--chief", "claude", text=ADVICE)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.review("--kind", "council", "--item", "T2", "--member", "2", "--note", "A or B?",
                    "--chief", "claude", text=ADVICE)
        self.review("--kind", "council", "--item", "T2", "--member", "3", "--note", "A or B?",
                    "--chief", "claude", text=ADVICE)
        calls = self.fake.calls()
        self.assertEqual([c["name"] for c in calls], ["codex", "claude", "codex"])
        self.assertIn(route("advisor", "codex")["model"], calls[0]["argv"])
        self.assertIn(route("advisor", "claude")["model"], calls[1]["argv"])
        self.assertIn(route("reviewer", "codex")["model"], calls[2]["argv"])
        self.assertEqual(self.verdict("T2-advisor")[0], "ADVICE")
        self.assertIn("A or B?", calls[0]["argv"][-1])

    def test_design_review_before_a_plan_exists(self):
        self.repo.path("docs/plan.md").unlink()
        res = subprocess.run([sys.executable, str(REVIEW), "--goal", "F-9", "--kind", "design", "--subject",
                              "docs/design.md", "--chief", "codex"], cwd=self.repo.dir,
                             env=clean_env(**self.fake.env(FAKE_TEXT=PASS)), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.fake.calls()[0]["name"], "claude")
        self.assertEqual(self.verdict("design")[0], "PASS")


class RoundTest(ReviewCase):
    def test_third_round_is_refused_whatever_the_note(self):
        for note in ("first look", "rereview of the fix"):
            self.assertEqual(self.review("--kind", "boundary", "--task", "T1", "--note", note,
                                         "--chief", "claude", text=BLOCK).returncode, 1)
        res = self.review("--kind", "boundary", "--task", "T1", "--note", "a renamed attempt",
                          "--diff", "HEAD~0", "--chief", "claude")
        self.assertEqual(res.returncode, 1)
        self.assertIn("refused", res.stdout)
        self.assertEqual(len(self.fake.calls()), 2)
        self.assertEqual(self.verdict("T1-boundary")[2]["round"], "2")
        self.assertTrue(self.repo.path(".runs/F-9/verdicts/history/T1-boundary-r1.md").is_file())

    def test_advisor_gets_one_call_per_item(self):
        self.review("--kind", "advisor", "--item", "T2", "--note", "q", "--chief", "claude", text=ADVICE)
        res = self.review("--kind", "advisor", "--item", "T2", "--note", "q, rephrased", "--chief", "claude")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(len(self.fake.calls()), 1)

    def test_partitions_have_their_own_caps_and_cannot_be_invented(self):
        self.assertEqual(self.review("--kind", "acceptance", "--milestone", "M2", "--chief", "claude").returncode, 2)
        res = self.review("--kind", "acceptance", "--milestone", "M2", "--partition", "gamma", "--chief", "claude")
        self.assertEqual(res.returncode, 2)
        self.assertIn("declares acceptance", res.stderr)
        self.assertIn("goal/F-9/M1 not found", self.review("--kind", "acceptance", "--milestone", "M2",
                                                           "--partition", "alpha", "--chief", "claude").stderr)
        self.repo.git("tag", "goal/F-9/M1")
        for _ in range(2):
            self.assertEqual(self.review("--kind", "acceptance", "--milestone", "M2", "--partition", "alpha",
                                         "--chief", "claude", text=BLOCK).returncode, 1)
        res = self.review("--kind", "acceptance", "--milestone", "M2", "--partition", "beta", "--chief", "claude")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.verdict("M2-acceptance-beta")[0], "PASS")
        self.assertEqual(self.review("--kind", "acceptance", "--milestone", "M2", "--partition", "alpha",
                                     "--chief", "claude").returncode, 1)

    def test_invalid_judge_output_counts_as_a_round(self):
        res = self.review("--kind", "plan", "--subject", "docs/plan.md", "--chief", "claude", text="Looks fine.")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(self.verdict("plan")[0], "INVALID")
        self.assertIn('"plan": 1', self.repo.read(".runs/F-9/verdicts/rounds.json"))


class FallbackTest(ReviewCase):
    def test_same_vendor_fallback_on_quota_is_recorded(self):
        self.repo.finish_m1()
        res = self.review("--kind", "acceptance", "--milestone", "M1", "--chief", "claude", FAKE_QUOTA="codex")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual([c["name"] for c in self.fake.calls()], ["codex", "claude"])
        _v, _t, head = self.verdict("M1-acceptance")
        self.assertEqual(head["vendor"], "claude")
        self.assertIn("codex quota exhausted", head["fallback"])

    def test_both_vendors_out_of_quota_writes_nothing(self):
        res = self.review("--kind", "plan", "--chief", "claude", FAKE_QUOTA="codex,claude")
        self.assertEqual(res.returncode, 2)
        self.assertIn("judge call failed", res.stderr)
        self.assertFalse(self.repo.path(".runs/F-9/verdicts/plan.md").exists())

    def test_missing_chief_and_unmigrated_project_are_refused(self):
        res = self.review("--kind", "plan")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--chief", res.stderr)
        self.repo.write("docs/agents/execution/runtime.json", "{}")
        res = self.review("--kind", "plan", "--chief", "claude")
        self.assertEqual(res.returncode, 2)
        self.assertIn("migrate", res.stderr)
        self.assertEqual(self.fake.calls(), [])


if __name__ == "__main__":
    unittest.main()
