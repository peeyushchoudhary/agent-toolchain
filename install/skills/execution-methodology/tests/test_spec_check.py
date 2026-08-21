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
import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "spec_check.py"

sys.path.insert(0, str(SCRIPTS))

import ratio_meter  # noqa: E402  — the path insertion above has to happen first
import spec_check  # noqa: E402


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

    def test_b2_accepts_an_optional_milestone_key(self) -> None:
        """The key is optional and its ABSENCE carries meaning: the feature is specified and
        waiting, which is the normal state of most of a backlog. Requiring it would turn the
        backlog into findings and teach the reader to fill in whichever milestone is nearest."""
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nmilestone: M2"))
        self.assertDoesNotFind("B2")
        self.corpus()
        self.assertDoesNotFind("B2")

    def test_b3_rejects_a_milestone_that_is_not_an_id(self) -> None:
        """Features are collected by an exact match on this value, so a near miss is not a loud
        failure — it is a feature quietly missing from the schedule that claims to hold it."""
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nmilestone: Q2"))
        self.assertFinds("B3")
        self.corpus(front=SPEC_HEAD.replace("status: draft", "status: draft\nmilestone: M12"))
        self.assertDoesNotFind("B3")

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



# --- F: the persona binding ----------------------------------------------------------------------

HORIZONTALS = """
## Horizontals

| Concern | Disposition |
|---|---|
| Tenancy / isolation | Every read is scoped to the requesting tenant by the database. |
| Money handling | Export totals are recomputed from the ledger, never carried. |
| Accessibility | N/A -- this feature exposes no screen. |
"""

VALIDATOR = """---
name: {name}
description: Use when a change touches this domain.
writes: no
claude.model: opus
codex.sandbox: read-only
{covers}---

You validate one invariant.
"""


class PersonaBindingFixture(SpecCheckFixture):
    """Rule F needs two corpora at once: the product documents and this REPOSITORY's persona pool."""

    def persona(self, name: str, covers: str = "") -> None:
        self.write(f"docs/agents/personas/{name}.md",
                   VALIDATOR.format(name=name, covers=f"covers: {covers}\n" if covers else ""))

    def binding(self) -> spec_check.Binding:
        return spec_check.analyse(self.root.resolve())[1]


class PersonaPoolTest(PersonaBindingFixture):
    def test_a_repository_with_no_pool_says_nothing_at_all(self) -> None:
        """Most repositories have no personas. Rule F prints nothing there, findings or none."""
        self.corpus(CRITERIA + HORIZONTALS)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_the_pool_is_read_from_the_repository_not_from_the_home_directory(self) -> None:
        """A checker whose verdict depends on the laptop it runs on is not a checker.

        The base pool lives in a machine-global agents directory. If any part of rule F reached it,
        this fixture -- which has exactly one persona on disk -- would report thirteen or more.
        """
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator", "[tenancy]")
        binding = self.binding()
        self.assertEqual([p.name for p in binding.personas], ["tenancy-validator"])
        self.assertEqual(binding.pool_dir, "docs/agents/personas")

    def test_a_persona_overlay_with_no_front_matter_is_a_finding_not_a_silence(self) -> None:
        """A pool the rule half-read is how it goes inert without saying so."""
        self.corpus(CRITERIA + HORIZONTALS)
        self.write("docs/agents/personas/broken.md", "no front matter here\n")
        self.assertFinds("F1")


