# Installing

```bash
cd install
./install.sh --dry-run     # see what it would do
./install.sh               # do it
./verify.sh                # the repository gate
```

A plain install removes nothing: files an installed skill has and this package lacks, such as the
v5.1 scripts, references and persona sources, are carried forward, and v5.1 skills, personas and
data stay where they are until `--retire-v5`. A project that still carries the v5.1 runtime pin
(`docs/agents/execution/runtime.json`) is migrated by hand first: v6 refuses to execute there and the
session hook says so. Follow the [migration reference](skills/execution-methodology/references/migrate.md).

## Requirements

| | |
|---|---|
| **Python 3.10+** | The tools use PEP 604 syntax; the installer refuses older versions |
| **git** | Required for the per-repository hooks and the goal tools |
| **Claude Code and/or Codex** | Either alone is fine. The Codex side is skipped when its home directory is absent |

`gh`, `ripgrep` and `graphify` are optional. Without `graphify` the `graph-navigation` skill and
the two graphify hooks are inert.

## What it installs

```
~/.claude/skills/        the four published skills named in skills/.gitignore:
                         execution-methodology, agent-personas, progressive-disclosure, graph-navigation
~/.claude/hooks/         every script in hooks/, overwriting older copies
~/.claude/settings.json  hook entries, merged: four existing ones, plus
                           SessionStart  [ -n "${GOAL_HARNESS:-}" ] || bash ~/.claude/hooks/goal-session.sh 2>/dev/null || true
                           Stop          [ -n "${GOAL_HARNESS:-}" ] || python3 ~/.claude/skills/execution-methodology/scripts/goal.py stop-hook
~/.claude/agents/        the persona pool, rendered by sync_personas.py
$CODEX_HOME/skills/      the same four skills (CODEX_HOME defaults to ~/.codex)
$CODEX_HOME/hooks/       goal-session.sh
$CODEX_HOME/hooks.json   the same SessionStart and Stop hooks, with absolute paths, merged; each also
                         steps aside when the project's .codex/hooks.json registers that hook
$CODEX_HOME/agents/      the same personas, as TOML
$CODEX_HOME/config.toml  an [agents] block, appended only if none exists
```

**Merged, never replaced.** `settings.json` and `hooks.json` are parsed first, and a file that is not
valid JSON is refused. Entries are appended only when their command is absent, so existing entries
keep their position. The file is rewritten, after a backup, only when something was added. A second
install changes nothing.

**One goal hook per event.** The global goal hooks exit silently when `GOAL_HARNESS` is set:
`run_goal.py` sets it in driver sessions and registers its own hooks there. Two Stop hooks over one
goal would defeat the stall cap.

**Codex hook trust.** Codex runs a user-level hook only after you review and trust it in Codex. The
installer never writes trust state, so trust the two new hooks once after the first install, and
again whenever their entries change.

**Personas** are rendered into a scratch directory and copied file by file. Run directly, the
renderer would also prune every generated agent it does not know, including the v5.1 personas, and
a plain install removes nothing.

The installer does not touch `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md`; see
[../docs/architecture/operating-model.md](../docs/architecture/operating-model.md) and
[../docs/runbooks/codex.md](../docs/runbooks/codex.md).

## Retiring v5.1

After every project is migrated:

```bash
./install.sh --retire-v5 --dry-run   # lists exactly what it would delete
./install.sh --retire-v5
```

It installs as usual and then deletes only the paths named in the retire-v5 list at the top of
`install.sh`:
- the six retired skill directories;
- the thirteen retired persona renders, and only when they carry the renderer's GENERATED marker;
- inside the published skills, the files v5.1 shipped and v6 does not (old scripts, references,
  tests and persona sources), and the v5.1 round-grant ledger.

`--retire-v5` is skipped if any install step fails. Anything else it finds in the skill and agent
directories is reported and left in place, including files inside a published skill that the
list does not name. That
includes any `approved-runtimes` bundle, which is yours to remove by hand.

## The repository gate

`./verify.sh` runs, from the repository root:
1. every published skill's unittest suite;
2. `validate_disclosure.py --standard`;
3. the identifier guard over the tree;
4. the size ceilings (`tests/test_size.py`);
5. a dangling-reference scan for retired names;
6. the installer tests (`tests/test_install.py`, against a temporary HOME) and
   `preserve_selftest.sh`;
7. `install.sh --dry-run` against a scratch HOME.

A suite with failing tests prints unittest's own `FAIL:`/`ERROR:` lines. Any other failing check
(including a suite that ran no test, crashed, or is missing for a skill with `scripts/`) prints
`FAIL: <check> (verify.checks)`. The last line is `verify: PASS` or
`verify: FAIL (<n> checks)`. `./verify.sh --installed` adds a read-only parity check of the
installed skills, hooks, registrations and personas against this repository.

## If something fails

| Symptom | Cause |
|---|---|
| `REFUSED: … is not valid JSON` | Fix the file by hand; the installer will not write over it |
| Hooks installed but nothing appears at session start | In Claude Code open `/hooks` once or restart; in Codex, trust the hooks |
| `unknown option` and exit 64 | A mistyped flag; nothing was changed |
| Codex does not spawn personas | No `[agents]` block, or `enabled = false` |
