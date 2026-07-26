#!/usr/bin/env python3
"""Install the per-repository git hooks that keep agent context true.

Three hooks, all per-repo because git hooks are not shared through git — every clone and every
project needs this run once:

  pre-commit   validates the disclosure route (broken link, missing command, unscoped dir)
  pre-push     blocks the mistakes a push makes permanent (secrets, huge files, pushes to main)
  post-commit  re-extracts changed code into the Graphify graph, via `graphify hook install`

pre-push carries the rules that GitHub itself would charge for: secret scanning on a private repo
needs paid Secret Protection, and protected branches need a paid plan. Enforcing them locally costs
nothing and matches the operating model, where local gates are the only gates.

Both are written as a marked block, so an existing hook is preserved and re-running replaces only
our block rather than duplicating it.

The pre-commit hook is deliberately forgiving about *setup* and strict about *breakage*: it skips
silently when the repo has no `docs/agents/README.md` or no validator installed, so it is safe to
install anywhere, including a project that has not been standardised yet. When the route does
exist and is broken, it fails the commit — bypass with `git commit --no-verify`.

Usage:
  install_hooks.py [ROOT]              # install / update
  install_hooks.py [ROOT] --check      # report status, change nothing
  install_hooks.py [ROOT] --uninstall  # remove only our block
  install_hooks.py [ROOT] --standard   # pre-commit also enforces the structure standard
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BEGIN = "# >>> progressive-disclosure >>>"
END = "# <<< progressive-disclosure <<<"

PRE_COMMIT = """{begin}
# Validates the agent disclosure route. Skips silently when this repo has no route yet or the
# validator is not installed. Bypass a genuine emergency with: git commit --no-verify
_pd_validator="$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py"
if [ -f "docs/agents/README.md" ] && [ -f "$_pd_validator" ]; then
  _pd_out=$(PYTHONDONTWRITEBYTECODE=1 python3 "$_pd_validator" .{flags} 2>&1) || {{
    printf '%s\\n' "$_pd_out"
    echo "pre-commit: the agent disclosure route is broken. Fix it, or use --no-verify."
    exit 1
  }}
fi
{end}
"""

PRE_PUSH = """{begin}
# Blocks credentials, oversized blobs, and direct pushes to the default branch. Skips silently
# when the guard is not installed. Bypass with: git push --no-verify
_pd_guard="$HOME/.claude/skills/progressive-disclosure/scripts/push_guard.py"
if [ -f "$_pd_guard" ]; then
  PYTHONDONTWRITEBYTECODE=1 python3 "$_pd_guard" "$@" || exit 1
