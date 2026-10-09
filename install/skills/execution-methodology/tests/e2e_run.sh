#!/usr/bin/env bash
# M2's end-to-end check (S-1 T9). Everything runs in disposable homes and scratch repositories;
# the real ~/.claude and ~/.codex are never written, and nothing is pushed.
#
#   e2e_run.sh [--harness claude|codex|none] [--live]
#
# Which harness runs, and how:
#   (no flags)      both harnesses. Each runs live when its CLI is installed and logged in under the
#                   disposable home; otherwise that harness, and only that one, runs the same path with
#                   a fake harness (founder decision 2026-10-09: no credentials in disposable homes
#                   yet). The summary line names each harness `live` or `fake`.
#   --harness <h>   only <h>, and it must run live: an absent or logged-out CLI prints why and exits 1
#                   before anything runs, with no fake fallback. `none` runs the rehearsal (3.) only.
#   --live          every selected harness must run live, or exit 1 the same way. This is the
#                   authenticated run the fake path stands in for.
#
# 1. Per harness, on its own fresh repository with a two-task goal E-1: install the skill with the
#    real install.sh into a disposable HOME/CODEX_HOME, probe a forbidden `git push`, then
#    `run.sh E-1 --harness <h> --sessions 3`. Asserts: the push was refused, both [T1] and [T2]
#    commits exist, run.sh's session Stop hook ran in every session (goal.py stop-hook wrote
#    stop_state.json, at most three blocks each), a Stop hook registered outside run.sh never
#    fired, the session did not write its own review, and, after the merge-review step (below),
#    `goal.py done` prints DONE and packet.md exists. The fake harness ends each session the way a
#    harness does: it runs the Stop hook its command line registers and, on a block, stops again.
#    E2E_FAKE_NO_STOP_HOOK=1 (tests only) makes it skip the hook, so the check must fail. Credentials for a disposable home: Claude reads CLAUDE_CODE_OAUTH_TOKEN
#    (`claude setup-token`) or ANTHROPIC_API_KEY from the environment; Codex reads CODEX_API_KEY,
#    or E2E_CODEX_AUTH_JSON=<path to an auth.json> is copied into the disposable CODEX_HOME.
#    A fake run has no push probe and no --settings experiment, and says so.
# 2. The --settings experiment (Claude, live): does a user-level Stop hook fire beside --settings?
# 3. Install rehearsal: install, expected set, uninstall back to a byte-identical home, the D29
#    rollback exactly as install/README.md documents it, in a temporary clone, its installed set
#    against methodology/v6-base's own install/, uninstall.
#
# The merge review is the one step outside a session: a sandboxed session cannot reach the other
# vendor, and run.sh only restarts. Here a labelled fixture stands in for that review once rows 1-7
# hold; it is not a review. Exit 0 when every step that ran passed.
set -uo pipefail

ONLY="" LIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --harness) ONLY="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --live) LIVE=1; shift ;;
    *) ONLY="?"; break ;;
  esac
done
case "$ONLY" in claude|codex) HARNESSES="$ONLY" ;; none) HARNESSES="" ;; "") HARNESSES="claude codex" ;;
  *) sed -n '5p' "$0" >&2; exit 2 ;; esac
must_live() { [ -n "$LIVE" ] || [ "$ONLY" = "$1" ]; }
SKILL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL="$(cd "$SKILL_SRC/../.." && pwd)"
REPO="$(git -C "$INSTALL" rev-parse --show-toplevel)"
tmp="$(mktemp -d)" || exit 2
tmp="$(cd "$tmp" && pwd -P)"
[ -n "${E2E_KEEP:-}" ] || trap 'rm -rf "$tmp"' EXIT
export PYTHONDONTWRITEBYTECODE=1 RUN_NO_NOTIFY=1
errors=0 ran=""
line() { printf 'e2e_run: %-34s %s\n' "$1" "$2"; }
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
snapshot() {  # snapshot DIR: every path, and every file's bytes
  (cd "$1" && find . -print | LC_ALL=C sort && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum 2>/dev/null)
}
stop_regs() {  # stop_regs FILE NEEDLE: Stop hook commands in FILE containing NEEDLE
  python3 - "$1" "$2" <<'PY'
import json, sys
try: hooks = json.load(open(sys.argv[1], encoding="utf-8")).get("hooks", {})
except (OSError, ValueError): hooks = {}
print(sum(sys.argv[2] in h.get("command", "") for e in hooks.get("Stop", []) for h in e.get("hooks", [])))
PY
}
add_marker_hook() {  # add_marker_hook FILE MARKER: a user-level Stop hook that only records it fired
  python3 - "$1" "$2" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text()) if p.is_file() else {}
