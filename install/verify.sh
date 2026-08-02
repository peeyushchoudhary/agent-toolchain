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
# COULD NOT RUN AT ALL, 64 this script was invoked wrongly (EX_USAGE — an unknown option). 64 is
# separate on purpose: the argument parser used to exit 2, so `./verify.sh --tpyo` was
# indistinguishable from "a vendored suite produced no result" to any caller keying on the code.
# Note what 0 does NOT mean: a default run always skips at least the opt-in drift gate, so 0 is
# never a claim that every check ran. Skips are counted and printed in the verdict for exactly that
# reason — the verdict may not claim more than what actually executed.
#
# 2 DOMINATES 1, and that ordering is the TC-06 ruling already quoted above: the exit code answers
# "can you trust this report" BEFORE it answers "did it find anything". A run that could not execute
# a vendored suite does not know what that suite would have said, so it may not present itself as a
# run that merely found problems. See `exit_arm`.
#
# WHAT RAISES 2 TODAY, STATED AS A FACT ABOUT THIS FILE RATHER THAN AS A PRINCIPLE. `cnr` is called
# from exactly one place — the vendored-suite runner — so a vendored skill suite that produced no
# test result is the ONLY thing that raises 2. An earlier version of this comment justified that by
# claiming every other `skip` in the file is a check "deliberately NOT ATTEMPTED". That is false,
# and the next maintainer acting on it would mis-route. These skips are ATTEMPTED AND PRODUCED NO
# RESULT — the file's own definition of could-not-run — and remain UNMIGRATED, each exiting 0:
#   * "cannot compare — vendored check_toolchain.py is missing"
#   * "no installed check_toolchain.py to fall back to — the comparison was NOT measured"
#   * "cannot check — installed check_toolchain.py is missing"
#   * the payload renderer's skip for an EMPTY legacy bare array — a payload that established nothing
# They are left as skips because migrating them is a change to the machine section's exit behaviour
# that no card has authorised, not because they are a different kind of thing. What IS true, and is
# the reason 2 must stay narrow, is that a default run always contains at least one genuinely
# not-attempted skip (the opt-in drift gate, the Codex checks on a machine with no Codex): routing
# every skip to 2 would make 2 the permanent exit status and destroy the distinction it draws.
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
could not run at all, so the report is not known to be complete; 64 unknown option (EX_USAGE). 2
outranks 1. 64 is NOT 2: a mistyped flag must not be readable as "a suite produced no result".

