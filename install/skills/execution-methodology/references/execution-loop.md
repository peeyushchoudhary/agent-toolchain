# The chief-of-staff operating loop

The methodology said "hand the approved plan to `chief-of-staff`" in one sentence and then described
the instruments — waves, cards, the drift phase, the commit check, the seal — without ever saying
who runs which one, when, or what to do with each exit code. This file is that procedure. It is
written for the `chief-of-staff` persona and it is the only place the loop is defined.

Everything below runs between the plan gate and the merge gate, unattended. Every command writes
nothing to the repository, costs zero model calls, and exits `0` clean, `1` findings, `2` the
question could not be asked. Exit `2` is never a pass and is never retried blindly: it means the
loop and the repository disagree about what exists.

## 0. What the orchestrator may write

The `chief-of-staff` persona declares `writes: ledger, task cards, and reports only`. That is the
whole surface. It does not implement, does not judge, and does not repair a one-line finding itself
— a fix it makes is a fix nobody reviewed, and it lands in a context that will be compacted rather
than in a diff that will be reviewed.

## 1. State is derived from git, never held in the ledger

**The loop never reads the ledger to find out where it is.** One real ledger measured 745 KB —
about 186,000 tokens, 10,940 lines, 702 headings, sessions S-1 to S-73. All 29 cards of that
milestone together are about 319,000 tokens, so a single ledger read costs 58% of the entire card
corpus, and the loop would pay it at every dispatch decision. It is also written by the party it
would bind, so what it records is a claim; a commit is a fact.

Status is one command, recomputed every time:

```bash
plan_waves.py --root . --milestone M<n> --since <seal-rev> --json
```

It reads the plans and `git log <seal-rev>..HEAD`, resolves each commit subject to a qualified task
id (`F-9/T1`), and returns every task as `done`, `duplicate`, `in-flight`, `ready` or `blocked`,
plus `unclaimed_commits` for commits naming a task no plan declares any more. `complete` is a JSON
**key, not an exit code**: a half-built milestone has no findings and exits `0`. After a compaction,
after a crash, after a founder interrupt, this one command rebuilds the whole picture. Nothing is
carried forward that this cannot recompute.

**What the ledger is still for**, given the loop must never read it to know where it is:

- **rulings that git cannot hold** — a parked finding and why it was parked, a founder decision, a
  scope change accepted at the plan gate;
- **the distillation** promoted at the end of the milestone, which is what the next plan reads
  instead of re-deriving the same interface decisions by hand;
- **the pointer set** — report paths, verdict paths, diff ranges — never their contents.

It holds no task status, no done-ness, no next-task decision, no in-flight list. In-flight is passed
as `--in-flight` on the command line precisely because it is the one fact git cannot state, and
writing it to a file would recreate the thing this replaces. The ledger is a current-state document
like every other product document: updated in place, read by its `## Status` head, never appended to
until it is 10,940 lines long.

## 2. The loop

| # | Step | Command | Cast |
|---|---|---|---|
| 0 | resume / status | `plan_waves.py --milestone --since --json` | `chief-of-staff` |
| 1 | select | `plan_waves.py --milestone --since --ready --in-flight` | `chief-of-staff` |
| 2 | dispatch | `validate_card.py --phase pre` | `developer` / `senior-developer` |
| 3 | per-turn drift | `validate_card.py --phase mid` | `chief-of-staff` |
| 4 | validate | card `validation` argv + `verify_junit.py` | `test-judge` |
| 5 | review | `check_review_budget.py --next` | `reviewer` + `test-judge`; see §4 |
| 6 | commit check | `plan_waves.py --milestone --commit` | `chief-of-staff` |
| 7 | deferrals | `spec_check.py --deferred` | `chief-of-staff` |
| 8 | coverage | `trace_check.py --evidence --commit` | `test-judge` |
| 9 | seal | `milestone_seal.py --record` | `chief-of-staff`, then `acceptance` |

### Step 0 — resume

```bash
plan_waves.py --root . --milestone M<n> --since <seal-rev> --json
```

