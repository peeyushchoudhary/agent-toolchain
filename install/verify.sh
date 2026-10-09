#!/usr/bin/env bash
# The repository gate. Run from install/ or anywhere inside the repository.
#
#   ./verify.sh               this repository's checks
#   ./verify.sh --installed   also: parity of the installed skills, hooks and personas against
#                             ~/.claude and ~/.codex (read-only; never part of the default run)
#
# Output contract, which gate.py reads: each unittest suite prints unittest's own output unchanged
# (`Ran N tests`, `OK` / `FAILED (...)`, `FAIL: test_x (module.Class.test_x)`), and every other
# check that fails prints one line `FAIL: <check> (verify.checks)`, so each failure is attributable
# by id. The last line is `verify: PASS` or `verify: FAIL (<n> checks)`; exit 0 or 1.
set -uo pipefail

INSTALLED=0
for arg in "$@"; do
  case "$arg" in
    --installed) INSTALLED=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 64 ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null)" || ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 2
export PYTHONDONTWRITEBYTECODE=1
PD="install/skills/progressive-disclosure/scripts"
TMP="$(mktemp -d)" || { echo "could not create a temporary directory" >&2; exit 2; }
trap 'rm -rf "$TMP"' EXIT

FAILED=0
FAILED_NAMES=""
section() { printf '\n== %s\n' "$1"; }
pass()    { printf 'verify: %s ok\n' "$1"; }
failed()  {  # failed CHECK_ID [SCOPE] — SCOPE defaults to checks
  FAILED=$((FAILED + 1)); FAILED_NAMES="$FAILED_NAMES $1"
  printf 'FAIL: %s (verify.%s)\n' "$1" "${2:-checks}"
}

# Published skills: install/skills/.gitignore's `!/name` lines that name a directory, exactly as
# install.sh reads them.
published_skills() {
  awk '/^!\/[A-Za-z0-9._-]+$/ { print substr($0, 3) }' install/skills/.gitignore |
    while IFS= read -r s; do [ -d "install/skills/$s" ] && echo "$s"; done
}

# run_suite ID DIR [PATTERN] — unittest discover, output unchanged. A suite that runs no test, or
# exits non-zero without a unittest verdict (a crash), is a failure of its own; test failures are
# already attributed by unittest's FAIL:/ERROR: lines and get no second id here.
run_suite() {
  local id="$1" dir="$2" pattern="${3:-test*.py}" log="$TMP/$1.log" rc ran
  python3 -m unittest discover -s "$dir" -t "$dir" -p "$pattern" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  ran=$(sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\} in .*/\1/p' "$log" | tail -1)
  if [ -z "$ran" ] || [ "$ran" -eq 0 ]; then
    failed "${id}_ran_no_tests"
  elif [ "$rc" -ne 0 ] && ! grep -qE '^FAILED \(' "$log"; then
    failed "${id}_crashed"
  elif [ "$rc" -ne 0 ]; then
    FAILED=$((FAILED + 1)); FAILED_NAMES="$FAILED_NAMES $id"
    printf 'verify: %s has failing tests (ids above)\n' "$id"
  else
    pass "$id ($ran tests)"
  fi
}

# ── 1. Every published skill's unittest suite ────────────────────────────────────────────────────
# A skill with code (scripts/) must carry a suite; one with neither (graph-navigation) has nothing
# to run.
for s in $(published_skills); do
  if [ ! -d "install/skills/$s/tests" ]; then
    if [ -d "install/skills/$s/scripts" ]; then
      section "suite: $s"; failed "suite_${s}_missing"
      echo "verify: install/skills/$s has scripts/ but no tests/"
    fi
    continue
  fi
  section "suite: $s"
  run_suite "suite_$s" "install/skills/$s/tests"
done

# ── 2. Route and structure standard ──────────────────────────────────────────────────────────────
section "validate_disclosure --standard"
if python3 "$PD/validate_disclosure.py" . --standard; then pass disclosure_standard
else failed disclosure_standard; fi

