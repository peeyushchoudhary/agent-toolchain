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
`docs.py`, `guard.py`, `git-hooks.sh`, the references) to both homes, with the builder, reviewer
and scout agent files in each harness's agents directory. `git-hooks.sh` then installs the guard in
each clone. Details: [install/README.md](install/README.md).

## How a goal runs

1. The chief writes `docs/goals/<id>/spec.md`, `design.md` when `touches:` names anything but
   `none`, and `plan.md`, whose tasks name what the builder reads; the other vendor reviews the
   design and the plan once each, read-only.
2. The founder approves from `goal.py packet --approval`'s page with the tag `goal/<id>/approved`.
3. Each task goes to a builder in its own worktree; the chief runs the gate and commits `[Tn]`.
4. `goal.py done` checks eight mechanical rows, including tree-bound gate and end-to-end receipts.
5. The other vendor reviews the milestone diff once; blocking findings close by test or removal,
   and the founder merges.

The founder's own open session is the chief and resumes from `goal.py resume`; no launcher, loop or
Stop hook runs it. `goal.py cost` records each harness's tokens and enforces nothing. Pages under
`docs/` carry frontmatter, and `docs.py` generates their index and pointer files. Design, measured
reasons and accepted risks: [methodology.md](docs/architecture/methodology.md).

## Read next

[docs/README.md](docs/README.md) indexes every page but the goals' (`docs.py index` generates the
table); agents start at [AGENTS.md](AGENTS.md). A
change here passes `cd install && ./install.sh --dry-run && ./verify.sh` with `verify: PASS`.

[MIT license](LICENSE)
