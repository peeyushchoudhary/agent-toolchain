# Execution methodology

How work travels from a product intent to a merged milestone. Authored once, rendered into every
repository, followed identically by Claude Code and Codex.

This document is the *sequence between* roles. The personas say who; this says what must exist
before a stage begins, what must be true before it ends — and, declared in v3 and enforced since
v4, what the process itself is allowed to cost.

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
scope change, and it routes to a human gate instead of blocking a round. The spec is the ceiling as
well as the floor: build what the PRD, the spec, and the plan say, and stop. A finding that demands
more than the spec requires — extra hardening, extra generality, extra polish — is over-engineering
and non-blocking by definition. The deliverable is the outcome, not its perfection.

**8. The process is measured by a script that can fail the gate.** `scripts/ratio_meter.py`
classifies committed churn into product, product thinking, and process, and exits non-zero when
process exceeds its band. The budget is **10%** of classified churn; the gate warns above **15%**
and fails a merge above **30%**, and nothing fails below 500 classified lines. The target and the
enforcement bands are different numbers on purpose: 10% is what the process is worth, and 30% is
the point past which a merge is not worth arguing about. It runs at the merge gate and in the
weekly review. A subject that hits the review budget, a process-only commit outside a milestone seal, and
a 48-hour zero-commit stall on an active milestone remain process regressions, triaged at the
merge gate with the same seriousness.

This principle is new in substance, not in wording. v3 stated the budget as a ratio and left it to
intention, and the measured consequence in one repository was a process share that climbed from 4%
to 75% over eight weeks while product output fell 97% — with no rule firing, because the rule had
no mechanism. Principle 1 says a check must prove it ran. Principle 8 is now the same kind of
claim: a number a script produced, or nothing. The meter binds where a round-counter could not,
because it reads git's own numstat and nobody can inflate the product side without writing
product.

## The budget

Every methodology spends someone's attention. This one declares the split it is allowed to spend,
and `ratio_meter.py` enforces it:

| Bucket | What it is | Share |
|---|---|---|
| **Product** | Source, tests, migrations, build and infrastructure files | **at least 70%** |
| **Product thinking** | PRD, feature specs, design, decision records, architecture, runbooks | about 20% |
| **Process** | Workspace, ledger, cards, verdicts, receipts, deferrals, agent docs | **10% target · 15% warns · 30% fails** |

The product floor is advisory. The process band is binding: above 15% the gate warns, above 30% it
fails. Only committed churn is measured, so the git-ignored workspace never reaches the meter —
cards are bounded by their own 150-line cap and the workspace's 50-file / 500 KB limit instead. Removing
bookkeeping is never a breach: a commit that only deletes process files is classified `cleanup` and
is exempt, because a budget that punishes cleanup guarantees the corpus only grows.

Two consequences follow, and they are the whole of v4:

- **A process artifact earns its place against the ceiling, not against usefulness.** Every
  artifact in the record was arguably useful. The question is whether it is worth part of the 10%.
- **Process is capped per week, not per artifact.** Ten percent of a week that shipped a feature is
  a real budget. Ten percent of a week that shipped nothing is nothing — which is the correct
  amount of bookkeeping for a week that shipped nothing.

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

**Where founder attention goes** — the shape measured in the repository that out-shipped the fleet
(46 commits, seven same-day pull requests, bookkeeping at 3% of product lines):

1. **Specs, reviewed with the founder.** `product-steward` writes the PRD and feature specs; the
   founder reviews them with a disposable interactive HTML explainer — one file, rendered from the
   specs, deleted at approval. Decisions land in the spec text, never in the explainer.
2. **Task breakdown, reviewed with the founder.** `planner` (plus `contract-architect` on durable
   boundaries) decomposes features into lane-tagged tasks; the founder reviews the task list —
   titles, outcomes, dependencies — never the cards.
3. **Plans, machine-reviewed.** Implementation and validation plans at two granularities — feature
   level (wave definition, area gate, integration order) and task level (dispatch or card) — under
   the review budget, fresh `reviewer`, apply-and-close. No founder round here.
4. **Autonomous execution.** The task loop, in strict adherence to the plans; a deviation is a stop
   condition or a scope change under principle 7, never an improvisation. The founder's next
   appearance is the merge gate.

Gate 1 therefore attaches the founder to *what is being built* (specs, with the design riding under
machine review) and Gate 2 to *what will be done* (the task list, with the plans riding under
machine review). Front-loading founder attention this way is what empties the escalation queue: the
decisions that stalled repositories mid-execution are made in batch, up front, where they cost
minutes.

