# Shared machinery for the sandboxed gate. Sourced, never executed.
#
# The whole point of this file is that the READINESS phase and the GATE phase build the identical
# environment. A readiness check that proves something about a DIFFERENT environment than the gate
# runs in has proven nothing, and that is the easiest mistake to make here, because the two are
# separate scripts and it costs nothing to let them drift. So both call the same four functions --
# make_copy, provision_root, write_profile, sandboxed -- and nothing builds an environment inline.
#
# No project fact appears below. Everything specific arrives from gate_config.sh.

set -uo pipefail

GATE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$GATE_LIB_DIR/gate_config.sh"

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; RST=$'\033[0m'
FAILURES=0

say()   { printf '  %s\n' "$*"; }
head_() { printf '\n%s── %s%s\n' "$DIM" "$*" "$RST"; }
ok()    { printf '  %sok%s    %s\n' "$GRN" "$RST" "$*"; }
warn()  { printf '  %swarn%s  %s\n' "$YEL" "$RST" "$*"; }
bad()   { printf '  %sFAIL%s  %s\n' "$RED" "$RST" "$*"; FAILURES=$((FAILURES+1)); }
die()   { printf '\n%sSTOP%s  %s\n' "$RED" "$RST" "$*" >&2; exit 2; }

# ── The referent ────────────────────────────────────────────────────────────────────────────────
# "Freeze writers and bind the full source sha." Freezing writers cannot be enforced by a script --
# nothing here can stop another process writing to the checkout -- so what this does instead is bind
# and then RE-CHECK: resolve_referent records the sha and the tree state, assert_source_unchanged
# runs again afterwards. A source that moved under the gate invalidates the evidence, and that is
# detectable even though it is not preventable.
resolve_referent() {
  local head branch dirty
  head="$(git -C "$GATE_REPO" rev-parse HEAD 2>/dev/null)" || die "cannot resolve HEAD in $GATE_REPO"
  branch="$(git -C "$GATE_REPO" rev-parse --abbrev-ref HEAD)"
  dirty="$(git -C "$GATE_REPO" status --porcelain -uall | wc -l | tr -d ' ')"

  # GATE_REFERENT is an OPTIONAL pin. Empty means "bind whatever HEAD is now", which is still a
  # binding -- the sha is recorded and rechecked. Setting it is for a frozen milestone, where
  # running against a different tree is the specific accident worth refusing.
  if [ -n "$GATE_REFERENT" ] && [ "$head" != "$GATE_REFERENT" ]; then
    die "HEAD is $head but the pinned referent is $GATE_REFERENT.
       Either check that commit out, or change GATE_REFERENT deliberately -- do not let the gate
       silently run against a tree nobody named."
  fi
  if [ -n "$GATE_BRANCH" ] && [ "$branch" != "$GATE_BRANCH" ]; then
    die "on branch $branch, expected $GATE_BRANCH"
  fi
  # A dirty tree cannot be manifest-equal to `git archive HEAD`, and the copy is built from HEAD.
  # Refusing here is the difference between "the gate tested the referent" and "the gate tested
  # something nobody can name".
  [ "$dirty" = "0" ] || die "the checkout has $dirty uncommitted path(s); the copy is built from HEAD, so the gate would not test what is on disk"
  REFERENT="$head"
  REFERENT_BRANCH="$branch"
}

assert_source_unchanged() {
  local head dirty
  head="$(git -C "$GATE_REPO" rev-parse HEAD 2>/dev/null)"
  dirty="$(git -C "$GATE_REPO" status --porcelain -uall | wc -l | tr -d ' ')"
  [ "$head" = "$REFERENT" ] && [ "$dirty" = "0" ]
}

