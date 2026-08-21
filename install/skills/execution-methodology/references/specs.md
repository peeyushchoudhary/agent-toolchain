# Product definition

Two artifacts. **One PRD per repository, one feature spec per feature.** Both owned by
`product-steward`. Both say what the product must do; neither says how.

Rich product definition is wanted, so neither template carries a line cap. Each section states its
intent: write what that intent needs and stop. What is capped is everything the process spawns
*around* a spec, never the definition itself. Both are read under time pressure by an agent that
will skim anything long, and a spec that gets skimmed is a spec that did not exist.

---

## The current-state rule

This governs both templates and outranks every other rule here.

**A spec states what is true now.** It is updated in place. Nothing is appended to it.

**A spec never says what it used to say.** No dated headings, no changelog section, no "an earlier
version of this said", no strikethrough, no correction note, no superseded paragraph standing beside
its replacement. A reader who has to date the sentences to find which one binds is interpreting the
document at runtime, and two readers will interpret it differently.

Three places absorb what the body will not hold:

- **History lives in git.** `git log -p docs/product/prd.md` is the changelog, and it cannot drift
  from the file it describes.
- **Why lives in an ADR** under `docs/decisions/`, linked by path. A spec that argues with itself is
  carrying an ADR it never wrote.
- **The append-only parts live in front matter**, as keys — never in prose.

### Withdrawn criteria

Criterion ids are append-only, the body is current-state, and those two pull against each other:
delete a withdrawn criterion and its number is free, so the next criterion written silently takes
it, and a test citing `AC-3` now asserts something nobody chose. The resolution splits them.
**Delete the text from the body; retire the number in front matter** — `withdrawn: [3, 9]`. A
retired number is never reused and never renumbered once the spec is approved; before approval
nothing cites it, so a duplicate can still be fixed. The body stays current, the id space stays
stable, and the append-only residue is two integers instead of a history section.

**A requirement that MOVED is written `3>11`.** `withdrawn: [3, 9>14]` says AC-3 is gone and AC-9
became AC-14. The distinction is the only thing that tells a reader what to do with a test that
still cites the old number: a plain retirement means the test is asserting something nobody wants
any more and should go; a supersession means it should be repointed, and only the spec knows where
to. Without the arrow both read as "dead id" and the tracer could say nothing more useful than that.

**A feature that turns out to be several takes letters** — `F-9` becomes `F-9A`..`F-9J`, and the
bare number is spent. Renumbering the survivors would repoint every test already citing them, which
is the same reason criterion ids never get reused.

---

## The PRD

`docs/product/prd.md` — one per repository. It replaces the area-level product spec. Two levels of
product document overlap by most of their sections, so a scope change has to edit two to four files;
the one nobody edited is then wrong and still looks authoritative.

````markdown
---
title: <product>
status: draft | approved | building | shipped | dropped
updated: <YYYY-MM-DD>
reach: <who can use this today, one line>      # optional
---

# <Product>

## Why this exists
The problem, and what happens to whom if it stays unsolved.

## Who it serves
Each actor, and what that actor is authorized to do. Name the actors precisely: a product for
everyone has nobody to test against. Authorization belongs here because it is a product decision
before it is a technical one.

## Where it stops
What this product does NOT do, and who or what does it instead. This section prevents more rework
than the rest of the document combined.

## Appetite and constraints
What this is worth — the time and money it may take, and the fixed limits nothing may exceed. Scope
with no ceiling is how one feature becomes one quarter.

## Success criteria
Observable, and checkable by someone who did not write them.

## Off-repo blockers
What must be true OUTSIDE this repository before any of this reaches a person. At most five rows.

| thing | state | who | date |
|---|---|---|---|
| <server, vendor account, signing key, domain> | not-created \| requested \| live | <role> | <YYYY-MM-DD> |

A row leaves the table when it goes live. It is never softened in place.

## Open questions
`[NEEDS CLARIFICATION: <question>]`, inline where the gap sits. Greppable beats sectioned.

<!-- features: docs/product/specs/F-*.md -->
````

