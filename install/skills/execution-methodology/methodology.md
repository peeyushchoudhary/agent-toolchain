# Execution methodology

How work travels from a product intent to a merged milestone. Authored once, rendered into every
repository, followed identically by Claude Code and Codex.

This document is the *sequence between* roles. The personas say who; this says what must exist
before a stage begins, what must be true before it ends — and, new in v3, what the process itself
is allowed to cost.

## Principles

Eight rules. Each exists because its absence cost a measured amount of work, and each is enforced
by a mechanism rather than by intention wherever a mechanism is possible. v3 exists because the
review loop was the one place that standard was never applied to the methodology itself, and the
loop diverged exactly as an unmechanized rule predicts (see the v3.0 changelog).

**1. Evidence binds to a tree, and proves execution.** A passing gate that does not name a commit,
a tree, and the stages that ran certifies nothing. A check must prove it *ran*, not merely that it
succeeded: count what ran from machine-readable results, never from a console line.

**2. There is no flag choice.** A checker has one canonical invocation with maximal strictness
baked in, and it rejects arguments. A checker whose strictness is chosen at the call site will be
invoked at its weakest setting eventually.

**3. A builder never approves its own work, and a judge never authorizes a merge.** Judging roles
cannot edit — by tool restriction, not instruction. Their verdict is a finding to triage, never an
authorization; deterministic gates are the only gates. `test-judge` keeps a shell as the stated
exception, because a judge that must take someone else's word for what the gate printed is not a
judge. No other judging persona gets a shell, and none gets an editor.

**4. Context is acquired by recipe, and verdicts are returned compact.** Every dispatched agent
receives paths and commands, not file contents. Writers put reports in files and return a short
verdict. Judges cannot write, so they return their verdict — and *only* a verdict: the structured
form below, thirty lines or fewer, which the orchestrator persists. A judge that returns a
report-shaped essay forces the orchestrator to carry it forever; the essay form is what turned the
persist-one-read exception of v1 into the dominant cost of v2.

**5. Every stop is a resumable boundary.** A quota pause, a crash, and a context limit are
operating conditions, not incidents. Work is checkpointed at each completed step, and nothing
partial survives unlabelled.

**6. Scope is drained, not deferred.** A parked item without an owning milestone is scope loss
wearing a hat. Deferrals live in a register that a milestone can fail against.

**7. Execution is bound to one approved outcome.** The approved plan owns one Goal Capsule. Before
implementation or repair, a dispatch names the capsule criterion or invariant it advances and the
observable delta expected. Review discovers evidence; it does not redefine the product. A
"correction" that adds mechanism the plan's primitives do not contain is not a correction — it is a
scope change, and it routes to a human gate instead of blocking a round.

**8. The process is measured, and it can fail.** Every milestone receipt records what the process
cost next to what it shipped. A process:product ratio worse than 1:1, a subject that hits the
review budget, or a 48-hour zero-commit stall on an active milestone is a *process regression* —
triaged like any other regression, at the merge gate, with the same seriousness. A methodology
that measures everything except itself discovers its own failure two weeks late, from the outside.

## Two lanes

Not every task earns the full machinery. The lane is chosen by the plan, per task, by one test:

**Does this task cross a durable boundary?** A REST contract, a database schema or migration, a
queue message shape, a module's public interface, a generated client — or a declared safety
surface: consent, authorization, personal or health data, redaction, retention, audit, tokens,
money. If yes, **full lane**. If no, **light lane**.

**Light lane** — the default. No card. The dispatch carries the goal, the capsule criterion, the
paths it may write, the tests to run, and the lane's area check. One implementation review by
`reviewer` (compact verdict), `test-judge` on the gate, commit with distillation. That is the
whole ceremony. The measured record is unambiguous: this shape shipped ten pull requests in three
days in one repository and a same-day plan-to-merge milestone in another, with no quality incident
attributable to the missing ceremony.

**Full lane** — everything below: a validated card, contract review where a contract moves,
`security-validator` where a safety surface moves, the full-diff pass, the sealed evidence.

A light-lane task that turns out to touch a durable boundary stops and returns to the plan — the
lane was mis-assigned, and the plan owns lane assignment.

## The chain

Seven artifacts, three human gates. Nothing downstream begins until its input exists.

