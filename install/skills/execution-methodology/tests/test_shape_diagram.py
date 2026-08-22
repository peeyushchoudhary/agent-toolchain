#!/usr/bin/env python3
"""The pipeline diagram at the head of SKILL.md, against the file it summarises.

Run: python3 -m unittest tests.test_shape_diagram   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

WHY THIS FILE EXISTS. "The shape, in one screen" was an ASCII pipeline in a plain fence for the
whole life of this skill, and nothing read it. Measured before it was replaced: four of its terms --
budgeted review, full-diff review, sealed receipt, process metrics -- appeared NOWHERE ELSE in
SKILL.md. A drawing had quietly become a second vocabulary for the same pipeline, with no owner and
no check, which is the same failure as the architecture PNG this repository shipped in its README
and left wrong for 93 commits. The picture was not lying yet. Nothing would have said so if it had.

What is pinned, and why each part is worth a rule:

  * Every EDGE LABEL that ends in `.py` is the instrument that binds that stage transition, so it
    must be a script in `scripts/`. A diagram that names a tool nobody ships is worse than no
    diagram: it is a claim of enforcement.
  * Every NODE LABEL must be said somewhere in SKILL.md OUTSIDE the fence. This is the rule that
    catches the failure actually measured above -- a box whose words exist only inside the box.
  * The GATES are counted against the prose sentence that states how many there are, and each gate
    is named after one of the three that sentence names. The three human gates are the load-bearing
    claim of this methodology; a fourth appearing in a picture would be a change of policy made by
    a drawing.

`diagram_problems` is one implementation with two callers: the shipped file must produce none, and
`ShapeDriftTest` mutates that same shipped file in memory and requires each mutation to produce its
kind. Nothing is written to disk.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
SKILL_MD = SKILL / "SKILL.md"

MERMAID_FENCE = re.compile(r"^```mermaid\s*$(.*?)^```\s*$", re.DOTALL | re.MULTILINE)
# Any of Mermaid's shape brackets, single or doubled: ["a"], {{"a"}}, ("a"), >"a"].
NODE_LABEL = re.compile(r"[\[({>]{1,2}\s*\"([^\"]+)\"\s*[\])}]{1,2}")
EDGE_LABEL = re.compile(r"--\s*\"([^\"]+)\"\s*--?>")
# "Three human gates: the design, the plan, and the merge." The count and the names, in one place.
GATE_SENTENCE = re.compile(r"Three human gates:([^.]*)\.")
GATE_NODE = re.compile(r"^gate\s*[-—:]\s*(.+)$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def diagram_problems(text: str) -> list[str]:
    """Every way the pipeline fence can disagree with SKILL.md, as `kind: detail`."""
    problems: list[str] = []
    fence = MERMAID_FENCE.search(text)
    if fence is None:
        return ["no-diagram: SKILL.md no longer opens with a ```mermaid pipeline"]
    body = fence.group(1)
    outside = text[:fence.start()] + text[fence.end():]

    for label in EDGE_LABEL.findall(body):
        for token in label.split():
            if token.endswith(".py") and not (SCRIPTS / token).is_file():
                problems.append(f"no-such-script: an edge names {token}, which is not in "
                                f"{SCRIPTS.name}/")

    gates = []
    for label in NODE_LABEL.findall(body):
        gate = GATE_NODE.match(label.strip())
        if gate:
            gates.append(gate.group(1).strip())
        elif label.casefold() not in outside.casefold():
            problems.append(f"invented-box: {label!r} is said nowhere else in SKILL.md")

    sentence = GATE_SENTENCE.search(outside)
    if sentence is None:
        problems.append("no-gate-sentence: SKILL.md no longer states its three human gates")
        return problems
    if len(gates) != 3:
        problems.append(f"gate-count: the diagram draws {len(gates)} gates, the text says three")
    for gate in gates:
        if gate.casefold() not in sentence.group(1).casefold():
            problems.append(f"gate-drift: the diagram draws a {gate!r} gate that the three-gates "
                            "sentence does not name")
    if re.search(r"!\[[^\]]*\]\([^)]+\.(png|jpe?g|gif|webp|bmp|avif)", text):
        problems.append("raster: an exported image is back in a document the guard cannot read")
    return problems


class ShapeDiagramTest(unittest.TestCase):
    """The shipped SKILL.md."""

    def setUp(self) -> None:
        self.text = read(SKILL_MD)

    def test_the_skill_opens_with_a_mermaid_pipeline(self) -> None:
        """The guard on everything below: an absent fence satisfies every loop over it."""
        self.assertTrue(MERMAID_FENCE.search(self.text), "SKILL.md holds no ```mermaid fence")

    def test_the_pipeline_says_only_what_the_skill_says(self) -> None:
        self.assertEqual([], diagram_problems(self.text))

    def test_the_per_task_loop_is_drawn_once_and_it_is_not_here(self) -> None:
        """Two drawings of one loop is the duplication this whole change is against."""
        fence = MERMAID_FENCE.search(self.text)
        self.assertIsNotNone(fence)
        for step in ("resume", "dispatch", "deferrals", "coverage"):
            self.assertNotIn(step, fence.group(1),
                             f"the pipeline redraws {step}; that belongs to execution-loop.md")
        self.assertIn("references/execution-loop.md", self.text)


class ShapeDriftTest(unittest.TestCase):
    """Each way the pipeline can go false, applied to the shipped file, in memory."""

    def setUp(self) -> None:
        self.text = read(SKILL_MD)

    def assert_fires(self, kind: str, mutated: str) -> None:
        problems = diagram_problems(mutated)
        self.assertTrue(any(p.startswith(kind) for p in problems),
                        f"mutating SKILL.md produced {problems!r}, no {kind}")

    def test_an_instrument_that_does_not_ship_is_caught(self) -> None:
        self.assert_fires("no-such-script",
                          self.text.replace('"validate_card.py"', '"validate_cards.py"', 1))

    def test_a_box_whose_words_exist_only_in_the_box_is_caught(self) -> None:
        """The exact defect measured in the ASCII pipeline this replaced."""
        self.assert_fires("invented-box", self.text.replace('COMMIT["commit"]',
                                                            'COMMIT["sealed receipt"]', 1))

    def test_a_fourth_gate_drawn_into_the_picture_is_caught(self) -> None:
        """Three human gates is policy. A drawing does not get to add one."""
        self.assert_fires("gate-count",
                          self.text.replace('    G3 --> PR["PR"]',
                                            '    G3 --> G4{{"gate — release"}}\n    G4 --> PR["PR"]',
                                            1))

    def test_renaming_a_gate_in_the_diagram_alone_is_caught(self) -> None:
        self.assert_fires("gate-drift", self.text.replace('{{"gate — merge"}}',
                                                          '{{"gate — release"}}', 1))

    def test_dropping_the_three_gates_sentence_is_caught(self) -> None:
        self.assert_fires("no-gate-sentence", self.text.replace("Three human gates:",
                                                                "Some human gates:", 1))

    def test_putting_an_exported_image_back_is_caught(self) -> None:
        self.assert_fires("raster", self.text + "\n![the shape](assets/shape.png)\n")

    def test_deleting_the_fence_is_caught(self) -> None:
        self.assert_fires("no-diagram", MERMAID_FENCE.sub("", self.text, count=1))


if __name__ == "__main__":
    unittest.main()
