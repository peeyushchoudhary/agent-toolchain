"""Behaviour-level facts about the skill's rules: routes resolve and ceilings hold.

No prose is pinned here. The tests check that every path the rules name exists (or is a named
later deliverable), that the word ceilings of F-3 AC-9 hold for every role route, and that no routed
file points at a retired reference.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[2]
REFS = SKILL / "references"

# The route: the entry file, the shared core, and one reference per role.
ENTRY = SKILL / "SKILL.md"
CORE = SKILL / "methodology.md"
ROLE_REFERENCES = ("planning.md", "run.md", "migrate.md")
ROUTED = [ENTRY, CORE] + [REFS / name for name in ROLE_REFERENCES]

# Deliverables of a later task that the rules already name. Anything else must exist.
NOT_YET_BUILT: frozenset = frozenset()

RETIRED = ("execution-loop.md", "task-card.md", "specs.md", "junit-evidence.md",
           "codex-gate-sandbox.md", "readme.md", "changelog-v1-v2.md", "history-v3-v5.md")

CORE_CEILING = 1500
ROUTE_CEILING = 3000

LINK = re.compile(r"\]\(([^)\s]+)\)")
SKILL_PATH = re.compile(r"(?<![\w-])((?:scripts|references)/[\w.-]+\.(?:py|md|html|sh|json|yaml))")
REPO_PATH = re.compile(r"(?<![\w/.-])(install/[\w./-]+\.(?:py|md|html|sh|json|yaml))")


def words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split())


def named_paths(path: Path, text: str | None = None):
    """(label, resolved path) for every link and skill- or repo-relative path a rules file names."""
    text = path.read_text(encoding="utf-8") if text is None else text
    out = []
    for target in LINK.findall(text):
        target = target.split("#", 1)[0]
        if not target or re.match(r"^[a-z]+:", target):
            continue
        resolved = (path.parent / target).resolve()
        out.append((resolved.relative_to(SKILL).as_posix() if SKILL in resolved.parents else target,
                    resolved))
    out += [(m, SKILL / m) for m in SKILL_PATH.findall(text)]
    out += [(m, REPO / m) for m in REPO_PATH.findall(text)]
    return out


class RoutesResolve(unittest.TestCase):
    def test_every_routed_file_exists(self):
        for path in ROUTED:
            self.assertTrue(path.is_file(), path)

    def test_every_named_path_resolves_or_is_a_named_later_deliverable(self):
        for path in ROUTED:
            for label, resolved in named_paths(path):
                with self.subTest(file=path.name, named=label):
                    self.assertTrue(resolved.exists() or label in NOT_YET_BUILT,
                                    f"{path.name} names {label}, which does not exist")

    def test_the_entry_routes_to_the_core_and_every_role_reference(self):
        linked = {resolved for _label, resolved in named_paths(ENTRY)}
        for target in [CORE] + [REFS / name for name in ROLE_REFERENCES]:
            self.assertIn(target.resolve(), linked, f"SKILL.md does not route to {target.name}")

    def test_the_path_detector_sees_a_missing_path(self):
        # Guard the guard: a file naming a missing reference must be reported, not skipped.
        text = "[x](does-not-exist.md), [ok](run.md) and `scripts/nope.py`\n"
        missing = [label for label, resolved in named_paths(REFS / "probe.md", text)
                   if not resolved.exists()]
        self.assertEqual(sorted(missing), ["references/does-not-exist.md", "scripts/nope.py"])


class WordCeilings(unittest.TestCase):
    def test_core_is_within_its_ceiling(self):
        self.assertLessEqual(words(CORE), CORE_CEILING)

    def test_every_role_route_is_within_its_ceiling(self):
        shared = words(ENTRY) + words(CORE)
        for name in ROLE_REFERENCES:
            with self.subTest(reference=name):
                self.assertLessEqual(shared + words(REFS / name), ROUTE_CEILING)


class NoRetiredReferences(unittest.TestCase):
    def test_no_routed_file_names_a_retired_reference(self):
        for path in ROUTED:
            text = path.read_text(encoding="utf-8")
            for name in RETIRED:
                with self.subTest(file=path.name, retired=name):
                    self.assertIsNone(re.search(r"(?<![\w-])" + re.escape(name), text),
                                      f"{path.name} names retired {name}")


if __name__ == "__main__":
    unittest.main()
