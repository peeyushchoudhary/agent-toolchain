# Execution methodology

This common core states the invariants shared by every stage. The skill entrypoint routes each
reader to the existing reference that owns its procedure. Personas say who may act; the methodology
says what must be true before work advances.

## Principles

The sections below are the mandatory common invariants. Stage procedures remain in the single
references selected by the skill entrypoint.

## Runtime and outcome

Use the repository-approved runtime in `docs/agents/execution/runtime.json`, including an older
approved bundle. A newer global source or candidate never replaces that binding. Resolve commands
and references through the inventory's verified `bundle_root`; do not fall back to global source.
At controller entry and after restart, run the bound `sync_methodology.py --repo <repo>
--status-json`. Governed adopted execution requires `state=current` and `ready=true`. Missing,
changed, or unverified inputs stop dependent work. Ordinary execution does not invoke maintenance,
model research or upgrades.

Execution is goal-bound. Every dispatch names the approved outcome through a criterion or invariant
and an observable delta. The PRD, spec, design, and plan are the floor and ceiling. Preferences,
speculative hardening, and invented requirements do not block delivery.

Before dependent design and planning close, product definition closes the actors, problem,
outcome, priorities, non-goals, literal journeys and states, shared constraints, dependencies,
existing consumers, and local verification prerequisites. Walk the founder through the literal
journeys, consequential alternatives, and contradictions; resolve the choices in their owning
artifacts before freezing dependent work. Where product UX applies, a separate
founder-approved UX journey supplies its authoritative artifact and implementation inputs.

## Chain, gates, and authority

The chain is PRD → feature spec → design → plan → tasks → implementation → task validation and
review → commit → milestone validation → acceptance → merge.

Three founder gates control it:

- Gate 1, design, approves outcome, scope, invariants, and structural decisions.
- Gate 2, plan, approves the whole bounded milestone execution: decomposition, dependencies, write
  boundaries, validation, lane assignment, permitted operations, routine recovery, resource
  envelope, local commit authority, and any separately authorized external-action grants. The plan
  covers the coherent milestone batch, including every member feature's required tasks.
- Gate 3, merge, considers the sealed milestone, acceptance verdict, honest documentation, and
  observed process evidence.

The founder is the approval authority at all three gates; the controller is the reader that records
and applies the explicit decision. Missing approval is never inferred from silence or elapsed time.
Technical corrections in Design, Plan, and Implementation use the cause-based recovery in
`references/execution-loop.md`. Initial design/UX and plan approvals remain founder gates;
a substantive new design or plan choice returns to its owning founder gate.

A gate pass by itself authorizes no deployment, provider activation, production write, push, PR, or
merge. Each external action requires its own explicit grant, recorded with its scope.
Within Gate 2 authority the controller may dispatch, resume, retry recoverable tool inputs, repair
inside an existing write boundary, and integrate where the plan permits. This does not weaken any
safety, review, evidence, or acceptance stop. Necessary companion paths and equal or stronger
proof amendments use the independently confirmed procedures in `references/execution-loop.md`;
neither is unilateral controller authority. A new outcome, durable interface, material scope
expansion, safety-policy decision, missing permission, or exhausted required resource returns to
its owning authority.
Only when Gate 2 explicitly grants local commit authority may the controller commit; otherwise it
must preserve the accepted slice, then checkpoint and pause before any further selection.

That bounded authority persists across sessions and checkpoints without arbitrary time expiry.
At resume and before external action, recheck its scope, frozen inputs, permissions, resources,
and revocation state. Ask again only for a material scope or safety change, revocation, or an
external action outside the approved grant.

Unless Gate 2 records another envelope, execution continues through approved completion, with at
most two file-disjoint builders and one heavy local gate at a time. An explicit founder deadline
or actual exhausted quota, disk, memory, credentials, or required service stops affected work;
elapsed hours, sleep, compaction, checkpoints, and session changes do not expire authority.
Concurrent writers use distinct named task working trees and one integration owner; solo execution
may use the shared checkout. Conflicting service or runtime state
is serialized through the existing plan `serialises:` relation. Numeric review spend triggers
technical diagnosis, not a founder transaction by itself, and never weakens quality, validation,
review, safety, evidence, or acceptance.

## Safety, lanes, and judgement

A builder never approves their own work. Judges are fresh and structurally read-only;
`test-judge` retains only the shell access needed to run a gate. One semantic `reviewer` owns the
task review, with at most one relevant specialist for a distinct invariant and
`security-validator` for a safety surface. An unresolved semantic defect is INCOMPLETE. Safety
findings block acceptance and integration until resolved. Restore an unchanged approved
security/privacy invariant through its technical owner, Full lane, and independent security
review; changing that invariant or promise requires founder approval. Material scope changes and
new durable boundaries return to their owning authority. Same-cause recurrence changes the
diagnosis or approach through the existing A/B/C recovery, never a budget waiver.

Implementation review is one initial full task-diff review and, after a valid correction, one scoped
correction review per causal approach with independent executable confirmation. Its procedure and packet are
owned by `references/execution-loop.md`, Step 5. On a frozen candidate and relevant inputs,
semantic review may overlap independent focused/area validation. Integration requires both PASS
verdicts, the Full lane strict post check, and a recheck of the admitted bytes and inputs.

Before repair, classify every finding as a current-scope defect, harness defect, pre-existing
defect, invalid frozen assumption, new outcome or claim, external fact, evidence defect, safety
finding, or scope change. Route technical defects to the existing technical or proof owner first.
A safety label alone does not require founder permission; an unchanged policy repair retains its
Full-lane and independent security checks. Existing paths remain binding until a permitted
companion-path amendment passes; other findings go to their named authority. Implementation review
mechanics remain in `references/execution-loop.md`, Step 5.

