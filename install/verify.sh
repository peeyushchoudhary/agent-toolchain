#!/usr/bin/env bash
# Verify the toolchain. Exits non-zero if anything essential is missing or broken.
#
# This script answers TWO different questions and keeps them apart:
#
#   1. Is THIS REPOSITORY's vendored tree correct?  — anchored to the script's own location, so a
#      stranger who clones the repo is told about the repo. This is what a published verification
#      script is for.
#   2. Is THIS MACHINE correctly installed?         — anchored to $HOME/.claude and $HOME/.codex.
#      Useful, but a different question, with its own accounting and its own verdict line.
#
# They must never share a verdict line: a green machine has repeatedly masked a broken repository.
#
# Checks presence, then checks that things actually run — a file being in the right place is not
# evidence it works. Every finding printed is counted; nothing is reported and discarded. The one
# exception is the `ctx` level in `toolchain_report`, which prints a checker's coverage sentence —
# context about what ran, not a finding — and is deliberately uncounted.
#
# NO VERDICT IS RENDERED FROM AN EXIT CODE ALONE. This script used to run
# `check_toolchain.py >/dev/null 2>&1` and print "personas, instructions, and mirrors agree" on a
# zero exit — while that same run was printing `NOT A CLEAN RESULT — 3 finding(s)` on the stdout
# being discarded. The checker is right and the caller was lying: by the TC-06 ruling the exit code
# answers "can you trust this report" BEFORE it answers "did it find anything", so warn-only
# findings exit 0 on purpose. Findings are therefore read from `--json`. See `toolchain_report`.
#
# THREE OUTCOMES, NOT TWO. A check that could not run is neither a pass nor a failure, and it is
# reported in those words. `skip` is a first-class bucket for exactly that, and a skipped check
# never contributes its name to a passing line.
#
# Exit codes: 0 nothing that ran failed, 1 at least one check failed, 2 something that had to run
# COULD NOT RUN AT ALL. Note what 0 does NOT mean: a default run always skips at least the opt-in
# drift gate, so 0 is never a claim that every check ran. Skips are counted and printed in the
# verdict for exactly that reason — the verdict may not claim more than what actually executed.
#
# 2 DOMINATES 1, and that ordering is the TC-06 ruling already quoted above: the exit code answers
# "can you trust this report" BEFORE it answers "did it find anything". A run that could not execute
# a vendored suite does not know what that suite would have said, so it may not present itself as a
# run that merely found problems. See `exit_arm`.
#
# 2 IS CLAIMED NARROWLY, AND THE NARROWNESS IS DELIBERATE. Only a vendored skill suite that could
# not be executed raises it. The other `skip`s in this file are checks that were deliberately NOT
# ATTEMPTED — the opt-in drift gate, the Codex checks on a machine with no Codex — and a default run
# always has at least one of those. Routing every skip to 2 would make 2 the permanent exit status
# and destroy the distinction it exists to draw. "Was not attempted" and "was attempted and could
# not run" are different sentences; only the second is a 2.
# Absence of an OPTIONAL dependency (gh, ripgrep, graphify) is a warning and never fails.
set -uo pipefail

# ── anchoring ────────────────────────────────────────────────────────────────────────────────────
# Resolve the repository from this script's own path, never from $HOME. VENDOR is the published
# copy under test; the $HOME paths below are used only by the machine section.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
VENDOR="$SCRIPT_DIR"
VPD="$VENDOR/skills/progressive-disclosure/scripts"

CLAUDE="$HOME/.claude"
CODEX="$HOME/.codex"
IPD="$CLAUDE/skills/progressive-disclosure/scripts"

# ── options ──────────────────────────────────────────────────────────────────────────────────────
# The vendored-vs-installed drift gate is OFF by default, and the ORDER here is deliberate rather
# than deferred. Three reasons, listed with their expiry dates because two of them have one.
#
#   1. THE COMPARATOR THIS GATE ACTUALLY RUNS CANNOT YET READ THE PUBLICATION DECLARATION. An
#      `install/skills/.gitignore` declaring `graphify` unpublished is honoured by the INSTALLED
#      check_toolchain.py — but this gate prefers the VENDORED one WHENEVER THE PROBE BELOW ACCEPTS
#      IT, which today it does, and the vendored copy predates that feature, so `graphify` reports
#      as a critical rather than as excluded. Both of those are PRESENT TENSE and true today. The
#      claim that is NOT yet true — the one that must never be written in the present tense — is
#      their negation: "this gate honours the publication declaration". Re-vendoring the tree makes
#      it true; "and not before" would be false, because the fallback path below reaches the same
#      state by a different route whenever the probe rejects the vendored copy.
#      A PARTIAL LIVE SIGNAL, AND IT IS NOT AN EXPIRY TRIGGER. Whenever this gate actually uses the
#      vendored comparator, that comparator emits a legacy bare-array payload and `toolchain_report`
#      prints a `warn` saying so. While that warning prints, this reason has not expired.
#      THE CONVERSE DOES NOT HOLD, and an earlier draft of this comment claimed it did. The warning
#      is equally absent when the gate is off (the default); when the vendored check_toolchain.py is
#      missing; and when the probe rejects the vendored copy and the run falls back to the INSTALLED
#      comparator — which emits an object AND reads the declaration, so in that state reason 1 is at
#      its most alive while its signal is silent. A loud FAIL prints alongside in that state, but
#      that is a mitigation, not the signal. So: do NOT read a missing warning as expiry, and do not
#      flip reason 2's default on it.
#      THE TEST THAT IS GREEN EXACTLY WHEN THIS REASON ENDS lives in the re-vendor card's acceptance
#      criteria, in two parts: with the gate enabled, `graphify` appears under `excluded` and never
#      as `critical`, AND the legacy bare-array warning is absent. Two parts on purpose — "emits
#      objects" and "reads the declaration" are coupled only by version coincidence, and this
#      comment previously treated them as one property.
#   2. THE RE-VENDOR ORDERING. The drift is real today and is cleared by re-vendoring the tree, not
#      by editing this script. `validation:` for that work is `./verify.sh` — so making drift fatal
#      NOW would make the gate red for the very change that clears it, and the card that fixes the
#      drift could not pass its own gate. Re-vendor first, flip this second. EXPIRES with (1).
#   3. ITS ANSWER IS A PROPERTY OF THE MACHINE, NOT OF THIS REPOSITORY, AND THAT NEVER EXPIRES.
#      `--vendored` compares this tree against $HOME/.claude. A stranger who clones this repo onto
#      a machine with a different installed layer — or none — learns something about their machine.
#      That is why this block is counted in the MACHINE section below and not in the repository
#      section. A checked-in manifest would answer a DIFFERENT question — "is the published tree
#      what we said we would publish" — and is worth having, but it does not turn this comparison
#      into a repository property. Nothing does; one of the two operands is $HOME.
#
# Reasons 1 and 2 expire together when the tree is re-vendored. Reason 3 does not, and it is why
# the flip in (2) is a change of DEFAULT only — never a move back into the repository verdict.
CHECK_VENDORED_DRIFT="${VERIFY_VENDORED_DRIFT:-0}"
SELF_TEST=0

usage() {
  cat <<'USAGE'
usage: verify.sh [--check-vendored-drift] [--self-test] [-h|--help]

  --check-vendored-drift  Also compare this repository's vendored tree against the installed layer
                          (check_toolchain.py --vendored). Off by default because its answer
                          depends on the machine, not on this repository; see the comment above
                          CHECK_VENDORED_DRIFT. Equivalent to VERIFY_VENDORED_DRIFT=1.
  --self-test             Run this script's own assertions about how it reads a checker payload and
                          what it does with a vendored skill suite, print them, and exit. Checks
                          nothing about the machine or the repository.

Exit codes: 0 nothing that ran failed; 1 at least one check failed; 2 something that had to run
could not run at all, so the report is not known to be complete. 2 outranks 1.

Environment:
  VERIFY_VENDORED_DRIFT=1 same as --check-vendored-drift.
  VERIFY_SUITE_PY=PATH    interpreter used to run the vendored skill suites (default: python3).
                          The interpreter actually used is printed beside their results.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check-vendored-drift) CHECK_VENDORED_DRIFT=1 ;;
    --self-test) SELF_TEST=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'verify.sh: unknown option %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# ── accounting ───────────────────────────────────────────────────────────────────────────────────
