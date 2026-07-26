---
name: agent-personas
description: Use when delegating work to a subagent and you need to pick the right role, model, and effort — developer, senior-developer, reviewer, architect, scout, acceptance and the rest. Also use when adding or editing a persona, when a project needs its own specialist, or when generated agent files are out of sync with the persona pool.
---

# The persona pool

Eleven roles, authored once, rendered into whichever harness you are driving. The point is that a
session should not re-derive "what is a reviewer and which model should it use" every time.

## The roster

| Persona | Writes | ~Runs/milestone | Claude | Codex | Effort |
|---|---|---|---|---|---|
| `scout` locate code, return paths not opinions | no | ~60 | `haiku` | `gpt-5.4-mini` | low |
| `test-judge` run the gate, report verbatim | no | ~40 | `haiku` | `gpt-5.6-luna` | low |
| `docs-steward` route, README, lessons | yes | ~10 | `sonnet` | `gpt-5.6-terra` | medium |
| `developer` bounded work in one module | yes | ~14 | `sonnet` | `gpt-5.6-terra` | medium |
| `senior-developer` judgement, cross-cutting, security | yes | ~6 | `opus` | `gpt-5.6-sol` | medium |
| `planner` what to build, in what order | no | ~3 | `fable` | `gpt-5.6-sol` | high |
| `architect` is this the right shape | design docs only | ~4 | `opus` | `gpt-5.6-sol` | high |
| `contract-architect` API, schema, migrations | yes | ~3 | `opus` | `gpt-5.6-sol` | high |
| `reviewer` independent, cannot edit | no | ~20 | `opus` | `gpt-5.6-sol` | high |
| `security-validator` consent, authz, PHI | no | ~5 | `opus` | `gpt-5.6-sol` | high |
| `acceptance` milestone judge, cannot edit | no | 1 | `opus` | `gpt-5.6-sol` | xhigh |

**Pick the implementation tier by the task, not by feel.** `developer` takes work inside one module
where the spec is complete and a pattern exists; it **stops and escalates** rather than inferring
anything about interfaces, migrations, contracts, security, concurrency, or where code should live.
`senior-developer` takes everything else. A cheap tier is only safe because it refuses to improvise.

`architect` may write, but only under `docs/architecture/` and `docs/decisions/`. Tool restriction
cannot be scoped to a path, so that limit lives in its body as an instruction rather than a
guarantee — it is the one persona whose boundary is not structurally enforced.

## Why these models and efforts

**Effort tracks reasoning depth, not importance.** Importance is already handled by model choice and
by tool restriction. `test-judge` runs a command and repeats the output — that is `low` however much
the result matters. `acceptance` runs once per milestone, so `xhigh` costs nothing in aggregate.

**Frequency drives the cheap end.** `scout` runs ~60 times per milestone; it is the one place a
cheap model pays for itself. `acceptance` runs once.

**Splitting implementation by tier is where the money is.** Routing the ~70% of tasks that are
genuinely bounded to `developer` (sonnet/terra) instead of opus cuts implementation cost by about
40% — roughly $8.00 to $4.64 per milestone at ~20 runs.

**Measured anchor:** an in-harness `opus` review of a small class, grounded in real repo files, cost
about $0.21 (27K input, 3K output, 7 tool calls, 80s). Reviews dominate the persona budget at ~20
runs; a milestone lands around $4–5 total.

Model choices follow published benchmarks: Opus 5 scores 79.2 on SWE-bench Pro against Sonnet 5's
63.2 for 2.5× the price, and Anthropic's own cost-per-task data puts Opus ahead on accuracy per
dollar above medium effort — so `senior-developer` is Opus and `developer` is Sonnet. Fable 5 buys +0.8 over Opus 5 for double the
input price, which is why it appears only in `planner`. Full rationale in
[references/roster.md](references/roster.md).

## Judges cannot edit

`reviewer`, `security-validator`, `acceptance`, `scout`, `test-judge` and `planner` carry
`disallowedTools: Write, Edit, NotebookEdit` on Claude and `sandbox_mode = "read-only"` on Codex.

A judge that **cannot** edit is a stronger guarantee than one instructed not to. It also removes the
failure where a reviewer finds a defect and quietly patches it, so the defect never gets recorded.

## Authoring and generation

Personas live in `personas/<name>.md` — harness-neutral, with flat dotted frontmatter keys:

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
sync_personas.py                      # render the pool to ~/.claude/agents and ~/.codex/agents
sync_personas.py --repo PATH          # also merge that repo's overlays
sync_personas.py --repo PATH --check  # exit 1 when generated output is stale
sync_personas.py --list               # the roster
```

**Never edit `~/.claude/agents/` or `~/.codex/agents/` directly.** They are generated and carry a
banner saying so; the next sync overwrites them.

## Project specialisation

A repository can refine a persona or add its own, via `docs/agents/personas/<name>.md`:

- **Same name as a base persona** → the overlay is appended under a "Project-specific direction"
  heading, and may retune `model`/`effort`. Anything it omits inherits.
- **A new name** → a project-only specialist, rendered from itself.

Overlays are committed, inside the disclosure route, and readable by both harnesses. The generated
`.claude/agents/` and `.codex/agents/` are committed too, with `--check` in the repo's gate — the
same contract as a generated API client.

Generation is required, not cosmetic: Claude Code's project-level agents **override** a same-named
user agent wholesale, so "base plus project direction" cannot be expressed by file placement alone.

To derive specialists from a project's own documents, use the `agent-persona-factory` skill.

## No cross-harness dispatch

A persona runs in whichever harness you are driving. Nothing shells out to the other family.

That was measured and rejected: a quality-matched cross-harness review cost $0.367 against $0.212
in-harness — about 1.7× — because a cold subprocess shares no context with the parent and re-reads
source it already has, on top of a ~23K-token system-prompt floor per invocation.
