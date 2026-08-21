#!/usr/bin/env python3
"""Tests for ratio_meter.py — the process-cost budget meter.

Run: python3 -m unittest tests.test_ratio_meter  (from the skill root)
  or python3 -m unittest discover -s tests -t tests

Every test builds a real git repository and makes real commits. The meter's whole claim is that it
reads git's own numstat rather than a workspace the measured party writes, so a fixture that fed it
a synthetic log would test the one half of the tool that is not the point.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "ratio_meter.py"

sys.path.insert(0, str(SCRIPTS))

import ratio_meter  # noqa: E402  — the path insertion above has to happen first


class GitFixture(unittest.TestCase):
    """A throwaway repository plus the two helpers every test below writes commits with."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "meter@example.invalid")
        self.git("config", "user.name", "Meter Test")
        self.git("config", "commit.gpgsign", "false")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess:
        completed = subprocess.run(["git", *arguments], cwd=self.repo,
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed

    def write(self, relative: str, lines: int, *, first: int = 0) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"line {first + n}\n" for n in range(lines)), encoding="utf-8")

    def write_bytes(self, relative: str, payload: bytes) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def commit(self, message: str = "commit") -> None:
        self.git("add", "-A")
        self.git("commit", "-m", message)

    def run_meter(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *extra],
            capture_output=True, text=True,
        )

    def payload(self, *extra: str) -> dict:
        result = self.run_meter("--json", *extra)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return json.loads(result.stdout)