No screens, no schemas, no technology. Naming a table or a component means the wrong document is
being written.

**Why off-repo blockers earn a section.** In the measured record the risks that actually stopped
delivery were external — no server, no vendor account, no live key. Every other section describes
the product, so those risks had nowhere to live and were tracked nowhere, while the document read
healthy right up to the day nothing shipped.

---

## The feature index

The PRD carries the marker `<!-- features: docs/product/specs/F-*.md -->` and no hand-written list.
Each feature spec carries `prd: docs/product/prd.md` back. Nothing is generated into the tree.

The glob is the index: `ls docs/product/specs/F-*.md` enumerates it, and the `prd:` key proves each
spec belongs. **An index that can only derive cannot drift.** A typed list is wrong the first time a
spec is added, renamed, or dropped, and the wrongness is invisible — it still reads like a list.

---

## The feature spec

`docs/product/specs/F-<id>-<slug>.md`

````markdown
---
id: F-<id>
title: <feature>
prd: docs/product/prd.md
status: draft | approved | building | shipped | dropped
updated: <YYYY-MM-DD>
depends: [F-3]                            # optional
milestone: M2                             # optional — absent means specified and waiting
withdrawn: [3, 9]                         # optional — retired AC numbers
decisions: [docs/decisions/<adr>.md]      # optional
edge_cases: [empty, concurrent, permission-denied]
---

# F-<id> — <Feature>

## Why
The problem, and what happens if it stays unsolved. First, not last — everything downstream is
judged against it, and a reader who does not know why cannot tell a corner from a cut corner.

## Scope
**In:**  …
**Out:** …   (explicit; "out" is the load-bearing half)

## Surface
The route, command, screen, or event this feature exposes, named. It is a product decision: left
blank, the implementer invents one, and the code contradicts the spec within a day. `TBD` is
allowed once and belongs in the open questions, not here.

## Acceptance criteria
**AC-1** When <trigger>, given <precondition>, <observable result>.

Tag the criteria a horizontal constrains: `[authz]` `[audit]` `[money]` `[pii]` `[a11y]`.
Edge cases — empty, first run, concurrent, partial failure, permission denied — are criteria like
any other. A feature whose criteria only describe the happy path is not finished.

The classes considered go in `edge_cases:` front matter, and the checker requires it to be
non-empty. Deleting the edge-case *section* removed the only thing that forced the unhappy path, and
a sentence asking for diligence is not a forcing function; a required key is. Naming a class there
without a criterion for it is still possible — the key proves the question was asked, not answered.

## Examples
Literal values, not shapes. One line per case, input → observable result. An example that says
`<amount>` instead of `1200` has moved the decision to the implementer.

## Horizontals
One or two sentences: which of tenancy, authorization, audit, money, personal data, retention,
accessibility, localisation and runtime cost this feature moves, and why the rest do not apply.

## Assumptions and open questions
Anything guessed rather than known, marked where it sits. An unmarked assumption becomes a
requirement three stages later and nobody remembers it was invented.
````

**The horizontals pass survives; the table does not.** Going through the nine concerns takes a
minute, and not going through it is how a feature ships without an audit row. The nine-row table was
the ceremony around that pass: seven rows are "N/A" on a typical feature, which trains the reader to
skim the two that are not.

Also gone: **Behaviour** and **User stories** each restated what the criteria and the Why already
said, and a restatement is a second copy that goes stale silently. A separate **Edge cases** section
let edge cases stay prose while the real criteria sat elsewhere, so they were never tested.

---

## The milestone

`docs/product/milestones/M<n>-<slug>.md` — what a set of features is being taken to together, and
nothing about how. It exists for ONE reason: the parallelism worth having is across features, not
inside one, and until a scope names which features dispatch at the same time there is nothing to
check that parallelism against.

````markdown
---
milestone: M<n>
title: <what this milestone delivers>
status: draft | approved | building | shipped | dropped
updated: <YYYY-MM-DD>
---

# M<n> — <milestone>

## Goal
One paragraph, in the user's terms, of what is true when this milestone lands. Not a feature list —
a state of the world. This is the only sentence in the corpus that spans features, which is why it
cannot be derived from them and why the milestone document has to exist at all.

