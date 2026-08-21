#!/usr/bin/env python3
"""Weekly process-cost trend across one or more repositories, so the drift is seen while it is small.

`ratio_meter.py` answers "is this range within budget". That is the right question at a gate and the
wrong one for steering: the eight-week collapse the meter exists to catch never breached anything on
any single day. It was a slope. Each week looked like the one before it, and the ratio moved by an
order of magnitude while every individual reading stayed unremarkable.

So this is a REPORT and not a gate, and the difference is in the exit code as well as in the prose:
a degrading trend exits 0. A weekly cadence read by a person is where a trend gets acted on, and a
report that can fail the build would be run by a machine and read by nobody. The one thing it must
never do is be silently absent, which is why an unreadable repository is printed as a finding rather
than dropped from the roll-up.

The classifier is imported from `ratio_meter.py` rather than restated. A second copy of a
classification table drifts from the first one, and then two tools disagree about what a file is
while both of them report confidently.

Usage:
  weekly_review.py --repo PATH                          # the last 8 ISO weeks
  weekly_review.py --repo PATH --repo PATH --weeks 12   # portfolio, longer window
  weekly_review.py --repo PATH --json                   # machine-readable

Exit codes: 0 the report was produced, 2 the arguments or a repository could not be used at all.
There is no exit 1: nothing here renders a verdict that should stop anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple, Optional

from ratio_meter import (DEFAULT_CEILING, PROCESS, PRODUCT, PRODUCT_THINK, RATIO_BUCKETS,
                         MeterError, collect, contrast, tally)

# Weeks compared on each side of the trend test. Three is short enough that a quarter of a year is
# not needed before the report says anything, and long enough that one heavy refactor week does not
# decide the verdict on its own.
TREND_WINDOW = 3
# The share movement below which two windows are called flat. Without a dead band every report
# would read `improving` or `degrading`, because two averages of real data are never equal, and a
# trend verdict that is never `flat` carries no information.
TREND_DEAD_BAND = 0.02


class WeekRow(NamedTuple):
    label: str
    lines: dict[str, int]
    denominator: int
    process_share: Optional[float]


def iso_label(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_start(day: date) -> date:
    """The Monday of the ISO week containing `day`."""
    return day - timedelta(days=day.isoweekday() - 1)


def week_labels(today: date, weeks: int) -> list[str]:
    first = week_start(today) - timedelta(weeks=weeks - 1)
    return [iso_label(first + timedelta(weeks=index)) for index in range(weeks)]


def commit_week(iso_timestamp: str) -> Optional[str]:
    """The ISO week label of a `%cI` committer date, or None if git handed back something else."""
    try:
        return iso_label(datetime.fromisoformat(iso_timestamp).date())
    except ValueError:
        return None


def measure_repo(repo: Path, labels: list[str], since: date) -> tuple[dict[str, WeekRow], Counter]:
    """Per-week rows for one repository, plus its process churn by file over the whole window.

    One `git log` call per repository rather than one per week. The commits are then bucketed by
    their own committer date, so a week with no commits is an explicit empty row instead of a gap
    the reader has to notice is missing.
    """
    commits = collect(repo, since=since.isoformat())
    by_week: dict[str, list] = {label: [] for label in labels}
    for commit in commits:
        label = commit_week(commit.date)
        if label in by_week:
            by_week[label].append(commit)
    rows: dict[str, WeekRow] = {}
    churn: Counter = Counter()
    for label in labels:
        counted = tally(by_week[label])
        denominator = sum(counted.lines[bucket] for bucket in RATIO_BUCKETS)
        rows[label] = WeekRow(
            label=label,
            lines=dict(counted.lines),
            denominator=denominator,
            process_share=None if denominator == 0 else counted.lines[PROCESS] / denominator,
        )
        churn.update(counted.process_churn)
    return rows, churn


def trend(rows: list[WeekRow]) -> tuple[str, Optional[float], Optional[float]]:
    """(verdict, recent mean share, earlier mean share) over the last two three-week windows.

    Weeks with no classified churn are left out of both means rather than counted as 0.00. A week
    nobody committed in is not a week the process cost was zero; it is a week with no measurement,
    and averaging it in would report a holiday as an improvement.
    """
    if len(rows) < TREND_WINDOW * 2:
        return "insufficient history", None, None
    recent = [row.process_share for row in rows[-TREND_WINDOW:] if row.process_share is not None]
    earlier = [row.process_share for row in rows[-TREND_WINDOW * 2:-TREND_WINDOW]
               if row.process_share is not None]
    if not recent or not earlier:
        return "insufficient data", None, None
    new = sum(recent) / len(recent)
    old = sum(earlier) / len(earlier)
    if new > old + TREND_DEAD_BAND:
        return "degrading", new, old
    if new < old - TREND_DEAD_BAND:
        return "improving", new, old
    return "flat", new, old


def share_text(value: Optional[float]) -> str:
    """Three decimals, not two: a week printed as `0.10  BREACH` argues with its own marker."""
    return "   --" if value is None else f"{value:5.3f}"


def render(repos: list[dict[str, object]], portfolio: dict[str, object],
           labels: list[str], ceiling: float) -> list[str]:
    out: list[str] = [f"weekly process-cost review — {labels[0]} to {labels[-1]}, "
                      f"ceiling {ceiling:.2f}", ""]
    for entry in repos:
        if entry.get("error"):
            out.append(f"{entry['name']}  COULD NOT READ — {entry['error']}")
            out.append("")
            continue
        out.append(f"{entry['name']}")
        out.append(f"  {'week':<9}{'product':>9}{'think':>7}{'process':>9}{'share':>7}  verdict")
        for row in entry["weeks"]:
            marker = "  --  " if row["process_share"] is None else (
                "BREACH" if row["process_share"] > ceiling else "PASS  ")
            out.append(f"  {row['label']:<9}{row['lines'][PRODUCT]:>9}"
                       f"{row['lines'][PRODUCT_THINK]:>7}{row['lines'][PROCESS]:>9}"
                       f"{share_text(row['process_share']):>7}  {marker}")
        movement = ""
        if entry["trend_recent"] is not None:
            movement = (f" ({entry['trend_earlier']:.2f} -> {entry['trend_recent']:.2f}"
                        f" over {TREND_WINDOW} weeks)")
        out.append(f"  trend: {entry['trend']}{movement}")
        out.append("")
    out.append(f"portfolio  {portfolio['repos_read']} repo(s) read, "
               f"{portfolio['repos_failed']} unreadable")
    out.append(f"  product {portfolio['lines'][PRODUCT]}, "
               f"think {portfolio['lines'][PRODUCT_THINK]}, "
               f"process {portfolio['lines'][PROCESS]}")
    if portfolio["process_share"] is None:
        out.append(f"  {'NO DATA':<8} no classified churn in the window")
    else:
        state = "BREACH" if portfolio["breach"] else "WITHIN"
        actual, limit = contrast(portfolio["process_share"], ceiling)
        out.append(f"  {state:<8} process share {actual}, ceiling {limit}")
    if portfolio["largest_process_files"]:
        out.append("  largest process files across the portfolio:")
        for item in portfolio["largest_process_files"]:
            out.append(f"    {item['lines']:>7}  {item['path']}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", action="append", required=True, metavar="PATH",
                        help="repository to review; repeat for a portfolio")
    parser.add_argument("--weeks", type=int, default=8, help="ISO weeks to report (default 8)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--ceiling", type=float, default=DEFAULT_CEILING,
                        help=f"process share each week is marked against (default {DEFAULT_CEILING})")
    args = parser.parse_args()

    if args.weeks < 1:
        parser.error(f"--weeks must be at least 1, got {args.weeks}")
    if not 0.0 < args.ceiling <= 1.0:
        parser.error(f"--ceiling must be a share above 0 and at most 1, got {args.ceiling}")

    today = date.today()
    labels = week_labels(today, args.weeks)
    since = week_start(today) - timedelta(weeks=args.weeks - 1)

    entries: list[dict[str, object]] = []
    totals = {bucket: 0 for bucket in RATIO_BUCKETS}
    portfolio_churn: Counter = Counter()
    read = failed = 0
    for raw in args.repo:
        repo = Path(raw).expanduser()
        # The repository NAME, not the path: this report is read aloud and pasted around, and a
        # home directory is nobody's business but its owner's. `--json` carries the path for a
        # caller that needs to act on it.
        entry: dict[str, object] = {"name": repo.name or str(repo), "path": str(repo)}
        if not repo.is_dir():
            entry["error"] = "not a directory"
        else:
            try:
                rows, churn = measure_repo(repo, labels, since)
            except MeterError as exc:
                entry["error"] = str(exc)
            else:
                ordered = [rows[label] for label in labels]
                verdict, recent, earlier = trend(ordered)
                entry.update({
                    "weeks": [row._asdict() for row in ordered],
                    "trend": verdict,
                    "trend_recent": recent,
                    "trend_earlier": earlier,
                })
                for row in ordered:
                    for bucket in RATIO_BUCKETS:
                        totals[bucket] += row.lines[bucket]
                portfolio_churn.update(churn)
        if entry.get("error"):
            failed += 1
        else:
            read += 1
        entries.append(entry)

    denominator = sum(totals.values())
    process_share = None if denominator == 0 else totals[PROCESS] / denominator
    portfolio = {
        "repos_read": read,
        "repos_failed": failed,
        "lines": totals,
        "ratio_lines": denominator,
        "process_share": process_share,
        "process_ceiling": args.ceiling,
        "breach": process_share is not None and process_share > args.ceiling,
        "largest_process_files": [{"path": path, "lines": count}
                                  for path, count in portfolio_churn.most_common(3)],
    }
    if args.json:
        print(json.dumps({"weeks": labels, "repos": entries, "portfolio": portfolio},
                         indent=2, sort_keys=True))
    else:
        print("\n".join(render(entries, portfolio, labels, args.ceiling)))
    # Every repository unreadable is the one shape that is not a report at all: nothing was
    # measured, so there is no trend to have read, and exiting 0 would present silence as a result.
    if read == 0:
        print("ERROR: no repository could be read", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
