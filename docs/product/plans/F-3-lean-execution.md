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

### [x] T1 — `goal.py` and `gate.py`
- writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/test_gate.py, install/skills/execution-methodology/tests/fixtures/**, .gitignore
- needs: —
- covers: AC-3, AC-4, AC-5
- risk: none
- builder: judgement
- tests-may-change: install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/test_gate.py

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

### [x] T2 — rules, references, explainer template
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

### [x] T3 — personas and renderer
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

### [x] T4 — `review.py`, `run_goal.py`, hooks, smoke run
- writes: install/skills/execution-methodology/scripts/review.py, install/skills/execution-methodology/scripts/run_goal.py, install/skills/execution-methodology/tests/test_review.py, install/skills/execution-methodology/tests/test_run_goal.py, install/skills/execution-methodology/tests/smoke_goal.py, install/hooks/goal-session.sh
- needs: T1, T2, T3
- covers: AC-2, AC-6, AC-12
- risk: none
- builder: judgement
- tests-may-change: install/skills/execution-methodology/tests/test_review.py, install/skills/execution-methodology/tests/test_run_goal.py, install/skills/execution-methodology/tests/smoke_goal.py

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

### [x] T5 — retire v5.1 machinery and repair its couplings
- writes: install/skills/execution-methodology/scripts/**, install/skills/execution-methodology/tests/**, install/skills/execution-methodology/references/**, install/skills/gate-sandbox/**, install/skills/methodology-management/**, install/skills/project-onboarding/**, install/skills/project-migration/**, install/skills/project-conformance/**, install/skills/agent-persona-factory/**, install/skills/.gitignore, install/skills/README.md, install/skills/progressive-disclosure/**, install/hooks/disclosure-check.sh, docs/runbooks/**, docs/decisions/decisions.md, docs/README.md, docs/agents/**, docs/architecture/operating-model.md, docs/architecture/repository-standard.md, README.md, AGENTS.md, docs/product/research/**, docs/product/README.md, install/README.md
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

### [x] T6 — installer and repository gate
- writes: install/install.sh, install/README.md, install/verify.sh, install/preserve_selftest.sh, install/tests/**, install/skills/progressive-disclosure/scripts/check_toolchain.py, install/skills/progressive-disclosure/scripts/migrate_to_standard.py, install/skills/progressive-disclosure/scripts/migrate_to_standard_selftest.py, install/skills/progressive-disclosure/tests/test_check_toolchain.py, install/skills/agent-personas/scripts/sync_personas.py, install/skills/agent-personas/tests/**
- needs: T5
- covers: AC-9, AC-10, AC-11, AC-12
- risk: boundary
- builder: judgement
- tests-may-change: install/preserve_selftest.sh, install/skills/progressive-disclosure/scripts/migrate_to_standard_selftest.py, install/skills/progressive-disclosure/tests/test_check_toolchain.py, install/skills/agent-personas/tests/**, install/tests/**

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

### [x] T7 — repository documentation to v6
- writes: README.md, AGENTS.md, install/AGENTS.md, install/CLAUDE.md, docs/README.md, docs/agents/**, docs/architecture/README.md, docs/architecture/operating-model.md, docs/architecture/repository-standard.md, docs/architecture/goal-directed-execution.md, docs/runbooks/**, docs/assets/readme/**, docs/product/README.md, docs/product/specs/F-1-methodology-efficiency-vendoring.md, docs/product/specs/F-2-goal-directed-autonomy.md, docs/product/plans/F-1-methodology-efficiency-vendoring.md, docs/product/plans/F-2-goal-directed-autonomy.md, docs/product/plans/goal-directed-autonomy-task-boundaries.md, docs/product/milestones/**, install/skills/progressive-disclosure/tests/test_readme_diagram.py
- needs: T6
- covers: AC-1, AC-10
- risk: none
- builder: routine
- tests-may-change: install/skills/progressive-disclosure/tests/test_readme_diagram.py

**Rewrites.** Rewrite these to describe v6:
- the front page's current-state section and visual descriptions;
- the repository contract;
- the route index;
- the operating model;
- the repository standard's tooling references;
- the runbooks.

**Deletions.** Delete the superseded F-1 and F-2 documents and the
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

### [x] T8 — records hold current decisions only
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

### [x] T9 — progressive-disclosure slimming
- writes: install/skills/progressive-disclosure/**, install/tests/test_size.py
- needs: T8
- covers: AC-13
- risk: safety
- builder: judgement
- tests-may-change: install/skills/progressive-disclosure/tests/**, install/skills/progressive-disclosure/scripts/*_selftest.py, install/tests/test_size.py

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

- 2026-10-07: amendment before T1 (founder-approved). T5's deletions break links inside
  `docs/product/research/` and one link in `install/README.md`, and the installed pre-commit hook
  rejects broken links. T5 therefore also deletes the research folder (moved from T7), repairs its
  inbound links including `docs/product/README.md`, and repairs that one README link (T6 still
  rewrites the file). No criterion or goal scope changed. The approval
  tag moved to this commit, and T1–T4 were replayed on top of it.

- 2026-10-07: amendment before T1 (founder-approved). Seven retired-name mentions remain in
  progressive-disclosure (`check_toolchain.py`, `migrate_to_standard.py` and their tests), which only
  T9 could edit, so M3's AC-10 could not pass. T6 now also cleans those mentions; T9 still slims
  the files. The founder also granted standing authority for amendments that only move files between
  task write sets within the approved scope; each is logged here and listed at merge. The approval
  tag moved to this commit, and T1–T5 were replayed on top of it.

- 2026-10-07: amendment before T1 (standing authority). A plain install now keeps v5.1 files inside
  published skills until `--retire-v5`. The carried v5.1 persona sources would make the installed
  renderer exit 2, which would break `validate_disclosure` in every project until retirement. T6
  therefore also changes `sync_personas.py`: it renders only the v6 pool and reports other sources
  as a warning. The approval tag moved to this commit, and T1–T5 were replayed on top of it.

- 2026-10-07: amendment (standing authority). T7 may change
  `install/skills/progressive-disclosure/tests/test_readme_diagram.py`. Its corpus test mutates a
  literal row of the v5.x front-page diagram, so rewriting the README to v6 breaks it. The criteria
  and scope are unchanged.

- 2026-10-07: amendment (founder-approved). M3 acceptance round 1 returned BLOCK on both partitions,
  with eleven tooling findings and one retirement finding, all reachable and small. Their regression
  tests belong in test files that T1, T4 and T6 created, so T1 (`test_goal.py`, `test_gate.py`), T4
  (`test_review.py`, `test_run_goal.py`, `smoke_goal.py`) and T6 (`install/tests/**`) may now modify
  them, for the acceptance correction. The criteria, scope and guard semantics are unchanged.

- 2026-10-07: amendment (founder-approved). T9 may change `install/tests/test_size.py`. It was
  already in T9's writes, and T6 left the AC-13 placeholder there for T9, but tests-may-change
  omitted it. The approval and M3 tags moved, every later commit was replayed with only the plan
  differing, and M3 was re-confirmed on its replayed tree.

- 2026-10-07: `full_gate` baseline. On the approval base the old `verify.sh` exits 1 and prints no
  test ids; its only failure is the known PluginSurface test inside the progressive-disclosure suite.
  That id is recorded for `full_gate` too, with the base log kept in `.runs/F-3/logs/`. The T6
  `verify.sh` must print suite failure ids and counts so that `gate.py` can attribute them.

- 2026-10-07: T3 security review: round 1 BLOCK (persona-name YAML injection could shadow a
  read-only judge), corrected once; scoped rereview PASS. Codex judge role files now also pin
  `approval_policy = "never"` and `multi_agent = false`, accepted by `codex doctor`; runtime loss
  of sub-agent spawning is not yet observed. Deferred as non-blocking: an unmanaged hand-written
  project agent can shadow a judge, a project persona may declare `writes: no` with dispatch tools,
  and the GENERATED marker is matched anywhere in a file.

- 2026-10-07: T4 smoke. Claude: 9 of 9 checks pass, including the blocked premature stop, M1 then
  M2 in fresh sessions, harness commits, cross-vendor acceptance, the judge unable to write, and the
  migrate notice. Codex: 6 of 9 pass. The driver finished the goal and the judge could not write,
  but the three hook checks fail because Codex runs project hooks only after trust is saved in the
  user's config. The founder approved a smoke-only trust bypass, but the permission classifier
  refused it in both the builder's and the controller's sessions, so it is not implemented.

- 2026-10-07: T5 security review PASS. Deferred to T9 as non-blocking: a selftest that pins the
  bare-repository exit 2 now that only the surviving probe keeps it; the pre-existing silent skip in
  the installed pre-push hook when the guard file is missing (recorded there as a founder call). The
  push-guard and identifier-guard selftest harnesses gained a one-line module-registration fix; their
  remaining failures (push guard 11, identifier guard 12f and 13) are environmental, because they
  expect the copy installed in `~/.claude`.

- 2026-10-07: T6 boundary review. Round 1 BLOCK: a plain install replaced each published skill
  wholesale, so it deleted the v5.1 files inside them. Corrected once: install now carries forward
  installed files that the package lacks, and `--retire-v5` deletes only the named list of 64. The
  renderer skips retired persona sources with a warning and keeps their rendered agents while each
  source exists. The scoped rereview passed. Known limitations, all non-blocking:
  - the global Codex goal hooks step aside whenever the project's `.codex/hooks.json` names the
    hook, even when that hook is untrusted and so does not run;
  - a symlinked `settings.json` or `hooks.json` becomes a regular file when merged;
  - `verify.sh --installed` counts carried installed-only files as drift, so it reports drift until
    `--retire-v5`, and afterwards still flags five unlisted carried test files;
  - no test pins that a stale v6 render beside a retired source is still rewritten (it holds by
    construction).

  Two Stop hooks over one goal are avoided because the global hooks exit when `GOAL_HARNESS` is set.

- 2026-10-07: T7. Two README images showed v5.1 machinery and could not be regenerated here, so
  they are deleted. The front page now draws the architecture as a Mermaid diagram with a stage
  table. `docs/runbooks/global-instructions.md` keeps the heading and the closing sentence that
  `check_toolchain.py` uses to find the mirrored block; T9 owns any change to that check. T7 carries
  risk none, so it has no task review; the milestone acceptance covers it.

- 2026-10-07: M3 acceptance correction (round 1 of 1), one commit per owning task:
  - T1: a clean-tree `check` invalidates the receipt it reruns; a nonzero exit must match the
    baseline's exit; exit 0 with counted failures or a FAIL verdict line fails; a moved HEAD
    fails; more test layouts are protected; `done` re-verifies every tagged milestone.
  - T4: acceptance refuses a dirty checkout; Claude judges run with `disableAllHooks`, proven by a
    real probe; a Codex run refuses a project without goal hooks and warns when they are untrusted;
    `run.network: false` denies the web tools; the driver re-verifies the tags before reporting
    done.
  - T2: `run.md` specifies the sandbox, approval, writable paths and network for both harnesses.
  - T3: the persona suite runs on Python 3.10 with a strict fallback for the renderer's TOML subset.
  - T6: the toolchain check no longer flags the mirrored persona tests, and the 3.10 floor is
    pinned.

  Raising the floor to 3.11 was considered and rejected, because the spec fixes Python 3.10+.
  Every suite passed on a real Python 3.10. The now-empty `CLAUDE_ONLY_IN_MIRROR` mechanism stays
  because `install_hooks.py` imports it; T9 may remove it. The retirement partition's optional
  finding on D27 goes to T8.

- 2026-10-07: M3 acceptance round 2 (scoped rereview). Tooling PASS on tree `754da62`.
  Retirement still BLOCK, so its review loop ended: the Claude launch profile in `run.md` omits
  that inherited user, project and local settings, such as `sandbox` and `additionalDirectories`,
  still apply. The controller also found that parallel partition reviews race on `rounds.json`,
  which mislabelled retirement's second review as round 1. The extra round was not used. The
  advisor (Codex, high confidence, reversible) recommended a docs-only fix for `run.md` and an M3
  fix for round accounting.

  The founder decided: fix both, refresh the receipts and e2e, then grant one final cross-vendor
  review per partition, scoped to the fix diff. If either still blocks, M3 returns to the founder.
  The grant is applied through `review.py --founder-grant`, which admits one round past the cap,
  once per subject, and stamps the verdict. The fix adds that option.

- 2026-10-07: M3 founder-granted final reviews on tree `4104752`. Retirement PASS. Tooling BLOCK, with
  three concurrency edge cases in the new round-reservation code: out-of-order completion of one
  subject, a reservation not released, and a progress-log failure undoing a round. The founder
  decided to simplify: a per-subject lock held for the whole review, a round counted only when its
  verdict is written, and best-effort progress logging. The founder also authorised one more scoped
  tooling review of that diff, applied by clearing the used grant record (logged), and a scoped
  retirement confirmation on the new tree.

- 2026-10-07: M3 closed. `goal.py done` passed on tree `4b05935`, and `goal/F-3/M3` is at `0222799`.
  Both partitions passed in round 4 under the founder's grants. The pushed branch is not updated:
  the machine's installed v5.1 pre-push guard rejects the frozen spec's dated heading "Founder
  decisions (2026-10-06)". The v6 guard no longer runs that check, and installing v6 is the
  founder's action.

- 2026-10-07: founder decision on T8. `docs/product/improvements-weekly.md` stays in place and
  unchanged for now. Its inbound links in `README.md` and `docs/product/README.md` are outside T8's
  writes, and widening those writes would need a replay that voids M3's tag, receipts and
  acceptance. It is deleted after F-3 merges (Queue Q2). Methodology lesson: write sets cannot be
  amended after a milestone is tagged without re-closing that milestone.

- 2026-10-07: M3 re-closed after the founder-approved replay for T9's amendment. `goal.py done`
  passed on tree `abe8f81`, and `goal/F-3/M3` is at `143bae8`. All five receipts passed, and both
  partitions passed scoped confirmations in round 5 under the founder's grant. The e2e receipt was
  taken from the main checkout, because the Codex fixture's trusted hooks carry that checkout's
  path (Queue Q6).

- 2026-10-07: founder decision on T9's security review, which blocked in both rounds on
  `install_hooks.py` hook writes that can leave the project. Round 1's plain-path gap was fixed.
  Round 2 found two graphify paths that predate T9: `post-checkout` is not destination-checked, and
  graph discovery follows a symlinked child directory. Both are fixed in T9, and one
  founder-granted scoped rereview (round 3) follows.

- 2026-10-07: founder decision on T9's security review round 3, which blocked on a third graphify
  path: graphify follows an inherited `GIT_DIR` to another repository's hooks. The founder's
  answer: "Graphify should work. Figure out a way." So the graphify git hook stays, and
  `install_hooks.py` stops delegating hook writes to graphify. graphify renders its hook blocks
  inside a throwaway sandbox repository, and `install_hooks.py` writes them through its own
  destination-checked path. Uninstall strips graphify's marker blocks itself. One scoped
  rereview (round 4) follows under this decision.

- 2026-10-07: M4 acceptance round 1 BLOCK. With `core.hooksPath` set, the plain installer wrote
  the graph hooks to `.git/hooks` and reported them installed, although git would not run them.
  T9's third security fix had removed that skip. Corrected under T9: the graph hook is skipped,
  with a message, when `core.hooksPath` is set. One scoped rereview follows. The same gap for our
  own hooks predates F-3 and is queued for the founder (Q7). The round-1 packet's diff covered only
  the plan, because the close passed it as `--subject`. The reviewer reconstructed the full diff,
  and round 2 is given the whole milestone diff.

- 2026-10-08: founder decision on M4 acceptance round 2. Round 2 blocked because an empty
  `core.hooksPath=""` still let the graph hook be reported installed, though git would not run it
  (verified locally). It is the same defect family as round 1: the check read the config value
  instead of asking git where it runs hooks. The family is fixed under T9: the graph hook is
  skipped unless `git rev-parse --git-path hooks` resolves to the project's `.git/hooks`. One
  founder-granted scoped acceptance round (round 3) follows.

- 2026-10-08: founder decision on M4 acceptance round 3, which blocked on three path-comparison
  cases in the same family: a trailing space, a missing path component, and a case-insensitive
  filesystem. All were verified locally. The founder chose the unset-only rule under T9: the graph
  hook is installed only when `core.hooksPath` is unset at every level (`git config --get` exits
  1). Any value means an honest skip, so no path comparison remains. One founder-granted scoped
  acceptance round (round 4) follows.

- 2026-10-08: founder decision on M4 acceptance round 4, which blocked on one finding, verified
  locally: with `GIT_CONFIG` set, `git config --get core.hooksPath` reads only that file and reports
  unset, while a running git ignores `GIT_CONFIG` and still applies `GIT_CONFIG_COUNT` and the other
  config sources. git documents `GIT_CONFIG` as affecting only the `git config` command, so it is
  the one variable that separates the query from the runtime. The founder chose the fix under T9:
  drop `GIT_CONFIG` from the query's environment, with a test using the reviewer's trigger. One
  founder-granted scoped acceptance round (round 5) follows; the round-4 grant is archived.

- 2026-10-08: founder decision after M4 was tagged ("take care of this"). A test in a throwaway
  repository with real git 2.54 and graphify 0.8.49 showed that graphify's post-commit block,
  which the installer writes unchanged into the hooks directory linked worktrees share, creates a
  graph holding only the committed files in a worktree that has no graph, with `built_at_commit`
  at HEAD. The fix is under T9, at the class: the installer writes its own guard before each
  graphify block, so a hook refreshes only an existing graph at the hook's worktree root; and a
  graph found under a child directory gets an honest skip, because git runs the hook at the
  worktree root and the child's graph was never refreshed. A scan of this machine's projects
  found no graphify hooks installed and no partial graph. The round-5 grant is archived; one
  founder-granted scoped acceptance round (round 6) follows, and `goal/F-3/M4` moves to the
  re-closed commit.

- 2026-10-08: founder decision on M4 acceptance round 6, which blocked on four findings in the
  guard work: `GRAPHIFY_OUT=''` made the guard check the default directory while graphify wrote at
  the root; `--scope project --no-graph` left existing blocks unguarded; `--scope project
  --uninstall --no-graph` left blocks installed; the real-graphify tests inherited
  `GRAPHIFY_OUT`. The founder chose the class fix under T9: hooks refresh only the default
  `graphify-out/` at the worktree root and skip whenever `GRAPHIFY_OUT` is set, so the guard no
  longer emulates graphify's output rules; every installer mode guards (install), strips
  (uninstall) or leaves untouched (check and preview) existing graph blocks, proven by a mode
  matrix; tests drop inherited `GRAPHIFY_*` variables. One founder-granted scoped acceptance round
  (round 7) follows; the round-6 grant is archived.

## Queue

- Q1 (2026-10-07, resolved 2026-10-07): the Codex Stop and SessionStart hooks for AC-2 are now
  proven. The founder trusted the fixed fixture's hooks by hand once, and the Codex smoke passed 9
  of 9: the premature stop was blocked, the session hook ran, and the judge was not held by the Stop
  hook.

- Q2 (2026-10-07, blocks nothing in F-3): after F-3 merges, delete
  `docs/product/improvements-weekly.md` and repair its links in `README.md`, `docs/README.md` and
  `docs/product/README.md`.

- Q3 (2026-10-07, blocks nothing in F-3): after F-3 merges, bring the `check_toolchain.py` row in
  `docs/agents/what-gets-installed.md` in line with T9's renderer-parity scope. Also add
  `progressive-disclosure/scripts/promote_lesson.py` to `install.sh`'s retire list: an installed
  copy is otherwise carried forward forever and `verify.sh --installed` reports it as drift.
- Q4 (2026-10-07, founder decision, blocks nothing in F-3): the installed pre-push hook skips
  silently when the push-guard file is missing. Decide whether it should block instead.
- Q5 (2026-10-07, blocks nothing in F-3): after F-3 merges, make
  `test_run_goal.DriveTest.test_settings_file_registers_hooks_and_allows_the_gates` independent of
  the checkout path. It asserts the shell-quoted form of the `goal.py` path, and that form exists
  only when the path contains a space, so the test fails in a checkout whose path has none.
- Q6 (2026-10-07, blocks nothing in F-3): after F-3 merges, make the Codex smoke's fixture
  independent of the checkout path, and make its trust pre-check compare the stored hook hash.
  The fixture's hook command carries the absolute `scripts` path, so a run from any other checkout
  changes the hooks Codex trusted. Codex then skips them silently, while the pre-check, which
  matches only the key, still reports them trusted.
- Q7 (2026-10-07, founder decision, blocks nothing in F-3): `install_hooks.py` writes our own
  pre-commit, commit-msg and pre-push hooks to `.git/hooks` and reports them installed even when
  `core.hooksPath` is set, in which case git never runs them, the push guard included. This
  predates F-3. Decide whether the installer should refuse, warn, or install into
  `core.hooksPath` when it resolves inside the project.
