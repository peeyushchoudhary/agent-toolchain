"""Tests for run_goal.py and goal-session.sh, driving a fake harness executable on PATH.

The fake stands in for both `claude` and `codex`: it records its argv and role, performs the
scripted steps for its session (complete a task with a commit, tag a milestone, sleep, report
exhausted quota) and prints JSON shaped like the real CLI's. Each test drives the fixture goal F-9
(M1: T1, T2; M2: T3) through the real driver loop.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import FULL, Repo, env, plan_text  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RUN_GOAL = SCRIPTS / "run_goal.py"
SESSION_HOOK = Path(__file__).resolve().parents[3] / "hooks" / "goal-session.sh"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1] / "agent-personas" / "scripts"))
import sync_personas  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
name = Path(sys.argv[0]).name
d = Path(os.environ["FAKE_DIR"])
calls = d / "calls.jsonl"
n = len(calls.read_text().splitlines()) if calls.exists() else 0
with open(calls, "a") as fh:
    fh.write(json.dumps({"name": name, "argv": sys.argv[1:], "cwd": os.getcwd(),
                         "role": os.environ.get("GOAL_ROLE"), "harness": os.environ.get("GOAL_HARNESS")}) + "\n")
script = json.loads(os.environ.get("FAKE_SCRIPT", "[]"))
steps = script[min(n, len(script) - 1)] if script else []
steps = [steps] if isinstance(steps, str) else steps
text = os.environ.get("FAKE_TEXT", "done")
if name in os.environ.get("FAKE_QUOTA", "").split(","):
    steps = ["quota"]
def git(*a):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=Fake", "-c",
                    "user.email=fake@example.invalid", *a], check=True, capture_output=True)
for step in steps:
    kind, _, arg = step.partition(":")
    if kind == "task":
        tid, path = arg.split(":")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("x = 1\n")
        plan = Path("docs/plan.md")
        plan.write_text(plan.read_text().replace(f"### [ ] {tid} ", f"### [x] {tid} "))
        git("add", "-A")
        git("commit", "-qm", f"[{tid}] fake work")
    elif kind == "commit":
        tid, path = arg.split(":")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("y = 2\n")
        git("add", "-A")
        git("commit", "-qm", f"[{tid}] untick work")
    elif kind == "tag":
        git("tag", f"goal/F-9/{arg}")
    elif kind == "sleep":
        time.sleep(float(arg))
    elif kind == "waitclose":
        for _ in range(100):
            s = Path(".runs/F-9/session.json")
            if s.exists() and json.loads(s.read_text()).get("hours") == 0:
                (d / "closed").write_text("yes")
                break
            time.sleep(0.05)
    elif kind == "quota":
        if name == "claude":
            print(json.dumps({"type": "result", "is_error": True, "result": "Claude usage limit reached; resets 5am"}))
        else:
            print(json.dumps({"type": "error", "message": "You've hit your usage limit. Try again at 5am."}))
        sys.exit(1)
if name == "claude":
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text,
                      "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 7},
                      "total_cost_usd": 0.01, "permission_denials": []}))
else:
    print(json.dumps({"type": "thread.started", "thread_id": "t"}))
    print(json.dumps({"type": "item.completed", "item": {"id": "i", "type": "agent_message", "text": text}}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 20, "cached_input_tokens": 4,
                                                          "output_tokens": 3, "reasoning_output_tokens": 1}}))
'''

HAPPY = [["task:T1:src/a/x.py", "task:T2:src/b/y.py", "tag:M1", "waitclose"],
         ["task:T3:src/c/z.py", "tag:M2"]]


class FakeHarness:
    """A temporary bin directory holding the fake as both `claude` and `codex`."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fakecli-"))
        for name in ("claude", "codex"):
            p = self.dir / name
            p.write_text(FAKE)
            p.chmod(0o755)

    def env(self, script=(), **extra):
        base = {"PATH": f"{self.dir}{os.pathsep}{os.environ['PATH']}", "FAKE_DIR": str(self.dir),
                "FAKE_SCRIPT": json.dumps(list(script))}
        base.update(extra)
        return base

    def calls(self):
        p = self.dir / "calls.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def clean_env(**extra):
    e = env(**extra)
    for k in ("GOAL_HARNESS", "CLAUDE_PROJECT_DIR", "FAKE_QUOTA", "FAKE_TEXT"):
        if k not in extra:
            e.pop(k, None)
    return e


class DriverCase(unittest.TestCase):
    plan = None

    def setUp(self):
        self.repo = Repo(self.plan)
        self.fake = FakeHarness()
        self.addCleanup(self.repo.cleanup)
        self.addCleanup(self.fake.cleanup)

    def drive(self, script, harness="claude", *extra, **envs):
        args = [sys.executable, str(RUN_GOAL), "--goal", "F-9", "--harness", harness, "--plan",
                "docs/plan.md", "--poll", "0.05", "--backoff", "0.1", *extra]
        return subprocess.run(args, cwd=self.repo.dir, env=clean_env(**self.fake.env(script, **envs)),
                              capture_output=True, text=True, timeout=120)

    def progress(self):
        return self.repo.read(".runs/F-9/progress.md")


