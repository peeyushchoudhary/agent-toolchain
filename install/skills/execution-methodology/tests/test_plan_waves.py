#!/usr/bin/env python3
"""Tests for plan_waves.py — the wave computation and the write-collision check over feature plans.

Run: python3 -m unittest tests.test_plan_waves   (from the skill root)
  or python3 -m unittest discover -s tests -t tests

Two things are pinned harder than the rest, because they are the two ways this script could be
worse than useless. The first is that a collision is REPORTED AND NOT REPAIRED: there is a test
asserting the colliding pair stays in the same wave, because a version that quietly serialises the
pair reports a green schedule for a plan that still says two agents own one file. The second is
that glob overlap is decided WITHOUT the filesystem — the fixtures never create the files the globs
name, so a re-implementation that starts expanding globs against a tree fails every one of them.

The overlap tests run in BOTH directions on every pair. The relation is symmetric by definition and
a dynamic program is exactly the kind of code that ends up not being.
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

HEAD = """---
id: F-7
title: Reminders
status: building
updated: 2026-01-01
---

# F-7 — Reminders
"""


def task(ident: str, needs: str = "", writes: str = "src/{}/**", covers: str = "[AC-1]",
         lane: str = "light", serialises: str = "") -> str:
    """One task block. `writes` takes the id, so tasks are disjoint unless a test says otherwise."""
    lines = [f"task: {ident}", f"title: work for {ident}", f"lane: {lane}"]
    if needs:
        lines.append(f"needs: {needs}")
    if serialises:
        lines.append(f"serialises: {serialises}")
    lines.append(f"writes: [{writes.format(ident.lower())}]")
    lines.append(f"covers: {covers}")
    return "\n```task\n" + "\n".join(lines) + "\n```\n"


class PlanFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "product" / "plans").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def plan(self, *blocks: str, name: str = "F-7-reminders.md", head: str = HEAD) -> Path:
        path = self.root / "docs" / "product" / "plans" / name
        path.write_text(head + "".join(blocks), encoding="utf-8")
        return path

    def run_cli(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *extra],
                              capture_output=True, text=True)

    def report(self) -> dict:
        result = self.run_cli("--json")
        return json.loads(result.stdout)

    def rules(self) -> list[str]:
        findings, _ = plan_waves.run(self.root.resolve())
        return [item.rule for item in findings]

    def messages(self, rule: str) -> list[str]:
        findings, _ = plan_waves.run(self.root.resolve())
        return [item.message for item in findings if item.rule == rule]

    def waves(self) -> list[list[str]]:
        _, plans = plan_waves.run(self.root.resolve())
        return plans[0].waves if plans else []

    def assertFinds(self, rule: str) -> None:
        found = self.rules()
        self.assertIn(rule, found, f"expected a {rule} finding, got {found}")

    def assertDoesNotFind(self, rule: str) -> None:
        found = self.rules()
        self.assertNotIn(rule, found, f"unexpected {rule} finding in {found}")


class DiscoveryTest(PlanFixture):
    def test_a_repository_without_plans_is_silent(self) -> None:
        """Mid-adoption repositories must not be blocked by a layout they never agreed to."""
        (self.root / "docs" / "product" / "plans").rmdir()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_an_empty_plans_directory_is_silent(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_clean_plan_exits_zero_and_prints_the_wave_plan(self) -> None:
        self.plan(task("T1"), task("T2", needs="[T1]"))
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wave 1  width 1  T1", result.stdout)
        self.assertIn("wave 2  width 1  T2", result.stdout)

    def test_the_script_writes_nothing(self) -> None:
        """The whole design rests on this: a checker that emits artifacts defeats its own purpose."""
        self.plan(task("T1", needs="[T9]"))
        before = {path: path.stat().st_mtime_ns
                  for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(self.run_cli().returncode, 1)
        after = {path: path.stat().st_mtime_ns
                 for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(before, after)

    def test_a_missing_root_is_a_usage_error(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root / "nope")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a directory", result.stderr)

    def test_a_document_that_is_not_a_feature_plan_is_not_read(self) -> None:
        self.plan(task("T1", needs="[T9]"), name="notes.md")
        self.assertEqual(self.run_cli().returncode, 0)


class WaveTest(PlanFixture):
    def test_a_three_wave_dag_produces_the_right_waves_and_widths(self) -> None:
        self.plan(task("T1"), task("T2"), task("T3", needs="[T1]"), task("T4", needs="[T1, T2]"),
                  task("T5", needs="[T3, T4]"))
        report = self.report()
        self.assertEqual(report["exit"], 0, report["findings"])
        waves = report["plans"][0]["waves"]
        self.assertEqual([w["tasks"] for w in waves], [["T1", "T2"], ["T3", "T4"], ["T5"]])
        self.assertEqual([w["width"] for w in waves], [2, 2, 1])

    def test_a_task_with_no_edges_at_all_is_one_wave(self) -> None:
        self.plan(task("T1"), task("T2"), task("T3"))
        self.assertEqual(self.waves(), [["T1", "T2", "T3"]])

    def test_a_chain_is_one_task_per_wave(self) -> None:
        self.plan(task("T1"), task("T2", needs="[T1]"), task("T3", needs="[T2]"))
        self.assertEqual(self.waves(), [["T1"], ["T2"], ["T3"]])

    def test_two_plans_are_scheduled_independently(self) -> None:
        """Task ids are plan-local. Fusing two features into one graph would make every plan that
        starts at `T1` depend on every other plan that does."""
        self.plan(task("T1"), task("T2", needs="[T1]"))
        self.plan(task("T1"), name="F-8-other.md")
        report = self.report()
        self.assertEqual(report["exit"], 0, report["findings"])
        self.assertEqual(len(report["plans"]), 2)
        self.assertEqual([w["tasks"] for w in report["plans"][1]["waves"]], [["T1"]])


class EdgeTest(PlanFixture):
    def test_w1_names_an_edge_to_a_task_declared_nowhere(self) -> None:
        """Four of these already exist in a real 51-task corpus, and nothing objected."""
        self.plan(task("T1"), task("T2", needs="[T1, TC-01]"))
        self.assertFinds("W1")
        self.assertIn("`T2` needs `TC-01`", self.messages("W1")[0])

    def test_w1_does_not_fire_on_a_resolved_edge(self) -> None:
        self.plan(task("T1"), task("T2", needs="[T1]"))
        self.assertDoesNotFind("W1")

    def test_w1_catches_a_self_edge_and_the_task_still_schedules(self) -> None:
        self.plan(task("T1", needs="[T1]"))
        self.assertFinds("W1")
        self.assertEqual(self.waves(), [["T1"]])

    def test_a_dangling_edge_does_not_stall_the_schedule(self) -> None:
        """A dropped edge must not look like a cycle: the two defects need different repairs."""
        self.plan(task("T1", needs="[T9]"), task("T2", needs="[T1]"))
        self.assertEqual(self.waves(), [["T1"], ["T2"]])
        self.assertDoesNotFind("W2")

    def test_w2_names_the_shortest_cycle(self) -> None:
        self.plan(task("T1", needs="[T4]"), task("T2", needs="[T1]"), task("T3", needs="[T2]"),
                  task("T4", needs="[T3, T2]"))
        self.assertFinds("W2")
        self.assertIn("T1 -> T4 -> T2 -> T1", self.messages("W2")[0])

    def test_w2_reports_the_tasks_it_could_not_schedule(self) -> None:
        self.plan(task("T1"), task("T2", needs="[T3]"), task("T3", needs="[T2]"))
        _, plans = plan_waves.run(self.root.resolve())
        self.assertEqual(plans[0].waves, [["T1"]])
        self.assertEqual(plans[0].stuck, ["T2", "T3"])

    def test_w2_does_not_fire_on_a_diamond(self) -> None:
        """Two paths to one task is a normal plan, not a cycle."""
        self.plan(task("T1"), task("T2", needs="[T1]"), task("T3", needs="[T1]"),
                  task("T4", needs="[T2, T3]"))
        self.assertDoesNotFind("W2")

    def test_w3_names_the_first_declaration_of_a_repeated_id(self) -> None:
        self.plan(task("T1"), task("T2"), task("T1", writes="other/**"))
        self.assertFinds("W3")
        self.assertIn("already declared on line", self.messages("W3")[0])

    def test_w3_does_not_fire_across_two_plans(self) -> None:
        self.plan(task("T1"))
        self.plan(task("T1"), name="F-8-other.md")
        self.assertDoesNotFind("W3")


class WriteOverlapTest(PlanFixture):
    def test_w4_names_both_tasks_and_both_globs(self) -> None:
        self.plan(task("T1"), task("T2", needs="[T1]", writes="backend/x/**"),
                  task("T3", needs="[T1]", writes="backend/x/y.java"))
        self.assertFinds("W4")
        message = self.messages("W4")[0]
        for fragment in ("`T2`", "`T3`", "wave 2", "backend/x/**", "backend/x/y.java"):
            self.assertIn(fragment, message)

    def test_w4_does_not_serialise_the_pair_it_reports(self) -> None:
        """THE LOAD-BEARING TEST. Moving one task down a wave would turn this plan green while the
        decomposition defect — two owners for one file — is still in the file."""
        self.plan(task("T1"), task("T2", needs="[T1]", writes="backend/x/**"),
                  task("T3", needs="[T1]", writes="backend/x/y.java"))
        self.assertEqual(self.waves(), [["T1"], ["T2", "T3"]])

    def test_w4_decides_overlap_without_the_files_existing(self) -> None:
        """Nothing under `backend/` is ever created by these fixtures. That is the requirement:
        two tasks collide over files that the plan has not caused to exist yet."""
        self.assertFalse((self.root / "backend").exists())
        self.plan(task("T1", writes="backend/**"), task("T2", writes="backend/db/V1__init.sql"))
        self.assertFinds("W4")

    def test_w4_is_silent_when_the_write_sets_are_disjoint(self) -> None:
        self.plan(task("T1", writes="backend/a/**"), task("T2", writes="backend/b/**"))
        self.assertDoesNotFind("W4")

    def test_w4_is_silent_when_the_colliding_tasks_are_in_different_waves(self) -> None:
        """An edge between them IS the planner owning the serialisation, and it is accepted."""
        self.plan(task("T1", writes="backend/x/**"),
                  task("T2", needs="[T1]", writes="backend/x/y.java"))
        self.assertDoesNotFind("W4")

    def test_w4_reports_one_finding_per_colliding_pair(self) -> None:
        self.plan(task("T1", writes="a/**"), task("T2", writes="a/b/**"),
                  task("T3", writes="a/b/c.java"))
        self.assertEqual(len(self.messages("W4")), 3)


class GlobTest(unittest.TestCase):
    """The pattern-intersection subset, tested on the pairs that decide a real plan."""

    def check(self, left: str, right: str, expected: bool) -> None:
        for one, two in ((left, right), (right, left)):   # the relation is symmetric, so test both
            with self.subTest(left=one, right=two):
                self.assertEqual(plan_waves.overlap(one, two), expected)

    def test_a_double_star_covers_a_deep_path(self) -> None:
        self.check("a/**", "a/b/c.java", True)

    def test_a_double_star_covers_a_sibling_wildcard(self) -> None:
        self.check("a/*.java", "a/**", True)

    def test_two_double_stars_meet_through_a_single_star_segment(self) -> None:
        self.check("a/b/**", "a/*/c/**", True)

    def test_a_leading_double_star_matches_a_named_directory(self) -> None:
        self.check("**/x.md", "docs/x.md", True)

    def test_disjoint_extensions_do_not_meet(self) -> None:
        self.check("a/*.java", "a/*.py", False)

    def test_disjoint_directories_do_not_meet(self) -> None:
        self.check("a/b/**", "a/c/**", False)
        self.check("docs/**/*.md", "src/a.md", False)

    def test_question_mark_matches_exactly_one_character(self) -> None:
        self.check("a/?.java", "a/b.java", True)
        self.check("a/?.java", "a/bb.java", False)

    def test_character_classes_and_their_negation(self) -> None:
        self.check("src/[a-c]*.py", "src/b1.py", True)
        self.check("src/[a-c]*.py", "src/z1.py", False)
        self.check("src/[!a-c]*.py", "src/z1.py", True)
        self.check("src/[!a-c]*.py", "src/b1.py", False)

    def test_a_migration_wildcard_meets_its_directory(self) -> None:
        self.check("backend/db/migration/V12__*.sql", "backend/db/**", True)

    def test_a_bare_path_is_also_read_as_a_directory(self) -> None:
        """Conservative by decision: `backend/x` almost always names a directory, and reading it as
        a file only would miss the collision with everything inside it."""
        self.check("backend/x", "backend/x/y.java", True)

    def test_a_brace_is_treated_as_a_wildcard_rather_than_ignored(self) -> None:
        """Brace expansion is not implemented. Reading `{a,b}` literally would MISS a real overlap,
        so the segment widens to `*` instead, which over-reports and never under-reports."""
        self.check("a/{b,c}/x", "a/c/x", True)
        self.check("a/{b,c}/x", "a/c/y", False)

    def test_normalisation_of_leading_and_trailing_separators(self) -> None:
        self.check("./a/b.java", "a/b.java", True)
        self.check("a/b/", "a/b/c.java", True)
        self.check("a//b.java", "a/b.java", True)

    def test_an_empty_pattern_meets_nothing(self) -> None:
        self.check("", "a/b.java", False)


class SizeTest(PlanFixture):
    def test_w5_flags_more_than_five_write_globs(self) -> None:
        self.plan(task("T1", writes="a/**, b/**, c/**, d/**, e/**, f/**"))
        self.assertFinds("W5")
        self.plan(task("T1", writes="a/**, b/**, c/**, d/**, e/**"))
        self.assertDoesNotFind("W5")

    def test_w5_flags_a_task_that_covers_no_criterion(self) -> None:
        self.plan(task("T1", covers="[]"))
        self.assertFinds("W5")
        self.assertIn("covers no acceptance criterion", self.messages("W5")[0])

    def test_w5_flags_a_feature_with_too_many_full_lane_tasks(self) -> None:
        self.plan(*[task(f"T{n}", lane="full") for n in range(1, 14)])
        self.assertFinds("W5")
        self.assertIn("13 full-lane tasks", self.messages("W5")[0])

    def test_w5_accepts_twelve_full_lane_tasks(self) -> None:
        self.plan(*[task(f"T{n}", lane="full") for n in range(1, 13)])
        self.assertDoesNotFind("W5")

    def test_light_lane_tasks_are_not_counted_against_the_feature_limit(self) -> None:
        self.plan(*[task(f"T{n}") for n in range(1, 20)])
        self.assertDoesNotFind("W5")


class BlockTest(PlanFixture):
    def test_w0_flags_an_unknown_key(self) -> None:
        self.plan("\n```task\ntask: T1\nrepo: something\nwrites: [a/**]\ncovers: [AC-1]\n```\n")
        self.assertFinds("W0")

    def test_w0_flags_an_unknown_lane(self) -> None:
        self.plan(task("T1", lane="medium"))
        self.assertFinds("W0")

    def test_w0_flags_a_block_with_no_usable_id(self) -> None:
        self.plan("\n```task\ntitle: nameless\nwrites: [a/**]\n```\n")
        self.assertFinds("W0")

    def test_w0_flags_a_block_that_does_not_parse(self) -> None:
        """A parser that drops a line it could not read is how a checker starts lying."""
        self.plan("\n```task\ntask: T1\nwrites:\n  - a/**\n```\n")
        self.assertFinds("W0")

    def test_a_block_that_does_not_parse_reports_its_line_in_the_file(self) -> None:
        self.plan(task("T1"), "\n```task\ntask: T2\n  nested: yes\n```\n")
        message = self.messages("W0")[0]
        line = int(message.split("line ", 1)[1].split(":", 1)[0])
        self.assertEqual(self.plan_text().splitlines()[line - 1].strip(), "nested: yes")

    def plan_text(self) -> str:
        return (self.root / "docs" / "product" / "plans" / "F-7-reminders.md").read_text("utf-8")

    def test_a_task_block_quoted_inside_a_longer_fence_is_not_a_task(self) -> None:
        """A reference page showing the template is not a plan. A bare fence toggle would read the
        example as a real task and then report on documentation."""
        self.plan("\n````markdown\n```task\ntask: T1\nneeds: [T9]\n```\n````\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")

    def test_a_scalar_is_read_as_the_one_element_list_it_obviously_is(self) -> None:
        self.plan(task("T1"), "\n```task\ntask: T2\nneeds: T1\nwrites: a/**\ncovers: AC-2\n```\n")
        self.assertEqual(self.rules(), [])
        self.assertEqual(self.waves(), [["T1"], ["T2"]])

    def test_a_plan_with_no_task_blocks_produces_nothing(self) -> None:
        self.plan("\nProse only, no tasks yet.\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


class OutputTest(PlanFixture):
    def test_json_carries_the_waves_the_findings_and_the_exit_code(self) -> None:
        self.plan(task("T1", writes="a/**"), task("T2", writes="a/b.java"))
        report = self.report()
        self.assertEqual(report["exit"], 1)
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["findings"][0]["rule"], "W4")
        self.assertEqual(report["plans"][0]["waves"][0]["width"], 2)
        self.assertEqual(report["plans"][0]["unscheduled"], [])

    def test_findings_exit_one_and_the_wave_plan_still_prints(self) -> None:
        """The schedule is the reason to run this. Withholding it on a finding would make the
        planner fix one thing at a time with no view of the shape."""
        self.plan(task("T1", writes="a/**"), task("T2", writes="a/b.java"))
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("W4", result.stdout)
        self.assertIn("wave 1  width 2  T1, T2", result.stdout)

    def test_a_fifty_task_corpus_schedules_in_well_under_a_second(self) -> None:
        """O(n^2) pairwise over write sets is the cost model, and it is affordable at plan scale."""
        blocks = [task("T1")]
        blocks += [task(f"T{n}", needs=f"[T{n - 1}]" if n % 5 == 0 else "[T1]")
                   for n in range(2, 51)]
        self.plan(*blocks)
        start = time.perf_counter()
        findings, plans = plan_waves.run(self.root.resolve())
        elapsed = time.perf_counter() - start
        self.assertEqual(list(findings), [])
        self.assertEqual(sum(len(wave) for wave in plans[0].waves), 50)
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()


class SerialisedOverlapTest(PlanFixture):
    """W6 — the check may not be defeated by the remedy it recommends.

    The wave-scoped version told the planner to add a `needs` edge, and doing so moved the pair into
    different waves and silenced the finding while both tasks still owned one file. Measured on a
    real 51-task graph: 41 such edges silenced all 37 collisions.
    """

    def test_a_dependency_edge_no_longer_hides_a_shared_write_set(self) -> None:
        self.plan(task("T1", writes="backend/shared/**"),
                  task("T2", needs="[T1]", writes="backend/shared/auth.java"))
        found = self.rules()
        self.assertIn("W6", found, found)
        self.assertNotIn("W4", found, "different waves, so it reports as W6 rather than W4")

    def test_declaring_the_overlap_closes_it(self) -> None:
        self.plan(task("T1", writes="backend/shared/**"),
                  task("T2", needs="[T1]", serialises="[T1]", writes="backend/shared/auth.java"))
        self.assertEqual(self.rules(), [], "a declared overlap is a statement, not a defect")

    def test_serialises_does_not_excuse_a_same_wave_collision(self) -> None:
        """Declaring shared ownership is not permission to run the pair concurrently."""
        self.plan(task("T1", writes="backend/shared/**"),
                  task("T2", serialises="[T1]", writes="backend/shared/auth.java"))
        self.assertIn("W4", self.rules())


class CommitWritesTest(PlanFixture):
    """W7 — the declared write set against what a commit actually wrote.

    Measured on 16 sealed cards against their real commits: 4 of 83 files landed outside the
    declaring task's set, and all four sat inside ANOTHER task's set. That is the collision the wave
    checks exist to prevent, happening at commit time where nothing was looking.
    """

    def repo(self, *blocks: str) -> None:
        self.plan(*blocks)
        self.git("init", "-q", ".")
        self.git("config", "user.email", "a@b.c")
        self.git("config", "user.name", "t")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=False)

    def commit(self, subject: str, *paths: str) -> None:
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", subject)

    def test_a_file_outside_the_declared_set_is_named_with_its_real_owner(self) -> None:
        self.repo(task("T1", writes="backend/a/**"), task("T2", needs="[T1]", writes="backend/b/**"))
        self.commit("feat(T1): also touches b", "backend/a/one.java", "backend/b/two.java")
        result = self.run_cli("--commit", "HEAD")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("W7", result.stdout)
        self.assertIn("backend/b/two.java", result.stdout)
        self.assertIn("`T2` declares it", result.stdout)

    def test_a_commit_inside_its_own_set_is_clean(self) -> None:
        self.repo(task("T1", writes="backend/a/**"), task("T2", needs="[T1]", writes="backend/b/**"))
        self.commit("feat(T1): stays home", "backend/a/one.java")
        self.assertEqual(self.run_cli("--commit", "HEAD").returncode, 0)

    def test_a_commit_naming_no_task_is_not_a_finding(self) -> None:
        """Light-lane work has no card. Inventing a violation for it gets the check removed."""
        self.repo(task("T1", writes="backend/a/**"))
        self.commit("chore: unrelated tidy-up", "docs/notes.md")
        self.assertEqual(self.run_cli("--commit", "HEAD").returncode, 0)


class QualifiedCommitReferenceTest(CommitWritesTest):
    """W7 could not read the id this methodology tells people to write.

    A subject reference is `F-12/T3`. The old word-split saw `F-12` and `T3` as two separate words
    and matched neither, so under `--milestone` — where every id carries its feature — NO subject
    resolved and the check reported nothing. Worse, `--milestone` never called the check at all: the
    flag was accepted and silently ignored, and the milestone view is the ONLY scope that can see a
    commit landing in another FEATURE's set, because a per-plan run never loads the other plan.
    """

    def test_a_qualified_id_resolves_in_plan_scope(self) -> None:
        self.repo(task("T1", writes="backend/a/**"), task("T2", needs="[T1]", writes="backend/b/**"))
        self.commit("feat(T1): also touches b", "backend/a/one.java", "backend/b/two.java")
        bare = self.run_cli("--commit", "HEAD")
        self.git("reset", "-q", "--hard", "HEAD~1")
        self.commit("feat(F-7/T1): also touches b", "backend/a/one.java", "backend/b/two.java")
        qualified = self.run_cli("--commit", "HEAD")
        self.assertEqual(bare.returncode, 1)
        self.assertEqual(qualified.returncode, 1,
                         "a qualified id must resolve where a bare one does")
        self.assertIn("backend/b/two.java", qualified.stdout)

    def test_a_task_shaped_id_that_resolves_to_nothing_is_reported(self) -> None:
        """Silence here let a card that had drifted from its plan push clean."""
        self.repo(task("T1", writes="backend/a/**"))
        self.commit("feat(T9): a task no plan declares", "backend/a/one.java")
        result = self.run_cli("--commit", "HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("T9", result.stdout)

    def test_ordinary_prose_stays_silent(self) -> None:
        """Light-lane work has no card. Inventing a violation for it gets the check removed."""
        self.repo(task("T1", writes="backend/a/**"))
        self.commit("docs: tidy the README", "backend/a/one.java")
        self.assertEqual(self.run_cli("--commit", "HEAD").returncode, 0)


class ReferenceShapeTest(CommitWritesTest):
    """WHICH UNRESOLVED REFERENCE DESERVES A FINDING — the answer measured, not assumed.

    Over 2,672 real commit subjects in eight repositories the reference pattern matches 198 times
    and 136 of those (69%) are ordinary English. Every subject below is real, copied from that
    corpus, and every one of them used to report `the card and the plan disagree` about a commit
    that never claimed a task. The whole point of `--since` is to run this check over a RANGE, so a
    69% false rate stops being a nuisance on one commit and becomes the normal exit status.
    """

    # The T-words are the evidence and are copied verbatim; the surrounding prose is neutral.
    ENGLISH = ("chore: rotate the TLS certificates",
               "feat(auth): complete the secure TOTP baseline",
               "feat(transport): complete the Transport domain",
               "chore(contracts): regenerate OpenAPI and TypeScript",
               "feat(billing): a slice with TC-blocked-on-dues (Task F-a)",
               "feat(authz): make THE_INVARIANT machine-enforced",
               "docs(decisions): the veto is named — TaskStop is not a write",
               "feat(auth): refresh TTL 30 days becomes 7",
               "chore: adopt TDD for the importer")

    REAL = ("feat(privacy): the consent register (T9)",
            "feat(auth)!: remove the forced enrolment family (T9a)",
            "feat(users): show which users have two-factor (T-FE1)",
            "docs(decisions): the ADR for it (T-DOCS)")

    def test_english_words_beginning_with_t_are_not_task_references(self) -> None:
        self.repo(task("T1", writes="backend/a/**"))
        for subject in self.ENGLISH:
            with self.subTest(subject=subject):
                self.commit(subject, "backend/a/one.java")
                result = self.run_cli("--commit", "HEAD")
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_real_task_shaped_id_that_resolves_to_nothing_is_still_reported(self) -> None:
        """The other half: narrowing the shape must not silence the drift W7 exists to catch."""
        self.repo(task("T1", writes="backend/a/**"))
        for subject in self.REAL:
            with self.subTest(subject=subject):
                self.commit(subject, "backend/a/one.java")
                result = self.run_cli("--commit", "HEAD")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("W7", result.stdout)

    def test_a_declared_id_resolves_whatever_shape_it_has(self) -> None:
        """The narrowing gates the FINDING and never the resolution: a plan free to declare
        `task: TOTP` must still have its commits checked against its own write set."""
        self.repo(task("TOTP", writes="backend/a/**"), task("T2", writes="backend/b/**"))
        self.commit("feat(TOTP): the baseline", "backend/a/one.java", "backend/b/two.java")
        result = self.run_cli("--commit", "HEAD")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("`T2` declares it", result.stdout)

    def test_a_trailing_separator_belongs_to_the_sentence_and_not_to_the_id(self) -> None:
        """`Implement TRS-C11 moderation backend T1-T5.` is a real subject; the captured `T5.`
        resolved to nothing and then reported itself as a card that had drifted."""
        self.repo(task("T5", writes="backend/a/**"), task("T6", writes="backend/b/**"))
        self.commit("feat: moderation backend T5.", "backend/a/one.java", "backend/b/two.java")
        result = self.run_cli("--commit", "HEAD")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("`T6` declares it", result.stdout)
