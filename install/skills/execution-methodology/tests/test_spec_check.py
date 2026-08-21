#!/usr/bin/env python3
"""Tests for spec_check.py — the current-state lint for product-definition documents.

Run: python3 -m unittest tests.test_spec_check   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

Every check is exercised in BOTH directions: a corpus that must produce the finding and a corpus
that must not. A one-sided test on a linter is worth very little — a check that fires on everything
passes the failure half and is useless, and the false-positive half is where a lint actually dies.
A3 gets a dedicated pass-side test over domain vocabulary for exactly that reason.

The fixtures are written into throwaway directories that are NOT git repositories, so the A4
commit-date check skips itself everywhere except in the two tests that build a real repository. It
is the same reason the script skips it in CI: the answer does not exist without git.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "spec_check.py"

sys.path.insert(0, str(SCRIPTS))

import spec_check  # noqa: E402  — the path insertion above has to happen first


PRD = """---
title: Ledger
status: draft
updated: 2026-01-01
---

# Ledger

<!-- features: docs/product/specs/F-*.md -->

F-007 covers the export.
"""

SPEC_HEAD = """---
id: F-007
title: Export
prd: docs/product/prd.md
status: draft
updated: 2026-01-01
---

# F-007 — Export
"""

CRITERIA = """
## Acceptance criteria