class DriveTest(DriverCase):
    def test_two_milestones_in_fresh_claude_sessions(self):
        res = self.drive(HAPPY)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.fake.calls()
        self.assertEqual([c["name"] for c in calls], ["claude", "claude"])
        route = sync_personas.routing(sync_personas.load("chief")[0])["claude"]
        settings = str(self.repo.dir / ".runs/F-9/claude-settings.json")
        self.assertEqual(calls[0]["argv"][:-1], ["-p", "--model", route["model"], "--effort", route["effort"],
                                                 "--permission-mode", "auto", "--settings", settings,
                                                 "--output-format", "json"])
        self.assertTrue(all(c["role"] == "chief" and c["harness"] == "claude" for c in calls))
        first, second = calls[0]["argv"][-1], calls[1]["argv"][-1]
        self.assertIn("Active milestone: M1", first)
        self.assertIn("goal.py status:\nGoal F-9: Fixture outcome", first)
        self.assertIn("Active milestone: M2", second)
        self.assertIn("progress 0→3", second)  # the progress tail carries the first session's line
        self.assertTrue((self.fake.dir / "closed").exists(), "envelope was not closed after the M1 tag")
        self.assertFalse((self.repo.dir / ".runs/F-9/session.json").exists())
        self.assertEqual(json.loads(self.repo.read(".runs/active"))["goal"], "F-9")
        progress = self.progress()
        self.assertEqual(progress.count("usage: claude in=15 out=7 cost=$0.0100"), 2)
        self.assertIn("driver: goal F-9 done", progress)

    def test_settings_file_registers_hooks_and_allows_the_gates(self):
        self.drive(HAPPY)
        data = json.loads(self.repo.read(".runs/F-9/claude-settings.json"))
        stop = data["hooks"]["Stop"][0]["hooks"][0]["command"]
        start = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn(f"{SCRIPTS / 'goal.py'}' stop-hook | tee -a", stop)
        self.assertIn("goal-session.sh", start)
        allow = data["permissions"]["allow"]
        for rule in ("Bash(git add:*)", "Bash(git commit:*)", "Bash(git tag goal/F-9/:*)", f"Bash({FULL})",
                     f"Bash(python3 {SCRIPTS / 'gate.py'}:*)", f"Bash(python3 {SCRIPTS / 'review.py'}:*)"):
            self.assertIn(rule, allow)

    def test_codex_profile_with_network(self):
        self.repo.write("docs/plan.md", plan_text().replace("network: false", "network: true"))
        self.repo.commit("F-9: network on")
        self.repo.git("tag", "-f", "goal/F-9/approved")
        res = self.drive(HAPPY, "codex")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        route = sync_personas.routing(sync_personas.load("chief")[0])["codex"]
        argv = self.fake.calls()[0]["argv"]
        self.assertEqual(argv[:-1], ["exec", "--approve-for-me", "-m", route["model"],
                                     "-c", f"model_reasoning_effort={route['effort']}",
                                     "-c", "sandbox_workspace_write.network_access=true", "--json"])
        self.assertIn("usage: codex in=20 cached=4 out=4", self.progress())
        self.assertFalse((self.repo.dir / ".runs/F-9/claude-settings.json").exists())

    def test_codex_profile_without_network_and_extra_args(self):
        res = self.drive(HAPPY, "codex", "--harness-arg=--ignore-rules")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        argv = self.fake.calls()[0]["argv"]
        self.assertNotIn("sandbox_workspace_write.network_access=true", argv)
        self.assertEqual(argv[-3:-1], ["--json", "--ignore-rules"])

    def test_codex_command_never_bypasses_hook_trust(self):
        import run_goal
        for network in (False, True):
            cmd = run_goal.session_command("codex", {"model": "m", "effort": "e"}, "p", network=network)
            self.assertFalse([a for a in cmd if "dangerously" in a or a in ("-s", "--sandbox")], cmd)
        res = self.drive(HAPPY, "codex", "--harness-arg=--dangerously-bypass-hook-trust")
        self.assertEqual(res.returncode, 2)
        self.assertIn("may not pass a --dangerously-* flag", res.stderr)
        self.assertEqual(self.fake.calls(), [])


