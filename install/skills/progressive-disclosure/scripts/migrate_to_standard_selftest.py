#!/usr/bin/env python3
"""Break-test for migrate_to_standard.py — proves the one tool licensed to WRITE fails safely.

THIS SCRIPT HAD NO SELFTEST AND NO TEST MODULE OF ITS OWN before this file. Stated plainly because
the gap is the finding: `migrate_to_standard.py` is the only script in this toolchain that renames
files and rewrites their contents, and it was the only writing script with nothing that had watched
it fail. Cases 1 and 2 below both reproduce behaviour that was LIVE in the shipped file.

  1  a moved file's link to a neighbour that did NOT move   resolves after --apply
     <- LIVE DEFECT. `rewrite_links` asked only "did the TARGET move", so a runbook rising from
        `docs/` to `docs/runbooks/` kept `architecture/design.md` and pointed at nothing.
  2  the same, in --product mode, at corpus scale            resolves after --apply
  3  a dry run                                               writes NOTHING, byte for byte
  4  --product never edits PROSE                             every body diff is a link target,
                                                             and the body word count is unchanged
  5  an H1 with no derivable feature id                      SKIPPED whole and reported
  6  a `prd:` that resolves to nothing                       written as TODO, never guessed
  7  the area id survives                                    in the filename AND in the title
  8  README.md / plan.md siblings, and files outside docs/   never proposed for rename
  9  --apply on a dirty tree without --force                 exit 1, and nothing moved

WHAT THESE CASES DO NOT COVER, said plainly because an overstated coverage claim in a break-test is
the same failure the tool has: none of them run against a real repository. The real-corpus numbers
(64 renames, 140 relinks, 102,901 body words before and after, 1,254 links and 0 broken, spec_check
0 -> 64 documents read) were measured by hand on a COPY of one repository and are NOT asserted here.
Case 9 checks the refusal, not the backup: the backup path is exercised by every --apply case
above it, but no case asserts that the backup is RESTORABLE. That is untested.

Run:  python3 migrate_to_standard_selftest.py     (exit 0 = every case passes)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MIGRATOR = Path(__file__).resolve().parent / "migrate_to_standard.py"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(name.split()[0])
        if detail:
            print(f"        {detail}")


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def new_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.email", "selftest@example.invalid", cwd=repo)
    sh("git", "config", "user.name", "selftest", cwd=repo)
    return repo


def write(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def commit(repo: Path, message: str = "fixture") -> None:
    sh("git", "add", ".", cwd=repo)
    sh("git", "commit", "-qm", message, cwd=repo)


def run(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(MIGRATOR), ".", *args],
                          cwd=repo, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and ".git/" not in
            p.relative_to(root).as_posix()}


SPEC = """# FED-C1 — Health-only ingestion boundary

Product spec: [../feed.md](../feed.md)
Status: draft

## Why

Only health content may enter the feed.

See the [plan](plan.md) and the [ranking spec](../fed-c5-ranking/spec.md).

## Horizontals

| Concern | Disposition |
| --- | --- |
| Privacy | owned here |
"""


def case_source_move_relinks_a_stationary_target() -> None:
    """The live defect, in the migrator's OWN shipped move set — no product mode involved."""
    print("1  a moved file's link to a neighbour that did not move")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/RUNBOOK-deploy.md",
              "# Deploy runbook\n\nSee [the design](architecture/design.md).\n")
        write(repo, "docs/architecture/design.md", "# Design\n")
        commit(repo)
        code, out = run(repo, "--apply", "--no-create")
        moved = repo / "docs" / "runbooks" / "runbook-deploy.md"
        check("1a the move happened", code == 0 and moved.is_file(), f"exit {code}: {out[:300]}")
        text = moved.read_text(encoding="utf-8") if moved.is_file() else ""
        check("1b the link was rewritten", "../architecture/design.md" in text, text[:200])
        # Resolve the link AS WRITTEN, from the file's NEW directory. An earlier version of this
        # case resolved a hardcoded path instead and passed under the very mutation it exists to
        # catch — a break-test that cannot fail is the defect it is testing for.
        written = re.findall(r"\]\(([^)]+)\)", text)
        check("1c and every link in it resolves from its new directory",
              bool(written) and all((moved.parent / t).resolve().exists() for t in written),
              f"{written} from {moved.parent}")