class BindingInertnessTest(PersonaBindingFixture):
    """The whole reason rule F exists in this shape. Seven checkers in this toolchain passed their
    own tests and matched nothing real; the guard against being the eighth is that a run which
    checked nothing has to SAY so, on stdout, next to its exit code."""

    def test_personas_with_no_covers_report_that_nothing_was_checked(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator")
        self.persona("money-validator")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RULE F CHECKED NOTHING", result.stdout)
        self.assertIn("0 with `covers:`", result.stdout)

    def test_a_corpus_with_no_concern_rows_reports_that_nothing_was_checked(self) -> None:
        """A `## Horizontals` written as prose yields no row. That is not a pass."""
        self.corpus(CRITERIA + "\n## Horizontals\n\nAuthorization and audit move; nothing else.\n")
        self.persona("tenancy-validator", "[tenancy]")
        result = self.run_cli()
        self.assertIn("RULE F CHECKED NOTHING", result.stdout)
        self.assertIn("prose", result.stdout)
        self.assertEqual(self.binding().unreadable, 1)

    def test_a_covers_that_matches_no_concern_in_the_corpus_is_a_finding(self) -> None:
        """F4, and it fires at the PERSONA because that is where the fix is. From the document side
        a binding that cannot match is invisible: the document simply never gets a demand."""
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("drift-validator", "[model drift]")
        self.assertFinds("F4")

    def test_a_covers_that_does_match_is_not_a_finding(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator", "[tenancy]")
        self.assertDoesNotFind("F4")

    def test_the_note_is_printed_even_when_there_are_no_findings(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS,
                    front=SPEC_HEAD.replace("status: draft",
                                            "status: draft\nreviewed_by: [tenancy-validator]"))
        self.persona("tenancy-validator", "[tenancy]")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("persona binding:", result.stdout)
        self.assertNotIn("CHECKED NOTHING", result.stdout)

    def test_the_json_payload_states_whether_anything_was_checked(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator")
        payload = json.loads(self.run_cli("--json").stdout)
        self.assertTrue(payload["binding"]["checked_nothing"])
        self.assertEqual(payload["binding"]["bound"], 0)


class BindingDemandTest(PersonaBindingFixture):
    def test_an_owned_live_concern_demands_the_validator(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator", "[tenancy]")
        self.assertFinds("F3")

    def test_naming_the_validator_satisfies_the_demand(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS,
                    front=SPEC_HEAD.replace("status: draft",
                                            "status: draft\nreviewed_by: [tenancy-validator]"))
        self.persona("tenancy-validator", "[tenancy]")
        self.assertDoesNotFind("F3")

    def test_a_concern_declared_inapplicable_demands_nobody(self) -> None:
        """`N/A -- this feature exposes no screen.` is the spec answering the question. Measured:
        every one of the 45 real exemptions in an 805-row corpus is a prefix like that one."""
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("a11y-validator", "[accessibility]")
        self.assertDoesNotFind("F3")

    def test_a_mid_sentence_mention_of_not_applicable_does_not_buy_silence(self) -> None:
        """The declaration has to open the cell, where a reader sees it too."""
        self.corpus(CRITERIA + """
## Horizontals

| Concern | Disposition |
|---|---|
| Money handling | Totals are recomputed; the rounding rule is not applicable here. |
""")
        self.persona("money-validator", "[money]")
        self.assertFinds("F3")

    def test_a_persona_without_covers_is_never_demanded(self) -> None:
        """The 13 base personas own no domain and must stay free of new authoring."""
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("reviewer")
        self.persona("tenancy-validator", "[tenancy]")
        findings = [f for f in spec_check.run(self.root.resolve()) if f.rule == "F3"]
        self.assertEqual(len(findings), 1)
        self.assertIn("tenancy-validator", findings[0].message)

    def test_one_finding_per_document_and_persona_not_one_per_row(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("both-validator", "[tenancy, money]")
        findings = [f for f in spec_check.run(self.root.resolve()) if f.rule == "F3"]
        self.assertEqual(len(findings), 1)

    def test_a_document_with_no_front_matter_is_still_bound(self) -> None:
        """MEASURED AND DECISIVE: zero of the 23 feature specs across four real repositories carry a
        `---` block. Gating rule F on parsed front matter -- as every other schema rule here does --
        would have made it inert on the entire real corpus while passing every fixture above."""
        self.write("docs/product/prd.md", PRD)
        self.write("docs/product/specs/F-007-export.md",
                   "# F-007 -- Export\n" + CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator", "[tenancy]")
        self.assertFinds("F3")
        self.assertEqual(self.binding().no_front_matter, 1)

    def test_the_bullet_form_of_the_section_is_read(self) -> None:
        self.corpus(CRITERIA + """
## Horizontals

- **Tenancy / isolation:** every read is scoped by the database.
- **Accessibility:** N/A -- no screen.
""")
        self.persona("tenancy-validator", "[tenancy]")
        self.assertFinds("F3")
        self.assertEqual(self.binding().live_rows, 1)

    def test_the_milestone_and_the_prd_are_bound_by_the_same_carrier(self) -> None:
        self.corpus()
        self.write("docs/product/milestones/M1-first.md",
                   "---\nmilestone: M1\n---\n\n# M1\n" + HORIZONTALS)
        self.persona("tenancy-validator", "[tenancy]")
        paths = {f.path for f in spec_check.run(self.root.resolve()) if f.rule == "F3"}
        self.assertEqual(paths, {"docs/product/milestones/M1-first.md"})


class ReviewedByShapeTest(PersonaBindingFixture):
    def test_reviewed_by_is_an_accepted_key_on_a_spec_and_on_the_prd(self) -> None:
        self.corpus(CRITERIA,
                    prd=PRD.replace("status: draft", "status: draft\nreviewed_by: [reviewer]"),
                    front=SPEC_HEAD.replace("status: draft",
                                            "status: draft\nreviewed_by: [reviewer]"))
        self.assertClean()

    def test_a_malformed_entry_is_a_finding(self) -> None:
        self.corpus(CRITERIA, front=SPEC_HEAD.replace(
            "status: draft", "status: draft\nreviewed_by: [Tenancy Validator]"))
        self.assertFinds("F2")

    def test_a_repeated_entry_is_a_finding(self) -> None:
        self.corpus(CRITERIA, front=SPEC_HEAD.replace(
            "status: draft", "status: draft\nreviewed_by: [reviewer, reviewer]"))
        self.assertFinds("F2")

    def test_an_empty_list_is_a_finding(self) -> None:
        self.corpus(CRITERIA, front=SPEC_HEAD.replace(
            "status: draft", "status: draft\nreviewed_by: []"))
        self.assertFinds("F2")

    def test_no_closed_roster_a_project_may_name_its_own_validator(self) -> None:
        """`VALID_PERSONAS` in validate_card.py is ("developer", "senior-developer") and real cards
        already declare test-judge, docs-steward and chief-of-staff, so they fail today for naming
        personas that exist. A hardcoded roster here would repeat that AND stop a project naming its
        own validator, which is the entire point of the rule."""
        self.corpus(CRITERIA, front=SPEC_HEAD.replace(
            "status: draft", "status: draft\nreviewed_by: [tenancy-rls-validator, chief-of-staff]"))
        self.assertDoesNotFind("F2")


class ConcernMatchTest(unittest.TestCase):
    """Token-set containment, never substring. Three rules in this toolchain have already flagged
    real product by matching a WORD where they meant a STRUCTURE."""

    def test_a_short_declaration_reaches_a_longer_label(self) -> None:
        self.assertTrue(spec_check.concern_match("tenancy", "Tenancy / isolation"))
        self.assertTrue(spec_check.concern_match("audit", "Audit trail"))

    def test_a_longer_declaration_reaches_a_shorter_label(self) -> None:
        self.assertTrue(spec_check.concern_match("money handling", "Money"))
        self.assertTrue(spec_check.concern_match("personal data", "Isolation and personal data"))

    def test_a_substring_is_not_a_match(self) -> None:
        self.assertFalse(spec_check.concern_match("cost", "Costume design"))
        self.assertFalse(spec_check.concern_match("audit", "Auditorium booking"))

    def test_an_unrelated_pair_is_not_a_match(self) -> None:
        self.assertFalse(spec_check.concern_match("tenancy", "Isolation and personal data"))
        self.assertFalse(spec_check.concern_match("money", "Runtime cost"))


class PersonasViewTest(PersonaBindingFixture):
    def test_the_view_answers_why_the_rule_was_silent(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator")
        result = self.run_cli("--personas")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("tenancy-validator", result.stdout)
        self.assertIn("declares no `covers:`", result.stdout)
        self.assertIn("Tenancy / isolation", result.stdout)

    def test_the_view_is_honest_about_an_absent_pool(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        result = self.run_cli("--personas")
        self.assertEqual(result.returncode, 0)
        self.assertIn("rule F does not apply here", result.stdout)

    def test_the_view_writes_nothing(self) -> None:
        self.corpus(CRITERIA + HORIZONTALS)
        self.persona("tenancy-validator", "[tenancy]")
        before = sorted(p.relative_to(self.root).as_posix()
                        for p in self.root.rglob("*") if p.is_file())
        self.run_cli("--personas")
        self.run_cli("--personas", "--json")
        after = sorted(p.relative_to(self.root).as_posix()
                       for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(before, after)

if __name__ == "__main__":
    unittest.main()



class DecisionQueueTest(SpecCheckFixture):
    """The one aggregate view a rendered explainer would have added, without the renderer."""

    def queue(self, *extra: str) -> list[dict]:
        result = self.run_cli("--questions", "--json", *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)["questions"]

    def test_it_folds_a_marker_that_wraps_across_lines(self) -> None:
        """Documents are hard-wrapped, so a per-line scan misses every question worth asking."""
        self.corpus(spec_body=CRITERIA + (
            "\n## Assumptions and open questions\n"
            "The vendor window is assumed. [NEEDS CLARIFICATION: what does the view show\n"
            "for a patient who never opted in?]\n"))
        rows = self.queue()
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("what does the view show for a patient who never opted in?",
                      rows[0]["question"])

    def test_a_question_in_an_approved_document_sorts_first(self) -> None:
        self.corpus(spec_body=CRITERIA + "\nx [NEEDS CLARIFICATION: draft question]\n")
        self.write("docs/product/notes.md",
                   "---\nstatus: approved\nupdated: 2026-01-01\n---\n\n"
                   "# Notes\n\ny [NEEDS CLARIFICATION: approved question]\n")
        rows = self.queue()
        self.assertEqual(rows[0]["status"], "approved")
        self.assertIn("approved question", rows[0]["question"])

    def test_a_bare_tbd_is_listed_and_is_never_a_finding(self) -> None:
        """A repository that has not adopted the marker is not thereby non-compliant."""
        self.corpus(spec_body=CRITERIA + "\nRetention is TBD.\n")
        rows = self.queue()
        self.assertTrue(any("unmarked" in row["question"] for row in rows), rows)
        self.assertDoesNotFind("D4")

    def test_the_queue_never_fails_and_writes_nothing(self) -> None:
        self.corpus(spec_body=CRITERIA + "\nz [NEEDS CLARIFICATION: unanswered]\n")
        before = sorted(p.relative_to(self.root).as_posix()
                        for p in self.root.rglob("*") if p.is_file())
        result = self.run_cli("--questions")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = sorted(p.relative_to(self.root).as_posix()
                       for p in self.root.rglob("*") if p.is_file())

SURFACE_SPEC = """---
id: F-101
title: Orders
prd: docs/product/prd.md
status: {status}
updated: 2026-03-04
edge_cases: [empty]
---

# F-101 — Orders

## Surface
- `GET /api/orders`
- `GET /api/orders/{{id}}`
- `POST /api/orders/{{id}}/cancel`
- `orders`

## Acceptance criteria

**AC-1** When an operator lists orders, given the ledger has entries, the response names every
entry.
"""


class SurfaceFixture(unittest.TestCase):
    """A real git repository: the surface check reads a diff, so there is nothing to test without
    one. Every case here is a pair — a route that must be reported and a route that must not."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "tester@example.invalid")
        self.git("config", "user.name", "Tester")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> None:
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-03-04T10:00:00",
                   GIT_COMMITTER_DATE="2026-03-04T10:00:00")
        subprocess.run(["git", "-C", str(self.root), *args], check=True, env=env,
                       capture_output=True, text=True)

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def baseline(self, status: str = "approved", spec: bool = True) -> None:
        """The commit the range starts from: the product definition, and nothing else."""
        self.write("docs/product/prd.md", PRD)
        if spec:
            self.write("docs/product/specs/F-101-orders.md", SURFACE_SPEC.format(status=status))
        self.git("add", "-A")
        self.git("commit", "-qm", "state the product definition")

    def commit_code(self, files: dict[str, str], message: str = "add code") -> None:
        for relative, text in files.items():
            self.write(relative, text)
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def restart(self) -> None:
        """A fresh repository inside a subTest loop; the old one is cleaned before it is dropped."""
        self.tearDown()
        self.setUp()

    def check(self) -> tuple[list, int]:
        return spec_check.check_surfaces(self.root.resolve(), "HEAD~1..HEAD", None)

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--surfaces",
                               *extra], capture_output=True, text=True)


class SurfaceAdoptionTest(SurfaceFixture):
    """The guard that decides whether the check is allowed to speak at all. It is the reason this
    can be switched on: a repository that never adopted specs is never blocked by them."""

    UNNAMED = {"src/hostel.py": '@app.get("/api/hostel/rooms")\ndef rooms():\n    return []\n'}

    def test_a_repository_without_specs_is_silent(self) -> None:
        self.baseline(spec=False)
        self.commit_code(self.UNNAMED)
        findings, exempt = self.check()
        self.assertEqual((list(findings), exempt), ([], 0))
        result = self.run_cli("--range", "HEAD~1..HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_a_draft_spec_does_not_switch_the_check_on(self) -> None:
        self.baseline(status="draft")
        self.commit_code(self.UNNAMED)
        self.assertEqual(list(self.check()[0]), [])

    def test_approved_building_and_shipped_all_switch_it_on(self) -> None:
        for status in ("approved", "building", "shipped"):
            with self.subTest(status=status):
                self.restart()
                self.baseline(status=status)
                self.commit_code(self.UNNAMED)
                self.assertEqual([item.rule for item in self.check()[0]], ["S1"])

    def test_a_spec_whose_surface_section_is_empty_stays_silent(self) -> None:
        """No surfaces means no answer, and a check with no answer must not invent findings."""
        self.write("docs/product/prd.md", PRD)
        head, _, tail = SURFACE_SPEC.format(status="approved").partition("## Surface")
        criteria = "## Acceptance" + tail.partition("## Acceptance")[2]
        self.write("docs/product/specs/F-101-orders.md", head + "## Surface\n\nTBD\n\n" + criteria)
        self.git("add", "-A")
        self.git("commit", "-qm", "state the product definition")
        self.commit_code(self.UNNAMED)
        self.assertEqual(list(self.check()[0]), [])


class SurfaceMatchTest(SurfaceFixture):
    def test_a_route_named_in_the_surface_section_passes(self) -> None:
        self.baseline()
        self.commit_code({"src/orders.py": '@app.get("/api/orders")\ndef orders():\n    return []\n'})
        result = self.run_cli("--range", "HEAD~1..HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_a_route_no_spec_names_is_reported_with_its_path_and_line(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py": '@app.get("/api/hostel/rooms")\ndef rooms():\n    r = 1\n'})
        result = self.run_cli("--range", "HEAD~1..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/hostel.py:1", result.stdout)
        self.assertIn("S1", result.stdout)
        self.assertIn("/api/hostel/rooms is not named in the Surface section", result.stdout)

    def test_only_added_lines_count_so_a_move_is_not_new_surface(self) -> None:
        """A refactor that relocates a route exposes nothing; a check that fires on one is removed."""
        self.baseline()
        self.commit_code({"src/hostel.py": '@app.get("/api/hostel/rooms")\ndef rooms():\n    r = 1\n'},
                         message="add the module")
        self.commit_code({"src/hostel.py": '@app.get("/api/hostel/rooms")\ndef rooms():\n    r = 2\n'},
                         message="touch the body, not the route")
        self.assertEqual(list(self.check()[0]), [])

    def test_a_class_level_request_mapping_prefixes_the_methods_below_it(self) -> None:
        self.baseline()
        self.commit_code({"src/OrderController.java":
                          '@RequestMapping("/api/orders")\nclass OrderController {\n'
                          '  @GetMapping("/{id}")\n  Order one() { return null; }\n}\n'})
        self.assertEqual(list(self.check()[0]), [])

    def test_a_class_level_prefix_is_never_reported_as_a_route_of_its_own(self) -> None:
        self.baseline()
        self.commit_code({"src/HostelController.java":
                          '@RequestMapping("/api/hostel")\nclass HostelController {\n}\n'})
        self.assertEqual(list(self.check()[0]), [])

    def test_a_prefixed_method_outside_any_visible_prefix_matches_by_suffix(self) -> None:
        """The prefix is normally outside the hunk, so `/{id}/cancel` has to reach the spec's
        `/api/orders/{id}/cancel` on its own."""
        self.baseline()
        self.commit_code({"src/OrderController.java":
                          '  @PostMapping("/{id}/cancel")\n  void cancel() {}\n'})
        self.assertEqual(list(self.check()[0]), [])

    def test_a_suffix_that_is_not_on_a_segment_boundary_does_not_match(self) -> None:
        self.baseline()
        self.commit_code({"src/orders.py": '@app.get("/api/backorders")\ndef back():\n    r = 1\n'})
        self.assertEqual([item.rule for item in self.check()[0]], ["S1"])


class SurfaceExtractorTest(SurfaceFixture):
    """The pattern table, one dialect at a time. Each declares a route the spec does NOT name, so a
    silent extractor fails the test rather than passing it."""

    DIALECTS = {
        "src/Hostel.java": '  @GetMapping("/api/hostel/rooms")\n  List<Room> rooms() { return null; }\n',
        "src/hostel.js": "app.get('/api/hostel/rooms', (req, res) => res.json([]));\n",
        "src/rooms.js": "router.post('/api/hostel/rooms', handler);\n",
        "src/hostel.py": '@router.delete("/api/hostel/rooms")\ndef drop():\n    r = 1\n',
        "src/flask_app.py": '@app.route("/api/hostel/rooms")\ndef page():\n    r = 1\n',
        "src/cli.py": 'sub.add_parser("hostel")\n',
        "src/commands.py": '@cli.command("hostel")\ndef hostel():\n    r = 1\n',
    }

    def test_every_documented_dialect_is_extracted(self) -> None:
        for relative, text in self.DIALECTS.items():
            with self.subTest(dialect=relative):
                self.restart()
                self.baseline()
                self.commit_code({relative: text})
                self.assertEqual([item.rule for item in self.check()[0]], ["S1"], text)

    def test_the_pattern_table_is_a_readable_constant(self) -> None:
        """The table is the documented coverage; a reader must be able to enumerate it."""
        self.assertEqual([name for name, _ in spec_check.ROUTE_PATTERNS],
                         ["spring", "js", "python", "cli"])
        for _, pattern in spec_check.ROUTE_PATTERNS:
            self.assertIn("route", pattern.groupindex)

    def test_ordinary_code_declares_no_routes(self) -> None:
        """The false-positive half. None of these lines exposes anything."""
        for text in ("value = config.get('/api/orders')\n", "logger.info('/api/hostel/rooms')\n",
                     "# see /api/hostel/rooms for the shape\n", "self.assertEqual(a, b)\n",
                     "return requests.get(url).json()\n"):
            with self.subTest(text=text):
                self.restart()
                self.baseline()
                self.commit_code({"src/thing.py": text})
                self.assertEqual(list(self.check()[0]), [], text)


class SurfaceNormalisationTest(unittest.TestCase):
    """Normalisation and matching, directly: these are the two places a false positive is born."""

    def test_every_path_parameter_spelling_collapses_to_one_star(self) -> None:
        for raw in ("/api/orders/{id}", "/API/Orders/:id/", "/api/orders/<int:id>",
                    "/api/orders/<id>", "GET /api/orders/{orderId}"):
            with self.subTest(raw=raw):
                self.assertEqual(spec_check.normalise_route(raw), "/api/orders/*")

    def test_a_command_name_normalises_like_a_path(self) -> None:
        self.assertEqual(spec_check.normalise_route("orders"), "/orders")
        self.assertEqual(spec_check.normalise_route(""), "/")

    def test_a_suffix_matches_only_on_a_segment_boundary(self) -> None:
        self.assertTrue(spec_check.surface_match("/*", "/api/orders/*"))
        self.assertTrue(spec_check.surface_match("/api/orders/*", "/orders/*"))
        self.assertTrue(spec_check.surface_match("/api/orders", "/api/orders"))
        self.assertFalse(spec_check.surface_match("/api/backorders", "/api/orders"))
        self.assertFalse(spec_check.surface_match("/api/orders/cancel", "/api/orders/close"))


class SurfaceExemptionTest(SurfaceFixture):
    """An exemption nobody can see is a hole; an exemption everyone can count is a decision."""

    def test_an_exemption_on_the_route_line_is_skipped_and_counted(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py":
                          '@app.get("/api/hostel/rooms")  # spec-exempt: internal probe, F-102\n'
                          'def rooms():\n    r = 1\n'})
        findings, exempt = self.check()
        self.assertEqual(list(findings), [])
        self.assertEqual(exempt, 1)

    def test_an_exemption_on_the_line_above_is_skipped_and_counted(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py":
                          '# spec-exempt: internal probe, tracked in F-102\n'
                          '@app.get("/api/hostel/rooms")\ndef rooms():\n    r = 1\n'})
        findings, exempt = self.check()
        self.assertEqual(list(findings), [])
        self.assertEqual(exempt, 1)

    def test_the_count_is_printed_in_the_summary(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py":
                          '@app.get("/api/hostel/a")  # spec-exempt: probe\n'
                          '@app.get("/api/hostel/b")  # spec-exempt: probe\n'
                          '@app.get("/api/hostel/c")  # spec-exempt: probe\n'})
        result = self.run_cli("--range", "HEAD~1..HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("3 route(s) exempt", result.stdout)

    def test_an_exemption_reaches_one_line_and_no_further(self) -> None:
        """It covers its own line and the line below, because that is where the comment sits. The
        next route down is still reported: an exemption is one decision, not a switch."""
        self.baseline()
        self.commit_code({"src/hostel.py":
                          '@app.get("/api/hostel/a")  # spec-exempt: probe\n'
                          'def a():\n    r = 1\n'
                          '@app.get("/api/hostel/b")\ndef b():\n    r = 2\n'})
        findings, exempt = self.check()
        self.assertEqual([item.message.split(" is not")[0] for item in findings],
                         ["/api/hostel/b"])
        self.assertEqual(exempt, 1)


class SurfaceExclusionTest(SurfaceFixture):
    def test_test_files_and_vendored_trees_are_not_new_surface(self) -> None:
        for relative in ("tests/test_hostel.py", "src/__tests__/hostel.js", "src/hostel.test.ts",
                         "src/HostelControllerTest.java", "node_modules/x/index.js",
                         "vendor/x/app.js", "build/gen.js"):
            with self.subTest(path=relative):
                self.restart()
                self.baseline()
                self.commit_code({relative: '@app.get("/api/hostel/rooms")\nx = 1\n'
                                            if relative.endswith(".py")
                                            else "app.get('/api/hostel/rooms', h);\n"})
                self.assertEqual(list(self.check()[0]), [], relative)

    def test_the_exclusion_list_is_the_shared_one(self) -> None:
        """Imported, not copied: two lists drift, and the drift is invisible until it matters."""
        self.assertIs(spec_check.is_excluded, ratio_meter.is_excluded)


class SurfaceCliTest(SurfaceFixture):
    def test_surfaces_without_a_scope_is_a_usage_error(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("--range", result.stderr)

    def test_since_selects_the_same_commits_as_a_range(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py": '@app.get("/api/hostel/rooms")\ndef rooms():\n    r = 1\n'})
        # `--since=<today>` is git approxidate: the date alone means this time of day, so the
        # fixture asks for a date safely before the commits rather than the day they sit on.
        findings, _ = spec_check.check_surfaces(self.root.resolve(), None, "2026-03-01")
        self.assertEqual([item.rule for item in findings], ["S1"])

    def test_json_carries_the_findings_and_the_exempt_count(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py":
                          '@app.get("/api/hostel/a")\n'
                          '@app.get("/api/hostel/b")  # spec-exempt: probe\ndef a():\n    r = 1\n'})
        result = self.run_cli("--range", "HEAD~1..HEAD", "--json")
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload["exempt"], 1)
        self.assertEqual([item["rule"] for item in payload["findings"]], ["S1"])

    def test_the_surface_check_writes_nothing(self) -> None:
        self.baseline()
        self.commit_code({"src/hostel.py": '@app.get("/api/hostel/rooms")\ndef rooms():\n    r = 1\n'})
        before = {path: path.stat().st_mtime_ns
                  for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(self.run_cli("--range", "HEAD~1..HEAD").returncode, 1)
        after = {path: path.stat().st_mtime_ns
                 for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(before, after)


class TemplateSelfCheckTest(SpecCheckFixture):
    """Every template this skill ships must pass the checker that reads it.

    Both shipped templates failed this the first time it was run: `withdrawn: [3, 9]  # optional`
    kept its comment, so the value never reached the flow-list branch and arrived as a string that
    every list check mis-read. The templates are the one input guaranteed to be copied verbatim, so
    a template the checker rejects is a defect in one of the two, every time.
    """

    REFERENCE = SCRIPT.parent.parent / "references" / "specs.md"

    def extract(self, heading: str) -> str:
        text = self.REFERENCE.read_text(encoding="utf-8")
        start = text.index(heading)
        block = re.search(r"````markdown\n(.*?)\n````", text[start:], re.S)
        self.assertIsNotNone(block, f"no fenced template under {heading}")
        return block.group(1)

    def concrete(self, template: str) -> str:
        """Fill the angle-bracket placeholders; everything else must already be valid."""
        for token, value in (("F-<id>", "F-12"), ("<slug>", "reminders"), ("<feature>", "Reminder"),
                             ("<YYYY-MM-DD>", "2026-02-11"), ("<n>", "1"),
                             ("draft | approved | building | shipped | dropped", "draft"),
                             ("draft | approved | building | shipped", "draft"),
                             ("light | full", "full"), ("<trigger>", "x happens"),
                             ("<precondition>", "y holds"),
                             ("<observable result>", "the system shall z")):
            template = template.replace(token, value)
        return re.sub(r"<[^>\n]{1,60}>", "placeholder", template)

    def test_the_feature_spec_template_passes_the_checker(self) -> None:
        self.write("docs/product/prd.md",
                   "---\ntitle: T\nstatus: draft\nupdated: 2026-02-11\n---\n\n"
                   "# T\n\n## Why this exists\nx\n")
        self.write("docs/product/specs/F-12-reminders.md",
                   self.concrete(self.extract("## The feature spec")))
        self.assertEqual(self.rules(), [], "the shipped feature-spec template must self-check")

    def test_a_trailing_comment_never_reaches_the_value(self) -> None:
        data, _, _ = spec_check.parse_front_matter(
            ["---", "withdrawn: [3, 9]   # optional", "status: draft  # a note",
             'title: "keeps the #3"', "id: F-12#a", "---"])
        self.assertEqual(data["withdrawn"], ["3", "9"])
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["title"], "keeps the #3", "a quoted value keeps its hash")
        self.assertEqual(data["id"], "F-12#a", "no space before # means it is part of the value")


class RecordExemptionTest(SpecCheckFixture):
    """A rule binds the documents it was written for.

    Measured on a real repository: 12 findings, of which 9 were this category error. A change
    request exists to say "this was X, make it Y", and a ruling inside one is dated because the date
    is the point. Applying the current-state rule there is the same mistake as demanding front
    matter from every README, which this checker already made once.
    """

    DATED = "\n## RULING 2026-08-11 — the row closes\n\nx\n"

    def test_a_change_request_may_record_its_own_history(self) -> None:
        self.corpus()
        self.write("docs/product/change-requests/CR-2026-08-09-thing.md",
                   "# CR — a thing\n" + self.DATED)
        self.assertDoesNotFind("A1")

    def test_a_decision_record_and_a_changelog_are_exempt(self) -> None:
        self.corpus()
        self.write("docs/product/decisions/0004-timing.md", "# 0004\n" + self.DATED)
        self.write("docs/product/CHANGELOG.md", "# Changelog\n\n## Revision history\n\nx\n")
        self.assertEqual(self.rules(), [])

    def test_a_specification_is_not_exempt_by_sitting_beside_one(self) -> None:
        """The exemption is the document's purpose, not its neighbourhood."""
        self.corpus()
        self.write("docs/product/screens/thing/specification.md",
                   "# Thing\n\n## Changelog\n\nx\n")
        self.assertFinds("A2")


class HistoryHeadingPrecisionTest(SpecCheckFixture):
    """The heading must BE a history section, not mention one.

    `# Run history` is a real screen in a real product — an audit log a user reads — and the
    word-anywhere pattern told a feature about history to stop being a changelog. Third instance of
    the same collision after `receipt`/`cards` in the classifier and `superseded` in the prose rule.
    """

    def assertHeading(self, flagged: bool, *headings: str) -> None:
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertEqual(bool(spec_check.HISTORY_HEADING_RE.match(heading)), flagged)

    def test_a_product_feature_named_history_is_not_a_changelog(self) -> None:
        self.assertHeading(False, "# Run history (`aut_runs`)", "## Run history",
                           "## Payment history", "### Order history and receipts")

    def test_a_real_history_section_is_still_caught(self) -> None:
        self.assertHeading(True, "## Changelog", "## Change log", "## Revision history",
                           "### History of changes", "## What changed since the last handoff",
                           "## Revisions")


class WithdrawnSuccessorTest(SpecCheckFixture):
    """`3` and `3>11` mean different things to whoever holds a test citing AC-3.

    A plain retirement means the test asserts something nobody wants and should go. A supersession
    means it should be repointed, and only the spec knows where to. Without the arrow both read as
    "dead id" and a tracer could say nothing more useful.
    """

    def front(self, withdrawn: str) -> str:
        return ("---\nid: F-7\ntitle: T\nprd: docs/product/prd.md\nstatus: draft\n"
                f"updated: 2026-01-01\nedge_cases: [empty]\nwithdrawn: {withdrawn}\n---\n")

    def spec_with(self, withdrawn: str) -> None:
        self.write("docs/product/prd.md", PRD)
        self.write("docs/product/specs/F-7-thing.md", self.front(withdrawn) + CRITERIA)

    def test_a_supersession_is_accepted(self) -> None:
        self.spec_with("[3>11]")
        self.assertDoesNotFind("B5")

    def test_an_arrow_with_no_successor_is_refused(self) -> None:
        self.spec_with("[3>]")
        self.assertFinds("B5")

    def test_a_chain_may_not_end_on_a_withdrawn_id(self) -> None:
        self.spec_with("[3>11, 11]")
        self.assertFinds("B5")

    def test_a_split_feature_takes_a_letter(self) -> None:
        """F-9 becoming F-9A..F-9J must not require renumbering what tests already cite."""
        self.assertTrue(spec_check.ID_RE.match("F-9A"))
        self.assertTrue(spec_check.ID_RE.match("F-009"))
        self.assertFalse(spec_check.ID_RE.match("F-9AB"))
        self.assertFalse(spec_check.ID_RE.match("F-9a"))


class DeferralRegisterTest(SpecCheckFixture):
    """Rule E — the milestone's `## Deferred` register.

    Principle 6 promised "deferrals live in a register that a milestone can fail against" and no
    script could fail against anything. These tests are written in both directions for every rule,
    and the shape tests below are the ones that matter most: this parser was first written to read
    a key as "any indent, then `word:`" and, run over 178 rows of a REAL register, called 22 of
    them malformed because a wrapped line of prose began `design:` or `confirmed:`. The indent rule
    that replaced it is tested here directly.
    """

    ENTRY = """- **D-1** the export re-reads the manifest for every row
  found_by: F-007/T3
  site: `src/export/writer.py:214`
  threatens: AC-1
  trigger: `python3 -m unittest tests.test_export` — 1 failure, 3.9 s
  owner: M4
  raised: 2026-01-05
"""

    def milestone(self, name: str = "M1", status: str = "building", register: str | None = None,
                  slug: str = "core") -> None:
        body = f"## Deferred\n\n{register}" if register is not None else ""
        self.write(f"docs/product/milestones/{name}-{slug}.md",
                   f"---\nmilestone: {name}\ntitle: {slug}\nstatus: {status}\n"
                   f"updated: 2026-01-01\n---\n\n# {name} — {slug}\n\n## Goal\nIt ships.\n\n"
                   + body)

    def member_spec(self, milestone: str = "M1") -> None:
        self.write("docs/product/specs/F-007-export.md",
                   SPEC_HEAD.replace("updated: 2026-01-01",
                                     f"updated: 2026-01-01\nmilestone: {milestone}") + CRITERIA)

    def setUpRegister(self, register: str, status: str = "building") -> None:
        self.corpus()
        self.member_spec()
        self.milestone(status=status, register=register)
        self.write("docs/product/milestones/M4-later.md",
                   "---\nmilestone: M4\ntitle: later\nstatus: draft\nupdated: 2026-01-01\n"
                   "---\n\n# M4 — later\n\n## Goal\nLater.\n")

    # --- the pass side -------------------------------------------------------------------------

    def test_a_well_formed_entry_is_silent(self) -> None:
        self.setUpRegister(self.ENTRY)
        self.assertEqual([r for r in self.rules() if r.startswith("E")], [])

    def test_a_milestone_with_no_register_is_silent(self) -> None:
        """Adoption: a milestone document written before the register existed is not a finding."""
        self.corpus()
        self.member_spec()
        self.milestone()
        self.assertEqual([r for r in self.rules() if r.startswith("E")], [])

    def test_none_is_legal_for_threatens_trigger_and_owner(self) -> None:
        """A finding with no trigger is exactly what the fix/record rule sends here. Requiring one
        would make the register refuse the entries it exists to hold."""
        self.setUpRegister(self.ENTRY.replace("threatens: AC-1", "threatens: none")
                           .replace("trigger: `python3 -m unittest tests.test_export` — 1 "
                                    "failure, 3.9 s", "trigger: none")
                           .replace("owner: M4", "owner: none"))
        self.assertEqual([r for r in self.rules() if r.startswith("E")], [])

    def test_threatens_may_name_an_invariant_rather_than_a_criterion(self) -> None:
        self.setUpRegister(self.ENTRY.replace("threatens: AC-1", "threatens: exports-are-append-only"))
        self.assertDoesNotFind("E4")

    def test_a_bare_task_id_is_legal(self) -> None:
        self.setUpRegister(self.ENTRY.replace("found_by: F-007/T3", "found_by: T3"))
        self.assertDoesNotFind("E3")

    def test_a_lead_paragraph_under_the_heading_is_not_an_entry(self) -> None:
        self.setUpRegister("Open items only; closing one deletes it.\n\n" + self.ENTRY)
        self.assertEqual([r for r in self.rules() if r.startswith("E")], [])

    def test_a_fenced_example_of_the_shape_is_not_linted(self) -> None:
        """A document showing its own template must stay lintable, the rule `doc.body()` already
        applies to every other check."""
        self.setUpRegister("```yaml\n- **D-9** an example with no keys at all\n```\n")
        self.assertEqual([r for r in self.rules() if r.startswith("E")], [])

    # --- shape, E1 and E2 ----------------------------------------------------------------------

    def test_a_missing_key_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("  raised: 2026-01-05\n", ""))
        self.assertFinds("E1")

    def test_an_unknown_key_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY + "  severity: high\n")
        self.assertFinds("E1")

    def test_a_repeated_key_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY + "  owner: M4\n")
        self.assertFinds("E1")

    def test_an_entry_with_no_headline_text_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace(
            "- **D-1** the export re-reads the manifest for every row", "- **D-1**"))
        self.assertFinds("E1")

    def test_a_continuation_line_beginning_with_a_word_and_a_colon_is_not_a_key(self) -> None:
        """THE REGRESSION THIS PARSER WAS BUILT WRONG FOR ONCE. Measured on a real 178-row
        register: 22 rows were called malformed because a wrapped line of prose began `design:`,
        `known:`, `confirmed:` or `verbatim:`. Four spaces of indent is continuation, always."""
        wrapped = self.ENTRY.replace(
            "  trigger: `python3 -m unittest tests.test_export` — 1 failure, 3.9 s",
            "  trigger: `python3 -m unittest tests.test_export` — 1 failure, 3.9 s\n"
            "    design: the writer opens the manifest inside the row loop\n"
            "    confirmed: reproduced on a clean tree")
        self.setUpRegister(wrapped)
        self.assertEqual([r for r in self.rules() if r.startswith("E")], [])

    def test_a_key_at_two_spaces_is_still_a_key(self) -> None:
        """The other direction of the same rule: tightening the indent must not stop reading the
        keys that are there."""
        self.setUpRegister(self.ENTRY.replace("  owner: M4", "  ownr: M4"))
        rules = [r for r in self.rules() if r.startswith("E")]
        self.assertIn("E1", rules)

    def test_two_entries_under_one_id_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY + self.ENTRY)
        self.assertFinds("E2")

    def test_an_empty_site_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("  site: `src/export/writer.py:214`", "  site:"))
        self.assertFinds("E1")

    # --- the cross-references, E3 to E6 --------------------------------------------------------

    def test_found_by_that_is_not_a_task_id_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("found_by: F-007/T3", "found_by: the reviewer"))
        self.assertFinds("E3")

    def test_found_by_naming_a_feature_outside_this_milestone_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("found_by: F-007/T3", "found_by: F-900/T3"))
        self.assertFinds("E3")

    def test_threatens_naming_a_criterion_no_member_declares_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("threatens: AC-1", "threatens: AC-77"))
        self.assertFinds("E4")

    def test_an_owner_that_is_not_a_milestone_id_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("owner: M4", "owner: next quarter"))
        self.assertFinds("E5")

    def test_an_owner_with_no_milestone_document_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("owner: M4", "owner: M9"))
        self.assertFinds("E5")

    def test_an_open_entry_owned_by_a_shipped_milestone_is_a_finding(self) -> None:
        """The one outcome a register exists to make impossible: the milestone closed and the
        deferral did not. This is the rule a real project's own gate enforces in bash."""
        self.setUpRegister(self.ENTRY)
        self.write("docs/product/milestones/M4-later.md",
                   "---\nmilestone: M4\ntitle: later\nstatus: shipped\nupdated: 2026-01-01\n"
                   "---\n\n# M4 — later\n\n## Goal\nLater.\n")
        self.assertFinds("E5")

    def test_sealing_a_milestone_with_an_unowned_entry_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("owner: M4", "owner: none"), status="shipped")
        self.assertFinds("E5")

    def test_an_unowned_entry_before_the_seal_is_not_a_finding(self) -> None:
        """The other direction. `owner: none` is the honest state of a finding nobody has scheduled
        yet, and failing it before the seal trains authors to guess an owner."""
        self.setUpRegister(self.ENTRY.replace("owner: M4", "owner: none"), status="building")
        self.assertDoesNotFind("E5")

    def test_a_raised_date_that_is_not_a_date_is_a_finding(self) -> None:
        self.setUpRegister(self.ENTRY.replace("raised: 2026-01-05", "raised: last week"))
        self.assertFinds("E6")

    # --- rule A stands back from the register ---------------------------------------------------

    def test_a3_does_not_fire_inside_the_register(self) -> None:
        """A deferral entry describes A DEFECT's past, not the document's. Measured: A3 fired on 7
        of 178 real register rows on the other reading."""
        self.setUpRegister(self.ENTRY.replace(
            "the export re-reads the manifest for every row",
            "the earlier drafts of the writer were wrong about the manifest"))
        self.assertDoesNotFind("A3")

    def test_a3_still_fires_outside_the_register_in_the_same_document(self) -> None:
        self.setUpRegister(self.ENTRY)
        path = self.root / "docs/product/milestones/M1-core.md"
        path.write_text(path.read_text(encoding="utf-8")
                        + "\n## Where it stops\nAn earlier version of this milestone said more.\n",
                        encoding="utf-8")
        self.assertFinds("A3")

    def test_a2_still_fires_inside_the_register(self) -> None:
        """A1 and A2 are NOT relaxed: a changelog heading inside the register is the register being
        appended to, which is precisely what rule A is for."""
        self.setUpRegister(self.ENTRY)
        path = self.root / "docs/product/milestones/M1-core.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "## Deferred", "## Deferred\n\n### Changelog\n"), encoding="utf-8")
        self.assertFinds("A2")

    # --- the listing ----------------------------------------------------------------------------

    def test_deferred_lists_the_register_and_exits_zero(self) -> None:
        self.setUpRegister(self.ENTRY)
        result = self.run_cli("--deferred")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("D-1", result.stdout)
        self.assertIn("1 open deferral(s)", result.stdout)

    def test_deferred_counts_the_unowned_separately(self) -> None:
        """The count is the whole reason this mode exists: a register nobody counts only grows."""
        self.setUpRegister(self.ENTRY.replace("owner: M4", "owner: none"))
        result = self.run_cli("--deferred")
        self.assertIn("1 open, 1 with no owner", result.stdout)

    def test_deferred_json_is_machine_readable(self) -> None:
        self.setUpRegister(self.ENTRY)
        result = self.run_cli("--deferred", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["deferred"][0]["id"], "D-1")
        self.assertEqual(payload["deferred"][0]["milestone"], "M1")

    def test_deferred_on_a_corpus_with_no_milestone_says_so(self) -> None:
        self.corpus()
        result = self.run_cli("--deferred")
        self.assertEqual(result.returncode, 0)
        self.assertIn("no deferral register", result.stdout)

    def test_a_malformed_entry_does_not_break_the_listing(self) -> None:
        """`--deferred` is a list, not a gate: `run()` owns the shape findings, and a register that
        cannot be listed because one row is wrong is a register nobody can triage."""
        self.setUpRegister(self.ENTRY + "- **D-2** no keys at all\n")
        result = self.run_cli("--deferred")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("D-2", result.stdout)


