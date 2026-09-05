---
name: agent-personas
description: Use when delegating work to a subagent and you need to pick the right role, model, and effort — developer, senior-developer, reviewer, architect, scout, acceptance and the rest. Also use when adding or editing a persona, when a project needs its own specialist, or when generated agent files are out of sync with the persona pool.
---

# The persona pool

Fourteen roles, authored once, rendered into whichever harness you are driving. The point is that a
session should not re-derive "what is a reviewer and which model should it use" every time.

The pool decides *who*. The order they run in, and what must be true to leave a stage, belongs to
the `execution-methodology` skill.

## The roster

The source pool contains fourteen compatibility definitions. Ordinary selection shows only active
roles; `docs-steward`, `planner`, and `contract-architect` remain renderable so old references keep
working, but their existing `SUPERSEDED` or `RETIRED` description prefixes exclude them from the
default list. No separate status registry exists.

Generate the current roster from those sources rather than maintaining another table here:

```bash
sync_personas.py --list
sync_personas.py --list --include-retired
sync_personas.py --list --include-retired --format markdown
```

The Markdown form includes status, writes, and the model and effort for both harnesses.

**`migration-validator` is the newest seat and it is cast EARLY.** It was added because the pool had
no owner for the data plane, and the gap was measured rather than felt: across four repositories,
three reviews named `syntax`, `nullcheck` and `blocker` were improvised by three personas that own
no schema, all landed on ONE 386-line migration, all at implementation time, and all three blocked.
Two of the three were work a TOOL does for free — two missing closing parentheses, and a `CHECK`
that evaluates to UNKNOWN — so the persona's first rule is that it **refuses to review** until a
parse, a dry run and the migration's contract test are attached to the dispatch. It holds no shell,
which is what makes that rule enforceable instead of advisory. It judges the half a parser cannot
reach: which arms of a predicate are *meant* to admit a `NULL`, a trigger attached to more tables
than it was written for, a constraint that is true only of rows written after it. A seat that
absorbs work a parser does for free is over-engineering wearing a new hat, and this one says so in
its own body.

**Pick the implementation tier by the task, not by feel.** `developer` takes work inside one module
where the spec is complete and a pattern exists; it **stops and escalates** rather than inferring
anything about interfaces, migrations, contracts, security, concurrency, or where code should live.
`senior-developer` takes everything else. A cheap tier is only safe because it refuses to improvise.

**Three personas have a write boundary that is an instruction, not a guarantee.** `architect` writes
only under `docs/architecture/` and `docs/decisions/`; `product-steward` owns product definition and
routine documentation custody; `chief-of-staff` owns plans and bounded workspace state. Tool restriction cannot be
scoped to a path, so each limit lives in the persona's body.

`chief-of-staff` is the one to watch. Its boundary erodes in a predictable way: a review returns a
one-line fix, dispatching feels like overhead, and the orchestrator patches it directly — producing
a change nobody reviewed, recorded nowhere but its own context. Its body says this explicitly
because saying it is the only enforcement available.

## Model and effort defaults

The four model and effort values in each persona's frontmatter remain the source authority. They
are frozen for this reconciliation; reassessment, per-dispatch overrides, and rollout are separate
decisions. Permissions, frozen criteria, independent review, and executable gates carry the safety
guarantees regardless of model. Do not add phase keys to persona frontmatter.

The dated rationale and earlier measurements are retained as history in
[references/roster.md](references/roster.md); they are not current model evidence.

## Judges cannot edit

`acceptance`, `migration-validator`, `planner`, `reviewer`, `scout`, `security-validator` and
`test-judge` — the roster
pinned in `skills/agent-personas/ROSTER` — are denied a **derived core** of tools on Claude
(`JUDGE_DENIED_TOOLS` in `sync_personas.py` — write and dispatch, and more besides: it also carries
`Monitor`, `EnterWorktree`, `ExitWorktree` and `TaskStop`, so read the name rather than this
paraphrase) and run `sandbox_mode = "read-only"` on Codex. The derived core itself is never
hand-written and can never be shrunk per source — but a source MAY add to it locally, and that is a
supported mechanism, not a hole: `sync_personas.py` merges whatever a source declares in
`claude.disallowedTools` with the derived core rather than rejecting it, and six of the seven judging
sources use exactly this to deny `Bash` locally (the worked example below is one of them — its
`claude.disallowedTools: Bash` line is a local addition, not part of the derived core). For the
current core names and the argument behind each one, read `~/.claude/docs/decisions.md`'s "What it withholds",
or `JUDGE_DENIED_TOOLS` in `sync_personas.py` for the enforced value — not this paragraph, which will
drift again the next time either does. The mirror mistake is real, and only one thing catches it: the
renderer raises nothing at render time if a source's local `Bash` line is deleted — `Bash` is not
part of the derived core, so nothing is contradicted — and session-start `--check` stays clean, since
the check that would need to run is not one `--check` performs. Only
`test_roster_personas_disallow_bash_except_the_sanctioned_exception` in the INSTALLED suite at
`~/.claude/skills/agent-personas/tests/test_repo_sync.py` catches it, and nothing runs that suite
automatically.

