#!/usr/bin/env bash
# M2's end-to-end check (S-2 T9): the founder's open session is the chief, with no launcher, loop or
# Stop hook (D30). For each harness this script plays that session by hand, through the copy of the
# skill install.sh put in a disposable HOME and CODEX_HOME; the real ~/.claude and ~/.codex are never
# written, no harness CLI runs, no credentials are read and nothing is pushed.
#
#   e2e_run.sh            (no flags)
#
# Per harness, on its own scratch repository holding the two-task v7.1 goal E-1 (approved, tagged:
# spec.md with AC1 and AC2 traced to T1 and T2, `reads:` on both tasks, one docs/ page with
# frontmatter and `covers`, the generated docs/README.md index and pointer files, all committed):
# install with the real install.sh; `goal.py lint` and `goal.py packet --approval`; print `goal.py
# resume`; for T1 and T2 write the task's files, run `gate.py check` on the plan's gate (the unit
# tests and `docs.py lint`), tick the task and commit `[Tn] ...`; record the full_gate and e2e
# receipts with `gate.py receipt`; write the labelled review fixture (the merge review runs outside
# the session, by the other vendor; this stands in for it and is not a review). Asserts: lint passes
# and .runs/E-1/approval.html holds the criteria, resume names T1, both [Tn] commits exist, `goal.py
# done` prints DONE M1, `goal.py packet` writes .runs/E-1/packet.md, `goal.py cost` prints a claude
# and a codex line (`unknown` here: a scratch HOME has no transcripts), and the repository's bare
# origin received nothing. Then, in one more disposable home: install.sh puts the skill (minus
# tests/), the global files and the six agent files there and nothing else, --uninstall leaves the
# home byte-identical to before, and the documented D29 rollback (install/README.md) to
# methodology/v6-base installs every v6 skill and hook as shipped in a temporary clone. Exit 0 when
# all hold.
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

