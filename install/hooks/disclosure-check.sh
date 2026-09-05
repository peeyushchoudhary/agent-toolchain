#!/usr/bin/env bash
# SessionStart: report the state of this project's agent context.
#
# Reports, never writes. This fires automatically in every directory a session starts in —
# including repositories that are not yours and scratch clones — so creating files here would put
# unexplained untracked files in someone's tree. It tells; the human decides.
#
# For a project with no git (and therefore no pre-commit hook possible), this is the ONLY automated
# integrity check that can run at all, which is why it validates rather than just checking presence.
#
# Silent when there is nothing worth saying.

set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"
skill="$HOME/.claude/skills/progressive-disclosure/scripts"
validator="$skill/validate_disclosure.py"

looks_like_project=0
for marker in .git package.json Makefile pyproject.toml go.mod Cargo.toml build.gradle.kts pom.xml; do
  [ -e "$root/$marker" ] && looks_like_project=1 && break
done
# A directory can hold real source and carry none of those markers — plain scripts, or a project
# whose manifest was never added. That is the case that most needs flagging, because it is usually
# also the one with no git. Threshold of 3 keeps a stray script in a documents folder quiet.
if [ "$looks_like_project" -eq 0 ]; then
  n=$(find "$root" -maxdepth 3 \( -name '*.py' -o -name '*.ts' -o -name '*.js' -o -name '*.java' \
        -o -name '*.go' -o -name '*.rs' \) -not -path '*/node_modules/*' -not -path '*/.*' \
        2>/dev/null | head -3 | wc -l | tr -d ' ')
  [ "${n:-0}" -ge 3 ] && looks_like_project=1
fi
[ "$looks_like_project" -eq 1 ] || exit 0

index="$root/docs/agents/README.md"
notes=""
add() { notes="${notes}$1"$'\n'; }

# 0. Is this project stored anywhere but this laptop, and is it stored safely? Runs for every
#    project, route or not — a repo with no remote is the one failure that loses everything, and
#    it is invisible from inside the working tree.
gh_check="$skill/check_github.py"
if [ -f "$gh_check" ]; then
  gh_out=$(cd "$root" && PYTHONDONTWRITEBYTECODE=1 python3 "$gh_check" . --hook 2>/dev/null || true)
  [ -n "$gh_out" ] && add "$gh_out"
fi

# 0b. The machine-global toolchain: persona pool vs generated agents, the mirrored instruction
#     blocks, and the Codex skills copy. None of these belong to any repository, which is precisely
#     why nothing else notices when they drift — a stale persona or an unmirrored rule is invisible
#     from inside a project and silent at the point of use.
tc_check="$skill/check_toolchain.py"
if [ -f "$tc_check" ]; then
  tc_out=$(PYTHONDONTWRITEBYTECODE=1 python3 "$tc_check" --hook 2>/dev/null || true)
  [ -n "$tc_out" ] && add "$tc_out"
fi

if [ ! -f "$index" ]; then
  # Name what is actually missing rather than issuing a generic nag. A prompt that lists three
  # specific absences reads as a finding; "this project is not set up" reads as noise.
  missing="no disclosure route (docs/agents/README.md)"
  [ -d "$root/.git" ] || missing="$missing, not a git repository"
  if [ -d "$root/.git" ] && ! grep -q "progressive-disclosure" "$root/.git/hooks/pre-commit" 2>/dev/null; then
    missing="$missing, no git hooks"
  fi
  [ -f "$root/README.md" ] || missing="$missing, no README"
  add "AGENT CONTEXT: this project is not initialised for agent work — $missing. Report this gap. The user can invoke \`methodology-management\` (or the \`project-onboarding\` compatibility entry) for a setup proposal. Do not select setup from this notice; follow an explicit source/toolchain repository route where present. Do not scaffold a repository, create a remote, or push unasked."
else
  # 1. Is the route actually intact? On a non-git project this is the only check that ever runs.
  # --readme included: the seven-section README contract is part of the standard, and it is checked
  # here because this hook fires in every project every session. Without it the README checks run
  # nowhere at all — nine errors once sat unseen in a repository while the route summary printed a
  # reassuring "0 error(s)", because neither this hook nor pre-commit passed --readme.
  if [ -f "$validator" ]; then
    out=$(cd "$root" && PYTHONDONTWRITEBYTECODE=1 python3 "$validator" . --readme --hook 2>&1 || true)
    [ -n "$out" ] && \
      add "AGENT CONTEXT: this project's disclosure route needs attention:"$'\n'"$out"
  fi

  # 2. Git hooks are not cloned, so a fresh clone silently loses its guard rails.
  if [ -d "$root/.git" ] && ! grep -q "progressive-disclosure" "$root/.git/hooks/pre-commit" 2>/dev/null; then
    add "AGENT CONTEXT: this clone has no pre-commit route check (git hooks are never cloned). Install with \`python3 $skill/install_hooks.py .\`."
  fi

  # 3. Documentation changes never trigger a graph rebuild; nothing else notices they went stale.
  graph="$root/graphify-out/graph.json"
  if [ -f "$graph" ]; then
    stale=$(find "$root/docs" "$root/AGENTS.md" -newer "$graph" -type f 2>/dev/null | grep -cv superpowers || true)
    if [ "${stale:-0}" -gt 0 ]; then
      add "AGENT CONTEXT: $stale documentation file(s) are newer than graphify-out/graph.json, so graph answers about docs are stale. A code-only refresh is \`make graph-update\`; documentation needs a semantic rebuild (\`make graph-build\` then \`graphify cluster-only .\`)."
    fi
  fi

  # 4. The cross-agent learning channel, if this project keeps one.
  [ -f "$root/docs/agents/lessons.md" ] && \
    add "AGENT CONTEXT: this project keeps route lessons at docs/agents/lessons.md — read it before trusting a guide, and append there when something in the docs misleads you."
fi

# >>> execution-methodology adoption >>>
# Reports whether this repository has adopted the shared execution methodology, has drifted from
# it, or deliberately deferred it. Reports only: it never renders, never adopts, and never fails a
# session. --adoption-check exits 0 by contract, and `|| true` covers anything it does not.
# Skips silently when this repo has no route or the script is not installed.
_em_sync="$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py"
if [ -f "$root/docs/agents/README.md" ] && [ -f "$_em_sync" ]; then
  _em_out=$(PYTHONDONTWRITEBYTECODE=1 python3 "$_em_sync" --repo "$root" --adoption-check 2>/dev/null || true)
  [ -n "$_em_out" ] && add "$_em_out"
fi
# <<< execution-methodology adoption <<<

[ -n "$notes" ] || exit 0

python3 -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.stdin.read().strip()},
    "suppressOutput": True,
}))
' <<<"$notes"
