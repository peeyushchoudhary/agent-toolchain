# Operating model

Solo founder, several ideas in parallel, one laptop, no team, no hosted CI. Every other decision in
this documentation set follows from those four facts.

Both harnesses carry the same short global instructions, which the installer writes from
`install/global.md`.
The procedure itself is owned by the
[execution methodology](../../install/skills/execution-methodology/SKILL.md), and the
structure behind it by the [lean execution design](lean-execution.md). This page explains the
operating priorities and does not restate either. A project that still follows v5.1 migrates with
the migration guide (`docs/runbooks/migrate-v5.md`, written in T8).

## The three stages, in order

1. **Local execution quality.** Get the change right on this machine — narrowest production path,
   its adjacent tests, then the area gate. Depth over breadth; a half-finished feature is worth
   less than a small one that holds.
2. **Local end-to-end validation.** Before anything is called pilot- or release-ready, prove the
   whole path locally with real services and the full check gate. A green unit suite is not
   validation, and neither is a green push.
3. **Production deploy.** A separate, deliberate, explicitly authorised step — never a side effect
   of finishing the work.

Do not skip ahead. Stage 2 is the one that gets skipped, because stage 1 feels like finishing.

## What follows from it

**The founder touches a goal twice.** The routine touchpoints are exactly goal approval, where the
spec, design and plan are approved together with their grants, and merge per milestone. Decisions
the plan does not settle are defaulted, escalated to an advisor, or queued for the founder to
answer whenever they choose, while independent work continues. Founder attention is the scarcest
resource here, so every extra transaction delays the run.

**Machines decide done.** Completion, scope, test integrity and freshness are computed by
`goal.py` and `gate.py` from git and executed commands, and rechecked at completion. Report the
command and its real output; never claim a state you have not observed. If something is flaky or
environmental, say which and prove it by re-running. A failure already recorded in the goal's
baseline is not attributed to the change; a new one is.

**There is no second reviewer.** Independent verification has to be manufactured rather than
assumed. Judging roles cannot edit, by construction, and the reviewer comes from the other vendor
at design, plan and acceptance, with the prompt in
`install/skills/execution-methodology/agents/reviewer.md`. Review runs
where it has measured yield, each subject gets at most one correction and one scoped rereview, and
spend never changes a verdict.

**The approved plan is the scope.** A run cannot add tasks, widen a write set or edit criteria.
Criteria, durable interfaces, safety policy and external or irreversible actions, such as merge,
deploy, data deletion and paid services, are never decided by an agent: they are queued for the
founder and block only the tasks that depend on them.

**Context switches across projects are constant.** Assume no memory of another project. This is why
every repo carries its own route (`docs/agents/README.md`) and its own `docs/agents/lessons.md`,
rather than relying on an agent's private memory — one agent's memory is invisible to every other
harness.

**GitHub is storage.** Nothing deploys from it, nothing runs on it. See [github.md](../runbooks/github.md).

## Deliberately not done

These look like gaps and are not. Do not "fix" them.

| Not done | Why |
|---|---|
| Hosted CI / GitHub Actions | The founder laptop is the only release runner. A push is not evidence |
| Committed `.claude/settings.json` | Sole-founder mode; machine-local config stays machine-local |
| Bulk migration of other projects | Deliberate adoption at a project boundary |
| Automatic methodology or model upgrade | Installation, project adoption and model activation are separate decisions |
| A chief subagent under a long-lived session | The chief is always the root session; layering it cost most of the spend and added no judgement |
| Cross-harness persona dispatch | The only cross-harness call is the one-shot read-only reviewer; see [decisions.md](../decisions/decisions.md) |

## Delegation posture

Builders write inside one task's write set, at most two at a time and in separate worktrees; the
chief is the only other writer. Reviewers, advisors and councils read and advise and never act. A
builder never approves their own work.

Doing a task directly is correct when it takes a handful of tool calls and delegation would add no
isolation, parallelism or independent verification. Committed decisions and distillations stay
append-only.
