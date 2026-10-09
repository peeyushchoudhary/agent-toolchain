"""The always-loaded ceiling (D29): the prose every session pays for stays short.

The always-loaded files are the global instructions, this repository's AGENTS.md and the skill's
SKILL.md. Words are whitespace-separated tokens, which is what a reader's context pays for.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALWAYS_LOADED = (REPO / "install" / "global.md", REPO / "AGENTS.md",
                 REPO / "install" / "skills" / "execution-methodology" / "SKILL.md")
MAX_LINES = 200
MAX_WORDS = 1_350


class AlwaysLoadedCeiling(unittest.TestCase):
    def test_each_file_is_at_most_200_lines_and_all_together_at_most_1350_words(self):
        texts = {p.relative_to(REPO).as_posix(): p.read_text(encoding="utf-8") for p in ALWAYS_LOADED}
        lines = {name: len(t.splitlines()) for name, t in texts.items()}
        words = {name: len(t.split()) for name, t in texts.items()}
        self.assertTrue(all(lines.values()), lines)
        self.assertLessEqual(max(lines.values()), MAX_LINES, lines)
        self.assertLessEqual(sum(words.values()), MAX_WORDS, words)


if __name__ == "__main__":
    unittest.main()