```
PRODUCT SPEC        why this exists, who it serves, where it stops
    │               → product-steward
    ▼
FEATURE SPEC        scope · stories · behaviour · edge cases · horizontals · acceptance criteria
    │               → product-steward
    ▼
DESIGN              structure, boundaries, invariants at risk
    │               → architect · one adversarial review under the review budget
    ╞══════════════ GATE 1 — human approves the design
    ▼
PLAN                Goal Capsule · lanes · file structure · task decomposition
    │               FROZEN interfaces including payloads
    │               → planner, contract-architect on durable boundaries
    │               one adversarial review under the review budget
    ╞══════════════ GATE 2 — human approves the plan
    ▼
TASKS               light lane: dispatch directly · full lane: card, machine-checked
    │
    │   ┌─────── unattended loop, per task ───────┐
    └──▶│ context → implement → review (budgeted) │
        │ → validate → commit + distillation      │
        └──────────────────────────────────────────┘
    ▼
MILESTONE           release gate → sealed receipt (incl. process metrics) → acceptance
    ╞══════════════ GATE 3 — human approves the merge
    ▼
                    merge commit, tagged
```

Between Gate 2 and Gate 3 the loop runs unattended. It stops only for a blocker it cannot resolve,
a material ambiguity, an exhausted review budget, or a writer-failure escalation. **A report is not
a request**: report at milestones, then keep going. Before stopping, name the decision — if it is
not a gate, a spend, an irreversible or outward-facing action, or a genuine fork, there is nothing
to ask.

Founder decisions are **batched**. The three gates are the three gates; an approval that is not one
of them rides in the next gate or the next report, and a correction whose wording a review already
specified is transcription, not a fourth gate. Six approval ceremonies in thirty-six hours for one
migration file — one of them for a syntax fix — is the measured cost of forgetting this.

### Specs, design, plan

Spec skeletons live in the execution-methodology skill's `references/specs.md`; the
acceptance-criteria form turns into test names without translation. A feature spec with no edge-case section is not finished, and every
horizontal is addressed or declared not-applicable with a reason.

The design (`docs/superpowers/specs/<date>-<topic>-design.md`, owned by `architect`) carries
structure, module boundaries, dependency direction, and the section that earns the gate: **which
existing invariants this change puts at risk, and what fails closed if it is wrong.**

The plan (`docs/superpowers/plans/<date>-<feature>.md`, owned by `planner`) freezes file structure,
task decomposition, **interfaces including payloads**, each task's lane, and one Goal Capsule: the
actor outcome, one primary byte-real observable, the named safety and compatibility invariants,
non-goals, the allowed write boundary, known facts, `UNKNOWN`s, and the stop condition. Plan the
smallest operationally real safe slice first, on existing or native primitives; proof machinery
with its own durable authority is a new product boundary and returns to Gate 1.

## The review budget

This section is the reason v3 exists. Review in v2 had a written stop-loss and no mechanism, and
the measured result was rounds numbered to fifteen and eighteen, five-reviewer panels issuing
blocks for free, and designs that *grew* 140% under review before ending blocked with the same
verdict distribution they started with. Every rule here is enforceable by a script, and the
orchestrator runs that script before every review dispatch.

**One reviewer.** A review round is one fresh, isolated, read-only `reviewer`, handed only named
artifact paths, never the author conversation or rationale — plus `security-validator` when and
only when the diff touches a declared safety surface, and at most one other domain specialist when
and only when the diff touches that specialist's invariant. Never a panel. Reviewer count per
round is capped at the surfaces the diff actually touches, maximum three, and two of the three
exist only conditionally.

**Two rounds.** The author gets one correction and one scoped rereview of that correction and its
causal area. There is no round three. The orchestrator refuses to dispatch a third round on the
same artifact — mechanically, via the budget check — and instead escalates on the same cause:
Design recurrence returns to Gate 1; plan recurrence returns to Gate 2; implementation recurrence
goes to the founder with the escalation packet. Renaming the task, the attempt, the workspace, or
the card does not reset the counter; the subject is the artifact, not its filename.

**The verdict is structured and compact.** `PASS`, or a finding list. Each finding names the
frozen criterion or invariant, a reachable trigger or state sequence, the observable consequence,
artifact evidence, severity, and the smallest correction or human decision. Thirty lines total.
Preferences, speculative hardening, and invented requirements are non-blocking; `PASS` is valid;
there is no finding quota. The reviewer never authors or applies its correction.

