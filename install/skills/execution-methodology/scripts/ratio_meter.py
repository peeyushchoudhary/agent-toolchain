#!/usr/bin/env python3
"""Meter committed line churn against the process-cost budget, read from git's own numstat.

Principle 8 sets a process-cost budget and calls a breach a "process regression". Nothing computed
it, so nothing ever fired. Measured over eight weeks in one repository running this methodology:
the bookkeeping-to-product line ratio moved from 0.04 to 2.96 while product output fell by more
than an order of magnitude, and every gate in the pipeline stayed green throughout. A budget with
no meter is a sentence in a document, not a budget.

## Why this one binds when the review-round budget does not

`check_review_budget.py` was reclassified advisory on the ruling that "the tool is run by the party
it binds": it reads a workspace directory that the same party writes, so the party can satisfy it
by renaming its own files. That ruling is correct and it is not repaired by adding checks.

This meter is not run against a workspace. It reads `git log --numstat` over a committed range, so
the product side of the ratio is line churn in source files that exist in history. The ratio can be
improved in exactly two ways: write less bookkeeping, or write more product code. The second one is
the thing the budget wants. There is no third move that does not involve committing real code, and
that — not a stricter check — is what makes this measurement binding.

WHAT IT STILL DOES NOT ESTABLISH, stated here rather than left to be discovered. Churn is a
quantity, never a quality: a thousand lines of generated boilerplate outrank a ten-line fix, and
nothing here can tell them apart. The meter says how the effort was DISTRIBUTED, and it is honest
about that being a different question from whether the effort was any good.

## Classification is by path only, and PROCESS wins ties

A path is tested against the exclusion list first, then PROCESS, then PRODUCT_THINK, then PRODUCT.
The ordering is the conservative one for a binding meter: the failure that matters is a process
breach that goes unreported, so an ambiguous path is charged to process rather than credited to
product. A file cannot be moved out of the process bucket by naming it `docs/product/…`.

The cost of that ordering is real and is named rather than hidden. `src/reports/ReportService.java`
matches the `/reports/` bookkeeping segment and is charged to PROCESS; so is any product file whose
name contains `receipt`. That is why a breach prints the five largest process files by churn
instead of only a verdict: a false positive is then visible in one line of output and can be
argued with, rather than sitting inside an aggregate nobody can decompose.

Matching is case-insensitive throughout. `LEDGER.md` and `ledger.md` are the same bookkeeping file
to everyone except a case-sensitive substring test.

## The cleanup exemption

Deleting bookkeeping is process churn — the lines were touched and the time was spent — so
deletions count into the process bucket exactly like additions. A commit that ONLY deletes process
files is different in kind: it is the budget being repaid. Such a commit is reported as `cleanup`,
its churn is kept out of the ratio's denominator, and it can never cause a breach. Punishing
somebody for removing bookkeeping would make the meter argue against its own purpose.

Usage:
  ratio_meter.py --range main..HEAD                     # any range git log accepts
  ratio_meter.py --since 2026-08-14                     # any date git log accepts
  ratio_meter.py --range main..HEAD --repo PATH         # default: the current directory
  ratio_meter.py --since 2026-08-14 --json              # machine-readable
  ratio_meter.py --range main..HEAD --ceiling 0.15      # default 0.10

Exit codes: 0 within budget, 1 BREACH — the process share is over the ceiling, 2 the arguments or
the repository could not be used. The product floor is advisory and never reaches the exit code:
one number decides the verdict, so there is no argument about which one did.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple, Optional

PRODUCT = "product"
PRODUCT_THINK = "product_think"
PROCESS = "process"
OTHER = "other"
EXCLUDED = "excluded"

# The three buckets the ratio is computed over. OTHER is measured and reported but is not in the
# denominator: it is churn the model has no opinion about, and letting it dilute the process share
# would make the budget easier to meet by committing files nobody classified.
RATIO_BUCKETS = (PRODUCT, PRODUCT_THINK, PROCESS)
BUCKETS = (PRODUCT, PRODUCT_THINK, PROCESS, OTHER)

# Two thresholds, because one number cannot both catch drift early and be worth failing a merge
# over. Calibrated against 36 project-weeks of real history: the median week runs 0.081, and the
# bands sit at p61 and p76 of that distribution. Back-tested against the collapse this budget
# exists to prevent, WARN fires in the first week of the inversion and FAIL in the week product
# output fell 97% — while no healthy week (0.00-0.03) trips either.
WARN_CEILING = 0.15
DEFAULT_CEILING = 0.30

# Below this many classified lines the ratio is noise and only reports. A brand-new repository
# whose first commit is a PRD reads 0.17, and a week holding one bug fix and its distillation reads
# 0.26 — both would fail a 0.10 gate on a handful of bookkeeping lines. A budget that fires on a
# quiet week teaches its operator to ignore it, which is the failure mode this whole instrument
# exists to avoid.
MIN_CLASSIFIED_LINES = 500

# Advisory only, and deliberately not a gate. Product definition is wanted, not tolerated: a
# repository writing its PRD and feature specs has a low product share BY DESIGN, and that is a
# healthy week for a project in definition. Nothing here may block it.
PRODUCT_FLOOR = 0.70

# Generated and vendored output. Excluded entirely rather than bucketed, and reported separately so
# the exclusion is visible: a vendored tree can outweigh every hand-written line in a range, and
# whichever bucket it landed in would decide the verdict on its own.
EXCLUDED_SEGMENTS = ("node_modules", "dist", "build", "target", ".venv", "vendor",
                     "graphify-out", "__pycache__")
EXCLUDED_SUFFIXES = (".lock", ".gen.ts")
EXCLUDED_NAMES = ("package-lock.json",)

PRODUCT_SUFFIXES = (".java", ".kt", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts",
                    ".cts", ".py", ".go", ".rs", ".swift", ".rb", ".php", ".cs", ".c", ".h",
                    ".cpp", ".hpp", ".m", ".sql", ".css", ".scss", ".less", ".html", ".vue",
                    ".svelte", ".sh", ".bash", ".zsh", ".tf", ".tfvars", ".yaml", ".yml", ".toml")
# The subset of PRODUCT_SUFFIXES that compiles or executes. Only these outrank an ambiguous
# bookkeeping word, because the data and config formats are exactly what bookkeeping is written in:
# a task card is `.yaml`, a register is `.tsv`, a ledger is `.md`. An API contract is `.yaml` too,
# and it must stay reachable by the product-thinking rules rather than being claimed here.
CODE_SUFFIXES = tuple(s for s in PRODUCT_SUFFIXES
                      if s not in (".yaml", ".yml", ".toml"))

PRODUCT_NAMES = ("package.json", "pom.xml", "cargo.toml", "pyproject.toml")
PRODUCT_NAME_PREFIXES = ("build.gradle", "dockerfile", "docker-compose", "requirements")
PRODUCT_SEQUENCES = ("/.github/workflows/",)

PRODUCT_THINK_SEQUENCES = ("/docs/product/", "/docs/architecture/", "/docs/decisions/",
                           "/docs/runbooks/", "/specs/", "/design/")

# Checked BEFORE process, and the only sequences that are. Principle 8 names the exception itself:
# process is "workspace, ledger, verdicts, cards, escalations — not product specs or design
# documents, which are product thinking". A plan is a design document, and plans are conventionally
# filed under a process-shaped parent such as docs/superpowers/plans/. Charging them to process
# read the best-measured repository in the fleet at a 0.45 share on plans alone, which is the
# false positive that teaches an operator to ignore the meter. `/design/` is here for the same
# reason and cost the same way: a directory of UI mockups filed as `design/<x>/cards/` is design
# work, and `/cards/` alone charged 63,000 lines of it to bookkeeping.
PRODUCT_THINK_OVERRIDE_SEQUENCES = ("/plans/", "/design/")
PRODUCT_THINK_NAMES = ("readme.md",)
PRODUCT_THINK_NAME_PREFIXES = ("openapi",)
PRODUCT_THINK_SUBSTRINGS = ("prd",)

# Bookkeeping, in three strengths, because "process" is also an ordinary product vocabulary.
#
# STRONG sequences are directories that exist only to hold bookkeeping. Nothing inside them is
# product, including a script — tooling that serves the workspace is still workspace cost.
#
# WEAK sequences and SUBSTRINGS are words a product legitimately uses. `cards` is a task card and
# also a loyalty card; `reports` is a review essay and also a reporting feature; `receipt` is a
# milestone receipt and also a consent receipt, a payment receipt, and a goods-receipt screen.
# Against a source file these lose, because bookkeeping is prose and data — it is never compiled or
# executed. Measured across four adopting repositories before this rule existed, the ambiguity
# charged 16,429 lines of domain code to process: ConsentReceipts.java, GoodsReceiptScreen.tsx,
# validation_receipt_v3.py, and a whole com/…/cards/ package whose subject is health cards.
#
# A SEQUENCE must appear as whole path segments, so `/cards/` cannot be matched by `flashcards.md`;
# a SUBSTRING matches anywhere, because those names are the artifacts themselves wherever they sit.
# STRONG roots outrank even the product-thinking overrides: a workspace directory is bookkeeping
# whatever is filed inside it. `/docs/superpowers/` is deliberately NOT here — it is a docs tree
# that legitimately holds implementation plans and designs, so it must stay beatable by `/plans/`.
# The dot-prefixed `/.superpowers/` workspace is the opposite and stays strong.
PROCESS_STRONG_SEQUENCES = ("/.superpowers/", "/sdd/", "/docs/agents/",
                            "/verdicts/", "/workspace/", "/escalations/")
PROCESS_WEAK_SEQUENCES = ("/cards/", "/reports/", "/docs/superpowers/")
PROCESS_SUBSTRINGS = ("deferral", "progress.md", "ledger.md", "lessons.md", "receipt",
                      "agents.md", "claude.md", "methodology.md", "personas")
PROCESS_SUFFIXES = (".diff",)

# git renders a rename inside numstat as `old => new`, or with a shared prefix and suffix factored
# out as `pre/{old => new}/post`. Both are ONE path in the output and neither is the path that now
# exists, so both are resolved to the destination before classification. A rename that is not
# resolved is classified under the name the file used to have, which is how a bookkeeping file that
# moved into a source tree keeps counting as source.
BRACE_RENAME_RE = re.compile(r"^(?P<pre>.*)\{(?P<old>[^{}]*) => (?P<new>[^{}]*)\}(?P<post>.*)$")
RECORD = "\x1e"


class MeterError(Exception):
    pass


class FileChurn(NamedTuple):
    path: str
    bucket: str
    added: int
    deleted: int
    binary: bool

    @property
    def lines(self) -> int:
        return self.added + self.deleted


class Commit(NamedTuple):
    sha: str
    date: str
    files: tuple[FileChurn, ...]

    @property
    def counted(self) -> tuple[FileChurn, ...]:
        return tuple(f for f in self.files if f.bucket != EXCLUDED)

    @property
    def is_cleanup(self) -> bool:
        """A commit that only removes bookkeeping. Exempt from the breach test — see the header.

        Three conditions, all of them necessary. Every counted file is PROCESS, so a commit that
        deletes bookkeeping AND touches anything else is an ordinary commit. Nothing was added, so
        a rewrite is not a cleanup. Something was actually deleted, so an empty or binary-only
        commit does not acquire the exemption by having no lines to disqualify it.
        """
        counted = self.counted
        return (bool(counted)
                and all(f.bucket == PROCESS for f in counted)
                and sum(f.added for f in counted) == 0
                and sum(f.deleted for f in counted) > 0)


class Tally(NamedTuple):
    lines: dict[str, int]
    files: dict[str, int]
    cleanup_lines: int
    cleanup_files: int
    cleanup_commits: int
    excluded_lines: int
    excluded_files: int
    binary_files: int
    commits: int
    process_churn: Counter


def rename_destination(field: str) -> str:
    """The path a numstat field refers to after any rename notation is resolved."""
    if " => " not in field:
        return field
    match = BRACE_RENAME_RE.match(field)
    if match:
        joined = match.group("pre") + match.group("new") + match.group("post")
        # `docs/{ => sub}/x.md` and `docs/{sub => }/x.md` both leave a doubled or trailing
        # separator behind when one side of the rename is empty.
        return re.sub(r"/{2,}", "/", joined).strip("/")
    return field.split(" => ", 1)[1]


def normalise(path: str) -> str:
    """The path as the matchers see it: lower-cased and slash-delimited at both ends.

    The sentinel slashes are what let a segment test be a plain substring test. Without them
    `/cards/` would never match a path that starts with `cards/`, which is every path in a
    repository whose bookkeeping sits at the root.
    """
    return "/" + path.strip("/").lower() + "/"


def is_excluded(path: str) -> bool:
    norm = normalise(path)
    name = norm.rstrip("/").rsplit("/", 1)[-1]
    return (any(f"/{segment}/" in norm for segment in EXCLUDED_SEGMENTS)
            or any(name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)
            or name in EXCLUDED_NAMES)


def classify(path: str) -> str:
    """One of PRODUCT, PRODUCT_THINK, PROCESS, OTHER, EXCLUDED. Path only; contents are never read.

    Order is the whole design: exclusion, then process, then product thinking, then product. See
    the module header for why an ambiguous path is charged to process rather than credited to
    product, and for what that costs.
    """
    norm = normalise(path)
    name = norm.rstrip("/").rsplit("/", 1)[-1]
    if is_excluded(path):
        return EXCLUDED
    # Bookkeeping ROOTS win first, and they win over everything. A directory that exists only to
    # hold workspace, ledger, and verdicts is bookkeeping whatever is filed inside it — including a
    # subdirectory called `plans/` or `design/`. The opposite ordering shipped for one day and put
    # `.superpowers/sdd/plans/verdicts/TC-01-r1-reviewer.md` in product thinking, which is the
    # exact artifact class the budget exists to bound.
    if any(sequence in norm for sequence in PROCESS_STRONG_SEQUENCES):
        return PROCESS
    if any(sequence in norm for sequence in PRODUCT_THINK_OVERRIDE_SEQUENCES):
        return PRODUCT_THINK
    # Source beats an ambiguous name. Everything below this line is a word a product may own, and a
    # file that compiles or runs is product whatever it is called. CODE_SUFFIXES rather than
    # PRODUCT_SUFFIXES is the whole precision here: a task card is `.yaml` and an API contract is
    # `.yaml`, so the data formats must stay claimable by the rules below.
    if any(name.endswith(suffix) for suffix in CODE_SUFFIXES):
        return PRODUCT
    if (any(sequence in norm for sequence in PROCESS_WEAK_SEQUENCES)
            or any(token in norm for token in PROCESS_SUBSTRINGS)
            or any(name.endswith(suffix) for suffix in PROCESS_SUFFIXES)):
        return PROCESS
    if (any(sequence in norm for sequence in PRODUCT_THINK_SEQUENCES)
            or name in PRODUCT_THINK_NAMES
            or any(name.startswith(prefix) for prefix in PRODUCT_THINK_NAME_PREFIXES)
            or any(token in name for token in PRODUCT_THINK_SUBSTRINGS)):
        return PRODUCT_THINK
    if (any(name.endswith(suffix) for suffix in PRODUCT_SUFFIXES)
            or name in PRODUCT_NAMES
            or any(name.startswith(prefix) for prefix in PRODUCT_NAME_PREFIXES)
            or any(sequence in norm for sequence in PRODUCT_SEQUENCES)):
        return PRODUCT
    return OTHER


def git_log(repo: Path, arguments: list[str]) -> str:
    """Run one `git log --numstat` invocation and return its stdout, or raise MeterError.

    `core.quotePath=false` is set for the run rather than assumed: with it left at the default git
    C-quotes any path outside ASCII, and the classifier would then be reading an escape sequence
    instead of a filename.
    """
    command = ["git", "-C", str(repo), "-c", "core.quotePath=false", "log", "--numstat",
               "--find-renames", f"--format={RECORD}%H%x1f%cI", *arguments]
    try:
        completed = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        raise MeterError(f"cannot run git in {repo}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        first = detail[0] if detail else "no reason given"
        # THE ONE GIT FAILURE THAT IS AN ANSWER. A repository whose branch has no commits yet exits
        # 128 with this message, and the honest reading of it is "no churn", not "unreadable". It is
        # matched on the message rather than on the exit code, which every other git failure shares,
        # and it is the only such case: anything else stays an error, because a meter that turns
        # failures into empty measurements reports a clean budget for a repository it never read.
        if "does not have any commits yet" in first:
            return ""
        raise MeterError(f"git log failed in {repo}: {first}")
    return completed.stdout


def parse_log(output: str) -> list[Commit]:
    commits: list[Commit] = []
    for block in output.split(RECORD):
        if not block.strip():
            continue
        head, _, body = block.partition("\n")
        sha, _, date = head.partition("\x1f")
        files: list[FileChurn] = []
        for line in body.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                # numstat is three tab-separated fields per file. Anything else is a shape this
                # parser does not understand, and a silently dropped file is a silently smaller
                # process bucket.
                raise MeterError(f"unparseable numstat line for {sha[:12]}: {line!r}")
            raw_added, raw_deleted, raw_path = parts
            binary = raw_added == "-" or raw_deleted == "-"
            path = rename_destination(raw_path)
            files.append(FileChurn(
                path=path,
                bucket=classify(path),
                added=0 if binary else int(raw_added),
                deleted=0 if binary else int(raw_deleted),
                binary=binary,
            ))
        commits.append(Commit(sha=sha.strip(), date=date.strip(), files=tuple(files)))
    return commits


def collect(repo: Path, *, revision_range: Optional[str] = None, since: Optional[str] = None,
            until: Optional[str] = None) -> list[Commit]:
    arguments: list[str] = []
    if since is not None:
        arguments.append(f"--since={since}")
    if until is not None:
        arguments.append(f"--until={until}")
    if revision_range is not None:
        arguments.append(revision_range)
    # The `--` terminator stops git resolving a mistyped range as a pathspec and reporting nothing
    # rather than failing: an empty report and a wrong argument must not look alike.
    return parse_log(git_log(repo, arguments + ["--"]))


def tally(commits: list[Commit]) -> Tally:
    lines = {bucket: 0 for bucket in BUCKETS}
    files = {bucket: 0 for bucket in BUCKETS}
    cleanup_lines = cleanup_files = cleanup_commits = 0
    excluded_lines = excluded_files = binary_files = 0
    process_churn: Counter = Counter()
    for commit in commits:
        cleanup = commit.is_cleanup
        cleanup_commits += cleanup
        for churn in commit.files:
            if churn.binary:
                binary_files += 1
            if churn.bucket == EXCLUDED:
                excluded_lines += churn.lines
                excluded_files += 1
                continue
            if cleanup:
                cleanup_lines += churn.lines
                cleanup_files += 1
                continue
            lines[churn.bucket] += churn.lines
            files[churn.bucket] += 1
            if churn.bucket == PROCESS:
                process_churn[churn.path] += churn.lines
    return Tally(lines=lines, files=files, cleanup_lines=cleanup_lines,
                 cleanup_files=cleanup_files, cleanup_commits=cleanup_commits,
                 excluded_lines=excluded_lines, excluded_files=excluded_files,
                 binary_files=binary_files, commits=len(commits), process_churn=process_churn)


def shares(counted: Tally) -> tuple[int, Optional[float], Optional[float]]:
    """(denominator, process share, product share). The shares are None when nothing was measured.

    None rather than 0.0, and the distinction is the point: a range with no classified churn has
    no process share, and reporting one as 0.00 would let an empty range read as a clean result.
    """
    denominator = sum(counted.lines[bucket] for bucket in RATIO_BUCKETS)
    if denominator == 0:
        return 0, None, None
    return (denominator,
            counted.lines[PROCESS] / denominator,
            counted.lines[PRODUCT] / denominator)


def report(counted: Tally, ceiling: float, warn_ceiling: float = WARN_CEILING) -> dict[str, object]:
    denominator, process_share, product_share = shares(counted)
    # Under the volume floor the ratio still reports, but it cannot fail a merge. See
    # MIN_CLASSIFIED_LINES for why: at low volume the share is dominated by whichever handful of
    # lines happened to land in the range.
    thin = denominator < MIN_CLASSIFIED_LINES
    over_fail = process_share is not None and process_share > ceiling
    over_warn = process_share is not None and process_share > warn_ceiling
    breach = over_fail and not thin
    if breach:
        verdict = "BREACH"
    elif over_fail or over_warn:
        verdict = "WARN"
    else:
        verdict = "WITHIN BUDGET"
    return {
        "warn_ceiling": warn_ceiling,
        "min_classified_lines": MIN_CLASSIFIED_LINES,
        "below_volume_floor": thin,
        "warn": over_warn and not breach,
        "commits": counted.commits,
        "cleanup_commits": counted.cleanup_commits,
        "ratio_lines": denominator,
        "lines": dict(counted.lines),
        "files": dict(counted.files),
        "cleanup_lines": counted.cleanup_lines,
        "cleanup_files": counted.cleanup_files,
        "excluded_lines": counted.excluded_lines,
        "excluded_files": counted.excluded_files,
        "binary_files": counted.binary_files,
        "process_ceiling": ceiling,
        "process_share": process_share,
        "product_floor": PRODUCT_FLOOR,
        "product_share": product_share,
        "product_floor_met": product_share is not None and product_share >= PRODUCT_FLOOR,
        "breach": breach,
        "largest_process_files": [
            {"path": path, "lines": count}
            for path, count in counted.process_churn.most_common(5)
        ],
        "verdict": verdict,
    }


def contrast(value: float, reference: float) -> tuple[str, str]:
    """Render two shares at the least precision that still tells them apart.

    A share of 0.1004 against a ceiling of 0.10 printed as `0.10 is over the 0.10 ceiling`, which
    reads as a contradiction and invites the reader to distrust the verdict rather than the
    rounding. A verdict line may not print two numbers that its own sentence says differ and its
    own formatting says do not.
    """
    for precision in range(2, 7):
        left, right = f"{value:.{precision}f}", f"{reference:.{precision}f}"
        if left != right:
            return left, right
    return f"{value:.6f}", f"{reference:.6f}"


def render(payload: dict[str, object], scope: str) -> list[str]:
    lines: list[str] = [f"process-cost meter — {scope}", ""]
    lines.append(f"  {'bucket':<14}{'files':>7}{'lines':>9}{'share':>8}")
    denominator = payload["ratio_lines"]
    for bucket in RATIO_BUCKETS:
        count = payload["lines"][bucket]
        share = f"{count / denominator:8.2f}" if denominator else "      --"
        lines.append(f"  {bucket:<14}{payload['files'][bucket]:>7}{count:>9}{share}")
    lines.append(f"  {'-' * 36}")
    lines.append(f"  {'other':<14}{payload['files'][OTHER]:>7}{payload['lines'][OTHER]:>9}"
                 f"{'   n/a':>8}   not in the ratio")
    lines.append(f"  {'cleanup':<14}{payload['cleanup_files']:>7}{payload['cleanup_lines']:>9}"
                 f"{'   n/a':>8}   process deletions, exempt")
    lines.append(f"  {'excluded':<14}{payload['excluded_files']:>7}{payload['excluded_lines']:>9}"
                 f"{'   n/a':>8}   generated or vendored")
    lines.append("")
    lines.append(f"  {payload['commits']} commit(s), {payload['cleanup_commits']} cleanup-only, "
                 f"{payload['binary_files']} binary file(s) counted at 0 lines")
    ceiling = payload["process_ceiling"]
    process_share = payload["process_share"]
    if process_share is None:
        lines.append(f"  {'NO DATA':<8} no classified churn in this range — the {ceiling:.2f} "
                     "process ceiling was not tested")
        lines.append(f"  {'NO DATA':<8} product floor (advisory) — nothing to measure it against")
        return lines
    share_text, ceiling_text = contrast(process_share, ceiling)
    if payload["breach"]:
        lines.append(f"  {'BREACH':<8} process share {share_text} is over the "
                     f"{ceiling_text} ceiling — this is a process regression")
    else:
        lines.append(f"  {'WITHIN':<8} process share {share_text}, ceiling {ceiling_text}")
    floor = "MET" if payload["product_floor_met"] else "BELOW"
    product_text, floor_text = contrast(payload["product_share"], payload["product_floor"])
    lines.append(f"  {floor:<8} product share {product_text}, floor "
                 f"{floor_text} (advisory — never changes the exit code)")
    if payload["breach"]:
        lines.append("  largest process files by churn:")
        for item in payload["largest_process_files"]:
            lines.append(f"    {item['lines']:>7}  {item['path']}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--range", dest="revision_range",
                           help="any commit range git log accepts, e.g. main..HEAD")
    selection.add_argument("--since", help="any date git log accepts, e.g. 2026-08-14")
    parser.add_argument("--repo", default=".", help="repository to measure (default: cwd)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--ceiling", type=float, default=DEFAULT_CEILING,
                        help=f"process share that must not be exceeded (default {DEFAULT_CEILING})")
    args = parser.parse_args()

    if not 0.0 < args.ceiling <= 1.0:
        parser.error(f"--ceiling must be a share above 0 and at most 1, got {args.ceiling}")
    repo = Path(args.repo).expanduser()
    if not repo.is_dir():
        print(f"ERROR: not a directory: {repo}", file=sys.stderr)
        return 2
    try:
        commits = collect(repo, revision_range=args.revision_range, since=args.since)
    except MeterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = report(tally(commits), args.ceiling)
    scope = f"--range {args.revision_range}" if args.revision_range else f"--since {args.since}"
    payload["scope"] = scope
    payload["repo"] = str(repo)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("\n".join(render(payload, scope)))
    return 1 if payload["breach"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
