# Execution methodology

How work travels from a product intent to a merged milestone. Authored once, rendered into every
repository, followed identically by Claude Code and Codex.

This document is the *sequence between* roles. It does not describe what a reviewer thinks or how a
developer implements — that is what the personas are for. It describes what must exist before a
stage may begin, and what must be true before it may end.

## Principles

Seven rules. Each one exists because its absence cost a measured amount of work, and each one is
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

**7. Execution is bound to one approved outcome.** The approved plan owns one Goal Capsule. Before
implementation or repair, a dispatch names the capsule criterion or invariant it advances and the
observable delta expected. Review discovers evidence; it does not silently redefine the product.
Every finding is classified before dispatch, and repeated causal failure returns to the existing
human gate rather than acquiring a new attempt identity.

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
    │               → architect, reviewed by domain specialists, then adversarial reviewer
    │
    ╞══════════════ GATE 1 — human approves the design
    ▼
PLAN                Goal Capsule · file structure · task decomposition
    │               FROZEN interfaces including payloads
    │               → planner, with contract-architect on boundaries, then adversarial reviewer
    │
    ╞══════════════ GATE 2 — human approves the plan
    ▼
TASK CARDS          one per task, generated from the plan, machine-checked
    │
    │   ┌─────────── unattended loop, per card ──────────────┐
    └──▶│  context → smallest safe slice → review → classify │
        │  → admitted repair → validate → commit             │
        └────────────────────────────────────────────────────┘
    │
    ▼
MILESTONE           release gate → sealed receipt → acceptance judgement
    │
    ╞══════════════ GATE 3 — human approves the merge
    ▼
                    merge commit, tagged
```

Between Gate 2 and Gate 3 the loop runs unattended. It stops early only for a blocker it cannot
resolve, a material ambiguity, same-cause recurrence after one independently reviewed repair, or the
human repair checkpoint described below. It does not stop to ask whether to continue when none of
those conditions is present.

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

Ambiguity is material only when the available readings change product acceptance, safety, authority,
an irreversible boundary, or the work needed to satisfy them. Material ambiguity returns to the
appropriate human gate. Otherwise, state one bounded assumption, do everything that does not depend
on it, and carry on. A vague request is not an implementation command or an automatic refusal: turn
it into a proposed Goal Capsule for approval.

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

**One Goal Capsule is frozen here.** It contains:

- the actor/user outcome;
- one primary byte-real, externally observable outcome observation;
- named safety, privacy, authorization, financial, and data-lifecycle invariants required to trust
  that outcome;
- named negative, compatibility, and adjacent-regression checks required at final acceptance;
- non-goals, prohibited claims, the solution/interface boundary, and allowed write boundary;
- known external facts, facts explicitly marked `UNKNOWN`, and the stop condition.

Cards reference the capsule's relevant criteria through their existing `goal`, `invariants`,
`tests`, `frozen_values`, `exclusive_writes`, and `stop_conditions`. They neither duplicate the
capsule nor add a schema field or materializer. One primary observation does not cap the number of
independent safety invariants or findings.

**Plan the smallest operationally real safe slice first.** Prove a byte-real path through production
boundaries before horizontal preservation work. Include only the compatibility and safety controls
encountered by that path, while naming adjacent-regression checks for final acceptance. Prefer an
existing or native primitive. A new abstraction is admitted only when the plan records what the
native primitive cannot satisfy; proof machinery with its own durable authority, persistence,
compatibility, recovery lifecycle, or reusable API is a new product boundary and returns to Gate 1.

### Pre-gate adversarial review

After domain-specialist review and before Gate 1 or Gate 2, cast the existing `reviewer` in design
or plan mode. Domain specialists remain additive: their focused judgement does not replace this
independent attempt to falsify the whole artifact. Existing implementation review stays unchanged.

Give a fresh, isolated, read-only `reviewer` only named artifact paths, never the author conversation
or rationale. The paths identify the artifact under review and the frozen specifications, criteria,
and invariants that govern it; do not include an author summary arguing for the proposed answer.
The reviewer tries to construct a reachable counterexample. `PASS` is valid; there is no finding
quota, and review cannot require a defect to be invented.

Freshness is a dispatch property. In Codex, dispatch the pre-gate review and scoped rereview with
`fork_turns: "none"`; another harness must use its equivalent fresh-thread primitive. Prompt wording
alone does not establish isolation. A post-code reviewer dispatch defaults to Implementation unless
Design or Plan is explicitly named, preserving existing implementation-review callers.

A blocking finding names the frozen criterion or invariant, a reachable trigger or state sequence,
the observable consequence, artifact evidence, severity, and the smallest correction or human
decision. Preferences, speculative future hardening, and invented requirements are non-blocking.
The reviewer reports the correction but never authors or applies it.

The author gets one correction and one scoped rereview of that correction and its causal area. The
rereview packet names the persisted original finding or report path, correction or diff path,
corrected artifact path, and governing frozen artifact paths; it excludes author conversation and
rationale. If the same causal problem recurs, the automatic loop terminates: Design recurrence
returns to Gate 1; plan recurrence returns to Gate 2. The scoped rereview cannot expand into another
correction round or a consensus loop. A changed outcome, claim, threat boundary, or governing
invariant routes to the appropriate human gate under the existing Goal Capsule rules rather than
being repaired as a review preference.

## The task card

Generated from the plan, one per task. The card is the implementer's entire world: it does not read
the plan, and it reads nothing the card does not name.

```yaml
id:                  # stable identifier, used in commits and the ledger
title:               # the card's name — one line, ≤ 72 characters, unique among sibling cards
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
                     # Java: Create|Retain: repo/path/Test.java :: fully.qualified.Test