class ExitTest(DriverCase):
    def test_stall_after_two_sessions_without_progress(self):
        res = self.drive([[]])
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertEqual(len(self.fake.calls()), 2)
        self.assertIn("STALLED", self.progress())

    def test_out_of_scope_completion_is_not_progress(self):
        res = self.drive([["task:T1:src/b/q.py"], []])
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertIn("progress 0→0", self.progress())

    def test_commit_without_tick_is_not_progress(self):
        res = self.drive([["commit:T1:src/a/x.py"]])
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertIn("progress 0→0", self.progress())

    def test_progress_resets_the_stall_count(self):
        res = self.drive([[], ["task:T1:src/a/x.py"], [], []])
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertEqual(len(self.fake.calls()), 4)

    def test_all_parked_exits_without_a_session(self):
        self.repo.tick("T1", "!")
        res = self.drive(HAPPY)
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertEqual(self.fake.calls(), [])

    def test_queue_blocked_tasks_count_as_waiting(self):
        self.repo.edit("docs/plan.md", "## Queue\n", "## Queue\n- [blocks T1] which store? A or B; recommend A\n")
        res = self.drive(HAPPY)
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)

    def test_quota_backoff_then_continue(self):
        res = self.drive(["quota"] + HAPPY)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(len(self.fake.calls()), 3)
        self.assertIn("quota exhausted", self.progress())

    def test_quota_window_runs_out(self):
        res = self.drive(["quota"], "claude", "--quota-wait", "0.00001")
        self.assertEqual(res.returncode, 5, res.stdout + res.stderr)
        self.assertEqual(len(self.fake.calls()), 1)
        self.assertIn("quota still exhausted", self.progress())

    def test_envelope_ends_a_runaway_session(self):
        self.repo.edit("docs/plan.md", "session_hours: 1", "session_hours: 0.0003")
        self.repo.commit("F-9: short envelope")
        self.repo.git("tag", "-f", "goal/F-9/approved")
        began = time.time()
        res = self.drive(["sleep:30"])
        self.assertEqual(res.returncode, 4, res.stdout + res.stderr)
        self.assertLess(time.time() - began, 25)
        self.assertIn("envelope expired", self.progress())

    def test_unmigrated_project_is_refused(self):
        self.repo.write("docs/agents/execution/runtime.json", "{}")
        res = self.drive(HAPPY)
        self.assertEqual(res.returncode, 2)
        self.assertIn("migrate it to v6 first", res.stderr)
        self.assertEqual(self.fake.calls(), [])

    def test_another_active_goal_is_refused(self):
        self.repo.write(".runs/active", json.dumps({"goal": "F-8", "plan": "docs/plan.md"}))
        res = self.drive(HAPPY)
        self.assertEqual(res.returncode, 2)
        self.assertIn("goal F-8 is active", res.stderr)


class HookTest(DriverCase):
    def hook(self, cwd, **extra):
        return subprocess.run(["bash", str(SESSION_HOOK)], cwd=cwd, env=clean_env(**extra),
                              capture_output=True, text=True, timeout=60)

    def test_session_hook_prints_status_for_the_active_goal(self):
        self.repo.activate()
        res = self.hook(self.repo.dir)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Goal F-9: Fixture outcome", res.stdout)
        self.assertIn("Next ready: T1", res.stdout)

    def test_session_hook_prints_the_migrate_notice(self):
        self.repo.activate()
        self.repo.write("docs/agents/execution/runtime.json", "{}")
        res = self.hook(self.repo.dir)
        self.assertEqual(res.returncode, 0)
        self.assertIn("v6 will not execute here", res.stdout)
        self.assertIn("migrate it to v6 first, following references/migrate.md", res.stdout)
        goal_res = self.repo.goal("status")
        self.assertEqual(goal_res.returncode, 2)

    def test_session_hook_is_silent_without_a_goal_or_repository(self):
        res = self.hook(self.repo.dir)
        self.assertEqual((res.returncode, res.stdout), (0, ""))
        outside = tempfile.mkdtemp(prefix="nogit-")
        self.addCleanup(shutil.rmtree, outside, True)
        res = self.hook(outside)
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_registered_stop_command_blocks_a_chief_and_logs_it(self):
        sys.path.insert(0, str(SCRIPTS))
        import goal
        import run_goal
        self.repo.activate()
        ctx = goal.Ctx(self.repo.dir, self.repo.dir / "docs/plan.md")
        ctx.runs.mkdir(parents=True, exist_ok=True)
        command = run_goal.hook_commands(ctx)["Stop"]
        event = json.dumps({"session_id": "s1", "cwd": str(self.repo.dir)})
        run = lambda role: subprocess.run(["bash", "-c", command], cwd=self.repo.dir, input=event,  # noqa: E731
                                          env=clean_env(GOAL_ROLE=role), capture_output=True, text=True)
        chief = run("chief")
        self.assertEqual(chief.returncode, 0)
        self.assertEqual(json.loads(chief.stdout)["decision"], "block")
        self.assertIn('"decision": "block"', self.repo.read(".runs/F-9/hooks.log"))
        judge = run("judge")
        self.assertEqual((judge.returncode, judge.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
