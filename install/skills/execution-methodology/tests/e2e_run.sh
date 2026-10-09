#!/usr/bin/env bash
# M2's end-to-end check (S-2 T9): the founder's open session is the chief, with no launcher, loop or
# Stop hook (D30). For each harness this script plays that session by hand, through the copy of the
# skill install.sh put in a disposable HOME and CODEX_HOME; the real ~/.claude and ~/.codex are never
# written, no harness CLI runs, no credentials are read and nothing is pushed.
#
#   e2e_run.sh            (no flags)
#
# Per harness, on its own scratch repository holding the two-task goal E-1 (approved, tagged):
# install with the real install.sh; print `goal.py resume`; for T1 and T2 write the task's files, run
# `gate.py check` on the plan's gate, tick the task and commit `[Tn] ...`; record the full_gate and
# e2e receipts with `gate.py receipt`; write the labelled review fixture (the merge review runs
# outside the session, by the other vendor; this stands in for it and is not a review). Asserts:
# resume names T1, both [Tn] commits exist, `goal.py done` prints DONE M1, `goal.py packet` writes
# .runs/E-1/packet.md, and the repository's bare origin received nothing. Exit 0 when all hold.
set -uo pipefail

[ $# -eq 0 ] || { sed -n '7p' "$0" >&2; exit 2; }
SKILL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL="$(cd "$SKILL_SRC/../.." && pwd)"
tmp="$(mktemp -d)" || exit 2
tmp="$(cd "$tmp" && pwd -P)"
[ -n "${E2E_KEEP:-}" ] || trap 'rm -rf "$tmp"' EXIT
export PYTHONDONTWRITEBYTECODE=1 GIT_CONFIG_NOSYSTEM=1
errors=0
line() { printf 'e2e_run: %-26s %s\n' "$1" "$2"; }
ok()   { line "$1" "ok${2:+ ($2)}"; }
bad()  { line "$1" "FAIL: $2"; errors=$((errors + 1)); }
gitq() { git -c commit.gpgsign=false "$@"; }

# ── The scratch repository: global.md-style AGENTS.md, a two-task v7 plan, approved ─────────────
make_repo() {  # make_repo DIR
  mkdir -p "$1/docs/goals/E-1" && cd "$1" && gitq init -q -b main . &&
    gitq config user.email e2e@example.invalid && gitq config user.name e2e || return 1
  cp "$INSTALL/global.md" AGENTS.md
  printf '.runs/\n__pycache__/\n.claude/\n' > .gitignore
  cat > docs/goals/E-1/plan.md <<'PLAN'
---
goal: E-1
title: A two-function arithmetic module
gate: python3 -m unittest discover -s tests -t .
full_gate: python3 -m unittest discover -s tests -t .
milestones:
  M1: {tasks: [T1, T2], e2e: "python3 -m unittest discover -s tests -t . -v"}
touches: [none]
protected: [AGENTS.md]
---

## Outcome

`calc/` provides `add(a, b)` and `mul(a, b)` for integers, each covered by a unittest under `tests/`.

## Tasks

### [ ] T1 — add
writes: calc/__init__.py, calc/add.py, tests/__init__.py, tests/test_add.py
`calc/add.py` defines `add(a, b)` returning `a + b`; `tests/test_add.py` checks `add(2, 3) == 5`.

### [ ] T2 — mul
writes: calc/mul.py, tests/test_mul.py
`calc/mul.py` defines `mul(a, b)` returning `a * b`; `tests/test_mul.py` checks `mul(4, 5) == 20`.

## Decisions

- The merge review of this goal runs outside the session, after both tasks and both receipts; a
  session never writes `.runs/E-1/review.md`.

## Parked
PLAN
  gitq add -A && gitq commit -qm "E-1: approved plan" && gitq tag goal/E-1/approved
}

# ── One task, the way the chief session does it: the files, the gate, the tick, the [Tn] commit ──
task() {  # task SCRIPTS T1|T2
  local name op call want
  case "$2" in T1) name=add op=+ call="add(2, 3)" want=5 ;; *) name=mul op='*' call="mul(4, 5)" want=20 ;; esac
  mkdir -p calc tests && touch calc/__init__.py tests/__init__.py
  printf 'def %s(a, b):\n    return a %s b\n' "$name" "$op" > "calc/$name.py"
  printf 'import unittest\nfrom calc.%s import %s\n\n\nclass T(unittest.TestCase):\n    def test_%s(self):\n        self.assertEqual(%s, %s)\n' \
    "$name" "$name" "$name" "$call" "$want" > "tests/test_$name.py"
  python3 "$1/gate.py" check --goal E-1 --cmd "python3 -m unittest discover -s tests -t ." > /dev/null || return 1
  sed -i.bak "s/^### \[ \] $2 /### [x] $2 /" docs/goals/E-1/plan.md && rm -f docs/goals/E-1/plan.md.bak
  gitq add -A && gitq commit -qm "[$2] $name"
}