gate_risk:           # bookkeeping artifacts this task touches (contract, manifest, taxonomy,
                     # inventory, registry) — these are what fail late in a full gate run
validation:          # direct {cwd, argv} processes, in order, that prove this task
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
- **An incomplete or invented schema.** Every current field must be present; unknown fields and
  misplaced path globs are findings, and strict validation rejects every such warning.
- **A Java test declaration that cannot execute exactly.** Its path must map to its FQCN, `Retain`
  must exist, an absent `Create` must be owned by `exclusive_writes`, and every declaration must
  have exactly one exact, non-wildcard Gradle `--tests` class filter. Every exact Java class filter
  must have exactly one declaration; prose-only `tests` entries cannot bypass this contract.

Validate twice without editing the card: `--strict --phase pre` before dispatch and
`--strict --phase post` after implementation. Pre-validation permits an owned declared `Create`
test to be absent. Post-validation requires that exact path/FQCN to exist and contain a JUnit test;
a class shell and a wildcard filter are both failures. It parses the source after removing comments
and strings, then verifies the real package and top-level class form the declared FQCN. Validation
entries are decoded once as direct processes with exactly `cwd` and `argv`. The Gradle `argv`
itself must contain the selector. `--rerun-tasks` is the only accepted Gradle freshness proof;
`clean`, `cleanTest`, qualified clean tasks, exclusions, properties, option operands, and every
other token do not count. Only `argv[0]` identifies the executable, so later arguments cannot lend
Gradle evidence. Shell strings, grouping
maps, pipelines, redirects, environment assignments, and compound commands are rejected rather
than approximated. Put necessary orchestration in a repository script with a shebang and invoke it
directly.

The same phases govern write-path existence. Pre-validation accepts an absent `exclusive_writes`
entry without warning only when it is a safe exact repository-relative file literal, which permits
strict validation before a new production or `Create` test file exists. A missing `Retain` Java file
still fails pre-validation. Post-validation requires every write entry and every `Create`/`Retain`
Java path to exist, then applies the Java source checks. A typo in an exact new-file literal is
indistinguishable from intentional creation at pre time and is therefore deliberately deferred to
the mandatory post check. Globs, metacharacters, directories, absolute paths, and escaping paths do
not receive the absence exception.