# ── 3. The guard: its self-test, then the tree ───────────────────────────────────────────────────
# guard.py scans a staged diff, so the tree (tracked files plus untracked files that are not
# ignored, i.e. what a commit could carry) is staged into a scratch repository with no history and
# scanned there. The origin URL is carried over so the account rule has something to check. Exit 2
# (private-name list missing, guard could not run) fails this check rather than passing it.
GUARD="install/skills/execution-methodology/scripts/guard.py"
section "guard --self-test"
if python3 "$GUARD" --self-test; then pass guard_self_test; else failed guard_self_test; fi
section "guard over the tree"
SCAN="$TMP/tree"
mkdir -p "$SCAN"
if git ls-files -z --cached --others --exclude-standard |
     python3 -c '
import os, shutil, sys
dest = sys.argv[1]
for rel in filter(None, sys.stdin.buffer.read().decode("utf-8", "surrogateescape").split("\0")):
    if os.path.isfile(rel) and not os.path.islink(rel):
        os.makedirs(os.path.join(dest, os.path.dirname(rel)), exist_ok=True)
        shutil.copy2(rel, os.path.join(dest, rel))
' "$SCAN" && git -C "$SCAN" init -q && git -C "$SCAN" add -A; then
  origin="$(git remote get-url origin 2>/dev/null)" && git -C "$SCAN" remote add origin "$origin"
  (cd "$SCAN" && python3 "$ROOT/$GUARD" --staged)
  rc=$?
  if [ "$rc" -eq 0 ]; then pass guard
  else failed guard; [ "$rc" -eq 2 ] && echo "verify: the guard could not run (exit 2)"; fi
else
  failed guard
  echo "verify: could not stage the tree for the guard"
fi

# ── 4. Size ceilings (AC-9) ──────────────────────────────────────────────────────────────────────
section "size ceilings"
run_suite size install/tests test_size.py

# ── 5. Dangling references to retired names ──────────────────────────────────────────────────────
# Over the tracked and non-ignored files in install/, README.md, AGENTS.md and docs/. Instructions,
# routes and code must not name retired machinery; records may, as rationale. Excluded: the exact
# paths in EXCLUDE below (each group says why); install.sh's retire-v5 list, the lines between its
# markers; and this file, whose pattern is the scanner's own list. There is no directory exclusion.
# Persona names that are ordinary words (planner, developer, scout, architect, acceptance) are not
# scanned. A file list that cannot be read fails the check rather than passing it empty.
section "dangling references to retired names"
RETIRED_RE='methodology-management|project-onboarding|project-migration|project-conformance|agent-persona-factory|gate-sandbox'
RETIRED_RE="$RETIRED_RE"'|validate_card|check_review_budget|trace_check|spec_check|ratio_meter|weekly_review|verify_junit|start_junit_run|milestone_seal|plan_waves|sync_methodology'
RETIRED_RE="$RETIRED_RE"'|ROUND-GRANTS|task-card\.md'
RETIRED_RE="$RETIRED_RE"'|docs-steward|contract-architect|senior-developer|test-judge|migration-validator|product-steward|chief-of-staff|security-validator'
# Instructions, routes and code must not name retired machinery; these name it on purpose:
EXCLUDE="docs/product/specs/F-3-lean-execution.md docs/architecture/lean-execution.md docs/product/plans/F-3-lean-execution.md install/skills/execution-methodology/references/migrate.md install/verify.sh"
# test_rules.py holds the retired list it asserts absent from routed files.
EXCLUDE="$EXCLUDE install/skills/execution-methodology/tests/test_rules.py"
# Records may name retired machinery as the rationale for a current decision.
EXCLUDE="$EXCLUDE docs/decisions/decisions.md docs/product/measurements.md docs/product/improvements-weekly.md docs/agents/lessons.md"
: > "$TMP/hits"
if ! git ls-files -z --cached --others --exclude-standard -- install README.md AGENTS.md docs > "$TMP/scan-z" ||
   ! tr '\0' '\n' < "$TMP/scan-z" > "$TMP/scan-files" || [ ! -s "$TMP/scan-files" ]; then
  echo "verify: could not list the files to scan" > "$TMP/hits"
fi
while IFS= read -r f; do
  [ -f "$f" ] || continue
  case " $EXCLUDE " in *" $f "*) continue ;; esac
  grep -Iq . "$f" 2>/dev/null || continue    # binary or empty
  awk -v re="$RETIRED_RE" -v f="$f" '
    f == "install/install.sh" && /^# BEGIN retire-v5 list$/ { skip = 1 }
    f == "install/install.sh" && /^# END retire-v5 list$/   { skip = 0; next }
    !skip { line = $0
      while (match(line, re)) { print f ":" FNR ": " substr(line, RSTART, RLENGTH); line = substr(line, RSTART + RLENGTH) } }
  ' "$f" >> "$TMP/hits"
