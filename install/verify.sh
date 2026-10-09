#!/usr/bin/env bash
# The repository gate. Run from install/ or anywhere inside the repository.
#
#   ./verify.sh               this repository's checks
#   ./verify.sh --installed   also: parity of the installed copies in ~/.claude and $CODEX_HOME
#                             (read-only; never part of the default run)
#   ./verify.sh --installed-only   that parity check alone
#
# Output contract, which gate.py reads: each unittest suite prints unittest's own output unchanged,
# every other check prints `verify: <id> ok` or `FAIL: <id> (verify.checks)`, and the last line is
# `verify: PASS` or `verify: FAIL (<n> checks)`; exit 0 or 1.
set -uo pipefail
INSTALLED=0
for arg in "$@"; do
  case "$arg" in
    --installed) INSTALLED=1 ;;
    --installed-only) INSTALLED=2 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 64 ;;
  esac
done
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null)" || ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 2
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)" || { echo "could not create a temporary directory" >&2; exit 2; }
trap 'rm -rf "$TMP"' EXIT
SKILL=install/skills/execution-methodology
GUARD="$SKILL/scripts/guard.py"

FAILED=0 FAILED_NAMES=""
section() { printf '\n== %s\n' "$1"; }
pass()    { printf 'verify: %s ok\n' "$1"; }
failed()  { FAILED=$((FAILED + 1)); FAILED_NAMES="$FAILED_NAMES $1"; printf 'FAIL: %s (verify.%s)\n' "$1" "${2:-checks}"; }
check()   { local id="$1"; shift; if "$@"; then pass "$id"; else failed "$id"; fi; }   # check ID CMD...

# run_suite ID DIR — unittest discover, output unchanged. A suite that runs no test or crashes
# without a unittest verdict fails under its own id; failing tests are already named by unittest.
run_suite() {
  local id="$1" log="$TMP/$1.log" rc ran
  section "suite: $id"
  python3 -m unittest discover -s "$2" -t "$2" -p 'test*.py' 2>&1 | tee "$log"; rc=${PIPESTATUS[0]}
  ran=$(sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\} in .*/\1/p' "$log" | tail -1)
  if [ -z "$ran" ] || [ "$ran" -eq 0 ]; then failed "${id}_ran_no_tests"
  elif [ "$rc" -ne 0 ] && ! grep -qE '^FAILED \(' "$log"; then failed "${id}_crashed"
  elif [ "$rc" -ne 0 ]; then FAILED=$((FAILED + 1)); FAILED_NAMES="$FAILED_NAMES $id"; echo "verify: $id has failing tests (ids above)"
  else pass "$id ($ran tests)"; fi
}

# 8. Installed parity (--installed: after check 7; --installed-only: alone). Each harness home holds
# this skill (tests/ excepted) and global.md byte-equal, and no Stop registration of goal.py
# stop-hook (run.sh registers it per session). Files the installed skill carries forward from an
# older install are listed, not counted (--retire-v5 judges them).
installed_parity() {
  local CX="${CODEX_HOME:-$HOME/.codex}" drift=0 roots r g h n
  section "installed parity (read-only)"
  roots=("$HOME/.claude"); [ -d "$CX" ] && roots+=("$CX")   # an array: a home may contain spaces
  for r in "${roots[@]}"; do
    if [ "$r" = "$HOME/.claude" ]; then g="$r/CLAUDE.md" h="$r/settings.json"; else g="$r/AGENTS.md" h="$r/hooks.json"; fi
    cmp -s install/global.md "$g" || { echo "  drift: $g differs from install/global.md"; drift=1; }
    diff -rq -x __pycache__ -x tests "$SKILL" "$r/skills/execution-methodology" > "$TMP/diff" 2>&1
    grep -F "Only in $r/" "$TMP/diff" | sed 's/^/  carried forward: /'
    grep -vF "Only in $r/" "$TMP/diff" | sed 's/^/  drift: /' | grep . && drift=1
    n="$(python3 -c 'import json,sys
try: hooks = json.load(open(sys.argv[1])).get("hooks", {})
except (OSError, ValueError): hooks = {}
print(sum("goal.py stop-hook" in h.get("command", "") for e in hooks.get("Stop", []) for h in e.get("hooks", [])))' "$h")"
    [ "$n" = 0 ] || { echo "  drift: $h has $n Stop registrations of goal.py stop-hook, want 0 (./install.sh drops them)"; drift=1; }
  done
  if [ "$drift" -eq 0 ]; then pass installed_parity
  else echo "  run ./install.sh to bring the installed copies level with this repository"; failed installed_parity installed; fi
}
verdict() {
  echo
  if [ "$FAILED" -eq 0 ]; then echo "verify: PASS"; exit 0; fi
  echo "failing:$FAILED_NAMES"
  echo "verify: FAIL ($FAILED checks)"
  exit 1
}
[ "$INSTALLED" -ne 2 ] || { installed_parity; verdict; }