**That suite is deliberately not vendored, and this paragraph is cited by absolute path for exactly
that reason.** Three of its tests resolve the human record at `<skill>/../../docs/`, a path that
exists in the installed layout and not in a vendored one, so a published copy of the suite would
fail where it sits. A published copy of *this file* still points at a suite that exists — on the
machine, where it runs — instead of at a relative path that resolves to nothing, or worse, to a
different document that happens to share a name.

What each judge additionally **holds** is a separate, mandatory allow-list: `claude.tools`. Absence
of one on a roster member is rejected, not defaulted to "everything the deny-list didn't name". Six
judges declare `Read, Grep, Glob, TodoWrite`; `test-judge` adds `Bash` to its own allow-list instead —
the one sanctioned exception, so it is **not** among the judges denied a shell below — see
`~/.claude/docs/decisions.md`'s "Exception denied: `test-judge` keeps `Bash`, loses `Agent`" for the argument.
Current names, same caveat as above: `~/.claude/docs/decisions.md`'s "What it grants".

A judge that **cannot** edit is a stronger guarantee than one instructed not to. It also removes the
failure where a reviewer finds a defect and quietly patches it, so the defect never gets recorded.

**`test-judge`'s `Bash` is the one sanctioned exception, and it is narrow.** Running a gate requires
a shell; without one the persona was assigned a job it could not do, and in practice it chained to a
sub-subagent rather than say so. `test-judge` is the only judge holding a shell — every other judge
denies `Bash` (six of them locally, as above), and every dispatch tool stays denied on all seven, so
`test-judge` still cannot author a fix or hand the work to something that can. The residual — edits
through shell redirection — is covered by instruction rather than restriction, which is weaker, and
its body says so plainly. Codex remains `read-only`. A gate that writes therefore runs only against
a controller-prepared, manifest-bound standalone copy inside a nested sandbox; the source referent
is never made writable to the judge. The controller supplies the copy and custom inner profile. The
judge requests approval for the **exact sandbox-launch** command only; the approved nested launch is
`env CODEX_HOME=<temporary-home> codex sandbox -p gate -P copy-write -C <copy> -- <exact gate argv>`.
Approval moves only the launcher outside the outer read-only boundary and never runs the gate
unsandboxed. The launcher immediately enters the inner profile, which grants source read, copy
write, and network disabled. Manifest mismatch, ambiguous inputs, nested-sandbox failure,
cached/zero/skipped execution, or failed cleanup blocks the gate. Exact `--rerun-tasks` is the only
Gradle freshness evidence; `cleanTest` never qualifies.

A consequence worth stating because it looks like an oversight: **judges cannot write their own
reports.** Do not resolve that by granting a write tool. The judge returns its findings and the
orchestrator persists them — one read per review is the price of the guarantee. The installed suite
at `~/.claude/skills/agent-personas/tests/test_repo_sync.py` enforces both halves, with the exemption
named rather than inferred.

## Authoring and generation

**The base pool is a fixed set of fourteen**, pinned by `BASE_PERSONA_NAMES` in `sync_personas.py`:
a file dropped into `personas/<name>.md` under any other name is rejected at exit 2 (`base persona
pool must contain exactly the canonical 14 (unexpected: <name>)`) however correct its frontmatter is.
This location is for editing one of the fourteen — never for adding a new specialist. A new
specialist goes through `agent-persona-factory` into a project overlay
(`docs/agents/personas/<name>.md`; see "Project specialisation" below).

Each source is harness-neutral, with flat dotted frontmatter keys. A judging-roster member (see
"Judges cannot edit" above) must additionally declare `claude.tools`, its allow-list — absence is
rejected. The deny-list's derived core comes from roster membership alone, never per source; a
source may still add a local extra to it (`claude.disallowedTools`, merged rather than replaced —
see "Judges cannot edit").

Persona bodies define responsibilities and permissions. The `execution-methodology` skill owns
stage order, lane admission, review packets and rounds, gates, and terminal states. Review mode
defaults to Implementation unless Design or Plan is explicitly named; the reviewer body preserves
the mode-specific examination and no-edit rules.

`reviewer`'s own source is the worked example, copied verbatim rather than reconstructed from
memory — when authoring a new persona, copy an existing source file, not a prose rendering of one:

```yaml
---
name: reviewer
description: Use before design and plan gates or after implementation, to independently falsify the artifact against its frozen criteria and invariants.
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

**This is a judging-roster member's shape, and copying it is not what protects a project judge.**
`reviewer` is on `skills/agent-personas/ROSTER`, so `restrict_for_roster` runs on it at render time:
it completes `claude.disallowedTools` by merging in the derived core (no vocabulary check applies to
this half — a typo'd tool name there renders as a dead entry, not a rejection), and it validates
`claude.tools` outright — mandatory, non-empty, no overlap with the deny-list, closed vocabulary. A
project specialist — a new name under `docs/agents/personas/`, the shape `agent-persona-factory`
produces — is never on that roster, so **none** of this runs for it: cloning only the
`claude.disallowedTools: Bash` line above, or omitting `claude.tools`, renders exactly that and
nothing else, holding every tool the render pipeline itself doesn't drop. See
`agent-persona-factory/SKILL.md` for the template that shape actually needs — read there rather than
`~/.claude/docs/decisions.md`'s "Known limits" for what a *conformant* specialist looks like; that passage
predates this template and, as written, does not describe it (a correction is tracked separately).

```bash
sync_personas.py --scope global --preview --json
sync_personas.py --scope global
sync_personas.py --repo PATH --scope project --preview --json
sync_personas.py --repo PATH --scope project
sync_personas.py --repo PATH --scope all --preview --json
sync_personas.py --list
sync_personas.py --list --include-retired
sync_personas.py --list --format markdown
```

Explicit `project` scope requires `--repo` and touches only that repository's Claude and Codex
agent trees. Explicit `global` scope forbids `--repo` and never visits a project. `all` makes
the combined impact visible. Preview, check and apply consume the same plan; `--preview --json`
writes nothing and reports every create, update and delete before authorization. Management
callers always select a scope. The omitted-scope CLI keeps its historical compatibility behavior
for existing callers.

**Never edit `~/.claude/agents/` or `~/.codex/agents/` directly.** They are generated and carry a
banner saying so; the next sync overwrites them.

## Project specialisation

A repository can refine a persona or add its own, via `docs/agents/personas/<name>.md`:

- **Same name as a base persona** → the overlay is appended under a "Project-specific direction"
  heading, and may retune `model`/`effort`. Anything it omits inherits. If the base name is on the
  judging roster, `restrict_for_roster` still runs on the merged result — an overlay may narrow a
  judge's tools and may never widen them.
- **A new name** → a project-only specialist, rendered from itself, and **never on the judging
  roster no matter what it claims about itself.** `restrict_for_roster` only ever runs for a name in
  `JUDGING_PERSONA_NAMES`, so a new-name specialist gets nothing derived — no mandatory allow-list,
  no derived deny-list — however plainly its `writes: no` or its description says it only judges.
  Use `agent-persona-factory`, which authors this case correctly by hand.

Overlays are committed, inside the disclosure route, and readable by both harnesses. The generated
`.claude/agents/` and `.codex/agents/` are committed too, with `--check` in the repo's gate — the
same contract as a generated API client.

### `covers:` — reaching the product definition, not just the review

A project-only specialist IS a domain invariant with a reader attached. Measured across four real
repositories carrying 15 of them: they are cited **100 times in reviews, 83 in task cards, 7 in
plans, 5 in feature specs, and 0 in a PRD or a milestone.** The invariant lands after the product
has already been defined, which is the most expensive moment to discover it.

One optional key in the overlay's front matter fixes that:

```yml
covers: [tenancy, personal data]
```

The values name horizontal concerns — tenancy, authorization, audit, money handling, personal data,
retention, accessibility, localisation, runtime cost, or any label the project's own specs use in
their `## Horizontals` section. `spec_check.py` rule F then requires this persona in a spec's,
PRD's or milestone's `reviewed_by:` whenever that document's own horizontals say it MOVES a concern
this persona owns, and rule F4 fails a `covers:` that matches nothing in the corpus so the binding
cannot go quietly inert. `spec_check.py --personas` prints the pool and what it could match.

The key is OPTIONAL and no base persona carries it: a base persona owns a stage, not a domain. The
cost is one line per project specialist, once.

Every onboarded repository records the decision:

- Persona sources require a maintained `docs/agents/personas.md` linked directly from
  `docs/agents/README.md`.
- If the shared base pool is sufficient, the index carries
  `<!-- agent-personas: {"mode":"base-only","reason":"..."} -->` with a real reason.

Missing both is warned. A `base-only` decision does not skip repository drift checking:
`sync_personas.py --repo PATH --scope project --check` also catches generated project agents left
behind after the last source is removed. Repository checks verify both committed harness formats
without depending on whether Codex is installed and do not fail because the machine-global pool
drifted; `sync_personas.py --scope global --check` owns global drift.

Generation is required, not cosmetic: Claude Code's project-level agents **override** a same-named
user agent wholesale, so "base plus project direction" cannot be expressed by file placement alone.

To derive specialists from a project's own documents, use the `agent-persona-factory` skill.

## No cross-harness dispatch

A persona runs in whichever harness you are driving. Nothing shells out to the other family. The
dated comparison that led to this rule remains in the historical roster reference; it is not a
current cost or quality claim.