class ClassifyTest(unittest.TestCase):
    """The classifier is pure and path-only, so it is asserted directly rather than through git."""

    def assert_bucket(self, bucket: str, *paths: str) -> None:
        for path in paths:
            self.assertEqual(ratio_meter.classify(path), bucket, path)

    def test_source_and_build_and_iac_files_are_product(self) -> None:
        self.assert_bucket(
            ratio_meter.PRODUCT,
            "src/main/java/Service.java", "app/Screen.kt", "web/src/App.tsx", "web/src/util.ts",
            "web/src/util.js", "web/src/App.jsx", "tool/run.py", "cmd/main.go", "src/lib.rs",
            "ios/View.swift", "db/V1__init.sql", "web/app.css", "web/app.scss", "web/index.html",
            "web/App.vue", "app/build.gradle", "app/build.gradle.kts", "package.json", "pom.xml",
            "Cargo.toml", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
            "infra/main.tf", "infra/prod.tfvars", "Dockerfile", "Dockerfile.prod",
            "docker-compose.yml", ".github/workflows/ci.yml",
        )

    def test_specs_and_decisions_and_contracts_are_product_thinking(self) -> None:
        self.assert_bucket(
            ratio_meter.PRODUCT_THINK,
            "docs/product/onboarding.md", "docs/architecture/overview.md",
            "docs/decisions/0004-queueing.md", "docs/runbooks/rollback.md",
            "specs/search.md", "design/checkout.md", "PRD.md", "docs/billing-prd.md",
            "README.md", "web/README.md", "api/openapi.yaml", "api/openapi-v2.json",
        )

    def test_bookkeeping_paths_are_process(self) -> None:
        self.assert_bucket(
            ratio_meter.PROCESS,
            ".superpowers/plan.md", "work/sdd/spec.md", "docs/agents/execution/methodology.md",
            "docs/superpowers/notes.md", "work/cards/TC-01.yaml", "work/verdicts/TC-01.md",
            "work/reports/week.md", "work/workspace/scratch.md", "work/escalations/E-1.md",
            "work/deferral-log.md", "docs/agents/progress.md", "LEDGER.md", "lessons.md",
            "work/receipt-TC-01.json", "AGENTS.md", "CLAUDE.md", "work/change.diff",
            "docs/personas/reviewer.md",
        )

    def test_generated_and_vendored_paths_are_excluded(self) -> None:
        self.assert_bucket(
            ratio_meter.EXCLUDED,
            "node_modules/left-pad/index.js", "web/dist/bundle.js", "app/build/output.class",
            "target/classes/Service.class", ".venv/lib/site.py", "vendor/lib/thing.go",
            "Cargo.lock", "package-lock.json", "web/src/api.gen.ts", "graphify-out/graph.json",
            "tool/__pycache__/run.cpython-311.pyc",
        )

    def test_unclassified_paths_are_other(self) -> None:
        self.assert_bucket(ratio_meter.OTHER, "notes.txt", "assets/logo.svg", "data/seed.json")

    def test_configuration_and_shell_are_product(self) -> None:
        """Config, orchestration, and shell are how a product is built and run, not commentary."""
        self.assert_bucket(ratio_meter.PRODUCT, "config/app.yml", "deploy/stack.yaml",
                           "scripts/release-gate.sh", "web/vite.config.mts", "tools/build.mjs")

    def test_plans_and_design_outrank_a_process_shaped_parent(self) -> None:
        """The two overrides, each earned by a false positive on a real repository.

        A plan filed under a process-shaped parent is still a design document, and a directory of
        UI mockups is design work even when its leaf directory is called `cards`.
        """
        self.assert_bucket(ratio_meter.PRODUCT_THINK,
                           "docs/superpowers/plans/2026-01-01-ship-plan.md",
                           "design/sync/cards/screen-01-empty-state.html")
        # The override is scoped: bookkeeping outside those two sequences still charges to process.
        self.assert_bucket(ratio_meter.PROCESS,
                           "docs/superpowers/progress.md",
                           "workspace/cards/task-01.md")

    def test_process_wins_an_ambiguous_path_and_the_cost_is_asserted(self) -> None:
        """The documented ordering, both directions, including the false positive it produces."""
        # A bookkeeping file cannot buy its way into product thinking with a directory name.
        self.assertEqual(ratio_meter.classify("docs/product/cards/TC-01.yaml"),
                         ratio_meter.PROCESS)
        self.assertEqual(ratio_meter.classify("specs/PRD-progress.md"), ratio_meter.PROCESS)
        # And the price, now bounded: a NON-source file under a generically-named directory is
        # still charged to process. Asserted so changing the ordering has to change this on purpose.
        self.assertEqual(ratio_meter.classify("src/reports/report-notes.md"),
                         ratio_meter.PROCESS)

    def test_source_beats_an_ambiguous_process_word(self) -> None:
        """`receipt`, `cards`, and `reports` are product vocabulary too.

        Each of these is a real path from an adopting repository that the first meter charged to
        bookkeeping: a consent receipt, a goods-receipt screen, a receipt validator, and a package
        whose subject is health cards. Bookkeeping is prose and data; it is never compiled or run.
        """
        self.assert_bucket(
            ratio_meter.PRODUCT,
            "backend/trust-core/src/main/java/com/x/trust/ConsentReceipts.java",
            "web/src/screens/inventory/GoodsReceiptScreen.tsx",
            "tools/agent/validation_receipt_v3.py",
            "backend/src/main/java/com/x/cards/CardService.java",
            "src/reports/ReportService.java",
            "src/main/java/com/x/personas/PersonaMapper.java",
        )

    def test_a_bookkeeping_root_still_owns_everything_inside_it(self) -> None:
        """The strong sequences are directories that exist only to hold bookkeeping.

        A script that serves the workspace is workspace cost, so source does NOT win there — this
        is the boundary that keeps the previous test from becoming an escape hatch.
        """
        self.assert_bucket(
            ratio_meter.PROCESS,
            ".superpowers/sdd/scripts/seal.py",
            "docs/agents/tools/render.ts",
            "work/verdicts/TC-01-r1-reviewer.md",
            "work/workspace/helper.sh",
        )

    def test_exclusion_outranks_every_other_bucket(self) -> None:
        self.assertEqual(ratio_meter.classify("node_modules/pkg/AGENTS.md"), ratio_meter.EXCLUDED)
        self.assertEqual(ratio_meter.classify("build/docs/product/spec.md"), ratio_meter.EXCLUDED)

    def test_matching_is_case_insensitive(self) -> None:
        self.assertEqual(ratio_meter.classify("ledger.md"), ratio_meter.PROCESS)
        self.assertEqual(ratio_meter.classify("docs/LESSONS.md"), ratio_meter.PROCESS)
        self.assertEqual(ratio_meter.classify("readme.md"), ratio_meter.PRODUCT_THINK)

    def test_segment_tokens_do_not_match_part_of_a_name(self) -> None:
        """`/cards/` is a directory, so a file that merely contains the letters is not process."""
        self.assertEqual(ratio_meter.classify("web/src/flashcards.ts"), ratio_meter.PRODUCT)
        self.assertEqual(ratio_meter.classify("src/main/java/Design.java"), ratio_meter.PRODUCT)

    def test_rename_notation_resolves_to_the_destination(self) -> None:
        self.assertEqual(ratio_meter.rename_destination("old.py => new.py"), "new.py")
        self.assertEqual(ratio_meter.rename_destination("docs/{a => b}/x.md"), "docs/b/x.md")
        self.assertEqual(ratio_meter.rename_destination("docs/{ => sub}/x.md"), "docs/sub/x.md")
        self.assertEqual(ratio_meter.rename_destination("docs/{sub => }/x.md"), "docs/x.md")
        self.assertEqual(ratio_meter.rename_destination("plain/path.md"), "plain/path.md")


