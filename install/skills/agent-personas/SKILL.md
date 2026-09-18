---
name: agent-personas
description: Use when delegating work to a subagent and you need to pick the right role, model, and effort — developer, senior-developer, reviewer, architect, scout, acceptance and the rest. Also use when adding or editing a persona, when a project needs its own specialist, or when generated agent files are out of sync with the persona pool.
---

# Select and render personas

The pool decides who acts. The `execution-methodology` skill owns stage order, lane admission,
review packets and rounds, gates, and terminal states. Persona source files define each role's
responsibilities and permissions.

## Select a role

The source pool has fourteen compatibility definitions. Ordinary selection shows active roles;
`docs-steward`, `planner`, and `contract-architect` remain renderable but their `SUPERSEDED` or
`RETIRED` description prefixes exclude them from the default list. The source descriptions are the
status authority; do not create a second status table.

```bash
sync_personas.py --list
sync_personas.py --list --include-retired
sync_personas.py --list --include-retired --format markdown
```

The Markdown form reports status, writes, model, and effort for both harnesses. Use the role source
for its complete boundary. For routine selection:

- `scout` locates code and does not judge or edit.
- `developer` implements a bounded, single-module task with a complete spec and an existing pattern;
  it stops when interface, migration, contract, security, concurrency, or placement judgement is
  required. `senior-developer` owns implementation that needs that judgement.
- `product-steward` owns product definition and documentation custody. `architect` judges system
  structure. `chief-of-staff` owns plans, scheduling, and bounded workspace state.
- `reviewer` independently falsifies design, plan, or implementation. `security-validator` owns
  consent, authorization, privacy, token, and public-capability invariants.
  `migration-validator` owns schema, migration, and backfill invariants and requires the dispatched
  parse, dry run, and contract-test evidence before review.
- `test-judge` runs declared checks and reports their real output. `acceptance` judges the sealed
  milestone against frozen criteria.

`architect`, `product-steward`, and `chief-of-staff` have instruction-level write boundaries because
tools cannot restrict writes to their owned paths. They never absorb another role's implementation.

## Authority and restrictions

Each persona's frontmatter is the model and effort authority for both harnesses. Per-dispatch
overrides and model rollout are separate, explicit decisions. Permissions, frozen criteria,
independent review, and executable gates carry safety; model choice does not replace them.

## Judge tool boundary

The judging roster in `ROSTER` is `acceptance`, `migration-validator`, `planner`, `reviewer`,
`scout`, `security-validator`, and `test-judge`. The renderer derives their Claude deny-list from
roster membership and requires an explicit Claude allow-list. Codex renders them with
`sandbox_mode = "read-only"`. A source may narrow a judge further and may not widen the derived
restriction.

On Claude, direct write and dispatch tools are withheld from every judge. On Codex, the read-only
sandbox withholds direct filesystem writes, but no dispatch-denial key exists; Codex dispatch
remains instruction-bound and unmitigated. `test-judge` alone may hold `Bash` so it can run a gate;
Claude Bash remains instruction-bound against shell writes. A write-producing gate runs against a prepared copy inside the approved nested sandbox;
the controller prepares and manifest-binds that copy, never writable source. Other judges have no shell. Judges
return findings for the controller to persist because they have no direct report-writing tool.
Never weaken this boundary to simplify a handoff.

## Preview and render

```bash
sync_personas.py --scope global --preview --json
sync_personas.py --scope global
sync_personas.py --repo PATH --scope project --preview --json
sync_personas.py --repo PATH --scope project
sync_personas.py --repo PATH --scope all --preview --json
```

Explicit global scope forbids `--repo` and never visits a project. Project scope requires `--repo`
and touches only that repository's Claude and Codex agent trees. `all` shows combined impact.
Preview, check, and apply use the same plan; preview writes nothing. Never edit generated global or
project agent files directly.

## Project overlays

Project overlays live at `docs/agents/personas/<name>.md` and are committed with both generated
harness formats. A same-name overlay appends project direction and may retune model or effort; a
roster judge may only be narrowed. A new-name overlay is never automatically a judge, regardless of
`writes: no`; create project specialists through `agent-persona-factory` so their restrictions are
explicit. Optional `covers:` values bind specialist concerns to product horizontals through
`spec_check.py`.

Every onboarded repository links a maintained persona index or records a non-empty `base-only`
reason. Project checks own project drift; global checks own the global pool. A persona runs in the
current harness only; do not dispatch across harnesses.

## Authoring route

Routine selection stops here. Read the complete
[persona authoring reference](references/roster.md) before any of these actions:

- adding or editing a base persona;
- changing roster or judge policy;
- changing model or effort defaults;
- diagnosing generation or overlay behavior;
- using historical measurements or rationale.

Use `agent-persona-factory` when a project needs a new specialist. Do not edit `ROSTER`, persona
sources, renderer policy, models, permissions, sandboxes, or generated agents as a side effect of
ordinary selection.