**AC-1** When an operator requests an export, given the ledger has entries, the response is a CSV
file naming every entry.
**AC-2** When an operator requests an export, given the ledger is empty, the response is a CSV file
with a header row and no data rows.
"""


class SpecCheckFixture(unittest.TestCase):
    """A corpus builder plus the two ways the script is driven: the CLI and a direct call."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "product" / "specs").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def corpus(self, spec_body: str = CRITERIA, prd: str = PRD, front: str = SPEC_HEAD) -> None:
        self.write("docs/product/prd.md", prd)
        self.write("docs/product/specs/F-007-export.md", front + spec_body)

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *extra],
                              capture_output=True, text=True)

    def rules(self) -> list[str]:
        return [item.rule for item in spec_check.run(self.root.resolve())]

    def assertClean(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def assertFinds(self, rule: str) -> None:
        found = self.rules()
        self.assertIn(rule, found, f"expected a {rule} finding, got {found}")

    def assertDoesNotFind(self, rule: str) -> None:
        found = self.rules()
        self.assertNotIn(rule, found, f"unexpected {rule} finding in {found}")


class DiscoveryTest(SpecCheckFixture):
    def test_repository_without_product_documents_is_silent(self) -> None:
        """Most repositories have not adopted this layout. A linter that shouts at them is removed."""
        (self.root / "docs" / "product" / "specs").rmdir()
        (self.root / "docs" / "product").rmdir()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_well_formed_corpus_produces_nothing(self) -> None:
        self.corpus()
        self.assertClean()

    def test_the_script_writes_nothing(self) -> None:
        """The whole design rests on this: a checker that emits artifacts defeats its own purpose."""
        self.corpus(spec_body="\n**AC-1** malformed\n")
        before = {path: path.stat().st_mtime_ns
                  for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(self.run_cli().returncode, 1)
        after = {path: path.stat().st_mtime_ns
                 for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(before, after)

    def test_a_missing_root_is_a_usage_error(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root / "nope")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a directory", result.stderr)


class CurrentStateTest(SpecCheckFixture):
    def test_a1_flags_a_dated_heading_and_accepts_an_undated_one(self) -> None:
        self.corpus(spec_body="\n## Scope 2026-02-01\n" + CRITERIA)
        self.assertFinds("A1")
        self.corpus(spec_body="\n## Scope\n" + CRITERIA)
        self.assertDoesNotFind("A1")

    def test_a1_ignores_a_dated_heading_inside_a_fenced_block(self) -> None:
        """A template showing its own shape is not a document being appended to."""
        self.corpus(spec_body="\n```markdown\n## Release 2026-02-01\n```\n" + CRITERIA)
        self.assertDoesNotFind("A1")

    def test_a2_flags_a_history_section_and_accepts_a_scope_section(self) -> None:
        for heading in ("## Changelog", "## History", "### Revision log", "## What changed"):
            with self.subTest(heading=heading):
                self.corpus(spec_body=f"\n{heading}\n\nsomething\n" + CRITERIA)
                self.assertFinds("A2")
        self.corpus(spec_body="\n## Scope\n\nsomething\n" + CRITERIA)
        self.assertDoesNotFind("A2")

    def test_a3_flags_prose_about_the_document_itself(self) -> None:
        for sentence in (
                "An earlier version of this section allowed partial exports.",
                "This spec previously required a signature.",
                "The limit previously said 20 rows.",
                "Earlier drafts named the actor an auditor.",
                "The row order was previously wrong."):
            with self.subTest(sentence=sentence):
                self.corpus(spec_body=f"\n{sentence}\n" + CRITERIA)
                self.assertFinds("A3")

    def test_a3_does_not_fire_on_domain_vocabulary(self) -> None:
        """THE REASON THE PATTERN IS NARROW, pinned as a test rather than left in a comment.

        A broad history-word pattern hit 1057 lines across 164 files of a real corpus, nearly all
        of them sentences like these: the product supersedes a campaign, corrects a snapshot,
        deprecates an endpoint. Widening the pattern until one of these fires is widening it until
        the check is switched off.
        """
        for sentence in (
                "A superseded campaign keeps its identifier and stops accruing spend.",
                "A corrected snapshot replaces the previous value in the ledger.",
                "The deprecated endpoint is no longer offered to new tenants.",
                "Formerly active accounts are archived after ninety days.",
                "The revised total is shown beside the original.",
                "Historical rates are retained for audit."):
            with self.subTest(sentence=sentence):
                self.corpus(spec_body=f"\n{sentence}\n" + CRITERIA)
                self.assertDoesNotFind("A3")


class CommitDateTest(SpecCheckFixture):
    """A4 needs a real repository; everything about it is about NOT producing noise."""

    def git(self, *args: str) -> None:
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-03-04T10:00:00",
                   GIT_COMMITTER_DATE="2026-03-04T10:00:00")
        subprocess.run(["git", "-C", str(self.root), *args], check=True, env=env,
                       capture_output=True, text=True)

    def make_repo(self) -> None:
        self.git("init", "-q")
        self.git("config", "user.email", "tester@example.invalid")
        self.git("config", "user.name", "Tester")

    def test_a4_agrees_with_the_commit_date_and_flags_a_stale_one(self) -> None:
        self.make_repo()
        self.corpus(front=SPEC_HEAD.replace("updated: 2026-01-01", "updated: 2026-03-04"))
        self.git("add", "-A")
        self.git("commit", "-qm", "add product definition")
        self.assertNotIn("A4", [item.rule for item in spec_check.run(self.root.resolve())
                                if item.path.endswith("F-007-export.md")])
        self.write("docs/product/specs/F-007-export.md",
                   SPEC_HEAD.replace("updated: 2026-01-01", "updated: 2019-01-01") + CRITERIA)
        self.git("add", "-A")
        self.git("commit", "-qm", "restate the export rule")
        self.assertFinds("A4")

    def test_a4_skips_an_untracked_file_and_a_tree_without_git(self) -> None:
        self.make_repo()
        self.corpus(front=SPEC_HEAD.replace("updated: 2026-01-01", "updated: 2019-01-01"))
        self.assertDoesNotFind("A4")   # untracked: there is no commit date to disagree with
        self._tmp.cleanup()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.corpus(front=SPEC_HEAD.replace("updated: 2026-01-01", "updated: 2019-01-01"))
        self.assertDoesNotFind("A4")   # no repository at all

    def test_a4_flags_an_updated_value_that_is_not_a_date(self) -> None:
        self.corpus(front=SPEC_HEAD.replace("updated: 2026-01-01", "updated: last tuesday"))
        self.assertFinds("A4")


class FrontMatterParserTest(unittest.TestCase):
    """The ~40-line YAML subset, tested directly. It is the one place a silent drop would hide."""

    def parse(self, text: str) -> dict[str, object]:
        data, _, _ = spec_check.parse_front_matter(text.splitlines())
        return data

    def test_it_reads_scalars_quotes_lists_comments_and_blank_lines(self) -> None:
        data = self.parse('---\n# a comment\nid: F-007\ntitle: "Export, with a comma"\n\n'
                          "status: 'draft'\nwithdrawn: [3, 9]\ndepends: []\n---\nbody\n")
        self.assertEqual(data, {"id": "F-007", "title": "Export, with a comma", "status": "draft",
                                "withdrawn": ["3", "9"], "depends": []})

    def test_it_records_the_line_each_key_sat_on(self) -> None:
        _, where, end = spec_check.parse_front_matter(
            "---\nid: F-007\nstatus: draft\n---\n".splitlines())
        self.assertEqual((where["id"], where["status"], end), (2, 3, 3))

    def test_it_refuses_shapes_it_cannot_read_rather_than_dropping_them(self) -> None:
        for text, fragment in (
                ("no front matter here\n", "no `---` front matter"),
                ("---\nid: F-007\n", "never closed"),
                ("---\nid: F-007\nid: F-008\n---\n", "duplicate"),
                ("---\n  - a block list item\n---\n", "not a `key: value`"),
                ("---\nnested:\n  key: value\n---\n", "not a `key: value`")):
            with self.subTest(text=text):
                with self.assertRaises(spec_check.SpecError) as caught:
                    self.parse(text)
                self.assertIn(fragment, str(caught.exception))


class SpecStructureTest(SpecCheckFixture):
    def test_b1_reports_unparseable_front_matter_and_accepts_a_good_block(self) -> None:
        self.corpus(front="---\nid: F-007\ntitle: Export\n")
        self.assertFinds("B1")
        self.corpus()
        self.assertDoesNotFind("B1")

    def test_b2_requires_five_keys_and_rejects_an_unknown_one(self) -> None:
        self.corpus(front=SPEC_HEAD.replace("status: draft\n", ""))
        self.assertFinds("B2")
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nowner: someone"))
        self.assertFinds("B2")
        self.corpus(front=SPEC_HEAD.replace(
            "status: draft",
            "status: draft\ndepends: [F-1]\nwithdrawn: [4]\ndecisions: [docs/decisions/d1.md]\n"
            "edge_cases: [empty, concurrent]"))
        self.assertDoesNotFind("B2")

    def test_b3_binds_the_id_to_the_filename(self) -> None:
        self.corpus(front=SPEC_HEAD.replace("id: F-007", "id: F-008"))
        self.assertFinds("B3")
        self.corpus()
        self.assertDoesNotFind("B3")

    def test_b3_rejects_a_duplicated_id_across_the_corpus(self) -> None:
        self.corpus()
        self.write("docs/product/specs/F-007-second.md", SPEC_HEAD + CRITERIA)
        self.assertFinds("B3")

    def test_b4_closes_the_status_enum(self) -> None:
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: in-progress"))
        self.assertFinds("B4")
        for status in ("draft", "approved", "building", "shipped", "dropped"):
            with self.subTest(status=status):
                self.corpus(front=SPEC_HEAD.replace("status: draft", f"status: {status}"))
                self.assertDoesNotFind("B4")

    def test_b5_will_not_let_a_withdrawn_number_stay_live(self) -> None:
        """The ledger is what lets the body hold only current state while ids stay append-only."""
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nwithdrawn: [2]"))
        self.assertFinds("B5")
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nwithdrawn: [3, 4]"))
        self.assertDoesNotFind("B5")

    def test_b5_rejects_a_ledger_entry_that_is_not_a_criterion_number(self) -> None:
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nwithdrawn: [AC-3]"))
        self.assertFinds("B5")


class CriteriaTest(SpecCheckFixture):
    def test_c1_lints_the_shape_and_passes_a_conforming_criterion(self) -> None:
        self.corpus(spec_body="\n**AC-1** The export should work end to end.\n")
        self.assertFinds("C1")
        self.corpus()
        self.assertDoesNotFind("C1")

    def test_c2_flags_two_live_criteria_over_one_situation(self) -> None:
        """One situation with two outcomes is how a spec begins contradicting itself."""
        self.corpus(spec_body=CRITERIA + (
            "\n**AC-3** When an operator requests an export, given the ledger has entries,\n"
            "the response is a JSON document.\n"))
        self.assertFinds("C2")
        self.corpus()
        self.assertDoesNotFind("C2")

    def test_c2_normalises_whitespace_and_case_before_comparing(self) -> None:
        self.corpus(spec_body=CRITERIA + (
            "\n**AC-3** When AN OPERATOR   requests an export, given the LEDGER has entries,\n"
            "the response is a JSON document.\n"))
        self.assertFinds("C2")

    def test_c3_requires_unique_positive_numbers(self) -> None:
        self.corpus(spec_body=CRITERIA.replace("**AC-2**", "**AC-1**"))
        self.assertFinds("C3")
        self.corpus(spec_body=CRITERIA.replace("**AC-1**", "**AC-0**"))
        self.assertFinds("C3")
        self.corpus()
        self.assertDoesNotFind("C3")

    def test_c4_flags_a_result_no_input_can_falsify(self) -> None:
        for word in ("gracefully", "appropriately", "correctly", "properly", "as needed",
                     "if necessary", "reasonable"):
            with self.subTest(word=word):
                self.corpus(spec_body="\n**AC-1** When an operator requests an export, given the "
                                      f"ledger is empty, the system behaves {word}.\n")
                self.assertFinds("C4")
        self.corpus()
        self.assertDoesNotFind("C4")


class PrdTest(SpecCheckFixture):
    def test_d1_requires_the_prd_front_matter(self) -> None:
        self.corpus(prd=PRD.replace("status: draft\n", ""))
        self.assertFinds("D1")
        self.corpus(prd=PRD.replace("status: draft", "status: draft\nreach: 400 operators"))
        self.assertDoesNotFind("D1")

    def test_d2_permits_one_feature_index_marker_and_no_more(self) -> None:
        marker = "<!-- features: docs/product/specs/F-*.md -->"
        self.corpus(prd=PRD + "\n" + marker + "\n")
        self.assertFinds("D2")
        self.corpus()
        self.assertDoesNotFind("D2")

    def test_d3_reports_a_dangling_reference_in_either_direction(self) -> None:
        self.corpus(prd=PRD.replace("F-007 covers", "F-404 covers"))
        self.assertFinds("D3")
        self.corpus(front=SPEC_HEAD.replace("prd: docs/product/prd.md", "prd: docs/nowhere.md"))
        self.assertFinds("D3")
        self.corpus()
        self.assertDoesNotFind("D3")

    def test_d4_lets_a_draft_hold_open_questions_but_not_an_approved_document(self) -> None:
        question = "\n[NEEDS CLARIFICATION: does an export include voided entries?]\n"
        self.corpus(prd=PRD + question)
        self.assertDoesNotFind("D4")
        self.corpus(prd=PRD.replace("status: draft", "status: approved") + question)
        self.assertFinds("D4")


class OutputTest(SpecCheckFixture):
    def test_a_finding_line_names_the_path_the_line_and_the_rule(self) -> None:
        self.corpus(spec_body="\n## Changelog\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        first = result.stdout.splitlines()[0]
        self.assertTrue(first.startswith("docs/product/specs/F-007-export.md:11"), first)
        self.assertIn("A2", first)

    def test_output_is_capped_and_the_remainder_is_counted(self) -> None:
        body = "\n".join(f"## Section {n} 2026-01-0{n % 10}" for n in range(60))
        self.corpus(spec_body="\n" + body + "\n")
        result = self.run_cli()
        printed = result.stdout.splitlines()
        self.assertEqual(len(printed), spec_check.PRINT_CAP + 1)
        self.assertIn("and 20 more finding(s)", printed[-1])

    def test_json_lists_every_finding_with_the_exit_code(self) -> None:
        self.corpus(spec_body="\n## Changelog\n")
        result = self.run_cli("--json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["exit"], 1)
        self.assertEqual(payload["count"], len(payload["findings"]))
        self.assertEqual(payload["findings"][0]["rule"], "A2")

    def test_warn_only_prints_the_findings_and_exits_zero(self) -> None:
        self.corpus(spec_body="\n## Changelog\n")
        result = self.run_cli("--warn-only")
        self.assertEqual(result.returncode, 0)
        self.assertIn("A2", result.stdout)


if __name__ == "__main__":
    unittest.main()