# ── Manifest ────────────────────────────────────────────────────────────────────────────────────
# Canonical, and canonical means DERIVED THE SAME WAY ON BOTH SIDES or it proves nothing. The source
# manifest is git's own index of the commit (mode, blob sha, path). The copy manifest is recomputed
# with git hash-object over the extracted files. Same hash function, same normalisation, so equality
# is a real claim rather than two different summaries that happen to have equal lengths.
manifest_source() {
  git -C "$GATE_REPO" ls-tree -r --full-tree "$REFERENT" \
    | awk '{printf "%s %s %s\n", $1, $3, substr($0, index($0,$4))}' | LC_ALL=C sort
}

# BATCHED, and the reason is measurable rather than stylistic. The first version called
# `git hash-object` once per file, and the manifest is computed twice per run -- on a 2000-file tree
# that is ~4000 process spawns, which dominated the entire readiness phase. `--stdin-paths` hashes
# the same files in one process. Same hash, same ordering, same comparison; only the process count
# changes, and it was verified to produce a byte-identical manifest before it was kept.
manifest_copy() {
  local root="$1"
  ( cd "$root" || return 1
    find . -type f | sed 's|^\./||' | LC_ALL=C sort > .__paths
    if [ -s .__paths ]; then
      git hash-object --stdin-paths < .__paths > .__hashes
      # Mode is git's own distinction: 100755 if executable by the owner, else 100644.
      paste -d' ' .__hashes .__paths | while IFS=' ' read -r h f; do
        case "$f" in .__paths|.__hashes) continue ;; esac
        if [ -x "$f" ]; then printf '100755 %s %s\n' "$h" "$f"; else printf '100644 %s %s\n' "$h" "$f"; fi
      done
    fi
    # Symlinks: hashed over the TARGET STRING, exactly as git stores mode 120000. Following the link
    # instead would silently resolve an escaping link to whatever it points at, which is the one
    # thing the copy must not do.
    find . -type l | sed 's|^\./||' | LC_ALL=C sort | while IFS= read -r l; do
      [ -n "$l" ] || continue
      printf '120000 %s %s\n' "$(printf '%s' "$(readlink "$l")" | git hash-object --stdin)" "$l"
    done
    rm -f .__paths .__hashes
  ) | LC_ALL=C sort
}

# ── The standalone copy ─────────────────────────────────────────────────────────────────────────
# `git archive` satisfies most of the isolation requirements BY CONSTRUCTION rather than by a list
# of exclusions somebody has to keep correct:
#   .git-free            -- archive emits no .git
#   no ignored outputs   -- archive emits tracked paths only, so build/, node_modules/, .venv/,
#                           test XML and coverage cannot appear even if they exist in the checkout
#   no hard links        -- tar extraction writes fresh inodes
#   no shared objects    -- there is no object store in the output at all
#   no unresolved refs   -- an archive of a resolved commit has no external object references
# What archive does NOT check is the escaping symlink, so that is checked explicitly.
make_copy() {
  local dest="$1"
  mkdir -p "$dest"
  git -C "$GATE_REPO" archive --format=tar "$REFERENT" | ( cd "$dest" && tar -xf - )

  local escapes; escapes="$(escaping_symlinks "$dest")"
  [ -z "$escapes" ] || die "the copy contains symlink(s) escaping it; isolation would be a claim rather than a fact:
$escapes"
}

