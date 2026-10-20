#!/usr/bin/env bash
# M2's end-to-end check (S-2 T9): the founder's open session is the chief, with no launcher, loop or
# Stop hook (D30). For each harness this script plays that session by hand, through the copy of the
# skill install.sh put in a disposable HOME and CODEX_HOME; the real ~/.claude and ~/.codex are never
# written, no harness CLI runs, no credentials are read and nothing is pushed.
#
#   e2e_run.sh            (no flags)
#
# Per harness, on its own scratch repository holding the two-task v7.1 goal E-1 (approved, tagged:
# spec.md with AC1 and AC2 traced to T1 and T2, `reads:` on both tasks, T2 `needs: T1`, one docs/
# page with frontmatter and `covers`, the generated docs/README.md index and pointer files, all
# committed): install with the real install.sh; `goal.py lint` and `goal.py packet --approval`; print
# `goal.py resume`; `goal.py next`, and `resume` on a copy of the plan with T1 parked; one `gate.py
# baseline` on the plan's gate; for T1 and T2 write the task's files, run `gate.py check` on the
# plan's gate (the unit tests and `docs.py lint`), tick the task and commit `[Tn] ...`, and after
# [T1] run `next` again; record the full_gate and e2e receipts with `gate.py receipt`; write the
# labelled review fixture (the merge review runs outside the session, by the other vendor; this
# stands in for it and is not a review). Asserts: lint passes and .runs/E-1/approval.html holds the
# criteria, resume names T1, `next` prints T1 alone before [T1] and T2 after it, the parked copy's
# resume says `no ready task; T2 needs T1 (parked)`, both [Tn] commits exist, .runs/E-1/checks.jsonl
# holds exactly one baseline, two check and two receipt lines with their commands, numeric
# durations and verdicts, the last line of every baseline, check and receipt starts `budget:`,
# `goal.py done` prints DONE M1, `goal.py packet` writes .runs/E-1/packet.md, `goal.py cost` prints
# a claude and a codex line (`unknown` here: a scratch HOME has no transcripts), and the
# repository's bare origin received nothing. The fixture's module map (docs/goals/modules.json: `a`, and
# `b` needing `a`, each an emitter command) derives both tasks' gate, so `next` names `modules: a, b`;
# `gate.py check --modules a,b` passes both; a `receipt --modules all` whose `b` fails once is followed
# by one that keeps `a` and retries `b` to a pass; on a second tree where `b` fails twice, the third
# receipt refuses `b` and exits 1. Inner runs write to files under .runs/E-1/, never to stdout. Then, in one more disposable home: install.sh puts the skill (minus
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
  # The module map: `b` needs `a`; each test command is an emitter, and `b` fails while .runs/mode-b says so.
  cat > docs/goals/modules.json <<'MAP'
{"modules": {
  "a": {"paths": ["src/a/**"], "test": "printf 'Ran 1 test in 0.001s\\n\\nOK\\n'"},
  "b": {"paths": ["src/b/**"], "needs": ["a"],
        "test": "test \"$(cat .runs/mode-b 2>/dev/null || echo ok)\" = ok && printf 'Ran 2 tests in 0.001s\\n\\nOK\\n'"}}}
