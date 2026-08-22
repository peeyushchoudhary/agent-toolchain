# Weekly improvement record

One material repository improvement each week, newest first. This is a **record**: entries accrete
and are never rewritten. Current tooling remains the authority for behaviour; each entry points to
the implementation it describes.

The three most recent entries are summarised on the front page; every entry, including those three,
is below in full.

**Why paths into `install/` appear here as code rather than as links.** This document is routed, so
its outbound links join the disclosure graph. A record links to everything it has ever touched, and
routing through it pulled `README.md`, the methodology, the execution loop, and two SKILL.md files
into the crawl at depth 3 and 4 — five warnings that are true of the route and caused entirely by
history. A record of past weeks is not a route.

## Week of 21 August 2026 — v5.0: the milestone runs itself, and a review rule was falsified

The plan could be scheduled but nothing ran it, and the rule governing who reviews what turned out
to be wrong against the record.

Execution is now a written procedure rather than one sentence naming a persona. Ten steps against
the real commands, with a test that parses every command out of the document and checks it against
the scripts' own interfaces — the page cannot drift from the tools the way the sentence it replaced
did. State is derived from git rather than held in a ledger, because a ledger is a claim and one
real ledger costs about 188,000 tokens to read. Dispatch is a continuous ready set rather than a
wave barrier, since the collision check already compares every pair and waiting for the slowest task
in a wave buys nothing.

Scope discipline became checkable. A card's declared write set is compared to the working tree
before the commit, not only after it: on real cards, 116 of 558 files had landed outside what the
card allowed, across 25 of 56 cards. An issue found but not owned now has somewhere to go, under a
rule that costs no model call — fix it only if it is inside your write set, names a criterion
already on your card, and you can show the command and its output; otherwise record it.

The review rule was falsified by its own record. It said one reviewer, never a panel, at every
stage. Across 1,051 real review artifacts, panel findings are not redundant — 21 blocking pairs with
a median anchor overlap of 0.20 — and the decisive cut is stage rather than width: design blocks at
0.74 per artifact against 0.09 at implementation. Width is now scoped by stage. The published
"two reviewers" optimum was deliberately not imported, because it measures the same lens twice on a
diff while a design panel is different lenses on a document.

Nine checkers were found to be inert or wrong against the real corpus, several of them shipped
earlier by this repository. The worst reported a clean exit on a repository whose specs it had never
read, because their filenames did not match the bound shape; that silence is now printed. A
criterion pattern that demanded bold emphasis hid 521 real criteria in one repository — the fourth
time that single pattern has been too strict. Every one was found by running against real
repositories rather than fixtures, which is now a stated requirement rather than a habit.

## Week of 21 August 2026 — the product-definition checks reach a boundary that fires

A checker nobody runs is a checker that does not exist. `spec_check.py` and `plan_waves.py` shipped
as commands, and a command is a thing a founder remembers to type on the days they are not busy. So
both now run in the `pre-push` hook — the one boundary in this toolchain with a measured record of
firing — and their findings block the push. Cost: a median 154 ms added to a push in a repository
holding 204 product documents, which is why they run over the whole tree rather than over the
pushed range; range-scoping would buy nothing a human can feel and would let a spec broken by an
edit outside `docs/product/` push clean. The numbers sit beside the guard they govern in
[github.md](github.md); `measurements.md` is already at its route word budget.

**The adoption guard is the load-bearing half.** A repository with no `docs/product/` gets silence —
not a warning, not a hint. Adoption is staggered, so most repositories are in that state on any
given day, and a gate that blocks a push in a repository that never opted in gets uninstalled;
after that it protects nothing anywhere, including the repositories that did opt in. The asymmetry
worth naming: `docs/product/` absent is "nothing to check". `docs/product/` present with the
checker missing is "the check did not run", which exits 2 and says so.

A milestone gained the one thing no feature spec can carry. A feature's suite proves the feature;
nothing proves the journey that crosses three of them, and that journey is why milestones exist. So
the milestone document declares one command under `## Cross-feature validation`, and moving it to
`status: shipped` is the claim that the command passed. `milestone_seal.py --record M<n>` runs it
from a clean tree and receipts the pass against HEAD's *tree* object — not the commit, so an amend
or a re-message does not throw away a ten-minute end-to-end run, while any real edit ends the
evidence. The receipt is written outside the repository: evidence that can travel in a clone lets
one machine's run seal another machine's push. Only the `-> shipped` transition is gated, so a
milestone already sealed costs later pushes nothing.