class MeterTest(GitFixture):
    def test_a_product_heavy_range_is_within_budget(self) -> None:
        self.write("src/main/java/Service.java", 90)
        self.write("docs/product/spec.md", 8)
        self.write("docs/agents/progress.md", 2)
        self.commit("feat: service")
        result = self.run_meter("--since", "2000-01-01")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WITHIN", result.stdout)
        self.assertNotIn("largest process files", result.stdout)
        self.assertLess(len(result.stdout.splitlines()), 25, result.stdout)

    def test_each_bucket_is_counted_from_real_numstat(self) -> None:
        self.write("src/main/java/Service.java", 10)
        self.write("docs/product/spec.md", 4)
        self.write("docs/agents/progress.md", 3)
        self.write("notes.txt", 2)
        self.write("node_modules/pkg/index.js", 500)
        self.commit("chore: everything at once")
        data = self.payload("--since", "2000-01-01")
        self.assertEqual(data["lines"]["product"], 10)
        self.assertEqual(data["lines"]["product_think"], 4)
        self.assertEqual(data["lines"]["process"], 3)
        self.assertEqual(data["lines"]["other"], 2)
        self.assertEqual(data["ratio_lines"], 17)
        self.assertEqual(data["excluded_lines"], 500)
        self.assertEqual(data["excluded_files"], 1)
        self.assertEqual(data["commits"], 1)

    def test_excluded_churn_cannot_move_the_verdict(self) -> None:
        """A vendored tree outweighs everything and must not dilute the process share."""
        self.write("src/main/java/Service.java", 10)
        self.write("docs/agents/progress.md", 40)
        self.write("node_modules/pkg/index.js", 100000)
        self.commit("chore: vendor a tree")
        data = self.payload("--since", "2000-01-01")
        self.assertEqual(data["ratio_lines"], 50)
        self.assertAlmostEqual(data["process_share"], 0.8)
        self.assertTrue(data["breach"])

    def test_binary_files_are_counted_as_files_and_zero_lines(self) -> None:
        self.write("src/main/java/Service.java", 10)
        self.write_bytes("src/main/resources/logo.png", bytes(range(256)) * 8)
        self.commit("feat: add an image")
        data = self.payload("--since", "2000-01-01")
        self.assertEqual(data["binary_files"], 1)
        self.assertEqual(data["ratio_lines"], 10)
        self.assertEqual(data["lines"]["other"], 0)
        self.assertEqual(data["files"]["other"], 1)

    def test_deleting_bookkeeping_alongside_other_work_is_process_churn(self) -> None:
        self.write("docs/agents/progress.md", 30)
        self.commit("chore: bookkeeping")
        (self.repo / "docs/agents/progress.md").unlink()
        self.write("src/main/java/Service.java", 5)
        self.commit("chore: remove notes and add code")
        data = self.payload("--range", "HEAD~1..HEAD")
        self.assertEqual(data["cleanup_commits"], 0)
        self.assertEqual(data["lines"]["process"], 30)
        self.assertEqual(data["lines"]["product"], 5)
        self.assertTrue(data["breach"])

    def test_a_commit_that_only_deletes_bookkeeping_is_cleanup_and_never_breaches(self) -> None:
        self.write("docs/agents/progress.md", 400)
        self.write("src/main/java/Service.java", 10)
        self.commit("chore: seed")
        (self.repo / "docs/agents/progress.md").unlink()
        self.commit("chore: delete the bookkeeping")
        result = self.run_meter("--range", "HEAD~1..HEAD", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["cleanup_commits"], 1)
        self.assertEqual(data["cleanup_lines"], 400)
        self.assertEqual(data["cleanup_files"], 1)
        self.assertEqual(data["lines"]["process"], 0)
        self.assertEqual(data["ratio_lines"], 0)
        self.assertIsNone(data["process_share"])
        self.assertFalse(data["breach"])
        self.assertEqual(data["largest_process_files"], [])

    def test_a_cleanup_commit_does_not_exempt_the_rest_of_the_range(self) -> None:
        """The exemption is per commit. A breaching commit beside a cleanup still breaches."""
        self.write("docs/agents/progress.md", 100)
        self.write("src/main/java/Service.java", 10)
        self.commit("chore: seed")
        (self.repo / "docs/agents/progress.md").unlink()
        self.commit("chore: delete the bookkeeping")
        self.write("docs/agents/lessons.md", 60)
        self.write("src/main/java/Service.java", 12)
        self.commit("chore: write more bookkeeping")
        data = self.payload("--range", "HEAD~2..HEAD")
        self.assertEqual(data["cleanup_commits"], 1)
        self.assertEqual(data["cleanup_lines"], 100)
        self.assertEqual(data["lines"]["process"], 60)
        self.assertTrue(data["breach"])

    def test_a_rewrite_of_bookkeeping_is_not_a_cleanup(self) -> None:
        self.write("docs/agents/progress.md", 40)
        self.commit("chore: seed")
        self.write("docs/agents/progress.md", 40, first=1000)
        self.commit("chore: rewrite the notes")
        data = self.payload("--range", "HEAD~1..HEAD")
        self.assertEqual(data["cleanup_commits"], 0)
        self.assertEqual(data["lines"]["process"], 80)
        self.assertTrue(data["breach"])

    def test_a_breach_exits_one_and_names_the_largest_process_files(self) -> None:
        self.write("src/main/java/Service.java", 10)
        self.write("docs/agents/progress.md", 50)
        self.write("docs/agents/lessons.md", 30)
        self.write("work/cards/TC-01.yaml", 20)
        self.commit("chore: bookkeeping")
        result = self.run_meter("--since", "2000-01-01")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("BREACH", result.stdout)
        self.assertIn("process regression", result.stdout)
        self.assertIn("largest process files by churn:", result.stdout)
        self.assertIn("docs/agents/progress.md", result.stdout)
        self.assertLess(len(result.stdout.splitlines()), 25, result.stdout)

    def test_only_five_process_files_are_named(self) -> None:
        self.write("src/main/java/Service.java", 1)
        for index in range(9):
            self.write(f"work/cards/TC-{index:02d}.yaml", index + 1)
        self.commit("chore: many cards")
        data = self.payload("--since", "2000-01-01")
        self.assertEqual(len(data["largest_process_files"]), 5)
        self.assertEqual(data["largest_process_files"][0]["path"], "work/cards/TC-08.yaml")
        self.assertEqual(data["largest_process_files"][0]["lines"], 9)

    def test_the_product_floor_is_advisory_and_never_reaches_the_exit_code(self) -> None:
        """Product below the floor with process under the ceiling is a pass that says so."""
        self.write("src/main/java/Service.java", 20)
        self.write("docs/product/spec.md", 300)
        self.write("docs/agents/progress.md", 5)
        self.commit("docs: a heavy specification week")
        result = self.run_meter("--since", "2000-01-01")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BELOW", result.stdout)
        self.assertIn("advisory", result.stdout)
        data = self.payload("--since", "2000-01-01")
        self.assertFalse(data["product_floor_met"])
        self.assertFalse(data["breach"])

    def test_the_ceiling_is_configurable_and_the_verdict_follows_it(self) -> None:
        self.write("src/main/java/Service.java", 85)
        self.write("docs/agents/progress.md", 15)
        self.commit("chore: fifteen percent")
        self.assertEqual(self.run_meter("--since", "2000-01-01").returncode, 1)
        self.assertEqual(self.run_meter("--since", "2000-01-01", "--ceiling", "0.2").returncode, 0)

    def test_a_share_exactly_on_the_ceiling_is_within_budget(self) -> None:
        self.write("src/main/java/Service.java", 90)
        self.write("docs/agents/progress.md", 10)
        self.commit("chore: exactly ten percent")
        data = self.payload("--since", "2000-01-01")
        self.assertAlmostEqual(data["process_share"], 0.10)
        self.assertFalse(data["breach"])

    def test_a_share_just_over_the_ceiling_prints_two_distinguishable_numbers(self) -> None:
        """A verdict line may not print `0.10 is over the 0.10 ceiling` and expect to be believed."""
        self.write("src/main/java/Service.java", 905)
        self.write("docs/agents/progress.md", 101)
        self.commit("chore: just over the line")
        result = self.run_meter("--since", "2000-01-01")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("0.1004 is over the 0.1000 ceiling", result.stdout)

    def test_contrast_stops_at_the_first_precision_that_separates_two_shares(self) -> None:
        self.assertEqual(ratio_meter.contrast(0.5, 0.1), ("0.50", "0.10"))
        self.assertEqual(ratio_meter.contrast(0.1004, 0.10), ("0.1004", "0.1000"))
        self.assertEqual(ratio_meter.contrast(0.1, 0.1), ("0.100000", "0.100000"))

    def test_json_carries_the_whole_payload(self) -> None:
        self.write("src/main/java/Service.java", 10)
        self.commit("feat: service")
        data = self.payload("--range", "HEAD")
        for key in ("commits", "cleanup_commits", "ratio_lines", "lines", "files",
                    "cleanup_lines", "cleanup_files", "excluded_lines", "excluded_files",
                    "binary_files", "process_ceiling", "process_share", "product_floor",
                    "product_share", "product_floor_met", "breach", "largest_process_files",
                    "verdict", "scope", "repo"):
            self.assertIn(key, data)
        self.assertEqual(sorted(data["lines"]), ["other", "process", "product", "product_think"])
        self.assertEqual(data["verdict"], "WITHIN BUDGET")
        self.assertEqual(data["process_ceiling"], 0.10)
        self.assertEqual(data["product_floor"], 0.70)

    def test_a_range_with_no_commits_is_reported_as_no_data_rather_than_a_pass(self) -> None:
        self.write("src/main/java/Service.java", 10)
        self.commit("feat: service")
        result = self.run_meter("--range", "HEAD..HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NO DATA", result.stdout)
        data = self.payload("--range", "HEAD..HEAD")
        self.assertEqual(data["commits"], 0)
        self.assertIsNone(data["process_share"])
        self.assertIsNone(data["product_share"])

    def test_a_renamed_file_is_classified_where_it_landed(self) -> None:
        self.write("docs/agents/progress.md", 60)
        self.commit("chore: seed")
        self.git("mv", "docs/agents/progress.md", "docs/agents/status.md")
        self.commit("chore: rename")
        data = self.payload("--range", "HEAD~1..HEAD")
        self.assertEqual(data["lines"]["product"], 0)
        self.assertEqual(data["files"]["process"], 1)


