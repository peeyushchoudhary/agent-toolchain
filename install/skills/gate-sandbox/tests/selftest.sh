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

# A JVM binds IPv4 loopback through a dual-stack socket, so the kernel sees ::ffff:127.0.0.1 and no
# `(local ip "localhost:*")` filter matches it. That denied every Gradle daemon and reported
# "Unable to start the daemon process", which sends you to look at the daemon. Reproduced here with
# a dual-stack Python socket so the check needs no JDK and runs anywhere.
check "a dual-stack IPv4 loopback bind is permitted (the JVM's shape)" "BOUND" \
  "$(sandboxed "$FIX" "$FIX/copy" 'python3 -c "
import socket
s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
try:
    s.bind((\"::ffff:127.0.0.1\", 0)); s.listen(1); print(\"BOUND\")
except Exception as e: print(\"DENIED\", e)
"')"

printf '\n── the cache census (a marker is not the thing it stands for)\n'
# $TMPDIR is reaped by the operating system, and it reaps FILES while leaving DIRECTORIES. The
# clone therefore keeps its shape while losing its contents, the `.provisioned` marker survives,
# and provisioning reports "reused" over an empty cache -- after which every offline step fails as
# though the project were misconfigured. Measured once for real: 594 of 117,347 files left.
CACHEFIX="$FIXHOME/cachefix"
mkdir -p "$CACHEFIX/host/sub"
i=0; while [ "$i" -lt 40 ]; do printf 'x' > "$CACHEFIX/host/sub/f$i"; i=$((i+1)); done

census() { # census <run-root-for-caches> -> the check's own output
  ( GATE_RUN_ROOT="$1"; GATE_CACHES=(gradle); GATE_CACHE_PATH_gradle="$CACHEFIX/host"
    FAILURES=0
    provision_caches "$FIX" 1 >/dev/null 2>&1
    if [ "${2:-}" = "hollow" ]; then find "$(shared_cache_root)/gradle" -type f -delete; fi
    check_cache_content 2>&1
  )
}
full="$(census "$CACHEFIX/run-full")"
case "$full" in *intact*) c=intact ;; *) c="$full" ;; esac
check "an intact clone is reported intact" "intact" "$c"

hollowed="$(census "$CACHEFIX/run-hollow" hollow)"
case "$hollowed" in *"has lost content"*) h=caught ;; *) h="$hollowed" ;; esac
check "a clone whose files were reaped is CAUGHT, not reused" "caught" "$h"

printf '\n── the JVM agent-attach grant (present only for JVM gates, and narrow)\n'
# A denial here does not look like a denial: an inline mock maker attaches an agent to its own JVM
# on first use, so one denied handshake becomes one failure per mocked class, each reported as an
# exception from the mocking library. 1,142 of them in one run. These assert the rule's SHAPE,
# because the behavioural check below cannot run on a machine with no JDK.
JVM_PROF="$FIX/profile-jvm.sb"; NOJVM_PROF="$FIX/profile-nojvm.sb"
( GATE_JAVA_HOME="/nonexistent/jdk"; write_profile "$FIX" "$JVM_PROF" )
( GATE_JAVA_HOME="";                 write_profile "$FIX" "$NOJVM_PROF" )

check "a JVM gate is granted the attach paths" "1" \
  "$(grep -c 'java_pid|attach_pid' "$JVM_PROF" || true)"
check "a non-JVM gate is NOT widened by it" "0" \
  "$(grep -c 'java_pid|attach_pid' "$NOJVM_PROF" || true)"
# Both operations are in the one rule. Tested with a control: write alone and connect alone each
# still fail, so a rule carrying only one of them reads as correct and denies the handshake.
check "the grant carries file-write* AND network-outbound" "1" \
  "$(grep -c 'allow file-write\* network-outbound' "$JVM_PROF" || true)"
# THE BREAK-TEST FOR THE EXACT MISTAKE. The socket is bound under a suffixed temporary name and
# renamed into place, so a pattern anchored with [0-9]+$ matches the final name and never the one
# created -- and it fails as "target process doesn't respond within 10500ms", i.e. as a hung JVM.
check "the attach pattern is NOT anchored at the end" "0" \
  "$(grep -c 'attach_pid)\[0-9\]+\$' "$JVM_PROF" || true)"

# Neither flag is enough alone: without the profile grant the sandbox denies the handshake, and
# without the property the JVM refuses itself first with a different message.
JTO="$( GATE_JAVA_HOME=/nonexistent/jdk gate_env "$FIX" | sed -n 's/^JAVA_TOOL_OPTIONS=//p' )"
case "$JTO" in *allowAttachSelf=true*) sa=yes ;; *) sa=no ;; esac
check "the default JVM options permit self-attach" "yes" "$sa"
case "$JTO" in *preferIPv4Stack=true*) ip4=yes ;; *) ip4=no ;; esac
check "the default JVM options keep the IPv4 stack" "yes" "$ip4"

# THE GRANT MUST NOT WIDEN THE TEMP DIRECTORY. The per-user temp dir is shared and outside the run
# root; if this check ever flips, the sandbox has a writable escape hatch and every other deny
# assertion above is worth less.
check "a non-attach file in the per-user temp dir is still NOT writable" denied \
  "$(sandboxed "$FIX" "$FIX/copy" "touch '$GATE_DARWIN_TEMP_DIR/.__selftest_probe' 2>/dev/null && echo ok || echo denied")"
rm -f "$GATE_DARWIN_TEMP_DIR/.__selftest_probe" 2>/dev/null

# The behavioural check, when the machine has a JDK to run it with. Everything above is structure;
# this is the only one that proves the handshake actually completes.
if [ -n "${GATE_JAVA_HOME:-}" ] && [ -x "$GATE_JAVA_HOME/bin/java" ]; then
  mkdir -p "$FIX/attachprobe"
  cat > "$FIX/attachprobe/GateAttachSelftest.java" <<'JAVA'
import com.sun.tools.attach.VirtualMachine;
public class GateAttachSelftest {
  public static void main(String[] a) {
    try {
      VirtualMachine vm = VirtualMachine.attach(String.valueOf(ProcessHandle.current().pid()));
      vm.detach();
      System.out.println("ATTACHED");
    } catch (Throwable e) {
      System.out.println("DENIED");
    }
  }
}
JAVA
  check "a JVM can attach an agent to itself inside the profile" "ATTACHED" \
    "$(sandboxed "$FIX" "$FIX/attachprobe" 'java GateAttachSelftest.java 2>/dev/null | grep -E "^(ATTACHED|DENIED)$" || echo NORUN' 180)"
else
  printf '  %sskip%s  JVM attach behaviour (no JDK on this machine; structure asserted above)\n' "$DIM" "$RST"
fi

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
