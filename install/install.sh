#!/usr/bin/env bash
# Install the v6 toolchain into ~/.claude and ~/.codex (or $CODEX_HOME).
#
# Installs the published skills, the Stop hook registration for both harnesses, and the rendered
# personas. Idempotent: a second run changes nothing. A plain install removes nothing: files an
# installed skill has and this package lacks are carried forward. Only --retire-v5 deletes, and
# only the named v5.1 set below.
#
#   ./install.sh               install or update
#   ./install.sh --dry-run     print what would happen, change nothing
#   ./install.sh --no-codex    skip the Codex side
#   ./install.sh --retire-v5   install, then delete the known v5.1 global files and report the rest
#   ./install.sh -h|--help     print this and exit
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="$HOME/.claude"
# An empty CODEX_HOME is unset, as in the persona renderer.
CODEX="${CODEX_HOME:-$HOME/.codex}"
DRY=0
DO_CODEX=1
RETIRE=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --no-codex) DO_CODEX=0 ;;
    --retire-v5) RETIRE=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    # 64 (EX_USAGE), so a bad invocation is never mistaken for a failed install step (1).
    *) echo "unknown option: $arg" >&2; exit 64 ;;
  esac
done

say()  { printf '  %s\n' "$1"; }
run()  { if [ "$DRY" -eq 1 ]; then printf '  would: %s\n' "$*"; else "$@"; fi; }