d.setdefault("hooks", {}).setdefault("Stop", []).append(
    {"hooks": [{"type": "command", "command": f"echo fired >> '{sys.argv[2]}'"}]})
p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(d, indent=2) + "\n")
PY
}
authed() {  # authed HARNESS HOME: zero-cost login check in the disposable home
  if [ "$1" = claude ]; then HOME="$2" claude auth status >/dev/null 2>&1
  else [ -n "${CODEX_API_KEY:-}" ] || HOME="$2" CODEX_HOME="$2/.codex" codex login status >/dev/null 2>&1; fi
}
push_refused() {  # push_refused HARNESS SESSION_JSON: the git push tool call was denied or failed
  python3 - "$1" "$2" <<'PY'
import json, sys
harness, path = sys.argv[1:3]
rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip().startswith("{")]
if harness == "claude":
    r = next((x for x in reversed(rows) if x.get("type") == "result"), {})
    hit = [d for d in r.get("permission_denials") or [] if "git push" in json.dumps(d.get("tool_input", {}))]
    print("denied by the deny list" if hit else "not denied"); sys.exit(0 if hit else 1)
items = [x.get("item", {}) for x in rows if x.get("type") == "item.completed"]
runs = [i for i in items if i.get("type") == "command_execution" and "git push" in str(i.get("command"))]
failed = runs and all(i.get("exit_code") not in (0, None) for i in runs)
print("failed in the sandbox (network off)" if failed else f"{len(runs)} attempt(s), not all failed")
sys.exit(0 if failed else 1)
PY
}

