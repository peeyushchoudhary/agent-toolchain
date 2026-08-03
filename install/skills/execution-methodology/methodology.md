# Execution methodology

How work travels from a product intent to a merged milestone. Authored once, rendered into every
repository, followed identically by Claude Code and Codex.

This document is the *sequence between* roles. It does not describe what a reviewer thinks or how a
developer implements — that is what the personas are for. It describes what must exist before a
stage may begin, and what must be true before it may end.

## Principles

Six rules. Each one exists because its absence cost a measured amount of work, and each one is
enforced by a mechanism rather than by intention wherever a mechanism is possible.

**1. Evidence binds to a tree, and proves execution.** A passing gate that does not name a commit, a
tree, and the list of stages that ran certifies nothing — an unbound `PASS` is one character away
from a `FAIL` and cannot be distinguished from a run that skipped half its checks.

Binding is not sufficient. A check must prove it *ran*, not merely that it succeeded: a build tool
reporting `UP-TO-DATE` and `BUILD SUCCESSFUL` with zero tests executed is a green that certifies
nothing, and it exits 0. Force execution, and count what ran from the machine-readable results rather
than from a console line — many test runners print no summary at all, so a count read off a log is
invented.

**2. There is no flag choice.** A checker has one canonical invocation, with maximal strictness
baked in, and it rejects arguments. A checker whose strictness is chosen at the call site will be
invoked at its weakest setting eventually, and green will be indistinguishable from unchecked.

**3. A builder never approves its own work, and a judge never authorizes a merge.** Judging roles
cannot edit — by tool restriction, not instruction. And their verdict is a finding to triage, never
an authorization: language models judging conformance show high false-negative and high
false-positive rates *simultaneously*. Deterministic gates are the only gates.

The restriction is on *modifying the work*, not on *acting*. `test-judge` therefore keeps a shell:
it cannot run a gate without executing one, and the first trial's costliest failures were all
unexecuted greens — a cached `UP-TO-DATE`, a `--tests` filter matching nothing, a wrapper's exit
code standing in for a verdict. A judge that must take someone else's word for what the gate printed
is not a judge. So `Write`, `Edit`, and `NotebookEdit` stay blocked for every judging role, execution
stays available to the one whose job is execution, and on Codex it runs read-only sandboxed. State
the exception; do not let it spread. No other judging persona gets a shell, and none of them gets an
editor.

**4. Context is acquired by recipe, not pasted.** Every dispatched agent receives paths and
commands, not file contents. An orchestrator that reads full reports inline re-reads every one of
them on every subsequent turn, and that single habit costs more than every model-selection decision
combined.

Reports therefore live in files and dispatches carry paths — with one exception that follows from
principle 3: **a judging persona cannot write, so it cannot write its own report.** A judge returns
its findings as its return value and the orchestrator persists them. That costs the orchestrator one
read per review, which is the price of the no-edit guarantee and is worth paying. Do not resolve the
tension by granting judges a write tool.

**5. Every stop is a resumable boundary.** A quota pause, a crash, and a context limit are operating
conditions, not incidents. Work is checkpointed at each completed step, and nothing partial survives
unlabelled.

**6. Scope is drained, not deferred.** A parked item without an owning milestone is scope loss
wearing a hat. Deferrals live in a register that a milestone can fail against.

## The chain

Seven artifacts, three human gates. Nothing downstream may begin until its input exists.

```
PRODUCT SPEC        why this exists, who it serves, where it stops
    │               → product-steward
    ▼
FEATURE SPEC        scope · user stories · behaviour · edge cases
    │               horizontals · acceptance criteria · the WHY
    │               → product-steward
    ▼
DESIGN              structure, boundaries, invariants at risk
    │               → architect, reviewed by domain specialists
    │
    ╞══════════════ GATE 1 — human approves the design
    ▼
PLAN                file structure · task decomposition
    │               FROZEN interfaces including payloads
    │               → planner, with contract-architect on boundaries
    │
    ╞══════════════ GATE 2 — human approves the plan
    ▼
TASK CARDS          one per task, generated from the plan, machine-checked
    │
    │   ┌─────────── unattended loop, per card ──────────────┐
    │   │  acquire context → implement → review → fix ×N     │
    └──▶│  → validate → commit (code + distillation)         │
        └───────────────────────────────────────────────────┘
    │
    ▼
MILESTONE           release gate → sealed receipt → acceptance judgement
    │
    ╞══════════════ GATE 3 — human approves the merge
    ▼
                    merge commit, tagged
```