def case_product_move_relinks() -> None:
    print("2  --product: links out of a spec that rose a directory")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/feed.md", "# Feed\n")
        write(repo, "docs/product/specs/fed-c1-health-only/spec.md", SPEC)
        write(repo, "docs/product/specs/fed-c1-health-only/plan.md",
              "# Plan — FED-C1\n\nSee [the spec](spec.md).\n")
        write(repo, "docs/product/specs/fed-c5-ranking/spec.md",
              "# FED-C5 — Ranking\n\nProduct spec: [../feed.md](../feed.md)\nStatus: draft\n")
        commit(repo)
        code, out = run(repo, "--product", "--apply")
        check("2a exit 0", code == 0, f"exit {code}: {out[-600:]}")
        check("2b the plan reported 0 broken links after the move",
              "links        checked" in out and "broken 0" in out.replace("  ", " ") or
              "broken 0" in out, out[-500:])
        spec = repo / "docs/product/specs/F-1-fed-c1-health-only.md"
        check("2c the spec landed at a bound name", spec.is_file(), str(spec))
        text = spec.read_text(encoding="utf-8") if spec.is_file() else ""
        for target in ("feed.md", "fed-c1-health-only/plan.md", "F-2-fed-c5-ranking.md"):
            resolved = (spec.parent / dict(
                (t, t) for t in ()).get(target, target)).resolve() if spec.is_file() else Path("/")
            check(f"2d link `{target}` is present and resolves",
                  target in text and resolved.exists(), f"{target!r} in text={target in text}")
        sibling = repo / "docs/product/specs/fed-c1-health-only/plan.md"
        sib_text = sibling.read_text(encoding="utf-8")
        check("2e the plan's link INTO the moved spec was repointed",
              "../F-1-fed-c1-health-only.md" in sib_text, sib_text)


def case_dry_run_writes_nothing() -> None:
    print("3  a dry run writes nothing")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/feed.md", "# Feed\n")
        write(repo, "docs/product/specs/fed-c1-health-only/spec.md", SPEC)
        write(repo, "docs/RUNBOOK-deploy.md", "# Deploy\n")
        commit(repo)
        before = snapshot(repo)
        code_p, out_p = run(repo, "--product")
        code_s, out_s = run(repo)
        after = snapshot(repo)
        check("3a both modes exit 0", code_p == 0 and code_s == 0, f"{code_p} {code_s}")
        check("3b both said DRY RUN", "DRY RUN" in out_p and "DRY RUN" in out_s, out_p[-200:])
        check("3c the tree is byte-for-byte unchanged", before == after,
              str(set(before) ^ set(after)))


def case_never_edits_a_body() -> None:
    print("4  --product never edits a body")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/feed.md", "# Feed\n")
        original = write(repo, "docs/product/specs/fed-c1-health-only/spec.md",
                         "# FED-C1 — Health-only\n\nProduct spec: [../feed.md](../feed.md)\n"
                         "Status: draft\n\nProse that must not move.\n").read_text()
        commit(repo)
        code, out = run(repo, "--product", "--apply")
        moved = repo / "docs/product/specs/F-1-fed-c1-health-only.md"
        text = moved.read_text(encoding="utf-8")
        body = text.split("---\n", 2)[2].lstrip("\n")
        check("4a exit 0", code == 0, out[-400:])
        # NOT byte-identical, and asserting that would be a lie the first version of this case told.
        # A file that rises a directory has its own relative links re-rendered — `../feed.md` becomes
        # `feed.md` — and that IS a body edit. The honest invariant is the one the hand migration
        # used and the one the tool prints: the WORD COUNT does not move, and every difference is
        # inside a link target. Prose is untouched; link targets are the point of the move.
        blind = re.compile(r"\]\([^)]*\)")
        check("4b every body difference is inside a link target",
              blind.sub("](@)", body) == blind.sub("](@)", original),
              repr(blind.sub("](@)", body)[:140]))
        check("4c the body word count is unchanged",
              len(body.split()) == len(original.split()),
              f"{len(body.split())} != {len(original.split())}")
        check("4d and the tool said so", "IDENTICAL" in out, out[-400:])