# ── The scratch repository: AGENTS.md with pointer markers, a two-task v7.1 goal, approved ──────
make_repo() {  # make_repo DIR SCRIPTS GATE
  mkdir -p "$1/docs/goals/E-1" && cd "$1" && gitq init -q -b main . &&
    gitq config user.email e2e@example.invalid && gitq config user.name e2e || return 1
  cp "$INSTALL/global.md" AGENTS.md && printf '\n<!-- docs.py pointers -->\n<!-- /docs.py pointers -->\n' >> AGENTS.md
  printf '.runs/\n__pycache__/\n' > .gitignore
  cat > docs/goals/E-1/spec.md <<'SPEC'
# E-1 spec: a two-function arithmetic module

**Users and problem.** A caller needs integer arithmetic; the repository has none.

**What changes for the user.** `calc.add` and `calc.mul` exist, each covered by a unittest.

**Acceptance criteria.**

- AC1 WHEN `add(2, 3)` is called THE SYSTEM SHALL return 5.
- AC2 WHEN `mul(4, 5)` is called THE SYSTEM SHALL return 20.

**Non-goals.** Floats; other operations.

**Constraints.** Standard-library Python 3.
SPEC
  cat > docs/area.md <<'PAGE'
---
summary: The fixture's one area page; its pointer files are generated from covers.
read-when: Changing the source tree
covers: [src/**]
last-verified: 2026-10-09
---

# Area

## Layout

One function per file, one unittest per function.
PAGE
  printf -- '---\ngoal: E-1\ntitle: A two-function arithmetic module\ngate: %s\nfull_gate: %s\n' "$3" "$3" \
    > docs/goals/E-1/plan.md
  cat >> docs/goals/E-1/plan.md <<'PLAN'
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
reads: docs/goals/E-1/spec.md, docs/area.md#layout
`calc/add.py` defines `add(a, b)` returning `a + b`; `tests/test_add.py` checks `add(2, 3) == 5` (AC1).

### [ ] T2 — mul
writes: calc/mul.py, tests/test_mul.py
reads: calc/add.py, docs/area.md#layout
`calc/mul.py` defines `mul(a, b)` returning `a * b`; `tests/test_mul.py` checks `mul(4, 5) == 20` (AC2).

## Decisions

- The merge review of this goal runs outside the session, after both tasks and both receipts; a
  session never writes `.runs/E-1/review.md`.

## Parked
PLAN
  # The index and the pointer files are generated, then committed with the plan.
  printf '# Documentation\n\n' > docs/README.md && gitq add -A &&
    python3 "$2/docs.py" index . >> docs/README.md && python3 "$2/docs.py" pointers . || return 1
  gitq add -A && gitq commit -qm "E-1: approved plan" && gitq tag goal/E-1/approved
}

# ── One task, the way the chief session does it: the files, the gate, the tick, the [Tn] commit ──
task() {  # task SCRIPTS T1|T2 GATE
  local name op call want
  case "$2" in T1) name=add op=+ call="add(2, 3)" want=5 ;; *) name=mul op='*' call="mul(4, 5)" want=20 ;; esac
  mkdir -p calc tests && touch calc/__init__.py tests/__init__.py
  printf 'def %s(a, b):\n    return a %s b\n' "$name" "$op" > "calc/$name.py"
  printf 'import unittest\nfrom calc.%s import %s\n\n\nclass T(unittest.TestCase):\n    def test_%s(self):\n        self.assertEqual(%s, %s)\n' \
    "$name" "$name" "$name" "$call" "$want" > "tests/test_$name.py"
  python3 "$1/gate.py" check --goal E-1 --cmd "$3" > /dev/null || return 1
  sed -i.bak "s/^### \[ \] $2 /### [x] $2 /" docs/goals/E-1/plan.md && rm -f docs/goals/E-1/plan.md.bak
  gitq add -A && gitq commit -qm "[$2] $name"
}

# ── Each harness: install, approval, resume, two tasks, receipts, review fixture, done, packet, cost
harness_run() {  # harness_run claude|codex
  local h="$1" home="$tmp/home-$1" repo="$tmp/repo-$1" origin="$tmp/origin-$1.git" skill out t gate
  mkdir -p "$home/.codex"
  if ! HOME="$home" CODEX_HOME="$home/.codex" bash "$INSTALL/install.sh" > "$tmp/install-$h.log" 2>&1; then
    cat "$tmp/install-$h.log"; bad "$h install" "install.sh exited non-zero"; return; fi
  if [ "$h" = claude ]; then skill="$home/.claude/skills/execution-methodology/scripts"
  else skill="$home/.codex/skills/execution-methodology/scripts"; fi
  [ -f "$skill/goal.py" ] && ok "$h install" "$skill" || { bad "$h install" "no goal.py under $skill"; return; }
  export HOME="$home" CODEX_HOME="$home/.codex"   # this harness run's subshell only
  gate="python3 -m unittest discover -s tests -t . && python3 '$skill/docs.py' lint ."
  ( make_repo "$repo" "$skill" "$gate" ) > /dev/null || { bad "$h repo" "could not create the scratch repository"; return; }
  gitq init -q --bare "$origin" && gitq -C "$repo" remote add origin "$origin"
  cd "$repo" && mkdir -p .runs/E-1 || return
  if python3 "$skill/goal.py" --goal E-1 lint > /dev/null && python3 "$skill/goal.py" --goal E-1 packet --approval > /dev/null &&
    grep -q 'AC2 WHEN' .runs/E-1/approval.html; then ok "$h approval" "goal.py lint PASS, .runs/E-1/approval.html"
  else bad "$h approval" "goal.py lint failed, or .runs/E-1/approval.html lacks the criteria"; fi

  out="$(python3 "$skill/goal.py" --goal E-1 resume)"
  printf '%s\n' "$out" | sed 's/^/    /'
  case "$out" in *"Next: T1 — add"*) ok "$h resume" "names T1" ;; *) bad "$h resume" "does not name T1" ;; esac
  for t in T1 T2; do
    if task "$skill" "$t" "$gate" && [ "$(gitq log --format=%s goal/E-1/approved..HEAD | grep -c "^\[$t\] ")" = 1 ]; then
      ok "$h [$t]" "gate.py check passed (tests, docs.py lint), ticked, committed"
    else bad "$h [$t]" "the task did not land as one [$t] commit"; fi
  done
  python3 "$skill/gate.py" receipt --goal E-1 --name full_gate --cmd "$gate" > /dev/null &&
    python3 "$skill/gate.py" receipt --goal E-1 --name e2e --cmd "python3 -m unittest discover -s tests -t . -v" > /dev/null &&
    ok "$h receipts" "full_gate, e2e" || bad "$h receipts" "gate.py receipt failed"
  printf 'reviewer: e2e_run.sh fixture (not a review), %s, merge\nreviewed: %s\nverdict: PASS\n## Findings\n' \
    "$(date +%F)" "$(gitq rev-parse HEAD)" > .runs/E-1/review.md

  out="$(python3 "$skill/goal.py" --goal E-1 done | tail -1)"
  case "$out" in "DONE M1 "*) ok "$h goal.py done" "$out" ;; *) bad "$h goal.py done" "$out" ;; esac
  python3 "$skill/goal.py" --goal E-1 packet > /dev/null
  [ -s .runs/E-1/packet.md ] && ok "$h packet" ".runs/E-1/packet.md" || bad "$h packet" ".runs/E-1/packet.md missing"
  out="$(python3 "$skill/goal.py" --goal E-1 cost)"
  case "$out" in "claude: "*$'\n'"codex: "*) ok "$h cost" "$(printf '%s' "$out" | tr '\n' ';')" ;; *) bad "$h cost" "$out" ;; esac
  t="$(gitq -C "$origin" for-each-ref | wc -l | tr -d ' ')"
  [ "$t" = 0 ] && ok "$h push" "nothing pushed to origin" || bad "$h push" "$t ref(s) on origin"
}

for h in claude codex; do (errors=0; harness_run "$h"; exit "$errors") || errors=$((errors + $?)); done

# ── Install byte-identity, then the D29 rollback: the documented sequence, in a temporary clone ──
REPO="$(git -C "$INSTALL" rev-parse --show-toplevel)"
snapshot() { (cd "$1" && find . -print | LC_ALL=C sort && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum 2>/dev/null); }
r="$tmp/rehearsal"; mkdir -p "$r/.claude" "$r/.codex"
printf 'my own global instructions\n' > "$r/.claude/CLAUDE.md"
printf 'my own codex instructions\n' > "$r/.codex/AGENTS.md"
snapshot "$r" > "$tmp/before"
inst() { HOME="$r" CODEX_HOME="$r/.codex" bash "$1/install.sh" "${@:2}" > "$tmp/rehearsal.log" 2>&1 || { cat "$tmp/rehearsal.log"; return 1; }; }
if inst "$INSTALL"; then
  want="$(cd "$SKILL_SRC" && find . -type f -not -path './tests/*' -not -path '*/__pycache__/*' | LC_ALL=C sort)"
  drift=""
  for root in "$r/.claude" "$r/.codex"; do
    got="$(cd "$root/skills/execution-methodology" && find . -type f | LC_ALL=C sort)"
    [ "$got" = "$want" ] || drift="$drift $root/skills: $(diff <(echo "$want") <(echo "$got") | grep '^[<>]' | head -3 | tr '\n' ' ')"
    cmp -s "$INSTALL/global.md" "$root/$([ "$root" = "$r/.claude" ] && echo CLAUDE.md || echo AGENTS.md)" || drift="$drift global file in $root"
  done
  extra="$(cd "$r" && find . -type f -not -path './.claude/skills/*' -not -path './.codex/skills/*' | LC_ALL=C sort |
    grep -vE '^\./\.(claude/CLAUDE|codex/AGENTS)\.md(\.bak-[0-9-]+)?$|^\./\.(claude|codex)/agents/(builder|reviewer|scout)\.(md|toml)$')"
  [ -z "$extra" ] || drift="$drift unexpected: $(echo $extra)"
  [ -z "$drift" ] && ok "install" "skill = source minus tests/ in both homes, global files backed up, agents, nothing else" \
    || bad "install" "$drift"
else bad "install" "install.sh exited non-zero"; fi
if inst "$INSTALL" --uninstall; then
  snapshot "$r" > "$tmp/after"
  diff -q "$tmp/before" "$tmp/after" > /dev/null && ok "uninstall" "home byte-identical to before install" ||
    bad "uninstall" "home differs: $(diff "$tmp/before" "$tmp/after" | grep '^[<>]' | head -4 | tr '\n' ' ')"
else bad "uninstall" "install.sh --uninstall exited non-zero"; fi
# The reference is methodology/v6-base's own install/ (git archive), so a v7.1-only file the rollback
# left behind and the v6 installer copied is a difference.
v6="$tmp/v6-clone" ref="$tmp/v6-ref"; mkdir -p "$ref"
if gitq clone -q "$REPO" "$v6" 2>"$tmp/wt.log" && gitq -C "$REPO" archive methodology/v6-base install | tar -x -C "$ref" &&
   (cd "$v6" && git rm -r -q install && git checkout methodology/v6-base -- install) 2>>"$tmp/wt.log"; then
  if (cd "$v6" && HOME="$r" CODEX_HOME="$r/.codex" bash -c '(cd install && ./install.sh)') > "$tmp/rehearsal.log" 2>&1; then
    drift=""
    for s in $(sed -n 's|^!/\([A-Za-z0-9_-]*\)/*$|\1|p' "$ref/install/skills/.gitignore"); do
      for root in "$r/.claude" "$r/.codex"; do
        [ -d "$root/skills/$s" ] || { drift="$drift missing $root/skills/$s"; continue; }
        d="$(diff -rq -x __pycache__ "$ref/install/skills/$s" "$root/skills/$s" 2>&1 | head -2)"
        [ -z "$d" ] || drift="$drift $d"
      done
    done
    for f in "$ref"/install/hooks/*; do [ -f "$r/.claude/hooks/$(basename "$f")" ] || drift="$drift missing hooks/$(basename "$f")"; done
    [ -z "$drift" ] && ok "rollback to v6-base" "documented sequence; every v6 skill and hook installed as shipped" ||
      bad "rollback to v6-base" "$drift"
  else cat "$tmp/rehearsal.log"; bad "rollback to v6-base" "v6 install.sh exited non-zero"; fi
else bad "rollback to v6-base" "the documented sequence failed: $(head -1 "$tmp/wt.log")"; fi
if inst "$INSTALL" --uninstall; then
  left="$(cd "$r" && find . -type f | grep -vxF -e ./.claude/CLAUDE.md -e ./.codex/AGENTS.md | wc -l | tr -d ' ')"
  ok "uninstall after rollback" "v7.1 uninstall ran; $left v6 file(s) remain, which v7.1 does not own"
else bad "uninstall after rollback" "install.sh --uninstall exited non-zero"; fi

echo
if [ "$errors" -eq 0 ]; then
  echo "e2e_run: PASS (claude, codex: lint, approval page → resume → [T1] [T2] with docs.py lint in the gate → DONE, cost lines; no launcher; install byte-identity, rollback to v6-base)"
  exit 0
fi
echo "e2e_run: FAIL ($errors)"; exit 1
