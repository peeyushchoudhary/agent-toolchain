#!/usr/bin/env bash
# Install the agent toolchain into ~/.claude and ~/.codex.
#
# Idempotent: re-running updates the skills and hooks in place and leaves everything else alone.
# It never overwrites your settings.json wholesale — hook entries are merged, and a timestamped
# backup is taken first.
#
#   ./install.sh              install or update
#   ./install.sh --dry-run    print what would happen, change nothing
#   ./install.sh --no-codex   skip the Codex side
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="$HOME/.claude"
CODEX="$HOME/.codex"
DRY=0
DO_CODEX=1

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --no-codex) DO_CODEX=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '  %s\n' "$1"; }
run()  { if [ "$DRY" -eq 1 ]; then printf '  would: %s\n' "$*"; else "$@"; fi; }

# ── Preconditions ────────────────────────────────────────────────────────────────────────────────
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "python3 $PYV found; 3.10 or newer is required (the tools use PEP 604 type syntax)" >&2
  exit 1; }
command -v git >/dev/null || echo "  note: git not found — the per-repo hooks will be unusable"

echo "agent toolchain installer"
say "python3 $PYV"
say "target: $CLAUDE$([ "$DO_CODEX" -eq 1 ] && echo " and $CODEX")"
[ "$DRY" -eq 1 ] && say "DRY RUN — nothing will be written"

# ── Skills ───────────────────────────────────────────────────────────────────────────────────────
# graph-navigation is included but only useful alongside the third-party `graphify` CLI; it is inert
# without it, so installing it costs nothing.
SKILLS="progressive-disclosure agent-personas agent-persona-factory project-onboarding graph-navigation"

echo "skills"
run mkdir -p "$CLAUDE/skills"
for s in $SKILLS; do
  [ -d "$HERE/skills/$s" ] || { say "SKIP $s (not in this package)"; continue; }
  if [ "$DRY" -eq 0 ]; then
    rm -rf "$CLAUDE/skills/$s"
    cp -R "$HERE/skills/$s" "$CLAUDE/skills/$s"
    find "$CLAUDE/skills/$s" -name '*.py' -exec chmod +x {} \;
  fi
  say "$([ "$DRY" -eq 1 ] && echo 'would install' || echo installed) $s"
done

# ── Hooks ────────────────────────────────────────────────────────────────────────────────────────
echo "hooks"
run mkdir -p "$CLAUDE/hooks"
for h in "$HERE"/hooks/*; do
  [ -f "$h" ] || continue
  if [ "$DRY" -eq 0 ]; then
    cp "$h" "$CLAUDE/hooks/$(basename "$h")"
    chmod +x "$CLAUDE/hooks/$(basename "$h")"
  fi
  say "$([ "$DRY" -eq 1 ] && echo 'would install' || echo installed) $(basename "$h")"
done

# ── settings.json ────────────────────────────────────────────────────────────────────────────────
# Merged, never replaced. A settings.json that is overwritten loses every unrelated preference, and
# a malformed one silently disables ALL settings from that file — so this validates before writing.
echo "settings.json"
if [ "$DRY" -eq 1 ]; then
  say "would merge 3 hook entries into $CLAUDE/settings.json (backup taken first)"
else
python3 - "$CLAUDE/settings.json" <<'PY'
import json, shutil, sys, time
from pathlib import Path

path = Path(sys.argv[1])
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as e:
        print(f"  REFUSED: {path} is not valid JSON ({e}).")
        print("  Fix it by hand, then re-run. A malformed settings.json disables every setting in it.")
        raise SystemExit(1)
    backup = path.with_suffix(f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    print(f"  backup: {backup.name}")

WANT = [
    ("SessionStart", None, "bash ~/.claude/hooks/disclosure-check.sh 2>/dev/null || true"),
    ("SessionStart", None, "bash ~/.claude/hooks/graphify-session-lessons.sh 2>/dev/null || true"),
    ("PreToolUse", "Bash", "python3 ~/.claude/hooks/graphify-query-advisor.py 2>/dev/null || true"),
]

hooks = data.setdefault("hooks", {})
added = 0
for event, matcher, command in WANT:
    entries = hooks.setdefault(event, [])
    already = any(command in h.get("command", "")
                  for e in entries for h in e.get("hooks", []))
    if already:
        continue
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        entry["matcher"] = matcher
    entries.append(entry)
    added += 1

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  {added} hook entr{'y' if added == 1 else 'ies'} added, {len(WANT) - added} already present")
PY
fi

# ── Codex ────────────────────────────────────────────────────────────────────────────────────────
if [ "$DO_CODEX" -eq 1 ]; then
  echo "codex"
  if [ ! -d "$CODEX" ]; then
    say "no $CODEX — Codex not installed here. Re-run with Codex present, or --no-codex to silence this."
  else
    run mkdir -p "$CODEX/skills"
    for s in $SKILLS; do
      [ -d "$HERE/skills/$s" ] || continue
      if [ "$DRY" -eq 0 ]; then
        rm -rf "$CODEX/skills/$s"; cp -R "$HERE/skills/$s" "$CODEX/skills/$s"
      fi
      say "$([ "$DRY" -eq 1 ] && echo 'would mirror' || echo mirrored) $s"
    done
    if [ "$DRY" -eq 0 ] && ! grep -q '^\[agents\]' "$CODEX/config.toml" 2>/dev/null; then
      cp "$CODEX/config.toml" "$CODEX/config.toml.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
      cat >> "$CODEX/config.toml" <<'EOF'

# Subagent defaults. Personas in ~/.codex/agents/ set their own model and effort; these apply only
# when a spawned agent specifies neither. Parent session settings above are unaffected.
[agents]
enabled = true
default_subagent_reasoning_effort = "medium"
max_concurrent_threads_per_session = 6
EOF
      say "added [agents] to config.toml (backup taken) — subagents were off"
    else
      say "config.toml already has [agents], or dry run"
    fi
  fi
fi

# ── Personas ─────────────────────────────────────────────────────────────────────────────────────
echo "personas"
SYNC="$CLAUDE/skills/agent-personas/scripts/sync_personas.py"
if [ "$DRY" -eq 1 ]; then
  say "would render the persona pool into ~/.claude/agents and ~/.codex/agents"
elif [ -f "$SYNC" ]; then
  python3 "$SYNC" | sed 's/^/  /'
else
  say "sync_personas.py missing — skipped"
fi

echo
echo "next:"
say "1. ./verify.sh"
say "2. review the model names in ~/.claude/skills/agent-personas/personas/*.md — they are examples,"
say "   not recommendations, and go stale as models change"
say "3. open a project and run the project-onboarding skill"
[ "$DRY" -eq 0 ] && say "Claude Code may need /hooks opened once, or a restart, to load the new hooks"