def case_refuses_an_underivable_id() -> None:
    print("5  an H1 with no derivable feature id")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/met-metric-tree/spec.md",
              "# MET — Metric tree and guardrails\n\nStatus: draft\n")
        commit(repo)
        before = snapshot(repo)
        code, out = run(repo, "--product", "--apply")
        check("5a it is not migrated", snapshot(repo) == before, out[-400:])
        check("5b it is REPORTED, not silently dropped",
              "NOT MIGRATED" in out and "met-metric-tree/spec.md" in out
              and "no feature id in the H1" in out, out[-500:])
        check("5c and no F-<n> file was invented",
              not list((repo / "docs/product/specs").glob("F-*.md")))


def case_refuses_an_unresolvable_prd() -> None:
    print("6  a prd that resolves to nothing")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        # The real case: the top-level product document is a .docx, and the spec names no markdown
        # parent. Nothing resolves, so nothing may be written.
        write(repo, "docs/product/product-brief-v1.docx", "not markdown")
        write(repo, "docs/product/specs/fed-c1-health-only/spec.md",
              "# FED-C1 — Health-only\n\nStatus: draft\n\nBody.\n")
        commit(repo)
        code, out = run(repo, "--product", "--apply")
        moved = repo / "docs/product/specs/F-1-fed-c1-health-only.md"
        text = moved.read_text(encoding="utf-8") if moved.is_file() else ""
        check("6a the document still migrated", moved.is_file(), out[-400:])
        check("6b prd is TODO, not a guessed path", "prd: TODO" in text, text[:200])
        check("6c the .docx was NOT claimed as the parent", "docx" not in text, text[:200])
        check("6d and the refusal is printed with its reason",
              "REFUSED TO DERIVE" in out and "names no parent" in out, out[:900])


def case_area_id_survives() -> None:
    print("7  the area id survives the rename")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/feed.md", "# Feed\n")
        write(repo, "docs/product/specs/fed-c1-health-only/spec.md", SPEC)
        commit(repo)
        code, out = run(repo, "--product", "--apply")
        moved = repo / "docs/product/specs/F-1-fed-c1-health-only.md"
        text = moved.read_text(encoding="utf-8") if moved.is_file() else ""
        check("7a the filename still carries the area id",
              moved.is_file() and "fed-c1" in moved.name, str(moved))
        check("7b the title still carries it verbatim",
              'title: "FED-C1 — Health-only ingestion boundary"' in text, text[:200])
        check("7c and the machine id is the one ID_RE accepts", "id: F-1\n" in text, text[:200])


def case_leaves_everything_else_alone() -> None:
    print("8  indexes, plans and anything outside docs/")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/README.md", "# FED-C1 — index\n")
        write(repo, "docs/product/specs/fed-c1-health-only/plan.md", "# Plan — FED-C1 thing\n")
        write(repo, "docs/product/specs/fed-c1-health-only/README.md", "# FED-C1 — readme\n")
        write(repo, "specs/FED-C1.md", "# FED-C1 — outside docs\n")
        commit(repo)
        before = snapshot(repo)
        code, out = run(repo, "--product", "--apply")
        check("8a nothing was proposed", "spec-shaped and bound by nothing: 0" in out, out[:500])
        check("8b nothing was written", snapshot(repo) == before)
        check("8c nothing outside docs/ is named", "specs/FED-C1.md" not in out, out[:500])


def case_dirty_tree_refused() -> None:
    print("9  --apply on a dirty tree without --force")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/product/specs/feed.md", "# Feed\n")
        write(repo, "docs/product/specs/fed-c1-health-only/spec.md", SPEC)
        commit(repo)
        write(repo, "docs/product/specs/dirt.md", "# dirt\n")
        before = snapshot(repo)
        code, out = run(repo, "--product", "--apply")
        check("9a exit 1", code == 1, f"exit {code}: {out[-300:]}")
        check("9b it says REFUSED and names the remedy",
              "REFUSED" in out and "--force" in out, out[-300:])
        check("9c and it moved nothing", snapshot(repo) == before)


def main() -> int:
    if not MIGRATOR.exists():
        print(f"migrate_to_standard.py not found at {MIGRATOR}", file=sys.stderr)
        return 2
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CONFIG_SYSTEM"] = os.devnull
    print("migrate_to_standard break-test")
    for case in (case_source_move_relinks_a_stationary_target, case_product_move_relinks,
                 case_dry_run_writes_nothing, case_never_edits_a_body,
                 case_refuses_an_underivable_id, case_refuses_an_unresolvable_prd,
                 case_area_id_survives, case_leaves_everything_else_alone,
                 case_dirty_tree_refused):
        case()
    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the migrator plans, refuses and writes the way every case demands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
