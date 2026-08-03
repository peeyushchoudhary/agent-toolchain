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
# WHAT RAISES 2 TODAY, STATED AS A FACT ABOUT THIS FILE RATHER THAN AS A PRINCIPLE — AND THE FACT IS
# COUNTED RATHER THAN ASSERTED, BECAUSE THIS PARAGRAPH HAS NOW BEEN WRONG TWICE. `cnr` is called
# from SEVEN places in TWO subsystems: five in the vendored-suite path (`run_one_suite` and
# `check_vendored_suites`), and TWO in `check_installer_agrees`, where the installer subprocess this
# gate executes did not get far enough to produce a set to compare — one for a not-run whose cause
# this gate MEASURED and charged to the machine, one for a timeout, whose cause it cannot measure and
# therefore attributes to neither line. So 2 means what it always meant — something that had to run
# could not run at all — and today that something is a vendored skill suite that produced no test
# result, OR that installer subprocess.
#
# THE SENTENCE ABOVE SAID "EXACTLY ONE PLACE" FOR ONE COMMIT AFTER IT STOPPED BEING TRUE: the change
# that added the installer check added the sixth call site and left this paragraph standing, which
# is the same stale-second-copy defect the paragraph below this one is entirely about. So the number
# is PINNED — `--self-test` counts `^\s*cnr ` call sites in this file against a literal, the same
# shape as the `UNMIGRATED-CNR` assertions below. An eighth `cnr` is a red suite rather than a false
# header, and the pin did its job the very next round: splitting the timeout out of the machine arm
# added the seventh site and the suite went red until this paragraph and the literal moved together. WHAT IS PINNED IS THE COUNT, NOT THE PROSE: the assertion cannot tell you that the new
# site is in a third subsystem, so read the sites, not the number.
#
# An earlier version of this comment also justified the narrowness by claiming every other `skip` in
# the file is a check "deliberately NOT ATTEMPTED". That is false, and the next maintainer acting on
# it would mis-route. Some skips are ATTEMPTED AND PRODUCED NO RESULT — the file's own definition of
# could-not-run — and remain UNMIGRATED, each exiting 0.
#
# THAT SET IS NOT ENUMERATED HERE, AND THE ABSENCE OF A LIST IS THE FIX. It WAS enumerated, as a
# closed list of four, and the commit that wrote the list ADDED A FIFTH — so the enumeration was
# stale one commit after being written, for the second time. A prose list of call sites is a second
# copy of the truth and it drifts exactly like every other second copy this file has removed. The
# sites are tagged at the site instead, and the list is DERIVED:
#
#     grep -n 'UNMIGRATED-CNR:' install/verify.sh
#
# One copy instead of two, and `--self-test` asserts three things: that the marker convention still
# exists, that this recipe still appears in THIS header, and that EVERY tagged line is immediately
# followed by the `skip` call it claims to describe. Deleting either side of the derivation, or
# tagging a branch that does anything else, is a red suite rather than a silently stale comment.
#
# THE THIRD ASSERTION EXISTS BECAUSE THE DERIVATION WAS WRONG ON 3 OF 7 ENTRIES ON THE COMMIT THAT
# INTRODUCED IT, and the first two could not see it: they count markers and cannot tell a correct
# tag from an incorrect one. One tag sat on a branch that calls `cnr` and exits 2 — already
# migrated, both halves of the marker false — and two sat directly beneath comments arguing the
# opposite conclusion, in the repository-scope suite runner rather than the section this
# justification names. MOVING A LIST FROM PROSE INTO GREP-ABLE MARKERS RELOCATES THE FALSIFIABLE
# CLAIM; IT DOES NOT CHECK IT. The `skip`-adjacency assertion is the cheap half of the check that
# can be mechanised, and it is what catches all three.
#
# WHAT IS STILL NOT GUARANTEED, stated because the wording before this one ("kept current by being
# the thing itself") claimed a guarantee twice over. The derivation is only as complete as the
# tagging — a new unmigrated skip added WITHOUT a marker is absent from the list and nothing goes
# red. And adjacency proves the tagged site is a `skip` exiting 0; it cannot prove the skip is
# LEGACY rather than deliberate, which is the judgement that was got wrong. THE DERIVATION IS
# ANNOTATION-DEPENDENT: read the branch, not the tag. Better odds than prose, in both directions,
# and not a substitute for either.
# The tagged sites are left as skips because migrating them changes exit behaviour in the installed
# and payload-rendering layers, which no card has authorised, not because they are a different kind
# of thing — and NOT every skip in those layers is tagged. What IS true, and is
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

# A FIFTH TALLY, AND IT EXISTS BECAUSE THE ROUTING ABOVE CREATED A NEW SILENCE. Moving a
# $HOME-reaching suite's findings to the machine line is right — one operand is $HOME — but the
# routing as first written moved them and left the REPOSITORY line saying nothing at all. A run with
# three real failures in a vendored suite printed
#   PASS this repository — vendored tree — no failures in what ran, but 4 check(s) did NOT run
# BYTE-IDENTICAL to a run in which every suite passed cleanly, and identical again to a run in which
# someone had broken a vendored script outright and put 294 tests red. That is this file's own
# opening rule at the top — "a green machine has repeatedly masked a broken repository" — in mirror
# image: the repository line masking itself by pointing at the machine.
#
# So the repository line carries a count of what was taken off it. NOT a failure and not a skip:
# those buckets belong to the scope that owns the finding, and double-counting would make the two
# verdicts overlap again. It is a marker saying THIS LINE IS INCOMPLETE AND HERE IS BY HOW MUCH.
#
# ONLY FINDINGS COUNT, NOT SUITES. A $HOME-reaching suite that PASSES had nothing to attribute: it
# ran from the vendored location and produced positive evidence about the tree, and the repository
# line's "no failures in what ran" remains true and complete for it. What makes that sentence
# dishonest is a finding that existed and went somewhere else.
#
# AND A COULD-NOT-RUN IS SUCH A FINDING, WHICH IT WAS NOT ALLOWED TO BE FOR ONE COMMIT. The second
# contributor is `check_installer_agrees`: a REPOSITORY-scope check whose subprocess could not be
# completed for a reason belonging to the machine. The first version routed the whole not-run to
# `env` and incremented nothing here, so five repository checks did not run while the repository
# line said four — byte-identical to a clean run again, the exact silence this counter was created
# for, and the "the run as a whole is still distinguishable" defence had already been considered and
# rejected three paragraphs up. The finding stays on the machine line, where its cause is; the
# repository line carries the marker saying it is short by one. Hence the tail's wording is about
# CHECKS AND FINDINGS, not about suites — see `verdict_line`.
repo_attributed_out=0

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

# verdict_line WHAT FAILS WARNS SKIPS [CNRS] [ATTRIBUTED_OUT] — renders one scope's verdict.
#
# DEFINED HERE, BESIDE `exit_arm`, AND FOR THE SAME REASON. It lived at the bottom of the file, below
# the `--self-test` block, so the self-test could not call it at all — the rendered verdict was the
# one thing this script's own suite could never see, while being the one thing every reader of the
# script actually reads. The counters were asserted and the sentence they produce was not.
#
# A scope with no failures but with skipped checks did NOT establish that its tree is intact — it
# established that nothing it managed to look at was broken. Those are different sentences and the
# verdict says whichever one is true, because "intact" over an unrun check is the same class of
# overclaim as "mirrors agree" over a discarded finding.
verdict_line() {
  local what="$1" fails="$2" warns="$3" skips="$4" cnrs="${5:-0}" away="${6:-0}" tail=""
  # WHAT WAS TAKEN OFF THIS LINE, ON THIS LINE. Appended to every arm rather than only to the PASS
  # arms: a line that failed for one reason and had a second reason attributed away is just as
  # incomplete as a passing one, and an operator reading FAIL should still learn that the count in
  # front of them is not the whole story. See `repo_attributed_out`.
  if [ "$away" -ne 0 ]; then
    # WORDING GENERALISED FROM "vendored suite finding(s)", which was accurate when `run_one_suite`
    # was the only contributor and became a second false second-copy the moment
    # `check_installer_agrees` became the second. Two shapes reach here now — a suite finding whose
    # operand is $HOME, and a repository-scope check whose subprocess could not be completed for a
    # machine reason — and the sentence has to cover both without naming either wrongly.
    tail=$(printf '; and %s finding(s) or not-run check(s) from this scope were attributed to THIS MACHINE, so they are not evidence about this tree and are not counted above' "$away")
  fi
  if [ "$cnrs" -ne 0 ]; then
    # Same ordering as the exit code: a scope that could not run something does not know what that
    # something would have said, so it may not lead with PASS or with FAIL.
    printf '  \033[35mCOULD NOT RUN\033[0m  %s — %s check(s) could not be executed at all; %s problem(s), %s warning(s), %s not run in total%s\n' \
      "$what" "$cnrs" "$fails" "$warns" "$skips" "$tail"
  elif [ "$fails" -ne 0 ]; then
    printf '  \033[31mFAIL\033[0m  %s — %s problem(s), %s warning(s), %s not run%s\n' \
      "$what" "$fails" "$warns" "$skips" "$tail"
  elif [ "$skips" -ne 0 ]; then
    printf '  \033[33mPASS\033[0m  %s — no failures in what ran, but %s check(s) did NOT run (%s warning(s))%s\n' \
      "$what" "$skips" "$warns" "$tail"
  elif [ "$away" -ne 0 ]; then
    # A clean line that nonetheless had findings taken off it may not say "every check ran and
    # passed". Every check did not pass; some of them passed their verdict to the other line.
    printf '  \033[33mPASS\033[0m  %s — no failures in what ran (%s warning(s))%s\n' "$what" "$warns" "$tail"
  else
    printf '  \033[32mPASS\033[0m  %s — every check ran and passed (%s warning(s))\n' "$what" "$warns"
  fi
}

# render_verdicts — the two verdict lines, WITH THE COUNTERS THEY READ, as one testable unit.
#
# TAKES NO ARGUMENTS ON PURPOSE, AND THAT IS THE WHOLE POINT OF EXTRACTING IT. Moving `verdict_line`
# above the `--self-test` block made the FUNCTION testable and left its INVOCATION as the one thing
# the suite could not see — the same defect one level up, and it survived a round. `--self-test`
# exits before the verdict block at the bottom of the file ever runs, so a call site down there is
# unreachable from every assertion; the three assertions that call `verdict_line` pass LITERALS, and
# `expect_suites` pins the counters, but nothing pinned WHICH COUNTER REACHES WHICH PARAMETER.
# Measured, on the version that had the two calls inline: changing `"$repo_cnr"` to `0`, or to
# `"$env_cnr"`, left the suite at 70 of 70 while the repository line went back to being byte-identical
# to a green run — F1 restored in full under a green suite.
#
# So the join is inside a function that reads the globals itself, and `--self-test` sets those globals
# to nine pairwise-distinct fixture values and asserts the two rendered lines. Any swap between two
# counters, any constant substituted for one, and any label swapped between the lines changes a
# number in the output. A parameterised `render_verdicts A B C …` would NOT do this: it would move the
# unpinned join to its own call site and buy nothing.
render_verdicts() {
  verdict_line "this repository — vendored tree" \
    "$repo_fail" "$repo_warn" "$repo_skip" "$repo_cnr" "$repo_attributed_out"
  # The machine line's `away` is a literal 0 and stays one: attribution runs in one direction only.
  # `run_one_suite` and `check_installer_agrees` move findings OFF the repository line and ONTO this
  # one, so this line is never the incomplete one, and there is no counter to pass here that would
  # not be a fiction.
  verdict_line "this machine    — installed layer" \
    "$env_fail" "$env_warn" "$env_skip" "$env_cnr" 0
}

