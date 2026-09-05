#!/usr/bin/env python3
"""The README architecture diagram, and the three ways it can lie.

Run: python3 -m unittest tests.test_readme_diagram   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

WHY THIS FILE EXISTS. `readme-no-diagram` was satisfied by any `![...](...)` or `<img`. The
repository that ships this checker then embedded an exported PNG in its own architecture section
and left it there for 93 commits and one major version, while the picture said the work loop had
four steps and the loop had ten. The check passed on every one of those commits. That is the ninth
or tenth time in this toolchain that a WORD test stood in for a STRUCTURE that was not there, so
the tests below are written the other way round from the usual order:

  * FIXTURE tests state the contract on inputs built here.
  * CORPUS tests run the rules against THIS repository's own shipped README, and — the part that
    the inert checkers all lacked — mutate that real file in a scratch copy and require the rule to
    FIRE. A rule that only ever fires on a fixture is a rule with no evidence that it reaches the
    documents people actually write.

Nothing here writes inside the repository: every mutation happens in a temporary copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL / "scripts" / "validate_disclosure.py"
# Present when the skill is read from this repository, absent when it is installed under ~/.claude.
REPO_README = SKILL.parents[2] / "README.md"

DIAGRAM_RULES = ("readme-no-diagram", "readme-raster-diagram", "readme-diagram-drift",
                 "readme-architecture-image")


def findings(root: Path) -> list[dict]:
    """The README contract, as JSON, from the real CLI.

    A subprocess because the CLI is what a hook runs. `HOME` is redirected to an empty scratch
    directory for the same reason the sibling read-site suite does it: the validator stats
    `~/.claude/skills/`, and a suite whose result depends on what this machine has installed is
    not a suite.
    """
    home = Path(tempfile.mkdtemp(prefix="pd-diagram-home-"))
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(root), "--readme", "--json"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)
    if proc.returncode == 2:
        raise AssertionError(f"the validator could not run:\n{proc.stdout}{proc.stderr}")
    return json.loads(proc.stdout)["errors"]


def diagram_findings(root: Path) -> list[str]:
    return sorted(f["kind"] for f in findings(root) if f["kind"] in DIAGRAM_RULES)


ARCHITECTURE = """## Architecture

{figure}