done < "$TMP/scan-files"
if [ -s "$TMP/hits" ]; then
  cat "$TMP/hits"
  echo "verify: $(wc -l < "$TMP/hits" | tr -d ' ') reference(s) in $(cut -d: -f1 "$TMP/hits" | sort -u | wc -l | tr -d ' ') file(s):"
  cut -d: -f1 "$TMP/hits" | sort | uniq -c
  failed dangling_references
else
  pass dangling_references
fi

# ── 6. Installer behaviour (AC-11, AC-12) ────────────────────────────────────────────────────────
section "installer tests"
run_suite install install/tests test_install.py
section "install_tree preserve self-test"
if bash install/preserve_selftest.sh; then pass preserve_selftest; else failed preserve_selftest; fi

# ── 7. Installer dry run ─────────────────────────────────────────────────────────────────────────
# Against a scratch HOME, so the result describes this repository and not this machine.
section "install.sh --dry-run (scratch HOME)"
mkdir -p "$TMP/scratch-home/.codex"
if HOME="$TMP/scratch-home" CODEX_HOME="$TMP/scratch-home/.codex" bash install/install.sh --dry-run > "$TMP/dry.log" 2>&1; then
  tail -n 4 "$TMP/dry.log"
  pass install_dry_run
else
  cat "$TMP/dry.log"
  failed install_dry_run
fi

# ── 8. Installed parity (--installed only) ───────────────────────────────────────────────────────
if [ "$INSTALLED" -eq 1 ]; then
  section "installed parity against ~/.claude and ~/.codex (read-only)"
  CX="${CODEX_HOME:-$HOME/.codex}"
  drift=0
  differs() { echo "  drift: $1"; drift=$((drift + 1)); }
  roots="$HOME/.claude"; [ -d "$CX" ] && roots="$roots $CX"
  for root in $roots; do
    for s in $(published_skills); do
      diff -rq -x __pycache__ -x ROUND-GRANTS.tsv "install/skills/$s" "$root/skills/$s" >/dev/null 2>&1 ||
        differs "$root/skills/$s differs from install/skills/$s"
    done
  done
  for h in install/hooks/*; do
    cmp -s "$h" "$HOME/.claude/hooks/$(basename "$h")" || differs "$HOME/.claude/hooks/$(basename "$h")"
  done
  for pair in "$HOME/.claude/settings.json" "$CX/hooks.json"; do
    [ "$pair" = "$CX/hooks.json" ] && [ ! -d "$CX" ] && continue
    want="execution-methodology/scripts/goal.py stop-hook"
    grep -qF "$want" "$pair" 2>/dev/null || differs "$pair does not register $want"
  done
  mkdir -p "$TMP/render/.codex"
  HOME="$TMP/render" CODEX_HOME="$TMP/render/.codex" \
    python3 install/skills/agent-personas/scripts/sync_personas.py --scope global >/dev/null 2>&1 ||
    differs "the persona pool could not be rendered for comparison"
  for f in "$TMP/render/.claude/agents/"*.md; do
    [ -f "$f" ] && { cmp -s "$f" "$HOME/.claude/agents/$(basename "$f")" || differs "$HOME/.claude/agents/$(basename "$f")"; }
  done
  if [ -d "$CX" ]; then
    for f in "$TMP/render/.codex/agents/"*.toml; do
      [ -f "$f" ] && { cmp -s "$f" "$CX/agents/$(basename "$f")" || differs "$CX/agents/$(basename "$f")"; }
    done
  fi
  if [ "$drift" -eq 0 ]; then pass installed_parity
  else echo "  run ./install.sh to bring the installed copy level with this repository"; failed installed_parity installed; fi
fi

# ── Verdict ──────────────────────────────────────────────────────────────────────────────────────
echo
if [ "$FAILED" -eq 0 ]; then
  echo "verify: PASS"
  exit 0
fi
echo "failing:$FAILED_NAMES"
echo "verify: FAIL ($FAILED checks)"
exit 1
