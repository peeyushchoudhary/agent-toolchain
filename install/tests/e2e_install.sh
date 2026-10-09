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
  for f in goal.py docs.py guard.py git-hooks.sh; do
    [ -f "$scripts/$f" ] || fail "$scripts/$f is missing"
  done
  [ -f "$scripts/goal.py" ] && { HOME="$tmp" python3 "$scripts/goal.py" --help > /dev/null 2>&1 ||
    fail "$scripts/goal.py --help exited non-zero"; }
  [ -f "$scripts/docs.py" ] && { HOME="$tmp" python3 "$scripts/docs.py" --help > /dev/null 2>&1 ||
    fail "$scripts/docs.py --help exited non-zero"; }
  [ -f "$scripts/guard.py" ] && { HOME="$tmp" python3 "$scripts/guard.py" --self-test > "$tmp/self-test.log" 2>&1 ||
    { cat "$tmp/self-test.log"; fail "$scripts/guard.py --self-test exited non-zero"; }; }
done

# The founder's open session is the chief (D30): the installer registers no hook and writes no settings file.
for file in "$tmp/.claude/settings.json" "$tmp/.codex/hooks.json"; do
  [ ! -e "$file" ] || fail "$file was written; the installer writes no settings or hooks file"
done

# The six agent files, each carrying install.sh's marker; then --uninstall removes them and the skill.
mark="$(sed -n 's/^AGENT_MARK="\(.*\)"$/\1/p' "$INSTALL/install.sh")"
[ -n "$mark" ] || fail "install.sh defines no AGENT_MARK"
agents=()
for n in builder reviewer scout; do agents+=("$tmp/.claude/agents/$n.md" "$tmp/.codex/agents/$n.toml"); done
for a in "${agents[@]}"; do
  grep -qxF "$mark" "$a" 2>/dev/null || fail "$a is missing or does not carry the install marker"
done
if ! HOME="$tmp" CODEX_HOME="$tmp/.codex" bash "$INSTALL/install.sh" --uninstall > "$tmp/uninstall.log" 2>&1; then
  cat "$tmp/uninstall.log"
  fail "install.sh --uninstall exited non-zero"
fi
for a in "${agents[@]}" "$tmp/.claude/skills/execution-methodology" "$tmp/.codex/skills/execution-methodology"; do
  [ ! -e "$a" ] || fail "$a is still present after --uninstall"
done

if [ "$errors" -eq 0 ]; then
  echo "e2e_install: PASS (installed into both harnesses; goal.py, docs.py, guard.py, git-hooks.sh present; no settings or hooks file written; goal.py --help, docs.py --help and guard.py --self-test ok; builder, reviewer and scout agents marked in both homes; --uninstall removed the agents and the skill)"
  exit 0
fi
echo "e2e_install: FAIL ($errors)"
exit 1
