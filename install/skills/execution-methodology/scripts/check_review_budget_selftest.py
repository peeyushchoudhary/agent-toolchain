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
  4  the verdict LINE CAP binds a verdict and never evidence
        methodology.md fixed five caps by ruling — "Card 150 lines, verdict 30 lines ..." — and
        four of them are read by an instrument. This one was prose, so the author's own live
        workspace answers 51 cards (mean 85 lines, 50 of 51 inside the card cap) with 204
        verdict-class files, the longest 1,349 lines. We capped what the agent READS and left what
        it WRITES free. Every case here is PAIRED ON LENGTH: two files of the same length in one
        directory, differing only in what the tool has already decided they are. The evidence half
        is the load-bearing one — a judge that deletes a finding to fit thirty lines is a worse
        outcome than a long verdict.

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
# The documented verdict cap, written here as a LITERAL rather than imported. This file drives the
# installed sibling as a process and asserts on its receipt, so importing the constant would let
# both halves move together and agree about a number the methodology fixed at thirty. Case 4o
# checks that the script still reports this same number, which is the only coupling wanted.
VERDICT_LINE_CAP = 30

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


def sized(tmp: Path, lines: int, *names: str) -> Path:
    """A workspace whose every artifact is exactly `lines` lines long.

    Same shape as `workspace`, and the length is the ONLY difference between the two halves of
    every pair below — a case that varied the name and the length together would prove nothing
    about which one the tool read.
    """
    root = tmp / "workspace"
    (root / "reviews").mkdir(parents=True)
    for name in names:
        (root / "reviews" / name).write_text("finding\n" * lines, encoding="utf-8")
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


def case_the_verdict_cap_binds_verdicts_and_never_evidence() -> None:
    """The rule methodology.md wrote in prose and no instrument read: verdict 30 lines.

    THE WHOLE RISK OF THIS RULE IS OVER-REACH, so every case below is PAIRED on length. Each pair
    holds two files of the SAME length in the SAME directory, differing only in what the tool has
    already decided they are. A checker that measured length alone would trip both halves; one
    that measured nothing would trip neither. Only a checker that caps the VERDICT and leaves the
    EVIDENCE alone splits a pair — and a judge that deletes a finding to fit thirty lines is a
    worse outcome than a long verdict, which is why the evidence half is the load-bearing half.
    """
    over = VERDICT_LINE_CAP + 10
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        code, payload = run(sized(tmp / "verdict", over, "T1-r1-reviewer.md"))
        check("4a a judge verdict past the documented cap is an ERROR",
              "VERDICT_OVER_CAP" in kinds(payload, "errors"), str(payload)[:400])
        check("4b and it stops the dispatch rather than warning about it", code == 1, f"got {code}")

        # THE PAIRED HALF. Same length, same round, same directory — a fix report is the work a
        # judgement provoked and is not a judgement, so it is not capped however long it runs.
        code, payload = run(sized(tmp / "work", over, "T1-r1-fix-report.md"))
        check("4c an implementer's report of the same length is NOT capped",
              "VERDICT_OVER_CAP" not in kinds(payload, "errors"), str(payload)[:400])
        check("4d so the pair distinguishes a verdict reader from a line counter", code == 0,
              f"got {code}")

        # `-test-judge` runs a command and reports an exit code: measured evidence, block rate
        # 0.02 against 0.16 for `reviewer`. It does not spend a round and it is not capped either.
        code, payload = run(sized(tmp / "testjudge", over, "T1-r1-test-judge.md"))
        check("4e a test-judge is evidence and is not capped",
              "VERDICT_OVER_CAP" not in kinds(payload, "errors") and code == 0,
              f"exit {code}, {kinds(payload, 'errors')}")

        # A non-prose suffix is evidence by the rule that already exists. It has its own finding
        # (NON_PROSE_VERDICT) and must not collect a length finding on top of it.
        code, payload = run(sized(tmp / "nonprose", over, "T1-r1-reviewer.txt"))
        check("4f a non-prose artifact is never measured for verdict length",
              "VERDICT_OVER_CAP" not in kinds(payload, "errors"), str(payload)[:400])

        # THE TWO POLARITIES IN ONE FILE. An unrecognised kind is CHARGED as a review (fail
        # closed: never lose a round) and NOT capped (fail open: never cap what may be evidence).
        # A future edit that "tidies" this into one polarity breaks exactly one of these lines.
        code, payload = run(sized(tmp / "unknown", over, "T1-r1-opinion.md"))
        check("4g an unrecognised kind is charged as a review",
              "UNCLASSIFIED_ROUND_ARTIFACT" in kinds(payload, "warnings"), str(payload)[:400])
        check("4h and is NOT capped — charging fails closed, capping fails open",
              "VERDICT_OVER_CAP" not in kinds(payload, "errors"), str(payload)[:400])

        # The boundary. The cap is "thirty lines", so thirty lines passes and thirty-one does not.
        code, payload = run(sized(tmp / "exact", VERDICT_LINE_CAP, "T1-r1-reviewer.md"))
        check("4i a verdict AT the cap is clean — the cap is not off by one",
              code == 0 and not kinds(payload, "errors"), str(payload)[:400])
        code, payload = run(sized(tmp / "one-over", VERDICT_LINE_CAP + 1, "T1-r1-reviewer.md"))
        check("4j and one line over it is a finding",
              "VERDICT_OVER_CAP" in kinds(payload, "errors"), str(payload)[:400])

        # A marker-free judge verdict charges NO round — the counter cannot tell which round it
        # belongs to — but thirty lines is a property of the verdict and not of its round.
        code, payload = run(sized(tmp / "marker-free", over, "T2-security.md"))
        check("4k a marker-free judge verdict is capped even though it charges nothing",
              "VERDICT_OVER_CAP" in kinds(payload, "errors")
              and "MISSING_ROUND_MARKER" in kinds(payload, "warnings"), str(payload)[:400])
        # Its paired half: `review` and `audit` are ordinary nouns and JUDGE_NAME_TOKENS excludes
        # them, so a marker-free name ending in one of those is NOT read as a verdict here.
        code, payload = run(sized(tmp / "ordinary-noun", over, "T2-review.md"))
        check("4l and an ordinary noun in a marker-free name is not promoted to a verdict",
              "VERDICT_OVER_CAP" not in kinds(payload, "errors"), str(payload)[:400])

        # THE SUPPRESSION MUST NOT RUN AHEAD OF THE BOOKKEEPING IT DOES NOT INTEND TO SKIP — the
        # one mechanism this module has recorded four occurrences of. An over-cap verdict still
        # spends its round, so a long verdict cannot buy a free one.
        root = sized(tmp / "still-charged", over, "T1-r1-reviewer.md")
        (root / "reviews" / "T1-r2-reviewer.md").write_text("finding\n" * over, encoding="utf-8")
        code, payload = run(root, "--next", "T1")
        check("4m an over-cap verdict still spends its round",
              "ROUND_BUDGET_EXHAUSTED" in kinds(payload, "errors"), str(payload)[:400])
        check("4n and the receipt reports the length of every verdict it measured, not only the "
              "breaches",
              len(payload.get("receipt", {}).get("verdict_lines", {})) == 2,
              str(payload.get("receipt", {}).get("verdict_lines"))[:300])
        check("4o and the cap it enforced is the documented thirty",
              payload.get("receipt", {}).get("verdict_cap") == VERDICT_LINE_CAP,
              str(payload.get("receipt", {}).get("verdict_cap")))