Reads: the plans, and every commit in `<seal-rev>..HEAD`. `<seal-rev>` is the previous milestone's
sealed commit — a revision, not a date.
Decides: nothing yet; this is the picture every later step is computed against.
`0` — read the payload and go to step 1.
`1` — findings, and the run still produced a full status payload. The commit-versus-declaration
check runs over every commit in the range as a side effect, so a resume also re-audits what the
finished work actually wrote. Route the findings by rule before dispatching anything else: `W7` is a
writer-failure escalation (step 6), an unclaimed commit is a replan (step 1), a graph finding
(`W1`–`W6`) goes back to the plan.
`2` — the question could not be asked: unresolvable revision, a milestone id that is not `M<n>`, an
`--in-flight` id no task declares, or a milestone with no task in any plan — the state of every real
repository that has not adopted the layout. Fix the argument or the plan. Never proceed on a `2`.

### Step 1 — select, with no wave barrier

```bash
plan_waves.py --root . --milestone M<n> --since <rev> --ready --in-flight <ids> --limit N
```

The wave schedule is a **legality certificate, not a dispatch schedule**. Waves are Kahn levels — a
barrier where wave *N+1* waits on all of wave *N* even when a task needs one predecessor. On a
measured 51-task graph that is 8 waves at mean width 6.4, well above the three-writer cap, so wide
waves get chunked anyway and the barrier only idles the pool.

What the wave run certifies is that once `plan_waves.py --milestone M<n>` exits `0`, no two tasks
with overlapping `writes` are unaccounted for: the write check compares **every** pair, not just
same-wave pairs, and deliberate sharing must be declared with `serialises:`. That certificate
licenses a continuous ready set instead: dispatch any task whose `needs` are done, whose `writes`
miss every in-flight task's, and none of whose `serialises` partners is in flight. `--ready`
computes exactly that, admitting each chosen task into the in-flight set before testing the next, so
the emitted set is legal against itself and not only against what was already running.

`--limit N` is the operator's cap and no number is compiled in. Use **three concurrent full-lane
writers, each in its own `git worktree`**. Three is not safe because write sets are disjoint — they
are declared intent, and a measured 4 of 83 committed files landed outside the declaring task's set,
every one of them inside another task's. Safety comes from isolation plus detection: separate
worktrees mean a stray write becomes a merge conflict or a `W7` finding instead of a silent
clobber.

`0`/`1` — dispatch `ready`, in the order given; `deferred` carries the reason each candidate was
held, which is a dispatch fact and not a defect. `2` — as step 0.

### Step 2 — dispatch

```bash
validate_card.py <card> --repo . --phase pre
```

Four things must be true before a card leaves the orchestrator's hands, and this command answers
three of them. `0` — dispatch. `1` — an ERROR: the card is regenerated from the plan under a new
id, never patched. `2` — the card or the repo path does not resolve.

The dispatch hands over **paths, not contents**: the card path, the worktree, the report path. The
implementer writes its report to a file and returns a verdict. The persona is on the card and the
orchestrator does not re-litigate it at dispatch; an unnamed or misspelled persona silently falls
back to a general-purpose agent carrying every tool, which is how a judge acquires the ability to
edit what it is judging.

### Step 3 — drift, every turn boundary

```bash
validate_card.py <card> --repo . --phase mid
```

Compares every uncommitted path against the card's `exclusive_writes` and `forbidden_paths` with the
same glob intersection the commit check uses. One `git status`, tens of milliseconds, one line of
context, zero model calls.

`0` — continue. `1` — the task is writing outside its declaration. The orchestrator **never widens
the card**: it edits the plan's `writes`, re-runs `plan_waves.py --milestone M<n>`, and regenerates
the card under a new id. One wasted dispatch against a silent stray. `2` — the card no longer
resolves; stop the task, not the loop.

When the implementer finds something outside its task, the answer is the fix/record rule, not a
stop. FIX iff it writes only inside `exclusive_writes`, touches no `forbidden_paths`, advances an id
already in `invariants`/`frozen_values`, **and** either has a pasted command with its observed
output or fails this card's own `validation`. Otherwise RECORD it to the milestone's `## Deferred`
register (step 7). Safety-class findings — a live secret, an auth bypass, an injection, data loss —
bypass the test and are fixed in-task, never parked.

### Step 4 — validate

The card's `validation` argv is run by a read-only `test-judge`, never by the writer and never by
the orchestrator, with `start_junit_run.py` immediately before the test task and `verify_junit.py`
after. A verdict from the writer is a claim; the judge's re-run is the evidence.

