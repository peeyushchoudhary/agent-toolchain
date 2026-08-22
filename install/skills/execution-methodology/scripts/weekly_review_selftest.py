#!/usr/bin/env python3
"""Break-test for weekly_review.py — proves the printed share cannot argue with its own marker.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
found by mutating this file's sibling and watching the skill's own `unittest discover` stay green.

  1  a week one line over the ceiling prints `0.101  BREACH`, not `0.10  BREACH`
  2  a week EXACTLY at the ceiling passes; the ceiling is a ceiling, not a trigger
  3  it is a REPORT: neither week changes the exit code

WHAT MADE THESE CASES REAL, measured rather than imagined. Both mutations below left the vendored
suite GREEN:
    `share_text` `f"{value:5.3f}"` -> `f"{value:5.2f}"`               green
    the weekly marker `> ceiling` -> `>= ceiling`                     green
`share_text`'s own docstring is the specification the first case enforces: "Three decimals, not
two: a week printed as `0.10  BREACH` argues with its own marker." A reader who cannot reconcile
the number with the verdict beside it stops reading the report, and this report has no exit code to
fall back on — it is prose or it is nothing.

THE FIXTURE IS ARITHMETIC, NOT A GUESS. Each repository commits exactly 899 product lines, 1
product-thinking line and 100 or 101 process lines, so the denominator is exactly 1000 or 1001 and
the share lands on 0.100 or just past it. Both cases run against `--ceiling 0.10`, which is the
only value at which the two-decimal rendering and the marker can disagree.

WHAT THIS DOES NOT COVER. Both cases drive the INSTALLED sibling as a process over a real git
repository in a temporary directory, in TEXT mode, because the rendering is the subject. The trend
window, the dead band, the empty-week rule and the unreadable-repository rule are covered by the
vendored suite and are not duplicated here. Nothing here writes inside the repository.

Run:  python3 weekly_review_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "weekly_review.py"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def build(root: Path, process_lines: int) -> Path:
    """899 product lines, 1 product-thinking line, `process_lines` bookkeeping lines, this week."""
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "selftest@example.invalid")
    git(root, "config", "user.name", "selftest")
    (root / "README.md").write_text("# repo\n", encoding="utf-8")     # 1 line, product thinking
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "chore: init")

    source = root / "src" / "App.java"
    source.parent.mkdir(parents=True)
    source.write_text("// product\n" * 899, encoding="utf-8")
    notes = root / "docs" / "agents" / "notes.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("bookkeeping\n" * process_lines, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "feat: the work")
    return root


def review(repo: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--weeks", "1",
                           "--ceiling", "0.10"], capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def week_line(out: str) -> str:
    return next((line for line in out.splitlines()
                 if "-W" in line and ("PASS" in line or "BREACH" in line or "--" in line)), "")


def case_a_breach_prints_a_number_that_agrees_with_it() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = build(Path(td) / "over", 101)          # 101 / 1001 — just past the ceiling
        code, out = review(repo)
        line = week_line(out)
        check("1a a week over the ceiling is marked BREACH", "BREACH" in line, out[:400])
        check("1b and the share beside it is 0.101, which a reader can reconcile",
              "0.101" in line, line or out[:400])
        check("1c never `0.10  BREACH`, which argues with itself",
              "0.10 " not in line.replace("0.101", ""), line)


def case_exactly_at_the_ceiling_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = build(Path(td) / "at", 100)            # 100 / 1000 — exactly the ceiling
        code, out = review(repo)
        line = week_line(out)
        check("2a a week exactly AT the ceiling passes", "PASS" in line, out[:400])
        check("2b and it is not marked BREACH", "BREACH" not in line, line)
        check("2c the share prints as 0.100, so the boundary is visible to the reader",
              "0.100" in line, line or out[:400])


def case_it_is_a_report_and_not_a_gate() -> None:
    """A report that can fail the build would be run by a machine and read by nobody."""
    with tempfile.TemporaryDirectory() as td:
        for label, process_lines in (("over the ceiling", 101), ("at the ceiling", 100)):
            repo = build(Path(td) / label.replace(" ", "-"), process_lines)
            code, out = review(repo)
            check(f"3 a week {label} still exits 0", code == 0, f"got {code}: {out[:200]}")


def main() -> int:
    if not SCRIPT.exists():
        print(f"weekly_review.py not found at {SCRIPT}", file=sys.stderr)
        return 2
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("git is not available; this break-test reads committed history", file=sys.stderr)
        return 2

    print("weekly_review break-test")
    for case in (case_a_breach_prints_a_number_that_agrees_with_it,
                 case_exactly_at_the_ceiling_passes, case_it_is_a_report_and_not_a_gate):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the number and the marker beside it say the same thing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
