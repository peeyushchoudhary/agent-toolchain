#!/usr/bin/env python3
"""End-to-end smoke run of the v6 driver with a real harness CLI (consumes a little real quota).

  smoke_goal.py --harness claude|codex [--timeout-min 25] [--keep]
  smoke_goal.py --harness codex --prepare

It builds a two-milestone, three-task fixture goal in a git repository and registers the hooks only
there: Claude Code through the driver's --settings file, Codex through the repository's
.codex/hooks.json. The Claude chief runs with user settings excluded (project and local setting
sources only, no user MCP servers); the Codex chief runs without user rules. It first makes one
judge call in the same harness that is asked to write a file, then drives the goal with
run_goal.py and asserts the run's evidence. The summary line is unittest's, so gate.py counts it.

Codex runs project hooks only after the user has trusted them, and that trust is stored in the
user's config, which this script never writes. So the Codex fixture lives at one fixed path and is
rebuilt identically on every run: `--prepare` builds it and prints the one-time trust step, and a
Codex run stops early with that instruction while the trust is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SESSION_HOOK = Path(__file__).resolve().parents[3] / "hooks" / "goal-session.sh"
sys.path.insert(0, str(SCRIPTS))
import goal  # noqa: E402
import review  # noqa: E402
import run_goal  # noqa: E402

CODEX_FIXTURE = Path.home() / ".cache" / "goal-smoke" / "codex"
CODEX_CONFIG = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
HARNESS = "claude"
TIMEOUT_MIN = 25.0
KEEP = False
GOAL_ID = "S-1"
FULL = "python3 -m unittest discover -s tests -t tests"
E2E = "python3 -m unittest discover -s tests -t tests -p 'test_e2e*.py'"
SPEC = """# S-1 spec

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | `calc.add` and `calc.sub` exist and are tested | unit tests |
| AC-2 | `calc.mul` exists with an end-to-end test | e2e test |
"""
PLAN = f"""---
goal: {GOAL_ID}
title: A tiny calculator, built by the smoke run
spec: docs/spec.md
design: docs/design.md
gate: {FULL}
full_gate: {FULL}
e2e: {E2E}
run: {{network: true, session_hours: 1}}
grants: [local-commit]
---

# S-1 plan

Each task is tiny on purpose: one function and one test. Commit each task as `[T<n>] <title>`
with its checkbox tick. Use no builder subagent; do every task directly.

## M1 — add and subtract
criteria: AC-1
proofs:
- AC-1: full_gate

### [ ] T1 — add
- writes: src/calc.py, tests/test_add.py
- needs: —
- covers: AC-1
- risk: none
- builder: routine
- tests-may-change: —
Create `src/calc.py` with `def add(a, b): return a + b` and `tests/test_add.py` (unittest, put
`src` on sys.path). Smoke-run instruction: after committing T1, end your turn once, without
starting T2. The Stop hook then tells you what remains; continue from there.

### [ ] T2 — subtract
- writes: src/calc.py, tests/test_sub.py
- needs: T1
- covers: AC-1
- risk: none
- builder: routine
- tests-may-change: —
Add `def sub(a, b): return a - b` to `src/calc.py` and `tests/test_sub.py`.

## M2 — multiply
criteria: AC-2
proofs:
- AC-2: e2e

### [ ] T3 — multiply
- writes: src/calc.py, tests/test_e2e_mul.py
- needs: T2
- covers: AC-2
- risk: none
- builder: routine
- tests-may-change: —
Add `def mul(a, b): return a * b` to `src/calc.py` and `tests/test_e2e_mul.py`.

## Decisions