### Step 5 — review

```bash
check_review_budget.py <workspace> --next <subject>
```

`0` — dispatch the round. `1` — the budget is spent, a third round is recorded, or a banned artifact
class is in the workspace. This instrument is advisory about the count and binding about what is on
disk; the count is adjudicated by a human at the merge gate. Selection is in §4.

### Step 6 — after every commit

```bash
plan_waves.py --root . --milestone M<n> --commit <rev>
```

Reads the commit's file list and compares it to the declaring task's `writes`. The **milestone**
scope is the only one that can see a commit landing in another feature's declared set, because a
per-plan run never loads the other plan; a per-plan view once reported 0 findings while 6
cross-feature collisions existed.

`0` — the commit wrote what its task declared. `1` — treat it as a **writer-failure escalation**,
not a note: the finding names the other task that declares the stray path. `2` — the revision does
not resolve.

### Step 7 — deferrals

```bash
spec_check.py --root . --deferred
```

Lists the register with its counts and **always exits 0** — it is a queue view, not a gate. The gate
is the ordinary `spec_check.py` run, where rule E fails a milestone that ships while an entry it
owns has no owner. Read the queue at every wave boundary and before the seal; a register nobody
reads is the state that existed before the register.

### Step 8 — coverage

```bash
trace_check.py --root . --evidence <receipt> --commit <range>
```

Every `covers:` criterion must resolve to a test that RAN, via a verified JUnit receipt. `--commit`
arms T7: an id that arrived inside the range must sit on a test whose body the range also changed,
because 0 of 5,866 real `@Test` methods carry a criterion id today and the cheapest way to satisfy
the check is a bulk rename that adds no assertion. Without `--evidence` the run traces nothing, says
so, and exits `0` — read the printed limit line, never the exit code alone.

### Step 9 — seal

```bash
milestone_seal.py --root . --gate M<n>
milestone_seal.py --root . --record M<n>
```

`--gate` prints the declared command and exits `0`. `--record` refuses a dirty tree, runs the gate
against HEAD's tree, and writes a receipt keyed to the tree sha outside the repository. `0` — the
gate ran and passed on this exact tree. `1` — the gate failed; there is no receipt and no seal. `2`
— no milestone document, no `Gate:` line, or the command could not start. The push guard then asks
`milestone_seal.py --verify --tree <tree> --command <gate>`, which exits `1` when no receipt binds
that tree. The seal is not the orchestrator's verdict: `acceptance` judges the milestone against the
criteria, and committing, pushing and merging stay founder decisions.

## 3. Who is cast, and when

The persona pool is not decoration. Five of its members — `developer`, `senior-developer`, `scout`,
`acceptance` and `docs-steward` — were cast only by a stage/role table and never by a procedure: no
step of the methodology said run this one, now. Two of the five are the ones that implement.

| Step | Persona | Why this one |
|---|---|---|
| Hold the loop | `chief-of-staff` | writes ledger, cards and reports only; implements nothing |
| Locate code before a card is written | `scout` | read-only; keeps search out of the writer's context |
| Implement a light-lane or bounded task | `developer` | the plan chose it with the whole design in view |
| Implement a task crossing a durable boundary | `senior-developer` | the lane test, decided in the plan |
| Run the gate, re-run the card's `validation` | `test-judge` | cannot write, so its verdict is not self-attested |
| Review a selected diff | `reviewer` | fresh, isolated, read-only; never applies its own fix |
| Safety surface moved | `security-validator` | the one specialist that blocks at BOTH stages |
| Schema, migration or backfill moved | `migration-validator` | the data plane had no owner; see §4 |
| Domain invariant moved | the repository's own validator | cast at DESIGN, not here: 66 implementation reviews, 0 blocks |
| Judge the milestone against criteria | `acceptance` | the only judgement the loop must not make about itself |
| Route, README, lessons after the milestone | `docs-steward` | prose with no behavioural claim is not the writer's |

A card's `persona` is the **implementer**, which is why the validator accepts exactly `developer`
and `senior-developer` there. Measured on 272 real cards in four repositories, 271 name one of those
two; the one that names a judge fails validation today, and correctly. Casting a judge or a validator on a card is a mis-cast card, not a
missing feature: those personas are cast at their own step, on a diff, and none of them may write.
A repository's own domain validators live in its persona overlay directory and are cited at review
and execution time; they are named on the diff at step 5, never on the card.