**Growth is a tripwire.** An artifact under review may not grow more than 20% in lines from the
version frozen at first dispatch. Review that expands an artifact is review inventing scope — the
measured endpoint of unbounded expansion was a phone-number confirmation feature whose review loop
demanded a kernel patch. Exceeding the tripwire ends review immediately and routes to the human
gate with the escalation packet.

**Freshness is a dispatch property.** Pre-gate and rereview dispatches are fresh threads —
`fork_turns: "none"` in Codex, the equivalent fresh-thread primitive elsewhere. Prompt wording
alone does not establish isolation. The rereview packet names the persisted original finding or
report path, the correction or diff path, the corrected artifact path, and the governing frozen
artifact paths — never author conversation or rationale. A post-code reviewer dispatch defaults
to Implementation unless Design or Plan is explicitly named.

**The escalation packet is one page.** The decision needed, stated as a question. The positions,
each in two sentences. What each round found and what it cost. Nothing else — a founder asked to
break a tie does not need the eighteen rounds re-narrated, and producing the narration is how one
page becomes a workspace.

**Classification survives from v2**, unchanged in substance: every finding is classified before
repair (current-scope defect, harness defect, pre-existing defect, invalid frozen assumption, new
outcome or claim, external fact, evidence defect), each class keeps its v2 routing, and distinct
safety findings are never capped by any budget. What the budget bounds is *rounds*, never the
severity or number of findings a round may raise.

## The task card (full lane only)

The card is the implementer's entire world: it does not read the plan, and reads nothing the card
does not name. Schema and worked example: the skill's `references/task-card.md`. Validation
contract: v2, unchanged — `validate_card.py --strict --phase pre` before dispatch, `--phase post`
after.

Three constraints are new, and the validator enforces the first two:

- **A card is 150 lines or fewer.** The measured alternative was a 2,250-line card that opened
  with an all-caps preamble instructing readers to distrust the rest of the document. A card that
  cannot say its task in 150 lines is describing a task the plan failed to decompose; it returns
  to the plan, not to a bigger card.
- **Freeze by reference.** `frozen_values` inlines only what fits in ten lines — a signature, an
  event name, a version. Anything larger lives in a committed contract or interface file the card
  names by path and commit. A payload shape inlined into a card can be paraphrased wrong once; the
  same shape in a committed file is one authority every card shares.
- **Prerequisites assert tree state, not git history.** A prerequisite is satisfied when the paths
  and tests it names exist in the working tree at dispatch. Requiring a *commit* as a precondition
  deadlocked a milestone's critical path for five days against its own uncommitted work.

A card is generated once and dispatched once. A card found wrong is regenerated from the plan
under a new id — never patched, never superseded in place, never versioned by filename.

## The task loop

Per task, unattended:

1. **Acquire context** by the dispatch's recipe. Nothing else.
2. **Implement the smallest safe slice.** Name the capsule criterion and the expected delta. Test
   first where it gives a concrete assertion, and watch the test fail for the stated reason before
   implementing — a test never observed red proves nothing. Native primitives; no speculative
   recovery for unreachable states; reachable failure, concurrency, retry, privacy, and
   authorization paths handled and tested.
3. **Validate** with the task's commands, at the task tier.
4. **Review** under the review budget. Full lane adds one **full-diff pass** before the commit
   gate — scoped rereview is structurally blind to defects outside the fix delta, and the
   full-diff pass has caught what three green scoped rounds missed. Once, not per round.
5. **Judge the gate.** `test-judge` runs the card's or dispatch's gate and reports what it printed,
   with the referent (tree, interpreter, command). The implementer's numbers are a claim until it
   does. Where the figures differ, the difference is a finding, never an average.
6. **Commit** the code and the distillation together.

**Commit cadence is an invariant.** Completed work commits at each completed task. An active
milestone branch that has produced no commit in 48 hours is a blocker escalation — not silence.
The most expensive stall in the record was four days of intense artifact production and zero
commits, visible to nobody.

**Writer failure has a floor.** A writer persona that returns nothing twice on the same dispatch
is not replaced a third time. The orchestrator either applies a *fully specified, mechanical*
change itself — labelled as such in the commit, and still subject to the standard independent
review — or escalates. Looping replacement writers while documenting each corpse is process
producing process.

**Failed dispatches are ledger lines.** A dispatch that produced no verdict, an invalid attempt, a
replaced writer — each is one line in the workspace ledger. Never a file. The measured alternative
was nine files whose entire content is "the review did not happen."

