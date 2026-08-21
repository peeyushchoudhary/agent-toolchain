#!/usr/bin/env python3
"""Tests for the milestone scope of plan_waves.py — one wave plan across several feature plans.

Run: python3 -m unittest tests.test_plan_waves_milestone   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

THE POINT OF THE SCOPE, AND THEREFORE OF THIS FILE: task ids are plan-local, so a per-plan run
never compares one feature against another and the write collision BETWEEN two features is invisible
to it. Two things are pinned hardest here. The first is that `T1` in two features stays two tasks:
several tests would pass just as well against an implementation that fused them, so the ones that
would not — the qualified ids, and the wave that holds both features' T1 — are asserted explicitly.
The second is that a feature with NO `milestone:` key is not an error anywhere: it is the normal
state of most of a backlog, and a version that reports it would be switched off within a week.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "plan_waves.py"

sys.path.insert(0, str(SCRIPTS))

import plan_waves  # noqa: E402  — the path insertion above has to happen first

PRD = """---
title: A product
status: approved
updated: 2026-01-01
---

# A product
"""


def spec(ident: str, milestone: str | None = "M2") -> str:
    """A feature spec. `milestone=None` is the specified-and-waiting state, not a defect."""
    lines = ["---", f"id: {ident}", f"title: feature {ident}", "prd: docs/product/prd.md",
             "status: approved", "updated: 2026-01-01"]
    if milestone is not None:
        lines.append(f"milestone: {milestone}")
    lines += ["---", "", f"# {ident} — feature", ""]
    return "\n".join(lines)


def task(ident: str, needs: str = "", writes: str = "", covers: str = "[AC-1]",
         lane: str = "light") -> str:
    lines = [f"task: {ident}", f"title: work for {ident}", f"lane: {lane}"]
    if needs:
        lines.append(f"needs: {needs}")
    lines.append(f"writes: [{writes}]")
    lines.append(f"covers: {covers}")
    return "\n```task\n" + "\n".join(lines) + "\n```\n"


class MilestoneFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for part in ("specs", "plans", "milestones"):
            (self.root / "docs" / "product" / part).mkdir(parents=True)
        (self.root / "docs" / "product" / "prd.md").write_text(PRD, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def milestone(self, name: str = "M2", slug: str = "checkout", front: str | None = None) -> Path:
        path = self.root / "docs" / "product" / "milestones" / f"{name}-{slug}.md"
        head = front if front is not None else f"---\nmilestone: {name}\n"
        path.write_text(head + "title: the milestone\nstatus: building\nupdated: 2026-01-01\n"
                        f"---\n\n# {name} — the milestone\n", encoding="utf-8")
        return path

    def feature(self, ident: str, *blocks: str, milestone: str | None = "M2",
                slug: str = "thing") -> None:
        """A spec, and a plan for it when any task block is given."""
        (self.root / "docs" / "product" / "specs" / f"{ident}-{slug}.md").write_text(
            spec(ident, milestone), encoding="utf-8")
        if blocks:
            (self.root / "docs" / "product" / "plans" / f"{ident}-{slug}.md").write_text(
                f"---\nid: {ident}\n---\n\n# {ident} — plan\n" + "".join(blocks),
                encoding="utf-8")

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *extra],
                              capture_output=True, text=True)

    def report(self, name: str = "M2") -> dict:
        return json.loads(self.run_cli("--milestone", name, "--json").stdout)

    def result(self, name: str = "M2"):
        return plan_waves.run_milestone(self.root.resolve(), name)

    def rules(self, name: str = "M2") -> list[str]:
        findings, _ = self.result(name)
        return [item.rule for item in findings]

    def messages(self, rule: str, name: str = "M2") -> list[str]:
        findings, _ = self.result(name)
        return [item.message for item in findings if item.rule == rule]

    def waves(self, name: str = "M2") -> list[list[str]]:
        _, milestone = self.result(name)
        return milestone.waves if milestone else []

    def assertFinds(self, rule: str) -> None:
        found = self.rules()
        self.assertIn(rule, found, f"expected a {rule} finding, got {found}")

    def assertDoesNotFind(self, rule: str) -> None:
        found = self.rules()
        self.assertNotIn(rule, found, f"unexpected {rule} finding in {found}")


class ScopeTest(MilestoneFixture):
    def test_a_milestone_that_does_not_exist_exits_zero_and_says_nothing(self) -> None:
        """A repository that never adopted the layout is not a repository with a defect."""
        self.feature("F-11", task("T1", writes="a/**"))
        result = self.run_cli("--milestone", "M9")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_milestone_no_feature_has_joined_exits_zero_and_says_nothing(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"), milestone=None)
        result = self.run_cli("--milestone", "M2")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_repository_with_no_product_directory_at_all_is_silent(self) -> None:
        empty = Path(tempfile.mkdtemp())
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(empty),
                                 "--milestone", "M2"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_milestone_argument_that_is_not_an_id_is_a_usage_error(self) -> None:
        """Silence would read as `that milestone is clean`, which is the one thing it is not."""
        result = self.run_cli("--milestone", "2")
        self.assertEqual(result.returncode, 2)
        self.assertIn("M<number>", result.stderr)

    def test_the_milestone_run_writes_nothing(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="shared/**"))
        self.feature("F-12", task("T1", writes="shared/**"), slug="other")
        before = {path: path.stat().st_mtime_ns
                  for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(self.run_cli("--milestone", "M2").returncode, 1)
        after = {path: path.stat().st_mtime_ns
                 for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(before, after)


class MembershipTest(MilestoneFixture):
    def test_membership_derives_from_the_specs_and_not_from_a_list(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", writes="b/**"), slug="other")
        _, milestone = self.result()
        self.assertEqual(milestone.features, ["F-11", "F-12"])

    def test_a_feature_with_no_milestone_key_is_excluded_and_is_not_a_finding(self) -> None:
        """THE LOAD-BEARING TEST for the optional key: specified and waiting is a legitimate state
        for most of a backlog, and a version that reports it gets switched off."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", writes="a/**"), milestone=None, slug="other")
        findings, milestone = self.result()
        self.assertEqual(milestone.features, ["F-11"])
        self.assertEqual(list(findings), [])
        self.assertEqual(self.run_cli("--milestone", "M2").returncode, 0)

    def test_a_feature_with_no_milestone_key_is_not_a_finding_in_the_default_scope_either(self):
        self.milestone()
        self.feature("F-12", task("T1", writes="a/**"), milestone=None, slug="other")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_feature_in_another_milestone_is_excluded(self) -> None:
        self.milestone()
        self.milestone(name="M3", slug="later")
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", writes="a/**"), milestone="M3", slug="other")
        self.assertEqual(self.waves(), [["F-11/T1"]])
        self.assertEqual(self.waves("M3"), [["F-12/T1"]])

    def test_features_are_ordered_by_number_and_not_by_filename(self) -> None:
        self.milestone()
        for number in (2, 11, 3):
            self.feature(f"F-{number}", task("T1", writes=f"a{number}/**"), slug=f"s{number}")
        _, milestone = self.result()
        self.assertEqual(milestone.features, ["F-2", "F-3", "F-11"])

    def test_a_member_feature_with_no_plan_is_reported_and_is_not_a_finding(self) -> None:
        """A spec is approved before its plan is written. Failing that state would fire through the
        whole normal life of a milestone; omitting it silently would mislead the orchestrator."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", slug="other")
        findings, milestone = self.result()
        self.assertEqual(list(findings), [])
        self.assertEqual(milestone.unplanned, ["F-12"])
        self.assertEqual(milestone.features, ["F-11", "F-12"])
        self.assertIn("UNPLANNED", self.run_cli("--milestone", "M2").stdout)

    def test_two_documents_claiming_one_milestone_id_is_a_w6_finding(self) -> None:
        self.milestone(slug="checkout")
        self.milestone(slug="payments")
        self.feature("F-11", task("T1", writes="a/**"))
        self.assertFinds("W6")
        self.assertIn("also declared by", self.messages("W6")[0])

    def test_a_plan_with_no_matching_spec_is_not_in_any_milestone(self) -> None:
        self.milestone()
        (self.root / "docs" / "product" / "plans" / "F-99-orphan.md").write_text(
            "---\nid: F-99\n---\n\n# F-99\n" + task("T1", writes="a/**"), encoding="utf-8")
        self.feature("F-11", task("T1", writes="b/**"))
        self.assertEqual(self.waves(), [["F-11/T1"]])


class QualifiedIdTest(MilestoneFixture):
    def test_t1_in_two_features_stays_two_tasks_in_one_wave(self) -> None:
        """THE GAP THIS SCOPE CLOSES. One graph over plan-local ids would fuse both T1s into one
        node, and the wave plan would then describe a milestone nobody wrote."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="a2/**"))
        self.feature("F-12", task("T1", writes="b/**"), task("T2", needs="[T1]", writes="b2/**"),
                     slug="other")
        self.assertEqual(self.waves(), [["F-11/T1", "F-12/T1"], ["F-11/T2", "F-12/T2"]])

    def test_a_needs_edge_stays_plan_local_by_default(self) -> None:
        """`needs: [T1]` in F-12 orders F-12's T1, never F-11's, and no finding is raised for it."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", writes="b/**"), task("T2", needs="[T1]", writes="b2/**"),
                     slug="other")
        self.assertEqual(list(self.result()[0]), [])
        self.assertEqual(self.waves(), [["F-11/T1", "F-12/T1"], ["F-12/T2"]])

    def test_an_explicit_cross_feature_edge_orders_the_two_features(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="a2/**"))
        self.feature("F-12", task("T1", needs="[F-11/T2]", writes="b/**"), slug="other")
        self.assertEqual(list(self.result()[0]), [])
        self.assertEqual(self.waves(), [["F-11/T1"], ["F-11/T2"], ["F-12/T1"]])

    def test_a_cross_feature_edge_to_a_task_that_does_not_exist_is_w1(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", needs="[F-11/T9]", writes="b/**"), slug="other")
        self.assertFinds("W1")
        self.assertIn("`F-12/T1` needs `F-11/T9`", self.messages("W1")[0])
        self.assertIn("the milestone", self.messages("W1")[0])

    def test_a_cross_feature_edge_leaving_the_milestone_is_w6_and_is_named(self) -> None:
        """Named rather than dropped: the milestone claims to be dispatchable on its own and that
        edge says it is not."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", needs="[F-40/T2]", writes="b/**"), slug="other")
        self.assertFinds("W6")
        message = self.messages("W6")[0]
        self.assertIn("`F-12/T1` needs `F-40/T2`", message)
        self.assertIn("not in this milestone", message)

    def test_an_edge_leaving_the_milestone_does_not_stall_the_schedule(self) -> None:
        """A cycle and a broken edge need different repairs, so they must not look alike."""
        self.milestone()
        self.feature("F-11", task("T1", needs="[F-40/T2]", writes="a/**"))
        self.assertEqual(self.waves(), [["F-11/T1"]])
        self.assertDoesNotFind("W2")

    def test_a_cross_feature_edge_is_ignored_by_the_default_per_plan_scope(self) -> None:
        """The per-plan scope cannot resolve `F-11/T4` either way, and calling it dangling would
        make the default run unusable for any plan that has one."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", needs="[F-11/T1]", writes="b/**"), slug="other")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("W1", result.stdout)

    def test_a_cycle_that_closes_through_two_features_is_named_with_qualified_ids(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", needs="[F-12/T1]", writes="a/**"))
        self.feature("F-12", task("T1", needs="[F-11/T1]", writes="b/**"), slug="other")
        self.assertFinds("W2")
        self.assertIn("F-11/T1 -> F-12/T1 -> F-11/T1", self.messages("W2")[0])

    def test_task_level_findings_are_still_charged_to_the_right_plan_file(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", writes="b/**", covers="[]"), slug="other")
        findings, _ = self.result()
        self.assertEqual([(item.path, item.rule) for item in findings],
                         [("docs/product/plans/F-12-other.md", "W5")])


class CrossFeatureOverlapTest(MilestoneFixture):
    def test_w4_names_both_qualified_ids_and_the_shared_glob(self) -> None:
        """THE COLLISION THE PER-PLAN SCOPE CANNOT SEE: two features, same wave, one shared tree."""
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/shared/auth.py"))
        self.feature("F-12", task("T1", writes="backend/shared/**"), slug="other")
        self.assertFinds("W4")
        message = self.messages("W4")[0]
        for fragment in ("`F-11/T1`", "`F-12/T1`", "wave 1", "backend/shared/**",
                         "backend/shared/auth.py"):
            self.assertIn(fragment, message)

    def test_the_same_pair_is_clean_under_the_per_plan_scope(self) -> None:
        """The measurement that justifies the whole scope: run the two plans separately and the
        collision is not merely missed, it is reported as green."""
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/shared/auth.py"))
        self.feature("F-12", task("T1", writes="backend/shared/**"), slug="other")
        per_plan, _ = plan_waves.run(self.root.resolve())
        self.assertEqual(list(per_plan), [])
        self.assertEqual(self.rules(), ["W4"])

    def test_w4_does_not_serialise_the_cross_feature_pair_it_reports(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/shared/auth.py"))
        self.feature("F-12", task("T1", writes="backend/shared/**"), slug="other")
        self.assertEqual(self.waves(), [["F-11/T1", "F-12/T1"]])

    def test_w4_is_silent_when_a_cross_feature_edge_separates_the_pair(self) -> None:
        """The explicit edge IS the planner owning the serialisation, and it is accepted."""
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/shared/auth.py"))
        self.feature("F-12", task("T1", needs="[F-11/T1]", writes="backend/shared/**"),
                     slug="other")
        self.assertDoesNotFind("W4")

    def test_w4_is_silent_when_two_features_write_disjoint_trees(self) -> None:
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/a/**"))
        self.feature("F-12", task("T1", writes="backend/b/**"), slug="other")
        self.assertDoesNotFind("W4")

    def test_w4_still_decides_overlap_without_the_files_existing(self) -> None:
        self.assertFalse((self.root / "backend").exists())
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/**"))
        self.feature("F-12", task("T1", writes="backend/db/V1__init.sql"), slug="other")
        self.assertFinds("W4")

    def test_a_feature_outside_the_milestone_cannot_raise_w4_against_a_member(self) -> None:
        """The milestone is what dispatches together, so it is the boundary of the check."""
        self.milestone()
        self.feature("F-11", task("T1", writes="backend/shared/**"))
        self.feature("F-12", task("T1", writes="backend/shared/**"), milestone=None, slug="other")
        self.assertDoesNotFind("W4")


class JsonTest(MilestoneFixture):
    def setUp(self) -> None:
        super().setUp()
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**", covers="[AC-1, AC-2]", lane="full"),
                     task("T2", needs="[T1]", writes="a2/**"))
        self.feature("F-12", task("T1", needs="[F-11/T1]", writes="b/**"), slug="other")
        self.feature("F-13", slug="third")

    def test_waves_are_lists_of_qualified_ids_and_nothing_else(self) -> None:
        """The dispatch interface: an orchestrator sends `waves[n]`, and parses nothing to do it."""
        report = self.report()
        self.assertEqual(report["waves"], [["F-11/T1"], ["F-11/T2", "F-12/T1"]])
        self.assertEqual(report["exit"], 0)
        self.assertEqual(report["milestone"], "M2")
        self.assertEqual(report["path"], "docs/product/milestones/M2-checkout.md")

    def test_every_id_in_a_wave_resolves_in_the_task_map(self) -> None:
        report = self.report()
        for wave in report["waves"]:
            for ident in wave:
                self.assertIn(ident, report["tasks"])

    def test_a_task_carries_the_lane_the_writes_and_the_covers(self) -> None:
        entry = self.report()["tasks"]["F-11/T1"]
        self.assertEqual(entry["lane"], "full")
        self.assertEqual(entry["writes"], ["a/**"])
        self.assertEqual(entry["covers"], ["AC-1", "AC-2"])
        self.assertEqual(entry["feature"], "F-11")
        self.assertEqual(entry["plan"], "docs/product/plans/F-11-thing.md")

    def test_needs_are_reported_qualified_so_no_consumer_re_resolves_them(self) -> None:
        report = self.report()
        self.assertEqual(report["tasks"]["F-11/T2"]["needs"], ["F-11/T1"])
        self.assertEqual(report["tasks"]["F-12/T1"]["needs"], ["F-11/T1"])

    def test_the_features_and_the_unplanned_features_are_both_carried(self) -> None:
        report = self.report()
        self.assertEqual(report["features"], ["F-11", "F-12", "F-13"])
        self.assertEqual(report["unplanned"], ["F-13"])
        self.assertEqual(report["unscheduled"], [])

    def test_an_absent_milestone_is_still_valid_json_a_consumer_can_read(self) -> None:
        """A machine interface that answers an empty milestone with an empty stdout makes every
        consumer handle a parse error instead of a documented shape."""
        result = self.run_cli("--milestone", "M9", "--json")
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["waves"], [])
        self.assertEqual(report["tasks"], {})
        self.assertIsNone(report["milestone"])

    def test_findings_exit_one_and_the_wave_plan_still_prints(self) -> None:
        self.feature("F-14", task("T1", writes="a/**"), slug="fourth")
        result = self.run_cli("--milestone", "M2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("W4", result.stdout)
        self.assertIn("wave 1  width 2  F-11/T1, F-14/T1", result.stdout)

    def test_the_printed_plan_names_the_features_each_wave_represents(self) -> None:
        """Wave width alone does not say whether the parallelism is inside one feature or across
        three, and only the second kind is what a milestone is dispatched for."""
        stdout = self.run_cli("--milestone", "M2").stdout
        self.assertIn("wave 2  width 2  F-11/T2, F-12/T1   [F-11, F-12]", stdout)
        self.assertIn("milestone M2  3 feature(s), 3 task(s), 2 wave(s)", stdout)


class ScaleTest(MilestoneFixture):
    def test_five_features_of_ten_tasks_schedule_in_well_under_a_second(self) -> None:
        """O(n^2) pairwise over the merged write sets is the cost model. Merging five features
        squares a bigger n than any single plan reaches, which is the number worth pinning."""
        self.milestone()
        for feature in range(11, 16):
            blocks = [task("T1", writes=f"svc{feature}/a/**")]
            blocks += [task(f"T{n}", needs=f"[T{n - 1}]" if n % 3 == 0 else "[T1]",
                            writes=f"svc{feature}/m{n}/**") for n in range(2, 11)]
            self.feature(f"F-{feature}", *blocks, slug=f"s{feature}")
        start = time.perf_counter()
        findings, milestone = self.result()
        elapsed = time.perf_counter() - start
        self.assertEqual(list(findings), [])
        self.assertEqual(len(milestone.tasks), 50)
        self.assertEqual(sum(len(wave) for wave in milestone.waves), 50)
        self.assertEqual(len(milestone.waves), 3)
        self.assertLess(elapsed, 1.0)

    def test_a_shared_module_across_five_features_is_found_only_by_the_merged_graph(self) -> None:
        """The justification for the scope, as a number: every one of these features is clean on
        its own, and the pairs only exist once the graphs are merged."""
        self.milestone()
        for feature in range(11, 16):
            blocks = [task("T1", writes="backend/shared/**")]
            blocks += [task(f"T{n}", needs="[T1]", writes=f"svc{feature}/m{n}/**")
                       for n in range(2, 11)]
            self.feature(f"F-{feature}", *blocks, slug=f"s{feature}")
        per_plan, _ = plan_waves.run(self.root.resolve())
        self.assertEqual(list(per_plan), [])
        merged = self.messages("W4")
        self.assertEqual(len(merged), 10)          # every pair of the five features' T1


if __name__ == "__main__":
    unittest.main()
