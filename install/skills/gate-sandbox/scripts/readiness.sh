#!/usr/bin/env bash
# The non-semantic readiness phase.
#
# THIS IS PREPARATION, NOT GATE EVIDENCE. Nothing it prints is a product verdict, and a green run
# here is not a pass of anything. Its only job is to stop a semantic gate attempt being spent
# discovering that a port was busy or a base image was missing -- a gate attempt that ran zero tests
# because of a provisioning block has cost the full price and bought nothing.
#
# It builds its environment with the SAME functions the gate uses, because a readiness check that
# proves something about a different environment has proven nothing.
#
#   readiness.sh                  build a run root, check everything, leave the root for inspection
#   readiness.sh --clean          remove the run root afterwards
#   readiness.sh --refresh-caches rebuild the shared cache clone from the host first
#   readiness.sh --config <path>  use a specific project configuration
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$HERE/gate_lib.sh"

CLEAN=0; REFRESH_CACHES=0; CONFIG=""
while [ $# -gt 0 ]; do case "$1" in
  --clean) CLEAN=1 ;;
  --refresh-caches) REFRESH_CACHES=1 ;;
  --config) shift; CONFIG="${1:-}" ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac; shift; done

gate_load_config "$CONFIG"

printf '%sSandboxed gate readiness%s  (preparation only -- never gate evidence)\n' "$DIM" "$RST"
printf '%sconfig: %s%s\n' "$DIM" "$GATE_CONFIG_PATH" "$RST"

head_ "Referent"
resolve_referent
ok "referent  $REFERENT"
ok "branch    $REFERENT_BRANCH, tree clean"

NONCE="$(date +%s)$$"
COMPOSE_PROJECT="$(compose_project_name "$NONCE")"
ROOT="$(resolve_root "$GATE_RUN_ROOT/readiness-$NONCE")"   # physical, or the sandbox denies every write
# --clean removes the run root, EXCEPT when checks failed. Evidence for a failed run is the only
# evidence anyone needs: the first version deleted a 900s timeout's log along with everything else,
# so the one line that could explain the failure was destroyed by the flag meant to keep things
# tidy. A passing run has nothing worth keeping; a failing one is all keep.
cleanup() {
  if [ "$CLEAN" = "1" ] && [ "$FAILURES" -eq 0 ]; then
    rm -rf "$ROOT"
  elif [ "$CLEAN" = "1" ]; then
    printf '%sevidence kept at %s/evidence (checks failed; --clean does not discard that)%s\n' "$DIM" "$ROOT" "$RST"
  fi
}
trap cleanup EXIT

head_ "Run root"
provision_root "$ROOT"
ok "root      $ROOT"
ok "project   $COMPOSE_PROJECT"

head_ "Standalone copy"
make_copy "$ROOT/copy"
ok "copy materialised, .git-free, no escaping symlinks"

SRC_M="$ROOT/evidence/manifest-source.txt"; CPY_M="$ROOT/evidence/manifest-copy.txt"
manifest_source > "$SRC_M"
manifest_copy "$ROOT/copy" > "$CPY_M"
if diff -q "$SRC_M" "$CPY_M" >/dev/null; then
  ok "manifests equal ($(wc -l < "$SRC_M" | tr -d ' ') paths), sha $(git hash-object "$SRC_M")"
else
  bad "manifest mismatch -- the copy is not the referent"
  diff "$SRC_M" "$CPY_M" | head -15
fi

head_ "Caches"
provision_caches "$ROOT" "$REFRESH_CACHES"
check_cache_provenance "$ROOT"

# THE MANIFEST RECHECK BELONGS HERE, NOT AT THE END.
#
# "Manifests match before and after provisioning" means CACHE provisioning -- the step that could
# smuggle host state into the copy. The offline toolchain probes below deliberately write into the
# copy: that is what `install` and `sync` do. An earlier version rechecked after those ran and so
# could only ever report "provisioning mutated the copy", a failure that was purely an artefact of
# where the check stood. The invariant that survives the whole run is the SOURCE being unchanged,
# and that is asserted at the end.
if diff -q "$CPY_M" <(manifest_copy "$ROOT/copy") >/dev/null; then
  ok "copy manifest unchanged by cache provisioning"