## 4. Review selection — THIS SECTION IS THE IMPLEMENTATION STAGE ONLY

Read this first, because an earlier version of this section was written against a rule that capped
review at one specialist and forbade a panel at every stage, and that rule is falsified. **Width is
scoped by stage.** Design and plan take a panel — up to three reviewers with different lenses, plus
`security-validator` on safety surfaces — because a design review blocks at 0.74 per artifact and
panel findings were measured to be disjoint (median anchor Jaccard 0.20 across 21 blocking pairs).
The rule and its evidence live in the skill's "Design and plan" paragraph; that is the single
source. Everything below governs the loop, which runs AFTER the plan gate, so its width is **one
model reviewer plus `test-judge`** — implementation reviews block at 0.09 per artifact, and a
four-or-more-wide implementation round blocked in 2 of 65 groups. `test-judge` runs a command and
reports an exit code; it is not a lens and it does not spend a review round.

Everything gets the **free structural review** — `validate_card.py --strict --phase post` and
`plan_waves.py --milestone M<n> --commit <rev>`, zero model calls. The one model reviewer is routed
by score, highest first, until the budget is spent. Cutting review to save tokens is the worst
available trade: a measured 72% of first-round verdicts block, and the whole fleet's empty rounds
cost less than one milestone's ledger re-reads.

Score, all four terms computed from one `plan_waves.py --milestone --json` run plus the card:

1. **Write-set overlap** — the number of other tasks in this milestone whose `writes` intersect
   this task's, from the JSON `tasks[].writes`. This is where the in-wave collisions and the
   out-of-set files actually landed. Use the count, not a boolean.
2. **Dependency fan-in ≥ 2** — from `tasks[].needs` in the same JSON.
3. **Dispatched over a warning** — `validate_card.py --strict` was not clean at dispatch, which is
   how an oversized card is caught: the budget is 150 lines and the validator already warns.
4. **Retry ≥ 1** — a `<subject>-r<N>-<kind>.md` round marker already exists for this subject.

**Never select on `gate_risk`**: it names the bookkeeping artifacts a task touches, and 177 of 182
cards in one sample list some, so it selects almost everything and discriminates nothing. **Never
select on a non-empty `forbidden_paths`** either — measured on 272 real cards, 272 of them have one.
**Never read fan-in from the card's `prerequisites`**: that field asserts tree state in prose, not
dependency edges — 203 of the same 272 cards fill it with at least one sentence.

**Measured on 272 real cards in four repositories**, so that the score's spread is known before it
is trusted: overlap with at least one other card in the same workspace selects 192 (71%), at least
two selects 155 (57%), at least three selects 128 (47%); over the 150-line card budget, 62 (23%),
with p90 at 298 lines; an id-shaped prerequisite fan-in of two or more, 20 (7%); a retry marker in
the filename, 4 (1.5%). That is why the rule is an ordered score and not a threshold — the overlap
term alone would select two thirds of a real milestone, which is a budget, not a selection.

Every input is a fact about the tree or about a file on disk, not a field the writer chose to
describe its own risk. That is the difference between selection and self-assessment.

## 5. What stops the loop

Stops:

- a **blocker** the loop cannot resolve, including a milestone branch with no commit in 48 hours;
- a **genuine ambiguity** that prevents progress — a fork the plan does not decide;
- the **fix cap**: five rounds on one subject, because past it the failure is structural;
- an **exhausted review budget**;
- a **writer-failure escalation** — a writer that returns nothing twice is not replaced a third
  time. Silence is not death: confirm before concluding, because deciding a live writer has died
  and dispatching a second onto the same write set breaks the one rule that is the orchestrator's
  alone;
- a **third distinct task** returning `NEEDS_CONTEXT` or `BLOCKED` against one plan section: the
  plan is wrong and is edited in place. Committed work stays committed — it was validated against
  criteria, not against the plan's later shape — and status recomputes.

Does **not** stop:

- a **report**. A report informs; it does not pause the loop. Before stopping, name the decision:
  if it is not one of the three gates, a spend, an irreversible or outward-facing action, or a
  genuine fork, there is nothing to ask. "Confirm I should carry on with what we agreed" is not a
  decision;
