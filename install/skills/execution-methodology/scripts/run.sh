#!/usr/bin/env bash
# Unattended goal run: one fresh harness session at a time until `goal.py done` holds.
#
#   run.sh <goal-id> --harness claude|codex [--sessions N]     (default 6 sessions)
#
# Exit: 0 DONE (packet at .runs/<id>/packet.md), 3 STALLED (two sessions with no new tick or [Tn]
# commit), 4 PARKED (the active milestone has a [!] task and no [ ] task), 5 sessions exhausted,
# 2 usage. RUN_HARNESS_CMD, when set, replaces the harness command; it receives the prompt as $1 and
# then the full harness command line it replaces, with the session's Stop hook registration.
# RUN_PROMPT, when set, replaces the goal.py resume prompt (e2e_run.sh's forbidden-push probe).
#
# Permissions (founder decision, S-1 plan): a scoped allowlist, a deny list and a sandbox with the
# network off, never a blanket allow. Each session's Stop hook is registered here, for that session
# only. User and project settings are not loaded (Claude --setting-sources "", Codex
# --ignore-user-config --ignore-rules), so nothing outside this file widens the envelope.
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

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOALPY="$SCRIPTS/goal.py"
ROOT="$(git rev-parse --show-toplevel)" || exit 2
ROOT="$(cd "$ROOT" && pwd -P)"
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

# The Claude settings for one session: allow, deny, sandbox, and the Stop hook. The plan's gate,
# full_gate and every milestone's e2e are allowed verbatim, read with goal.py's own parser.
claude_settings() {
  python3 - "$SCRIPTS" "$ROOT" "$PLAN" "$GOAL" <<'PY'
import json, shlex, sys
scripts, root, plan, goal = sys.argv[1:5]
sys.path.insert(0, scripts)
from goal import parse_plan
p = parse_plan(open(f"{root}/{plan}", encoding="utf-8").read())
cmds = [p["meta"].get("gate"), p["meta"].get("full_gate")] + [m.get("e2e") for m in p["milestones"].values()]
allow = ["Bash(git add *)", "Bash(git commit *)", "Bash(git status*)", "Bash(git diff *)", "Bash(git log *)",
         "Bash(git rev-parse *)", "Bash(python3 *goal.py *)", "Bash(python3 *gate.py *)"]
allow += [f"Bash({c})" for c in dict.fromkeys(c for c in cmds if c)]
allow += ["Edit", "Write", "Read", "Grep", "Glob", "Agent"]
deny = ["Bash(git push *)", "Bash(gh *)", "Bash(curl *)", "Bash(wget *)", "Bash(rm -rf *)",
        "Bash(git reset --hard *)", "Bash(git checkout -- *)", "WebFetch", "WebSearch"]
hook = "python3 %s --goal %s stop-hook" % (shlex.quote(scripts + "/goal.py"), shlex.quote(goal))
print(json.dumps({
    "permissions": {"allow": allow, "deny": deny},
    "sandbox": {"enabled": True, "failIfUnavailable": True, "autoAllowBashIfSandboxed": False,
                "allowUnsandboxedCommands": False, "network": {"allowedDomains": []},
                "filesystem": {"allowWrite": [root, f"{root}/.runs"]}},
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": hook}]}]},
}, indent=2))
PY
}
# One line for progress.md from the harness's JSON output: Claude's total_cost_usd, Codex's tokens.
cost_of() {  # cost_of HARNESS FILE
  python3 - "$1" "$2" <<'PY'
import json, sys
harness, path = sys.argv[1:3]
try:
    lines = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip().startswith("{")]
except (OSError, ValueError):
    lines = []
if harness == "claude":
    r = next((l for l in reversed(lines) if l.get("type") == "result"), {})
    print(f"cost ${r.get('total_cost_usd', '?')}, {r.get('num_turns', '?')} turns, "
          f"{len(r.get('permission_denials') or [])} denials" if r else "cost unknown (no result object)")
else:
    u = [l.get("usage", {}) for l in lines if l.get("type") == "turn.completed"]
    tok = lambda k: sum(x.get(k, 0) for x in u)
    print(f"tokens in {tok('input_tokens')} (cached {tok('cached_input_tokens')}), out {tok('output_tokens')}"
          if u else "tokens unknown (no turn.completed)")
PY
}
session() {  # session PROMPT OUT — run one fresh session, its JSON output to OUT
  local cmd settings="" hook rc
  if [ "$HARNESS" = codex ]; then
    hook="python3 '$SCRIPTS/goal.py' --goal '$GOAL' stop-hook"
    hook="${hook//\\/\\\\}"; hook="${hook//\"/\\\"}"
    # .git is read-only under workspace-write, so it is the one extra writable root (commits).
    cmd=(codex --ask-for-approval never exec --sandbox workspace-write
      -c sandbox_workspace_write.network_access=false
      -c "sandbox_workspace_write.writable_roots=[\"$ROOT/.git\"]"
      -c "hooks.Stop=[{hooks=[{type=\"command\",command=\"$hook\"}]}]" --dangerously-bypass-hook-trust
      --ignore-user-config --ignore-rules -C "$ROOT" --json "$1")
  else
    settings="$(mktemp)"
    claude_settings > "$settings" || { rm -f "$settings"; return 2; }
    cmd=(claude -p "$1" --permission-mode dontAsk --setting-sources "" --settings "$settings" --output-format json)
  fi
  if [ -n "${RUN_HARNESS_CMD:-}" ]; then $RUN_HARNESS_CMD "$1" "${cmd[@]}" > "$2"
  elif [ "$HARNESS" = codex ]; then "${cmd[@]}" > "$2" < /dev/null
  else "${cmd[@]}" > "$2"; fi
  rc=$?; [ -z "$settings" ] || rm -f "$settings"; return $rc
}
prompt() {
  if [ -n "${RUN_PROMPT:-}" ]; then printf '%s\n' "$RUN_PROMPT"; return; fi
  goal resume
  printf '\nThe execution-methodology skill is %s/SKILL.md; <skill> is %s. Push, merge and network are not available.\n' \
    "$(dirname "$SCRIPTS")" "$(dirname "$SCRIPTS")"
}

done_or_continue() { goal done >/dev/null 2>&1 && { goal packet >/dev/null; stop 0 DONE; }; }
stalled=0
done_or_continue
for i in $(seq 1 "$SESSIONS"); do
  before="$(score)" out="$RUNS/session-$i.json" t0="$(date +%s)"
  session "$(prompt)" "$out"; rc=$?
  after="$(score)" secs=$(( $(date +%s) - t0 ))
  echo "$(date -u +%FT%TZ) session $i/$SESSIONS ($HARNESS${RUN_HARNESS_CMD:+ test}) exit $rc, ${secs}s, $(cost_of "$HARNESS" "$out"), progress $before -> $after" >> "$RUNS/progress.md"
  done_or_continue  # DONE outranks STALLED: a session can close receipts and review without a tick
  if [ "$after" -gt "$before" ]; then stalled=0; else stalled=$((stalled + 1)); fi
  [ "$stalled" -ge 2 ] && stop 3 STALLED
  goal next >/dev/null 2>&1 || { goal status | grep -E ' active: ' | grep -qF '[!]' && stop 4 PARKED; }
done
stop 5 "SESSIONS EXHAUSTED"
