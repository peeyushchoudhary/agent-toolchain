#!/usr/bin/env bash
# SessionStart: print the active goal's status, or the migrate-first notice in a v5.1 project.
#
# Both harnesses run it (Claude Code from settings, Codex from the project's .codex/hooks.json);
# its stdout becomes session context. The notice text comes from goal.py itself, so the hook and
# the tool can never disagree. It must never block or break a session: every path exits 0, and it
# is silent when the project has neither a runtime pin nor an active goal.

root=$(cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null) || exit 0
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd) || exit 0
# Installed beside the skills (~/.claude/hooks, ~/.claude/skills) and in this repository's install/.
goal_py="${GOAL_PY:-$here/../skills/execution-methodology/scripts/goal.py}"

if [ -f "$root/docs/agents/execution/runtime.json" ]; then
  notice=$(cd "$root" && PYTHONDONTWRITEBYTECODE=1 python3 "$goal_py" status 2>&1 >/dev/null)
  [ -n "$notice" ] || notice="goal.py: this project still carries the v5.1 runtime pin (docs/agents/execution/runtime.json); migrate it to v6 first, following references/migrate.md"
  echo "GOAL: v6 will not execute here. ${notice#goal.py: }"
  exit 0
fi
[ -f "$root/.runs/active" ] && [ -f "$goal_py" ] || exit 0
(cd "$root" && PYTHONDONTWRITEBYTECODE=1 python3 "$goal_py" status 2>/dev/null) || true
exit 0
