#!/usr/bin/env bash
# git-hooks.sh [--guard PATH] [--uninstall] [REPO]
#
# Installs guard.py into a repository's git hooks: pre-commit (--staged), commit-msg (--message)
# and pre-push (--pre-push, stdin forwarded). The hooks directory comes from
# `git rev-parse --git-path hooks`, so core.hooksPath is honoured. Every file written carries the
# marker line below; an existing hook without it is left alone and reported (exit 1). --uninstall
# removes only marked files. The guard defaults to the installed skill's copy and must exist: an
# absent guard is refused (exit 2) rather than registered. Exit 0 done, 1 a hook left alone,
# 2 could not run.
set -uo pipefail

MARKER="# swe-agent guard"
GUARD="$HOME/.claude/skills/execution-methodology/scripts/guard.py"
UNINSTALL=0
REPO="."
while [ $# -gt 0 ]; do
  case "$1" in
    --guard) [ $# -ge 2 ] || { echo "git-hooks: --guard needs a path" >&2; exit 2; }; GUARD="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    -*) echo "git-hooks: unknown option $1" >&2; exit 2 ;;
    *) REPO="$1"; shift ;;
  esac
done

HOOKS="$(git -C "$REPO" rev-parse --path-format=absolute --git-path hooks 2>/dev/null)" ||
  { echo "git-hooks: $REPO is not a git repository" >&2; exit 2; }

if [ "$UNINSTALL" -eq 0 ]; then
  [ -f "$GUARD" ] || { echo "git-hooks: no guard at $GUARD; install the skill first (nothing written)" >&2; exit 2; }
  GUARD="$(cd "$(dirname "$GUARD")" && pwd)/$(basename "$GUARD")"
  QUOTED="'${GUARD//\'/\'\\\'\'}'"   # single-quoted for /bin/sh
fi

status=0
for hook in pre-commit commit-msg pre-push; do
  file="$HOOKS/$hook"
  if [ "$UNINSTALL" -eq 1 ]; then
    if [ -f "$file" ] && grep -qxF "$MARKER" "$file"; then rm -f "$file" && echo "removed $file"; fi
    continue
  fi
  if [ -e "$file" ] && ! grep -qxF "$MARKER" "$file"; then
    echo "git-hooks: $file exists and is not ours; left alone" >&2; status=1; continue
  fi
  case "$hook" in
    pre-commit) cmd='python3 "$GUARD" --staged' ;;
    commit-msg) cmd='python3 "$GUARD" --message "$1"' ;;
    pre-push)   cmd='python3 "$GUARD" --pre-push "$@"' ;;   # stdin is inherited, so the payload reaches it
  esac
  mkdir -p "$HOOKS" || exit 2
  printf '#!/bin/sh\n%s\nGUARD=%s\nexec %s\n' "$MARKER" "$QUOTED" "$cmd" > "$file" && chmod +x "$file" ||
    { echo "git-hooks: could not write $file" >&2; exit 2; }
  echo "wrote $file"
done
exit "$status"