# render_summary — the overall line, and it RETURNS the exit code the run will use.
#
# Extracted for the same reason and by the same rule as `exit_arm` before it: the summary sentence and
# the exit code are one claim, and asserting them apart lets a summary that says PASS sit above an
# `exit 1`. The totals are computed HERE rather than at the call site, because "which counters are
# summed into the total" is exactly the kind of join finding 1 was about — `total_fail` reaching only
# `repo_fail` would have printed a clean summary over a failing machine with nothing to catch it.
render_summary() {
  local tf=$((repo_fail + env_fail)) tw=$((repo_warn + env_warn)) ts=$((repo_skip + env_skip)) arm
  arm=$(exit_arm "$tf" "$could_not_run")
  case "$arm" in
    2)
      echo "COULD NOT RUN — $could_not_run check(s) could not be executed, so this report cannot be trusted to be complete ($tf problem(s), $tw warning(s), $ts check(s) not run). Exit 2 outranks exit 1 on purpose: whether you can trust the report is answered before whether it found anything."
      ;;
    1) echo "FAIL — $tf problem(s), $tw warning(s), $ts check(s) not run" ;;
    *) echo "PASS — $tw warning(s) and $ts check(s) not run, none fatal" ;;
  esac
  return "$arm"
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
        # UNMIGRATED-CNR: attempted and produced no result, still exiting 0. See the header.
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
suites_tests=0; suites_skipevents=0; suites_exec_lo=0

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
# Caught by running the gate under a PATH that did not resolve `find`.
#
# has_test_file DIR — THREE OUTCOMES IN THE RETURN CODE: 0 a suite was found, 1 there is none, 2 a
# directory in the walk COULD NOT BE OPENED so the answer is unknown.
#
# THE THIRD OUTCOME IS WHY THIS IS NOT A PREDICATE, AND IT IS THE PREVIOUS ROUND'S FIX ONE LEVEL
# DOWN. A boolean version cannot distinguish "I looked and there is nothing" from "I could not
# look", so `suite_dir_state` tested `-r`/`-x` on `<skill>/tests` itself to recover the difference at
# the top of the walk — and only at the top. `tests/` readable, `tests/unit/` at mode 000 holding the
# only `test*.py`, and the unreadable subdirectory silently contributed no match: `none`, the same
# false `NOT TESTED HERE — no vendored test suite` sentence over a suite sitting right there, with no
# finding and no floor. The state now travels out of the recursion instead of being probed beside it.
#
# A MATCH OUTRANKS AN UNREADABLE SIBLING, deliberately. If any readable part of the tree holds a
# suite, there is a suite to run and the run itself is the evidence; unknown-ness elsewhere only
# decides the answer when nothing was found.
#
# `test*.py` and recursive, matching what `unittest discover` collects, NOT the old
# `tests/test_*.py` non-recursive glob — which called `tests/unit/test_x.py` and `tests/tests_x.py`
# no suite at all. Over-matching is the safe direction: a directory that matches and then discovers
# nothing is already a loud `bad`, whereas under-matching is a silent skip.
has_test_file() {
  local d="$1" f rc=1 sub
  { [ -r "$d" ] && [ -x "$d" ]; } || return 2
  for f in "$d"/test*.py; do [ -f "$f" ] && return 0; done
  for f in "$d"/*/; do
    [ -d "${f%/}" ] || continue
    has_test_file "${f%/}"; sub=$?
    [ "$sub" -eq 0 ] && return 0
    [ "$sub" -eq 2 ] && rc=2
  done
  return "$rc"
}

# suite_dir_state SKILL_DIR — echoes one of: none | unreadable | suite.
#
# THREE STATES, BECAUSE TWO CONFLATED "THE SUITE IS ABSENT" WITH "I COULD NOT LOOK". The predicate
# used to be `[ -d tests ] && has_test_file tests`, and a `tests/` directory that exists but cannot
# be opened fails the second half exactly as a missing one does — producing
# `NOT TESTED HERE — no vendored test suite at <name>/tests` over a suite sitting right there. A
# false sentence, counted as a not-run, with no finding attached and the floor guard silent because
# other skills did have suites. Absence of evidence reported as evidence of absence is this card's
# defect class, so the unreadable case is now its own state and reaches `cnr`.
#
# THE UNREADABLE TEST IS NOW `has_test_file`'S, AT EVERY DEPTH, rather than an `-r`/`-x` probe on the
# top directory only. `tests/` itself unreadable still yields `unreadable` — the walk returns 2 on its
# first step — and so now does an unreadable directory anywhere beneath it.
suite_dir_state() {
  local t="$1/tests"
  [ -d "$t" ] || { echo none; return; }
  has_test_file "$t"
  case $? in
    0) echo suite ;;
    2) echo unreadable ;;
    *) echo none ;;
  esac
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
#
# THE RESULT LINE IS ANCHORED TO THE RUNNER, NOT TO THE END OF THE STREAM, and the difference is not
# theoretical. The first version of this parse read the LAST NON-EMPTY LINE of merged stdout+stderr
# and called it "unittest's trailing line". They are the same line only while nothing reaches either
# stream after the summary. `unittest` writes its summary to STDERR, which is line-buffered; a test's
# own `print` goes to STDOUT, which is BLOCK-buffered because `$( … 2>&1 )` is a pipe, so it flushes
# at interpreter exit — AFTER `OK (skipped=K)`. MEASURED, not reasoned: a two-test suite with one
# `print` and one skip emits
#     Ran 2 tests in 0.000s / (blank) / OK (skipped=1) / trailing stdout from the test
# and the old parse took the last line, matched no `skipped=`, and yielded sk=0 — printing
# "2 of 2 vendored test(s) passed" over a test that never executed an assertion. That is exactly the
# absorption this function was written to remove, one layer in. Any shutdown-time stderr
# (`ResourceWarning`, `Exception ignored in:`) does the same.
#
# So the result line is the FIRST non-empty line matching a runner result shape that appears AFTER
# `Ran N test…`. First-after-Ran, not last-matching: a test that prints the word `OK` before the
# summary is ignored because `Ran` has not been seen, and one that prints it after is ignored because
# the real result line was already captured.
#
# AND A MISSING RESULT LINE IS `cnr`, NEVER sk=0. "Ran a suite and found no recognisable result" is
# not evidence that there were no skips; it is the absence of evidence, which is this file's
# definition of could-not-run. The old code had no such state, so an unrecognised shape degraded
# silently into a clean pass.
run_one_suite() {
  local name="$1" dir="$2" out rc ran="" ln tail_line="" first_line="" sk=0 exec_lo
  local home=0 saved_scope="$SCOPE" seen_ran=0 result_line="" ran_num=1 sk_num=1
  local env_f0=$env_fail env_s0=$env_skip env_w0=$env_warn
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
      "Ran "*" test"*)
        ran="${ln#Ran }"; ran="${ran%% *}"
        # A second `Ran` line means a second runner result in one stream; the later one wins, so the
        # captured result line is reset with it rather than kept from the earlier run.
        seen_ran=1; result_line=""
        ;;
      "OK"|"OK "*|"FAILED"|"FAILED "*|"NO TESTS RAN"|"NO TESTS RAN "*)
        [ "$seen_ran" -eq 1 ] && [ -z "$result_line" ] && result_line="$ln"
        ;;
    esac
  done <<< "$out"
  # The skip count lives in the RESULT line — `OK (skipped=10)`, or `FAILED (failures=1, skipped=2)`.
  # Pure bash, not sed/grep -o: the suites' failure output carries em dashes and macOS sed dies on
  # exactly that with "RE error: illegal byte sequence", so a parse of the result would become an
  # error message about the parse. The same trap is documented in --self-test below.
  case "$result_line" in
    *"skipped="*) sk="${result_line#*skipped=}"; sk="${sk%%[!0-9]*}"; sk="${sk:-0}" ;;
  esac
  # AND BOTH OPERANDS ARE VALIDATED FOR ARITHMETIC-SAFETY BEFORE ANY ARITHMETIC READS THEM, WHICH IS
  # NOT THE SAME PROPERTY AS DIGIT-NESS AND IS THE CORRECTION OF THIS COMMENT'S PREVIOUS CLAIM. It
  # said `sk` needed no guard because "`sk` is forced non-negative by the `%%[!0-9]*` strip above".
  # Non-negative is not what `$(( ))` requires. A LEADING ZERO IS BASE 8 IN BASH ARITHMETIC and both
  # operands could carry one, so the comment certified as safe the one operand left unprotected:
  #   * `Ran 08 tests` passed the all-digits guard (`[ 08 -eq 0 ]` is FALSE — `test` is base 10 — so
  #     it fell to the else arm), and then `$((ran - sk))` raised `08: value too great for base` and
  #     NEVER ASSIGNED `exec_lo`, which is `local` with no value. The next command reads it under
  #     `set -u`: the identical truncation measured for `Ran abc tests` below — no verdict section,
  #     exit 2, this script's could-not-run code worn by a gate that died.
  #   * `Ran 010 tests` is worse because it does not fail. It is VALID octal, so the per-suite
  #     sentence prints `010 of 010` while the aggregate silently gains 8.
  # So the guards below reject `0?*` as well as empty and non-digit: `0` is a value this parser
  # understands and has branches for, `08` and `010` are shapes it does not, and an unreadable count
  # is UNKNOWN, which is this file's could-not-run — reported and counted, not absorbed. `sk` gets
  # its own branch for the same reason `ran` has one: how many events were skipped being unreadable
  # is not the same fact as none having been.
  # `sk` is forced digits-only by the `%%[!0-9]*` strip above; `ran` is the first whitespace-
  # delimited word after `Ran `, taken verbatim from a stream this function's own comment (see the
  # status-character rejection in the else arm below) says a test can write anything into. Two
  # measured consequences of trusting it, both on bash 3.2 with `set -uo pipefail`:
  #   * `Ran -3 tests in 0.000s` / `OK (skipped=9)` passes every branch test, gives suites_tests=-3
  #     with exec_lo clamped to 0, and the summary prints `between 0 and -3 of -3` — an interval
  #     whose upper end is below its lower, from a comment that says that cannot happen.
  #   * `Ran abc tests` makes `[ "$ran" -eq 0 ]` print `integer expression expected` and fall to the
  #     else arm, where `$((ran - sk))` resolves `abc` as a VARIABLE NAME, hits `set -u`, and the
  #     shell exits mid-run. MEASURED against the real vendored tree with that stream: `abc: unbound
  #     variable`, NO verdict section rendered at all, and exit 2 — which is this script's own
  #     could-not-run code, so a caller reading only the status cannot tell a reported could-not-run
  #     from a gate that died before it had anything to report.
  # Neither is hypothetical enough to leave to a narrowed comment: the second is a TRUNCATION of the
  # gate wearing a legitimate exit code. Unparseable is UNKNOWN, and unknown is this file's
  # could-not-run — reported, counted, and reached by the summary line, which is what the fixed path
  # does with the same stream.
  case "$ran" in ''|*[!0-9]*|0?*) ran_num=0 ;; esac
  case "$sk"  in ''|*[!0-9]*|0?*) sk_num=0  ;; esac

  # $HOME-reaching suites: failures and could-not-runs are MACHINE facts. See the block comment.
  [ "$home" -eq 1 ] && SCOPE="env"

  if [ -z "$ran" ]; then
    suites_cnr=$((suites_cnr+1))
    cnr "$name: the vendored suite COULD NOT RUN — \`$SUITE_PY\` produced no test result (rc=$rc). No verdict about this suite exists either way. First output line: ${first_line:-(no output)}"
  elif [ "$ran_num" -eq 0 ]; then
    # A `Ran N test…` LINE WHOSE N IS NOT A NON-NEGATIVE INTEGER. Same disposition and same reason as
    # the missing-result-line branch below: a shape that was not understood does not contribute a
    # number to a summary claiming to describe what executed. Tested before every branch that does
    # arithmetic on `ran`, because the abort case aborts inside the arithmetic itself.
    # NOT AN UNMIGRATED SITE, AND IT CARRIED THE MARKER FOR ONE COMMIT. The marker says "attempted
    # and produced no result, STILL EXITING 0"; this branch calls `cnr` two lines down and therefore
    # exits 2, which the self-test pins. Both halves of the tag were false the moment it was pasted
    # here. See the tag-correctness assertion in --self-test, which now catches exactly this.
    suites_cnr=$((suites_cnr+1))
    cnr "$name: the vendored suite COULD NOT RUN — its summary reported a test count this parser cannot read as a non-negative integer (\`Ran $ran test…\`, rc=$rc), so how many tests ran is UNKNOWN and no arithmetic is done on it. No verdict about this suite exists either way. Last output line: ${tail_line:-(no output)}"
  elif [ -z "$result_line" ]; then
    # RAN, BUT PRODUCED NO RECOGNISABLE RESULT LINE. Nothing after `Ran $ran test…` matched
    # `OK…`/`FAILED…`/`NO TESTS RAN…`, so how many of those tests skipped is UNKNOWN — and unknown is
    # not zero. Reporting it as a pass with sk=0 is the absorption this whole function exists to
    # remove, so it is a could-not-run: attempted, produced no result. `ran` is deliberately NOT
    # accumulated into the test totals, because a parse that was not understood may not contribute a
    # number to a summary that claims to describe what executed.
    #
    # TESTED BEFORE `ran -eq 0` RATHER THAN AFTER IT, which is a change. `Ran 0 test…` with no result
    # line at all was previously a hard `bad` — a repository FAILURE asserted from a stream this
    # function admits it did not parse. Unknown is unknown at every value of N.
    suites_cnr=$((suites_cnr+1))
    cnr "$name: the vendored suite ran $ran test(s) but produced NO RECOGNISABLE RESULT LINE (rc=$rc), so how many of them SKIPPED is unknown — and unknown is not zero. No verdict about this suite exists either way. Last output line: ${tail_line:-(no output)}"
  elif [ "$sk_num" -eq 0 ]; then
    # A `skipped=` FIELD WHOSE VALUE THIS PARSER CANNOT READ AS A NON-NEGATIVE BASE-10 INTEGER.
    # Placed here, above every branch that compares or accumulates `sk`, for the same reason the
    # `ran` guard is placed above every branch that reads `ran`: the abort case aborts inside the
    # arithmetic itself, so a check after it is a check that never runs. Same disposition as the
    # missing-result-line branch above and for the same sentence — how many of these tests skipped
    # is UNKNOWN, and unknown is not zero.
    suites_cnr=$((suites_cnr+1))
    cnr "$name: the vendored suite COULD NOT RUN — its result line reported a skip count this parser cannot read as a non-negative integer (\`${result_line}\`, rc=$rc), so how many of its $ran test(s) skipped is UNKNOWN and no arithmetic is done on it. No verdict about this suite exists either way. Last output line: ${tail_line:-(no output)}"
  elif [ "$ran" -eq 0 ] && [ "$sk" -gt 0 ]; then
    # `Ran 0 tests` + `OK (skipped=N)` — A CLASS- OR MODULE-LEVEL GUARD FIRED, AND IT IS NOT A
    # REPOSITORY FAILURE. MEASURED on CPython 3.14.6, not reasoned from the source: a
    # `setUpClass`/`setUpModule` raising `unittest.SkipTest` emits
    #     s / ----- / Ran 0 tests in 0.000s / (blank) / OK (skipped=1)      rc=0
    # for a class holding two tests. `TestSuite._addClassOrModuleLevelException` records the skip
    # against an `_ErrorHolder` WITHOUT calling `startTest`, so `testsRun` never moves and `skipped=`
    # counts GUARDS, not tests. It is `Ran 0` and a clean result at the same time.
    #
    # This branch used to fall into the `bad` below: a HARD REPOSITORY FAILURE, exit 1, for a
    # $HOME-keyed machine guard — while discarding a result line that said `OK (skipped=1)`. That is
    # this card's own defect class, one branch over, and worse than the silence F1 was about: not a
    # verdict that says too little but one that says the opposite of what it read.
    #
    # Treated as the whole suite NOT TESTED HERE, exactly like the all-skipped branch below, and in
    # the scope the $HOME routing selected — a guard that fired is not a fact about the tree. SCOPE is
    # therefore NOT restored here, unlike the genuine ran-0 branch beneath it.
    #
    # NOTHING IS ADDED TO THE TEST TOTALS. `sk` here counts guards and `ran` is 0; feeding either into
    # the test totals would print `-1 of 0` in the test-level summary, a filtered count whose total it
    # contradicts. THAT GUARANTEE IS THIS BRANCH'S ONLY BECAUSE `ran -eq 0`; the general case is the
    # `else` arm below, and an earlier version of this comment claimed the whole function while sitting
    # over a branch that still did `execd=$((ran - sk))`. See the SKIP EVENTS block above that arm.
    #
    # BUT THE SKIP-EVENT TOTAL IS NOT A TEST TOTAL, AND THIS BRANCH DOES FEED IT. `suites_skipevents`
    # was fed only from the `else` arm, which excluded the branch that is the PARADIGM CASE of "an
    # event that is not a test" — the entire reason the counter exists in its own unit. A run holding
    # one method-skip suite and one guard-only suite reported `1 skip event(s) were reported` over two
    # events, and the sentence prints that number with no denominator, so a reader has nothing to
    # check it against. Adding it here leaves the guarantee above untouched: `suites_skipevents` is
    # never a numerator or a denominator over tests, and the summary never divides by it.
    #
    # AND IT IS NOT AN UNMIGRATED COULD-NOT-RUN, THOUGH IT CARRIED THAT MARKER FOR ONE COMMIT —
    # directly beneath the paragraphs above, which argue the opposite conclusion at length. This
    # branch HAS a result and reports it (`OK (skipped=N)`); it is a deliberate skip in the
    # repository-scope runner, not a legacy site awaiting migration in the machine section the
    # header's justification names.
    suites_skipevents=$((suites_skipevents+sk))
    suites_vacuous=$((suites_vacuous+1))
    skip "$name: NOT TESTED HERE — discovery ran 0 test(s) because $sk class- or module-level guard(s) raised SkipTest before any test started, so 0 assertions executed. \`${result_line}\` is not evidence, and it is not a repository failure either — these guards are keyed on machine state"
  elif [ "$ran" -eq 0 ]; then
    # Discovery reached the suite, produced a recognisable result, and that result says nothing ran
    # and nothing was skipped. That is a fact about the tree, so it is reported in the scope in force
    # before the $HOME routing above — restored first, deliberately.
    SCOPE="$saved_scope"
    suites_fail=$((suites_fail+1))
    bad "$name: the vendored suite has a tests/ directory but discovery ran 0 tests and skipped none (\`${result_line}\`) — a suite that runs nothing is not a passing suite"
  else
    # ── SKIP EVENTS, NOT SKIPPED TESTS. This arm is `ran > 0` with a recognisable result line, and it
    # is where `skipped=` and `Ran N` are combined. THEY ARE NOT IN THE SAME UNIT.
    #
    # `skipped=` counts SKIP EVENTS. A method-level skip (`@unittest.skip`, `self.skipTest`) is one
    # event AND one test inside `Ran N`, because `startTest` increments `testsRun` before the skip is
    # recorded. A class- or module-level guard is one event and ZERO tests, because
    # `_addClassOrModuleLevelException` records it against an `_ErrorHolder` without `startTest` — the
    # measurement the `ran -eq 0` branch above is built on. So `sk = method_skips + guards`, and
    # `ran - sk` is `executed - guards`, which is NOT the number of tests that executed an assertion.
    #
    # WHAT THAT COST, MEASURED on CPython 3.14.6 with the previous `execd=$((ran - sk))`. One guarded
    # class over two tests plus one ordinary passing test emits `Ran 1 test` / `OK (skipped=1)`:
    # `execd` came out 0, the arm below reported "all 1 vendored test(s) were SKIPPED … 0 of 1
    # executed", and a real pass became a counted skip. With TWO guarded classes it emits `Ran 1 test`
    # / `OK (skipped=2)`: `execd` came out -1 and the test-level summary printed
    # `tests: -1 of 1 … 2 of 1 were SKIPPED` — a negative filtered count and a numerator above its own
    # total, which is precisely the shape the `ran -eq 0` branch above was written to avoid.
    #
    # THE SPLIT CANNOT BE RECOVERED FROM THIS STREAM, so the arithmetic stops pretending it can.
    # Two ways to recover it were considered and rejected:
    #   * counting the status characters (`s` / `.` / `F`) — their total is `ran + guards`, so the
    #     split falls out. Rejected: that line carries no delimiter, and anything a test writes to
    #     either stream lands inside it. This function has already been bitten twice by a freeform
    #     parse of runner output (the trailing-emission defect, and the last-line skip parse).
    #   * replacing `-m unittest discover` with a bespoke runner that prints `testsRun`, `len(skipped)`
    #     and how many of those are `_ErrorHolder`. EXACT, and the right long-term answer — but it
    #     changes how every suite is invoked and what `reproduce with:` means, which is a card of its
    #     own, not a line here.
    #
    # SO ONLY BOUNDS ARE PRINTED, AND NEVER A CLAMPED POINT. `method_skips <= min(sk, ran)`, therefore
    # `executed = ran - method_skips` lies in `[max(0, ran - sk), ran]`. `exec_lo` is that lower bound.
    # Clamping it at 0 is not hiding the negative: the negative was never a count of anything, and
    # whenever the interval is wider than a point the output SAYS "between X and Y" rather than
    # picking an end. The interval collapses to a point exactly when `sk == 0` — which is every
    # vendored suite on this tree ON A MACHINE WHERE NONE OF ITS `$HOME`- AND TOOL-KEYED GUARDS FIRE,
    # not a property of the tree. `sk == 0` is a machine fact and this file's header exists to punish
    # exactly that conflation. MEASURED on this tree rather than reasoned: the progressive-disclosure
    # suite carries four CLASS-level `@unittest.skipIf(REAL_GIT is None, …)` decorators, and a
    # class-level skip is NOT the `_ErrorHolder` path the `ran -eq 0` branch above is built on —
    # `TestCase.run` calls `startTest` before it tests `__unittest_skip__`, so each guarded test is
    # counted inside `Ran N`. That suite run with `git` off PATH emits `Ran 294 tests` /
    # `skipped=11`, giving `sk=11` and `exec_lo=283`, and this arm takes the INTERVAL form. So the
    # ordinary sentence is unchanged THERE, and correctly different elsewhere.
    suites_tests=$((suites_tests+ran))
    suites_skipevents=$((suites_skipevents+sk))
    exec_lo=$((ran - sk)); [ "$exec_lo" -lt 0 ] && exec_lo=0
    suites_exec_lo=$((suites_exec_lo+exec_lo))
    if [ "$rc" -ne 0 ]; then
      suites_fail=$((suites_fail+1))
      bad "$name: the vendored suite FAILED — $ran test(s) ran and between $exec_lo and $ran of them executed an assertion ($sk skip event(s) reported), rc=$rc, ${result_line:-(no summary line)}$([ "$home" -eq 1 ] && printf ' [counted against THIS MACHINE, not this repository: this suite reads $HOME, so its result is not a property of the vendored tree alone]')"
    elif [ "$exec_lo" -le 0 ]; then
      # `sk >= ran`: NOT ONE test can be SHOWN to have executed an assertion. Under the all-skipped
      # reading nothing did; under the guard reading up to $ran of them did and passed. The two are
      # indistinguishable here, so the conservative reading is taken and SAID: this suite is not
      # evidence, which is true either way, rather than "0 executed", which is true only one way.
      # It is a skip and not a could-not-run because a guard that fired is a machine fact with a
      # clean result line, not an attempt that produced nothing — and exit 2 over a decorator-skipped
      # suite would be a false alarm on every machine those guards are keyed on.
      # THAT IS ALSO WHY THE UNMIGRATED-CNR MARKER THAT SAT ON THIS LINE FOR ONE COMMIT WAS WRONG:
      # the three lines above it are the argument that this is NOT an attempt that produced nothing,
      # and it is in the repository-scope runner rather than the machine section the header's
      # justification names. The aggregate case — every suite in the corpus landing here — is a
      # finding, and it is made once, by the floor, not per suite.
      suites_vacuous=$((suites_vacuous+1))
      skip "$name: NOT TESTED HERE — $ran vendored test(s) ran and $sk skip event(s) were reported, so 0 of $ran can be SHOWN to have executed an assertion (\`${result_line:-?}\`). A skip event is one test OR one whole guarded class and a runner summary cannot tell them apart, so between 0 and $ran of $ran may in fact have passed; neither reading makes this suite evidence"
    elif [ "$exec_lo" -eq "$ran" ]; then
      # `sk == 0`: the interval is a point, and the sentence is the exact one it has always been.
      suites_pass=$((suites_pass+1))
      ok "$name: $ran of $ran vendored test(s) passed"
    else
      suites_pass=$((suites_pass+1))
      ok "$name: between $exec_lo and $ran of $ran vendored test(s) passed"
      # Surfaced as its own counted skip, never folded into the sentence above. This is the row that
      # made the first green machine-dependent without saying so. Stated as an interval for the same
      # reason: `sk` of them is the upper bound, not the count.
      skip "$name: between 0 and $sk of $ran vendored test(s) NOT TESTED HERE — the suite's own guards reported $sk skip event(s) (\`${result_line:-?}\`), typically keyed on \$HOME state this repository does not own; a skip event is one test OR one whole guarded class, so at least $exec_lo of $ran did execute an assertion"
    fi
  fi

  # WHAT THE $HOME ROUTING TOOK OFF THE REPOSITORY LINE, COUNTED. Derived from the counters rather
  # than incremented at each of the branches above, so a branch added later is covered without anyone
  # remembering to add a line: whatever actually landed in `env` while this suite held the routing,
  # having entered in `repo` scope, is what was attributed away. The `ran -eq 0` branch restores SCOPE
  # before it reports, so it contributes nothing here — correctly, since it is a tree fact that stayed
  # on the tree's line.
  #
  # ALL THREE BUCKETS, WHICH IT WAS NOT. The sum was `fail + skip` and `env_warn` was simply absent,
  # so the "covered without anyone remembering" claim above was false for the one bucket it omitted:
  # a future branch here calling `note` would move its finding to the machine line and leave the
  # repository line saying nothing — F1 verbatim, in the one place F1's fix does not reach. There is
  # no branch in this function that calls `note` today, so the warn term is zero on every run and no
  # assertion can pin it above zero; it is here because a derivation that omits a bucket is not a
  # derivation, and the omission is exactly the kind that is noticed only after it has bitten.
  if [ "$home" -eq 1 ] && [ "$saved_scope" = "repo" ]; then
    repo_attributed_out=$(( repo_attributed_out \
      + (env_fail - env_f0) + (env_skip - env_s0) + (env_warn - env_w0) ))
  fi
  SCOPE="$saved_scope"
}

# ── the published-skill roster, and the two checks that read it ──────────────────────────────────
#
# THE DECLARATION IS `install/skills/.gitignore`, and it is read here rather than re-listed. That
# file is this repository's own statement of what install/skills/ publishes (see docs/README.md,
# "What is published, and what is not"): an allowlist that ignores everything at the top level and
# re-includes each published skill by a `!/name` line. TC-51 found the presence loop below
# hardcoding four of the six names, disagreeing with install.sh's own separate hardcoded five, and
# nothing able to notice either.
#
# WHY A READER HERE AND NOT `git check-ignore`, WHICH IS THE AUTHORITY 30 LINES BELOW. MEASURED on
# git 2.50.1: `git check-ignore` consults the index and REFUSES TO CALL A TRACKED PATH IGNORED.
# Every published skill is tracked, so deleting a skill's `!/` line does not change git's answer at
# all — a fixture with `!/beta` removed still reports `beta/` as not-ignored; only `--no-index`
# sees the change. git can therefore answer "should this UNTRACKED arrival be excluded from
# discovery", which is the only question check_vendored_suites asks it and the reason its comment
# about not writing a second parser is still true. It cannot answer "what does the declaration
# name", which is the question a presence check has to ask. So this is a reader, and it is strict.
#
# STRICT MEANS LOUD, NOT PERMISSIVE. gitignore negation syntax is larger than the `!/name` form
# this allowlist actually uses — `!name` without the slash and `!/name/` with a trailing one are
# both legal and both mean something this reader would get wrong. The previous `grep -E '^!/'`
# missed the first entirely (a published-and-gated skill silently dropped from the roster: TC-51's
# own defect, restored, at exit 0) and mangled the second into `name/`, which install.sh installs
# and this check then reports NOT installed. So one `if` decides what the strict form is, and the
# SAME `if` emits everything it rejects — the two modes are complementary by construction, and an
# entry cannot fall into the gap between two independently-written patterns.
skill_roster_scan() {
  awk -v mode="$2" '
    /^!/ {
      if ($0 ~ /^!\/[A-Za-z0-9._-]+$/ && $0 !~ /^!\/\.\.?$/) {
        if (mode == "names") print substr($0, 3)
      } else if (mode == "rejects") print
    }
  ' "$1" 2>/dev/null
}

# skill_roster DECL_DIR — the declared SKILL names, one per line.
#
# NOT EVERY ALLOWLIST ENTRY IS A SKILL: `!/.gitignore` and `!/README.md` are files that live beside
# the skills. The previous version excluded those two BY NAME, in both scripts — itself a hardcoded
# roster, of which entries are not skills, and one that fails on the next such file: declare
# `!/LICENSE`, commit `install/skills/LICENSE`, and the presence check hard-FAILS looking for
# `LICENSE/SKILL.md` on a correct repository. Filtered by TYPE instead: an entry that exists as a
# regular file in the declaration's own directory is not a skill directory. A declared name with
# NOTHING on disk stays in the roster on purpose — that is the missing-skill case this check exists
# to catch, and a filter keyed on the directory existing would delete the check along with the list.
skill_roster() {
  skill_roster_scan "$1/.gitignore" names | while IFS= read -r _e; do
    [ -n "$_e" ] || continue
    [ -f "$1/$_e" ] || printf '%s\n' "$_e"
  done
}

# check_skill_presence CHECK_ROOT DECL_DIR WHERE OWNS_DECL — every declared skill is present under
# CHECK_ROOT, and (when OWNS_DECL is 1) the declaration and the directory agree in BOTH directions
# and the declaration's own integrity is reported as a finding.
#
# TAKES ITS ROOTS AS ARGUMENTS FOR THE REASON check_vendored_suites DOES: `--self-test` exits ~1,500
# lines above the two production call sites, so anything written inline there is unreachable from
# every assertion in this file. That is not a hypothetical — the first version of this check was
# written inline at both call sites, and MEASURED, two mutations survived the suite at 108 of 108
# green: replacing the roster derivation with two hardcoded names, and reverting install.sh to its
# stale five-name literal. `exit_arm`, `verdict_line` and `render_verdicts` were each hoisted here
# for exactly this, each after the same defect got through a review.
#
# CROSSCHECK EXISTS BECAUSE "N of M" IS ONLY EVIDENCE WHEN M IS MEASURED INDEPENDENTLY OF N. The
# first version derived both from the roster, so the total could not disagree with the count: delete
# one `!/` line from the declaration and both scripts printed a clean `5 of 5` full house, exit 0,
# on a tree where a published skill had silently stopped being installed and checked. The honest
# denominator is the DIRECTORY. So repository scope counts `CHECK_ROOT/*/SKILL.md` as well, and both
# disagreements are findings: declared-with-no-directory (the `want_file` below) and
# directory-with-no-declaration.
#
# OWNS_DECL IS 0 FOR THE MACHINE SCOPE, and that is not a weaker check, it is the only correct one:
# `~/.claude/skills` legitimately holds skills this repository never published (graphify installs
# itself there via `uv tool`), so its directory count is not a denominator for anything. The
# roster's own integrity is established once, in repository scope, against the tree that owns it.
#
# WHICH IS WHY ONE FLAG GOVERNS BOTH THE CROSS-CHECK AND THE INTEGRITY REPORTING, and why it is
# named for the tree rather than for one of the two behaviours. Three findings below — a missing
# declaration, an uninterpretable allowlist line, an allowlist that names nothing — are facts about
# `install/skills/.gitignore`, a REPOSITORY file, and this function is called twice against that one
# file: once for the repository tree and once for `~/.claude/skills`. Firing them in both scopes
# made ONE syntax error print TWO problems and charged the second to the MACHINE, which is this
# file's cardinal rule inverted. `check_installer_agrees` already refuses to double-count exactly
# this fact ("Already reported by check_skill_presence"); the same principle now holds here. Both
# behaviours answer the same question — is this the tree that owns the declaration — so they take
# the same flag rather than a second one that could only ever be set to the same value.
check_skill_presence() {
  local check_root="$1" decl_dir="$2" where="$3" owns_decl="$4"
  local decl="$decl_dir/.gitignore" roster rejects s d dn found
  local declared=0 present=0 dirs=0 undeclared=0

  if [ ! -f "$decl" ]; then
    if [ "$owns_decl" -eq 1 ]; then
      bad "$where: the publication declaration $decl_dir/.gitignore is missing, so there is nothing to check presence AGAINST — this is not an empty pass"
    else
      ctx "$where: presence not checked — $decl_dir/.gitignore is missing (reported against the repository, which owns that file; not counted twice)"
    fi
    return
  fi
  # AN ENTRY THIS READER CANNOT INTERPRET IS A FAILURE, NOT AN OMISSION. Silently skipping it is how
  # a published skill leaves the roster without anyone finding out, which is the defect above.
  rejects=$(skill_roster_scan "$decl" rejects)
  if [ -n "$rejects" ]; then
    while IFS= read -r s; do
      [ -n "$s" ] || continue
      if [ "$owns_decl" -eq 1 ]; then
        bad "$where: cannot interpret the allowlist line \`$s\` in $decl_dir/.gitignore — this check reads a strict \`!/name\` form only, and refuses to guess rather than leave an entry silently out of the roster"
      else
        ctx "$where: the allowlist line \`$s\` in $decl_dir/.gitignore cannot be interpreted (reported against the repository, which owns that file; not counted twice) — the roster below is therefore short by at least that entry"
      fi
    done <<< "$rejects"
  fi
  roster=$(skill_roster "$decl_dir")
  if [ -z "$roster" ]; then
    if [ "$owns_decl" -eq 1 ]; then
      bad "$where: $decl_dir/.gitignore names no skills — the declaration reached nothing, which is a finding and not a clean zero"
    else
      ctx "$where: presence not checked — $decl_dir/.gitignore names no skills (reported against the repository, which owns that file; not counted twice)"
    fi
    return
  fi

  # The roster admits no whitespace and no glob metacharacter, so this word-split is safe and a
  # declared entry can never undergo pathname expansion against the caller's working directory.
  for s in $roster; do
    declared=$((declared + 1))
    # graph-navigation is declared like the rest but stays a WARNING here rather than a failure: it
    # is useful only alongside the third-party `graphify` CLI (see install.sh), which is a statement
    # about usefulness, not about whether this repository published it — so its severity is
    # deliberately different from the other five even though its name comes from the same
    # declaration. Whether that is right for the REPOSITORY scope specifically (as opposed to the
    # machine scope, where it plainly is) is a live question carded separately; it is unchanged here.
    if [ "$s" = "graph-navigation" ]; then
      opt_file "$check_root/$s/SKILL.md" "graph-navigation (optional)" \
        "graph-navigation absent from $where — only matters if you use graphify"
    else
      want_file "$check_root/$s/SKILL.md" "$s" "$s missing from $where"
    fi
    [ -f "$check_root/$s/SKILL.md" ] && present=$((present + 1))
  done

  if [ "$owns_decl" -eq 1 ]; then
    for d in "$check_root"/*/; do
      [ -f "${d}SKILL.md" ] || continue
      dirs=$((dirs + 1))
      dn=$(basename "$d")
      found=0
      for s in $roster; do [ "$s" = "$dn" ] && { found=1; break; }; done
      # A FAILURE HERE, THOUGH check_vendored_suites CALLS THE SAME SITUATION MERELY EXCLUDED, and
      # the two are consistent because they are asked about different trees. That function's
      # informational treatment is for an untracked vendor arrival, and the declaration's own header
      # says where those arrive: "graphify arrives via `uv tool` and writes into both
      # ~/.claude/skills and ~/.codex/skills". Neither is a checkout. A SKILL.md under this
      # repository's OWN install/skills/ that no `!/` line names is a re-vendor that forgot the
      # line — TC-51's defect in mirror image, and the direction nothing was watching.
      [ "$found" -eq 1 ] || {
        undeclared=$((undeclared + 1))
        bad "$where: $dn/ ships a SKILL.md but no \`!/$dn\` line declares it in $decl_dir/.gitignore — it is neither published nor installed; declare it or remove it"
      }
    done
    # EVERY FILTERED COUNT CARRIES ITS TOTAL, and here it carries the INDEPENDENT one too. The
    # declaration count and the directory count come from different places and are printed side by
    # side, so a reader can see them agree rather than being told a number that cannot disagree.
    ctx "$present of $declared declared skill(s) present in $where; the directory holds $dirs with a SKILL.md, $undeclared of them undeclared"
  else
    ctx "$present of $declared declared skill(s) present in $where (total from the repository's declaration, cross-checked against the vendored directory in section 1)"
  fi
}

# ── the vendored hook roster ──────────────────────────────────────────────────────────────────────
#
# THIS IS THE SKILL DEFECT ONE DIRECTORY OVER, and it was found by review rather than by this gate.
# Both hook sections used to name THREE files as literals — `disclosure-check.sh` required, the two
# `graphify-*` ones optional — against an `install/hooks/` that holds FOUR. The fourth,
# `preflight.sh`, is vendored, is installed by install.sh's `hooks/*` glob loop, and is routed to by
# the PUBLISHED progressive-disclosure/SKILL.md. Neither scope checked it: delete it and
# `./verify.sh` exited 0 in silence while every agent reading that SKILL.md was sent to a hook that
# no longer installs. This file already knew the real number — the comment in `check_installer_agrees`
# says reading past the skills block "swept four hook filenames into the skill set" — and still
# checked three.
#
# SO THE ROSTER IS DISCOVERED FROM THE DIRECTORY, exactly as the skill roster is discovered from the
# declaration: every regular file directly under install/hooks/ is a hook this repository ships, and
# both scopes check every one of them. install.sh installs by the same rule (`for h in "$HERE"/hooks/*`
# with an `[ -f ]` filter), so the gate's roster and the installer's roster are the same fact read
# the same way, and a re-vendor that adds a fifth hook is picked up by both with no edit here.
#
# AND A DISCOVERED ROSTER NEEDS A SECOND, INDEPENDENT SOURCE, WHICH IS WHAT `required` IS FOR. This
# was MEASURED on the skill side of the same card and is the reason the pin exists rather than being
# a preference: deleting a skill's `!/` line left the counter reading a clean `5 of 5`, because the
# denominator was derived from the same place as the numerator and could not disagree with it. What
# made that case loud was not the count — it was a separate check that NAMED the missing skill. A
# hook roster read only from the directory has precisely that hole: delete `install/hooks/preflight.sh`
# and the roster becomes three, `3 of 3` is printed, and the gate is green over a published route
# that no longer resolves.
#
# `required` closes it, and it is a hardcoded list ON PURPOSE — a hardcoded list that is MECHANICALLY
# CHECKED is not the defect this card is about; a hardcoded list nobody checks is. It is checked in
# both directions against the directory: a required name the directory does not carry is a FAILURE
# that names it, and a directory entry the pin does not name is not a failure at all, because that is
# the optional case (the graphify hooks are inert without the third-party `graphify` CLI, which the
# optional-dependency contract requires stay non-required).
#
# WHICH NAMES ARE PINNED, AND WHY THOSE TWO. Not "the ones that exist today" — the ones whose absence
# breaks something this repository PUBLISHES. `disclosure-check.sh` is the SessionStart hook the
# installer wires into settings.json; `preflight.sh` is what progressive-disclosure/SKILL.md tells
# every agent to run. Both are load-bearing for a documented route, so neither may go missing quietly.
HOOKS_REQUIRED="disclosure-check.sh preflight.sh"

# HOOKS_NAMED — every hook name whose absence from install/hooks/ must be REPORTED, even when it is
# not fatal. HOOKS_REQUIRED alone does not cover this: a roster DISCOVERED from the directory has a
# hole a hand-written roster never had — delete a file from install/hooks/ and the roster shrinks
# with it, so a name that is not in HOOKS_REQUIRED simply vanishes from every loop that walks the
# roster, with nothing left saying it used to be there.
#
# THE REGRESSION THIS CLOSES, MEASURED. Before the roster became directory-discovery, the two
# graphify hooks were named literals checked in both scopes, and deleting either one WARNED. After,
# deleting `install/hooks/graphify-query-advisor.py` produces NOTHING — not even the warn it used to
# — because `hook_roster`'s output no longer contains the name and every loop below is keyed off that
# output. Meanwhile install.sh HARD-FAILS its settings.json merge when any of the three scripts it
# wires is missing (see `missing_hooks` in install.sh's settings.json section), so `./verify.sh` was
# exiting 0 in silence on a tree install.sh itself refuses to finish installing.
#
# DERIVED FROM install.sh's OWN WANT LIST, UNION HOOKS_REQUIRED — not restated. This is the same
# extraction `check_settings_wired` performs against the installed settings.json, applied here
# against the vendored directory instead: one fact read twice, not a second roster. `disclosure-
# check.sh` and `preflight.sh` are already in HOOKS_REQUIRED and FAIL (via `check_hook_presence`)
# when missing; the two graphify names are new to this set, and MACHINE-SCOPE SEVERITY FOR THEM
# STAYS WARN — they are an optional dependency, and that is a repository fact, not a machine one, so
# `check_hook_named` below checks it exactly once, at repository scope, rather than making them fail.
HOOKS_NAMED="$HOOKS_REQUIRED $(grep -oE '~/\.claude/hooks/[A-Za-z0-9._-]+' "$VENDOR/install.sh" 2>/dev/null | sed 's#.*/##' | sort -u)"

# hook_roster DIR — the hooks this repository ships, one per line.
#
# Regular files only, one level deep, which is install.sh's own rule. With no directory at all the
# glob stays literal, `[ -f ]` is false, and this prints nothing — the caller treats an empty roster
# as a finding rather than as a clean zero, for the same reason `skill_roster` does.
hook_roster() {
  local d="$1" f
  for f in "$d"/*; do
    [ -f "$f" ] || continue
    printf '%s\n' "${f##*/}"
  done
}

# check_hook_presence CHECK_ROOT VENDOR_HOOKS WHERE OWNS_DIR REQUIRED — every vendored hook is
# present under CHECK_ROOT, and every REQUIRED name is one the vendored directory actually carries.
#
# TAKES ITS ROOTS AS ARGUMENTS FOR THE REASON `check_skill_presence` DOES, and the reason is measured
# rather than stylistic: `--self-test` exits ~2,300 lines above the two production call sites, so a
# loop written inline at those sites is unreachable from every assertion in this file. That is how
# the three-name roster survived every green run it was ever part of.
#
# OWNS_DIR IS 1 ONLY FOR THE REPOSITORY SCOPE, and it governs the same thing the skill check's
# OWNS_DECL governs: whether a fact about `install/hooks/` — a REPOSITORY directory — is charged as a
# finding here. This function runs twice against that one directory, once per scope, so firing the
# required-set findings in both would make ONE missing hook print TWO problems and charge the second
# to the MACHINE, which is this file's cardinal rule inverted.
check_hook_presence() {
  local check_root="$1" vend="$2" where="$3" owns_dir="$4" required="$5"
  local roster h r found present=0 total=0 req_total=0 req_absent=0

  roster=$(hook_roster "$vend")
  if [ -z "$roster" ]; then
    if [ "$owns_dir" -eq 1 ]; then
      bad "$where: install/hooks/ carries no hook at all, so there is nothing to check presence AGAINST — this is not an empty pass"
    else
      ctx "$where: presence not checked — install/hooks/ carries no hook (reported against the repository, which owns that directory; not counted twice)"
    fi
    return
  fi

  # The vendored tree carries no filename with whitespace or a glob metacharacter — install.sh's
  # `chmod_scripts` records the same constraint — so this word-split is safe.
  for h in $roster; do
    total=$((total + 1))
    found=0
    for r in $required; do [ "$r" = "$h" ] && { found=1; break; }; done
    if [ "$found" -eq 1 ]; then
      want_exec "$check_root/$h" "$h" "$h missing from $where, or not executable"
    else
      opt_file "$check_root/$h" "$h (optional)" \
        "$h absent from $where — it is vendored but not in the required set; the graphify hooks are inert without the third-party \`graphify\` CLI, so their absence is not a failure"
    fi
    [ -f "$check_root/$h" ] && present=$((present + 1))
  done

  # THE DIRECTION A DISCOVERED ROSTER CANNOT SEE. Everything above is measured against the vendored
  # directory, so a hook DELETED from that directory leaves the loop above with nothing to say.
  for r in $required; do
    req_total=$((req_total + 1))
    found=0
    for h in $roster; do [ "$h" = "$r" ] && { found=1; break; }; done
    [ "$found" -eq 1 ] && continue
    req_absent=$((req_absent + 1))
    if [ "$owns_dir" -eq 1 ]; then
      bad "$where: \`$r\` is a REQUIRED hook and install/hooks/ does not carry it — it is wired by the installer or routed to by a published SKILL.md, so its absence breaks a documented route rather than merely shrinking this roster; restore it or stop publishing the route"
    else
      ctx "$where: \`$r\` is required and install/hooks/ does not carry it (reported against the repository, which owns that directory; not counted twice) — the count below is short by that hook"
    fi
  done

  # EVERY FILTERED COUNT CARRIES ITS TOTAL, and the required tally is printed beside it because the
  # first total comes from the directory and so cannot contradict the directory. The second one can.
  ctx "$present of $total vendored hook(s) present in $where; the required set names $req_total, $req_absent of which install/hooks/ does not carry"
}

# check_hook_named VENDOR_HOOKS NAMED — every name in NAMED that VENDOR_HOOKS (install/hooks/) does
# not carry is REPORTED, once, here, at repository scope — install/hooks/ is a repository directory,
# and whether it ships an optional hook is a repository fact, not a machine one, so unlike
# check_hook_presence this is not run once per scope.
#
# A name already in HOOKS_REQUIRED is skipped: check_hook_presence's own req_absent loop already
# fails it by name, and reporting it again here would turn one missing file into two findings. Every
# other name in NAMED is the optional-dependency case this function exists for, and its absence is a
# WARNING, never a failure — the invariant HOOKS_NAMED's header records.
check_hook_named() {
  local vend="$1" named="$2" roster n f found
  roster=$(hook_roster "$vend")
  for n in $named; do
    found=0
    for f in $HOOKS_REQUIRED; do [ "$f" = "$n" ] && { found=1; break; }; done
    [ "$found" -eq 1 ] && continue
    found=0
    for f in $roster; do [ "$f" = "$n" ] && { found=1; break; }; done
    [ "$found" -eq 1 ] && continue
    note "install/hooks/ does not carry \`$n\`, which install.sh wires into settings.json when it is present — an optional dependency (its absence is a warning, not a failure), but a roster discovered from the directory cannot see a file that is not there, so this is checked independently of it"
  done
}

# check_persona_count LABEL DIR PATTERN TOTAL — LABEL's rendered persona count against an
# INDEPENDENT total supplied by the caller (the vendored pool, counted from a directory neither
# call site touches). Three sites used to be bare `> 0` floors with no denominator at all — the same
# defect this card's hook and skill rosters were built to close, one roster over: move all but one
# file out of `~/.claude/agents` and `ok  1 persona(s)`, exit 0, over a pool documented as thirteen.
# Reports N of TOTAL and FAILS ON A SHORTFALL, not merely on zero, which is the fix.
#
# DEFINED ABOVE THE `--self-test` DISPATCH FOR THE REASON `check_hook_presence` IS: a function
# written inline at its call site is unreachable from every assertion in this file, which is how the
# three floors survived every green run they were ever part of.
check_persona_count() {
  local label="$1" dir="$2" pattern="$3" total="$4" n
  n=$(find "$dir" -name "$pattern" 2>/dev/null | wc -l | tr -d ' ')
  n=${n:-0}
  if [ "$total" -le 0 ]; then
    # The vendored pool itself is empty or unreadable — already reported where it is counted;
    # do not report the same fact a second time here.
    ctx "$label: persona count not checked against a total — the vendored pool total is not known (reported above)"
    return
  fi
  if [ "$n" -ge "$total" ]; then
    ok "$n of $total persona(s) in $label"
  else
    bad "$label: only $n of $total persona(s) present — short by $((total - n)); run sync_personas.py"
  fi
}