The nonce-receipt protocol in `references/junit-evidence.md` was read first and deliberately not
reused. It needs a start artifact and a 256-bit nonce because the thing it certifies is written by
a different process; here the recorder executes the command and reads its exit status directly, so
the only axis left to spoof is which content ran, and a tree sha closes that in one field.

## Week of 21 August 2026 — v4.2: the plan is scheduled, not described

A feature spec says what to build. Turning it into tasks was prose, and the two things prose cannot
do are schedule and collide. `docs/product/plans/F-<id>-<slug>.md` now carries the implementation
plan and the validation plan in one file — two files would let the tasks and the tests that justify
them disagree, and each would read complete alone. Tasks are blocks with `needs`, `writes` and
`covers`; nobody writes the waves down, because `plan_waves.py` derives them.

What it derives is worth less than what it refuses. On a real 51-task graph the dependency edges
alone yield 8 waves, and 37 pairs inside those waves declare overlapping write sets — two agents
sent at one file by a schedule that read clean. Across a milestone it is worse and invisible: on a
5-feature corpus the per-plan view reported zero findings and exited green while six cross-feature
pairs collided. The milestone is what scopes that, which is its third reason to exist after the
goal and the cross-feature journeys.

The check also had to survive its own advice. The first version compared same-wave pairs only and
told the planner to add a dependency edge — which moved the pair apart and silenced the finding
while both tasks still owned one file. On the real graph, 41 such edges silence all 37 collisions.
Every colliding pair is now compared, and a pair held apart by a dependency closes only when
`serialises:` says the shared ownership is deliberate. A check that recommends the thing that
defeats it is worse than one that says nothing.

The validation plan is smaller than expected, because the acceptance criteria already are the
classic test-case template. Only the cost decisions were missing: the test level, the paired
negative, the end-to-end set capped at three, and the absence claim — every criterion deliberately
left untested, with its reason. An `expected_red` field was designed and dropped; three of three
such literals in a real plan were already false when they were checked.

Extracting each shipped template and running the checker over it — which nobody had done — found a
parser bug in both. A trailing `# optional` survived into the value, so a flow list never reached
the branch that parses it. A test now extracts the templates and checks them, because the templates
are the one input guaranteed to be copied verbatim.

## Week of 21 August 2026 — v4.1: the product definition is checkable

The budget landed first and needed two corrections within a day. Its calibration had put the
product-thinking overrides ahead of the bookkeeping roots, so a workspace verdict filed under a
`plans/` subdirectory classified as product thinking — the exact class the budget bounds, escaping
through a directory name. And one ceiling could not do two jobs: 0.10 failed a new repository whose
first commit was a PRD, and failed a week holding one bug fix. Both are fixed. WARN at 0.15, FAIL at
0.30, and nothing fails below 500 classified lines. Back-tested against the collapse that earned
v4.0, the warning fires in the first week of the inversion and the failure in the week product
output fell 97%, while no healthy week trips either.

The rest is the half the budget could not reach. A budget bounds what the process costs; it says
nothing about whether the product was defined well enough to build. `references/specs.md` becomes
one PRD per repository and its feature specs, governed by a rule that outranks the rest of the file:
**a spec states what is true now.** It is updated in place, never appended to, and it never says what
it used to say — history is in git, *why* is in a decision record, and the append-only residue is a
front-matter key rather than a paragraph. `spec_check.py` enforces that structurally, because the
semantic version does not work: a broad word-match for history language fired 1,057 times across 164
real documents, mostly on domain vocabulary.

Two things were built as the cheap substitute rather than the thing asked for. The interactive HTML
explainer is a decision queue behind `--questions`, because a stdlib markdown renderer is ~540 lines
to display prose that is deleted on sight, while the one thing it could add — every open question
across a PRD and a dozen specs, in one place — is thirty lines. The approval interview is a single
clause: the agent answers its own question from the spec first, and asks only what survives. There
is no transcript. A comprehension check that stores its own results has become the thing it was
measuring.

`--surfaces` is the one with a measured failure behind it. In the record a PRD section headed "out
of scope" named eight modules and all eight were built — 229 endpoints, none reachable. A route
added in a diff must now appear in the Surface section of an approved feature spec.

## Week of 21 August 2026 — methodology v4.0: the budget binds

