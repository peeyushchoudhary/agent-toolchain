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


def spec(ident: str, milestone: str | None = "M2", tags: dict | None = None) -> str:
    """A feature spec. `milestone=None` is the specified-and-waiting state, not a defect.

    `tags` writes acceptance criteria and marks them: `{2: "P1", 3: ""}`. The criteria are WRAPPED
    over two lines, as the real corpus writes them, so the optional `[P1]` tag lands on a line
    carrying no `AC-<n>` at all — a reader that took one line at a time would find nothing here.
    """
    lines = ["---", f"id: {ident}", f"title: feature {ident}", "prd: docs/product/prd.md",
             "status: approved", "updated: 2026-01-01"]
    if milestone is not None:
        lines.append(f"milestone: {milestone}")
    lines += ["---", "", f"# {ident} — feature", ""]
    for number in sorted(tags or {}):
        mark = f" [{tags[number]}]" if tags[number] else ""
        lines += ["## Acceptance criteria" if number == sorted(tags)[0] else "", "",
                  f"**AC-{number}** When request {number} arrives, given the store is",
                  f"reachable, result {number} is recorded.{mark}", ""]
    return "\n".join(lines)


def task(ident: str, needs: str = "", writes: str = "", covers: str = "[AC-1]",
         lane: str = "light", serialises: str = "") -> str:
    lines = [f"task: {ident}", f"title: work for {ident}", f"lane: {lane}"]
    if needs:
        lines.append(f"needs: {needs}")
    lines.append(f"writes: [{writes}]")
    lines.append(f"covers: {covers}")
    if serialises:
        lines.append(f"serialises: {serialises}")
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
                slug: str = "thing", tags: dict | None = None) -> None:
        """A spec, and a plan for it when any task block is given."""
        (self.root / "docs" / "product" / "specs" / f"{ident}-{slug}.md").write_text(
            spec(ident, milestone, tags), encoding="utf-8")
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


