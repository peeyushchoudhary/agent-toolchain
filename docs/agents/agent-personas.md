# Agent personas

Fourteen compatibility definitions are authored once and rendered into whichever harness is being
driven. Eleven are active choices. Three remain generated so old references resolve; their
descriptions reject new dispatch, while the renderer excludes them from ordinary `--list`
selection. They remain callable by explicit name. A session should not re-derive role, model,
effort or lifecycle status.

Implementation: `~/.claude/skills/agent-personas/`. Specialists:
`~/.claude/skills/agent-persona-factory/`.

## The active roster

The table is generated from the same persona frontmatter used by both harnesses. Normal `--list`
output excludes compatibility definitions; `--include-retired` shows them with explicit status.

| Persona | Status | Writes | Claude model | Claude effort | Codex model | Codex effort |
|---|---|---|---|---|---|---|
| acceptance | active | no | claude-fable-5-1 | xhigh | gpt-6-astra | xhigh |
| architect | active | yes | claude-fable-5-1 | high | gpt-6-astra | high |
| chief-of-staff | active | plans and bounded workspace state only | opus | medium | gpt-5.6-sol | medium |
| developer | active | yes | sonnet | medium | gpt-5.6-terra | medium |
| migration-validator | active | no | claude-fable-5-1 | high | gpt-6-astra | high |
| product-steward | active | product definition and documentation only | opus | high | gpt-5.6-sol | high |
| reviewer | active | no | opus | high | gpt-5.6-sol | high |
| scout | active | no | haiku | low | gpt-5.6-luna | low |
| security-validator | active | no | claude-fable-5-1 | high | gpt-6-astra | high |
| senior-developer | active | yes | opus | medium | gpt-5.6-sol | medium |
| test-judge | active | no | haiku | low | gpt-5.6-luna | low |

## Three principles

**Permissions and evidence carry safety. Model and effort are workload choices.**

The current assignments are a selective, unmeasured pilot. Scout and test execution use the least
expensive factual tier. Ordinary builders and implementation review retain their established tiers.
Architecture, security, migration and acceptance start on the flagship candidates because their
decisions propagate or are costly to reverse. Acceptance retains `xhigh`; no ordinary default uses
`max` or `ultra`.

Where a harness supports native per-dispatch overrides, the controller may use `high` for planning,
`medium` for routine product custody, and Fable 5.1/Astra at `medium` or `high` for difficult causal
work. Record the resolved model and effort. These phase choices are not extra persona definitions
or unsupported frontmatter keys. Fable 5.1 evaluation requires Claude Code 2.1.255 or newer; an
older harness is an unmet local prerequisite, not a failed model result.

## Judges cannot edit

The six active judging roles — `reviewer`, `security-validator`, `migration-validator`,
`acceptance`, `scout`, and `test-judge` — use `codex.sandbox: read-only`. On Claude, all six use the
`Read, Grep, Glob, TodoWrite` allowlist; five also disallow `Bash`. `test-judge` alone adds `Bash` so
it can run the gate. The superseded `planner` retains the read-only judge restriction for compatibility.

A judge that **cannot** edit is a stronger guarantee than one instructed not to, and it removes the
failure where a reviewer finds a defect and quietly patches it so the defect is never recorded.

The `reviewer` handles design, plan and implementation review. The canonical
[execution methodology](../../install/skills/execution-methodology/methodology.md) owns review
inputs, finding classification, correction, scoped rereview and terminal states. Persona files
define responsibility and restrictions rather than repeating that state machine.

`test-judge` can verify a gate that writes against a controller-supplied manifest-equal copy and
custom inner profile. Source remains read-only, copy writes are allowed, and network is disabled.
The judge requests approval only for the exact nested launch:
`env CODEX_HOME=<temporary-home> codex sandbox -p gate -P copy-write -C <copy> -- <exact gate argv>`.
A mismatch, sandbox failure, cached/zero/skipped run, or failed cleanup blocks the result. For
Gradle, only exact `--rerun-tasks` establishes freshness.

**Writer path boundaries are instructions.** Harness tool restrictions cannot scope a write tool to
a directory. `architect` is limited to architecture and decision documents, `chief-of-staff` to
plans and bounded workspace state, and `product-steward` to product definition and documentation.
Their path boundaries are therefore softer than the judges' structural no-write boundary.

## Choosing an implementation tier

`developer` takes work inside one module where the spec is complete and a pattern exists. It **stops
and escalates** rather than inferring anything about interfaces, migrations, contracts, security,
concurrency, or where code should live. `senior-developer` takes everything else.

The escalation rule keeps a bounded task from silently becoming an interface, migration,
concurrency or safety decision. `product-steward` owns product definition and current documentation
custody. `chief-of-staff` owns approved plans and execution state. The compatibility definitions
for `docs-steward`, `planner` and `contract-architect` name the active role that absorbed their work.

## Authoring and generation

Personas are harness-neutral markdown with flat dotted frontmatter keys:

```yaml
---
name: reviewer
description: Use before design and plan gates or after implementation…
writes: no
claude.model: opus
claude.effort: high
claude.tools: Read, Grep, Glob, TodoWrite
claude.disallowedTools: Bash
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---
The body becomes the system prompt on Claude and developer_instructions on Codex.
```

```bash
sync_personas.py --scope global --preview --json
sync_personas.py --scope global
sync_personas.py --repo PATH --scope project --preview --json
sync_personas.py --repo PATH --scope project
sync_personas.py --repo PATH --scope all --preview --json
sync_personas.py --list
sync_personas.py --list --format markdown
sync_personas.py --list --include-retired
```

Project scope requires `--repo`; global forbids it. `all` combines both. Preview writes nothing and
is write-equivalent. Management callers state scope.

**Generation is required, not cosmetic.** Claude Code's project-level agents *override* a same-named
user agent wholesale, so "base persona plus project direction" cannot be expressed by file placement
— the project file would silently replace the base rather than extend it.

**Never edit `~/.claude/agents/` or `~/.codex/agents/` directly.** They are generated, carry a
banner saying so, and the next sync overwrites them.

`sync_personas.py` prunes generated orphans only within the selected scope and preserves
hand-written files, which lack the generation banner.

## Project specialisation

A repository refines a persona or adds its own via `docs/agents/personas/<name>.md`:

- **Same name as a base persona** → appended under a "Project-specific direction" heading; may
  retune `model`/`effort`; anything omitted inherits.
- **A new name** → a project-only specialist, rendered from itself.

Overlays are committed and inside the disclosure route. Generated `.claude/agents/` and
`.codex/agents/` are committed too, with `--check` in the repo's gate — the same contract as a
generated API client.

`agent-persona-factory` derives specialists from a project's **guardrails, architecture, and PRD**,
in that order of signal strength. It writes only to `<repo>/docs/agents/personas/`, proposes before
writing, and must cite the invariant justifying each specialist. Two to four; beyond that they
overlap, and an overlapping persona is worse than a missing one because dispatch becomes ambiguous.

## No cross-harness dispatch

A persona runs in whichever harness is being driven. Nothing shells out to the other family.
One dated experiment measured it at 1.7 times the in-harness cost. See
[decisions.md](../decisions/decisions.md) and [measurements.md](../product/measurements.md).

## Reload behaviour

One historical sync observed `implementer` disappear and
`developer`/`senior-developer`/`architect` become dispatchable without restarting that session.
That observation does not prove a newly introduced model ID resolves in the current harness. Verify
the generated file and actual dispatch before treating the configured model as active. Git hooks,
by contrast, need `/hooks` or a restart.

Public assignments are candidates. Persona synchronization does not activate models.
