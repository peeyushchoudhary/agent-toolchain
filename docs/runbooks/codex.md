# Codex

Codex and Claude Code share the repository layer: `AGENTS.md` and `docs/` (`CLAUDE.md` is the one
line `@AGENTS.md`). Anything both must follow belongs there or in `install/`, never in one harness's
settings, where the other silently ignores it.

## Install

When `$CODEX_HOME` (default `~/.codex`) exists, `install/install.sh` writes `install/global.md` to
`$CODEX_HOME/AGENTS.md` (the same bytes as `~/.claude/CLAUDE.md`) and the skill to
`$CODEX_HOME/skills/execution-methodology/`. `config.toml` is yours: builder subagents need an
`[agents]` block there, and Codex runs a hook only after you trust it once. Check parity with
`cd install && ./verify.sh --installed`.

## Codex as chief

`run.sh <id> --harness codex` starts each session as:

```bash
codex --ask-for-approval never exec --sandbox workspace-write "$(goal.py resume)"
```

The sandbox keeps writes in the workspace and network off, so a session cannot push.

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
