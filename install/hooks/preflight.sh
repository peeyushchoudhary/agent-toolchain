#!/usr/bin/env bash
# preflight.sh: mechanical checks for the environment-failure class — machine facts that are
# identically true in every repository on day one and are otherwise re-learned one gate run at a
# time. Point it at a repository before trusting a gate to run cleanly there.
#
# Reports, never writes, never scaffolds, never fixes. It runs against arbitrary directories,
# including repositories that are not ours, so it must never create a file inside the target,
# never modify one, and never execute anything the target repository supplies. It reads a bounded
# set of the target's own check scripts as DATA only.
#   Precisely: nothing under the target directory is ever created, modified or removed, and no
#   redirection anywhere in this script has a destination derived from the target. Two things
#   outside the target do touch the filesystem and are named here rather than hidden — bash 3.2
#   implements here-documents by writing a temp file under $TMPDIR and unlinking it, and a JVM
#   started by `java -version` creates and removes /tmp/hsperfdata_<user>/<pid>.
#
# Relation to disclosure-check.sh: the never-writes contract is the same, and both are wired as
# SessionStart hooks in settings.json. The output contract is NOT the same. disclosure-check.sh
# emits a JSON payload; this script emits plain `PREFLIGHT:` lines on stdout — one per finding,
# plus `PREFLIGHT: NOTE:` coverage lines that are never findings and never affect the exit status.
# Both are safe at session start for the same reason: they report, they exit 0 whenever they ran,
# and settings.json wraps each in `2>/dev/null || true` so no exit code of theirs can fail a
# session.
#
# TWO INVOCATIONS, NEITHER OF WHICH SUBSTITUTES FOR THE OTHER:
#   1. SessionStart, against the directory the session opened in. Cheap enough to be unconditional
#      (worst measured run 0.111s against a ~2s budget) and it puts the machine facts in front of
#      an agent before it starts trusting them.
#   2. Standalone, against a named repository, IMMEDIATELY BEFORE A LONG GATE RUN — which is the
#      moment the environment-failure class actually bites and the moment no session-start hook
#      covers, because a session can be hours old and can have opened somewhere else entirely.
#
# Not a gate itself, and not slow: this script is fast. The thing that is slow is the gate you run
# after it, which can take ~60 minutes — past the tool-call cap for an agent turn. Launch THE GATE
# detached (setsid, or Popen(..., start_new_session=True)) and poll with `ps -p <pid>`; do not wait
# on it inline. See the SIGHUP check below for why nohup is the wrong tool for that.
#
# Usage: preflight.sh [path]
#   path   directory to check (default: current directory)
#
# Exit: 0  the checks ran — whether or not they found anything. Findings are the stdout payload,
#          not the exit status. A preflight that fails a session because it found something true
#          about the machine gets switched off within a day; it reports, the human decides.
#       2  the check itself could not run: bad usage, or a check that could not be completed
#          (a missing interpreter, an external invocation that did not return). Never used for
#          "found a problem".

# No pipelines anywhere in this script by design (see check 2), so there is nothing for pipefail
# to protect; `set -u` alone catches the failure mode that actually applies here.
set -u

if [ "$#" -gt 1 ]; then
  echo "preflight: usage: preflight.sh [path]" >&2
  exit 2
fi
target="${1:-$PWD}"

if [ ! -d "$target" ]; then
  echo "preflight: '$target' is not a directory" >&2
  exit 2
fi

unable=0
add() {
  printf 'PREFLIGHT: %s\n' "$1"
}
# Coverage, not a finding. A check whose only output channel is findings cannot tell a reader
# "I read twelve files and every tool resolved" apart from "I found nothing to read" — both are
# silence. A note says which one happened without ever asserting that anything is wrong, so it
# costs nothing against the cry-wolf property.
note() {
  printf 'PREFLIGHT: NOTE: %s\n' "$1"
}
# A check that could not be completed is not a clean result and not a finding. It is reported in
# the output text as well as in the exit status, so it is distinguishable either way.
cannot_run() {
  printf 'PREFLIGHT: CHECK COULD NOT RUN: %s\n' "$1"
  unable=$((unable + 1))
}