Between Gate 2 and Gate 3 the loop runs unattended. It stops early only for a blocker it cannot
resolve, an ambiguity that prevents progress, or a fix loop that hits its cap. It does not stop to
ask whether to continue.

**A report is not a request.** Reporting at a milestone and pausing for a reply are different acts,
and conflating them is how an unattended loop becomes an attended one without anyone deciding to
change it. Report, then keep going. The founder reads a milestone report to stay informed, not to
issue a permission the methodology never asked for — and a loop that halts after every report has
silently converted each milestone into a fourth gate.

Earned rather than assumed: in the milestone that produced this paragraph the founder typed
"proceed" three times, each against a queue already decided, already scoped, and blocked on nothing.
None of the three carried information. The cost is not the typing — it is that work sat idle waiting
for it, and that the founder had to track whether an agent was working or waiting.

The test to apply before stopping is to **name the decision**. If it is one only the founder can
make — one of the three gates, a spend, an outward-facing or irreversible action, or a genuine fork
where the readings lead to materially different work — stop and ask it plainly. If it is "confirm I
should carry on with what we agreed", that is not a decision and there is nothing to ask. Proceed,
and record it in the next report.

Non-blocking ambiguity is handled the same way: do everything that does not depend on the answer,
state the assumption, and carry on. The question is asked where the work actually forks, not where
the uncertainty was first noticed.

### Product spec

`docs/product/specs/<area>.md` — owned by `product-steward`, authored with the founder.

Why this exists and who it serves. The scope boundary, stated as much by exclusion as inclusion.
The actors and what each is authorized to do. Success criteria that could be checked by someone who
did not write them. It does not contain screens, schemas, or technology.

### Feature spec

`docs/product/specs/F-<id>-<slug>.md` — owned by `product-steward`.

- **The WHY** — the problem, and what happens if it stays unsolved. First, not last.
- **Scope** — in and out, explicitly.
- **User stories** — actor, action, outcome.
- **Behaviour** — what the system does, in the acceptance-criteria form below.
- **Edge cases** — empty, first-run, concurrent, partial-failure, permission-denied, and whatever
  the domain adds. A feature spec with no edge-case section is not finished.
- **Horizontals** — the cross-cutting obligations this feature inherits whether or not anyone
  remembers them: tenancy and isolation, authorization, audit, money handling, personal data,
  retention, accessibility, localisation, and runtime cost. Each is either addressed or explicitly
  declared not-applicable with a reason. Silence is not an answer.
- **Acceptance criteria** — written so that each one names a trigger, a precondition, and an
  observable result. "When a guardian with no active enrolment opens the fee page, the system shows
  the dues-cleared state and offers no payment action." Criteria in this form become test names
  without translation.

### Design

`docs/superpowers/specs/<date>-<topic>-design.md` — owned by `architect`, reviewed by whichever
domain specialists the repository defines.

Structure, module boundaries, dependency direction, and — the section that earns the gate — **which
existing invariants this change puts at risk, and what fails closed if it is wrong.**

### Plan

`docs/superpowers/plans/<date>-<feature>.md` — owned by `planner`, with `contract-architect` on
anything crossing a durable boundary.

File structure before task decomposition. Then tasks, each one the smallest unit that carries its
own test cycle and is worth a fresh reviewer's gate.

**Interfaces are frozen here, including payloads.** A plan that freezes route names but not request
and response shapes hands the implementer an invention it will make silently and a consumer will
discover later.

## The task card

Generated from the plan, one per task. The card is the implementer's entire world: it does not read
the plan, and it reads nothing the card does not name.

```yaml
id:                  # stable identifier, used in commits and the ledger
goal:                # one sentence — what is true after this task that was not before
persona:             # developer | senior-developer — which persona implements this card,
                     # decided by the planner, not at dispatch

prerequisites:       # task ids that must be complete
exclusive_writes:    # paths ONLY this task may write — the parallelism contract
forbidden_paths:     # paths that must not change, even incidentally

context_acquisition: # a numbered recipe the agent RUNS, in order. Not prose.
                     # 1. the repository's context command for this lane
                     # 2. the route index — this lane's row only
                     # 3. the binding invariants file
                     # 4. named lessons sections
                     # 5. relational orientation ONLY if relationships are unclear
                     # Read nothing else unless this card names it.

frozen_values:       # verbatim, never re-derived: signatures, payload shapes, event names,
                     # formats, identifiers, migration version. Inline what must not be paraphrased.

invariants:          # what must remain true — with what fails closed if it does not
instructions:        # the work
tests:               # the specific tests to write, and the pattern to follow

gate_risk:           # bookkeeping artifacts this task touches (contract, manifest, taxonomy,
                     # inventory, registry) — these are what fail late in a full gate run
validation:          # the exact commands, in order, that prove this task
stop_conditions:     # what makes this task stop rather than infer
handoff:             # who receives the report
commit_subject:      # the exact commit subject line
```