class DerivedStateFixture(MilestoneFixture):
    """`--since` — where the milestone actually is, read out of git and never out of a ledger.

    The ledger is written by the agent it would bind, so it is a claim; a commit is a fact. Every
    test here therefore asserts against commits and never against a recorded state, and the two
    that matter most are the ones a held-state implementation would also pass and then get wrong
    after a compaction: status is recomputed from the range on every run, and a task the plan later
    drops resurfaces as an unresolved commit rather than disappearing.
    """

    def setUp(self) -> None:
        super().setUp()
        self.milestone()

    def git(self, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True,
                              check=False)
        return done.stdout.strip()

    def start(self) -> str:
        self.git("init", "-q", ".")
        self.git("config", "user.email", "a@b.c")
        self.git("config", "user.name", "t")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "the plans")
        return self.git("rev-parse", "HEAD")

    def commit(self, subject: str, *paths: str) -> str:
        for relative in paths or ("notes.md",):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(subject + "\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def since(self, base: str, *extra: str) -> dict:
        result = self.run_cli("--milestone", "M2", "--since", base, "--json", *extra)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return json.loads(result.stdout)

    def states(self, base: str, *extra: str) -> dict:
        return {ident: row["state"] for ident, row in self.since(base, *extra)["status"].items()}


class DerivedStatusTest(DerivedStateFixture):
    def test_a_commit_naming_a_task_is_what_makes_it_done(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        base = self.start()
        self.commit("feat(F-11/T1): the first one", "a/x")
        self.assertEqual(self.states(base), {"F-11/T1": "done", "F-11/T2": "ready"})

    def test_a_task_whose_needs_are_unmet_names_what_blocks_it(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        base = self.start()
        report = self.since(base)
        self.assertEqual(report["status"]["F-11/T2"]["state"], "blocked")
        self.assertEqual(report["status"]["F-11/T2"]["blocked_on"], ["F-11/T1"])

    def test_a_cross_feature_edge_blocks_across_the_milestone(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", needs="[F-11/T1]", writes="b/**"), slug="other")
        base = self.start()
        self.assertEqual(self.states(base)["F-12/T1"], "blocked")
        self.commit("feat(F-11/T1): done", "a/x")
        self.assertEqual(self.states(base)["F-12/T1"], "ready")

    def test_status_is_recomputed_and_never_read_back_from_anywhere(self) -> None:
        """The compaction test. Two identical runs either side of a new commit must disagree only
        because the TREE changed, and the second run is given nothing the first one produced."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        base = self.start()
        first = self.states(base)
        self.commit("feat(F-11/T1): landed", "a/x")
        second = self.states(base)
        self.assertEqual(first["F-11/T1"], "ready")
        self.assertEqual(second["F-11/T1"], "done")
        self.assertEqual(self.states(base), second)

    def test_the_range_is_what_bounds_it_so_earlier_work_is_not_counted(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        self.start()
        self.commit("feat(F-11/T1): before the base", "a/x")
        later = self.git("rev-parse", "HEAD")
        self.assertEqual(self.states(later)["F-11/T1"], "ready")

    def test_two_commits_naming_one_task_are_reported_and_not_failed(self) -> None:
        """A follow-up fix naming the same task is as common as a re-dispatch, and a rule that
        fires on the ordinary case is a rule somebody removes. It still counts as done."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        base = self.start()
        self.commit("feat(F-11/T1): the work", "a/x")
        self.commit("fix(F-11/T1): the follow-up", "a/y")
        report = self.since(base)
        self.assertEqual(report["status"]["F-11/T1"]["state"], "duplicate")
        self.assertEqual(len(report["status"]["F-11/T1"]["commits"]), 2)
        self.assertEqual(report["status"]["F-11/T2"]["state"], "ready")

    def test_a_task_the_plan_dropped_resurfaces_as_an_unresolved_commit(self) -> None:
        """A replan edits the plan in place. Held state would lose the committed work silently;
        derived state cannot, because the commit is still in the range."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", writes="b/**"))
        base = self.start()
        self.commit("feat(F-11/T2): the work", "b/x")
        self.feature("F-11", task("T1", writes="a/**"))       # T2 re-cut out of the plan
        self.commit("docs: replan")
        report = self.since(base)
        self.assertEqual([item["names"] for item in report["unclaimed_commits"]], [["F-11/T2"]])
        self.assertIn("F-11/T2", " ".join(item["message"] for item in report["findings"]))

    def test_the_milestone_is_complete_only_when_every_task_has_a_commit(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        base = self.start()
        self.commit("feat(F-11/T1): one", "a/x")
        self.assertFalse(self.since(base)["complete"])
        self.commit("feat(F-11/T2): two", "b/x")
        self.assertTrue(self.since(base)["complete"])

    def test_being_unfinished_is_not_a_finding_and_does_not_exit_one(self) -> None:
        """Overloading exit 1 with `not done yet` would make the resume primitive red on every run
        but the last, which is the shape of a check that gets switched off."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"))
        base = self.start()
        result = self.run_cli("--milestone", "M2", "--since", base)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1 ready", result.stdout)
        self.assertIn("1 blocked", result.stdout)

    def test_the_write_check_runs_over_every_commit_in_the_range(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        self.feature("F-12", task("T1", writes="b/**"), slug="other")
        base = self.start()
        self.commit("feat(F-11/T1): strays into F-12", "a/x", "b/x")
        report = self.since(base)
        strays = [item for item in report["findings"] if item["rule"] == "W7"]
        self.assertTrue(strays, report["findings"])
        self.assertIn("`F-12/T1` declares it", " ".join(item["message"] for item in strays))

    def test_it_writes_nothing(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        base = self.start()
        self.commit("feat(F-11/T1): work", "a/x")
        before = {path: path.stat().st_mtime_ns
                  for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.run_cli("--milestone", "M2", "--since", base, "--ready")
        after = {path: path.stat().st_mtime_ns
                 for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(before, after)


class DispatchScopeTest(DerivedStateFixture):
    def test_status_across_plans_is_refused_because_ids_are_plan_local(self) -> None:
        """`T1` is a different task in every feature. A merged per-plan status view would resolve
        no bare subject at all and report the whole fleet as ready, which is the most dangerous
        wrong answer this script could give."""
        self.feature("F-11", task("T1", writes="a/**"))
        base = self.start()
        result = self.run_cli("--since", base)
        self.assertEqual(result.returncode, 2)
        self.assertIn("plan-local", result.stderr)

    def test_the_ready_set_needs_a_base_to_derive_from(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        self.start()
        result = self.run_cli("--milestone", "M2", "--ready")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--since", result.stderr)

    def test_an_unreadable_revision_is_an_error_and_never_an_empty_range(self) -> None:
        """`no commits` and `I could not read that` are the same output and opposite facts."""
        self.feature("F-11", task("T1", writes="a/**"))
        self.start()
        result = self.run_cli("--milestone", "M2", "--since", "no-such-rev-here")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no-such-rev-here", result.stderr)

    def test_an_in_flight_id_no_task_declares_is_an_error(self) -> None:
        """It means the caller and the plan disagree about what exists, and continuing would build
        a ready set against a mutex that is not there."""
        self.feature("F-11", task("T1", writes="a/**"))
        base = self.start()
        result = self.run_cli("--milestone", "M2", "--since", base, "--in-flight", "F-11/T9")
        self.assertEqual(result.returncode, 2)
        self.assertIn("F-11/T9", result.stderr)

    def test_a_limit_below_one_is_an_error(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        base = self.start()
        result = self.run_cli("--milestone", "M2", "--since", base, "--ready", "--limit", "0")
        self.assertEqual(result.returncode, 2)


class ReadySetTest(DerivedStateFixture):
    """The dispatchable set — the same certificate the waves carry, with no barrier.

    `schedule()` is Kahn LEVELS, so wave N+1 waits on all of wave N even where a task needs one
    predecessor. W4/W6 compare EVERY pair rather than same-wave pairs, which is what licenses this:
    on a graph those two checks pass, disjointness against the in-flight set is the whole condition.
    """

    def test_a_task_whose_predecessor_landed_is_dispatchable_before_its_wave_peers(self) -> None:
        """THE LOAD-BEARING TEST. T2 sits in wave 3 behind T1; the barrier makes it wait for the
        whole of wave 2, and the ready set does not, because nothing in wave 2 blocks it."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"),
                     task("T3", needs="[T2]", writes="c/**"))
        self.feature("F-12", task("T1", writes="d/**"), task("T2", needs="[T1]", writes="e/**"),
                     slug="other")
        base = self.start()
        _, milestone = self.result()
        self.assertEqual(len(milestone.waves), 3)
        self.commit("feat(F-11/T1): one", "a/x")
        self.assertEqual(self.since(base, "--ready")["ready"], ["F-11/T2", "F-12/T1"])

    def test_a_task_that_writes_where_something_in_flight_writes_is_deferred(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), task("T2", writes="a/deep/**"))
        base = self.start()
        report = self.since(base, "--ready", "--in-flight", "F-11/T1")
        self.assertEqual(report["ready"], [])
        self.assertIn("in flight", report["deferred"][0]["reason"])
        self.assertEqual(report["deferred"][0]["task"], "F-11/T2")

    def test_a_serialises_partner_in_flight_is_the_declared_mutex(self) -> None:
        """The blocker this fixed: the dispatch interface omitted `serialises`, so a consumer could
        compute that two write sets overlap but not that the overlap was deliberate."""
        self.feature("F-11", task("T1", writes="a/**"),
                     task("T2", needs="[T1]", writes="a/**", serialises="[T1]"))
        base = self.start()
        self.commit("feat(F-11/T1): one", "a/x")
        report = self.since(base, "--ready", "--in-flight", "F-11/T1")
        self.assertEqual(report["ready"], [])
        self.assertIn("serialises with `F-11/T1`", report["deferred"][0]["reason"])

    def test_the_emitted_set_is_legal_against_itself_and_not_only_against_what_runs(self) -> None:
        """A milestone with findings still gets a usable answer: two colliding candidates must not
        both come back, or the caller dispatches the collision this script exists to refuse."""
        self.feature("F-11", task("T1", writes="shared/**"))
        self.feature("F-12", task("T1", writes="shared/**"), slug="other")
        base = self.start()
        report = self.since(base, "--ready")
        self.assertEqual(len(report["ready"]), 1)
        self.assertEqual(len(report["deferred"]), 1)

    def test_the_set_is_ordered_by_how_much_each_task_unlocks(self) -> None:
        """Removing the barrier is only half of it: measured on a reconstructed 51-task graph, a
        ready set dispatched in id order is no faster than the waves and at five writers slower."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", needs="[T1]", writes="b/**"),
                     task("T3", needs="[T2]", writes="c/**"))
        self.feature("F-12", task("T9", writes="d/**"), slug="other")
        base = self.start()
        self.assertEqual(self.since(base, "--ready")["ready"], ["F-11/T1", "F-12/T9"])

    def test_the_limit_is_the_operators_and_the_deferred_tasks_say_so(self) -> None:
        """No cap is compiled in. Legality is re-derived against the actual in-flight set at every
        dispatch, so the set is disjoint at any size, and the measured 4-of-83 stray is a per-task
        rate that running fewer at once does not lower — W7 at commit time is what catches it."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", writes="b/**"),
                     task("T3", writes="c/**"))
        base = self.start()
        self.assertEqual(len(self.since(base, "--ready")["ready"]), 3)
        capped = self.since(base, "--ready", "--limit", "2")
        self.assertEqual(len(capped["ready"]), 2)
        self.assertEqual(capped["deferred"], [{"task": "F-11/T3", "reason": "--limit 2 reached"}])

    def test_ready_emits_json_even_without_the_json_flag(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        base = self.start()
        result = self.run_cli("--milestone", "M2", "--since", base, "--ready")
        self.assertEqual(json.loads(result.stdout)["ready"], ["F-11/T1"])

    def test_a_done_task_never_comes_back_in_the_set(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"))
        base = self.start()
        self.commit("feat(F-11/T1): done", "a/x")
        self.assertEqual(self.since(base, "--ready")["ready"], [])


class CriterionPriorityTest(DerivedStateFixture):
    """The OPTIONAL `[P1]` tag on a criterion, and the one key it is allowed to touch.

    The tag exists because `AC-1..n` are unordered and the first ordering in the corpus arrives at
    `milestone:`, after the spec is frozen. It reaches exactly one decision — the last sort key of
    the ready set, which was alphabetical and which the operator was overriding from memory.
    """

    def test_the_tag_is_read_off_the_wrapped_line_that_carries_no_criterion_id(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), tags={1: "P2", 2: "", 3: "P1"})
        table = plan_waves.criterion_priorities(self.root.resolve())
        self.assertEqual(table, {"F-11": {"1": 2, "3": 1}})

    def test_a_spec_that_marks_nothing_contributes_nothing(self) -> None:
        """The common case, and it has to stay free: 0 of 995 real criteria carry a tag today."""
        self.feature("F-11", task("T1", writes="a/**"), tags={1: "", 2: ""})
        self.assertEqual(plan_waves.criterion_priorities(self.root.resolve()), {})

    def test_a_task_takes_the_best_priority_it_covers(self) -> None:
        """The task has to run for its most important criterion to close, so that rank is its
        floor; taking the worst would bury a P1 behind whatever else the task also satisfied."""
        self.feature("F-11", task("T1", writes="a/**", covers="[AC-1, AC-3]"),
                     tags={1: "P3", 3: "P1"})
        _, milestone = self.result()
        table = plan_waves.criterion_priorities(self.root.resolve())
        self.assertEqual(plan_waves.task_priorities(milestone.tasks, table), {"F-11/T1": 1})

    def test_the_marked_criterion_reorders_its_own_feature(self) -> None:
        self.feature("F-11", task("T1", writes="a/**", covers="[AC-1]"),
                     task("T2", writes="b/**", covers="[AC-2]"),
                     task("T3", writes="c/**", covers="[AC-3]"), tags={1: "", 2: "", 3: ""})
        base = self.start()
        self.assertEqual(self.since(base, "--ready")["ready"],
                         ["F-11/T1", "F-11/T2", "F-11/T3"])
        self.feature("F-11", task("T1", writes="a/**", covers="[AC-1]"),
                     task("T2", writes="b/**", covers="[AC-2]"),
                     task("T3", writes="c/**", covers="[AC-3]"), tags={1: "", 2: "", 3: "P1"})
        report = self.since(base, "--ready")
        self.assertEqual(report["ready"], ["F-11/T3", "F-11/T1", "F-11/T2"])
        self.assertEqual(report["priority"], {"F-11/T3": "P1"})

    def test_a_priority_in_one_feature_never_jumps_another_feature(self) -> None:
        """The inversion this guards: the FIRST spec in a milestone to write a tag would otherwise
        promote itself over every feature that had not, so unmarked would silently mean last."""
        self.feature("F-11", task("T1", writes="a/**"), task("T2", writes="b/**"),
                     tags={1: "", 2: ""})
        self.feature("F-12", task("T1", writes="c/**", covers="[AC-1]"), slug="other",
                     tags={1: "P1"})
        base = self.start()
        report = self.since(base, "--ready")
        self.assertEqual(report["ready"], ["F-11/T1", "F-11/T2", "F-12/T1"])
        self.assertEqual(report["priority"], {"F-12/T1": "P1"})

    def test_a_task_that_unlocks_another_still_outranks_the_p1(self) -> None:
        """`unlocks` is a measured throughput ordering — 11%-22% faster than id order across two to
        eight writers. Priority is the tiebreak and never buys any of that back."""
        self.feature("F-11", task("T1", writes="a/**", covers="[AC-1]"),
                     task("T2", needs="[T1]", writes="b/**", covers="[AC-1]"),
                     task("T3", writes="c/**", covers="[AC-3]"), tags={1: "", 3: "P1"})
        base = self.start()
        self.assertEqual(self.since(base, "--ready")["ready"], ["F-11/T1", "F-11/T3"])

    def test_the_payload_distinguishes_marked_nothing_from_changed_nothing(self) -> None:
        self.feature("F-11", task("T1", writes="a/**"), tags={1: ""})
        base = self.start()
        self.assertEqual(self.since(base, "--ready")["priority"], {})

    def test_a_spec_whose_front_matter_does_not_parse_is_skipped_in_silence(self) -> None:
        """The spec checker owns that finding; a second copy here would report it twice, and a
        traceback would take the schedule away over a document this run does not own."""
        self.feature("F-11", task("T1", writes="a/**"), tags={1: "P1"})
        path = next((self.root / "docs" / "product" / "specs").glob("F-11-*.md"))
        path.write_text("# F-11 — no front matter\n\n**AC-1** When a thing happens, given "
                        "another, a third is recorded. [P1]\n", encoding="utf-8")
        self.assertEqual(plan_waves.criterion_priorities(self.root.resolve()), {})


class DispatchInterfaceTest(MilestoneFixture):
    def test_the_task_payload_carries_the_declared_mutex(self) -> None:
        """`milestone_json` called itself the dispatch interface and omitted the one key a
        dispatcher cannot build the mutex without."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"),
                     task("T2", needs="[T1]", writes="a/**", serialises="[T1]"))
        payload = self.report()["tasks"]
        self.assertEqual(payload["F-11/T2"]["serialises"], ["F-11/T1"])
        self.assertEqual(payload["F-11/T1"]["serialises"], [])

    def test_serialises_is_left_plan_local_exactly_as_written(self) -> None:
        """`needs` is qualified because the scheduler resolves it; `serialises` is passed through,
        so a consumer reading it must qualify against the same feature. Pinned because a silent
        change of either convention would leave two readers disagreeing about one id."""
        self.milestone()
        self.feature("F-11", task("T1", writes="a/**"),
                     task("T2", needs="[T1]", writes="a/**", serialises="[T1]"))
        payload = self.report()["tasks"]["F-11/T2"]
        self.assertEqual(payload["needs"], ["F-11/T1"])
        self.assertEqual(payload["serialises"], ["F-11/T1"])


if __name__ == "__main__":
    unittest.main()