# ---------------------------------------------------------------------------
# 1. Tool resolution: does a tool the repository's own checks name resolve as a real binary under a
#    non-interactive bash subshell — the same way a script's `#!/usr/bin/env bash` shebang sees the
#    world? `command -v <tool>` typed into an interactive shell is NOT this check: it also finds
#    shell functions and aliases (Claude Code's `rg` is exactly that) and reports a success a script
#    will not get. This is the known recurring case that broke verify-agent-guidance.sh and
#    agent-context.sh: `#!/usr/bin/env bash` + `rg` -> "rg: command not found", even though `rg`
#    "works" for the human typing it.
#
#    The list is DERIVED FROM THE TARGET, never hardcoded: a tool this repository does not name is
#    not this repository's problem, and requiring an optional dependency for a clean run is exactly
#    the failure this script exists to prevent. Derivation is an intersection of (a) a candidate set
#    of tools that are commonly shadowed, keg-only, or simply absent, and (b) whether the target's
#    own hooks/scripts/Makefile actually name that tool. Nothing outside the intersection is
#    checked, and when the intersection is empty this check runs zero subprocesses and says nothing.
#
#    Judgement call, recorded deliberately: the alternative — extracting arbitrary command tokens
#    from the target's scripts — was rejected. A free-form extractor over a foreign repository
#    produces findings about words that are not commands, and a preflight that cries wolf is worth
#    less than one that misses a case. Widening the candidate set is a one-line change; unlearning
#    distrust of a noisy check is not.
candidates="rg fd jq yq gh shellcheck graphify bat ag shfmt tree timeout gtimeout"

scan_files=""
scan_count=0
for d in "" /scripts /hooks /.githooks /tools /bin /ci /install; do
  for f in "$target$d"/*.sh; do
    [ -f "$f" ] || continue
    # Skip ANY file whose basename is preflight.sh, in any repository — not only this one. The
    # test is deliberately by basename rather than by identity: this script names every candidate
    # tool in its own candidate list, so scanning a copy of it manufactures a finding per
    # candidate, and resolving identity across symlinks and bind mounts without a subprocess is
    # not worth it. The only cost of the over-approximation is a false negative on someone else's
    # unrelated preflight.sh, which is the direction this script errs in everywhere else too.
    [ "${f##*/}" = "preflight.sh" ] && continue
    [ "$scan_count" -ge 60 ] && break 2
    scan_files="$scan_files$f"$'\n'
    scan_count=$((scan_count + 1))
  done
done
# GNUmakefile / makefile / Makefile are three spellings of ONE file, and make itself uses the first
# it finds in that order. Stop at the first hit: on a case-insensitive filesystem (the macOS
# default) `Makefile` and `makefile` both stat successfully for the same inode, and scanning it
# twice would make the coverage note below claim two files were read when one was.
for f in "$target/GNUmakefile" "$target/makefile" "$target/Makefile"; do
  [ -f "$f" ] || continue
  scan_files="$scan_files$f"$'\n'
  scan_count=$((scan_count + 1))
  break
done
# The fleet's real guard scripts are git hooks: extensionless, so the *.sh sweep above cannot see
# them, and the directory is .git/hooks, not .githooks. They are named explicitly rather than
# globbed so the stock *.sample files stay out of the scan set.
for f in "$target/justfile" \
         "$target/.git/hooks/pre-commit" "$target/.git/hooks/pre-push" \
         "$target/.git/hooks/commit-msg"; do
  [ -f "$f" ] || continue
  [ "$scan_count" -ge 60 ] && break
  scan_files="$scan_files$f"$'\n'
  scan_count=$((scan_count + 1))
done

