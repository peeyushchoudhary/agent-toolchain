"""The records' live facts: D35 ends the pilot, D29's table status names it, and the pages say so (S-9);
D36 ships the repository rules, the layout runbook guards what a migration could lose, and the README answers
the seven questions (S-10)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECISIONS = REPO / "docs" / "decisions" / "decisions.md"
METHODOLOGY = REPO / "docs" / "architecture" / "methodology.md"
STANDARD = REPO / "docs" / "architecture" / "repository-standard.md"
MEASUREMENTS = REPO / "docs" / "product" / "measurements.md"
GLOBAL = REPO / "install" / "global.md"
VERIFY = REPO / "install" / "verify.sh"
RUNBOOK = REPO / "docs" / "runbooks" / "migrate-layout.md"
REFERENCES = REPO / "install" / "skills" / "execution-methodology" / "references"
README = REPO / "README.md"
D35 = "## D35 — The pilot and its stop rule have ended (S-9)"
D36 = ("## D36 — The README answers seven questions again; the repository rules ship with the skill;"
       " docs.py links (S-10)")


def table_row(lines: list[str], ident: str) -> str:
    """The decisions table's row whose first cell links ident."""
    return next((l for l in lines if l.startswith(f"| [{ident}](")), "")


def sentence(path: Path, words: str) -> str:
    """The first sentence of path, its lines joined, that holds words."""
    text = " ".join(path.read_text(encoding="utf-8").split())
    return next((s for s in re.split(r"(?<=\.) ", text) if words in s), "")


class RecordsTest(unittest.TestCase):
    def test_d35_ends_the_pilot_and_updates_d29(self):
        lines = DECISIONS.read_text(encoding="utf-8").splitlines()
        self.assertIn(D35, lines)
        section = lines[lines.index(D35) + 1:]
        section = section[:next((i for i, l in enumerate(section) if l.startswith("## ")), len(section))]
        reverses = next((l for l in section if l.startswith("**Reverses:**")), "")
        self.assertIn("D29", reverses)
        self.assertIn("D30", reverses)
        self.assertIn("ended by D35", table_row(lines, "D29"))
        self.assertTrue(table_row(lines, "D35").endswith("| standing |"), table_row(lines, "D35"))

    def test_pages_state_the_pilot_ended_and_the_map_as_current(self):
        methodology = METHODOLOGY.read_text(encoding="utf-8")
        self.assertIn("#d35--the-pilot-and-its-stop-rule-have-ended-s-9", methodology)
        self.assertIn("Until D35 ended it", methodology)
        self.assertNotIn("D29's stop rule stands", methodology)
        standard = STANDARD.read_text(encoding="utf-8")
        self.assertIn("`docs/goals/<id>/**`", standard)
        self.assertIn("`docs/goals/modules.json` states the current map", standard)
        self.assertIn("read-when: Citing a number or recording a measurement",
                      MEASUREMENTS.read_text(encoding="utf-8").splitlines())

    def test_d36_ships_the_repository_rules(self):
        lines = DECISIONS.read_text(encoding="utf-8").splitlines()
        self.assertIn(D36, lines)
        self.assertIn("restored as prose by D36", table_row(lines, "D1"))
        self.assertIn("superseded by D30 and D36", table_row(lines, "D17"))
        self.assertTrue(table_row(lines, "D36").endswith("| standing |"), table_row(lines, "D36"))
        self.assertIn("read each AGENTS.md between the repository root and it", GLOBAL.read_text(encoding="utf-8"))

    def test_lessons_record_can_retain_retired_component_rationale(self):
        self.assertIn("`docs/agents/lessons.md`", sentence(STANDARD, "may name removed components"))
        excludes = [l for l in VERIFY.read_text(encoding="utf-8").splitlines() if l.startswith("EXCLUDE=")]
        self.assertTrue(any("docs/agents/lessons.md" in l for l in excludes), excludes)

    def test_readme_answers_the_seven_questions_in_order(self):
        lines = README.read_text(encoding="utf-8").splitlines()
        self.assertEqual([l[3:] for l in lines if l.startswith("## ")],
                         ["Overview", "Current state", "Product requirements", "Architecture", "Components",
                          "Run locally", "Working in this repository"])
        self.assertTrue(lines[-1].startswith("<!-- covers: ["), lines[-1])
        self.assertEqual(re.findall(r"\b[0-9a-f]{7,40}\b", "\n".join(lines)), [])


class LayoutMigrationTest(unittest.TestCase):
    """S-10: the layout runbook checks readers, gates a fresh checkout and keeps what it untracks."""

    def text(self) -> str:
        return RUNBOOK.read_text(encoding="utf-8")

    def test_gate_input_survives_migration_in_a_fresh_checkout(self):
        text = " ".join(self.text().split())
        self.assertIn("git worktree add --detach", text)
        self.assertIn("Markdown included", text)

    def test_rollback_preserves_modified_ignored_files(self):
        rollback = next((l for l in self.text().splitlines() if l.startswith("Rollback")), "")
        self.assertIn("copy the untracked paths aside", rollback)

    def test_archival_preserves_cited_records_and_verifies_recovery_content(self):
        text = " ".join(self.text().split())
        for words in ("git cat-file -e", "pushed", "records"):
            self.assertIn(words, text)
        self.assertNotIn(":!*.md", text)

    def test_planning_and_close_point_to_the_reference(self):
        planning = " ".join((REFERENCES / "planning.md").read_text(encoding="utf-8").split())
        self.assertIn("a last task writing `README.md`", planning)
        self.assertIn("(repository.md)", planning)
        self.assertIn("last-verified: YYYY-MM-DD", (REFERENCES / "repository.md").read_text(encoding="utf-8"))
        self.assertIn("(repository.md#lifecycle)", (REFERENCES / "close.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
