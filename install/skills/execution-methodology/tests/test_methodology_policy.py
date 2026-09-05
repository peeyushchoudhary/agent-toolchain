#!/usr/bin/env python3
"""Regression pins for the current execution policy shared by the route and loop."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METHODOLOGY = ROOT / "methodology.md"
SKILL = ROOT / "SKILL.md"
LOOP = ROOT / "references" / "execution-loop.md"
HISTORY = ROOT / "references" / "history-v3-v5.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class CurrentPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.methodology = read(METHODOLOGY)
        self.skill = read(SKILL)
        self.loop = read(LOOP)
        self.current = "\n".join((self.methodology, self.skill, self.loop))

    def test_both_lanes_require_plan_identity_lane_writes_and_criteria(self) -> None:
        for phrase in ("existing plan task id", "explicit `lane:`", "non-empty `writes:`",
                       "acceptance criteria"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.current)
        self.assertIn("Light lane", self.loop)
        self.assertIn("Full lane", self.loop)

    def test_review_is_one_full_diff_then_one_scoped_correction_review(self) -> None:
        for phrase in ("one initial full task-diff review", "one scoped correction review",
                       "independent executable confirmation"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.current)
        self.assertNotIn("five rounds", self.current.lower())
        self.assertNotIn("routed by score", self.current.lower())

    def test_unresolved_semantic_findings_never_become_ready_automatically(self) -> None:
        self.assertIn("unresolved semantic", self.current)
        self.assertIn("INCOMPLETE", self.current)
        self.assertNotIn("applies the final verdict's named smallest correction", self.current)

    def test_controller_state_and_append_only_decisions_are_separate(self) -> None:
        loop = self.loop.lower()
        self.assertIn("bounded controller state", loop)
        self.assertIn("append-only decisions", loop)
        self.assertIn("current resume pointers", loop)

    def test_history_is_labelled_and_removed_from_the_current_method(self) -> None:
        history = read(HISTORY)
        self.assertIn("# Historical methodology rationale", history)
        self.assertIn("not current authority", history.lower().replace("\n", " "))
        self.assertNotIn("## What changed, and what earned it", self.methodology)

    def test_skill_is_a_short_route_to_the_canonical_method_and_loop(self) -> None:
        self.assertLessEqual(len(self.skill.splitlines()), 240)
        self.assertIn("methodology.md", self.skill)
        self.assertIn("references/execution-loop.md", self.skill)

    def test_successful_gate_evidence_is_reused_until_it_is_invalidated(self) -> None:
        method = " ".join(self.methodology.split())
        self.assertIn("Repeat a gate only when its referent or inputs change", method)
        self.assertIn("a run fails, or prior evidence becomes invalid", method)
        self.assertIn("Record the reason for every repeat", method)
        self.assertIn("reuse a still-valid successful result", method)
        self.assertIn("repeating an unchanged successful check adds no evidence", method)


if __name__ == "__main__":
    unittest.main()