`forbidden_paths` has different existence semantics. A safe exact repository-relative literal that
is absent is a proven fence and produces no unmatched warning in either phase. An existing file,
directory, or matching boundary is also permitted; the validator enforces that it does not overlap
`exclusive_writes`, not that forbidden paths are generally absent. Unsafe, globbed, absolute, or
escaping absent expressions remain findings. If `frozen_values` repeats a higher migration version
that is paired to an exact forbidden migration filename, the mention is fencing evidence and does
not become intended migration drift. The exemption applies only to frozen mentions: unpaired higher
versions and operational mentions in instructions, tests, validation, or writes remain active.

None of these is a judgement call; all of them are a script. The first live card written under this
methodology carried three of them.

## The task loop

Per card, unattended:

1. **Acquire context** by running the card's recipe. Nothing else.
2. **Bind and implement the smallest safe slice.** Name the Goal Capsule criterion or invariant and
   the expected observable delta. Test first where it gives a concrete assertion: write the test,
   run it, watch it fail *for the stated reason*, then implement with existing/native primitives.
   Do not add speculative recovery branches for states the current design makes unreachable; assert
   or fail closed at the boundary. Reachable I/O, concurrency, retry, privacy, authorization, and
   partial-failure paths remain handled and tested. A test that has never been observed red proves
   nothing.
3. **Validate** with the card's commands, at the task tier (below).
4. **Report to a file** if you can write; return a short verdict — status, commits, one-line test
   summary, concerns. Judging personas cannot write, so they return findings and the orchestrator
   persists them.
5. **Review** by a non-editing judge, handed a diff *file*, plus any domain specialist whose
   invariant the diff touches.
6. **Classify every finding before dispatch.** Zero unclassified findings proceed. Record the exact
   capsule criterion/invariant, reachable input or state sequence, observable wrong consequence,
   evidence, category, causal class, disposition, and owner. Use these categories:
   - current-scope defect or candidate regression: repair in the current loop;
   - harness defect: freeze the candidate, repair and independently validate the harness separately,
     then rerun the unchanged candidate;
   - pre-existing defect: assign a separate owner; it still blocks when safety or acceptance is
     invalid;
   - invalid frozen assumption: return to Gate 2;
   - new outcome, threat, or claim: return to Gate 1 or Gate 2 according to the changed authority;
   - external fact: record `UNKNOWN` or block the claim; code cannot manufacture authority;
   - evidence/bookkeeping defect: correct the evidence without expanding product scope.
7. **Apply causal stop-loss and the repair checkpoint.** One independently reviewed repair is
   allowed for a causal mechanism. If that mechanism recurs, stop automatic repair and reopen Gate
   2; renaming the task, version, or attempt cannot reset it. Distinct findings do not share this
   causal counter, and safety review has no total finding cap. After two total ordinary repair
   dispatches, a third distinct repair also reopens Gate 2 for explicit human continue/replan
   authority. It is never automatically deferred or treated as non-blocking.
8. **Re-review each admitted repair** with a scoped judge. Every finding is repaired, routed to a
   human gate, or parked with a written owner and ruling; silent discard is forbidden. A changed
   user outcome, claim, or threat boundary returns to Gate 1. A first newly exposed composition
   repair inside the capsule may proceed; another composition repair reaches the same human
   checkpoint, while same-cause recurrence returns to Gate 2 immediately.
9. **One full-diff review before the commit gate.** Not scoped — the whole change, once.
10. **Independent test judgement, local E2E, and final acceptance remain mandatory.** A repair
    checkpoint changes dispatch authority, never the verdict of a test, review, safety check, or
    acceptance judgement.
11. **Commit** the code and the distillation together.

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

