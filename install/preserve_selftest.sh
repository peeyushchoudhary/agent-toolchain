#!/usr/bin/env bash
# Break-test for install_tree's carry-forward. verify.sh runs it.
#
# install_tree replaces a skill directory by a staged swap. A plain install must remove nothing
# (AC-12), so every file the installed copy has and the vendored tree lacks is carried into the
# staged tree. The property under test: such a file survives being installed over, at any depth,
# while a vendored file still wins over an installed one of the same name, and the vendored content
# lands. Deleting carried files is --retire-v5's job, tested in tests/test_install.py.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0

# install.sh runs from the top, so the functions under test are extracted as text, not sourced.
eval "$(sed -n '/^chmod_scripts()/,/^}/p;/^extras_between()/,/^}/p;/^install_tree()/,/^}/p' "$HERE/install.sh")"
say() { printf '  %s\n' "$1"; }
for fn in chmod_scripts extras_between install_tree; do
  declare -F "$fn" >/dev/null || { echo "$fn could not be read from install.sh" >&2; exit 2; }
done

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

# Vendored source: a skill as this repository ships it.
mkdir -p "$root/src/skill/scripts"
echo 'vendored' > "$root/src/skill/SKILL.md"
echo 'vendored tool' > "$root/src/skill/scripts/tool.py"

# Installed copy: an older SKILL.md and tool.py, plus files the package no longer ships, one nested.
mkdir -p "$root/dest/skill/scripts" "$root/dest/skill/references/deep"
echo 'old' > "$root/dest/skill/SKILL.md"
echo 'old tool' > "$root/dest/skill/scripts/tool.py"
echo 'machine-only data' > "$root/dest/skill/ledger.tsv"
echo 'older release script' > "$root/dest/skill/scripts/removed_checker.py"
echo 'older reference' > "$root/dest/skill/references/deep/old.md"
for f in ledger.tsv scripts/removed_checker.py references/deep/old.md; do
  [ -f "$root/dest/skill/$f" ] || { echo "FIXTURE NOT BUILT: $f" >&2; exit 2; }
done

install_tree "$root/src/skill" "$root/dest/skill"
check "install_tree succeeded" 0 "$?"
check "machine-only data survived" "machine-only data" "$(cat "$root/dest/skill/ledger.tsv" 2>/dev/null)"
check "an unshipped script survived" "older release script" "$(cat "$root/dest/skill/scripts/removed_checker.py" 2>/dev/null)"
check "a nested unshipped file survived" "older reference" "$(cat "$root/dest/skill/references/deep/old.md" 2>/dev/null)"
check "the vendored SKILL.md won" "vendored" "$(cat "$root/dest/skill/SKILL.md" 2>/dev/null)"
check "the vendored script won" "vendored tool" "$(cat "$root/dest/skill/scripts/tool.py" 2>/dev/null)"
check "no staging or aside directory was left" "0" "$(ls -d "$root/dest/"*.staging.* "$root/dest/"*.replacing.* 2>/dev/null | wc -l | tr -d ' ')"
check "extras_between lists exactly the carried files" \
  "ledger.tsv references/deep/old.md scripts/removed_checker.py" \
  "$(extras_between "$root/src/skill" "$root/dest/skill" | sort | tr '\n' ' ' | sed 's/ $//')"

echo
if [ "$fails" -eq 0 ]; then echo "PASS — install_tree carries forward what the package lacks"; exit 0; fi
echo "FAIL — $fails check(s)"; exit 1