# check_installer_agrees INSTALLER DECL_DIR — the installer's OWN skill set, obtained by running it,
# equals the roster derived above.
#
# THE ONE MUTATION A ROSTER CHECK INSIDE THIS FILE CANNOT SEE. install.sh derives its set from the
# same declaration with its own copy of the same strict reader; nothing in verify.sh reads
# install.sh, so reverting install.sh to a stale hardcoded list changes nothing any assertion here
# touches — MEASURED, the five-name literal came back and both scopes stayed green, because machine
# scope checks `~/.claude`, where the sixth skill was already installed by an earlier correct run.
# An installed layer cannot testify about the installer that will next write to it.
#
# So the installer is EXECUTED, in the dry run that writes nothing (every write in install.sh is
# behind `run`, `[ "$DRY" -eq 1 ]`, or `[ "$DRY" -eq 0 ]`), and the names it says it would install
# are compared as a set. Its exit code is deliberately NOT the assertion: a fixture installer fails
# on absent hooks/ for reasons that are not about skills, so failing on rc alone would report a
# package fact as a disagreement about the roster.
#
# BUT "IGNORE THE EXIT CODE" IS NOT "COMPARE WHATEVER CAME BACK", AND THE FIRST VERSION MADE THAT
# EXACT MISTAKE. `install.sh:83-87` exits 1 BEFORE it prints `skills` when python3 is absent or
# older than 3.10 — Apple's `/usr/bin/python3` through macOS 12, and many minimal images. `got` was
# then EMPTY, the set comparison ran anyway, and the check printed a REPOSITORY FAIL naming all six
# declared skills as an installer disagreement. `./verify.sh` exited 1 for a repository reason
# caused entirely by the machine's interpreter, and sent the maintainer to install.sh's roster
# reader, which was fine. An earlier comment here waved that away as belonging to "its own check";
# no such check existed anywhere in this file. So the two cases are now told apart: an installer
# that REACHED the skills section and named a different set is a repository finding, and an
# installer that never reached it produced no set to compare, quoting the installer's own first line
# so the real reason is on screen.
#
# THE CAUSE IS PROBED, NOT ASSERTED, AND THE FIRST VERSION OF THAT SPLIT ASSERTED IT. "No `skills`
# line" was treated as a synonym for "the interpreter is too old" and the message said so in
# words — *"That is the installer reporting a fact about THIS MACHINE (it requires python3 3.10+)"*.
# That test fires on EVERY reason install.sh fails to print the header. MEASURED: change
# `install.sh:159` from `echo "skills"` to `echo "skills:"` and run on 3.13, and the gate reported
# the installer *"exited 0 before reaching its `skills` section … a fact about THIS MACHINE"* —
# false in three clauses at once, exit 2, repository FAIL suppressed. A bash syntax error in
# install.sh misattributes identically. The consequence is the serious one: the roster comparison is
# the ONLY thing in this file that can see install.sh revert to a hardcoded skill list, and it
# silently stopped running while the gate blamed the machine.
#
# So the interpreter precondition install.sh enforces at its top is RUN HERE, by this gate, on this
# machine. python3 absent, or older than 3.10 — each PROBED here, not inferred from the installer's
# silence — is a machine fact and the not-run is attributed to the machine. python3 present AND
# >= 3.10 and the installer STILL never reached `skills` is a REPOSITORY finding at exit 1, because
# nothing this gate can measure excuses it.
#
# AND THE TIMEOUT ARM IS NEITHER, WHICH IS THE CORRECTION THIS ROUND MAKES. An rc of 124/137 was
# routed into the machine arm and said "recorded against THIS MACHINE" — the same unmeasured
# diagnosis the paragraph above was written to remove, surviving in the one arm that was not
# rewritten, with a comment vouching for it. A TIMEOUT IS A FACT ABOUT THE INSTALLER'S RUNTIME, NOT
# ABOUT THIS BOX. Put a hang in install.sh above `echo "skills"` and run anywhere a `timeout` binary
# exists — every Linux box and every CI runner — and the gate blamed the machine, exited 2, and did
# not run the roster comparison. Nothing here measures whether a 120s overrun is a slow machine or a
# wedged script, so the third arm NAMES NEITHER: it is a COULD NOT RUN left on the entering
# (repository) scope, saying in those words that the cause was not determined. It is not charged to
# the machine, so `repo_attributed_out` is NOT incremented for it — the repository line carries the
# finding itself rather than a marker pointing at another line. No arm names a cause it did not test.
#
# AND THE NOT-RUN IS MARKED ON THE REPOSITORY LINE. This is a repository-scope check; sending the
# whole not-run to `env` left the repository verdict byte-identical to a clean run. The finding goes
# where its cause is and `repo_attributed_out` records that the repository line is short by one.
#
# ON WEDGING, DOWNGRADED TO WHAT HOLDS. The subprocess gets `</dev/null`, and `timeout`/`gtimeout`
# IF THE PLATFORM HAS ONE — on the machine this was written on it has NEITHER, so there stdin is the
# only bound and no real installer can REACH rc 124 here. The arm itself is still exercised on every
# machine, by a stub that exits 124 on its own; see (j3) in the self-test. The honest claim is narrow:
# an installer
# that reads stdin gets EOF instead of the gate's terminal, and where a `timeout` exists a
# long-running one is bounded too. install.sh reads no stdin and makes no network call today — every
# branch checked — so this is not a fix for a live hang; it is a bound on a surface that did not
# exist before this check ran another script, and that now exists twice, because `--self-test` runs
# the real vendored installer too. A non-completion lands in the COULD NOT RUN arm, never in the set
# comparison. `timeout` is optional, like every other third-party binary this file touches: without
# it the call is exactly what it was before, minus stdin.
check_installer_agrees() {
  local installer="$1" decl_dir="$2" out roster want got s rc=0 runner="" first prev_scope why pyv
  if [ ! -f "$installer" ]; then
    bad "no installer at $installer — the install set cannot be compared with what this repository declares it publishes"
    return
  fi
  roster=$(skill_roster "$decl_dir")
  if [ -z "$roster" ]; then
    # Already reported by check_skill_presence; do not count the same fact twice.
    ctx "installer agreement not checked — the declaration named no skills (reported above)"
    return
  fi
  if command -v timeout >/dev/null 2>&1; then runner="timeout 120"
  elif command -v gtimeout >/dev/null 2>&1; then runner="gtimeout 120"; fi
  # $runner is unquoted ON PURPOSE: it is either empty or a fixed two-word literal set four lines up,
  # never anything derived from the environment, so the word split is the whole point of it.
  # shellcheck disable=SC2086
  out=$($runner bash "$installer" --dry-run --no-codex </dev/null 2>&1) || rc=$?
  if ! printf '%s\n' "$out" | grep -q '^skills$'; then
    first=$(printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | head -n 1)
    [ -n "$first" ] || first="(it printed nothing)"
    # THE UNATTRIBUTABLE ARM FIRST, because it is the one that must not borrow either of the others'
    # words. A 120s overrun is a fact about the installer's runtime; this gate measures nothing that
    # separates a slow machine from a wedged script, so it diagnoses neither and says so. It stays in
    # the ENTERING scope — the finding is not taken off the repository line, so there is nothing for
    # `repo_attributed_out` to mark.
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
      cnr "the installer agreement could not be checked — $installer did not finish within 120s and was killed (rc $rc), so it never printed its \`skills\` section, and the last thing it said was: \`$first\`. THIS GATE CANNOT TELL WHETHER THAT IS THE MACHINE OR THE SCRIPT: a timeout is a fact about the installer's runtime, not about this machine, and nothing here measures which one produced it — so it is attributed to NEITHER and left on the $SCOPE line. Nothing about what $decl_dir/.gitignore declares is claimed in either direction, because no set was produced, so none was compared; the roster comparison — the only check in this file that can see install.sh revert to a hardcoded skill list — did not run"
      return
    fi
    # THE TWO MACHINE CAUSES, EACH ONE MEASURED BEFORE IT IS NAMED. Anything else falls through to
    # the repository arm; "this gate could not find a machine reason" is the only thing that puts a
    # finding on the repository line here, and it is stated in those words rather than as a diagnosis.
    if ! command -v python3 >/dev/null 2>&1; then
      why="$installer exited $rc before reaching its \`skills\` section, saying: \`$first\` — and python3 is NOT ON PATH here, probed by this gate, which is the precondition install.sh enforces at its top"
    elif ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
      pyv=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
      why="$installer exited $rc before reaching its \`skills\` section, saying: \`$first\` — and the python3 on PATH is ${pyv:-of an unreadable version}, which fails the 3.10-or-newer precondition install.sh enforces at its top, probed by this gate rather than inferred from the installer's silence"
    else
      # NOT A MACHINE FACT, AND THIS ARM IS THE WHOLE POINT OF PROBING. python3 is present and new
      # enough, so the installer's own documented precondition is satisfied and something else
      # stopped it — a syntax error, a renamed section header, a new precondition. Whatever it is,
      # it is in the repository, and the check that can see install.sh revert to a hardcoded skill
      # list did not run. Exit 1, and no cause is named beyond the one that was excluded.
      pyv=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
      bad "the installer agreement could not be checked, and NOT for a reason on this machine — $installer exited $rc without ever printing its \`skills\` section, saying: \`$first\`. python3 ${pyv:-(version unreadable)} is on PATH and satisfies the 3.10-or-newer precondition install.sh enforces at its top, so the interpreter is not the reason; this gate does not know what the reason is and will not guess one. The roster comparison — the only check in this file that can see install.sh revert to a hardcoded skill list — did not run"
      return
    fi
    # THE FINDING GOES TO THE MACHINE, THE MARKER STAYS ON THE REPOSITORY LINE. See
    # `repo_attributed_out`: routing the whole not-run to `env` left the repository verdict
    # byte-identical to a clean run while a repository-scope check had not executed.
    prev_scope="$SCOPE"; SCOPE="env"
    cnr "the installer agreement could not be checked — $why. That is recorded against THIS MACHINE and taken off the repository line; nothing about what $decl_dir/.gitignore declares is claimed in either direction, because no set was produced, so none was compared"
    SCOPE="$prev_scope"
    # Guarded on the entering scope for the same reason `run_one_suite`'s is: this function has one
    # call site and it is in repository scope, but a counter named `repo_` must not be incremented
    # from a machine-scope call that a later card adds.
    [ "$prev_scope" = "repo" ] && repo_attributed_out=$((repo_attributed_out+1))
    return
  fi
  # BOUNDED TO THE `skills` SECTION FIRST. The hooks loop below it prints `would install <file>` in
  # the identical wording, and reading the whole output swept four hook filenames into the skill set
  # — caught on the first real run, because the check compares SETS and said exactly which extra
  # names it had. The section runs from the `skills` header to the next column-0 header.
  #
  # `would install X`, `installed X`, and `SKIP X (not in this package)` — the installer's INTENT,
  # which is the set under comparison. A declared skill whose directory is absent is a package fact
  # the presence check above already owns; it must not read here as the installer disagreeing.
  got=$(printf '%s\n' "$out" \
    | awk '/^skills$/ { inblock = 1; next } inblock && /^[^ ]/ { exit } inblock' \
    | sed -n -e 's/^  would install \(.*\)$/\1/p' -e 's/^  installed \(.*\)$/\1/p' -e 's/^  SKIP \(.*\) (not in this package)$/\1/p' \
    | sort)
  want=$(printf '%s\n' "$roster" | sort)
  if [ "$got" = "$want" ]; then
    ok "install.sh would install exactly the $(printf '%s\n' "$want" | grep -c .) declared skill(s)"
  else
    bad "install.sh's skill set does not match the declaration — it would act on [$(printf '%s' "$got" | tr '\n' ' ')] while $decl_dir/.gitignore declares [$(printf '%s' "$want" | tr '\n' ' ')]; the installer and this gate are reading different answers, which is how the sixth skill went unpublished the first time"
  fi
}

# check_settings_wired INSTALLER SETTINGS_JSON WHERE — every hook entry INSTALLER's settings.json
# merge wants is actually present in SETTINGS_JSON. WHERE is a display label only (e.g.
# `~/.claude/settings.json`) so messages read the same as before extraction rather than printing
# whatever absolute path the caller resolved SETTINGS_JSON to.
#
# EXTRACTED FOR THE REASON check_hook_presence AND check_skill_presence WERE. This used to be ~30
# lines of INLINE PRODUCTION LOGIC WITH ZERO ASSERTIONS, unreachable from --self-test — the same
# shape as the three-name hook roster this card's earlier rounds fixed one directory over. MEASURED:
# mutating the extraction regex to match nothing, or deleting the empty-extraction guard, left
# production printing "3 of 3 hook entries ... are wired" over a settings.json with no hook entries
# at all, and --self-test stayed green throughout, because nothing in this file's assertions ever
# called this code. Extracting the body here is what lets a fixture drive it.
#
# THE EXPECTED SET IS STILL READ OUT OF INSTALLER RATHER THAN WRITTEN AGAIN HERE — the installer's
# `WANT` list is the only place that decides what gets merged; a copy of it in this file would be a
# second roster that drifts exactly as the skill list once did. An empty extraction is a FAILURE
# rather than a clean zero, the same rule the skill and hook rosters follow.
check_settings_wired() {
  local installer="$1" settings_json="$2" where="$3" settings_want settings_cmds w sw_total=0 sw_wired=0
  settings_want=$(grep -oE '~/\.claude/hooks/[A-Za-z0-9._-]+' "$installer" 2>/dev/null | sort -u)
  if [ -z "$settings_want" ]; then
    bad "could not derive which hook entries install.sh merges — no \`~/.claude/hooks/<name>\` reference was found in $installer, so this check had nothing to look for and must not pass vacuously"
    return
  fi
  if [ ! -f "$settings_json" ]; then
    bad "no $where"
    return
  fi
  if ! settings_cmds=$(python3 - "$settings_json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"settings.json is not valid JSON: {e}", file=sys.stderr); raise SystemExit(1)
for ev in d.get("hooks", {}).values():
    for e in ev:
        for h in e.get("hooks", []):
            print(h.get("command", ""))
PY
  ); then
    bad "$where could not be read as JSON, so not one hook entry could be checked — a malformed settings.json disables every setting in it"
    return
  fi
  for w in $settings_want; do
    sw_total=$((sw_total + 1))
    if printf '%s\n' "$settings_cmds" | grep -qF -- "$w"; then
      ok "wired: ${w##*/}"
      sw_wired=$((sw_wired + 1))
    else
      bad "${w##*/} is not wired into $where — install.sh merges an entry naming \`$w\` and this settings.json has none; re-run ./install.sh"
    fi
  done
  ctx "$sw_wired of $sw_total hook entr$([ "$sw_total" -eq 1 ] && echo y || echo ies) install.sh merges are wired into $where"
}

# check_vendored_suites SKILLS_ROOT — discover every vendored skill under SKILLS_ROOT and apply
# whichever of the two treatments it earns. Takes the root as an argument so --self-test can drive
# it against constructed fixtures; a fixture built on a REAL suite's test count would be broken
# already, because another card may re-vendor this tree at any time.
check_vendored_suites() {
  local root="$1" d name has_suite
  suites_found=0; suites_with=0; suites_none=0; suites_excluded=0
  suites_pass=0;  suites_fail=0;  suites_cnr=0; suites_vacuous=0
  suites_tests=0; suites_skipevents=0; suites_exec_lo=0

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
  # git itself is the authority FOR THIS QUESTION, and it is the right authority for exactly this
  # one: "is this arrival something the repository excludes". No second gitignore parser is
  # introduced HERE. Note what git cannot be asked, because the qualifier used to be missing and a
  # maintainer reading only this line would look in the wrong place: `git check-ignore` consults the
  # index and will not call a TRACKED path ignored, so it cannot enumerate the declaration or notice
  # a tracked skill losing its `!/` line. That question belongs to `skill_roster` above, which reads
  # a deliberately strict subset of the syntax and fails loudly on anything outside it.
  #
  # If git cannot answer — not installed, or this is an unpacked tarball rather than a checkout —
  # the EXCLUSION cannot be applied, which is not the same as empty: it is reported, and discovery
  # proceeds over everything, because testing more than declared is the safe direction and testing
  # less is not. The wording below says "the exclusion could not be applied" rather than "the
  # declaration could not be read", because the latter was false in the same run that printed it:
  # the presence check a few hundred lines down reads that same file with no git at all and prints a
  # count from it. One run, one file, two sentences that contradicted each other.
  local can_read_decl=1
  if ! command -v git >/dev/null 2>&1 || ! git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    can_read_decl=0
    # MACHINE scope: the exclusion is a repository question, but every reason it cannot be applied is
    # machine-side — git not installed, or this tree was unpacked from a tarball rather than cloned.
    # Same rule as everywhere else in this file: if the answer depends on the machine, it does not
    # belong in the repository verdict.
    local decl_scope="$SCOPE"; SCOPE="env"
    note "git could not apply install/skills/.gitignore to this tree — no git, or this is not a checkout — so discovery below cannot tell a skill this repository publishes from one a vendor installed here on its own. The declaration is still READ, by the presence check; only the exclusion is unavailable"
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
    has_suite=$(suite_dir_state "${d%/}")
    if [ "$has_suite" = "suite" ]; then
      suites_with=$((suites_with+1))
      run_one_suite "$name" "${d%/}"
    elif [ "$has_suite" = "unreadable" ]; then
      # Counted into suites_with, because the evidence-bearing quantity is "skills whose suite we
      # were supposed to have a result for". Leaving it out would let an unreadable tree drive
      # suites_with to zero and trip the FLOOR instead — a loud finding, but the wrong one, naming
      # the whole tree rather than the one directory that could not be opened.
      suites_with=$((suites_with+1))
      suites_cnr=$((suites_cnr+1))
      cnr "$name: the vendored suite COULD NOT RUN — $name/tests exists but it, or a directory beneath it, cannot be read (permissions), so whether it holds a suite is UNKNOWN. That is not the same as having none, and it is not a pass"
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
    # THE FLOOR, FIRST STOREY. `suites_found` is not the evidence-bearing quantity. Delete every
    # vendored `tests/` directory and the old check printed "6 discovered, 0 with a vendored suite,
    # 6 NOT TESTED HERE" and exited 0 — the published tests silently stop being evidence and nothing
    # says so. Same argument as the zero-discovery guard, applied one quantity further in.
    bad "$suites_found vendored skill(s) discovered under $root and NOT ONE has a test suite — this repository publishes tests as evidence, so zero runnable suites is a finding and not a clean result"
  elif [ "$suites_pass" -eq 0 ] && [ "$suites_fail" -eq 0 ] && [ "$suites_cnr" -eq 0 ]; then
    # THE FLOOR, SECOND STOREY, AND THE COMMENT ABOVE USED TO NAME `suites_with` AS THE
    # EVIDENCE-BEARING QUANTITY. It was, until `suites_vacuous` existed. IT IS NOW `suites_pass`,
    # and this arm is the correction: `suites_with` counts skills that HAVE a `tests/` directory,
    # which is known before any result is, so every suite in the corpus could land in
    # `suites_vacuous` — via the class-guard branch or the `exec_lo <= 0` branch, both of which call
    # `skip`, neither `bad` nor `cnr` — leaving `repo_fail=0`, `could_not_run=0`, the yellow
    # PASS-with-skips verdict, and EXIT 0 OVER A RUN THAT DEMONSTRATED NOT ONE ASSERTION. That is
    # this file's founding defect (published tests that nobody runs are a claim, not a check) read
    # by `$?` instead of by a reader, and it was pinned green by this file's own self-test.
    #
    # THE CONDITION IS NARROWER THAN "NOT ONE PASSED", AND THE NARROWING IS MEASURED RATHER THAN
    # PREFERRED. `suites_with > 0` holds by the arm above; the extra two terms say no suite failed
    # and none could not run — which, since the four buckets sum to `suites_with`, is exactly
    # `suites_vacuous == suites_with`, the all-vacuous run. Stated as the three counters rather than
    # as that identity so it does not depend on the sum holding.
    #
    # IT LOSES NO COVERAGE OF THE HOLE. Exit 0 requires `repo_fail`, `env_fail` and `could_not_run`
    # all zero; `suites_fail > 0` has already called `bad` and `suites_cnr > 0` has already called
    # `cnr`, so every run this arm declines to fire on has ALREADY earned 1 or 2. The set of runs
    # that reach exit 0 with `suites_pass == 0` is precisely the set this fires on.
    #
    # AND THE BARE `suites_pass == 0` FORM WAS MEASURED TO BREAK TWO OF THIS FILE'S OWN FIXES. On the
    # could-not-run fixtures it printed a repository FAIL immediately beneath a `COULD NOT RUN` line
    # reading "No verdict about this suite exists either way" — a verdict, over the one disposition
    # that exists to refuse one. And on the `$HOME`-routed fixtures it put a finding back on the
    # repository line in a run whose only finding had just been attributed to the machine, which is
    # F1 inverted in the place F1 was fixed. Neither could ever change an exit code, since both runs
    # were already 1 or 2, so both were pure misattribution.
    #
    # WHY `bad` (exit 1) AND NOT `cnr` (exit 2). The suites RAN. Nothing could-not-run about them;
    # they simply yielded nothing that can be shown to be an assertion, which is a finding about
    # this run and not a reason to distrust the report. 2 stays reserved for could-not-run, so the
    # frozen three-code contract is untouched and no fourth exit state is invented.
    #
    # PER SUITE, a vacuous result is still exit 0 and still a skip — a guard that fired is a machine
    # fact with a clean result line, argued at the `exec_lo <= 0` branch, and a skip is not a
    # finding. This arm is the AGGREGATE claim, which is a different claim: when nothing passed, the
    # gate has established nothing at all about the published tests, and a 0 from it would mean "the
    # tests are evidence" on the strength of tests that executed no assertion.
    #
    # IT FIRES EVEN WHEN THE VACUITY IS MACHINE-KEYED, and that is the point rather than an oversight.
    # A tree whose every suite is guarded on `$HOME` or on a tool being present yields nothing on a
    # machine that has neither, and that is exactly the reachable case: this repository's own two
    # vendored suites carry such guards. Per suite that stays a machine fact and a skip. In the
    # aggregate it is a fact about THIS RUN — that it is not evidence — which is why the sentence
    # blames neither the tree nor the machine, and says what is true of both readings.
    bad "0 of $suites_with vendored suite(s) under $root yielded a demonstrable assertion — every suite that has a test directory ran only guards or skips, so this run established NOTHING about the published tests, and exit 0 over it would report that absence as evidence"
  fi

  # EVERY FILTERED COUNT CARRIES ITS TOTAL. "0 suites failed" is indistinguishable from "nothing was
  # discovered"; "0 of 2" is not. Printed as ctx because it is a description of the run, not a
  # finding — the findings above it are already counted. Two lines: suites, then tests, because the
  # test-level skip count is the one this gate was previously silent about.
  #
  # THE LAST BUCKET IS NAMED FOR WHAT IS TRUE OF BOTH ITS OCCUPANTS, WHICH `ran only skips` WAS NOT.
  # `suites_vacuous` holds two branches: the `ran -eq 0` guard branch, where nothing ran at all, and
  # the `sk >= ran` branch, where the per-suite sentence four lines above this one is CAREFUL not to
  # assert that nothing ran — it says `0 of N can be SHOWN to have executed` and names the reading
  # under which up to N of them ran and passed. `ran only skips` re-asserted, in different words and
  # in the aggregate, exactly the claim that sentence was reworded to stop making: for the
  # mixed-guard fixture the same output block said `between 0 and 1 of 1 may in fact have passed`
  # and `1 of 1 ran only skips`. `yielded no demonstrable assertion` is true of both occupants and
  # asserts nothing about what executed.
  ctx "$(printf 'suites: %d skill(s) discovered (%d excluded by the publication declaration), %d with a vendored suite, %d NOT TESTED HERE; %d of %d suite(s) passed, %d of %d failed, %d of %d could not run, %d of %d yielded no demonstrable assertion' \
    "$suites_found" "$suites_excluded" "$suites_with" "$suites_none" \
    "$suites_pass" "$suites_with" "$suites_fail" "$suites_with" "$suites_cnr" "$suites_with" \
    "$suites_vacuous" "$suites_with")"
  #
  # AND THE TEST-LEVEL LINE IS A BOUND WHENEVER THE UNDERLYING QUANTITY IS ONE. `suites_skipevents`
  # counts skip EVENTS and `suites_tests` counts tests; the two are different units and subtracting
  # one from the other is what printed `-1 of 1 … 2 of 1` (see the SKIP EVENTS block in
  # run_one_suite). `suites_exec_lo` is the sum of per-suite lower bounds and is therefore in
  # `[0, suites_tests]` by construction, so neither a negative numerator nor a numerator above its
  # own total can be produced here — for any `ran` that reaches the arithmetic, which is now only a
  # `ran` that parsed as a non-negative integer, ENFORCED at the parse rather than assumed (see the
  # validation above the branch chain in run_one_suite; `Ran -3 tests` used to reach here and print
  # `between 0 and -3 of -3`).
  #
  # THE SKIP-EVENT TOTAL IS PRINTED WITHOUT A DENOMINATOR ON PURPOSE, AND IT NOW NAMES ITS WHOLE
  # POPULATION. It has no total in the units of the sentence, and inventing `suites_tests` as its
  # total is exactly the category error being fixed. What a count without a denominator still owes
  # the reader is its population, and this one used to understate it: fed only from the `else` arm of
  # run_one_suite, it excluded the `ran -eq 0` guard branch — the paradigm case of an event that is
  # not a test. It is now fed from BOTH, so it is every skip event this run observed, over every
  # suite that produced a recognisable result line. The filtered count over TESTS is the interval
  # beside it, and that one carries its total.
  #
  # THE SHAPE SELECTOR KEYS ON THE INTERVAL'S OWN ENDS, NOT ON THE EVENT COUNT, and that is a
  # consequence of the fix above rather than a preference. The two quantities used to move together;
  # they no longer do. A run whose only skip events come from the guard branch has
  # `suites_tests == suites_exec_lo == 0` with `suites_skipevents > 0`, and keying on the event count
  # would print `between 0 and 0 of 0 … between 0 and 0 of 0` — a bound whose ends coincide, over a
  # population of nothing. Keying on `suites_exec_lo -eq suites_tests` prints the point form there,
  # correctly, and the event clause below still reports the events. The two corollaries that keep
  # each shape honest: `suites_exec_lo < suites_tests` is exactly when a method-skip is possible, so
  # the interval form can never print `between N and N`; and equality means no test-level skip was
  # observed at all, so the point form can never print anything but `N of N` and a literal 0.
  #
  # TWO SHAPES, because a bound whose ends coincide should not be printed as a bound: with no
  # test-level skips the interval is a point and the sentence is the exact one it has always been —
  # which is every run on this tree ON A MACHINE WHERE NONE OF ITS `$HOME`- AND TOOL-KEYED GUARDS
  # FIRE. That qualifier is the whole content of the claim and it was missing: `sk == 0` is a
  # property of the MACHINE, never of the tree. MEASURED end to end, by pointing `VERIFY_SUITE_PY` at
  # a python3 wrapper that hides `git` from the suite and changing nothing else — this line came out
  # `between 381 and 392 of 392 … 11 skip event(s) were reported`. So the line is unchanged in
  # production HERE, and correctly different elsewhere.
  #
  # The event clause is built once and appended to whichever shape is chosen, because it is a fact
  # about the run in its own unit and not a fact about either shape. Empty when there were none, so
  # neither sentence gains a trailing dash it has no number for.
  local ev=""
  [ "$suites_skipevents" -gt 0 ] && ev=$(printf -- ' — %d skip event(s) were reported, and a skip event is one test OR one whole guarded class, which a runner summary line cannot tell apart' "$suites_skipevents")
  if [ "$suites_exec_lo" -eq "$suites_tests" ]; then
    ctx "$(printf 'tests:  %d of %d vendored test(s) actually executed an assertion; %d of %d were SKIPPED and are NOT TESTED HERE' \
      "$suites_exec_lo" "$suites_tests" 0 "$suites_tests")$ev"
  else
    ctx "$(printf 'tests:  between %d and %d of %d vendored test(s) actually executed an assertion; between %d and %d of %d were SKIPPED and are NOT TESTED HERE' \
      "$suites_exec_lo" "$suites_tests" "$suites_tests" \
      0 "$((suites_tests - suites_exec_lo))" "$suites_tests")$ev"
  fi
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
  st_pass=0; st_fail=0; st_skipped=0
  # THE NOT-RUN COUNT IS DERIVED FROM THE BRANCH, NOT HAND-WRITTEN BESIDE IT. `st_skip NAME N REASON`
  # took N as a literal, and the pinned total can only catch a wrong N ON A MACHINE THAT TAKES THE
  # BRANCH. Every guard here is false on a developer machine with python3, git and working mode bits,
  # so adding an assertion to a guarded branch and forgetting to bump N reads correct locally and goes
  # red only on someone else's laptop — which is the round-1 defect, surviving the fix for it.
  #
  # So the branch is WALKED either way. `ST_DRY=1` makes every assertion helper count itself as
  # not-run and return before doing any work, and the not-run arm runs exactly the same lines as the
  # run arm. The count therefore cannot disagree with the branch, because it IS the branch. What made
  # this cheap rather than a refactor: all five guarded bodies are assertion calls only — their
  # fixture setup already sits ABOVE the guard, because each guard exists to test whether that setup
  # took.
  #
  # WHAT A DRY WALK COSTS, STATED ONCE AND STATED TRUE. It repeats no `chmod` and no `git init`:
  # those are the expensive and order-dependent operations, and every one of them sits above a
  # guard. It forks exactly ONE subprocess, a `mkdir` — exception (1) below. An earlier version of
  # this line said "and no subprocess" and then disclosed that `mkdir` two sentences later, which is
  # the same unqualified-sentence-plus-exception shape being corrected here; the two writes in that
  # exception are `printf` and `: >`, both builtins, and the `rm` in exception (2) is behind a test
  # that is false on the dry walk, so `mkdir` really is the whole of it.
  # It is NOT free of the filesystem, and an earlier version of this line said it was
  # — while three writes lived inside a dry region 1,000 lines below, which is exactly the shape of
  # unchecked self-description this suite keeps removing. There are TWO documented exceptions, each
  # marked at the line with `# ST_DRY-SIDE-EFFECT:` and each asserted by the range check in the
  # self-test. (1) In `skills_deep_unreadable`, the `zz` sub-fixture — a `mkdir` and two small writes
  # — cannot be hoisted above the guard, because the FIRST assertion in that region requires the tree
  # WITHOUT it; a dry walk therefore does create three files under the temp root. (2) In the
  # declaration region, one conditional `rm` of a fixture `.gitignore`, which no-ops in the dry walk
  # because the fixture was never built. Nothing else in a dry region may touch the filesystem, and
  # that is CHECKED rather than promised — see the `ST_DRY-SIDE-EFFECT` assertion.
  ST_DRY=0
  # st_dry_begin NAME REASON / st_dry_end — the not-run arm. The count is unknown at `begin`, so the
  # NOT RUN line is printed at `end`, from the delta the walk produced.
  st_dry_begin() { st_dry_name="$1"; st_dry_reason="$2"; st_dry_n0=$st_skipped; ST_DRY=1; }
  st_dry_end() {
    [ "$ST_DRY" -eq 1 ] || return 0
    ST_DRY=0
    printf '  \033[36mNOT RUN\033[0m  %s (%s assertion(s)) — %s\n' \
      "$st_dry_name" "$((st_skipped - st_dry_n0))" "$st_dry_reason"
  }
  st_dir=$(mktemp -d) || { echo "self-test: no temp dir"; exit 2; }

  # THE FIXTURE ROOT MUST BE OUTSIDE ANY GIT WORK TREE, AND IT IS PROVEN ONCE HERE RATHER THAN
  # GUARDED AT ONE CALL SITE. Round 2 guarded the single assertion whose premise is "the declaration
  # is UNREADABLE here" — correct, and far too narrow. About forty-five `expect_suites` calls share
  # the INVERSE premise: `check_vendored_suites` asks `git check-ignore` about every fixture skill
  # whenever the declaration is readable, so a fixture root inside a work tree that IGNORES it
  # excludes every skill, drives `suites_found` to 0, and turns those assertions red with
  # `discovered total of zero`. Not hypothetical: this repository's own `.gitignore` ignores
  # `analysis/`, and on any platform where `mktemp -d` honours `TMPDIR` — Linux does; macOS, measured,
  # does not — `TMPDIR=<repo>/analysis/tmp ./verify.sh --self-test` is that shape. Guarding one
  # assertion there turns one spurious FAIL into a NOT RUN and leaves forty-five red.
  #
  # One condition covers both hazards, because `check-ignore` is only consulted when the tree is a
  # checkout at all: NOT INSIDE A WORK TREE. Without git, `can_read_decl` is 0 unconditionally and
  # neither hazard exists, so the probe passes trivially and correctly.
  #
  # WHEN IT FAILS, RELOCATE, THEN REFUSE. `/tmp` by explicit template is tried second because the
  # first root's location is TMPDIR's choice and not this script's. If that is inside a work tree too,
  # the suite EXITS 2 rather than skipping forty-five assertions and printing a count: this file's own
  # meaning for 2 is "something that had to run could not run at all", and a self-test that cannot
  # construct an independent fixture root is exactly that. A skip would be a filtered count over a
  # denominator nobody could act on.
  st_root_ok() {
    command -v git >/dev/null 2>&1 || return 0
    git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1 && return 1
    return 0
  }
  if ! st_root_ok "$st_dir"; then
    st_first_dir="$st_dir"
    st_dir=$(TMPDIR=/tmp mktemp -d /tmp/verify-selftest.XXXXXXXX 2>/dev/null) || st_dir=""
    if [ -z "$st_dir" ] || ! st_root_ok "$st_dir"; then
      [ -n "$st_dir" ] && rm -rf "$st_dir"
      rm -rf "$st_first_dir"
      echo "SELF-TEST COULD NOT RUN — no fixture root outside a git work tree. Tried \`mktemp -d\` (${st_first_dir}) and /tmp. Every suite assertion drives \`check_vendored_suites\`, which asks \`git check-ignore\` about each fixture skill whenever the declaration is readable; inside an ignoring work tree that excludes all of them and the assertions fail for a reason that is not about verify.sh. Set TMPDIR to a directory outside any checkout and re-run." >&2
      exit 2
    fi
    rm -rf "$st_first_dir"
  fi
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
    [ "$ST_DRY" -eq 0 ] || { st_skipped=$((st_skipped+1)); return 0; }
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
  # A SUITE THAT EMITS AFTER ITS OWN SUMMARY — the fixture for the parse anchoring, and it had to be
  # written rather than found: NO VENDORED SUITE DOES THIS TODAY, so nothing on the real tree would
  # ever have gone red while the defect sat there. Identical to st_skip_body except for the `print`.
  # `unittest` writes `OK (skipped=1)` to stderr (line-buffered); this `print` goes to stdout, which
  # is BLOCK-buffered because the caller captures through a `$( … 2>&1 )` pipe, so it flushes at
  # interpreter exit and lands AFTER the summary. Measured output:
  #     .s / ----- / Ran 2 tests in 0.000s / (blank) / OK (skipped=1) / trailing stdout from the test
  # The last-non-empty-line parse took `trailing stdout from the test`, matched no `skipped=`, and
  # reported `2 of 2 vendored test(s) passed` over a test that never executed an assertion.
  st_trailing_body='import unittest


class T(unittest.TestCase):
    def test_a(self):
        print("trailing stdout from the test")
        self.assertTrue(True)

    @unittest.skip("guard fired")
    def test_b(self):
        self.assertEqual(1, 1)
'
  # A $HOME-reaching suite with a PARTIAL skip. `env_skip` was a default-zero expectation that no
  # assertion ever pinned non-zero, so the routing of a machine-caused NOT-TESTED-HERE was uncovered
  # on one of its two counters while the fail side was covered on both.
  st_home_skip_body='import unittest
from pathlib import Path

_WHERE = Path.home()


class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)

    @unittest.skip("guard fired")
    def test_b(self):
        self.assertEqual(1, 1)
