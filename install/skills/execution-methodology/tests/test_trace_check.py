#!/usr/bin/env python3
"""Tests for trace_check.py — the required/declared/executed diff.

Run: python3 -m unittest tests.test_trace_check   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

Every rule is exercised in BOTH directions: a corpus that must produce the finding and a corpus
that must not. A one-sided test on a checker is worth very little — one that fires on everything
passes the failure half and is useless, and the false-positive half is where a check actually dies.

THE EVIDENCE IS REAL, NOT HAND-WRITTEN JSON. Each fixture runs `start_junit_run.py`, writes JUnit
XML, and runs `verify_junit.py` over it, so the receipts under test are the ones the toolchain
actually produces. A stubbed receipt would let this suite pass while the two scripts disagreed
about the one field the freshness boundary rests on.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "trace_check.py"

sys.path.insert(0, str(SCRIPTS))

import trace_check  # noqa: E402  — the path insertion above has to happen first


SPEC = """---
id: F-7
title: Resend a pending invite
prd: docs/product/prd.md
status: {status}
updated: 2026-01-14
{withdrawn}---

# F-7 — Resend a pending invite

## Acceptance criteria
{criteria}
"""
CRITERIA = ("**AC-1** When an admin resends a pending invite, given it has not expired, the system "
            "sends a new mail to the same address.\n"
            "**AC-2** When an admin resends twice inside five minutes, the system refuses and "
            "states the time the next resend is allowed.\n")
PLAN = """---
feature: F-7
title: Resend a pending invite
spec: docs/product/specs/F-7-resend.md
status: approved
updated: 2026-01-14
---

# F-7 — implementation and validation plan

## Validation plan

### Coverage map

| AC | level | task | note |
|---|---|---|---|
{rows}

### Planned tests

```test
covers: {covers}
assert: sends at 09:20
and_not: does not send when the invite is already accepted
```

### Not tested, and why
{absent}

### Gate
`./gradlew test`
"""
ROWS = "| AC-1 | unit | T1 | |\n| AC-2 | unit | T1 | |"
PASSING = [("com.x.ResendTest", "sendsMail__F7_AC1"), ("com.x.ResendTest", "refuses__F7_AC2")]


class TraceFixture(unittest.TestCase):
    """A corpus builder, a real evidence builder, and the two ways the script is driven."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.results = self.root / "build" / "test-results" / "test"
        self.reports = self.root / ".work"
        self.results.mkdir(parents=True)
        self.reports.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def corpus(self, criteria: str = CRITERIA, status: str = "approved", withdrawn: str = "",
               rows: str = ROWS, covers: str = "AC-1", absent: str = "") -> None:
        self.write("docs/product/specs/F-7-resend.md",
                   SPEC.format(criteria=criteria, status=status, withdrawn=withdrawn))
        self.write("docs/product/plans/F-7-resend.md",
                   PLAN.format(rows=rows, covers=covers, absent=absent))

    def xml(self, cases: list[tuple[str, str]]) -> None:
        """One JUnit file per class, counts declared exactly as verify_junit.py requires."""
        classes: dict[str, list[str]] = {}
        for fqcn, name in cases:
            classes.setdefault(fqcn, []).append(name)
        for fqcn, names in classes.items():
            body = "".join(f'  <testcase classname="{fqcn}" name="{name}" time="0.01"/>\n'
                           for name in names)
            (self.results / f"TEST-{fqcn}.xml").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<testsuite name="{fqcn}" tests="{len(names)}" skipped="0" failures="0" '
                f'errors="0">\n{body}</testsuite>\n', encoding="utf-8")

    def evidence(self, cases: list[tuple[str, str]] = None) -> Path:
        """A receipt produced by the real scripts, over XML written between start and verify."""
        cases = PASSING if cases is None else cases
        start, receipt = self.reports / "start.json", self.reports / "evidence.json"
        self.run_script("start_junit_run.py", "--results", str(self.results),
                        "--output", str(start), expect=0)
        self.xml(cases)
        counts = {}
        for fqcn, _ in cases:
            counts[fqcn] = counts.get(fqcn, 0) + 1
        expects = [arg for fqcn, count in counts.items() for arg in ("--expect", f"{fqcn}={count}")]
        self.run_script("verify_junit.py", "--results", str(self.results),
                        "--start-receipt", str(start), "--output", str(receipt), *expects, expect=0)
        return receipt

    def run_script(self, name: str, *args: str, expect: int = None) -> subprocess.CompletedProcess:
        result = subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                                capture_output=True, text=True)
        if expect is not None:
            self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def run_cli(self, *evidence: Path, extra: tuple = ()) -> subprocess.CompletedProcess:
        args = ["--root", str(self.root)]
        for path in evidence:
            args += ["--evidence", str(path)]
        return self.run_script("trace_check.py", *args, *extra)

    def rules(self, *evidence: Path) -> list[str]:
        result = self.run_cli(*evidence, extra=("--json",))
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return [item["rule"] for item in json.loads(result.stdout)["findings"]]

    def assertFinds(self, rule: str, *evidence: Path) -> None:
        found = self.rules(*evidence)
        self.assertIn(rule, found, f"expected a {rule} finding, got {found}")

    def assertDoesNotFind(self, rule: str, *evidence: Path) -> None:
        found = self.rules(*evidence)
        self.assertNotIn(rule, found, f"unexpected {rule} finding in {found}")