An eight-week external audit measured every repository the methodology reaches and found the
failure principle 8 was written to predict, in the one place v3 never looked: at itself. In the
largest repository the process share of committed churn ran 4% in week 27 and 75% in week 34, while
product output fell 97% and 73 of the last 100 commits were `docs`. Two unrelated repositories
crossed into breach in the same week — the week each adopted v3. No rule fired, because principle 8
was the only one of the eight with no mechanism behind it, while the review round count — a rule
that cannot be mechanized, since the tool is run by the party it binds — had received 1,085 lines
of Python.

v4.0 adds the mechanism. `ratio_meter.py` splits committed churn into product, product thinking,
and process, and fails the gate above a 10% process ceiling; it binds because no orchestrator can
inflate the product side without committing product code. `weekly_review.py` reports the trend,
since the failure is a slope rather than a bad day. The five caps v3 wrote as prose are now gate
enforced, reports stop being an artifact class, the ledger rotates at 500 lines, and a methodology
change may only be authored in a week that read in budget — which closes the loops where a stale
receipt bought a sweep that bought a round that bought a process-only commit.

Calibration is part of the change: run against the repository this methodology already cites as its
gold standard, the first meter read 0.45 by charging design plans and UI mockups to bookkeeping. It
now reads 0.02 there and 0.39 on the audited repository. A meter that cannot separate those two
teaches its operator to ignore it.

## Week of 17 August 2026 — methodology v3.1: outcome focus and the unattended founder

The v3.0 round cap held everywhere it was adopted, and the same measurement pass that proved it
found the next constraint: capped reviews escalated to a serialized human gate that did not drain,
narration grew faster than product, and cold per-dispatch sessions paid a ~133 KB boot 588 times
for nine commits. v3.1 replaces escalate-on-refusal with apply-and-close, gives every non-safety
escalation a named default action, caps ledger distillations at five lines, bans raw verdict dumps
and persisted prompts, states the long-lived controller session as the default, and lands work in
wave-sized pull requests. The installer now carries the operator grants ledger across installs, and
the vendored suite runs without it. Numbers in [measurements.md](measurements.md).

## Week of 10 August 2026 — methodology v3.0: the review budget

A two-week audit of actively developed repositories measured the v1.4–v2.1 machinery producing more
process than product: review rounds ran far past the written two-round stop-loss, workspaces filled
with re-serialized diffs of changes git already stored, and milestones stalled on card
preconditions. The numbers are in [measurements.md](measurements.md). v3.0 applies the
methodology's own mechanism-over-intention principle to its review loop:
`install/skills/execution-methodology/scripts/check_review_budget.py`
refuses a dispatch whose subject has spent its two review rounds and rejects the diff-snapshot and
restatement-packet artifact classes; the orchestrator applies a 20% growth tripwire that ends any
review expanding its subject.
Tasks default to a card-free light lane; the card validator warns on a 150-line card budget and a
ten-line inline limit for frozen values, and `--strict` — the gate mode — fails both; milestone
receipts carry process metrics so a process regression is triaged like any other. The methodology body shrank from 732 to about 410 lines, with
the JUnit-evidence and Codex-sandbox protocols moved verbatim into reference files and the v1–v2
changelog preserved alongside them.

## Week of 3 August 2026 — goal-bound execution with trustworthy evidence

The execution methodology (`install/skills/execution-methodology/methodology.md`) now binds each
implementation and review repair to one approved Goal Capsule, classifies findings before they can
become scope, and returns repeated causal failure to a human plan gate. Contract v2.1 also casts the
existing read-only reviewer in fresh design and plan modes before their approval gates. `PASS` is a
valid outcome; blocking findings need a reachable counterexample and artifact evidence, and one
correction plus one scoped rereview prevents an adversarial pass from becoming an endless debate.

Task-card validation contract v2 replaces shell command strings with direct `{cwd, argv}` processes
and accepts only exact `--rerun-tasks` as Gradle freshness evidence. Single-use JUnit receipts verify
post-boundary XML freshness and consistency and reject pre-existing or same-content XML, replay,
count mismatches, failures, errors, and skips; the exact uncached runner command establishes
execution.

`install/verify.sh` executes the published vendored suites and reports what each proved:
tests run, skips or not-tested status, failures, or inability to run. The installer also derives the
published skill roster from its declaration instead of maintaining a second count.