else
  bad "cache provisioning mutated the copy"
fi

head_ "Isolation properties (inside the exact gate profile)"
probe="$(sandboxed "$ROOT" "$ROOT/copy" '
  printf "source-write:%s\n"  "$(touch "'"$GATE_REPO"'/.__gate_probe" 2>/dev/null && echo ALLOWED || echo denied)"
  printf "source-read:%s\n"   "$(git -C "'"$GATE_REPO"'" rev-parse HEAD >/dev/null 2>&1 && echo ok || echo FAILED)"
  printf "copy-write:%s\n"    "$(touch ./.__gate_probe 2>/dev/null && rm -f ./.__gate_probe && echo ok || echo FAILED)"
  printf "host-egress:%s\n"   "$(curl -sS --max-time 5 -o /dev/null https://registry-1.docker.io/v2/ 2>/dev/null && echo REACHED || echo blocked)"
' 2>&1)"
rm -f "$GATE_REPO/.__gate_probe" 2>/dev/null
case "$probe" in *source-write:denied*) ok "source write denied" ;; *) bad "THE SOURCE IS WRITABLE from inside the sandbox" ;; esac
case "$probe" in *source-read:ok*)      ok "source readable"     ;; *) bad "source not readable" ;; esac
case "$probe" in *copy-write:ok*)       ok "copy writable"       ;; *) bad "copy not writable" ;; esac
case "$probe" in *host-egress:blocked*) ok "host egress blocked" ;; *) bad "host egress reachable from inside the profile" ;; esac

head_ "Container runtime (inside the exact gate profile)"
dprobe="$(sandboxed "$ROOT" "$ROOT/copy" '
  docker version --format "server={{.Server.Version}}" 2>&1 | head -1
  docker compose version 2>&1 | head -1
  docker buildx version  2>&1 | head -1
  docker compose config >/dev/null 2>&1 && echo "compose-config=ok" || echo "compose-config=FAILED"
' 2>&1)"
printf '%s\n' "$dprobe" | sed 's/^/        /'
case "$dprobe" in *server=*)           ok "daemon reachable over the exact socket" ;; *) bad "daemon unreachable" ;; esac
case "$dprobe" in *"Docker Compose"*)  ok "compose plugin discovered in a fresh HOME" ;; *) bad "compose plugin not discovered" ;; esac
case "$dprobe" in *buildx*)            ok "buildx plugin discovered in a fresh HOME"  ;; *) bad "buildx plugin not discovered" ;; esac
case "$dprobe" in *compose-config=ok*) ok "compose model resolves" ;; *) bad "compose config does not resolve" ;; esac

# ── Runtime behaviours (inside the exact gate profile) ──────────────────────────────────────────
# A CLASS THE REST OF THIS SCRIPT DOES NOT COVER, added because its absence cost a whole gate
# attempt.
#
# Everything above checks PROVISIONING: is the port free, is the image present, is the cache
# populated, does the offline install resolve. All of it passed, the gate was cast, and it failed
# 1,142 times on something none of it models -- whether the profile permits the runtime behaviours
# a real test suite performs once it is running. Those are not provisioning facts and no amount of
# provisioning checking finds them.
#
# The probes here are the behaviours that have actually broken, each reduced to its smallest form.
# They are deliberately about the SANDBOX and the RUNTIME, never about the product: a failure here
# means the environment would refuse a working test suite.
if [ -n "${GATE_JAVA_HOME:-}" ]; then
  head_ "Runtime behaviours (inside the exact gate profile)"
  mkdir -p "$ROOT/probes"

  # Loading an agent into your own JVM. This is what every inline mock maker does on first use, so
  # a denial here is one failure per mocked class rather than one failure.
  cat > "$ROOT/probes/GateAttachProbe.java" <<'JAVA'