# Which candidates does the target actually name? Files are read as data into a variable and
# matched in-shell — no subprocess, no eval, nothing from the target is ever executed or expanded.
wanted=""
wanted_src=""
wanted_count=0
read_count=0
# Counts candidate files that were found but could not be read. Kept SEPARATE from read_count
# because the coverage note below must distinguish "nothing to read" from "found things and could
# not read them" — read_count alone is 0 in both cases, and a note that names one of those two
# causes while the other one happened asserts something the script never observed.
skipped=0
content=""
f=""
# Match the accumulated buffer against every candidate not already found. Called once per chunk of
# input rather than once per file — see the chunking note below. Reads and writes the globals
# `content`, `wanted`, `wanted_src`, `wanted_count` and `f`; it must NOT be run in a subshell or
# the results would be discarded.
scan_chunk() {
  [ -n "$content" ] || return 0
  for c in $candidates; do
    case " $wanted " in
      *" $c "*) continue ;;
    esac
    # Word boundary without a subprocess. The RHS must stay an unquoted variable: bash 3.2
    # treats a quoted =~ operand as a literal string, not a pattern.
    #
    # The two exclusions beyond the obvious identifier characters are load-bearing, because
    # several candidates are also ordinary shell variable names (`timeout`, `fd`, `tree`, `ag`):
    #   - `=` is excluded from the TRAILING class, so an assignment `timeout=300` is not a use.
    #     Without this, any repository containing `timeout=300` in a scanned script yields a
    #     permanent false finding, since stock macOS ships no timeout(1) for the search to find.
    #   - `$` `{` `"` are excluded from the LEADING class, so `$timeout`, `${timeout}` and
    #     `exec {fd}>` are not uses either.
    # Deliberately NOT solved by dropping the identifier-like candidates: `timeout` genuinely is
    # a tool this fleet's scripts reach for and genuinely is absent, so it belongs in the list.
    # Near-misses that already failed to match and still do: `--timeout=5` (leading `-`),
    # `gtimeout` (leading alnum), `timeout_secs` (trailing `_`), `TIMEOUT=` (case).
    re="(^|[^[:alnum:]_./\${\"-])${c}([^[:alnum:]_=-]|$)"
    if [[ $content =~ $re ]]; then
      wanted="$wanted $c"
      wanted_src="$wanted_src$c $f"$'\n'
      wanted_count=$((wanted_count + 1))
    fi
  done
}
if [ -n "$scan_files" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    # An unreadable file, or a filename containing a newline (which splits scan_files above), makes
    # the redirect below fail: bash writes to stderr, content stays empty, and the file is skipped
    # with nothing on stdout. Silently examining fewer files than claimed is the same defect class
    # as claiming a tool is missing when the probe never ran, so it is reported, not swallowed.
    [ -r "$f" ] || { skipped=$((skipped + 1)); cannot_run "could not read $f, so it was not scanned for tool names. Nothing is being claimed about the tools it may name. Fix: make it readable, or exclude it from the check scripts this preflight scans."; continue; }
    read_count=$((read_count + 1))
    # Comments are stripped before matching. A tool discussed in prose ("check the working tree")
    # is not a tool the repository's checks invoke, and treating it as one produces findings about
    # words. Stripping from the first `#` can also drop a real invocation inside a quoted string;
    # that bias is deliberate — a missed check is cheaper than a false one.
    #
    # CHUNKED, and that is a performance requirement, not a style choice. `content="$content..."`
    # re-copies the whole accumulated string once per line, so scanning a file in one buffer is
    # quadratic in its length. Measured on this machine, accumulating a single file: 1000 lines
    # 0.28s, 2000 lines 1.07s, 4000 lines 4.29s, 8000 lines 17.8s — and the 60-file cap bounds
    # file COUNT, not size, so sixty thousand-line scripts would cost ~17s against the card's ~2s
    # budget. Flushing every 200 lines makes the total linear and keeps each copy small.
    # Chunking is lossless here because the flush happens only at a line boundary and no tool name
    # spans a newline; the already-found test in scan_chunk keeps repeats across chunks cheap.
    content=""
    chunk=0
    while IFS= read -r line || [ -n "$line" ]; do
      while [ -n "$line" ]; do
        case "$line" in
          [[:blank:]]*) line="${line#?}" ;;
          *) break ;;
        esac
      done
      case "$line" in
        '#'*|'') continue ;;
      esac
      content="$content${line%%#*}"$'\n'
      chunk=$((chunk + 1))
      if [ "$chunk" -ge 200 ]; then
        scan_chunk
        content=""
        chunk=0
      fi
    done <"$f"
    scan_chunk
    content=""
  done <<EOF
$scan_files
EOF
fi