# 1–2. The skill's suite, then the installer's (test_install.py and the size ceiling, test_size.py).
run_suite suite_execution-methodology "$SKILL/tests"
run_suite install install/tests

# 3–4. The guard: its self-test, then the tree (tracked plus untracked non-ignored files, symlinks as
# their link text) staged into a scratch repository by tree_scan.py and scanned there. Exit 2 (the
# guard could not run) fails the check.
section "guard"
check guard_self_test python3 "$GUARD" --self-test
mkdir -p "$TMP/tree"
check guard bash -c 'python3 "$1/install/tests/tree_scan.py" "$1" "$2" && cd "$2" && python3 "$1/$3" --staged' _ "$ROOT" "$TMP/tree" "$GUARD"

# 5. Relative links in AGENTS.md, README.md and docs/**/*.md resolve (install/tests/link_check.py).
section "links"
python3 install/tests/link_check.py "$ROOT" || failed links   # prints `verify: links ok` itself

# 6. No current file names a deleted component. Over the tracked and non-ignored files in install/,
# README.md, AGENTS.md and docs/. Records may name them as rationale and are excluded: decisions.md,
# measurements.md, docs/goals/**, install.sh's retire list (between its markers), and this file.
# The rest of EXCLUDE is owed to later tasks or to files this one may not edit; each says why.
# Persona names that are ordinary words (planner, developer, scout, architect) are not scanned.
section "dangling names"
RE='methodology-management|project-onboarding|project-migration|project-conformance|agent-persona-factory|gate-sandbox'
RE="$RE"'|validate_card|check_review_budget|trace_check|spec_check|ratio_meter|weekly_review|verify_junit|start_junit_run|milestone_seal|plan_waves|sync_methodology|ROUND-GRANTS|task-card\.md'
RE="$RE"'|docs-steward|contract-architect|senior-developer|test-judge|migration-validator|product-steward|chief-of-staff|security-validator'
RE="$RE"'|review\.py|run_goal|goal-session|smoke_goal|sync_personas|agent-personas|graphify|graph-navigation|preflight|disclosure-check'
RE="$RE"'|validate_disclosure|check_github|check_toolchain|migrate_to_standard|install_hooks|identifier_guard|push_guard'
RE="$RE"'|progressive-disclosure|explainer-template|escalation\.md'
EXCLUDE="docs/decisions/decisions.md docs/product/measurements.md install/verify.sh"
# test_rules.py asserts these names absent from the routed files, so it must hold them.
EXCLUDE="$EXCLUDE install/skills/execution-methodology/tests/test_rules.py"
# The skills .gitignore explains why it is an allowlist with the vendor tool that writes beside it.
EXCLUDE="$EXCLUDE install/skills/.gitignore"
# T8 deleted the v6 records and the diagram the old README embedded.
EXCLUDE="$EXCLUDE docs/assets/readme/skill-surface.svg docs/architecture/lean-execution.md"
EXCLUDE="$EXCLUDE docs/product/specs/F-3-lean-execution.md docs/product/plans/F-3-lean-execution.md"
EXCLUDE="$EXCLUDE docs/product/improvements-weekly.md docs/agents/lessons.md"
: > "$TMP/hits"
git ls-files -z --cached --others --exclude-standard -- install README.md AGENTS.md docs | tr '\0' '\n' > "$TMP/files"
[ -s "$TMP/files" ] || echo "verify: could not list the files to scan" > "$TMP/hits"
while IFS= read -r f; do
  [ -f "$f" ] && grep -Iq . "$f" 2>/dev/null || continue    # missing, binary or empty
  case " $EXCLUDE " in *" $f "*) continue ;; esac
  case "$f" in docs/goals/*) continue ;; esac
  awk -v re="$RE" -v f="$f" '
    f == "install/install.sh" && /^# BEGIN retire-v5 list$/ { skip = 1 }
    f == "install/install.sh" && /^# END retire-v5 list$/   { skip = 0; next }
    !skip { line = $0
      while (match(line, re)) { print f ":" FNR ": " substr(line, RSTART, RLENGTH); line = substr(line, RSTART + RLENGTH) } }
  ' "$f" >> "$TMP/hits"
done < "$TMP/files"
if [ -s "$TMP/hits" ]; then cat "$TMP/hits"; failed dangling_references; else pass dangling_references; fi

# 7. The installer's dry run, against a scratch HOME so the result describes this repository.
section "install.sh --dry-run (scratch HOME)"
mkdir -p "$TMP/hm/.codex"
if HOME="$TMP/hm" CODEX_HOME="$TMP/hm/.codex" bash install/install.sh --dry-run > "$TMP/dry.log" 2>&1; then
  cat "$TMP/dry.log"; pass install_dry_run
else cat "$TMP/dry.log"; failed install_dry_run; fi

[ "$INSTALLED" -eq 0 ] || installed_parity
verdict