**Inline what must be verbatim; retrieve what is stateful.** A payload shape must be inlined,
because a retrieval step can paraphrase it wrong. Branch state, ledger head, and index freshness
must be retrieved, because they cannot be frozen into a document written yesterday.

### Cards are machine-checked before dispatch

A card is an assertion about the repository — that these paths exist, that these tests exist, that
these commands prove something. Assertions rot, and a wrong card is expensive precisely because
everything downstream trusts it.

Run the card validator before dispatching. It catches, at minimum:

- **A named test that does not exist.** The worst failure the card format allows: a test filter
  matching nothing is silently ignored by the build tool, which then reports success. The card claims
  to prove an invariant and executes nothing.
- **A validation block that can be satisfied from cache**, and so can pass without running.
- **`exclusive_writes` contradicted by `forbidden_paths`** — a card that cannot be completed as
  written.
- **A frozen migration version that no longer matches the tree.**

None of these is a judgement call; all of them are a script. The first live card written under this
methodology carried three of them.

## The task loop

Per card, unattended:

1. **Acquire context** by running the card's recipe. Nothing else.
2. **Implement.** Test first where the acceptance criteria give a concrete assertion: write it, run
   it, watch it fail *for the stated reason*, then implement. A test that has never been observed
   red proves nothing.
3. **Validate** with the card's commands, at the task tier (below).
4. **Report to a file** if you can write; return a short verdict — status, commits, one-line test
   summary, concerns. Judging personas cannot write, so they return findings and the orchestrator
   persists them.
5. **Review** by a non-editing judge, handed a diff *file*, plus any domain specialist whose
   invariant the diff touches.
6. **Fix rounds**, each ending in a scoped re-review, capped at five. Past the cap the failure is
   structural: stop and surface it. Every finding is either fixed or parked with a written ruling —
   silent discards are forbidden.
7. **One full-diff review before the commit gate.** Not scoped — the whole change, once.
8. **Commit** the code and the distillation together.

### Why the full-diff pass is not optional

A scoped re-review reads only the fix delta. That is correct for cost and correct for focus: it
verifies the fixes and cannot wander. But it is *structurally blind* to a defect sitting in the
original work that no fix round happened to touch — and such a defect can collect any number of
green scoped verdicts without ever being looked at.

This is not hypothetical. On this methodology's first live task, three judges returned green scoped
verdicts across three rounds while a reachable duplicate-send path sat in code the fix rounds never
touched. The full-diff pass found it, along with a fix whose guarantee no test constrained.

Scoped per round, full-diff once before commit. The second does not replace the first.

### On tests

The implementer's own tests confirm the implementer's own understanding. They are necessary and they
are not sufficient. What actually catches damage is the **pre-existing** suite — so every task
reports pass-to-pass breakage explicitly, and a task that turns a previously-green test red has not
passed, whatever its new tests say.

Where a task's correctness is genuinely subtle, the tests are written from the acceptance criteria
by an agent that has not seen the implementation, before the implementer starts.

## Validation tiers

A full release gate is not a per-task instrument. Running one per task is how a plan takes a week.

**Per task** — minutes. The red/green cycle with the failing output quoted. The targeted tests named
on the card. The lane's area check. Plus the cheap verifier owning each artifact named in
`gate_risk`: contract verification, manifest checks, taxonomy, inventory, route conformance. Those
verifiers exist precisely so that the failures that surface an hour into a full gate surface in
thirty seconds instead.

**Per card, at the commit boundary** — `test-judge` runs the card's gate and reports what it printed.
Until it does, **the implementer's numbers are a claim, not a result.** They are worth having — an
implementer that ran its own suite catches most things — but a builder reporting its own gate is the
one measurement nobody else took, and it is the shape every silent pass in this methodology's history
has had. `test-judge` is Haiku at low effort and holds Bash precisely so this costs one cheap call
per card rather than an argument.