class GitErrorTest(GitFixture):
    def test_a_repository_with_no_commits_yet_is_no_data_rather_than_an_error(self) -> None:
        """git exits 128 for an unborn branch; the honest reading of that is "no churn"."""
        result = self.run_meter("--since", "2000-01-01")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NO DATA", result.stdout)
        data = self.payload("--since", "2000-01-01")
        self.assertEqual(data["commits"], 0)
        self.assertIsNone(data["process_share"])

    def test_a_bad_range_exits_two_and_says_why(self) -> None:
        self.write("src/main/java/Service.java", 5)
        self.commit("feat: service")
        result = self.run_meter("--range", "no-such-ref..HEAD")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ERROR:", result.stderr)
        self.assertIn("git log failed", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_a_directory_that_is_not_a_repository_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", tmp, "--since", "2000-01-01"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("ERROR:", result.stderr)

    def test_a_missing_repository_exits_two(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo / "absent"),
             "--since", "2000-01-01"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not a directory", result.stderr)

    def test_neither_selector_is_a_usage_error(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("usage:", result.stderr)

    def test_both_selectors_together_are_a_usage_error(self) -> None:
        result = self.run_meter("--range", "HEAD", "--since", "2000-01-01")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not allowed with", result.stderr)

    def test_an_out_of_range_ceiling_is_a_usage_error(self) -> None:
        for value in ("0", "-0.5", "1.5"):
            result = self.run_meter("--range", "HEAD", "--ceiling", value)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("--ceiling", result.stderr)

    def test_an_unparseable_numstat_line_is_refused_rather_than_dropped(self) -> None:
        with self.assertRaises(ratio_meter.MeterError):
            ratio_meter.parse_log("\x1eabc123\x1f2026-08-14T00:00:00+00:00\n1 0 one.py\n")


if __name__ == "__main__":
    unittest.main()
