# Lean goal execution — design (methodology v6)

**Status: approved 2026-10-06 with [F-3](../product/specs/F-3-lean-execution.md); in implementation.** This
document describes v6 as it will exist once built. It records current decisions only; git holds the
history.

## Principles

1. **Machines decide "done".** Completion, scope, test integrity and freshness are computed by
   scripts from git and executed commands, and they are re-checked at completion rather than
   trusted from earlier steps. LLM judgement is spent only where it has measured yield: design,
   plan, safety and data surfaces, and milestone acceptance.
2. **One writer, extra agents add judgement.** The chief is the root session. Builders write inside
   one task's write set, with at most two at once in separate worktrees. Reviewers, advisors and
   councils read and advise; they never act.
3. **The approved plan is the scope.** An unattended run cannot add tasks, widen write sets or
   edit criteria. Anything else becomes a logged default, an escalation or a queued question.
4. **Small enough to obey.** One rules file for the chief and one page per role. Rules state the
   reason rather than shouting. Vendor guidance for current models is that bloated, conflicting or
   capitalised instructions are followed worse, not better.
5. **Re-earn every component.** Each part below names the failure it prevents. A part whose
   failure class stops occurring is deleted, not kept as insurance.

## Artifacts

Each goal lives in `docs/product/goals/<goal-id>/` of the project and holds three current-state
documents. A goal is one coherent outcome, usually one to three milestones.

| File | Holds | Changes after approval |
| --- | --- | --- |
| `spec.md` | why, actors, journeys, acceptance criteria `AC-n`, non-goals | only by founder re-approval |
| `design.md` | structure, interfaces, data, the smallest-sufficient-change trace, rejected options in one line each | only by founder re-approval |
| `plan.md` | milestones, proofs, tasks, gates, run profile, grants, decisions, queue | the chief may only tick tasks and append to `Decisions` / `Queue` |

Run state is local and gitignored, under `.runs/<goal-id>/`. Migration adds `/.runs/` to the
project's `.gitignore`.

| Item | Contents |
| --- | --- |
| `progress.md` | one line per event: task, commit, check result, verdict path, default taken, usage |
| `attempts.json` | failed attempts per task, carried across sessions |
| `receipts/` | gate receipts, one per (tree, command) |
| `baseline.json` | failures already present on the base commit, recorded once at goal start |
| `verdicts/` | reviewer, security, advisor and acceptance verdicts |
| `explainer.html` | the founder explainer, regenerated per approval or merge |

### `plan.md` format

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

Task states are `[ ]` (todo), `[x]` (done) and `[!]` (parked, with a Queue entry). Every task
commit names its task as `[T<n>]` in the subject line. Edits to `plan.md` that only change
checkboxes, `Decisions` or `Queue` are controller metadata. They are always admitted alongside a
task's own writes; any other `plan.md` edit fails the frozen-plan check.

## Roles and routing

The chief is the root session. Spawning a chief subagent under another long-lived session is not
allowed: in the measured project that layering cost 68% of spend. Routing lives only in persona
frontmatter. The table below is the rendering of it. `chief` is a routing profile that the driver
reads; it is never rendered as a spawnable agent.

| Role | Claude | Codex | Notes |
| --- | --- | --- | --- |
| chief (root session) | Opus 5.5, medium | GPT-6.1 Sol, medium | standard context; effort held constant within a session so the cache holds |
| builder | Sonnet 5.5, medium | Sol, medium | `judgement`: Opus 5.5 high / Sol high; `mechanical`: Haiku 4.5 / Luna |
| reviewer | Opus 5.5, high | Sol, high | read-only; design, plan, boundary, data and acceptance lenses; acceptance may use xhigh |
| security-reviewer | Opus 5.5, high | Sol, high | read-only; triggered by `risk: safety` |
| advisor | Fable 5.1, high | GPT-6 Astra, high | read-only; escalations and council members |
| exploration | native Explore / Haiku | Luna, low | no persona; harness built-in |

The reviewer's **data lens** carries the data-plane checks of the retired migration validator, for
designs and tasks marked `risk: data`:
- the migration parses and applies to a scratch database;
- backfill and rollback are stated;
- a migration contract test exists and runs in the gate;
- an index exists for every new query plan;
- retention and erasure paths are covered.