'
  # A $HOME-reaching suite where EVERY test skipped: the other env_skip path, and the one the
  # surviving mutation (hoisting the SCOPE restore above these two branches) lands on.
  st_home_allskip_body='import unittest
from pathlib import Path

_WHERE = Path.home()


@unittest.skip("guard fired")
class T(unittest.TestCase):
    def test_a(self):
        self.assertTrue(True)
'
  # A CLASS-LEVEL GUARD THAT FIRES BEFORE ANY TEST STARTS -> `Ran 0 tests` + `OK (skipped=1)`, rc 0.
  # MEASURED on CPython 3.14.6 before this fixture was written, because the branch it drives was
  # added on a reading of `unittest/suite.py` and this card has already had a round where measurement
  # beat reasoning. Note `skipped=1` for a class holding TWO tests: the skip is recorded against an
  # `_ErrorHolder`, so it counts guards and not tests, which is why the branch adds nothing to the
  # test totals. This shape used to be a hard repository FAILURE.
  st_classguard_body='import unittest


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("machine guard fired")

    def test_a(self):
        self.assertTrue(True)

    def test_b(self):
        self.assertTrue(True)
'
  # The same shape reaching $HOME, so the branch's SCOPE handling is pinned as well as its wording:
  # a guard that fired is not a fact about the tree and must not stay on the repository line.
  st_home_classguard_body='import unittest
from pathlib import Path

_WHERE = Path.home()


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("machine guard fired")

    def test_a(self):
        self.assertTrue(True)
'
  # A GUARDED CLASS *BESIDE* A RUNNING TEST — the shape that proves `skipped=` and `Ran N` are in
  # different units, and the fixture the round-3 `execd=$((ran - sk))` had no answer for. MEASURED on
  # CPython 3.14.6: `s.` / `Ran 1 test` / `OK (skipped=1)`, rc 0 — one skip event for a guarded class
  # holding TWO tests, and `ran` counting only `test_3`, which really did execute and pass.
  # `ran - sk` is 0 here, so this used to print "all 1 vendored test(s) were SKIPPED … 0 of 1
  # executed" over a genuine pass.
  st_mixedguard_body='import unittest


class Guarded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("machine guard fired")

    def test_1(self):
        self.assertTrue(True)

    def test_2(self):
        self.assertTrue(True)


class Runs(unittest.TestCase):
    def test_3(self):
        self.assertTrue(True)
'
  # THE SAME SHAPE WITH TWO GUARDED CLASSES, which is the one that went NEGATIVE. MEASURED:
  # `ss.` / `Ran 1 test` / `OK (skipped=2)`, rc 0. `ran - sk` is -1, and the test-level summary
  # printed `tests: -1 of 1 … 2 of 1 were SKIPPED` — a negative filtered count and a numerator above
  # its own total, in one sentence.
  st_twoguard_body='import unittest


class GuardedA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("machine guard fired")

    def test_1(self):
        self.assertTrue(True)


class GuardedB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("machine guard fired")

    def test_2(self):
        self.assertTrue(True)


class Runs(unittest.TestCase):
    def test_3(self):
        self.assertTrue(True)
'
  # mk_skill ROOT NAME — a skill with a SKILL.md and no suite.
  mk_skill() { mkdir -p "$1/$2"; printf '# %s\n' "$2" > "$1/$2/SKILL.md"; }
  # mk_suite ROOT NAME BODY — give an existing fixture skill a suite.
  mk_suite() { mkdir -p "$1/$2/tests"; printf '%s' "$3" > "$1/$2/tests/test_fixture.py"; }

  # expect_suites NAME ROOT WANT_FAIL WANT_SKIP WANT_CNR WANT_ARM [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  #               [WANT_ENV_FAIL] [WANT_ENV_SKIP] [WANT_ENV_CNR] [WANT_ATTRIBUTED_OUT]
  #
  # THE ENV DELTAS ARE ASSERTED TOO, AND DEFAULT TO ZERO. Without them a mutation that routed every
  # suite finding into the machine scope would leave every assertion here green while the repository
  # verdict went permanently silent — and $HOME-scope routing is precisely what this block now
  # contains, so the counter it moves has to be pinned on BOTH sides.
  #
  # AND THE COULD-NOT-RUN SPLIT IS PINNED THE SAME WAY, which it was not when the split was
  # introduced. `could_not_run` is the total the exit arm reads; `repo_cnr`/`env_cnr` are what the
  # two verdict LINES read, and only the total was ever measured. Two mutations survived all fifty
  # assertions as a result: deleting the scope-routing line entirely (production exits 2 while BOTH
  # verdict lines print "no failures in what ran"), and SWAPPING THE ARMS — which restores precisely
  # the mis-attribution the split was added to remove. Only WANT_ENV_CNR is passed, because the
  # repository expectation is DERIVED as WANT_CNR - WANT_ENV_CNR: one number, no way for the two to
  # be stated inconsistently, and every existing call site now asserts the whole total landed on the
  # repository line rather than merely that it landed somewhere.
  expect_suites() {
    [ "$ST_DRY" -eq 0 ] || { st_skipped=$((st_skipped+1)); return 0; }
    local name="$1" root="$2" wf="$3" ws="$4" wc="$5" wa="$6" needle="${7:-}" absent="${8:-}"
    local wef="${9:-0}" wes="${10:-0}" wec="${11:-0}" wao="${12:-0}"
    local f0=$repo_fail s0=$repo_skip c0=$could_not_run ef0=$env_fail es0=$env_skip
    local rc0=$repo_cnr ec0=$env_cnr ao0=$repo_attributed_out
    local df ds dc def des drc dec dao arm why="" st_ln wrc
    check_vendored_suites "$root" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); ds=$((repo_skip - s0)); dc=$((could_not_run - c0))
    def=$((env_fail - ef0)); des=$((env_skip - es0))
    drc=$((repo_cnr - rc0)); dec=$((env_cnr - ec0)); dao=$((repo_attributed_out - ao0))
    wrc=$((wc - wec))
    arm=$(exit_arm "$((df + def))" "$dc")
    # ASCII `!=` and braced parameters, for the reason documented on expect_route: a multibyte
    # character here made `set -u` kill the whole suite on the first delta mismatch.
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$ds" = "$ws" ] || why="$why skip(${ds}!=${ws})"
    [ "$dc" = "$wc" ] || why="$why cnr(${dc}!=${wc})"
    [ "$def" = "$wef" ] || why="$why envfail(${def}!=${wef})"
    [ "$des" = "$wes" ] || why="$why envskip(${des}!=${wes})"
    [ "$drc" = "$wrc" ] || why="$why repocnr(${drc}!=${wrc})"
    [ "$dec" = "$wec" ] || why="$why envcnr(${dec}!=${wec})"
    [ "$dao" = "$wao" ] || why="$why attributedout(${dao}!=${wao})"
    [ "$arm" = "$wa" ] || why="$why exit(${arm}!=${wa})"
    if [ -n "$needle" ] && ! grep -q -- "$needle" "$st_dir/rendered"; then
      why="$why missing:\"$needle\""
    fi
    if [ -n "$absent" ] && grep -q -- "$absent" "$st_dir/rendered"; then
      why="$why must-not-contain:\"$absent\""
    fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s skip+%s cnr+%s(repo %s/env %s) envfail+%s envskip+%s away+%s exit %s\n' \
        "$name" "$df" "$ds" "$dc" "$drc" "$dec" "$def" "$des" "$dao" "$arm"
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
    [ "$ST_DRY" -eq 0 ] || { st_skipped=$((st_skipped+1)); return 0; }
    if [ "$2" -eq 0 ]; then
      printf '  \033[32mok\033[0m    %s\n' "$1"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s — %s\n' "$1" "$3"; st_fail=$((st_fail+1))
    fi
  }
  # NOT-RUN ASSERTIONS ARE A FIRST-CLASS STATE, and the mechanism for them is `st_dry_begin` /
  # `st_dry_end` at the top of this block. The self-test used to have no such state, so a missing
  # prerequisite arrived as arithmetic: without `git`, the declaration fixture's `git init` failed
  # silently, discovery proceeded over the excluded skill, and three assertions reported
  # `fail(1!=0) exit(1!=0)` — reading as "verify.sh is broken" on a machine that merely lacks a tool
  # THE PRODUCTION PATH REPORTS CLEANLY a few hundred lines below. It is loud, it is counted
  # separately, and it is printed in the final line, so it can never be mistaken for coverage.
  #
  # THE COUNT USED TO BE A PARAMETER — `st_skip NAME COUNT WHY` — AND THAT IS THE THIRD TIME THIS
  # ONE NUMBER HAS BEEN WRONG. First `st_skipped` moved by one per GROUP over groups of 3 and 2, so
  # a machine without git printed a denominator of 68 against a real total of 70 — a filtered count
  # whose total MOVES WITH THE NUMERATOR. Then the fix for that declared `5` over a branch holding
  # 4. Then `st_expected_total` pinned the sum, which catches both — BUT ONLY ON A MACHINE THAT
  # TAKES THE BRANCH, and every guard in this suite is false on a machine with python3, git and
  # working mode bits. So the literal is gone and the branch is walked in both directions instead;
  # see the comment on `ST_DRY`. There is no number left here for anyone to get wrong.

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
  #
  #    STATED AS AN INTERVAL, WHICH IS THE ROUND-4 CHANGE. `skipped=1` here is one skip EVENT, and an
  #    event is one test or one whole guarded class; nothing in this stream says which. So the honest
  #    reading of `Ran 2 tests` + `OK (skipped=1)` is "between 1 and 2 executed an assertion", and the
  #    point value `1` this used to print was only right because the fixture happens to use a
  #    decorator. See the SKIP EVENTS block in run_one_suite.
  expect_suites "a skipped test is counted and named, not folded into the passed count" \
    "$st_skip_root" 0 1 0 0 "alpha: between 0 and 1 of 2 vendored test(s) NOT TESTED HERE"
  expect_suites "the passed sentence covers only tests that executed an assertion" \
    "$st_skip_root" 0 1 0 0 "alpha: between 1 and 2 of 2 vendored test(s) passed"
  expect_suites "the test-level summary carries the skip count" \
    "$st_skip_root" 0 1 0 0 "tests:  between 1 and 2 of 2 vendored test(s) actually executed an assertion; between 0 and 1 of 2 were SKIPPED"
  # AND THE INTERVAL IS PINNED AT BOTH ENDS AND IN THE UNIT. Without this, dropping the skip-event
  # term from the summary sentence would leave the two assertions above green while the count that
  # cannot be expressed as a fraction of tests disappeared.
  expect_suites "the summary names the skip-event count and says it is not a count of tests" \
    "$st_skip_root" 0 1 0 0 "1 skip event(s) were reported, and a skip event is one test OR one whole guarded class"
  # POSITIVE CONTROL for that absence: the identical fixture WITHOUT the skip decorator says none of
  # it, says `2 of 2 ... passed` instead, and gets the POINT form of the summary sentence rather than
  # the interval form — which is what pins the two shapes apart.
  expect_suites "control: the same fixture without the skip says nothing about skips" "$st_ok_root" \
    0 0 0 0 "alpha: 2 of 2 vendored test(s) passed" "skip event(s)"

  # ── a suite where EVERY test skipped: `OK (skipped=2)`, exit 0, zero assertions executed. That is
  #    not a pass. It is the whole suite NOT TESTED HERE, and the passed sentence must be absent.
  #
  #    AND THE ROOT IS A SINGLE-SKILL ROOT, SO IT IS ALSO AN ALL-VACUOUS CORPUS, WHICH IS A FINDING.
  #    THESE TWO ASSERTIONS USED TO PIN `fail+0 … exit 0` AND THAT IS THE DEFECT THEY NOW PIN CLOSED.
  #    The pair asserted `0 1 0 0` — no finding, arm 0 — for a run in which every published suite
  #    yielded nothing, which is this file's founding defect read through `$?`: published tests that
  #    nobody runs, reported as a clean gate. A test that asserts a defect is correct is worse than
  #    no test, because it converts the fix into a regression. The per-suite claim each assertion
  #    makes is unchanged and is carried by its needle and its absent-text; what changed is the
  #    delta, which now records that the AGGREGATE is a finding. Every fixture root below that holds
  #    one skill whose only suite is vacuous is corrected the same way and for the same reason.
  st_allskip_root="$st_dir/skills_allskip"
  mk_skill "$st_allskip_root" alpha; mk_suite "$st_allskip_root" alpha "$st_allskip_body"
  expect_suites "a suite where every test skipped is NOT TESTED HERE, never a pass" \
    "$st_allskip_root" 1 1 0 1 "alpha: NOT TESTED HERE — 2 vendored test(s) ran and 2 skip event(s) were reported, so 0 of 2 can be SHOWN to have executed an assertion" "vendored test(s) passed"
  expect_suites "and the summary counts it as ran-only-skips, not as passed" \
    "$st_allskip_root" 1 1 0 1 "0 of 1 suite(s) passed, 0 of 1 failed, 0 of 1 could not run, 1 of 1 yielded no demonstrable assertion" "ran only skips"
  # AND THE FLOOR IS ASSERTED AT ITS OWN LEVEL, not merely as a delta on the two above: a corpus in
  # which not one suite yielded a demonstrable assertion is a FINDING and exit 1, and it says which
  # quantity is zero. Without this, restoring `0 1 0 0` above would put the hole back with nothing
  # naming it.
  expect_suites "a corpus where NOT ONE suite yielded an assertion is a finding, never a clean gate" \
    "$st_allskip_root" 1 1 0 1 "0 of 1 vendored suite(s) under $st_allskip_root yielded a demonstrable assertion"
  # POSITIVE CONTROL, and it is the whole reason the floor is narrowed to the vacuous case: an
  # ordinary root with a passing suite is untouched by it — no finding, arm 0, and the floor's
  # sentence absent. Ordinary skips do not go red; only a corpus that demonstrated nothing does.
  expect_suites "control: the floor does not fire when a suite did yield an assertion" \
    "$st_ok_root" 0 0 0 0 "alpha: 2 of 2 vendored test(s) passed" "yielded a demonstrable assertion"

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
  #    This fixture is a real git checkout because git itself is the parser FOR THE EXCLUSION
  #    QUESTION discovery asks — a bash reimplementation of gitignore matching would be a second
  #    copy of the truth. git is a declared prerequisite of this gate (see --help), so requiring it
  #    here is not a new dependency. It is NOT the parser for the roster: `git check-ignore` will
  #    not call a tracked path ignored, so `skill_roster` reads the declaration itself, in a strict
  #    `!/name` subset that refuses what it cannot interpret. Two questions, two readers, and the
  #    reason they are not one is measured rather than assumed — see the comment on skill_roster.
  #
  #    GIT IS A PREREQUISITE OF THESE THREE ASSERTIONS, AND ITS ABSENCE IS NOW REPORTED AS ONE. It
  #    used to arrive as arithmetic: no git meant `git init` failed silently, `can_read_decl=0`,
  #    graphify was discovered and its failing suite ran, and three assertions printed
  #    `fail(1!=0) exit(1!=0)` — which reads as "verify.sh is broken" rather than "this machine has
  #    no git", on a machine whose git absence the PRODUCTION path reports in one clean sentence.
  st_decl_root="$st_dir/skills_decl"
  st_have_git=0
  if command -v git >/dev/null 2>&1; then
    mk_skill "$st_decl_root" alpha;    mk_suite "$st_decl_root" alpha "$st_pass_body"
    mk_skill "$st_decl_root" graphify; mk_suite "$st_decl_root" graphify "$st_fail_body"
    printf '/*\n!/.gitignore\n!/alpha\n' > "$st_decl_root/.gitignore"
    # The init is CHECKED, not fired and hoped for. A silent failure here is what turned a missing
    # prerequisite into three misleading assertion failures.
    if git -C "$st_decl_root" init -q >/dev/null 2>&1 \
       && git -C "$st_decl_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      st_have_git=1
    fi
  fi
  [ "$st_have_git" -eq 1 ] || st_dry_begin "discovery honours the publication declaration" \
    "git is unavailable or could not initialise a checkout, and git IS the gitignore parser here — the alternative was a second gitignore implementation in bash. Production reports git's absence cleanly; this is the self-test declining to fabricate a fixture, not a defect"
  # graphify is declared unpublished, so its FAILING suite must never be discovered, never run, and
  # never reach a counter. Without the declaration it would be a fatal failure over a skill this
  # repository says it does not publish.
  expect_suites "a skill the declaration excludes is not discovered and its suite is not run" \
    "$st_decl_root" 0 0 0 0 "graphify: EXCLUDED and not discovered" "the vendored suite FAILED"
  expect_suites "and the excluded count is reported beside the discovered total" \
    "$st_decl_root" 0 0 0 0 "1 skill(s) discovered (1 excluded by the publication declaration), 1 with a vendored suite"
  # POSITIVE CONTROL: with the declaration removed, the same tree discovers graphify and its failing
  # suite goes red. Without this, a mutation that simply skipped every skill would pass the two above.
  # Guarded on the fixture rather than on `ST_DRY`: in the not-run walk the fixture was never built,
  # and `rm` on an absent path would print an error into a suite that is meant to be silent here.
  # ST_DRY-SIDE-EFFECT: conditional, and its condition is FALSE on the dry walk — the fixture was
  # never built, so this removes nothing. Marked anyway: the range check reads what the line IS, not
  # what it does, and a marker is cheaper than a reader having to re-derive that argument.
  [ -f "$st_decl_root/.gitignore" ] && rm "$st_decl_root/.gitignore"
  expect_suites "control: remove the declaration and the same excluded suite is discovered and fails" \
    "$st_decl_root" 1 0 0 1 "graphify: the vendored suite FAILED" "EXCLUDED and not discovered"
  st_dry_end
  # And the DEGRADED path: outside a checkout the declaration cannot be read, which is reported
  # rather than silently treated as "nothing is excluded". Every other fixture root in this block is
  # a bare mktemp directory, so this warning was firing throughout, unpinned by anything.
  #
  # ITS PREMISE IS ESTABLISHED ONCE, AT `$st_dir`, NOT GUARDED HERE. This assertion needs
  # `$st_ok_root` to be outside a git work tree; `st_root_ok` proved that of `$st_dir` at creation and
  # refused to continue otherwise, and inside-a-work-tree is inherited by every child, so the premise
  # holds for every fixture root in this block rather than for this one assertion. The round that
  # guarded it HERE fixed one spurious FAIL and left the forty-five assertions with the inverse
  # premise unprotected; a guard that could never fire now would be worse than none.
  #
  # THE NEEDLE SAYS "COULD NOT APPLY", NOT "COULD NOT BE READ", and the change is the point rather
  # than a rewording. The old sentence was false in the same run that printed it: the presence check
  # reads that same declaration with no git involved and prints a count from it, so one run said
  # both "the declaration could NOT be read" and "6 of 6 declared skill(s) present". What git cannot
  # do here is APPLY the exclusion; reading is a separate faculty and it still works.
  expect_suites "an inapplicable declaration is reported, not treated as an empty one" "$st_ok_root" \
    0 0 0 0 "git could not apply install/skills/.gitignore to this tree" \
    "could NOT be read"

  # ── (row 2) A SUITE WHOSE OWN SOURCE READS $HOME IS NOT FATAL TO THE *REPOSITORY* VERDICT.
  #    Reason 3 of the drift-gate comment, applied: one operand is $HOME, so the answer is a property
  #    of the machine. The failure is still counted and still selects exit 1 — it moves scope, it
  #    does not soften. The pair of assertions below is the whole claim: repo_fail must NOT move,
  #    env_fail MUST, and the arm must still be 1.
  st_home_root="$st_dir/skills_home"
  mk_skill "$st_home_root" zeta; mk_suite "$st_home_root" zeta "$st_home_fail_body"
  expect_suites "a \$HOME-reaching suite's failure lands on the MACHINE line, not the repository's" \
    "$st_home_root" 0 0 0 1 "zeta: the vendored suite FAILED" "" 1 0 0 1
  expect_suites "and it says why it was attributed to the machine" \
    "$st_home_root" 0 0 0 1 "counted against THIS MACHINE, not this repository" "" 1 0 0 1
  # POSITIVE CONTROL: the same failure shape in a suite that does NOT read $HOME stays on the
  # repository line. Without this, routing everything to env would satisfy the two above.
  expect_suites "control: a failing suite that does not read \$HOME stays on the repository line" \
    "$st_fail_root" 1 0 0 1 "beta: the vendored suite FAILED" "counted against THIS MACHINE" 0 0 0 0

  # ── (F4) `env_skip` PINNED NON-ZERO, ON BOTH PATHS THAT MOVE IT. It was a default-zero expectation
  #    that no assertion anywhere pinned above zero, so half of the routing the comment on
  #    expect_suites claims to have closed was in fact uncovered. The surviving mutation: hoist
  #    `SCOPE="$saved_scope"` above the `elif [ "$exec_lo" -le 0 ]` and partial-skip branches,
  #    putting a machine-caused NOT-TESTED-HERE onto the repository line. Both assertions below
  #    require skip+0 AND envskip+1, so the mutation moves both deltas and is caught twice.
  st_home_skip_root="$st_dir/skills_home_skip"
  mk_skill "$st_home_skip_root" zeta; mk_suite "$st_home_skip_root" zeta "$st_home_skip_body"
  expect_suites "a \$HOME-reaching suite's PARTIAL skip lands on the machine line, and is marked away from the repository's" \
    "$st_home_skip_root" 0 0 0 0 "zeta: between 0 and 1 of 2 vendored test(s) NOT TESTED HERE" "" 0 1 0 1
  st_home_allskip_root="$st_dir/skills_home_allskip"
  mk_skill "$st_home_allskip_root" zeta; mk_suite "$st_home_allskip_root" zeta "$st_home_allskip_body"
  # Single-skill, all-vacuous: the floor fires, on the REPOSITORY line, while the per-suite skip
  # stays on the machine line — `fail+1` with `envskip+1` and `away+1`, which is the pairing that
  # pins both facts at once. The routing is deliberate and argued at the floor itself: per suite a
  # fired guard is a machine fact, but "this run demonstrated nothing" is a fact about the corpus
  # this repository publishes, and the mutation that moved the per-suite skip back onto the
  # repository line is still caught, because `envskip` and `away` would move with it.
  expect_suites "a \$HOME-reaching suite that skipped ENTIRELY lands on the machine line too" \
    "$st_home_allskip_root" 1 0 0 1 "zeta: NOT TESTED HERE — 1 vendored test(s) ran and 1 skip event(s) were reported" "vendored test(s) passed" 0 1 0 1
  # POSITIVE CONTROL for both: the same two skip shapes in suites that do NOT read $HOME stay on the
  # repository line — skip+1, envskip+0, and nothing attributed away. `st_skip_root` and
  # `st_allskip_root` above already assert exactly that with the defaults, so the control is the
  # pairing itself; restated here explicitly so the pair cannot be separated by a later edit.
  expect_suites "control: the same partial skip without \$HOME stays on the repository line" \
    "$st_skip_root" 0 1 0 0 "alpha: between 0 and 1 of 2 vendored test(s) NOT TESTED HERE" "" 0 0 0 0

  # ── (F1) THE REPOSITORY LINE SAYS WHAT WAS TAKEN OFF IT. The routing above was directed and is
  #    right; the SILENCE it left on the repository line was not. With every suite finding moved to
  #    the machine scope, the repository verdict printed
  #      PASS this repository — vendored tree — no failures in what ran, but N check(s) did NOT run
  #    byte-identical to a fully green run, and identical again to a run with a vendored script
  #    broken outright and hundreds of tests red. The tally is asserted above on every $HOME
  #    fixture; here the RENDERED LINE is asserted, because a counter nobody prints is not a fix.
  st_v_away=$(verdict_line "this repository — vendored tree" 0 0 4 0 2)
  st_v_clean=$(verdict_line "this repository — vendored tree" 0 0 4 0 0)
  case "$st_v_away" in
    *"were attributed to THIS MACHINE"*) st_rc=0 ;;
    *) st_rc=1 ;;
  esac
  st_assert "the repository verdict line reports findings attributed to the machine" "$st_rc" \
    "rendered without the marker: $st_v_away"
  # THE WHOLE POINT, ASSERTED AS THE POINT: the two lines must not be the same bytes. Same failure
  # count, same skip count, same warning count — only the attribution differs.
  st_rc=0; [ "$st_v_away" = "$st_v_clean" ] && st_rc=1
  st_assert "a run with findings attributed away is DISTINGUISHABLE from a clean one on the repository line" \
    "$st_rc" "both rendered as: $st_v_clean"
  # And a line with nothing attributed away must not claim "every check ran and passed" when
  # something was. The zero-skip case is the one that would otherwise print the strongest sentence.
  st_v_strong=$(verdict_line "x" 0 0 0 0 1)
  case "$st_v_strong" in
    *"every check ran and passed"*) st_rc=1 ;;
    *) st_rc=0 ;;
  esac
  st_assert "a verdict line with findings attributed away never claims every check ran and passed" \
    "$st_rc" "rendered as: $st_v_strong"

  # ── (F1, LAST LINK) THE JOIN: WHICH COUNTER REACHES WHICH LINE. The three assertions above call
  #    `verdict_line` with LITERALS and `expect_suites` pins the counters, so between them they cover
  #    the renderer and the tally and nothing at all in between. `--self-test` exits before the
  #    verdict block at the bottom of the file, so while the two calls lived down there they were
  #    unreachable from every assertion in this suite — measured: changing `"$repo_cnr"` to `0`, or to
  #    `"$env_cnr"`, kept the suite at 70 of 70 while the repository line went back to being
  #    byte-identical to a green run. Moving `verdict_line` up made the FUNCTION testable and left its
  #    INVOCATION as the untestable thing; this pins the invocation.
  #
  #    NINE PAIRWISE-DISTINCT FIXTURE VALUES, which is the whole method. Every counter is a different
  #    number, so any swap between two of them, any constant substituted for one, and any label
  #    exchanged between the lines changes a digit in the rendered output. Values are chosen so both
  #    lines take the could-not-run arm, which is the only arm that prints all four counts at once.
  st_sv="$repo_fail:$repo_warn:$repo_skip:$repo_cnr:$repo_attributed_out:$env_fail:$env_warn:$env_skip:$env_cnr:$could_not_run"
  repo_fail=11; repo_warn=12; repo_skip=13; repo_cnr=14; repo_attributed_out=15
  env_fail=21;  env_warn=22;  env_skip=23;  env_cnr=24
  could_not_run=38
  st_v_out=$(render_verdicts)
  st_v_l1=""; st_v_l2=""; st_v_n=0
  while IFS= read -r st_ln4; do
    st_v_n=$((st_v_n+1))
    [ "$st_v_n" -eq 1 ] && st_v_l1="$st_ln4"
    [ "$st_v_n" -eq 2 ] && st_v_l2="$st_ln4"
  done <<< "$st_v_out"
  st_rc=1; [ "$st_v_n" -eq 2 ] && st_rc=0
  st_assert "the verdict renders exactly two lines, one per question" "$st_rc" \
    "rendered $st_v_n line(s); the two questions must never share a verdict line and must both appear"
  case "$st_v_l1" in
    *"this repository — vendored tree — 14 check(s) could not be executed at all; 11 problem(s), 12 warning(s), 13 not run in total; and 15 finding(s) or not-run check(s) from this scope were attributed to THIS MACHINE"*) st_rc=0 ;;
    *) st_rc=1 ;;
  esac
  st_assert "every repository counter reaches its own slot on the repository verdict line" "$st_rc" \
    "with repo fail/warn/skip/cnr/away = 11/12/13/14/15 the line rendered as: $st_v_l1"
  case "$st_v_l2" in
    *"this machine    — installed layer — 24 check(s) could not be executed at all; 21 problem(s), 22 warning(s), 23 not run in total"*) st_rc=0 ;;
    *) st_rc=1 ;;
  esac
  st_assert "every machine counter reaches its own slot on the machine verdict line" "$st_rc" \
    "with env fail/warn/skip/cnr = 21/22/23/24 the line rendered as: $st_v_l2"
  # Attribution runs one way only. If the repository line's marker ever reached the machine line the
  # same finding would be announced twice, and the two verdicts would overlap again.
  case "$st_v_l2" in
    *"attributed to THIS MACHINE"*) st_rc=1 ;;
    *) st_rc=0 ;;
  esac
  st_assert "the machine line is never itself marked with findings attributed away" "$st_rc" \
    "rendered as: $st_v_l2"

  # ── AND THE SUMMARY'S JOIN, WHICH HAS THE SAME SHAPE: which counters are summed into the totals,
  #    and whether the sentence and the exit code agree. Same reasoning as extracting `exit_arm`,
  #    applied to the one caller of it that no assertion could reach. All three arms, each asserting
  #    the TEXT and the RETURNED CODE in one condition — a PASS sentence above an `exit 1` is the
  #    defect, and it is only visible when the pair is asserted together.
  st_sum=$(render_summary); st_rc2=$?
  st_rc=1
  case "$st_sum" in
    *"COULD NOT RUN — 38 check(s) could not be executed"*"(32 problem(s), 34 warning(s), 36 check(s) not run)"*)
      [ "$st_rc2" -eq 2 ] && st_rc=0 ;;
  esac
  st_assert "the summary totals both scopes and returns 2 when something could not run" "$st_rc" \
    "returned $st_rc2 and rendered: $st_sum"
  could_not_run=0
  st_sum=$(render_summary); st_rc2=$?
  st_rc=1
  case "$st_sum" in
    *"FAIL — 32 problem(s), 34 warning(s), 36 check(s) not run"*) [ "$st_rc2" -eq 1 ] && st_rc=0 ;;
  esac
  st_assert "the summary totals both scopes and returns 1 when something failed" "$st_rc" \
    "returned $st_rc2 and rendered: $st_sum"
  # The machine's failures must reach the total too: with only the repository's zeroed, a summary
  # reading `repo_fail` alone would print PASS over a failing machine.
  repo_fail=0
  st_sum=$(render_summary); st_rc2=$?
  st_rc=1
  case "$st_sum" in
    *"FAIL — 21 problem(s), 34 warning(s), 36 check(s) not run"*) [ "$st_rc2" -eq 1 ] && st_rc=0 ;;
  esac
  st_assert "a failure in the machine scope alone still fails the summary" "$st_rc" \
    "returned $st_rc2 and rendered: $st_sum"
  env_fail=0
  st_sum=$(render_summary); st_rc2=$?
  st_rc=1
  case "$st_sum" in
    *"PASS — 34 warning(s) and 36 check(s) not run, none fatal"*) [ "$st_rc2" -eq 0 ] && st_rc=0 ;;
  esac
  st_assert "with nothing failed and nothing unrun the summary passes and returns 0" "$st_rc" \
    "returned $st_rc2 and rendered: $st_sum"
  # Restored, because every assertion after this point measures counter DELTAS and would otherwise be
  # measuring deltas from a fixture.
  IFS=: read -r repo_fail repo_warn repo_skip repo_cnr repo_attributed_out \
                env_fail env_warn env_skip env_cnr could_not_run <<< "$st_sv"

  # ── (F2) A SUITE THAT EMITS AFTER ITS OWN SUMMARY. The parse used to take the LAST NON-EMPTY LINE
  #    of merged stdout+stderr and call it unittest's trailing line. They differ whenever anything
  #    reaches either stream after the summary — a test's own `print` (stdout is block-buffered
  #    through the capture pipe and flushes at interpreter exit, AFTER unittest's stderr summary), a
  #    ResourceWarning, an `Exception ignored in:`. The parse then silently yielded sk=0.
  #    NO VENDORED SUITE DOES THIS TODAY, which is exactly why the fixture had to be written: the
  #    defect could not have gone red on the real tree, and --self-test could not have noticed.
  st_trail_root="$st_dir/skills_trailing"
  mk_skill "$st_trail_root" alpha; mk_suite "$st_trail_root" alpha "$st_trailing_body"
  # First, prove the FIXTURE actually reproduces the condition — that the last line of the captured
  # stream really is the test's print and not unittest's summary. Without this the assertions below
  # could pass on a Python that happened to flush in the other order, and prove nothing.
  st_trail_out=$( cd "$st_trail_root/alpha" && PYTHONDONTWRITEBYTECODE=1 "$SUITE_PY" -m unittest discover -s tests -t tests 2>&1 )
  st_trail_tail=""
  while IFS= read -r st_ln2; do [ -n "$st_ln2" ] && st_trail_tail="$st_ln2"; done <<< "$st_trail_out"
  st_rc=1; [ "$st_trail_tail" = "trailing stdout from the test" ] && st_rc=0
  st_assert "control: the fixture really does emit after unittest's summary" "$st_rc" \
    "last line was \`$st_trail_tail\`, not the test's print — the fixture does not reproduce the condition, so the assertions below prove nothing"
  # The skip is still seen. Under the old parse this root reported `2 of 2 vendored test(s) passed`,
  # skip+0, and the test-level summary said `0 of 2 were SKIPPED`.
  expect_suites "a skip is still counted when the suite emits after its own summary" \
    "$st_trail_root" 0 1 0 0 "alpha: between 0 and 1 of 2 vendored test(s) NOT TESTED HERE"
  expect_suites "and the passed sentence does not absorb it" \
    "$st_trail_root" 0 1 0 0 "alpha: between 1 and 2 of 2 vendored test(s) passed" "alpha: 2 of 2 vendored test(s) passed"
  expect_suites "and the test-level summary is not silently zero" \
    "$st_trail_root" 0 1 0 0 "tests:  between 1 and 2 of 2 vendored test(s) actually executed an assertion; between 0 and 1 of 2 were SKIPPED"
  # POSITIVE CONTROL: the identical fixture WITHOUT the trailing emission. Same counts, so the
  # assertions above are measuring the parse anchoring and not the fixture's skip decorator.
  expect_suites "control: the same fixture without the trailing emission reports the same skip" \
    "$st_skip_root" 0 1 0 0 "alpha: between 0 and 1 of 2 vendored test(s) NOT TESTED HERE"

  # ── (F2, second half) RAN, BUT NO RECOGNISABLE RESULT LINE, IS COULD-NOT-RUN — NEVER sk=0. Driven
  #    through a stub runner rather than through unittest, because real unittest cannot be made to
  #    emit `Ran N tests` with no `OK`/`FAILED` after it. What is under test is the PARSE, and the
  #    parse's input is a stream, so a stream is what the fixture supplies.
  cat > "$st_dir/stub_runner" <<'STUB'