```
PRODUCT SPEC        why this exists, who it serves, where it stops
    │               → product-steward
    ▼
FEATURE SPEC        why · scope · surface · acceptance criteria · examples · horizontals
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
acceptance-criteria form turns into test names without translation. Edge cases are acceptance
criteria like any other — a feature whose criteria describe only the happy path is not finished,
and `edge_cases:` in the front matter names the classes that were considered. Every horizontal is
addressed or declared not-applicable with a reason.

**The agent answers its own question first.** Before asking the founder anything at a spec gate,
the asking agent must answer the question itself from the spec text. If it can, the question was
never needed. If it cannot, that is a defect in the spec rather than a gap in the founder, and the
agent fixes the spec and shows the diff. What survives that filter is a genuine product decision,
and `spec_check.py --questions` is the queue of them — read it at the gate, one item at a time,
each answer edited into the spec at the place the question sat. There is no transcript, no approval
record, and no per-feature ceremony: the answer IS the artifact, and the queue emptying is the
evidence. A comprehension check that stores its own results has become the thing it was measuring.

**A spec states what is true now.** Both templates are updated in place and never appended to: no
dated headings, no changelog section, no correction standing beside the thing it corrects. History
is in git, *why* is in an ADR under `docs/decisions/`, and the append-only residue — a retired
criterion number — is a front-matter key rather than a paragraph. A reader who has to date the
sentences to find which one binds is interpreting the document at runtime, and two readers will
interpret it differently.

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
verdict distribution they started with. The round budget binds by counting round markers on persisted verdict filenames — the
`<subject>-r<N>-<kind>.md` convention in the workspace rules below, which is why that convention is
mandatory. v3 spent 1,085 lines of Python on that count and then reclassified the tool advisory,
for a correct reason: a checker run by the party it binds cannot bind that party. The count is
cheap and the honesty is the orchestrator's either way, so **v4 stops treating that count as a
control**. The script stays for the half of its job that is a control: the banned-artifact scan
reads what is on disk, which is a fact about a directory rather than a claim by its author, and it
is what found 468 raw dumps in one workspace. The reviewer count, the verdict form, and the growth
tripwire bind at dispatch construction. What binds mechanically is the process ceiling of principle
8, which no orchestrator can satisfy by producing more process.

**One reviewer.** A review round is one fresh, isolated, read-only `reviewer`, handed only named
artifact paths, never the author conversation or rationale — plus `security-validator` when and
only when the diff touches a declared safety surface, and at most one other domain specialist when
and only when the diff touches that specialist's invariant. Never a panel. Reviewer count per
round is capped at the surfaces the diff actually touches, maximum three, and two of the three
exist only conditionally.

**Two rounds.** The author gets one correction and one scoped rereview of that correction and its
causal area. There is no round three: before dispatching, the orchestrator names the subject to
the budget check (`--next <subject>`), which refuses when that subject has already spent its two
rounds — the third round is refused before it exists, not discovered after. The refusal counts
the round markers on persisted verdict filenames (the `<subject>-r<N>-<kind>.md` convention in the
workspace rules below), which is why that convention is mandatory. On refusal the subject
closes instead of looping: the orchestrator applies the final verdict's named smallest correction
and closes — no third round, no rereview of the application, no escalation. Only two finding
classes still escalate: a safety-class finding, and a scope change under principle 7 (Design
recurrence returns to Gate 1; plan recurrence returns to Gate 2; the brief names its default).
A dispatch that never produced a verdict — a harness refusal, a thread-limit rejection, zero
bytes returned — spends no round of any budget; the measured alternative converted three harness
refusals into a spent budget and a gate frozen for six days. Renaming the task, the
attempt, the workspace, or the card does not reset the counter; the subject is the artifact, not
its filename. The check keys on the declared subject and on filename lineage — it is protection
against drift, not against an orchestrator that renames its subjects, and a renamed subject is
itself a violation that shows in the receipt.

**The verdict is structured and compact.** `PASS`, or a finding list. Each finding names the
frozen criterion or invariant, a reachable trigger or state sequence, the observable consequence,
artifact evidence, severity, and the smallest correction or human decision. Thirty lines total.
Preferences, speculative hardening, and invented requirements are non-blocking; `PASS` is valid;
there is no finding quota. The reviewer never authors or applies its correction.

**Growth is a tripwire.** An artifact under review may not grow more than 20% in lines from the
version frozen at first dispatch. Review that expands an artifact is review inventing scope — the
measured endpoint of unbounded expansion was a phone-number confirmation feature whose review loop
demanded a kernel patch. Exceeding the tripwire ends review immediately and routes to the human
gate with the escalation brief.

**Freshness is a dispatch property.** Pre-gate and rereview dispatches are fresh threads —
`fork_turns: "none"` in Codex, the equivalent fresh-thread primitive elsewhere. Prompt wording
alone does not establish isolation. The rereview dispatch — a message to the reviewer, never a
workspace file — names the persisted original finding or
report path, the correction or diff path, the corrected artifact path, and the governing frozen
artifact paths — never author conversation or rationale. A post-code reviewer dispatch defaults
to Implementation unless Design or Plan is explicitly named.

**The escalation brief is one page, and it names a default.** The decision needed, stated as a
question. The positions, each in two sentences. What each round found and what it cost. And the
**default action** — the smallest safe resolution, which the orchestrator executes if the founder
has not answered within minutes when present in the session, or by the next session start
otherwise. A queue that hard-blocks on every question froze a repository for six days on two
unanswered briefs while the working tree sat clean. Only a safety-class or irreversible decision
has no default and truly waits. Nothing else goes in the brief — a founder asked to break a tie
does not need the eighteen rounds re-narrated, and producing the narration is how one page becomes
a workspace.

**Classification survives from v2**, unchanged in substance: every finding is classified before
repair (current-scope defect, harness defect, pre-existing defect, invalid frozen assumption, new
outcome or claim, external fact, evidence defect), each class keeps its v2 routing, and distinct
safety findings are never capped by any budget. What the budget bounds is *rounds*, never the
severity or number of findings a round may raise.

## The task card (full lane only)

The card is the implementer's entire world: it does not read the plan, and reads nothing the card
does not name. Schema and worked example: the skill's `references/task-card.md`. Validation
contract: v2, extended by the size budget below — `validate_card.py --strict --phase pre` before
dispatch, `--phase post` after. A sealed pre-v3 card over the size budget still passes a plain
run; `--strict`, the gate mode, now fails it.

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

**The seal is gated at the push, and the gate wants evidence rather than a claim.** A milestone
document declares its cross-feature command under `## Cross-feature validation`; moving it to
`status: shipped` is the claim that the journeys no single feature's suite can prove were proved.
`milestone_seal.py --record M<n>` runs that command from a clean tree and receipts a pass, and the
pre-push guard refuses the seal without a receipt bound to the pushed tree. Only the transition is
checked, so a milestone already shipped costs nothing on any later push. The receipt is written
outside the repository: evidence that can travel in a clone lets one machine's run seal another
machine's push.

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
- **No raw dumps and no persisted prompts.** A `.raw` capture of a verdict duplicates the
  structured verdict beside it; a persisted dispatch prompt duplicates the recipe that generated
  it. Both are banned classes the budget check rejects — one workspace held 468 of them.
