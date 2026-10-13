"""The records' live facts: D35 ends the pilot, D29's table status names it, and the pages say so (S-9)."""
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECISIONS = REPO / "docs" / "decisions" / "decisions.md"
METHODOLOGY = REPO / "docs" / "architecture" / "methodology.md"
STANDARD = REPO / "docs" / "architecture" / "repository-standard.md"
MEASUREMENTS = REPO / "docs" / "product" / "measurements.md"
D35 = "## D35 — The pilot and its stop rule have ended (S-9)"


def table_row(lines: list[str], ident: str) -> str:
    """The decisions table's row whose first cell links ident."""
    return next((l for l in lines if l.startswith(f"| [{ident}](")), "")


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


if __name__ == "__main__":
    unittest.main()