class IdFormTest(unittest.TestCase):
    """The carrier convention, which is the whole mechanism. Its edge cases are not incidental."""

    def test_a_qualified_id_in_a_method_name_is_read(self) -> None:
        self.assertEqual(trace_check.cites("resendsInWindow__F7_AC2"), [("7", "2")])

    def test_one_test_may_carry_several_ids(self) -> None:
        """`_AC4` chained after `F7_AC2` inherits the feature to its left, as the convention says."""
        self.assertEqual(trace_check.cites("resends__F7_AC2_AC4"), [("7", "2"), ("7", "4")])

    def test_the_prose_form_and_the_method_form_are_the_same_id(self) -> None:
        self.assertEqual(trace_check.cites("F-7/AC-2"), trace_check.cites("x__F7_AC2"))

    def test_a_suffix_letter_survives_and_leading_zeros_do_not(self) -> None:
        """`AC-8A` is a real form, and `F-007` in a spec is `F007` in a method name."""
        self.assertEqual(trace_check.cites("x__F007_AC08A"), [("7", "8A")])

    def test_a_bare_id_is_unqualified_rather_than_guessed_at(self) -> None:
        self.assertEqual(trace_check.cites("checks_AC-4"), [("", "4")])

    def test_an_id_glued_to_a_word_is_not_read(self) -> None:
        """The convention separates the id, and the boundary is what keeps `MacAC4` out of the set."""
        self.assertEqual(trace_check.cites("checksAC-4"), [])

    def test_a_plain_word_is_not_an_id(self) -> None:
        """`AcceptanceTest` and `FACT` must not become criteria; the corpus is full of both."""
        self.assertEqual(trace_check.cites("AcceptanceTestOfFACTS"), [])

    def test_a_plan_qualifies_a_bare_id_with_its_own_feature(self) -> None:
        self.assertEqual(trace_check.cites("| AC-4 | unit |", "7"), [("7", "4")])


