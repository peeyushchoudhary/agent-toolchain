#!/usr/bin/env bash
# Verify the installation. Exits non-zero if anything essential is missing.
#
# Checks presence, then checks that things actually run — a file being in the right place is not
# evidence it works.
set -uo pipefail

CLAUDE="$HOME/.claude"
CODEX="$HOME/.codex"
PD="$CLAUDE/skills/progressive-disclosure/scripts"
fail=0
warn=0

ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
note() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; warn=$((warn+1)); }

echo "── skills"
for s in progressive-disclosure agent-personas agent-persona-factory project-onboarding; do
  [ -f "$CLAUDE/skills/$s/SKILL.md" ] && ok "$s" || bad "$s missing from ~/.claude/skills"
done
[ -f "$CLAUDE/skills/graph-navigation/SKILL.md" ] && ok "graph-navigation (optional)" \
  || note "graph-navigation absent — only matters if you use graphify"

echo "── scripts run"
for s in validate_disclosure check_github check_toolchain push_guard install_hooks; do
  if [ ! -f "$PD/$s.py" ]; then bad "$s.py missing"; continue; fi
  if python3 "$PD/$s.py" --help >/dev/null 2>&1; then ok "$s.py"
  else bad "$s.py present but fails to run — check the python version (3.10+ needed)"; fi
done
SYNC="$CLAUDE/skills/agent-personas/scripts/sync_personas.py"
if [ -f "$SYNC" ] && python3 "$SYNC" --list >/dev/null 2>&1; then ok "sync_personas.py"
else bad "sync_personas.py missing or failing"; fi

echo "── hooks on disk"
for h in disclosure-check.sh; do
  [ -x "$CLAUDE/hooks/$h" ] && ok "$h" || bad "$h missing or not executable"
done
for h in graphify-query-advisor.py graphify-session-lessons.sh; do
  [ -f "$CLAUDE/hooks/$h" ] && ok "$h (optional)" || note "$h absent — graphify integration only"
done

echo "── hooks wired into settings.json"
if [ -f "$CLAUDE/settings.json" ]; then
  python3 - "$CLAUDE/settings.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"  \033[31mFAIL\033[0m  settings.json is not valid JSON: {e}"); raise SystemExit(1)
cmds = [h.get("command", "") for ev in d.get("hooks", {}).values()
        for e in ev for h in e.get("hooks", [])]
found = any("disclosure-check.sh" in c for c in cmds)
print(f"  \033[32mok\033[0m    disclosure-check wired" if found
      else "  \033[31mFAIL\033[0m  disclosure-check.sh is not wired into settings.json")
raise SystemExit(0 if found else 1)
PY
  [ $? -eq 0 ] || fail=$((fail+1))
else
  bad "no ~/.claude/settings.json"
fi

echo "── the hook actually produces output"
tmp=$(mktemp -d); mkdir -p "$tmp/src"
printf 'a=1\n' > "$tmp/src/a.py"; printf 'b=2\n' > "$tmp/src/b.py"; printf 'c=3\n' > "$tmp/src/c.py"
out=$(CLAUDE_PROJECT_DIR="$tmp" bash "$CLAUDE/hooks/disclosure-check.sh" 2>/dev/null)
if echo "$out" | grep -q "project-onboarding"; then
  ok "uninitialised project is detected and names the skill"
else
  bad "hook did not flag an uninitialised project (got: ${out:0:80})"
fi
rm -rf "$tmp"

echo "── personas rendered"
n=$(ls "$CLAUDE/agents"/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "${n:-0}" -gt 0 ] && ok "$n persona(s) in ~/.claude/agents" \
  || bad "no personas in ~/.claude/agents — run sync_personas.py"

echo "── codex"
if [ -d "$CODEX" ]; then
  m=$(ls "$CODEX/skills" 2>/dev/null | wc -l | tr -d ' ')
  [ "${m:-0}" -ge 4 ] && ok "$m skills mirrored" || bad "only ${m:-0} skills in ~/.codex/skills"
  a=$(ls "$CODEX/agents"/*.toml 2>/dev/null | wc -l | tr -d ' ')
  [ "${a:-0}" -gt 0 ] && ok "$a persona(s) in ~/.codex/agents" || bad "no personas in ~/.codex/agents"
  grep -q '^\[agents\]' "$CODEX/config.toml" 2>/dev/null && ok "subagents enabled" \
    || bad "no [agents] block in config.toml — Codex will not spawn personas"
else
  note "Codex not installed — skipped"
fi

echo "── global toolchain consistency"
if [ -f "$PD/check_toolchain.py" ]; then
  if python3 "$PD/check_toolchain.py" >/dev/null 2>&1; then ok "personas, instructions, and mirrors agree"
  else note "drift reported — run: python3 $PD/check_toolchain.py"; fi
fi

echo
echo "── optional third-party"
command -v gh >/dev/null && ok "gh (GitHub checks)" || note "gh absent — check_github.py local half only"
command -v graphify >/dev/null && ok "graphify" || note "graphify absent — graph features inert (fine)"
command -v rg >/dev/null && ok "ripgrep" || note "rg absent — some documented searches assume it"

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS — $warn optional item(s) absent"
else
  echo "FAIL — $fail problem(s), $warn warning(s)"
fi
exit $((fail > 0))