MAP
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
writes: src/a/**, calc/__init__.py, calc/add.py, tests/__init__.py, tests/test_add.py
reads: docs/goals/E-1/spec.md, docs/area.md#layout
`calc/add.py` defines `add(a, b)` returning `a + b`; `tests/test_add.py` checks `add(2, 3) == 5` (AC1).

### [ ] T2 — mul
writes: calc/mul.py, tests/test_mul.py
needs: T1
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
  python3 "$1/gate.py" check --goal E-1 --cmd "$3" > ".runs/E-1/out/check-$2.out" || return 1
  sed -i.bak "s/^### \[ \] $2 /### [x] $2 /" docs/goals/E-1/plan.md && rm -f docs/goals/E-1/plan.md.bak
  gitq add -A && gitq commit -qm "[$2] $name"
}

# ── An immutable-test migration, through the installed CLIs, with separate negative histories ──
migration_run() {  # migration_run HARNESS SCRIPTS REPO
  python3 - "$1" "$2" "$3" <<'PY'
import hashlib, json, os, pathlib, subprocess, sys

harness, scripts, location = sys.argv[1:]
scripts, repo = pathlib.Path(scripts), pathlib.Path(location)
repo.mkdir()
controls = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT")
hostile = {name: "hostile-inherited-value" for name in controls}
env = {**os.environ, **hostile, "E2E_MIGRATION_KEEP": "unrelated-value"}

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def run(args, cwd=repo, code=0):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    require(result.returncode == code, f"{args!r}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result.stdout + result.stderr

def git(*args, cwd=repo):
    return run(["git", "-c", "commit.gpgsign=false", *args], cwd).strip()

def goal(action, cwd=repo, code=0):
    return run(["python3", str(scripts / "goal.py"), action, "--goal", "M-1"], cwd, code)

def label(name, detail):
    print(f"e2e_run: {harness + ' migration ' + name:26} ok ({detail})")

git("init", "-q", "-b", "main", ".")
git("config", "user.email", "e2e@example.invalid")
git("config", "user.name", "e2e")
(repo / ".gitignore").write_text(".runs/\n__pycache__/\n")
tests = repo / "tests"
tests.mkdir()
(tests / "__init__.py").write_text("")
original = b"import unittest\n\nclass Historical(unittest.TestCase):\n    def test_old(self):\n        self.assertEqual(2 + 3, 5)\n"
(tests / "test_old.py").write_bytes(original)
for name, expression, expected in (("keep", "2 + 3", 5), ("current", "4 * 5", 20), ("extra", "9 - 2", 7)):
    (tests / f"test_{name}.py").write_text(
        "import os, unittest\n\nclass Current(unittest.TestCase):\n"
        f"    def test_behavior(self):\n        self.assertEqual({expression}, {expected})\n"
        "    def test_environment(self):\n"
        f"        for name in {controls!r}:\n            self.assertNotIn(name, os.environ)\n"
        "        self.assertEqual(os.environ.get('E2E_MIGRATION_KEEP'), 'unrelated-value')\n")
before = "python3 -m unittest tests/test_old.py tests/test_keep.py"
after = "python3 -m unittest tests/test_keep.py tests/test_current.py tests/test_extra.py"
full = "python3 -m unittest -v tests/test_keep.py tests/test_current.py tests/test_extra.py"
e2e = "python3 -m unittest -q tests/test_current.py tests/test_extra.py"
directory = repo / "docs/goals/M-1"
directory.mkdir(parents=True)
map_path = repo / "docs/goals/modules.json"
module_map = {"modules": {"legacy": {"paths": ["tests/**"], "test": before}}}
map_path.write_text(json.dumps(module_map) + "\n")
(directory / "test-migrations.json").write_text(json.dumps({"version": 1, "migrations": [{
    "module": "legacy", "before": before, "after": after,
    "originals": [{"path": "tests/test_old.py", "sha256": hashlib.sha256(original).hexdigest()}],
    "successors": ["tests/test_current.py", "tests/test_extra.py"], "historical_claim": "BYTES_ONLY",
    "reason": "Preserve historical bytes while current arithmetic has named executable coverage."
}]}) + "\n")
(directory / "spec.md").write_text("""# Migration fixture

**Users and problem.** A caller needs current arithmetic coverage.
**What changes for the user.** Current tests replace a historical route, whose bytes remain.
**Acceptance criteria.**
- AC1 WHEN the route migrates THE SYSTEM SHALL require current and preservation proofs.
**Non-goals.** Historical environment replay.
**Constraints.** Standard-library Python; no provider calls.
""")
plan_path = directory / "plan.md"
plan_path.write_text(f"""---
goal: M-1
title: Immutable-test migration fixture
gate: {after}
full_gate: {full}
milestones:
  M1: {{tasks: [T1], e2e: "{e2e}"}}
touches: [none]
protected: []
---
## Outcome
Current arithmetic has named proof receipts; historical bytes remain unchanged.
## Tasks
### [ ] T1 — migrate the route
writes: docs/goals/modules.json, candidate.txt
reads: docs/goals/M-1/spec.md
AC1: activate the exact replacement and collect its proofs.
## Decisions
- The merge review below is an explicitly labelled fixture, never an independent review.
## Parked
""")
(repo / "candidate.txt").write_text("first candidate\n")
git("add", "-A")
git("commit", "-qm", "M-1: migration proposal")
require("lint: PASS" in goal("lint"), "proposal lint did not pass")
proposal = json.loads(goal("migration-proofs"))
require(proposal["version"] == 1 and len(proposal["migrations"]) == 1
        and proposal["migrations"][0]["applied"] is False, "proposal descriptors missing")
# All original/current sources, hashes, map and goal precede this fixture's approval.
git("tag", "goal/M-1/approved")
approved = git("rev-parse", "HEAD")
for violation, diagnostic in (("command", "command is neither approved before nor after"),
                              ("digest", "original sha256 mismatch")):
    negative = repo.with_name(repo.name + "-" + violation)
    git("clone", "-q", str(repo), str(negative))
    git("config", "user.email", "e2e@example.invalid", cwd=negative)
    git("config", "user.name", "e2e", cwd=negative)
    if violation == "command":
        changed = json.loads(map_path.read_text())
        changed["modules"]["legacy"]["test"] = before + " tests/test_current.py"
        (negative / "docs/goals/modules.json").write_text(json.dumps(changed) + "\n")
    else:
        (negative / "tests/test_old.py").write_bytes(original + b"\n# changed historical bytes\n")
    git("add", "-A", cwd=negative)
    git("commit", "-qm", "[T1] invalid migration fixture", cwd=negative)
    require(diagnostic in goal("lint", negative, 1), f"{violation} mismatch was not refused")
    rejected = goal("done", negative, 1)
    require(diagnostic in rejected and "NOT DONE M1" in rejected, "invalid history reached DONE")
require(git("rev-parse", "HEAD") == approved, "negative fixtures changed the success history")
label("negatives", "separate command/digest clones refused; success history untouched")

module_map["modules"]["legacy"]["test"] = after
map_path.write_text(json.dumps(module_map) + "\n")
plan_path.write_text(plan_path.read_text().replace("### [ ] T1", "### [x] T1"))
git("add", "-A")
git("commit", "-qm", "[T1] activate exact migration")
require("lint: PASS" in goal("lint"), "approved replacement lint did not pass")
data = json.loads(goal("migration-proofs"))
entry = data["migrations"][0]
proofs = entry["proofs"]
require(entry["applied"] is True and proofs == proposal["migrations"][0]["proofs"]
        and [p["kind"] for p in proofs] == ["module", "successor", "successor", "preservation"],
        "installed descriptors did not bind the approved replacement")
out = repo / ".runs/M-1/out"
out.mkdir(parents=True)

def receipt(arguments, name):
    text = run(["python3", str(scripts / "gate.py"), "receipt", "--goal", "M-1", *arguments])
    (out / (name + ".out")).write_text(text)
    require(text.splitlines()[-1].startswith("budget:"), "receipt has no final budget line")
    return text

def standard_evidence():
    receipt(["--name", "full_gate", "--cmd", full], "full_gate")
    receipt(["--name", "e2e", "--cmd", e2e], "e2e")
    # A parser fixture only: no provider is contacted and this is not an independent review.
    (repo / ".runs/M-1/review.md").write_text(
        "reviewer: e2e_run.sh fixture codex gpt-6-astra at high (read-only, not a review), merge\n"
        f"reviewed: {git('rev-parse', 'HEAD')}\nverdict: PASS\n## Findings\n")

def missing_proofs():
    text = goal("done", code=1)
    for row in (1, 2, 3, 4, 5, 6, 8):
        require(f"row {row} ok\n" in text, f"unexpected DONE row failure: {text}")
    for kind in ("module", "successor", "preservation"):
        require(f"no valid migration {kind} proof" in text, f"missing {kind} proof accepted")
    require("no PASS full_gate" not in text and "no PASS e2e" not in text, "standard evidence missing")
    require(text.splitlines()[-1] == "NOT DONE M1", "missing migration proofs reached DONE")

def fresh_proofs():
    tree = git("rev-parse", "HEAD^{tree}")
    for index, proof in enumerate(proofs):
        arguments = (["--modules", proof["module"]] if proof["kind"] == "module"
                     else ["--cmd", proof["command"]])
        if not proof["tests"]:
            arguments += ["--count", "none"]
        text = receipt(arguments, f"proof-{index}")
        rows = [json.loads(p.read_text()) for p in (repo / ".runs/M-1/receipts").glob("*.json")]
        matches = [r for r in rows if r.get("tree") == tree and r.get("command") == proof["command"]
                   and r.get("module") == proof["module"]]
        require(len(matches) == 1, f"no unique exact-tree receipt for {proof['kind']}")
        record = matches[0]
        require(record["verdict"] == "PASS" and record["exit"] == 0 and record["failed"] == 0
                and record["skipped"] == 0 and not record["baseline_failures"] and not record["reasons"],
                f"unclean {proof['kind']} receipt")
        require(record["executed"] > 0 if proof["tests"] else record["executed"] == 0,
                f"wrong executed count for {proof['kind']}")
        if not proof["tests"]:
            require("preservation: PASS" in text, "generated preservation check did not pass")
    require((tests / "test_old.py").read_bytes() == original, "original bytes changed")
    return tree

close_missing = goal("done", code=1)
for message in ("no PASS full_gate", "no PASS e2e", "no .runs/M-1/review.md"):
    require(message in close_missing, f"standard close requirement waived: {message}")
standard_evidence()
missing_proofs()
label("missing proofs", "DONE refused despite fresh full/E2E receipts and labelled review fixture")
old_tree = fresh_proofs()
require(goal("done").splitlines()[-1] == f"DONE M1 on tree {old_tree}", "fresh proofs did not reach DONE")
(repo / "candidate.txt").write_text("second candidate\n")
git("add", "candidate.txt")
git("commit", "-qm", "[T1] refresh candidate tree")
require(git("rev-parse", "HEAD^{tree}") != old_tree, "candidate tree did not change")
standard_evidence()
missing_proofs()
require(any(p.name.startswith(old_tree + "-") for p in (repo / ".runs/M-1/receipts").glob("*.json")),
        "stale receipts were not retained")
label("stale tree", "old passing proofs retained and refused on a new committed candidate")
tree = fresh_proofs()
label("fresh proofs", "real module and individual unittest receipts; generated preservation --count none")
label("immutable bytes", "original bytes equal their approval-frozen source")
require(all(env[name] == hostile[name] for name in controls), "parent environment changed")
label("environment", "all four inherited pytest controls absent in real module/command children; unrelated value kept")
require(goal("done").splitlines()[-1] == f"DONE M1 on tree {tree}", "final fresh proofs did not reach DONE")
label("DONE", "exact candidate tree; full/E2E receipts and labelled review fixture still mandatory")
PY
}

# ── Each harness: install, approval, resume, two tasks, receipts, review fixture, done, packet, cost
harness_run() {  # harness_run claude|codex
  local h="$1" home="$tmp/home-$1" repo="$tmp/repo-$1" origin="$tmp/origin-$1.git" skill out t f gate
  local e2e="python3 -m unittest discover -s tests -t . -v"
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
  cd "$repo" && mkdir -p .runs/E-1/out || return
  if python3 "$skill/goal.py" --goal E-1 lint > /dev/null && python3 "$skill/goal.py" --goal E-1 packet --approval > /dev/null &&
    grep -q 'AC2 WHEN' .runs/E-1/approval.html; then ok "$h approval" "goal.py lint PASS, .runs/E-1/approval.html"
  else bad "$h approval" "goal.py lint failed, or .runs/E-1/approval.html lacks the criteria"; fi

  out="$(python3 "$skill/goal.py" --goal E-1 resume)"
  printf '%s\n' "$out" | sed 's/^/    /'
  case "$out" in *"Next: T1 — add"*) ok "$h resume" "names T1" ;; *) bad "$h resume" "does not name T1" ;; esac
  out="$(python3 "$skill/goal.py" --goal E-1 next)"
  [ "$out" = "T1 — add · gate: modules: a, b" ] && ok "$h next before [T1]" "$out" ||
    bad "$h next before [T1]" "not T1 alone with the derived gate: $out"
  sed 's/^### \[ \] T1 /### [!] T1 /' docs/goals/E-1/plan.md > .runs/E-1/plan-T1-parked.md
  out="$(python3 "$skill/goal.py" --plan .runs/E-1/plan-T1-parked.md resume)"
  case "$out" in *"Next: no ready task; T2 needs T1 (parked)."*) ok "$h resume, T1 parked" "T2 needs T1 (parked)" ;;
    *) bad "$h resume, T1 parked" "does not say T2 needs T1 (parked): $out" ;; esac
  python3 "$skill/gate.py" baseline --goal E-1 --cmd "$gate" > .runs/E-1/out/baseline.out &&
    ok "$h baseline" "plan gate, before T1" || bad "$h baseline" "gate.py baseline failed"
  for t in T1 T2; do
    if task "$skill" "$t" "$gate" && [ "$(gitq log --format=%s goal/E-1/approved..HEAD | grep -c "^\[$t\] ")" = 1 ]; then
      ok "$h [$t]" "gate.py check passed (tests, docs.py lint), ticked, committed"
    else bad "$h [$t]" "the task did not land as one [$t] commit"; fi
    if [ "$t" = T1 ]; then
      out="$(python3 "$skill/goal.py" --goal E-1 next)"
      [ "$out" = "T2 — mul · gate: modules: a, b" ] && ok "$h next after [T1]" "$out" ||
        bad "$h next after [T1]" "not T2 alone with the derived gate: $out"
    fi
  done
  python3 "$skill/gate.py" receipt --goal E-1 --name full_gate --cmd "$gate" > .runs/E-1/out/receipt-full_gate.out &&
    python3 "$skill/gate.py" receipt --goal E-1 --name e2e --cmd "$e2e" > .runs/E-1/out/receipt-e2e.out &&
    ok "$h receipts" "full_gate, e2e" || bad "$h receipts" "gate.py receipt failed"
  out="$(python3 - .runs/E-1/checks.jsonl "$gate" "$e2e" <<'PY'
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1])]
want = [("baseline", sys.argv[2], "RECORDED"), ("check", sys.argv[2], "PASS"), ("check", sys.argv[2], "PASS"),
        ("receipt", sys.argv[2], "PASS"), ("receipt", sys.argv[3], "PASS")]
got = [(r.get("label"), r.get("command"), r.get("verdict")) for r in rows]
untimed = [r.get("label") for r in rows if type(r.get("duration_s")) not in (int, float)]
print("ok" if got == want and not untimed else f"got {got}; no numeric duration_s: {untimed}")
PY
)"
  [ "$out" = ok ] && ok "$h checks record" "1 baseline, 2 check, 2 receipt lines" || bad "$h checks record" "$out"
  out=""
  for f in .runs/E-1/out/*.out; do [ "$(tail -1 "$f" | cut -c1-7)" = "budget:" ] || out="$out ${f##*/}"; done
  [ "$(ls .runs/E-1/out/*.out | wc -l | tr -d ' ')" = 5 ] && [ -z "$out" ] &&
    ok "$h budget lines" "last line of baseline, 2 check, 2 receipt" ||
    bad "$h budget lines" "not 5 outputs, or no budget: last line in:${out:- none}"
  printf 'reviewer: e2e_run.sh fixture codex gpt-6-astra at high (read-only, not a review), %s, merge\nreviewed: %s\nverdict: PASS\n## Findings\n' \
    "$(date +%F)" "$(gitq rev-parse HEAD)" > .runs/E-1/review.md

  out="$(python3 "$skill/goal.py" --goal E-1 done | tail -1)"
  case "$out" in "DONE M1 "*) ok "$h goal.py done" "$out" ;; *) bad "$h goal.py done" "$out" ;; esac
  python3 "$skill/goal.py" --goal E-1 packet > /dev/null
  [ -s .runs/E-1/packet.md ] && ok "$h packet" ".runs/E-1/packet.md" || bad "$h packet" ".runs/E-1/packet.md missing"
  out="$(python3 "$skill/goal.py" --goal E-1 cost)"
  case "$out" in "claude: "*$'\n'"codex: "*) ok "$h cost" "$(printf '%s' "$out" | tr '\n' ';')" ;; *) bad "$h cost" "$out" ;; esac
  t="$(gitq -C "$origin" for-each-ref | wc -l | tr -d ' ')"
  [ "$t" = 0 ] && ok "$h push" "nothing pushed to origin" || bad "$h push" "$t ref(s) on origin"

  # The derived gate's modules, then same-tree reuse, one retry and the refusal after a second failure
  f=.runs/E-1/mod; mkdir -p "$f"
  python3 "$skill/gate.py" check --goal E-1 --modules a,b > "$f/check.out" &&
    [ "$(grep -c '^module [ab]: gate: PASS' "$f/check.out")" = 2 ] && grep -qx 'modules: PASS 2 of 2' "$f/check.out" &&
    ok "$h check --modules a,b" "two module lines, modules: PASS 2 of 2" ||
    bad "$h check --modules a,b" "not two passing modules: $(tr '\n' ';' < "$f/check.out")"
  printf fail > .runs/mode-b
  python3 "$skill/gate.py" receipt --goal E-1 --modules all > "$f/receipt-1.out"; t="$?"
  printf ok > .runs/mode-b
  python3 "$skill/gate.py" receipt --goal E-1 --modules all > "$f/receipt-2.out"; t="$t $?"
  [ "$t" = "1 0" ] && grep -qx 'module a: PASS on this tree (kept)' "$f/receipt-2.out" &&
    grep -qx 'module b: retry after a failure on this tree' "$f/receipt-2.out" &&
    grep -q '^module b: gate: PASS' "$f/receipt-2.out" && grep -qx 'modules: PASS 2 of 2' "$f/receipt-2.out" &&
    ok "$h b fails once" "a kept, b retried and passed" ||
    bad "$h b fails once" "exits $t; $(tr '\n' ';' < "$f/receipt-2.out")"
  mkdir -p src/b && printf 'b\n' > src/b/b.txt && gitq add -A && gitq commit -qm "a second tree"
  printf fail > .runs/mode-b; out=""
  for t in 3 4 5; do python3 "$skill/gate.py" receipt --goal E-1 --modules all > "$f/receipt-$t.out"; out="$out $?"; done
  [ "$out" = " 1 1 1" ] && grep -qx 'module b failed twice on this tree; diagnose and commit a fix' "$f/receipt-5.out" &&
    grep -qx 'modules: FAIL 1 of 2 (b)' "$f/receipt-5.out" &&
    ok "$h b fails twice" "refused on the second tree, exit 1" ||
    bad "$h b fails twice" "exits$out; $(tr '\n' ';' < "$f/receipt-5.out")"
  migration_run "$h" "$skill" "$tmp/migration-$h" || bad "$h migration rehearsal" "installed CLI flow failed"
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
  echo "e2e_run: PASS (claude, codex: lint, approval page → resume → ready tasks by needs → baseline → [T1] [T2] with docs.py lint in the gate → checks record with budget lines → DONE, cost lines; module map → derived gate → kept, retried and refused modules; no launcher; install byte-identity, rollback to v6-base)"
  exit 0
fi
echo "e2e_run: FAIL ($errors)"; exit 1
