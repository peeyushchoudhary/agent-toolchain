# Configuration resolution for the sandboxed gate. Sourced, never executed.
#
# THIS FILE IS THE REASON THE REST OF THE SKILL CAN BE PUBLIC.
#
# Everything that identifies a project or a machine -- checkout path, branch, referent, gate argv,
# port list, image tags, cache locations -- arrives through here from files that live OUTSIDE this
# repository. Nothing below hardcodes a project fact, and a review of this skill that finds one has
# found a defect, not a convenience.
#
# Three layers, resolved in this order, each overriding the last:
#
#   1. DERIVED       whatever this machine can work out for itself (docker socket, JDK, TMPDIR).
#   2. HOST FILE     $GATE_HOME/host.env -- per machine, not per project.
#   3. PROJECT FILE  the project's own gate.env -- per project, not per machine.
#
# The split matters when a project moves between machines: layer 3 travels with it, layer 2 does
# not. Collapsing them into one file is what makes a config that cannot be moved.

# ── Where the private configuration lives ───────────────────────────────────────────────────────
# Not inside this skill. The skill is installed and REPLACED WHOLESALE on every install (see
# install_tree in install.sh, which stages a fresh copy and swaps it in). Anything written into the
# installed skill directory is destroyed by the next install; that is not a hypothetical, it is the
# bug that deleted a whole test suite before PRESERVE_ACROSS_INSTALLS existed. Configuration
# therefore lives beside the skill, never in it.
GATE_HOME="${GATE_HOME:-$HOME/.claude/gate}"

gate_config_die() { printf '\nSTOP  %s\n' "$*" >&2; exit 2; }

# ── Layer 1: derivation ─────────────────────────────────────────────────────────────────────────
# Values a machine can determine about itself. Each is a DEFAULT: the host file may override any of
# them, and does so whenever the machine is not the common case.
gate_derive_host() {
  : "${GATE_DOCKER_SOCKET:=$HOME/.orbstack/run/docker.sock}"

  # The Docker CLI finds its plugins under $HOME/.docker/cli-plugins. A fresh HOME -- which this
  # sandbox insists on, so no credential or proxy setting leaks in -- therefore hides compose and
  # buildx completely. That is not a Docker fault and not a sandbox fault; it is the interaction,
  # and it is the single diagnosis that cost the most to reach. The runtime's own plugin directory
  # is exposed instead, through a throwaway config, because the real ~/.docker/config.json carries
  # registry auth and must never enter the sandbox.
  if [ -z "${GATE_DOCKER_PLUGINS:-}" ]; then
    for d in /Applications/OrbStack.app/Contents/MacOS/xbin \
             /Applications/Docker.app/Contents/Resources/cli-plugins \
             /opt/homebrew/lib/docker/cli-plugins \
             /usr/local/lib/docker/cli-plugins; do
      [ -d "$d" ] && { GATE_DOCKER_PLUGINS="$d"; break; }
    done
  fi

  # `env -i` strips JAVA_HOME. A login shell that never set one still builds fine, because the
  # wrapper finds a JDK on PATH -- so the variable's absence is invisible until the sandbox removes
  # PATH too, and then Gradle reports "Unable to locate a Java Runtime", which reads like a broken
  # sandbox and is really a missing variable. Projects that need a specific JDK pin GATE_JAVA_HOME
  # in their own config; a gate that silently picks up a different JDK is not the same gate.
  if [ -z "${GATE_JAVA_HOME:-}" ] && [ -x /usr/libexec/java_home ]; then
    GATE_JAVA_HOME="$(/usr/libexec/java_home 2>/dev/null || true)"
  fi

  : "${GATE_RUN_ROOT:=${TMPDIR:-/tmp}/gate-sandbox}"

  # Host cache locations, per toolchain. Overridable individually; a project names only the KINDS it
  # wants imported, never the paths.
  : "${GATE_CACHE_PATH_gradle:=$HOME/.gradle}"
  : "${GATE_CACHE_PATH_pnpm:=$HOME/Library/pnpm/store}"
  : "${GATE_CACHE_PATH_uv:=$HOME/.cache/uv}"
  : "${GATE_CACHE_PATH_playwright:=$HOME/Library/Caches/ms-playwright}"
  : "${GATE_CACHE_PATH_npm:=$HOME/.npm}"
  : "${GATE_CACHE_PATH_cargo:=$HOME/.cargo}"
  : "${GATE_CACHE_PATH_go:=$HOME/go/pkg/mod}"
  : "${GATE_CACHE_PATH_maven:=$HOME/.m2}"
}

