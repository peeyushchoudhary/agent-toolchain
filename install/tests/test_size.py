"""Size ceilings on the published methodology (AC-9), and the place for T9's AC-13 check.

Words are whitespace-separated tokens, which is what a reader's context pays for. Code lines are
physical lines of `.py` and `.sh` files under a skill's `scripts/`, which is where the non-test code
lives; tests sit under `tests/`, and `*_selftest.py` files are tests by name.
"""
from __future__ import annotations

import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
EM = SKILLS / "execution-methodology"
AP = SKILLS / "agent-personas"

RULES_WORDS = 1_500        # methodology.md, the chief's rules
ROLE_LOAD_WORDS = 3_000    # SKILL.md + methodology.md + any one reference
CODE_LINES = 2_500         # execution-methodology + agent-personas, non-test code
PERSONA_SOURCES = 5


def words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split())


def non_test_lines(skill: Path) -> int:
    """Physical lines of non-test .py/.sh code under skill/scripts. T9's AC-13 check reuses this."""
    total = 0
    for p in sorted((skill / "scripts").rglob("*")):
        if p.suffix in (".py", ".sh") and p.is_file() and "__pycache__" not in p.parts \
                and not p.name.endswith("_selftest.py"):
            total += len(p.read_text(encoding="utf-8").splitlines())
    return total


class SizeCeilings(unittest.TestCase):
    def test_rules_core_is_at_most_1500_words(self):
        self.assertLessEqual(words(EM / "methodology.md"), RULES_WORDS)

    def test_any_one_role_loads_at_most_3000_words(self):
        base = words(EM / "SKILL.md") + words(EM / "methodology.md")
        refs = sorted((EM / "references").glob("*.md"))
        self.assertTrue(refs, "no references found; the ceiling would pass vacuously")
        for ref in refs:
            with self.subTest(reference=ref.name):
                self.assertLessEqual(base + words(ref), ROLE_LOAD_WORDS)

    def test_methodology_and_persona_code_is_at_most_2500_lines(self):
        lines = {s.name: non_test_lines(s) for s in (EM, AP)}
        self.assertTrue(all(lines.values()), lines)
        self.assertLessEqual(sum(lines.values()), CODE_LINES, lines)

    def test_at_most_five_persona_sources(self):
        sources = sorted((AP / "personas").glob("*.md"))
        self.assertTrue(sources)
        self.assertLessEqual(len(sources), PERSONA_SOURCES, [p.name for p in sources])


# AC-13 (owned by T9): progressive-disclosure loses at least half of its non-test code lines,
# measured with non_test_lines(SKILLS / "progressive-disclosure") against the number recorded before
# T9 starts. T9 adds that recorded number and its test here.


if __name__ == "__main__":
    unittest.main()
