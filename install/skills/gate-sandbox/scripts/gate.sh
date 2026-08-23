#!/usr/bin/env bash
# The gate launcher.
#
# Runs the EXACT configured gate argv against a manifest-equal standalone copy of the bound
# referent, inside the enforced profile, and persists evidence BEFORE removing anything.
#
#   gate.sh                 refuse unless the readiness phase passes, then run the gate
#   gate.sh --force         run even if readiness failed (recorded in the receipt as forced)
#   gate.sh --keep          leave the run root in place, for inspecting a failure
#   gate.sh --config <path> use a specific project configuration
#
# WHAT THIS DOES NOT CLAIM. The gate reaches the container daemon through its socket, and that
# daemon lives OUTSIDE this sandbox. Host egress is denied and provable; image pulls, build steps and
# container egress are constrained by nothing here. A receipt from this launcher may say "host
# network denied". It may never say "the gate ran offline".
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$HERE/gate_lib.sh"

FORCE=0; KEEP=0; CONFIG=""
while [ $# -gt 0 ]; do case "$1" in
  --force) FORCE=1 ;;
  --keep) KEEP=1 ;;
  --config) shift; CONFIG="${1:-}" ;;
  *) die "unknown option: $1" ;;
esac; shift; done

gate_load_config "$CONFIG"

printf '%sSandboxed gate%s\n' "$DIM" "$RST"
printf '%sconfig: %s%s\n' "$DIM" "$GATE_CONFIG_PATH" "$RST"

# ── Freeze and bind ─────────────────────────────────────────────────────────────────────────────
head_ "Referent"
resolve_referent
ok "referent $REFERENT"

NONCE="$(date +%s)$$"
COMPOSE_PROJECT="$(compose_project_name "$NONCE")"
ROOT="$(resolve_root "$GATE_RUN_ROOT/gate-$NONCE")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
KEEP_DIR="$GATE_EVIDENCE_ROOT/$STAMP-$(printf '%s' "$REFERENT" | cut -c1-12)"
mkdir -p "$KEEP_DIR"

# ── Readiness precondition ──────────────────────────────────────────────────────────────────────
# Making the rule a MECHANISM rather than a note. A gate attempt blocked on provisioning costs the
# full price of the attempt and returns nothing -- and --force is recorded in the receipt rather
# than passing silently, because "we skipped the check" is a fact the reader is entitled to.
head_ "Readiness precondition"
if [ "$FORCE" = "1" ]; then
  warn "FORCED -- readiness not required for this run; the receipt says so"
else
  say "running the readiness phase first (its run root is separate and disposable)"
  if "$HERE/readiness.sh" --clean ${CONFIG:+--config "$CONFIG"} >"$KEEP_DIR/readiness.log" 2>&1; then
    ok "readiness passed"
  else
    die "readiness FAILED -- not spending a gate attempt. See $KEEP_DIR/readiness.log
       Fix what it named, or re-run with --force if you accept spending the attempt."
  fi
fi

# ── The standalone copy ─────────────────────────────────────────────────────────────────────────
head_ "Standalone copy"
provision_root "$ROOT"
make_copy "$ROOT/copy"
manifest_source > "$ROOT/evidence/manifest-source.txt"
manifest_copy "$ROOT/copy" > "$ROOT/evidence/manifest-copy.txt"
diff -q "$ROOT/evidence/manifest-source.txt" "$ROOT/evidence/manifest-copy.txt" >/dev/null \
  || die "manifest mismatch before the gate -- the copy is not the referent"
MANIFEST_SHA="$(git hash-object "$ROOT/evidence/manifest-source.txt")"
MANIFEST_PATHS="$(wc -l < "$ROOT/evidence/manifest-source.txt" | tr -d ' ')"
ok "manifest-equal, $MANIFEST_PATHS paths, sha $MANIFEST_SHA"

head_ "Caches"
provision_caches "$ROOT" 0

# ── The exact gate argv ─────────────────────────────────────────────────────────────────────────
head_ "Gate"
say "project  $COMPOSE_PROJECT"
say "argv     $GATE_ARGV"
printf '%s\n' "$GATE_ARGV" > "$ROOT/evidence/gate-argv.txt"