The exact pre-gate contract is a fresh, isolated, read-only `reviewer` with only named artifact
paths, never the author conversation. `PASS` is valid; there is no finding quota. A blocker names
its criterion or invariant, a reachable trigger or state sequence, the observable consequence,
artifact evidence, severity, and the smallest correction or human decision. The author receives
one correction and one scoped rereview per causal approach. Unresolved technical recurrence
remains INCOMPLETE and follows the loop's A/B/C recovery; it never resets finding lineage or
substitutes for a required founder decision. Codex uses `fork_turns: "none"`; another harness uses
its equivalent fresh-thread primitive. Prompt wording alone does not establish isolation. The scoped dispatch names the
persisted original finding or report path, correction or diff path, corrected artifact path, and
governing frozen artifact paths. A post-code review defaults to Implementation unless Design or Plan
is explicitly named.

Every governed task has an existing plan task id, explicit `lane:`, non-empty `writes:`, acceptance
criteria, and declared dependencies. Light lane carries a complete inline dispatch and is limited
to work that moves no durable boundary or declared safety surface. Full lane retains the light-lane
controls and adds a validated task card, the applicable specialist, and sealed evidence for public
contracts, schema or migrations, message shapes, module interfaces, generated clients, consent,
authorization, personal or health data, redaction, retention, erasure, audit, tokens, or money. A
Light lane task that reaches a Full lane boundary stops and returns to the plan.

Light remains the ordinary bounded lane; Full remains limited to durable or safety boundary
changes. One logical task produces one compact report and receives one complete review across its
maintained change and any declared byte-identical projection.

Every stop is resumable: completed steps leave a named referent and receipt, partial state is
labelled or discarded, and deferrals keep an owner, trigger, consequence, and destination
milestone. An unresolvable tool error, material ambiguity, write-boundary breach, unresolved review
defect, safety finding requiring authority, or exhausted required resource stops affected work.
Before asking the founder, state the unresolved consequential choice, options and recommendation,
or the concrete unavailable permission/resource or exhausted causal recovery. Route technical
questions already decided by the approved outcome internally.

## Evidence

Evidence binds to a referent. Record the source/tree, exact command, interpreter, runtime identity,
environment inputs, exit status, and machine-readable results. A green summary without executed
test counts is not proof. Strictness belongs to the checker; callers do not select weaker modes.
Reuse successful evidence only while its referent, command, runtime, and environment inputs are
unchanged. An equal or stronger proof correction requires independent confirmation before revised
evidence is admitted; preserve failed and skipped receipts and all required obligations. Repeat a
gate only when its referent or inputs change, a run fails, or prior evidence becomes invalid.
Record the reason for every repeat and reuse a still-valid successful result;
repeating an unchanged successful check adds no evidence.

For Gradle execution, `--rerun-tasks` is the only accepted freshness evidence; `cleanTest` is
insufficient.

Context arrives by path and recipe. Writers put detailed reports in files and return compact
handoffs. Read-only judges return a structured verdict of at most thirty lines, which the
controller persists. Current resume pointers are replaceable bounded state derived from git and
`plan_waves.py`; append-only decisions retain founder rulings, interface distillations, corrected
assumptions, verified commands and limits, and owned deferrals.

Process evidence is owned here. `ratio_meter.py` classifies committed churn against the 10% process
target, and `weekly_review.py` reports the same classification over time. The executable tools own
their calculations; this common core owns the target and verdict policy. Committed churn does
not prove elapsed delivery time or handoff efficiency.

## Stage ownership

| Stage | Owner | Canonical procedure |
| --- | --- | --- |
| Product definition and feature specs | `product-steward` | `references/specs.md` |
| System structure and design invariants | `architect` | frozen design plus `references/specs.md` |
| Plan, scheduling, recovery, and integration | `chief-of-staff` | `references/execution-loop.md` |
| Bounded implementation | `developer` or `senior-developer` | inline dispatch or `references/task-card.md` |
| Semantic review | `reviewer`, conditional specialist | `references/execution-loop.md`, Step 5 |
| Executable validation | `test-judge` | Step 4 plus `references/junit-evidence.md` or `references/codex-gate-sandbox.md` |
| Sealed milestone judgement | `acceptance` | `references/execution-loop.md`, Step 9 |

Before design and plan freeze, trace **required outcome → existing production path → existing
executable proof → actual uncovered gap → smallest sufficient addition**. A new parser, protocol,
registry, or recovery subsystem must justify a specific uncovered gap. The plan inventories actual
consumers, fixtures and generated companions, and prerequisite states. It distinguishes staging,
acceptance, and activation so a task does not require that a successor task is already accepted.

For weekly and ad hoc observation during an active methodology-management session,
`chief-of-staff` owns collection, classification, and persistence. Follow
`methodology-management/references/assessment.md`, append its distillation to
`~/.claude/docs/LEDGER.md`, and record accepted outcomes with exact Git,
task, trace, seal, and acceptance referents; noncached input, cache reads, cache writes, and output
as separate units; actual cash or allowance evidence in its native unit; coverage and missing logs;
founder, quota, and gate waits; and interruptions and rework classified by cause. Absent or
unattributable data stays explicitly unknown. Observation records facts; it does not approve
policy, model, or runtime changes.

This maintained source is rendered into adopted repositories. Adoption, installation, publication,
commit, push, PR, merge, release, and deployment remain deliberate actions under their existing
authority. Historical rationale lives in `references/history-v3-v5.md` and is not current authority.