## Validation tiers

**Per task** — minutes. Red/green with the failing output quoted, the named tests, the lane's area
check, plus the cheap verifier for each artifact named in `gate_risk` — those exist so failures
surface in thirty seconds instead of an hour into a full gate.

**Per full-lane card, at the commit boundary** — `test-judge` runs the card's gate. Gradle/JUnit
runs prove freshness and counts with the nonce-receipt protocol in the skill's
`references/junit-evidence.md`; exact `--rerun-tasks` is the only accepted Gradle freshness proof.

**Per milestone** — once. The full gate, run by a non-editing judge reporting the gate's own
verdict line verbatim; then acceptance against that exact commit. A read-only Codex `test-judge`
never runs a write-producing gate against the source referent — the standalone-copy sandbox
protocol is in the skill's `references/codex-gate-sandbox.md`.

**A gate pass authorizes nothing.** Not deployment, not provider activation, not a production
write.

## Artifacts, the workspace, and the ledger

**The workspace** (git-ignored, one per plan) holds the recovery ledger, cards, dispatch records,
and persisted verdicts. It exists to survive compaction, and it is deleted at promotion. Because it
is write-only history, what enters it is bounded:

- **No diff snapshots.** A review subject is a commit range or a working-tree state named by SHA;
  git regenerates any diff on demand. The measured cost of serializing them was sixty-eight
  thousand lines of `.diff` files — 4.8× the product output of the stage they reviewed.
- **No restatement packets.** A dispatch that failed is a ledger line; the re-dispatch carries the
  same paths the original did.
- **Verdicts, not reports, from judges.** Thirty lines, structured, persisted once.
- **A workspace growing past ~50 files or ~500 KB is a process-regression signal** and is reported
  in the next milestone receipt, not silently accumulated. Twenty-one megabytes of review record
  scheduled for deletion at merge is not an audit trail; it is heat.

**The program ledger** (tracked, append-only) is the durable record. A plan may not be marked
finished, nor its workspace deleted, until each task's **distillation** is appended and committed:
interfaces produced that later tasks consume; deferrals, each with an owning milestone;
verification actually run, verbatim, including what was not run; surprises and corrected
assumptions. The distillation rides in the task's own commit — never a batch at the end.

**The milestone receipt carries the process metrics** (principle 8): product lines merged, process
lines produced (tracked and workspace, measured at seal), plan-to-merge days, maximum review
rounds reached and by which subject, and writer-failure count. Acceptance reads them; a breach is
recorded as a process regression against the next methodology-change window.

## Stopping and resuming

Work stops in the middle; design for it. Checkpoint at each completed step. A partial state is
labelled or discarded; an unlabelled dirty tree or unverified head blocks the next task until
quarantined. Deleting a workspace is a completion action, permitted only after promotion.

**An orchestrator cannot wait.** It cannot block on a long-running command — its turn ends, and
nothing wakes it unless arranged. Poll, or arrange to be woken. And silence is not death: an agent
that has not reported is not thereby finished or gone. The expensive misread is concluding a live
writer died and dispatching a second onto the same exclusive write set.

## Casting

The methodology says when; the persona pool says who, on which model, with which tools. One
orchestrator holds the loop and serializes every write to a shared interface, manifest, registry,
or generated artifact. Parallelize reads; serialize writes — concurrent implementers are capped,
file-disjoint by their write sets, never concurrent on a shared artifact.

| Stage | Role |
|---|---|
| Product and feature specs | `product-steward` |
| Design | `architect` |
| Pre-gate review (design / plan mode) | fresh read-only `reviewer` |
| Plan | `planner`, `contract-architect` on durable boundaries |
| Locating code | `scout` |
| Implementation | `developer` or `senior-developer`, chosen by the plan |
| Task review | `reviewer`; `security-validator` on safety surfaces; +1 specialist max |
| Gate execution | `test-judge` |
| Milestone judgement | `acceptance` |
| Route, README, lessons | `docs-steward` |
| Holding the loop | `chief-of-staff` |

**Prose routing** is by who still holds the judgement: a behavioural claim written by whoever
changed the behaviour stays with the implementer; drift with no behavioural claim, and corrections
a review has already worded, go to `docs-steward`. The test: can the fix be applied without
reading the code? An **absence claim** — what a check does *not* cover — is never transcription;
this methodology's history is mostly wrong absence claims made confidently.