# Two independent tallies. Every printed finding increments exactly one counter. `skip` is its own
# bucket so a deliberately-not-run check is visible in the verdict rather than silently absent or
# inflating the warning count.
repo_fail=0; repo_warn=0; repo_skip=0
env_fail=0;  env_warn=0;  env_skip=0
SCOPE="repo"

# A FOURTH TALLY, NOT A FOURTH BUCKET. `could_not_run` does not replace the scope routing above; a
# could-not-run is still printed and still counted into that scope's `skip`, so the verdict line
# goes on being honest about what did not run. This counter exists only to reach the exit code,
# because `skip` cannot: `skip` is also how a deliberately-not-attempted check is recorded, and a
# default run always has one of those. Inventing a fourth *bucket* would have meant re-routing every
# existing skip; adding a tally beside them does not.
could_not_run=0

count() {
  case "$SCOPE:$1" in
    repo:fail) repo_fail=$((repo_fail+1)) ;;
    repo:warn) repo_warn=$((repo_warn+1)) ;;
    repo:skip) repo_skip=$((repo_skip+1)) ;;
    env:fail)  env_fail=$((env_fail+1))   ;;
    env:warn)  env_warn=$((env_warn+1))   ;;
    env:skip)  env_skip=$((env_skip+1))   ;;
    *)
      printf '  \033[31mFAIL\033[0m  internal: unroutable finding (%s)\n' "$SCOPE:$1"
      repo_fail=$((repo_fail+1))
      ;;
  esac
}

ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; count fail; }
note() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; count warn; }
# `skip` is now scope-routed like the other two. It used to be a single global tally, which meant a
# not-run check in the machine section could not be told apart from one in the repository section,
# and each scope's verdict line went on claiming its tree was "intact" while a check inside it had
# not run at all.
skip() { printf '  \033[36mskip\033[0m  %s\n' "$1"; count skip; }
# `cnr` is `skip` plus the exit-2 tally, and the words COULD NOT RUN are in the label rather than
# only in the colour — the same ruling `toolchain_report`'s renderer already makes for the rc-2
# path, so an operator scanning the output can tell "was not attempted" from "was attempted and
# produced no result" without reading the sentence.
cnr()  { printf '  \033[35mCOULD NOT RUN\033[0m  %s\n' "$1"; count skip; could_not_run=$((could_not_run+1)); }
# ctx prints without counting. Same rule as the `ctx` level in toolchain_report: context about what
# ran is not a finding, and composing a finding out of it would inflate the tallies the verdict is
# computed from.
ctx()  { printf '        %s\n' "$1"; }

# exit_arm FAILS CNR -> 0 | 1 | 2. Extracted from the exit block at the bottom so --self-test can
# assert the arm a fixture selects, rather than asserting counters and *inferring* the exit code.
# The card that added the suites requires the summary and the exit code to be asserted together;
# they cannot be if the exit code exists only as a literal inside an `if` at the end of the file.
exit_arm() {
  if [ "$2" -ne 0 ]; then echo 2
  elif [ "$1" -ne 0 ]; then echo 1
  else echo 0
  fi
}

# want_file PATH OK_LABEL FAIL_MSG   — required file
want_file() { if [ -f "$1" ]; then ok "$2"; else bad "$3"; fi; }
# opt_file PATH OK_LABEL WARN_MSG    — optional file, absence is a warning
opt_file()  { if [ -f "$1" ]; then ok "$2"; else note "$3"; fi; }
# want_exec PATH OK_LABEL FAIL_MSG   — required executable
want_exec() { if [ -x "$1" ]; then ok "$2"; else bad "$3"; fi; }
# opt_cmd CMD OK_LABEL WARN_MSG      — optional third-party binary on PATH
opt_cmd()   { if command -v "$1" >/dev/null 2>&1; then ok "$2"; else note "$3"; fi; }

# runs_help SCRIPT LABEL WHERE — the script exists AND actually executes.
runs_help() {
  if [ ! -f "$1" ]; then
    bad "$2 missing from $3"
  elif python3 "$1" --help >/dev/null 2>&1; then
    ok "$2"
  else
    bad "$2 is present in $3 but fails to run — check the python version (3.10+ needed)"
  fi
}

# hook_produces_output HOOK_PATH LABEL — run the hook against a throwaway uninitialised project and
# assert it names the onboarding skill. Calls ok/bad itself.
hook_produces_output() {
  local hook_path="$1" label="$2" tmp out
  if [ ! -f "$hook_path" ]; then
    bad "$label: disclosure-check.sh not found at $hook_path"
    return
  fi
  if ! tmp=$(mktemp -d); then
    bad "$label: could not create a temp dir"
    return
  fi
  mkdir -p "$tmp/src"
  printf 'a=1\n' > "$tmp/src/a.py"
  printf 'b=2\n' > "$tmp/src/b.py"
  printf 'c=3\n' > "$tmp/src/c.py"
  out=$(CLAUDE_PROJECT_DIR="$tmp" bash "$hook_path" 2>/dev/null)
  if printf '%s' "$out" | grep -q "project-onboarding"; then
    ok "$label: uninitialised project is detected and names the skill"
  else
    bad "$label: hook did not flag an uninitialised project (got: ${out:0:80})"
  fi
  rm -rf "$tmp"
}

# ── reading a checker's result ───────────────────────────────────────────────────────────────────
# THE CONSUMER CONTRACT, and it is NARROW ON PURPOSE.
#
# This renderer is for `check_toolchain.py` ONLY. It reads `status` and `counts`.
#
# It must NOT be reused for `validate_disclosure.py`. That script's `status` is `partial` whenever
# any check family was not requested — which is every default-flag run and every session-start run —
# and `partial` still carries exit 1 when there are ERRORs. A consumer that mapped `partial` to
# "non-blocking" would swallow every error on every project. For that script, READ THE EXIT CODE.
# This script does not call it for findings (only `--help`, via runs_help), so that claim is stated
# here and NOT asserted: asserting it needs a test that runs validate_disclosure.py, which lives in
# the checker's own suite, not in this repository's write set.
#
# THE ONE RULE THAT HOLDS FOR BOTH SCRIPTS: CHECK THE EXIT STATUS BEFORE PARSING, because both have
# an rc-2 path that writes a reason to STDERR and emits NO JSON AT ALL, even under `--json`.
# `json.loads("")` raises. Re-derived at source rather than taken on trust, and the second bullet is
# a correction of what this comment said in its first draft:
#
#   * `check_toolchain.py`: five usage/environment paths (empty `--vendored`, either root missing,
#     either root a symlink, both roots resolving to the same directory, an OSError while reading).
#     Stdout is empty. Deliberate on the checker's side — an empty findings array on a path that
#     established nothing reads as "nothing was wrong".
#   * `validate_disclosure.py`: the `root.is_dir()` guard prints `not a directory: <path>` and
#     returns 2 before any payload exists. MEASURED, not inferred.
#
# WHAT THE TWO SHARE, stated here because this comment twice claimed the opposite. Once either
# script emits an OBJECT payload at all, that object carries `exit` — including
# `validate_disclosure.py`'s could-not-run object, which sets `"exit": 2` with a source comment
# saying it is present on every payload precisely so a consumer need not special-case the path
# where the answer matters most. `check_toolchain.py` says the same from its side. So
# `payload["exit"]` does NOT raise KeyError there, and the earlier claim that it did is withdrawn.
#
# THE SHAPE THAT BREAKS EVEN THAT, and it is the one this repository ships: the VENDORED
# check_toolchain.py is pre-TC-36 and emits a bare ARRAY — no `exit`, no `status`, no coverage —
# and the drift gate runs exactly that copy. So the generalisation above holds for objects only.
# `.get` is used below for that reason, and the missing key is a WARNING rather than a silent
# `None`, so the gap is visible instead of assumed. See the `exit`-key assertion in --self-test.
#
# COULD-NOT-RUN IS NOT DRIFT — AND IT SPLITS INTO TWO SHAPES THAT ARE ROUTED DIFFERENTLY.
# Exit 2 means "nothing was compared", never "the things compared differ", and the message says so
# rather than leaving it to the colour. But:
#
#   * rc 2 WITH a payload (`status: not-run`) — the checker ran, and honestly named the families it
#     could not evaluate. Routed to `skip`. A missing ~/.codex/skills arrives this way, and this
#     script explicitly supports a machine with no Codex (see the codex section), so it is never a
#     failure and never says "drifted".
#   * rc 2 with NO payload — the checker could not produce a report at all. Routed to `fail`,
#     because verify.sh controls the arguments at both call sites and cannot itself establish
#     anything from silence. The message says COULD NOT RUN, so it is distinguishable from a real
#     difference in the words and not only in the colour.
#
# SEVERITY IS THE CHECKER'S; THE ACTION IS OURS. Nothing here re-labels a finding. It only decides
# what verify.sh DOES with each severity, and an unroutable one is a failure — the same ruling
# `count()` already makes for an unroutable finding of our own.
TOOLCHAIN_RENDER_PY=$(cat <<'PY'
import json, sys

label, rc, out_path, err_path = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]

