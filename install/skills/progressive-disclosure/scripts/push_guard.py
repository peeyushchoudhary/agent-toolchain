#!/usr/bin/env python3
"""pre-push guard: the three mistakes that a push makes permanent.

Everything else in this toolkit is recoverable — a bad commit is amended, a broken route is fixed
on the next commit. A push is different: it hands the content to a server that keeps it, and for
the three cases below the damage survives any later cleanup of the local branch.

  BLOCK  a credential in the pushed diff   — rotating a leaked key is the only real fix
  BLOCK  a file over the size limit        — git history keeps it forever; the clone never shrinks
  BLOCK  a direct push to the default branch — milestone work lands through a PR, not sideways
  warn   a newly added .env-style file     — sometimes deliberate, so it asks rather than stops
  warn   source changed, README untouched  — the front-page question, asked while it is cheap

Reads the standard pre-push payload on stdin: `<local ref> <local oid> <remote ref> <remote oid>`.

Escapes, in order of preference: fix it; `PD_ALLOW_MAIN_PUSH=1 git push`; `git push --no-verify`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_disclosure import SECRET_PATTERNS  # noqa: E402

ZERO = "0" * 40
DEFAULT_BRANCHES = ("refs/heads/main", "refs/heads/master")
MAX_FILE_MB = float(os.environ.get("PD_MAX_FILE_MB", "10"))
MAX_DIFF_BYTES = 40 * 1024 * 1024        # beyond this, scanning costs more than it catches
ENV_FILE = re.compile(r"(^|/)\.env(\.|$)")
ENV_ALLOWED = re.compile(r"\.env\.(example|sample|template|defaults)$")


def git(*args: str, timeout: int = 60) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=timeout, check=True).stdout
    except subprocess.CalledProcessError:
        return ""
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def base_for(local: str, remote: str) -> str | None:
    """What this push actually adds. None means 'no sane base' — scan nothing rather than everything.

    For an existing remote branch the base is obvious. For a brand-new branch, anything already on
    another remote-tracking ref is by definition already pushed, so `--not --remotes` is the range
    that isolates the new work; falling back to full history would re-flag the whole repository.
    """
    if remote != ZERO:
        return remote
    new_commits = git("rev-list", "--reverse", local, "--not", "--remotes").split()
    if not new_commits:
        return None
    # The root commit of a brand-new repository has no parent; there is nothing to diff against.
    return git("rev-parse", f"{new_commits[0]}^").strip() or None


def changed_files(base: str | None, local: str) -> list[str]:
    if not base:
        return []
    return [f for f in git("diff", "--name-only", "--diff-filter=d", base, local).splitlines()
            if f.strip()]


def added_files(base: str | None, local: str) -> list[str]:
    if not base:
        return []
    return [f for f in git("diff", "--name-only", "--diff-filter=A", base, local).splitlines()
            if f.strip()]


def oversized(base: str | None, local: str) -> list[tuple[str, float]]:
    """Blobs introduced by this push that exceed the limit, by real object size."""
    rng = [f"{base}..{local}"] if base else [local, "--not", "--remotes"]
    # `rev-list --objects` emits "<sha>" for commits and "<sha> <path>" for trees and blobs — and
    # the root tree of each commit comes through as "<sha> " with an empty path, which a naive
    # two-way unpack chokes on.
    entries: dict[str, str] = {}
    for ln in git("rev-list", "--objects", *rng).splitlines():
        sha, _, path = ln.partition(" ")
        if sha and path.strip():
            entries[sha] = path
    if not entries:
        return []
    query = "\n".join(entries) + "\n"
    try:
        out = subprocess.run(["git", "cat-file", "--batch-check=%(objecttype) %(objectsize) %(objectname)"],
                             input=query, capture_output=True, text=True, timeout=120, check=True).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return []
    limit = MAX_FILE_MB * 1024 * 1024
    big: list[tuple[str, float]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[0] != "blob":
            continue
        size = int(parts[1])
        if size > limit:
            big.append((entries.get(parts[2], parts[2]), size / 1024 / 1024))
    return sorted(set(big), key=lambda t: -t[1])


def secrets(base: str | None, local: str) -> list[tuple[str, str, str]]:
    """(file, pattern name, redacted line) for added lines only.

    Scans every commit in the range, not the net diff. A secret added in one commit and removed in
    the next still ships to the server inside the pushed objects and stays recoverable there, but a
    `git diff base..local` cancels the two out and reports nothing. Verified: the net-diff version
    of this function missed exactly that case.

    Added lines only: a secret already on the remote is history, and re-flagging it on every later
    push would train the founder to pass --no-verify by reflex.
    """
    rng = [f"{base}..{local}"] if base else [local, "--not", "--remotes"]
    diff = git("log", "-p", "--unified=0", "--no-merges", "--format=%H", *rng, timeout=120)
    if len(diff) > MAX_DIFF_BYTES:
        print(f"  note: diff is {len(diff) // 1024 // 1024} MB — skipping the content scan.")
        return []

    hits: list[tuple[str, str, str]] = []
    current = "?"
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for name, pattern in SECRET_PATTERNS:
            m = re.search(pattern, line)
            if m:
                shown = m.group(0)
                redacted = shown[:6] + "…" + shown[-2:] if len(shown) > 12 else shown[:4] + "…"
                hits.append((current, name, redacted))
                break
    return hits


def readme_stale(base: str | None, local: str) -> bool:
    if not base:
        return False
    files = changed_files(base, local)
    if not files or any(Path(f).name.lower() == "readme.md" for f in files):
        return False
    top = {f.split("/")[0] for f in files if "/" in f}
    return bool(top - {"docs", ".github", ".claude", "graphify-out"})


def main() -> int:
    payload = [ln.split() for ln in sys.stdin.read().splitlines() if ln.strip()]
    if not payload:
        return 0

    blocking: list[str] = []
    warnings: list[str] = []

    for parts in payload:
        if len(parts) != 4:
            continue
        local_ref, local_oid, remote_ref, remote_oid = parts
        if local_oid == ZERO:              # a branch deletion pushes nothing to inspect
            continue
        if local_oid == remote_oid:        # already there; git can still call us with a no-op ref
            continue

        if remote_ref in DEFAULT_BRANCHES and remote_oid != ZERO \
                and not os.environ.get("PD_ALLOW_MAIN_PUSH"):
            blocking.append(
                f"direct push to {remote_ref}. Milestone work lands through a pull request:\n"
                f"      git switch -c milestone/<name> && git push -u origin HEAD && gh pr create\n"
                f"      Deliberate exception: PD_ALLOW_MAIN_PUSH=1 git push")

        base = base_for(local_oid, remote_oid)

        for path, mb in oversized(base, local_oid):
            blocking.append(f"{path} is {mb:.1f} MB (limit {MAX_FILE_MB:g} MB). Git keeps it in "
                            f"history forever — every future clone pays for it.")

        for path, name, shown in secrets(base, local_oid):
            blocking.append(f"{path}: looks like a {name} ({shown}). If it is real, rotate it — "
                            f"removing the line does not remove it from history.")

        for path in added_files(base, local_oid):
            if ENV_FILE.search(path) and not ENV_ALLOWED.search(path):
                warnings.append(f"{path} is a new .env-style file. Confirm it holds no secrets.")

        if readme_stale(base, local_oid):
            warnings.append("source changed but README.md did not — confirm the front page is "
                            "still true before this becomes a PR.")

    for w in warnings:
        print(f"  pre-push warn: {w}")

    if blocking:
        print("\n  pre-push BLOCKED:")
        for b in blocking:
            print(f"    - {b}")
        print("\n  Override only if you are certain: git push --no-verify\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