Requirements for the vendored skill suites:
  python3   required. Which interpreter is used is printed beside the results, because a green
            result is only as good as the interpreter that produced it, and the default is
            whatever `python3` PATH resolves to — which differs between machines.
  git       REQUIRED, and this is a real prerequisite rather than an optional extra. The vendored
            progressive-disclosure suite calls `subprocess.run(["git", ...], check=True)` at 19
            unguarded call sites; without git on PATH those tests raise and the suite goes red.
            Checked before the suites run, and reported as a machine finding if absent.
  sh, bash  required by three further call sites. Present on any POSIX machine.

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
    # 64 = EX_USAGE, NOT 2. This exited 2 before, which collided with "something that had to run
    # could not run at all" — so a caller keying on 2 got it for a typo.
    *) printf 'verify.sh: unknown option %s\n\n' "$1" >&2; usage >&2; exit 64 ;;
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
#
# AND IT IS SCOPE-ROUTED LIKE THE OTHERS. `could_not_run` is the total, which is what the exit arm
# reads; `repo_cnr` and `env_cnr` are what the two verdict LINES read. A previous version kept only
# the total and attributed all of it to the repository line with a comment saying "split this if a
# machine-scope check ever grows a could-not-run". It has: a vendored suite whose tests reach into
# $HOME can fail to run for a reason that belongs to the machine, and printing COULD NOT RUN against
# "this repository" for it is the same overclaim in the opposite direction.
could_not_run=0
repo_cnr=0; env_cnr=0

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
cnr()  {
  printf '  \033[35mCOULD NOT RUN\033[0m  %s\n' "$1"
  count skip
  could_not_run=$((could_not_run+1))
  case "$SCOPE" in env) env_cnr=$((env_cnr+1)) ;; *) repo_cnr=$((repo_cnr+1)) ;; esac
}
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
# A FAILING SUITE IS FATAL TO THE PROCESS. Which SCOPE it is fatal in is a second question, and the
# first version of this block got it wrong by answering only the first.
#
# The ordering objection was checked rather than waved past. The precedent in this file is the drift
# gate (see reason 2 in the options comment): a gate is defaulted OFF when it would be red for the
# very change that clears it. That reasoning does not transfer here, and the difference is which side
# of the change the gate runs on. The drift exists BEFORE the re-vendor and is cleared BY it, so the
# re-vendor card's own `./verify.sh` would be red through no fault of its work. A failing vendored
# suite generally appears in a tree a re-vendor has already produced, and the same re-vendor can
# produce a green one by fixing the source first. So: no default-off flag, and no opt-out flag —
# a knob that lets a red suite exit 0 is the skip-reported-as-success shape this file exists to keep
# out.
#
# WHAT THAT ARGUMENT DOES NOT COVER, AND THE FIRST VERSION OF THIS COMMENT ASSERTED ANYWAY: it said a
# failing vendored suite "can ONLY appear in a tree a re-vendor has already produced", i.e. that the
# failure is always repository-attributable and always fixable from inside this repository. The
# suites themselves contradict that. `execution-methodology/tests/test_repo_sync.py` executes
# `$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py` and asserts its stderr
# is empty; `progressive-disclosure`'s suite reaches into `$HOME` in four of its seven files. Land a
# new finding kind in the INSTALLED validator, or upgrade the interpreter so it emits one
# DeprecationWarning on stderr, and a pristine untouched clone goes red — for a reason living
# entirely outside the clone.
#
# THE RULE THAT SETTLES IT IS ALREADY IN THIS FILE, as reason 3 of the drift-gate comment above:
# "one of the two operands is $HOME", therefore the answer is a property of the machine and never a
# move back into the repository verdict. That is a precedent, not a new policy, and it is applied
# here rather than re-derived: a suite whose own sources reach into $HOME has its FAILURES and its
# COULD-NOT-RUNS counted in the MACHINE scope. It is still fatal to the process — env failures always
# were, exactly like `only N skills in ~/.codex/skills` two hundred lines below — so nothing becomes
# silently green. What changes is which verdict line wears it, and a stranger cloning this repository
# onto a machine with a different ~/.claude no longer reads "FAIL this repository" for their machine.
#
# Whether a suite reaches into $HOME is DISCOVERED from its own sources, not listed here, for the
# same reason the skills are: a list is a second copy of a fact that moves with every re-vendor.
#
# NO OPT-OUT FLAG, and the cost is real: the suites take roughly forty seconds together. A flag to
# skip them would be a flag to make the gate green without the evidence, which is the same shape.
#
# THE INTERPRETER IS A MACHINE PROPERTY THIS GATE CANNOT CONTROL. `python3` from PATH is whatever
# this machine put first, so the green below is green UNDER THAT INTERPRETER and no other. The
# version is printed with the results for exactly that reason. Detecting that a user's default
# interpreter differs from the one a green was recorded under is a real gap and is one layer above
# this check; what is in scope here is that the output must never let a reader assume otherwise.
SUITE_PY="${VERIFY_SUITE_PY:-python3}"

suites_found=0; suites_with=0; suites_none=0; suites_excluded=0
suites_pass=0;  suites_fail=0;  suites_cnr=0; suites_vacuous=0
suites_tests=0; suites_skipped=0

# suite_reaches_home TESTS_DIR — does this suite's own source read $HOME? Discovered, never listed.
# The answer decides which SCOPE a failure or a could-not-run is counted in; see the long comment
# above. Deliberately over-inclusive: a false positive moves a failure to the machine line, where it
# is still printed and still fatal to the process, while a false negative would put a machine fact
# back into the repository verdict — which is the thing reason 3 of the drift-gate comment forbids.
# grep's own failure is treated as "yes" for the same fail-safe reason.
suite_reaches_home() {
  grep -rqE 'Path\.home\(\)|expanduser|HOME' "$1" --include='*.py' 2>/dev/null && return 0
  [ $? -eq 1 ] && return 1
  return 0
}