- **Verdicts, not reports, from judges.** Thirty lines, structured, persisted once — and named
  `<subject>-r<N>-<kind>.md`. The round marker on a persisted verdict is load-bearing: it is what
  the budget check counts, so a marker-free verdict filename is a methodology violation, not a
  style choice. This is the one deliberate exception to the retired round-numbered lineages.
- **No reports.** A report is a verdict that outgrew thirty lines. The class is banned wherever a
  verdict, a ledger line, or a commit message can carry the finding — which is everywhere except a
  spec, a design, or a decision record, all of which are product thinking and live in the tracked
  tree. The measured cost of the exception was 453 report files and 6.35 MB in one workspace, a
  third of its entire process corpus, restating findings already recorded in the verdicts beside
  them.
- **The caps are gate-enforced, not advisory.** Card 150 lines, verdict 30 lines, distillation 5
  lines, workspace 50 files or 500 KB, ledger 500 lines before rotation. v3 wrote all five as prose
  and the author repository breached every one of them — the workspace by 28x on files and 37x on
  bytes, the largest card by 15x, twenty artifacts past a round cap that reads "there is no round
  three". A cap only a human notices is a preference. Twenty-one megabytes of review record
  scheduled for deletion at merge is not an audit trail; it is heat.

**The program ledger** (tracked, append-only) is the durable record. A plan may not be marked
finished, nor its workspace deleted, until each task's **distillation** is appended and committed:
interfaces produced that later tasks consume; deferrals, each with an owning milestone;
verification actually run, verbatim, including what was not run; surprises and corrected
assumptions. A distillation is five lines or fewer, and it rides in the task's own commit — never
a batch at the end, never a process-only commit. The ledger is a record, not a narrative: the
measured alternative grew one ledger by twelve thousand lines in a week while ninety-four of a
hundred and fifty commits carried no product. **The ledger rotates at 500 lines** — the live file
carries the open milestone, closed milestones move to a dated archive nothing reads by default. An
eighteen-thousand-line ledger is not a record; it is a file every session pays to skim, and the one
in the record held entries averaging seventy-four lines against a five-line cap.