def case_a_sealed_workspace_is_history() -> None:
    """DEFECT 5, live on the day the cap went binding: it blocked a push over 40 findings in a
    workspace whose milestone had SEALED months earlier and had had no write since. Every round was
    spent, adjudicated and closed; the tool was measuring a graveyard and asking a human to grant
    rounds that could no longer be taken. Re-introducing the miss means deleting the SEALED-RECEIPT
    probe, after which a sealed workspace fails exactly like a live one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "ws"
        work.mkdir()
        # A workspace that WOULD fail: a verdict far over the cap.
        (work / "S1-r1-review.md").write_text("x\n" * 400, encoding="utf-8")

        live_code, live_out = run(work)
        (work / "SEALED-RECEIPT.md").write_text("# Sealed\n", encoding="utf-8")
        code, out = run(work)

        check("a live workspace over the cap still fails", live_code == 1, live_out)
        check("a sealed workspace exits 0", code == 0, out)
        check("and says WHY it checked nothing", out.get("sealed"), out)
        check("naming the receipt it found", out.get("sealed") == "SEALED-RECEIPT.md", out)
        check("with no findings invented", out.get("errors") == [], out)

def main() -> int:
    if not SCRIPT.exists():
        print(f"check_review_budget.py not found at {SCRIPT}", file=sys.stderr)
        return 2

    print("check_review_budget break-test")
    for case in (case_kind_before_the_marker_is_read, case_the_kind_is_not_part_of_the_subject,
                 case_family_spend_is_visible_and_advisory,
                 case_the_verdict_cap_binds_verdicts_and_never_evidence,
                 case_a_sealed_workspace_is_history):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the kind is read where it is written, one artifact keeps one budget, and the "
          "cap binds the verdict without touching the evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