# ── Each harness: install, resume, two tasks, receipts, the review fixture, done, packet ─────────
harness_run() {  # harness_run claude|codex
  local h="$1" home="$tmp/home-$1" repo="$tmp/repo-$1" origin="$tmp/origin-$1.git" skill out t
  mkdir -p "$home/.codex"
  if ! HOME="$home" CODEX_HOME="$home/.codex" bash "$INSTALL/install.sh" > "$tmp/install-$h.log" 2>&1; then
    cat "$tmp/install-$h.log"; bad "$h install" "install.sh exited non-zero"; return; fi
  if [ "$h" = claude ]; then skill="$home/.claude/skills/execution-methodology/scripts"
  else skill="$home/.codex/skills/execution-methodology/scripts"; fi
  [ -f "$skill/goal.py" ] && ok "$h install" "$skill" || { bad "$h install" "no goal.py under $skill"; return; }
  export HOME="$home" CODEX_HOME="$home/.codex"   # this harness run's subshell only
  ( make_repo "$repo" ) > /dev/null || { bad "$h repo" "could not create the scratch repository"; return; }
  gitq init -q --bare "$origin" && gitq -C "$repo" remote add origin "$origin"
  cd "$repo" && mkdir -p .runs/E-1 || return

  out="$(python3 "$skill/goal.py" --goal E-1 resume)"
  printf '%s\n' "$out" | sed 's/^/    /'
  case "$out" in *"Next: T1 — add"*) ok "$h resume" "names T1" ;; *) bad "$h resume" "does not name T1" ;; esac
  for t in T1 T2; do
    if task "$skill" "$t" && [ "$(gitq log --format=%s goal/E-1/approved..HEAD | grep -c "^\[$t\] ")" = 1 ]; then
      ok "$h [$t]" "gate.py check passed, ticked, committed"
    else bad "$h [$t]" "the task did not land as one [$t] commit"; fi
  done
  python3 "$skill/gate.py" receipt --goal E-1 --name full_gate --cmd "python3 -m unittest discover -s tests -t ." > /dev/null &&
    python3 "$skill/gate.py" receipt --goal E-1 --name e2e --cmd "python3 -m unittest discover -s tests -t . -v" > /dev/null &&
    ok "$h receipts" "full_gate, e2e" || bad "$h receipts" "gate.py receipt failed"
  printf 'reviewer: e2e_run.sh fixture (not a review), %s, merge\nreviewed: %s\nverdict: PASS\n## Findings\n' \
    "$(date +%F)" "$(gitq rev-parse HEAD)" > .runs/E-1/review.md

  out="$(python3 "$skill/goal.py" --goal E-1 done | tail -1)"
  case "$out" in "DONE M1 "*) ok "$h goal.py done" "$out" ;; *) bad "$h goal.py done" "$out" ;; esac
  python3 "$skill/goal.py" --goal E-1 packet > /dev/null
  [ -s .runs/E-1/packet.md ] && ok "$h packet" ".runs/E-1/packet.md" || bad "$h packet" ".runs/E-1/packet.md missing"
  t="$(gitq -C "$origin" for-each-ref | wc -l | tr -d ' ')"
  [ "$t" = 0 ] && ok "$h push" "nothing pushed to origin" || bad "$h push" "$t ref(s) on origin"
}

for h in claude codex; do (errors=0; harness_run "$h"; exit "$errors") || errors=$((errors + $?)); done

echo
if [ "$errors" -eq 0 ]; then echo "e2e_run: PASS (claude, codex: resume → [T1] [T2] → DONE, no launcher)"; exit 0; fi
echo "e2e_run: FAIL ($errors)"; exit 1