It states the **referent** with the number: which tree (HEAD or working), which interpreter, which
command. A count without a referent cannot be compared with another count, and two correct
measurements of different objects read exactly like a disagreement. Where its figure and the
implementer's differ, the difference is itself a finding — usually a referent, occasionally a defect,
never something to average.

**Per milestone** — once. The full gate, run by a non-editing judge that reports the gate's own
verdict line verbatim rather than a wrapper's exit code, and cannot fix what it finds. Then the
acceptance judgement against that exact commit.

**A gate pass authorizes nothing.** Not deployment, not provider activation, not a production write.

## The ledger

Two tiers. They are different artifacts and only one of them is durable.

**Plan workspace** — git-ignored, one directory per plan. Holds that plan's recovery ledger, cards,
reports, and review packages. Its only job is to survive compaction: after a context reset, the
workspace and the commit log are trusted over recollection. It is deleted when the plan finishes.

**Program ledger** — tracked, append-only, never deleted. The durable record of what was built,
what was decided, and what remains owed. Where there is no CI, this and the commit history are the
audit trail.

### Promotion is a gate, not a habit

A plan may not be marked finished, and its workspace may not be deleted, until each task's
**distillation** has been appended to the program ledger and committed. The distillation carries
four things, because each one names a channel that has demonstrably lost information:

- **Interfaces produced that later tasks consume.** Ports, types, events, endpoints. When this
  channel fails, a later plan re-derives a contract by hand and gets it wrong.
- **Deferrals, each with an owning milestone.** A parked item with no owner is invisible by
  construction; some of them mature into critical defects.
- **Verification actually run, verbatim — including what was not run.** The commands and their real
  output. "Complete" beside "gate not run" is a contradiction the ledger must be able to express and
  a milestone must be able to fail on.
- **Surprises and corrected assumptions.** What the task found that the plan got wrong. A ledger
  containing no record of anyone ever being wrong is not a record of what happened.

**The distillation rides in the task's own commit.** Not a separate bookkeeping commit, not a batch
at the end of a phase: the entry and the tree it describes enter history together, so every line is
attributable to a tree and a time.

## Stopping and resuming

Work stops in the middle. Design for it.

- **Checkpoint at each completed step**, so an interruption costs one step rather than a plan.
- **A partial state is labelled or it is discarded.** Where a checkpoint must be committed
  mid-task, it is marked unverified in its subject and body, states plainly what was in flight, and
  says it must be reviewed or discarded rather than merged.
- **A dirty tree or an unverified head blocks the next task** until it is quarantined or discarded.
  The most expensive recoveries begin with work that was neither.
- **Deleting a plan workspace is a completion action**, permitted only after promotion.

### An orchestrator cannot wait

An agent holding a loop has no way to block on a long-running command. It launches a fifteen-minute
test run, its turn ends, and nothing wakes it when the run finishes. This is a property of the
harness, not a failure of judgement, and it has two consequences that must be designed around:

- **Poll, or arrange to be woken.** Either the loop-holder waits on the process itself before ending
  its turn, or whoever dispatched it watches for completion and resumes it. Launch-and-return with
  no arrangement is how a loop appears to die while it is merely asleep.
- **Silence is not death.** An agent that has not reported is not thereby finished, failed, or gone.
  Confirm before acting on that conclusion — and note that a resumed agent does not stream to its
  transcript, so an empty transcript proves nothing.

Getting this wrong has a specific and expensive shape: concluding a live writer had died, dispatching
a second writer onto the same exclusive write set, and breaking the one serialization rule the
orchestrator personally owns.

## Casting

The methodology says when; the persona pool says who, on which model, with which tools. One
orchestrator holds the loop and serializes every write to a shared interface, manifest, registry, or
generated artifact.

| Stage | Role |
|---|---|
| Product and feature specs | `product-steward` |
| Design | `architect` + domain specialists |
| Plan | `planner`, with `contract-architect` on durable boundaries |
| Locating code | `scout` |
| Implementation | `developer` or `senior-developer`, the card's `persona`, chosen by the plan |
| Task review | `reviewer` + any specialist whose invariant the diff touches |
| Gate execution | `test-judge` |
| Milestone judgement | `acceptance` |
| Route, README, lessons | `docs-steward` |
| Holding the loop | `chief-of-staff` |

**Parallelize reads; serialize writes.** Scouts, reviewers, and gate runs fan out freely. Writers do
not: concurrent implementers are capped, file-disjoint by their `exclusive_writes`, and never
concurrent on a shared artifact.