**The milestone receipt carries the process metrics** (principle 8): product lines merged, process
lines produced (tracked and workspace, measured at seal), plan-to-merge days, maximum review
rounds reached and by which subject, and writer-failure count. Acceptance reads them; a breach is
recorded as a process regression against the next methodology-change window.

## The weekly review

Once a week, `scripts/weekly_review.py` reports each repository's three-bucket split for the last
eight weeks, its process share against the ceiling, and a trend verdict. It takes ten minutes, and
it is the only recurring process ceremony this methodology schedules.

It exists because the failure it catches is invisible from inside a single week. Every individual
bookkeeping commit is defensible on its own; the eighth consecutive week of them is not, and
nothing in one session's context can see the eighth week. Read the trend, not the week — three
weeks degrading is a signal, one week over is noise.

The review has exactly two possible outputs: a decision about what to build next, and at most one
methodology change, which is itself subject to the rule below.

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

**The orchestrator is one long-lived session per milestone.** Cold fresh-thread dispatch is
reserved for the roles that need isolation — the judging personas. Implementation and stewardship
run inside the controller's session or as warm subagents that inherit its context, because every
cold session pays its full boot — system prompt, roster, rendered methodology — before its first
token of work. The measured week put 438 cold sessions beside two warm ones: the cold sessions
landed four commits, the warm ones a hundred and fifty-one.

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

**A process change requires a week that was in budget.** A methodology edit may only be authored
in a week whose process share read at or below the ceiling. Every self-generating loop in the
record began as a process change made while already over budget: a stale receipt bought a staleness
sweep, which bought a review round, which bought a process-only commit, which was itself the
regression. A process permitted to rewrite itself while failing its own budget has no fixed point.

**Every version that adds a rule retires one.** The changelog records both, and what earned each.
A methodology whose changelog only ratchets tighter is compounding: every failure buys a rule,
every rule buys artifacts, and the artifacts buy failures. v1.1 was the last version to remove
anything; v3.0 is the correction.

## Landing

Small, single-purpose commits during the plan, landed in wave-sized pull requests as they turn
green — main moves the same day a wave passes its gate, and nothing accumulates unmerged past the
48-hour cadence invariant. The measured alternative was thirty commits and eight thousand product
lines stranded on branches while main sat ten days stale. Merge commits, never squash, tagged at
the milestone — where there is no CI, commit history is the audit trail. Agent
work is never force-pushed. The README is updated with the change, not after it. A merge exists to
land work: a merge whose entire content is an approval receipt is ceremony, and the receipt rides
with the work it approves. Committing, pushing, opening a pull request, and merging are founder
decisions; the methodology prepares them and never takes them.

## What changed, and what earned it

### v4.2 — the plan is scheduled, not described

A feature spec says what to build; turning it into tasks was prose, and prose can neither schedule
nor collide. A feature plan at `docs/product/plans/F-<id>-<slug>.md` carries the implementation plan
and the validation plan together, its tasks declare `needs`, `writes` and `covers`, and the waves
are derived rather than written. The milestone gains the goal no single feature owns, outcome-level
success criteria, and the cross-feature journeys no feature suite can prove — which is also what
scopes concurrency across features.

Earned by measurement on a real 51-task graph: the dependency edges alone give 8 waves, and 37 pairs
inside those waves declare overlapping write sets. Across a 5-feature milestone the per-plan view
reported zero findings and exited green while six cross-feature pairs collided. Matching 16 sealed
cards to their commits, 4 of 83 files landed outside the declaring task's write set, all four inside
another task's.

Added: the feature plan and validation plan; `plan_waves.py` with wave derivation, collision
refusal, and a commit-versus-declaration check; `serialises:` for a deliberate shared write set;
the milestone's goal, success criteria and validation gate.

