#!/usr/bin/env bash
# M1's end-to-end check: the real install.sh into a disposable HOME and CODEX_HOME, then the
# installed copies are exercised. Never touches the real ~/.claude or ~/.codex. Exit 0 on success.
set -uo pipefail

INSTALL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)" || { echo "e2e_install: could not create a temporary directory" >&2; exit 2; }
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/.codex"   # the installer skips Codex when its home is absent
export PYTHONDONTWRITEBYTECODE=1

errors=0
fail() { echo "e2e_install: FAIL: $1"; errors=$((errors + 1)); }

if ! HOME="$tmp" CODEX_HOME="$tmp/.codex" bash "$INSTALL/install.sh" > "$tmp/install.log" 2>&1; then
  cat "$tmp/install.log"
  fail "install.sh exited non-zero"
fi

for root in "$tmp/.claude" "$tmp/.codex"; do
  scripts="$root/skills/execution-methodology/scripts"
  for f in goal.py guard.py git-hooks.sh run.sh; do
    [ -f "$scripts/$f" ] || fail "$scripts/$f is missing"
  done
  [ -f "$scripts/goal.py" ] && { HOME="$tmp" python3 "$scripts/goal.py" --help > /dev/null 2>&1 ||
    fail "$scripts/goal.py --help exited non-zero"; }
  [ -f "$scripts/guard.py" ] && { HOME="$tmp" python3 "$scripts/guard.py" --self-test > "$tmp/self-test.log" 2>&1 ||
    { cat "$tmp/self-test.log"; fail "$scripts/guard.py --self-test exited non-zero"; }; }
done

for file in "$tmp/.claude/settings.json" "$tmp/.codex/hooks.json"; do
  n="$(python3 - "$file" <<'PY'
import json, sys
try:
    hooks = json.load(open(sys.argv[1], encoding="utf-8")).get("hooks", {})
except (OSError, ValueError):
    print(-1); raise SystemExit
print(sum("goal.py stop-hook" in h.get("command", "")
          for e in hooks.get("Stop", []) for h in e.get("hooks", [])))
PY
)"
  [ "$n" = "1" ] || fail "$file has $n Stop registration(s) of goal.py stop-hook, want 1"
done

if [ "$errors" -eq 0 ]; then
  echo "e2e_install: PASS (installed into both harnesses; goal.py, guard.py, git-hooks.sh, run.sh present; one Stop hook each; goal.py --help and guard.py --self-test ok)"
  exit 0
fi
echo "e2e_install: FAIL ($errors)"
exit 1
