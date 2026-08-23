#!/usr/bin/env bash
# Break-test for install_tree's PRESERVE_ACROSS_INSTALLS carve-out.
#
# Run by hand: ./preserve_selftest.sh
#
# Why this exists as a test rather than as care. install_tree replaces a skill directory wholesale,
# so every path under it that the vendored tree does not carry is deleted on each run. For a stale
# script that is the correct behaviour and the reason the function is written that way. For content
# that lives only on the installed machine it is destruction, and the two are indistinguishable by
# inspection — both are simply "a file the vendored tree does not have".
#
# The list was a single hard-coded `if` for ROUND-GRANTS.tsv for as long as there was one such path.
# The second one, agent-personas/tests, was never added, and so every install silently deleted a
# suite that existed in no other copy anywhere. Nothing failed. Nothing printed. It was noticed a
# milestone later, by which point four live files cited a suite that was not on disk.
#
# So the property under test is not "the code looks right" but "a path on the list survives being
# installed over, and one that is not on the list does not" — the second half matters as much,
# because a carve-out that preserved everything would resurrect deleted files forever.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0

# Source install.sh for install_tree and the list, without running the installer: it executes from
# the top, so it is read as text and the two pieces under test are extracted. Sourcing the whole
# file would install the toolchain as a side effect of testing it.
eval "$(sed -n '/^PRESERVE_ACROSS_INSTALLS="/,/^"$/p' "$HERE/install.sh")"
eval "$(sed -n '/^chmod_scripts()/,/^}/p;/^install_tree()/,/^}/p' "$HERE/install.sh")"

check() {  # check DESCRIPTION EXPECTED ACTUAL
  if [ "$2" = "$3" ]; then
    printf '  ok    %s\n' "$1"
  else
    printf '  FAIL  %s — expected %s, got %s\n' "$1" "$2" "$3"
    fails=$((fails+1))
  fi
}

root="$(mktemp -d)" || { echo "could not create a fixture root" >&2; exit 2; }
trap 'rm -rf "$root"' EXIT

# The vendored source: a skill as this repository ships it. No tests/, no ledger.
mkdir -p "$root/src/agent-personas/scripts" "$root/src/execution-methodology/scripts"
echo 'vendored' > "$root/src/agent-personas/SKILL.md"
echo 'vendored' > "$root/src/execution-methodology/SKILL.md"

# The installed machine: the same skills, plus the two machine-only paths, plus one file that is
# genuinely stale — a script the vendored tree dropped, which MUST NOT come back.
mkdir -p "$root/dest/agent-personas/tests" "$root/dest/agent-personas/scripts" \
         "$root/dest/execution-methodology"
echo 'old' > "$root/dest/agent-personas/SKILL.md"
echo 'the only copy anywhere' > "$root/dest/agent-personas/tests/test_repo_sync.py"
echo 'retired last release' > "$root/dest/agent-personas/scripts/removed_checker.py"
echo 'old' > "$root/dest/execution-methodology/SKILL.md"
printf 'subject\tr3\tabc\t2026-08-21\tfounder ruling\n' > "$root/dest/execution-methodology/ROUND-GRANTS.tsv"

# ASSERT THE FIXTURE BEFORE ASSERTING ANYTHING ABOUT IT. Both interesting checks below are
# absence/presence claims, and an absence check passes hardest when the file was never created --
# the fail-open shape this whole test exists to catch, reproduced inside the test itself.
for f in "$root/dest/agent-personas/tests/test_repo_sync.py" \
         "$root/dest/agent-personas/scripts/removed_checker.py" \
         "$root/dest/execution-methodology/ROUND-GRANTS.tsv"; do
  [ -f "$f" ] || { echo "FIXTURE NOT BUILT: $f was never created, so the checks below prove nothing" >&2; exit 2; }
done

install_tree "$root/src/agent-personas" "$root/dest/agent-personas"
check "install_tree succeeded (agent-personas)" 0 "$?"
install_tree "$root/src/execution-methodology" "$root/dest/execution-methodology"
check "install_tree succeeded (execution-methodology)" 0 "$?"

# THE REGRESSION. This is the file whose absence went unnoticed for a milestone.
check "the non-vendored persona suite survived" \
  "the only copy anywhere" "$(cat "$root/dest/agent-personas/tests/test_repo_sync.py" 2>/dev/null)"
check "the operator ledger survived" \
  "founder ruling" "$(cut -f5 "$root/dest/execution-methodology/ROUND-GRANTS.tsv" 2>/dev/null)"

# THE OTHER HALF, and it is not decoration. A carve-out that preserved anything the vendored tree
# lacked would keep every retired file alive forever, which is a slower version of the same bug:
# the installed machine stops matching what this repository ships and nobody can see the difference.
check "a retired vendored file did NOT come back" \
  "absent" "$([ -e "$root/dest/agent-personas/scripts/removed_checker.py" ] && echo present || echo absent)"

# The vendored copy is what an install is FOR.
check "the vendored content actually landed" \
  "vendored" "$(cat "$root/dest/agent-personas/SKILL.md" 2>/dev/null)"

# A vendored copy must WIN, so that vendoring a listed path later needs no edit to the list.
rm -rf "$root/dest2"; mkdir -p "$root/dest2/execution-methodology"
printf 'machine copy\n' > "$root/dest2/execution-methodology/ROUND-GRANTS.tsv"
printf 'vendored copy\n' > "$root/src/execution-methodology/ROUND-GRANTS.tsv"
install_tree "$root/src/execution-methodology" "$root/dest2/execution-methodology"
check "a vendored copy wins over the preserved one" \
  "vendored copy" "$(cat "$root/dest2/execution-methodology/ROUND-GRANTS.tsv" 2>/dev/null)"
rm -f "$root/src/execution-methodology/ROUND-GRANTS.tsv"

# Every entry must name a skill that exists, or it is a line that silently protects nothing — which
# is the state agent-personas/tests was in before it was a line at all.
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  check "entry names a shipped skill: $rel" \
    "yes" "$([ -d "$HERE/skills/${rel%%/*}" ] && echo yes || echo no)"
done <<< "$PRESERVE_ACROSS_INSTALLS"

echo
if [ "$fails" -eq 0 ]; then echo "PASS — install_tree preserves what is listed and nothing else"; exit 0; fi
echo "FAIL — $fails check(s)"; exit 1