# has_test_file DIR — does DIR, or anything beneath it, hold a file matching `test*.py`?
#
# PURE BASH, AND THAT IS NOT STYLE. The first version of this used
# `find "$dir" -name 'test*.py' -print -quit`, which introduced an external-binary dependency into
# the one predicate that decides whether a suite gets run at all — and its failure mode when `find`
# is unavailable is to return nothing, i.e. a SILENT FALSE "NOT TESTED HERE". That is the exact
# defect this function was being changed to remove, reintroduced one layer down by the fix for it.
# Caught by running the gate under a PATH that did not resolve `find`. Recursion by plain glob has
# no such mode: a directory that cannot be read simply contributes no match, and the floor guard
# below turns "nothing at all has a suite" into a loud finding either way.
#
# `test*.py` and recursive, matching what `unittest discover` collects, NOT the old
# `tests/test_*.py` non-recursive glob — which called `tests/unit/test_x.py` and `tests/tests_x.py`
# no suite at all. Over-matching is the safe direction: a directory that matches and then discovers
# nothing is already a loud `bad`, whereas under-matching is a silent skip.
has_test_file() {
  local d="$1" f
  for f in "$d"/test*.py; do [ -f "$f" ] && return 0; done
  for f in "$d"/*/; do
    [ -d "$f" ] || continue
    has_test_file "${f%/}" && return 0
  done
  return 1
}

# run_one_suite NAME SKILL_DIR — run SKILL_DIR/tests from inside SKILL_DIR. Calls ok/bad/cnr/skip
# itself, so every line it prints is counted by the scope in force at that moment.
#
# SKIPS ARE PARSED AND SURFACED, AND THIS IS THE CARD'S OWN DEFECT CLASS ONE LEVEL DOWN. This
# function used to discriminate on `Ran N` plus the return code alone. `TestResult.startTest`
# increments `testsRun` BEFORE the skip check, so a skipped test is inside `Ran N`, and the run still
# exits 0 with `OK (skipped=K)` — which meant `98 vendored test(s) passed` over a 10-test class that
# never executed an assertion. Both vendored suites carry live conditional skips keyed on
# `Path.home()` state this repository does not own, so the first green recorded for this gate was
# obtained on a machine where none of those guards fire, and the output did not say so.
#   * skipped tests are subtracted from the passed count and reported as `K of N ... NOT TESTED HERE`
#   * they are routed to `skip`, so they reach the verdict as checks that DID NOT RUN
#   * a suite where EVERY test skipped is not a pass at all: it is the whole suite NOT TESTED HERE
# The word "passed" now only ever appears over tests that actually executed an assertion.
run_one_suite() {
  local name="$1" dir="$2" out rc ran="" ln tail_line="" first_line="" sk=0 execd
  local home=0 saved_scope="$SCOPE"
  suite_reaches_home "$dir/tests" && home=1
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
  # The skip count lives in unittest's trailing line — `OK (skipped=10)`, or
  # `FAILED (failures=1, skipped=2)`. Pure bash for the reason above: macOS sed dies on the em dashes
  # these suites emit, so a parse of the result would become an error message about the parse.
  case "$tail_line" in
    *"skipped="*) sk="${tail_line#*skipped=}"; sk="${sk%%[!0-9]*}"; sk="${sk:-0}" ;;
  esac

  # $HOME-reaching suites: failures and could-not-runs are MACHINE facts. See the block comment.
  [ "$home" -eq 1 ] && SCOPE="env"

  if [ -z "$ran" ]; then
    suites_cnr=$((suites_cnr+1))
    cnr "$name: the vendored suite COULD NOT RUN — \`$SUITE_PY\` produced no test result (rc=$rc). No verdict about this suite exists either way. First output line: ${first_line:-(no output)}"
    SCOPE="$saved_scope"
    return
  fi
  suites_tests=$((suites_tests+ran))
  suites_skipped=$((suites_skipped+sk))
  execd=$((ran - sk))
  if [ "$ran" -eq 0 ]; then
    # Discovery reached the suite and found nothing to run. That is a fact about the tree, so it is
    # reported in the scope in force before the $HOME routing above — restored first, deliberately.
    SCOPE="$saved_scope"
    suites_fail=$((suites_fail+1))
    bad "$name: the vendored suite has a tests/ directory but discovery ran 0 tests — a suite that runs nothing is not a passing suite"
  elif [ "$rc" -ne 0 ]; then
    suites_fail=$((suites_fail+1))
    bad "$name: the vendored suite FAILED — $execd of $ran test(s) executed, $sk skipped, rc=$rc, ${tail_line:-(no summary line)}$([ "$home" -eq 1 ] && printf ' [counted against THIS MACHINE, not this repository: this suite reads $HOME, so its result is not a property of the vendored tree alone]')"
  elif [ "$execd" -le 0 ]; then
    # Every test skipped. `OK (skipped=N)` over zero executed assertions is not a pass, and it is not
    # a repository failure either — the guards that fired are keyed on $HOME state. It is the whole
    # suite NOT TESTED HERE, in those words, counted as a skip.
    suites_vacuous=$((suites_vacuous+1))
    skip "$name: NOT TESTED HERE — all $ran vendored test(s) were SKIPPED by the suite's own guards, so 0 of $ran executed an assertion. \`${tail_line:-?}\` is not evidence"
  else
    suites_pass=$((suites_pass+1))
    ok "$name: $execd of $ran vendored test(s) passed"
    if [ "$sk" -gt 0 ]; then
      # Surfaced as its own counted skip, never folded into the sentence above. This is the row that
      # made the first green machine-dependent without saying so.
      skip "$name: $sk of $ran vendored test(s) NOT TESTED HERE — SKIPPED by the suite's own guards (\`${tail_line:-?}\`), typically keyed on \$HOME state this repository does not own"
    fi
  fi
  SCOPE="$saved_scope"
}

# check_vendored_suites SKILLS_ROOT — discover every vendored skill under SKILLS_ROOT and apply
# whichever of the two treatments it earns. Takes the root as an argument so --self-test can drive
# it against constructed fixtures; a fixture built on a REAL suite's test count would be broken
# already, because another card may re-vendor this tree at any time.
check_vendored_suites() {
  local root="$1" d name has_suite
  suites_found=0; suites_with=0; suites_none=0; suites_excluded=0
  suites_pass=0;  suites_fail=0;  suites_cnr=0; suites_vacuous=0
  suites_tests=0; suites_skipped=0

  if [ ! -d "$root" ]; then
    bad "no vendored skills directory at $root — there is nothing to discover, which is a finding and not an empty pass"
    return
  fi

  # WHICH INTERPRETER RAN THEM, printed INSIDE this function rather than at the call site. It lived
  # at the single call site before, which put a hard requirement of the card outside everything
  # --self-test can reach: deleting the line left the whole suite green. It is now emitted by the
  # function under test and pinned by an assertion.
  ctx "interpreter: $(command -v "$SUITE_PY" 2>/dev/null || echo "$SUITE_PY (not on PATH)") — $("$SUITE_PY" -V 2>&1 || echo 'version unavailable') (whatever this machine puts first on PATH; a green below is green under THIS interpreter and no other)"

  # THE REPOSITORY ALREADY DECLARES WHAT IT PUBLISHES, and discovery must read the same declaration
  # the rest of the toolchain does. `install/skills/.gitignore` is an allowlist — "ignore everything
  # at the top level, then name the skills this repository owns" — written because this directory is
  # also where vendor skills install THEMSELVES (graphify arrives via `uv tool` on its own schedule).
  # `check_toolchain.py` honours it. This loop did not, so a wholesale re-vendor leaving an untracked
  # `graphify/` here would have added a seventh discovered skill and, if it shipped tests, run a
  # third party's suite fatally against a skill this repository declares it does not publish.
  #
  # git itself is the authority, so no second gitignore parser is introduced. If git cannot answer —
  # not installed, or this is an unpacked tarball rather than a checkout — the declaration is
  # UNREADABLE, which is not the same as empty: it is reported, and discovery proceeds over
  # everything, because testing more than declared is the safe direction and testing less is not.
  local can_read_decl=1
  if ! command -v git >/dev/null 2>&1 || ! git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    can_read_decl=0
    # MACHINE scope: the declaration is a repository artifact, but every reason it cannot be read is
    # machine-side — git not installed, or this tree was unpacked from a tarball rather than cloned.
    # Same rule as everywhere else in this file: if the answer depends on the machine, it does not
    # belong in the repository verdict.
    local decl_scope="$SCOPE"; SCOPE="env"
    note "the publication declaration (install/skills/.gitignore) could NOT be read — no git, or this is not a checkout — so discovery below cannot tell a skill this repository publishes from one a vendor installed here on its own"
    SCOPE="$decl_scope"
  fi

  for d in "$root"/*/; do
    [ -f "${d}SKILL.md" ] || continue
    name=$(basename "$d")
    if [ "$can_read_decl" -eq 1 ] && git -C "$root" check-ignore -q "$d" 2>/dev/null; then
      suites_excluded=$((suites_excluded+1))
      ctx "$name: EXCLUDED and not discovered — install/skills/.gitignore declares this repository does not publish it"
      continue
    fi
    suites_found=$((suites_found+1))
    has_suite=0
    if [ -d "${d}tests" ] && has_test_file "${d}tests"; then has_suite=1; fi
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
  elif [ "$suites_with" -eq 0 ]; then
    # THE FLOOR, and the zero-guard above does not supply it. `suites_found` is not the
    # evidence-bearing quantity; `suites_with` is. Delete every vendored `tests/` directory and the
    # old check printed "6 discovered, 0 with a vendored suite, 6 NOT TESTED HERE" and exited 0 —
    # the published tests silently stop being evidence and nothing says so. Same argument as the
    # zero-discovery guard, applied to the quantity that actually carries the evidence.
    bad "$suites_found vendored skill(s) discovered under $root and NOT ONE has a test suite — this repository publishes tests as evidence, so zero runnable suites is a finding and not a clean result"
  fi

  # EVERY FILTERED COUNT CARRIES ITS TOTAL. "0 suites failed" is indistinguishable from "nothing was
  # discovered"; "0 of 2" is not. Printed as ctx because it is a description of the run, not a
  # finding — the findings above it are already counted. Two lines: suites, then tests, because the
  # test-level skip count is the one this gate was previously silent about.
  ctx "$(printf 'suites: %d skill(s) discovered (%d excluded by the publication declaration), %d with a vendored suite, %d NOT TESTED HERE; %d of %d suite(s) passed, %d of %d failed, %d of %d could not run, %d of %d ran only skips' \
    "$suites_found" "$suites_excluded" "$suites_with" "$suites_none" \
    "$suites_pass" "$suites_with" "$suites_fail" "$suites_with" "$suites_cnr" "$suites_with" \
    "$suites_vacuous" "$suites_with")"
  ctx "$(printf 'tests:  %d of %d vendored test(s) actually executed an assertion; %d of %d were SKIPPED and are NOT TESTED HERE' \
    "$((suites_tests - suites_skipped))" "$suites_tests" "$suites_skipped" "$suites_tests")"
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
  # One passing test and one SKIPPED test -> `Ran 2 tests` + `OK (skipped=1)`, which is exactly the
  # shape that used to be printed as "2 vendored test(s) passed".
  st_skip_body='import unittest


class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)

    @unittest.skip("guard fired")
    def test_b(self):
        self.assertEqual(1, 1)
