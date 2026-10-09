#!/usr/bin/env bash
# Unattended goal run: one fresh harness session at a time until `goal.py done` holds.
#
#   run.sh <goal-id> --harness claude|codex [--sessions N]     (default 6 sessions)
#
# Exit: 0 DONE (packet at .runs/<id>/packet.md), 3 STALLED (two sessions with no new tick or [Tn]
# commit), 4 PARKED (the active milestone has a [!] task and no [ ] task), 5 sessions exhausted,
# 2 usage. RUN_HARNESS_CMD, when set, replaces the harness command; it receives the prompt as $1.
set -uo pipefail

GOAL="${1:-}"; HARNESS=""; SESSIONS=6
[ -n "$GOAL" ] && shift
while [ $# -gt 0 ]; do
  case "$1" in
    --harness) HARNESS="${2:-}"; shift 2 ;;
    --sessions) SESSIONS="${2:-}"; shift 2 ;;
    *) echo "run.sh: unknown option $1" >&2; exit 2 ;;
  esac
done
case "$HARNESS" in claude|codex) ;; *) [ -n "${RUN_HARNESS_CMD:-}" ] || {
  sed -n '4p' "$0" >&2; exit 2; } ;; esac
[ -n "$GOAL" ] && [[ "$SESSIONS" =~ ^[0-9]+$ ]] || { sed -n '4p' "$0" >&2; exit 2; }

GOALPY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/goal.py"
ROOT="$(git rev-parse --show-toplevel)" || exit 2
cd "$ROOT" || exit 2
PLAN="docs/goals/$GOAL/plan.md"
RUNS=".runs/$GOAL"
mkdir -p "$RUNS"
goal() { python3 "$GOALPY" --goal "$GOAL" "$@"; }
stop() {  # stop CODE WORD — log, notify, exit
  echo "$(date -u +%FT%TZ) $2" >> "$RUNS/progress.md"
  echo "$2"
  if [ -z "${RUN_NO_NOTIFY:-}" ] && command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$2\" with title \"run.sh $GOAL\"" 2>/dev/null || true
  fi
  exit "$1"
}
score() {
  echo $(( $(grep -cE '^### \[x\] T[0-9]+' "$PLAN") \
         + $(git log --format=%s "goal/$GOAL/approved..HEAD" | grep -cE '\[T[0-9]+\]') ))
}
session() {
  if [ -n "${RUN_HARNESS_CMD:-}" ]; then
    $RUN_HARNESS_CMD "$1"
  elif [ "$HARNESS" = claude ]; then
    settings="$(mktemp)"
    printf '{"permissions": {"allow": ["Bash", "Edit", "Write"]}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python3 %s --goal %s stop-hook"}]}]}}\n' \
      "'$GOALPY'" "'$GOAL'" > "$settings"
    claude -p "$1" --settings "$settings"; rc=$?; rm -f "$settings"; return $rc
  else
    codex --ask-for-approval never exec --sandbox workspace-write "$1"
  fi
}

done_or_continue() { goal done >/dev/null 2>&1 && { goal packet >/dev/null; stop 0 DONE; }; }
stalled=0
done_or_continue
for i in $(seq 1 "$SESSIONS"); do
  before="$(score)"
  session "$(goal resume)"; rc=$?
  after="$(score)"
  echo "$(date -u +%FT%TZ) session $i/$SESSIONS ($HARNESS${RUN_HARNESS_CMD:+ test}) exit $rc, progress $before -> $after" >> "$RUNS/progress.md"
  done_or_continue  # DONE outranks STALLED: a session can close receipts and review without a tick
  if [ "$after" -gt "$before" ]; then stalled=0; else stalled=$((stalled + 1)); fi
  [ "$stalled" -ge 2 ] && stop 3 STALLED
  goal next >/dev/null 2>&1 || { goal status | grep -E ' active: ' | grep -qF '[!]' && stop 4 PARKED; }
done
stop 5 "SESSIONS EXHAUSTED"
