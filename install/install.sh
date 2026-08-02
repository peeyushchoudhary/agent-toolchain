#!/usr/bin/env bash
# Install the agent toolchain into ~/.claude and ~/.codex.
#
# Idempotent: re-running updates the skills and hooks in place and leaves everything else alone.
# It never overwrites your settings.json wholesale — hook entries are merged, and a timestamped
# backup is taken first.
#
#   ./install.sh              install or update
#   ./install.sh --dry-run    print what would happen, change nothing
#   ./install.sh --no-codex   skip the Codex side
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="$HOME/.claude"
CODEX="$HOME/.codex"
DRY=0
DO_CODEX=1

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --no-codex) DO_CODEX=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '  %s\n' "$1"; }
run()  { if [ "$DRY" -eq 1 ]; then printf '  would: %s\n' "$*"; else "$@"; fi; }

# This script deliberately does NOT use `set -e`: several steps are probes that are expected to
# return non-zero. Instead, every step that must succeed records its failure here, and the script
# exits non-zero at the end with a summary. Without this, a step could fail loudly in the middle,
# print its success line anyway, and still exit 0 — so `./install.sh && ./verify.sh` would report
# success for an install that wired nothing.
FAILURES=""
fail() { FAILURES="${FAILURES}${1}
"; printf '  FAILED: %s\n' "$1"; }

# `find ... -exec chmod +x {} \;` reports find's OWN errors but NOT a non-zero exit from chmod, so a
# per-file chmod failure would pass unnoticed. Check find's status and each chmod separately.
# (Filenames containing newlines are not handled; the vendored tree has none.)
chmod_scripts() {
  local root="$1" list f rc=0
  list="$(find "$root" -name '*.py' -print)" || return 1
  [ -n "$list" ] || return 0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    chmod +x "$f" || rc=1
  done <<< "$list"
  return "$rc"
}

# Copy a skill tree into place without a window in which the old copy is deleted and the new one has
# not landed. `rm -rf dest && cp -R src dest` reports a failed copy correctly, but by then the skill
# that was working is gone — for progressive-disclosure that silently disarms the pre-push guard in
# every repository. Stage beside the target, then swap: a failed copy leaves the old copy untouched.
#
# The old copy is moved aside by rename, never deleted in place. `rm -rf dest` on a tree holding one
# undeletable file (an immutable flag, a root-owned file) deletes everything it CAN and then fails —
# leaving a gutted destination and no swap. A rename does not recurse, so it does not care what is
# inside; the old copy only gets removed once the new one is already in place, and a failure there
# leaves a working install. There is therefore no point at which both copies are gone.
install_tree() {
  local src="$1" dest="$2" staged="$2.staging.$$" aside="$2.replacing.$$"
  rm -rf "$staged" "$aside" || return 1
  if cp -R "$src" "$staged" && chmod_scripts "$staged"; then
    if [ ! -e "$dest" ] || mv "$dest" "$aside"; then
      if mv "$staged" "$dest"; then
        [ ! -e "$aside" ] || rm -rf "$aside" ||
          say "note: the previous copy could not be removed — delete $aside by hand"
        return 0
      fi
      [ ! -e "$aside" ] || mv "$aside" "$dest"   # put the old copy back; the swap never happened
    fi
  fi
  rm -rf "$staged"
  return 1
}

# ── Preconditions ────────────────────────────────────────────────────────────────────────────────
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "python3 $PYV found; 3.10 or newer is required (the tools use PEP 604 type syntax)" >&2
  exit 1; }
command -v git >/dev/null || echo "  note: git not found — the per-repo hooks will be unusable"

echo "agent toolchain installer"
say "python3 $PYV"
say "target: $CLAUDE$([ "$DO_CODEX" -eq 1 ] && echo " and $CODEX")"
[ "$DRY" -eq 1 ] && say "DRY RUN — nothing will be written"

