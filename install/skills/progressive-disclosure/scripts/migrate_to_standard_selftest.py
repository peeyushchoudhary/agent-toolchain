#!/usr/bin/env python3
"""Break-test for migrate_to_standard.py — proves the one tool licensed to WRITE fails safely.

`migrate_to_standard.py` is the only script in this toolchain that renames files and rewrites their
contents.

  1  a moved file's link to a neighbour that did NOT move   resolves after --apply
     <- a LIVE DEFECT once. `rewrite_links` asked only "did the TARGET move", so a runbook rising
        from `docs/` to `docs/runbooks/` kept `architecture/design.md` and pointed at nothing.
  2  a dry run                                               writes NOTHING, byte for byte
  3  --apply on a dirty tree without --force                 exit 1, and nothing moved

WHAT THESE CASES DO NOT COVER: none of them run against a real repository, and case 3 checks the
refusal, not the backup. No case asserts that the backup is RESTORABLE.

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


def case_source_move_relinks_a_stationary_target() -> None:
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
        # Resolve the link AS WRITTEN, from the file's NEW directory; a hardcoded path once passed
        # under the very mutation this case exists to catch.
        written = re.findall(r"\]\(([^)]+)\)", text)
        check("1c and every link in it resolves from its new directory",
              bool(written) and all((moved.parent / t).resolve().exists() for t in written),
              f"{written} from {moved.parent}")


def case_dry_run_writes_nothing() -> None:
    print("2  a dry run writes nothing")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/RUNBOOK-deploy.md", "# Deploy\n")
        commit(repo)
        before = snapshot(repo)
        code, out = run(repo)
        after = snapshot(repo)
        check("2a exit 0", code == 0, f"{code}")
        check("2b it said DRY RUN", "DRY RUN" in out, out[-200:])
        check("2c the tree is byte-for-byte unchanged", before == after,
              str(set(before) ^ set(after)))


def case_dirty_tree_refused() -> None:
    print("3  --apply on a dirty tree without --force")
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        write(repo, "docs/RUNBOOK-deploy.md", "# Deploy\n")
        commit(repo)
        write(repo, "docs/dirt.md", "# dirt\n")
        before = snapshot(repo)
        code, out = run(repo, "--apply")
        check("3a exit 1", code == 1, f"exit {code}: {out[-300:]}")
        check("3b it says REFUSED and names the remedy",
              "REFUSED" in out and "--force" in out, out[-300:])
        check("3c and it moved nothing", snapshot(repo) == before)


def main() -> int:
    if not MIGRATOR.exists():
        print(f"migrate_to_standard.py not found at {MIGRATOR}", file=sys.stderr)
        return 2
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CONFIG_SYSTEM"] = os.devnull
    print("migrate_to_standard break-test")
    for case in (case_source_move_relinks_a_stationary_target, case_dry_run_writes_nothing,
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
