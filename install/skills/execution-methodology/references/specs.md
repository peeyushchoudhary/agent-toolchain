# Spec templates

Two artifacts, one owner (`product-steward`). The product spec says what an area is for; the feature
spec says what one feature must do. Neither says how.

Keep both short. They are read under time pressure by an agent that will skim anything long, and a
spec that gets skimmed is a spec that did not exist.

---

## Product spec

`docs/product/specs/<area>.md`

```markdown
# <Area>

## Why this exists
The problem, and what happens if it stays unsolved. Two paragraphs at most.

## Who it serves
Each actor, and what that actor is authorized to do. Authorization belongs here because
it is a product decision before it is a technical one.

## Where it stops
What this area does NOT handle, and who or what handles it instead. This section
prevents more rework than the rest of the document combined.

## Success criteria
Observable, and checkable by someone who did not write them.

## Open questions
What is genuinely undecided. Marked, not silently resolved.
```

No screens, no schemas, no technology. Naming a table or a component means the wrong document is
being written.

---

## Feature spec

`docs/product/specs/F-<id>-<slug>.md`

```markdown
# F-<id> — <Feature>

Product spec: <link>          Status: draft | approved

## Why
The problem, and what happens if it stays unsolved. First, not last —
everything downstream is judged against it, and a reader who does not know why
cannot tell a corner from a cut corner.

## Scope
**In:**  …
**Out:** …   (explicit; "out" is the load-bearing half)

## User stories
As a <actor>, I <action>, so that <outcome>.

## Behaviour
What the system does. Observable from outside.

## Edge cases
Empty · first run · concurrent · partial failure · permission denied ·
and whatever the domain adds.

A feature spec with no edge-case section is not finished. A thin one is worse
than none, because it looks answered.

## Horizontals
Go through each. Address it, or declare it not applicable WITH A REASON.
Silence is not an answer, and a bare "N/A" is silence.

| Concern | Disposition |
|---|---|
| Tenancy / isolation | |
| Authorization | |
| Audit trail | |
| Money handling | |
| Personal data | |
| Retention / erasure | |
| Accessibility | |
| Localisation | |
| Runtime cost | |

## Acceptance criteria
Each names a trigger, a precondition, and an observable result.

AC-1  When <trigger>, given <precondition>, the system <observable result>.

## Assumptions
Anything guessed rather than known, marked where it sits. An unmarked assumption
becomes a requirement three stages later and nobody remembers it was invented.
```

---

## On acceptance criteria

The form exists so criteria become test names without translation:

> **AC-3** When a guardian with no active enrolment opens the fee page, the system shows the
> dues-cleared state and offers no payment action.

That is a test name, a test body, and a review checkpoint in one sentence. Compare:

> The fee page should handle guardians without enrolments gracefully.

"Gracefully" cannot fail, so it cannot be tested, so it will be implemented as whatever the
implementer happened to think. Every vague criterion is a decision silently delegated downstream.

Two rules that catch most of the rest:

**A criterion must be observable from outside the system.** "The service caches the lookup" is a
design note wearing a criterion's clothes — it belongs to the architect. "A second request within
the same session returns the same result without a new charge" is a criterion.

**A criterion must be able to fail.** If no realistic input makes it false, it is describing an
intention rather than a requirement, and it will pass a review without ever having been implemented.

---

## Scaling down

A feature that touches two files does not need three pages. It does need the WHY, the scope
boundary, the edge cases, and the acceptance criteria — those four are where the incompleteness that
costs rework actually lives.

What can shrink: user stories collapse to one line, horizontals to the row that applies plus a
one-line "the rest are not applicable because this touches no persisted state".

What cannot be skipped: the horizontals *pass*. Going through the list and finding nothing takes a
minute. Not going through it is how a feature ships without an audit row.