# Every symlink inside <dir> whose target resolves OUTSIDE it, one per line. Empty output means the
# tree is self-contained.
#
# A link escaping the copy re-opens the source -- or anything else -- as a path the gate can reach,
# which defeats the whole reason the copy exists.
#
# Its own function, not inline in make_copy, because a rule that can only be exercised by building a
# whole repository copy is a rule that never gets a test.
escaping_symlinks() {
  local dir="$1" l target resolved
  dir="$(cd "$dir" && pwd -P)"
  while IFS= read -r l; do
    [ -n "$l" ] || continue
    target="$(readlink "$dir/$l")"
    case "$target" in
      /*) resolved="$target" ;;
       *) resolved="$(cd "$(dirname "$dir/$l")" 2>/dev/null && pwd -P)/$target" ;;
    esac
    # Normalise .. segments so `a/../../etc/passwd` cannot hide inside a prefix match.
    resolved="$(python3 -c 'import os,sys; print(os.path.normpath(sys.argv[1]))' "$resolved")"
    case "$resolved/" in
      "$dir"/*) ;;
      *) printf '  %s -> %s\n' "$l" "$target" ;;
    esac
  done < <(cd "$dir" && find . -type l | sed 's|^\./||')
}

# ── Caches ──────────────────────────────────────────────────────────────────────────────────────
# SHARED BETWEEN RUNS, AND THAT IS A DELIBERATE SPLIT FROM THE COPY.
#
# The COPY must be fresh every run -- it is the referent under test. The caches must not be: they are
# imported host state that no receipt claims anything about. Cloning tens of gigabytes of language
# caches per run costs minutes even with APFS clones, because the cost is per-file syscalls across
# hundreds of thousands of small files rather than bytes. Measured: it dominated the entire readiness
# phase, and a readiness check too slow to run before every attempt is one that stops being run
# before any attempt -- which is the whole failure this phase exists to prevent.
#
# So the clone lands once in a shared root and every later run reuses it. --refresh-caches rebuilds
# it, and the receipt records which was used, because "reused a cache from a previous run" is a fact
# a reader of the evidence is entitled to.
shared_cache_root() { resolve_root "$GATE_RUN_ROOT/shared-caches"; }

# APFS clones (`cp -c`), not copies and not links: near constant-time, no extra disk, and a fresh
# inode the sandbox may write to. A hard link would let the run corrupt the host cache; a plain
# recursive copy of a multi-gigabyte cache would make every readiness run cost minutes.
clone_cache() {
  local src="$1" dst="$2" label="$3"
  if [ ! -d "$src" ]; then warn "$label absent at $src -- offline steps that need it will fail"; return 0; fi
  mkdir -p "$(dirname "$dst")"
  if cp -c -R "$src" "$dst" 2>/dev/null; then ok "$label cloned (APFS clone, no extra disk)"
  elif cp -R "$src" "$dst" 2>/dev/null;  then warn "$label copied (clone unavailable -- slower, uses disk)"
  else bad "$label could not be provisioned"; return 0; fi
  # The census this clone is judged against later. See check_cache_content.
  cache_file_count "$dst" > "$(shared_cache_root)/.provisioned/$(basename "$dst").count"
}

cache_file_count() { find "$1" -type f 2>/dev/null | wc -l | tr -d " "; }

# A CACHE ROOT THAT STILL EXISTS IS NOT A CACHE ROOT THAT STILL HAS ANYTHING IN IT.
#
# The shared clone lives under $TMPDIR, which the operating system reaps. It reaps FILES and leaves
# DIRECTORIES, so the tree keeps its shape while its contents go: measured, one day after
# provisioning, gradle held 594 of 117,347 files and pnpm held 2 of 123,756. The `.provisioned`
# marker directory survived intact, so provisioning reported "shared caches reused" and every
# offline step then failed as though the project were misconfigured -- a download attempt from a
# wrapper, a missing tarball, a missing wheel. None of it looked like a cache problem.
#
# Reusing a marker to decide a cache is present is the same defect as trusting any other marker over
# the thing it stands for. This counts.
check_cache_content() { # check_cache_content
  local shared kind recorded now
  shared="$(shared_cache_root)"
  for kind in ${GATE_CACHES[@]+"${GATE_CACHES[@]}"}; do
    [ -d "$shared/$kind" ] || { bad "$kind cache directory is gone from the shared clone"; continue; }
    recorded="$(cat "$shared/.provisioned/$kind.count" 2>/dev/null || echo "")"
    now="$(cache_file_count "$shared/$kind")"
    if [ -z "$recorded" ]; then
      warn "$kind clone holds $now files, but no census was recorded when it was made -- re-run with --refresh-caches to establish one"
    elif [ "$now" -lt $(( recorded * 95 / 100 )) ]; then
      bad "$kind clone has lost content: $now files now, $recorded when cloned. \$TMPDIR is reaped -- re-run with --refresh-caches"
    else
      ok "$kind clone intact ($now files, census $recorded)"
    fi
  done
}

provision_caches() { # provision_caches <run-root> [refresh]
  local root="$1" refresh="${2:-0}" shared kind path var
  shared="$(shared_cache_root)"
  if [ "$refresh" = "1" ]; then say "refreshing the shared cache root from the host"; rm -rf "$shared"; shared="$(shared_cache_root)"; fi

  if [ "${#GATE_CACHES[@]}" -eq 0 ]; then
    say "no caches requested (GATE_CACHES is empty)"
  elif [ -d "$shared/.provisioned" ]; then
    ok "shared caches reused from $shared"
  else
    say "first run: cloning host caches into $shared (once; later runs reuse it)"
    mkdir -p "$shared/.provisioned"
    for kind in "${GATE_CACHES[@]}"; do
      var="GATE_CACHE_PATH_$kind"; path="${!var:-}"
      [ -n "$path" ] || { warn "no host path known for cache kind '$kind'"; continue; }
      clone_cache "$path" "$shared/$kind" "$kind cache"
    done
    mkdir -p "$shared/.provisioned"
  fi
  # The run gets its own view by symlink rather than another copy.
  rm -rf "$root/caches"
  ln -s "$shared" "$root/caches"
  CACHE_SOURCE="$shared"
  check_cache_targets "$root"
  check_cache_agreement "$root"
}

# THE VARIABLE EXISTED, POINTED SOMEWHERE REAL, AND THE TOOL IGNORED IT.
#
# check_cache_targets asserts the path exists, which is necessary and was not sufficient: pnpm was
# handed a correct path through a variable it does not read, so the check passed and the toolchain
# still used an empty default store. The only honest question is whether the TOOL AGREES about
# where its cache is, so that is what this asks — of the tool, not of our configuration.
check_cache_agreement() {
  local root="$1" kind reported
  for kind in ${GATE_CACHES[@]+"${GATE_CACHES[@]}"}; do
    case "$kind" in
      pnpm)
        # Asked through the ONLY mechanism that works. pnpm's store location is settable by
        # `--store-dir` and by nothing else: not PNPM_STORE_PATH, not npm_config_store_dir, and not
        # a `store-dir=` line in .npmrc, .config/pnpm/rc or .config/npm/npmrc — all four were tried
        # and all four were silently ignored. So a project's probe must pass the flag, and this
        # verifies the flag reaches the provisioned cache rather than verifying our own intent.
        command -v pnpm >/dev/null 2>&1 || continue
        reported="$(HOME="$root/home" pnpm store path --store-dir "$root/caches/pnpm" 2>/dev/null)"
        case "$reported" in
          "$root/caches/pnpm"/*)
            ok "pnpm resolves --store-dir to the provisioned cache (\$GATE_CACHE_DIR_pnpm)" ;;
          *)
            bad "pnpm resolves --store-dir to ${reported:-<unknown>}, not the provisioned cache" ;;
        esac ;;
    esac
  done
}

# EVERY VARIABLE HANDED TO A TOOLCHAIN MUST POINT AT SOMETHING THAT EXISTS.
#
# A cache variable aimed at a path the clone never created does not fail — the toolchain creates the
# directory, finds it empty, and behaves as though it has no cache at all. Offline then fails for a
# reason that has nothing to do with being offline. That is exactly how a mistyped pnpm store path
# presented as a 900-second timeout, with the log saying only that it had not finished.
check_cache_targets() {
  local root="$1" kind line var path
  for kind in ${GATE_CACHES[@]+"${GATE_CACHES[@]}"}; do
    var="GATE_CACHE_PATH_$kind"; [ -n "${!var:-}" ] || continue
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      path="${line#*=}"
      case "$path" in
        *.pnpm-home) continue ;;   # a bin directory the toolchain creates; not a cache lookup
        -*) continue ;;            # a flag, not a path (maven passes -Dmaven.repo.local=...)
      esac
      [ -e "$path" ] || bad "$kind cache: ${line%%=*} points at $path, which does not exist — the toolchain will see an EMPTY cache and offline steps will fail for the wrong reason"
    done < <(gate_cache_env_vars "$kind" "$root/caches/$kind")
  done
}

# "The imported caches contain no project build/test outputs" is true BY CONSTRUCTION -- only host
# cache directories are cloned, never the checkout -- so the honest check is of the CONSTRUCTION.
#
# The first version scanned the clone for a bare `classes` directory and flagged five hits inside
# Gradle's OWN internal build-script cache, which is exactly what an offline Gradle needs. A check
# that reports a healthy cache as contamination gets switched off, and then it checks nothing.
check_cache_provenance() {
  local root="$1" kind var path polluted
  for kind in ${GATE_CACHES[@]+"${GATE_CACHES[@]}"}; do
    var="GATE_CACHE_PATH_$kind"; path="${!var:-}"
    [ -n "$path" ] || continue
    case "$path/" in
      "$GATE_REPO"/*) bad "cache source $path lies INSIDE the checkout -- importing it would import project outputs" ;;
    esac
  done
  # Names with no legitimate place in a LANGUAGE cache; they appear only if a cache path was aimed at
  # a project directory. `build` and `classes` are deliberately absent: Gradle owns both inside its
  # own cache.
  polluted="$(find "$root/caches" -maxdepth 4 \( -name node_modules -o -name .venv -o -name test-results \) -print 2>/dev/null | head -5)"
  if [ -z "$polluted" ]; then ok "caches are host caches only; no checkout outputs imported"
  else bad "imported caches contain project outputs -- they must never be imported:"; printf '        %s\n' $polluted; fi
}

# ── The sandbox profile ─────────────────────────────────────────────────────────────────────────
# Rendered per run, because the temporary root is per run.
#
# WHY sandbox-exec DIRECTLY. The methodology reference prescribes `codex sandbox -p gate -P
# copy-write`. That named profile did not exist on the machine this was built on -- no CODEX_HOME
# config declared it -- and the schema behind it is undocumented; probing recovered four of five
# fields and every minimal profile died on a silent SIGABRT with no denials logged. `codex sandbox`
# runs seatbelt underneath, which is what sandbox-exec is, so this reaches the same enforcement
# mechanism directly, under our own control, without depending on CLI internals that move between
# versions.
#
# THE BOUNDARY THIS DOES NOT DRAW, stated here because a receipt that overclaims it is worse than no
# receipt: allowing the container runtime's socket hands the inner process control of a daemon that
# lives OUTSIDE this profile. Host egress is denied and that is provable, but image pulls, build
# steps and containers are not constrained by any of it. A green run here is never "the gate ran
# offline".
write_profile() {
  local root="$1" out="$2"
  cat > "$out" <<SBPL
(version 1)
(deny default)
(allow process-exec process-fork signal)
(allow sysctl-read mach-lookup ipc-posix-shm)

; The source is READ, never written. The read grant is broad on purpose: toolchains resolve
; interpreters, libraries and SDKs from all over the filesystem, and a narrow read list becomes an
; endless chase of denials that ends with somebody widening the WRITE rules to make it stop.
(allow file-read*)
; A RESTATEMENT, NOT THE ENFORCEMENT. The deny-default line above already denies every write; deleting
; this line changes nothing, and the selftest was mutated to prove exactly that -- it survived. It
; stays because a reader scanning the profile for "are writes denied?" should find the answer
; without having to reason from deny-default, but nobody should believe it is what holds the line.
(deny file-write*)
(allow file-write* (subpath "$root"))
; The shared cache root lives BESIDE the run root, not under it, so it needs its own grant: a
; symlink does not inherit the permission of the directory holding it, and every language toolchain
; writes to its cache during a normal run. Without this line each cached build fails with a denial
; that looks exactly like a corrupt cache.
(allow file-write* (subpath "$(shared_cache_root)"))

; Devices a shell pipeline cannot run without. Enumerated rather than granting /dev wholesale.
(allow file-write-data
  (literal "/dev/null") (literal "/dev/zero") (literal "/dev/random") (literal "/dev/urandom")
  (literal "/dev/stdout") (literal "/dev/stderr") (literal "/dev/tty"))
(allow file-ioctl (literal "/dev/tty"))

; The EXACT socket, by literal path. Not a subpath of its directory, not a wildcard.
(allow network-outbound (literal "$GATE_DOCKER_SOCKET"))

; OUTBOUND is the restricted direction, and it stays restricted: loopback only, plus the one
; daemon socket granted above. Nothing in this profile can reach the internet, and that is the
; property the receipt depends on.
(allow network-outbound (remote ip "localhost:*"))

; BIND AND INBOUND ARE UNFILTERED, deliberately, with a measured cause.
;
; A JVM on macOS binds IPv4 loopback through a DUAL-STACK socket, so the kernel sees
; ::ffff:127.0.0.1 and no (local ip "localhost:*") filter matches it. Measured with a control: in
; the filtered profile the JVM's bind to 127.0.0.1 is denied while its bind to ::1 succeeds, and
; Python's bind to 127.0.0.1 succeeds -- the difference is the socket, not the address. It presents
; as "Unable to start the daemon process", which sends you to look at the daemon.
;
; Both are required together; each alone still denies the bind, and the filtered forms
; (local ip "*:*") do not help. Tested, not assumed.
;
; What this widens: listening, not reaching out. The residual exposure is a listening socket on a
; non-loopback address, and that is not a new class here -- the compose stack already publishes
; host ports from OUTSIDE this sandbox entirely.
(allow network-bind)
(allow network-inbound)
SBPL

  # THE AGENT-ATTACH HANDSHAKE, granted only when this is a JVM gate.
  #
  # A JVM that loads an agent into itself -- which is what every inline-mock-maker test framework
  # does -- performs a handshake through the PER-USER temp directory: the target binds a unix socket
  # at <darwin-temp>/.java_pid<pid> and the client writes <darwin-temp>/.attach_pid<pid>. That
  # directory is NOT $TMPDIR and does not follow it (see GATE_DARWIN_TEMP_DIR), so it falls outside
  # every write grant above and the handshake is denied.
  #
  # It presents as a mass failure of unrelated tests -- one denial per mock -- with an exception
  # that names the mocking library, so the whole search goes to the test code. Measured: 1,142
  # failures in one run, all of them this.
  #
  # BOTH OPERATIONS ARE REQUIRED TOGETHER. Tested with a control: write alone and connect alone each
  # still fail. file-write* creates the two files; network-outbound is the client CONNECTING to the
  # unix socket, which SBPL treats as an outbound operation on a path rather than a file one.
  #
  # DELIBERATELY UNANCHORED AT THE END. The socket is bound under a suffixed temporary name and
  # renamed into place, so a pattern ending in [0-9]+$ matches the final name and not the one
  # actually created -- which fails as "target process doesn't respond within 10500ms", i.e. as a
  # hung JVM rather than as a denied write. Anchored at the start only.
  #
  # This does NOT widen the temp directory: everything there that is not an attach file stays
  # denied, and egress to a raw address is still refused. Both re-verified with controls.
  if [ -n "${GATE_JAVA_HOME:-}" ]; then
    cat >> "$out" <<SBPL

(allow file-write* network-outbound
  (regex #"^$GATE_DARWIN_TEMP_DIR/\.(java_pid|attach_pid)[0-9]+"))
SBPL
  fi
}

# ── Provisioning the run root ───────────────────────────────────────────────────────────────────
# THE RUN ROOT MUST BE A PHYSICAL PATH BEFORE THE PROFILE EVER SEES IT.
#
# macOS sandbox-exec matches RESOLVED paths, and both directories anyone would naturally put a run
# root in are symlinks: /tmp -> /private/tmp, and $TMPDIR's /var -> /private/var. A profile granting
# write to the logical path therefore grants it to a path the kernel does not recognise, and EVERY
# write inside the sandbox is denied while the profile reads as though it permits them.
#
# Measured: with the logical path the readiness phase reported "copy not writable" -- a true
# observation with a completely misleading cause, since nothing was wrong with the copy. Resolving
# here rather than at each use means the profile, the environment and the cwd all agree; a single
# unresolved one reintroduces the whole failure.
resolve_root() { ( mkdir -p "$1" && cd "$1" && pwd -P ); }

provision_root() {
  local root="$1"
  mkdir -p "$root/home" "$root/tmp" "$root/docker" "$root/caches" "$root/copy" "$root/evidence"
  # A throwaway Docker config that exposes the runtime's plugin directory. The real
  # ~/.docker/config.json carries registry auth and must never enter the sandbox.
  if [ -n "${GATE_DOCKER_PLUGINS:-}" ]; then
    printf '{"cliPluginsExtraDirs":["%s"]}\n' "$GATE_DOCKER_PLUGINS" > "$root/docker/config.json"
  else
    printf '{}\n' > "$root/docker/config.json"
  fi
  write_profile "$root" "$root/profile.sb"
}

# ── Running inside it ───────────────────────────────────────────────────────────────────────────
# The environment is rebuilt from nothing. `env -i` so no credential, proxy, or cache path leaks in
# from the invoking shell, and every writable location is recreated under the run root -- which is
# also what makes plugin discovery work.
gate_env() { # gate_env <run-root> -> one VAR=value per line
  local root="$1" kind var path
  printf 'HOME=%s\n'                  "$root/home"
  printf 'TMPDIR=%s\n'                "$root/tmp"
  printf 'DOCKER_CONFIG=%s\n'         "$root/docker"
  printf 'DOCKER_HOST=unix://%s\n'    "$GATE_DOCKER_SOCKET"
  printf 'COMPOSE_PROJECT_NAME=%s\n'  "$COMPOSE_PROJECT"
  printf 'LANG=%s\n'                  "${GATE_LANG:-en_US.UTF-8}"
  if [ -n "${GATE_JAVA_HOME:-}" ]; then
    printf 'JAVA_HOME=%s\n' "$GATE_JAVA_HOME"
    # FORCE A PURE IPv4 STACK, and the reason is the profile rather than the JVM.
    #
    # A dual-stack JVM connects to loopback as ::ffff:127.0.0.1, and SBPL cannot express that: it
    # accepts only `*` or `localhost` as a host in a network address, so the mapped form matches no
    # filter. The Gradle client then cannot reach its own daemon and reports "Could not connect to
    # the Gradle daemon", which sends you to look at the daemon.
    #
    # The alternative was unfiltered outbound, which would have allowed real internet egress and
    # cost the one property the receipt depends on. This keeps it: verified with a control, egress
    # to a raw IP is still refused under this profile.
    #
    # ALLOW SELF-ATTACH, for the same class of reason. A JVM refuses to attach an agent to itself
    # unless asked to permit it, and reports "Can not attach to current VM" -- which is a different
    # message from the sandbox denial and arrives first, so fixing only the profile leaves the
    # failure looking untouched. Both halves are needed; neither alone is enough.
    printf 'JAVA_TOOL_OPTIONS=%s\n' "${GATE_JAVA_TOOL_OPTIONS:--Djava.net.preferIPv4Stack=true -Djdk.attach.allowAttachSelf=true}"
  fi
  # An offline step that retries a lookup it can never satisfy turns a fast failure into a stall;
  # these bound npm-family resolvers so a blocked fetch reports rather than hangs.
  printf 'npm_config_fetch_retries=0\n'
  printf 'npm_config_fetch_retry_maxtimeout=5000\n'
  for kind in ${GATE_CACHES[@]+"${GATE_CACHES[@]}"}; do
    var="GATE_CACHE_PATH_$kind"; path="${!var:-}"
    [ -n "$path" ] || continue
    gate_cache_env_vars "$kind" "$root/caches/$kind"
    # The raw directory, for toolchains whose cache location is NOT settable by environment. A
    # project's probe references it as $GATE_CACHE_DIR_<kind> and passes whatever flag that tool
    # requires, rather than every project hardcoding a path this skill already knows.
    printf 'GATE_CACHE_DIR_%s=%s\n' "$kind" "$root/caches/$kind"
  done
  printf 'PATH=%s\n' "$(gate_path)"
}

gate_path() {
  local p=""
  [ -n "${GATE_JAVA_HOME:-}" ] && p="$GATE_JAVA_HOME/bin:"
  [ -n "${GATE_DOCKER_PLUGINS:-}" ] && p="$p$GATE_DOCKER_PLUGINS:"
  printf '%s%s\n' "$p" "${GATE_EXTRA_PATH:+$GATE_EXTRA_PATH:}/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

# The script is written to a FILE under the run root and executed, NEVER interpolated into an
# `sh -c` string. Interpolating cost an hour the first time it was done: a probe containing its own
# quotes produced `syntax error near unexpected token ;`, and every check depending on it then
# reported a FAILURE OF THE THING BEING PROBED rather than of the probe -- "source is writable",
# "daemon unreachable". That is the most expensive shape a test can fail in, because it accuses the
# subject instead of itself.
sandboxed() { # sandboxed <run-root> <cwd> <script> [timeout-seconds]
  local root="$1" cwd="$2" script="$3" secs="${4:-}"
  local f="$root/tmp/probe.$$.sh" env_args=() line rc
  printf '%s\n' "$script" > "$f"
  printf '%s\n' "cd '$cwd'" > "$root/tmp/runner.$$.sh"
  printf '%s\n' ". '$f'"   >> "$root/tmp/runner.$$.sh"
  while IFS= read -r line; do [ -n "$line" ] && env_args+=("$line"); done < <(gate_env "$root")

  if [ -n "$secs" ]; then
    bounded "$secs" env -i "${env_args[@]}" \
      sandbox-exec -f "$root/profile.sb" /bin/sh "$root/tmp/runner.$$.sh"
  else
    env -i "${env_args[@]}" \
      sandbox-exec -f "$root/profile.sb" /bin/sh "$root/tmp/runner.$$.sh"
  fi
  rc=$?
  rm -f "$f" "$root/tmp/runner.$$.sh"
  return $rc
}

# Every step that can hang gets a bound. The readiness phase is meant to be run repeatedly and
# cheaply; one unbounded dependency install turned a 40-second check into a 10-minute wall, and a
# check nobody waits for is a check nobody runs. A timeout is reported as its OWN outcome, never
# folded into "failed" -- "did not finish in 240s" and "is broken" are different facts.
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
bounded() { # bounded <seconds> <command...>
  local secs="$1"; shift
  if [ -n "$TIMEOUT_BIN" ]; then "$TIMEOUT_BIN" "$secs" "$@"; else "$@"; fi
}

# The name is the handle for observation and for cleanup. Fixed per referent+nonce so a run is
# findable while it is going and removable exactly when it is done.
compose_project_name() { printf '%s_%s_%s' "$GATE_PROJECT_PREFIX" "$(printf '%s' "${REFERENT}" | cut -c1-12)" "$1"; }