fi
{end}
"""


def hook_path(root: Path, name: str) -> Path:
    return root / ".git" / "hooks" / name


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def strip_block(text: str) -> str:
    if BEGIN not in text:
        return text
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    return (head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip("\n")


def write_hook(path: Path, block: str) -> str:
    """Insert or replace our block, preserving any hook the user already had."""
    existing = strip_block(read(path))
    if not existing.strip():
        body = "#!/bin/sh\n" + block
        action = "installed"
    else:
        lines = existing.splitlines()
        if lines and lines[0].startswith("#!"):
            body = lines[0] + "\n" + "\n".join(lines[1:]).strip("\n") + "\n\n" + block
        else:
            body = "#!/bin/sh\n" + existing + "\n\n" + block
        action = "updated (existing hook preserved)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return action


def sync_codex(root: Path) -> str | None:
    """Mirror the skills wherever Codex will look, so both agents run the same version.

    Prefers Codex's global skills directory — one copy that every project sees — and also refreshes
    a repo-local `.codex/skills` if the project already keeps one. Hand-copying drifts the first
    time anyone forgets, and the failure is silent: Codex quietly follows an older standard.
    """
    import shutil
    targets = [d for d in (Path.home() / ".codex" / "skills", root / ".codex" / "skills")
               if d.is_dir()]
    if not targets:
        return None
    copied: set[str] = set()
    for dest_root in targets:
        for name in ("progressive-disclosure", "graph-navigation", "agent-personas",
                     "agent-persona-factory", "project-onboarding"):
            src = Path.home() / ".claude" / "skills" / name
            if not src.is_dir():
                continue
            dest = dest_root / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
            copied.add(name)
    where = " + ".join("global" if t == Path.home() / ".codex" / "skills" else "repo" for t in targets)
    return f"{', '.join(sorted(copied))} -> {where}" if copied else None


def graphify_available() -> bool:
    try:
        subprocess.run(["graphify", "--help"], capture_output=True, timeout=20, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--check", action="store_true", help="report status only")
    ap.add_argument("--uninstall", action="store_true", help="remove our block from the hooks")
    ap.add_argument("--standard", action="store_true",
                    help="pre-commit also enforces the structure standard")
    ap.add_argument("--no-graph", action="store_true", help="skip the Graphify post-commit hook")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    print(f"hooks: {root}")

    if not (root / ".git").is_dir():
        print("  not a git repository — git hooks cannot be installed here.")
        print("  the agent-side hooks (query advisor, session lessons) still apply: they are")
        print("  configured once in ~/.claude/settings.json and run in every project.")
        return 0

    pre = hook_path(root, "pre-commit")

    if args.check:
        state = "present" if BEGIN in read(pre) else "ABSENT"
        push = "present" if BEGIN in read(hook_path(root, "pre-push")) else "ABSENT"
        post = read(hook_path(root, "post-commit"))
        graph = "present" if "graphify" in post else "ABSENT"
        route = "yes" if (root / "docs" / "agents" / "README.md").is_file() else "no route yet"
        print(f"  pre-commit route check: {state}")
        print(f"  pre-push secret/size/main guard: {push}")
        print(f"  post-commit graph refresh: {graph}")
        print(f"  repo has a disclosure route: {route}")
        return 0

    if args.uninstall:
        for name in ("pre-commit", "pre-push", "post-commit"):
            p = hook_path(root, name)
            if not p.is_file():
                continue
            cleaned = strip_block(read(p))
            if cleaned.strip() in ("", "#!/bin/sh"):
                p.unlink()
                print(f"  removed {name}")
            else:
                p.write_text(cleaned + "\n", encoding="utf-8")
                p.chmod(0o755)
                print(f"  cleaned {name} (kept the rest)")
        if graphify_available():
            subprocess.run(["graphify", "hook", "uninstall"], cwd=root, capture_output=True)
            print("  removed graphify post-commit hook")
        return 0

    synced = sync_codex(root)
    if synced:
        print(f"  synced .codex/skills: {synced}")

    # Personas render into both harnesses. Generated agent files are committed, so a clone that
    # never syncs would commit stale ones; the validator's persona-drift check catches that, and
    # this makes the common case correct without a separate step to remember.
    personas = Path.home() / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
    if personas.is_file():
        r = subprocess.run(["python3", str(personas), "--repo", str(root)],
                           capture_output=True, text=True)
        first = (r.stdout.strip().splitlines() or ["no output"])[0]
        print(f"  personas: {first}")

    flags = " --standard" if args.standard else ""
    action = write_hook(pre, PRE_COMMIT.format(begin=BEGIN, end=END, flags=flags))
    print(f"  pre-commit {action}"
          f"{' (enforcing the standard)' if args.standard else ''}")

    action = write_hook(hook_path(root, "pre-push"), PRE_PUSH.format(begin=BEGIN, end=END))
    print(f"  pre-push {action}")
    print("    blocks: credentials in the pushed range, files over "
          "$PD_MAX_FILE_MB (default 10) MB, direct pushes to main.")

    if args.no_graph:
        print("  post-commit graph refresh skipped (--no-graph)")
    elif not (root / "graphify-out" / "graph.json").is_file():
        print("  post-commit graph refresh skipped — no graphify-out/graph.json in this repo")
    elif not graphify_available():
        print("  post-commit graph refresh skipped — graphify is not installed")
    else:
        r = subprocess.run(["graphify", "hook", "install"], cwd=root, capture_output=True, text=True)
        ok = r.returncode == 0
        print(f"  post-commit graph refresh {'installed' if ok else 'FAILED: ' + r.stderr.strip()[:120]}")
        print("    note: it re-extracts changed CODE only. Documentation changes still need a")
        print("    semantic rebuild — `graphify extract . --mode deep --backend <backend>`.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