# Coverage. Zero files must never look like zero problems: the derivation is silent by design when
# it finds nothing to check, and without this line that silence is indistinguishable from a clean
# result. It is a NOTE, never a finding, and never touches the exit status.
#
# THE NOTE MAY ONLY STATE WHAT WAS OBSERVED. read_count is 0 in two distinct situations — no
# candidate file existed at all, and candidates existed but every one failed `[ -r ]` above — so
# "this target has no check scripts" is only true of the first, and $skipped is what tells them
# apart. Printing that sentence above a CHECK COULD NOT RUN line that names a file this script just
# failed to read is a direct self-contradiction, and it is the same defect as a finding that names
# a cause the probe never established. When anything was skipped the note reports the counts and
# nothing else: how many were read, how many could not be, and that the detail is in the lines
# above. It never guesses why, and it never claims coverage it does not have.
if [ "$read_count" -eq 0 ] && [ "$skipped" -eq 0 ]; then
  note "tool check read 0 file(s) — this target has no check scripts where this script looks (Makefile/justfile, .git/hooks/{pre-commit,pre-push,commit-msg}, and *.sh at the root or in scripts/ hooks/ .githooks/ tools/ bin/ ci/ install/), so NOTHING was checked about tool resolution here. This is coverage, not a finding."
elif [ "$read_count" -eq 0 ]; then
  note "tool check read 0 file(s); $skipped file(s) could not be read (reported above), so NOTHING was checked about tool resolution here. This is coverage, not a finding."
elif [ "$skipped" -eq 0 ]; then
  note "tool check read $read_count file(s) and derived $wanted_count tool name(s):${wanted:- (none)}"
else
  note "tool check read $read_count file(s) and derived $wanted_count tool name(s):${wanted:- (none)} — PARTIAL COVERAGE: a further $skipped file(s) could not be read (reported above) and nothing is claimed about the tools they may name."
fi

# Where a real binary would live if it were installed but simply not on a script's PATH. PATH
# itself is included so the search is honest about what it actually looked at.
#
# NEWLINE-separated, not space-separated, and $HOME is defaulted rather than read bare. Two
# reasons, both about surviving odd invocation contexts (launchd, cron, a minimal container):
#   - Under `set -u` a bare $HOME with HOME unset aborts the whole script with status 1 — the one
#     status the exit contract above reserves for nothing at all — before any check runs and
#     without printing a single PREFLIGHT: line.
#   - A $HOME containing a space would split into two bogus prefixes if this list were split on
#     spaces. Splitting on newlines only makes the entry survive intact.
prefixes="/opt/homebrew/bin
/opt/homebrew/sbin
/usr/local/bin
/usr/local/sbin
/usr/bin
/bin
/usr/sbin
/sbin
${HOME:-/nonexistent}/.local/bin
${HOME:-/nonexistent}/bin
${HOME:-/nonexistent}/.cargo/bin"
prefixes_display=${prefixes//$'\n'/ }

for tool in $wanted; do
  # The tool name is passed as an ARGUMENT into a fixed, single-quoted inner program. It is never
  # concatenated into shell program text: this name came out of a foreign repository's files, and
  # building `bash -c "command -v $tool"` from it would execute whatever that repository wrote.
  # `--` matters: a candidate beginning with a dash would otherwise be parsed as an option to
  # `command`, which exits 2, which this script reads as "the probe did not run" — turning every
  # run into CHECK COULD NOT RUN and exit 2. With `--` it is a plain not-found (1) instead.
  bash -c 'command -v -- "$1"' _ "$tool" >/dev/null 2>&1
  cv=$?
  [ "$cv" -eq 0 ] && continue
  if [ "$cv" -ne 1 ]; then
    # 0 = resolves, 1 = does not resolve. Anything else means the probe itself did not run —
    # no bash on PATH, or the interpreter died. That is not evidence the tool is missing.
    cannot_run "could not probe whether '$tool' resolves: \`bash -c 'command -v ...'\` exited $cv, which is neither 'found' (0) nor 'not found' (1). Nothing is being claimed about '$tool'. Fix: check that \`bash\` is on PATH and executable for a non-interactive subshell."
    continue
  fi

  # Report only what was observed. The script is a separate process and cannot see the invoking
  # shell's functions or aliases, so "it is a shell function" is never something it can assert.
  # What it can do is look for a real binary, and the two cases have different fixes.
  found=""
  saved_ifs="$IFS"
  IFS=":"
  for d in $PATH; do
    [ -n "$d" ] || continue
    if [ -x "$d/$tool" ] && [ ! -d "$d/$tool" ]; then found="$d/$tool"; break; fi
  done
  IFS="$saved_ifs"
  if [ -z "$found" ]; then
    saved_ifs="$IFS"
    IFS=$'\n'
    for d in $prefixes; do
      if [ -x "$d/$tool" ] && [ ! -d "$d/$tool" ]; then found="$d/$tool"; break; fi
    done
    IFS="$saved_ifs"
  fi

  src=""
  while IFS= read -r line; do
    case "$line" in
      "$tool "*) src="${line#"$tool" }"; break ;;
    esac
  done <<EOF
