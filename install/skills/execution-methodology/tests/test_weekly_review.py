#!/usr/bin/env python3
"""Tests for weekly_review.py — the weekly process-cost cadence.

Run: python3 -m unittest tests.test_weekly_review  (from the skill root)
  or python3 -m unittest discover -s tests -t tests

Real repositories with real commits, dated into the ISO weeks each assertion is about. The report's
only interesting behaviour is how it buckets and compares weeks, and a fixture that stubbed git out
would leave exactly that untested.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "weekly_review.py"

sys.path.insert(0, str(SCRIPTS))

import ratio_meter  # noqa: E402  — the path insertion above has to happen first
import weekly_review  # noqa: E402


class WeeklyFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.make_repo("alpha")
        self.today = date.today()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_repo(self, name: str) -> Path:
        repo = self.root / name
        repo.mkdir(parents=True)
        for arguments in (("init", "-b", "main"),
                          ("config", "user.email", "meter@example.invalid"),
                          ("config", "user.name", "Meter Test"),
                          ("config", "commit.gpgsign", "false")):
            completed = subprocess.run(["git", *arguments], cwd=repo,
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return repo

    def commit_in_week(self, repo: Path, weeks_ago: int, files: dict[str, int]) -> None:
        """One commit whose author and committer date sit inside the week `weeks_ago` weeks back."""
        for relative, count in files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.read_text(encoding="utf-8").count("\n") if path.exists() else 0
            path.write_text("".join(f"line {existing + n}\n" for n in range(count)),
                            encoding="utf-8")
        # Midday on the Wednesday of the target week: comfortably inside the ISO week whichever
        # local timezone the machine running the suite happens to be in.
        stamp = (weekly_review.week_start(self.today) - timedelta(weeks=weeks_ago)
                 + timedelta(days=2))
        when = f"{stamp.isoformat()} 12:00:00"
        env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        for arguments in (("add", "-A"), ("commit", "-m", f"commit for {stamp.isoformat()}")):
            completed = subprocess.run(["git", *arguments], cwd=repo, env=env,
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def run_review(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *extra],
                              capture_output=True, text=True)

    def payload(self, *extra: str) -> dict:
        result = self.run_review("--json", *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)


class ClassifierReuseTest(unittest.TestCase):
    def test_the_classifier_is_imported_and_not_restated(self) -> None:
        """One copy of the classification table, asserted by identity rather than by reading it."""
        self.assertIs(weekly_review.collect, ratio_meter.collect)
        self.assertIs(weekly_review.tally, ratio_meter.tally)
        self.assertIs(weekly_review.PROCESS, ratio_meter.PROCESS)
        source = SCRIPT.read_text(encoding="utf-8")
        for table in ("PROCESS_SEQUENCES", "PRODUCT_SUFFIXES", "EXCLUDED_SEGMENTS"):
            self.assertNotIn(table + " =", source)


class WeekArithmeticTest(unittest.TestCase):
    def test_week_start_is_the_monday_of_the_iso_week(self) -> None:
        for day in (date(2026, 8, 10), date(2026, 8, 14), date(2026, 8, 16)):
            self.assertEqual(weekly_review.week_start(day), date(2026, 8, 10))

    def test_labels_run_oldest_to_newest_and_end_on_this_week(self) -> None:
        labels = weekly_review.week_labels(date(2026, 8, 20), 4)
        self.assertEqual(labels, ["2026-W31", "2026-W32", "2026-W33", "2026-W34"])

    def test_an_unparseable_commit_date_is_not_bucketed(self) -> None:
        self.assertIsNone(weekly_review.commit_week("not-a-date"))
        self.assertEqual(weekly_review.commit_week("2026-08-20T12:00:00+00:00"), "2026-W34")


class TrendTest(unittest.TestCase):
    def rows(self, shares: list[float | None]) -> list[weekly_review.WeekRow]:
        return [weekly_review.WeekRow(label=f"w{index}", lines={}, denominator=0 if s is None else 1,
                                      process_share=s)
                for index, s in enumerate(shares)]

    def test_a_rising_process_share_is_degrading(self) -> None:
        verdict, new, old = weekly_review.trend(self.rows([0.02, 0.03, 0.04, 0.20, 0.30, 0.40]))
        self.assertEqual(verdict, "degrading")
        self.assertGreater(new, old)

    def test_a_falling_process_share_is_improving(self) -> None:
        verdict, _, _ = weekly_review.trend(self.rows([0.40, 0.30, 0.20, 0.04, 0.03, 0.02]))
        self.assertEqual(verdict, "improving")

    def test_a_small_movement_is_flat(self) -> None:
        verdict, _, _ = weekly_review.trend(self.rows([0.10, 0.10, 0.10, 0.11, 0.10, 0.11]))
        self.assertEqual(verdict, "flat")

    def test_too_few_weeks_is_named_rather_than_guessed(self) -> None:
        verdict, new, old = weekly_review.trend(self.rows([0.1, 0.2, 0.3]))
        self.assertEqual(verdict, "insufficient history")
        self.assertIsNone(new)
        self.assertIsNone(old)

    def test_weeks_with_no_churn_are_left_out_of_the_means(self) -> None:
        """A quiet week is a week with no measurement, never a week that scored zero."""
        verdict, new, old = weekly_review.trend(
            self.rows([0.40, None, None, None, None, 0.40]))
        self.assertEqual(verdict, "flat")
        self.assertAlmostEqual(new, 0.40)
        self.assertAlmostEqual(old, 0.40)
        empty, _, _ = weekly_review.trend(self.rows([0.4, 0.4, 0.4, None, None, None]))
        self.assertEqual(empty, "insufficient data")


class WeeklyReviewTest(WeeklyFixture):
    def test_commits_land_in_the_week_they_were_made(self) -> None:
        self.commit_in_week(self.repo, 2, {"src/main/java/Service.java": 30,
                                           "docs/agents/progress.md": 3})
        self.commit_in_week(self.repo, 0, {"src/main/java/Other.java": 10,
                                           "docs/agents/lessons.md": 40})
        data = self.payload("--repo", str(self.repo), "--weeks", "4")
        weeks = {row["label"]: row for row in data["repos"][0]["weeks"]}
        labels = data["weeks"]
        self.assertEqual(len(labels), 4)
        self.assertEqual(weeks[labels[1]]["lines"]["product"], 30)
        self.assertEqual(weeks[labels[1]]["lines"]["process"], 3)
        self.assertIsNone(weeks[labels[2]]["process_share"])
        self.assertEqual(weeks[labels[3]]["lines"]["process"], 40)
        self.assertAlmostEqual(weeks[labels[3]]["process_share"], 0.80)

    def test_each_week_is_marked_against_the_ceiling(self) -> None:
        self.commit_in_week(self.repo, 1, {"src/main/java/Service.java": 100,
                                           "docs/agents/progress.md": 2})
        self.commit_in_week(self.repo, 0, {"src/main/java/Other.java": 10,
                                           "docs/agents/lessons.md": 40})
        result = self.run_review("--repo", str(self.repo), "--weeks", "8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertIn("BREACH", result.stdout)
        self.assertIn("trend:", result.stdout)

    def test_a_degrading_repository_is_reported_but_still_exits_zero(self) -> None:
        """The report steers; it does not gate. See the module header."""
        for weeks_ago, process in ((5, 1), (4, 1), (3, 1), (2, 60), (1, 70), (0, 80)):
            self.commit_in_week(self.repo, weeks_ago, {
                "src/main/java/Service.java": 100,
                f"docs/agents/note-{weeks_ago}.md": process,
            })
        result = self.run_review("--repo", str(self.repo), "--weeks", "6")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("trend: degrading", result.stdout)
        data = self.payload("--repo", str(self.repo), "--weeks", "6")
        self.assertEqual(data["repos"][0]["trend"], "degrading")
        self.assertGreater(data["repos"][0]["trend_recent"], data["repos"][0]["trend_earlier"])

    def test_the_portfolio_rolls_every_repository_up(self) -> None:
        second = self.make_repo("beta")
        self.commit_in_week(self.repo, 0, {"src/main/java/Service.java": 90,
                                           "docs/agents/progress.md": 10})
        self.commit_in_week(second, 0, {"src/main/java/Other.java": 10,
                                        "docs/agents/lessons.md": 90})
        data = self.payload("--repo", str(self.repo), "--repo", str(second), "--weeks", "4")
        portfolio = data["portfolio"]
        self.assertEqual(portfolio["repos_read"], 2)
        self.assertEqual(portfolio["repos_failed"], 0)
        self.assertEqual(portfolio["lines"]["product"], 100)
        self.assertEqual(portfolio["lines"]["process"], 100)
        self.assertAlmostEqual(portfolio["process_share"], 0.50)
        self.assertTrue(portfolio["breach"])
        self.assertEqual([entry["name"] for entry in data["repos"]], ["alpha", "beta"])
        self.assertEqual(portfolio["largest_process_files"][0]["lines"], 90)

    def test_the_report_names_the_repository_and_not_its_path(self) -> None:
        self.commit_in_week(self.repo, 0, {"src/main/java/Service.java": 10})
        result = self.run_review("--repo", str(self.repo), "--weeks", "4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("alpha", result.stdout)
        self.assertNotIn(str(self.root), result.stdout)
        self.assertEqual(self.payload("--repo", str(self.repo))["repos"][0]["path"],
                         str(self.repo))

    def test_eight_weeks_of_three_repositories_stays_readable(self) -> None:
        repos = [self.repo, self.make_repo("beta"), self.make_repo("gamma")]
        for index, repo in enumerate(repos):
            for weeks_ago in range(8):
                self.commit_in_week(repo, weeks_ago, {
                    f"src/main/java/S{weeks_ago}.java": 10 + index,
                    f"docs/agents/n{weeks_ago}.md": weeks_ago + 1,
                })
        result = self.run_review(*sum([["--repo", str(repo)] for repo in repos], []),
                                 "--weeks", "8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(len(result.stdout.splitlines()), 60, result.stdout)
        for name in ("alpha", "beta", "gamma"):
            self.assertIn(name, result.stdout)

    def test_a_repository_with_no_commits_reports_empty_weeks_rather_than_failing(self) -> None:
        result = self.run_review("--repo", str(self.repo), "--weeks", "4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = self.payload("--repo", str(self.repo), "--weeks", "4")
        self.assertEqual(data["repos"][0]["trend"], "insufficient history")
        self.assertIsNone(data["portfolio"]["process_share"])
        self.assertTrue(all(row["process_share"] is None for row in data["repos"][0]["weeks"]))

    def test_an_unreadable_repository_is_a_finding_and_not_a_silent_omission(self) -> None:
        self.commit_in_week(self.repo, 0, {"src/main/java/Service.java": 10})
        result = self.run_review("--repo", str(self.repo),
                                 "--repo", str(self.root / "absent"), "--weeks", "4")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("COULD NOT READ", result.stdout)
        data = self.payload("--repo", str(self.repo), "--repo", str(self.root / "absent"))
        self.assertEqual(data["portfolio"]["repos_read"], 1)
        self.assertEqual(data["portfolio"]["repos_failed"], 1)
        self.assertEqual(data["repos"][1]["error"], "not a directory")

    def test_a_directory_that_is_not_a_repository_is_reported(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        result = self.run_review("--repo", str(plain), "--weeks", "4")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("COULD NOT READ", result.stdout)
        self.assertIn("no repository could be read", result.stderr)

    def test_json_carries_the_whole_payload(self) -> None:
        self.commit_in_week(self.repo, 0, {"src/main/java/Service.java": 10,
                                           "docs/agents/progress.md": 1})
        data = self.payload("--repo", str(self.repo), "--weeks", "8")
        self.assertEqual(sorted(data), ["portfolio", "repos", "weeks"])
        self.assertEqual(len(data["weeks"]), 8)
        entry = data["repos"][0]
        for key in ("name", "path", "weeks", "trend", "trend_recent", "trend_earlier"):
            self.assertIn(key, entry)
        for key in ("repos_read", "repos_failed", "lines", "ratio_lines", "process_share",
                    "process_ceiling", "breach", "largest_process_files"):
            self.assertIn(key, data["portfolio"])
        row = entry["weeks"][-1]
        self.assertEqual(sorted(row), ["denominator", "label", "lines", "process_share"])

    def test_bad_arguments_are_usage_errors(self) -> None:
        self.assertEqual(self.run_review().returncode, 2)
        self.assertEqual(self.run_review("--repo", str(self.repo), "--weeks", "0").returncode, 2)
        self.assertEqual(
            self.run_review("--repo", str(self.repo), "--ceiling", "0").returncode, 2)


if __name__ == "__main__":
    unittest.main()
