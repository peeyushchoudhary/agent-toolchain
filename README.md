# SWE Agent

Public tooling for coding-agent work in Claude Code and Codex: one skill that carries an approved
goal to merged milestones, a guard that keeps private facts and secrets out of commits, and the
installer that puts both in each harness's home. No runtime, hosted service or CI.

## What installs

```bash
cd install
./install.sh --dry-run     # print every action, write nothing
./install.sh               # install or update both homes
./install.sh --uninstall   # remove it; restore global-file backups
./verify.sh                # the repository gate; its last line is the verdict
```

`install.sh` copies `install/global.md` to `~/.claude/CLAUDE.md` and `$CODEX_HOME/AGENTS.md`
(backing up a file that differs) and the `execution-methodology` skill (`goal.py`, `gate.py`,
`run.sh`, `guard.py`, `git-hooks.sh`, the reviewer prompt) to both homes. `git-hooks.sh` then
installs the guard in each clone. Details: [install/README.md](install/README.md).

## How a goal runs

1. The chief writes `docs/goals/<id>/plan.md`; the other vendor reviews it once, read-only.
2. The founder approves with the tag `goal/<id>/approved`.
3. Each task goes to a builder in its own worktree; the chief runs the gate and commits `[Tn]`.
4. `goal.py done` checks eight mechanical rows, including tree-bound gate and end-to-end receipts.
5. The other vendor reviews the milestone diff once; blocking findings close by test or removal,
   and the founder merges.

`run.sh` runs the loop unattended. Design, measured reasons and accepted risks:
[methodology.md](docs/architecture/methodology.md).

## Read next

[docs/README.md](docs/README.md) indexes every page; agents start at [AGENTS.md](AGENTS.md). A
change here passes `cd install && ./install.sh --dry-run && ./verify.sh` with `verify: PASS`.

[MIT license](LICENSE)