$wanted_src
EOF
  named="named by this repository's own checks"
  [ -n "$src" ] && named="named by this repository's own checks ($src)"

  if [ -n "$found" ]; then
    # Only ONE cause can produce this observation: the binary is real and installed, so the
    # directory holding it is simply absent from the PATH a script inherits. A shell function or
    # alias cannot produce it — this script is a separate process and a parent shell's functions
    # are invisible to it, so a shadowed tool with no binary lands in the other branch below.
    add "'$tool' is $named, and a real binary exists at $found, but it does not resolve under \`bash -c 'command -v $tool'\` — so a script with \`#!/usr/bin/env bash\` will fail with '$tool: command not found' even though typing \`$tool\` yourself appears to work. Observed: binary present, not resolvable for a script. The cause is an install prefix that is on your interactive shell's PATH but not on the PATH a script inherits. Fix: invoke $found by its full path, or put its directory on PATH for the script."
  else
    install_hint="brew install $tool"
    case "$tool" in
      rg) install_hint="brew install ripgrep" ;;
      ag) install_hint="brew install the_silver_searcher" ;;
      graphify) install_hint="install graphify (it is an optional dependency; a check that needs it should skip instead)" ;;
      timeout|gtimeout) install_hint="brew install coreutils (stock macOS ships no timeout(1)); or bound the call in-shell instead" ;;
    esac
    # This is where a shell function or alias lands: `command -v` typed interactively finds the
    # function and reports success, while no binary exists for a script to find. That is exactly
    # how Claude Code exposes `rg`, and it is the recurring case this check was written for.
    add "'$tool' is $named, and no binary named '$tool' exists anywhere this script looked — not on PATH, and not in the usual install prefixes ($prefixes_display). Observed: not installed, as distinct from installed-but-shadowed. If typing \`$tool\` yourself appears to work, what you are running is a shell function or alias in your interactive shell, not a binary — this is exactly how Claude Code exposes \`rg\` — and a script with \`#!/usr/bin/env bash\` will still fail with '$tool: command not found'. Fix: $install_hint — or, if it is an optional dependency, make the check that names it skip when it is absent rather than fail."
  fi
done