# severity (owned by the checker) -> verify.sh action (owned by us)
ROUTE = {"critical": "fail", "warn": "warn", "info": "warn", "not-run": "skip"}

lines = []


def emit(level, msg):
    lines.append((level, " ".join(str(msg).split())))


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


raw = read(out_path)
err = read(err_path).strip()
first_err = err.splitlines()[0] if err else ""

payload = None
parse_error = ""
if raw.strip():
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        parse_error = str(exc)


def render_findings(findings):
    for item in findings:
        if not isinstance(item, dict):
            emit("fail", "%s: malformed finding %r" % (label, item))
            continue
        severity = item.get("severity", "")
        detail = item.get("detail", "(no detail)")
        level = ROUTE.get(severity)
        if level is None:
            emit("fail", "%s: unknown severity `%s`, which this script cannot route safely — %s"
                 % (label, severity, detail))
        else:
            emit(level, "%s [%s] %s" % (label, severity, detail))


if payload is None:
    if rc == 2:
        # The word "drift" is deliberately absent from this sentence rather than merely negated.
        # "nothing is known to have drifted" still puts the word in front of an operator who is
        # scanning, and `--self-test` pins its absence — a negated mention would make that
        # assertion unpinnable, which is how the previous version of it came to assert nothing.
        emit("fail", "%s: the check COULD NOT RUN — nothing was compared, so no comparison result "
                     "exists either way. Reason: %s"
             % (label, first_err or "(none given on stderr)"))
    elif parse_error:
        emit("fail", "%s: exited %d but stdout is not JSON (%s) — the result is unreadable, so no "
                     "verdict is available%s"
             % (label, rc, parse_error, first_err and ". stderr: " + first_err or ""))
    else:
        emit("fail", "%s: exited %d and printed nothing on stdout — no verdict is available%s"
             % (label, rc, first_err and ". stderr: " + first_err or ""))
elif isinstance(payload, list):
    # A pre-`status` payload: a bare findings array. It cannot express the difference between
    # "nothing was wrong" and "nothing was looked at", which is why the checker stopped emitting
    # one. An empty array from this shape is therefore NOT a pass.
    emit("warn", "%s: this checker emits a legacy bare-array payload with no `status` and no "
                 "coverage, so what it actually compared cannot be established" % label)
    if payload:
        render_findings(payload)
    else:
        emit("skip", "%s: the legacy payload lists no findings, but it also cannot say what was "
                     "compared, so this is not a clean result" % label)
elif isinstance(payload, dict):
    status = payload.get("status")
    counts = payload.get("counts") or {}
    findings = payload.get("findings") or []
    summary = payload.get("summary") or ""
    # `.get`, not `[...]`, and the reason has been wrong twice now, so it is stated as a scope
    # rather than as a guarantee. WHAT IS TRUE: the two checkers' OBJECT payloads carry `exit` on
    # every path, including validate_disclosure.py's could-not-run object. WHAT IS ALSO TRUE, and
    # was missing from the previous two attempts at this comment: THIS REPOSITORY'S OWN vendored
    # check_toolchain.py emits a bare array with no `exit` anywhere, and verify.sh runs exactly
    # that copy — which is why the list branch exists above. So "every payload carries `exit`" is
    # false as a general statement about what this script is handed. It is only true of the object
    # shape, and only until someone hands it a third one.
    # Rather than restate it a third time, the absence is now BEHAVIOUR: a dict payload with no
    # `exit` produces a warning, and `--self-test` fails if that stops being true.
    declared = payload.get("exit")
    if declared is None:
        emit("warn", "%s: the payload carries no `exit` key, so the process exit status (%d) could "
                     "not be cross-checked against what the checker believes it returned"
             % (label, rc))
    elif declared != rc:
        emit("warn", "%s: the payload declares exit %s but the process exited %d — the checker's "
                     "two channels disagree" % (label, declared, rc))
    if status == "clean":
        # Read EVERY severity bucket, not just `total`. A payload whose `total` is 0 while
        # `critical` is 3 is exactly the shape a clean-looking bug produces, and trusting the
        # summary field over the itemised ones is the habit this card exists to break.
        by_severity = sum(v for k, v in counts.items()
                          if k != "total" and isinstance(v, int))
        claimed = counts.get("total") or 0
        if claimed or by_severity or findings:
            emit("fail", "%s: status is `clean` but the payload carries findings "
                         "(total=%s, by severity=%s, listed=%d) — contradictory result, not trusted"
                 % (label, claimed, by_severity, len(findings)))
        else:
            # The checker's own summary names what it checked; composing our own sentence here is
            # how the old "personas, instructions, and mirrors agree" came to outlive the facts.
            emit("ok", "%s: %s" % (label, summary or "clean"))
    elif status in ("findings", "not-run"):
        if findings:
            # `not_evaluated` is deliberately not read: every entry in it is already present in
            # `findings` with severity `not-run`, and reading both prints each one twice.
            render_findings(findings)
        else:
            emit("fail", "%s: status is `%s` but no findings were listed — the payload contradicts "
                         "itself. Summary: %s" % (label, status, summary or "(none)"))
        # THE COVERAGE SENTENCE SURVIVES A NON-CLEAN RUN. It used to be printed only on the clean
        # branch, so a run with findings silently dropped "checked: personas, instruction mirror,
        # …; 1 excluded and NOT compared: graphify". That is the header's "reported and discarded"
        # rule broken in the one direction that matters: what a failing run did NOT look at.
        # `ctx` is context, not a finding, so it is printed without being counted.
        if summary:
            emit("ctx", "%s: %s" % (label, summary))
        for item in payload.get("excluded") or []:
            if isinstance(item, dict):
                emit("ctx", "%s: EXCLUDED and not compared — %s: %s"
                     % (label, item.get("name", "?"), item.get("why", "(no reason given)")))
    elif status is None:
        emit("fail", "%s: payload has no `status` key, so no verdict can be read from it" % label)
    else:
        emit("fail", "%s: unknown status `%s` — this script will not guess whether that is a pass"
             % (label, status))
else:
    emit("fail", "%s: payload is a %s, not an object or an array" % (label, type(payload).__name__))

if not lines:
    emit("fail", "%s: produced no rendered result at all — refusing to treat silence as a pass"
         % label)

for level, message in lines:
    sys.stdout.write(level + "\t" + message + "\n")
PY
)

