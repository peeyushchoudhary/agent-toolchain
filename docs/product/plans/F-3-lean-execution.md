---
goal: F-3
title: Lean goal execution (methodology v6)
spec: docs/product/specs/F-3-lean-execution.md
design: docs/architecture/lean-execution.md
status: approved
updated: 2026-10-06
gate: rc=0; for d in execution-methodology agent-personas progressive-disclosure; do [ -d install/skills/$d/tests ] || continue; python3 -m unittest discover -s install/skills/$d/tests -t install/skills/$d/tests || rc=1; done; exit $rc
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
e2e: python3 install/skills/execution-methodology/tests/smoke_goal.py --harness claude && python3 install/skills/execution-methodology/tests/smoke_goal.py --harness codex
run: {network: true, session_hours: 3}
grants: [local-commit, push-branch]
---

# F-3 plan — lean goal execution

This plan uses the v6 plan format it introduces. v6 does not exist yet, so the chief (the root
Claude Code session) executes it by hand, using each new check as soon as the task delivering it
lands.

**Branch.** `v6-lean-execution`. Local commits are granted, and pushing this branch once M3 is
READY. Merge, global installation and private-file edits are not granted; see
[Grants requested](#grants-requested).

**Commit rules.** Every task commit:
- leaves the per-task gate runnable and green;
- passes the installed pre-commit route and identifier checks;
- deletes or repairs, in the same commit, the tests and inbound links that its own change breaks.

`tests-may-change` lists exactly the existing tests each task may edit or delete.

**Cross-vendor review.** Codex `gpt-6.1-sol` at `xhigh` reviews the design and this plan before
approval and performs milestone acceptance. The founder chose this model and effort for this goal;
the v6 default is `high`.

## M3 — v6 core replaces v5.1

criteria: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12
proofs:
- AC-2: e2e
- AC-3, AC-4, AC-5: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_g*.py'
- AC-6, AC-7: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_review*.py'
- AC-8, AC-11: python3 -m unittest discover -s install/skills/agent-personas/tests -t install/skills/agent-personas/tests
- AC-9, AC-10, AC-12: full_gate
- AC-1: manual — founder confirms the two-touchpoint workflow in the merge explainer

acceptance: [tooling, retirement]

**Sizing exception.** M3 has 7 tasks but a large diff, mostly deletions of about 37,000 lines.
Acceptance is therefore split across two parallel cross-vendor reviewers over disjoint partitions,
`tooling` (T1, T3, T4, T6) and `retirement` (T2, T5, T7). Completion needs a current PASS from both,
and each has its own round cap. Deletions are summarised by path, not read line by line.

The walking skeleton is T1: a fixture goal in a throwaway repository is linted, checked, guarded,
receipted and judged done before any prose changes.

### [ ] T1 — `goal.py` and `gate.py`
- writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/test_gate.py, install/skills/execution-methodology/tests/fixtures/**, .gitignore
- needs: —
- covers: AC-3, AC-4, AC-5
- risk: none
- builder: judgement
- tests-may-change: —

**Scope.** Implement the plan parser, the `lint`, `status`, `next`, `guard`, `done`, `stop-hook`
and `evidence` subcommands, and `gate.py check` and `gate.py receipt`, exactly as specified by the
design's Tools table and run sections. This includes:
- controller-metadata admission for `plan.md`;
- `attempts.json`;
- the `GOAL_ROLE` exemption;
- the session-envelope allowance in the stop hook;
- receipts bound to (tree, command), with invalidation before rerun;
- completed milestones verified against their tags.

Counts are parsed from unittest, pytest, Gradle and JUnit XML output. Add `/.runs/` to
`.gitignore`.

**Tests.** They build throwaway git repositories and cover every way to fake progress:
- an out-of-scope edit, and a checkbox tick that is admitted;
- a deleted test, a weakened assertion and an added skip, each with and without
  `tests-may-change`;
- an edited frozen section;
- an exit-0 run printing a failure verdict, and a gate that dirties the tree;
- zero executed tests, and a baseline failure;
- a stale receipt after a failed rerun, and a receipt for the wrong command;
- a dirty-tree receipt refusal;
- `done` on a later milestone while the earlier one is verified by its tag;
- stop-hook block text, its stall cap, the judge exemption and envelope expiry.

### [ ] T2 — rules, references, explainer template
- writes: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/methodology.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/run.md, install/skills/execution-methodology/references/review.md, install/skills/execution-methodology/references/escalation.md, install/skills/execution-methodology/references/migrate.md, install/skills/execution-methodology/references/explainer-template.html, install/skills/execution-methodology/agents/openai.yaml, install/skills/execution-methodology/tests/test_methodology_policy.py, install/skills/execution-methodology/tests/test_execution_loop.py, install/skills/execution-methodology/tests/test_shape_diagram.py, install/skills/execution-methodology/tests/test_break_tests.py, install/skills/execution-methodology/tests/test_repo_sync.py, install/skills/execution-methodology/tests/test_rules.py
- needs: T1
- covers: AC-1, AC-6, AC-7, AC-9, AC-12
- risk: none
- builder: judgement
- tests-may-change: install/skills/execution-methodology/tests/test_*.py except test_goal.py and test_gate.py (any v5.1 test that asserts replaced prose or references)

**Scope.** Replace the v5.1 rules with:
- **`methodology.md`:** the chief's rules, at most 1,500 words.
- **The new references:** planning, run, review, escalation, migrate.
- **The explainer template:** self-contained, with a JSON data block and approval and merge views.

Old reference files stay on disk, unrouted, until T5 deletes them with their inbound links.

**Tests.** Delete the tests that pin v5.1 prose. Add `test_rules.py`, which asserts behaviour-level
facts only: that the routes and paths named in the skill exist, and the word ceilings.

**Style.** Write calmly: give the reason for each rule and use no capital-letter emphasis.

### [ ] T3 — personas and renderer
- writes: install/skills/agent-personas/**, install/skills/execution-methodology/scripts/sync_methodology.py, install/skills/execution-methodology/scripts/sync_methodology_selftest.py, install/skills/execution-methodology/scripts/runtime-status.schema.json, install/skills/execution-methodology/tests/test_runtime_status.py, install/skills/execution-methodology/tests/test_sync_preview.py, install/skills/execution-methodology/tests/test_onboarding_adoption.py
- needs: T2
- covers: AC-8, AC-11
- risk: safety
- builder: judgement
- tests-may-change: install/skills/agent-personas/tests/**, install/skills/execution-methodology/tests/test_runtime_status.py, install/skills/execution-methodology/tests/test_sync_preview.py, install/skills/execution-methodology/tests/test_onboarding_adoption.py

**Pool.** It becomes `builder`, `reviewer` (with design, plan, boundary, data and acceptance
lenses), `security-reviewer`, `advisor`, and the non-spawnable `chief` routing profile. Each is at
most 300 words, and its frontmatter carries the design's routing table.

**Removals.** Remove the other persona sources and the persona-factory references.

**Renderer.** `sync_personas.py` renders the spawnable four for both harnesses. Trim it so that
`execution-methodology` plus `agent-personas` stay within the 2,500-line ceiling.

**Tests.** Cover rendering parity and the AC-8 routing assertions. They also include negative
capability tests: a rendered judge in either harness has no write, edit, shell-write or
agent-dispatch capability.

`risk: safety` applies because judges' inability to write is a safety property. The security
reviewer checks the renderer diff.

### [ ] T4 — `review.py`, `run_goal.py`, hooks, smoke run
- writes: install/skills/execution-methodology/scripts/review.py, install/skills/execution-methodology/scripts/run_goal.py, install/skills/execution-methodology/tests/test_review.py, install/skills/execution-methodology/tests/test_run_goal.py, install/skills/execution-methodology/tests/smoke_goal.py, install/hooks/goal-session.sh
- needs: T1, T2, T3
- covers: AC-2, AC-6, AC-12
- risk: none
- builder: judgement
- tests-may-change: —

**`review.py`.** It runs judges read-only by construction:
- `codex exec -s read-only --ignore-user-config --ignore-rules`;
- `claude -p --tools Read,Grep,Glob --strict-mcp-config --setting-sources project,local`.

Both run with no user integrations loaded and with `GOAL_ROLE=judge`, at the reviewer frontmatter's
model and effort. Tests assert the constructed commands. The smoke run asserts that a judge in each
harness cannot write a file in the fixture. It caps rounds and
handles the same-vendor fallback.

**`run_goal.py`.** It implements the design's driver:
- the launch profiles for both harnesses;
- active-milestone selection;
- the session envelope;
- progress as newly completed tasks;
- stall, all-parked and quota-backoff exits;
- usage capture.

**Tests.** Unit tests use a fake harness executable on `PATH`.

**`smoke_goal.py`.** It builds a two-milestone, three-task fixture goal in a temporary repository
and registers the new hooks only inside that repository: Claude through `--settings`, Codex through
the project hook configuration. It drives the goal with the real CLI and asserts:
- a premature stop was blocked;
- milestone M1 was tagged and M2 completed in a later session;
- the commits were made by the harness;
- a judge call was not held by the stop hook;
- the migration notice appears in a fixture carrying a v5.1 runtime pin.

The run consumes a small amount of real quota.

**`goal-session.sh`.** It prints the active goal's status, or the migrate-first notice. `goal.py`
and the skill refuse execution in an unmigrated project (AC-12).

### [ ] T5 — retire v5.1 machinery and repair its couplings
- writes: install/skills/execution-methodology/scripts/**, install/skills/execution-methodology/tests/**, install/skills/execution-methodology/references/**, install/skills/gate-sandbox/**, install/skills/methodology-management/**, install/skills/project-onboarding/**, install/skills/project-migration/**, install/skills/project-conformance/**, install/skills/agent-persona-factory/**, install/skills/.gitignore, install/skills/README.md, install/skills/progressive-disclosure/**, install/hooks/disclosure-check.sh, docs/runbooks/**, docs/decisions/decisions.md, docs/README.md, docs/agents/**, docs/architecture/operating-model.md, docs/architecture/repository-standard.md, README.md, AGENTS.md
- needs: T4
- covers: AC-10, AC-12
- risk: safety
- builder: judgement
- tests-may-change: install/skills/execution-methodology/tests/smoke_goal.py, install/skills/execution-methodology/tests/test_check_review_budget.py, install/skills/execution-methodology/tests/test_milestone_seal.py, install/skills/execution-methodology/tests/test_onboarding_adoption.py, install/skills/execution-methodology/tests/test_plan_waves.py, install/skills/execution-methodology/tests/test_plan_waves_milestone.py, install/skills/execution-methodology/tests/test_ratio_meter.py, install/skills/execution-methodology/tests/test_repo_sync.py, install/skills/execution-methodology/tests/test_runtime_status.py, install/skills/execution-methodology/tests/test_spec_check.py, install/skills/execution-methodology/tests/test_sync_preview.py, install/skills/execution-methodology/tests/test_trace_check.py, install/skills/execution-methodology/tests/test_validate_card.py, install/skills/execution-methodology/tests/test_verify_junit.py, install/skills/execution-methodology/tests/test_weekly_review.py, install/skills/execution-methodology/scripts/*_selftest.py, install/skills/gate-sandbox/**, install/skills/project-conformance/**, install/skills/progressive-disclosure/tests/**, install/skills/progressive-disclosure/scripts/*_selftest.py

**Deletions.** Delete:
- the v5.1 scripts, schema and selftests in `execution-methodology`, keeping T1 and T4's new
  files;
- every old reference except the five T2 wrote;
- the six retired skills.

**Coupling repairs in `progressive-disclosure`:**
- `push_guard.py` makes no calls into retired scripts.
- Its secret, identifier, size and README behaviour stays exactly as today. It is proven by its
  existing tests, which do not change for that behaviour.
- `validate_disclosure.py`, `install_hooks.py` and `check_toolchain.py` stop referring to the
  runtime pin, the persona-decision marker and the retired skills.
- `disclosure-check.sh` stops calling `sync_methodology.py`.

**Inbound links.** Repair every inbound link to a deleted file in the same commit. This is a
minimal repair. Content rewrites belong to T7, and the condensing of `decisions.md` to M4.

`risk: safety` applies because the push guard protects this public repository. The security
reviewer confirms that the guard's behaviour on commit ranges and staged content is unchanged.

### [ ] T6 — installer and repository gate
- writes: install/install.sh, install/README.md, install/verify.sh, install/preserve_selftest.sh, install/tests/**
- needs: T5
- covers: AC-9, AC-10, AC-11, AC-12
- risk: boundary
- builder: judgement
- tests-may-change: install/preserve_selftest.sh

**`install.sh`.** It installs:
- the four skills;
- the session hook and Stop hook for both harnesses;
- the rendered personas.

It merges settings as today. `--retire-v5` removes only files matching the known v5.1 set and
reports anything else. A plain install removes nothing.

**`verify.sh`.** It is rewritten at about 300 lines and runs:
- every published skill's unittest suite, checking executed counts;
- `validate_disclosure.py --standard`;
- the identifier guard over the tree;
- the AC-9 size test (`install/tests/test_size.py`);
- a dangling-reference scan for retired names over `install/` and the routed docs;
- the installer tests (`install/tests/test_install.py`, run against a temporary HOME);
- with `--installed`, a parity diff against `~/.claude` and `~/.codex`.

`risk: boundary` applies because the installer writes into the founder's harness configuration.

### [ ] T7 — repository documentation to v6
- writes: README.md, AGENTS.md, install/AGENTS.md, install/CLAUDE.md, docs/README.md, docs/agents/**, docs/architecture/README.md, docs/architecture/operating-model.md, docs/architecture/repository-standard.md, docs/architecture/goal-directed-execution.md, docs/runbooks/**, docs/assets/readme/**, docs/product/README.md, docs/product/specs/F-1-methodology-efficiency-vendoring.md, docs/product/specs/F-2-goal-directed-autonomy.md, docs/product/plans/F-1-methodology-efficiency-vendoring.md, docs/product/plans/F-2-goal-directed-autonomy.md, docs/product/plans/goal-directed-autonomy-task-boundaries.md, docs/product/milestones/**, docs/product/research/**
- needs: T6
- covers: AC-1, AC-10
- risk: none
- builder: routine
- tests-may-change: —

**Rewrites.** Rewrite these to describe v6:
- the front page's current-state section and visual descriptions;
- the repository contract;
- the route index;
- the operating model;
- the repository standard's tooling references;
- the runbooks.

**Deletions.** Delete the superseded F-1 and F-2 documents, the research folder and the
goal-directed design; git holds them.

**Global-instructions runbook.** Add `docs/runbooks/global-instructions.md` with the exact
replacement text for the founder's private `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`
execution sections. The founder applies it; this goal edits no private file.

## M4 — current-state records and toolchain slimming

criteria: AC-10, AC-13
proofs:
- AC-13: python3 -m unittest discover -s install/tests -t install/tests -p 'test_size.py'
- AC-10: full_gate

**Sizing exception.** M4 has two tasks, below the minimum. It is kept separate because it can merge
independently of M3 and carries no criterion M3 needs.

### [ ] T8 — records hold current decisions only
- writes: docs/decisions/**, docs/product/measurements.md, docs/product/improvements-weekly.md, docs/agents/lessons.md, docs/README.md, docs/agents/README.md
- needs: T7
- covers: AC-10
- risk: none
- builder: routine
- tests-may-change: —

- **`decisions.md`:** keep only decisions in force under v6, each with its reason and the
  alternative it beat in a few lines.
- **`measurements.md`:** keep only the numbers those decisions and the v6 design cite.
- **`improvements-weekly.md`:** delete it.
- **`lessons.md`:** turn it into a curated current list.

### [ ] T9 — progressive-disclosure slimming
- writes: install/skills/progressive-disclosure/**, install/tests/test_size.py
- needs: T8
- covers: AC-13
- risk: safety
- builder: judgement
- tests-may-change: install/skills/progressive-disclosure/tests/**, install/skills/progressive-disclosure/scripts/*_selftest.py

Changes:
- `check_toolchain.py` shrinks to a renderer-parity check, since there is one source.
- `promote_lesson.py` and `migrate_to_standard.py` are deleted if nothing routed needs them.
- The filename-keyed record exemption is removed if no remaining record needs it.
- `validate_disclosure.py` keeps its route, link, budget and README checks.

**Target:** at least half of the skill's non-test lines removed. **Unchanged:** the push guard's
secret and identifier behaviour; the security reviewer confirms it.

## Milestone close (both)

1. Commit everything, then run `full_gate`, `e2e` and every automatic proof.
   - Once T1 exists, each runs through `gate.py receipt`.
   - Before T1 exists, run them directly and record the exit status and counts.
2. Run cross-vendor acceptance with Codex `gpt-6.1-sol` at xhigh. For M3 this is the two
   partitions above.
3. Write the merge explainer and the digest for the founder.

## Grants requested

- **Granted with approval (2026-10-06):** local commits on `v6-lean-execution`, and pushing that
  branch, never `main`, to the private remote once M3 is READY.
- **Not requested.** Each of these is a separate founder action:
  - merging to `main`;
  - running `install/install.sh` against `~/.claude` or `~/.codex`;
  - running `--retire-v5`;
  - editing the private global instruction files;
  - migrating any project.
- **Before any global install,** the founder must commit or discard `~/.claude`'s current
  uncommitted persona and settings changes. Until then, the installer would overwrite them.

## Decisions
- 2026-10-06: the plan uses the v6 format and is executed by hand until T1 and T4 exist (bootstrap).
- 2026-10-06: the baseline on `3bd256d` holds one environmental failure,
  `test_check_toolchain.PluginSurfaceTest.test_the_real_machine_is_enumerable_and_its_clear_result_is_a_compared_one`.
  It reads this machine's plugin state, where an enabled plugin's install path is unresolvable. It
  goes into `baseline.json` and is never attributed to F-3. `agent-personas` has no tests directory
  today (D24); T3 creates one, which reverses D24.
- 2026-10-06: Codex design and plan review round 1 returned BLOCK on both. All findings were
  accepted. Two design findings were accepted with a different fix:
  - an exhausted acceptance review goes to the founder with advice, with no extra round;
  - v5.1 projects are told to migrate first, and global v5.1 removal requires `--retire-v5`.

- 2026-10-06: Codex scoped rereview (round 2, final) closed 23 of 27 findings and raised two new
  ones. The four still open were corrected without a third review round and are shown at
  approval:
  - P1: a gate that tolerates a missing suite directory, with the baseline recorded;
  - D10: v6 refuses execution in unmigrated projects;
  - N1: judges run with integrations excluded;
  - N2: every declared acceptance partition must pass.

  D14 (migration contract evidence) is folded into the data lens.

- 2026-10-06: founder approved F-3 as one goal (M3+M4). `install/` becomes the single authored
  source. Grants: local commits, and pushing the branch at M3 READY.

- 2026-10-06: format-only correction after approval. Proof entries are now exact commands, or the
  `full_gate`/`e2e` tokens, so that `goal.py lint` can run them. No scope or criterion changed. The
  approval tag moved to this commit; reported to the founder at merge.

- 2026-10-07: amendment before T3 (founder-approved). `sync_methodology.py` hard-codes the v5.1
  persona pool and `ROSTER`, so T3 could not delete them without breaking its tests. T3 now also
  deletes `sync_methodology.py`, its selftest, `runtime-status.schema.json`, `test_runtime_status.py`,
  `test_sync_preview.py` and `test_onboarding_adoption.py`, all previously in T5's scope. The
  Branch paragraph now matches the granted push. No criterion or goal scope changed. The approval
  tag moved to this commit, and T1 and T2 were replayed on top of it.

- 2026-10-07: design amendment before T1 (founder-approved). codex-cli 0.160.0 rejects
  `-s workspace-write` together with `--approve-for-me`, which already uses that sandbox, so the
  Codex launch drops `-s`. The Claude judge adds `--setting-sources project,local`, so that it loads
  no user-level hooks or plugins, as the cross-vendor rule already claimed. Codex project hooks live
  in `.codex/hooks.json` and need a one-time trust step; only the Codex smoke run passes
  `--dangerously-bypass-hook-trust`, on its own throwaway fixture. The approval tag moved to this
  commit, and T1–T3 were replayed on top of it.

- 2026-10-07: amendment before T1 (founder-approved through the Codex hook-trust choice). The founder
  chose to trust the Codex fixture's hooks by hand, so the smoke run's Codex fixture moves to one
  fixed path that is rebuilt identically on every run. That edits `smoke_goal.py`, which T5 may now
  change. The approval tag moved to this commit, and T1–T4 were replayed on top of it.

## Queue
