# Agent personas

Five persona sources are authored once in `install/skills/agent-personas/personas/` and rendered
into whichever harness is being driven. Four are spawnable; `chief` is a routing profile for the
root session and is never rendered. A session should not re-derive role, model or effort.

Implementation: `install/skills/agent-personas/`, installed to `~/.claude/skills/agent-personas/`.
The skill's own [SKILL.md](../../install/skills/agent-personas/SKILL.md) is the operating page; this
guide records the reasons.

## The roster

The table is printed from persona frontmatter by
`sync_personas.py --list --format markdown`, which is the authority if the two differ.

| Persona | Spawnable | Writes | Claude model | Claude effort | Codex model | Codex effort |
|---|---|---|---|---|---|---|
| advisor | yes | no | claude-fable-5-1 | high | gpt-6-astra | high |
| builder | yes | yes | claude-sonnet-5-5 | medium | gpt-6.1-sol | medium |
| chief | no | yes | claude-opus-5-5 | medium | gpt-6.1-sol | medium |
| reviewer | yes | no | claude-opus-5-5 | high | gpt-6.1-sol | high |
| security-reviewer | yes | no | claude-opus-5-5 | high | gpt-6.1-sol | high |

The `builder` carries two variants matching a plan task's `builder:` field: `judgement` for Opus
and high effort, and `mechanical` for the smallest models. The `reviewer` carries `acceptance`, the
only place `xhigh` appears. `sync_personas.py --route <name> [--variant <v>]` prints the routing as
JSON, which is how the driver reads it.

## Principles

**Permissions and evidence carry safety. Model and effort are workload choices.** The assignments
are engineering choices from documented capabilities and role complexity, not a measured optimum.
Routing lives only in persona frontmatter, so cost and quality do not depend on a choice made in
the moment. A per-dispatch override is an explicit recorded decision and creates no second default.

The advisor is the one role that defaults to the strongest models, because it answers a single
escalated question rather than doing sustained work. Nothing else defaults to them.

The routing follows the official [Codex model guidance](https://developers.openai.com/codex/models),
[latest-model prompting guidance](https://developers.openai.com/api/docs/guides/latest-model) and
[Claude effort guidance](https://platform.claude.com/docs/en/build-with-claude/effort). These
describe capability and effort controls; they do not establish cost guarantees. Opus 5.5 requires
Claude Code 2.1.280 or newer and Sonnet 5.5 requires 2.1.284 or newer; see the
[model configuration reference](https://code.claude.com/docs/en/model-config). An older harness is
an unmet prerequisite, not a model result.

## Judges are read-only by construction

`reviewer`, `security-reviewer` and `advisor` are the judging set. The set is fixed in the
renderer, and each member must declare `writes: no`, so a persona cannot leave it by editing its own
file. A judge declares a `claude.tools` allow-list from `Read`, `Grep`, `Glob` and `TodoWrite`; the
renderer adds a fixed deny-list and renders Codex with `sandbox_mode = "read-only"`. A judging
source that declares a writer, Bash, an unclassified tool or another sandbox is rejected with exit
2, never silently corrected.

A judge that cannot edit is a stronger guarantee than one told not to. It removes the failure where
a reviewer finds a defect and quietly patches it, so the defect is never recorded. The reasons for
each boundary are in [roster.md](../../install/skills/agent-personas/references/roster.md).

Review lenses and finding classes belong to the execution methodology, not to the persona files,
which define responsibility and restrictions only.

## Authoring and rendering

Personas are harness-neutral markdown with flat dotted frontmatter keys: `name`, `description`,
`writes`, `claude.model`, `claude.effort`, `claude.tools`, `claude.disallowedTools`, `codex.model`,
`codex.effort`, `codex.sandbox`, and `variant.<name>.<claude|codex>.<model|effort>` overrides. The
body becomes the system prompt on Claude and `developer_instructions` on Codex.

```bash
sync_personas.py --scope global --preview --json
sync_personas.py --scope global
sync_personas.py --repo PATH --scope project --preview --json
sync_personas.py --list --format markdown
sync_personas.py --check          # 0 current, 1 stale, 2 source error
```

Project scope requires `--repo`; global forbids it. Preview writes nothing. Generation is required,
not cosmetic: Claude Code's project-level agents override a same-named user agent wholesale, so
"base persona plus project direction" cannot be expressed by file placement.

Never edit `~/.claude/agents/` or `~/.codex/agents/` directly. Generated files carry a banner and the
next sync overwrites them. `install.sh` renders into a scratch home and copies file by file, so a
plain install never prunes agents it does not know.

## Project specialists

A repository may add whole personas of its own in `docs/agents/personas/<name>.md`. They render into
the project's `.claude/agents/` and `.codex/agents/`, with their tool policy as declared. A project
file named like a base persona is skipped with a warning: overlays of base personas are retired, and
the direction belongs in the project's docs or in a persona with its own name. An overlapping
specialist is worse than a missing one, because dispatch becomes ambiguous.

## Cross-vendor review

Persona dispatch stays in-harness. The one cross-harness call is the read-only reviewer at design,
plan and acceptance, made as one read-only call to the other vendor's CLI; see the [design](../architecture/lean-execution.md). Its cost and yield are recorded
in [measurements.md](../product/measurements.md).