| Stage | What happens |
|---|---|
| 1. Intake | A request arrives. |
| 2. Work | Something is built. |
"""


class FixtureMixin:
    """A README with every other section satisfied, so only the diagram rules can speak."""

    def repo(self, figure: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pd-diagram-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "AGENTS.md").write_text("# Contract\n\n[index](docs/agents/README.md)\n",
                                        encoding="utf-8")
        (root / "docs" / "agents" / "README.md").write_text(
            '# Index\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n',
            encoding="utf-8")
        (root / "README.md").write_text(
            "# Fixture\n\n## Overview\n\nWhat it is.\n\n## Current state\n\nShipping.\n\n"
            "## Product requirements\n\nNone yet.\n\n"
            + ARCHITECTURE.format(figure=figure)
            + "\n## Components\n\nOne.\n\n## Run locally\n\n`make`\n\n"
              "## Working in this repository\n\nRead AGENTS.md.\n",
            encoding="utf-8")
        return root

    def declared_image(self, *, embed: str = "markdown", marker_in_architecture: bool = True,
                       sha256: str | None = None, text: str = "The image shows intake flowing to work.",
                       image_path: str = "docs/assets/readme/architecture.png",
                       text_path: str = "docs/assets/readme/README.md") -> Path:
        root = self.repo("")
        image = root / image_path
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"reviewed architecture pixels")
        counterpart = root / text_path
        counterpart.parent.mkdir(parents=True, exist_ok=True)
        counterpart.write_text(text, encoding="utf-8")
        digest = sha256 or hashlib.sha256(image.read_bytes()).hexdigest()
        marker = "<!-- readme-architecture-image: " + json.dumps({
            "path": image_path, "sha256": digest, "text": text_path,
        }, separators=(",", ":")) + " -->"
        if embed == "markdown":
            figure = f"![Architecture]({image_path})"
        elif embed == "html":
            figure = f'<img src="{image_path}" alt="Architecture">'
        else:
            figure = embed
        readme = root / "README.md"
        content = readme.read_text(encoding="utf-8")
        if marker_in_architecture:
            content = content.replace("## Architecture\n\n", f"## Architecture\n\n{marker}\n{figure}\n", 1)
        else:
            content = marker + "\n" + content.replace("## Architecture\n\n",
                                                       f"## Architecture\n\n{figure}\n", 1)
        readme.write_text(content, encoding="utf-8")
        return root


class FixtureTest(FixtureMixin, unittest.TestCase):
    """What may stand as a diagram, and what may not."""

    FENCE = ('```mermaid\nflowchart LR\n    A["1. Intake"] --> B["2. Work"]\n```')

    def test_a_mermaid_fence_is_a_diagram(self) -> None:
        self.assertEqual([], diagram_findings(self.repo(self.FENCE)))

    def test_an_architecture_section_without_a_diagram_is_refused(self) -> None:
        self.assertEqual(["readme-no-diagram"], diagram_findings(self.repo("")))

    def test_an_exported_image_is_no_longer_a_diagram(self) -> None:
        """The exact defect: this input passed for 93 commits of the repository that ships it."""
        self.assertEqual(["readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(self.repo("![architecture](docs/assets/arch.png)")))

    def test_an_html_image_tag_does_not_get_a_second_door(self) -> None:
        self.assertEqual(["readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(self.repo('<img src="docs/assets/arch.webp" alt="a">')))

    def test_a_declared_reviewed_raster_with_text_counterpart_is_a_diagram(self) -> None:
        self.assertEqual([], diagram_findings(self.declared_image()))

    def test_a_declared_html_raster_is_also_accepted(self) -> None:
        self.assertEqual([], diagram_findings(self.declared_image(embed="html")))

    def test_declaration_must_be_inside_architecture_section(self) -> None:
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(self.declared_image(marker_in_architecture=False)))

    def test_declared_image_must_be_embedded_exactly(self) -> None:
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(self.declared_image(embed="![Other](other.png)")))

    def test_bad_declared_hash_fails_closed(self) -> None:
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(self.declared_image(sha256="0" * 64)))

    def test_missing_declared_image_fails_closed(self) -> None:
        root = self.declared_image()
        (root / "docs/assets/readme/architecture.png").unlink()
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(root))

    def test_empty_text_counterpart_fails_closed(self) -> None:
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(self.declared_image(text=" \n")))

    def test_duplicate_declarations_fail_even_with_mermaid(self) -> None:
        root = self.declared_image()
        readme = root / "README.md"
        marker = next(line for line in readme.read_text(encoding="utf-8").splitlines()
                      if "readme-architecture-image:" in line)
        content = readme.read_text(encoding="utf-8").replace(marker, marker + "\n" + marker)
        content = content.replace("## Components", self.FENCE + "\n\n## Components", 1)
        readme.write_text(content, encoding="utf-8")
        self.assertEqual(["readme-architecture-image", "readme-raster-diagram"],
                         diagram_findings(root))

    def test_malformed_declaration_fails_even_with_mermaid(self) -> None:
        root = self.repo('<!-- readme-architecture-image: {bad json} -->\n' + self.FENCE)
        self.assertEqual(["readme-architecture-image"], diagram_findings(root))

    def test_a_fenced_declaration_example_is_not_an_active_declaration(self) -> None:
        figure = (self.FENCE + '\n\n```markdown\n'
                  '<!-- readme-architecture-image: {bad json} -->\n```')
        self.assertEqual([], diagram_findings(self.repo(figure)))

    def test_declared_image_suffix_must_be_supported_raster(self) -> None:
        self.assertEqual(["readme-architecture-image", "readme-no-diagram"],
                         diagram_findings(self.declared_image(
                             image_path="docs/assets/readme/architecture.svg")))

    def test_missing_text_counterpart_fails_closed(self) -> None:
        root = self.declared_image()
        (root / "docs/assets/readme/README.md").unlink()
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(root))

    def test_undeclared_raster_beside_declared_one_is_still_refused(self) -> None:
        root = self.declared_image()
        readme = root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace(
            "![Architecture](docs/assets/readme/architecture.png)",
            "![Architecture](docs/assets/readme/architecture.png)\n![Other](other.png)", 1),
            encoding="utf-8")
        self.assertEqual(["readme-raster-diagram"], diagram_findings(root))

    def test_declared_paths_cannot_escape_repository_through_symlinks(self) -> None:
        root = self.declared_image()
        outside = Path(tempfile.mkdtemp(prefix="pd-diagram-outside-"))
        self.addCleanup(shutil.rmtree, outside, True)
        external = outside / "architecture.png"
        external.write_bytes(b"reviewed architecture pixels")
        image = root / "docs/assets/readme/architecture.png"
        image.unlink()
        image.symlink_to(external)
        self.assertEqual(["readme-architecture-image", "readme-no-diagram", "readme-raster-diagram"],
                         diagram_findings(root))

    def test_a_raster_beside_a_real_fence_is_still_a_raster(self) -> None:
        """A fence answers `readme-no-diagram`; it does not license pixels next to it, because the
        identifier guard reads the diff either way."""
        self.assertEqual(["readme-raster-diagram"],
                         diagram_findings(self.repo(self.FENCE + "\n\n![also](a/arch.png)")))

    def test_a_query_string_does_not_launder_the_suffix(self) -> None:
        self.assertIn("readme-raster-diagram",
                      diagram_findings(self.repo("![a](docs/arch.PNG?v=2)")))

    def test_a_box_the_section_never_mentions_is_drift(self) -> None:
        fence = '```mermaid\nflowchart LR\n    A["1. Intake"] --> B["2. Deploy"]\n```'
        self.assertEqual(["readme-diagram-drift"], diagram_findings(self.repo(fence)))

    def test_a_description_after_a_line_break_is_not_required_in_the_prose(self) -> None:
        """The box NAME is what the table has to agree with. A label carrying a description was
        compared whole, which demanded the literal `<br/>` appear in a sentence — unsatisfiable, so
        the only way to green was to strip the diagram or pad the prose. Both damage a correct
        README to quiet the matcher, which is the opposite of what the rule is for."""
        fence = ('```mermaid\nflowchart LR\n'
                 '    A["1. Intake<br/>within one working day"] --> B["2. Work"]\n```')
        self.assertEqual([], diagram_findings(self.repo(fence)))

    def test_a_description_after_a_spaced_em_dash_is_not_required_either(self) -> None:
        fence = ('```mermaid\nflowchart LR\n'
                 '    A["1. Intake — within one working day"] --> B["2. Work"]\n```')
        self.assertEqual([], diagram_findings(self.repo(fence)))

    def test_renaming_a_described_box_is_still_drift(self) -> None:
        """The tolerance above must not cost the rule its teeth: a description may say anything,
        but the name in front of it still has to be in the table."""
        fence = ('```mermaid\nflowchart LR\n'
                 '    A["1. Intake"] --> B["2. Deploy<br/>within one working day"]\n```')
        self.assertEqual(["readme-diagram-drift"], diagram_findings(self.repo(fence)))

    def test_a_label_that_is_nothing_but_a_separator_does_not_silence_the_rule(self) -> None:
        """An empty name would be `"" in rest`, which is always true — the rule would pass on a
        malformed box instead of failing on it. Going quiet on bad input is the worse failure."""
        fence = ('```mermaid\nflowchart LR\n'
                 '    A["<br/>unnamed"] --> B["2. Work"]\n```')
        self.assertEqual(["readme-diagram-drift"], diagram_findings(self.repo(fence)))

    def test_an_edge_label_is_not_required_to_appear_in_the_prose(self) -> None:
        """An edge says how two boxes relate. That sentence has no reason to be in the table, and
        requiring it there would make the rule noisy enough to be turned off."""
        fence = ('```mermaid\nflowchart LR\n'
                 '    A["1. Intake"] -- "rejected, with a reason" --> B["2. Work"]\n```')
        self.assertEqual([], diagram_findings(self.repo(fence)))

    def test_an_svg_is_accepted_because_it_is_text_a_diff_and_a_guard_can_read(self) -> None:
        """The rule is about raster, not about images as a category. An SVG diffs and its labels
        are characters the identifier guard scans, so it fails only the fence requirement."""
        self.assertEqual(["readme-no-diagram"],
                         diagram_findings(self.repo("![a](docs/assets/arch.svg)")))


@unittest.skipUnless(REPO_README.is_file(), "the skill is installed, not read from its repository")
class CorpusTest(unittest.TestCase):
    """The rules against the shipped README, including one mutation that must be caught.

    Every inert checker this session found passed its own fixtures. The difference between those
    and a rule that works is whether it has ever been fired by a change to a real document.
    """

    def repo_copy(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pd-diagram-corpus-"))
        self.addCleanup(shutil.rmtree, root, True)
        source = REPO_README.parent
        shutil.copytree(source, root / "repo",
                        ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        return root / "repo"

    def test_this_repository_satisfies_its_own_diagram_rules(self) -> None:
        self.assertEqual([], diagram_findings(self.repo_copy()))

    def test_changing_the_real_diagram_without_its_checked_counterpart_is_caught(self) -> None:
        root = self.repo_copy()
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        if "readme-architecture-image:" in text:
            match = re.search(
                r'<!--\s*readme-architecture-image:\s*(\{[^\r\n]*\})\s*-->', text)
            self.assertIsNotNone(match, "the real declaration is malformed")
            image = root / json.loads(match.group(1))["path"]
            image.write_bytes(image.read_bytes() + b"changed")
            self.assertEqual(["readme-architecture-image", "readme-no-diagram",
                              "readme-raster-diagram"], diagram_findings(root))
        else:
            self.assertIn("| 3. Harness layer |", text, "the stage table no longer has this row")
            readme.write_text(text.replace("| 3. Harness layer |", "| 3. Harness plane |"),
                              encoding="utf-8")
            self.assertEqual(["readme-diagram-drift"], diagram_findings(root))

    def test_putting_the_exported_image_back_is_refused(self) -> None:
        root = self.repo_copy()
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        marker = "## Architecture\n"
        self.assertIn(marker, text)
        readme.write_text(text.replace(
            marker, marker + "\n![architecture](docs/assets/undeclared-architecture.png)\n", 1),
            encoding="utf-8")
        self.assertEqual(["readme-raster-diagram"], diagram_findings(root))


if __name__ == "__main__":
    unittest.main()
