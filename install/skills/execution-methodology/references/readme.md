# README template

One README per repository, at the root. **Its first job is to say what is true today** — what the
repository is, what actually works, and what does not. Everything else on the page is navigation.

A README is read by someone deciding whether to trust this repository, in about ninety seconds. A
README that reads like a plan makes that decision on evidence that does not exist.

The current-state rule from [specs.md](specs.md) applies here in full: updated in place, never
appended to, never a record of what it used to claim. History is `git log -p README.md`.

---

## One hop each

**The README links the PRD. The PRD links the feature specs.** The README never lists features.

A feature list in the README has to be edited on every feature, forever, by someone whose attention
is on the feature — so it is wrong within a month, and it is the first thing an outsider reads. One
hop each keeps maintenance flat: the README changes when the *product* changes, not when a feature
does.

The same rule bans restating the PRD. Say what the product is in a paragraph, then link. Two copies
of a scope statement means one of them is out of date and neither says which.

---

## The seven sections

Order matters only for the first two. Headings may be renamed to local usage; the question each one
answers may not go missing.

````markdown
# <Repository>

**<One sentence: what this is, for whom, and the line it does not cross.>**

A short paragraph on the problem and why this shape of solution. No feature list.

## Current state

**<Stage in two words.>** What works today, in prose a stranger can check.

| | |
| --- | --- |
| <Component> | <what it is, in one line> |
| <Gate> | <what runs, and its result on the current branch> |

**Shipped:** the capabilities that a real user can reach today.

**Not shipped:** what is absent, parked, or blocked, named plainly — no deployment, no live user,
the modules that exist only as a spec, the external thing that is not created yet. This subsection
is mandatory and it is never empty. A repository with nothing false to report is a repository whose
README stopped being checked.

**Next:** one link to the current plan, and one sentence on the binding constraint.

## Product requirements

One paragraph on what the product is for, then the link: [PRD](docs/product/prd.md). The PRD
carries the feature index; this section does not.

## Architecture

How it fits together, with a diagram — the boxes, the direction data moves, and the one property
the design protects.

## Components

One row per component, each with a deep-dive link. The map, not the contents.

## Running locally

The shortest command sequence that produces a working setup, and the requirements it assumes.

## Working in this repository

The agent route, the branch and review rules, and where decisions are recorded.
````

---

## The rules that keep it true

**Lead with what is false.** The not-shipped subsection sits above the architecture, not in a
footnote. Written last, it becomes marketing; written first, it is the only line in the README that
cannot be faked by intention.

**No dates in prose that a reader must reconcile.** "Since March we have been building X" ages into a
lie without anyone touching the file. State the condition, not the elapsed time.

**Every claim is checkable.** A gate result, a count, a command, or a link. "Production ready" is not
checkable and therefore is not a claim.

**Blocked is a state, not a silence.** If an external thing blocks delivery, the README says so and
the PRD's off-repo blockers table carries the row. A README that omits the blocker is describing a
different repository.

**Nothing here is generated.** No badge that reports on a service nobody watches, no table built by
a script that must be re-run by hand. A stale generator is worse than no generator: it looks live.
