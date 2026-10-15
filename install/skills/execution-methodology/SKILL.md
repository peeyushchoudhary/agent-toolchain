---
name: execution-methodology
description: Drive an approved goal (docs/goals/<id>/plan.md) to merged milestones; goal.py done decides done.
---

# Execution methodology

You are the chief: the root session, in either harness. Read the last section first. `<skill>` is
this skill's directory; its `scripts/` print usage with `--help`.

## What this is

An approved `docs/goals/<id>/plan.md`, with its `spec.md` and any `design.md`, is the whole goal;
approval is the tag `goal/<id>/approved`, the founder's: the chief places it only when told to. `goal.py done` decides done. The founder is touched at
approval and at merge, never in between.

**Before a goal**, plan it with the founder by [references/planning.md](references/planning.md).
Each role's model and effort: [references/roles.md](references/roles.md).

## The loop, per task

1. `goal.py next` lists the ready tasks: open, in the active milestone, every task they `needs`
   committed.
2. Read the task and its `reads:` (`docs.py reads <Tn> --goal <id>` prints line ranges). Write a
   packet: goal, `writes`, `tests-may-change`, `reads`, the task's gate, stop conditions, your
   checkout's path and HEAD; paths, never text.
3. Dispatch one builder per ready task, at most four builders at once, each in its own worktree
   (`agents/builder.md`) under `.claude/worktrees/`, which the repository must ignore. Record each
   builder's worktree, once reported, with `goal.py own --goal <id> <path>`. A task waits
   until every task it `needs` is committed. Build only trivial tasks yourself.
4. With your checkout clean, apply one builder's staged diff; remove its worktree and branch after the commit.
5. Run the task's gate yourself: its `gate:`, the modules `goal.py next` names (`--modules a,b`),
   or the plan's, one check at a time: `gate.py check --goal <id> --cmd "<gate>"`. Red goes back to a builder with the output; a task
   that stays red is parked.
6. Scan the diff for private facts: names, home paths, emails, secrets.
7. Commit `[Tn] <title>` with the tick and one Decisions line per default taken.
8. Where the full gate takes 600 s or less, every third task commit start `gate.py receipt --name
   full_gate --runs <your .runs>` in a detached worktree at that commit, recorded with `goal.py own`,
   in the background, one at a
   time, and remove that worktree when the run ends; a sample due during a run starts on the newest
   commit when it ends. Otherwise the full gate
   runs only at close. A full-gate FAIL stops dispatch until a fix passes.

## `plan.md` format

```
---
goal: G-3
title: <outcome>
gate: <per-task command>
full_gate: <milestone command>
milestones:
  M1: {tasks: [T1, T2], e2e: "<real-services command>"}
touches: [none]   # or data, auth, external, interface, ui
protected: [path/**, doc.md#section]
---
## Outcome
## Tasks
### [ ] T1 — <title>
writes: src/a/**, tests/a/**
reads: src/b.py, docs/area.md#section
tests-may-change: tests/a/test_old.py
gate: <this task's command, under 600 s alone>
needs: <earlier task ids>
<what, constraints, the test it adds>
## Decisions
- <date> T1: chose X over Y (default).
## Parked
- <what waits for the founder>
```

`goal.py lint` checks it. Ticks: `[ ]` open, `[x]` gate green and committed as `[Tn]`, `[!]` parked
with a Parked line. A plan-only commit (subject `<id>: …`) changes only ticks, Decisions, Parked,
`reads:`, `gate:` or `needs:`, or widens `writes:`/`tests-may-change:`, with a new Decisions line. A commit that
deletes a file repairs the links naming it.

## Done, in words

1. Every milestone task is `[x]`, or `[!]` with a Parked line.
2. The tree is clean.
3. Every commit since the approval tag names one `[Tn]` or is plan-only.
4. Each `[Tn]` commit stays inside Tn's `writes` as read at its parent; no `writes` touches
   `protected`.
5. No existing test changed or deleted outside `tests-may-change`; no skip, only or xfail added.
6. Frontmatter, Outcome and task headers equal the approved commit's.
7. PASS receipts for `full_gate` and the milestone's `e2e` on HEAD's tree.
8. `.runs/<id>/review.md`, from `goal.py review`, reviewed an ancestor of HEAD, every later commit
   is a recorded fix or plan-only, and no `- [ ] BLOCKING` line remains.


## Authority

**Default and log a Decisions line:** names and file layout; choice among libraries already in the
lockfile; test approach and fixtures; task order; internal interfaces not named in the Outcome;
error-message wording; refactors inside the write set; widening `writes` outside `protected`;
retry, timeout and dev-config values; which of two equivalent implementations; resolution of
non-blocking findings.

**Park (`[!]` and a Parked line), continue other work:** any change to Outcome or frontmatter; a new
external dependency, service, account or cost; any `protected` path; schema changes that drop,
rename or re-type data; auth or permission model; user-visible copy or pricing; deleting or
exporting user data; secrets; merge, deploy, publish, visibility, any push but the milestone
close's; a blocking finding you cannot fix inside the write sets. Parked work waits for the next
touchpoint; never request a grant.

## Review

`goal.py review --chief <claude|codex> --stage <s>` runs the other vendor's reviewer, adversarial
and read-only, with [agents/reviewer.md](agents/reviewer.md) and the exact models in
[references/roles.md](references/roles.md); never hand-build the call. Once each at:

- **design**, whenever `design.md` exists ([references/design.md](references/design.md));
- **plan**, before the approval tag; resolve findings in the plan;
- **merge**, the milestone diff `goal/<id>/approved..HEAD`, with
  [references/security-checklist.md](references/security-checklist.md) when `touches:` names
  data, auth or external.

One round, no grant. Closing findings and the milestone close: [references/close.md](references/close.md).

## Resuming

The founder's own open session is the chief; no launcher starts it and no loop restarts it. This
skill loads in that root session on its own when a plan has an open milestone (D31), never inside
a subagent (D31 says why). On the founder's word, run
`goal.py resume`, read `plan.md`, and run the loop. Pushes pass the pre-push guard and the
harness's own permission prompts.

## Before anything

A project with `docs/agents/execution/runtime.json` is not migrated. Do nothing in it; tell the
founder to migrate it first (`docs/runbooks/migrate-v5.md` in this methodology's source repository).
