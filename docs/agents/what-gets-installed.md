# What gets installed

Every file the installer places outside a project, what each does, and how they interact. The
authored sources live in `../../install/`, and the installed files are the authority: when this
document disagrees with them, they win. The full procedure is in
[install/README.md](../../install/README.md).

`install/` is the only source. Nothing is copied back from `~/.claude` or `~/.codex`, so an edit
made to an installed file is overwritten by the next install.

## Claude Code, in `~/.claude/`

### Skills

One skill, copied without its `tests/`. Files an earlier install left inside it are kept and
reported, never deleted, except by `--retire-v5`.

| Path | Purpose |
|---|---|
| `skills/execution-methodology/` | The chief's rules (`SKILL.md`), the design-page reference, the reviewer prompt, the goal and gate tools, the unattended runner |

Other skills may be present. This repository neither publishes nor manages them.

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

`~/.claude/CLAUDE.md` is written from `install/global.md`. A file that differs is first backed up
beside it as `CLAUDE.md.bak-<YYYYmmdd-HHMMSS>`; `--uninstall` removes an unmodified copy and
restores the newest backup.

## Codex, in `~/.codex/`

Skipped when the Codex home is absent.

| Path | Purpose |
|---|---|
| `skills/` | The same skill |
| `hooks.json` | The same Stop hook with an absolute path, merged |
| `AGENTS.md` | The same `global.md`, with the same backup rule |

Codex runs a user-level hook only after the user trusts it. The installer never writes trust state,
so trust the goal hook once after the first install and again whenever its entry changes.

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

## Uninstalling and retiring

`install.sh --uninstall` removes the skill, the Stop registrations and an unmodified global file,
and restores the newest global-file backup. A plain install removes nothing. `install.sh
--retire-v5` deletes only the paths in the marked list in `install.sh` (the v5.1 set and what v6
installed that v7 does not), and `--dry-run` prints exactly that set first. Run it once every project
is migrated; see the
migration reference (`docs/runbooks/migrate-v5.md`, written in T8).