# ── 1. Each harness on its own fresh repository ─────────────────────────────────────────────────
harness_run() {  # harness_run HARNESS live|fake: the goal run and its assertions; 1 when not logged in
  local h="$1" mode="$2" home="$tmp/home-$1-$2" repo="$tmp/repo-$1-$2" hooks skill marker probe why t0 rc secs n t
  local unmet done_out envh
  mkdir -p "$home/.codex"
  [ "$h" = codex ] && [ -n "${E2E_CODEX_AUTH_JSON:-}" ] && cp "$E2E_CODEX_AUTH_JSON" "$home/.codex/auth.json"
  if ! HOME="$home" CODEX_HOME="$home/.codex" bash "$INSTALL/install.sh" > "$tmp/install-$h.log" 2>&1; then
    cat "$tmp/install-$h.log"; bad "$h install" "install.sh exited non-zero"; return 0; fi
  if [ "$mode" = live ] && ! authed "$h" "$home"; then
    line "$h" "not live: not logged in under the disposable home (see the header for credentials)"; return 1; fi
  ran="${ran:+$ran, }$h $mode"
  if [ "$h" = claude ]; then hooks="$home/.claude/settings.json" skill="$home/.claude/skills/execution-methodology"
  else hooks="$home/.codex/hooks.json" skill="$home/.codex/skills/execution-methodology"; fi
  marker="$tmp/user-stop-$h"; : > "$marker"; add_marker_hook "$hooks" "$marker"
  ( make_repo "$repo" ) > /dev/null || { bad "$h repo" "could not create the scratch repository"; return 0; }
  envh=(env HOME="$home" CODEX_HOME="$home/.codex")
  [ "$mode" = live ] || envh+=(RUN_HARNESS_CMD="python3 $tmp/fake_harness.py" FAKE_GATE="$skill/scripts/gate.py")

  if [ "$mode" = live ]; then
    # The forbidden push, on a copy so the goal run starts fresh. The remote exists and would accept.
    probe="$tmp/probe-$h"; cp -R "$repo" "$probe"; gitq init -q --bare "$tmp/origin-$h.git"
    gitq -C "$probe" remote add origin "$tmp/origin-$h.git"
    (cd "$probe" && RUN_PROMPT='Run exactly this shell command: git push --dry-run origin HEAD
Then report its output verbatim and stop. Do not try any other command.' \
      "${envh[@]}" bash "$skill/scripts/run.sh" E-1 --harness "$h" --sessions 1 > /dev/null 2>&1)
    if why="$(push_refused "$h" "$probe/.runs/E-1/session-1.json" 2>&1)"; then ok "$h push probe" "$why"
    else bad "$h push probe" "$why"; fi
  fi

  t0=$(date +%s)
  (cd "$repo" && "${envh[@]}" bash "$skill/scripts/run.sh" E-1 --harness "$h" --sessions 3) > "$tmp/run-$h.log" 2>&1
  rc=$?; secs=$(( $(date +%s) - t0 ))
  line "$h run.sh" "exit $rc ($(tail -1 "$tmp/run-$h.log")), ${secs}s"
  grep ' session ' "$repo/.runs/E-1/progress.md" | sed 's/^/    /'
  for t in T1 T2; do
    n=$(gitq -C "$repo" log --format=%s goal/E-1/approved..HEAD | grep -c "^\[$t\]")
    [ "$n" -ge 1 ] && ok "$h [$t] commit" || bad "$h [$t] commit" "none"
  done
  [ -s "$marker" ] && bad "$h stop hook" "a user-level Stop hook fired $(wc -l < "$marker" | tr -d ' ') time(s) beside run.sh's" \
    || ok "$h stop hook" "no user-level Stop hook fired"
  # run.sh's per-session Stop hook ran: goal.py stop-hook itself writes stop_state.json, one key per
  # session it blocked (every session here stops with the goal not done), at most three blocks each.
  if why="$(python3 - "$repo/.runs/E-1/stop_state.json" "$(grep -c ' session ' "$repo/.runs/E-1/progress.md")" <<'PY'
import json, os, sys
path, sessions = sys.argv[1], int(sys.argv[2])
if not os.path.isfile(path):
    print("no stop_state.json: run.sh's session Stop hook never ran"); sys.exit(1)
state = {k: v for k, v in json.load(open(path)).items() if not k.startswith("several:")}
if len(state) < sessions:
    print(f"the Stop hook recorded {len(state)} of {sessions} session(s)"); sys.exit(1)
if max(state.values()) > 3:
    print(f"{max(state.values())} blocks in one session (cap 3)"); sys.exit(1)
print(f"ran in all {sessions} session(s), at most {max(state.values())} block(s) each (cap 3)")
PY
)"; then ok "$h session stop hook" "$why"; else bad "$h session stop hook" "$why"; fi
  if [ -e "$repo/.runs/E-1/review.md" ]; then bad "$h review" "the session wrote its own review.md"
  else
    # rows 1-7 must hold before the merge review; then the fixture stands in for it.
    unmet="$(cd "$repo" && python3 "$skill/scripts/goal.py" --goal E-1 done | grep -E '^row [1-7]:')"
    if [ -n "$unmet" ]; then bad "$h rows 1-7" "$(echo "$unmet" | tr '\n' ';')"
    else
      printf 'reviewer: e2e_run.sh fixture (not a review), %s, merge\nreviewed: %s\nverdict: PASS\n## Findings\n' \
        "$(date +%F)" "$(gitq -C "$repo" rev-parse HEAD)" > "$repo/.runs/E-1/review.md"
      (cd "$repo" && "${envh[@]}" bash "$skill/scripts/run.sh" E-1 --harness "$h" --sessions 1) >> "$tmp/run-$h.log" 2>&1
    fi
  fi
  done_out="$(cd "$repo" && python3 "$skill/scripts/goal.py" --goal E-1 done | tail -1)"
  case "$done_out" in DONE*) ok "$h goal.py done" "$done_out" ;; *) bad "$h goal.py done" "$done_out" ;; esac
  [ -f "$repo/.runs/E-1/packet.md" ] && ok "$h packet.md" || bad "$h packet.md" "missing"

  # 2. The --settings experiment: the same user-level marker, a session WITHOUT --setting-sources "".
  if [ "$h" = claude ] && [ "$mode" = live ]; then
    : > "$marker"
    (cd "$probe" && HOME="$home" claude -p "Reply with the single word OK." --permission-mode dontAsk \
      --settings '{"permissions": {"allow": ["Read"]}}' --output-format json > "$tmp/merge.json" 2>&1)
    if [ -s "$marker" ]; then line "claude --settings" "MERGES with ~/.claude/settings.json (user Stop hook fired); run.sh passes --setting-sources \"\""
    else line "claude --settings" "user Stop hook did not fire beside --settings"; fi
  fi
  return 0
}
# A harness that must run live (--harness <h>, --live) and cannot is a failure before anything runs:
# no fake fallback stands in for a requested live run.
refused=""
for h in $HARNESSES; do
  must_live "$h" || continue
  if ! command -v "$h" >/dev/null 2>&1; then why="the $h CLI is not installed"
  else
    mkdir -p "$tmp/auth-$h/.codex"
    [ "$h" = codex ] && [ -n "${E2E_CODEX_AUTH_JSON:-}" ] && cp "$E2E_CODEX_AUTH_JSON" "$tmp/auth-$h/.codex/auth.json"
    authed "$h" "$tmp/auth-$h" && continue
    why="$h is not logged in under a disposable home (see the header for credentials)"
  fi
  bad "$h" "a live run was requested, but $why; no fallback"; refused=1
