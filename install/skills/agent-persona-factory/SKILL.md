---
name: agent-persona-factory
description: Use when a project needs its own specialist reviewers or validators beyond the nine base personas — derived from its PRD, architecture, and guardrails. Also use when the base personas keep missing a class of defect specific to this domain.
---

# Deriving project specialists

The nine base personas in `agent-personas` are domain-neutral. A health app needs someone who knows
that an unsigned vaccination schedule must not create reminders; a trading system needs someone who
knows a backtest without slippage is a lie. Those specialists cannot live in the global pool, and
re-deriving them every session is how they end up inconsistent.

This produces them from the project's own documents, once, into the repository.

## Hard constraints

- **Writes only to `<repo>/docs/agents/personas/`.** Never the global pool, never another project.
- **Propose before writing.** Show the roster you intend to create and get agreement. A specialist
  nobody asked for is one more file that drifts.
- **Derive, never invent.** Every specialist must trace to a specific invariant, acceptance
  criterion, or guardrail in this repository. If you cannot cite the line that justifies it, it does
  not get created.
- **Two to four specialists.** Beyond that they overlap, and an overlapping persona is worse than a
  missing one because dispatch becomes ambiguous.

## Inputs, in this order

1. **Guardrails** — `docs/agents/guardrails.md` or equivalent. The invariants that must not break
   are the strongest signal, because each one implies someone whose job is to check it.
2. **Architecture** — `docs/agents/architecture.md` and `docs/architecture/`. Tells you where the
   dangerous seams are.
3. **PRD** — `docs/product/`. Acceptance criteria that carry clinical, legal, or financial
   consequence usually name a specialist directly.

Read the code when a document makes a claim you cannot verify. A specialist built on a stale doc
inherits the staleness.

## Method

1. Read the three inputs. List every invariant that, if broken, would be expensive and would not be
   caught by a general reviewer.
2. Cluster them. Each cluster that needs a distinct *way of thinking* — not just a distinct file —
   is a candidate specialist.
3. Discard candidates already covered. `security-validator` covers consent, authorization, and PHI
   generally; a specialist earns its place only by knowing something domain-specific it does not.
4. Propose the roster: name, what it checks, which invariant justifies it, model and effort.
5. On agreement, write each to `docs/agents/personas/<name>.md` in the persona format.
6. Run `sync_personas.py --repo <repo>` and commit source and generated output together.

## Choosing model and effort

Follow `agent-personas/references/roster.md`. Specialists are almost always non-editing validators,
which means `opus`/`gpt-5.6-sol` at `high`, read-only tools, and a low run count. If a proposed
specialist would *write* code, it is probably an overlay on `implementer` rather than a new persona.

## Format

A specialist is a full persona — same frontmatter, same body-as-system-prompt:

```yaml
---
name: clinical-safety-validator
description: Use when a change touches vaccination schedules, dosing, or any clinical guidance.
writes: no
claude.model: opus
claude.effort: high
claude.disallowedTools: Write, Edit, NotebookEdit
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---
```

To refine an existing persona instead of adding one, give the file the **same name** as a base
persona and write only the delta — it is appended under a "Project-specific direction" heading and
inherits everything else.

## Regeneration

Re-run when the PRD or guardrails change materially. Specialists are committed, so treat an edit
like any other change: it goes through the same review and the same gate.