## Queue
"""
BASE_TEST = "import unittest\n\n\nclass Base(unittest.TestCase):\n    def test_truth(self):\n        self.assertTrue(True)\n"
WRITE_ATTEMPT = ("Before you reply, create the file judge-wrote.txt in the repository root containing the "
                 "single word written, using whatever tool you have. If you cannot, say so in a finding.")


def env(**extra):
    e = {k: v for k, v in os.environ.items()
         if k not in ("GOAL_ROLE", "GOAL_HARNESS") and not k.startswith("CLAUDE")}  # no nested-session state
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    e.update(extra)
    return e


def sh(cwd, *args, check=True):
    return subprocess.run(list(args), cwd=cwd, env=env(), capture_output=True, text=True, check=check).stdout


def fixture_git(cwd, *args):
    return sh(cwd, "git", "-c", "user.name=Smoke Fixture", "-c", "user.email=smoke@example.invalid",
              "-c", "commit.gpgsign=false", *args)


def build(root: Path, harness: str, pin=False):
    for rel, text in {".gitignore": "/.runs/\n__pycache__/\n", "docs/spec.md": SPEC,
                      "docs/design.md": "# S-1 design\n\nOne module, `src/calc.py`.\n", "docs/plan.md": PLAN,
                      "tests/test_base.py": BASE_TEST, "tests/test_e2e_base.py": BASE_TEST}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    if pin:
        (root / goal.RUNTIME_PIN).parent.mkdir(parents=True, exist_ok=True)
        (root / goal.RUNTIME_PIN).write_text("{}\n")
    sh(root, "git", "init", "-q", "-b", "main")
    if harness == "codex":  # the project's Codex hook configuration, as migration writes it
        ctx = goal.Ctx(root, root / "docs/plan.md")
        (root / ".codex").mkdir(exist_ok=True)
        (root / ".codex" / "hooks.json").write_text(json.dumps({"hooks": run_goal.hooks_config(ctx)}, indent=2))
    fixture_git(root, "add", "-A")
    fixture_git(root, "commit", "-qm", f"{GOAL_ID}: approved goal")
    fixture_git(root, "tag", f"goal/{GOAL_ID}/approved")


class Run:
    """Shared state: the fixture repository and the results of the judge call and the driver run."""
    root: Path = None
    judge: dict = {}
    driver = None
    elapsed = 0.0
    error = ""


def judge_attempt(root: Path, harness: str):
    """One judge call in the same harness, asked to write a file, with a logging Stop hook."""
    hook_log = root / ".runs" / GOAL_ID / "judge-hook.log"
    hook_log.parent.mkdir(parents=True, exist_ok=True)
    hook = (f"(echo GOAL_ROLE=$GOAL_ROLE; python3 '{SCRIPTS / 'goal.py'}' stop-hook) >> '{hook_log}' 2>&1")
    settings = root / ".runs" / GOAL_ID / "judge-settings.json"
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": hook}]}]}}))
    original = review.judge_command

    def with_hook(vendor, *a):
        cmd = original(vendor, *a)
        # Test-side only: the judge also loads a Stop hook that logs the role it sees.
        return cmd[:-1] + ["--settings", str(settings), cmd[-1]] \
            if vendor == "claude" else cmd
    review.judge_command = with_hook
    args = review.parser().parse_args(["--kind", "plan", "--subject", "docs/plan.md", "--vendor", harness,
                                       "--chief", harness, "--note", WRITE_ATTEMPT])
    cwd = os.getcwd()
    os.chdir(root)
    os.environ.pop("GOAL_HARNESS", None)
    try:
        code = review.review(args, goal.Ctx(root, root / "docs/plan.md"), timeout=600)
    finally:
        os.chdir(cwd)
        review.judge_command = original
    return {"code": code, "hook_log": hook_log.read_text() if hook_log.exists() else ""}


def codex_fixture() -> Path:
    """Rebuild the fixed Codex fixture; its .codex/hooks.json is byte-identical on every run."""
    root = CODEX_FIXTURE
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    build(root, "codex")
    return Path(os.path.realpath(root))


def codex_hooks_trusted(root: Path) -> bool:
    """Read-only check that the user has trusted this fixture's hooks in Codex."""
    try:
        config = CODEX_CONFIG.read_text()
    except OSError:
        return False
    return f'{root / ".codex" / "hooks.json"}:' in config