class UnboundSpecSilenceTest(SpecCheckFixture):
    """A repository whose specs this checker cannot see must not read as a clean one.

    Measured: one real repository writes every feature spec as `specs/<slug>/spec.md`. It holds 274
    such documents, 130 of them carrying the `## Horizontals` section rule F reads, and `spec_check`
    bound NONE of them and printed 0 findings, exit 0. That result was reported as clean three times
    before anyone noticed it meant unchecked. The naming is the repository's choice and is not a
    defect, so this is never a finding — but the silence is now said out loud.
    """

    def nested(self) -> None:
        self.write("docs/product/prd.md", PRD)
        self.write("docs/product/specs/moderation/spec.md", "# Moderation\n\n## Horizontals\n\n"
                   "| Concern | Disposition |\n|---|---|\n| Audit trail | Every action logged. |\n")

    def test_an_unreadable_layout_is_reported_not_charged(self) -> None:
        self.nested()
        out = self.run_cli().stdout
        self.assertNotIn("specs/moderation/spec.md", out,
                         "a naming choice is not a defect and must not be charged as one")
        self.assertIn("are not named `F-<n>-<slug>.md`", out,
                      "said in both the pool and no-pool forms of the report")

    def test_a_bound_layout_says_nothing_about_unbound_documents(self) -> None:
        """The line must stay quiet when there is nothing unread, or it becomes noise."""
        self.corpus()
        self.assertNotIn("are not named `F-<n>-<slug>.md`", self.run_cli().stdout)