#!/bin/sh
printf '.\n'
printf -- '----------------------------------------------------------------------\n'
printf 'Ran 2 tests in 0.001s\n'
printf '\n'
printf 'some shape this parser does not recognise\n'
STUB
  chmod 755 "$st_dir/stub_runner"
  st_saved_py2="$SUITE_PY"
  SUITE_PY="$st_dir/stub_runner"
  expect_suites "a suite that ran but produced no recognisable result line is COULD NOT RUN, not zero skips" \
    "$st_ok_root" 0 1 1 2 "produced NO RECOGNISABLE RESULT LINE" "vendored test(s) passed"
  expect_suites "and it is counted as a could-not-run against its total, not as a pass" \
    "$st_ok_root" 0 1 1 2 "0 of 1 suite(s) passed, 0 of 1 failed, 1 of 1 could not run"
  # POSITIVE CONTROL: the same stub with a result line appended parses cleanly and is NOT a
  # could-not-run — so the assertions above are about the missing result line and not about the stub.
  cat > "$st_dir/stub_runner" <<'STUB'
#!/bin/sh
printf '.s\n'
printf -- '----------------------------------------------------------------------\n'
printf 'Ran 2 tests in 0.001s\n'
printf '\n'
printf 'OK (skipped=1)\n'
printf 'and then something after the summary\n'
STUB
  chmod 755 "$st_dir/stub_runner"
  expect_suites "control: the same stub WITH a result line parses, and the trailing emission is ignored" \
    "$st_ok_root" 0 1 0 0 "alpha: between 0 and 1 of 2 vendored test(s) NOT TESTED HERE" "COULD NOT RUN"
  SUITE_PY="$st_saved_py2"

  # ── (F3) THE COULD-NOT-RUN SPLIT IS PINNED ON THE ENV SIDE, which no assertion did: `repo_cnr`
  #    and `env_cnr` were written at one place and read only by the verdict lines, so deleting the
  #    routing line — or SWAPPING ITS ARMS — survived every assertion. The repo side is now pinned
  #    by every call above (WANT_CNR - WANT_ENV_CNR); this fixture pins the env side non-zero, which
  #    is what makes the swap detectable rather than merely the deletion.
  st_home_cnr_root="$st_dir/skills_home_cnr"
  mk_skill "$st_home_cnr_root" zeta; mk_suite "$st_home_cnr_root" zeta "$st_home_fail_body"
  st_saved_py3="$SUITE_PY"
  SUITE_PY="$st_dir/no-such-interpreter"
  expect_suites "a \$HOME-reaching suite that CANNOT RUN counts its could-not-run on the machine line" \
    "$st_home_cnr_root" 0 0 1 2 "COULD NOT RUN" "" 0 1 1 1
  SUITE_PY="$st_saved_py3"

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

  # ── (F5) A `tests/` DIRECTORY THAT EXISTS BUT CANNOT BE READ IS NOT "NO SUITE". The predicate was
  #    `[ -d tests ] && has_test_file tests`, and an unreadable directory fails the second half
  #    exactly as a missing one does — printing `NOT TESTED HERE — no vendored test suite`, a false
  #    sentence, over a suite sitting right there. The floor guard does NOT cover it: the floor fires
  #    only when suites_with == 0 across all skills, so one unreadable tests/ beside one readable one
  #    produced no finding at all. The fixture root below is exactly that shape.
  st_unread_root="$st_dir/skills_unreadable"
  mk_skill "$st_unread_root" alpha; mk_suite "$st_unread_root" alpha "$st_pass_body"
  mk_skill "$st_unread_root" beta;  mk_suite "$st_unread_root" beta  "$st_pass_body"
  chmod 000 "$st_unread_root/beta/tests" 2>/dev/null
  # The chmod is CHECKED, not assumed: as root, or on a filesystem that ignores mode bits, the
  # directory stays readable and the fixture does not reproduce the condition. Asserting on a
  # fixture that did not take is how a green suite comes to mean nothing.
  if [ -r "$st_unread_root/beta/tests" ] && [ -x "$st_unread_root/beta/tests" ]; then
    st_dry_begin "an unreadable tests/ is COULD NOT RUN, not 'no vendored test suite'" \
      "chmod 000 did not take on this filesystem (running as root, or mode bits ignored), so the fixture does not reproduce the condition"
  fi
  expect_suites "an unreadable tests/ is COULD NOT RUN, never a false 'no vendored test suite'" \
    "$st_unread_root" 0 1 1 2 "beta: the vendored suite COULD NOT RUN — beta/tests exists but it, or a directory beneath it, cannot be read" "beta: NOT TESTED HERE — no vendored test suite"
  # It is counted as a skill WITH a suite, so it cannot drag suites_with to zero and trip the
  # FLOOR instead — a loud finding, but the wrong one, naming the tree rather than the directory.
  expect_suites "and it is counted against the with-a-suite total, not routed into the floor" \
    "$st_unread_root" 0 1 1 2 "2 with a vendored suite, 0 NOT TESTED HERE" "NOT ONE has a test suite"
  st_dry_end
  # POSITIVE CONTROL for the absence claim above: with the mode restored, the same root says nothing
  # about could-not-run and both suites pass. Without it, a mutation reporting nothing at all would
  # satisfy the "must not contain" halves.
  chmod 755 "$st_unread_root/beta/tests" 2>/dev/null
  expect_suites "control: with the mode restored the same root passes and says nothing about COULD NOT RUN" \
    "$st_unread_root" 0 0 0 0 "2 of 2 suite(s) passed" "COULD NOT RUN"

  # ── (F5, ONE LEVEL DOWN) AN UNREADABLE *SUB*DIRECTORY OF `tests/`. The previous round fixed the
  #    conflation at the top of the walk only: `suite_dir_state` probed `-r`/`-x` on `<skill>/tests`
  #    and `has_test_file` recursed by glob, where an unreadable subdirectory simply contributes no
  #    match. So `tests/` readable + `tests/unit/` at mode 000 holding the only `test*.py` returned
  #    `none` and printed the SAME false `NOT TESTED HERE — no vendored test suite` sentence the fix
  #    was written to remove, with no finding and no floor. The three-outcome return code now carries
  #    the unknown out of the recursion, so this root is a could-not-run at any depth.
  st_deep_root="$st_dir/skills_deep_unreadable"
  mk_skill "$st_deep_root" alpha; mk_suite "$st_deep_root" alpha "$st_pass_body"
  mk_skill "$st_deep_root" beta
  mkdir -p "$st_deep_root/beta/tests/unit"
  printf '%s' "$st_pass_body" > "$st_deep_root/beta/tests/unit/test_x.py"
  chmod 000 "$st_deep_root/beta/tests/unit" 2>/dev/null
  # Checked, not assumed, for the same reason as the top-level fixture above.
  # THE ONE DRY WALK THAT WRITES, said here rather than left to be discovered: the `zz` fixture below
  # cannot be hoisted above the guard, because the FIRST assertion requires the tree without it. So a
  # not-run walk of this branch does create three files under the temp root. That is a mkdir and two
  # writes into a directory built above the guard — not the `chmod` this guard exists for, and not
  # repeatable work — so the walk stays free of the condition it declined. Each of the three carries
  # an `# ST_DRY-SIDE-EFFECT:` marker, which is what makes this paragraph a claim the suite checks
  # rather than one it merely states; the ST_DRY header names this exception and the one other.
  if [ -r "$st_deep_root/beta/tests/unit" ] && [ -x "$st_deep_root/beta/tests/unit" ]; then
    st_dry_begin "an unreadable subdirectory of tests/ is COULD NOT RUN, not 'no vendored test suite'" \
      "chmod 000 did not take on this filesystem (running as root, or mode bits ignored), so the fixture does not reproduce the condition"
  fi
    expect_suites "an unreadable SUBdirectory of tests/ is COULD NOT RUN, never a false 'no vendored test suite'" \
      "$st_deep_root" 0 1 1 2 "beta: the vendored suite COULD NOT RUN — beta/tests exists but it, or a directory beneath it, cannot be read" "beta: NOT TESTED HERE — no vendored test suite"
    # A READABLE suite elsewhere in the same tests/ tree OUTRANKS the unreadable sibling: there is a
    # suite, it can be run, and the run is the evidence. Without this, "unknown anywhere wins" would
    # turn a perfectly runnable suite with one locked scratch directory into a could-not-run.
    # THE MATCH IS PUT IN A SIBLING SUBDIRECTORY SORTING *AFTER* `unit`, AND THAT IS NOT COSMETIC.
    # A `test*.py` at the top of `tests/` matches before the recursion begins, so a control built that
    # way is satisfied without the walk ever reaching the unreadable directory — it would pass under a
    # mutation that returns unknown the moment it meets one. `unit` < `zz`, so the unreadable
    # directory is visited FIRST and the later match has to actually outrank it.
    # `__init__.py` so `unittest discover` can actually IMPORT it. Without it the walk still finds a
    # `test*.py` and calls the skill "has a suite" — correct, and the over-matching this file prefers
    # — but discovery then collects nothing and the assertion would be measuring the resulting
    # `ran 0 tests` finding instead of the ordering it exists to pin. Measured: with the package
    # marker present, discovery runs the readable suite and steps over the mode-000 sibling cleanly.
    # ST_DRY-SIDE-EFFECT: the one fixture that cannot be hoisted above its guard, so a dry walk of
    # this region does create it. See the ST_DRY header for why that is disclosed rather than fixed.
    mkdir -p "$st_deep_root/beta/tests/zz"
    # ST_DRY-SIDE-EFFECT: as above — an empty package marker under the same fixture.
    : > "$st_deep_root/beta/tests/zz/__init__.py"
    # ST_DRY-SIDE-EFFECT: as above — the readable suite the ordering control needs.
    printf '%s' "$st_pass_body" > "$st_deep_root/beta/tests/zz/test_y.py"
    expect_suites "control: a readable suite AFTER the unreadable subdirectory still outranks it" \
      "$st_deep_root" 0 0 0 0 "2 of 2 suite(s) passed" "COULD NOT RUN"
  st_dry_end
  chmod 755 "$st_deep_root/beta/tests/unit" 2>/dev/null

  # ── (F2, round 3) `Ran 0 tests` + `OK (skipped=N)` IS A GUARD THAT FIRED, NOT A REPOSITORY FAILURE.
  #    A `setUpClass`/`setUpModule` raising `unittest.SkipTest` records the skip against an
  #    `_ErrorHolder` without `startTest`, so `testsRun` stays 0 while the result line reads
  #    `OK (skipped=1)`. verify.sh read the 0 and ignored the result line, printing
  #    `discovery ran 0 tests — a suite that runs nothing is not a passing suite`: a HARD REPOSITORY
  #    FAILURE, exit 1, over a machine-keyed guard, while discarding the line that said otherwise.
  #    Worse than the silence F1 was about — a verdict saying the opposite of what it read.
  #
  #    THE FIXTURE'S PREMISE IS ASSERTED FIRST. If this interpreter emitted `Ran 2 tests` instead, the
  #    assertions below would be measuring the ordinary all-skipped path and proving nothing about
  #    this branch. Measured on CPython 3.14.6: `Ran 0 tests` / `OK (skipped=1)` / rc 0.
  st_guard_root="$st_dir/skills_classguard"
  mk_skill "$st_guard_root" alpha; mk_suite "$st_guard_root" alpha "$st_classguard_body"
  st_guard_out=$( cd "$st_guard_root/alpha" && PYTHONDONTWRITEBYTECODE=1 "$SUITE_PY" -m unittest discover -s tests -t tests 2>&1 )
  st_rc=1
  case "$st_guard_out" in
    *"Ran 0 test"*) case "$st_guard_out" in *"skipped="*) st_rc=0 ;; esac ;;
  esac
  st_assert "control: a setUpClass SkipTest really does emit \`Ran 0 tests\` with a skipped result line" \
    "$st_rc" "this interpreter emitted something else, so the assertions below are not exercising the ran-0-with-skips branch: $st_guard_out"
  #    AND THE `fail+1 … exit 1` IN THESE FOUR VECTORS IS THE FLOOR, NOT THIS BRANCH. This is a
  #    single-skill root, so it is also an all-vacuous corpus. The claim these assertions exist to
  #    make — that the GUARD is not a repository failure — is carried by the absent-text below, which
  #    pins the `ran 0 tests` failure sentence out of the output; the delta records the separate,
  #    aggregate finding that nothing in this corpus demonstrated an assertion. The two are different
  #    claims and the assertion names now say which is which, because `0 1 0 0` here used to mean
  #    "an entire corpus yielded nothing and the gate exited 0".
  expect_suites "a class-level guard that fires before any test is NOT TESTED HERE, never the ran-0 repository failure" \
    "$st_guard_root" 1 1 0 1 "alpha: NOT TESTED HERE — discovery ran 0 test(s) because 1 class- or module-level guard(s) raised SkipTest" "a suite that runs nothing is not a passing suite"
  # The guard count is not a test count and must not reach the test totals: a skip-event count moving
  # while `suites_tests` did not would print `-1 of 0` in the test-level summary.
  expect_suites "and the guard count does not leak into the test-level totals" \
    "$st_guard_root" 1 1 0 1 "tests:  0 of 0 vendored test(s) actually executed an assertion; 0 of 0 were SKIPPED"
  # AND IT IS STILL COUNTED, IN THE UNIT THAT IS NOT TESTS. The two facts are easy to confuse and the
  # counter used to satisfy the first by failing the second: `suites_skipevents` was fed only from the
  # general arm, so this branch — the paradigm case of an event that is not a test — contributed
  # nothing, and the run reported fewer events than occurred.
  expect_suites "and the guard IS counted as a skip event, which is not a test count" \
    "$st_guard_root" 1 1 0 1 "1 skip event(s) were reported, and a skip event is one test OR one whole guarded class"
  # THE TRAP THAT FIX CREATES, PINNED AS AN ABSENCE. Once the event count can be non-zero while the
  # test interval is a point, a shape selector keyed on the event count sends this root to the
  # interval form and prints `between 0 and 0 of 0` — a bound whose ends coincide over a population
  # of nothing. The selector keys on `suites_exec_lo -eq suites_tests` instead, and this is what says
  # so; the needle above would stay green through that regression on its own.
  expect_suites "and a guard-only run keeps the POINT form rather than bounding a population of nothing" \
    "$st_guard_root" 1 1 0 1 "tests:  0 of 0 vendored test(s)" "between 0 and 0"
  # ── (row 1, round 5) BOTH SHAPES IN ONE ROOT, WHICH NO ASSERTION HELD BEFORE. Every fixture above
  #    is homogeneous: a root is all method-skips or all guards, so the aggregate can be right about
  #    one arm while contributing nothing from the other and no needle can tell. `alpha` is
  #    `st_skip_body` (`Ran 2` / `OK (skipped=1)`, the general arm) and `beta` is `st_classguard_body`
  #    (`Ran 0` / `OK (skipped=1)`, the guard branch). TWO events occur. Fed only from the general
  #    arm the line said `1 skip event(s) were reported` — an undercount printed with no denominator,
  #    so nothing in the sentence lets a reader catch it. Both fixture shapes have had their premises
  #    asserted against this interpreter above, so this root needs no third control.
  #
  #    PINNED IN BOTH DIRECTIONS. The present needle is the true total; the absent needle is the
  #    undercount specifically, so the assertion fails on a regression rather than merely on the
  #    sentence disappearing — and the test-level interval needle proves the sentence was rendered.
  st_bothk_root="$st_dir/skills_bothkinds"
  mk_skill "$st_bothk_root" alpha; mk_suite "$st_bothk_root" alpha "$st_skip_body"
  mk_skill "$st_bothk_root" beta;  mk_suite "$st_bothk_root" beta  "$st_classguard_body"
  expect_suites "a run holding BOTH skip shapes counts every event, not just the general arm's" \
    "$st_bothk_root" 0 2 0 0 "— 2 skip event(s) were reported" "1 skip event(s) were reported"
  expect_suites "and the test interval covers only the arm that has tests in it" \
    "$st_bothk_root" 0 2 0 0 "tests:  between 1 and 2 of 2 vendored test(s) actually executed an assertion; between 0 and 1 of 2 were SKIPPED"
  # POSITIVE CONTROL: `Ran 0 tests` WITHOUT skips is still a hard failure. Without this, routing every
  # ran-0 to a skip would satisfy the two above and delete the check entirely. The stub supplies the
  # stream because real unittest will not emit `Ran 0 tests` + a bare `OK` for a non-empty suite.
  cat > "$st_dir/stub_zero" <<'STUB'
#!/bin/sh
printf -- '----------------------------------------------------------------------\n'
printf 'Ran 0 tests in 0.000s\n'
printf '\n'
printf 'OK\n'
STUB
  chmod 755 "$st_dir/stub_zero"
  st_saved_py4="$SUITE_PY"
  SUITE_PY="$st_dir/stub_zero"
  expect_suites "control: ran 0 tests and skipped NONE is still a repository failure" \
    "$st_ok_root" 1 0 0 1 "discovery ran 0 tests and skipped none" "NOT TESTED HERE — discovery ran 0 test(s)"
  # AND `Ran 0 test…` WITH NO RESULT LINE AT ALL IS COULD-NOT-RUN, NOT A FAILURE. The missing-result
  # test is now made BEFORE the ran-0 test, which is a reordering and needs its own pin: previously
  # this stream produced a hard repository FAILURE asserting "a suite that runs nothing is not a
  # passing suite" from a stream the parser had just admitted it did not understand. Unknown is
  # unknown at every value of N, and 0 is a value of N.
  cat > "$st_dir/stub_zero" <<'STUB'
#!/bin/sh
printf -- '----------------------------------------------------------------------\n'
printf 'Ran 0 tests in 0.000s\n'
printf '\n'
printf 'some shape this parser does not recognise\n'
STUB
  chmod 755 "$st_dir/stub_zero"
  expect_suites "ran 0 tests with NO recognisable result line is COULD NOT RUN, not a failure" \
    "$st_ok_root" 0 1 1 2 "produced NO RECOGNISABLE RESULT LINE" "a suite that runs nothing is not a passing suite"
  # ── (row 4, round 5) AND A TEST COUNT THAT IS NOT A NON-NEGATIVE INTEGER IS COULD-NOT-RUN TOO. The
  #    `[0, suites_tests]` invariant the summary's comment asserts is conditional on `ran` being one,
  #    and nothing enforced it: `ran` is the first word after `Ran ` on a line from a stream this
  #    parser's own comments say a test can write anything into. A stub is the right instrument for
  #    the same reason it is above — real unittest will not emit these, so nothing on the real tree
  #    would go red while the hole sat there.
  #
  #    NEGATIVE: `Ran -3 tests` / `OK (skipped=9)` passed every branch test, gave `suites_tests=-3`
  #    with `exec_lo` clamped to 0, and printed `between 0 and -3 of -3` — an interval whose upper end
  #    is BELOW its lower, from a comment saying that cannot happen. Both halves pinned.
  cat > "$st_dir/stub_zero" <<'STUB'