# No `set -e`: every step that must succeed records its failure here and the script exits 1 at the
# end, so `./install.sh && ./verify.sh` can never report success for an install that wired nothing.
FAILURES=""
fail() { FAILURES="${FAILURES}${1}
"; printf '  FAILED: %s\n' "$1"; }

TMP="$(mktemp -d)" || { echo "could not create a temporary directory" >&2; exit 1; }
trap 'rm -rf "$TMP"' EXIT

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

# ── The known v5.1 set ───────────────────────────────────────────────────────────────────────────
# The one place that names the retired set on purpose; verify.sh's dangling-reference scan skips the
# lines between the markers. --retire-v5 deletes exactly these paths under ~/.claude and the Codex
# home and reports everything else it finds:
#   RETIRED_SKILLS        whole skill directories
#   RETIRED_PERSONAS      persona renders in agents/, only when they carry the GENERATED marker
#   RETIRED_SKILL_FILES   files inside a published skill (relative to skills/) that v5.1 shipped and
#                         v6 does not: every file F-3 deleted from execution-methodology and
#                         agent-personas, plus the round-grant ledger. A plain install carries them
#                         forward (see install_tree); only --retire-v5 removes them.
# BEGIN retire-v5 list
RETIRED_SKILLS="methodology-management project-onboarding project-migration project-conformance agent-persona-factory gate-sandbox"
RETIRED_PERSONAS="acceptance architect chief-of-staff contract-architect developer docs-steward migration-validator planner product-steward scout security-validator senior-developer test-judge"
RETIRED_SKILL_FILES="
agent-personas/ROSTER
agent-personas/personas/acceptance.md
agent-personas/personas/architect.md
agent-personas/personas/chief-of-staff.md
agent-personas/personas/contract-architect.md
agent-personas/personas/developer.md
agent-personas/personas/docs-steward.md
agent-personas/personas/migration-validator.md
agent-personas/personas/planner.md
agent-personas/personas/product-steward.md
agent-personas/personas/scout.md
agent-personas/personas/security-validator.md
agent-personas/personas/senior-developer.md
agent-personas/personas/test-judge.md
execution-methodology/ROUND-GRANTS.tsv
execution-methodology/references/changelog-v1-v2.md
execution-methodology/references/codex-gate-sandbox.md
execution-methodology/references/execution-loop.md
execution-methodology/references/history-v3-v5.md
execution-methodology/references/junit-evidence.md
execution-methodology/references/readme.md
execution-methodology/references/specs.md
execution-methodology/references/task-card.md
execution-methodology/scripts/check_review_budget.py
execution-methodology/scripts/check_review_budget_selftest.py
execution-methodology/scripts/milestone_seal.py
execution-methodology/scripts/milestone_seal_selftest.py
execution-methodology/scripts/plan_waves.py
execution-methodology/scripts/plan_waves_selftest.py
execution-methodology/scripts/ratio_meter.py
execution-methodology/scripts/ratio_meter_selftest.py
execution-methodology/scripts/runtime-status.schema.json
execution-methodology/scripts/spec_check.py
execution-methodology/scripts/spec_check_selftest.py
execution-methodology/scripts/start_junit_run.py
execution-methodology/scripts/start_junit_run_selftest.py
execution-methodology/scripts/sync_methodology.py
execution-methodology/scripts/sync_methodology_selftest.py
execution-methodology/scripts/trace_check.py
execution-methodology/scripts/trace_check_selftest.py
execution-methodology/scripts/validate_card.py
execution-methodology/scripts/validate_card_selftest.py
execution-methodology/scripts/verify_junit.py
execution-methodology/scripts/verify_junit_selftest.py
execution-methodology/scripts/weekly_review.py
execution-methodology/scripts/weekly_review_selftest.py
execution-methodology/tests/test_break_tests.py
execution-methodology/tests/test_check_review_budget.py
execution-methodology/tests/test_execution_loop.py
execution-methodology/tests/test_methodology_policy.py
execution-methodology/tests/test_milestone_seal.py
execution-methodology/tests/test_onboarding_adoption.py
execution-methodology/tests/test_plan_waves.py
execution-methodology/tests/test_plan_waves_milestone.py
execution-methodology/tests/test_ratio_meter.py
execution-methodology/tests/test_repo_sync.py
execution-methodology/tests/test_runtime_status.py
execution-methodology/tests/test_shape_diagram.py
execution-methodology/tests/test_spec_check.py
execution-methodology/tests/test_sync_preview.py
execution-methodology/tests/test_trace_check.py
execution-methodology/tests/test_validate_card.py
execution-methodology/tests/test_verify_junit.py
execution-methodology/tests/test_weekly_review.py
"
# END retire-v5 list

# Files under DEST (paths relative to it) that SRC lacks, ignoring __pycache__: what a plain
# install carries forward and what --retire-v5 judges against RETIRED_SKILL_FILES.
extras_between() {  # extras_between SRC DEST
  [ -d "$2" ] || return 0
  (cd "$2" && find . \( -type f -o -type l \) -not -path '*/__pycache__/*' -print) | sed 's|^\./||' |
    while IFS= read -r rel; do
      [ -e "$1/$rel" ] || [ -L "$1/$rel" ] || printf '%s\n' "$rel"
    done
}

# Copy a skill tree into place with no window in which neither copy exists: stage beside the
# target, move the old copy aside by rename, swap, and only then delete the old copy. A failed copy
# leaves the working install untouched, which matters most for execution-methodology, whose guard.py
# every repository's git hooks call.
#
# Every file the installed copy has and the vendored tree lacks is carried into the staged tree, so
# a plain install removes nothing (AC-12): v5.1 scripts, references and persona sources, and any
# machine-only data, survive until --retire-v5. A vendored file always wins over an installed one.
install_tree() {
  local src="$1" dest="$2" staged="$2.staging.$$" aside="$2.replacing.$$" rel
  rm -rf "$staged" "$aside" || return 1
  if cp -R "$src" "$staged" && chmod_scripts "$staged"; then
    find "$staged" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      mkdir -p "$(dirname "$staged/$rel")" && cp -P -p "$dest/$rel" "$staged/$rel" ||
        { rm -rf "$staged"; return 1; }
    done < <(extras_between "$staged" "$dest")
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

# Write one file only when its content differs, through a rename so a symlink at the target is
# replaced rather than written through. Prints "wrote" or nothing.
place_file() {
  local src="$1" dest="$2"
  cmp -s "$src" "$dest" 2>/dev/null && return 0
  if [ "$DRY" -eq 1 ]; then say "would write $dest"; return 0; fi
  mkdir -p "$(dirname "$dest")" && cp "$src" "$dest.tmp.$$" && mv -f "$dest.tmp.$$" "$dest" ||
    { rm -f "$dest.tmp.$$"; return 1; }
  say "wrote $dest"
}

# ── Preconditions ────────────────────────────────────────────────────────────────────────────────
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "python3 $PYV found; 3.10 or newer is required" >&2; exit 1; }
command -v git >/dev/null || echo "  note: git not found — the per-repo hooks will be unusable"
[ -d "$CODEX" ] || { [ "$DO_CODEX" -eq 1 ] && say "no $CODEX — Codex is not installed here; the Codex side is skipped (--no-codex silences this)"; DO_CODEX=0; }

echo "agent toolchain installer"
say "python3 $PYV"
say "target: $CLAUDE$([ "$DO_CODEX" -eq 1 ] && echo " and $CODEX")"
[ "$DRY" -eq 1 ] && say "DRY RUN — nothing will be written"

# ── Skills ───────────────────────────────────────────────────────────────────────────────────────
# The published set is install/skills/.gitignore's `!/name` allow lines, so no script carries a
# second list. The reader is strict: any other negation form is a failure, never a silent omission.
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
    fail "skills: install/skills/.gitignore line \`$badline\` is not the \`!/name\` form — refusing to guess what it publishes"
  done < <(skill_roster_scan "$GITIGNORE" rejects)
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    [ -f "$HERE/skills/$entry" ] && continue   # .gitignore and README.md sit beside the skills
    SKILLS="${SKILLS}${SKILLS:+ }$entry"
  done < <(skill_roster_scan "$GITIGNORE" names)
  [ -n "$SKILLS" ] || fail "skills: install/skills/.gitignore declares no skills"
else
  fail "skills: install/skills/.gitignore is missing — nothing is known to install"
fi

# All skills land in this one step, so an installed tree never pairs a new skill with an older one.
install_skills() {  # install_skills DEST_ROOT VERB
  local root="$1" verb="$2" s n=0 total=0 kept rel
  run mkdir -p "$root/skills" || { fail "skills: could not create $root/skills"; return; }
  for s in $SKILLS; do
    total=$((total + 1))
    [ -d "$HERE/skills/$s" ] && kept="$(extras_between "$HERE/skills/$s" "$root/skills/$s")" || kept=""
    if [ -n "$kept" ]; then
      if [ "$DRY" -eq 1 ]; then
        while IFS= read -r rel; do say "would keep $root/skills/$s/$rel (not in this package)"; done <<< "$kept"
      else
        say "kept $(printf '%s\n' "$kept" | grep -c .) file(s) in $root/skills/$s that this package does not ship (--retire-v5 judges them)"
      fi
    fi
    if [ ! -d "$HERE/skills/$s" ]; then
      fail "skill $s: declared in install/skills/.gitignore but not in this package"
    elif [ "$DRY" -eq 1 ]; then
      say "would $verb $s"; n=$((n + 1))
    elif install_tree "$HERE/skills/$s" "$root/skills/$s"; then
      say "${verb}ed $s"; n=$((n + 1))
    else
      fail "skill $s: could not $verb into $root/skills"
    fi
  done
  say "$n of $total declared skill(s) ${verb}ed into $root/skills"
}

echo "skills"
install_skills "$CLAUDE" install
[ "$DO_CODEX" -eq 1 ] && install_skills "$CODEX" mirror
for d in "$HERE"/skills/*/; do
  [ -f "${d}SKILL.md" ] || continue
  case " $SKILLS " in *" $(basename "$d") "*) ;; *)
    say "note: $(basename "$d") is under install/skills but not declared in its .gitignore — NOT installed" ;;
  esac
done

# ── Hook registration ────────────────────────────────────────────────────────────────────────────
# Merged, never replaced: an existing file is parsed first (malformed JSON is refused), entries are
# appended only when their command is absent, and the file is rewritten, with a backup, only when
# something was added. Appending keeps every existing entry at its index, which is what Codex keys
# hook trust on. WANT is the one roster; `list` prints the scripts it references so the shell can
# refuse to register a script that is not installed.
MERGE="$TMP/merge_hooks.py"
cat > "$MERGE" <<'PY'
import json, shlex, shutil, sys, time
from pathlib import Path

harness, root, path, mode = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
GOAL = "skills/execution-methodology/scripts/goal.py"
# One goal hook per harness: the Stop hook, which blocks a stop while `goal.py done` is unmet.
if harness == "claude":
    ref = lambda rel: "~/.claude/" + rel  # noqa: E731
    WANT = [
        ("Stop", None, "python3 {} stop-hook", GOAL),
    ]
else:  # codex: absolute paths, because CODEX_HOME need not be ~/.codex
    ref = lambda rel: shlex.quote(f"{root}/{rel}")  # noqa: E731
    WANT = [
        ("Stop", None, "python3 {} stop-hook", GOAL),
    ]

if mode == "list":
    print("\n".join(rel for *_, rel in WANT))
    raise SystemExit(0)

data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as e:
        print(f"  REFUSED: {path} is not valid JSON ({e}). Fix it by hand, then re-run.")
        raise SystemExit(1)
def shape_ok(d):
    """{"hooks": {Event: [{"hooks": [{...}, ...], ...}, ...]}}, with every level the right type."""
    if not isinstance(d, dict) or not isinstance(d.get("hooks", {}), dict):
        return False
    for entries in d.get("hooks", {}).values():
        if not isinstance(entries, list):
            return False
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get("hooks", []), list) \
                    or not all(isinstance(h, dict) for h in e.get("hooks", [])):
                return False
    return True


if not shape_ok(data):
    print(f"  REFUSED: {path} is not in the expected hooks shape (an event must hold a list of "
          "entries, each a dict whose `hooks` is a list of dicts). Fix it by hand; nothing merged.")
    raise SystemExit(1)

hooks = data.setdefault("hooks", {})
added = []
for event, matcher, template, rel in WANT:
    command = template.format(ref(rel))
    entries = hooks.setdefault(event, [])
    if any(command in h.get("command", "") for e in entries for h in e.get("hooks", [])):
        continue
    entry = {"hooks": [{"type": "command", "command": command}]}
    if matcher:
        entry["matcher"] = matcher
    entries.append(entry)
    added.append(f"{event}: {command}")

if mode == "plan":
    for a in added:
        print(f"  would register {a}")
    print(f"  {len(added)} to add, {len(WANT) - len(added)} already present in {path}")
    raise SystemExit(0)
if not added:
    print(f"  0 added, {len(WANT)} already present — {path.name} unchanged")
    raise SystemExit(0)
if path.is_file():
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    print(f"  backup: {backup.name}")
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_name(path.name + ".tmp")
tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
tmp.replace(path)
for a in added:
    print(f"  registered {a}")
print(f"  {len(added)} added, {len(WANT) - len(added)} already present in {path.name}")
PY

register_hooks() {  # register_hooks HARNESS ROOT FILE
  local harness="$1" root="$2" file="$3" refs rel missing=""
  refs="$(python3 "$MERGE" "$harness" "$root" "$file" list)" && [ -n "$refs" ] ||
    { fail "$harness hooks: the registration roster could not be read — nothing registered"; return; }
  if [ "$DRY" -eq 1 ]; then
    python3 "$MERGE" "$harness" "$root" "$file" plan || fail "$harness hooks: $file could not be planned"
    return
  fi
  for rel in $refs; do [ -f "$root/$rel" ] || missing="$missing $rel"; done
  if [ -n "$missing" ]; then
    fail "$harness hooks: NOT registered — these scripts are not installed under $root:$missing"
  else
    python3 "$MERGE" "$harness" "$root" "$file" merge || fail "$harness hooks: $file was NOT merged"
  fi
}

echo "hook registration"
register_hooks claude "$CLAUDE" "$CLAUDE/settings.json"
if [ "$DO_CODEX" -eq 1 ]; then
  # Codex reads user-level hooks from $CODEX_HOME/hooks.json. It runs a hook only after the
  # founder trusts it in Codex's hook review; this installer never writes trust state.
  register_hooks codex "$CODEX" "$CODEX/hooks.json"
  say "Codex runs new or changed hooks only after you review and trust them once in Codex"
fi

# ── Codex subagents ──────────────────────────────────────────────────────────────────────────────
if [ "$DO_CODEX" -eq 1 ]; then
  echo "codex config"
  if grep -q '^\[agents\]' "$CODEX/config.toml" 2>/dev/null; then
    say "config.toml already has [agents]"
  elif [ "$DRY" -eq 1 ]; then
    say "would append [agents] to $CODEX/config.toml$([ -f "$CODEX/config.toml" ] && echo " (backup taken first)")"
  else
    toml_ok=1
    if [ -f "$CODEX/config.toml" ]; then
      cp "$CODEX/config.toml" "$CODEX/config.toml.bak-$(date +%Y%m%d-%H%M%S)" ||
        { fail "codex: could not back up config.toml — [agents] was NOT appended"; toml_ok=0; }
    fi
    if [ "$toml_ok" -eq 1 ]; then
      cat >> "$CODEX/config.toml" <<'EOF' && say "added [agents] to config.toml" || fail "codex: could not append [agents] to config.toml"

# Subagent defaults. Personas in agents/ set their own model and effort; these apply only when a
# spawned agent specifies neither.
[agents]
enabled = true
default_subagent_reasoning_effort = "medium"
max_concurrent_threads_per_session = 6
EOF
    fi
  fi
fi

# ── Personas ─────────────────────────────────────────────────────────────────────────────────────
# Rendered by sync_personas.py (global scope) into a scratch HOME, then copied file by file. Run
# against the real directories the renderer would also prune every generated render it does not
# know, which includes the v5.1 personas; a plain install removes nothing, so pruning is left to
# --retire-v5 and its named list.
echo "personas"
SYNC="$HERE/skills/agent-personas/scripts/sync_personas.py"
RENDER="$TMP/render"
mkdir -p "$RENDER/.claude" "$RENDER/.codex"
if [ ! -f "$SYNC" ]; then
  fail "personas: $SYNC is missing from this package"
elif ! HOME="$RENDER" CODEX_HOME="$RENDER/.codex" PYTHONDONTWRITEBYTECODE=1 \
       python3 "$SYNC" --scope global >"$TMP/render.log" 2>&1; then
  sed 's/^/  /' "$TMP/render.log"
  fail "personas: sync_personas.py could not render the pool — nothing was written"
else
  rendered=0
  for f in "$RENDER/.claude/agents/"*.md; do
    [ -f "$f" ] || continue
    rendered=$((rendered + 1))
    place_file "$f" "$CLAUDE/agents/$(basename "$f")" || fail "personas: could not write $(basename "$f")"
  done
  if [ "$DO_CODEX" -eq 1 ]; then
    for f in "$RENDER/.codex/agents/"*.toml; do
      [ -f "$f" ] || continue
      place_file "$f" "$CODEX/agents/$(basename "$f")" || fail "personas: could not write $(basename "$f")"
    done
  fi
  [ "$rendered" -gt 0 ] || fail "personas: the renderer produced no persona"
  say "$rendered persona(s) current$([ "$DO_CODEX" -eq 1 ] && echo " in both harnesses")"
fi

# ── Retire v5.1 ──────────────────────────────────────────────────────────────────────────────────
# Deletes exactly the paths the list at the top names. A hand-written agent that shares a retired
# name is kept. Any other entry in the skill and agent directories, and any approved-runtimes
# bundle, is reported and left in place.
GENERATED_MARK="# GENERATED by agent-personas/scripts/sync_personas.py"

retire_path() {
  if [ "$DRY" -eq 1 ]; then say "would delete $1"; return; fi
  rm -rf "$1" && say "deleted $1" || fail "retire-v5: could not delete $1"
}

retire_root() {  # retire_root ROOT AGENT_EXT
  local root="$1" ext="$2" n p e name keep s rel
  for n in $RETIRED_SKILLS; do
    { [ -e "$root/skills/$n" ] || [ -L "$root/skills/$n" ]; } && retire_path "$root/skills/$n"
  done
  # Inside each published skill: the files this package does not ship are deleted when the list
  # names them, and reported otherwise.
  for s in $SKILLS; do
    [ -d "$HERE/skills/$s" ] || continue
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      case "$RETIRED_SKILL_FILES" in
        *"
$s/$rel
"*) retire_path "$root/skills/$s/$rel" ;;
        *) say "left in place (not in the v5.1 set): $root/skills/$s/$rel" ;;
      esac
    done < <(extras_between "$HERE/skills/$s" "$root/skills/$s")
  done
  for n in $RETIRED_PERSONAS; do
    p="$root/agents/$n.$ext"
    [ -f "$p" ] || continue
    if grep -qF "$GENERATED_MARK" "$p"; then retire_path "$p"
    else say "kept $p (named in the v5.1 set but not generated by the persona renderer)"; fi
  done
  # Report everything else in the two directories the v5.1 set lived in.
  for e in "$root"/skills/* "$root"/skills/.[!.]*; do
    [ -d "$e" ] || continue
    name="$(basename "$e")"; keep=0
    case " $SKILLS $RETIRED_SKILLS " in *" $name "*) keep=1 ;; esac
    [ "$keep" -eq 1 ] || say "left in place (not in the v5.1 set): $e"
  done
  for e in "$root"/agents/*.md "$root"/agents/*.toml; do
    [ -f "$e" ] || continue
    name="$(basename "${e%.*}")"
    [ -f "$HERE/skills/agent-personas/personas/$name.md" ] && continue
    case " $RETIRED_PERSONAS " in *" $name "*) continue ;; esac
    say "left in place (not in the v5.1 set): $e"
  done
  [ -d "$root/approved-runtimes" ] &&
    say "left in place (approved v5.1 runtime bundles are the founder's to remove by hand): $root/approved-runtimes"
  return 0
}

if [ "$RETIRE" -eq 1 ]; then
  echo "retire v5.1"
  if [ -n "$FAILURES" ]; then
    # Retiring v5.1 while its v6 replacement is incomplete would leave neither working.
    say "SKIPPED: an install step above failed, so nothing was retired; fix it and re-run --retire-v5"
  else
    retire_root "$CLAUDE" md
    [ "$DO_CODEX" -eq 1 ] && retire_root "$CODEX" toml
  fi
fi

# ── Result ───────────────────────────────────────────────────────────────────────────────────────
if [ -n "$FAILURES" ]; then
  {
    echo
    echo "install FAILED — these steps did not complete:"
    printf '%s' "$FAILURES" | sed 's/^/  - /'
    echo
    say "Nothing was rolled back. A skill that failed to copy was staged, so the copy you already"
    say "had is untouched. Fix the causes and re-run; re-running is the repair."
  } >&2
  exit 1
fi

echo
echo "next:"
say "1. ./verify.sh"
say "2. migrate each v5.1 project by hand: skills/execution-methodology/references/migrate.md"
[ "$RETIRE" -eq 0 ] && say "3. once every project is migrated: ./install.sh --retire-v5"
[ "$DRY" -eq 0 ] && say "Claude Code may need /hooks opened once, or a restart, to load new hooks"
exit 0
