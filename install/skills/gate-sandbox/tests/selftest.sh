#!/usr/bin/env bash
# Break-tests for the properties readiness.sh and gate.sh depend on.
#
# readiness.sh reports whether a MACHINE is ready. It does not check whether the isolation logic is
# still correct, and those are different questions: a profile that granted everything would make
# every readiness check pass. This file asserts the logic, on fixtures, IN BOTH DIRECTIONS -- the
# thing that should be allowed is allowed, and the thing that should be denied is denied.
#
# Both directions matter. A test that only proves "the copy is writable" passes just as well against
# a profile with no deny rule at all.
#
# HERMETIC. It builds its own git repository and its own configuration, so it needs no project on
# the machine and reads none of the operator's real config. A test suite that only runs where the
# author's checkout happens to sit is one that stops running.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$(cd "$HERE/../scripts" && pwd)"

FIXHOME="$(mktemp -d "${TMPDIR:-/tmp}/gate-sandbox-selftest.XXXXXX")"
export GATE_HOME="$FIXHOME/gate"
mkdir -p "$GATE_HOME/projects"

# shellcheck source=/dev/null
. "$SCRIPTS/gate_lib.sh"

PASS=0; FAIL=0
check() { # check <label> <expected> <actual>
  if [ "$2" = "$3" ]; then printf '  %sok%s    %s\n' "$GRN" "$RST" "$1"; PASS=$((PASS+1))
  else printf '  %sFAIL%s  %s -- expected %s, got %s\n' "$RED" "$RST" "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi
}
trap 'rm -rf "$FIXHOME"' EXIT

printf '%sgate-sandbox selftest%s\n\n' "$DIM" "$RST"

# ── A real, tiny git repository to stand in for a project ───────────────────────────────────────
REPO="$FIXHOME/repo"
mkdir -p "$REPO/sub"
git -C "$REPO" init -q 2>/dev/null || { mkdir -p "$REPO"; ( cd "$REPO" && git init -q ); }
printf 'hello\n'   > "$REPO/a.txt"
printf 'nested\n'  > "$REPO/sub/b.txt"
printf '#!/bin/sh\n' > "$REPO/run.sh"; chmod +x "$REPO/run.sh"
ln -sf a.txt "$REPO/link-inside"
git -C "$REPO" add -A >/dev/null 2>&1
git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm fixture >/dev/null 2>&1

cat > "$GATE_HOME/projects/repo.env" <<CONF
GATE_REPO="$REPO"
GATE_ARGV='true'
GATE_PROJECT_PREFIX=selftest
GATE_CACHES=()
CONF

printf '── configuration\n'
( cd "$REPO" && gate_load_config >/dev/null 2>&1 && printf 'ok' ) >/dev/null 2>&1
CFG_PATH="$( cd "$REPO" && gate_project_config_path )"
check "project config is found from inside the checkout" "$GATE_HOME/projects/repo.env" "$CFG_PATH"

gate_load_config "$GATE_HOME/projects/repo.env"
check "derivation fills a value neither file set" "yes" "$([ -n "$GATE_RUN_ROOT" ] && echo yes || echo no)"
check "the project file wins over the default prefix" "selftest" "$GATE_PROJECT_PREFIX"

# The validator has to refuse, not warn. A launcher that starts and dies halfway through
# provisioning has already spent the expensive part.
refuses() { ( GATE_ARGV=""; GATE_REPO="$REPO"; gate_validate_config ) >/dev/null 2>&1; echo $?; }
check "an empty GATE_ARGV is refused" "2" "$(refuses)"
bad_prefix() { ( GATE_PROJECT_PREFIX="Not Legal"; gate_validate_config ) >/dev/null 2>&1; echo $?; }
check "a compose-illegal project prefix is refused" "2" "$(bad_prefix)"

# ── The run root and the profile ────────────────────────────────────────────────────────────────
REFERENT="$(git -C "$REPO" rev-parse HEAD)"
REFERENT_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
COMPOSE_PROJECT="selftest_$$"
FIX="$(resolve_root "$FIXHOME/run")"
provision_root "$FIX"
OUTSIDE="$(resolve_root "$FIXHOME/outside")"

printf '\n── profile: the allow direction\n'
check "the copy is writable" ok \
  "$(sandboxed "$FIX" "$FIX/copy" 'touch ./w 2>/dev/null && echo ok || echo denied')"
check "the temporary HOME is writable" ok \
  "$(sandboxed "$FIX" "$FIX/copy" 'touch "$HOME/w" 2>/dev/null && echo ok || echo denied')"
check "the source is readable" ok \
  "$(sandboxed "$FIX" "$FIX/copy" "head -c1 '$REPO/a.txt' >/dev/null 2>&1 && echo ok || echo denied")"

printf '\n── profile: the deny direction (each of these passing is the point)\n'
check "the source is NOT writable" denied \
  "$(sandboxed "$FIX" "$FIX/copy" "touch '$REPO/.__selftest' 2>/dev/null && echo ok || echo denied")"
rm -f "$REPO/.__selftest" 2>/dev/null
check "a path outside the run root is NOT writable" denied \
  "$(sandboxed "$FIX" "$FIX/copy" "touch '$OUTSIDE/w' 2>/dev/null && echo ok || echo denied")"
check "host egress is NOT reachable" denied \
  "$(sandboxed "$FIX" "$FIX/copy" 'curl -sS --max-time 5 -o /dev/null https://registry-1.docker.io/v2/ 2>/dev/null && echo ok || echo denied')"