## Changing this document

**The methodology is frozen while a milestone is in flight.** Rendered versions change at
milestone boundaries only, per repository, and adoption stays staggered and deliberate. The
measured alternative was four versions in six days, landing mid-milestone, with the rendered copy
hand-edited ahead of its own source — the process definition churning faster than any milestone
completed under it.

**Every version that adds a rule retires one.** The changelog records both, and what earned each.
A methodology whose changelog only ratchets tighter is compounding: every failure buys a rule,
every rule buys artifacts, and the artifacts buy failures. v1.1 was the last version to remove
anything; v3.0 is the correction.

## Landing

Small, single-purpose commits during the plan. One milestone-sized pull request at the end, merged
with a merge commit and tagged — where there is no CI, commit history is the audit trail. Agent
work is never force-pushed. The README is updated with the change, not after it. A merge exists to
land work: a merge whose entire content is an approval receipt is ceremony, and the receipt rides
with the work it approves. Committing, pushing, opening a pull request, and merging are founder
decisions; the methodology prepares them and never takes them.

## What changed, and what earned it

### v3.0 — the review budget, two lanes, and the process metric

Earned, all of it, by a two-week audit (2026-08-10) of the three repositories then running
v1.4–v2.1. The measured record: process:product line ratios of 2.5:1 to 15.5:1; review rounds
numbered to R15 and R18 against a written cap of two; five-reviewer panels re-issuing the same
verdict distribution nine hours apart; a design grown 637→1,547 lines under review; a 2,250-line
self-superseding card; a five-day deadlock on a commit-history precondition; a four-day zero-commit
stall; 55% of one repository's merges shipping zero product code; and 68,000 lines of `.diff`
snapshots serialized beside a stage that produced 14,000 lines of product. Under the same period's
*lighter* process, one repository merged ten PRs in three days and another took a milestone from
plan to merge in a day. The mechanism-versus-intention principle was applied everywhere except to
the review loop itself; v3 applies it there.

Added:

- **The review budget** — one reviewer plus conditional specialists (max three), two rounds
  enforced by the orchestrator's budget check, structured thirty-line verdicts, the 20% growth
  tripwire, the one-page escalation packet.
- **Two lanes**, light lane default; the full machinery is reserved for durable boundaries and
  safety surfaces.
- **Principle 8** — process metrics in every milestone receipt, with breach handled as a
  regression.
- **Commit-cadence invariant** (48 hours), **tree-state prerequisites**, **card size cap and
  freeze-by-reference**, **writer-failure floor**, **workspace artifact rules** (no diff
  snapshots, no restatement packets, failed dispatches are ledger lines), **batched founder
  approvals**, and **the methodology freeze with a removal budget**.

Retired (the removal budget, paid in advance):

- **Multi-persona review panels.** Blocks were free and divergence was measured; conditional
  specialists replace the quorum.
- **Round-numbered artifact lineages** (`-r14`, `-r15` cards; per-round frozen packages; rereview
  meta-files). The subject is the artifact; two rounds is the lineage.
- **Diff snapshots and restatement packets** as artifact classes.
- **Approval-receipt-only merges** and per-correction founder approvals.
- **JUnit-evidence and Codex-sandbox protocol prose from this document** — moved intact to the
  skill's `references/junit-evidence.md` and `references/codex-gate-sandbox.md`; the protocols
  themselves are unchanged, and the tooling is identical. A per-task security protocol does not
  need to be read by every persona in every repository at every dispatch.

Kept, deliberately: the three human gates; builder/judge separation by tool restriction and the
`test-judge` shell exception; evidence bound to a tree with forced execution; the Goal Capsule and
finding classification of v1.6; card validation contract v2; the full-diff pass; the two-tier
ledger with distillation-in-commit; merge-commit landing. Each of these has a failure it
demonstrably caught in the record.

Still assumed, not yet tested: that 150 lines is the right card cap rather than merely a right
one; that the 20% growth tripwire is calibrated; that the light lane's boundary test catches every
task that needed the full lane. The process metrics of the next two milestones are the test.

### Prior versions

The v1.1–v2.1 changelog is preserved verbatim in the skill's `references/changelog-v1-v2.md`. Its
earned
lessons — unexecuted greens, the full-diff discovery, card validation, write-set collisions, the
orchestrator that cannot wait — remain the foundation this version stands on.
