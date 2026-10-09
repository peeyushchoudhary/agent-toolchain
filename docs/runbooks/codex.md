---
summary: Codex beside Claude Code: the repository layer both share, what the installer writes into `$CODEX_HOME`, how a Codex session runs as the chief (the sandbox, the git-level push denial and its limits; the launcher section below is superseded by D30 and leaves in S-2 T9), and the exact `codex exec` call that runs the read-only review when Claude is the chief.
read-when: Running Codex as the chief or as the other vendor's reviewer
covers: []
last-verified: 2026-10-09
---

# Codex

Codex and Claude Code share the repository layer: `AGENTS.md` and `docs/` (`CLAUDE.md` is the one
line `@AGENTS.md`). Anything both must follow belongs there or in `install/`, never in one harness's
settings, where the other silently ignores it.

## Install

When `$CODEX_HOME` (default `~/.codex`) exists, `install/install.sh` writes `install/global.md` to
`$CODEX_HOME/AGENTS.md` (the same bytes as `~/.claude/CLAUDE.md`) and the skill to
`$CODEX_HOME/skills/execution-methodology/`. It does not touch `config.toml`, and it registers no
hook. Check parity with `cd install && ./verify.sh --installed`.

It also installs the three custom agents, `builder.toml`, `reviewer.toml` and `scout.toml`, into
`$CODEX_HOME/agents/` (the Claude side gets the `.md` files in `~/.claude/agents/`). Each carries the
same body as its `.md` file, the model and effort from `references/roles.md` and a sandbox mode, and
a marker line: uninstall removes a marked file only while it is unchanged, and a same-named file
without the marker is never touched. Your own Codex session loads `$CODEX_HOME/agents/` itself, so no
per-session flag is needed; that a session selects the installed agents is checked live in the
pilot's first goal. The review call below passes the reviewer prompt itself and does not depend on
the installed file.

A builder needs its own worktree. On the Claude side, a subagent with `isolation: worktree` branches
from the default branch unless `~/.claude/settings.json` sets `"worktree": {"baseRef": "head"}`;
set it so builders branch from the chief's HEAD (the installer only reminds you; it writes no
settings file). On the Codex side, `codex exec --worktree` (present in 0.160.0) runs the builder in a
new managed worktree and is the first choice; otherwise the Codex chief runs `git worktree add` and
names the path in the packet.

## Codex as chief

`run.sh <id> --harness codex` starts each session as:

```bash
codex --ask-for-approval never exec --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=false \
  -c 'sandbox_workspace_write.writable_roots=["<repo>/.git"]' \
  -c 'hooks.Stop=[{hooks=[{type="command",command="python3 <skill>/scripts/goal.py --goal <id> stop-hook"}]}]' \
  --dangerously-bypass-hook-trust --ignore-user-config --ignore-rules \
  -C <repo> --json "<goal.py resume prompt>" < /dev/null
```

The session loads neither your `config.toml` nor any execpolicy `.rules` file, so nothing there
widens or narrows it; no `[agents]` block is needed, because builder subagents (`multi_agent`) are on
by default. The Stop hook is registered for that session only and runs without prior trust
(`--dangerously-bypass-hook-trust`), so you trust nothing once.

The sandbox keeps writes in the workspace and `.git`, with the network off. That alone does not stop
a push: git's local transport to a path remote needs no network. `run.sh` therefore denies pushes in
the repository's own git config for the run's duration and restores it at exit: `core.hooksPath`
points at a copy of the repository's hooks whose `pre-push` refuses, and
`url.run-sh-denies-push://.pushInsteadOf` rewrites every push URL to a transport that does not exist,
which `--no-verify` does not skip. Codex offers no per-session execpolicy rule (no flag or `-c` key
names a rules file), so this git-level denial is the mechanism. A session that edits `.git/config`
can undo it; it stops a push, not a hostile session. Claude sessions get the same denial, behind
their `Bash(git push *)` deny rule.

## Codex as the other vendor's reviewer

When Claude is the chief, the design, plan and merge reviews run the
[reviewer prompt](../../install/skills/execution-methodology/agents/reviewer.md) through:

```bash
codex exec -s read-only --ignore-user-config --ignore-rules \
  -m <model> -c model_reasoning_effort=<effort> --json -C <dir> "<packet>" < /dev/null
```

`-m` names the reviewing model (Astra in S-1). The `--ignore` flags keep user servers and hooks out
of the judge; outside a git repository add `--skip-git-repo-check`. Each call spends about
23K input tokens on the base prompt. The chief saves the output, already in the `review.md` format,
to `.runs/<id>/review.md`.