For JUnit, console output is not the count. Create a new start artifact immediately before the test
task with `python3 start_junit_run.py --results RESULT_DIR --output START.json`; it contains a 256-bit nonce,
timestamp, exact result path, and hashes of any direct XML already present.
Run the task with cache bypassed, then invoke `python3 verify_junit.py --results RESULT_DIR
--start-receipt START.json --expect FQCN=N [--expect FQCN=N ...] --output RECEIPT.json`.
Every direct XML file must have both mtime and ctime strictly after the start boundary. The verifier
records the start hash and nonce and creates a consumption marker, so a valid pre-existing result or
a reused run receipt cannot certify a later invocation. Each expected class must have exactly its
declared testcase count—not merely a nonzero or aggregate minimum. JUnit failures, errors, and
skips all fail evidence verification. Cleaning remains
good hygiene, but it is no longer the freshness security boundary.

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

### Non-normative execution budgets

At Gate 2, the founder may set milestone envelopes for wall span, agent compute, processed tokens,
or completed turns. These are telemetry and dispatch-authority signals, not acceptance criteria. No
universal absolute budget follows from this methodology.

- At half of an approved envelope with no first primary outcome-observation green, record a mission
  checkpoint and verify that current work still maps to the Goal Capsule.
- At the full envelope, pause automatic dispatch for human continue/replan authority.
- Same-cause recurrence and the third-distinct-repair checkpoint apply regardless of consumption.
- A budget can never turn a blocker into a backlog item, limit distinct safety findings, or alter a
  test, independent review, full-diff review, local E2E, safety, or acceptance verdict.

Each checkpoint records the referent and measurement method as well as wall span, agent-hours,
processed/output tokens, turns, finding categories, repeated causal classes, repair dispatches, and
whether the primary observation is green. The numbers are diagnostic; they confer no authority.

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
| Pre-Gate 1 adversarial review | fresh read-only `reviewer`, design mode |
| Plan | `planner`, with `contract-architect` on durable boundaries |
| Pre-Gate 2 adversarial review | fresh read-only `reviewer`, plan mode |
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

### v1.5 — exact card schemas and executed-test evidence

- The validator now covers all seventeen task-card fields, reports unknown fields, and makes strict
  validation an exact-schema check while preserving named diagnostics for obsolete fields.
- Java tests have one-to-one path/FQCN `Create` and `Retain` declarations and exact Gradle class
  filters, plus explicit pre/post phases so one immutable card validates both phases.
- The shared JUnit result verifier binds the exact direct-XML directory to a single-use
  nonce/timestamp start boundary, proves required classes and counts from XML, rejects ambiguous or
  inconsistent results, and emits a new JSON receipt bound to that start artifact.
- JUnit evidence detects accidental pre-existing, same-content, unchanged, malformed, replayed,
  failed, errored, skipped, or count-inconsistent results. It does not detect a cache restore that
  writes plausible valid XML after the boundary. Exact runner rerun settings prevent cache use;
  Gradle requires exact `--rerun-tasks`. It is **not tamper-resistant** against a deliberate local
  writer controlling both XML and evidence files; it is not hostile-writer attestation.

### v1.6 — one approved outcome and causal repair authority

- Plans now freeze one Goal Capsule, and cards reference it through existing fields without a new
  schema or materializer.
- Every dispatch names a criterion or invariant and observable delta; material ambiguity returns to
  a human gate, while bounded non-material ambiguity proceeds under a recorded assumption.
- The first slice is byte-real and uses native primitives where sufficient. Impossible states fail
  closed without speculative machinery; reachable failure, concurrency, retry, privacy, and
  authorization paths remain tested.
- Findings are classified before repair. Same-cause recurrence after one independently reviewed
  repair reopens Gate 2, and a third distinct ordinary repair requires human continue/replan
  authority. Distinct safety findings remain uncapped and can block release.
- Optional budgets trigger mission review only. Independent review, full-diff review, test
  judgement, local E2E, and final acceptance are unchanged.

### v2.0 — direct validation processes

This is a major version because v1 scalar validation entries and v2 direct-process mappings are
operationally incompatible in both directions; treating the change as minor would let adopted v1
repositories receive only a warning while their cards fail validation.

