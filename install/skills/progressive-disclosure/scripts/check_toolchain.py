#!/usr/bin/env python3
"""Check the machine-global agent toolchain for drift. Reports; fixes nothing.

Two checks, both outside any repository, which is why nothing else notices when they drift:

  personas      the generated agents match the persona sources (`sync_personas.py --check`)
  instructions  the shared `# Execution and maintenance route` block is byte-identical in
                ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md, from the `# GitHub` heading through
                the route block's closing sentence

Three states, never two: a check that could not run is `not-run`, never absorbed into a pass.

Exit codes: 0 clean, 1 a critical finding, 2 a check could not run (2 outranks 1).

Usage:
  check_toolchain.py           # human report
  check_toolchain.py --hook    # compact agent context, silent when healthy
  check_toolchain.py --json    # {"status", "exit", "evaluated", "not_evaluated", "findings", "summary"}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
CODEX_MD = HOME / ".codex" / "AGENTS.md"
SYNC = HOME / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"

ROUTE_HEADING = "# Execution and maintenance route"
ROUTE_END = ("User authority, privacy, local verification and deployment boundaries remain in "
             "force throughout.")
# (start, end) markers present in both files; the end marker is excluded from the comparison.
# The operating-model prose is deliberately not compared: it differs in voice between harnesses.
MIRRORED = [
    ("# GitHub", ROUTE_HEADING),
    (ROUTE_HEADING, ROUTE_END),
]

NOT_RUN = "not-run"


def section(text: str, start: str, end: str) -> str | None:
    try:
        return text[text.index(start):text.index(end)]
    except ValueError:
        return None


def check_personas() -> list[tuple[str, str]]:
    if not SYNC.is_file():
        return [(NOT_RUN, f"persona sync was NOT RUN: the sync tool is missing at {SYNC}, so no "
                          f"generated agent file was compared against the pool")]
    try:
        r = subprocess.run([sys.executable, str(SYNC), "--check"],
                           capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as e:
        return [(NOT_RUN, f"persona sync was NOT RUN: the sync check could not be started ({e})")]
    if r.returncode == 1:
        n = sum(1 for line in r.stdout.splitlines() if line.strip().startswith("/"))
        return [("critical", f"{n} generated agent file(s) do not match the persona pool. Both "
                             f"harnesses are running a stale persona. Fix: python3 {SYNC}")]
    if r.returncode != 0:
        return [(NOT_RUN, f"persona sync was NOT RUN: the sync check exited {r.returncode} without "
                          f"reaching a verdict ({r.stderr.strip()[:120]})")]
    return []


def check_instructions() -> list[tuple[str, str]]:
    if not CLAUDE_MD.is_file() or not CODEX_MD.is_file():
        return [(NOT_RUN, "the instruction mirror was NOT RUN: one of ~/.claude/CLAUDE.md or "
                          "~/.codex/AGENTS.md is missing, so no shared block was compared")]
    try:
        a = CLAUDE_MD.read_text(encoding="utf-8", errors="strict")
        b = CODEX_MD.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as e:
        return [(NOT_RUN, f"the instruction mirror was NOT RUN: ~/.claude/CLAUDE.md or "
                          f"~/.codex/AGENTS.md could not be read ({e}), so no shared block was "
                          f"compared")]
    out = []
    for start, end in MIRRORED:
        sa, sb = section(a, start, end), section(b, start, end)
        if sa is None or sb is None:
            out.append((NOT_RUN, f"section `{start}` was NOT COMPARED: it is missing from "
                                 f"{'~/.claude/CLAUDE.md' if sa is None else '~/.codex/AGENTS.md'}, "
                                 f"so whether the two harnesses agree on it is unknown"))
        elif sa != sb:
            out.append(("critical", f"section `{start}` differs between ~/.claude/CLAUDE.md and "
                                    f"~/.codex/AGENTS.md — the two harnesses are following "
                                    f"different rules"))
    return out


CHECKS = (
    ("personas", "personas in sync", check_personas),
    ("instruction mirror", "instructions mirrored", check_instructions),
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hook", action="store_true", help="compact context; silent when healthy")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    findings: list[tuple[str, str]] = []
    evaluated: list[str] = []
    phrases: list[str] = []
    not_evaluated: list[tuple[str, str]] = []
    for label, phrase, fn in CHECKS:
        found = fn()
        findings += found
        why = [d for s, d in found if s == NOT_RUN]
        if why:
            not_evaluated.append((label, why[0]))
        else:
            evaluated.append(label)
            phrases.append(phrase)
    findings.sort(key=lambda f: (f[0] != NOT_RUN, f[0]))

    if not_evaluated:
        status, code = NOT_RUN, 2
    elif findings:
        status, code = "findings", 1
    else:
        status, code = "clean", 0
    if status == "clean":
        summary = "clean — " + "; ".join(phrases)
    else:
        summary = (f"NOT A CLEAN RESULT — {len(findings)} finding(s); checked: "
                   f"{', '.join(evaluated) or 'nothing'}")
        if not_evaluated:
            summary += (f". NOT RUN: {', '.join(c for c, _ in not_evaluated)}. "
                        f"No verdict is available for what did not run.")
        else:
            summary += "."

    if args.as_json:
        print(json.dumps({
            "status": status, "exit": code, "evaluated": evaluated,
            "not_evaluated": [{"check": c, "why": w} for c, w in not_evaluated],
            "findings": [{"severity": s, "detail": d} for s, d in findings],
            "summary": summary,
        }, indent=2))
    elif args.hook:
        if findings:
            print("AGENT CONTEXT: the shared agent toolchain has drifted. This affects every "
                  "project, not just this one.")
            for s, d in findings:
                print(f"  - [{s}] {d}")
            print(f"  {summary}")
    else:
        print("agent toolchain:")
        for s, d in findings:
            print(f"  {s.upper():8} {d}")
        print(f"  {summary}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
