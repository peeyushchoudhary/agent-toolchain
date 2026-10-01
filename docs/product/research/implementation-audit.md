# Implementation audit — 2026-09-30

**Status: dated assessment, not behavioral authority.** Referent: `f6eca7c`.

## Current shape

This repository ships methodology, persona generation, hooks, validators and installation tooling;
it has no application runtime. Ten skills are published. Persona source descriptions expose eleven
active roles and retain three compatibility definitions. The chief of staff owns planning and
scheduling, writers implement, and separate judges supply semantic and executable evidence.

The execution chain is product definition, design, plan, task execution, review, integration,
milestone validation, acceptance and merge. Gate 2 already covers routine milestone operations and
defaults to six elapsed hours, two builders with separate write sets, and one heavy gate.
See [common methodology](../../../install/skills/execution-methodology/methodology.md), lines 26–55,
and [execution loop](../../../install/skills/execution-methodology/references/execution-loop.md),
lines 7–39.

`plan_waves.py` computes dependencies and path overlap without filesystem glob expansion. Its
continuous ready set avoids waiting for an entire wave when a successor is already legal. Git
commits recover task progress; task IDs, write sets and test criteria keep work bounded. Full cards
apply to durable boundaries and safety surfaces; ordinary light work uses an inline dispatch.

These are useful existing controls. The shipped limitations also matter: declared disjoint files
can interfere semantically, a criterion-named test can assert the wrong thing, and a coherent plan
can misunderstand the product. Independent review and real local integration address those limits.

## Findings

| Finding | Classification | Consequence and smallest proposal |
| --- | --- | --- |
| Sandbox verdict and exit disagree | High; executable defect | `gate.sh` can print nonpass yet return zero. Derive its exit from its complete verdict. |
| Seal checks source only before running | High; executable defect | A successful command can alter tracked source and still receive a receipt. Recheck source and referent after the gate. |
| Seal reuse lacks runtime/environment binding | Evidence gap | An unchanged tree and command retain a receipt after service/tool changes. Extend the existing seal owner with a bounded input identity. |
| Execution authority is prose | Autonomy/enforcement gap | The ready set proves schedule legality, not the founder's approval. Bind the existing decision to executable status. |
| Local commit authority can be absent | Workflow gap | Accepted dirty slices require a pause. Make allow/withhold explicit in the plan decision. |
| Judge dispatch restriction is instruction-only in Codex | Isolation limit | A filesystem sandbox alone does not prevent a writer spawned by a judge. Test native role-level disabling before changing rendering. |
| Actual cost and interruption causes are unknown | Measurement gap | Price tables and churn cannot rank accepted-work economics. Join existing task evidence with available harness usage. |

### Sandbox success contract

[gate.sh](../../../install/skills/gate-sandbox/scripts/gate.sh), lines 89–92 and 142–157, records
source-integrity and cleanup failures, prints a verdict using those failures, then exits using only
the gate child's status. With child exit zero and failed integrity, the process returns zero.
[milestone_seal.py](../../../install/skills/execution-methodology/scripts/milestone_seal.py),
lines 218–240, accepts a declared command's zero exit and writes a receipt. This can promote a
nonpassing launcher result if that launcher is the declared milestone command.

The smallest repair belongs to the current launcher. Retain the raw child exit separately from the
launcher's final verdict; require a nonzero launcher exit for integrity/cleanup failure. Specify how
capture failures and unreadable cleanup evidence affect that verdict. A new evidence framework is
unnecessary.

### Seal identity

The same recorder, lines 196–240, rejects an initially dirty tree, executes the command, and writes
a success receipt without a post-run source check. Its verification, lines 246–273, compares tree,
command and exit. Its header explicitly admits environment changes do not expire the receipt.
That is narrower than the common methodology's reuse rule, lines 100–110.

Require stable source/ref checks after the command and a declared, secret-free identity for actual
gate inputs: methodology bundle, gate implementation, interpreter/toolchain, lockfiles and relevant
service/image identities. Record unknown inputs honestly. Avoid hashing the entire environment,
timestamps, secret values or irrelevant settings; doing so creates needless invalidation and leaks
data. Write-producing gates continue through the existing prepared-copy route.

### Authority and completion

[plan_waves.py](../../../install/skills/execution-methodology/scripts/plan_waves.py), lines 146–148
and 217–261, parses task fields. Its status derives progress from named commits, while execution
requires the controller to track approval, review and remaining resources separately. Consequently,
`done` and `complete` are Git progress facts, not independent acceptance or release readiness.
Proposed authority fields must preserve that distinction.

The current loop explicitly pauses if Gate 2 withheld local commits, lines 237–247. Fewer pauses
there require an explicit founder decision covering commits; repeated prompting cannot manufacture
that authority.

## Complexity and documentation

A tracked-file census counted 134 text files and 72,368 lines under `install/`, including tests and
comments. The execution skill contains 22 Python script files and 18 test modules. `verify.sh` has
5,291 lines; the largest production validators have roughly 1,500–3,000 lines. These counts price
maintenance surface; they do not prove waste or poor correctness.

Simplification should remove a demonstrated duplicate or unused branch, one change at a time,
while preserving behavior. The entry validator reported an existing 1,211-word guide against a
1,200-word budget. Runtime inspection reported `unadopted`, `ready=false`, no approved inventory;
this assessment does not silently adopt the source repository or substitute a global runtime.