import com.sun.tools.attach.VirtualMachine;
public class GateAttachProbe {
  public static void main(String[] a) {
    try {
      VirtualMachine vm = VirtualMachine.attach(String.valueOf(ProcessHandle.current().pid()));
      vm.detach();
      System.out.println("attach:ok");
    } catch (Throwable e) {
      System.out.println("attach:FAILED " + e);
    }
  }
}
JAVA

  # A loopback round trip THROUGH A JVM SOCKET, which is not the same probe as reaching a port.
  # A dual-stack JVM presents 127.0.0.1 to the kernel as ::ffff:127.0.0.1, an address SBPL cannot
  # express, so a filtered profile denies the JVM while every other client on the machine succeeds.
  cat > "$ROOT/probes/GateLoopbackProbe.java" <<'JAVA'
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
public class GateLoopbackProbe {
  public static void main(String[] a) {
    try (ServerSocket server = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))) {
      Thread t = new Thread(() -> {
        try (Socket peer = server.accept(); OutputStream out = peer.getOutputStream()) {
          out.write(42);
        } catch (Exception ignored) { }
      });
      t.setDaemon(true);
      t.start();
      try (Socket client = new Socket()) {
        client.connect(new InetSocketAddress("127.0.0.1", server.getLocalPort()), 5000);
        InputStream in = client.getInputStream();
        System.out.println(in.read() == 42 ? "loopback:ok" : "loopback:FAILED wrong byte");
      }
    } catch (Throwable e) {
      System.out.println("loopback:FAILED " + e);
    }
  }
}
JAVA

  rprobe="$(sandboxed "$ROOT" "$ROOT/probes" '
    java GateAttachProbe.java   2>&1 | grep "^attach:"   || echo "attach:FAILED probe did not run"
    java GateLoopbackProbe.java 2>&1 | grep "^loopback:" || echo "loopback:FAILED probe did not run"
  ' 180 2>&1)"
  printf '%s\n' "$rprobe" | grep -v '^\(attach\|loopback\):ok$' | sed 's/^/        /'
  case "$rprobe" in
    *attach:ok*) ok "JVM can load an agent into itself (inline mock makers need this)" ;;
    *) bad "JVM agent self-attach is DENIED -- every inline-mocked test will fail, and the exception will name the mocking library rather than this" ;;
  esac
  case "$rprobe" in
    *loopback:ok*) ok "JVM loopback round trip (dual-stack IPv4, the shape that breaks)" ;;
    *) bad "a JVM cannot complete a loopback round trip -- build daemons and test containers will report themselves unreachable" ;;
  esac

  # Heap is a RESOURCE fact, not a permission one, and it is checked here because it fails in the
  # same place and reads the same way: an OutOfMemoryError inside a test worker surfaces as the
  # framework failing to start, not as a memory problem. Only checked when a project states what it
  # needs; this skill will not invent a number.
  if [ -n "${GATE_MIN_HEAP_MB:-}" ]; then
    cat > "$ROOT/probes/GateHeapProbe.java" <<'JAVA'
public class GateHeapProbe {
  public static void main(String[] a) {
    int mb = Integer.parseInt(a[0]);
    try {
      byte[][] held = new byte[mb][];
      for (int i = 0; i < mb; i++) {
        held[i] = new byte[1024 * 1024];
        held[i][0] = 1;   // touch it: reserving address space is not the same as having the memory
      }
      System.out.println("heap:ok " + mb + "m reserved and touched");
    } catch (Throwable e) {
      System.out.println("heap:FAILED " + e);
    }
  }
}
JAVA
    hprobe="$(sandboxed "$ROOT" "$ROOT/probes" "
      java -Xmx$(( GATE_MIN_HEAP_MB + 96 ))m GateHeapProbe.java $GATE_MIN_HEAP_MB 2>&1 | grep '^heap:' || echo 'heap:FAILED probe did not run'
    " 180 2>&1)"
    case "$hprobe" in
      *heap:ok*) ok "a forked JVM can reserve and touch ${GATE_MIN_HEAP_MB}m of heap" ;;
      *) bad "a JVM cannot obtain ${GATE_MIN_HEAP_MB}m of heap here -- test workers will die with OutOfMemoryError, which presents as the test framework failing to start"
         printf '%s\n' "$hprobe" | sed 's/^/        /' ;;
    esac
  fi
