# Execution methodology

How work travels from product intent to a merged milestone. This maintained source is rendered into
adopted repositories and is followed by every harness. Personas say who may act; this document says
what must exist before a stage begins and what must be true before it ends.

## Approved runtime

Use the repository-approved runtime bound by `docs/agents/execution/runtime.json`, including an
older approved bundle. A newer global source or candidate never replaces that binding. Resolve all
commands and references below, including `~/.claude/skills/...` spellings, through the inventory's
verified `bundle_root`; do not fall back to global source.

At controller entry and after restart, run that bundle's
`execution-methodology/scripts/sync_methodology.py --repo <repo> --status-json`. Repeat before
dispatch or a long gate when runtime inputs or repository bindings changed; reuse a result only for
identical checked inputs. Governed adopted execution requires `state=current` and `ready=true`.
Missing, changed or unverified inputs stop dependent work. Without inventory, an inspector may
report the gap but grants no adoption; unadopted or deferred projects retain their existing contract.

Keep full status as tool-side evidence and pass the verified referent and required input paths to
actors. Ordinary execution does not invoke maintenance, model research or upgrades. Report the gap;
methodology-management coordinates a separately authorized change.

## Principles

1. **Evidence binds to a referent and proves execution.** Record the tree, command, interpreter,
   exit status, and machine-readable results. A green console summary without executed-test counts
   is not evidence.
2. **Strictness is owned by the checker.** A gate has one canonical strict invocation. Callers do
   not choose a weaker mode.
3. **A builder never approves their own work.** Judges are structurally read-only. `test-judge`
   retains the minimum shell needed to run a gate and reports its real output; no judge promotes or
   merges work.
4. **Context arrives by path and recipe.** Writers put detailed reports in files and return compact
   handoffs. Read-only judges return a structured verdict of at most thirty lines, which the
   controller persists.
5. **Every stop is resumable.** Complete steps leave a named referent and receipt. Partial state is
   labelled or discarded.
6. **Deferrals keep an owner.** A finding may be parked only in the milestone register with its
   trigger, consequence, and destination milestone.
7. **Execution is goal-bound.** Every dispatch names an approved criterion or invariant and an
   observable delta. The PRD, spec, design, and plan are both floor and ceiling; preferences,
   speculative hardening, and invented scope do not block delivery.
8. **The process is measured.** `~/.claude/skills/execution-methodology/scripts/ratio_meter.py` classifies committed churn as product, product
   thinking, or process. Process targets 10%, warns above 15%, and fails above 30% once at least 500
   classified lines exist. Deleting process files is cleanup and cannot breach the budget.

## One chain and three gates

The chain is PRD → feature spec → design → plan → tasks → implementation → task validation and
review → commit → milestone validation → acceptance → merge. The skill diagram is the single
high-level drawing; the loop reference is the single task-loop drawing.

Three human gates remain compatible in name and responsibility:

- **Gate 1, design:** approves the outcome, scope, invariants, and structural decisions.
- **Gate 2, plan:** approves task decomposition, dependencies, write boundaries, validation, and
  lane assignment.
- **Gate 3, merge:** considers the sealed milestone, acceptance verdict, honest documentation, and
  observed process metrics.

Repeat a gate only when its referent or inputs change, a run fails, or prior evidence becomes
invalid. Record the reason for every repeat and reuse a still-valid successful result; repeating an
unchanged successful check adds no evidence.

Related decisions may be presented together, but missing approval is never inferred from elapsed
time. Between Gate 2 and Gate 3, the controller follows
`references/execution-loop.md` without pausing for routine confirmations. A gate pass authorizes no
deployment, provider activation, production write, push, PR, or merge.

## Product definition, design, and plan

`product-steward` owns the current-state PRD and feature specs. Acceptance criteria cover reachable
success, failure, edge, authorization, privacy, and recovery behavior as applicable. Project domain
validators read definition and design when their declared concern moves. `~/.claude/skills/execution-methodology/scripts/spec_check.py` verifies
document shape, criterion coverage, horizontals, validator routing, and owned deferrals.

`architect` owns system structure, module boundaries, dependency direction, and the named
invariants put at risk. The plan, owned by `chief-of-staff`, freezes interfaces including payloads,
task decomposition, dependencies, write boundaries, validation, lane assignment, and the Goal
Capsule. Use the smallest operationally real safe slice and existing/native primitives. A new
durable authority returns to design.

