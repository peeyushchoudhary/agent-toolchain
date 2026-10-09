---
name: execution-methodology
description: Drive an approved goal (docs/goals/<id>/plan.md) to merged milestones; goal.py done decides done.
disable-model-invocation: true
---

# Execution methodology

You are the chief: the root session, in either harness. Read the last section first. `<skill>` is
this skill's directory; its `scripts/` print usage with `--help`.

## What this is

An approved `docs/goals/<id>/plan.md` is the whole goal; approval is the tag `goal/<id>/approved`.
`goal.py done` decides done. The founder is touched at approval and at merge, never in between.

## The loop, per task

1. `goal.py next` names the first `[ ]` task of the active milestone.
2. Write a packet: goal, `writes`, `tests-may-change`, gate, stop conditions, paths to read
   (never pasted text).
3. Dispatch one builder in its own worktree (`agents/builder.md`; until it exists, the harness's
   default agent). Build only trivial tasks yourself.
4. Apply its staged diff. Never commit while a builder shares your checkout.
5. Run the plan's `gate` yourself: `gate.py check --goal <id> --cmd "<gate>"`. Red goes back to the
   builder with the output; a task that stays red is parked.
6. Scan the diff for private facts: names, home paths, emails, secrets.
7. Commit `[Tn] <title>` with the tick and one Decisions line per default taken.

## `plan.md` format

```
---
goal: G-3
title: <outcome>
gate: <per-task command>
full_gate: <milestone command>
milestones:
  M1: {tasks: [T1, T2], e2e: "<real-services command>"}
touches: [none]        # or data, auth, external
protected: [path/**, doc.md#section]
---
## Outcome
## Tasks
### [ ] T1 — <title>
writes: src/a/**, tests/a/**
tests-may-change: tests/a/test_old.py
<what, constraints, the test it adds>
## Decisions
- <date> T1: chose X over Y (default).
## Parked
- <what waits for the founder>
```

`goal.py lint` checks it. Ticks: `[ ]` open, `[x]` gate green and committed as `[Tn]`, `[!]` parked
with a Parked line. A plan-only commit (subject `<id>: …`) changes only ticks, Decisions, Parked,
or widens `writes:`/`tests-may-change:` with a new Decisions line. A commit that
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
8. `.runs/<id>/review.md` reviewed an ancestor of HEAD, every later commit is a recorded fix or
   plan-only, and no `- [ ] BLOCKING` line remains.

Nothing else counts as done.

## Authority

**Default and log a Decisions line:** names and file layout; choice among libraries already in the
lockfile; test approach and fixtures; task order; internal interfaces not named in the Outcome;
error-message wording; refactors inside the write set; widening `writes` outside `protected`;
retry, timeout and dev-config values; which of two equivalent implementations; resolution of
non-blocking findings.

**Park (`[!]` and a Parked line), continue other work:** any change to Outcome or frontmatter; a new
external dependency, service, account or cost; any `protected` path; schema changes that drop,
rename or re-type data; auth or permission model; user-visible copy or pricing; deleting or
exporting user data; secrets; push, merge, deploy, publish, visibility; a blocking finding you
cannot fix inside the write sets. Parked work waits for the next touchpoint; never request a grant.

## Review

The other vendor reviews adversarially, read-only, with [agents/reviewer.md](agents/reviewer.md):
Codex when Claude is chief, Claude when Codex is. Once each at:

- **design**, only when `touches:` names data, auth or external ([references/design.md](references/design.md));
- **plan**, before the approval tag; resolve findings in the plan;
- **merge**, the milestone diff `goal/<id>/approved..HEAD`.

One round, no grant. Findings go to `.runs/<id>/review.md`:

```
reviewer: <vendor model> (read-only), <date>, <stage>
reviewed: <full sha>
verdict: PASS | BLOCK
## Findings
- [ ] BLOCKING R1 <defect>
  paths: <glob>, <glob>
```

Never reclass a blocking finding. Close it with a `[Tn][Rn]` fix commit that adds or changes its
test, then tick it and add under it, above `paths:`, `- [x] R1 resolved-by <sha> closes <test
path>::<name>`; or remove the work: `- [x] R1 removed-by <sha>`. Park non-blocking findings.

## Milestone close

Clean tree → `gate.py receipt --goal <id> --name full_gate --cmd "<full_gate>"` and `--name e2e
--cmd "<e2e>"` → merge review (fix commits need fresh receipts) → `goal.py done` prints DONE →
`goal.py packet` writes the PR body → the founder merges and tags. Next milestone: same branch,
fresh session. Record failures present at approval once with `gate.py baseline`; diagnose any new
failure, never rerun until green.

## Unattended runs

`<skill>/scripts/run.sh <id> --harness claude|codex --sessions N` restarts fresh sessions, each
prompted by `goal.py resume`, until DONE, PARKED, STALLED or out of sessions. The session is the
chief; `run.sh` only restarts, notifies and registers the Stop hook. Sessions get a scoped allowlist
(git add/commit/status/diff/log, `goal.py`, `gate.py`, the plan's commands, edit, write, agent), a
deny list (`git push`, `gh`, `curl`, `wget`, `rm -rf`, `git reset --hard`, `git checkout --`) and a
sandbox with network off and writes limited to the repository and `.runs/`; push and merge never.
To resume by hand: `goal.py resume`, then read `plan.md`.

## Before anything

A project with `docs/agents/execution/runtime.json` is not migrated. Do nothing in it; tell the
founder to migrate it first (`docs/runbooks/migrate-v5.md` in this methodology's source repository).