done
[ -z "$refused" ] || { echo; echo "e2e_run: FAIL (a requested live harness cannot run)"; exit 1; }

# Founder decision 2026-10-09: no credentials in disposable homes yet. Without flags, each harness
# that cannot run live runs the same path with this fake harness (no push probe, no --settings
# experiment), so the loop, commits, receipts, done and packet are proven per harness; the first
# authenticated run takes the live path.
cat > "$tmp/fake_harness.py" <<'FAKE'
"""Stand-in for one harness session: the next open task, else the two receipts; then, as a harness
does at the end of its session, the Stop hook its command line registers. Not a harness.
argv: the prompt, then the claude or codex command line run.sh would have run."""
import json, os, pathlib, re, subprocess, sys, tomllib, uuid


def stop_hooks(argv):
    """The Stop hook commands registered by Claude's --settings file or Codex's -c hooks.Stop=..."""
    cmds = []
    for flag, value in zip(argv, argv[1:]):
        if flag == "--settings":
            hooks = json.loads(pathlib.Path(value).read_text()).get("hooks", {})
        elif flag == "-c" and value.startswith("hooks.Stop="):
            hooks = tomllib.loads(value)["hooks"]
        else:
            continue
        cmds += [h["command"] for e in hooks.get("Stop", []) for h in e.get("hooks", [])]
    return cmds


def end_session():
    """The Stop event; on a block the session continues and stops again (goal.py caps blocks at 3)."""
    sid = str(uuid.uuid4())
    for cmd in stop_hooks(sys.argv[2:]):
        for turn in range(5):
            event = {"session_id": sid, "transcript_path": "", "cwd": os.getcwd(),
                     "hook_event_name": "Stop", "stop_hook_active": turn > 0}
            out = subprocess.run(cmd, shell=True, input=json.dumps(event), capture_output=True, text=True).stdout
            try:
                if json.loads(out).get("decision") != "block":
                    break
            except ValueError:
                break


