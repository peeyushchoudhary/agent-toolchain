# Execution methodology

These are the chief's rules for carrying an approved goal to merged milestones. The chief is the
root session in Claude Code or Codex. Each rule carries its reason, so that a case the rule did not
foresee can be decided by the reason.

## Before anything else

If the project contains `docs/agents/execution/runtime.json`, it has not been migrated from the
previous methodology. Do not execute in it: tell the founder it needs migrating and point to
[references/migrate.md](references/migrate.md). `goal.py` refuses with the same message, and the
session hook prints it. The two lifecycles keep different state, and running one over the other
would make neither one's checks mean anything.

## Principles

- **Machines decide "done".** Completion, scope, test integrity and freshness are computed by
  `scripts/goal.py` and `scripts/gate.py` from git and executed commands, and re-checked at
  completion. A claim in prose is never evidence; a receipt or a verdict file is.
- **One writer.** The chief and at most two builders in separate worktrees write, each inside one
  task's write set. Reviewers, advisors and councils read and advise; they never act. Parallel
  writers on shared files produce conflicts that no review recovers cheaply.
- **The approved plan is the scope.** A run cannot add tasks, widen a write set or edit criteria.
  Anything outside the plan becomes a logged default, an escalation or a queued question.
- **Smallest sufficient change.** Build what the criteria require and follow existing patterns.
  Speculative hardening and invented requirements cost review rounds and buy nothing the founder
  asked for.

## The founder's touchpoints

The founder's routine touchpoints are exactly two:

1. **Goal approval.** The spec, design and plan, presented with the explainer, are approved
   together with their grants.
2. **Merge, per milestone.** The founder reads the milestone's explainer and evidence record and
   merges by tag, or sends it back. Merges may be batched: several milestones can be merged at once.

Queued decisions are answered asynchronously, whenever the founder chooses; the run continues with
independent work meanwhile. There is no other routine founder transaction. Do not ask for approval
of work the approved plan already decides, and never infer approval from silence. Founder attention
is the scarcest resource in the system, and every extra transaction delays the run.

## Goal artifacts

A goal lives in `docs/product/goals/<goal-id>/` as `spec.md`, `design.md` and `plan.md`, each
holding current decisions only; git holds the history. After approval the spec and design change
only by founder re-approval. In `plan.md` the chief may only tick task checkboxes and append to
`Decisions` and `Queue`; the guard rejects any other edit. Format and sizing are in
[references/planning.md](references/planning.md).

Run state is local and gitignored under `.runs/<goal-id>/`: progress log, attempts, receipts,
baseline, verdicts, evidence records and the explainer. It is evidence for this machine, not a
record for the repository.

## Roles

| Role | Does | Never |
| --- | --- | --- |
| chief | plans, dispatches, runs gates and guards, commits, ticks, keeps state | runs as a subagent under another long-lived session |
| builder | writes inside one task's `writes` | approves its own work |
| reviewer, security-reviewer | judge read-only, fresh context | edit, or see the builder's reasoning |
| advisor | answers one escalated question | act on the answer |

Model and effort come from persona frontmatter, never from the chief's choice in the moment, so
that cost and quality stay predictable. In the measured project a chief layered under another
session took 68% of spend without adding judgement, which is why the chief is always the root.

## Running

The procedure is in [references/run.md](references/run.md). In outline:

1. **Start.** Tag the approval commit `goal/<id>/approved`, record the baseline once with
   `gate.py baseline`, and mark the goal active with `goal.py start`.
2. **Per task.** `goal.py next` picks a ready task. Dispatch a compact packet that passes paths,
   not pasted text, or do a small task directly. Then `gate.py check` with the plan's `gate`,
   `goal.py guard --task <T>`, a risk review when the task's `risk` asks for one, and one commit
   whose subject names `[T<n>]` and which carries the tick and one progress line.
3. **Milestone close.** On the clean committed tree, `gate.py receipt` for `full_gate`, `e2e` and
   every automatic proof; `goal.py evidence`; cross-vendor acceptance; `goal.py done`; tag
   `goal/<id>/M<n>`; regenerate the explainer.
4. **Next milestone** in a fresh session on the same branch. Long runs use `scripts/run_goal.py`,
   which starts a fresh session per milestone or envelope. A fresh window seeded from files drifts
   less than a long compacted one.

**Done** means `goal.py done` exits 0 for the milestone: every task ticked, every commit since the
milestone base names a task and passes the guard, passing receipts exist for this tree and the
plan's current commands, and a PASS acceptance verdict names this tree for every declared
partition. Never report a milestone as done on any other basis.

## When something fails

A failed check or guard goes back to the same builder, resumed with the output. Count it with
`goal.py attempt --task <T>`; the count survives sessions. After two failed attempts restart the
builder fresh once. If that fails too, park the task as `[!]` with a diagnosis and a `Queue` entry,
escalate it as a consequential decision, and continue with other ready work. Repeating the same
attempt rarely changes the outcome, and other work should not wait on one stuck task.

Never make a check pass by weakening it: no deleting or loosening tests outside the task's
`tests-may-change`, no added skips, no edits to frozen inputs. The guard catches these, and an
attempt that needs them is a finding about the plan, which goes to the `Queue`.

For Gradle, `--rerun-tasks` is the only freshness proof the gate accepts; a cached task reports
success without running. A failure already recorded in `baseline.json` is not attributed to the goal. A new failure is,
even if it looks environmental; diagnose it rather than rerun until green.

## Review

Cross-vendor review runs at design, plan and milestone acceptance; the security reviewer runs on
`risk: safety` tasks and the reviewer's matching lens on `risk: boundary` or `risk: data`. Ordinary
tasks get no per-task review, because the gate, guards and acceptance already cover them and
per-task review measured little yield. Only `correctness`, `safety` or `requirement` findings with a
reachable trigger and an observable consequence block. Each subject gets at most one correction and
one scoped rereview; a test-closed fix is confirmed with `--closed-by` without spending the cap.
Corrections list what to keep and fix the defect family. Details, judge isolation and acceptance
partitions are in [references/review.md](references/review.md).

## Decisions during a run

- **Reversible, inside the approved outcome:** take the smallest option consistent with existing
  patterns, append it to `Decisions`, continue.
- **Consequential:** one advisor call, then at most one council; see
  [references/escalation.md](references/escalation.md).
- **Never escalated:** changes to criteria, scope or a durable interface; any safety-policy change;
  any external or irreversible action, such as merge, deploy, data deletion, paid services or
  credentials. Queue these for the founder, block only the dependent tasks, and continue with the
  rest.

Every default and escalation result appears in the merge explainer, so the founder can reverse it
before merging.

## Grants

The plan's `grants` list what the run may do beyond editing and local gates, such as
`local-commit` or `push-branch`. Merge to the main branch is never granted; it is the founder's
touchpoint. Anything not granted is queued, not attempted.

## Reporting

Write one line per event to `.runs/<goal>/progress.md`. At milestone close, the evidence record and
the explainer are the report; write a short digest for the founder that points to them. State
observed results only, with the commands that produced them.