#!/bin/sh
printf -- '----------------------------------------------------------------------\n'
printf 'Ran -3 tests in 0.000s\n'
printf '\n'
printf 'OK (skipped=9)\n'
STUB
  chmod 755 "$st_dir/stub_zero"
  expect_suites "a NEGATIVE test count is COULD NOT RUN, not arithmetic" \
    "$st_ok_root" 0 1 1 2 "cannot read as a non-negative integer" "of -3"
  expect_suites "and no interval is printed whose upper end is below its lower" \
    "$st_ok_root" 0 1 1 2 "tests:  0 of 0 vendored test(s)" "between 0 and -3"
  #    NON-NUMERIC: worse than a wrong number. `[ "$ran" -eq 0 ]` errors and falls through to the
  #    general arm, where `$((ran - sk))` resolves `abc` as a VARIABLE NAME and `set -u` kills the
  #    shell. Measured on bash 3.2 against the REAL vendored tree: no verdict section is rendered at
  #    all and the process exits 2 — this script's own could-not-run code, worn by a gate that died.
  #    So the LIVENESS is the assertion here, and it is carried by the counter deltas rather than by
  #    any needle: an abort inside `check_vendored_suites` kills the whole self-test process, so a
  #    matched delta and a rendered summary line are together the proof that the run survived the
  #    stream. The needles pin the disposition on top of that.
  cat > "$st_dir/stub_zero" <<'STUB'
#!/bin/sh
printf -- '----------------------------------------------------------------------\n'
printf 'Ran abc tests in 0.000s\n'
printf '\n'
printf 'OK (skipped=1)\n'
STUB
  chmod 755 "$st_dir/stub_zero"
  expect_suites "a NON-NUMERIC test count is COULD NOT RUN and does not abort the run mid-render" \
    "$st_ok_root" 0 1 1 2 "cannot read as a non-negative integer" "unbound variable"
  expect_suites "and the summary line is still reached and reports both suites as could-not-run" \
    "$st_ok_root" 0 1 1 2 "1 of 1 could not run" "vendored test(s) passed"
  SUITE_PY="$st_saved_py4"
  # AND THE SCOPE: the same guard in a $HOME-reaching suite belongs on the machine line, marked away
  # from the repository's. The branch does not restore SCOPE, and this is what pins that.
  st_home_guard_root="$st_dir/skills_home_classguard"
  mk_skill "$st_home_guard_root" zeta; mk_suite "$st_home_guard_root" zeta "$st_home_classguard_body"
  expect_suites "a \$HOME-reaching class-level guard lands on the machine line and is marked away" \
    "$st_home_guard_root" 1 0 0 1 "zeta: NOT TESTED HERE — discovery ran 0 test(s) because" "" 0 1 0 1

  # ── (F1, round 4) A GUARDED CLASS *BESIDE* A RUNNING TEST. The branch above only covers the case
  #    where guards are the ONLY thing in the module, so `Ran 0` routes it out of the arithmetic
  #    entirely. Put one ordinary test next to the guarded class and the same guard count lands in
  #    the general arm, where `execd=$((ran - sk))` treated it as a count of tests.
  #
  #    THE FIXTURE PREMISE IS ASSERTED FIRST, as it is for the `Ran 0` branch: if this interpreter
  #    counted the guarded class's tests into `Ran`, the assertions below would be measuring an
  #    ordinary partial skip and proving nothing.
  st_mixg_root="$st_dir/skills_mixedguard"
  mk_skill "$st_mixg_root" alpha; mk_suite "$st_mixg_root" alpha "$st_mixedguard_body"
  st_mixg_out=$( cd "$st_mixg_root/alpha" && PYTHONDONTWRITEBYTECODE=1 "$SUITE_PY" -m unittest discover -s tests -t tests 2>&1 )
  st_rc=1
  case "$st_mixg_out" in
    *"Ran 1 test"*) case "$st_mixg_out" in *"skipped=1"*) st_rc=0 ;; esac ;;
  esac
  st_assert "control: a guarded class beside a running test really does emit \`Ran 1 test\` + \`skipped=1\`" \
    "$st_rc" "this interpreter emitted something else, so the assertions below are not exercising the mixed-unit case: $st_mixg_out"
  # `ran - sk` is 0, so the OLD code took the all-skipped arm and said so. It must not: `test_3` ran.
  expect_suites "a guard beside a running test is not reported as an all-skipped suite" \
    "$st_mixg_root" 1 1 0 1 "alpha: NOT TESTED HERE — 1 vendored test(s) ran and 1 skip event(s) were reported, so 0 of 1 can be SHOWN to have executed an assertion" "all 1 vendored test(s) were SKIPPED"
  # AND IT SAYS THE OTHER READING OUT LOUD, which is the whole difference between a conservative
  # verdict and a false one. Without this needle the sentence above could drop the alternative and
  # go back to asserting that nothing ran.
  expect_suites "and it names the reading under which a test did pass, rather than asserting none did" \
    "$st_mixg_root" 1 1 0 1 "between 0 and 1 of 1 may in fact have passed"
  expect_suites "and the test-level summary states the bound instead of a point" \
    "$st_mixg_root" 1 1 0 1 "tests:  between 0 and 1 of 1 vendored test(s) actually executed an assertion; between 0 and 1 of 1 were SKIPPED"
  # AND THE AGGREGATE MUST NOT RE-ASSERT WHAT THE PER-SUITE SENTENCE STOPPED ASSERTING. This is the
  # same output block as the two assertions above: it says `between 0 and 1 of 1 may in fact have
  # passed` AND, four lines later, it used to say `1 of 1 ran only skips`. Under the guard reading
  # `test_3` ran and passed, so that was flatly false — the unhedged claim the per-suite reword
  # removed, surviving in the aggregate in different words. Both halves are pinned here, present and
  # absent, on the one fixture where the two readings actually diverge.
  expect_suites "and the aggregate bucket does not assert what ran either" \
    "$st_mixg_root" 1 1 0 1 "1 of 1 yielded no demonstrable assertion" "ran only skips"

  # ── TWO guarded classes beside one running test: `Ran 1 test` + `OK (skipped=2)`, the shape that
  #    produced `tests: -1 of 1 … 2 of 1 were SKIPPED`. Both halves of that are pinned as ABSENT, and
  #    the present needle proves the line was rendered at all rather than skipped over.
  st_twog_root="$st_dir/skills_twoguard"
  mk_skill "$st_twog_root" alpha; mk_suite "$st_twog_root" alpha "$st_twoguard_body"
  st_twog_out=$( cd "$st_twog_root/alpha" && PYTHONDONTWRITEBYTECODE=1 "$SUITE_PY" -m unittest discover -s tests -t tests 2>&1 )
  st_rc=1
  case "$st_twog_out" in
    *"Ran 1 test"*) case "$st_twog_out" in *"skipped=2"*) st_rc=0 ;; esac ;;
  esac
  st_assert "control: two guarded classes beside a running test really do emit \`Ran 1 test\` + \`skipped=2\`" \
    "$st_rc" "this interpreter emitted something else, so the negative-count assertions below prove nothing: $st_twog_out"
  expect_suites "more skip events than tests cannot produce a negative filtered count" \
    "$st_twog_root" 1 1 0 1 "tests:  between 0 and 1 of 1 vendored test(s) actually executed an assertion" "-1 of 1"
  expect_suites "and cannot produce a numerator above its own total" \
    "$st_twog_root" 1 1 0 1 "between 0 and 1 of 1 were SKIPPED" "2 of 1 were SKIPPED"
  # The event count is still REPORTED — bounding the test-level counts must not silently discard the
  # number that revealed the mismatch. It is printed in its own unit, without a test denominator.
  expect_suites "and the skip-event count survives, in its own unit and without a test denominator" \
    "$st_twog_root" 1 1 0 1 "2 skip event(s) were reported, and a skip event is one test OR one whole guarded class"
  # POSITIVE CONTROL for the two absences: a root whose summary DOES contain a bare `N of M` test
  # line, so the absent needles above are measuring the negative and the over-total specifically and
  # not the whole sentence having vanished.
  expect_suites "control: an unskipped root still prints a plain N-of-M test line" "$st_ok_root" \
    0 0 0 0 "tests:  2 of 2 vendored test(s) actually executed an assertion; 0 of 2 were SKIPPED" "between"

  # ── (F6) THE UNMIGRATED-SKIP LIST IS DERIVED, NOT ENUMERATED, AND THIS PINS THE MECHANISM. The
  #    header used to carry a prose list of four such call sites; the commit that wrote the list
  #    added a fifth, so it was stale one commit after being written — the second time that
  #    enumeration has been wrong. A prose list of call sites is a second copy of the truth. The
  #    sites are tagged in place and the header carries the grep that derives them, so BOTH halves
  #    are asserted here: remove the markers, or remove the recipe, and the suite goes red. This is
  #    the only form of coverage a comment can have, and it is why the fix is mechanical rather than
  #    a sixth bullet.
  #    BOTH PATTERNS ARE ANCHORED TO A COMMENT LINE, AND THAT IS NOT COSMETIC — IT IS THE FIX FOR A
  #    DEFECT IN THIS ASSERTION PAIR. The first version searched for the bare token
  #    `UNMIGRATED-CNR:` anywhere in the file, and the file that contains the sites ALSO contains
  #    these two assertions, which mention the token in their own grep patterns and failure
  #    messages. Mutation testing removed all five real site markers and the count fell from 9 to 4
  #    — still above the threshold — so BOTH mutations survived a suite that was, quite literally,
  #    measuring itself. `^\s*#\s*MARKER` matches a tagged call site and matches neither the
  #    header's recipe line (`#  grep -n …`) nor these two lines (which do not begin with `#`).
  st_self="${BASH_SOURCE[0]}"
  # No `|| echo 0` on either of these two counts. `grep -c` with no match prints `0` AND exits 1, so
  # the fallback appended a SECOND zero and the variable became the two-line string "0\n0" — which
  # fails in the right direction (it is not the pinned number) but reports itself as `0\n0` in the
  # message. The `${x:-0}` guards below already cover the only case the fallback was for: an
  # unreadable file, where grep prints nothing at all.
  st_marks=$(grep -cE '^[[:space:]]*#[[:space:]]*UNMIGRATED-CNR:' "$st_self" 2>/dev/null)
  st_rc=1; [ "${st_marks:-0}" -gt 0 ] && st_rc=0
  st_assert "the unmigrated attempted-no-result skips are tagged at their call sites" "$st_rc" \
    "found ${st_marks:-0} tagged call site(s) in $st_self — the header derives its list from these, so with none the derived list is empty and silently wrong, which is the stale-enumeration defect in a new costume"
  #    AND THE TAGS ARE CHECKED, NOT JUST COUNTED — the assertion above cannot tell a correct tag
  #    from an incorrect one, and the commit that introduced the derivation was wrong on 3 of its 7
  #    entries with both assertions green. The marker's own text is "attempted and produced no
  #    result, STILL EXITING 0", so the line beneath it must be the `skip` call that does that: a
  #    shell `skip …` or, in the embedded renderer, `emit("skip", …)`. A marker over a branch that
  #    calls `cnr` (exit 2, already migrated) or over anything else now goes red, which is exactly
  #    the three entries this replaced. It cannot check the remaining judgement — whether a tagged
  #    skip is legacy or deliberate — and the header says so rather than implying otherwise.
  #    Anchored to a comment line for the reason above, and the awk program's own pattern line does
  #    not begin with `#`, so this assertion cannot satisfy itself.
  st_badtag=$(awk '
      tagged==1 { tagged=0; if ($0 !~ /^[[:space:]]*(skip |emit\("skip",)/) bad = bad (bad=="" ? "" : ",") (NR-1) }
      /^[[:space:]]*#[[:space:]]*UNMIGRATED-CNR:/ { tagged=1 }
      END { print bad }
    ' "$st_self" 2>/dev/null)
  st_rc=1; [ -z "$st_badtag" ] && st_rc=0
  st_assert "and every tagged site really is a skip that exits 0, not merely a line with a marker on it" \
    "$st_rc" "the marker on line(s) ${st_badtag:-?} of $st_self is not immediately followed by a \`skip\` call, so the derived list names a site that does something else — a tag is a falsifiable claim about the branch beneath it and this is the only part of it a machine can check"
  #    AND THE SECOND ASSERTION SEARCHES THE HEADER, NOT THE FILE. It used to grep the whole script
  #    for a column-0 comment matching the recipe — so the claim "the HEADER carries the recipe" was
  #    satisfied by such a comment appearing anywhere at all, including in a block a reader arriving
  #    at the top would never see. The header is everything above `set -uo pipefail`, accumulated in
  #    pure bash: `sed -n '1,/…/p'` over this file is the macOS em-dash trap documented twice above.
  st_hdr=""
  while IFS= read -r st_ln3; do
    case "$st_ln3" in "set -uo pipefail"*) break ;; esac
    st_hdr="$st_hdr$st_ln3"$'\n'
  done < "$st_self"
  st_rc=1
  printf '%s' "$st_hdr" | grep -qE "^#[[:space:]]+grep -n 'UNMIGRATED-CNR:' install/verify\.sh" && st_rc=0
  st_assert "the header carries the recipe that derives that list, rather than a prose copy of it" \
    "$st_rc" "the derivation recipe is missing from the header comment (the ${#st_hdr} bytes above \`set -uo pipefail\`), so a reader has no way to enumerate the sites and the enumeration will be reintroduced as prose"
  #    AND THE HEADER'S OTHER FALSIFIABLE CLAIM — HOW MANY THINGS RAISE 2 — IS PINNED THE SAME WAY.
  #    The three assertions above cover the marker convention, the tag adjacency and the recipe.
  #    NONE of them covers the sentence a reader actually acts on: "`cnr` is called from exactly one
  #    place — the vendored-suite runner". That sentence went false when `check_installer_agrees`
  #    grew a `cnr`, in the same commit, with all three green — the second time that paragraph has
  #    been stale, in a file whose entire subject is claims about itself that nothing checks. A
  #    claim about the file, asserted in the file, with nothing checking it, is the defect; this is
  #    the check. It pins the COUNT, which is all a machine can do here — it cannot tell the reader
  #    that the seventh site is in a third subsystem, and the header says so.
  #    IT CANNOT SATISFY ITSELF: this line begins `st_cnrsites=`, and the pattern requires the line
  #    to begin with optional whitespace and then `cnr ` — the same anchoring argument as the two
  #    assertions above, for the same reason.
  st_cnrsites=$(grep -cE '^[[:space:]]*cnr ' "$st_self" 2>/dev/null)
  st_expected_cnrsites=7
  st_rc=1; [ "${st_cnrsites:-0}" -eq "$st_expected_cnrsites" ] && st_rc=0
  st_assert "and the number of \`cnr\` call sites still matches what the header says raises exit 2" "$st_rc" \
    "$st_self has ${st_cnrsites:-0} \`cnr\` call site(s), pinned at $st_expected_cnrsites — the header paragraph beginning 'WHAT RAISES 2 TODAY' names them and how many subsystems they span, so a changed count means that paragraph is now describing a different file. Fix the paragraph, then move the literal in the same commit"

  # ── (F7) THE `ST_DRY` MECHANISM ITSELF, WHICH HAD ZERO COVERAGE IN A GREEN RUN. On a machine with
  #    git, python3 3.10+ and working mode bits, NOT ONE of the five guards fires, `ST_DRY` never
  #    leaves 0, and every short-circuit in the five assertion helpers is dead code. `136 of 136, 0
  #    not set up` proved nothing whatever about it. MEASURED, on the commit that introduced it:
  #    delete any single short-circuit and this suite still reads all-green here, while on a machine
  #    without git the three assertions in the declaration region run against a fixture that was
  #    never built and print three `fail(1!=0)` lines — the round-1 defect restored in full, green
  #    locally and misleading elsewhere.
  #
  #    Correctness was established by the implementer forcing each arm by hand. That is exactly the
  #    "implementer's habit" this mechanism was written to encode into the suite, and the argument is
  #    made in this file for the interpreter-less PATH while not being made here. So: two assertions,
  #    one static and one live.
  #
  #    THE STATIC ONE IS A RANGE CHECK, NOT A BASH PARSER, and it is the same shape as the
  #    `UNMIGRATED-CNR` adjacency assertion above: read `$st_self`, take every region from an
  #    `st_dry_begin` CALL to its bare `st_dry_end`, and require every line in it to be one of —
  #    a comment, a blank, a continuation of the line above, a bare block keyword, a call to one of
  #    the five assertion helpers, or a line immediately beneath an `# ST_DRY-SIDE-EFFECT:` marker.
  #    That is what makes the dry walk's cost knowable: anything else in a dry region is work the
  #    not-run arm performs and the run arm performs twice, unreviewed.
  #
  #    IT CANNOT SATISFY ITSELF, and the anchoring is why. The awk source below contains the literal
  #    `st_dry_begin "`, so an unanchored pattern would open a bogus region at the awk program itself
  #    and run it to the next real `st_dry_end` a few hundred lines down — the identical trap that
  #    made the first `UNMIGRATED-CNR` pair measure its own grep patterns. The pattern therefore
  #    requires the line to BEGIN with the call (optionally behind a `[ … ] ||` guard, the form the
  #    three conditional regions use), and the matching end pattern requires a line that is `st_dry_end`
  #    and NOTHING ELSE. Neither of the two awk lines carrying those literals can satisfy that: both
  #    carry them inside a regex body, so the `st_dry_begin "` line begins with `if (` and the
  #    `st_dry_end` line — the only awk line containing that token — begins with `$0 ~` and continues
  #    past it. The anchoring is what closes this; a claim about how awk lines happen to start is not.
  st_dryviol=$(awk '
      { prev_cont = cont; cont = ($0 ~ /\\[[:space:]]*$/) }
      inr == 0 {
        if ($0 ~ /^[[:space:]]*(\[[^]]*\][[:space:]]*\|\|[[:space:]]*)?st_dry_begin "/) { inr = 1; exempt = 0; nreg++ }
        next
      }
      $0 ~ /^[[:space:]]*st_dry_end[[:space:]]*$/ { inr = 0; exempt = 0; next }
      prev_cont == 1 { next }
      $0 ~ /^[[:space:]]*$/ { next }
      $0 ~ /^[[:space:]]*#[[:space:]]*ST_DRY-SIDE-EFFECT:/ { exempt = 1; next }
      $0 ~ /^[[:space:]]*#/ { next }
      exempt == 1 { exempt = 0; next }
      $0 ~ /^[[:space:]]*(expect_route|expect_suites|st_assert|expect_presence|expect_installer)[[:space:]]/ { next }
      $0 ~ /^[[:space:]]*(fi|else|then|done|esac|\})[[:space:]]*$/ { next }
      { bad = bad (bad == "" ? "" : ",") NR }
      # AND A ZERO-REGION FILE IS NOT A PASS. A range check over no ranges is vacuously green, which
      # is the same empty-denominator defect the marker-count assertion above exists to prevent; if
      # the pattern ever stops matching the call form, this must say so rather than say nothing.
      #
      # AND NEITHER IS AN AWK THAT NEVER REACHED `END`. Empty output has to mean "did not run", not
      # "found nothing", or a syntax error here — stderr suppressed, exit 2 discarded by `$( )` —
      # buys a green `ok` from the assertion whose own message says `NO-REGIONS-MATCHED` catches the
      # vacuous pass; that marker is unreachable in exactly this mode, because `END` never runs. So
      # the pass is a POSITIVE sentinel and empty is a failure, the same `${st_marks:-0}` idiom two
      # assertions above. (`st_badtag` above has the identical hole and is left as it was found.)
      END { if (nreg == 0) print "NO-REGIONS-MATCHED"; else if (bad == "") print "OK"; else print bad }
    ' "$st_self" 2>/dev/null)
  st_rc=1; [ "$st_dryviol" = "OK" ] && st_rc=0
  st_assert "every line inside an ST_DRY region is an assertion call or a marked exception" "$st_rc" \
    "${st_dryviol:-?} — line numbers here sit between \`st_dry_begin\` and \`st_dry_end\` in $st_self and are neither an assertion helper call nor beneath an \`# ST_DRY-SIDE-EFFECT:\` marker; the dry walk executes them with ST_DRY=1 and the real walk executes them too, so whatever they do happens on a path nobody reviewed as doing it. Move the work above the guard, or mark the line and say in the ST_DRY header what it costs. \`NO-REGIONS-MATCHED\` instead means the check found no dry regions at all and was about to pass vacuously, and a bare \`?\` means awk printed nothing — it died before \`END\`, so the check never ran"
  #    The LIVE half of this pair — whether the short-circuits actually short-circuit — cannot go
  #    here: `expect_presence` and `expect_installer` are defined further down. It sits at the end of
  #    the suite, immediately before the accounting block, and covers all five helpers.

  echo
  echo "════ self-test — the vendored hook roster and its presence check"
  # THIS SECTION EXISTS BECAUSE THE CHECK IT DRIVES HAD NO ASSERTIONS AT ALL, and the roster it
  # replaced was three literal filenames against a directory of four. Nothing in this suite could see
  # that: both hook loops were written inline ~2,300 lines below the `exit` at the end of this block.
  # The fourth hook, `preflight.sh`, is vendored, installed and routed to by a PUBLISHED SKILL.md, and
  # deleting it left `./verify.sh` at exit 0 in silence.

  # mk_hooks DIR NAME… — a hooks root carrying exactly the executable files named, and nothing else.
  mk_hooks() {
    local dir="$1" n; shift
    rm -rf "$dir"; mkdir -p "$dir"
    for n in "$@"; do printf '#!/usr/bin/env bash\n' > "$dir/$n"; chmod 755 "$dir/$n"; done
  }

  # expect_hooks NAME CHECK_ROOT VENDOR_HOOKS OWNS_DIR REQUIRED WANT_FAIL WANT_WARN [MUST_CONTAIN]
  #              [MUST_NOT_CONTAIN]
  #
  # Counter deltas rather than needles alone, for the reason `expect_presence` gives: a message that
  # says the right words while counting nothing leaves the verdict and the exit code untouched.
  #
  # NO `ST_DRY` SHORT-CIRCUIT, DELIBERATELY, AND IT IS NOT THE SIXTH HELPER THE F7 CONTROL COVERS.
  # The five that have one are called inside dry regions, because their fixtures depend on a machine
  # fact that may be absent — git, python3 3.10+, a filesystem that honours `chmod 000`. Nothing here
  # does: every fixture below is files this function creates, and no assertion depends on a file being
  # NON-executable, which is the only direction a mode-bit-ignoring filesystem breaks. So this helper
  # is never called inside a dry region, and adding a short-circuit it can never take would make the
  # F7 control's "all five" claim false without buying a single covered line.
  expect_hooks() {
    local name="$1" root="$2" vend="$3" owns="$4" req="$5" wf="$6" ww="$7" needle="${8:-}" absent="${9:-}"
    local f0=$repo_fail w0=$repo_warn df dw why="" st_ln
    check_hook_presence "$root" "$vend" "fixture" "$owns" "$req" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); dw=$((repo_warn - w0))
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$dw" = "$ww" ] || why="$why warn(${dw}!=${ww})"
    if [ -n "$needle" ] && ! grep -qF -- "$needle" "$st_dir/rendered"; then why="$why missing:\"$needle\""; fi
    if [ -n "$absent" ] && grep -qF -- "$absent" "$st_dir/rendered"; then why="$why must-not-contain:\"$absent\""; fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s warn+%s\n' "$name" "$df" "$dw"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }

  # ── (H1) THE POSITIVE CONTROL: a complete mirror is clean, and both totals are printed.
  st_hook_full="$st_dir/hooks_full"
  mk_hooks "$st_hook_full" a-required.sh b-optional.sh
  expect_hooks "a hooks directory whose every file is present is a clean pass, with the required tally stated beside the roster total" \
    "$st_hook_full" "$st_hook_full" 1 "a-required.sh" 0 0 \
    "2 of 2 vendored hook(s) present in fixture; the required set names 1, 0 of which install/hooks/ does not carry"

  # ── (H2) THE FINDING THIS SECTION IS FOR, DIRECTION ONE: a shipped hook is not installed.
  st_hook_inst="$st_dir/hooks_installed"
  mk_hooks "$st_hook_inst" b-optional.sh
  expect_hooks "a vendored hook missing from the installed layer is a FAILURE that NAMES it" \
    "$st_hook_inst" "$st_hook_full" 0 "a-required.sh" 1 0 \
    "a-required.sh missing from fixture, or not executable"

  # ── (H3) AND AN OPTIONAL ONE IS A WARNING, not a failure — the optional-dependency contract.
  st_hook_noopt="$st_dir/hooks_noopt"
  mk_hooks "$st_hook_noopt" a-required.sh
  expect_hooks "a vendored hook outside the required set is a WARNING when absent, not a failure" \
    "$st_hook_noopt" "$st_hook_full" 0 "a-required.sh" 0 1 \
    "b-optional.sh absent from fixture"

  # ── (H4) DIRECTION TWO, WHICH A DISCOVERED ROSTER CANNOT SEE ON ITS OWN, and the reason the
  #    required set is pinned. Delete the hook from the VENDORED directory and the roster shrinks with
  #    it: the count reads a clean full house over a published route that no longer resolves. This is
  #    the same defect MEASURED on the skill side of this card, where `5 of 5` stayed green after a
  #    `!/` line was deleted, and what made THAT loud was a separate check naming the skill.
  st_hook_gone="$st_dir/hooks_gone"
  mk_hooks "$st_hook_gone" b-optional.sh
  st_rc=1; [ -f "$st_hook_full/a-required.sh" ] && [ ! -f "$st_hook_gone/a-required.sh" ] && st_rc=0
  st_assert "control: the baseline fixture really does carry the required hook and the mutated one really does not" "$st_rc" \
    "the two hook fixtures do not differ in the required file, so the two assertions below would prove nothing"
  expect_hooks "a required hook deleted from the vendored directory is a FAILURE that NAMES it, not a shrunken denominator" \
    "$st_hook_gone" "$st_hook_gone" 1 "a-required.sh" 1 0 \
    "\`a-required.sh\` is a REQUIRED hook and install/hooks/ does not carry it"
  expect_hooks "and the count says so too — 1 of 1 present, and the required set short by one" \
    "$st_hook_gone" "$st_hook_gone" 1 "a-required.sh" 1 0 \
    "1 of 1 vendored hook(s) present in fixture; the required set names 1, 1 of which install/hooks/ does not carry"

  # ── (H5) AND THAT FACT IS NOT CHARGED TWICE. `install/hooks/` is a REPOSITORY directory and this
  #    function runs against it in both scopes; firing it in both would make one missing hook print
  #    two problems and attribute the second to the MACHINE.
  expect_hooks "a required hook the repository does not carry is not charged to the machine scope a second time" \
    "$st_hook_gone" "$st_hook_gone" 0 "a-required.sh" 0 0 \
    "(reported against the repository, which owns that directory; not counted twice)" \
    "FAIL"

  # ── (H6) A ROSTER THAT REACHED NOTHING IS A FINDING, NOT A CLEAN ZERO — the same rule the skill
  #    roster follows, and the reason `0 hooks missing` may never be printed on its own.
  expect_hooks "a hooks directory that carries nothing is a FAILURE in the scope that owns it, not an empty pass" \
    "$st_dir/hooks_absent" "$st_dir/hooks_absent" 1 "a-required.sh" 1 0 \
    "carries no hook at all, so there is nothing to check presence AGAINST"
  expect_hooks "and it is not charged to the machine scope a second time either" \
    "$st_dir/hooks_absent" "$st_dir/hooks_absent" 0 "a-required.sh" 0 0 \
    "presence not checked — install/hooks/ carries no hook (reported against the repository, which owns that directory; not counted twice)" \
    "FAIL"

  # ── (H7) THE PIN ITSELF, ASSERTED RATHER THAN LEFT TO A COMMENT. `preflight.sh` is the hook this
  #    whole section was written for: 30KB, vendored, installed by the glob loop, and named at three
  #    places in the PUBLISHED progressive-disclosure/SKILL.md. Dropping it from the required set
  #    would restore the exact silence this fixes, so removing it must cost an assertion.
  st_rc=1; case " $HOOKS_REQUIRED " in *' preflight.sh '*) st_rc=0 ;; esac
  st_assert "the production required-hook set names preflight.sh" "$st_rc" \
    "HOOKS_REQUIRED is \`$HOOKS_REQUIRED\` and does not name preflight.sh — the hook a published SKILL.md routes to would be optional again, and deleting it would be silent"

  # ── (H7b) THE SAME REASONING, APPLIED TO THE OTHER PINNED NAME. H7 above asserted preflight.sh and
  #    ONLY preflight.sh — dropping `disclosure-check.sh` from HOOKS_REQUIRED reddened no assertion in
  #    this file, even though the comment that justifies the pin ("removing it must cost an
  #    assertion") applies to it verbatim: it is the SessionStart hook install.sh wires into
  #    settings.json, load-bearing for the same reason preflight.sh is.
  st_rc=1; case " $HOOKS_REQUIRED " in *' disclosure-check.sh '*) st_rc=0 ;; esac
  st_assert "the production required-hook set names disclosure-check.sh" "$st_rc" \
    "HOOKS_REQUIRED is \`$HOOKS_REQUIRED\` and does not name disclosure-check.sh — the hook install.sh wires into settings.json would be optional again, and deleting it would be silent"

  # ── (H8) AND DISCOVERY REACHES THE REAL DIRECTORY. Every assertion above runs on fixtures; a
  #    `hook_roster` that returned nothing against `install/hooks/` would leave all of them green and
  #    the production check vacuous. A discovered total of zero is itself a finding.
  st_hook_real=$(hook_roster "$VENDOR/hooks")
  st_hook_realn=$(printf '%s\n' "$st_hook_real" | grep -c . )
  #    NO NUMERIC THRESHOLD HERE, and that is the finding this card is closing wearing its own name:
  #    the Codex gate two hundred lines below was `-ge 4` against a set of six, a literal nobody
  #    derived and nobody could keep true. So this asserts the two things that are actually knowable —
  #    the roster is not empty, and it contains the name whose absence was silent.
  st_rc=1
  [ "${st_hook_realn:-0}" -gt 0 ] && printf '%s\n' "$st_hook_real" | grep -qx 'preflight.sh' && st_rc=0
  st_assert "hook discovery over the real install/hooks/ reaches it, and finds preflight.sh" "$st_rc" \
    "\`hook_roster $VENDOR/hooks\` returned ${st_hook_realn:-0} name(s) — [$(printf '%s' "$st_hook_real" | tr '\n' ' ')] — and either reached nothing at all or did not find preflight.sh, so the production hook check is running against a roster that reached nothing or reached the wrong thing"

  echo
  echo "════ self-test — the named-but-not-required hook (the regression this card closes)"
  # THIS FUNCTION DID NOT EXIST BEFORE THIS ROUND. Before the hook roster became directory-discovery,
  # the two graphify hooks were literals checked in both scopes, and deleting either one WARNED.
  # After, the same deletion produced NOTHING — not even the warn it used to — because `hook_roster`'s
  # output no longer contains a name that is not on disk, and every loop keyed off that output has
  # nothing left to say. See HOOKS_NAMED's header for the full account and why severity stays warn.

  # expect_hook_named NAME VENDOR_HOOKS NAMED WANT_WARN [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  expect_hook_named() {
    local name="$1" vend="$2" named="$3" ww="$4" needle="${5:-}" absent="${6:-}"
    local w0=$repo_warn dw why="" st_ln
    check_hook_named "$vend" "$named" > "$st_dir/rendered" 2>&1
    dw=$((repo_warn - w0))
    [ "$dw" = "$ww" ] || why="$why warn(${dw}!=${ww})"
    if [ -n "$needle" ] && ! grep -qF -- "$needle" "$st_dir/rendered"; then why="$why missing:\"$needle\""; fi
    if [ -n "$absent" ] && grep -qF -- "$absent" "$st_dir/rendered"; then why="$why must-not-contain:\"$absent\""; fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → warn+%s\n' "$name" "$dw"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }

  # ── (HN1) A NAMED HOOK PRESENT IN THE ROSTER IS SILENT — the ordinary case.
  st_hn_full="$st_dir/hn_full"
  mk_hooks "$st_hn_full" a-required.sh b-optional.sh
  expect_hook_named "a NAMED hook present in the roster is silent" \
    "$st_hn_full" "b-optional.sh" 0

  # ── (HN2) THE REGRESSION ITSELF: a NAMED hook deleted from install/hooks/ is a WARNING that names
  #    it, where a directory-discovered roster on its own would have nothing left to say.
  st_hn_gone="$st_dir/hn_gone"
  mk_hooks "$st_hn_gone" a-required.sh
  expect_hook_named "a NAMED hook absent from install/hooks/ is a WARNING that names it" \
    "$st_hn_gone" "b-optional.sh" 1 \
    "install/hooks/ does not carry \`b-optional.sh\`"

  # ── (HN3) AND IT IS A WARNING, NEVER A FAILURE — the optional-dependency severity invariant this
  #    card was told to hold: these hooks are inert without the third-party graphify CLI.
  expect_hook_named "the missing NAMED hook is never a FAILURE" \
    "$st_hn_gone" "b-optional.sh" 1 "" "FAIL"

  # ── (HN4) A NAMED HOOK ALSO IN HOOKS_REQUIRED IS NOT DOUBLE-REPORTED HERE. check_hook_presence's
  #    own req_absent loop already fails a required name by NAME; reporting it again here would turn
  #    one missing file into two findings on the same line count.
  expect_hook_named "a NAMED hook that is also in HOOKS_REQUIRED is skipped here, not double-reported" \
    "$st_hn_gone" "disclosure-check.sh" 0 "" "disclosure-check.sh"

  echo
  echo "════ self-test — the published-skill roster, its presence check, and the installer's agreement"
  # THIS SECTION EXISTS BECAUSE THE FIRST VERSION OF THE CHECK IT DRIVES HAD NO ASSERTIONS AT ALL.
  # The presence loop was written inline at the two call sites ~150 lines below the `exit` at the
  # end of this block, so the suite could not reach it, and the count stayed at 108 of 108 across
  # the whole change — a number that read as "nothing regressed" and actually meant "the fix is
  # invisible to the suite". Two mutations were then MEASURED to survive it green: replacing the
  # roster derivation with two hardcoded names, and reverting install.sh to its stale five-name
  # literal. Both are assertions below.

  # mk_decl DIR ENTRY… — a skills root whose allowlist declares exactly the lines given.
  mk_decl() {
    local dir="$1"; shift
    mkdir -p "$dir"
    { printf '/*\n!/.gitignore\n'; printf '%s\n' "$@"; } > "$dir/.gitignore"
  }

  # expect_presence NAME ROOT DECL_DIR CROSS WANT_FAIL WANT_WARN [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  #
  # Counter deltas, not just needles, for the reason expect_suites gives: a message that says the
  # right words while counting nothing leaves the verdict and the exit code untouched, and the
  # verdict is what an operator acts on.
  expect_presence() {
    [ "$ST_DRY" -eq 0 ] || { st_skipped=$((st_skipped+1)); return 0; }
    local name="$1" root="$2" decl="$3" cross="$4" wf="$5" ww="$6" needle="${7:-}" absent="${8:-}"
    local f0=$repo_fail w0=$repo_warn df dw why="" st_ln
    check_skill_presence "$root" "$decl" "fixture" "$cross" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); dw=$((repo_warn - w0))
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$dw" = "$ww" ] || why="$why warn(${dw}!=${ww})"
    if [ -n "$needle" ] && ! grep -qF -- "$needle" "$st_dir/rendered"; then why="$why missing:\"$needle\""; fi
    if [ -n "$absent" ] && grep -qF -- "$absent" "$st_dir/rendered"; then why="$why must-not-contain:\"$absent\""; fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s warn+%s\n' "$name" "$df" "$dw"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }

  # expect_installer NAME INSTALLER DECL_DIR WANT_REPO_FAIL WANT_ENV_CNR WANT_AWAY [MUST_CONTAIN]
  #                  [MUST_NOT_CONTAIN]
  #
  # THE ENV DELTA IS ASSERTED BESIDE THE REPO ONE, not inferred from it, because the defect this
  # pair exists to catch was a finding landing in the WRONG BUCKET rather than a finding going
  # missing: an installer that never reached its `skills` section printed a repository FAIL, and a
  # harness watching only `repo_fail` would call that a green assertion.
  #
  # AND `away` IS THE THIRD, for the mirror-image defect one round later. Routing the whole not-run
  # to `env` put the finding in the right bucket and left the REPOSITORY line unmarked — a
  # repository-scope check that did not run, and a verdict byte-identical to a clean run. A pair of
  # counters cannot see that; the triple can.
  #
  # MUST_NOT_CONTAIN is here because the repository arm's defining property is a NEGATIVE: it must
  # not attribute anything to the machine. A needle alone cannot assert the absence of a diagnosis.
  #
  # AND `repocnr` IS THE FOURTH DELTA, TRAILING AND DEFAULTING TO 0, added for the unattributable
  # timeout arm. Without it that arm's counter signature — repo_fail 0, env_cnr 0, away 0 — is
  # BYTE-IDENTICAL to a clean pass, and the only thing separating the two would be a needle. A
  # mutation deleting the `cnr` call and returning silently would then read green on the counters.
  # It trails the two needles rather than sitting beside the other deltas so that every call site
  # that does not need it keeps its arity: ten of the twelve omit it, each wanting 0 and saying so
  # by omission, and only the two timeout arms pass it.
  expect_installer() {
    [ "$ST_DRY" -eq 0 ] || { st_skipped=$((st_skipped+1)); return 0; }
    local name="$1" inst="$2" decl="$3" wf="$4" wc="$5" wa="$6" needle="${7:-}" absent="${8:-}" wrc="${9:-0}"
    local f0=$repo_fail c0=$env_cnr ef0=$env_fail a0=$repo_attributed_out r0=$repo_cnr df dc def da drc why="" st_ln
    check_installer_agrees "$inst" "$decl" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0)); dc=$((env_cnr - c0)); def=$((env_fail - ef0))
    da=$((repo_attributed_out - a0)); drc=$((repo_cnr - r0))
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    [ "$dc" = "$wc" ] || why="$why envcnr(${dc}!=${wc})"
    [ "$da" = "$wa" ] || why="$why away(${da}!=${wa})"
    [ "$def" = 0 ]    || why="$why envfail(${def}!=0)"
    [ "$drc" = "$wrc" ] || why="$why repocnr(${drc}!=${wrc})"
    if [ -n "$needle" ] && ! grep -qF -- "$needle" "$st_dir/rendered"; then why="$why missing:\"$needle\""; fi
    if [ -n "$absent" ] && grep -qF -- "$absent" "$st_dir/rendered"; then why="$why must-not-contain:\"$absent\""; fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s envcnr+%s away+%s repocnr+%s\n' "$name" "$df" "$dc" "$da" "$drc"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }

  # ── (a) THE POSITIVE CONTROL: declaration and directory agree, and both numbers are printed.
  #    THIS IS ALSO THE ASSERTION THAT KILLS MUTATION A — replacing the roster derivation with two
  #    hardcoded names. The fixture declares its own three, so a two-name stand-in leaves the third
  #    looking undeclared and this needle's `0 of them undeclared` becomes `1 of them undeclared`.
  #    A separate assertion (d) used to say so a second time with the same fixture, the same
  #    arguments, the same expected counters and a needle that was a SUBSTRING of this one — it
  #    could not go red in any run where this one was green, and its `must-not-contain` was
  #    unfalsifiable given its own needle. It has been removed rather than kept as a count.
  st_pres_root="$st_dir/pres_ok"
  mk_skill "$st_pres_root" alpha; mk_skill "$st_pres_root" beta; mk_skill "$st_pres_root" gamma
  mk_decl "$st_pres_root" '!/alpha' '!/beta' '!/gamma'
  expect_presence "declaration and directory agreeing is a clean pass, with the directory total stated beside the declared one" \
    "$st_pres_root" "$st_pres_root" 1 0 0 \
    "3 of 3 declared skill(s) present in fixture; the directory holds 3 with a SKILL.md, 0 of them undeclared"

  # ── (b) THE FINDING THIS WHOLE SECTION IS FOR: a published skill loses its `!/` line.
  #    MEASURED on the version without this assertion — exit 0, `5 of 5` in both scopes, verdict
  #    lines byte-identical to a clean run, a four-line diff none of which says anything is wrong.
  #    `N of M` was not evidence because M was the length of N.
  st_pres_gap="$st_dir/pres_gap"
  mk_skill "$st_pres_gap" alpha; mk_skill "$st_pres_gap" beta; mk_skill "$st_pres_gap" gamma
  mk_decl "$st_pres_gap" '!/alpha' '!/beta' '!/gamma'
  cp "$st_pres_gap/.gitignore" "$st_dir/decl_before"
  mk_decl "$st_pres_gap" '!/alpha' '!/beta'
  st_rc=1; cmp -s "$st_dir/decl_before" "$st_pres_gap/.gitignore" || st_rc=0
  st_assert "control: deleting the negation really did change the fixture declaration" "$st_rc" \
    "the mutated declaration is byte-identical to the baseline, so the assertion below would prove nothing"
  expect_presence "a published directory whose \`!/\` line was deleted is a FAILURE, not a clean full house" \
    "$st_pres_gap" "$st_pres_gap" 1 1 0 \
    "gamma/ ships a SKILL.md but no \`!/gamma\` line declares it" "3 of 3 declared"
  expect_presence "and the count says 2 declared against 3 on disk — the denominator moved because it is measured elsewhere" \
    "$st_pres_gap" "$st_pres_gap" 1 1 0 \
    "2 of 2 declared skill(s) present in fixture; the directory holds 3 with a SKILL.md, 1 of them undeclared"

  # ── (c) THE OTHER DIRECTION, which was already loud and must not regress.
  st_pres_miss="$st_dir/pres_miss"
  mk_skill "$st_pres_miss" alpha; mk_skill "$st_pres_miss" beta
  mk_decl "$st_pres_miss" '!/alpha' '!/beta' '!/delta'
  expect_presence "a declared skill with no directory is still a FAILURE that names it" \
    "$st_pres_miss" "$st_pres_miss" 1 1 0 \
    "delta missing from fixture"

  # ── (d) was here; it is subsumed by (a), which now records why.

  # ── (e) THE STRICT READER IS LOUD. Both legal negation forms it does not accept are named, rather
  #    than silently absent from the roster (`!name`) or silently mangled into `name/` (`!/name/`).
  st_pres_odd="$st_dir/pres_odd"
  mk_skill "$st_pres_odd" alpha
  mk_decl "$st_pres_odd" '!/alpha' '!beta' '!/gamma/'
  expect_presence "an allowlist line the reader cannot interpret is a FAILURE naming the line, not an omission" \
    "$st_pres_odd" "$st_pres_odd" 1 2 0 \
    "cannot interpret the allowlist line \`!beta\`"
  expect_presence "and the trailing-slash form is named too, rather than becoming an entry that installs and then fails equality" \
    "$st_pres_odd" "$st_pres_odd" 1 2 0 \
    "cannot interpret the allowlist line \`!/gamma/\`"

  # ── (f) A DECLARED ENTRY THAT IS A FILE IS NOT A SKILL, and the filter is by type rather than by
  #    a hardcoded list of the two filenames that happen to be there today.
  st_pres_file="$st_dir/pres_file"
  mk_skill "$st_pres_file" alpha
  mk_decl "$st_pres_file" '!/alpha' '!/LICENSE' '!/README.md'
  printf 'x\n' > "$st_pres_file/LICENSE"; printf 'x\n' > "$st_pres_file/README.md"
  #    THE ABSENCE NEEDLE IS THE RENDERED FAILURE, NOT THE PATH. It used to be `LICENSE/SKILL.md`,
  #    which the rendered text never contains in EITHER direction: `want_file` prints its third
  #    argument, `LICENSE missing from fixture`, so the old needle could not fire under the mutation
  #    it claimed to exclude and had no possible positive control. The text below is what a
  #    regression actually prints.
  expect_presence "a declared entry that exists as a regular file is not looked up as a skill directory" \
    "$st_pres_file" "$st_pres_file" 1 0 0 \
    "1 of 1 declared skill(s) present in fixture" "LICENSE missing from"

  # ── (g) MACHINE SCOPE DOES NOT CROSS-CHECK, and that is correct: ~/.claude/skills holds skills this
  #    repository never published, so its directory count is not a denominator for anything.
  expect_presence "with OWNS_DECL off an undeclared directory is not a finding, and no directory total is claimed" \
    "$st_pres_gap" "$st_pres_gap" 0 0 0 \
    "2 of 2 declared skill(s) present in fixture (total from the repository's declaration" "undeclared"


  # ── (h) graph-navigation KEEPS ITS WARNING SEVERITY, pinned so that the separate card that may
  #    change it has to change an assertion rather than discover the behaviour by accident.
  st_pres_gn="$st_dir/pres_gn"
  mk_decl "$st_pres_gn" '!/graph-navigation'
  expect_presence "graph-navigation absent is a WARNING and not a failure, in both scopes, unchanged by this card" \
    "$st_pres_gn" "$st_pres_gn" 1 0 1 \
    "only matters if you use graphify"

  # ── (i) NO DECLARATION AT ALL is a finding, not an empty pass.
  st_pres_nodecl="$st_dir/pres_nodecl"
  mk_skill "$st_pres_nodecl" alpha
  expect_presence "a missing declaration is a FAILURE — there is nothing to check presence against" \
    "$st_pres_nodecl" "$st_pres_nodecl" 1 1 0 \
    "is missing, so there is nothing to check presence AGAINST"

  # ── (i2) AND NONE OF THE THREE DECLARATION-INTEGRITY FINDINGS IS CHARGED TWICE. This function runs
  #    against ONE `install/skills/.gitignore` in both scopes; firing these in both made a single
  #    syntax error print two problems and attributed the second to the MACHINE. Each fixture below
  #    already has its repository-scope positive control above — (e) for the uninterpretable line,
  #    (i) for the missing declaration — so these three assert only that the SECOND count is gone,
  #    with `must-not-contain "FAIL"` proving the line is context rather than a re-worded finding.
  #    The empty-declaration case has no control above, so it gets one here.
  expect_presence "an uninterpretable allowlist line is not charged to the machine scope a second time" \
    "$st_pres_odd" "$st_pres_odd" 0 0 0 \
    "cannot be interpreted (reported against the repository, which owns that file; not counted twice)" \
    "FAIL"
  expect_presence "nor is a missing declaration" \
    "$st_pres_nodecl" "$st_pres_nodecl" 0 0 0 \
    "is missing (reported against the repository, which owns that file; not counted twice)" \
    "FAIL"
  st_pres_empty="$st_dir/pres_empty"
  mk_decl "$st_pres_empty" '!/.gitignore'
  expect_presence "control: a declaration that names no skills IS a FAILURE in the scope that owns it" \
    "$st_pres_empty" "$st_pres_empty" 1 1 0 \
    "names no skills — the declaration reached nothing"
  expect_presence "nor is a declaration that names no skills, in the scope that does not own it" \
    "$st_pres_empty" "$st_pres_empty" 0 0 0 \
    "names no skills (reported against the repository, which owns that file; not counted twice)" \
    "FAIL"

  # ── (j) MUTATION B: THE INSTALLER'S OWN SET, obtained by running it. Nothing inside this file can
  #    see install.sh revert to a hardcoded list; only executing it can. The first fixture runs the
  #    REAL installer, which also pins the output wording the comparison parses; the second is a stub
  #    that names a subset, which is exactly what the stale five-name literal was.
  #
  #    ONLY THE REAL-INSTALLER ASSERTION NEEDS AN INTERPRETER, and the guard is now around that one
  #    line rather than around the whole section. It used to wrap all four, so three assertions that
  #    are pure bash — a `cmp` control and two stub runs — went unrun on a machine without python3
  #    for no reason. The guard also tests the version install.sh actually requires, not merely that
  #    the binary exists: on 3.9 the real installer exits before its `skills` section, which is the
  #    COULD NOT RUN path asserted in (j2), not this one.
  st_inst="$st_dir/inst"
  mkdir -p "$st_inst"
  cp "$VENDOR/install.sh" "$st_inst/install.sh"
  mk_skill "$st_inst/skills" alpha; mk_skill "$st_inst/skills" beta
  mk_decl "$st_inst/skills" '!/alpha' '!/beta'
  st_py310=1
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1 || st_py310=0
  [ "$st_py310" -eq 1 ] || st_dry_begin "the real-installer agreement assertion" \
    "python3 3.10+ is absent, so install.sh exits on its own precondition before it reaches the skills block — that is the installer reporting a machine fact, and (j2) below asserts what this check does with it"
  expect_installer "the real installer, run, installs exactly what the declaration names" \
    "$st_inst/install.sh" "$st_inst/skills" 0 0 0 \
    "install.sh would install exactly the 2 declared skill(s)"
  st_dry_end
  cat > "$st_dir/stub_installer" <<'STUB'