**Cross-vendor rule.** At design, plan and acceptance, the reviewer comes from the other vendor
than the chief. It is invoked as a one-shot call that is read-only by construction:
- `codex exec -s read-only --ignore-user-config --ignore-rules`;
- or `claude -p --tools Read,Grep,Glob --strict-mcp-config`.

Neither call loads the user's MCP servers, apps or other integrations, so a judge has no mutating
surface besides the sandboxed shell. `--allowedTools` alone would only pre-approve tools; it would
not remove the others. If the other
vendor's quota is exhausted, the same vendor is used in a fresh context and the verdict header
records why. Re-pricing the earlier experiment at current rates puts a one-shot cross-vendor
review at about 0.77× the in-harness cost. In that experiment the cross-vendor reviewer caught an
invented API that the same-vendor reviewer missed.

**Quota balance.** Most tokens sit with the chief and builders, so alternate the chief's harness
between projects rather than within a run.

## The run

```
approve ──► run_goal.py ──► session (chief) ──► per task: dispatch → check → guard → [risk review] → commit+tick
                 ▲                │                                                  │
                 │                └── milestone close: receipts (full_gate, e2e, proofs) → acceptance → tag
                 └── fresh session per milestone or envelope, until goal done | all parked | stall | quota
```

### Starting

After approval the chief tags the approval commit as `goal/<id>/approved` and records
`baseline.json` by running `full_gate` once on the base commit. It then either works interactively
or starts the driver for multi-day runs:

- **Interactively:** native `/goal` in either harness, with the condition "`goal.py done` exits 0
  for the active milestone, or stop after N turns".
- **Driver:** `python3 <skill>/scripts/run_goal.py --goal G-3 --harness claude|codex`.

### Launch profiles

The driver launches each session with the chief profile's model and effort, plus a profile that
lets the chief edit, commit and run the declared gates with no human present. Smoke runs prove
both profiles (F-3 AC-2).

| Harness | Command shape | Permissions |
| --- | --- | --- |
| Claude Code | `claude -p --model <m> --effort <e> --permission-mode auto --settings .runs/<goal>/claude-settings.json --output-format json "<resume prompt>"` | The settings file allows `git add`/`git commit`, the plan's gate commands and the skill's scripts. It registers the Stop and SessionStart hooks. Auto mode's reviewer decides the rest. A denial is logged, never retried blindly. |
| Codex | `codex exec -s workspace-write --approve-for-me -m <m> -c model_reasoning_effort=<e> --json "<resume prompt>"`, adding `-c sandbox_workspace_write.network_access=true` when `run.network` is true | The workspace-write sandbox covers the repository. Automatic approval review handles the rest. Hooks come from the project's Codex hook configuration, which migration writes. |

`GOAL_ROLE=chief` is set in the session environment. Judge and advisor calls set
`GOAL_ROLE=judge`.

### Driver

`run_goal.py` is a foreground loop, not a service. Each iteration does three things:

1. It selects the active milestone: the first one without a `goal/<id>/M<n>` tag.
2. It launches one fresh headless chief session with the resume prompt:
   - the goal line;
   - the active milestone;
   - `goal.py status`;
   - the progress tail.
3. It enforces the session envelope, `run.session_hours`, by ending the session when it expires.

Progress means newly completed tasks (ticked, committed and guard-clean) or a new milestone tag.
Commits, verdicts and Queue entries alone are not progress. The driver stops when one of these
holds:

- the goal is done;
- every remaining task is parked or waiting on the Queue;
- two consecutive sessions made no progress (a stall);
- the harness reports quota exhaustion and the retry window has run out. It retries with backoff,
  so an overnight quota reset continues the run.

A fresh session per milestone or envelope replaces compaction. Vendor guidance and practitioner
reports agree that a fresh window seeded from files drifts less than a long compacted one.
Per-session usage from the CLI's JSON output is appended to `progress.md`.

### Stop hook (both harnesses)

`goal.py stop-hook` is wired as the Stop hook in both Claude Code and Codex. It is active only when
`.runs/active` names a goal and `GOAL_ROLE` is unset or `chief`. A reviewer or advisor session
therefore always stops freely. When the active milestone is not done, the hook blocks the stop with
a reason that re-anchors the session:

> Goal G-3: <outcome>. Not done: T4 unchecked; no full_gate receipt for the candidate tree. Next ready: T4 (covers AC-3).

It allows the stop when any of these holds:

- there have been three consecutive blocks without progress, as defined above; the hook logs
  `STALLED`;
- every remaining task is parked;
- the session envelope has expired.

Claude Code's own cap of eight consecutive blocks is a further backstop.

### Per task

1. **Select.** `goal.py next` returns the next ready task: its `needs` are done, it is not parked,
   and its `writes` do not overlap a running task.
2. **Dispatch.** The chief sends the builder a compact packet:
   - the goal line;
   - the task block;
   - the criteria text;
   - the path of the relevant design section;
   - the gate command;
   - the stop conditions.

   Paths are passed, not pasted. A task the chief can finish in a handful of tool calls, it does
   directly.
3. **Check.** `gate.py check --cmd "<gate>"` runs on the working tree and writes no receipt. A
   task-level check only gates the commit; receipts belong to committed trees.
4. **Guard.** `goal.py guard --task T4` runs over the working-tree diff, using the same rules as
   at completion (Tools).
5. **Risk review.** `risk: safety` brings the security reviewer onto the task diff. `boundary` or
   `data` brings the reviewer with the matching lens.
6. **Commit and tick.** One commit carries `[T4]`, the task's changes, the checkbox tick and one
   progress line.

A failed check or guard goes back to the same builder, resumed rather than respawned, with the
output. Attempts are counted in `attempts.json`. After two failed attempts the chief restarts the
builder fresh once. If that also fails, the task is parked `[!]` with a diagnosis, escalated as a
consequential decision (Escalation), and other ready work continues.

### Milestone close

1. With the tree committed and clean, `gate.py receipt` runs `full_gate`, `e2e` and every
   automatic proof command. Each run produces a receipt bound to (tree, exact command), and any
   older receipt for that pair is deleted before the run.
2. `goal.py evidence --milestone M1` writes the evidence record (below).
3. Cross-vendor acceptance reviews the milestone diff, the criteria and the evidence record, and
   names the tree it judged.
4. When `goal.py done --milestone M1` passes, the chief tags `goal/<id>/M1`, regenerates the
   explainer and writes the founder digest. The next milestone continues on the same branch,
   normally in a fresh session.
5. The founder merges by tag whenever they choose. Several milestones can be merged at once.

## Tools

The tools are standard-library Python. `execution-methodology` plus `agent-personas` hold at most
2,500 non-test lines.

| Tool | Does | Prevents |
| --- | --- | --- |
| `goal.py lint` | Checks plan structure. (a) Ids are unique. (b) `writes` and `covers` are non-empty. (c) `needs` resolve. (d) `covers` names real `AC-n`. (e) Every milestone criterion has a proof entry. | Plans the scheduler cannot run (a third of past plan blockers); criteria without proof |
| `goal.py status / next` | Reports milestone and task states, the active milestone and the next ready task. | Resume-from-memory drift |
| `goal.py guard` | Runs three checks. **Scope:** changed paths ⊆ the task's `writes`, plus admitted controller metadata in `plan.md`. **Test integrity:** existing test files are not modified or deleted outside `tests-may-change`, and no skip/only/xfail markers are added. **Frozen inputs:** since `goal/<id>/approved`, `spec.md` and `design.md` are unchanged, and `plan.md` changes only checkboxes, `Decisions` and `Queue`. | Out-of-scope edits (116 of 558 files historically); test tampering (no check existed); plan drift |
| `goal.py done` | Checks the active milestone on its candidate tree (HEAD). (a) Every task is `[x]`. (b) Every commit since the milestone base names a task. (c) Guard passes for every task commit over its own diff. (d) Receipts pass for `full_gate`, `e2e` and every automatic proof, each for this tree and the plan's current command. (e) A PASS acceptance verdict names this tree for every partition the milestone declares (one by default). For completed milestones it verifies the same against their tag's tree. | Premature "done"; text-only completion claims; guards skipped mid-run |
| `goal.py stop-hook` | Implements the Stop-hook behaviour above. | Sessions ending early or looping |
| `goal.py evidence` | Writes the milestone evidence record. | Hand-written status reports |
| `gate.py check` / `gate.py receipt` | Runs the command and records the exit status and the executed, failed and skipped counts. Counts come from unittest, pytest, Gradle or JUnit XML newer than the run start, summed across every summary in the output. Failures are identified by test id. Gradle runs must carry `--rerun-tasks`. It fails on any of: (a) a nonzero exit; (b) an exit/verdict mismatch; (c) zero executed tests, unless the command is declared `count: none`; (d) failures not in `baseline.json`; (e) a tracked file changed by the run. `receipt` additionally requires a clean committed tree, deletes any prior receipt for (tree, command) first, and writes the new one. | Unexecuted greens; cached results; misattributed pre-existing failures; gates that dirty the tree; fail-open launchers; stale receipts |
| `review.py` | Builds the review packet from `references/review.md` and the given paths, and runs the other vendor's CLI read-only by construction, with integrations excluded and `GOAL_ROLE=judge`. It writes the verdict with a vendor/model/effort/tree/round header. It refuses a third round on a subject. | Unbounded review loops; reviewer contamination; judges triggering the Stop hook |
| `run_goal.py` | Runs the driver loop above. | Multi-day runs depending on one session's context; runaway sessions |

