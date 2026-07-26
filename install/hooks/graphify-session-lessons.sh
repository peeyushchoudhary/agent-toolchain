#!/usr/bin/env bash
# SessionStart: in any project that has a Graphify graph, refresh the deterministic lessons
# digest and surface it. `reflect --if-stale` is a no-op when LESSONS.md already postdates
# every input, so this costs ~nothing on repeat sessions and never calls an LLM.
#
# Silent no-op in projects without a graph.

set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"
graph="$root/graphify-out/graph.json"
lessons="$root/graphify-out/reflections/LESSONS.md"

[ -f "$graph" ] || exit 0
command -v graphify >/dev/null 2>&1 || exit 0

(cd "$root" && graphify reflect --if-stale >/dev/null 2>&1) || true
[ -f "$lessons" ] || exit 0

# Cap the injection: preferred sources and dead ends live at the top of the digest.
body=$(head -c 4000 "$lessons")
[ -n "$body" ] || exit 0

python3 -c '
import json, sys
body = sys.stdin.read()
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": (
            "Graphify lessons for this repo (graphify-out/reflections/LESSONS.md, "
            "deterministic digest of past query outcomes). Preferred sources are good "
            "starting points; known dead ends are worth skipping. These are navigation "
            "hints from earlier sessions, not current truth — confirm at the source line "
            "before acting.\n\n" + body
        ),
    },
    "suppressOutput": True,
}))
' <<<"$body"