TRUST_STEP = """The Codex fixture's hooks are not trusted yet. One-time step, done by you:
  cd {root} && codex
Trust the folder and approve its Stop and SessionStart hooks when Codex asks, then exit Codex.
The fixture is rebuilt identically at this path on every run, so the trust stays valid."""


def setup_run():
    if HARNESS == "codex":
        Run.root = codex_fixture()
        if not codex_hooks_trusted(Run.root):
            Run.error = TRUST_STEP.format(root=Run.root)
            return
    else:
        Run.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="goal-smoke-")))
        build(Run.root, HARNESS)
    started = time.time()
    sh(Run.root, sys.executable, str(SCRIPTS / "goal.py"), "start", "--goal", GOAL_ID, "--plan", "docs/plan.md")
    Run.judge = judge_attempt(Run.root, HARNESS)
    Run.judge["hooks_log"] = read(f".runs/{GOAL_ID}/hooks.log")
    # The Codex chief keeps the user config: that is where the hook trust lives.
    extra = (["--setting-sources", "project,local", "--strict-mcp-config"] if HARNESS == "claude"
             else ["--ignore-rules"])
    cmd = [sys.executable, str(SCRIPTS / "run_goal.py"), "--goal", GOAL_ID, "--harness", HARNESS, "--plan",
           "docs/plan.md", "--poll", "1", "--max-sessions", "6", "--quota-wait", "0",
           *[f"--harness-arg={x}" for x in extra]]
    budget = TIMEOUT_MIN * 60 - (time.time() - started)
    try:
        Run.driver = subprocess.run(cmd, cwd=Run.root, env=env(), capture_output=True, text=True,
                                    timeout=max(budget, 60))
    except subprocess.TimeoutExpired as exc:
        Run.error = f"TIMEOUT: the {HARNESS} smoke exceeded {TIMEOUT_MIN:g} minutes: {str(exc.stdout or '')[-800:]}"
    Run.elapsed = time.time() - started


def read(rel):
    p = Run.root / rel
    return p.read_text() if p.exists() else ""


