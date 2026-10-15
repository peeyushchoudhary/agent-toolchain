---
summary: Codex beside Claude Code: the repository layer both share, what the installer writes into `$CODEX_HOME`, how the founder's own Codex session runs as the chief (`goal.py resume`, the pre-push guard, `codex exec --worktree` for builders), and `goal.py review`, which runs the read-only cross-vendor review with the exact model and effort.
read-when: Running Codex as the chief or as the other vendor's reviewer
covers: []
last-verified: 2026-10-15
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

Your own open Codex session is the chief; nothing launches or restarts it, and no hook keeps it
going. Ask it to run the goal and it starts from `goal.py resume`, which prints the next task, the
milestone state and the tail of `.runs/<id>/progress.md`; it stops when `goal.py done` prints DONE.
Pushes go through the guard's `pre-push` hook, which `git-hooks.sh` installs in each clone
([github.md](github.md#the-guard)). Each builder runs in its own worktree through
`codex exec --worktree`, as above, so its staged diff never shares the chief's index.

## Codex as the other vendor's reviewer

When Claude is the chief, the design, plan and merge reviews run through
`goal.py review --chief claude --stage <design|plan|merge>`, never a hand-built call. It sends the
[reviewer prompt](../../install/skills/execution-methodology/agents/reviewer.md) and the stage's
packet to:

```bash
codex exec -s read-only --ignore-user-config --ignore-rules \
  -m gpt-6-astra -c model_reasoning_effort=high --json -C <dir> -o <raw> "<prompt>" < /dev/null
```

`codex exec` reads no agent file, so without `-m` it falls back to Codex's default model; that is
why the call is built by `goal.py`, whose model table `roles.md` states. The `--ignore` flags keep
user servers and hooks out of the judge. Each call spends about 23K input tokens on the base prompt.
`goal.py review` writes the review, its reviewer line naming the model, to `.runs/<id>/review.md`
for merge, and `goal.py done` refuses one from any other model. When Codex is the chief, the same
command with `--chief codex` runs `claude -p --model claude-opus-5-5 --effort high` with only
Read, Grep and Glob.
