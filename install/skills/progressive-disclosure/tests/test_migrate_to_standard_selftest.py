"""`unittest discover` executes the migrator's break-test, so `install/verify.sh` does too.

The break-test itself is `scripts/migrate_to_standard_selftest.py`, a hand-runnable script matching
the house shape of `push_guard_selftest.py`. This module is the thin bridge, and it exists because
of a measured gap: `install/verify.sh` runs `python3 -m unittest discover -s tests -t tests` per
skill and runs no `*_selftest.py` at all, so the two break-tests already in this directory are
executed by NOTHING automated. A break-test nobody runs is not evidence.

`migrate_to_standard.py` is the ONLY script in this toolchain licensed to rename files and rewrite
their contents. It was, before this pair of files, the only writing script with no break-test at
all.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SELFTEST = (Path(__file__).resolve().parents[1] / "scripts"
            / "migrate_to_standard_selftest.py")


class MigrateToStandardSelftest(unittest.TestCase):
    def test_break_test_passes(self) -> None:
        self.assertTrue(SELFTEST.is_file(), f"missing break-test: {SELFTEST}")
        proc = subprocess.run([sys.executable, str(SELFTEST)],
                              capture_output=True, text=True, timeout=300)
        # The whole output, not a tail: a failing case names itself and the reason, and truncating
        # that turns a diagnosable failure into "the selftest failed".
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