class DiscoveryTest(TraceFixture):
    def test_a_repository_with_no_plans_says_so_and_exits_zero(self) -> None:
        """Silence would read as "traced clean" on a repository that never adopted the layout."""
        result = self.run_cli(self.evidence())
        self.assertEqual(result.returncode, 0)
        self.assertIn("no feature plan", result.stdout)

    def test_evidence_that_was_never_given_says_so_and_exits_zero(self) -> None:
        self.corpus()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertIn("no --evidence", result.stdout)

    def test_a_traced_corpus_produces_no_findings(self) -> None:
        self.corpus()
        result = self.run_cli(self.evidence())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2 testcase(s) read", result.stdout)

    def test_the_script_writes_nothing(self) -> None:
        """The whole design rests on this: a checker that emits artifacts defeats its own purpose."""
        self.corpus(rows="| AC-1 | unit | T1 | |")
        receipt = self.evidence()
        before = {path: path.stat().st_mtime_ns
                  for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(self.run_cli(receipt).returncode, 1)
        after = {path: path.stat().st_mtime_ns
                 for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(before, after)

    def test_a_missing_root_is_a_usage_error(self) -> None:
        result = self.run_script("trace_check.py", "--root", str(self.root / "nope"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a directory", result.stderr)

    def test_the_honest_limit_is_printed_with_the_counts(self) -> None:
        """Nothing in the output may imply the criterion is met, on any run that reports numbers."""
        self.corpus()
        self.assertIn("not that it asserts anything", self.run_cli(self.evidence()).stdout)


class RuleTest(TraceFixture):
    def test_t0_fires_on_an_approved_spec_with_no_criteria(self) -> None:
        """The measured failure: a criterion pattern that matches nothing makes every later check
        inert, and the run reports green over a feature nobody tested."""
        self.corpus(criteria="The system resends invites reliably.")
        self.assertFinds("T0", self.evidence())

    def test_t0_does_not_fire_on_a_draft_spec_with_no_criteria(self) -> None:
        """A draft is allowed to be empty; that is what draft means."""
        self.corpus(criteria="Still being written.", status="draft", rows="")
        self.assertDoesNotFind("T0", self.evidence([("com.x.ResendTest", "notYet")]))

    def test_t0_fires_on_a_coverage_row_whose_level_is_unreadable(self) -> None:
        self.corpus(rows="| AC-1 | unit | T1 | |\n| AC-2 | maybe | T1 | |")
        self.assertFinds("T0", self.evidence())

    def test_t0_fires_on_a_plan_that_names_no_feature(self) -> None:
        self.corpus()
        path = self.root / "docs" / "product" / "plans" / "F-7-resend.md"
        path.write_text(path.read_text(encoding="utf-8").replace("feature: F-7\n", "", 1),
                        encoding="utf-8")
        self.assertFinds("T0", self.evidence())

    def test_t1_fires_on_a_criterion_with_no_coverage_row(self) -> None:
        self.corpus(rows="| AC-1 | unit | T1 | |")
        self.assertFinds("T1", self.evidence())

    def test_t1_does_not_fire_when_every_criterion_has_a_row(self) -> None:
        self.corpus()
        self.assertDoesNotFind("T1", self.evidence())

    def test_t1_does_not_fire_on_a_draft_spec(self) -> None:
        """A draft binds nobody, so an uncovered criterion in one is not yet a gap."""
        self.corpus(status="draft", rows="| AC-1 | unit | T1 | |")
        self.assertDoesNotFind("T1", self.evidence())

    def test_t2_fires_on_a_row_naming_a_criterion_that_does_not_exist(self) -> None:
        self.corpus(rows=ROWS + "\n| AC-9 | unit | T3 | |")
        self.assertFinds("T2", self.evidence())

    def test_t2_fires_on_a_planned_test_covering_a_criterion_that_does_not_exist(self) -> None:
        """The ```test block is a second declaration site and drifts from the map the same way."""
        self.corpus(covers="AC-9")
        self.assertFinds("T2", self.evidence())

    def test_t2_does_not_fire_when_the_map_matches_the_spec(self) -> None:
        self.corpus()
        self.assertDoesNotFind("T2", self.evidence())

    def test_t3_fires_when_no_executed_test_carries_the_id(self) -> None:
        self.assertFinds("T3", self._corpus_missing_one_test())

    def test_t3_does_not_fire_when_the_test_ran(self) -> None:
        self.corpus()
        self.assertDoesNotFind("T3", self.evidence())

    def test_t3_does_not_fire_on_a_criterion_whose_level_is_none(self) -> None:
        """`none` is a declared absence, not a gap: the absence claim below carries the reason."""
        self.corpus(rows="| AC-1 | unit | T1 | |\n| AC-2 | none | — | |",
                    absent="- AC-2 — the mail provider is not exercised in CI.")
        self.assertDoesNotFind("T3", self.evidence([PASSING[0]]))

    def test_t4_fires_on_a_test_citing_an_id_no_spec_declares(self) -> None:
        self.corpus()
        self.assertFinds("T4", self.evidence(PASSING + [("com.x.ResendTest", "extra__F7_AC9")]))

    def test_t4_fires_on_an_unqualified_id_rather_than_guessing_the_feature(self) -> None:
        """Two features may both have an AC-4, so a bare id in a test name names neither."""
        self.corpus()
        self.assertFinds("T4", self.evidence(PASSING + [("com.x.ResendTest", "bare_AC-4")]))

    def test_t4_does_not_fire_on_a_qualified_id_the_spec_declares(self) -> None:
        self.corpus()
        self.assertDoesNotFind("T4", self.evidence())

    def test_t5_fires_when_the_map_and_the_absence_claim_disagree(self) -> None:
        self.corpus(absent="- AC-1 — the mail provider is not exercised in CI.")
        self.assertFinds("T5", self.evidence())

    def test_t5_does_not_fire_when_the_absence_claim_agrees_with_a_none_level(self) -> None:
        self.corpus(rows="| AC-1 | unit | T1 | |\n| AC-2 | none | — | |",
                    absent="- AC-2 — the mail provider is not exercised in CI.")
        self.assertDoesNotFind("T5", self.evidence([PASSING[0]]))

    def test_t6_fires_on_a_test_citing_a_retired_id(self) -> None:
        self.corpus(criteria=CRITERIA.splitlines()[0] + CRITERIA.splitlines()[1],
                    withdrawn="withdrawn: [2]\n", rows="| AC-1 | unit | T1 | |")
        self.assertFinds("T6", self.evidence())

    def test_t6_does_not_fire_when_no_test_cites_the_retired_id(self) -> None:
        self.corpus(criteria=CRITERIA.splitlines()[0] + CRITERIA.splitlines()[1],
                    withdrawn="withdrawn: [2]\n", rows="| AC-1 | unit | T1 | |")
        self.assertDoesNotFind("T6", self.evidence([PASSING[0]]))

    def _corpus_missing_one_test(self) -> Path:
        self.corpus()
        return self.evidence([PASSING[0]])


class AttributionTest(TraceFixture):
    """The measured failure mode: a parameterised case loses its method name in the XML."""

    def test_a_parameterised_case_is_attributed_by_its_class_name(self) -> None:
        """`name="[1] image/png"` carries no method name at all — 3.0% of a real corpus. Keying on
        `name=` alone would fire T3 on a criterion that IS tested, and the cheapest way to a green
        checker would be to stop writing table-driven tests. That is a bookkeeping rule dictating
        test design, which is the inversion this whole toolchain exists to prevent."""
        self.corpus()
        receipt = self.evidence([("com.x.ResendTest__F7_AC1", "[1] image/png"),
                                 ("com.x.ResendTest__F7_AC1", "[2] 2026-12-31, 26"),
                                 ("com.x.ResendTest", "refuses__F7_AC2")])
        result = self.run_cli(receipt, extra=("--json",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["testcases"], 3)
        self.assertEqual(payload["unattributable"], 0)
        self.assertIn("1 carried an id in the test name, 2 in the class name", payload["summary"])

    def test_a_testcase_carrying_no_id_anywhere_is_counted_and_reported(self) -> None:
        """An unattributable testcase is not a pass. The count is the finding."""
        self.corpus()
        receipt = self.evidence(PASSING + [("com.x.OtherTest", "somethingElse")])
        payload = json.loads(self.run_cli(receipt, extra=("--json",)).stdout)
        self.assertEqual(payload["unattributable"], 1)
        self.assertIn("1 in neither", payload["summary"])


class EvidenceBindingTest(TraceFixture):
    """grep proving a string exists is not evidence a test ran, and neither is a receipt whose
    result directory has moved on since it was issued."""

    def test_a_stale_result_from_an_earlier_tree_cannot_satisfy_the_gate(self) -> None:
        self.corpus()
        receipt = self.evidence()
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["started_at_unix_ns"] = time.time_ns()
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        result = self.run_cli(receipt)
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the window", result.stderr)

    def test_xml_written_after_the_gate_went_green_is_refused(self) -> None:
        """The receipt's boundary is a LOWER bound only, so a second narrower run fired after the
        gate satisfies it. The moment verification finished is the upper bound that closes it."""
        self.corpus()
        receipt = self.evidence()
        target = sorted(self.results.glob("*.xml"))[0]
        time.sleep(0.01)
        target.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        result = self.run_cli(receipt)
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the window", result.stderr)

    def test_an_added_result_file_is_refused(self) -> None:
        self.corpus()
        receipt = self.evidence()
        (self.results / "TEST-com.x.Late.xml").write_text(
            '<testsuite name="com.x.Late" tests="1" skipped="0" failures="0" errors="0">'
            '<testcase classname="com.x.Late" name="late__F7_AC2"/></testsuite>', encoding="utf-8")
        result = self.run_cli(receipt)
        self.assertEqual(result.returncode, 2)
        self.assertIn("result set changed", result.stderr)

    def test_a_receipt_that_is_not_one_is_a_usage_error(self) -> None:
        self.corpus()
        path = self.write(".work/nonsense.json", '{"hello": 1}')
        result = self.run_cli(path)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a verify_junit evidence receipt", result.stderr)

    def test_a_failing_testcase_does_not_enter_the_executed_set(self) -> None:
        """verify_junit refuses a red run outright; a re-read red case still proves nothing, so it
        leaves the set and T3 fires rather than the criterion counting as covered."""
        self.corpus()
        receipt = self.evidence()
        target = self.results / "TEST-com.x.ResendTest.xml"
        target.write_text(target.read_text(encoding="utf-8").replace(
            '"refuses__F7_AC2" time="0.01"/>',
            '"refuses__F7_AC2" time="0.01"><failure message="no"/></testcase>'), encoding="utf-8")
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["verified_at_utc"] = "2099-01-01T00:00:00Z"     # only the upper bound is relaxed
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        self.assertFinds("T3", receipt)


JAVA = """package com.x;

import org.junit.jupiter.api.Test;

class ResendTest {{

    @Test
    void {one}() {{
        assertTrue(mailer.sentTo("a@b.c"));
    }}

    @Test
    void {two}() {{
{body}    }}
}}
"""
PY = """import unittest


class ResendTest(unittest.TestCase):

    def {one}(self):
        self.assertTrue(mailer.sent)

    def {two}(self):
        self.assertTrue(limiter.blocked)
"""
KEPT = '        assertTrue(limiter.blocked());\n'


class NewlyCarriedIdTest(TraceFixture):
    """T7 — the id arrived and the body did not.

    T3 asks only whether a test carrying the id ran and passed, and renaming an already-green test
    answers that in full. This is not a hypothetical shortcut: across the four repositories this
    methodology runs on, 1,073 Java test files hold 5,866 `@Test` methods and NOT ONE of them
    carries a criterion id, so the migration T3 asks for is literally a bulk rename and the cheapest
    way to finish it is to change nothing else. Every test below is written in both directions,
    because a T7 that fires on honest work is a T7 somebody deletes.
    """

    SOURCE = "backend/src/test/java/com/x/ResendTest.java"
    PYSOURCE = "backend/tests/ResendTest.py"

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=False)

    def repo(self, *relative: str) -> None:
        self.git("init", "-q", ".")
        self.git("config", "user.email", "a@b.c")
        self.git("config", "user.name", "t")
        self.commit("base", *relative)

    def commit(self, subject: str, *relative: str) -> None:
        """Staged BY NAME, so the JUnit XML this fixture also writes never enters the history."""
        for item in relative:
            self.git("add", "--", item)
        self.git("commit", "-q", "-m", subject)

    def source(self, one: str, two: str, body: str = KEPT, template: str = JAVA,
               where: str = None) -> None:
        self.write(where or self.SOURCE, template.format(one=one, two=two, body=body))

    def t7(self, *evidence: Path, rev: str = "HEAD") -> list[str]:
        result = self.run_cli(*evidence, extra=("--json", "--commit", rev))
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_a_bulk_rename_that_adds_the_id_and_nothing_else_is_a_finding(self) -> None:
        """The whole reason T7 exists: `sed` over 5,866 method names makes T3 green for free."""
        self.corpus()
        self.source("sendsMail", "refuses")
        self.repo(self.SOURCE, "docs")
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.commit("chore: carry criterion ids", self.SOURCE)
        payload = self.t7(self.evidence())
        self.assertEqual(payload["exit"], 1, payload["summary"])
        self.assertEqual([item["rule"] for item in payload["findings"]], ["T7", "T7"])
        self.assertIn("the id arrived without the work", payload["findings"][0]["message"])

    def test_a_test_written_in_the_range_is_clean(self) -> None:
        """A criterion covered by real work must pass, or nobody keeps the check."""
        self.corpus()
        self.write("docs/product/prd.md", "# product\n")
        self.repo("docs")
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.commit("feat(F-7/T1): resend limits", self.SOURCE)
        payload = self.t7(self.evidence())
        self.assertEqual(payload["exit"], 0, payload["summary"])
        self.assertEqual(payload["t7"], {"green": 2, "arrived": 2, "worked": 2, "stale": 0})

    def test_an_id_that_predates_the_range_is_counted_rather_than_judged(self) -> None:
        """T7 has no opinion on work older than the range, and an opinion it does not have must
        not print as a pass — the count is how an inert T7 stays visible."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.repo(self.SOURCE, "docs")
        self.write("README.md", "unrelated\n")
        self.commit("docs: unrelated", "README.md")
        payload = self.t7(self.evidence())
        self.assertEqual(payload["exit"], 0)
        self.assertEqual(payload["t7"], {"green": 2, "arrived": 0, "worked": 0, "stale": 2})
        self.assertIn("2 carried the id before the range", payload["summary"])

    def test_a_body_emptied_in_the_range_counts_as_touched(self) -> None:
        """Measured: the ONE disagreement in 581 judgeable real methods was a commit that renamed a
        test and moved its assertions into a new one, so its body changed by subtraction. T7 claims
        the range touched the body, and a deletion touched it; it claims nothing about assertions."""
        self.corpus()
        self.source("sendsMail", "refuses", body=KEPT + "        assertTrue(clock.frozen());\n")
        self.repo(self.SOURCE, "docs")
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2", body=KEPT)
        self.commit("refactor(F-7/T1): move the clock assertion out", self.SOURCE)
        payload = self.t7(self.evidence())
        self.assertEqual([item["rule"] for item in payload["findings"]], ["T7"],
                         "only the untouched body may be reported: " + payload["summary"])

    def test_a_python_test_is_judged_by_the_same_rule(self) -> None:
        """T7 matches a name against changed line numbers and parses no language. The seat's own
        measurement said an assertion regex flags 4.30% of 32,141 Python test functions against
        0.55% of Java, so anything language-shaped here would be the same mistake twice."""
        self.corpus()
        self.source("test_sends", "test_refuses", template=PY, where=self.PYSOURCE)
        self.repo(self.PYSOURCE, "docs")
        self.source("test_sends__F7_AC1", "test_refuses__F7_AC2", template=PY,
                    where=self.PYSOURCE)
        self.commit("chore: carry criterion ids", self.PYSOURCE)
        payload = self.t7(self.evidence([("tests.ResendTest", "test_sends__F7_AC1"),
                                         ("tests.ResendTest", "test_refuses__F7_AC2")]))
        self.assertEqual([item["rule"] for item in payload["findings"]], ["T7", "T7"],
                         payload["summary"])

    def test_a_name_a_registry_already_mentioned_is_not_a_new_id(self) -> None:
        """Measured false positive, and the reason "arrived" is decided against the left side of the
        range rather than against the added lines: one real project keeps a pinned-defect registry
        that names its own test methods in string literals, so editing that registry made every
        long-standing test look newly named — 18 of 494 judgeable methods, 3.6%."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.repo(self.SOURCE, "docs")
        self.write(self.SOURCE, (self.root / self.SOURCE).read_text(encoding="utf-8").replace(
            "class ResendTest {", 'class ResendTest {\n\n    // pinnedBy "refuses__F7_AC2"\n'))
        self.commit("chore(F-7/T1): pin the defect", self.SOURCE)
        payload = self.t7(self.evidence())
        self.assertEqual(payload["exit"], 0, payload["summary"])
        self.assertEqual(payload["t7"]["stale"], 2)

    def test_a_same_named_method_in_another_file_cannot_answer_for_this_one(self) -> None:
        """`classRegistryIsComplete` exists in several suites of one real project, and a global
        token search let an unrelated file's added body satisfy the claim."""
        self.corpus()
        self.source("sendsMail", "refuses")
        self.repo(self.SOURCE, "docs")
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2",
                    body=KEPT + "        assertTrue(other.thing());\n",
                    where="backend/src/test/java/com/x/OtherTest.java")
        self.commit("chore: carry criterion ids", self.SOURCE,
                    "backend/src/test/java/com/x/OtherTest.java")
        payload = self.t7(self.evidence())
        self.assertEqual([item["rule"] for item in payload["findings"]], ["T7", "T7"],
                         payload["summary"])

    def test_a_range_spelled_with_two_dots_reads_the_same_work(self) -> None:
        self.corpus()
        self.source("sendsMail", "refuses")
        self.repo(self.SOURCE, "docs")
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.commit("chore: carry criterion ids", self.SOURCE)
        self.assertEqual([item["rule"] for item in self.t7(self.evidence(),
                                                           rev="HEAD~1..HEAD")["findings"]],
                         ["T7", "T7"])

    def test_a_root_commit_is_read_against_the_empty_tree_not_the_working_tree(self) -> None:
        """`git diff <root>` compares a root commit to the WORKING TREE, which would let an
        uncommitted edit answer for a committed claim. That default is not inherited."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.repo(self.SOURCE, "docs")
        payload = self.t7(self.evidence())
        self.assertEqual(payload["exit"], 0)
        self.assertEqual(payload["t7"]["worked"], 2)

    def test_a_revision_git_cannot_resolve_is_a_usage_error(self) -> None:
        """Silently reading an unresolvable range as "no diff" would report every claim as
        pre-existing and find nothing, which is the shape of every inert check in this toolchain."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.repo(self.SOURCE, "docs")
        result = self.run_cli(self.evidence(), extra=("--commit", "no-such-rev"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot resolve", result.stderr)

    def test_the_flag_is_never_accepted_in_silence(self) -> None:
        """A `--commit` accepted and never acted on is how the last check here became inert."""
        self.corpus()
        result = self.run_script("trace_check.py", "--root", str(self.root), "--commit", "HEAD")
        self.assertEqual(result.returncode, 0)
        self.assertIn("T7 did not run", result.stdout)

    def test_the_honest_limit_names_what_t7_does_not_prove(self) -> None:
        """T7 proves the body changed. It does not prove the body asserts anything, and the run
        that reports it must say so on the same line as the number."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.repo(self.SOURCE, "docs")
        result = self.run_cli(self.evidence(), extra=("--commit", "HEAD"))
        self.assertIn("A changed body is work, not an assertion.", result.stdout)
        self.assertIn("not that it asserts anything", result.stdout)

    def test_t7_is_silent_without_the_flag(self) -> None:
        """The pre-push gate has no range; T7 is an extra question, not a new default."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses__F7_AC2")
        self.repo(self.SOURCE, "docs")
        result = self.run_cli(self.evidence(), extra=("--json",))
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["t7"])
        self.assertEqual(payload["exit"], 0)

    def test_a_criterion_t3_already_reports_is_not_reported_twice(self) -> None:
        """T7 judges what T3 calls green. A criterion with no executed test is T3's finding alone."""
        self.corpus()
        self.source("sendsMail__F7_AC1", "refuses")
        self.repo(self.SOURCE, "docs")
        payload = self.t7(self.evidence([("com.x.ResendTest", "sendsMail__F7_AC1")]))
        self.assertEqual([item["rule"] for item in payload["findings"]], ["T3"])
        self.assertEqual(payload["t7"]["green"], 1)


class BodySpanTest(unittest.TestCase):
    """The span rule, which is the only thing here that could be called parsing — and is not."""

    def test_a_java_body_ends_on_the_brace_at_the_signature_indent(self) -> None:
        lines = ["class A {", "    void t() {", "        one();", "    }", "}"]
        self.assertEqual(list(trace_check.body_span(lines, 1)), [3])

    def test_a_python_body_ends_on_the_next_definition(self) -> None:
        lines = ["class A:", "    def t(self):", "        one()", "", "    def u(self):"]
        self.assertEqual(list(trace_check.body_span(lines, 1)), [3, 4])

    def test_an_empty_body_spans_nothing(self) -> None:
        """`void ac2() {}` is the case this file has always named. T7 sees no body to change."""
        self.assertEqual(list(trace_check.body_span(["    void t() {}", "    void u() {}"], 0)), [])

    def test_a_call_site_is_not_a_declaration_because_it_opens_nothing(self) -> None:
        lines = ["    void other() {", "        t();", "        more();", "    }"]
        self.assertEqual(list(trace_check.body_span(lines, 1)), [])


class CarrierTest(unittest.TestCase):
    """Which identifier T7 goes looking for. The wild answers are not all identifiers."""

    def test_the_method_name_carries_when_it_holds_the_id(self) -> None:
        self.assertEqual(trace_check.carrier(trace_check.Key("7", "2"),
                                             "com.x.ResendTest#refuses__F7_AC2"),
                         "refuses__F7_AC2")

    def test_a_parameterised_case_falls_back_to_its_class(self) -> None:
        """3.0% of 267,943 real testcases render `name="[2] ..."` and the method name is gone."""
        self.assertEqual(trace_check.carrier(trace_check.Key("7", "2"),
                                             "com.x.Resend__F7_AC2#[2] 2026-12-31"),
                         "Resend__F7_AC2")

    def test_a_display_name_that_is_not_an_identifier_is_refused(self) -> None:
        """`@DisplayName("F-7/AC-2 rejects a blank")` names no token any diff contains."""
        self.assertIsNone(trace_check.carrier(trace_check.Key("7", "2"),
                                              "com.x.Other#F-7/AC-2 rejects a blank"))

    def test_a_class_stem_decides_which_file_owns_the_test(self) -> None:
        self.assertTrue(trace_check.owns("a/b/ResendTest.java", "com.x.ResendTest"))
        self.assertTrue(trace_check.owns("a/tests/gate.py", "tests.gate.Cases"))
        self.assertFalse(trace_check.owns("a/b/OtherTest.java", "com.x.ResendTest"))
        self.assertFalse(trace_check.owns("com/x/Helper.java", "com.x.ResendTest"))


if __name__ == "__main__":
    unittest.main()