# ── Skills ───────────────────────────────────────────────────────────────────────────────────────
# The skill set is DISCOVERED from install/skills/.gitignore rather than named a second time here.
# That file is this repository's own declaration of what install/skills/ publishes (see
# docs/README.md, "What is published, and what is not") — an allowlist that ignores everything in
# the directory and then re-includes each published skill by a `!/name` line. A hardcoded SKILLS
# string here was a second copy of that same fact, and it went stale: it named five of the six
# skills and nothing caught the sixth (`execution-methodology`) going unpublished by this installer
# while verify.sh's own vendored-suite runner was already executing its tests.
#
# THIS IS NOT THE ONLY PLACE THE SIX ARE WRITTEN DOWN, and an earlier version of this comment
# claimed it was. `docs/README.md` names all six in prose — the very document this comment sends the
# reader to. What is true is narrower and is the thing that matters: neither SCRIPT carries a list,
# so a re-vendor cannot drift install.sh and verify.sh apart by hand-editing one of them, and
# verify.sh executes this installer's dry run and compares the two sets rather than trusting that
# both copies of the reader below agree. The doc remains a second copy, checked by a human.
#
# THE READER IS STRICT AND LOUD, DELIBERATELY. gitignore negation syntax is larger than the `!/name`
# form this allowlist uses: `!name` without the slash is legal and a permissive `grep -E '^!/'`
# misses it entirely — dropping a published skill from the install set silently, which is precisely
# the defect this block was written to fix. `!/name/` with a trailing slash is legal too and yields
# an entry that installs and then fails every equality check downstream. So one `if` decides what
# the strict form is, the SAME `if` emits everything it rejects, and a rejected line is a FAILURE
# rather than an absence. This mirrors `skill_roster_scan` in verify.sh, whose header records the
# measurement behind not using `git check-ignore` for this: it consults the index and will not call
# a tracked path ignored, so it cannot see a tracked skill lose its `!/` line.
#
# graph-navigation is declared like every other skill and installed the same way; it is included
# even though it is only useful alongside the third-party `graphify` CLI, because it is inert
# without that CLI, so installing it costs nothing.
skill_roster_scan() {
  awk -v mode="$2" '
    /^!/ {
      if ($0 ~ /^!\/[A-Za-z0-9._-]+$/ && $0 !~ /^!\/\.\.?$/) {
        if (mode == "names") print substr($0, 3)
      } else if (mode == "rejects") print
    }
  ' "$1" 2>/dev/null
}

GITIGNORE="$HERE/skills/.gitignore"
SKILLS=""
if [ -f "$GITIGNORE" ]; then
  while IFS= read -r badline; do
    [ -n "$badline" ] || continue
    fail "skills: install/skills/.gitignore line \`$badline\` is not the \`!/name\` form this reader accepts — refusing to guess what it publishes rather than silently leaving it out of the install set"
  done < <(skill_roster_scan "$GITIGNORE" rejects)
  # NOT EVERY ALLOWLIST ENTRY IS A SKILL — `!/.gitignore` and `!/README.md` are files beside the
  # skills. Filtered by TYPE, not by a hardcoded list of the two names, which was itself a second
  # roster duplicated into verify.sh and would hard-fail the next such file (`!/LICENSE`). An entry
  # that names a regular file here is not a skill directory. An entry with NOTHING on disk stays in:
  # that is the missing-skill case, and it must reach the SKIP line below rather than vanish.
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    [ -f "$HERE/skills/$entry" ] && continue
    SKILLS="${SKILLS}${SKILLS:+ }$entry"
  done < <(skill_roster_scan "$GITIGNORE" names)
  # A declaration that names no skill is not an empty install, it is an unreadable declaration, and
  # saying so HERE is what stops the catch-all at the end of this block from blaming skills/.
  [ -n "$SKILLS" ] ||
    fail "skills: install/skills/.gitignore declares no skills — the declaration is empty or names only non-skill files, so nothing is known to install; skills/ itself is not the problem"
else
  fail "skills: install/skills/.gitignore is missing — the published-skill declaration could not be read, so nothing is known to install"
fi

echo "skills"
run mkdir -p "$CLAUDE/skills" || fail "skills: could not create $CLAUDE/skills"
skills_installed=0
skills_declared=0
# The roster admits no whitespace and no glob metacharacter, so this word-split is safe and a
# declared entry cannot undergo pathname expansion against the caller's working directory.
for s in $SKILLS; do
  skills_declared=$((skills_declared + 1))
  [ -d "$HERE/skills/$s" ] || { say "SKIP $s (not in this package)"; continue; }
  if [ "$DRY" -eq 1 ]; then
    say "would install $s"
    skills_installed=$((skills_installed + 1))
  elif install_tree "$HERE/skills/$s" "$CLAUDE/skills/$s"; then
    say "installed $s"
    skills_installed=$((skills_installed + 1))
  else
    fail "skill $s: could not install into $CLAUDE/skills"
  fi
