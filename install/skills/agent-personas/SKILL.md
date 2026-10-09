---
name: agent-personas
description: Use when choosing which role does a piece of goal work (builder, reviewer, security-reviewer, advisor) and at what model and effort, when editing a persona, or when generated agent files are out of sync with the persona pool.
---

# Personas

The pool is five sources in `personas/`. The execution methodology says when each role runs; a
persona says how it behaves and which model and effort it uses. Routing lives only in persona
frontmatter, so cost and quality do not depend on a choice made in the moment.

| Persona | Does | Writes |
| --- | --- | --- |
| `builder` | implements one task inside its write set | yes |
| `reviewer` | judges design, plan, boundary, data or acceptance | no |
| `security-reviewer` | judges `risk: safety` tasks | no |
| `advisor` | answers one escalated question, or sits on a council | no |
| `chief` | routing profile for the root session; never rendered | yes |

`sync_personas.py --list` prints the current models and efforts for both harnesses.

## Frontmatter

Flat `key: value` lines, parsed without YAML:

- `name`, `description`, `writes: yes|no`, and `spawnable: no` for a profile the renderer skips.
- `claude.model`, `claude.effort`, `claude.tools`, `claude.disallowedTools`; `codex.model`,
  `codex.effort`, `codex.sandbox`. These are the defaults.
- `variant.<name>.<claude|codex>.<model|effort>` overrides one default for a named variant; keys it
  does not name are inherited. The builder carries `judgement` and `mechanical`, matching a plan
  task's `builder:` field (`routine` is the default). The reviewer carries `acceptance`, the only
  place `xhigh` appears.

The driver reads routing with `routing(meta, variant)` from the script, or
`sync_personas.py --route <name> [--variant <v>]`, which prints JSON.

## Judges are read-only by construction

`JUDGING_PERSONA_NAMES` (reviewer, security-reviewer, advisor) is fixed in the renderer, and each
must declare `writes: no`; a persona cannot leave the set by editing its own file. A judge must
declare a `claude.tools` allow-list from `Read`, `Grep`, `Glob` and `TodoWrite`. The renderer adds a
fixed deny-list (write, edit, notebook, agent dispatch, messaging, monitor, worktree, task-stop and
Bash) and renders Codex with `sandbox_mode = "read-only"`. A judging source that declares a writer,
Bash, an unclassified tool or another sandbox is rejected with exit 2, never silently corrected.
See [references/roster.md](references/roster.md) for why each boundary exists.

## Render

```bash
sync_personas.py                                  # user level: ~/.claude/agents, $CODEX_HOME/agents
sync_personas.py --check                          # 0 current, 1 stale, 2 source error
sync_personas.py --scope project --repo PATH --preview --json
```

Codex agents are rendered only when the Codex home exists. Writes are atomic and never follow a
symlink, and files carrying the generated marker that no source produces are removed. Never edit a
generated agent; edit the persona and re-render.

A project may add whole personas of its own in `docs/agents/personas/<name>.md`; they render into
the project's `.claude/agents/` and `.codex/agents/`, with their tool policy as declared. A project
file named like a base persona is skipped with a warning: overlays of base personas are retired, and
the project should move that direction into its own docs or a persona with its own name.