- Every validation entry now names exactly one working directory and argument vector. Shell text,
  grouping maps, and legacy scalar commands are rejected instead of partially interpreted.
- The validator decodes that structure once and shares one immutable command record across Gradle,
  Java selector, pytest, cacheability, module-placement, migration, and gate-risk checks.
- Executable evidence comes only from `argv[0]`; shell-looking later arguments are data and cannot
  lend Gradle or pytest execution evidence.
- The exact rejected shell basename set is `sh`, `bash`, `dash`, `zsh`, `ksh`, `mksh`, `csh`,
  `tcsh`, `fish`, `ash`, `pwsh`, `powershell`, `cmd`, and `cmd.exe`. Unlisted wrappers remain
  direct processes and never lend evidence about an executable nested in their later arguments.
- v1 cards are invalid under v2 because their validation items are scalar shell strings. v2 cards
  are invalid under v1 because the old validator flattens their mappings instead of decoding direct
  processes; this is an intentional bidirectional incompatibility, not a rolling compatibility
  mode.
- Migration moves a leading working-directory change into `cwd`, writes the executable and each
  argument as separate `argv` values, and splits multiple processes into separate entries. If
  orchestration is indivisible, put it in a repository script with a shebang and invoke that script
  directly. Then rerun strict pre- and post-validation.
- Repository-relative `argv[0]` values containing `/` resolve from `cwd` and must stay within the
  repository. They must name an executable regular file and, for direct text scripts, start with a
  byte-zero `#!` shebang. Bare PATH names remain unchecked and absolute executable behaviour is
  unchanged.
- Exact nested Java selectors normalize `$` to `.`, but only the complete member-type chain in the
  containing source (with comments and strings removed) or its exact immutable `Create` declaration
  establishes existence. Capitalization never does.

### v2.1 — bounded pre-gate adversarial review

- The existing read-only `reviewer` now has design and plan modes before Gate 1 and Gate 2; no
  persona, schema field, hook, or cross-harness default was added.
- Each pre-gate reviewer starts fresh with named artifact paths and no author conversation or
  rationale. Domain specialists remain additive, and implementation review is unchanged.
- `PASS` is valid and no finding quota exists. Blocking findings carry reproducible evidence tied
  to a frozen criterion or invariant; preferences, speculative hardening, and invented requirements
  cannot block.
- One author correction and one scoped rereview are permitted. Same-cause recurrence returns design
  to Gate 1 or plan to Gate 2, terminating the automatic review loop.

### Read-only gate execution in Codex

A write-producing gate is never run directly against the source referent by a read-only
`test-judge`. The controller freezes writers and selects a committed tree or `HEAD` plus a canonical
manifest covering path, type, mode, content/link hash, base SHA, tracked deletions, and non-ignored
untracked files. It materializes a manifest-equal standalone copy below a fresh temporary root,
without a source `.git` relationship, shared object store, hard links, ignored outputs, unresolved
external objects, or escaping symlinks.

After comparing the source and copy manifests, the controller supplies a custom inner permission
profile. Because the outer judge is read-only, it requests approval for the **exact sandbox-launch**
command only. The approved nested sandbox launch is:

```text
env CODEX_HOME=<temporary-home> codex sandbox -p gate -P copy-write -C <copy> -- <exact gate argv>
```

Approval moves only the launcher outside the outer boundary; the gate never runs unsandboxed. The
launcher immediately enters the inner profile, which grants source read, copy write, and network
disabled.

The evidence names the referent and manifest hash, sandbox and gate commands, exit code, verbatim
failures, counts/skips, and the unchanged-source recheck. Ambiguous identity, a manifest mismatch,
nested-sandbox failure, cached/zero/skipped execution, a required bypass, or failure to remove the
exact temporary root blocks sealing. The judge remains read-only; the standalone copy is the only
writable boundary. Plain nested execution cannot widen the outer sandbox, and plain unsandboxed gate
execution is forbidden. Exact `--rerun-tasks` is the sole Gradle freshness flag—`cleanTest` is not.