done
# EVERY FILTERED COUNT CARRIES ITS TOTAL — but note that BOTH numbers on this line come from the
# declaration, so neither can contradict it, and this line is therefore not evidence that the
# declaration is right. The independent total is the directory, and comparing the two is verify.sh's
# job (`check_skill_presence … 1`), where a disagreement in either direction is a FAILURE. The loop
# below is this installer's half of that: it is what makes an undeclared directory visible here.
say "$skills_installed of $skills_declared declared skill(s) installed"
# A directory under skills/ that the declaration does NOT name is not installed — this installer
# must never copy a tree into ~/.claude on the strength of its presence alone. It is a `note` HERE
# and a FAILURE in verify.sh, which is not an inconsistency: an installer's job is to refuse it and
# say so, a gate's job is to refuse the tree. Reported so the gap is visible rather than silent.
for d in "$HERE"/skills/*/; do
  [ -f "${d}SKILL.md" ] || continue
  dn="$(basename "$d")"
  declared=0
  for s in $SKILLS; do [ "$s" = "$dn" ] && { declared=1; break; }; done
  [ "$declared" -eq 1 ] ||
    say "note: $dn is present under install/skills but not declared in install/skills/.gitignore — NOT installed"
done
# A skill missing from the package is a statement about package contents, not a failure — but ALL of
# them missing means the installer wired nothing, and WHICH cause it names decides which file the
# reader opens. This used to be one sentence blaming skills/ unconditionally, so a declaration that
# named nothing printed `0 of 0 declared skill(s) installed` as ordinary progress and then
# `is skills/ missing from this package?` — false, on an intact skills/ directory, sending the
# reader to the one place that was fine. The empty-declaration case now fails above, by name; this
# catch-all covers only what is left.
if [ "$skills_installed" -eq 0 ] && [ "$skills_declared" -gt 0 ]; then
  if [ ! -d "$HERE/skills" ]; then
    fail "skills: no skill was installed — skills/ is missing from this package"
  else
    fail "skills: no skill was installed — the declaration names $skills_declared skill(s) and not one of their directories is present under skills/, so this package is incomplete rather than empty"
  fi
fi

# ── Hooks ────────────────────────────────────────────────────────────────────────────────────────
echo "hooks"
run mkdir -p "$CLAUDE/hooks" || fail "hooks: could not create $CLAUDE/hooks"
hooks_installed=0
for h in "$HERE"/hooks/*; do
  [ -f "$h" ] || continue
  hb="$(basename "$h")"
  if [ "$DRY" -eq 1 ]; then
    say "would install $hb"
    hooks_installed=$((hooks_installed + 1))
  elif cp "$h" "$CLAUDE/hooks/$hb" && chmod +x "$CLAUDE/hooks/$hb"; then
    say "installed $hb"
    hooks_installed=$((hooks_installed + 1))
  else
    fail "hook $hb: could not install into $CLAUDE/hooks"
  fi
done
# With no hooks/ directory the glob above stays literal, `[ -f ]` is false and the loop records
# nothing at all — no failure, no output under this header. Count instead of trusting the loop.
[ "$hooks_installed" -gt 0 ] ||
  fail "hooks: no hook was installed — is hooks/ missing from this package?"

# ── settings.json ────────────────────────────────────────────────────────────────────────────────
# Merged, never replaced. A settings.json that is overwritten loses every unrelated preference, and
# a malformed one silently disables ALL settings from that file — so this validates before writing.
#
# The entries below name three scripts under $CLAUDE/hooks. Writing them when those scripts are not
# installed is the real damage of a package that shipped no hooks/: settings.json ends up wired to
# files that do not exist, and every later session reads it as configured. So the merge is gated on
# the scripts actually being present — not on the exit code, which the accounting already covers.
echo "settings.json"
missing_hooks=""
for hb in disclosure-check.sh graphify-session-lessons.sh graphify-query-advisor.py; do
  [ -f "$CLAUDE/hooks/$hb" ] || missing_hooks="$missing_hooks $hb"
done
if [ "$DRY" -eq 1 ]; then
  say "would merge 3 hook entries into $CLAUDE/settings.json (backup taken first)"
elif [ -n "$missing_hooks" ]; then
  fail "settings.json: hook entries were NOT merged — these scripts are not installed:$missing_hooks"
else
python3 - "$CLAUDE/settings.json" <<'PY' || fail "settings.json: hook entries were NOT merged (see the message above)"
import json, shutil, sys, time
from pathlib import Path

path = Path(sys.argv[1])
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as e:
        print(f"  REFUSED: {path} is not valid JSON ({e}).")
        print("  Fix it by hand, then re-run. A malformed settings.json disables every setting in it.")
        raise SystemExit(1)
    backup = path.with_suffix(f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    print(f"  backup: {backup.name}")

WANT = [
    ("SessionStart", None, "bash ~/.claude/hooks/disclosure-check.sh 2>/dev/null || true"),
    ("SessionStart", None, "bash ~/.claude/hooks/graphify-session-lessons.sh 2>/dev/null || true"),
    ("PreToolUse", "Bash", "python3 ~/.claude/hooks/graphify-query-advisor.py 2>/dev/null || true"),
]

hooks = data.setdefault("hooks", {})
added = 0
for event, matcher, command in WANT:
    entries = hooks.setdefault(event, [])
    already = any(command in h.get("command", "")
                  for e in entries for h in e.get("hooks", []))
    if already:
        continue
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        entry["matcher"] = matcher
    entries.append(entry)
    added += 1

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  {added} hook entr{'y' if added == 1 else 'ies'} added, {len(WANT) - added} already present")
PY
fi

# ── Codex ────────────────────────────────────────────────────────────────────────────────────────
if [ "$DO_CODEX" -eq 1 ]; then
  echo "codex"
  if [ ! -d "$CODEX" ]; then
    say "no $CODEX — Codex not installed here. Re-run with Codex present, or --no-codex to silence this."
  else
    run mkdir -p "$CODEX/skills" || fail "codex: could not create $CODEX/skills"
    for s in $SKILLS; do
      [ -d "$HERE/skills/$s" ] || continue
      if [ "$DRY" -eq 1 ]; then
        say "would mirror $s"
      elif install_tree "$HERE/skills/$s" "$CODEX/skills/$s"; then
        say "mirrored $s"
      else
        fail "skill $s: could not mirror into $CODEX/skills"
      fi
    done
    if [ "$DRY" -eq 0 ] && ! grep -q '^\[agents\]' "$CODEX/config.toml" 2>/dev/null; then
      # An existing config.toml must be backed up before we append; if that fails we do not append.
      # No config.toml at all is not a failure — the append below creates one, and in that case
      # there is nothing to back up, so the success line must not claim a backup was taken.
      toml_backup=""
      toml_ok=1
      if [ -f "$CODEX/config.toml" ]; then
        if cp "$CODEX/config.toml" "$CODEX/config.toml.bak-$(date +%Y%m%d-%H%M%S)"; then
          toml_backup=" (backup taken)"
        else
          fail "codex: could not back up config.toml — [agents] was NOT appended"
          toml_ok=0
        fi
      fi
      if [ "$toml_ok" -eq 0 ]; then
        :
      elif cat >> "$CODEX/config.toml" <<'EOF'

# Subagent defaults. Personas in ~/.codex/agents/ set their own model and effort; these apply only
# when a spawned agent specifies neither. Parent session settings above are unaffected.
[agents]
enabled = true
default_subagent_reasoning_effort = "medium"
max_concurrent_threads_per_session = 6
EOF
      then
        say "added [agents] to config.toml$toml_backup — subagents were off"
      else
        fail "codex: could not append [agents] to config.toml"
      fi
    else
      say "config.toml already has [agents], or dry run"
    fi
  fi
fi

# ── Personas ─────────────────────────────────────────────────────────────────────────────────────
echo "personas"
SYNC="$CLAUDE/skills/agent-personas/scripts/sync_personas.py"
if [ "$DRY" -eq 1 ]; then
  say "would render the persona pool into ~/.claude/agents and ~/.codex/agents"
elif [ -f "$SYNC" ]; then
  # pipefail is on, so a failing sync_personas.py is not masked by the trailing sed.
  python3 "$SYNC" | sed 's/^/  /' || fail "personas: sync_personas.py failed — ~/.claude/agents may be stale or incomplete"
else
  say "sync_personas.py missing — skipped"
  # Missing is only benign when agent-personas is genuinely absent from this package. If the skill
  # shipped, its script should be there and its absence means the skill install did not land.
  if [ -d "$HERE/skills/agent-personas" ]; then
    fail "personas: $SYNC missing even though the agent-personas skill is in this package"
  fi
fi

if [ -n "$FAILURES" ]; then
  # To stderr: the per-step FAILED lines above stay on stdout so they interleave with the progress
  # they belong to, but `./install.sh >/dev/null` must not be left with only an exit code.
  {
    echo
    echo "install FAILED — these steps did not complete:"
    printf '%s' "$FAILURES" | sed 's/^/  - /'
    echo
    say "Nothing was rolled back. A skill that failed to copy was staged, so the copy you already"
    say "had is untouched. Other failed steps may have completed partially — read each FAILED: line"
    say "above; each one says what it did or did not leave behind."
    say "Fix the causes and re-run — re-running is the repair, and is safe to repeat."
    say "Do not run ./verify.sh yet; this install is incomplete."
  } >&2
  exit 1
fi

echo
echo "next:"
say "1. ./verify.sh"
say "2. review the model names in ~/.claude/skills/agent-personas/personas/*.md — they are examples,"
say "   not recommendations, and go stale as models change"
say "3. open a project and run the project-onboarding skill"
[ "$DRY" -eq 0 ] && say "Claude Code may need /hooks opened once, or a restart, to load the new hooks"
exit 0
