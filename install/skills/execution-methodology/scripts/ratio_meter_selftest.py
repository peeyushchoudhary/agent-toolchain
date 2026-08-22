#!/usr/bin/env python3
"""Break-test for ratio_meter.py — proves domain code is not charged to bookkeeping.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
that was LIVE in this file's sibling, and the measurement is in the module header it guards: before
the source-beats-name rule existed, the ambiguity charged 16,429 LINES OF DOMAIN CODE to process
across four adopting repositories.

  1  the four measured files are PRODUCT, by name
        ConsentReceipts.java, GoodsReceiptScreen.tsx, validation_receipt_v3.py,
        and a whole com/.../cards/ package whose subject is health cards
  2  the workspace artifact is still PROCESS
        `.superpowers/sdd/plans/verdicts/TC-01-r1-reviewer.md` — the exact artifact class the
        budget exists to bound, and the one a `plans/` override put in product thinking for a day
  3  a breach NAMES the largest process files, because a budget that only scolds cannot be acted on

WHY THE FILENAMES ARE THE REAL ONES. `receipt` is a milestone receipt and also a consent receipt, a
payment receipt and a goods-receipt screen; `cards` is a task card and also a health card. A
fixture called `thing.java` proves the suffix rule and proves nothing about the ambiguity, which is
where every line of the 16,429 came from. These names are the corpus.

CASE 1 AND CASE 2 ARE ONE ASSERTION IN TWO HALVES and neither is meaningful alone. A classifier
that called everything product would pass case 1; one that called everything process would pass
case 2. Both run over ONE commit, so the same ordering decides both.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process over a real git
repository in a temporary directory. The exclusion rules, the cleanup verdict, the volume floor and
the ceiling arithmetic are covered by the vendored suite and are not duplicated here. Nothing here
writes inside the repository.

Run:  python3 ratio_meter_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ratio_meter.py"

# The four measured ambiguities, and one unambiguous file of each other kind so the run has a
# denominator that is not made only of the interesting cases.
PRODUCT_FILES = {
    "src/main/java/com/example/cards/HealthCard.java": "class HealthCard {}\n",
    "src/main/java/com/example/consent/ConsentReceipts.java": "class ConsentReceipts {}\n",
    "ui/src/screens/GoodsReceiptScreen.tsx": "export const GoodsReceiptScreen = () => null;\n",
    "lib/validation_receipt_v3.py": "VERSION = 3\n",
}
PROCESS_FILES = {
    ".superpowers/sdd/plans/verdicts/TC-01-r1-reviewer.md": "verdict: approved\n",
    "docs/agents/execution/methodology.md": "# rendered methodology\n",
}

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def build(tmp: Path, files: dict[str, str]) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "selftest@example.invalid")
    git(repo, "config", "user.name", "selftest")
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "chore: init")
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "feat: the work")
    return repo


def measure(repo: Path, *extra: str) -> dict:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo),
                           "--range", "HEAD~1..HEAD", "--json", *extra],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_stdout": proc.stdout, "_stderr": proc.stderr}


def case_ambiguous_names_on_source_files_are_product() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = build(Path(td), PRODUCT_FILES)
        report = measure(repo)
        lines = report.get("lines", {})
        check("1a every ambiguous SOURCE file is charged to product",
              lines.get("product") == len(PRODUCT_FILES),
              f"product={lines.get('product')} of {len(PRODUCT_FILES)}: {report}")
        check("1b and not one line of it reaches the bookkeeping bucket",
              lines.get("process") == 0, f"process={lines.get('process')}: "
              f"{report.get('largest_process_files')}")
        check("1c so a commit of pure domain code cannot breach",
              report.get("breach") is False, str(report.get("verdict")))


def case_workspace_artifacts_are_still_process() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = build(Path(td), PROCESS_FILES)
        report = measure(repo)
        lines = report.get("lines", {})
        check("2a a verdict under a workspace root is still bookkeeping",
              lines.get("process") == len(PROCESS_FILES),
              f"process={lines.get('process')} of {len(PROCESS_FILES)}: {report}")
        check("2b even though its path contains `plans/`, which would otherwise be thinking",
              lines.get("product_think") == 0, f"product_think={lines.get('product_think')}")
        check("2c and none of it is credited to product",
              lines.get("product") == 0, f"product={lines.get('product')}")


def case_a_breach_names_the_files() -> None:
    """A budget that only scolds cannot be acted on."""
    with tempfile.TemporaryDirectory() as td:
        heavy = {**PROCESS_FILES}
        heavy[".superpowers/sdd/plans/verdicts/TC-02-r1-reviewer.md"] = "line\n" * 200
        repo = build(Path(td), heavy)
        report = measure(repo)
        largest = report.get("largest_process_files") or []
        check("3a the report names the largest process files", bool(largest), str(report)[:300])
        if not largest:
            return
        check("3b the biggest one is first, so the reader knows where to start",
              largest[0]["path"].endswith("TC-02-r1-reviewer.md"), str(largest[:2]))
        check("3c with its line count, not just its name",
              largest[0].get("lines") == 200, str(largest[0]))


def main() -> int:
    if not SCRIPT.exists():
        print(f"ratio_meter.py not found at {SCRIPT}", file=sys.stderr)
        return 2
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("git is not available; this break-test reads committed history", file=sys.stderr)
        return 2

    print("ratio_meter break-test")
    for case in (case_ambiguous_names_on_source_files_are_product,
                 case_workspace_artifacts_are_still_process, case_a_breach_names_the_files):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — source beats an ambiguous name, and a workspace root beats everything")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