plan = pathlib.Path("docs/goals/E-1/plan.md")
text = plan.read_text()
m = re.search(r"^### \[ \] (T[12]) ", text, re.M)
if m:
    tid = m.group(1)
    name, op, call, want = {"T1": ("add", "+", "add(2, 3)", 5), "T2": ("mul", "*", "mul(4, 5)", 20)}[tid]
    for d in ("calc", "tests"):
        pathlib.Path(d).mkdir(exist_ok=True)
        pathlib.Path(d, "__init__.py").touch()
    pathlib.Path(f"calc/{name}.py").write_text(f"def {name}(a, b):\n    return a {op} b\n")
    pathlib.Path(f"tests/test_{name}.py").write_text(
        f"import unittest\nfrom calc.{name} import {name}\n\n\nclass T(unittest.TestCase):\n"
        f"    def test_{name}(self):\n        self.assertEqual({call}, {want})\n")
    plan.write_text(text.replace(f"### [ ] {tid} ", f"### [x] {tid} "))
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", f"[{tid}] {name}"], check=True)
else:
    for name, cmd in (("full_gate", "python3 -m unittest discover -s tests -t ."),
                      ("e2e", "python3 -m unittest discover -s tests -t . -v")):
        subprocess.run([sys.executable, os.environ["FAKE_GATE"], "receipt", "--goal", "E-1", "--cmd", cmd,
                        "--name", name], check=True, capture_output=True)
if os.environ.get("E2E_FAKE_NO_STOP_HOOK") != "1":
    end_session()
print('{"type": "result", "total_cost_usd": 0, "num_turns": 0, "permission_denials": []}')
FAKE
for h in $HARNESSES; do
  if ! command -v "$h" >/dev/null 2>&1; then line "$h" "not live: the $h CLI is not installed"
  elif harness_run "$h" live; then continue; fi
  if must_live "$h"; then bad "$h" "a live run was requested and did not happen"; continue; fi
  line "$h" "running with a fake harness (founder decision 2026-10-09)"
  harness_run "$h" fake
done


# ── 3. Install rehearsal in disposable homes ────────────────────────────────────────────────────
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
    grep -vE '^\./\.(claude/CLAUDE|codex/AGENTS)\.md(\.bak-[0-9-]+)?$|^\./\.claude/settings\.json$|^\./\.codex/hooks\.json$')"
  [ -z "$extra" ] || drift="$drift unexpected: $(echo $extra)"
  regs="$(stop_regs "$r/.claude/settings.json" "goal.py stop-hook")/$(stop_regs "$r/.codex/hooks.json" "goal.py stop-hook")"
  [ "$regs" = 0/0 ] || drift="$drift Stop registrations claude/codex $regs, want 0/0 (run.sh registers per session)"
  [ -z "$drift" ] && ok "install" "skill = source minus tests/ in both homes, global files backed up, no Stop registration" \
    || bad "install" "$drift"
else bad "install" "install.sh exited non-zero"; fi
if inst "$INSTALL" --uninstall; then
  snapshot "$r" > "$tmp/after"
  diff -q "$tmp/before" "$tmp/after" > /dev/null && ok "uninstall" "home byte-identical to before install" ||
    bad "uninstall" "home differs: $(diff "$tmp/before" "$tmp/after" | grep '^[<>]' | head -4 | tr '\n' ' ')"
else bad "uninstall" "install.sh --uninstall exited non-zero"; fi

# The D29 rollback, the documented sequence verbatim (install/README.md, methodology.md), in a
# temporary clone. The reference is methodology/v6-base's own install/ (git archive), so a v7-only
# file the rollback left behind and the v6 installer copied is a difference.
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
    [ -z "$drift" ] && ok "rollback to v6-base" "documented sequence; every v6 skill and hook installed as shipped, nothing else" ||
      bad "rollback to v6-base" "$drift"
  else cat "$tmp/rehearsal.log"; bad "rollback to v6-base" "v6 install.sh exited non-zero"; fi
else bad "rollback to v6-base" "the documented sequence failed: $(head -1 "$tmp/wt.log")"; fi
if inst "$INSTALL" --uninstall; then
  left="$(cd "$r" && find . -type f | grep -vxF -e ./.claude/CLAUDE.md -e ./.codex/AGENTS.md | wc -l | tr -d ' ')"
  ok "uninstall after rollback" "v7 uninstall ran; $left v6 file(s) remain, which v7 does not own"
else bad "uninstall after rollback" "install.sh --uninstall exited non-zero"; fi

echo
if [ "$errors" -eq 0 ]; then echo "e2e_run: PASS (harnesses: ${ran:-none})"; exit 0; fi
echo "e2e_run: FAIL ($errors; harnesses: ${ran:-none})"; exit 1