START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
sandboxed "$ROOT" "$ROOT/copy" "$GATE_ARGV" 2>&1 | tee "$ROOT/evidence/gate.log"
GATE_RC="${PIPESTATUS[0]}"
END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── The unchanged-source recheck ────────────────────────────────────────────────────────────────
head_ "Post-run integrity"
if assert_source_unchanged; then SOURCE_OK=1; ok "source unchanged and still at the referent"
else SOURCE_OK=0; bad "the source moved during the gate -- this run does not describe the referent"; fi

# ── Persist evidence BEFORE cleanup ─────────────────────────────────────────────────────────────
head_ "Evidence"
cp -R "$ROOT/evidence/." "$KEEP_DIR/" 2>/dev/null
cp "$ROOT/profile.sb" "$KEEP_DIR/profile.sb" 2>/dev/null
{
  printf '# Sandboxed gate receipt\n\n'
  printf 'referent          : %s\n' "$REFERENT"
  printf 'branch            : %s\n' "$REFERENT_BRANCH"
  printf 'manifest sha      : %s\n' "$MANIFEST_SHA"
  printf 'manifest paths    : %s\n' "$MANIFEST_PATHS"
  printf 'compose project   : %s\n' "$COMPOSE_PROJECT"
  printf 'gate argv         : %s\n' "$GATE_ARGV"
  printf 'started           : %s\n' "$START"
  printf 'ended             : %s\n' "$END"
  printf 'exit code         : %s\n' "$GATE_RC"
  printf 'cache source      : %s (shared between runs; not part of the referent)\n' "$CACHE_SOURCE"
  if [ "$FORCE" = "1" ]; then printf 'readiness         : NOT RUN -- forced with --force\n'
  else printf 'readiness         : passed before this run\n'; fi
  if [ "$SOURCE_OK" = "1" ]; then printf 'source unchanged  : yes\n'
  else printf 'source unchanged  : NO -- this receipt certifies nothing\n'; fi
  cat <<'BOUNDARY'

## The boundary of this receipt

Enforced by the macOS profile, and provable: the source is read-only, writes are confined to the
run root and the shared cache root, host egress is denied, and the daemon is reachable only over
one literal socket path.

NOT enforced by it: image pulls, build steps, and container egress. The daemon runs outside this
sandbox, so this run MUST NOT be described as offline or network-isolated.

## Test counts

Read them from gate.log. A run reporting zero tests is a provisioning block, NOT a product verdict,
and must never be recorded as one.
BOUNDARY
} > "$KEEP_DIR/receipt.md"
ok "evidence persisted to $KEEP_DIR"

# ── Remove ONLY what this run owns ──────────────────────────────────────────────────────────────
head_ "Cleanup"
if [ "$KEEP" = "1" ]; then
  warn "--keep given; run root left at $ROOT"
else
  # The owned project, by its unique name. Never a global prune -- a developer machine carries
  # unrelated historical containers, images and volumes that are not this run's to touch.
  down="$(sandboxed "$ROOT" "$ROOT/copy" "docker compose down --volumes --remove-orphans" 2>&1 | tail -3)"
  printf '        %s\n' "$down"
  if docker compose ls --all --format json 2>/dev/null | grep -q "\"Name\":\"$COMPOSE_PROJECT\""; then
    bad "compose project $COMPOSE_PROJECT still exists after down -- remove it by hand"
  else ok "owned compose project removed"; fi
  rm -rf "$ROOT"
  if [ -e "$ROOT" ]; then bad "run root not removed: $ROOT"; else ok "run root removed"; fi
fi

head_ "Verdict"
printf '  gate exit code: %s\n' "$GATE_RC"
if [ "$GATE_RC" = "0" ] && [ "$SOURCE_OK" = "1" ] && [ "$FAILURES" -eq 0 ]; then
  printf '  %sGATE PASSED%s -- read the test counts in gate.log before calling this evidence.\n' "$GRN" "$RST"
else
  printf '  %sGATE DID NOT PASS%s -- diagnose it; do not retry a semantic failure.\n' "$RED" "$RST"
fi
printf '  %sreceipt: %s/receipt.md%s\n' "$DIM" "$KEEP_DIR" "$RST"
exit "$GATE_RC"