# toolchain_report LABEL TOOL [ARGS...] — run a check_toolchain.py invocation with --json, then
# render its verdict from the PAYLOAD, never from its exit status alone. Calls ok/bad/note/skip
# itself, so every line it prints is counted by the scope in force.
toolchain_report() {
  local label="$1" tool="$2"; shift 2
  local out err rc lvl msg rendered=0
  if ! out=$(mktemp); then bad "$label: could not create a temp file"; return; fi
  if ! err=$(mktemp); then rm -f "$out"; bad "$label: could not create a temp file"; return; fi
  python3 "$tool" "$@" --json >"$out" 2>"$err"
  rc=$?
  # A severity reaches the exit code through TWO links, and both must be constrained: the ROUTE
  # table in the renderer (severity -> level) and this dispatch (level -> counter). Breaking either
  # one silently downgrades a finding. `--self-test` drives the pair end to end for exactly that
  # reason — an earlier version exercised the renderer alone, and a `fail) note` mutation here left
  # the whole suite green while 22 criticals exited 0: this card's own defect wearing a passing
  # test. If you add a third link, constrain it too; do not read this comment as a list of two.
  # `ctx` is the one level that is printed without being counted — it carries the checker's
  # coverage sentence, which is context about the run, not a finding of its own.
  while IFS=$'\t' read -r lvl msg; do
    rendered=$((rendered+1))
    case "$lvl" in
      ok)   ok   "$msg" ;;
      warn) note "$msg" ;;
      fail) bad  "$msg" ;;
      skip) skip "$msg" ;;
      ctx)  printf '        %s\n' "$msg" ;;
      *)    bad  "$label: internal — unroutable render level ($lvl)" ;;
    esac
  done < <(python3 -c "$TOOLCHAIN_RENDER_PY" "$label" "$rc" "$out" "$err" 2>"$err.render")
  if [ "$rendered" -eq 0 ]; then
    bad "$label: the payload renderer printed nothing (rc=$rc) — $(head -1 "$err.render" 2>/dev/null)"
  fi
  rm -f "$out" "$err" "$err.render"
}

# ── running the vendored skill test suites ───────────────────────────────────────────────────────
# THE REPOSITORY PUBLISHES TESTS AS EVIDENCE THE TOOLING WORKS, AND NOTHING RAN THEM. A vendored
# suite could be stale, broken or absent and this script still printed PASS. Published tests that
# nobody runs are a claim, not a check — so they are executed here, FROM THEIR VENDORED LOCATION.
# Running the copies under $HOME instead would prove something about this machine and nothing about
# what the repository publishes; that substitution is how the published agent-personas suite drifted
# to a third of the live one without anybody noticing.
#
# TWO TREATMENTS, N SKILLS — and the N is DISCOVERED, never listed here.
#   (a) a skill WITH a runnable vendored suite -> run it, report the real result;
#   (b) a skill WITH NONE                      -> NOT TESTED HERE, in those words, in the summary,
#                                                 and never absorbed into a pass.
# Which skills are in (a) is a property of the last re-vendor, not of this repository — the
# agent-personas suite is deliberately NOT vendored, because three of its tests resolve a human
# record at <skill>/../../docs/decisions.md that does not exist in the vendored layout. A list
# written here would be a second copy of that fact and would drift the next time anyone re-vendors.
# So: discover, and let the summary say what discovery found.
#
# THREE OUTCOMES FOR A SUITE, AND THE THIRD IS WHY `cnr` EXISTS.
#   * it ran and passed                      -> ok
#   * it ran and failed                      -> FAIL (see the fatal-vs-finding note below)
#   * it produced no test result at all      -> COULD NOT RUN, exit 2, never a pass and never a
#                                               failure. "Ran N tests" is the discriminator: unittest
#                                               prints it whenever it got as far as running anything,
#                                               including when collection failed and it synthesised
#                                               an error case. No such line means the interpreter
#                                               never reached the suite — a missing or non-executable
#                                               interpreter, a crash before collection. That is one
#                                               observable fact, not an invented fourth state.
#
# A FAILING SUITE IS FATAL, and the ordering objection was checked rather than waved past. The
# precedent in this file is the drift gate (see reason 2 in the options comment): a gate is defaulted
# OFF when it would be red for the very change that clears it. That reasoning does NOT transfer here,
# and the difference is which side of the change the gate runs on. The drift exists BEFORE the
# re-vendor and is cleared BY it, so the re-vendor card's own `./verify.sh` would be red through no
# fault of its work. A failing vendored suite is the OPPOSITE: it can only appear in a tree a
# re-vendor has already produced, and the same re-vendor can produce a green one by fixing the source
# first. Measured at the time of writing, on the committed tree of this branch, both discovered
# suites pass — so there is no red state today for a fatal gate to block. If that ever inverts, the
# fix is to fix the source and re-vendor again, not to downgrade this to a warning: a knob that lets
# a red suite exit 0 is the skip-reported-as-success shape this file exists to keep out.
#
# NO OPT-OUT FLAG, and the cost is real: the suites take roughly forty seconds together. A flag to
# skip them would be a flag to make the gate green without the evidence, which is the same shape.
SUITE_PY="${VERIFY_SUITE_PY:-python3}"

suites_found=0; suites_with=0; suites_none=0
suites_pass=0;  suites_fail=0;  suites_cnr=0; suites_tests=0

# run_one_suite NAME SKILL_DIR — run SKILL_DIR/tests from inside SKILL_DIR. Calls ok/bad/cnr itself,
# so every line it prints is counted by the scope in force.
run_one_suite() {
  local name="$1" dir="$2" out rc ran="" ln tail_line="" first_line=""
  # PYTHONDONTWRITEBYTECODE: the gate must not leave __pycache__ behind in the vendored tree. It is
  # gitignored, but a verification script that dirties the thing it verifies is a bad neighbour to
  # every hook that inspects the worktree.
  out=$(cd "$dir" && PYTHONDONTWRITEBYTECODE=1 "$SUITE_PY" -m unittest discover -s tests -t tests 2>&1)
  rc=$?
  # Pure bash, not sed/grep -o. The suites' failure output carries em dashes and macOS sed dies on
  # exactly that with "RE error: illegal byte sequence" — which would turn a parse of the result
  # into an error message about the parse. The same trap is documented in --self-test below.
  while IFS= read -r ln; do
    [ -n "$ln" ] && tail_line="$ln"
    [ -z "$first_line" ] && [ -n "$ln" ] && first_line="$ln"
    case "$ln" in
      "Ran "*" test"*) ran="${ln#Ran }"; ran="${ran%% *}" ;;
    esac
  done <<< "$out"

  if [ -z "$ran" ]; then
    suites_cnr=$((suites_cnr+1))
    cnr "$name: the vendored suite COULD NOT RUN — \`$SUITE_PY\` produced no test result (rc=$rc). No verdict about this suite exists either way. First output line: ${first_line:-(no output)}"
    return
  fi
  suites_tests=$((suites_tests+ran))
  if [ "$ran" -eq 0 ]; then
    suites_fail=$((suites_fail+1))
    bad "$name: the vendored suite has a tests/ directory but discovery ran 0 tests — a suite that runs nothing is not a passing suite"
  elif [ "$rc" -ne 0 ]; then
    suites_fail=$((suites_fail+1))
    bad "$name: the vendored suite FAILED — $ran test(s) ran, rc=$rc, ${tail_line:-(no summary line)}"
  else
    suites_pass=$((suites_pass+1))
    ok "$name: $ran vendored test(s) passed"
  fi
}

