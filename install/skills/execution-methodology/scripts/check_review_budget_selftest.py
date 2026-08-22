#!/usr/bin/env python3
r"""Break-test for check_review_budget.py — proves the kind is read WHERE THE CORPUS WRITES IT.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
that was LIVE in this file's sibling, and both were measured on real workspaces rather than
imagined.

  1  the kind written BEFORE the round marker is classified
        `<subject>-<kind>-r<N>.md`. The reader only ever looked AFTER the marker, so 129 of 264
        UNCLASSIFIED_ROUND_ARTIFACT warnings across 59 real workspaces were this one shape. The
        tool held the right vocabulary and read it in the wrong position.
  2  the kind inside the name does not become part of the SUBJECT
        `<subj>-spotless-amendment-{architecture,builder,contract,general,methodology,security}-rN`
        was six pseudo-subjects, each spending its own budget: 51 artifacts, rounds to r14, on ONE
        artifact under review.
  3  FAMILY_SPEND makes a renamed lineage visible, and stays ADVISORY

CASE 1 IS PAIRED IN THE ONLY WAY THAT PROVES ANYTHING. `T1-security-r3.md` must trip ROUND_CAP and
`T1-fix-r3.md` must not — same position, same structure, different kind. A reader that classified
nothing would charge both as reviews and trip both; a reader that charged nothing would trip
neither. Only a reader that actually reads the head distinguishes them.

A LIVE DEFECT THIS FILE DOES NOT COVER, recorded here rather than left to be rediscovered. The
documented `<subject>-<kind>-r<N>.md` order still mis-warns when the kind is `rereview`:

    ROUND_RE = [-_.](?:r|round|fixround|rereview[-_.]?r|attempt)0*(\d+)(?![0-9])
    stem `T1-rereview-r2` -> the match is the WHOLE span `-rereview-r2`
                          -> tail = ''   head = 'T1'   kind_of(...) = None
                          -> UNCLASSIFIED_ROUND_ARTIFACT

`rereview` is the one kind word ROUND_RE also claims as a marker spelling, so it is swallowed by
its own marker before `trailing_kind_tokens` is ever called with it — and that function handles it
correctly when it is. The round is still charged, so this is noise plus a remedy that tells the
author to rename a file which already follows the other shape this module documents. NO CASE IS
WRITTEN FOR IT because the defect is live: a case asserting the right answer would fail today.
The reproduction above is the case, ready to switch on with the fix.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process over a workspace
directory in a temporary location. The ledger rules, the terminal pass and the workspace size
budget are covered by the vendored suite and are not duplicated here. Nothing here writes inside
the repository.

Run:  python3 check_review_budget_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_review_budget.py"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def workspace(tmp: Path, *names: str) -> Path:
    root = tmp / "workspace"
    (root / "reviews").mkdir(parents=True)
    for name in names:
        (root / "reviews" / name).write_text("x\n", encoding="utf-8")
    return root


def run(root: Path, *extra: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), str(root), "--json", *extra],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.returncode, {"_stdout": proc.stdout[:400], "_stderr": proc.stderr[:400]}


def kinds(payload: dict, key: str) -> list[str]:
    return [item.get("kind") for item in payload.get(key, [])]


def case_kind_before_the_marker_is_read() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        code, payload = run(workspace(tmp / "review", "T1-security-r3.md"))
        check("1a a REVIEW kind before the marker spends rounds and trips the cap",
              "ROUND_CAP" in kinds(payload, "errors"), str(payload)[:300])
        check("1b and it is not reported as an unrecognised kind",
              "UNCLASSIFIED_ROUND_ARTIFACT" not in kinds(payload, "warnings"),
              str(payload.get("warnings"))[:300])

        code, payload = run(workspace(tmp / "work", "T1-fix-r3.md"))
        check("1c a WORK kind at the same position and round spends nothing",
              "ROUND_CAP" not in kinds(payload, "errors"), str(payload)[:300])
        check("1d so the pair distinguishes a reader from a charger", code == 0, f"got {code}")

        code, payload = run(workspace(tmp / "clean", "T1-review-r1.md", "T1-r2-rereview.md"))
        check("1e both written orders coexist in one workspace without a warning",
              not kinds(payload, "warnings"), str(payload.get("warnings"))[:300])


def case_the_kind_is_not_part_of_the_subject() -> None:
    """Six kinds on one artifact are one budget, not six."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Two rounds already spent on ONE artifact, written with the kind in the name. If the kind
        # leaked into the subject key these would be two subjects of one round each, and a third
        # round would be granted.
        root = workspace(tmp, "T1-review-r1.md", "T1-security-r2.md")
        code, payload = run(root, "--next", "T1")
        check("2a two kinds on one artifact are ONE subject with its budget spent",
              "ROUND_BUDGET_EXHAUSTED" in kinds(payload, "errors"), str(payload)[:400])
        check("2b and the third round is refused before dispatch, not after it", code == 1,
              f"got {code}")

        # The negative half: one round spent leaves one, so the refusal above is not unconditional.
        one = workspace(tmp / "one", "T1-review-r1.md")
        code, payload = run(one, "--next", "T1")
        check("2c a subject with one round left is still dispatchable",
              "ROUND_BUDGET_EXHAUSTED" not in kinds(payload, "errors"), str(payload)[:300])

        # And the same two rounds written the OTHER way round agree with each other.
        other = workspace(tmp / "other", "T1-r1-review.md", "T1-r2-security.md")
        code, payload = run(other, "--next", "T1")
        check("2d the two written orders reach the same budget for the same artifact",
              "ROUND_BUDGET_EXHAUSTED" in kinds(payload, "errors"), str(payload)[:300])


def case_family_spend_is_visible_and_advisory() -> None:
    """Renaming a subject resets its budget. No per-subject line can say so, so this one does."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root = workspace(tmp, "T1-r1-review.md", "T1-spotless-r1.md",
                         "T1-spotless-amendment-r1.md")
        code, payload = run(root)
        family = [item for item in payload.get("warnings", [])
                  if item.get("kind") == "FAMILY_SPEND"]
        check("3a a lineage split by qualifier is reported as one family", bool(family),
              str(payload.get("warnings"))[:400])
        if not family:
            return
        members = family[0].get("members") or []
        check("3b every member is NAMED, so the total can be acted on",
              {"t1", "t1-spotless", "t1-spotless-amendment"} <= set(members), str(members))
        check("3c the inner family is not elided into the outermost root",
              len(members) >= 3, str(members))
        check("3d and it is advisory: it raises no error and changes no exit code",
              code == 0 and "FAMILY_SPEND" not in kinds(payload, "errors"),
              f"exit {code}, errors {kinds(payload, 'errors')}")


def main() -> int:
    if not SCRIPT.exists():
        print(f"check_review_budget.py not found at {SCRIPT}", file=sys.stderr)
        return 2

    print("check_review_budget break-test")
    for case in (case_kind_before_the_marker_is_read, case_the_kind_is_not_part_of_the_subject,
                 case_family_spend_is_visible_and_advisory):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the kind is read where it is written, and one artifact keeps one budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
