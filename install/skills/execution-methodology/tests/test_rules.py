"""Behaviour-level facts about the skill's prose: the files exist, what they name exists, nothing
retired is named, and the reviewer cannot edit.

No prose is pinned here; the word ceiling is install/tests/test_size.py.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[2]
ENTRY = SKILL / "SKILL.md"
REVIEWER = SKILL / "agents" / "reviewer.md"
DESIGN = SKILL / "references" / "design.md"
ALWAYS_LOADED = (REPO / "install" / "global.md", REPO / "AGENTS.md", ENTRY)
SKILL_FILES = (ENTRY, REVIEWER, DESIGN)

# Named by the rules, delivered by a later task of the same goal. Anything else must exist.
NOT_YET_BUILT = frozenset({"agents/builder.md"})

# Machinery the v7 shape removed (D29). The rules must not send a session to any of it.
RETIRED = ("execution-methodology/methodology.md", "references/run.md", "references/planning.md",
           "references/migrate.md", "agent-personas", "sync_personas", "review.py", "run_goal",
           "goal-session", "graphify", "graph-navigation", "progressive-disclosure",
           "validate_disclosure", "check_github", "install_hooks", "identifier_guard", "push_guard",
           "preflight", "goal.py guard", "goal.py attempt", "goal.py evidence", "goal.py start")

LINK = re.compile(r"\]\(([^)\s]+)\)")
SKILL_PATH = re.compile(r"(?<![\w/.-])((?:scripts|references|agents)/[\w.-]+\.(?:py|md|sh))")


def named_paths(path: Path, text: str | None = None) -> list[tuple[str, Path]]:
    """(label, resolved path) for every relative link and skill-relative path a file names."""
    text = path.read_text(encoding="utf-8") if text is None else text
    out = []
    for target in LINK.findall(text):
        target = target.split("#", 1)[0]
        if target and not re.match(r"^[a-z]+:", target):
            resolved = (path.parent / target).resolve()
            label = resolved.relative_to(SKILL).as_posix() if SKILL in resolved.parents else target
            out.append((label, resolved))
    return out + [(m, SKILL / m) for m in SKILL_PATH.findall(text)]


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = lines.index("---", 1)
    return dict(l.split(":", 1) for l in lines[1:end] if ":" in l)


class FilesAndNames(unittest.TestCase):
    def test_the_always_loaded_files_and_the_skill_files_exist(self):
        for path in ALWAYS_LOADED + SKILL_FILES:
            self.assertTrue(path.is_file(), path)

    def test_every_path_the_skill_names_resolves(self):
        for path in SKILL_FILES:
            for label, resolved in named_paths(path):
                with self.subTest(file=path.name, named=label):
                    self.assertTrue(resolved.exists() or label in NOT_YET_BUILT,
                                    f"{path.name} names {label}, which does not exist")

    def test_the_entry_links_the_reviewer_and_the_design_page(self):
        linked = {resolved for _label, resolved in named_paths(ENTRY)}
        self.assertLessEqual({REVIEWER.resolve(), DESIGN.resolve()}, linked)

    def test_the_path_detector_sees_a_missing_path(self):
        # Guard the guard: a file naming a missing path must be reported, not skipped.
        text = "[x](does-not-exist.md), [ok](design.md) and `scripts/nope.py`\n"
        missing = [label for label, resolved in named_paths(DESIGN, text) if not resolved.exists()]
        self.assertEqual(sorted(missing), ["references/does-not-exist.md", "scripts/nope.py"])

    def test_no_always_loaded_or_skill_file_names_retired_machinery(self):
        for path in ALWAYS_LOADED + SKILL_FILES:
            text = path.read_text(encoding="utf-8")
            for name in RETIRED:
                with self.subTest(file=path.name, retired=name):
                    self.assertIsNone(re.search(r"(?<![\w-])" + re.escape(name), text),
                                      f"{path.name} names retired {name}")


class Frontmatter(unittest.TestCase):
    def test_the_skill_is_never_invoked_by_the_model_on_its_own(self):
        meta = frontmatter(ENTRY)
        self.assertEqual(meta.get("name", "").strip(), "execution-methodology")
        self.assertTrue(meta.get("description", "").strip())
        self.assertEqual(meta.get("disable-model-invocation", "").strip(), "true")

    def test_the_reviewer_is_read_only(self):
        tools = {t.strip() for t in frontmatter(REVIEWER).get("tools", "").split(",") if t.strip()}
        self.assertTrue(tools)
        self.assertLessEqual(tools, {"Read", "Grep", "Glob"}, tools)


if __name__ == "__main__":
    unittest.main()