## Why now
What becomes possible when these features land together, and what stays impossible until they do.

## Success criteria
Outcome-level, and NONE of them may be any single feature's acceptance criterion. If a line here
could be written as `**AC-n** When …` inside one spec, it belongs in that spec instead.

## Cross-feature validation
The journeys no feature's own suite can prove, because each proves only its own slice. One row per
journey: what it crosses, and what it establishes that the parts do not.

| journey | crosses | proves |
|---|---|---|
| J-1 <name> | F-11 → F-12 → F-13 | <the handoff that only the whole path exercises> |

Gate: `<the exact command that runs these journeys>`

The `Gate:` line is read by the push guard when this milestone moves to `status: shipped`. Sealing a
milestone runs its end-to-end validation; a seal whose journeys never ran is a claim, not evidence.

## Deferred
The register. One entry per finding this milestone found and did NOT fix, six keyed lines each.
Open items only — closing an entry DELETES it, because a closed deferral is history and history
lives in git.

- **D-1** <what was found, in one line a reader can triage>
  found_by: F-11/T3
  site: `src/export/writer.py:214`
  threatens: AC-8A            # or an invariant id, or `none`
  trigger: `python3 -m unittest tests.test_export` — 1 failure, 3.9 s   # or `none`
  owner: M4                   # the milestone that will close it, or `none`
  raised: 2026-01-05

A key sits at one to three spaces of indent; anything indented four or more is continuation text
and is never read as a key, whatever word it starts with.

## Where it stops
What is deliberately NOT in this milestone, and what that costs.

## Off-repo blockers
Only the ones this milestone adds. The PRD holds the rest.

## Cross-feature validation
The journeys no single feature's suite can prove, and the one command that proves them.
Gate: <command>
````

**A feature joins by declaring it, and the milestone holds no list.** A spec adds one optional key:

```
milestone: M2
```

**The key is optional, and its absence is a state rather than an omission.** A feature with no
milestone is specified and waiting — the normal condition of most of a backlog. Requiring the key
would make the backlog a wall of findings and train whoever writes a spec to put down whichever
milestone is nearest, which is worse than no answer.

**Membership derives; it is never typed twice.** `grep -l 'milestone: M2' docs/product/specs/F-*.md`
enumerates the milestone, the same way the PRD's glob enumerates the corpus. A hand-written feature
list in the milestone document is wrong the first time a feature moves, and the wrongness is
invisible because it still reads like a list. This is the same rule as the feature index, applied
to the same failure. **An index that can only derive cannot drift.**

**The register is the second thing the milestone owns.** Principle 6 says deferrals live in a
register a milestone can fail against; until `spec_check.py` grew rule E, nothing in this toolchain
could fail against anything and the promise was prose. Rule E checks that entries parse, that
`found_by` names a feature that actually belongs to this milestone, that `threatens: AC-<n>` names a
live criterion, that `raised` is a date, and — the two that bite — that an entry owned by a
milestone which has **already shipped** is a finding, and that a milestone cannot reach
`status: shipped` while an entry it owns has `owner: none`. `spec_check.py --deferred` lists every
register with its counts and exits 0.

**Why six keys and not prose.** One real project built this register itself, in TSV: 205 rows, 178
open, 27 closed, 17 unowned, **2,046 characters per row** and 423 KB of file. The information a
reader needs is the six keys; the rest is a row explaining itself because it has no shape. Six keys
is about seven short lines.

**There is deliberately no cap on the count.** A ceiling the seal refuses to grow past would have
bound that real register at roughly row 40 of 205, and the pressure lands on RECORDING the finding
rather than on fixing it — which returns the project to the state before the register existed, with
the findings still happening and nothing counting them. Deferral is already ~2% of throughput on a
real repository (12 of 571 commits, 11,524 of 596,010 lines) and it happens whether or not anyone
writes it down. The job here is to make it explicit and countable, not to add a budget. So the count
is printed and the ownership is enforced, and no number is capped.

