#!/usr/bin/env python3
"""Run every `*_selftest.py` break-test in scripts/ under `unittest discover`.

WHY THIS FILE EXISTS, and it is a finding rather than a convenience. The break-test precedent in
this repository is a SCRIPT beside the checker — progressive-disclosure ships push_guard_selftest.py
and identifier_guard_selftest.py that way, and the shape is right: a human runs one by hand against
the installed file, on the machine where the doubt arose, and reads which gate held. But
`install/verify.sh` runs `python3 -m unittest discover -s tests -t tests` per skill and nothing
else, so a `*_selftest.py` script is executed by NO automated path at all. A break-test nobody runs
is the same failure its own opening line names: a guard nobody has watched fail is not evidence of
anything, and neither is a break-test nobody has watched run.

So the scripts keep their shape and this module gives them a second caller. Each break-test becomes
one test method, run as a subprocess exactly as an operator would run it, with its own output
attached to the failure message so a red run here is as readable as a red run by hand.

THE ROSTER IS DISCOVERED FROM THE DIRECTORY, never listed here. A hardcoded list silently stops
covering a break-test added later, which is the same defect one layer up again. `test_roster_is_not_empty`
fails if discovery finds nothing, because a suite that runs nothing is not a passing suite.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
# `sorted` so the method order is the directory order and a reader can predict it.
SELFTESTS = sorted(SCRIPTS.glob("*_selftest.py"))
# Break-tests spawn real subprocesses, real repositories and real gate commands. The ceiling is
# generous because a timeout here would read as a broken break-test rather than as a slow machine.
TIMEOUT_SECONDS = 300


class BreakTests(unittest.TestCase):
    """One test method per break-test script; the methods are attached below."""

    def _run(self, script: Path) -> None:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                              cwd=str(SCRIPTS), timeout=TIMEOUT_SECONDS)
        detail = (proc.stdout + proc.stderr).strip()
        # Exit 2 is "the break-test could not run" — a missing sibling, no git. Reported as a
        # failure and not skipped: this repository ships the sibling, so absent is a finding.
        self.assertEqual(proc.returncode, 0,
                         f"{script.name} exited {proc.returncode}\n{detail}")


def _attach() -> None:
    for script in SELFTESTS:
        name = f"test_{script.stem}"

        def method(self: BreakTests, script: Path = script) -> None:
            self._run(script)

        method.__name__ = name
        method.__doc__ = f"{script.name} passes every case it declares"
        setattr(BreakTests, name, method)


_attach()


class Roster(unittest.TestCase):
    def test_roster_is_not_empty(self) -> None:
        """Zero discovered break-tests is a finding about discovery, not a clean run."""
        self.assertTrue(SCRIPTS.is_dir(), f"no scripts directory at {SCRIPTS}")
        self.assertGreater(len(SELFTESTS), 0,
                           f"no *_selftest.py break-test found under {SCRIPTS}")

    def test_every_break_test_is_attached(self) -> None:
        """Discovery and attachment must agree; a script found but not attached runs nowhere."""
        attached = {name for name in dir(BreakTests) if name.startswith("test_")}
        expected = {f"test_{script.stem}" for script in SELFTESTS}
        self.assertEqual(attached, expected)


if __name__ == "__main__":
    unittest.main()