printf '\n── the load-bearing line of the profile\n'
# Mutation testing found that `(deny file-write*)` can be deleted with no test noticing, because
# `(deny default)` is what actually denies writes. So the deny-default line is asserted directly:
# it is the one line whose removal opens everything, and the behavioural checks above cannot tell
# you which line they depend on.
PROF="$(cat "$FIX/profile.sb")"
case "$PROF" in *"(deny default)"*) dd=yes ;; *) dd=no ;; esac
check "the profile denies by default" "yes" "$dd"
check "exactly one write subpath grant per run root" "1" \
  "$(grep -c "allow file-write\* (subpath \"$FIX\")" "$FIX/profile.sb" || true)"
case "$PROF" in *"(allow network-outbound (literal \"$GATE_DOCKER_SOCKET\"))"*) sk=yes ;; *) sk=no ;; esac
check "the daemon socket is granted by literal path, not a subpath" "yes" "$sk"

printf '\n── the physical-path trap\n'
# The regression that cost the most time. A profile written against the LOGICAL path denies every
# write, because macOS matches resolved paths -- and it presents as "the copy is broken", which
# sends you looking at the copy. Asserting resolve_root actually resolves is far cheaper than
# rediscovering the symptom.
LOGICAL="${TMPDIR:-/tmp}/gate-sandbox-logical.$$"; mkdir -p "$LOGICAL"
RESOLVED="$(resolve_root "$LOGICAL")"
if [ "$RESOLVED" = "$(cd "$LOGICAL" && pwd -P)" ]; then r=yes; else r="no ($RESOLVED)"; fi
check "resolve_root returns the physical path" yes "$r"
rm -rf "$LOGICAL" "$RESOLVED"

printf '\n── the sh -c quoting trap\n'
# A probe carrying its own quotes must survive intact. When it did not, the failure was reported
# against the SUBJECT of the probe rather than the probe -- "the source is writable", "the daemon is
# unreachable" -- which is the most expensive shape a test can fail in.
check "a script containing quotes runs intact" 'it worked' \
  "$(sandboxed "$FIX" "$FIX/copy" 'msg="it worked"; printf "%s" "$msg"   # trailing comment')"
check "a script containing a semicolon and braces runs intact" 'ok' \
  "$(sandboxed "$FIX" "$FIX/copy" 'if true; then { printf "ok"; }; fi')"

printf '\n── the copy and its manifest\n'
CP="$FIX/copyfixture"
make_copy "$CP"
check "the copy has no .git" "no" "$([ -e "$CP/.git" ] && echo yes || echo no)"
check "source and copy manifests are equal" "same" \
  "$(diff -q <(manifest_source) <(manifest_copy "$CP") >/dev/null && echo same || echo different)"
check "an executable bit survives as git's 100755" "100755" \
  "$(manifest_copy "$CP" | awk '$3=="run.sh"{print $1}')"
check "a symlink is recorded as 120000, not followed" "120000" \
  "$(manifest_copy "$CP" | awk '$3=="link-inside"{print $1}')"

M="$FIX/manifest-empty"; mkdir -p "$M"
check "the manifest of an empty tree is empty" "0" "$(manifest_copy "$M" | grep -c . || true)"

printf '\n── escaping symlinks (the one exclusion git archive does not give us)\n'
E="$FIX/esc"; mkdir -p "$E/sub"
printf 'x' > "$E/inside.txt"
ln -s inside.txt      "$E/link-local"    # stays inside   -> must be accepted
ln -s ../inside.txt   "$E/sub/link-up"   # still inside   -> must be accepted
ln -s /etc/hosts      "$E/link-abs"      # absolute out   -> must be caught
ln -s ../../../../etc "$E/link-rel"      # traversal out  -> must be caught
found="$(escaping_symlinks "$E")"
has() { case "$found" in *"$1"*) echo yes ;; *) echo no ;; esac; }
check "an absolute escaping link is caught"     "yes" "$(has link-abs)"
check "a ../ traversal escape is caught"        "yes" "$(has link-rel)"
check "a link staying inside is NOT flagged"    "no"  "$(has link-local)"
check "a ../ link still inside is NOT flagged"  "no"  "$(has link-up)"

printf '\n── the referent binding\n'
check "a pinned referent that does not match is refused" "2" \
  "$( ( GATE_REFERENT=0000000000000000000000000000000000000000; resolve_referent ) >/dev/null 2>&1; echo $?)"
printf 'dirty\n' > "$REPO/untracked.txt"
check "a dirty checkout is refused" "2" \
  "$( ( GATE_REFERENT=""; resolve_referent ) >/dev/null 2>&1; echo $?)"
rm -f "$REPO/untracked.txt"

printf '\n── no project facts leaked into the published skill\n'
# The rule that lets this skill be public. Any absolute home path, or a `Users/<name>` fragment, in
# the shipped scripts is a defect rather than a convenience.
# -I skips binary files and --exclude-dir keeps compiled Python out: a .pyc embeds the absolute
# path of the source it was compiled from, so scanning it reports the machine that ran the test
# rather than anything the skill ships.
leak="$(grep -rInE --exclude-dir=__pycache__ '/Users/[a-z]|/home/[a-z]' "$SCRIPTS" "$HERE" 2>/dev/null | grep -v 'gate-sandbox-selftest' | head -3)"
check "no hardcoded user home path in the scripts" "" "$leak"

printf '\n'
if [ "$FAIL" -eq 0 ]; then printf '%sPASS%s -- %s checks\n' "$GRN" "$RST" "$PASS"; exit 0
else printf '%sFAIL%s -- %s of %s checks\n' "$RED" "$RST" "$FAIL" "$((PASS+FAIL))"; exit 1; fi