**The gate is the one thing the milestone owns that no feature does.** A feature's suite proves the
feature; nothing proves the journey that crosses three of them, because no single feature owns it —
and that journey is the reason a milestone exists at all. So the document declares one command, and
`status: shipped` is the claim that it passed. That claim is checked rather than believed:
`milestone_seal.py --record M<n>` runs the command from a clean tree and receipts a pass against
HEAD's tree object, and the pre-push guard refuses a push that moves the document to `shipped`
without a receipt for the tree being pushed. Any edit to the content gives a new tree and ends the
receipt, so the evidence cannot outlive what it was measured on. Only the transition is gated — a
milestone that is already shipped, or still building, costs a push nothing.

**One command, not a list.** `&&` composes as many suites as the milestone needs and still yields
the single exit status a receipt can bind to. A checklist of commands is a second copy of a script
that nobody runs in order.

**What a milestone must not become.** It is not a status report, not a progress table, not a
per-feature checklist — every one of those is a second copy of something git or the specs already
hold, and each is a cost paid on every future edit. The schedule in particular is COMPUTED:
`plan_waves.py --milestone M2` merges the plans of the member features into one graph with qualified
task ids (`F-12/T1`) and derives the waves. A wave list written into the milestone would disagree
with the plans the first time a task moves.

---

## The feature plan

`docs/product/plans/F-<id>-<slug>.md` — one per feature, holding the implementation plan and the
validation plan in one file. Two files would let the tasks and the tests they justify disagree, and
the disagreement would be invisible because each file would read complete on its own.

It is product thinking, not bookkeeping: it is committed, it counts toward the ~20% that is wanted,
and it is where implementation detail belongs. **The plan explains; the card names.** Anything that
would be identical for a second task belongs here or in a committed file; only what makes THIS task
stop belongs in a card.

````markdown
---
feature: F-<id>
title: <feature>
spec: docs/product/specs/F-<id>-<slug>.md
status: draft | approved | building | shipped
updated: <YYYY-MM-DD>
---

# F-<id> — implementation and validation plan

## Approach
How this is being built, in a paragraph. The shape of the change, the existing seams it uses, and
the one thing a reader would otherwise get wrong. Not a restatement of the spec.

## Frozen interfaces
Signatures, payload shapes and event names that later tasks consume, verbatim. A task may not
invent one of these, and a task that needs one that is not here returns to the plan.

## Tasks

```task
task: T1
title: <what is true after this task that was not before>
lane: full
needs: []
writes: [backend/x/**]
covers: [AC-1, AC-4]
```

```task
task: T2
title: <the next one>
lane: light
needs: [T1]
writes: [web/src/y/**]
covers: [AC-3]
```

One block per task. `needs` names the tasks that must finish first; `writes` is the only paths this
task may touch, and it is the parallelism contract; `covers` names the criteria the task satisfies.
An optional `serialises: [T1]` declares that a shared write set with another task is known and
deliberate — without it, two tasks that write the same paths are a finding whether or not a
dependency happens to hold them apart.

The orchestrator derives the waves; nobody writes them down.

## Validation plan

### Coverage map
Every criterion, its level, and the task that carries it. A criterion with no row is a gap; a
criterion whose level is `none` needs a reason in the absence claim below.

| AC | level | task | note |
|---|---|---|---|
| AC-1 | unit | T2 | |
| AC-4 | integration | T3 | crosses the vendor boundary |
| AC-8 | e2e | T5 | |

### Planned tests
Two fields per test, and both exist to stop the same defect.

```test
covers: AC-4
assert: schedules at 2026-02-13T09:30Z          # a value computed by hand, never read from the code
and_not: does not schedule when the appointment is cancelled
```

`assert` is a literal a human worked out. A value copied from what the code currently returns
asserts that the code does what it does, and a correct and an incorrect program pass it equally.

`and_not` is the paired negative — the thing that must NOT happen. It is the field a tautological
test cannot fill in honestly, which is the whole reason it is mandatory.

### End-to-end set
At most three, and each names the journey it proves. An e2e suite that grows past that stops being
run, and a suite that is not run is worse than one that does not exist, because it is cited.

