# Agent personas

Thirteen roles, authored once, rendered into whichever harness is being driven. A session should not
re-derive "what is a reviewer and which model should it use" every time.

Implementation: `~/.claude/skills/agent-personas/`. Specialists:
`~/.claude/skills/agent-persona-factory/`.

## The roster

| Persona | Writes | ~Runs/milestone | Claude | Codex | Effort |
|---|---|---|---|---|---|
| `scout` locate code, return paths not opinions | no | ~60 | `haiku` | `gpt-5.4-mini` | low |
| `test-judge` run the gate, report verbatim | no | ~40 | `haiku` | `gpt-5.6-luna` | low |
| `docs-steward` route, README, lessons | yes | ~10 | `sonnet` | `gpt-5.6-terra` | medium |
| `developer` bounded work in one module | yes | ~14 | `sonnet` | `gpt-5.6-terra` | medium |
| `senior-developer` judgement, cross-cutting, security | yes | ~6 | `opus` | `gpt-5.6-sol` | medium |
| `planner` what to build, in what order | no | ~3 | `fable` | `gpt-5.6-sol` | high |
| `product-steward` the WHY, scope, acceptance criteria | product specs only | not measured | `opus` | `gpt-5.6-sol` | high |
| `chief-of-staff` holds the loop, dispatches, keeps the ledger | ledger, task cards, and reports only | not measured | `opus` | `gpt-5.6-sol` | high |
| `architect` is this the right shape | design docs only | ~4 | `opus` | `gpt-5.6-sol` | high |
| `contract-architect` API, schema, migrations | yes | ~3 | `opus` | `gpt-5.6-sol` | high |
| `reviewer` independent, cannot edit | no | ~20 | `opus` | `gpt-5.6-sol` | high |
| `security-validator` consent, authz, PHI | no | ~5 | `opus` | `gpt-5.6-sol` | high |
| `acceptance` milestone judge, cannot edit | no | 1 | `opus` | `gpt-5.6-sol` | xhigh |

No reproducible run count is recorded for `product-steward` or `chief-of-staff`.

## Three principles

**Effort tracks reasoning depth. Model tracks stakes. Frequency decides where saving matters.**

Conflating importance with effort is the common mistake. `test-judge` reports whether the release
gate passed — as important as anything — but the task is "run a command and repeat the output",
which needs `low`. Its importance is handled by making it unable to edit, not by making it think
harder.

`scout` runs ~60 times per milestone and is the one place a cheap model pays for itself.
`acceptance` runs once, so `xhigh` costs nothing in aggregate.

## Judges cannot edit

`reviewer`, `security-validator`, `acceptance`, `scout`, `test-judge`, `planner` carry
`disallowedTools: Write, Edit, NotebookEdit` on Claude and `sandbox_mode = "read-only"` on Codex.

A judge that **cannot** edit is a stronger guarantee than one instructed not to, and it removes the
failure where a reviewer finds a defect and quietly patches it so the defect is never recorded.

**`architect` is the exception.** It may write so it can author ADRs, limited to
`docs/architecture/` and `docs/decisions/` — but tool restriction cannot be scoped to a path, so
that limit is an instruction, not a guarantee. It is the one persona whose boundary is soft.

## Choosing an implementation tier

`developer` takes work inside one module where the spec is complete and a pattern exists. It **stops
and escalates** rather than inferring anything about interfaces, migrations, contracts, security,
concurrency, or where code should live. `senior-developer` takes everything else.

The escalation rule is what makes the cheap tier legitimate rather than a gamble. Routing the ~70%
of genuinely bounded work to Sonnet cuts implementation from roughly **$8.00 to $4.64** per
milestone at ~20 runs.

`senior-developer` is Opus at **medium**, not high: Opus at medium is already strong, and the tier
difference is carried by the model. Raising both would double-charge for one increment of
difficulty.

## Authoring and generation

Personas are harness-neutral markdown with flat dotted frontmatter keys:

```yaml
---
name: reviewer
description: Use after code is written and before it lands…
writes: no
claude.model: opus
claude.effort: high
claude.disallowedTools: Write, Edit, NotebookEdit
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---
The body becomes the system prompt on Claude and developer_instructions on Codex.
```

```bash
sync_personas.py                      # render to ~/.claude/agents and ~/.codex/agents
sync_personas.py --repo PATH          # also merge that repo's overlays
sync_personas.py --repo PATH --check  # exit 1 when generated output is stale
sync_personas.py --list               # the roster
```

**Generation is required, not cosmetic.** Claude Code's project-level agents *override* a same-named
user agent wholesale, so "base persona plus project direction" cannot be expressed by file placement
— the project file would silently replace the base rather than extend it.

**Never edit `~/.claude/agents/` or `~/.codex/agents/` directly.** They are generated, carry a
banner saying so, and the next sync overwrites them.

`sync_personas.py` prunes: removing a persona deletes its generated files everywhere. It only
touches files carrying the banner, so a hand-written agent in the same directory survives.

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
Measured and rejected — see [decisions.md](decisions.md) and
[evidence/measurements.md](measurements.md).

## Reload behaviour

Agent definitions are picked up without restarting a session — verified when `implementer`
disappeared and `developer`/`senior-developer`/`architect` became dispatchable immediately after a
sync. Git hooks, by contrast, do need `/hooks` or a restart.
