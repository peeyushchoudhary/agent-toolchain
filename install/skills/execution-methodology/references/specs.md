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
status: approved
updated: 2026-01-14
withdrawn: [3]
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

---

## Scaling down

A feature that touches two files does not need three pages. It does need the Why, the scope
boundary, the surface, and the criteria — that is where the incompleteness that costs rework lives.
What can shrink: three criteria instead of twelve, two examples instead of six, and a horizontals
line reading "no persisted state, no money, no personal data; authorization unchanged".

What cannot be skipped: the horizontals pass, the `Out` half of scope, and the current-state rule.
The first two are cheap to write and expensive to discover; the third is what keeps the document
worth reading a year from now.