### Who fixes prose, and the line that is easy to get wrong

Prose describing a change is the highest-risk content in a diff — see the entry below on what earned
that. It does not follow that prose is cheap work to route away.

The split is by **who still has to make the judgement**, not by whether the file is code:

| The change | Role | Why |
|---|---|---|
| Prose asserting what code does, written by whoever changed that code | the card's implementer | The claim and the change are one act. Handing the sentence to someone else means they must re-derive the behaviour, which is the expensive half done twice. |
| Route, README, lessons, architecture pages, doc drift carrying no behavioural claim | `docs-steward` | Nothing to get wrong about execution. |
| Applying a correction a review has already specified, with the wording named | `docs-steward` | The judgement was made by the reviewer. What remains is transcription, and transcription is bounded work by definition. |

That third row is the one that gets mis-routed upward. A review that says *"this sentence is false;
here is what is true"* has already spent the judgement; sending it back to the implementer buys
nothing and costs the expensive tier. A review that says *"this sentence is false"* and stops has
not, and that goes back to whoever changed the code.

The test to apply: **can the fix be applied without reading the code?** If yes, it is transcription.
If the fixer must open the source to know what to write, it is implementation wearing prose.

**An absence claim is never transcription**, however precisely the review specified it. A sentence
saying what a check does *not* cover, what a guard does *not* catch, or which cases are *not*
handled can only be confirmed by reading the source — a supplied measurement of an absence is
someone else's reading, and this methodology's own history is mostly wrong absence claims made
confidently. The correction may look like three named lines; establishing that those three lines are
now right is the whole job.

Earned: a gap paragraph was twice rewritten from a specified correction without re-deriving, and was
wrong both times — the second time by *affirmatively denying* a third uncovered surface existed, so
the next card was scoped from it and inherited the denial.

## Landing

Small, single-purpose commits during the plan. One milestone-sized pull request at the end, merged
with a merge commit and tagged, because where there is no CI the commit history is the audit trail.
Agent work is never force-pushed. The front-page README is updated with the change, not after it.

Committing, pushing, opening a pull request, and merging are founder decisions. The methodology
prepares them; it does not take them.

## What changed, and what earned it

A rule that was assumed and a rule that cost a gate run are not worth the same, and the difference
is invisible once both are prose. This records which is which, so a later revision knows what it is
allowed to cheapen.

### v1.1 — after the first full trial

Earned. Every item below came from something that actually went wrong.

- **`test-judge` keeps a shell, stated as an exception** (principle 3). Unexecuted greens were the
  single largest failure class in the trial: a cached `UP-TO-DATE` reported as a pass, a `--tests`
  filter silently matching nothing, a wrapper's exit code masking a failing gate.
- **A full-diff review before the commit gate, not a scoped one.** Severity across review rounds
  looked like it was falling monotonically; it was not. The two rounds that broke the curve were
  both full-diff passes. Scoped review flatters itself.
- **Cards are validated before dispatch, and the orchestrator refuses otherwise.** The trial's first
  card named a test class that does not exist — which Gradle ignores silently and reports green —
  omitted the test proving its own invariant, and mandated an invariant its own stop condition
  forbade satisfying.
- **`exclusive_writes` must be proven disjoint from in-flight cards.** The orchestrator dispatched
  two concurrent writers onto one write set. It caught itself; nothing structural stopped it.
- **An orchestrator cannot wait.** Agents cannot block on long-running commands — they end their
  turn and must be resumed. Twice this was misread as a stalled agent.

Removed, because the trial showed them to be cost without benefit.

- **`allowed_reads`** was never enforceable. An agent must read to orient, so the validator could
  only ever warn, and the field became a thing to satisfy rather than a constraint.
- **`adversarial_probes`** duplicated by role what `reviewer` and the validator personas already do.
- **`tier` renamed to `persona`**, which is what the field always meant.

Still assumed, and not yet tested by anything.

- The three human gates sit at the right places. Only the back half of the chain has been run
  end to end; the design and plan gates have not been exercised on a real feature.
- The two-tier ledger's promotion gate holds under a stop that happens mid-task rather than between
  tasks.
- The validation tiers are calibrated. They have been used, but never in a case where the cheaper
  tier would have missed something the dearer one caught.

Known wrong and not yet fixed: the trial's own distillation in the project ledger records four fix
rounds. There were five.
