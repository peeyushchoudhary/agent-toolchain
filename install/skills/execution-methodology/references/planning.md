# Planning a goal

A goal is one coherent outcome, usually one to three milestones. One approval of its spec, design
and plan buys one to several days of unattended work, so the three documents must be complete
enough to run without asking.

## The three documents

They live in `docs/product/goals/<goal-id>/` and hold current state only. Superseded options and
reversals are not kept in them; git holds the history, and a document that mixes past and present
gets misread as authority.

| File | Holds | After approval |
| --- | --- | --- |
| `spec.md` | why, actors, journeys, acceptance criteria `AC-n` in a table, non-goals | changes only by founder re-approval |
| `design.md` | structure, interfaces, data, the smallest-sufficient-change trace, rejected options in one line each | changes only by founder re-approval |
| `plan.md` | milestones, proofs, tasks, gates, run profile, grants, decisions, queue | the chief may only tick tasks and append to `Decisions` and `Queue` |

Draft them by interviewing the founder about the outcome, the journeys and the consequential
alternatives. Resolve contradictions in the owning document before review, because a reviewer can
only falsify what is written down. Then run cross-vendor review of the design and of the plan (see
[review.md](review.md)), correct, generate the approval explainer from [explainer-template.html](explainer-template.html), and present
the package. Approval is recorded by the tag `goal/<id>/approved` on the approved commit.

## `plan.md` format

```markdown
---
goal: G-3
title: <outcome in one line>
spec: docs/product/goals/G-3/spec.md
design: docs/product/goals/G-3/design.md
gate: make test            # per-task check, run before commit
full_gate: make check      # milestone gate, receipt on the committed tree
e2e: make e2e              # real-services journey, receipt on the committed tree
run: {network: true, session_hours: 3}
grants: [local-commit]     # e.g. push-branch; merge is never granted
---

## M1 — <milestone outcome>
criteria: AC-1, AC-2
acceptance: [all]          # or named partitions, e.g. [tooling, docs]
proofs:
- AC-1: python3 -m unittest tests.billing.test_refund
- AC-2: make e2e-refund
- AC-3: manual — founder checks the receipt layout

### [ ] T1 — <title>
- writes: src/billing/**, tests/billing/**
- needs: —
- covers: AC-1
- risk: none            # none | boundary | data | safety
- builder: routine      # routine | judgement | mechanical
- tests-may-change: —   # existing test paths this task may edit or delete
<dispatch notes: the goal of the task, constraints, the proof to add>

## Decisions
- 2026-10-07 T3: chose X over Y (reversible; default). Advisor: —.

## Queue
- [blocks T5] <question>, options, recommendation
```

**Frontmatter.** `goal`, `title`, `spec`, `design`, `gate`, `full_gate`, `e2e`, `run` and `grants`.
`gate` runs on the working tree before each task commit. `full_gate` and `e2e` run once per
milestone on the committed tree and produce receipts. `run.session_hours` is the session envelope
the driver and the Stop hook enforce; `run.network` lets the Codex sandbox reach the network.
`grants` lists actions beyond editing and local gates; merge is never among them.

**Milestones** are `## M<n> — <outcome>` headings with three fields:
- `criteria:` the `AC-n` ids the milestone delivers;
- `acceptance:` `[all]` by default, or named partitions for a split acceptance;
- `proofs:` one entry per criterion.

**Proof entries** are `- AC-n[, AC-m]: <command>`. The command is an exact shell command, one of
the tokens `gate`, `full_gate` or `e2e` naming the frontmatter command, or
`manual — <what the founder checks>`. Exact commands matter because receipts are bound to the
command text; a paraphrase cannot be run or matched.

**Tasks** are `### [ ] T<n> — <title>` headings with these fields:
- `writes:` path globs the task may change; the guard holds it to them.
- `needs:` task ids that must be done first, or `—`.
- `covers:` the criteria the task advances; each must be a real `AC-n`.
- `risk:` `none`, `boundary`, `data` or `safety`; it selects the task-level review.
- `builder:` `routine` (mid tier), `judgement` (stronger model) or `mechanical` (smallest model).
- `tests-may-change:` existing test paths the task may edit or delete, or `—`. Without an entry
  here, the guard treats any edit to an existing test, or an added skip, as tampering.

Free text after the fields is dispatch notes: the task's goal, its constraints and the proof it
adds.

**States.** `[ ]` todo, `[x]` done, `[!]` parked with a `Queue` entry. Every task commit names its
task as `[T<n>]` in the subject line. A commit that only ticks boxes or appends to `Decisions` and
`Queue` is plan metadata; its subject starts with `<goal>:`.

**Decisions** are dated, name the task, and say what was chosen over what and how it was decided
(default, advisor or council). **Queue** entries name what they block, the options and a
recommendation, so the founder can answer without reconstructing context.

**Tags.** `goal/<id>/approved` marks the approved commit and is the base for the frozen-input
check. `goal/<id>/M<n>` marks each completed milestone; completed milestones are verified against
their tags, never against a later HEAD.

Check the plan with `python3 <skill>/scripts/goal.py lint --plan <path>`. It checks that ids are
unique, `writes` and `covers` are non-empty, `needs` resolve, `covers` names real criteria and
every milestone criterion has a proof. A third of past plan blockers were of this kind, and a
script finds them for free.

## Milestone sizing

A milestone is the largest batch for which all of these hold:

- Every criterion has a proof command that runs in about 15 minutes or less, or is explicitly
  `manual`. A milestone whose criteria are mostly manual is a founder walkthrough, not an
  unattended milestone.
- It contains at most one durable-boundary decision, and that decision is made at approval.
- It has 4–10 tasks, starting with a walking skeleton that proves the journey end to end. The
  skeleton surfaces integration problems while they are still cheap.
- Its merge diff is reviewable in about 30 minutes: roughly 1,500 product lines or fewer, with
  deletions counted separately.

A plan that breaks a sizing rule states the exception in the milestone and how acceptance is
partitioned. Partitions are disjoint file sets, each reviewed by its own reviewer with its own
round cap; the milestone needs a current PASS from every one.

## Writing tasks

Keep write sets tight and disjoint where tasks could run in parallel, since `goal.py next` will
not schedule two tasks whose writes overlap. Put the test a task adds inside its own `writes`. List
in `tests-may-change` exactly the existing tests a task may change, with the reason in its notes;
a broad entry hides the tampering the guard exists to catch. Mark `risk` honestly: it is the only
thing that buys a task-level review.

- Code that predicts an external tool's behaviour carries an oracle test. It runs the tool under
  the same environment over the setups the code must handle, and compares the decisions. A test
  that asserts the code's own guess proves nothing.
- A design or task that prints a fix command (in a status line, a refusal or an error) carries a
  test that runs the command and shows the condition clears.