#!/usr/bin/env bash
echo "skills"
echo "  would install alpha"
echo "hooks"
echo "  would install alpha"
echo "  would install beta"
STUB
  chmod 755 "$st_dir/stub_installer"
  st_rc=1; cmp -s "$st_inst/install.sh" "$st_dir/stub_installer" || st_rc=0
  st_assert "control: the stub installer is not the real one" "$st_rc" \
    "the stub is byte-identical to the real installer, so the assertion below would prove nothing"
  expect_installer "an installer naming a SUBSET of the declaration is a FAILURE that prints both sets" \
    "$st_dir/stub_installer" "$st_inst/skills" 1 0 0 \
    "install.sh's skill set does not match the declaration"
  expect_installer "and the hooks section, which prints the identical wording, is not swept into the skill set" \
    "$st_dir/stub_installer" "$st_inst/skills" 1 0 0 \
    "it would act on [alpha]"

  # ── (j2) AN INSTALLER THAT NEVER REACHED ITS `skills` SECTION IS ONLY A MACHINE FACT IF A MACHINE
  #    FACT WAS MEASURED. `install.sh:83-87` exits 1 before printing `skills` when python3 is
  #    absent or older than 3.10 — Apple's /usr/bin/python3 through macOS 12, and many minimal
  #    images. The first version of this check compared the empty set anyway and printed a
  #    REPOSITORY FAIL naming all six declared skills. The fix for THAT then over-corrected: it
  #    treated "no `skills` line" as a synonym for the interpreter being too old and said so in
  #    words, so `echo "skills:"` in install.sh on a 3.13 machine produced a message that was false
  #    in three clauses, exit 2, and a silently-skipped roster comparison — mutation B going
  #    undetected behind a reassuring sentence.
  #
  #    SO BOTH ARMS ARE ASSERTED, AND BOTH USE THE SAME INSTALLER STUB. The only thing that differs
  #    between them is the INTERPRETER ON PATH, which is the thing the check now probes. That is
  #    the whole design in one fixture pair: same input, different machine, different verdict.
  #
  #    AND THE MACHINE ARM IS DRIVEN BY A REAL INTERPRETER-LESS PATH, not by overriding a function.
  #    Building a bin directory holding only the binaries this code path uses is the same habit that
  #    caught the round-1 skip-count defect; encoding it here makes it a property of the suite rather
  #    than of whoever runs it. Both negative machines are constructed: one with no python3 at all,
  #    one with a python3 that answers 3.9 and fails install.sh's own probe.
  cat > "$st_dir/stub_old_python" <<'STUB'
#!/usr/bin/env bash
echo "python3 3.9 found; 3.10 or newer is required (the tools use PEP 604 type syntax)" >&2
exit 1
STUB
  chmod 755 "$st_dir/stub_old_python"

  # (j2a) THE REPOSITORY ARM. python3 on this machine satisfies install.sh's precondition, so the
  #       interpreter is excluded by measurement and the not-run is a fact about the repository:
  #       exit 1, and — the defining property, asserted as a NEGATIVE — nothing attributed to the
  #       machine. This is the assertion the `echo "skills:"` mutation trips.
  [ "$st_py310" -eq 1 ] || st_dry_begin "the repository arm of the installer not-run" \
    "python3 3.10+ is absent, so this machine cannot exercise the arm that requires the interpreter precondition to be MET; the machine arms below still run"
  expect_installer "an installer that never reaches \`skills\` on a machine that MEETS the interpreter precondition is a REPOSITORY finding" \
    "$st_dir/stub_old_python" "$st_inst/skills" 1 0 0 \
    "NOT for a reason on this machine" "THIS MACHINE and taken off the repository line"
  st_dry_end

  # The interpreter-less machines. Only the binaries this code path actually invokes are linked in:
  # awk (the roster reader), grep and head (the not-reached branch), bash (the installer subprocess),
  # and nothing else. `command -v timeout` finding nothing is incidental and correct — that is the
  # state of the machine this was written on anyway.
  st_nopy="$st_dir/bin_nopy"; st_oldpy="$st_dir/bin_oldpy"
  mkdir -p "$st_nopy" "$st_oldpy"
  for st_b in bash awk grep head; do
    st_bp=$(command -v "$st_b" 2>/dev/null) || continue
    ln -s "$st_bp" "$st_nopy/$st_b" 2>/dev/null
    ln -s "$st_bp" "$st_oldpy/$st_b" 2>/dev/null
  done
  cat > "$st_oldpy/python3" <<'STUB'
#!/bin/sh
case "$2" in
  *print*) echo "3.9"; exit 0 ;;
esac
exit 1
STUB
  chmod 755 "$st_oldpy/python3"

  st_pathsave="$PATH"
  PATH="$st_nopy"
  st_rc=0; command -v python3 >/dev/null 2>&1 && st_rc=1
  st_assert "control: the interpreter-less fixture PATH really has no python3 on it" "$st_rc" \
    "python3 is still reachable, so the machine arm below would be measuring the real interpreter and would prove nothing"
  expect_installer "with python3 ABSENT, the same installer is COULD NOT RUN against the MACHINE — and the repository line is marked short by one" \
    "$st_dir/stub_old_python" "$st_inst/skills" 0 1 1 \
    "python3 is NOT ON PATH here"
  PATH="$st_oldpy"
  st_rc=1
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1 || st_rc=0
  st_assert "control: the 3.9 fixture interpreter really fails install.sh's own version probe" "$st_rc" \
    "the fixture python3 PASSES the 3.10 probe, so the too-old arm below is not the arm being exercised"
  expect_installer "with a python3 that FAILS the probe, it is the machine — and the version is the one this gate measured, not one it assumed" \
    "$st_dir/stub_old_python" "$st_inst/skills" 0 1 1 \
    "the python3 on PATH is 3.9, which fails the 3.10-or-newer precondition"
  expect_installer "and it quotes the installer's own first line rather than sending the reader to the roster reader" \
    "$st_dir/stub_old_python" "$st_inst/skills" 0 1 1 \
    "3.10 or newer is required"
  expect_installer "and it claims nothing about the declaration in either direction" \
    "$st_dir/stub_old_python" "$st_inst/skills" 0 1 1 \
    "no set was produced, so none was compared"
  PATH="$st_pathsave"

  # ── (j3) THE TIMEOUT ARM, WHICH HAD NO FIXTURE AT ALL AND SO COULD NOT GO RED ANYWHERE. Deleting
  #    the rc-124 test changed no assertion on any machine, and the arm meanwhile said the not-run
  #    was "recorded against THIS MACHINE" — a diagnosis of the box, produced by a fact about the
  #    installer's runtime. On a machine with `timeout` (every Linux box, every CI runner) a hang in
  #    install.sh above `echo "skills"` reached it.
  #
  #    THE STUB EXITS 124 ITSELF RATHER THAN HANGING, and that is the whole reason this arm is now
  #    testable everywhere. A stub that actually slept would exercise nothing on a machine with no
  #    `timeout` binary — the machine this was written on — and would cost 120s where there is one.
  #    The arm keys on the RC, so producing the rc directly exercises exactly the branch, in
  #    milliseconds, whether or not the platform can kill a subprocess. rc 137 takes the same branch;
  #    only 124 is asserted, because a second fixture would pin the same line twice.
  #
  #    THE DEFINING PROPERTY IS ASSERTED AS A PAIR: the finding is a COULD NOT RUN on the REPOSITORY
  #    line (repocnr+1, env_cnr 0, away 0 — attributed to neither the machine nor a marker), and the
  #    message must NOT say THIS MACHINE. Either half alone is satisfiable by the defect: the old arm
  #    would fail the counters, and an arm that moved the counters while keeping the old sentence
  #    would fail the needle.
  cat > "$st_dir/stub_timeout" <<'STUB'
#!/usr/bin/env bash
echo "installing skills into a very large tree" >&2
exit 124
STUB
  chmod 755 "$st_dir/stub_timeout"
  expect_installer "an installer killed on a timeout is a COULD NOT RUN attributed to NEITHER line, on the scope that ran it" \
    "$st_dir/stub_timeout" "$st_inst/skills" 0 0 0 \
    "CANNOT TELL WHETHER THAT IS THE MACHINE OR THE SCRIPT" "recorded against THIS MACHINE" 1
  expect_installer "and it still claims nothing about the declaration, having produced no set to compare" \
    "$st_dir/stub_timeout" "$st_inst/skills" 0 0 0 \
    "no set was produced, so none was compared" "" 1

  # AND THE STDIN WEDGE IS CLOSED — WITH A CAVEAT THAT HAS TO BE STATED, BECAUSE WITHOUT IT THIS
  # ASSERTION LOOKS LIKE MORE THAN IT IS. The stub reads a line; with `</dev/null` in the subprocess
  # call it gets EOF and completes. IT IS A POSITIVE CONTROL ONLY WHEN verify.sh's OWN STDIN BLOCKS.
  # Run `./verify.sh --self-test </dev/null`, or from any harness whose stdin is already at EOF, and
  # the stub's `read -r` returns immediately whether or not the fix is present — the assertion passes
  # either way. And when it DOES constrain, it constrains BY HANGING: the failure mode is no output
  # at all, which is the one failure `st_expected_total` can never report, because a suite that never
  # reaches its accounting block reports nothing. Keep it — a control that works under a terminal is
  # better than none — but do not read a green here as evidence the wedge is closed.
  cat > "$st_dir/stub_reads_stdin" <<'STUB'