# check_vendored_suites SKILLS_ROOT — discover every vendored skill under SKILLS_ROOT and apply
# whichever of the two treatments it earns. Takes the root as an argument so --self-test can drive
# it against constructed fixtures; a fixture built on a REAL suite's test count would be broken
# already, because another card may re-vendor this tree at any time.
check_vendored_suites() {
  local root="$1" d name f has_suite
  suites_found=0; suites_with=0; suites_none=0
  suites_pass=0;  suites_fail=0;  suites_cnr=0; suites_tests=0

  if [ ! -d "$root" ]; then
    bad "no vendored skills directory at $root — there is nothing to discover, which is a finding and not an empty pass"
    return
  fi
  for d in "$root"/*/; do
    [ -f "${d}SKILL.md" ] || continue
    name=$(basename "$d")
    suites_found=$((suites_found+1))
    has_suite=0
    for f in "${d}tests"/test_*.py; do
      [ -f "$f" ] && { has_suite=1; break; }
    done
    if [ "$has_suite" -eq 1 ]; then
      suites_with=$((suites_with+1))
      run_one_suite "$name" "${d%/}"
    else
      suites_none=$((suites_none+1))
      # The exact words, and they are load-bearing: this is the state four previous attempts at this
      # check reported as a pass. It is counted as a skip, so it reaches the verdict line as a check
      # that did NOT run, and it can never contribute its name to a passing sentence.
      skip "$name: NOT TESTED HERE — no vendored test suite at $name/tests"
    fi
  done

  if [ "$suites_found" -eq 0 ]; then
    # A discovered total of zero is a finding about the DISCOVERY, not a clean run. "0 suites
    # failed" and "the loop matched nothing" are indistinguishable without this.
    bad "discovery matched no vendored skills under $root — a discovered total of zero means discovery reached nothing, which is a finding and not a clean result"
  fi

  # EVERY FILTERED COUNT CARRIES ITS TOTAL. "0 suites failed" is indistinguishable from "nothing was
  # discovered"; "0 of 2" is not. Printed as ctx because it is a description of the run, not a
  # finding — the findings above it are already counted.
  ctx "$(printf 'suites: %d skill(s) discovered, %d with a vendored suite, %d NOT TESTED HERE; %d of %d suite(s) passed, %d of %d failed, %d of %d could not run; %d test(s) executed' \
    "$suites_found" "$suites_with" "$suites_none" \
    "$suites_pass" "$suites_with" "$suites_fail" "$suites_with" "$suites_cnr" "$suites_with" \
    "$suites_tests")"
}

# ── self-test ────────────────────────────────────────────────────────────────────────────────────
# WHAT THESE ASSERTIONS MEASURE, and why it is not the rendered text.
#
# An earlier version of this suite called the renderer directly and compared the first line's level
# string. It was green under two mutations that reintroduce this card's defect: `fail) note` in the
# dispatch (22 criticals printed as warnings, exit 0) and `emit("skip") -> emit("ok")` for an empty
# legacy array (a payload that established nothing, read as clean). Both survived because nothing
# reached the dispatch and nothing looked past the first line.
#
# So each assertion now drives the REAL `toolchain_report` against a stand-in checker, and measures
# the DELTA IN THE COUNTERS — repo_fail, repo_warn, repo_skip. Those counters are what the verdict
# and the exit code are computed from, so an assertion that holds them is an assertion about the
# only thing a caller of this script can observe. Text is checked too, but only as a second
# condition, never as the first.
#
# What this still CANNOT assert: anything about the real checkers' output. That belongs to their
# own suites in the progressive-disclosure skill.
if [ "$SELF_TEST" = "1" ]; then
  st_pass=0; st_fail=0
  st_dir=$(mktemp -d) || { echo "self-test: no temp dir"; exit 2; }
  cat > "$st_dir/fake_checker.py" <<'FAKE'
# A stand-in for check_toolchain.py. Replays the payload, stderr and exit code staged beside it, so
# the assertions drive the whole of toolchain_report — rc capture, the renderer, and the bash
# level->action dispatch — rather than the renderer in isolation. Arguments are ignored on purpose:
# the caller's argv is not what is under test here.
import pathlib, sys
d = pathlib.Path(__file__).resolve().parent
sys.stdout.write((d / "payload").read_text())
sys.stderr.write((d / "stderr").read_text())
sys.exit(int((d / "rc").read_text().strip()))
FAKE
  # expect_route NAME RC STDOUT STDERR WANT_FAIL WANT_WARN WANT_SKIP [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  #
  # Counter deltas are the primary condition and always checked. The two text conditions exist for
  # the cases where NO counter moves — `ctx` lines are uncounted by design, so the only way to pin
  # one is its text, and without MUST_CONTAIN the coverage sentence could be deleted with the suite
  # still green. MUST_NOT_CONTAIN pins an absence, which is the only honest way to assert a message
  # does not say something.
  expect_route() {
    local name="$1" rc="$2" so="$3" se="$4" wf="$5" ww="$6" ws="$7" needle="${8:-}" absent="${9:-}"
    local f0=$repo_fail w0=$repo_warn s0=$repo_skip df dw ds why=""
    printf '%s' "$so" > "$st_dir/payload"
    printf '%s' "$se" > "$st_dir/stderr"
    printf '%s' "$rc" > "$st_dir/rc"
    # Redirection, NOT a command substitution. `$(toolchain_report ...)` would run it in a subshell
    # and the counter deltas — the only thing that reaches the exit code — would be thrown away.
    # That is the same class of mistake this whole card is about, one layer down.
    toolchain_report "probe" "$st_dir/fake_checker.py" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); dw=$((repo_warn - w0)); ds=$((repo_skip - s0))
    # `${df}` braced and `!=` in ASCII, both deliberately. `"$df≠$wf"` looks fine and is not: bash
    # in a UTF-8 locale takes the multibyte character as part of the parameter name, so `set -u`
    # killed the whole suite with `dw≠: unbound variable` the first time a DELTA assertion failed —
    # destroying the diagnostic and skipping every assertion after it. Needle failures never hit
    # this line, so it survived until a mutation run produced a delta mismatch.
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$dw" = "$ww" ] || why="$why warn(${dw}!=${ww})"
    [ "$ds" = "$ws" ] || why="$why skip(${ds}!=${ws})"
    if [ -n "$needle" ] && ! grep -q -- "$needle" "$st_dir/rendered"; then
      why="$why missing:\"$needle\""
    fi
    if [ -n "$absent" ] && grep -q -- "$absent" "$st_dir/rendered"; then
      why="$why must-not-contain:\"$absent\""
    fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s warn+%s skip+%s\n' "$name" "$df" "$dw" "$ds"
      st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      # Pure bash, not `sed 's/^/  | /'`. The checker's findings carry em dashes and backticks, and
      # macOS sed died with "RE error: illegal byte sequence" on exactly this file — so the ONE
      # branch that exists to show evidence when an assertion fails printed an error instead of the
      # evidence. Found by a mutation run, not by review.
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }
  echo "════ self-test — what verify.sh DOES with a checker payload (counter deltas)"

  # ── the defect this card removes: not clean, yet exit 0. Must reach `warn`, never `ok`.
  expect_route "warn findings at exit 0 are counted as warnings, not passed" 0 \
    '{"status":"findings","exit":0,"counts":{"warn":1,"total":1},"findings":[{"severity":"warn","detail":"codex mirror differs"}],"summary":"NOT A CLEAN RESULT — 1 finding(s)"}' \
    '' 0 1 0 "codex mirror differs"
  # ── and the mutation that used to survive: a critical must reach the FAILURE counter, because
  #    that counter is the exit code.
  expect_route "critical findings reach the failure counter" 1 \
    '{"status":"findings","exit":1,"counts":{"critical":2,"total":2},"findings":[{"severity":"critical","detail":"a differs"},{"severity":"critical","detail":"b differs"}]}' \
    '' 2 0 0 "a differs"
  expect_route "clean touches no counter and prints the checker's own summary" 0 \
    '{"status":"clean","exit":0,"counts":{"total":0},"findings":[],"summary":"clean — personas in sync"}' \
    '' 0 0 0 "personas in sync"

  # ── the Codex-less machine: not-run is a skip, and nothing says "drifted".
  expect_route "not-run is skipped, never failed" 2 \
    '{"status":"not-run","exit":2,"counts":{"not-run":2,"total":2},"findings":[{"severity":"not-run","detail":"the Codex skill mirror was NOT RUN: ~/.codex/skills does not exist"},{"severity":"not-run","detail":"the instruction mirror was NOT RUN"}]}' \
    '' 0 0 2 "NOT RUN"
  # The name used to promise "does NOT say drifted" and pin nothing, while the message contained
  # the word. Both halves are now real: the phrase is pinned present, and "drift" pinned ABSENT.
  expect_route "could-not-run fails, says COULD NOT RUN, and never says drift" 2 '' \
    'error: installed root not found or unreadable: /nope' 1 0 0 "COULD NOT RUN" "drift"

  # ── nothing unreadable is ever a pass.
  expect_route "unparseable stdout is never a pass" 0 'not json at all' '' 1 0 0
  expect_route "empty stdout at exit 0 is never a pass" 0 '' '' 1 0 0
  expect_route "a status this script does not know is a failure" 0 \
    '{"status":"probably-fine","exit":0,"counts":{"total":0},"findings":[]}' '' 1 0 0
  expect_route "a payload with no status at all is a failure" 0 \
    '{"exit":0,"counts":{"total":0},"findings":[]}' '' 1 0 0
  expect_route "status clean contradicted by counts.total is not trusted" 0 \
    '{"status":"clean","exit":0,"counts":{"total":3},"findings":[]}' '' 1 0 0
  # counts.total says 0 while a severity bucket says 2 — the shape a clean-looking bug produces.
  expect_route "status clean contradicted by a SEVERITY bucket is not trusted" 0 \
    '{"status":"clean","exit":0,"counts":{"critical":2,"total":0},"findings":[]}' '' 1 0 0
  expect_route "an unknown severity is routed to failure, never dropped" 0 \
    '{"status":"findings","exit":0,"counts":{"total":1},"findings":[{"severity":"spicy","detail":"d"}]}' \
    '' 1 0 0 "unknown severity"

  # ── the legacy bare-array payload the vendored comparator still emits. An empty one is a SKIP:
  #    an array that cannot say what it compared has not earned a pass. The skip is asserted by the
  #    delta, so turning it into an `ok` turns this assertion red.
  expect_route "an EMPTY legacy array is warn + skip, and never ok" 0 '[]' '' 0 1 1 \
    "not a clean result"
  expect_route "a legacy array's findings are still routed by severity" 0 \
    '[{"severity":"critical","detail":"graphify absent from the vendored copy"}]' '' 1 1 0 \
    "graphify absent"

  # ── cross-checks between the two channels, and coverage that must survive a non-clean run.
  expect_route "payload exit disagreeing with the process exit is reported" 1 \
    '{"status":"clean","exit":0,"counts":{"total":0},"findings":[],"summary":"clean"}' '' 0 1 0 \
    "disagree"
  # A dict payload with NO `exit` key. The comment beside `declared` claimed twice that this cannot
  # happen; this repository's own vendored comparator disproves the general form of that claim, so
  # the gap is asserted here instead of asserted in prose.
  expect_route "a payload with no exit key is reported, not silently accepted" 0 \
    '{"status":"clean","counts":{"total":0},"findings":[],"summary":"clean"}' '' 0 1 0 \
    "no \`exit\` key"
  # F7's two ctx lines move NO counter, so the delta alone cannot pin them: deleting either
  # `emit("ctx", ...)` left this green until each got its own needle. The summary and the excluded
  # line are therefore asserted separately.
  expect_route "the coverage sentence survives a run WITH findings, uncounted" 0 \
    '{"status":"findings","exit":0,"counts":{"warn":1,"total":1},"findings":[{"severity":"warn","detail":"w"}],"excluded":[{"name":"graphify","why":"declared unpublished"}],"summary":"checked: personas, instruction mirror"}' \
    '' 0 1 0 "checked: personas, instruction mirror"
  expect_route "the excluded list survives a run WITH findings, uncounted" 0 \
    '{"status":"findings","exit":0,"counts":{"warn":1,"total":1},"findings":[{"severity":"warn","detail":"w"}],"excluded":[{"name":"graphify","why":"declared unpublished"}],"summary":"checked: personas, instruction mirror"}' \
    '' 0 1 0 "EXCLUDED and not compared — graphify"

  # ── what verify.sh DOES with a vendored skill suite ──────────────────────────────────────────
  # SAME METHOD AS ABOVE, FOR THE SAME REASON: drive the real `check_vendored_suites` and measure
  # the counter deltas, because those are what the verdict and the exit code are computed from.
  # `exit_arm` is called on the deltas so the SUMMARY TEXT and the EXIT CODE are asserted in one
  # condition — a summary that claims more than ran, with the arm that claim would select, is
  # exactly the pair that has to be pinned together.
  #
  # EVERY FIXTURE IS CONSTRUCTED HERE. None reads a real vendored suite, and none encodes a real
  # test count: another card may re-vendor install/skills/ at any moment, so a fixture anchored to
  # "294" would be a test of the calendar. The fixtures assert the two-of-two ratio and the words,
  # never a number this repository does not own.
  echo
  echo "════ self-test — what verify.sh DOES with a vendored skill suite (counter deltas + exit arm)"

  st_pass_body='import unittest


class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)

    def test_b(self):
        self.assertEqual(1, 1)
'
  st_fail_body='import unittest


class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)

    def test_b(self):
        self.assertEqual(1, 2)
'
  # mk_skill ROOT NAME — a skill with a SKILL.md and no suite.
  mk_skill() { mkdir -p "$1/$2"; printf '# %s\n' "$2" > "$1/$2/SKILL.md"; }
  # mk_suite ROOT NAME BODY — give an existing fixture skill a suite.
  mk_suite() { mkdir -p "$1/$2/tests"; printf '%s' "$3" > "$1/$2/tests/test_fixture.py"; }

  # expect_suites NAME ROOT WANT_FAIL WANT_SKIP WANT_CNR WANT_ARM [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  expect_suites() {
    local name="$1" root="$2" wf="$3" ws="$4" wc="$5" wa="$6" needle="${7:-}" absent="${8:-}"
    local f0=$repo_fail s0=$repo_skip c0=$could_not_run df ds dc arm why="" st_ln
    check_vendored_suites "$root" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); ds=$((repo_skip - s0)); dc=$((could_not_run - c0))
    arm=$(exit_arm "$df" "$dc")
    # ASCII `!=` and braced parameters, for the reason documented on expect_route: a multibyte
    # character here made `set -u` kill the whole suite on the first delta mismatch.
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$ds" = "$ws" ] || why="$why skip(${ds}!=${ws})"
    [ "$dc" = "$wc" ] || why="$why cnr(${dc}!=${wc})"
    [ "$arm" = "$wa" ] || why="$why exit(${arm}!=${wa})"
    if [ -n "$needle" ] && ! grep -q -- "$needle" "$st_dir/rendered"; then
      why="$why missing:\"$needle\""
    fi
    if [ -n "$absent" ] && grep -q -- "$absent" "$st_dir/rendered"; then
      why="$why must-not-contain:\"$absent\""
    fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s skip+%s cnr+%s exit %s\n' "$name" "$df" "$ds" "$dc" "$arm"
      st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }
  # st_assert NAME CONDITION_RC WHY — for the fixture controls, which are assertions about the
  # FIXTURE rather than about verify.sh, and so have no counter delta to measure.
  st_assert() {
    if [ "$2" -eq 0 ]; then
      printf '  \033[32mok\033[0m    %s\n' "$1"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s — %s\n' "$1" "$3"; st_fail=$((st_fail+1))
    fi
  }

  # ── (a) a skill WITH a runnable suite: it runs, and the result is real.
  st_ok_root="$st_dir/skills_ok"
  mk_skill "$st_ok_root" alpha
  mk_suite "$st_ok_root" alpha "$st_pass_body"
  expect_suites "a passing vendored suite runs and is reported as passing" "$st_ok_root" \
    0 0 0 0 "alpha: 2 vendored test(s) passed" "NOT TESTED HERE — no vendored test suite"
  # The absence above is only worth anything with a positive control, which the NOT-TESTED-HERE
  # assertion below supplies: the same needle must be PRESENT there.

  # ── the summary carries the total beside every filtered count.
  expect_suites "the summary reports each count against its total" "$st_ok_root" \
    0 0 0 0 "1 skill(s) discovered, 1 with a vendored suite, 0 NOT TESTED HERE"

  # ── (b) a skill with NO suite: NOT TESTED HERE, in those words, never a pass.
  st_none_root="$st_dir/skills_none"
  mk_skill "$st_none_root" gamma
  expect_suites "a skill with no vendored suite is NOT TESTED HERE and never a pass" "$st_none_root" \
    0 1 0 0 "gamma: NOT TESTED HERE — no vendored test suite" "vendored test(s) passed"
  # ^ the positive control for the previous assertion's absence claim, and its own absence claim
  #   ("vendored test(s) passed") is controlled by the passing assertion above.

  # ── a FAILING suite. Built by MUTATING a fixture that is first proven to pass, so the failure can
  #    only come from the mutation — and the mutation is proven to have changed the file.
  st_fail_root="$st_dir/skills_fail"
  mk_skill "$st_fail_root" alpha; mk_suite "$st_fail_root" alpha "$st_pass_body"
  mk_skill "$st_fail_root" beta;  mk_suite "$st_fail_root" beta  "$st_pass_body"
  cp "$st_fail_root/beta/tests/test_fixture.py" "$st_dir/beta_original.py"
  expect_suites "control: before the mutation, both fixture suites pass" "$st_fail_root" \
    0 0 0 0 "2 of 2 suite(s) passed, 0 of 2 failed"
  mk_suite "$st_fail_root" beta "$st_fail_body"
  # modified != original, asserted rather than assumed: if the mutation were a no-op the assertion
  # below it would be measuring the unmutated fixture and would still look meaningful.
  st_differs=1
  cmp -s "$st_dir/beta_original.py" "$st_fail_root/beta/tests/test_fixture.py" && st_differs=0
  st_assert "control: the mutated fixture actually differs from the original" \
    "$((1 - st_differs))" "modified == original, so the next assertion proves nothing"
  expect_suites "a failing vendored suite is reported, named, and selects exit 1" "$st_fail_root" \
    1 0 0 1 "beta: the vendored suite FAILED"
  expect_suites "the summary cannot claim more than passed" "$st_fail_root" \
    1 0 0 1 "1 of 2 suite(s) passed, 1 of 2 failed, 0 of 2 could not run"

  # ── a suite that CANNOT EXECUTE. Not a pass, and not an ordinary failure: the failure counter
  #    must not move, and the arm must be 2.
  st_saved_py="$SUITE_PY"
  SUITE_PY="$st_dir/no-such-interpreter"
  expect_suites "a missing interpreter yields COULD NOT RUN, not pass and not failure" "$st_ok_root" \
    0 1 1 2 "COULD NOT RUN" "vendored test(s) passed"
  printf 'not an interpreter\n' > "$st_dir/notexec"; chmod 644 "$st_dir/notexec"
  SUITE_PY="$st_dir/notexec"
  expect_suites "a non-executable interpreter yields COULD NOT RUN too" "$st_ok_root" \
    0 1 1 2 "0 of 1 suite(s) passed" "vendored test(s) passed"
  SUITE_PY="$st_saved_py"
  # Control for the two absences above: with the interpreter restored, the phrase comes back.
  expect_suites "control: with the interpreter restored the same root passes again" "$st_ok_root" \
    0 0 0 0 "vendored test(s) passed" "COULD NOT RUN"

  # ── discovery that reaches nothing is a FINDING, not an empty pass.
  st_empty_root="$st_dir/skills_empty"; mkdir -p "$st_empty_root"
  expect_suites "a discovered total of zero is a finding" "$st_empty_root" \
    1 0 0 1 "discovered total of zero"
  expect_suites "a missing skills root is a finding, not a clean run" "$st_dir/no-such-root" \
    1 0 0 1 "nothing to discover"

  rm -rf "$st_dir"
  echo
  if [ "$st_fail" -eq 0 ]; then echo "SELF-TEST PASS — $st_pass assertion(s)"; exit 0; fi
  echo "SELF-TEST FAIL — $st_fail of $((st_pass + st_fail)) assertion(s)"; exit 1
fi

echo "════ 1. THIS REPOSITORY — the vendored tree at $VENDOR"
SCOPE="repo"

echo "── vendored skills"
for s in progressive-disclosure agent-personas agent-persona-factory project-onboarding; do
  want_file "$VENDOR/skills/$s/SKILL.md" "$s" "$s missing from install/skills"
done
opt_file "$VENDOR/skills/graph-navigation/SKILL.md" "graph-navigation (optional)" \
  "graph-navigation absent from install/skills — only matters if you use graphify"

echo "── vendored scripts run"
for s in validate_disclosure check_github check_toolchain push_guard install_hooks identifier_guard promote_lesson; do
  runs_help "$VPD/$s.py" "$s.py" "$VPD"
done
VSYNC="$VENDOR/skills/agent-personas/scripts/sync_personas.py"
if [ ! -f "$VSYNC" ]; then
  bad "sync_personas.py missing from install/skills/agent-personas/scripts"
elif python3 "$VSYNC" --list >/dev/null 2>&1; then
  ok "sync_personas.py"
else
  bad "sync_personas.py is vendored but fails to run"
fi

echo "── vendored personas"
vp=$(find "$VENDOR/skills/agent-personas/personas" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "${vp:-0}" -gt 0 ]; then
  ok "$vp persona(s) vendored"
else
  bad "no personas in install/skills/agent-personas/personas"
fi

echo "── vendored skill test suites (run from install/skills, not from ~/.claude)"
# WHICH INTERPRETER RAN THEM, stated in the output rather than assumed. A green gate is only as good
# as the interpreter it invoked: this machine can have a 3.9 at /usr/bin/python3 alongside a newer
# python3 on PATH, and some of these scripts need 3.10+. The line below says which one was used, so
# a green result is attributable.
ctx "interpreter: $(command -v "$SUITE_PY" 2>/dev/null || echo "$SUITE_PY (not on PATH)") — $("$SUITE_PY" -V 2>/dev/null || echo 'version unavailable')"
check_vendored_suites "$VENDOR/skills"

echo "── vendored hooks"
want_exec "$VENDOR/hooks/disclosure-check.sh" "disclosure-check.sh" \
  "install/hooks/disclosure-check.sh missing or not executable"
for h in graphify-query-advisor.py graphify-session-lessons.sh; do
  opt_file "$VENDOR/hooks/$h" "$h (optional)" "install/hooks/$h absent — graphify integration only"
done
hook_produces_output "$VENDOR/hooks/disclosure-check.sh" "vendored hook"

echo "── installer"
want_exec "$VENDOR/install.sh" "install.sh present and executable" \
  "install/install.sh missing or not executable"

# TWO SCOPES IN ONE BLOCK, AND THE SPLIT IS THE POINT. An earlier fix put the whole block in
# `env`, which was right about the comparison and wrong about everything leading up to it:
#
#   * THE COMPARISON is a machine question. One of its two operands is $HOME/.claude, so a stranger
#     with a different installed layer — or none — must not see the REPOSITORY verdict fail for it.
#     Counted under `env`. See reason 3 in the options comment for why that is permanent.
#   * THE PROBE VERDICT is a repository question, with NO $HOME operand at all. "the vendored
#     check_toolchain.py predates --vendored" is a statement about install/skills/ and nothing
#     else. Under the all-`env` version it produced "PASS this repository — every check ran and
#     passed" beside "FAIL this machine" on a machine whose install was perfect and a repository
#     that was stale — the header's rule at the top of this file, inverted, and the exact
#     wrong-cause class this file is being fixed for. Counted under `repo`.
#
# So: `repo` is in force by default here, and `env` is switched on for the comparison alone.
echo "── vendored tree vs the installed layer (the PROBE is about this repo; the COMPARISON is about this machine)"
if [ "$CHECK_VENDORED_DRIFT" != "1" ]; then
  # The comparison is what did not run, and the comparison is the machine question.
  SCOPE="env"
  skip "vendored-drift gate is opt-in — its answer depends on this machine's ~/.claude, not on this repository; enable with --check-vendored-drift"
  SCOPE="repo"
elif [ ! -f "$VPD/check_toolchain.py" ]; then
  # A file missing from the vendored tree: a repository fact, so `repo` scope, unchanged.
  skip "cannot compare — vendored check_toolchain.py is missing (already reported above)"
else
  # Prefer this repository's own comparator, and PROBE rather than assume it can do the job.
  #
  # THREE OUTCOMES, AND THE FIRST ONE USED TO BE MISREPORTED AS THE SECOND. Reading only the
  # substring and discarding `$?` meant a SyntaxError, an ImportError or a half-written re-vendor
  # all produced "predates the --vendored feature" — sending the operator to re-vendor a tree whose
  # vendored copy is BROKEN rather than merely OLD. That is the wrong-cause class this whole file
  # is being fixed for, so the rc is captured and checked first.
  drift_tool="$VPD/check_toolchain.py"
  drift_help=$(python3 "$drift_tool" --help 2>&1)
  drift_help_rc=$?
  drift_help_first=$(printf '%s\n' "$drift_help" | head -1)
  drift_usable=1
  if [ "$drift_help_rc" -ne 0 ]; then
    bad "the vendored check_toolchain.py is present but --help exits $drift_help_rc — the vendored copy is BROKEN, not old, so re-vendoring is not the fix until it runs: $drift_help_first"
    drift_usable=0
  else
    case "$drift_help" in
      *--vendored*) ;;
      *)
        bad "the vendored check_toolchain.py runs but predates the --vendored feature, so it cannot check its own tree — re-vendor the tree"
        drift_usable=0
        ;;
    esac
  fi
  if [ "$drift_usable" -eq 0 ]; then
    if [ -f "$IPD/check_toolchain.py" ]; then
      drift_tool="$IPD/check_toolchain.py"
      note "falling back to the installed check_toolchain.py so the drift is still reported"
    else
      drift_tool=""
      # The absent fallback is a MACHINE fact, unlike the probe verdict above it.
      SCOPE="env"
      skip "no installed check_toolchain.py to fall back to — the comparison was NOT measured"
      SCOPE="repo"
    fi
  fi
  if [ -n "$drift_tool" ]; then
    echo "   reproduce with: python3 $drift_tool --vendored $REPO_ROOT"
    # ONLY the comparison runs in machine scope.
    SCOPE="env"
    toolchain_report "vendored drift" "$drift_tool" --vendored "$REPO_ROOT"
    SCOPE="repo"
  fi
fi

echo
echo "════ 2. THIS MACHINE — the installed layer at $CLAUDE"
SCOPE="env"

echo "── installed skills"
for s in progressive-disclosure agent-personas agent-persona-factory project-onboarding; do
  want_file "$CLAUDE/skills/$s/SKILL.md" "$s" "$s missing from ~/.claude/skills"
done
opt_file "$CLAUDE/skills/graph-navigation/SKILL.md" "graph-navigation (optional)" \
  "graph-navigation absent — only matters if you use graphify"

echo "── installed scripts run"
for s in validate_disclosure check_github check_toolchain push_guard install_hooks identifier_guard promote_lesson; do
  runs_help "$IPD/$s.py" "$s.py" "$IPD"
done
SYNC="$CLAUDE/skills/agent-personas/scripts/sync_personas.py"
if [ ! -f "$SYNC" ]; then
  bad "sync_personas.py missing from ~/.claude/skills/agent-personas/scripts"
elif python3 "$SYNC" --list >/dev/null 2>&1; then
  ok "sync_personas.py"
else
  bad "sync_personas.py is installed but fails to run"
fi

echo "── installed hooks on disk"
want_exec "$CLAUDE/hooks/disclosure-check.sh" "disclosure-check.sh" \
  "disclosure-check.sh missing or not executable"
for h in graphify-query-advisor.py graphify-session-lessons.sh; do
  opt_file "$CLAUDE/hooks/$h" "$h (optional)" "$h absent — graphify integration only"
done

echo "── hooks wired into settings.json"
if [ ! -f "$CLAUDE/settings.json" ]; then
  bad "no ~/.claude/settings.json"
elif python3 - "$CLAUDE/settings.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"settings.json is not valid JSON: {e}", file=sys.stderr); raise SystemExit(1)
cmds = [h.get("command", "") for ev in d.get("hooks", {}).values()
        for e in ev for h in e.get("hooks", [])]
raise SystemExit(0 if any("disclosure-check.sh" in c for c in cmds) else 1)
PY
then
  ok "disclosure-check wired"
else
  bad "disclosure-check.sh is not wired into ~/.claude/settings.json (or settings.json is unreadable)"
fi

echo "── the installed hook actually produces output"
hook_produces_output "$CLAUDE/hooks/disclosure-check.sh" "installed hook"

echo "── personas rendered"
n=$(find "$CLAUDE/agents" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "${n:-0}" -gt 0 ]; then
  ok "$n persona(s) in ~/.claude/agents"
else
  bad "no personas in ~/.claude/agents — run sync_personas.py"
fi

echo "── codex"
if [ ! -d "$CODEX" ]; then
  # Three checks live in this block, and one `warn` used to stand in for all three — in a file that
  # had just introduced `skip` for exactly this. Absent Codex is not a warning about Codex; it is
  # three checks that did not run, and the verdict now counts them that way.
  echo "   ~/.codex does not exist — the three Codex checks below did not run"
  skip "Codex skill mirror NOT CHECKED — no ~/.codex"
  skip "Codex personas NOT CHECKED — no ~/.codex"
  skip "Codex [agents] config NOT CHECKED — no ~/.codex"
else
  m=$(find "$CODEX/skills" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
  if [ "${m:-0}" -ge 4 ]; then ok "$m skills mirrored"
  else bad "only ${m:-0} skills in ~/.codex/skills"; fi

  a=$(find "$CODEX/agents" -name '*.toml' 2>/dev/null | wc -l | tr -d ' ')
  if [ "${a:-0}" -gt 0 ]; then ok "$a persona(s) in ~/.codex/agents"
  else bad "no personas in ~/.codex/agents"; fi

  if grep -q '^\[agents\]' "$CODEX/config.toml" 2>/dev/null; then ok "subagents enabled"
  else bad "no [agents] block in config.toml — Codex will not spawn personas"; fi
fi

echo "── global toolchain consistency"
if [ ! -f "$IPD/check_toolchain.py" ]; then
  skip "cannot check — installed check_toolchain.py is missing (already reported above)"
else
  # This call site is the one the header is about. It used to be
  #   elif python3 "$IPD/check_toolchain.py" >/dev/null 2>&1; then ok "personas, instructions, and
  #   mirrors agree"
  # which asserted three named checks agreed, from an exit code, with their findings on the
  # discarded stdout — and printed it over a run whose own summary line read NOT A CLEAN RESULT.
  # The success sentence is now the checker's, so it cannot outlive the checker's facts.
  echo "   reproduce with: python3 $IPD/check_toolchain.py"
  toolchain_report "installed toolchain" "$IPD/check_toolchain.py"
fi

echo "── optional third-party"
opt_cmd gh       "gh (GitHub checks)" "gh absent — check_github.py local half only"
opt_cmd graphify "graphify"           "graphify absent — graph features inert (fine)"
opt_cmd rg       "ripgrep"            "rg absent — some documented searches assume it"

echo
echo "════ verdict"
# A scope with no failures but with skipped checks did NOT establish that its tree is intact — it
# established that nothing it managed to look at was broken. Those are different sentences and the
# verdict says whichever one is true, because "intact" over an unrun check is the same class of
# overclaim as "mirrors agree" over a discarded finding.
verdict_line() {
  local what="$1" fails="$2" warns="$3" skips="$4" cnrs="${5:-0}"
  if [ "$cnrs" -ne 0 ]; then
    # Same ordering as the exit code: a scope that could not run something does not know what that
    # something would have said, so it may not lead with PASS or with FAIL.
    printf '  \033[35mCOULD NOT RUN\033[0m  %s — %s check(s) could not be executed at all; %s problem(s), %s warning(s), %s not run in total\n' \
      "$what" "$cnrs" "$fails" "$warns" "$skips"
  elif [ "$fails" -ne 0 ]; then
    printf '  \033[31mFAIL\033[0m  %s — %s problem(s), %s warning(s), %s not run\n' \
      "$what" "$fails" "$warns" "$skips"
  elif [ "$skips" -ne 0 ]; then
    printf '  \033[33mPASS\033[0m  %s — no failures in what ran, but %s check(s) did NOT run (%s warning(s))\n' \
      "$what" "$skips" "$warns"
  else
    printf '  \033[32mPASS\033[0m  %s — every check ran and passed (%s warning(s))\n' "$what" "$warns"
  fi
}
# Every could-not-run so far is a vendored suite, which is a repository fact, so the whole tally is
# attributed to the repository verdict line. If a machine-scope check ever grows a could-not-run,
# split this the way the counters above are split rather than letting one line speak for both.
verdict_line "this repository — vendored tree" "$repo_fail" "$repo_warn" "$repo_skip" "$could_not_run"
verdict_line "this machine    — installed layer" "$env_fail" "$env_warn" "$env_skip"

total_fail=$((repo_fail + env_fail))
total_warn=$((repo_warn + env_warn))
total_skip=$((repo_skip + env_skip))
echo
case "$(exit_arm "$total_fail" "$could_not_run")" in
  2)
    echo "COULD NOT RUN — $could_not_run check(s) could not be executed, so this report cannot be trusted to be complete ($total_fail problem(s), $total_warn warning(s), $total_skip check(s) not run). Exit 2 outranks exit 1 on purpose: whether you can trust the report is answered before whether it found anything."
    exit 2
    ;;
  1)
    echo "FAIL — $total_fail problem(s), $total_warn warning(s), $total_skip check(s) not run"
    exit 1
    ;;
  *)
    echo "PASS — $total_warn warning(s) and $total_skip check(s) not run, none fatal"
    exit 0
    ;;
esac