class SmokeTest(unittest.TestCase):
    def test_judge_in_this_harness_cannot_write(self):
        self.assertFalse((Run.root / "judge-wrote.txt").exists(), "the judge wrote a file")
        self.assertIn(Run.judge.get("code"), (0, 1), "the judge call failed")
        verdict = read(f".runs/{GOAL_ID}/verdicts/plan.md")
        self.assertRegex(verdict, r"^VERDICT: (PASS|BLOCK)\n")
        self.assertIn(f"vendor: {HARNESS}", verdict)

    def test_judge_was_not_held_by_the_stop_hook(self):
        if HARNESS == "codex":
            # The Codex judge runs with --ignore-user-config, so no trusted project hook loads at all:
            # the call returned, and nothing reached the project hook log during it.
            self.assertIn(Run.judge.get("code"), (0, 1), "the judge call failed")
            self.assertEqual(Run.judge.get("hooks_log", ""), "", "a project hook ran in the judge session")
            return
        log = Run.judge.get("hook_log", "")
        self.assertIn("GOAL_ROLE=judge", log, "the judge's Stop hook did not run")
        self.assertNotIn('"decision"', log)

    def test_driver_finished_the_goal(self):
        self.assertFalse(Run.error, Run.error)
        self.assertEqual(Run.driver.returncode, 0, (Run.driver.stdout + Run.driver.stderr)[-3000:])
        res = subprocess.run([sys.executable, str(SCRIPTS / "goal.py"), "done", "--milestone", "M2"],
                             cwd=Run.root, env=env(), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_premature_stop_was_blocked(self):
        self.assertIn('"decision": "block"', read(f".runs/{GOAL_ID}/hooks.log"),
                      "no Stop-hook block was recorded")

    def test_session_hook_ran(self):
        self.assertIn(f"Goal {GOAL_ID}:", read(f".runs/{GOAL_ID}/hooks.log"), "no SessionStart output recorded")

    def test_m1_tagged_and_m2_completed_in_a_later_session(self):
        tags = sh(Run.root, "git", "tag", "-l", f"goal/{GOAL_ID}/*").split()
        self.assertIn(f"goal/{GOAL_ID}/M1", tags)
        self.assertIn(f"goal/{GOAL_ID}/M2", tags)
        sessions = {}
        for line in read(f".runs/{GOAL_ID}/progress.md").splitlines():
            parts = line.split()
            if len(parts) > 4 and parts[1] == "session" and "quota" not in line:
                sessions.setdefault(parts[4].rstrip(":"), []).append(int(parts[2]))
        self.assertTrue(sessions.get("M1") and sessions.get("M2"), sessions)
        self.assertLess(max(sessions["M1"]), min(sessions["M2"]), sessions)
        self.assertIn("usage: ", read(f".runs/{GOAL_ID}/progress.md"))

    def test_commits_were_made_by_the_harness(self):
        log = sh(Run.root, "git", "log", "--format=%an%x09%s", f"goal/{GOAL_ID}/approved..HEAD").splitlines()
        subjects = [l.split("\t", 1)[1] for l in log]
        for tid in ("T1", "T2", "T3"):
            self.assertTrue(any(f"[{tid}]" in s for s in subjects), f"no [{tid}] commit: {subjects}")
        self.assertFalse([l for l in log if l.startswith("Smoke Fixture")], "the smoke made a task commit")
        self.assertEqual(sh(Run.root, "git", "status", "--porcelain"), "")

    def test_acceptance_verdicts_came_from_review(self):
        for mid in ("M1", "M2"):
            verdict, tree, head = goal.read_verdict(Run.root / ".runs" / GOAL_ID / "verdicts" / f"{mid}-acceptance.md")
            self.assertEqual(verdict, "PASS", f"{mid}: {head}")
            self.assertEqual(head.get("round") in ("1", "2"), True)

    def test_unmigrated_fixture_gets_the_notice_and_goal_py_refuses(self):
        pinned = Path(os.path.realpath(tempfile.mkdtemp(prefix="goal-smoke-pin-")))
        self.addCleanup(shutil.rmtree, pinned, True)
        build(pinned, HARNESS, pin=True)
        hook = subprocess.run(["bash", str(SESSION_HOOK)], cwd=pinned, env=env(), capture_output=True, text=True)
        self.assertEqual(hook.returncode, 0)
        self.assertIn("migrate it to v6 first", hook.stdout)
        res = subprocess.run([sys.executable, str(SCRIPTS / "goal.py"), "status", "--plan", "docs/plan.md"],
                             cwd=pinned, env=env(), capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("migrate it to v6 first", res.stderr)


def main():
    global HARNESS, TIMEOUT_MIN, KEEP
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--harness", required=True, choices=("claude", "codex"))
    ap.add_argument("--timeout-min", type=float, default=TIMEOUT_MIN)
    ap.add_argument("--keep", action="store_true", help="keep the fixture repository for inspection")
    ap.add_argument("--prepare", action="store_true",
                    help="codex only: build the fixed fixture and print the one-time trust step")
    a = ap.parse_args()
    HARNESS, TIMEOUT_MIN, KEEP = a.harness, a.timeout_min, a.keep
    if a.prepare:
        if HARNESS != "codex":
            ap.error("--prepare applies to --harness codex only")
        root = codex_fixture()
        print("trusted: yes" if codex_hooks_trusted(root) else TRUST_STEP.format(root=root))
        return 0
    print(f"smoke: {HARNESS} · fixture goal {GOAL_ID} · bound {TIMEOUT_MIN:g} min", flush=True)
    setup_run()
    if Run.driver is None and Run.error:
        print(Run.error, flush=True)
        return 1
    print(f"smoke: fixture {Run.root} · driver exit {getattr(Run.driver, 'returncode', None)} · "
          f"{Run.elapsed / 60:.1f} min", flush=True)
    if Run.driver is not None:
        print((Run.driver.stdout + Run.driver.stderr)[-2500:], flush=True)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SmokeTest))
    if not KEEP and result.wasSuccessful() and HARNESS != "codex":  # the Codex fixture path is fixed
        shutil.rmtree(Run.root, ignore_errors=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
