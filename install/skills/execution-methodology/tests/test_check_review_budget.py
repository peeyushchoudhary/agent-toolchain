#!/usr/bin/env python3
"""Tests for check_review_budget.py — the methodology v3.1 review-budget REPORT.

Run: python3 -m unittest tests.test_check_review_budget  (from the skill root)
  or python3 tests/test_check_review_budget.py
"""

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_review_budget.py"

# {ledger path: the copy of the script for which that ledger is a COMMITTED AUTHORITY}. See
# `track()` — the tool now resolves a named ledger against the repository holding the SCRIPT, so a
# test that wants a grant to apply has to run a script that really lives with its ledger.
_AUTHORITIES: dict[str, Path] = {}


def script_for(*extra: str) -> Path:
    """The script to invoke: the authority copy built for this `--grants` path, else the real one."""
    for i, arg in enumerate(extra):
        if arg == "--grants" and i + 1 < len(extra):
            return _AUTHORITIES.get(extra[i + 1], SCRIPT)
    return SCRIPT


def run(workspace: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script_for(*extra)), str(workspace), "--json", *extra],
        capture_output=True, text=True,
    )


def findings(proc: subprocess.CompletedProcess) -> dict:
    return json.loads(proc.stdout)


class CheckReviewBudgetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, rel: str, content: str = "x\n"):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_clean_workspace_passes(self):
        self.touch("ledger.md")
        self.touch("cards/T1.yaml")
        self.touch("reviews/T1-review.md")
        self.touch("reviews/T1-r2-rereview.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = findings(proc)
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["warnings"], [])

    def test_round_three_is_refused(self):
        self.touch("reviews/T1-r3-rereview.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        kinds = {e["kind"] for e in findings(proc)["errors"]}
        self.assertIn("ROUND_CAP", kinds)

    def test_round_two_is_allowed(self):
        self.touch("reviews/T1-r2-rereview.md")
        self.assertEqual(run(self.ws).returncode, 0)

    def test_round_markers_group_under_one_subject(self):
        """r-, round-, fixround-, attempt- spellings of one artifact are one subject."""
        self.touch("reviews/T9-round4.md")
        self.touch("reviews/T9-fixround3.md")
        self.touch("reviews/T9-attempt5-rereview.md")
        errors = findings(run(self.ws))["errors"]
        cap = [e for e in errors if e["kind"] == "ROUND_CAP"]
        self.assertEqual(len(cap), 1, errors)
        self.assertEqual(cap[0]["round"], 5)

    def test_round_marker_in_any_filename_trips_the_cap(self):
        """A high round number is caught wherever it appears, whatever the surrounding name."""
        self.touch("reviews/M1-01-spotless-r15.yaml")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(cap[0]["round"], 15)

    def test_next_subject_with_spent_budget_is_refused_before_dispatch(self):
        """The pre-dispatch refusal: two rounds on record means the third is refused."""
        self.touch("reviews/T1-r1-review.md")
        self.touch("reviews/T1-r2-rereview.md")
        proc = run(self.ws, "--next", "T1")
        self.assertEqual(proc.returncode, 1)
        refused = [e for e in findings(proc)["errors"]
                   if e["kind"] == "ROUND_BUDGET_EXHAUSTED"]
        self.assertEqual(len(refused), 1, proc.stdout)
        self.assertEqual(refused[0]["subject"], "t1")

    def test_next_subject_with_budget_remaining_is_allowed(self):
        self.touch("reviews/T1-r1-review.md")
        self.assertEqual(run(self.ws, "--next", "T1").returncode, 0)
        self.assertEqual(run(self.ws, "--next", "T2").returncode, 0)

    def test_version_suffix_is_not_a_round(self):
        """v3, schema-v1 and similar version tokens are not review rounds."""
        self.touch("cards/v3-stage2-plan.md")
        self.touch("reports/schema-v1-notes.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_diff_snapshots_are_banned_in_every_spelling(self):
        for name in ("reports/T1-final.diff", "reports/T1.patch", "reports/T2.diff.txt"):
            self.touch(name)
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        banned = [e for e in findings(proc)["errors"] if e["kind"] == "BANNED_CLASS"]
        self.assertEqual(len(banned), 3, proc.stdout)

    def test_meta_artifacts_are_banned_in_every_spelling(self):
        for name in ("reports/T2-correction-packet.md", "reports/T2_correction_packet.md",
                     "reports/packet.md", "reviews/gate2-plan-review-invalid-attempt.md",
                     "reviews/T3-authority-review-no-verdict.md",
                     "reviews/T4-second-replacement-no-progress.md"):
            self.touch(name)
        errors = findings(run(self.ws))["errors"]
        self.assertEqual(len([e for e in errors if e["kind"] == "BANNED_CLASS"]), 6)

    def test_raw_dumps_and_persisted_prompts_are_banned(self):
        """v3.1: a .raw verdict dump and a persisted dispatch prompt are workspace debris."""
        for name in ("verdicts/T5-r1-test-judge.raw", "reports/T5-reviewer-prompt.md",
                     "prompts/T5-anything-at-all.md"):
            self.touch(name)
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1)
        banned = [e for e in findings(proc)["errors"] if e["kind"] == "BANNED_CLASS"]
        self.assertEqual(len(banned), 3, proc.stdout)

    def test_a_prompt_shaped_subject_name_is_not_banned(self):
        """Only the artifact classes are banned, not subjects that contain the word."""
        self.touch("verdicts/prompt-engine-r1-reviewer.md")
        self.assertEqual(run(self.ws).returncode, 0)

    def test_escalation_brief_is_permitted(self):
        """The founder-facing escalation brief is mandated by the methodology, not banned."""
        self.touch("reports/gate2-escalation-brief.md")
        self.assertEqual(run(self.ws).returncode, 0)

    def test_max_round_is_configurable(self):
        self.touch("reviews/T1-r3.md")
        self.assertEqual(run(self.ws, "--max-round", "3").returncode, 0)
        self.assertEqual(run(self.ws, "--max-round", "2").returncode, 1)

    def test_workspace_budget_warns_but_does_not_block(self):
        for i in range(60):
            self.touch(f"reports/T{i}-report.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0)
        data = findings(proc)
        self.assertEqual([w["kind"] for w in data["warnings"]], ["WORKSPACE_BUDGET"])

    def test_missing_workspace_is_a_usage_error(self):
        proc = run(self.ws / "nope")
        self.assertEqual(proc.returncode, 2)


class ReviewVsFixArtifactTest(unittest.TestCase):
    """A review round is spent by a REVIEW artifact (a judge verdict), never by a FIX artifact.

    The three subjects below are the historical workspaces the artifact-counting logic got wrong;
    each asserts the verdict the founder ratified as correct on 2026-08-20.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, rel: str, content: str = "x\n"):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def d201(self):
        """D201-BYPASS-SHAPE-HYGIENE: one review round, plus fix reports at r1 and r2."""
        self.touch("D201-BYPASS-SHAPE-HYGIENE-r1-fix-brief.md")
        self.touch("reports/D201-BYPASS-SHAPE-HYGIENE-r1-report.md")
        self.touch("reports/D201-BYPASS-SHAPE-HYGIENE-r2-report.md")
        self.touch("verdicts/D201-BYPASS-SHAPE-HYGIENE-r1-reviewer.md")
        self.touch("verdicts/D201-BYPASS-SHAPE-HYGIENE-r1-tenancy-rls-validator.md")
        self.touch("verdicts/D201-BYPASS-SHAPE-HYGIENE-r1-test-judge.md")
        self.touch("verdicts/D201-BYPASS-SHAPE-HYGIENE-full-diff-reviewer.md")
        self.touch("verdicts/D201-BYPASS-SHAPE-HYGIENE-full-diff-test-judge.md")

    def entry53(self):
        """ENTRY53-REWRITE: one review round; the r3 marker lives on a FIX brief."""
        self.touch("ENTRY53-REWRITE-r3-fix-brief.md")
        self.touch("verdicts/ENTRY53-REWRITE-r1-reviewer.md")
        self.touch("verdicts/ENTRY53-REWRITE-r1-test-judge.md")
        self.touch("verdicts/ENTRY53-REWRITE-full-diff-reviewer.md")

    def d185d(self):
        """D185D: one review round; two fix rounds; a verdict named `r1fix-test-judge`."""
        self.touch("D185D-r1-fix-brief.md")
        self.touch("D185D-r2-fix-brief.md")
        self.touch("reports/D185D-implementation.md")
        self.touch("reports/D185D-r1-fix-report.md")
        self.touch("reports/D185D-r2-fix-report.md")
        self.touch("verdicts/D185D-r1-reviewer.md")
        self.touch("verdicts/D185D-r1-security-validator.md")
        self.touch("verdicts/D185D-r1-test-judge.md")
        self.touch("verdicts/D185D-r1fix-test-judge.md")
        self.touch("verdicts/D185D-terminal-fulldiff-reviewer.md")

    # --- the three historical subjects -------------------------------------------------

    def test_d201_second_review_round_is_allowed(self):
        self.d201()
        proc = run(self.ws, "--next", "D201-BYPASS-SHAPE-HYGIENE")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_entry53_fix_brief_does_not_trip_the_round_cap(self):
        self.entry53()
        proc = run(self.ws, "--next", "ENTRY53-REWRITE")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_d185d_second_review_round_is_allowed(self):
        self.d185d()
        proc = run(self.ws, "--next", "D185D")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    # --- the control must still bite ---------------------------------------------------

    def test_two_genuine_review_rounds_still_exhaust_the_budget(self):
        self.touch("verdicts/T7-r1-reviewer.md")
        self.touch("verdicts/T7-r1-test-judge.md")
        self.touch("T7-r1-fix-brief.md")
        self.touch("reports/T7-r1-fix-report.md")
        self.touch("verdicts/T7-r2-reviewer.md")
        self.touch("verdicts/T7-r2-test-judge.md")
        proc = run(self.ws, "--next", "T7")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        refused = [e for e in findings(proc)["errors"]
                   if e["kind"] == "ROUND_BUDGET_EXHAUSTED"]
        self.assertEqual(len(refused), 1, proc.stdout)
        self.assertEqual(refused[0]["round"], 2)

    def test_a_genuine_third_review_round_is_still_refused(self):
        """THE invariant. Judge verdicts at r1, r2 and r3 must still trip the standing cap."""
        for r in (1, 2, 3):
            self.touch(f"verdicts/T8-r{r}-reviewer.md")
            self.touch(f"verdicts/T8-r{r}-test-judge.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(len(cap), 1, proc.stdout)
        self.assertEqual(cap[0]["round"], 3)
        self.assertEqual(cap[0]["subject"], "t8")
        proc = run(self.ws, "--next", "T8")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED",
                      {e["kind"] for e in findings(proc)["errors"]})

    def test_fix_artifacts_alone_never_spend_a_review_round(self):
        self.touch("T9-r1-fix-brief.md")
        self.touch("T9-r2-fix-brief.md")
        self.touch("reports/T9-r1-fix-report.md")
        self.touch("reports/T9-r2-fix-report.md")
        proc = run(self.ws, "--next", "T9")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_a_verdict_named_r1fix_is_counted_as_a_review(self):
        """`D185D-r1fix-test-judge.md` is a judge verdict at round 1, not an unparsable name."""
        self.touch("verdicts/T10-r1fix-test-judge.md")
        self.touch("verdicts/T10-r2fix-test-judge.md")
        proc = run(self.ws, "--next", "T10")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        refused = [e for e in findings(proc)["errors"]
                   if e["kind"] == "ROUND_BUDGET_EXHAUSTED"]
        self.assertEqual(len(refused), 1, proc.stdout)
        self.assertEqual(refused[0]["subject"], "t10")

    # --- nothing round-marked may be dropped in silence --------------------------------

    def test_unclassifiable_round_artifact_is_reported(self):
        self.touch("T11-r1-quux.md")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = findings(proc)
        unclassified = [w for w in data["warnings"]
                        if w["kind"] == "UNCLASSIFIED_ROUND_ARTIFACT"]
        self.assertEqual(len(unclassified), 1, proc.stdout)
        self.assertEqual(unclassified[0]["path"], "T11-r1-quux.md")

    def test_unclassifiable_round_artifact_still_counts_toward_the_budget(self):
        """Fails closed: an unreadable kind is charged as a review, never quietly dropped."""
        self.touch("T12-r1-quux.md")
        self.touch("T12-r2-quux.md")
        proc = run(self.ws, "--next", "T12")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED",
                      {e["kind"] for e in findings(proc)["errors"]})


def track(path: Path) -> Path:
    """Make `path` a ledger the tool accepts as an AUTHORITY — honestly, not by forging one.

    THIS HELPER USED TO BE THE FORGERY IT WAS TESTING. It ran `git init` and `git add` in the
    file's own throwaway directory and its docstring said "`git add` is enough", because the tool
    asked `git ls-files --error-unmatch` in THE FILE'S OWN DIRECTORY — a question the caller
    answers for themselves. A test suite that ships the bypass recipe cannot catch it, and this one
    did not.

    The tool now asks two questions instead: does the ledger resolve inside the repository holding
    THE SCRIPT, and does it exist at HEAD. Neither can be satisfied by building a repository around
    the ledger alone. So the authority is built for real — a repository containing a genuine copy
    of the script WITH the ledger committed beside it — and `run()` invokes that copy. The script
    copy sits under `authority/scripts/` so the ledger stays NON-DEFAULT for that copy (its default
    would be `authority/ROUND-GRANTS.tsv`), which is what the non-default cases need to exercise.
    """
    top = path.parent

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(top), *args], capture_output=True, check=True)

    if not (top / ".git").exists():
        git("init", "-q")
        git("config", "user.email", "tests@example.invalid")
        git("config", "user.name", "tests")
    copy = top / "authority" / "scripts" / "check_review_budget.py"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(SCRIPT.read_bytes())
    git("add", "--", str(path.relative_to(top)), "authority/scripts/check_review_budget.py")
    git("commit", "-q", "--allow-empty", "-m", "ledger")
    _AUTHORITIES[str(path)] = copy
    return path


class RoundGrantTest(unittest.TestCase):
    """A founder round grant is DATA THIS TOOL READS (council ruling 2026-08-20, `bdcb7369`).

    The thing every case below tries to falsify: a grant line may ONLY EVER SUPPRESS `ROUND_CAP`
    for the one (subject, round) pair it names exactly. It may never raise a cap, never create a
    round, and never turn a refusal into a pass for a pair it does not name.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str, content: str = "x\n"):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def ledger(self, *lines: str) -> Path:
        """Write a grants file. Each line is already tab-separated, or a raw malformed line."""
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_text("# SUBJECT\tROUND\tCOMMIT\tDATE\tREASON\n" + "".join(
            line + "\n" for line in lines))
        return track(path)

    def grant(self, subject: str, rnd: str) -> str:
        return "\t".join([subject, rnd, "deadbee1", "2026-08-20", "founder ruling, one round"])

    def go(self, grants: Path, *extra: str) -> subprocess.CompletedProcess:
        return run(self.ws, "--grants", str(grants), *extra)

    def kinds(self, proc, key="errors") -> set:
        return {f["kind"] for f in findings(proc)[key]}

    # --- the negative control, and the one thing a grant is allowed to do ---------------

    def test_without_the_grant_line_the_workspace_still_fails(self):
        """THE NEGATIVE CONTROL. A mechanism that passes with the line absent proves nothing."""
        self.touch("verdicts/D185D-r3-reviewer.md")
        proc = self.go(self.ledger())
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(len(cap), 1, proc.stdout)
        self.assertEqual((cap[0]["subject"], cap[0]["round"]), ("d185d", 3))

    def test_the_grant_line_suppresses_exactly_that_pair(self):
        self.touch("verdicts/D185D-r3-reviewer.md")
        proc = self.go(self.ledger(self.grant("d185d", "r3")))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    # --- everything a grant must NOT do ------------------------------------------------

    def test_a_grant_never_creates_a_round_for_the_subject_it_names(self):
        """The grant unblocks the WORKSPACE, never the SUBJECT: D185D is still refused."""
        self.touch("verdicts/D185D-r3-reviewer.md")
        proc = self.go(self.ledger(self.grant("d185d", "r3")), "--next", "D185D")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        refused = [e for e in findings(proc)["errors"]
                   if e["kind"] == "ROUND_BUDGET_EXHAUSTED"]
        self.assertEqual(len(refused), 1, proc.stdout)
        self.assertEqual(refused[0]["round"], 3)

    def test_a_grant_does_not_cover_a_later_round_on_the_same_subject(self):
        self.touch("verdicts/D185D-r3-reviewer.md")
        self.touch("verdicts/D185D-r4-reviewer.md")
        proc = self.go(self.ledger(self.grant("d185d", "r3")))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(len(cap), 1, proc.stdout)
        self.assertEqual(cap[0]["round"], 4)

    def test_a_grant_does_not_cover_another_subject_at_the_same_round(self):
        self.touch("verdicts/T21-r3-reviewer.md")
        proc = self.go(self.ledger(self.grant("t20", "r3")))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual([c["subject"] for c in cap], ["t21"], proc.stdout)

    def test_a_grant_does_not_lower_the_bar_for_a_round_it_does_not_name(self):
        """A grant at r3 leaves an r5 breach exactly as loud as it was."""
        self.touch("verdicts/T22-r5-reviewer.md")
        self.assertEqual(self.go(self.ledger(self.grant("t22", "r3"))).returncode, 1)

    def test_a_grant_does_not_clear_a_spent_terminal_pass(self):
        self.touch("verdicts/T23-full-diff-reviewer.md")
        proc = self.go(self.ledger(self.grant("t23", "r3")),
                       "--next", "T23-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("TERMINAL_PASS_SPENT", self.kinds(proc))

    def test_a_grant_does_not_clear_a_banned_class(self):
        self.touch("reports/T24-r3-final.diff")
        proc = self.go(self.ledger(self.grant("t24", "r3")))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("BANNED_CLASS", self.kinds(proc))

    def test_a_missing_grants_file_grants_nothing(self):
        self.touch("verdicts/T25-r3-reviewer.md")
        proc = self.go(Path(self._led.name) / "absent.tsv")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_CAP", self.kinds(proc))
        self.assertIn("GRANTS_FILE_MISSING", self.kinds(proc, "warnings"))

    def test_a_malformed_grant_line_grants_nothing_and_is_named(self):
        """Fail closed: an unparsable line must not widen what is permitted, nor vanish."""
        self.touch("verdicts/T26-r3-reviewer.md")
        proc = self.go(self.ledger("t26 r3 deadbee1 2026-08-20 space separated, not tabs"))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_CAP", self.kinds(proc))
        self.assertIn("GRANT_LINE_MALFORMED", self.kinds(proc, "warnings"))

    # --- a grant that protects nothing must say so -------------------------------------

    def test_a_grant_at_a_round_the_subject_never_reached_is_reported_stale(self):
        self.touch("verdicts/T27-r1-reviewer.md")
        proc = self.go(self.ledger(self.grant("t27", "r3")))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        stale = [w for w in findings(proc)["warnings"] if w["kind"] == "STALE_GRANT"]
        self.assertEqual(len(stale), 1, proc.stdout)
        self.assertEqual((stale[0]["subject"], stale[0]["round"]), ("t27", 3))

    def test_a_grant_for_a_subject_this_workspace_does_not_hold_is_not_stale(self):
        """The ledger spans milestones; a sealed subject is out of scope here, not stale."""
        self.touch("verdicts/T28-r1-reviewer.md")
        proc = self.go(self.ledger(self.grant("authz-b5a", "r3")))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("STALE_GRANT", self.kinds(proc, "warnings"))

    # --- subject keys that collide are REPORTED, never re-keyed ------------------------

    def test_separator_variants_are_reported_as_colliding_subject_keys(self):
        """Reported only. Re-keying subject derivation would silently re-key every grant."""
        for name in ("AUTHZ_B3P1", "AUTHZ-B3P1", "AUTHZ.B3P1"):
            self.touch(f"verdicts/{name}-r1-reviewer.md")
        proc = self.go(self.ledger())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        coll = [w for w in findings(proc)["warnings"]
                if w["kind"] == "COLLIDING_SUBJECT_KEYS"]
        self.assertEqual(len(coll), 1, proc.stdout)
        self.assertEqual(coll[0]["keys"], ["authz-b3p1", "authz.b3p1", "authz_b3p1"])

    def test_a_grant_key_mistyped_as_a_separator_variant_is_reported(self):
        self.touch("verdicts/AUTHZ-B5a-r1-reviewer.md")
        proc = self.go(self.ledger(self.grant("authz_b5a", "r1")))
        coll = [w for w in findings(proc)["warnings"]
                if w["kind"] == "COLLIDING_SUBJECT_KEYS"]
        self.assertEqual(len(coll), 1, proc.stdout)
        self.assertIn("authz_b5a", coll[0]["keys"])


class KindVocabularyTest(unittest.TestCase):
    """The four short-form specialist suffixes this repository actually writes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.grants = Path(self._led.name) / "ROUND-GRANTS.tsv"
        self.grants.write_text("# none\n")
        track(self.grants)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def go(self, *extra: str):
        return run(self.ws, "--grants", str(self.grants), *extra)

    def test_short_form_specialist_verdicts_spend_a_round_and_are_not_unclassified(self):
        for kind in ("security", "tenancy", "provider", "crosscheck"):
            with self.subTest(kind=kind):
                for f in self.ws.rglob("*.md"):
                    f.unlink()
                self.touch(f"verdicts/T30-r1-{kind}.md")
                self.touch(f"verdicts/T30-r2-{kind}.md")
                proc = self.go("--next", "T30")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                data = findings(proc)
                self.assertIn("ROUND_BUDGET_EXHAUSTED", {e["kind"] for e in data["errors"]})
                self.assertNotIn("UNCLASSIFIED_ROUND_ARTIFACT",
                                 {w["kind"] for w in data["warnings"]})


class SilentUndercountTest(unittest.TestCase):
    """The two measured silent-undercount classes: a missing round marker, and non-prose files."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.grants = Path(self._led.name) / "ROUND-GRANTS.tsv"
        self.grants.write_text("# none\n")
        track(self.grants)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def go(self, *extra: str):
        return run(self.ws, "--grants", str(self.grants), *extra)

    def test_a_verdict_with_no_round_marker_is_named_rather_than_dropped_in_silence(self):
        """MEASURED 2026-08-20: an unmarked architect verdict was a free round, and said nothing.

        An unrecognised KIND already warned; a missing ROUND MARKER did not. This closes that
        asymmetry. The file is still not CHARGED — the round it belongs to is unknowable from the
        name — but it is no longer invisible.
        """
        self.touch("verdicts/T31-r1-reviewer.md")
        self.touch("verdicts/T31-architect-verdict.md")
        proc = self.go("--next", "T31-r2-reviewer")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        missing = [w for w in findings(proc)["warnings"]
                   if w["kind"] == "MISSING_ROUND_MARKER"]
        self.assertEqual([w["path"] for w in missing],
                         ["verdicts/T31-architect-verdict.md"], proc.stdout)

    def test_the_missing_marker_warning_does_not_silently_charge_a_round(self):
        self.touch("verdicts/T32-reviewer.md")
        proc = self.go("--next", "T32")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_a_terminal_pass_is_not_a_missing_round_marker(self):
        self.touch("verdicts/T33-full-diff-reviewer.md")
        proc = self.go()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("MISSING_ROUND_MARKER",
                         {w["kind"] for w in findings(proc)["warnings"]})

    def test_a_report_with_no_round_marker_does_not_warn(self):
        for name in ("reports/T34-implementation.md", "T34-fix-brief.md", "ledger.md"):
            self.touch(name)
        proc = self.go()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("MISSING_ROUND_MARKER",
                         {w["kind"] for w in findings(proc)["warnings"]})

    def test_non_prose_artifacts_are_not_charged_as_review_rounds(self):
        """A JUnit XML, a probe log and a source file are evidence, not judgements."""
        self.touch("evidence/T35-R3-GREEN-suite.xml")
        self.touch("evidence/T35-R4-probe.txt")
        self.touch("evidence/T35-r5-registry.tsx")
        proc = self.go("--next", "T35")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_a_prose_verdict_at_the_same_round_is_still_charged(self):
        """The control for the case above: the suffix is what changed, not the round marker."""
        self.touch("evidence/T36-R3-GREEN-suite.md")
        proc = self.go()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(cap[0]["round"], 3, proc.stdout)


class SuppressionOrderTest(unittest.TestCase):
    """BLOCK 1 and its family: a suppression must never run before bookkeeping it does not skip.

    The council killed the previous design because two exemptions COMPOSED — a grant-marked
    terminal artifact never populated `terminals`, so TERMINAL_PASS_SPENT could not fire. The
    non-prose suffix filter reproduced that defect by FILE EXTENSION, from a different direction.
    These cases pin the ordering of the terminal record. They do not close the class:
    occurrence four was written after they passed, at the `continue` that jumps `charged`.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.grants = Path(self._led.name) / "ROUND-GRANTS.tsv"
        self.grants.write_text("# none\n")
        track(self.grants)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def go(self, *extra: str):
        return run(self.ws, "--grants", str(self.grants), *extra)

    def test_a_terminal_pass_is_registered_whatever_its_suffix(self):
        """BLOCK 1. A second terminal pass must not be purchasable by renaming .md to .txt."""
        for suffix in (".md", ".txt", ".xml", ".tsx"):
            with self.subTest(suffix=suffix):
                for f in list(self.ws.iterdir()):
                    f.unlink()
                self.touch(f"SUBJ-full-diff-reviewer{suffix}")
                proc = self.go("--next", "SUBJ-full-diff-reviewer")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("TERMINAL_PASS_SPENT",
                              {e["kind"] for e in findings(proc)["errors"]})

    def test_a_non_prose_verdict_is_named_rather_than_dropped_in_silence(self):
        """A round that costs only a file extension to skip is not a budget.

        CHANGED IN D208, and the change is the whole point: this asserted the finding was in
        `warnings`, and it WAS, and RC was 0 anyway — three `.txt` verdicts bought three rounds
        while this test watched them be named. The property under test (`named rather than dropped
        in silence`) is unchanged and is asserted over BOTH lists; the severity is asserted
        separately in NonProseVerdictIsAnErrorTest, which is the part that was missing.
        """
        self.touch("verdicts/AUTHZ-B7b-r1-reviewer.txt")
        self.touch("verdicts/AUTHZ-B7b-r2-reviewer.txt")
        proc = self.go("--next", "AUTHZ-B7b-r3-reviewer")
        f = findings(proc)
        named = [x["path"] for x in f["errors"] + f["warnings"]
                 if x["kind"] == "NON_PROSE_VERDICT"]
        self.assertEqual(sorted(named), ["verdicts/AUTHZ-B7b-r1-reviewer.txt",
                                         "verdicts/AUTHZ-B7b-r2-reviewer.txt"], proc.stdout)

    def test_genuine_evidence_files_are_still_not_named_as_verdicts(self):
        """The control for the case above: evidence carries no judge token and must stay quiet.

        Load-bearing now that NON_PROSE_VERDICT is an ERROR: `-registry.tsx` and `-probe.txt` are
        source and evidence carried into a workspace, and they must not stop a dispatch.
        """
        self.touch("evidence/T35-R3-GREEN-suite.xml")
        self.touch("evidence/T35-R4-probe.txt")
        self.touch("evidence/T35-r5-registry.tsx")
        proc = self.go()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        f = findings(proc)
        self.assertNotIn("NON_PROSE_VERDICT", {x["kind"] for x in f["errors"] + f["warnings"]})


class GrantKeyingTest(unittest.TestCase):
    """BLOCK 2: a grant suppresses the pair it NAMES, never a pair it merely outranks."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def ledger(self, *lines: str) -> Path:
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_text("".join(line + "\n" for line in lines))
        return track(path)

    def grant(self, subject: str, rnd: str) -> str:
        return "\t".join([subject, rnd, "deadbee1", "2026-08-20", "founder ruling, one round"])

    def test_a_grant_at_the_top_round_does_not_absorb_a_lower_ungranted_round(self):
        """THE INVARIANT. r3 and r4 on disk, only r4 granted: r3 was named by nobody."""
        self.touch("verdicts/T40-r3-reviewer.md")
        self.touch("verdicts/T40-r4-reviewer.md")
        proc = run(self.ws, "--grants", str(self.ledger(self.grant("t40", "r4"))))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(len(cap), 1, proc.stdout)
        self.assertEqual(cap[0]["ungranted"], [3], proc.stdout)

    def test_both_over_cap_rounds_granted_does_suppress(self):
        """The control: naming EVERY over-cap pair is what a suppression costs."""
        self.touch("verdicts/T41-r3-reviewer.md")
        self.touch("verdicts/T41-r4-reviewer.md")
        proc = run(self.ws, "--grants",
                   str(self.ledger(self.grant("t41", "r3"), self.grant("t41", "r4"))))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_a_merged_lineage_grant_does_not_unblock_the_lineage_it_cannot_see(self):
        """`S2-01-R18-r1` and `S2-01-R19-r1` both derive `s2-01` — a MERGE, reproduced.

        Fixed by keying the grant on every charged round, NOT by changing `subject_of`: re-keying
        subject derivation is D205 and would silently re-key every line already in the ledger.
        """
        self.touch("verdicts/S2-01-R18-r1-reviewer.md")
        self.touch("verdicts/S2-01-R19-r1-reviewer.md")
        proc = run(self.ws, "--grants", str(self.ledger(self.grant("s2-01", "r19"))))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        cap = [e for e in findings(proc)["errors"] if e["kind"] == "ROUND_CAP"]
        self.assertEqual(cap[0]["ungranted"], [18], proc.stdout)

    def test_a_grant_in_force_is_announced_with_its_attribution(self):
        self.touch("verdicts/T42-r3-reviewer.md")
        proc = run(self.ws, "--grants", str(self.ledger(self.grant("t42", "r3"))))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        applied = [w for w in findings(proc)["warnings"] if w["kind"] == "GRANT_APPLIED"]
        self.assertEqual(len(applied), 1, proc.stdout)
        self.assertEqual((applied[0]["subject"], applied[0]["round"], applied[0]["commit"]),
                         ("t42", 3, "deadbee1"), proc.stdout)

    def test_a_banned_over_cap_artifact_does_not_also_read_as_a_stale_grant(self):
        """A banned artifact still charges its round, so its grant is needed, not prunable."""
        self.touch("verdicts/T43-r1-reviewer.md")
        self.touch("reports/T43-r3-final.diff")
        proc = run(self.ws, "--grants", str(self.ledger(self.grant("t43", "r3"))))
        self.assertNotIn("STALE_GRANT", {w["kind"] for w in findings(proc)["warnings"]},
                         proc.stdout)

    def test_the_stale_grant_warning_does_not_advise_destroying_the_record(self):
        """It is 50% false-positive on real data; acting on it would delete a founder decision."""
        self.touch("verdicts/T44-r1-reviewer.md")
        proc = run(self.ws, "--grants", str(self.ledger(self.grant("t44", "r3"))))
        stale = [w for w in findings(proc)["warnings"] if w["kind"] == "STALE_GRANT"]
        self.assertEqual(len(stale), 1, proc.stdout)
        self.assertIn("IN THIS WORKSPACE", stale[0]["why"])
        self.assertNotIn("prune it", stale[0]["why"])


class GrantAuthorityTest(unittest.TestCase):
    """BLOCK 3: the ledger must be an authority, not a path the caller chooses."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        (self.ws / "verdicts").mkdir()
        (self.ws / "verdicts" / "T50-r3-reviewer.md").write_text("x\n")

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def line(self, subject="t50", rnd="r3", commit="deadbee1", date="2026-08-20", reason="ruling"):
        return "\t".join([subject, rnd, commit, date, reason])

    def write(self, *lines: str) -> Path:
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_text("".join(line + "\n" for line in lines))
        return path

    def test_an_untracked_ledger_grants_nothing_and_is_named(self):
        """`--grants /tmp/forged.tsv` is the rejected untracked file, one flag further away."""
        forged = self.write(self.line())
        proc = run(self.ws, "--grants", str(forged))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        data = findings(proc)
        kinds = {e["kind"] for e in data["errors"]}
        self.assertIn("GRANTS_FILE_UNTRACKED", kinds, proc.stdout)
        self.assertIn("ROUND_CAP", kinds, proc.stdout)
        self.assertEqual([e["path"] for e in data["errors"]
                          if e["kind"] == "GRANTS_FILE_UNTRACKED"], [str(forged)])

    def test_the_same_ledger_tracked_does_grant(self):
        """The control: tracked-ness is the whole difference between the two runs."""
        proc = run(self.ws, "--grants", str(track(self.write(self.line()))))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(findings(proc)["errors"], [], proc.stdout)

    def test_a_non_default_ledger_is_flagged_even_when_tracked(self):
        proc = run(self.ws, "--grants", str(track(self.write(self.line()))))
        self.assertIn("NON_DEFAULT_GRANTS", {w["kind"] for w in findings(proc)["warnings"]})

    def test_the_ledger_that_was_read_is_reported_in_json(self):
        ledger = track(self.write(self.line()))
        data = findings(run(self.ws, "--grants", str(ledger)))
        self.assertEqual(data["grants"]["path"], str(ledger))
        self.assertFalse(data["grants"]["default"])
        self.assertEqual(data["grants"]["entries"], 1)

    def test_the_ledger_is_named_on_every_plain_text_run(self):
        """A control that consults an authority without naming it cannot be audited."""
        ledger = track(self.write(self.line()))
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.ws),
                               "--grants", str(ledger)], capture_output=True, text=True)
        self.assertIn(f"grants: {ledger}", proc.stdout)
        self.assertIn("NON-DEFAULT", proc.stdout)

    def test_a_line_missing_any_attribution_field_grants_nothing(self):
        for label, line in (
            ("empty commit", self.line(commit="")),
            ("empty date", self.line(date="")),
            ("empty reason", self.line(reason="")),
            ("commit not a hash", self.line(commit="not-a-sha")),
        ):
            with self.subTest(label=label):
                proc = run(self.ws, "--grants", str(track(self.write(line))))
                self.assertEqual(proc.returncode, 1, proc.stdout)
                data = findings(proc)
                self.assertIn("ROUND_CAP", {e["kind"] for e in data["errors"]}, proc.stdout)
                self.assertIn("GRANT_LINE_MALFORMED",
                              {w["kind"] for w in data["warnings"]}, proc.stdout)

    def test_a_duplicate_pair_keeps_the_first_line_and_names_the_second(self):
        ledger = track(self.write(self.line(commit="1111111", reason="the real one"),
                                  self.line(commit="2222222", reason="the shadow")))
        proc = run(self.ws, "--grants", str(ledger))
        data = findings(proc)
        dupes = [w for w in data["warnings"] if w["kind"] == "DUPLICATE_GRANT"]
        self.assertEqual(len(dupes), 1, proc.stdout)
        applied = [w for w in data["warnings"] if w["kind"] == "GRANT_APPLIED"]
        self.assertEqual(applied[0]["commit"], "1111111", proc.stdout)

    def test_an_unreadable_ledger_fails_closed_with_parsable_output(self):
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_bytes(b"\xff\xfe not utf-8 \x00\x80\n")
        proc = run(self.ws, "--grants", str(track(path)))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        data = findings(proc)  # must not be a traceback
        self.assertIn("GRANTS_FILE_UNREADABLE", {e["kind"] for e in data["errors"]}, proc.stdout)

    def test_a_marker_free_short_form_specialist_verdict_is_named(self):
        """`verdicts/ENTRY53-security.md` — the exact short form this repo writes 27 of."""
        for kind in ("security", "tenancy", "provider", "crosscheck"):
            with self.subTest(kind=kind):
                target = self.ws / "verdicts" / f"ENTRY53-{kind}.md"
                target.write_text("x\n")
                proc = run(self.ws, "--grants", str(track(self.write(self.line()))))
                named = [w["path"] for w in findings(proc)["warnings"]
                         if w["kind"] == "MISSING_ROUND_MARKER"]
                self.assertIn(f"verdicts/ENTRY53-{kind}.md", named, proc.stdout)
                target.unlink()


# The terminal-marked artifact names that exist across the live workspaces, with the subject key
# each one derived BEFORE the exemption was removed. Pinned as data: removing `TERMINAL_RE` from
# `subject_of` would re-key every one of them and orphan the grants written against the old keys,
# so the strip is kept and this is the thing that proves it was.
TERMINAL_SHAPES = (
    ("AUTHZ-B3A3-full-diff-reviewer.md", "authz-b3a3"),
    ("AUTHZ-B3P5A-full-diff-2-founder-authorised-reviewer.md", "authz-b3p5a"),
    ("AUTHZ-B3P5A-full-diff-reviewer.md", "authz-b3p5a"),
    ("AUTHZ-B3S-terminal-fulldiff-reviewer.md", "authz-b3s-terminal"),
    ("AUTHZ-B3b-full-diff-reviewer.md", "authz-b3b"),
    ("AUTHZ-B5-full-diff-review.md", "authz-b5"),
    ("AUTHZ-B5a-full-diff-reviewer.md", "authz-b5a"),
    ("AUTHZ-B5a-full-diff-security-validator.md", "authz-b5a"),
    ("AUTHZ-B5d-terminal-fulldiff-reviewer.md", "authz-b5d-terminal"),
    ("AUTHZ-B6-full-diff-review.md", "authz-b6"),
    ("AUTHZ-B6-full-diff-security.md", "authz-b6"),
    ("AUTHZ-B7b-full-diff-review.md", "authz-b7b"),
    ("AUTHZ-B7b-full-diff-security.md", "authz-b7b"),
    ("D185D-terminal-fulldiff-reviewer.md", "d185d-terminal"),
    ("D185D-terminal-fulldiff-security-validator.md", "d185d-terminal"),
    ("D188-LESSONS-full-diff-reviewer.md", "d188-lessons"),
    ("D192-full-diff-review.md", "d192"),
    ("D201-BYPASS-SHAPE-HYGIENE-full-diff-reviewer.md", "d201-bypass-shape-hygiene"),
    ("D201-BYPASS-SHAPE-HYGIENE-full-diff-test-judge.md", "d201-bypass-shape-hygiene"),
    ("ENTRY53-REWRITE-full-diff-reviewer.md", "entry53-rewrite"),
    ("ENTRY53-REWRITE-full-diff-test-judge.md", "entry53-rewrite"),
    ("ESCALATION-review-budget-vs-full-diff-pass.md", "escalation-review-budget-vs"),
    ("VA-BRANCH-FULLDIFF-r1-reviewer.md", "va-branch"),
    ("VA-BRANCH-FULLDIFF-r1-security-validator.md", "va-branch"),
    ("m1-branch-full-diff-r1-reviewer.md", "m1-branch"),
    ("s10-t4-portal-sessions-fulldiff-r1-reviewer.md", "s10-t4-portal-sessions"),
    ("s10-t4-portal-sessions-fulldiff-r1-security.md", "s10-t4-portal-sessions"),
    ("s10-t4-portal-sessions-fulldiff-r1-tenancy.md", "s10-t4-portal-sessions"),
    ("s10-t4-portal-sessions-fulldiff-r2-reviewer.md", "s10-t4-portal-sessions"),
    ("s10-t4-portal-sessions-fulldiff-r2-security.md", "s10-t4-portal-sessions"),
)


class TerminalExemptionRemovedTest(unittest.TestCase):
    """D207. The terminal exemption is GONE; a terminal pass is a row in the ledger.

    The thing every case below tries to falsify: NO TOKEN IN A FILENAME BUYS ANYTHING. The
    exemption was keyed on `full-diff` appearing in a name written by the party the control binds,
    and it produced all three occurrences of one mechanism — a suppression running ahead of
    bookkeeping it did not intend to skip — including the occurrence its own repair created. Two
    repairs relocated it. Removal is the third answer, and these cases pin what removal means.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def ledger(self, *lines: str) -> Path:
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_text("# SUBJECT\tROUND\tCOMMIT\tDATE\tREASON\n"
                        + "".join(line + "\n" for line in lines))
        return track(path)

    def row(self, subject: str, token: str) -> str:
        return "\t".join([subject, token, "deadbee1", "2026-08-20", "founder ruling"])

    def go(self, grants: Path, *extra: str):
        return run(self.ws, "--grants", str(grants), *extra)

    # --- F1: the token buys no round ---------------------------------------------------

    def test_a_round_marked_name_carrying_the_terminal_token_is_charged(self):
        """F1, REPRODUCED BEFORE THE FIX AT RC=0 PRINTING `clean: 3 files`.

        Three verdicts named `<subj>-r<N>-full-diff-reviewer.md` charged NOTHING and warned about
        nothing, because the terminal branch `continue`d before `marks`, `seen_rounds` and
        `charged`. A review budget defeated by a substring, while the tool reported `clean`.
        """
        for rnd in (1, 2, 3):
            self.touch(f"verdicts/SUBJ-r{rnd}-full-diff-reviewer.md")
        proc = self.go(self.ledger(), "--next", "SUBJ-r4-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        kinds = {e["kind"] for e in findings(proc)["errors"]}
        self.assertIn("ROUND_BUDGET_EXHAUSTED", kinds, proc.stdout)
        self.assertIn("ROUND_CAP", kinds, proc.stdout)

    def test_the_token_makes_no_difference_to_the_verdict(self):
        """THE NEGATIVE CONTROL FOR THE CASE ABOVE. The token is the only variable."""
        outcomes = {}
        for label, name in (("token", "SUBJ-r{}-full-diff-reviewer.md"),
                            ("plain", "SUBJ-r{}-reviewer.md")):
            for f in sorted(self.ws.rglob("*")):
                if f.is_file():
                    f.unlink()
            for rnd in (1, 2, 3):
                self.touch("verdicts/" + name.format(rnd))
            proc = self.go(self.ledger(), "--next", "SUBJ-r4-reviewer")
            outcomes[label] = (proc.returncode,
                               tuple(sorted(e["kind"] for e in findings(proc)["errors"])))
        self.assertEqual(outcomes["token"], outcomes["plain"], outcomes)

    def test_a_next_dispatch_wearing_the_token_at_a_round_is_still_refused(self):
        """`--next SUBJ-r4-full-diff-reviewer` is a fourth scoped round in fancy dress."""
        for rnd in (1, 2):
            self.touch(f"verdicts/SUBJ-r{rnd}-reviewer.md")
        proc = self.go(self.ledger(), "--next", "SUBJ-r4-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    def test_a_terminal_dispatch_past_a_spent_budget_needs_a_LEDGER_ROW(self):
        """The removal, in one case: the name identifies, only the ledger authorises."""
        for rnd in (1, 2):
            self.touch(f"verdicts/SUBJ-r{rnd}-reviewer.md")
        proc = self.go(self.ledger(), "--next", "SUBJ-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    # --- the ledger row, and what it may do -------------------------------------------

    def test_a_terminal_row_honours_the_pass_and_is_reported_apart_from_a_grant(self):
        for rnd in (1, 2):
            self.touch(f"verdicts/SUBJ-r{rnd}-reviewer.md")
        proc = self.go(self.ledger(self.row("subj", "terminal")),
                       "--next", "SUBJ-full-diff-reviewer")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = findings(proc)
        applied = [w for w in data["warnings"] if w["kind"] == "TERMINAL_PASS_APPLIED"]
        self.assertEqual(len(applied), 1, proc.stdout)
        self.assertEqual(applied[0]["commit"], "deadbee1", proc.stdout)
        self.assertEqual([w for w in data["warnings"] if w["kind"] == "GRANT_APPLIED"], [])
        self.assertEqual(data["grants"]["terminal_passes"], 1, proc.stdout)
        self.assertEqual(data["grants"]["round_grants"], 0, proc.stdout)

    def test_the_terminal_row_is_honoured_ONCE_and_the_evidence_is_on_disk(self):
        """Once the pass has been taken, the row does not authorise a second one."""
        for rnd in (1, 2):
            self.touch(f"verdicts/SUBJ-r{rnd}-reviewer.md")
        self.touch("verdicts/SUBJ-full-diff-reviewer.md")
        proc = self.go(self.ledger(self.row("subj", "terminal")),
                       "--next", "SUBJ-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("TERMINAL_PASS_SPENT",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    def test_a_terminal_row_gets_a_grant_row_full_validation(self):
        """Attribution is not optional because the round field says `terminal`."""
        for label, line in (
            ("empty commit", "subj\tterminal\t\t2026-08-20\treason"),
            ("commit not a hash", "subj\tterminal\tnot-a-sha\t2026-08-20\treason"),
            ("empty date", "subj\tterminal\tdeadbee1\t\treason"),
            ("empty reason", "subj\tterminal\tdeadbee1\t2026-08-20\t"),
            ("empty subject", "\tterminal\tdeadbee1\t2026-08-20\treason"),
        ):
            with self.subTest(label=label):
                for rnd in (1, 2):
                    self.touch(f"verdicts/SUBJ-r{rnd}-reviewer.md")
                proc = self.go(self.ledger(line), "--next", "SUBJ-full-diff-reviewer")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                data = findings(proc)
                self.assertIn("GRANT_LINE_MALFORMED",
                              {w["kind"] for w in data["warnings"]}, proc.stdout)
                self.assertIn("ROUND_BUDGET_EXHAUSTED",
                              {e["kind"] for e in data["errors"]}, proc.stdout)

    def test_a_terminal_row_names_one_subject_exactly(self):
        for rnd in (1, 2):
            self.touch("verdicts/OTHER-r%d-reviewer.md" % rnd)
        proc = self.go(self.ledger(self.row("subj", "terminal")),
                       "--next", "OTHER-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    def test_a_terminal_row_does_not_suppress_the_round_cap(self):
        """It authorises a DISPATCH. It is not a round grant and may not act as one."""
        self.touch("verdicts/SUBJ-r3-reviewer.md")
        proc = self.go(self.ledger(self.row("subj", "terminal")))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_CAP", {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    def test_a_round_grant_does_not_authorise_a_terminal_pass(self):
        """The converse. Two row types, two authorities, neither substitutable."""
        for rnd in (1, 2):
            self.touch(f"verdicts/SUBJ-r{rnd}-reviewer.md")
        proc = self.go(self.ledger(self.row("subj", "r3")),
                       "--next", "SUBJ-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    def test_a_second_terminal_row_for_one_subject_keeps_the_first(self):
        self.touch("verdicts/SUBJ-r1-reviewer.md")
        proc = self.go(self.ledger(
            "\t".join(["subj", "terminal", "1111111", "2026-08-20", "the real one"]),
            "\t".join(["subj", "terminal", "2222222", "2026-08-20", "the shadow"])))
        data = findings(proc)
        dupes = [w for w in data["warnings"] if w["kind"] == "DUPLICATE_TERMINAL_PASS"]
        self.assertEqual(len(dupes), 1, proc.stdout)
        self.assertEqual(data["grants"]["terminal_passes"], 1, proc.stdout)

    def test_a_terminal_artifact_no_row_records_it_is_named(self):
        self.touch("verdicts/SUBJ-full-diff-reviewer.md")
        proc = self.go(self.ledger())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        named = [w["path"] for w in findings(proc)["warnings"]
                 if w["kind"] == "UNRECORDED_TERMINAL_PASS"]
        self.assertEqual(named, ["verdicts/SUBJ-full-diff-reviewer.md"], proc.stdout)

    def test_a_terminal_artifact_is_recorded_whatever_its_suffix(self):
        """The bookkeeping runs before every suppression, so no suffix can hide a pass."""
        for suffix in (".md", ".txt", ".xml", ".tsx"):
            with self.subTest(suffix=suffix):
                for f in sorted(self.ws.rglob("*")):
                    if f.is_file():
                        f.unlink()
                self.touch(f"SUBJ-full-diff-reviewer{suffix}")
                proc = self.go(self.ledger(), "--next", "SUBJ-full-diff-reviewer")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("TERMINAL_PASS_SPENT",
                              {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    # --- F2: an unrecognised kind on a non-prose suffix ---------------------------------

    def test_an_unrecognised_kind_on_a_non_prose_suffix_is_named(self):
        """F2, REPRODUCED BEFORE THE FIX AT RC=0 WITH NO WARNING AT ALL.

        `NON_PROSE_VERDICT` required `kind_of(...) == "review"`, so kind None — the case the prose
        branch charges PRECISELY to fail closed — fell through uncharged and unwarned. This is r1's
        security-F2 verbatim, and it would have been the fourth occurrence of the mechanism.
        """
        self.touch("verdicts/AUTHZ-B7b-r1-opinion.txt")
        self.touch("verdicts/AUTHZ-B7b-r2-opinion.txt")
        proc = self.go(self.ledger())
        named = sorted(w["path"] for w in findings(proc)["warnings"]
                       if w["kind"] == "NON_PROSE_UNCLASSIFIED")
        self.assertEqual(named, ["verdicts/AUTHZ-B7b-r1-opinion.txt",
                                 "verdicts/AUTHZ-B7b-r2-opinion.txt"], proc.stdout)

    def test_no_round_marked_non_prose_artifact_is_dropped_in_silence(self):
        """The general property F2 was one instance of: review, work, and unknown are exhaustive."""
        for name in ("verdicts/A-r1-reviewer.txt", "verdicts/B-r1-opinion.txt",
                     "evidence/C-r1-probe.txt", "evidence/D-r1-report.txt"):
            self.touch(name)
        # CHANGED IN D208: reads `errors` too, because NON_PROSE_VERDICT is now an error. The
        # property — review, work and unknown are exhaustive and none is dropped in silence — is
        # what this test is for and it is unchanged.
        f = findings(self.go(self.ledger()))
        warned = {x["path"] for x in f["errors"] + f["warnings"]
                  if x["kind"] in ("NON_PROSE_VERDICT", "NON_PROSE_UNCLASSIFIED")}
        # `-report` is a recognised WORK kind and is correctly silent; the other three are not.
        self.assertEqual(warned, {"verdicts/A-r1-reviewer.txt", "verdicts/B-r1-opinion.txt",
                                  "evidence/C-r1-probe.txt"})

    # --- the strip stays: subject keys must not move ------------------------------------

    def test_subject_keys_are_unchanged_for_every_terminal_marked_shape(self):
        """`subject_of` KEEPS stripping the terminal marker. Deleting the strip with the exemption
        would re-key `D185D-full-diff-reviewer.md` from `d185d` to `d185d-full-diff-reviewer` and
        orphan every grant written against the old derivation."""
        sys.path.insert(0, str(SCRIPT.parent))
        import check_review_budget as module
        for name, expected in TERMINAL_SHAPES:
            with self.subTest(name=name):
                self.assertEqual(module.subject_of(name), expected)

    def test_every_row_in_the_shipped_ledger_still_resolves(self):
        """Each live grant, exercised on the DEFAULT ledger against an artifact at its round."""
        shipped = SCRIPT.parent.parent / "ROUND-GRANTS.tsv"
        if not shipped.is_file():
            self.skipTest("no operator ledger beside this copy (vendored tree ships without it)")
        rows = [line.split("\t") for line in shipped.read_text().splitlines()
                if line.strip() and not line.startswith("#")]
        self.assertTrue(rows)
        for fields in rows:
            subject, token = fields[0].strip(), fields[1].strip()
            with self.subTest(subject=subject, token=token):
                for f in sorted(self.ws.rglob("*")):
                    if f.is_file():
                        f.unlink()
                if token.lower() == "terminal":
                    # No shipped row is terminal today; when one is written this arm asserts the
                    # pass is honoured rather than silently skipping the row.
                    self.touch(f"verdicts/{subject.upper()}-r1-reviewer.md")
                    proc = run(self.ws, "--next", f"{subject.upper()}-full-diff-reviewer")
                    self.assertIn("TERMINAL_PASS_APPLIED",
                                  {w["kind"] for w in findings(proc)["warnings"]}, proc.stdout)
                    continue
                rnd = int(token.lstrip("rR"))
                self.touch(f"verdicts/{subject.upper()}-r{rnd}-reviewer.md")
                proc = run(self.ws)
                applied = [w for w in findings(proc)["warnings"]
                           if w["kind"] == "GRANT_APPLIED" and w["subject"] == subject]
                self.assertEqual(len(applied), 1, proc.stdout)
                self.assertEqual(applied[0]["round"], rnd, proc.stdout)

    # --- F3: forging the ledger costs more than `git init` ------------------------------

    def test_a_ledger_in_a_repository_the_caller_created_is_refused(self):
        """F3, REPRODUCED BEFORE THE FIX AT RC=0 WITH THE GRANT APPLIED.

        `mkdir /tmp/f && git init -q && printf ... > g.tsv && git add g.tsv` was honoured although
        `git cat-file -e HEAD:g.tsv` failed — the file existed in no commit anywhere. Once a
        terminal pass is a ledger row the ledger is the SOLE authority for it, so shipping the
        removal on this would have traded a filename token for a `git init`.
        """
        self.touch("verdicts/SUBJ-r3-reviewer.md")
        forged = Path(self._led.name) / "g.tsv"
        forged.write_text(self.row("subj", "r3") + "\n")
        subprocess.run(["git", "init", "-q"], cwd=forged.parent, capture_output=True, check=True)
        subprocess.run(["git", "add", "--", forged.name], cwd=forged.parent,
                       capture_output=True, check=True)
        head = subprocess.run(["git", "-C", str(forged.parent), "cat-file", "-e",
                               f"HEAD:{forged.name}"], capture_output=True)
        self.assertNotEqual(head.returncode, 0, "the forgery must not exist at HEAD")
        proc = run(self.ws, "--grants", str(forged))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        kinds = {e["kind"] for e in findings(proc)["errors"]}
        self.assertIn("GRANTS_FILE_UNTRACKED", kinds, proc.stdout)
        self.assertIn("ROUND_CAP", kinds, proc.stdout)

    def test_committing_inside_the_callers_own_repository_does_not_help(self):
        """The escalation of the case above: `git commit` is one more command, not a review."""
        self.touch("verdicts/SUBJ-r3-reviewer.md")
        forged = Path(self._led.name) / "g.tsv"
        forged.write_text(self.row("subj", "r3") + "\n")
        for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                     ["config", "user.name", "t"], ["add", "--", forged.name],
                     ["commit", "-q", "-m", "forged"]):
            subprocess.run(["git", "-C", str(forged.parent), *args],
                           capture_output=True, check=True)
        head = subprocess.run(["git", "-C", str(forged.parent), "cat-file", "-e",
                               f"HEAD:{forged.name}"], capture_output=True)
        self.assertEqual(head.returncode, 0, "the control: it IS committed, in the caller's repo")
        proc = run(self.ws, "--grants", str(forged))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("GRANTS_FILE_UNTRACKED",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)

    def test_a_ledger_staged_but_not_committed_in_the_right_repository_is_refused(self):
        """The other half: the right repository, and still only an index. An index is not a review."""
        self.touch("verdicts/SUBJ-r3-reviewer.md")
        ledger = Path(self._led.name) / "ROUND-GRANTS.tsv"
        ledger.write_text(self.row("subj", "r3") + "\n")
        track(ledger)                      # builds the authority: script copy + committed ledger
        ledger.write_text(self.row("subj", "r3") + "\n")
        staged = Path(self._led.name) / "STAGED.tsv"
        staged.write_text(self.row("subj", "r3") + "\n")
        subprocess.run(["git", "-C", str(self._led.name), "add", "--", "STAGED.tsv"],
                       capture_output=True, check=True)
        _AUTHORITIES[str(staged)] = _AUTHORITIES[str(ledger)]
        proc = run(self.ws, "--grants", str(staged))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("GRANTS_FILE_UNTRACKED",
                      {e["kind"] for e in findings(proc)["errors"]}, proc.stdout)
        self.assertIn("does not exist at HEAD",
                      " ".join(e["why"] for e in findings(proc)["errors"]), proc.stdout)


# ======================================================================================
# D208 — THE TOOL IS ADVISORY. Founder gate ruling 2026-08-20, after the FOURTH occurrence
# of one mechanism. These do not close the class; they assert the three named corrections
# and the honesty of what the file says about itself.
# ======================================================================================


class NonProseVerdictIsAnErrorTest(unittest.TestCase):
    """CORRECTION 1. Occurrence four: three review rounds bought with a file extension.

    Reproduced before the fix — `verdicts/SUBJ-r1/-r2/-r3-reviewer.txt` then
    `--next SUBJ-r4-reviewer` returned RC=0 with three NON_PROSE_VERDICT WARNINGS and zero errors,
    while the identical files as `.md` returned RC=1. Warnings do not change an exit code. The
    finding is promoted to an ERROR and is still NOT CHARGED: charging it would have spent rounds
    on `T-r2-provider.tsx` and `-security.tsx`, which are source files carried in as evidence.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def test_three_txt_verdicts_no_longer_buy_a_fourth_round(self):
        for n in (1, 2, 3):
            self.touch(f"verdicts/SUBJ-r{n}-reviewer.txt")
        proc = run(self.ws, "--next", "SUBJ-r4-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        kinds = [e["kind"] for e in findings(proc)["errors"]]
        self.assertEqual(kinds.count("NON_PROSE_VERDICT"), 3, proc.stdout)

    def test_the_md_control_still_refuses_so_the_extension_now_costs_nothing_either_way(self):
        for n in (1, 2, 3):
            self.touch(f"verdicts/SUBJ-r{n}-reviewer.md")
        proc = run(self.ws, "--next", "SUBJ-r4-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("ROUND_BUDGET_EXHAUSTED", {e["kind"] for e in findings(proc)["errors"]})

    def test_the_error_does_not_charge_the_round_it_names(self):
        """THE HAZARD, named at the gate: promote it, do NOT charge it into `charged`."""
        self.touch("verdicts/T-r2-provider.tsx")
        self.touch("verdicts/T-r2-security.tsx")
        proc = run(self.ws)
        self.assertEqual(findings(proc)["receipt"]["rounds_charged"], {}, proc.stdout)

    def test_an_unrecognised_kind_on_a_non_prose_suffix_stays_a_warning(self):
        """Its sibling cannot be read as a verdict at all; erroring on every probe log is noise."""
        self.touch("evidence/T-r1-opinion.txt")
        proc = run(self.ws)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("NON_PROSE_UNCLASSIFIED", {w["kind"] for w in findings(proc)["warnings"]})


class GitEnvironmentIsScrubbedTest(unittest.TestCase):
    """CORRECTION 2. F-A: git answers `which repository` from the ENVIRONMENT first.

    Reproduced before the fix — a ledger committed in a caller-made repo at /tmp was correctly
    refused (RC=1), and the SAME file with `GIT_DIR=/tmp/f/.git GIT_WORK_TREE=/tmp/f` was honoured
    (RC=0, GRANT_APPLIED). THIS NARROWS F-A AND DOES NOT CLOSE IT: a caller may still run a COPY of
    the script beside their own committed ledger, and `track()` above ships exactly that recipe.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._forge = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.forge = Path(self._forge.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._forge.cleanup()

    def forged_ledger(self) -> Path:
        """A ledger genuinely COMMITTED in a repository the caller built around it."""
        g = self.forge / "g.tsv"
        g.write_text("forgedsubj\tr3\tdeadbee1\t2026-08-20\tforged by the caller\n")
        for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                     ["config", "user.name", "t"], ["add", "--", "g.tsv"],
                     ["commit", "-q", "-m", "forged"]):
            subprocess.run(["git", "-C", str(self.forge), *args], capture_output=True, check=True)
        return g

    def run_with(self, env_extra: dict, grants: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.ws), "--json", "--grants", str(grants)],
            capture_output=True, text=True, env=env,
        )

    def test_git_dir_cannot_nominate_the_repository_for_a_forged_ledger(self):
        (self.ws / "FORGEDSUBJ-r3-reviewer.md").write_text("x\n")
        g = self.forged_ledger()
        baseline = self.run_with({}, g)
        self.assertEqual(baseline.returncode, 1, baseline.stdout)
        attack = self.run_with(
            {"GIT_DIR": str(self.forge / ".git"), "GIT_WORK_TREE": str(self.forge)}, g)
        self.assertEqual(attack.returncode, 1, attack.stdout)
        f = findings(attack)
        self.assertIn("GRANTS_FILE_UNTRACKED", {e["kind"] for e in f["errors"]}, attack.stdout)
        self.assertNotIn("GRANT_APPLIED", {w["kind"] for w in f["warnings"]}, attack.stdout)

    def test_every_nominating_variable_is_dropped(self):
        (self.ws / "FORGEDSUBJ-r3-reviewer.md").write_text("x\n")
        g = self.forged_ledger()
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CEILING_DIRECTORIES",
                    "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE"):
            with self.subTest(var=var):
                proc = self.run_with({var: str(self.forge / ".git")}, g)
                self.assertNotIn("GRANT_APPLIED",
                                 {w["kind"] for w in findings(proc)["warnings"]}, proc.stdout)

    def test_the_scrub_list_is_passed_to_both_subprocess_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count("env=_scrubbed_env()"), 2, "both git calls, or neither")

    def test_the_containment_assertion_exists_in_code_and_not_only_in_prose(self):
        """`:298-301` asserted this in PROSE and tested it nowhere; that is how F-A survived."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Path(__file__).resolve().is_relative_to(top)", source)


class TerminalSpendIsRecordedInTheLedgerTest(unittest.TestCase):
    """CORRECTION 3. F-C: a `terminal` row is consumed by an ARTIFACT NAME, which is deletable.

    Reproduced before the fix — one founder `terminal` row, three consecutive
    `RC=0 TERMINAL_PASS_APPLIED`. THIS DOES NOT CLOSE F-C. The tool prints the exact
    `terminal-spent` line and honours it; a HUMAN must append it. The unbounded re-dispatch remains
    available to anyone who does not.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def row(self, subject: str, token: str) -> str:
        return "\t".join([subject, token, "deadbee1", "2026-08-20", "founder ruling"])

    def ledger(self, *lines: str) -> Path:
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_text("".join(line + "\n" for line in lines))
        return track(path)

    def spend_workspace(self):
        self.touch("verdicts/SUBJX-r1-reviewer.md")
        self.touch("verdicts/SUBJX-r2-reviewer.md")

    def test_a_terminal_row_grants_nothing_once_the_subject_carries_terminal_spent(self):
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal"),
                        self.row("subjx", "terminal-spent"))
        proc = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        f = findings(proc)
        self.assertIn("ROUND_BUDGET_EXHAUSTED", {e["kind"] for e in f["errors"]}, proc.stdout)
        kinds = {w["kind"] for w in f["warnings"]}
        self.assertIn("TERMINAL_PASS_ALREADY_SPENT", kinds, proc.stdout)
        self.assertNotIn("TERMINAL_PASS_APPLIED", kinds, proc.stdout)

    def test_the_withdrawal_does_not_depend_on_the_order_of_the_two_rows(self):
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal-spent"),
                        self.row("subjx", "terminal"))
        proc = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertNotIn("TERMINAL_PASS_APPLIED",
                         {w["kind"] for w in findings(proc)["warnings"]}, proc.stdout)

    def test_a_terminal_spent_row_alone_authorises_nothing_and_breaks_nothing(self):
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal-spent"))
        proc = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertNotIn("GRANT_LINE_MALFORMED",
                         {w["kind"] for w in findings(proc)["warnings"]}, proc.stdout)

    def test_an_applied_pass_prints_the_exact_line_to_append(self):
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal"))
        proc = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        f = findings(proc)
        advice = [w for w in f["warnings"] if w["kind"] == "TERMINAL_SPEND_UNRECORDED"]
        self.assertEqual(len(advice), 1, proc.stdout)
        line = advice[0]["append_line"]
        fields = line.split("\t")
        self.assertEqual(fields[0], "subjx")
        self.assertEqual(fields[1], "terminal-spent")
        self.assertEqual(len(fields), 5, line)
        self.assertTrue(all(x.strip() for x in fields), line)
        self.assertEqual(f["receipt"]["terminal_spend_to_record"], [line])

    def test_the_printed_line_is_accepted_verbatim_and_withdraws_the_row(self):
        """The advice has to be APPENDABLE, or it is a suggestion the ledger will reject."""
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal"))
        first = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
        line = [w for w in findings(first)["warnings"]
                if w["kind"] == "TERMINAL_SPEND_UNRECORDED"][0]["append_line"]
        with g.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        second = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
        self.assertEqual(second.returncode, 1, second.stdout)
        f = findings(second)
        self.assertNotIn("GRANT_LINE_MALFORMED", {w["kind"] for w in f["warnings"]}, second.stdout)
        self.assertIn("TERMINAL_PASS_ALREADY_SPENT", {w["kind"] for w in f["warnings"]},
                      second.stdout)

    def test_a_recorded_spend_is_in_the_receipt_even_with_no_matching_terminal_row(self):
        """r1-B2: `terminal_spent` was LOCAL, so a spend with a mistyped subject key appeared
        nowhere — not in the ledger counts, not in the receipt, and with no warning. The human who
        appended the printed line would believe it was recorded and the receipt could not
        contradict them, while the next run re-applied the pass at RC=0."""
        self.spend_workspace()
        g = self.ledger(self.row("mistyped-key", "terminal-spent"))
        proc = run(self.ws, "--grants", str(g))
        f = findings(proc)
        recorded = f["receipt"]["terminal_spend_recorded"]
        self.assertEqual([r["subject"] for r in recorded], ["mistyped-key"], proc.stdout)
        self.assertFalse(recorded[0]["withdraws_a_terminal_row"], proc.stdout)
        self.assertEqual(f["grants"]["terminal_spent"], 1, proc.stdout)
        self.assertEqual(f["grants"]["entries"], 1, proc.stdout)

    def test_a_spend_that_does_withdraw_a_row_says_so_in_the_receipt(self):
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal"), self.row("subjx", "terminal-spent"))
        recorded = findings(run(self.ws, "--grants", str(g)))["receipt"]["terminal_spend_recorded"]
        self.assertEqual(len(recorded), 1)
        self.assertTrue(recorded[0]["withdraws_a_terminal_row"])

    def test_f_c_is_still_open_and_this_test_exists_to_say_so(self):
        """NOT A REGRESSION. Without the appended row the pass repeats, exactly as reproduced.

        Recorded as a test rather than a comment so that a future reader cannot mistake the
        `terminal-spent` row for a fix. The control is a HUMAN appending a line; the tool only
        tells them which line.
        """
        self.spend_workspace()
        g = self.ledger(self.row("subjx", "terminal"))
        for attempt in (1, 2, 3):
            with self.subTest(attempt=attempt):
                proc = run(self.ws, "--grants", str(g), "--next", "SUBJX-full-diff-reviewer")
                self.assertEqual(proc.returncode, 0, proc.stdout)
                self.assertIn("TERMINAL_PASS_APPLIED",
                              {w["kind"] for w in findings(proc)["warnings"]}, proc.stdout)


class ReceiptTest(unittest.TestCase):
    """THE RECEIPT IS THE PRODUCT. The exit code is a tripwire; the receipt is what a human reads.

    So nothing in it may be summarised away — a receipt that aggregates its warnings reproduces the
    warning-fatigue failure that made four of them change nothing.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._led = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        self._led.cleanup()

    def touch(self, rel: str):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")

    def ledger(self, *lines: str) -> Path:
        path = Path(self._led.name) / "ROUND-GRANTS.tsv"
        path.write_text("".join(line + "\n" for line in lines))
        return track(path)

    def busy(self) -> subprocess.CompletedProcess:
        """A workspace that emits several DISTINCT warnings plus a grant and an error."""
        self.touch("verdicts/T50-r1-reviewer.md")
        self.touch("verdicts/T50-r2-reviewer.md")
        self.touch("verdicts/T50-r3-reviewer.md")
        self.touch("verdicts/T50-quux.md")
        self.touch("verdicts/T50-r4-quux.md")
        self.touch("evidence/T50-r1-opinion.txt")
        self.touch("verdicts/T51-verdict.md")
        g = self.ledger("\t".join(["t50", "r3", "deadbee1", "2026-08-20", "founder ruling"]))
        return run(self.ws, "--grants", str(g))

    def test_the_receipt_carries_every_warning_verbatim(self):
        proc = self.busy()
        f = findings(proc)
        self.assertGreaterEqual(len({w["kind"] for w in f["warnings"]}), 3, proc.stdout)
        self.assertEqual(f["receipt"]["warnings"], f["warnings"], proc.stdout)
        self.assertEqual(f["receipt"]["errors"], f["errors"], proc.stdout)

    def test_the_receipt_reports_rounds_charged_per_subject(self):
        proc = self.busy()
        charged = findings(proc)["receipt"]["rounds_charged"]
        self.assertEqual(sorted(charged["t50"]), ["1", "2", "3", "4"], proc.stdout)
        self.assertEqual(charged["t50"]["1"], "verdicts/T50-r1-reviewer.md")

    def test_the_receipt_reports_grants_applied_with_attribution(self):
        proc = self.busy()
        applied = findings(proc)["receipt"]["grants_applied"]
        self.assertEqual(len(applied), 1, proc.stdout)
        self.assertEqual(applied[0]["subject"], "t50")
        self.assertEqual(applied[0]["round"], 3)
        self.assertEqual(applied[0]["commit"], "deadbee1")
        self.assertEqual(applied[0]["reason"], "founder ruling")
        self.assertEqual(applied[0]["artifact"], "verdicts/T50-r3-reviewer.md")

    def test_the_receipt_reports_terminal_passes_with_attribution(self):
        self.touch("verdicts/SUBJY-r1-reviewer.md")
        self.touch("verdicts/SUBJY-r2-reviewer.md")
        g = self.ledger("\t".join(["subjy", "terminal", "deadbee1", "2026-08-20", "gate said so"]))
        proc = run(self.ws, "--grants", str(g), "--next", "SUBJY-full-diff-reviewer")
        applied = findings(proc)["receipt"]["terminal_passes_applied"]
        self.assertEqual(len(applied), 1, proc.stdout)
        self.assertEqual(applied[0]["subject"], "subjy")
        self.assertEqual(applied[0]["commit"], "deadbee1")
        self.assertEqual(applied[0]["reason"], "gate said so")

    def test_the_receipt_names_the_script_and_the_workspace_the_caller_chose(self):
        """Both are caller-chosen and neither was reportable: F-A turns on WHICH COPY ran."""
        proc = self.busy()
        r = findings(proc)["receipt"]
        self.assertEqual(r["workspace"], str(self.ws.resolve()))
        self.assertTrue(r["script"].endswith("check_review_budget.py"), r["script"])
        self.assertEqual(r["next"], [])
        self.assertEqual(r["max_round"], 2)

    def test_the_receipt_says_out_loud_that_the_tool_does_not_bind(self):
        advisory = findings(self.busy())["receipt"]["advisory"].lower()
        self.assertIn("does not bind the party that runs it", advisory)
        self.assertIn("merge gate", advisory)

    def test_the_text_output_names_the_script_and_the_workspace_too(self):
        self.touch("verdicts/T60-r1-reviewer.md")
        proc = subprocess.run([sys.executable, str(SCRIPT), str(self.ws)],
                              capture_output=True, text=True)
        self.assertIn("script:", proc.stdout)
        self.assertIn(str(self.ws.resolve()), proc.stdout)


# Phrases this tool has ALREADY BEEN CAUGHT USING to assert a bound it does not hold. Every entry
# was found in shipped text, not imagined: the first two in the v3.0 docstrings, the rest in the
# D208 change itself and in what that change left behind — including one in an EMITTED ERROR that
# goes into the receipt, which is the document the gate made the binding control.
#
# THIS IS A LEDGER OF MISTAKES ALREADY MADE. It is not a filter that catches the next one.   [retracted-quote]
BANNED_BOUND_CLAIMS = (                                                                   # [retracted-quote]
    "enforc", "guarantee", "unbypassable", "tamper-proof", "cannot be evaded",             # [retracted-quote]
    "cannot be bypassed", "impossible to", "permitted once", "cannot be taken twice",      # [retracted-quote]
    "cannot be recorded twice", "cannot recur", "cannot be written", "cannot be forged",   # [retracted-quote]
    "permits one dispatch", "once per subject", "authorises one", "spent once",             # [retracted-quote]
)
# A line carrying this marker is EXEMPT, because a file has to be able to QUOTE the claim it is
# withdrawing — the retraction comments in the module do exactly that, and a guard that forbade
# quotation would force the history out of the file and leave the next reader with no idea which
# sentences were ever false.
#
# THE ABUSE SURFACE, NAMED: anyone can silence this check on any line by typing the marker on it.
# That is not a hole to be closed — it is the same seam as everything else here, since the guard
# is run by the party it reports on. What the marker buys is that the silencing is GREPPABLE and
# shows up in a diff as a deliberate act rather than as a phrase nobody noticed.
RETRACTED_QUOTE = "[retracted-quote]"


def _bound_claims(text: str) -> list[str]:
    """Lines asserting a bound, ignoring lines marked as quoting a retracted one."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if RETRACTED_QUOTE in line:
            continue
        for token in BANNED_BOUND_CLAIMS:
            if token in line.lower():
                out.append(f"{i}: {token!r} in {line.strip()[:90]}")
                break
    return out


class EmittedMessagesAreHonestTest(unittest.TestCase):
    """r1-B1: `:827` was an EMITTED ERROR asserting a bound the module retracts 700 lines above.

    A docstring is read by whoever opens the file; an emitted `why` is read by the operator AND
    carried verbatim into `receipt.warnings`, which the gate ruled is the binding control. This is
    the register that mattered most and the one the first guard could not see.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def terminal_pass_spent(self) -> dict:
        (self.ws / "verdicts").mkdir(parents=True, exist_ok=True)
        (self.ws / "verdicts" / "SUBJ-full-diff-reviewer.md").write_text("x\n")
        proc = run(self.ws, "--next", "SUBJ-full-diff-reviewer")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        found = [e for e in findings(proc)["errors"] if e["kind"] == "TERMINAL_PASS_SPENT"]
        self.assertEqual(len(found), 1, proc.stdout)
        return found[0]

    def test_the_terminal_pass_spent_error_claims_no_once_per_subject_bound(self):
        why = self.terminal_pass_spent()["why"].lower()
        self.assertNotIn("once per subject", why)   # [retracted-quote]
        self.assertNotIn("permitted once", why)     # [retracted-quote]

    def test_it_says_instead_what_it_actually_observed(self):
        why = self.terminal_pass_spent()["why"]
        self.assertIn("ALREADY IN THIS SCANNED DIRECTORY", why)
        self.assertIn("F-C", why)

    def test_it_still_stops_the_dispatch(self):
        """Honesty is not a downgrade: the finding keeps its ERROR severity and its exit code."""
        self.terminal_pass_spent()


class AdvisoryPostureTest(unittest.TestCase):
    """The module must not claim a bound it does not hold. Asserted on the SOURCE TEXT.

    WHAT THIS CHECK ACTUALLY DOES, stated exactly, because the previous version of this docstring
    claimed it "fails on the next rewrite that reaches for the word, whatever register it reaches
    for it in" — AND IT DID NOT AND CANNOT. It matched seven literal tokens, none of which appeared
    in the two false claims sitting in the file it scanned, so the suite was green with the
    retracted claim shipped, and the implementation report leaned on it. A comment asserting
    coverage the code does not provide is worse than none.

    So: this greps two files and the emitted messages for a FIXED LIST OF PHRASES THIS TOOL HAS
    ALREADY BEEN CAUGHT USING (`BANNED_BOUND_CLAIMS`). It catches a repeat, and a repeat only. A
    new register — "holds", "ensures", "one and only one", a sentence with no banned substring at
    all — passes it silently. The list is extended when a judge finds the next one; that is the
    maintenance cost, and it is the honest description of a crude check.
    """

    SOURCE = SCRIPT.read_text(encoding="utf-8")
    TEST_SOURCE = Path(__file__).read_text(encoding="utf-8")

    def docstring(self) -> str:
        return " ".join(ast.get_docstring(ast.parse(self.SOURCE)).split())

    def test_the_module_repeats_no_bound_claim_it_has_already_been_caught_making(self):
        found = _bound_claims(self.SOURCE)
        self.assertEqual(found, [], "check_review_budget.py re-asserts a retracted bound:\n"
                                    + "\n".join(found))

    def test_these_tests_repeat_no_bound_claim_either(self):
        """Two of these phrases shipped HERE, in test prose a reader trusts as much as a comment."""
        found = _bound_claims(self.TEST_SOURCE)
        self.assertEqual(found, [], "the test file re-asserts a retracted bound:\n"
                                    + "\n".join(found))

    def test_the_ledger_header_repeats_no_bound_claim(self):
        shipped = SCRIPT.parent.parent / "ROUND-GRANTS.tsv"
        if not shipped.is_file():
            self.skipTest("no operator ledger beside this copy (vendored tree ships without it)")
        header = shipped.read_text(encoding="utf-8")
        found = _bound_claims(header)
        self.assertEqual(found, [], "ROUND-GRANTS.tsv re-asserts a retracted bound:\n"
                                    + "\n".join(found))

    def test_the_why_literals_in_dict_displays_repeat_no_bound_claim(self):
        """A SECOND, NARROWER PASS over the register that mattered most: `:827` was an EMITTED
        ERROR rather than a docstring, and it goes into `receipt.warnings`, which the gate made the
        binding control. A guard reading only comments would have missed it, and did.

        WHAT THIS ONE REACHES, EXACTLY, because its previous name said "every emitted message" and
        it does not read every emitted message. It collects values under a literal `"why"` key in a
        dict DISPLAY. So it does NOT see: `"why": why` (the identifier, in the BANNED_CLASS emit),
        the `BANNED_PATTERNS` reason strings, the `bad = "..."` parser strings that reach a receipt
        through an f-string, the `advisory` receipt string, `append_line`, or the "nothing visible"
        print. NONE of that is uncovered — the whole-source scan above reads all of it, and this
        method is a sharpened duplicate of that scan, not the only thing standing between a bad
        message and the receipt. The single genuine gap is a `[retracted-quote]` marker on one of
        those other lines, which has no second pass behind it the way a `why` literal does."""
        whys = []
        for node in ast.walk(ast.parse(self.SOURCE)):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "why":
                        whys.append(ast.get_source_segment(self.SOURCE, v) or "")
        # 23 present today (measured: `grep -c '"why":'`, this extraction re-run, and an AST
        # walk all agree — 22 literal or expression values plus the one bare identifier
        # `"why": why`). THAT FIGURE IS INDICATIVE ONLY AND NOTHING CHECKS IT: the floor is a canary
        # against the extraction silently matching NOTHING after a refactor, and it is deliberately
        # not pinned to the exact count, because a test that fails whenever someone adds a message
        # would be retuned rather than read. From 23 the floor of 15 absorbs a drop of 8 before it
        # says anything, which is the price of not being brittle.
        #
        # The prose figure is not self-checking, so the ASSERTION carries the live count instead —
        # any failure here reports what was actually found rather than what a comment once claimed.
        # This comment previously said 25, which was simply wrong, and its second sentence then
        # reasoned from the wrong number. A false count inside the honesty guard's own description
        # is the species this whole task exists to remove.
        self.assertGreaterEqual(len(whys), 15,
                                f"the extraction found {len(whys)} messages to check")
        self.assertEqual(_bound_claims("\n".join(whys)), [])

    def test_the_module_docstring_denies_that_it_binds_before_it_says_anything_else(self):
        doc = self.docstring()
        self.assertIn("THIS TOOL MAKES ROUND SPEND VISIBLE. IT DOES NOT BIND THE PARTY THAT RUNS "
                      "IT.", doc)
        self.assertLess(doc.index("IT DOES NOT BIND"), 300, "it is not said loudly enough")
        self.assertIn("No in-process control can bind its own operator", doc)
        self.assertIn("BINDING CONTROL IS A HUMAN READING THE RECEIPT AT THE MERGE GATE", doc)

    def test_the_module_docstring_names_every_known_open_finding(self):
        doc = self.docstring()
        for needle in (
            "KNOWN-OPEN",
            "F-A, NARROWED AND OPEN",
            "F-C, OPEN AND NOT ADDRESSED",
            "THE CEILING ON THE WHOLE DESIGN",
            "DEFAULT ledger is never git-queried at all",
            "MORE PERMISSIVE THAN THE GRANT IT WAS MODELLED ON",
            "THE ROUND-MARKED TERMINAL ARTIFACT",
            "four occurrences, one mechanism",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, doc)

    def test_the_known_open_section_names_all_four_occurrences(self):
        doc = self.docstring()
        for needle in (
            "1. `full-diff` in a filename bought an exemption outright",
            "2. The repair RELOCATED the exemption",
            "3. The second repair relocated it again",
            "4. `.txt` on three verdict names bought three review rounds",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, doc)

    def test_round_cap_and_budget_exhausted_keep_their_error_severity(self):
        """Advisory describes what the tool can achieve against its operator, not a downgrade."""
        for kind in ("ROUND_CAP", "ROUND_BUDGET_EXHAUSTED", "BANNED_CLASS",
                     "GRANTS_FILE_UNTRACKED", "NON_PROSE_VERDICT"):
            with self.subTest(kind=kind):
                appends = re.findall(r"(errors|warnings)\.append\(\{[^}]*?\"kind\": \"" + kind
                                     + r"\"", self.SOURCE, re.DOTALL)
                self.assertEqual(appends, ["errors"], f"{kind} must be raised as an ERROR")
        for kind in ("NON_PROSE_UNCLASSIFIED", "TERMINAL_PASS_APPLIED", "GRANT_APPLIED",
                     "STALE_GRANT", "TERMINAL_PASS_ALREADY_SPENT"):
            with self.subTest(kind=kind):
                appends = re.findall(r"(errors|warnings)\.append\(\{[^}]*?\"kind\": \"" + kind
                                     + r"\"", self.SOURCE, re.DOTALL)
                self.assertEqual(appends, ["warnings"], f"{kind} must stay a WARNING")

    def test_both_harness_copies_are_byte_identical(self):
        """A control whose answer depends on which harness invoked it is not a control."""
        codex = Path.home() / ".codex" / "skills" / "execution-methodology"
        if not codex.is_dir():
            self.skipTest("no ~/.codex mirror on this machine")
        for rel in ("scripts/check_review_budget.py", "tests/test_check_review_budget.py",
                    "ROUND-GRANTS.tsv"):
            with self.subTest(rel=rel):
                mine = SCRIPT.parent.parent / rel
                if rel == "ROUND-GRANTS.tsv" and not mine.is_file():
                    # Operator data: the vendored public copy ships without the ledger by
                    # invariant, so there is nothing of this copy to compare.
                    continue
                self.assertEqual(mine.read_bytes(), (codex / rel).read_bytes(), rel)


if __name__ == "__main__":
    unittest.main()
