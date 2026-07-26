#!/usr/bin/env python3
"""Report whether a project is backed by GitHub the way the operating model expects.

GitHub here is storage for code and config — nothing deploys from it, nothing runs on it. That
makes the interesting questions narrow: does the work exist anywhere but this laptop, is it
private, and is anything switched on that costs money or fragments the documentation route.

Two tiers of check, because session start must stay fast:

  local    git only, no network, always runs — remote configured? unpushed work? how old?
  remote   one `gh` call, cached for 24h — private? Actions off? Wiki/Projects/Issues off?

Reports. Never creates a repository, never pushes, never changes a setting — except under the
explicit `--apply-settings`, which touches only the three feature toggles and never visibility.

Usage:
  check_github.py [ROOT]                   # human report
  check_github.py [ROOT] --hook            # compact agent context, silent when healthy
  check_github.py [ROOT] --json
  check_github.py [ROOT] --refresh         # ignore the 24h cache
  check_github.py [ROOT] --apply-settings  # disable Wiki/Projects/Issues on the remote
  check_github.py --sweep DIR              # one line per project under DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".claude" / "cache" / "github-state"
CACHE_TTL = 24 * 3600
STALE_PUSH_DAYS = 3

# Free-tier reality, checked 2026-07. Everything below is $0 on a personal account with private
# repos; the toggles we turn off are off for fragmentation or blast-radius reasons, not for cost.
#   Actions   : free-tier minutes exist, but nothing here should run on them.
#   Wiki      : a second git repo, outside the disclosure route, that docs rot into.
#   Projects  : a second backlog competing with docs/product/backlog.md.
#   Issues    : same, for work tracking.
FEATURE_TOGGLES = ("has_wiki", "has_projects", "has_issues")


def git(root: Path, *args: str, timeout: int = 15) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=timeout, check=True).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


# Session start runs this in every project; a slow network must never hold a session open. On a
# cache miss in hook mode we would rather report the local half than wait.
GH_TIMEOUT = 25


def gh_json(*args: str):
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True,
                             timeout=GH_TIMEOUT, check=True).stdout
        return json.loads(out) if out.strip() else None
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
        return None


def slug(url: str) -> str | None:
    """owner/name from any GitHub remote spelling."""
    if not url or "github.com" not in url:
        return None
    tail = url.split("github.com", 1)[1].lstrip(":/")
    return tail[:-4] if tail.endswith(".git") else tail or None


def local_state(root: Path) -> dict:
    st: dict = {"root": str(root), "name": root.name}
    st["is_git"] = (root / ".git").is_dir()
    if not st["is_git"]:
        return st

    st["remote"] = git(root, "remote", "get-url", "origin")
    st["slug"] = slug(st["remote"])

    # Commits on a local branch that no remote-tracking ref contains. Tags are deliberately not
    # counted: `--not --remotes` ignores them, so a tag-only commit reads as unpushed when it is
    # not. Tag drift is checked against the remote instead, where it can be answered correctly.
    unpushed = git(root, "log", "--branches", "--not", "--remotes", "--format=%ct")
    stamps = [int(s) for s in unpushed.split() if s.isdigit()]
    st["unpushed"] = len(stamps)
    st["unpushed_age_days"] = int((time.time() - min(stamps)) / 86400) if stamps else 0

    st["no_upstream"] = [b for b in git(
        root, "for-each-ref", "--format=%(refname:short) %(upstream)", "refs/heads"
    ).splitlines() if b and len(b.split()) == 1]
    st["dirty"] = len([l for l in git(root, "status", "--porcelain").splitlines() if l.strip()])
    return st


def remote_state(st: dict, refresh: bool) -> dict:
    """One cached `gh` round trip. Session start runs in every project; do not pay this each time."""
    if not st.get("slug"):
        return {}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / (hashlib.sha1(st["slug"].encode()).hexdigest()[:16] + ".json")
    if not refresh and cache.is_file():
        try:
            blob = json.loads(cache.read_text())
            if time.time() - blob.get("fetched_at", 0) < CACHE_TTL:
                return blob
        except (json.JSONDecodeError, OSError):
            pass

    repo = gh_json("api", f"repos/{st['slug']}", "--jq",
                   "{private:.private,has_wiki:.has_wiki,has_projects:.has_projects,"
                   "has_issues:.has_issues,size:.size,default_branch:.default_branch}")
    if repo is None:
        return {"unreachable": True}
    perms = gh_json("api", f"repos/{st['slug']}/actions/permissions")
    repo["actions_enabled"] = bool(perms.get("enabled")) if isinstance(perms, dict) else None
    wf = gh_json("api", f"repos/{st['slug']}/actions/workflows", "--jq", ".total_count")
    repo["workflows"] = wf if isinstance(wf, int) else 0
    repo["fetched_at"] = time.time()
    try:
        cache.write_text(json.dumps(repo))
    except OSError:
        pass
    return repo


def findings(st: dict, rs: dict) -> list[tuple[str, str]]:
    """(severity, message). `critical` means data exposure or total loss risk."""
    out: list[tuple[str, str]] = []
    if not st["is_git"]:
        out.append(("critical", "not a git repository at all — nothing here is version controlled "
                                "or backed up. `git init` then create a PRIVATE GitHub repo."))
        return out
    if not st.get("remote"):
        out.append(("critical", "no git remote — this repository exists only on this laptop. "
                                "Create one with `gh repo create --private --source=. --push`."))
    elif not st.get("slug"):
        out.append(("warn", f"remote is not GitHub ({st['remote']})"))

    if st.get("unpushed"):
        sev = "critical" if st["unpushed_age_days"] >= STALE_PUSH_DAYS else "info"
        out.append((sev, f"{st['unpushed']} unpushed commit(s), oldest {st['unpushed_age_days']} "
                         f"day(s) old — that work exists on one machine only."))
    for b in st.get("no_upstream", []):
        out.append(("warn", f"branch `{b}` has no upstream; it will not be pushed by `git push`."))

    if rs.get("unreachable"):
        out.append(("warn", "could not read the repo from GitHub (gh not installed, not "
                            "authenticated, or no access)."))
        return out
    if not rs:
        return out

    if rs.get("private") is False:
        out.append(("critical", "this repository is PUBLIC. Everything committed is world "
                                "readable. Make it private before pushing anything further."))
    if rs.get("actions_enabled"):
        out.append(("warn", "GitHub Actions is enabled. Nothing deploys from GitHub in this "
                            "operating model; disable it so nothing can run or bill."))
    if rs.get("workflows"):
        out.append(("warn", f"{rs['workflows']} Actions workflow(s) are defined on the remote."))
    on = [k[4:] for k in FEATURE_TOGGLES if rs.get(k)]
    if on:
        out.append(("info", f"{', '.join(on)} enabled on the remote — each is a place documentation "
                            "or work tracking can live outside the repository route."))
    return out


def report(st: dict, rs: dict, as_json: bool) -> int:
    f = findings(st, rs)
    if as_json:
        print(json.dumps({"local": st, "remote": rs,
                          "findings": [{"severity": s, "detail": d} for s, d in f]}, indent=2,
                         default=str))
    else:
        print(f"github: {st['name']}  ({st.get('slug') or 'no GitHub remote'})")
        if rs and not rs.get("unreachable"):
            print(f"  visibility: {'private' if rs.get('private') else 'PUBLIC'}   "
                  f"actions: {'on' if rs.get('actions_enabled') else 'off'}   "
                  f"size: {rs.get('size', '?')} KB")
        for sev, detail in f:
            print(f"  {sev.upper():8} {detail}")
        if not f:
            print("  clean — private, pushed, nothing enabled that runs or bills")
    return 1 if any(s == "critical" for s, _ in f) else 0


def hook_line(st: dict, rs: dict) -> str:
    """Compact context for session start. Silent unless something is actually actionable."""
    f = [(s, d) for s, d in findings(st, rs) if s in ("critical", "warn")]
    if not f:
        return ""
    head = f"AGENT CONTEXT: GitHub state for `{st['name']}` needs attention."
    body = "\n".join(f"  - [{s}] {d}" for s, d in f)
    return (f"{head}\n{body}\n  Report only — do not create a repository, change visibility, or "
            f"push without asking. Full detail: `python3 {Path(__file__).resolve()} .`")


def apply_settings(st: dict) -> int:
    """Turn off the three feature toggles. Never touches visibility — that is the human's call."""
    if not st.get("slug"):
        print("  no GitHub remote — nothing to apply")
        return 1
    args = []
    for k in FEATURE_TOGGLES:
        args += ["-F", f"{k}=false"]
    r = subprocess.run(["gh", "api", "-X", "PATCH", f"repos/{st['slug']}", *args, "--silent"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  FAILED: {r.stderr.strip()[:200]}")
        return 1
    print(f"  {st['slug']}: wiki, projects, issues disabled")
    return 0


def sweep(base: Path, refresh: bool) -> int:
    """One line per project directory. The report that says which repos still need work."""
    print(f"github sweep: {base}\n")
    rows: list[tuple[str, str, str]] = []
    for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
        st = local_state(d)
        rs = remote_state(st, refresh) if st.get("slug") else {}
        f = findings(st, rs)
        worst = ("critical" if any(s == "critical" for s, _ in f)
                 else "warn" if any(s == "warn" for s, _ in f) else "ok")
        detail = next((dd for s, dd in f if s == worst), "private, pushed, nothing running")
        rows.append((d.name, worst, detail.split(" — ")[0].split(". ")[0]))
    width = max(len(r[0]) for r in rows) if rows else 10
    for name, worst, detail in rows:
        print(f"  {name:<{width}}  {worst.upper():8}  {detail}")
    n = sum(1 for _, w, _ in rows if w == "critical")
    print(f"\n  {len(rows)} project(s), {n} needing action.")
    return 1 if n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--hook", action="store_true", help="compact agent context; silent when healthy")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--refresh", action="store_true", help="bypass the 24h remote cache")
    ap.add_argument("--apply-settings", action="store_true",
                    help="disable Wiki/Projects/Issues on the remote (never changes visibility)")
    ap.add_argument("--sweep", metavar="DIR", default=None, help="report on every project under DIR")
    args = ap.parse_args()

    if args.sweep:
        base = Path(args.sweep).expanduser().resolve()
        if not base.is_dir():
            print(f"not a directory: {base}", file=sys.stderr)
            return 2
        return sweep(base, args.refresh)

    root = Path(args.root).resolve()
    st = local_state(root)

    if args.apply_settings:
        return apply_settings(st)

    global GH_TIMEOUT
    if args.hook:
        GH_TIMEOUT = 6

    # In hook mode a missing/unauthenticated gh must cost nothing: the local half still reports.
    rs = remote_state(st, args.refresh) if st.get("slug") else {}

    if args.hook:
        line = hook_line(st, rs)
        if line:
            print(line)
        return 0
    return report(st, rs, args.as_json)


if __name__ == "__main__":
    raise SystemExit(main())