Design, architecture, and data-flow visuals may use Mermaid or locally committed images, including
ImageGen output. Choose the form that makes the relationships clearest and remains practical to
maintain, honor the user's stated preference, and never require both. Keep labels, arrow direction,
and protected invariants consistent with the design; provide an accessible text description and
record image provenance. Raster review inspects rendered semantics and private pixels. A content
hash identifies the reviewed file; it does not prove those properties. README architecture images
follow the owning progressive-disclosure declaration contract. Other design images are not
automatically validator-checked merely because this rule permits them.

The exact pre-gate contract is a fresh, isolated, read-only `reviewer` with only named artifact
paths, never the author conversation. `PASS` is valid; there is no finding quota. A blocker names
its criterion or invariant, a reachable trigger or state sequence, the observable consequence,
artifact evidence, severity, and the smallest correction or human decision. The author receives
one correction and one scoped rereview. Design recurrence returns to Gate 1; plan recurrence returns
to Gate 2. Codex uses `fork_turns: "none"`; another harness uses its equivalent fresh-thread
primitive. Prompt wording alone does not establish isolation. The scoped dispatch names the
persisted original finding or report path, correction or diff path, corrected artifact path, and
governing frozen artifact paths. A post-code review defaults to Implementation unless Design or Plan
is explicitly named.

## Plan admission and the two lanes

Every governed task must already exist in a fenced plan task block with all of:

- an existing plan task id;
- an explicit `lane:` of `light` or `full`;
- a non-empty `writes:` boundary;
- non-empty acceptance criteria in `covers:`;
- dependencies and intentional serialization where applicable.

`~/.claude/skills/execution-methodology/scripts/plan_waves.py` rejects missing admission metadata before either lane dispatches. It derives waves,
continuous readiness, write-set conflicts, and named-commit conformance from the plans and git. It
does not create plans, state, or a second task registry.

**Light lane.** Use when the task moves no durable boundary or declared safety surface. There is no
card. Its inline dispatch carries the existing plan task id, goal, criterion/invariant, observable
delta, exact writes, tests, area check, persona, context paths, stop conditions, and report path.
The writer works within that boundary, `test-judge` runs the tests and area check, `reviewer`
inspects the full task diff, and `~/.claude/skills/execution-methodology/scripts/plan_waves.py --commit` checks the named commit against plan
`writes`. Git plus the plan provide resume state.

**Full lane.** Use for REST or published contracts, database schema and migrations, queue message
shapes, module public interfaces, generated clients, or consent, authorization, personal or health
data, redaction, retention, erasure, audit, tokens, and money. It retains every light-lane control
and adds a strict task-card v2 pre/mid/post check, the applicable boundary specialist, and sealed
evidence. The complete card, validation, JUnit, trace, sandbox, and handoff contracts live in
`references/task-card.md`, `references/junit-evidence.md`, and
`references/codex-gate-sandbox.md`; those maintained sources override summary prose.

A light task that reaches a full boundary stops and returns to the plan. The plan changes first;
the controller does not widen the dispatch in place.

## Implementation review: one procedure

Every implementation task receives **one initial full task-diff review** by a fresh read-only
`reviewer`. This review covers all task writes against the frozen criteria and invariants, with at
most one relevant specialist for a distinct owned invariant, plus `security-validator` when a
safety surface moves. `test-judge` runs commands and is not a semantic review lens.

Every finding is classified before repair as a current-scope defect, harness defect, pre-existing
defect, invalid frozen assumption, new outcome or claim, external fact, evidence defect, safety
finding, or scope change. Only a valid current-scope correction inside the existing task boundary
returns to the writer.

After that correction, perform **one scoped correction review**. The fresh reviewer receives the
persisted original finding, correction/diff, causal area, corrected artifact, and governing frozen
artifacts by path. It does not receive author conversation or rationale. This second review checks
the repair without repeating the whole task diff.

Two rounds are the procedure; they are not a rule that turns uncertainty into success. An
unresolved semantic defect leaves the task **INCOMPLETE**, never READY. A mechanically specified
final application may be performed by the controller only when it stays inside the frozen task and
then receives **independent executable confirmation**. It does not receive a semantic promotion by
default. A repeated causal defect returns to the relevant gate; distinct safety findings remain
blocking regardless of count.

`~/.claude/skills/execution-methodology/scripts/check_review_budget.py WORKSPACE --next SUBJECT` runs before each review dispatch. It enforces
banned artifact classes and exposes lineage/round use; a dispatch that returns no verdict spends no
round. Growth above 20% in the reviewed artifact returns to its gate. The review count never weakens
a test, safety, evidence, or acceptance result.

## Task execution and validation

The operational sequence and exact commands are in `references/execution-loop.md`. Per task:

1. Derive status and readiness from the plan and git.
2. Admit either the light inline dispatch or the full validated card.
3. Acquire only the named context and observe a repository-provable regression red where one
   exists.
4. Implement the smallest safe slice, including reachable failure, concurrency, ordering, retry,
   privacy, and authorization cases relevant to the task.
5. Run focused validation, the area gate, independent implementation review, and independent gate
   execution.
6. Commit with the plan task id and distillation; immediately check the commit's writes.
7. Drain deferrals, verify criterion trace evidence, run the milestone gate, and seal the exact
   tree before acceptance.

Full-lane cards are at most 150 lines. Frozen material over ten lines lives in a committed contract
file named by path. Prerequisites assert working-tree state, never git history. A wrong card is
regenerated from the plan under a new id. `~/.claude/skills/execution-methodology/scripts/validate_card.py --strict --phase pre` admits it;
`--phase mid` checks drift; `--strict --phase post` requires every declared output and exact test
to exist.

Every validation entry is a direct process mapping with normalized `cwd` and non-empty `argv`; the
task-card reference defines the exact v2 schema. Java selectors, `--rerun-tasks`, JUnit nonce
receipts, criterion trace checks, sandboxed write-producing gates, migration fencing, and seal
receipts retain their detailed source contracts. Do not paraphrase them into a second protocol.
`--rerun-tasks` is the only accepted Gradle freshness proof.

## Controller state, records, and recovery

The controller owns plans and **bounded controller state** needed to resume the active milestone.
Current resume pointers are a replaceable snapshot derived from git and `~/.claude/skills/execution-methodology/scripts/plan_waves.py`; they may
name the active milestone, seal revision, and current in-flight task ids. They do not claim task
completion and are refreshed or discarded as the tree changes.

The durable record contains **append-only decisions** and task distillations: interfaces produced,
verified commands and limits, corrected assumptions, deferrals with owners, and founder rulings.
Current resume pointers never live in that append-only record. Plans may be edited by the
controller; product source and tests always go to a dispatched writer.

The git-ignored workspace may hold full cards, dispatch records, writer reports, and persisted
judge verdicts. It holds no raw prompt dumps, restatement packets, accumulated diff snapshots, or
files whose only content is a failed dispatch. Judges return compact verdicts; writers return
reports. Workspace caps and verdict naming remain enforced by the existing review-budget tooling.

After compaction or restart, rerun `~/.claude/skills/execution-methodology/scripts/plan_waves.py --milestone M<n> --since <seal-rev> --json` and
reconcile only the current in-flight ids. Unclaimed commits remain visible as commits that did not
resolve to any declared task. They are not silently reclassified as light-lane work and cannot
complete a governed task.

## Evidence and milestone completion

Per-task validation records the real command and output. Java/JUnit tasks use a single-use start
receipt immediately before execution and verified XML afterward. `~/.claude/skills/execution-methodology/scripts/trace_check.py` compares criteria
with ids from verified evidence and reports its limits, including which ids predate the commit
range. A passing selector or receipt does not prove assertion quality.

A milestone declares its cross-feature gate. `~/.claude/skills/execution-methodology/scripts/milestone_seal.py --record M<n>` requires a clean
tree, runs the gate on that tree, and stores a receipt outside the repository keyed to its tree SHA.
`acceptance` independently evaluates the same sealed referent against the frozen criteria. The
founder alone authorizes merge.

The milestone report is composed from current command output: task status and unclaimed commits,
criterion trace, owned deferrals, seal verification, process ratio, review-budget state, and explicit
limits or skipped checks. Measurements use their actual unit and corpus; unmeasured claims stay
unmeasured. A model choice is never evidence of quality or safety.

`~/.claude/skills/execution-methodology/scripts/weekly_review.py` reports the same `~/.claude/skills/execution-methodology/scripts/ratio_meter.py` classification over time; it is a trend report,
while the merge-range ratio remains the gate input.

## Adoption, maintenance, and history

This file is the maintained source. `sync_methodology.py --repo PATH` renders it into an adopted
repository and `--check` detects drift; adoption is deliberate per repository. Source changes are
reviewed and tested before selective re-vendoring. Global installation is a separate action.

Methodology changes follow the same design, plan, review, and verification rules. Their goal names
an observed process defect, their plan owns an exact write set, and their acceptance requires a
real workflow fixture where possible. Historical measurements, superseded procedures, and the
rationale for versions 3 through 5 live in
`references/history-v3-v5.md`. That reference is not current authority.

Landing updates the repository README and route so they describe the resulting system. Run the
repository's local gate and report its verbatim verdict. Commit, push, PR, merge, release, and
deployment remain deliberate, separately authorized actions.