'
  # EVERY test skipped -> `Ran 2 tests` + `OK (skipped=2)`, exit 0, zero assertions executed.
  st_allskip_body='import unittest


@unittest.skip("guard fired")
class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)

    def test_b(self):
        self.assertEqual(1, 1)
'
  # A FAILING suite whose own source reads $HOME. `pathlib.Path.home()` is never called — its mere
  # presence in the source is what `suite_reaches_home` detects, and detecting it from the source
  # rather than from behaviour is the point: the check must work without running anything.
  st_home_fail_body='import unittest
from pathlib import Path

_WHERE = Path.home()


class T(unittest.TestCase):
    def test_a(self):
        self.assertEqual(1, 2)
'
  # mk_skill ROOT NAME — a skill with a SKILL.md and no suite.
  mk_skill() { mkdir -p "$1/$2"; printf '# %s\n' "$2" > "$1/$2/SKILL.md"; }
  # mk_suite ROOT NAME BODY — give an existing fixture skill a suite.
  mk_suite() { mkdir -p "$1/$2/tests"; printf '%s' "$3" > "$1/$2/tests/test_fixture.py"; }

  # expect_suites NAME ROOT WANT_FAIL WANT_SKIP WANT_CNR WANT_ARM [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  #               [WANT_ENV_FAIL] [WANT_ENV_SKIP]
  #
  # THE ENV DELTAS ARE ASSERTED TOO, AND DEFAULT TO ZERO. Without them a mutation that routed every
  # suite finding into the machine scope would leave every assertion here green while the repository
  # verdict went permanently silent — and $HOME-scope routing is precisely what this block now
  # contains, so the counter it moves has to be pinned on BOTH sides.
  expect_suites() {
    local name="$1" root="$2" wf="$3" ws="$4" wc="$5" wa="$6" needle="${7:-}" absent="${8:-}"
    local wef="${9:-0}" wes="${10:-0}"
    local f0=$repo_fail s0=$repo_skip c0=$could_not_run ef0=$env_fail es0=$env_skip
    local df ds dc def des arm why="" st_ln
    check_vendored_suites "$root" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); ds=$((repo_skip - s0)); dc=$((could_not_run - c0))
    def=$((env_fail - ef0)); des=$((env_skip - es0))
    arm=$(exit_arm "$((df + def))" "$dc")
    # ASCII `!=` and braced parameters, for the reason documented on expect_route: a multibyte
    # character here made `set -u` kill the whole suite on the first delta mismatch.
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$ds" = "$ws" ] || why="$why skip(${ds}!=${ws})"
    [ "$dc" = "$wc" ] || why="$why cnr(${dc}!=${wc})"
    [ "$def" = "$wef" ] || why="$why envfail(${def}!=${wef})"
    [ "$des" = "$wes" ] || why="$why envskip(${des}!=${wes})"
    [ "$arm" = "$wa" ] || why="$why exit(${arm}!=${wa})"
    if [ -n "$needle" ] && ! grep -q -- "$needle" "$st_dir/rendered"; then
      why="$why missing:\"$needle\""
    fi
    if [ -n "$absent" ] && grep -q -- "$absent" "$st_dir/rendered"; then
      why="$why must-not-contain:\"$absent\""
    fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s skip+%s cnr+%s envfail+%s envskip+%s exit %s\n' \
        "$name" "$df" "$ds" "$dc" "$def" "$des" "$arm"
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
    0 0 0 0 "alpha: 2 of 2 vendored test(s) passed" "NOT TESTED HERE — no vendored test suite"
  # The absence above is only worth anything with a positive control, which the NOT-TESTED-HERE
  # assertion below supplies: the same needle must be PRESENT there.

  # ── the summary carries the total beside every filtered count.
  expect_suites "the summary reports each count against its total" "$st_ok_root" \
    0 0 0 0 "1 skill(s) discovered (0 excluded by the publication declaration), 1 with a vendored suite, 0 NOT TESTED HERE"
  # The test-level line is a SECOND summary and needs its own pin: `suites_tests` was never asserted
  # at all before, so deleting the accumulator left every assertion green.
  expect_suites "the test-level summary reports executed against total, with a real value" "$st_ok_root" \
    0 0 0 0 "tests:  2 of 2 vendored test(s) actually executed an assertion; 0 of 2 were SKIPPED"
  # ── the interpreter-provenance line is a hard requirement of the card, so it is pinned. It used to
  #    live at the production call site, outside everything this block can reach.
  expect_suites "the interpreter that ran the suites is named in the output" "$st_ok_root" \
    0 0 0 0 "interpreter: "

  # ── (b) a skill with NO suite: NOT TESTED HERE, in those words, never a pass.
  st_none_root="$st_dir/skills_none"
  mk_skill "$st_none_root" gamma
  # fail+1/exit 1 because this root is ALSO the floor case (row 5): one skill, none with a suite.
  # Both findings are expected here, and pinning the pair together is what proves the NOT-TESTED-HERE
  # skip is not quietly standing in for the floor finding or vice versa.
  expect_suites "a skill with no vendored suite is NOT TESTED HERE and never a pass" "$st_none_root" \
    1 1 0 1 "gamma: NOT TESTED HERE — no vendored test suite" "vendored test(s) passed"
  # ^ the positive control for the previous assertion's absence claim, and its own absence claim
  #   ("vendored test(s) passed") is controlled by the passing assertion above.

  # ── A MIXED ROOT. Every sub-count of the summary is pinned NON-ZERO here, which is what the
  #    single-skill roots above cannot do. `suites_none` was pinned only at 0, so the mutation
  #    `suites_none=$((suites_none+0))` survived all thirty assertions while production printed
  #    "0 NOT TESTED HERE" over four untested skills. A counter no assertion pins non-zero is not
  #    covered, and that is the vacuity rule this card already carried, applied to counters.
  st_mixed_root="$st_dir/skills_mixed"
  mk_skill "$st_mixed_root" alpha; mk_suite "$st_mixed_root" alpha "$st_pass_body"
  mk_skill "$st_mixed_root" gamma
  expect_suites "a mixed root pins discovered, with-a-suite and NOT-TESTED-HERE all non-zero" \
    "$st_mixed_root" 0 1 0 0 "2 skill(s) discovered (0 excluded by the publication declaration), 1 with a vendored suite, 1 NOT TESTED HERE"

  # ── (row 10) DISCOVERY MATCHES WHAT `unittest discover` MATCHES. `tests_x.py` at the top level and
  #    `tests/unit/test_x.py` nested are both suites; the old `tests/test_*.py` non-recursive glob
  #    called them NO SUITE AT ALL — a false NOT TESTED HERE with no finding attached.
  st_shape_root="$st_dir/skills_shape"
  mk_skill "$st_shape_root" delta
  mkdir -p "$st_shape_root/delta/tests"
  printf '%s' "$st_pass_body" > "$st_shape_root/delta/tests/tests_oddly_named.py"
  expect_suites "a suite named tests_x.py is discovered, not reported as having none" "$st_shape_root" \
    0 0 0 0 "delta: 2 of 2 vendored test(s) passed" "no vendored test suite"
  st_nest_root="$st_dir/skills_nested"
  mk_skill "$st_nest_root" epsilon
  mkdir -p "$st_nest_root/epsilon/tests/unit"
  printf '%s' "$st_pass_body" > "$st_nest_root/epsilon/tests/unit/test_x.py"
  # It is counted as HAVING a suite. Whether unittest then collects it depends on the nested
  # directory being an importable package — which is why over-matching is safe: the miss becomes the
  # loud "ran 0 tests" finding below instead of a silent skip. Either outcome is a non-zero delta,
  # so the assertion pins the thing that matters: it is NOT reported as having no suite.
  expect_suites "a nested suite is counted as a suite, never as NOT TESTED HERE" "$st_nest_root" \
    1 0 0 1 "1 with a vendored suite, 0 NOT TESTED HERE"

  # ── (row 1, THE FINDING OF THIS ROUND) A SKIPPED TEST IS SURFACED, NEVER ABSORBED INTO "passed".
  #    `TestResult.startTest` increments `testsRun` before the skip check, so a skipped test is
  #    inside `Ran N` and the run still exits 0 with `OK (skipped=K)`. The old code discriminated on
  #    `Ran N` + rc alone and printed "2 vendored test(s) passed" over it.
  #
  #    The fixture is the SAME fixture as the passing root, with one decorator added — so the
  #    positive control for "this is what the same suite looks like without the skip" is the
  #    `st_ok_root` assertion above, which pins `2 of 2 ... passed` and, below, the ABSENCE of the
  #    skip sentence. Two roots, one differing line.
  st_skip_root="$st_dir/skills_skip"
  mk_skill "$st_skip_root" alpha; mk_suite "$st_skip_root" alpha "$st_skip_body"
  expect_suites "a skipped test is counted and named, not folded into the passed count" \
    "$st_skip_root" 0 1 0 0 "alpha: 1 of 2 vendored test(s) NOT TESTED HERE — SKIPPED"
  expect_suites "the passed sentence covers only tests that executed an assertion" \
    "$st_skip_root" 0 1 0 0 "alpha: 1 of 2 vendored test(s) passed"
  expect_suites "the test-level summary carries the skip count" \
    "$st_skip_root" 0 1 0 0 "tests:  1 of 2 vendored test(s) actually executed an assertion; 1 of 2 were SKIPPED"
  # POSITIVE CONTROL for that absence: the identical fixture WITHOUT the skip decorator says none of
  # it, and says `2 of 2 ... passed` instead.
  expect_suites "control: the same fixture without the skip says nothing about skips" "$st_ok_root" \
    0 0 0 0 "alpha: 2 of 2 vendored test(s) passed" "SKIPPED by the suite's own guards"

  # ── a suite where EVERY test skipped: `OK (skipped=2)`, exit 0, zero assertions executed. That is
  #    not a pass. It is the whole suite NOT TESTED HERE, and the passed sentence must be absent.
  st_allskip_root="$st_dir/skills_allskip"
  mk_skill "$st_allskip_root" alpha; mk_suite "$st_allskip_root" alpha "$st_allskip_body"
  expect_suites "a suite where every test skipped is NOT TESTED HERE, never a pass" \
    "$st_allskip_root" 0 1 0 0 "alpha: NOT TESTED HERE — all 2 vendored test(s) were SKIPPED" "vendored test(s) passed"
  expect_suites "and the summary counts it as ran-only-skips, not as passed" \
    "$st_allskip_root" 0 1 0 0 "0 of 1 suite(s) passed, 0 of 1 failed, 0 of 1 could not run, 1 of 1 ran only skips"

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
  # `suites_cnr` was pinned only at 0: the two assertions above pin the CNR bucket via the
  # `could_not_run` delta, which `cnr()` moves, not via this counter. Deleting `suites_cnr` left the
  # summary printing "0 of 1 could not run" beside a COULD NOT RUN line, with everything green.
  expect_suites "the summary counts the could-not-run against its total" "$st_ok_root" \
    0 1 1 2 "0 of 1 suite(s) passed, 0 of 1 failed, 1 of 1 could not run"
  SUITE_PY="$st_saved_py"
  # Control for the two absences above: with the interpreter restored, the phrase comes back.
  expect_suites "control: with the interpreter restored the same root passes again" "$st_ok_root" \
    0 0 0 0 "vendored test(s) passed" "COULD NOT RUN"

  # ── (row 7) DISCOVERY HONOURS THE PUBLICATION DECLARATION, the same one check_toolchain.py reads.
  #    This fixture is a real git checkout because git itself is the parser — the alternative was a
  #    second gitignore implementation in bash, which would be a second copy of the truth. git is a
  #    declared prerequisite of this gate (see --help), so requiring it here is not a new dependency.
  st_decl_root="$st_dir/skills_decl"
  mk_skill "$st_decl_root" alpha;    mk_suite "$st_decl_root" alpha "$st_pass_body"
  mk_skill "$st_decl_root" graphify; mk_suite "$st_decl_root" graphify "$st_fail_body"
  printf '/*\n!/.gitignore\n!/alpha\n' > "$st_decl_root/.gitignore"
  git -C "$st_decl_root" init -q >/dev/null 2>&1
  # graphify is declared unpublished, so its FAILING suite must never be discovered, never run, and
  # never reach a counter. Without the declaration it would be a fatal failure over a skill this
  # repository says it does not publish.
  expect_suites "a skill the declaration excludes is not discovered and its suite is not run" \
    "$st_decl_root" 0 0 0 0 "graphify: EXCLUDED and not discovered" "the vendored suite FAILED"
  expect_suites "and the excluded count is reported beside the discovered total" \
    "$st_decl_root" 0 0 0 0 "1 skill(s) discovered (1 excluded by the publication declaration), 1 with a vendored suite"
  # POSITIVE CONTROL: with the declaration removed, the same tree discovers graphify and its failing
  # suite goes red. Without this, a mutation that simply skipped every skill would pass the two above.
  rm "$st_decl_root/.gitignore"
  expect_suites "control: remove the declaration and the same excluded suite is discovered and fails" \
    "$st_decl_root" 1 0 0 1 "graphify: the vendored suite FAILED" "EXCLUDED and not discovered"
  # And the DEGRADED path: outside a checkout the declaration cannot be read, which is reported
  # rather than silently treated as "nothing is excluded". Every other fixture root in this block is
  # a bare mktemp directory, so this warning was firing throughout, unpinned by anything.
  expect_suites "an unreadable declaration is reported, not treated as an empty one" "$st_ok_root" \
    0 0 0 0 "publication declaration (install/skills/.gitignore) could NOT be read"

  # ── (row 2) A SUITE WHOSE OWN SOURCE READS $HOME IS NOT FATAL TO THE *REPOSITORY* VERDICT.
  #    Reason 3 of the drift-gate comment, applied: one operand is $HOME, so the answer is a property
  #    of the machine. The failure is still counted and still selects exit 1 — it moves scope, it
  #    does not soften. The pair of assertions below is the whole claim: repo_fail must NOT move,
  #    env_fail MUST, and the arm must still be 1.
  st_home_root="$st_dir/skills_home"
  mk_skill "$st_home_root" zeta; mk_suite "$st_home_root" zeta "$st_home_fail_body"
  expect_suites "a \$HOME-reaching suite's failure lands on the MACHINE line, not the repository's" \
    "$st_home_root" 0 0 0 1 "zeta: the vendored suite FAILED" "" 1 0
  expect_suites "and it says why it was attributed to the machine" \
    "$st_home_root" 0 0 0 1 "counted against THIS MACHINE, not this repository" "" 1 0
  # POSITIVE CONTROL: the same failure shape in a suite that does NOT read $HOME stays on the
  # repository line. Without this, routing everything to env would satisfy the two above.
  expect_suites "control: a failing suite that does not read \$HOME stays on the repository line" \
    "$st_fail_root" 1 0 0 1 "beta: the vendored suite FAILED" "counted against THIS MACHINE" 0 0

  # ── discovery that reaches nothing is a FINDING, not an empty pass.
  st_empty_root="$st_dir/skills_empty"; mkdir -p "$st_empty_root"
  expect_suites "a discovered total of zero is a finding" "$st_empty_root" \
    1 0 0 1 "discovered total of zero"
  expect_suites "a missing skills root is a finding, not a clean run" "$st_dir/no-such-root" \
    1 0 0 1 "nothing to discover"
  # ── (row 5) THE FLOOR. `suites_found` is not the evidence-bearing quantity; `suites_with` is.
  #    Skills discovered but NOT ONE with a suite was a clean exit 0 — delete every vendored tests/
  #    directory and 392 published tests silently stop being evidence with nothing saying so.
  st_floor_root="$st_dir/skills_floor"
  mk_skill "$st_floor_root" gamma; mk_skill "$st_floor_root" delta
  expect_suites "skills discovered but NOT ONE with a suite is a finding, not a clean pass" \
    "$st_floor_root" 1 2 0 1 "NOT ONE has a test suite"

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
# The interpreter-provenance line is emitted by `check_vendored_suites` itself, not here, so that
# --self-test constrains it. It was at this call site and therefore deletable with the suite green.
#
# git IS A DECLARED PREREQUISITE OF THESE SUITES, and the first pass cleared this stop condition on
# evidence that did not bear on it: `grep -L unittest` proves each file IMPORTS unittest and says
# nothing about external binaries. Measured properly, the vendored progressive-disclosure suite has
# 19 `subprocess.run(["git", ...], check=True)` call sites with no guard, so on a machine without git
# those tests raise and the suite goes red. Absence is reported as a MACHINE fact, before the suites
# run, so a red suite is not the first thing that tells you.
if ! command -v git >/dev/null 2>&1; then
  SCOPE="env"
  note "git is NOT on PATH — it is a required prerequisite of the vendored suites (19 unguarded \`git\` subprocess call sites), so the failures reported below are attributable to this machine, not to the vendored tree"
  SCOPE="repo"
fi
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
# Each line wears its own could-not-run tally. The previous version attributed the whole tally to
# the repository line with a note saying to split it if a machine-scope check ever grew one; a
# vendored suite whose sources read $HOME now routes there, so it has.
verdict_line "this repository — vendored tree" "$repo_fail" "$repo_warn" "$repo_skip" "$repo_cnr"
verdict_line "this machine    — installed layer" "$env_fail" "$env_warn" "$env_skip" "$env_cnr"

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