# The environment variable each cache kind is exposed through INSIDE the sandbox. Generic knowledge
# about toolchains, not about any project, which is why it belongs in the published skill. A kind
# with no mapping is still cloned and still reachable on disk -- it simply gets no variable, which
# is the honest outcome rather than a silent omission.
gate_cache_env_vars() { # gate_cache_env_vars <kind> <path>
  case "$1" in
    gradle)     printf 'GRADLE_USER_HOME=%s\n' "$2" ;;
    pnpm)       printf 'PNPM_HOME=%s\nPNPM_STORE_PATH=%s/store\n' "$2" "$2" ;;
    uv)         printf 'UV_CACHE_DIR=%s\n' "$2" ;;
    playwright) printf 'PLAYWRIGHT_BROWSERS_PATH=%s\n' "$2" ;;
    npm)        printf 'npm_config_cache=%s\n' "$2" ;;
    cargo)      printf 'CARGO_HOME=%s\n' "$2" ;;
    go)         printf 'GOMODCACHE=%s\n' "$2" ;;
    maven)      printf 'MAVEN_OPTS=-Dmaven.repo.local=%s/repository\n' "$2" ;;
  esac
}

# ── Layers 2 and 3: the files ───────────────────────────────────────────────────────────────────
# Resolution order for the PROJECT file, most explicit first:
#   --config <path>            an argument, for a one-off
#   $GATE_CONFIG               an environment variable, for a wrapper
#   $GATE_HOME/projects/<basename-of-checkout>.env
#
# The last one is what makes `readiness` runnable from inside a project with no arguments at all,
# and a launcher that needs arguments to be correct is one that gets run incorrectly.
gate_project_config_path() { # gate_project_config_path [explicit-path]
  if [ -n "${1:-}" ]; then printf '%s\n' "$1"; return 0; fi
  if [ -n "${GATE_CONFIG:-}" ]; then printf '%s\n' "$GATE_CONFIG"; return 0; fi
  local top; top="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$top" ] || return 1
  printf '%s/projects/%s.env\n' "$GATE_HOME" "$(basename "$top")"
}

gate_load_config() { # gate_load_config [explicit-project-config-path]
  # Host file first, so a project file can override a machine default rather than the reverse.
  if [ -f "$GATE_HOME/host.env" ]; then
    # shellcheck source=/dev/null
    . "$GATE_HOME/host.env"
  fi

  GATE_CONFIG_PATH="$(gate_project_config_path "${1:-}" || true)"
  [ -n "$GATE_CONFIG_PATH" ] || gate_config_die \
    "no project configuration: not inside a git repository, and neither --config nor \$GATE_CONFIG was given"
  [ -f "$GATE_CONFIG_PATH" ] || gate_config_die \
    "no project configuration at $GATE_CONFIG_PATH
       This skill ships machinery, never project facts. Write that file -- see the SKILL.md
       schema -- or pass --config <path>. Nothing here will guess a repository, a branch, or a
       gate command on your behalf."
  # shellcheck source=/dev/null
  . "$GATE_CONFIG_PATH"

  # Derivation runs AFTER both files so that `:=` fills only what neither file set.
  gate_derive_host
  gate_validate_config
}

# Every required field named in one place, with the reason it is required. A launcher that starts
# and fails halfway through provisioning has already cost minutes; these are all cheap.
gate_validate_config() {
  [ -n "${GATE_REPO:-}" ]  || gate_config_die "GATE_REPO is unset -- there is no checkout to gate"
  [ -d "$GATE_REPO/.git" ] || gate_config_die "no git repository at $GATE_REPO"
  [ -n "${GATE_ARGV:-}" ]  || gate_config_die "GATE_ARGV is unset -- the exact gate command is not optional, and this skill will not invent one"
  [ -n "${GATE_DOCKER_SOCKET:-}" ] || gate_config_die "GATE_DOCKER_SOCKET is unset and could not be derived"

  : "${GATE_BRANCH:=}"
  : "${GATE_REFERENT:=}"
  : "${GATE_PORTS:=}"
  : "${GATE_IMAGES:=}"
  : "${GATE_LOCKFILES:=}"
  : "${GATE_PROJECT_PREFIX:=gate}"
  # Evidence outlives the run root by construction: it is written OUTSIDE the tree that cleanup
  # removes. Persisting it inside the run root and copying it out afterwards is the arrangement in
  # which a failed cleanup and a lost receipt are the same incident.
  : "${GATE_EVIDENCE_ROOT:=$GATE_HOME/evidence/$(basename "$GATE_REPO")}"
  [ -n "${GATE_CACHES+x}" ] || GATE_CACHES=()
  [ -n "${GATE_OFFLINE_STEPS+x}" ] || GATE_OFFLINE_STEPS=()

  # The compose project name is the handle for observation and for cleanup, so it has to be a legal
  # one. Compose lowercases and strips; deriving a name that compose then rewrites means cleanup
  # looks for a project that never existed under that name.
  case "$GATE_PROJECT_PREFIX" in
    *[!a-z0-9_-]*) gate_config_die "GATE_PROJECT_PREFIX must be lowercase alphanumeric, '_' or '-' (compose rewrites anything else, and cleanup would then miss the project it created)" ;;
  esac
}
