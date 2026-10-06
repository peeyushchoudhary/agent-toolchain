---
id: F-3
title: Lean goal execution (methodology v6)
prd: docs/product/README.md
status: approved
updated: 2026-10-06
milestone: M3
edge_cases: [first-run, interrupted, stalled, repeated-failure, founder-unavailable, quota-exhausted, harness-switch, unmigrated-project]
---

# F-3 — Lean goal execution (methodology v6)

## Why

The founder runs several projects alone and wants approved goals carried to merged, validated
milestones with little attention, at low cost, without drift or over-engineering. The shipped
methodology (v5.1) does not deliver that. Measured on this repository and its sampled runs:

- **Overhead.** About 47,500 words of prose, 25,500 lines of scripts and 46,000 lines of tests.
  A chief loads about 15,800 words before reading any task. A six-task milestone takes 70–90 agent
  steps, 30+ fresh model contexts and 4–7 founder transactions.
- **Low-yield judging.** 11 of 13 first-round task reviews blocked and 6 of 6 acceptances passed.
  About a third of blockers policed the methodology's own forms. The criterion-trace checker is
  inert (0 of 5,866 tests carry an id), and every sampled test-judge failure was environmental or
  pre-existing.
- **Cost.** In one measured three-week project, controllers (a root session above a chief
  subagent) took 68% of spend, and 31% of tool calls were coordination polling. Builders ran 99%
  on the expensive tier.
- **Stalls and drift.** Runs ended parked on authority boundaries rather than merged. One
  prerequisite grew its own dispatcher, schemas and reviews while core work never started.

