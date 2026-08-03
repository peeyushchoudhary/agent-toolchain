---
name: agent-persona-factory
description: Use when a project needs its own specialist reviewers or validators beyond the thirteen base personas — derived from its PRD, architecture, and guardrails. Also use when the base personas keep missing a class of defect specific to this domain.
---

# Deriving project specialists

The thirteen base personas in `agent-personas` are domain-neutral. A health app needs someone who knows
that an unsigned vaccination schedule must not create reminders; a trading system needs someone who
knows a backtest without slippage is a lie. Those specialists cannot live in the global pool, and
re-deriving them every session is how they end up inconsistent.

This produces them from the project's own documents, once, into the repository.

## Hard constraints

- **Persona definitions stay in `<repo>/docs/agents/personas/`.** Never the global pool, never
  another project. The only companion writes are the maintained project guide
  `docs/agents/personas.md` and its direct row in `docs/agents/README.md`.
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
6. Maintain `docs/agents/personas.md` with the roster, boundaries, and sync command; link it directly
   from `docs/agents/README.md`.
7. Run `sync_personas.py --repo <repo>` and commit source, route, and generated output together.

## Choosing model and effort

Follow `agent-personas/references/roster.md`. Specialists are almost always non-editing validators,
which means `opus`/`gpt-5.6-sol` at `high`, read-only tools, and a low run count. If a proposed
specialist would *write* code, it is probably an overlay on `developer` rather than a new persona.

## Format

A specialist is a full persona — same frontmatter, same body-as-system-prompt. **It is never on
`skills/agent-personas/ROSTER`**, so unlike a base judge, nothing is derived or validated for it at
render time: `restrict_for_roster` returns unchanged for any name outside `JUDGING_PERSONA_NAMES`,
before any of its checks run, whatever this specialist's `writes:` or description claim. Read the
rules below rather than `~/.claude/docs/decisions.md`'s "Known limits" for what a specialist built from *this*
template looks like — that passage predates this template, states its conclusion unconditionally,
and as written does not describe a specialist that follows the rules below; a correction is tracked
separately.

**Nothing here validates the TOOL-POLICY KEY NAMES, which is the likely way this goes wrong.** Of
those keys specifically — `claude.tools`, `claude.disallowedTools`, and the matching `codex.*` keys —
a misspelling, such as the plausible `claude.allowedTools` (Claude Code's own key is `tools`, which
is where the name `claude.tools` below comes from), is silently dropped rather than rejected. Get
that one key name wrong and the specialist renders with no `tools:` key at all: unrestricted, and
nothing at rc 0 tells you. This is narrower than "any other key is dropped": `name` and `description`
are required and a missing or mismatched one raises `PersonaError`, and `writes` is read and checked
against a known vocabulary — it is what the warning below keys off. Only the tool-policy keys have
this silent-drop failure mode.

Declare an **allow-list**, `claude.tools`, the same shape the base judges use — not a hand-written
deny-list. A deny-list is default-open: it protects only against the names someone thought to write
down, which is how the base pool's own deny-list missed `Monitor` until a judge found it by reading
its own granted roster. An allow-list is default-closed: a tool not named is not granted.

**Nor does anything here validate the allow-list's CONTENTS**, unlike a base judge's — no empty-list
check, no overlap check, no closed vocabulary. Copy the tool names below exactly
(`Read, Grep, Glob, TodoWrite`, `+Bash` only if argued the way `test-judge` argues it); do not
extend the list with a tool name from memory. A typo renders verbatim and grants nothing while
reading like policy; a real but uncommon tool — an `mcp__…` name, `Skill`, `WebFetch` — renders
verbatim and grants exactly what it says, with nothing here to catch either.

```yaml
---
name: clinical-safety-validator
description: Use when a change touches vaccination schedules, dosing, or any clinical guidance.
writes: no
claude.model: opus
claude.effort: high
claude.tools: Read, Grep, Glob, TodoWrite
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---
```

`Read, Grep, Glob, TodoWrite` is the same allow-list five of the six base judges declare (see
`~/.claude/docs/decisions.md`, "What it grants") — a specialist that only reads, searches, and reports needs
nothing more. If a proposed specialist needs `Bash` the way `test-judge` does, argue it explicitly
in its own body the way `test-judge`'s does; do not default to granting it. `codex.sandbox:
read-only` above is self-declared for the same reason `claude.tools` is: nothing derives it for a
name off the roster, so omitting it leaves the Codex harness with no restriction at all.

**`sync_personas.py` will still warn about this specialist by name, every run — that firing condition
is unconditional on `writes: no` + off-roster and does not check whether `claude.tools` is present or
correct — but the warning's BODY is per-persona and does distinguish, so read which form you got
rather than disregarding it.** A specialist built correctly from this template gets: "In the Claude
harness its own declaration does withhold write, dispatch and shell — its own, so an edit that
removes it is checked by nothing," plus "That allow-list is closed, so a tool it does not name is not
granted." A specialist declaring no tool policy at all gets: "Still granted in the Claude harness,
because nothing withholds it: write (Write, Edit, NotebookEdit); dispatch (Agent, SendMessage); shell
(Bash, Monitor)," plus a note that an absent `claude.tools` leaves the harness granting every tool
outside the deny-list, MCP included. Those two forms read nothing alike — the first names what your
own declaration achieves, the second lists what it does not. Verify by reading the rendered
`.claude/agents/<name>.md` and, if the first form ever quietly becomes the second (for example after
`claude.tools` is renamed or dropped), that change is the signal to act on.

To refine an existing persona instead of adding one, give the file the **same name** as a base
persona and write only the delta — it is appended under a "Project-specific direction" heading and
inherits everything else.

## Regeneration

Re-run when the PRD or guardrails change materially. Specialists are committed, so treat an edit
like any other change: it goes through the same review and the same gate.