- **a real issue found outside the task**. It resolves through the fix/record rule (§step 3) and
  lands in the `## Deferred` register with `found_by`, `site`, `trigger` and `owner`. Uncapped
  fixing of found issues is measured not to converge: one workspace produced 51 cards, 230 reports
  and 64 review artifacts, with card creation flat for three days and three cards subdividing
  rather than closing, until a human applied a severity floor by hand;
- **a duplicate commit** on one task. It is reported and not failed; a follow-up fix is as common
  as a re-dispatch;
- **an unfinished milestone**. `complete: false` is a key, not an exit code;
- **a deferral queue with entries**. It fails at the seal, through rule E, not during the loop.

## 6. Who checks the orchestrator

Nothing in-process can. The tool that counts review rounds is run by the party it binds, and after
four rounds of hardening that was ruled advisory. The same is true of every claim the orchestrator
writes: the ledger, the cards and the reports are its own output, and cards are usually git-ignored,
so none of it reaches the process meter.

What is enforced instead:

- **Its writes are bounded by construction.** The orchestrator runs in a worktree in which the only
  paths it writes are the ledger, the cards and the reports; every writer gets its own worktree.
  A repository edit it makes is therefore a commit under its own name in a tree nobody dispatched —
  visible in `--since` as an `unclaimed_commit`.
- **Its dispatch decisions are recomputable.** Every id it dispatches must appear in a
  `plan_waves.py --milestone --since --ready` run against the current tree. A dispatch that does
  not is a fabrication, and re-running the command is how anyone checks.
- **Its verdicts are not its own.** The gate is run by `test-judge`, the milestone is judged by
  `acceptance`, and the seal is bound to a tree sha the orchestrator did not choose.

**Blast radius when it is wrong:** one milestone of commits, plus the record of what happened. The
worst single failure is compaction: after a reset it rebuilds state from artifacts it authored.
That is exactly why §1 makes state derived — the resume command reads the tree, not the record.

## 7. The one artifact a founder reads

One page per milestone, instead of 51 task reports. It is **composed of command output only** —
each block is the exact command, then its own stdout, run at print time on the tree being sealed:

```bash
plan_waves.py --root . --milestone M<n> --since <seal-rev>
trace_check.py --root . --evidence <receipt> --commit <range>
spec_check.py --root . --deferred
milestone_seal.py --verify --tree <tree> --command <gate>
ratio_meter.py --repo . --range <range>
check_review_budget.py <workspace> --json
```

For it to be trustworthy, three things must hold:

1. **Every line is re-derived at print time.** Nothing is copied from a task report; report paths
   may appear, report contents may not.
2. **Every line's referent was not chosen by the producer** — a tree sha, a commit range, a child
   process's exit status, a nonce the writer did not mint.
3. **The absences are printed.** The criteria that traced to nothing, the ids older than the range
   and therefore not judged, the deferral entries with no owner, the tasks with no commit. A page
   that only lists greens is a page that cannot fail.

The page is not a new script and deliberately so: a checker validated only against its author's
fixtures is what this toolchain has shipped seven times, each one inert against the real corpus. Six
existing commands already print these numbers, and each is validated by its own suite.

## 8. What this loop does not catch

- **A repository that has not adopted the layout.** Measured on four real repositories: none has a
  `docs/product/plans/` or `docs/product/milestones/` directory. Step 0 is safe there — it exits
  `2` and says "nothing to derive status for" — but a plain `plan_waves.py --milestone M<n> --json`
  run exits `0` with empty `features`, `waves` and `tasks`, which a consumer reads as "clean". A
  status view is only meaningful once `features` is non-empty. Silence is not a green.
- A stray write into a path **no task declares**: flagged, with no owner to name.
- **Semantic** interference between file-disjoint tasks. `writes` models paths, not behaviour.
- A writer that lies in its verdict, until the judge re-runs the gate.
- The **light lane**: the commit check ignores a commit naming no known task, and there is no card
  to validate.
- A **gate command that exits 0 without testing anything**. The receipt then means exactly that
  much.
- A plan that is coherent, green, perfectly parallel — and **wrong about the product**. No
  instrument here has an opinion about that; the three human gates are where it is caught.