### Not tested, and why
The absence claim. Every criterion the plan deliberately leaves untested, with the reason. This
section is the one most likely to be empty and the one most worth writing: an untested criterion
that nobody declared is indistinguishable from an oversight, and it will be read as covered.

### Gate
`<the exact command that runs this feature's tests>`
````

**Why there is no `expected_red`.** An earlier draft required the exact failure string a test emits
before the code exists. It is a fact about the tree at authoring time and goes stale the moment
anything else lands — three of three such literals in a real plan were already false when they were
checked. Watching the test fail for the stated reason is still required; recording last week's
failure text is not evidence that it did.

---

## On acceptance criteria

The form exists so a criterion becomes a test name without translation:

> **AC-3** When a member with no active subscription opens the billing page, the system shows the
> nothing-due state and offers no payment action.

That is a test name, a test body, and a review checkpoint in one sentence. Compare:

> The billing page should handle members without subscriptions gracefully.

"Gracefully" cannot fail, so it cannot be tested, so it will be implemented as whatever the
implementer happened to think. Every vague criterion is a decision silently delegated downstream.

Two rules catch most of the rest. **A criterion must be observable from outside the system**: "the
service caches the lookup" is a design note wearing a criterion's clothes and belongs to the
architect, while "a second request in the same session returns the same result without a new charge"
is a criterion. **A criterion must be able to fail**: if no realistic input makes it false, it
describes an intention rather than a requirement, and it will pass review without ever having been
implemented.

---

## A worked example

````markdown
---
id: F-7
title: Resend a pending invite
prd: docs/product/prd.md
status: draft
updated: 2026-01-14
withdrawn: [3]
edge_cases: [expired, rate-limited, permission-denied]
---

# F-7 — Resend a pending invite

## Why
An invite that lands in a spam folder strands the invitee. The only repair today is to delete the
invite and make a new one, which loses the record of who was invited when.

## Scope
**In:**  resending an invite that is still pending, from the members list.
**Out:** editing the invited address (delete and re-invite instead), bulk resend, SMS.

## Surface
`POST /invites/{id}/resend`, exposed as a **Resend** action on each pending row of the members list.

## Acceptance criteria
**AC-1** When an admin resends a pending invite, given it has not expired, the system sends a new
mail to the same address and shows the new send time on the row. `[authz]`
**AC-2** When an admin resends a pending invite, given one was sent less than 5 minutes ago, the
system refuses and states the time the next resend is allowed.
**AC-4** When a resend is attempted, given any outcome, the system writes an audit row naming the
actor, the invite, and the result. `[audit]`
**AC-5** When a non-admin calls the route, the system refuses and sends no mail. `[authz]`

## Examples
- pending, last sent 09:00, now 09:20 → mail sent, row reads `09:20`
- pending, last sent 09:18, now 09:20 → refused, "resend available at 09:23"
- invite already accepted → the action is absent from the row

## Horizontals
Authorization and audit move: resend is admin-only and every attempt is logged. No money, no new
personal data (the address is already held), no retention or localisation change.

## Assumptions and open questions
Assumes the 5-minute floor satisfies the mail provider's rate guidance.
[NEEDS CLARIFICATION: may an expired invite be resent, or only re-created?]
````

`AC-3` is absent from the body and retired in front matter: the text is gone, the number is spent.

It is `draft` because it still carries an open question, and approving it means answering that
question in the text — not marking it approved with the marker left in. The checker enforces exactly
that pairing, which is the whole of what `approved` means here.

---

## Scaling down

A feature that touches two files does not need three pages. It does need the Why, the scope
boundary, the surface, and the criteria — that is where the incompleteness that costs rework lives.
What can shrink: three criteria instead of twelve, two examples instead of six, and a horizontals
line reading "no persisted state, no money, no personal data; authorization unchanged".

What cannot be skipped: the horizontals pass, the `Out` half of scope, and the current-state rule.
The first two are cheap to write and expensive to discover; the third is what keeps the document
worth reading a year from now.