Vendor guidance for the current models (Claude Fable 5.1, Opus 5.5, Sonnet 5.5; GPT-6 Astra,
GPT-6.1 Sol, Luna) says the same thing. Start from a single agent and add complexity only when it
measurably pays. Keep instruction files short and free of conflicts, and remove legacy verification
scaffolding. Make "done" a runnable check. Keep writes single-threaded, and let extra agents add
judgement rather than actions. The evidence is in [design § Evidence](../../architecture/lean-execution.md#evidence).

## Outcome

One approval per goal and one merge decision per milestone. In between, the chief-of-staff runs
the approved plan unattended on the laptop for hours to days, in Claude Code or Codex. Completion
is decided by executed checks, cross-vendor review covers the high-yield points, and the process
is small enough to read in one sitting.

## Scope

**In:**
- The execution methodology skill: its rules, references, tools and hooks.
- The persona pool and its rendering for both harnesses.
- Retiring the v5.1 machinery and the maintenance skills that exist to serve it.
- The repository's own gate, installer and documentation to match.
- A manual per-project migration procedure.

**Out:**
- Hosted CI and cloud execution.
- Deployment automation.
- A daemon or service. The session driver is a foreground script.
- A benchmark or measurement apparatus.
- Migrating any private project. Each one migrates manually, when the founder triggers it.
- Global installation without an explicit grant.
- Changes to the founder's private global instruction files. Proposed text is supplied for the
  founder to apply.

## Actors

- **Founder:** approves goals, answers queued decisions, merges.
- **Chief-of-staff:** the root session in either harness. It plans, dispatches, runs gates,
  commits and keeps state.
- **Builder:** a subagent that writes code inside one task's write set.
- **Reviewer:** read-only, fresh context, from the other vendor at design, plan and acceptance.
- **Security reviewer:** read-only, triggered by risk.
- **Advisor:** a stronger model consulted to resolve escalations.

## Journeys

1. **Approve a goal.**
   1. The founder states a goal. The chief interviews them and drafts `spec.md`, `design.md` and
      `plan.md`, each holding current decisions only.
   2. Cross-vendor reviews of the design and the plan run, and findings are corrected.
   3. The chief generates an interactive HTML explainer. The founder reads it, asks questions, and
      approves the package with its grants.
2. **Run unattended.**
   1. The founder starts the run.
   2. For each milestone, the chief works through the ready tasks:
      1. dispatch the builder;
      2. run the task gate and the guards;
      3. run risk-triggered security review;
      4. commit;
      5. tick the box.
   3. Each milestone closes with the full gate, the end-to-end gate and cross-vendor acceptance.
      The run then continues to the next milestone in a fresh session, stacked on the accepted
      branch.
   4. The run ends when the goal is done, when the remaining work is blocked, or on a stall or
      exhausted quota.
3. **Decision during a run.**
   1. For a reversible choice inside the approved outcome, the chief takes the recommended default
      and logs it.
   2. A consequential choice goes to the advisor, or to a council of three experts drawn from both
      vendors. If confidence is high and the choice is reversible, the run adopts it and logs it.
      Otherwise the chief parks the affected item and continues with independent work.
   3. A review that is still blocked after its one correction goes to the founder with the
      advisor's recommendation attached.
   4. External, irreversible and safety-policy actions always wait for the founder.
4. **Merge.** The founder opens the milestone explainer and evidence record, reviews any defaults
   taken, and merges or sends back.
5. **Migrate a project.** The founder invokes migration in one project. The chief maps that
   project's v5.1 artifacts to v6 and removes the runtime pin; the project's next goal then runs
   on v6. Once every project is migrated, the founder runs `install.sh --retire-v5`.

## Acceptance criteria

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | Founder touchpoints are exactly goal approval (spec+design+plan with explainer) and merge per milestone. Merges may be batched, and queued decisions are answered asynchronously. No other routine founder transaction exists. | Rules text; reviewer check against the journeys |
| AC-2 | The chief is the root session. A goal with two or more milestones runs unattended across fresh sessions until done, all-blocked, stall, or quota exhaustion, in both harnesses. The headless launch profile of each harness is specified: sandbox, approval mode, writable paths and network. It is proven able to edit, commit and run the declared gates. | Driver tests with a fake harness; a two-milestone smoke run per harness with the new hooks registered in isolation |
| AC-3 | "Done" is computed deterministically. For the active milestone it requires all four of the following on the milestone's candidate tree. Completed milestones are verified against their tags, never against a later HEAD. | Tool tests |
| | 1. every task is ticked; | |
| | 2. passing receipts exist for `full_gate`, `e2e` and every criterion's proof command; | |
| | 3. the integrity guards pass over every task commit; | |
| | 4. a PASS acceptance verdict names that tree. | |
| AC-4 | Drift guards are mechanical and are re-validated by "done", not left to a step the chief must remember. A task's changed paths stay inside its `writes`; changes to the plan's checkboxes, `Decisions` and `Queue` are controller metadata and always admitted. Existing tests are not edited or deleted, and skips are not added, unless the plan allows it. Spec, design and the plan's frozen sections do not change after approval, and a run cannot add tasks. Task attempts persist across sessions. A wall-clock envelope bounds each session. A stall ends the run: no newly completed task in two sessions. | Tool tests over fixture repositories |
| AC-5 | The gate fails on: a nonzero exit; an exit/verdict mismatch; zero executed tests; failures not in the baseline; a tree changed by the gate. Receipts exist only for a clean committed tree. Each receipt is bound to the tree and the exact command, and is invalidated before any rerun. Pre-commit task gates are checks without receipts. | Tool tests |
| AC-6 | Cross-vendor review runs at design, plan and acceptance. Judges run with a structurally restricted tool set and are exempt from the execution Stop hook. Findings are classed, and only correctness, safety or requirement findings with a trigger block. Each subject gets at most one correction and one scoped rereview. A subject that is still blocked after its rereview goes to the founder with advice; it never gets an automatic extra round. | Rules text; review wrapper tests |
| AC-7 | Escalation is bounded. Default-and-log covers reversible choices. Advisor or council (≤3 members, one round) covers consequential choices, and it may unblock only items whose closure is deterministic (gate and guard) or a pure choice. External, irreversible and safety-policy actions are never escalated. Every default taken appears in the merge explainer. | Rules text; escalation reference |
| AC-8 | Model and effort routing lives only in persona frontmatter, including a non-spawnable chief profile that the driver reads. No `xhigh` default except acceptance. No chief subagent under a root session. Builders default to the mid tier. Judging roles render without write, edit or agent-dispatch capability in both harnesses. | Persona and renderer tests, including negative capability tests |
| AC-9 | Size ceilings: the rules core is ≤1,500 words; any one role loads ≤3,000 words of methodology; `execution-methodology` plus `agent-personas` hold ≤2,500 non-test code lines; there are ≤5 persona sources. | A size test in the repository gate |
| AC-10 | Retired machinery is deleted. No dangling reference to it remains in `install/` or the routed docs. Every task commit leaves the route valid, and the repository gate passes. | `install/verify.sh`; pre-commit route check; grep |
| AC-11 | Both harnesses get equivalent personas, hooks and instructions from one source. | Renderer tests |
| AC-12 | A documented manual migration path takes a v5.1 project to v6. Until then, v6 refuses to execute in an unmigrated project and tells the founder to migrate it. Global v5.1 files are removed only by an explicit `install.sh --retire-v5`. | Migration reference; hook and installer tests |
| AC-13 | `progressive-disclosure` loses at least half of its non-test code lines, and the push guard's secret and identifier behaviour is unchanged. | Line count; existing guard tests |

## Non-functional constraints

- The repository stays public-safe: no project names, personal paths, account identifiers or private facts.
- Python 3.10+ standard library only, macOS and Linux.
- Documents hold current state, and git holds history.

## Founder decisions (2026-10-06)

1. **Source of truth.** This repository's `install/` is the single authored source. `~/.claude` and
   `~/.codex` are install targets only.
2. **Grants.** Local commits, and pushing the `v6-lean-execution` branch once M3 is READY. Merge to
   `main` stays with the founder.