fi

if [ -n "$GATE_PORTS" ]; then
  head_ "Host preconditions"
  busy=""
  for p in $GATE_PORTS; do lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && busy="$busy $p"; done
  if [ -z "$busy" ]; then ok "all required ports clear ($GATE_PORTS)"
  else bad "ports in use:$busy (do NOT kill unrelated listeners -- they are not yours)"; fi
  if docker compose ls --all --format json 2>/dev/null | grep -q "\"Name\":\"$COMPOSE_PROJECT\""; then
    bad "compose project $COMPOSE_PROJECT already exists"
  else ok "compose project name is unused"; fi
fi

if [ -n "$GATE_IMAGES" ]; then
  head_ "Base images"
  for t in $GATE_IMAGES; do
    if docker image inspect "$t" >/dev/null 2>&1; then ok "$t"; else bad "$t MISSING"; fi
  done
fi

if [ "${#GATE_OFFLINE_STEPS[@]}" -gt 0 ]; then
  head_ "Offline toolchains (inside the exact gate profile)"
  # Bounded individually. These are the slow checks and the ones most likely to hang offline; each
  # reports ok / FAILED / TIMEOUT on its own line so one stall does not hide the others.
  for step in "${GATE_OFFLINE_STEPS[@]}"; do
    label="${step%%|*}"; rest="${step#*|}"; secs="${rest%%|*}"; cmd="${rest#*|}"
    printf '  %-10s ' "$label"
    if sandboxed "$ROOT" "$ROOT/copy" "$cmd" "$secs" >"$ROOT/evidence/$label.log" 2>&1; then
      printf '%sok%s\n' "$GRN" "$RST"
    else
      rc=$?
      if [ "$rc" = "124" ]; then
        printf '%sTIMEOUT%s after %ss (distinct from a failure -- see evidence/%s.log)\n' "$YEL" "$RST" "$secs" "$label"
      else
        printf '%sFAILED%s (rc=%s, see evidence/%s.log)\n' "$RED" "$RST" "$rc" "$label"
      fi
      FAILURES=$((FAILURES+1))
    fi
  done
fi

if [ -n "${GATE_HOME_SEED:-}" ]; then
  head_ "Seeded into the temporary HOME"
  for src in $GATE_HOME_SEED; do
    if [ ! -e "$src" ]; then warn "$src absent on the host -- not seeded"; continue; fi
    dest="$ROOT/home/${src#"$HOME"/}"
    mkdir -p "$(dirname "$dest")"
    if cp -c -R "$src" "$dest" 2>/dev/null || cp -R "$src" "$dest" 2>/dev/null; then ok "${src#"$HOME"/}"
    else bad "${src#"$HOME"/} could not be seeded"; fi
  done
fi

if [ -n "$GATE_LOCKFILES" ]; then
  head_ "Lockfiles byte-identical (source vs copy)"
  for lf in $GATE_LOCKFILES; do
    if [ ! -f "$GATE_REPO/$lf" ]; then warn "$lf not present in the checkout"; continue; fi
    if cmp -s "$GATE_REPO/$lf" "$ROOT/copy/$lf"; then ok "$lf"; else bad "$lf differs between source and copy"; fi
  done
fi

head_ "Verdict"
if assert_source_unchanged; then ok "source still at the referent, still clean"
else bad "THE SOURCE MOVED during the run -- nothing observed here describes the referent"; fi

echo
if [ "$FAILURES" -eq 0 ]; then
  printf '%sREADY%s -- every non-semantic check passed. A gate cast may be requested.\n' "$GRN" "$RST"
  printf '%sPreparation only. This says nothing about product behaviour, and the container runtime\n' "$DIM"
  printf 'was reachable throughout: it is not a claim that the gate will run offline.%s\n' "$RST"
else
  printf '%sNOT READY%s -- %s check(s) failed. Do not spend a semantic gate attempt.\n' "$RED" "$RST" "$FAILURES"
fi
[ "$CLEAN" = "1" ] || printf '%srun root kept at %s%s\n' "$DIM" "$ROOT" "$RST"
exit $(( FAILURES > 0 ))
