"""The bash break-tests, run under unittest so the repository's suite runner can see them.

`verify.sh` discovers `tests/` with `python3 -m unittest discover`. A shell suite sitting beside it
is invisible to that, and an invisible suite is one that stops being run — which is the failure this
repository has already been bitten by once, reported as `NOT TESTED HERE` over a suite that was
right there. So the shell suite is executed from here rather than duplicated here: there is exactly
one definition of what the profile must enforce, and it is the shell file.
"""

import re
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELFTEST = HERE / "selftest.sh"


class ShellBreakTests(unittest.TestCase):
    """Runs selftest.sh once and makes three separate assertions about the run."""

    result = None

    @classmethod
    def setUpClass(cls):
        if not SELFTEST.exists():
            raise unittest.SkipTest(f"no shell suite at {SELFTEST}")
        cls.result = subprocess.run(
            ["/bin/bash", str(SELFTEST)],
            capture_output=True, text=True, timeout=600,
        )

    ANSI = re.compile(r"\x1b\[[0-9;]*m")

    def output(self):
        """Colour-stripped. The shell suite wraps every verdict label in an escape sequence, so a
        plain substring search for `ok` or `FAIL` silently matches nothing — which reads as a
        passing suite that ran no checks rather than as a broken parser."""
        return self.ANSI.sub("", self.result.stdout + self.result.stderr)

    def test_the_shell_suite_passes(self):
        self.assertEqual(
            self.result.returncode, 0,
            "the shell break-tests failed:\n" + self.output(),
        )

    def test_no_individual_check_reported_a_failure(self):
        failed = [ln.strip() for ln in self.output().splitlines() if "FAIL  " in ln]
        self.assertEqual(failed, [], "checks reported FAIL:\n" + "\n".join(failed))

    def test_the_suite_actually_ran_its_checks(self):
        """A suite that exits 0 having run nothing is the failure mode worth guarding.

        The count is asserted as a FLOOR, not an equality: adding a check should never break this
        test, and removing most of them should. An exact number here would be a second copy of the
        suite's length, corrected in one place and stale in the other.
        """
        oks = sum(1 for ln in self.output().splitlines() if "ok    " in ln)
        self.assertGreaterEqual(
            oks, 20,
            f"only {oks} checks reported ok — the suite exited 0 without exercising much:\n"
            + self.output(),
        )


if __name__ == "__main__":
    unittest.main()
