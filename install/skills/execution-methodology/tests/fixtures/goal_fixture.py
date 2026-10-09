"""Throwaway git repositories holding a small v7 goal, for the goal.py, gate.py and run.sh tests.

The fixture goal F-9 (docs/goals/F-9/plan.md) has two milestones: M1 (T1, T2) and M2 (T3);
plan_text(v71=True) with V71_FILES (spec.md, design.md) makes it a v7.1 goal. Its
gates are tiny unittest suites inside the repository, and `emit.py` prints canned test-runner
output selected by the GATE_FIXTURE_MODE variable, so the same command string
can be made to pass or fail without changing the committed tree.
"""
from __future__ import annotations

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


def task(tid, title, writes, tmc="", state=" ", reads=""):
    return (f"### [{state}] {tid} — {title}\nwrites: {writes}\n" + (f"reads: {reads}\n" if reads else "")
            + (f"tests-may-change: {tmc}\n" if tmc else "") + f"Do the {title} work.\n")


SPEC = """# F-9 spec

**Users and problem.** The fixture user has two problems.

**What changes for the user.** Alpha and beta work.

**Acceptance criteria.**

- AC1 WHEN alpha runs THE SYSTEM SHALL do the alpha work.
- AC2 WHEN beta runs THE SYSTEM SHALL do the beta work.

**Non-goals.** Gamma.

**Constraints.** Standard-library Python.
"""

DESIGN = """# F-9 design

## Interfaces

1. **alpha.** One function.

### Interface detail

Inside the Interfaces section.

## Data touched

Nothing in a store.

## Smallest change

One file.
"""

V71_FILES = {"docs/goals/F-9/spec.md": SPEC, "docs/goals/F-9/design.md": DESIGN}


def plan_text(t2_writes="src/b/**, tests/**", v71=False):
    """The fixture plan; v71 adds reads: to every task, names AC1 and AC2 in T1 and T2, touches an interface."""
    r = "docs/goals/F-9/design.md#interfaces" if v71 else ""
    return f"""---
goal: F-9
title: Fixture outcome
gate: {FULL} -q
full_gate: {FULL}
milestones:
  M1: {{tasks: [T1, T2], e2e: "{E2E}"}}
  M2: {{tasks: [T3], e2e: "{E2E}"}}
touches: [{"interface" if v71 else "none"}]
protected: [docs/design.md]
---

## Outcome

The fixture does two things.

## Tasks

{task("T1", "alpha AC1" if v71 else "alpha", "src/a/**, tests/**", reads=r)}
{task("T2", "beta AC2" if v71 else "beta", t2_writes, tmc="tests/test_a.py", reads=r)}
{task("T3", "gamma", "src/c/**", reads=r)}
## Decisions

- 2026-01-01: fixture decision.

## Parked
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

    def __init__(self, plan=None, files=None):
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="goalfx-")))
        self.git("init", "-q", "-b", "main")
        self.write(".gitignore", "/.runs/\n__pycache__/\n")
        self.write("docs/design.md", "# design\n")
        for rel, text in (files or {}).items():
            self.write(rel, text)
        self.write("docs/goals/F-9/plan.md", plan or plan_text())
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
        text = self.read("docs/goals/F-9/plan.md")
        for m in " x!":
            text = text.replace(f"### [{m}] {tid} ", f"### [{mark}] {tid} ")
        self.write("docs/goals/F-9/plan.md", text)

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
        return self.run(GOAL, *args, **kw)

    def gate(self, *args, **kw):
        return self.run(GATE, *args, **kw)

    def receipt(self, cmd, name="proof", **kw):
        return self.gate("receipt", "--goal", "F-9", "--cmd", cmd, "--name", name, **kw)

    def review(self, body, reviewed="HEAD"):
        self.write(".runs/F-9/review.md", f"reviewed: {self.git('rev-parse', reviewed)}\n\n{body}")

    def close(self):
        """Tick and commit M1's tasks, then write PASS receipts for HEAD's tree and a review."""
        self.write("src/a/x.py", "A = 1\n")
        self.tick("T1")
        self.commit("[T1] alpha")
        self.write("src/b/y.py", "B = 1\n")
        self.tick("T2")
        self.commit("[T2] beta")
        for cmd, name in ((FULL, "full_gate"), (E2E, "e2e")):
            res = self.receipt(cmd, name)
            assert res.returncode == 0, res.stdout + res.stderr
        self.review("No findings.\n")