## Review and triage

| Point | Reviewer | Why here |
| --- | --- | --- |
| Design, before approval | cross-vendor reviewer | the highest measured yield: 0.74 blockers per artifact |
| Plan, before approval | cross-vendor reviewer | decomposition, write sets, gates, proofs, milestone sizing |
| Task with `risk: safety` | security-reviewer | the best catch record in the repository, including fail-open guards |
| Task with `risk: boundary` or `data` | reviewer, matching lens | durable interfaces and data changes are expensive to unwind |
| Milestone acceptance | cross-vendor reviewer | one whole-diff review catches what per-task review catches, at a fraction of the cost |

There is no default per-task review of ordinary tasks. Implementation review measured 0.09
blockers per artifact, while the gate, guards and proofs cover the mechanical failures and
acceptance reviews the whole diff. A large milestone may declare `acceptance: [<partition>, …]`
in the plan to split acceptance across parallel reviewers over disjoint file partitions. Each
partition has its own round cap, and completion needs a current PASS from every partition.

**Findings.** The reviewer reports everything. It is not told to be conservative, because current
models follow that literally and under-report. Each finding carries a class:

- `correctness`, `safety` or `requirement` **block**, but only when the finding names a reachable
  trigger and an observable consequence.
- `other` (style, hardening, preference, methodology form) **never blocks**. These findings are
  listed as optional in the explainer, and the founder can promote one.

**Closure.**
- Where it can, a blocking finding becomes a test that fails before the fix and passes after it;
  the gate then proves closure.
- Otherwise one scoped rereview of the correction runs.
- If the subject is still blocked after that rereview, the loop ends:
  - **Design or plan:** the issue returns to the founder at approval.
  - **Risk review:** the task is parked.
  - **Acceptance:** the milestone is NOT READY and is queued for the founder with the advisor's
    recommendation attached.
- No escalation buys an extra review round. A renamed attempt is the same subject.

## Escalation

| Situation | Action |
| --- | --- |
| A reversible choice inside the approved outcome (naming, test level, local structure, ordering) | Take the smallest option consistent with existing patterns, log it in `Decisions`, continue. |
| A consequential choice: unspecified behaviour with several valid designs, or a task parked after its attempts | **Advisor:** one read-only call to the stronger model with the question, options, constraints and evidence paths. It returns a recommendation, a confidence level and whether the choice is reversible. High confidence and reversible: adopt it, log "advisor". A parked task then gets one new attempt, judged by its deterministic check and guard. Otherwise go to the council. |
| Advisor not confident, or the choice is costly to reverse | **Council:** three independent read-only members spanning both vendors (two advisors and a reviewer), one round, then the chief synthesises. Unanimous and reversible: adopt it, log "council". Otherwise park the item and queue it. |
| A review still blocked after its rereview | Queue it for the founder with the advisor's recommendation attached; never closed automatically. |
| A change to criteria, scope or a durable interface; any safety-policy change; any external or irreversible action (merge, deploy, data deletion, paid service, credentials) | Never escalated. Queue it, block only the dependent tasks, continue with the rest. |

