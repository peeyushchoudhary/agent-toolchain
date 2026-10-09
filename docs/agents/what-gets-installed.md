# What gets installed

Every file the installer places outside a project, what each does, and how they interact. The
authored sources live in `../../install/`, and the installed files are the authority: when this
document disagrees with them, they win. The full procedure is in
[install/README.md](../../install/README.md).

`install/` is the only source. Nothing is copied back from `~/.claude` or `~/.codex`, so an edit
made to an installed file is overwritten by the next install.

## Claude Code, in `~/.claude/`

### Skills

The skills named in `install/skills/.gitignore`. The installer derives the set from that
allowlist rather than carrying its own count, and a declared skill missing from the package is a
failure.

| Path | Purpose |
|---|---|
| `skills/execution-methodology/` | The chief's rules (`SKILL.md`), the design-page reference, the reviewer prompt, the goal and gate tools, the unattended runner |

`graphify` may also be present. It is a vendor skill that this repository neither publishes nor
manages.

### Scripts

| Script | Does |
|---|---|
| `execution-methodology/scripts/goal.py` | Parses a plan; lint, status, next, resume, packet, the eight-row done; runs the Stop hook |
| `execution-methodology/scripts/gate.py` | Runs a gate, parses counts, writes receipts bound to tree and command |
| `execution-methodology/scripts/run.sh` | Runs fresh unattended sessions until `goal.py done` holds, or stalls or parks |
| `execution-methodology/scripts/guard.py` + `git-hooks.sh` | The one git guard (staged content, commit message, pushed range) and its per-repository hook installer |

### Hooks, registered in `~/.claude/settings.json`

The settings file is merged, never replaced: entries are appended only when their command is absent, a
file that is not valid JSON is refused, and a backup is taken before the first change.

| Event | Script | Behaviour |
|---|---|---|
| `Stop` | `goal.py stop-hook` | Blocks a stop while `goal.py done` is unmet, at most three times per session |

### Instructions

`~/.claude/CLAUDE.md` is private and untouched by the installer. The replacement text for its
execution section is in the [global-instructions runbook](../runbooks/global-instructions.md).

## Codex, in `~/.codex/`

Skipped when the Codex home is absent.

| Path | Purpose |
|---|---|
| `skills/` | The same skills |
| `hooks.json` | The same Stop hook with an absolute path, merged |
| `config.toml` | An `[agents]` block, appended only if none exists |
| `AGENTS.md` | Private, untouched; see the runbook above |

Codex runs a user-level hook only after the user trusts it. The installer never writes trust state,
so trust the two goal hooks once after the first install and again whenever their entries change.

## Per-repository

Git hooks are never cloned, so each clone installs them once (`--uninstall` removes only its own):

```bash
bash ~/.claude/skills/execution-methodology/scripts/git-hooks.sh <repo>
```

It writes `pre-commit`, `pre-merge-commit`, `commit-msg` and `pre-push` (honouring
`core.hooksPath`), each running `guard.py`: commits and merges may not add a home path, the local git identity, a name on the private list or
a secret; pushes may not carry a secret or a file over 10 MB, nor move an existing `main`. It
refuses when the installed `guard.py` is absent, and the guard exits 2, blocking, when it cannot
run.

## Verifying

```bash
cd install && ./verify.sh              # the repository gate
cd install && ./verify.sh --installed  # adds a read-only parity check against the installed copies
```

## Retiring v5.1

A plain install removes nothing. `install.sh --retire-v5` deletes only the paths in the marked list
at the top of `install.sh`, and `--dry-run` prints exactly that set first. Run it once every project
is migrated; see the
migration reference (`docs/runbooks/migrate-v5.md`, written in T8).
