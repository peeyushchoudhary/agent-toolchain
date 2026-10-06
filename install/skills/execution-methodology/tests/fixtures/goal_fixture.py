"""Throwaway git repositories holding a small v6 goal, for the goal.py and gate.py tests.

The fixture goal F-9 has two milestones: M1 (T1, T2; criteria AC-1, AC-2) and M2 (T3; AC-3, with
acceptance split into two partitions). Its gates are tiny unittest suites inside the repository,
and `emit.py` prints canned test-runner output selected by the GATE_FIXTURE_MODE variable, so the
same command string can be made to pass or fail without changing the committed tree.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
GOAL = SCRIPTS / "goal.py"
GATE = SCRIPTS / "gate.py"

FULL = "python3 -m unittest discover -s tests -t tests"
E2E = "python3 -m unittest discover -s tests -t tests -p 'test_e2e*.py'"
PROOF3 = "python3 -m unittest discover -s tests -t tests -p 'test_b*.py'"

SPEC = """# F-9 spec

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | first | tests |
| AC-2 | second | manual |
| AC-3 | third | tests |
"""


def task(tid, title, writes, covers, needs="—", tmc="—", state=" ", risk="none"):
    return (f"### [{state}] {tid} — {title}\n- writes: {writes}\n- needs: {needs}\n"
            f"- covers: {covers}\n- risk: {risk}            # none | boundary | data | safety\n"
            f"- builder: routine\n- tests-may-change: {tmc}\nDo the {title} work.\n")


def plan_text(extra_m1="", m2_acceptance="[alpha, beta]"):
    return f"""---
goal: F-9
title: Fixture outcome
spec: docs/spec.md
design: docs/design.md
gate: {FULL} -q            # per-task check
full_gate: {FULL}
e2e: {E2E}
run: {{network: false, session_hours: 1}}
grants: [local-commit]
---

# F-9 plan

## M1 — first milestone
criteria: AC-1, AC-2
proofs:
- AC-1: full_gate
- AC-2: manual — founder looks at it

{task("T1", "alpha", "src/a/**, tests/**", "AC-1")}
{task("T2", "beta", "src/b/**, tests/**", "AC-2", needs="T1", tmc="tests/test_a.py")}
{extra_m1}
## M2 — second milestone
criteria: AC-3
acceptance: {m2_acceptance}
proofs:
- AC-3: {PROOF3}

{task("T3", "gamma", "src/c/**, tests/test_b*.py", "AC-3", needs="T2")}
## Decisions
- 2026-01-01: fixture decision.

## Queue
"""


TEST_A = """import os, unittest


class A(unittest.TestCase):
    def test_value(self):
        self.assertEqual(1 + 1, 2)

    def test_flag(self):
        self.assertFalse(os.environ.get("FIXTURE_FAIL"))
"""

TEST_E2E = """import unittest


class Flow(unittest.TestCase):
    def test_flow(self):
        self.assertTrue(True)
"""

EMIT = r'''import os, sys
mode = os.environ.get("GATE_FIXTURE_MODE", "ok")
fail = "FAIL: test_known (mod.Case.test_known)"
new = "FAIL: test_new (mod.Case.test_new)"
out = {
    "ok": ("Ran 3 tests in 0.01s\n\nOK", 0),
    "zero": ("nothing ran here", 0),
    "lie": ("Ran 3 tests in 0.01s\n\nFAILED (failures=1)", 0),
    "crash": ("Traceback: boom", 1),
    "base": (f"{fail}\n----\nRan 3 tests in 0.01s\n\nFAILED (failures=1)", 1),
    "new": (f"{fail}\n{new}\n----\nRan 3 tests in 0.01s\n\nFAILED (failures=2)", 1),
    "two": (f"Ran 4 tests in 0.1s\n\nOK (skipped=1)\n{fail}\nRan 5 tests in 0.1s\n\nFAILED (failures=1, skipped=2)", 1),
}[mode]
print(out[0])
sys.exit(out[1])
'''


def env(**extra):
    e = {k: v for k, v in os.environ.items() if k not in ("GOAL_ROLE", "GATE_FIXTURE_MODE", "FIXTURE_FAIL")}
    e.update(GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
             GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
             GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, PYTHONDONTWRITEBYTECODE="1")
    e.update(extra)
    return e


class Repo:
    """A temporary repository with the fixture goal committed and tagged as approved."""

    def __init__(self, plan=None):
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="goalfx-")))
        self.git("init", "-q", "-b", "main")
        self.write(".gitignore", "/.runs/\n__pycache__/\n")
        self.write("docs/spec.md", SPEC)
        self.write("docs/design.md", "# design\n")
        self.write("docs/plan.md", plan or plan_text())
        self.write("tests/test_a.py", TEST_A)
        self.write("tests/test_e2e_flow.py", TEST_E2E)
        self.write("tests/test_b_start.py", TEST_E2E.replace("Flow", "B"))
        self.write("emit.py", EMIT)
        self.commit("F-9: approved goal")
        self.git("tag", "goal/F-9/approved")

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.dir,
                              env=env(), capture_output=True, text=True, check=True).stdout.strip()

    def path(self, rel):
        return self.dir / rel

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def read(self, rel):
        return (self.dir / rel).read_text()

    def edit(self, rel, old, new):
        text = self.read(rel)
        assert old in text, f"{old!r} not in {rel}"
        self.write(rel, text.replace(old, new, 1))

    def tick(self, tid, mark="x"):
        text = self.read("docs/plan.md")
        for m in " x!":
            text = text.replace(f"### [{m}] {tid} ", f"### [{mark}] {tid} ")
        self.write("docs/plan.md", text)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def tree(self, rev="HEAD"):
        return self.git("rev-parse", f"{rev}^{{tree}}")

    def run(self, script, *args, stdin=None, **extra):
        return subprocess.run([sys.executable, str(script), *args], cwd=self.dir, input=stdin,
                              env=env(**extra), capture_output=True, text=True, timeout=120)

    def goal(self, *args, **kw):
        return self.run(GOAL, "--plan", "docs/plan.md", *args, **kw)

    def gate(self, *args, **kw):
        return self.run(GATE, *args, **kw)

    def receipt(self, cmd, name="proof", **kw):
        return self.gate("receipt", "--goal", "F-9", "--cmd", cmd, "--name", name, **kw)

    def verdict(self, name, verdict="PASS", tree=None):
        self.write(f".runs/F-9/verdicts/{name}.md",
                   f"VERDICT: {verdict}\nvendor: codex\nmodel: fixture\neffort: high\nround: 1\n"
                   f"tree: {tree or self.tree()}\n\nNo findings.\n")

    def finish_m1(self):
        """Complete M1's tasks with one commit each."""
        self.write("src/a/x.py", "A = 1\n")
        self.tick("T1")
        self.commit("[T1] alpha")
        self.write("src/b/y.py", "B = 1\n")
        self.tick("T2")
        self.commit("[T2] beta")

    def close(self, mid, commands, partitions=("acceptance",)):
        """Write passing receipts and acceptance verdicts for the current HEAD tree."""
        for cmd in commands:
            res = self.receipt(cmd)
            assert res.returncode == 0, res.stdout + res.stderr
        for part in partitions:
            self.verdict(f"{mid}-{part}")

    def activate(self):
        self.write(".runs/active", json.dumps({"goal": "F-9", "plan": "docs/plan.md"}))