Limits:

- one advisor call and one council per item;
- at most three councils per milestone;
- missing approval is never inferred from silence;
- every default and escalation result appears in the merge explainer, so the founder can reverse
  it before merging.

## Milestone sizing

A milestone is the largest batch where all of the following hold:

- Every criterion has a proof command that runs in about 15 minutes or less, or is explicitly
  `manual`. A milestone whose criteria are mostly manual is a founder walkthrough, not an
  unattended milestone.
- It contains at most one durable-boundary decision, and that decision is made at approval.
- It has 4–10 tasks, starting with a walking skeleton that proves the journey end to end.
- Its merge diff is reviewable in about 30 minutes: roughly 1,500 product lines or fewer, with
  deletions counted separately.

A goal holds one to three milestones, so one approval buys one to several days of unattended work.
A plan that breaks a sizing rule states the exception and how acceptance is partitioned.

## Evidence record and explainer

`goal.py evidence` writes `.runs/<goal>/<M>-evidence.md`. The builder never writes it.

```
M1 — READY | NOT READY        base <sha> → tree <sha>
Criteria: AC-1 → python3 -m unittest tests.billing.test_refund → PASS (12 run) · AC-3 → manual
Gate: make check exit 0 · 1,240 run / 0 failed / 5 skipped (baseline 5) · tree clean
E2E: make e2e exit 0
Guard: scope 0 escapes · tests 0 unapproved edits · frozen inputs unchanged (all task commits)
Review: codex gpt-6.1-sol high · rounds 1 · blocking open 0 · optional 4
Security: T3 PASS | not triggered
Decisions taken: 3 (2 default, 1 advisor) — listed
Diff: product +1,120/−340 · tests +610/−20 · docs +90
Usage: claude 2.1M tok · codex 0.6M tok (from CLI JSON)
```

The explainer is `references/explainer-template.html`, a self-contained interactive page. The chief
fills its JSON data block.

- **At approval** it shows the outcome, journeys, criteria with their proofs, design choices with
  the alternatives considered, the milestone and task map, grants, and open decisions with
  recommendations.
- **At merge** it shows the evidence record, the decisions taken and the optional findings.

In Claude Code it may be published as a private Artifact; otherwise it is opened locally.

## Distribution and migration

This repository's `install/` is the single authored source. `install.sh` copies it to
`~/.claude` and `~/.codex`, renders the personas for both harnesses, and registers the session and
Stop hooks. Removed:

- the private re-vendoring loop;
- the runtime pin: `runtime.json`, approved bundles and `sync_methodology.py`;
- the mirror-drift checks that the pin required.

A project records the version it follows in one line of its `AGENTS.md`.

**Published skills:** `execution-methodology`, `agent-personas`, `progressive-disclosure` and
`graph-navigation`.

**Installing does not remove v5.1 global files.** After every project is migrated, the founder
runs `install.sh --retire-v5`. It deletes only files matching the known v5.1 set and reports
anything else.

**Until a project is migrated, v6 refuses to execute in it.** The v6 skill's first step and
`goal.py` stop with an actionable message when the project carries `docs/agents/execution/runtime.json`.
The session hook prints the same notice. The project's approved v5.1 bundle under `approved-runtimes`
is left untouched for reference. v6 runs no v5.1 lifecycle; the founder migrates the project and
then executes.

**Migration** is manual and per project, following `references/migrate.md`:

1. Finish or stop the in-flight milestone.
2. Map the overlay's project-specific invariants into the next goal's spec or design.
3. Remove the runtime pin and overlays.
4. Add `/.runs/` to `.gitignore` and write the Codex hook configuration.
5. Update the project's route rows.
6. Write the next goal in the v6 layout.

## Deleted, and why

