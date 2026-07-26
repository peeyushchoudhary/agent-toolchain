#!/usr/bin/env python3
"""Check the machine-global agent toolchain for drift.

Everything else here is scoped to a repository. These three things are not — they live in
`~/.claude` and `~/.codex`, are shared by every project, and no per-repo check owns them. That is
exactly why they rot silently:

  1. The persona pool vs the agents generated from it. A per-repo drift check only fires in a
     repository that has overlays — one project in thirteen — so an unsynced edit to the pool runs
     stale in every other project and nothing says so.
  2. The shared sections of ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md. Mirrored by hand; drift
     means the two harnesses are following different rules and neither announces it.
  3. The skills mirrored into ~/.codex/skills. Refreshed only when install_hooks.py runs, so a
     newly added skill is missing there until someone happens to run it in some repository.

Each failure is invisible from inside a project and silent at the point of use: Codex simply
follows an older contract. Reports; fixes nothing.

Usage:
  check_toolchain.py           # human report
  check_toolchain.py --hook    # compact agent context, silent when healthy
  check_toolchain.py --json
"""

from __future__ import annotations

import argparse
import filecmp
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
CODEX_MD = HOME / ".codex" / "AGENTS.md"
CODEX_SKILLS = HOME / ".codex" / "skills"
CLAUDE_SKILLS = HOME / ".claude" / "skills"
SYNC = CLAUDE_SKILLS / "agent-personas" / "scripts" / "sync_personas.py"

# Blocks that must be byte-identical in both harnesses' global instructions, as (start, end) text
# markers present in both files. The end marker is excluded from the comparison.
#
# Deliberately NOT listed: `# Operating model` and the surrounding `# Cross-project implementation
# strategy` prose. Those differ on purpose — first person for Claude, third for Codex, and each
# points at its own skills directory. Comparing them byte-for-byte would report a permanent failure
# and train the reader to ignore this check. Only blocks that carry rules, rather than voice, are
# required to match.
MIRRORED = [
    ("# GitHub", "# Cross-project implementation strategy"),
    ("**The personas are defined, not improvised.**", "system-prompt floor every call."),
]

# Skills both harnesses need. `graphify` is deliberately excluded: it is a vendor skill hidden from
# model-initiated use on the Claude side, and its presence in Codex is not something we manage.
MIRRORED_SKILLS = ("progressive-disclosure", "agent-personas", "agent-persona-factory",
                   "graph-navigation", "project-onboarding")


def section(text: str, start: str, end: str) -> str | None:
    try:
        return text[text.index(start):text.index(end)]
    except ValueError:
        return None


def check_personas() -> list[tuple[str, str]]:
    if not SYNC.is_file():
        return [("warn", f"persona sync tool missing at {SYNC}")]
    try:
        r = subprocess.run(["python3", str(SYNC), "--check"],
                           capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return [("warn", f"could not run the persona sync check: {e}")]
    if r.returncode == 1:
        n = sum(1 for line in r.stdout.splitlines() if line.strip().startswith("/"))
        return [("critical", f"{n} generated agent file(s) do not match the persona pool. Both "
                             f"harnesses are running a stale persona. Fix: python3 {SYNC}")]
    if r.returncode not in (0, 1):
        return [("warn", f"persona sync check failed: {r.stderr.strip()[:120]}")]
    return []


def check_instructions() -> list[tuple[str, str]]:
    if not CLAUDE_MD.is_file() or not CODEX_MD.is_file():
        return [("warn", "one of ~/.claude/CLAUDE.md or ~/.codex/AGENTS.md is missing")]
    a, b = CLAUDE_MD.read_text(), CODEX_MD.read_text()
    out = []
    for start, end in MIRRORED:
        sa, sb = section(a, start, end), section(b, start, end)
        if sa is None or sb is None:
            out.append(("warn", f"section `{start}` is missing from "
                                f"{'~/.claude/CLAUDE.md' if sa is None else '~/.codex/AGENTS.md'}"))
        elif sa != sb:
            out.append(("critical", f"section `{start}` differs between ~/.claude/CLAUDE.md and "
                                    f"~/.codex/AGENTS.md — the two harnesses are following "
                                    f"different rules"))
    return out


def check_skills() -> list[tuple[str, str]]:
    if not CODEX_SKILLS.is_dir():
        return [("warn", "~/.codex/skills does not exist; Codex has none of the shared skills")]
    out = []
    for name in MIRRORED_SKILLS:
        src, dst = CLAUDE_SKILLS / name, CODEX_SKILLS / name
        if not src.is_dir():
            continue
        if not dst.is_dir():
            out.append(("critical", f"skill `{name}` is missing from ~/.codex/skills — Codex "
                                    f"cannot use it. Fix: install_hooks.py <any-repo>"))
            continue
        cmp = filecmp.dircmp(src, dst, ignore=["__pycache__"])
        if cmp.left_only or cmp.right_only or cmp.diff_files:
            detail = ", ".join(sorted(cmp.left_only + cmp.diff_files)[:3]) or "content differs"
            out.append(("warn", f"skill `{name}` differs from the Codex copy ({detail}). "
                                f"Fix: install_hooks.py <any-repo>"))
    return out


def collect() -> list[tuple[str, str]]:
    return check_personas() + check_instructions() + check_skills()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hook", action="store_true", help="compact context; silent when healthy")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    findings = collect()

    if args.as_json:
        print(json.dumps([{"severity": s, "detail": d} for s, d in findings], indent=2))
    elif args.hook:
        if findings:
            print("AGENT CONTEXT: the shared agent toolchain has drifted. This affects every "
                  "project, not just this one.")
            for s, d in findings:
                print(f"  - [{s}] {d}")
    else:
        print("agent toolchain:")
        for s, d in findings:
            print(f"  {s.upper():8} {d}")
        if not findings:
            print("  clean — personas in sync, instructions mirrored, Codex skills current")
    return 1 if any(s == "critical" for s, _ in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