#!/usr/bin/env bash
read -r _line
echo "skills"
echo "  would install alpha"
echo "  would install beta"
STUB
  chmod 755 "$st_dir/stub_reads_stdin"
  expect_installer "an installer that reads stdin gets EOF and completes, rather than wedging the gate" \
    "$st_dir/stub_reads_stdin" "$st_inst/skills" 0 0 0 \
    "install.sh would install exactly the 2 declared skill(s)"

  echo
  echo "════ self-test — the persona count against an independent total"
  # THREE SITES USED TO BE BARE `> 0` FLOORS with no denominator: move all but one file out of
  # ~/.claude/agents and the old check printed `ok  1 persona(s)`, exit 0, over a pool documented as
  # thirteen. `check_persona_count` reports N of an INDEPENDENT total and fails on a SHORTFALL.

  # mk_personas DIR N [EXT] — a directory carrying exactly N files matching *.EXT.
  mk_personas() {
    local dir="$1" n="$2" ext="${3:-md}" i
    rm -rf "$dir"; mkdir -p "$dir"
    i=1
    while [ "$i" -le "$n" ]; do printf 'x\n' > "$dir/p$i.$ext"; i=$((i+1)); done
  }

  # expect_persona_count NAME DIR PATTERN TOTAL WANT_FAIL [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  expect_persona_count() {
    local name="$1" dir="$2" pattern="$3" total="$4" wf="$5" needle="${6:-}" absent="${7:-}"
    local f0=$repo_fail df why="" st_ln
    check_persona_count "fixture" "$dir" "$pattern" "$total" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0))
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    if [ -n "$needle" ] && ! grep -qF -- "$needle" "$st_dir/rendered"; then why="$why missing:\"$needle\""; fi
    if [ -n "$absent" ] && grep -qF -- "$absent" "$st_dir/rendered"; then why="$why must-not-contain:\"$absent\""; fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s\n' "$name" "$df"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }

  # ── (PC1) THE POSITIVE CONTROL: a directory meeting the total is a clean pass, with the total
  #    stated beside the count rather than a bare `N persona(s)`.
  st_pc_full="$st_dir/pc_full"
  mk_personas "$st_pc_full" 3
  expect_persona_count "a persona directory that meets the independent total is a clean pass, N of M stated" \
    "$st_pc_full" '*.md' 3 0 \
    "3 of 3 persona(s) in fixture"

  # ── (PC2) THE FINDING THIS FUNCTION IS FOR: a shortfall against the total is a FAILURE that says
  #    how short, not a floor that only fires at zero.
  st_pc_short="$st_dir/pc_short"
  mk_personas "$st_pc_short" 1
  expect_persona_count "a persona directory short of the independent total is a FAILURE naming the shortfall, not a floor that only fires at zero" \
    "$st_pc_short" '*.md' 3 1 \
    "only 1 of 3 persona(s) present — short by 2"

  # ── (PC3) AN OVERAGE IS NOT A FAILURE. A project-specific overlay can legitimately add a persona
  #    file beyond the base pool; the check is a floor against the total, not an exact match.
  st_pc_over="$st_dir/pc_over"
  mk_personas "$st_pc_over" 4
  expect_persona_count "more personas than the total is a clean pass, not a mismatch" \
    "$st_pc_over" '*.md' 4 0 \
    "4 of 4 persona(s) in fixture"

  # ── (PC4) A TOTAL OF ZERO IS NOT COMPARED AGAINST — the vendored pool being empty is reported once,
  #    where it is counted, and this function must not report the same fact a second time here.
  expect_persona_count "a total of zero is not double-reported as a shortfall here" \
    "$st_pc_short" '*.md' 0 0 \
    "persona count not checked against a total"

  echo
  echo "════ self-test — hooks wired into settings.json (counter deltas)"
  # ~30 LINES OF INLINE PRODUCTION LOGIC WITH ZERO ASSERTIONS, one directory over from the hook and
  # skill rosters this card's earlier rounds made testable. MEASURED before extraction: mutating the
  # extraction regex to match nothing, or deleting the empty-extraction guard, left production
  # printing "3 of 3 hook entries ... are wired" over a settings.json with no hook entries at all,
  # and this suite stayed green throughout, because nothing here ever called the code.

  # mk_fake_installer DIR NAME… — a stub install.sh whose settings.json section wires exactly the
  # `~/.claude/hooks/<name>` references given, in the shape `check_settings_wired`'s regex reads.
  mk_fake_installer() {
    local f="$1" n; shift
    { echo '#!/usr/bin/env bash'
      for n in "$@"; do echo "# ~/.claude/hooks/$n"; done
    } > "$f"
  }

  # mk_fake_settings FILE COMMAND… — a settings.json wiring exactly the commands given.
  mk_fake_settings() {
    local f="$1" c; shift
    python3 - "$f" "$@" <<'PY'
import json, sys
path, cmds = sys.argv[1], sys.argv[2:]
data = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": c}]} for c in cmds]}}
open(path, "w").write(json.dumps(data))
PY
  }

  # expect_settings_wired NAME INSTALLER SETTINGS_JSON WANT_FAIL [MUST_CONTAIN] [MUST_NOT_CONTAIN]
  expect_settings_wired() {
    local name="$1" installer="$2" settings="$3" wf="$4" needle="${5:-}" absent="${6:-}"
    local f0=$repo_fail df why="" st_ln
    check_settings_wired "$installer" "$settings" "fixture-settings.json" > "$st_dir/rendered" 2>&1
    df=$((repo_fail - f0))
    [ "$df" = "$wf" ] || why="$why fail(${df}!=${wf})"
    if [ -n "$needle" ] && ! grep -qF -- "$needle" "$st_dir/rendered"; then why="$why missing:\"$needle\""; fi
    if [ -n "$absent" ] && grep -qF -- "$absent" "$st_dir/rendered"; then why="$why must-not-contain:\"$absent\""; fi
    if [ -z "$why" ]; then
      printf '  \033[32mok\033[0m    %s → fail+%s\n' "$name" "$df"; st_pass=$((st_pass+1))
    else
      printf '  \033[31mFAIL\033[0m  %s →%s\n' "$name" "$why"
      printf '        rendered as:\n'
      while IFS= read -r st_ln; do printf '          | %s\n' "$st_ln"; done < "$st_dir/rendered"
      st_fail=$((st_fail+1))
    fi
  }

  # ── (SW1) THE POSITIVE CONTROL: every entry the fake installer wants is wired, a clean pass.
  st_sw_installer="$st_dir/sw_installer"
  st_sw_settings="$st_dir/sw_settings.json"
  mk_fake_installer "$st_sw_installer" alpha.sh beta.py
  mk_fake_settings "$st_sw_settings" \
    "bash ~/.claude/hooks/alpha.sh 2>/dev/null || true" \
    "python3 ~/.claude/hooks/beta.py 2>/dev/null || true"
  expect_settings_wired "every entry the installer wants is wired: a clean pass, both counted" \
    "$st_sw_installer" "$st_sw_settings" 0 \
    "2 of 2 hook entries install.sh merges are wired into fixture-settings.json"

  # ── (SW2) THE FINDING THIS FUNCTION IS FOR: an entry the installer wants is not wired, and the
  #    fixture proves the extraction runs by naming the ONE hook that is missing, not by a stale total.
  st_sw_settings_gap="$st_dir/sw_settings_gap.json"
  mk_fake_settings "$st_sw_settings_gap" \
    "bash ~/.claude/hooks/alpha.sh 2>/dev/null || true"
  expect_settings_wired "an entry the installer wants but settings.json does not carry is a FAILURE naming it" \
    "$st_sw_installer" "$st_sw_settings_gap" 1 \
    "beta.py is not wired into fixture-settings.json"

  # ── (SW3) AN EMPTY EXTRACTION IS A FAILURE, NOT A VACUOUS PASS — the same rule the hook and skill
  #    rosters follow. An installer with no `~/.claude/hooks/<name>` reference gives this check nothing
  #    to look for, and passing silently would make a mutated or emptied regex invisible.
  st_sw_installer_empty="$st_dir/sw_installer_empty"
  printf '#!/usr/bin/env bash\necho nothing here references a hook path\n' > "$st_sw_installer_empty"
  expect_settings_wired "an installer naming no hook entries is a FAILURE, not a vacuous pass" \
    "$st_sw_installer_empty" "$st_sw_settings" 1 \
    "no \`~/.claude/hooks/<name>\` reference was found"

  # ── (SW4) A MISSING settings.json IS A FAILURE NAMING THE DISPLAY LABEL, not the resolved path —
  #    the WHERE argument exists so a caller's absolute path does not leak into a message that used to
  #    read `~/.claude/settings.json` regardless of where the caller's copy actually lives.
  expect_settings_wired "a missing settings.json is named by its display label, not the resolved path" \
    "$st_sw_installer" "/nonexistent/st_dry_control/settings.json" 1 \
    "no fixture-settings.json" "/nonexistent/st_dry_control"

  # ── (F7, LIVE HALF) THE FIVE SHORT-CIRCUITS, EXERCISED. The static range check above says what a
  #    dry region CONTAINS; it says nothing about whether `ST_DRY=1` makes those lines decline to
  #    run. Nothing else in a green run does either — every guard in this suite is false on a machine
  #    with git, python3 3.10+ and working mode bits, so `ST_DRY` never leaves 0 and all five
  #    short-circuits are dead code that `140 of 140` reports nothing about.
  #
  #    ALL FIVE, NOT ONE, and that is the difference between a control and a token. With one helper
  #    probed, deleting the OTHER four short-circuits stays green here and reddens only on a machine
  #    that takes a guard — the round-1 defect, one layer up. Each is called with bogus paths and
  #    needles that appear nowhere, and MOST of the delta arguments are junk no real call produces —
  #    NOT EVERY POSITION, an earlier version of this comment overclaimed: `expect_installer`'s
  #    trailing `repocnr` is omitted here and defaults to 0, which is exactly what a real call
  #    against a missing installer would also produce, and `expect_presence`'s `cross` is passed the
  #    same value production uses. Neither weakens the control — it binds on the OTHER delta
  #    positions, which stay genuinely wrong for any real call, so a short-circuit that failed to
  #    return would still fail loudly there. If a helper does not return before touching its
  #    arguments it fails loudly, and if it returns without counting, the delta is short.
  #
  #    AND IT ENTERS A REAL REGION, rather than assigning `ST_DRY=1` by hand. MEASURED: with the
  #    control setting the flag itself, mutating `st_dry_begin` to `ST_DRY=0` — the reviewer's named
  #    mutation, and the one that turns every dry region back into a live one — left this suite
  #    GREEN, because no `st_dry_begin` is reached at all on a machine with git, python3 3.10+ and
  #    working mode bits. Driving the control through `st_dry_begin`/`st_dry_end` is what makes the
  #    two functions reachable here, and it puts `st_dry_end`'s printed count under assertion.
  #
  #    AND THE REGION IS ENTERED ON A NON-ZERO BASE, WHICH IS THE WHOLE OF WHY THAT ASSERTION BINDS.
  #    `st_skipped` is 0 here on any machine where the suite is green, so a control entered at 0
  #    makes `st_dry_n0` 0 too and `st_skipped - st_dry_n0` degenerate to `st_skipped`: MEASURED,
  #    mutating `st_dry_n0=$st_skipped` to `st_dry_n0=0` left the pair green here at `141 of 141`
  #    and would have reddened only on a machine without git — the round-1 defect, inside the
  #    assertion added to prevent it. So the counter is offset by 11 before the region and the 11 is
  #    taken back out after it, leaving every downstream number identical. The same mutation now
  #    prints `(16 assertion(s))` and reddens HERE.
  #
  #    WHAT THIS BUYS, EXACTLY, AND NO MORE: the printed count is PINNED to the region's real size.
  #    It is not the arithmetic asserted — with one region of one size, replacing the subtraction
  #    with a literal `5` still passes. Closing that needs a second region of a different size, and
  #    the smaller true claim is preferred to the larger one until there is.
  #
  #    THE REGION IS A BRACE GROUP WITH A REDIRECTION, NOT A COMMAND SUBSTITUTION. `$( … )` would run
  #    `st_dry_end` in a subshell and its `ST_DRY=0` would be discarded, leaving the flag set for the
  #    whole rest of the suite — every later assertion silently not-run, and the total still pinned.
  #    That is the same subshell mistake `expect_route` documents one layer down.
  #
  #    IT RESTORES `st_skipped` AND SO CONTRIBUTES 0 TO THE TOTAL, deliberately. Left counted, every
  #    run on every machine would end "5 of N could NOT be set up on this machine" over five
  #    assertions that were set up perfectly and declined on purpose — a false sentence in the
  #    summary line, bought to preserve an accounting identity. These are therefore the five call
  #    sites the pinned total does not include:
  #    `grep -cE '^\s*(expect_route|expect_suites|st_assert|expect_presence|expect_installer|expect_hooks|expect_hook_named|expect_persona_count|expect_settings_wired) '`
  #    reads exactly FIVE more than `st_expected_total`, and they are the five below. (`expect_hooks`,
  #    `expect_hook_named`, `expect_persona_count` and `expect_settings_wired` are in that alternation
  #    because each is an assertion helper the total counts; none is a sixth short-circuit — see
  #    `expect_hooks`'s header for why that helper needs none and is absent from the region below, and
  #    the other three are ordinary counter-delta helpers of the same shape.)
  st_dc0=$st_skipped; st_dp0=$st_pass; st_df0=$st_fail
  # The offset the paragraph above explains. Any non-zero constant does; 11 is not 5 and not a
  # multiple of it, so a printed count that picked up the base instead of the delta cannot land on
  # the wanted value by coincidence.
  st_skipped=$((st_dc0 + 11))
  {
  st_dry_begin "ST_DRY control — five helpers that must not run" \
    "entered on purpose by the control below; this is the mechanism being exercised, not a missing prerequisite"
  expect_route "MUST NOT RUN — ST_DRY control (expect_route)" 999 'not json at all' 'junk' 7 7 7 'a needle present nowhere'
  expect_suites "MUST NOT RUN — ST_DRY control (expect_suites)" "/nonexistent/st_dry_control" 7 7 7 7 'a needle present nowhere'
  expect_presence "MUST NOT RUN — ST_DRY control (expect_presence)" "/nonexistent/st_dry_control" "/nonexistent/st_dry_control" 1 7 7 'a needle present nowhere'
  expect_installer "MUST NOT RUN — ST_DRY control (expect_installer)" "/nonexistent/st_dry_control" "/nonexistent/st_dry_control" 7 7 7 'a needle present nowhere'
  st_assert "MUST NOT RUN — ST_DRY control (st_assert)" 1 'this failure message must never be printed'
  st_dry_end
  } > "$st_dir/st_dry_control" 2>&1
  st_skipped=$((st_skipped - 11))
  # The deltas are captured BEFORE the counter is restored, or the failure message would report the
  # restored 0 and tell the reader nothing about what actually happened.
  st_dds=$((st_skipped - st_dc0)); st_ddp=$((st_pass - st_dp0)); st_ddf=$((st_fail - st_df0))
  st_rc=1
  [ "$st_dds" -eq 5 ] && [ "$st_ddp" -eq 0 ] && [ "$st_ddf" -eq 0 ] && [ "$ST_DRY" -eq 0 ] && st_rc=0
  st_skipped=$st_dc0
  st_assert "st_dry_begin makes all five assertion helpers count themselves not-run and run nothing, and st_dry_end clears the flag" "$st_rc" \
    "inside a real ST_DRY region the five helpers called with junk in every argument moved st_skipped by $st_dds (want 5) and st_pass/st_fail by $st_ddp/$st_ddf (want 0/0), and ST_DRY came out at $ST_DRY (want 0) — a short-circuit is gone or does not return before doing work, or st_dry_begin no longer sets the flag, or st_dry_end no longer clears it. Any of the three turns a dry region back into a live one against fixtures that were never built"
  # Only the NOT RUN line is quoted back, not the whole capture: under the mutations this assertion
  # exists to catch, the region prints five failed assertions with their rendered evidence, and
  # pasting all of it into one message buries the one line being asserted about.
  #
  # MATCHED ON THE REGION NAME, NOT ON `NOT RUN`. All five helpers are NAMED "MUST NOT RUN — …", so
  # under exactly the mutations this assertion targets their five FAIL lines match `NOT RUN` and
  # print BEFORE st_dry_end's, and `head -n 1` quotes one of those instead — no false pass, but the
  # wrong evidence and a fallback that never fires. The region name is on st_dry_end's line only.
  # Not `NOT RUN  ST_DRY control`: MEASURED, that matches nothing, because the printf puts an
  # `\033[0m` between the words and the spaces.
  st_dryline=$(grep -F 'ST_DRY control — five helpers' "$st_dir/st_dry_control" 2>/dev/null | head -n 1)
  st_rc=1
  [ -n "$st_dryline" ] && case "$st_dryline" in *'(5 assertion(s))'*) st_rc=0 ;; esac
  st_assert "and st_dry_end reports the count it DERIVED from the walk, not one written beside it" "$st_rc" \
    "the region's NOT RUN line was \`${st_dryline:-(none was printed — the region did not run dry at all)}\`; it must read \`(5 assertion(s))\`, which is \`st_skipped - st_dry_n0\` over a region whose size only the walk knows. A wrong number here is the hand-maintained count this mechanism replaced, wearing its name"

  rm -rf "$st_dir"
  echo
  # EVERY FILTERED COUNT CARRIES ITS TOTAL, and the not-run count is printed even at zero — "N
  # assertion(s)" alone cannot distinguish a full run from one where the prerequisites for a third
  # of it were absent.
  #
  # AND THE TOTAL IS INVARIANT, which it was not, in the very line that asserts the rule. `st_skipped`
  # moved by one per GROUP while the groups cover 3 and 2 assertions, so a machine without git printed
  # `67 of 68` against a real total of 70 — a denominator that MOVES WITH THE NUMERATOR, which is the
  # one thing a denominator may not do.
  #
  # AND THE INVARIANT IS NOW CHECKED RATHER THAN ASSERTED IN THIS COMMENT, because the comment did
  # not hold: the fix for THAT declared `st_skip … 5` over a branch containing 4 counted assertions,
  # so the total was 124 with python3 and 125 without — the identical defect, four lines above the
  # paragraph saying it was impossible. A hand-maintained count guarded by prose is not a check. So
  # the total is PINNED to a literal, and a mismatch is a hard failure whatever the assertions did.
  #
  # THE PIN ALONE WAS STILL MACHINE-DEPENDENT, WHICH IS THE THIRD ROUND OF THIS. A pin catches a
  # wrong not-run count only on a machine that TAKES the branch, and every guard in this suite is
  # false on a machine with python3, git and working mode bits — so an assertion added to a guarded
  # branch with a stale count read correct locally and went red only on someone else's laptop.
  # Catching it depended on the implementer's habit of building an interpreter-less PATH. It no
  # longer does: `ST_DRY` walks the branch either way and derives the count from it, so the total is
  # the same number on every machine BEFORE the pin is consulted, and the pin now checks one thing
  # rather than two. MEASURED: with an extra assertion added inside the git-guarded branch and
  # nothing else changed, the suite reads 137 both with git and without it; on the previous
  # mechanism it read 137 here and 136 there.
  #
  # AND THE MECHANISM ITSELF IS NOW COVERED, which it was not on the commit that introduced it. Every
  # guard here is false on a machine with git, python3 3.10+ and working mode bits, so `ST_DRY` never
  # left 0 in a green run and every short-circuit was dead code — `136 of 136, 0 not set up` was not
  # evidence about the mechanism, it was silence about it. Two assertions in (F7) fix that: a static
  # range check over this file, and a live probe that forces `ST_DRY=1` and requires a helper to
  # count itself and return. Deleting a short-circuit now reddens HERE rather than on someone else's
  # laptop.
  #
  # THE FIVE CALL SITES THIS TOTAL DOES NOT COUNT are that live probe's: it restores `st_skipped`
  # after measuring it, because leaving it counted would print "5 of N could NOT be set up on this
  # machine" on every machine, over five assertions that were set up perfectly and declined on
  # purpose. So
  # `grep -cE '^\s*(expect_route|expect_suites|st_assert|expect_presence|expect_installer|expect_hooks|expect_hook_named|expect_persona_count|expect_settings_wired) '`
  # over this file reads exactly FIVE more than the literal below — 170 against 165 today — and those
  # five are the probe.
  #
  # WHAT HAPPENS WHEN SOMEONE LEGITIMATELY ADDS AN ASSERTION: this one line changes, in the same
  # commit, and the diff shows `+N assertions, total 141 -> 142`. That is the entire cost, and it is
  # the point — the number a reviewer must agree with becomes visible in the diff. Anyone who changes
  # it without changing the count is doing so deliberately and in the open.
  #
  # IT IS NOT ITSELF COUNTED. Incrementing `st_pass` or `st_fail` here would change the very total
  # it is comparing, so it reports through a separate flag that only the exit arm reads.
  # 141 -> 152: eleven assertions for the vendored hook roster (H1-H8), which had none at all.
  # 152 -> 165: thirteen assertions added by TC-60 — one more for the required-hook pin (H7b), four
  # for the named-but-not-required hook regression (HN1-HN4), four for the persona count against an
  # independent total (PC1-PC4), and four for hooks-wired-into-settings.json now being a testable
  # function instead of ~30 lines of unreached inline logic (SW1-SW4).
  st_expected_total=165
  st_total=$((st_pass + st_fail + st_skipped))
  st_total_ok=1
  if [ "$st_total" -ne "$st_expected_total" ]; then
    st_total_ok=0
    printf '  \033[31mFAIL\033[0m  harness: this suite ran %s assertion(s) (%s passed, %s failed, %s not set up on this machine) but is PINNED at %s\n' \
      "$st_total" "$st_pass" "$st_fail" "$st_skipped" "$st_expected_total"
    printf '        An assertion was added or removed without updating `st_expected_total` in the same commit.\n'
    printf '        The not-run count is DERIVED from the branch (see ST_DRY), so this number no longer depends\n'
    printf '        on the machine: whatever it reads here it reads everywhere. Set the literal to it.\n'
  fi
  if [ "$st_fail" -eq 0 ] && [ "$st_total_ok" -eq 1 ]; then
    echo "SELF-TEST PASS — $st_pass of $st_total assertion(s) ran and passed; $st_skipped of $st_total could NOT be set up on this machine (total pinned at $st_expected_total)"
    exit 0
  fi
  echo "SELF-TEST FAIL — $st_fail of $st_total assertion(s) FAILED; $st_pass of $st_total passed, $st_skipped of $st_total could NOT be set up on this machine (total pinned at $st_expected_total)"; exit 1
fi

echo "════ 1. THIS REPOSITORY — the vendored tree at $VENDOR"
SCOPE="repo"

echo "── vendored skills"
# Repository scope cross-checks: this is the tree the declaration belongs to, so declaration and
# directory must agree in both directions. The whole check is a function call, not a loop written
# here, because everything on this line and below it is unreachable from `--self-test`.
check_skill_presence "$VENDOR/skills" "$VENDOR/skills" "install/skills" 1
check_installer_agrees "$VENDOR/install.sh" "$VENDOR/skills"

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
# `vp` IS THE INDEPENDENT TOTAL the two machine-scope persona counts below were missing — a bare
# `> 0` floor over a pool documented as thirteen passes `1 persona(s)`, exit 0, after everything but
# one file is moved out of ~/.claude/agents. This directory count cannot itself be checked against a
# further total without inventing a second roster, so it stays the floor it always was; what changes
# is that the two RENDERED copies below are now checked against IT rather than against zero.
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
# Repository scope: this is the directory the roster is discovered from, so it owns the required-set
# findings. The whole check is a function call rather than a loop written here, for the reason the
# skills line above gives — everything below the `--self-test` exit is unreachable from every
# assertion in this file, which is how three hardcoded names survived against a directory of four.
check_hook_presence "$VENDOR/hooks" "$VENDOR/hooks" "install/hooks" 1 "$HOOKS_REQUIRED"
# THE DIRECTION check_hook_presence CANNOT SEE EVEN WITH HOOKS_REQUIRED: a name that is optional, not
# required, and gets deleted from the directory outright. See HOOKS_NAMED's header for the regression
# this closes and why severity for the two graphify names must stay warn.
check_hook_named "$VENDOR/hooks" "$HOOKS_NAMED"
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
  # UNMIGRATED-CNR: attempted and produced no result, still exiting 0. See the header.
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
      # UNMIGRATED-CNR: attempted and produced no result, still exiting 0. See the header.
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
# Same declaration as the repository section above — the installed layer is checked against what
# THIS REPOSITORY says it publishes, not against a second list of installed-skill names that could
# name a different set. CROSSCHECK is 0: `~/.claude/skills` legitimately holds skills this
# repository never published, so its directory count is not a denominator. See check_skill_presence.
check_skill_presence "$CLAUDE/skills" "$VENDOR/skills" "~/.claude/skills" 0

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
# Same roster as the repository section — the installed layer is checked against what THIS
# REPOSITORY ships, not against a second list of hook names that could name a different set. OWNS_DIR
# is 0: `install/hooks/` is a repository directory, and a required hook missing from it is reported
# once, in the scope that owns it.
check_hook_presence "$CLAUDE/hooks" "$VENDOR/hooks" "~/.claude/hooks" 0 "$HOOKS_REQUIRED"

echo "── hooks wired into settings.json"
# ONE OF THE THREE ENTRIES install.sh MERGES WAS CHECKED. This block asserted `disclosure-check.sh`
# and nothing else, so the two graphify entries could be dropped from the merge, or fail to merge,
# and the gate said "disclosure-check wired" and moved on — a single-name check standing in for a
# three-name fact, which is this card's defect in its smallest form. See `check_settings_wired` for
# why the body lives there now instead of here.
check_settings_wired "$VENDOR/install.sh" "$CLAUDE/settings.json" "~/.claude/settings.json"

echo "── the installed hook actually produces output"
hook_produces_output "$CLAUDE/hooks/disclosure-check.sh" "installed hook"

echo "── personas rendered"
check_persona_count "~/.claude/agents" "$CLAUDE/agents" '*.md' "${vp:-0}"

echo "── codex"
if [ ! -d "$CODEX" ]; then
  # Three checks live in this block, and one `warn` used to stand in for all three — in a file that
  # had just introduced `skip` for exactly this. Absent Codex is not a warning about Codex; it is
  # three checks that did not run, and the verdict now counts them that way.
  echo "   ~/.codex does not exist — the three Codex checks below did not run"
  # The mirror skip stands for the whole per-skill presence check below, which is one CHECK made of
  # as many assertions as the declaration names. Three skips, not N, because what did not run is
  # three questions about Codex, and the number of skills is not one of them.
  skip "Codex skill mirror NOT CHECKED (every declared skill) — no ~/.codex"
  skip "Codex personas NOT CHECKED — no ~/.codex"
  skip "Codex [agents] config NOT CHECKED — no ~/.codex"
else
  # THE THIRD CALL SITE `check_skill_presence` WAS PARAMETERISED OVER ITS ROOT FOR. This was
  # `m=$(find "$CODEX/skills" -mindepth 1 -maxdepth 1 …)` against `[ "$m" -ge 4 ]`, and it was wrong
  # in three separate ways at once:
  #
  #   * THE THRESHOLD WAS A LITERAL NOBODY DERIVED, and this card made it staler rather than fixing
  #     it — it raised the installer's mirror set from five skills to six and left the gate at four.
  #     A number that has to be edited by hand every time the roster moves is a number that is stale
  #     between the two edits, and nothing announces the gap.
  #   * THE COUNT HAD NO TOTAL. `ok "$m skills mirrored"` — of how many? The rule this file states
  #     everywhere else is that a filtered count carries its denominator, and this one did not.
  #   * THE NUMERATOR WAS NOT FILTERED TO SKILLS AT ALL. `-mindepth 1 -maxdepth 1` counts ANY entry,
  #     and `install/skills/.gitignore`'s own header records that graphify installs itself into
  #     `~/.codex/skills`. So four vendor arrivals and ZERO published skills was a green check.
  #
  # MEASURED before the change: deleting `execution-methodology` and `graph-navigation` from
  # `~/.codex/skills` left `ok  4 skills mirrored`, exit 0, and no name printed — while the identical
  # deletion under `~/.claude/skills` was caught BY NAME. That positive control is what settles the
  # remedy: what makes a missing mirror detectable is a check that names it, not a count with a total.
  #
  # OWNS_DECL IS 0, as it is for `~/.claude/skills` and for the same reason: the declaration's own
  # integrity is established once, in repository scope, and `~/.codex/skills` legitimately holds
  # skills this repository never published, so its directory count is not a denominator for anything.
  check_skill_presence "$CODEX/skills" "$VENDOR/skills" "~/.codex/skills" 0

  check_persona_count "~/.codex/agents" "$CODEX/agents" '*.toml' "${vp:-0}"

  if grep -q '^\[agents\]' "$CODEX/config.toml" 2>/dev/null; then ok "subagents enabled"
  else bad "no [agents] block in config.toml — Codex will not spawn personas"; fi
fi

echo "── global toolchain consistency"
if [ ! -f "$IPD/check_toolchain.py" ]; then
  # UNMIGRATED-CNR: attempted and produced no result, still exiting 0. See the header.
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
# Each line wears its own could-not-run tally. The previous version attributed the whole tally to
# the repository line with a note saying to split it if a machine-scope check ever grew one; a
# vendored suite whose sources read $HOME now routes there, so it has.
#
# WHAT IS STILL UNWIRED HERE, STATED AS A FLOOR AND NOT AS A ZERO. The counter-to-line join and the
# totals-to-exit-code join both live in functions defined above the `--self-test` block, which exits
# before this point and so could never reach a single line of it. What remains below is three calls
# with no arguments and no arithmetic — AND ONE `exit $?`, WHICH IS NOT NOTHING.
#
# THE LAST HOP IS UNTESTED AND NOT SELF-ANNOUNCING. `render_summary`'s return value becoming the
# process exit status happens on the line below, under the self-test's own exit, unreachable from
# every assertion in this file. MEASURED, on this version, against a copy of this script alone in an
# empty tree so the run has findings to report: changing the line below to `exit 0` leaves
# `--self-test` at 96 of 96 green, and production prints
# `FAIL — 17 problem(s), 8 warning(s), 1 check(s) not run` and exits 0. Nothing goes red, and the
# verdict line reads exactly as it does when the exit code is right — so it is not self-announcing
# either.
#
# IT IS IRREDUCIBLE BY EXTRACTION rather than merely unpinned, which is why it is named instead of
# fixed. Moving the hop inside a function means that function calls `exit`, which ends the self-test
# process the first time an assertion drives it — so along THAT route the residual can be relocated
# but not removed, and relocating it is what the extraction of `render_verdicts`/`render_summary`
# already did as far as it goes. It is NOT irreducible full stop: driving `verify.sh` as a
# SUBPROCESS against a fixture tree would pin the verdict text and `$?` together, which is the only
# technique that reaches this line, and no such harness exists here. The previous version of this
# comment said "NOTHING IS WIRED HERE ANY MORE"; a comment claiming zero where the floor is one is
# exactly what stops the next reader looking.
render_verdicts
echo
render_summary
exit $?