# ---------------------------------------------------------------------------
# 2. JAVA_HOME, but only when this repository actually has a Gradle build — a repo with no Gradle
#    build must not fail a JAVA_HOME check just because JAVA_HOME happens to be unset. openjdk@21
#    installed via Homebrew is keg-only, so it is never linked onto PATH or JAVA_HOME automatically.
#
#    `java -version` is the one call in this script that can block (a JDK on a stalled network
#    mount). stock macOS ships no timeout(1) and no gtimeout, so it is bounded in-shell: run it in
#    the background, poll for it with the `kill -0` builtin, and give up. No file is written and no
#    external bounding tool is required.
java_out=""
java_run() {
  # Sets java_stat: the JDK's own exit status, or 254 for "did not finish in time".
  # Sets java_out only when the status is non-zero, i.e. only when it is about to be quoted.
  java_out=""
  "$1" -version >/dev/null 2>&1 &
  jpid=$!
  i=0
  while [ "$i" -lt 15 ]; do
    kill -0 "$jpid" 2>/dev/null || break
    sleep 0.1
    i=$((i + 1))
  done
  if kill -0 "$jpid" 2>/dev/null; then
    # Drop it from the job table BEFORE terminating it, or bash reports `Terminated: 15` on stderr
    # for a job it still tracks and never sees waited. This is plain `disown`, whose only effect is
    # the job table — NOT `disown -h`, which is about SIGHUP and is not what is wanted here.
    disown "$jpid" 2>/dev/null || true
    kill -TERM "$jpid" 2>/dev/null
    # Deliberately NOT `wait "$jpid"` here, and that is the whole point of the bound. The scenario
    # this bound exists for is a JDK on a stalled network mount: a process in uninterruptible disk
    # wait does not receive SIGTERM until the syscall returns, so `wait` would block in waitpid()
    # indefinitely and re-introduce the unbounded hang immediately after bounding it. SIGKILL
    # would not help either — D state ignores that too.
    # The trade, accepted explicitly: this leaves a child running, which init reaps when this
    # script exits and which dies of its own accord when the mount recovers. A lingering process
    # that cleans itself up is strictly better than a preflight that never returns, and sending
    # TERM above already accepted abandoning it.
    java_stat=254
    return
  fi
  wait "$jpid" 2>/dev/null
  java_stat=$?
  if [ "$java_stat" -ne 0 ]; then
    # Safe to capture now: the bounded run just proved this binary terminates promptly.
    java_out=$("$1" -version 2>&1)
    java_out=${java_out//$'\n'/ }
  fi
}

if [ -f "$target/build.gradle" ] || [ -f "$target/build.gradle.kts" ] || [ -f "$target/gradlew" ]; then
  if [ -z "${JAVA_HOME:-}" ]; then
    # Do not report on JAVA_HOME being unset alone. Gradle falls back to the `java` on PATH, and
    # if that is a working JDK the build runs — reporting here would be a false alarm.
    jbin=$(bash -c 'command -v -- java' 2>/dev/null)
    cv=$?
    if [ "$cv" -ne 0 ] && [ "$cv" -ne 1 ]; then
      # Same discipline as the tool probe above: 0 = resolves, 1 = does not resolve, anything else
      # (127 for no bash on PATH, or a died interpreter) means the probe itself never ran. Calling
      # that "no java resolves" would assert something this script has no evidence for.
      cannot_run "could not probe whether \`java\` resolves for $target's Gradle build: \`bash -c 'command -v -- java'\` exited $cv, which is neither 'found' (0) nor 'not found' (1). Nothing is being claimed about JAVA_HOME or about \`java\`. Fix: check that \`bash\` is on PATH and executable for a non-interactive subshell."
    elif [ "$cv" -ne 0 ] || [ -z "$jbin" ]; then
      add "JAVA_HOME is unset and no \`java\` resolves on PATH for a script, and $target has a Gradle build, so Gradle has no JDK to fall back to. openjdk@21 installed via Homebrew is keg-only: it is never linked onto PATH or JAVA_HOME automatically. Fix: export JAVA_HOME=\"\$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home\" (adjust the formula to whatever JDK this build needs) before running the gate."
    else
      java_run "$jbin"
      if [ "$java_stat" -eq 254 ]; then
        cannot_run "\`$jbin -version\` did not return within 1.5s, so whether a usable JDK resolves for $target's Gradle build is unknown. Nothing is being claimed about JAVA_HOME. Fix: check whether that path is on a stalled network mount."
      elif [ "$java_stat" -ne 0 ]; then
        add "JAVA_HOME is unset, $target has a Gradle build, and the \`java\` Gradle would fall back to ($jbin) does not run: it exited $java_stat saying '$java_out'. On macOS /usr/bin/java can be a stub shim that reports no runtime rather than a JDK. Fix: export JAVA_HOME=\"\$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home\" (adjust the formula to whatever JDK this build needs) before running the gate."
      fi
    fi
  elif [ ! -x "$JAVA_HOME/bin/java" ]; then
    add "JAVA_HOME=$JAVA_HOME has no executable bin/java — it does not point at a real JDK. Fix: point JAVA_HOME at a keg-only Homebrew JDK, e.g. \$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home."
  else
    # UNPROVEN, NEAR-UNREACHABLE AS WRITTEN, AND KNOWN INCOMPLETE. Reaching this branch needs all
    # of: a Gradle build, JAVA_HOME set, $JAVA_HOME/bin/java executable, and that binary broken.
    # The macOS stub is /usr/bin/java, so the stub case needs JAVA_HOME=/usr — and nothing that
    # sets JAVA_HOME produces /usr (not /usr/libexec/java_home, not Homebrew, not SDKMAN, not an
    # IDE). It has never been observed red, and no synthetic stub was built to make it green,
    # because that would prove something about a fixture rather than about any real configuration.
    # Known incomplete: the branch inspects $JAVA_HOME/bin/java only. The check that would matter
    # is the java Gradle would ACTUALLY resolve, which is a follow-up card, not this one.
    # The predicate is the EXIT STATUS (a stub exits non-zero, a real JVM exits 0); the string
    # match below only chooses wording, and is never the sole evidence — it recognises one of at
    # least three stub messages ("Unable to locate a Java Runtime", "No Java runtime present,
    # requesting install.", "Unable to find any JVMs matching version...").
    java_run "$JAVA_HOME/bin/java"
    if [ "$java_stat" -eq 254 ]; then
      cannot_run "\`\$JAVA_HOME/bin/java -version\` did not return within 1.5s for JAVA_HOME=$JAVA_HOME, so whether it is a real JDK is unknown. Nothing is being claimed about it. Fix: check whether that path is on a stalled network mount."
    elif [ "$java_stat" -ne 0 ]; then
      case "$java_out" in
        *[Uu]nable\ to\ locate*|*[Nn]o\ Java\ runtime\ present*|*[Uu]nable\ to\ find\ any\ JVMs*)
          add "JAVA_HOME=$JAVA_HOME resolves to a macOS Java stub, not a JDK: \`java -version\` exited $java_stat saying '$java_out'. Fix: point JAVA_HOME at a keg-only Homebrew JDK, e.g. \$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home." ;;
        *)
          add "JAVA_HOME=$JAVA_HOME has an executable bin/java that does not work: \`java -version\` exited $java_stat saying '$java_out'. Fix: point JAVA_HOME at a working JDK, e.g. \$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home." ;;
      esac
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 3. SIGHUP inherited-ignored: if some ancestor of this shell ran under `nohup`, SIGHUP was set to
#    SIG_IGN, and an ignored disposition is inherited across both fork AND exec — every descendant
#    process is permanently deaf to SIGHUP for its whole lifetime. This bit a release gate three
#    times, misdiagnosed twice (a flake, then load sensitivity) before the actual cause surfaced,
#    in a signal-coalescing stage.
#
# What is DOCUMENTED: POSIX and bash both specify that a signal ignored at shell entry cannot be
# trapped — the trap request is accepted syntactically and the disposition stays SIG_IGN.
# What is an IMPLEMENTATION CONSEQUENCE, not documented: that `trap -p HUP` then prints nothing.
# The check relies on the consequence, so it is written to be obviously fragile rather than subtly
# fragile.
#
# LOAD-BEARING DEPENDENCY — do not refactor this line: `$(trap -p HUP)` reports the PARENT shell's
# trap state only because POSIX specially requires a subshell to do so. Hoisting it into a plain
# variable assignment, or moving it into a function that runs in a subshell of its own, would
# report the subshell's state and degrade this check to silently always-green.
trap 'true' HUP
if [ -z "$(trap -p HUP)" ]; then
  add "SIGHUP is ignored in this process, inherited from an ancestor — an ignored disposition survives both fork and exec, so every descendant (including a long gate launched from here) is permanently deaf to SIGHUP, and bash cannot install a trap on it. Observed: the disposition, not its cause. The usual cause is \`nohup\`, but launchd, a supervisor, or any harness that daemonises does the same thing. (\`disown\` does NOT: it only stops bash sending SIGHUP itself, it never sets SIG_IGN in the child.) This environment is not fit for a long-running gate. Fix: if you are detaching the gate yourself, do not use \`nohup\` — use \`setsid\` (or Python's subprocess.Popen(..., start_new_session=True)), then poll with \`ps -p <pid>\`; a full gate can run ~60 minutes, longer than a single agent turn should block on."
fi

# ---------------------------------------------------------------------------
# Findings are the stdout payload; the exit status says only whether the checks ran.
if [ "$unable" -gt 0 ]; then
  exit 2
fi
exit 0