| Removed | Replaced by | Why it goes |
| --- | --- | --- |
| Three founder gates; per-action grants | one goal approval and per-milestone merge | approvals never drained, and mechanical fixes were routed to the founder |
| Light/Full lanes, task cards, `validate_card.py`, `task-card.md` | the plan's task block with `risk:` | 2,256 lines for 18 keys; lane rules generated duplicate cards and reviews |
| Per-task reviewer and scoped rereview by default | risk-triggered task review and milestone acceptance | 0.09 blockers per artifact; 11 of 13 first rounds blocked while acceptance never did |
| `test-judge` persona, `start_junit_run.py`, nonce protocol | `gate.py`, which executes the command itself | every sampled test-judge FAIL was environmental or pre-existing, and one judge mis-added counts |
| `verify_junit.py` expected-class counts | per-criterion proof commands with executed counts | the same protection, bound to criteria instead of class lists |
| `milestone_seal.py`, `gate-sandbox` skill | `gate.py` receipts and `goal.py done` | the seal and launcher both failed open; the sandbox existed only for read-only test judges |
| `check_review_budget.py`, round grants | `review.py` refuses a third round | 1,630 lines to count to two; it misread persona sources as verdicts |
| `trace_check.py`, criterion-id carriers | proof commands in the plan | inert: 0 of 5,866 tests carried an id |
| `plan_waves.py`, resume pointers, ledgers | `goal.py` over plan checkboxes and git | one parser for one plan format |
| `spec_check.py` | `goal.py lint`; specs are read by reviewers | most findings were its own front-matter format |
| `ratio_meter.py`, `weekly_review.py`, LEDGER duties | usage lines in progress and evidence | measurement is not a gate; units were conflated |
| A/B/C recovery, companion-path and proof amendments | retry, fresh restart, park, escalate | each route needed its own fresh review, and they became founder transactions |
| `methodology-management`, `project-onboarding`, `project-migration`, `project-conformance`, `agent-persona-factory` | `references/migrate.md` | maintenance surface for the runtime pin and lane machinery that no longer exist |
| Personas: planner, docs-steward, contract-architect, architect, product-steward, chief-of-staff (as a subagent), developer, senior-developer, scout, test-judge, migration-validator, acceptance | the chief profile; builder; reviewer lenses; Explore | persona prose measurably helps nothing; tool restriction and model choice do |

Kept, because each has caught real defects:

- a builder never approves their own work;
- judges are structurally read-only;
- fresh-context review;
- the security reviewer;
- executed-count gating;
- the write-boundary check;
- the push guard's secret and identifier scans;
- gates run locally.

## Evidence

Repository measurements were taken on HEAD `3bd256d` and in sampled run workspaces on 2026-10-06:

- size and instruction load;
- the review-yield split: 0.74 blockers per design artifact against 0.09 per implementation
  artifact;
- first-round block rates and acceptance rates;
- the causes of test-judge failures;
- cost shares: controllers 68%, coordination calls 31%, and the builder tier split.

External sources, checked 2026-10-06:

- **Anthropic:**
  - Claude Code best practices, subagents, `/goal`, hooks, headless and costs docs;
  - per-model prompting guidance for Opus 5/5.5, Sonnet 5.5 and Fable 5/5.1: over-engineering,
    legacy verification scaffolding, literal "conservative" reviewers, auditing claims against
    tool results, and no more than two or three automatic continuations;
  - "Building effective agents";
  - the multi-agent research system: about 15× tokens, and a poor fit for coding;
  - harness design for long-running apps: a $9 solo run against a $200 harness; remove one
    component at a time;
  - the C compiler: the verifier must be nearly perfect;
  - the April 23 postmortem: eval every prompt change.
- **OpenAI:**
  - Codex `/goal`, hooks, subagents, non-interactive mode and worktrees;
  - long-horizon tasks (Prompt/Plan/Implement/Documentation files);
  - ExecPlans;
  - GPT-5.6 prompt guidance: leaner prompts scored +10–15% at 33–67% lower cost, and conflicting
    rules are worse than missing detail;
  - GPT-6 Astra guidance: audit skills and AGENTS.md, and no approval flows for hypothetical risk;
  - "A practical guide to building agents": single agent first.
- **Independent:**
  - the MAST multi-agent failure taxonomy: termination and verification failures;
  - Cognition, "Multi-agents: what's actually working": writes stay single-threaded, and a fresh
    reviewer finds about 2 bugs per PR;
  - ETH Zurich on AGENTS.md: no significant gain, at more than 20% extra cost;
  - CodeRabbit in the wild: 56% of AI review comments rejected;
  - METR on merge-worthiness;
  - Agent OS v3, which cut about 70% of its framework.
