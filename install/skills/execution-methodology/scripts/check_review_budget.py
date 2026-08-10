#!/usr/bin/env python3
"""Review-budget check (methodology v3.0, draft).

Run by the orchestrator BEFORE every review dispatch, against the plan workspace:

    check_review_budget.py WORKSPACE_DIR [--max-round 2] [--json]

Errors (exit 1) — the dispatch must not proceed:
  * ROUND_CAP     — any subject carries a round marker above --max-round. Round three does
                    not exist; the subject escalates to its gate instead.
  * BANNED_CLASS  — a banned artifact class is present: .diff snapshots, restatement
                    packets, or files recording a dispatch that produced nothing
                    (invalid-attempt / no-verdict / no-progress). Those are ledger lines.

Warnings (exit 0, reported) — process-regression signals for the milestone receipt:
  * WORKSPACE_BUDGET — workspace exceeds ~50 files or ~500 KB.

The subject is the artifact, not its filename: round markers are stripped before grouping,
so `S2-01-R18.md`, `S2-01-round18.md` and `S2-01-fixround3-rereview.md` are one subject.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROUND_RE = re.compile(
    r"[-_.](?:r|round|fixround|rereview[-_.]?r|attempt)0*(\d+)(?=[-_.]|$)", re.IGNORECASE
)
BANNED_PATTERNS = (
    (re.compile(r"\.diff$", re.IGNORECASE), "diff snapshot — name the commit range instead"),
    (re.compile(r"-packet\.md$", re.IGNORECASE), "restatement packet — re-dispatch with the original paths"),
    (re.compile(r"invalid[-_]?attempt", re.IGNORECASE), "failed dispatch — one ledger line"),
    (re.compile(r"no[-_]?verdict", re.IGNORECASE), "failed dispatch — one ledger line"),
    (re.compile(r"no[-_]?progress", re.IGNORECASE), "failed dispatch — one ledger line"),
)
FILE_BUDGET = 50
BYTE_BUDGET = 500 * 1024


def subject_of(name: str) -> str:
    """Everything before the first round marker is the subject.

    Real lineages name the round then qualify it (`S2-01-R18-R1`, `T6b-round5-rereview`), so the
    tail after the first marker is round-specific and must not split the subject.
    """
    stem = Path(name).stem
    m = ROUND_RE.search(stem)
    if m:
        stem = stem[: m.start()]
    return stem.strip("-_.").lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--max-round", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.workspace.is_dir():
        print(f"ERROR: not a directory: {args.workspace}", file=sys.stderr)
        return 2

    errors, warnings = [], []
    rounds: dict[str, tuple[int, str]] = {}
    n_files, n_bytes = 0, 0

    for path in sorted(args.workspace.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(args.workspace))
        n_files += 1
        n_bytes += path.stat().st_size

        for pattern, why in BANNED_PATTERNS:
            if pattern.search(path.name):
                errors.append({"kind": "BANNED_CLASS", "path": rel, "why": why})
                break

        for m in ROUND_RE.finditer(path.name):
            rnd = int(m.group(1))
            subj = subject_of(path.name)
            if rnd > rounds.get(subj, (0, ""))[0]:
                rounds[subj] = (rnd, rel)

    for subj, (rnd, rel) in sorted(rounds.items()):
        if rnd > args.max_round:
            errors.append({
                "kind": "ROUND_CAP", "subject": subj, "round": rnd, "path": rel,
                "why": f"round {rnd} exceeds the budget of {args.max_round}; "
                       "escalate to the owning gate — do not dispatch",
            })

    if n_files > FILE_BUDGET or n_bytes > BYTE_BUDGET:
        warnings.append({
            "kind": "WORKSPACE_BUDGET", "files": n_files, "bytes": n_bytes,
            "why": f"workspace at {n_files} files / {n_bytes // 1024} KB exceeds "
                   f"~{FILE_BUDGET} files / {BYTE_BUDGET // 1024} KB — record as a "
                   "process regression in the milestone receipt",
        })

    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings,
                          "files": n_files, "bytes": n_bytes}, indent=2))
    else:
        for f in errors:
            print(f"ERROR   {f['kind']:16} {f.get('path', '')}  {f['why']}")
        for f in warnings:
            print(f"WARNING {f['kind']:16} {f['why']}")
        if not errors and not warnings:
            print(f"clean: {n_files} files, {n_bytes // 1024} KB, "
                  f"no subject past round {args.max_round}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
