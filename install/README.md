# Installing

```bash
cd install
./install.sh --dry-run     # see what it would do
./install.sh               # do it
./verify.sh                # prove it worked
```

Then open Claude Code or Codex in a project and explicitly invoke **`methodology-management`**
to assess or adopt it. `project-onboarding` remains a compatibility entry for setup.

## Requirements

| | |
|---|---|
| **Python 3.10+** | The tools use PEP 604 (`str \| None`) syntax. The installer refuses on older versions rather than failing later |
| **git** | Required for the per-repo hooks; everything else degrades without it |
| **Claude Code and/or Codex** | Either alone is fine. The installer skips a harness that is not present |

Optional, and genuinely optional — nothing breaks without them:

| | Used for |
|---|---|
| `gh` | The remote half of `check_github.py` (private/public, Actions, Wiki). Local git checks still run |
| `ripgrep` | Some documented searches. `grep -r` works everywhere |
| `graphify` | Code-graph navigation. The `graph-navigation` skill and two hooks are inert without it, which is harmless |

## What it installs

```
~/.claude/skills/       published skills selected by skills/.gitignore
~/.claude/hooks/        disclosure-check.sh, preflight.sh, graphify-session-lessons.sh,
                        graphify-query-advisor.py
~/.claude/settings.json 4 hook entries (3 SessionStart, 1 PreToolUse), MERGED into your existing file
~/.claude/agents/       personas rendered from the pool
~/.codex/skills/        the same skills, mirrored
~/.codex/agents/        the same personas, as TOML
~/.codex/config.toml    an [agents] block, appended, if none exists
```

The [published inventory](../docs/README.md#what-is-published-and-what-is-not) names the skills;
the [management route](../docs/runbooks/methodology-management.md) explains execution,
maintenance and compatibility entries.

**Nothing is overwritten wholesale.** `settings.json` is parsed, backed up, and merged — hook
entries already present are left alone. If it is not valid JSON the installer refuses and tells you,
because a malformed `settings.json` silently disables every setting in it. `config.toml` is appended
to, after a backup, and only if it has no `[agents]` block.

It does **not** touch `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md`. Those carry your own operating
rules; see [../docs/architecture/operating-model.md](../docs/architecture/operating-model.md) for what belongs there and
[../docs/runbooks/codex.md](../docs/runbooks/codex.md) for the sections the two harnesses must keep identical.

## After installing

1. **Claude Code may need `/hooks` opened once, or a restart**, before it loads new hook entries.
   Skills and personas load without a restart.
2. **Review the model names.** `~/.claude/skills/agent-personas/personas/*.md` name specific models
   and effort levels. Those are worked examples from a particular week, not recommendations — see
   [../docs/product/measurements.md](../docs/product/measurements.md) for how they were derived, and retune them.
   `sync_personas.py --list` shows the current mapping; edit a persona and re-run
   `sync_personas.py` to apply.
3. **Invoke `methodology-management` in each project when ready.** Request assessment or adoption
   explicitly; global installation does not migrate projects. See the
   [setup procedure](skills/methodology-management/references/setup.md).

## Keeping it current

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/check_toolchain.py
```

Three pieces of global state drift silently and nothing else watches them: the persona pool versus
the agents generated from it, the instruction blocks mirrored between harnesses, and the Codex
skills copy. The session hook runs this in every project.

Re-run `./install.sh` to update after pulling a new version. It is idempotent.

## Uninstalling

Remove the published skill directories named in `skills/.gitignore` from `~/.claude/skills/` and
`~/.codex/skills/`, preserving any separately installed skills. Remove the four hook files listed
above and their entries in `~/.claude/settings.json` by hand. Generated agents and configuration
are separate; preserve any custom agents and restore configuration from the installer backups
when appropriate.

Per-repository git hooks are separate. In each repo:
`python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py . --scope project --uninstall`

## If something fails

| Symptom | Cause |
|---|---|
| `python3 3.9 found; 3.10 or newer is required` | Install a newer Python, or run the tools with an explicit `python3.11` |
| `REFUSED: settings.json is not valid JSON` | Fix the JSON by hand first — the installer will not write over a broken file |
| Hooks installed but nothing appears at session start | Open `/hooks` once, or restart. The watcher only tracks directories that existed at startup |
| `verify.sh` says a script "fails to run" | Almost always the Python version |
| Codex does not spawn personas | No `[agents]` block, or `enabled = false`. See [../docs/runbooks/codex.md](../docs/runbooks/codex.md) |