Retired: `expected_red`, a fact about the tree that goes stale on the next commit — three of three
such literals in a real plan were already false when checked; and the wave-scoped collision check,
whose own remedy silenced it.

### v4.1 — the product definition is checkable

`references/specs.md` became the product-definition contract: one PRD per repository, its feature
specs, and the rule that outranks the rest of the file — a spec states what is true now, is updated
in place, and never says what it used to say. `spec_check.py` enforces that structurally, because a
broad word-match for history language fired 1,057 times across 164 real documents, mostly on domain
vocabulary. `--surfaces` binds a newly exposed route to an approved Surface section, after a PRD
section headed "out of scope" named eight modules and all eight were built: 229 endpoints, none
reachable.

Added: the PRD, feature spec, milestone and README templates; `spec_check.py`; the decision queue;
the agent-first readback clause.

Retired: the per-area product spec, folded into one PRD; the interactive HTML explainer, replaced by
the decision queue; the per-feature approval interview.

### v4.0 — the budget binds

Earned by an eight-week external audit of the whole portfolio (2026-08-21, eleven repositories),
which found the failure v3.0's own principle 8 predicted and could not see. In the largest
repository the process share of committed churn ran 4% in week 27 and 75% in week 34; product
output fell from 404,312 lines to 11,129, a 97% collapse; of the last hundred commits, 73 were
`docs` and 8 were `feat`, with 67 subjects naming process machinery and 5 naming a product noun.
Two unrelated repositories collapsed in the same week — the week each adopted v3. The one
repository that never adopted it, and which methodology.md already cites as its gold standard,
carried bookkeeping at 3% of product lines and out-shipped the rest of the fleet by 3.5x.

The cause was not strictness. It was that principle 8 — the one principle that measures the
methodology itself — was the only principle with no mechanism. No script computed the ratio, and
no receipt recorded it. Meanwhile the rule that was provably unmechanizable, the review round count,
received 1,085 lines of Python before being reclassified advisory. Every numeric limit v3.1 set was
breached by its own author repository, most of them by more than an order of magnitude.

Added: the three-bucket budget with a 10% target, warning at 15% and failing at 30% (`ratio_meter.py`); the weekly
review (`weekly_review.py`); gate enforcement for the five caps v3 wrote as prose; ledger rotation
at 500 lines; the in-budget precondition on methodology changes.

Retired: reports as an artifact class; the advisory framing of all five numeric caps; and the
review-round count as a control — the script keeps its banned-artifact scan, which reads the disk
rather than the author, and the count keeps the verdict filename convention it always used. Nothing
here deletes a check that binds; what goes is the ceremony around the two that never did.

### v3.1 — outcome focus and the unattended founder

The week after v3.0 was measured the same way v2 was (2026-08-12..20, four repositories). The
round cap held — no post-adoption subject anywhere exceeded two rounds — and that exposed the
next constraint up the stack: every capped review failed closed onto a founder gate, and the
founder is one person across four repositories. One repo froze six days on two unanswered briefs
with a clean tree; another consumed five founder gates in one day; a third wrote ninety-four
process-only commits against twenty-six product ones and grew its ledger twelve thousand lines;
588 cold dispatch sessions landed nine commits while two warm sessions landed 151. Reviews exited
via block-and-escalate rather than pass; harness refusals were counted as spent rounds.

Added: the over-engineering guard on principle 7 (the spec is the ceiling); the default action on
every non-safety escalation; the five-line distillation cap; the raw-dump and persisted-prompt
banned classes; the long-lived orchestrator session; wave-sized landing; the founder-attention
milestone shape (specs and task breakdown reviewed with the founder, plans machine-reviewed,
execution autonomous), taken from the best-measured repository's own practice.

Retired: the escalate-on-refusal exit (now apply-and-close for non-safety findings); the founder
hard-block on non-safety escalations (now a named default after a short wait); rounds spent by
dispatches that never ran (now zero-cost ledger lines); the single milestone-sized pull request
(now wave-sized, main moving with every green wave); narrative ledger entries and process-only
commits (now five lines, riding the product commit).

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
  tripwire, the one-page escalation brief.
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
- **Round-numbered artifact lineages** — except the round marker on persisted verdict filenames,
  which the budget check counts — (`-r14`, `-r15` cards; per-round frozen packages; rereview
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
