"""Behaviour-level facts about the skill's rules: routes resolve, ceilings hold, the template works.

No prose is pinned here. The tests check that every path the rules name exists (or is a named
later deliverable), that the word ceilings of F-3 AC-9 hold for every role route, that no routed
file points at a retired reference, and that the explainer template is self-contained and driven
by one JSON block.
"""
from __future__ import annotations

import html.parser
import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[2]
REFS = SKILL / "references"

# The route: the entry file, the shared core, and one reference per role.
ENTRY = SKILL / "SKILL.md"
CORE = SKILL / "methodology.md"
ROLE_REFERENCES = ("planning.md", "run.md", "review.md", "escalation.md", "migrate.md")
TEMPLATE = REFS / "explainer-template.html"
ROUTED = [ENTRY, CORE] + [REFS / name for name in ROLE_REFERENCES]

# Deliverables of a later task (T4) that the rules already name. Anything else must exist.
NOT_YET_BUILT = frozenset({
    "scripts/review.py",
    "scripts/run_goal.py",
    "install/hooks/goal-session.sh",
})

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
        for path in ROUTED + [TEMPLATE]:
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
        for path in ROUTED + [TEMPLATE, SKILL / "agents" / "openai.yaml"]:
            text = path.read_text(encoding="utf-8")
            for name in RETIRED:
                with self.subTest(file=path.name, retired=name):
                    self.assertIsNone(re.search(r"(?<![\w-])" + re.escape(name), text),
                                      f"{path.name} names retired {name}")


class _Scan(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.data_blocks, self.urls, self.current = [], [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("src", "href", "action", "poster", "data"):
            if attrs.get(key):
                self.urls.append(attrs[key])
        if tag == "script" and attrs.get("id") == "goal-data":
            self.current = {"type": attrs.get("type"), "text": ""}
        if tag not in ("meta", "link", "br", "img", "input", "hr"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.current is not None and tag == "script":
            self.data_blocks.append(self.current)
            self.current = None
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data


class ExplainerTemplate(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")
        self.scan = _Scan()
        self.scan.feed(self.text)
        self.scan.close()

    def test_parses_with_balanced_elements(self):
        self.assertEqual(self.scan.stack, [], "unclosed elements")

    def test_exactly_one_goal_data_block_that_parses_as_json(self):
        self.assertEqual(len(self.scan.data_blocks), 1)
        block = self.scan.data_blocks[0]
        self.assertEqual(block["type"], "application/json")
        data = json.loads(block["text"])
        self.assertIn("approval", data)
        self.assertIn("merge", data)

    def test_references_no_network_resource(self):
        self.assertEqual([u for u in self.scan.urls if re.match(r"^(https?:)?//", u)], [])
        self.assertIsNone(re.search(r"https?://", self.text))
        self.assertIsNone(re.search(r"@import|url\(\s*['\"]?(https?:)?//", self.text))


if __name__ == "__main__":
    unittest.main()
