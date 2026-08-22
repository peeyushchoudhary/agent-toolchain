#!/usr/bin/env python3
r"""Break-test for sync_methodology.py — proves a DOCUMENTED marker is never read as a DECISION.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
found by mutating this file's sibling and watching the skill's own `unittest discover` stay green,
so a regression re-breaks a named case instead of quietly recording a deferral nobody made.

  1  a real single-line marker                         reported as deliberately deferred
  2  the marker MENTIONED in inline backticks          NOT a deferral   <- the inline half
  3  the marker inside an INDENTED fence, and inside
     a `~~~` fence                                     NOT a deferral   <- both fence spellings
  4  two markers in one README                         "keep exactly one", not first-wins

WHAT MADE THESE CASES REAL, measured rather than imagined. Each mutation below was applied to
sync_methodology.py and each left the vendored suite GREEN:
    `out.append(INLINE_CODE_RE.sub("", line))` -> `out.append(line)`     green
    `if total > 1:` -> dead (two markers, first wins)                    green
    `FENCE_RE` `^\s{0,3}(?:```|~~~)` -> `^(?:```)`                       green
A fifth mutation was tried and RETRACTED, and it is recorded because a retraction is evidence too:
making the marker regex accept multi-line JSON (`\{.*?\}` with `re.DOTALL`) turns the suite RED, so
the single-line rule is genuinely covered and gets no case here. The first attempt at that mutation
dropped `[^\r\n]` WITHOUT adding `re.DOTALL`, which changes no behaviour at all — a green run
against a no-op edit is not a finding, and reporting it as one would be the same error this file
exists to prevent.
`strip_code`'s docstring is the specification these cases enforce: "A repository that documents the
marker — in its own route index, under a fence — must not thereby be reported as having deferred."
The FENCED half of that sentence is covered by the vendored suite. The INLINE half, the INDENTED
fence and the `~~~` fence were covered by nothing, so a repository that merely EXPLAINS the marker
in its own documentation was recorded as having made a decision it never made.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process, in `--adoption-check`
mode, which never writes and always exits 0 — so these cases read its REPORT, and the exit code is
deliberately not the assertion. Nothing here exercises `--check` or the render itself; those are
covered by the vendored suite. Nothing here writes inside the repository.

Run:  python3 sync_methodology_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "sync_methodology.py"
MARKER = '<!-- execution-methodology: {"mode":"deferred","reason":"a real reason","date":"2026-01-05"} -->'

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def adoption_report(readme_body: str) -> tuple[int, str]:
    """Run `--adoption-check` against a throwaway repository carrying `readme_body`."""
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / "docs" / "agents").mkdir(parents=True)
        (repo / "docs" / "agents" / "README.md").write_text(readme_body, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo),
                               "--adoption-check"], capture_output=True, text=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        return proc.returncode, proc.stdout + proc.stderr


def case_a_real_deferral_is_read() -> None:
    """The positive control. Without it, every case below would pass against a reader that reads
    nothing at all."""
    code, out = adoption_report(f"# Agents\n\n{MARKER}\n")
    check("1a --adoption-check always exits 0", code == 0, f"got {code}")
    check("1b a real single-line marker is read as a deliberate deferral",
          "deliberately deferred" in out, out[:300])
    check("1c and the report carries the reason the repository gave",
          "a real reason" in out, out[:300])


def case_inline_backticks_are_not_a_decision() -> None:
    """A route index that EXPLAINS the marker in backticks has not deferred anything."""
    code, out = adoption_report(
        "# Agents\n\n"
        "Record a deferral by adding `" + MARKER + "` to this file.\n")
    check("2a a marker inside inline backticks is not a deferral",
          "deliberately deferred" not in out, out[:400])
    check("2b the repository is reported as unadopted instead",
          "has not been adopted" in out, out[:400])


def case_fenced_examples_are_not_a_decision() -> None:
    for label, body in (
        ("2-space indented ``` fence, as inside a list item",
         "# Agents\n\n- To defer:\n\n  ```\n  " + MARKER + "\n  ```\n"),
        ("a ~~~ fence",
         "# Agents\n\nTo defer:\n\n~~~\n" + MARKER + "\n~~~\n"),
        ("a plain ``` fence, the half the vendored suite already covers",
         "# Agents\n\nTo defer:\n\n```\n" + MARKER + "\n```\n"),
    ):
        code, out = adoption_report(body)
        check(f"3 {label} is not a deferral",
              "deliberately deferred" not in out, out[:400])


def case_two_markers_is_a_problem_not_a_choice() -> None:
    code, out = adoption_report(f"# Agents\n\n{MARKER}\n\nand again:\n\n{MARKER}\n")
    check("4a two markers do not silently become the first one",
          "deliberately deferred" not in out, out[:400])
    check("4b the report says exactly one may be kept",
          "keep exactly one" in out, out[:400])
    check("4c and it counts them, so the reader knows what to remove",
          "2 `execution-methodology` markers" in out, out[:400])


def main() -> int:
    if not SCRIPT.exists():
        print(f"sync_methodology.py not found at {SCRIPT}", file=sys.stderr)
        return 2

    print("sync_methodology break-test")
    for case in (case_a_real_deferral_is_read, case_inline_backticks_are_not_a_decision,
                 case_fenced_examples_are_not_a_decision,
                 case_two_markers_is_a_problem_not_a_choice):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — a documented marker stays documentation; only a declared one is a decision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
