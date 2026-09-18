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
SPECS = ROOT / "references" / "specs.md"


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

    def test_review_width_is_one_reviewer_with_conditional_owners(self) -> None:
        current = "\n".join((self.current, read(SPECS))).lower()
        for phrase in ("one semantic `reviewer`", "at most one relevant specialist",
                       "`security-validator`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, current)
        for stale in ("up to three reviewers", "divergent panel", "may use distinct lenses"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, current)

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

    def test_direct_common_route_preserves_approved_runtime_authority(self) -> None:
        method = " ".join(self.methodology.split())
        for phrase in (
            "including an older approved bundle",
            "A newer global source or candidate never replaces that binding",
            "do not fall back to global source",
            "Governed adopted execution requires `state=current` and `ready=true`",
            "Ordinary execution does not invoke maintenance, model research or upgrades",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, method)

    def test_successful_gate_evidence_is_reused_until_it_is_invalidated(self) -> None:
        method = " ".join(self.methodology.split())
        self.assertIn("Repeat a gate only when its referent or inputs change", method)
        self.assertIn("a run fails, or prior evidence becomes invalid", method)
        self.assertIn("Record the reason for every repeat", method)
        self.assertIn("reuse a still-valid successful result", method)
        self.assertIn("repeating an unchanged successful check adds no evidence", method)

    def test_planning_starts_from_existing_production_paths_and_executable_proof(self) -> None:
        method = " ".join(self.methodology.split())
        for phrase in (
            "required outcome",
            "existing production path",
            "existing executable proof",
            "actual uncovered gap",
            "smallest sufficient addition",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, method)
        self.assertIn("A new parser, protocol, registry, or recovery subsystem", method)
        self.assertIn("justify a specific uncovered gap", method)

    def test_plan_inventories_consumers_companions_and_dependency_states(self) -> None:
        method = " ".join(self.methodology.split())
        for phrase in (
            "actual consumers",
            "fixtures and generated companions",
            "prerequisite states",
            "staging, acceptance, and activation",
            "successor task is already accepted",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, method)

    def test_gate_two_approves_bounded_milestone_authority_and_resources(self) -> None:
        method = " ".join(self.methodology.split())
        for phrase in (
            "whole bounded milestone execution",
            "permitted operations",
            "routine recovery",
            "resource envelope",
            "local commit authority",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, method)
        self.assertIn("does not weaken any safety, review, evidence, or acceptance stop", method)
        self.assertIn("no deployment, provider activation, production write, push, PR, or merge", method)

    def test_task_commit_requires_explicit_gate_two_authority_or_pauses(self) -> None:
        method = " ".join(self.methodology.split()).lower()
        self.assertIn("only when gate 2 explicitly grants local commit authority", method)
        self.assertIn("checkpoint and pause before any further selection", method)

    def test_ordinary_resource_envelope_is_bounded_and_quality_preserving(self) -> None:
        method = " ".join(self.methodology.split()).lower()
        for phrase in (
            "up to six elapsed hours",
            "at most two file-disjoint builders",
            "one heavy local gate at a time",
            "unless gate 2 records another envelope",
            "budget exhaustion is a pause boundary",
            "never weakens quality",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, method)

    def test_weekly_and_ad_hoc_observation_has_one_owner_and_no_approval_power(self) -> None:
        method = " ".join(self.methodology.split())
        for phrase in (
            "weekly and ad hoc observation",
            "`chief-of-staff` owns collection, classification, and persistence",
            "methodology-management/references/assessment.md",
            "~/.claude/docs/LEDGER.md",
            "accepted outcomes with exact Git, task, trace, seal, and acceptance referents",
            "noncached input, cache reads, cache writes, and output as separate units",
            "actual cash or allowance evidence in its native unit",
            "coverage and missing logs",
            "founder, quota, and gate waits",
            "interruptions and rework classified by cause",
            "Absent or unattributable data stays explicitly unknown",
            "Observation records facts; it does not approve policy, model, or runtime changes",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, method)


if __name__ == "__main__":
    unittest.main()
