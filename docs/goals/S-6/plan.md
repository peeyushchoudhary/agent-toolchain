---
goal: S-6
title: Methodology v7.2 — each task's gate chosen at planning, the full gate every third task in the background, builders dispatched by dependency
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T5, T1, T2, T3, T4], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D31, docs/goals/S-6/design.md#interfaces, docs/goals/S-6/design.md#data-touched]
---

## Outcome

A task names its own gate and the tasks it needs (AC1); `goal.py next` lists every ready task and
`resume` names a blocked one (AC2); `lint` warns about a bad `needs`, unchained tasks sharing writes
and a slow default gate (AC3, AC5). `gate.py` records every run's duration in
`.runs/<id>/checks.jsonl`, under `--runs` when a run happens in another worktree, with a budget line
(AC4), and lets a task check force only its Gradle test tasks (`--rerun`) so compilation stays
incremental, counting only tests that ran, while receipts and baselines still rerun everything
(AC6). The test fixtures run with a scratch home, so no test reads this machine's transcripts. The skill tells the chief to dispatch up to
four builders on ready tasks, each in a fresh isolated worktree from HEAD removed after its commit,
and to run the full gate at close, and every third task commit in a separate worktree where it
takes 600 s or less (AC7); a
builder whose worktree lacks the packet's base commit stops (AC8). The e2e proves `next` and the
record in both harnesses (AC9). A goal approved under v7.1 keeps its `.runs/`; a task-body line
starting `gate:` or `needs:` becomes a field there too (none exists in any shipped or pilot plan). Decision record:
D32; design [design.md](design.md); spec [spec.md](spec.md).

## Tasks

### [ ] T5 — The `goal.py` test fixtures run with a scratch HOME and CODEX_HOME
writes: install/skills/execution-methodology/tests/fixtures/goal_fixture.py, install/skills/execution-methodology/tests/test_goal.py
reads: install/skills/execution-methodology/tests/fixtures/goal_fixture.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/scripts/goal.py
tests-may-change: install/skills/execution-methodology/tests/fixtures/goal_fixture.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Built by the chief, first. `env()` in `goal_fixture.py` passes the caller's environment through, so
every `goal.py packet` in a test reads the real `~/.claude/projects` and `$CODEX_HOME/sessions` for
its cost lines; on this machine (26 GB of Codex session files) that passed the fixture's 120 s
timeout and failed `ReviewRowTest.test_packet_counts_causes_over_closed_blocking_findings` and
`SpecLintTest.test_a_reads_change_in_a_plan_only_commit_needs_a_decision` at approval; the same
test took 7 s with a scratch home. `env()` sets `HOME` and `CODEX_HOME` to one empty directory made
once per process with `tempfile.mkdtemp`, before `extra`, so `CostTest`'s own HOME and CODEX_HOME
still win. Test in `test_goal.py`: `FixtureTest.test_fixture_runs_use_a_scratch_home` (`env()["HOME"]`
is not the real home, `CODEX_HOME` is under it, and an explicit `HOME=` argument overrides it). Do
not change scripts. The transcript scan's own speed is a follow-up, not this goal.

### [ ] T1 — v7.2 in words: D32, the 2026-10-13 measurements, the loop, dispatch by dependency and the builder's base check
writes: docs/decisions/decisions.md, docs/product/measurements.md, docs/architecture/methodology.md, docs/README.md, AGENTS.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/agents/builder.toml, install/skills/execution-methodology/tests/test_rules.py
reads: docs/goals/S-6/design.md#structure, docs/goals/S-6/design.md#interfaces, docs/decisions/decisions.md#d31--the-skill-is-model-invocable-the-chief-is-the-root-session-never-a-subagent, docs/product/measurements.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_rules.py' && python3 -m unittest discover -s install/tests -t install/tests -p 'test_size.py' && python3 install/skills/execution-methodology/scripts/docs.py lint .
Built by the chief. D32 records the decision with the measured numbers anonymised (repository A to
D; no project name). `measurements.md` gains a dated 2026-10-13 section with these numbers, measured
2026-10-09 to 13 from gate logs (start stamp to last write) and git: chief task checks A 100 runs,
median 1.4 min, p90 3.3, 2.9 h, full gate median 8.1 min, task cycle median 15 min, gate share 9%; B
144, 4.2, 7.7, 10.6 h, 5.0, 11, 38%; C 52, 8.9, 30.9 (max 44.5), 10.5 h, 37, 23, 39%; D 5, 0.3,
full gate 91, cycle 6, 5%. A check overlapping another gate ran 1.31× (A), 1.40× (B) and 3.68× (C)
slower than alone. Across 33 plans, 233 tasks with critical paths summing to 150 (ideal speedup
1.55×), median width 2, 11 plans with three or more independent tasks. Worktrees left: 108, 11, 9. `SKILL.md`: the plan format shows `gate:` and `needs:`; the loop says
`goal.py next` lists ready tasks; at most four builders at once, each dispatched only when its
`needs` are committed, each packet naming the chief's checkout and HEAD; before applying a diff the
chief confirms its own checkout is clean; it removes a builder's worktree after committing its task
(Interface 8); step 5 runs the task's gate; every third task commit, one
background full-gate receipt in a detached worktree with `--runs`, one at a time, a sample due
during a run starting on the newest commit when it ends, only where the full gate's last recorded
run (or its approval baseline) took 600 s or less; otherwise the full gate runs only at close, alone
(Interface 9). A full-gate FAIL stops dispatch. Builder worktrees live under `.claude/worktrees/`,
which the repository must ignore (`.gitignore` or `.git/info/exclude`), or every receipt refuses
the tree as dirty. The milestone-close section moves to
`references/close.md` with one pointer line left, keeping the always-loaded total at or under
1,350 words. `planning.md` step 5: each task gets a `gate:` under 600 s alone (the touched module's
build, the named test, `tests-may-change`, the test modules the scout says the writes reach) and a
`needs:` line; run the plan gate once while planning. `builder.md` and `builder.toml` keep
their isolation and gain the MUST line of Interface 8: before the first edit, confirm the worktree
is not the chief's checkout and the packet's commit is an ancestor of HEAD, else stop (AC8); "Run the gate" becomes "Run the task's gate".
`test_rules.py` gains `test_the_loop_runs_the_tasks_gate` (`SKILL.md` names "the task's gate"),
`test_the_full_gate_runs_every_third_task_and_a_due_sample_waits` ("every third task commit",
"newest", "600 s" and "only at close"), `test_at_most_four_builders_run_at_once` ("four builders"),
`test_dispatch_waits_for_committed_dependencies` ("needs" and "committed" in the dispatch step),
`test_the_chief_applies_only_to_a_clean_checkout` ("clean" in the apply step) (AC7), and
`test_both_builder_files_check_their_worktree` (both name `merge-base --is-ancestor` and the chief's
checkout; `builder.md` keeps `isolation: worktree`) (AC8). The additions must fit the existing
ceilings: always-loaded 1,350 words (`test_size.py`), each reference 400
(`Budgets.test_each_reference_is_within_its_word_ceiling`; `planning.md` is at 400 now), each agent
body 350 (`Budgets.test_each_agent_body_is_within_its_word_ceiling`; the builder is at 348): tighten
existing lines to make room, never drop a MUST. Do not touch scripts or other tests.

### [ ] T2 — `goal.py`: task `gate:` and `needs:`, ready and blocked tasks, lint warnings, the gate column
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-6/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
needs: T5
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Interfaces 1, 2, 3 and 7. `FIELD_RE` takes `gate` (the rest of the line, unsplit) and `needs`;
`frozen_view` drops both under a task header; `widenings` compares all five fields and row 3's
message reads "changes a task field without adding a Decisions line". `cmd_next` prints every ready
task in plan order with ` · gate: <cmd>` when set, the blocked lines and exit codes of Interface 2;
`resume` names the first ready task, or the blocked one, and never says to close a milestone with
open tasks. `cmd_lint` prints `lint: warning: …` lines (unknown or later
`needs`; unchained same-milestone pairs whose `writes` overlap; a task without `gate:` when the last
`check` line for the plan gate in `.runs/<id>/checks.jsonl` took over 600 s) before the verdict and
never changes the exit code. `packet --approval`'s table gains a Gate column. Tests in `test_goal.py`,
copying `LintTest.test_lint_names_each_planted_defect` and the fixture's `plan_text`:
`test_next_lists_every_ready_task` (T1 and T2 independent, T3 needs T1: next prints T1 and T2, then
after T1 ticks, T2 and T3) (AC2); `test_resume_reports_blocked_dependencies_without_suggesting_close`
(T2 needs a parked T1) (AC2); `test_a_task_gate_is_parsed_and_shown` (a gate with commas and `#`)
(AC1);
`test_needs_and_overlap_warn_without_failing` (a non-task `needs`, a later one, an overlap, a cycle)
(AC3); `test_slow_default_gate_warns` with a written
`checks.jsonl` line of 700 s (AC5); `test_changing_a_task_gate_needs_a_decisions_line` (row 3). Do
not change `gate.py`.

### [ ] T3 — `gate.py`: the checks record, the budget line, `--runs`, `--rerun` in `check`
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-6/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py'
Interfaces 4, 5 and 6. Signatures: `runs_dir(root, runs=None) -> Path` (`Path(runs)` or
`<root>/.runs`); `receipt_path(root, goal, tree, cmd, runs=None)`, so `goal.py`'s four-argument call
is unchanged; `run(root, cmd, goal, label, runs=None)` returns `(code, out, log, duration_s)`;
`budget_line(label, duration_s) -> str`. `check`, `receipt` and `baseline` under a goal append one
JSON line to `<runs>/<id>/checks.jsonl`. Each command prints `budget_line` as its very last line:
after `receipt superseded:` in a superseding check, after the rerun and `receipt:` lines in a
receipt, after the `baseline:` line in a baseline; `summary()` itself does not change. `--runs <dir>` on
all three sets the root of every `.runs` path (`receipt_path`, `active_goal`, `run`'s log
directory, `load_baseline`, `cmd_baseline`, the record); the default stays `<root>/.runs`; tree,
`dirty_paths` and `snapshot` stay in the running worktree. In `check` a Gradle command passes the
rerun rule with `--rerun` or `--rerun-tasks` (the reason reworded as in Interface 6); `receipt`
still needs `--rerun-tasks`; `baseline` refuses a Gradle command without it (exit 1, nothing
written). In `check`, Gradle's `actionable tasks:` line with `from cache` drops the JUnit XML count
and adds the FAIL reason of Interface 6. Tests in `test_gate.py`,
copying `CheckTest.test_pass_writes_log_and_no_receipt`: `test_every_run_appends_to_the_checks_record`
(check, receipt, baseline each add one line with label and duration) (AC4);
`test_every_command_ends_with_the_budget_line` (the last stdout line of a passing check, a
superseding check, a receipt, a replacing receipt and a baseline) (AC4); `test_runs_flag_records_a_linked_worktree_run_in_
the_named_directory` (`git worktree add`, receipt there with `--runs` naming the main `.runs/`; the
receipt binds the linked worktree's tree; without the flag nothing moves) (AC4);
`test_check_accepts_rerun_and_counts_only_tests_that_ran` (`--rerun` passes the rule; neither flag
FAILs; old XML from an up-to-date task is not counted; `from cache` with fresh XML: no XML counted,
FAIL) (AC6); `test_receipt_and_baseline_require_rerun_tasks` replacing `test_gradle_needs_rerun_tasks`
(`--rerun` alone is refused there) (AC6). Do not change `goal.py`.

### [ ] T4 — `e2e_run.sh`: ready tasks and the checks record in both harnesses
writes: install/skills/execution-methodology/tests/e2e_run.sh
reads: install/skills/execution-methodology/tests/e2e_run.sh, docs/goals/S-6/design.md#interfaces
tests-may-change: install/skills/execution-methodology/tests/e2e_run.sh
needs: T2, T3
gate: install/skills/execution-methodology/tests/e2e_run.sh
The script prints no test counts, so its check runs with `gate.py check --count none`, as every e2e
receipt since S-1 has. For each harness: E-1's T2 gains `needs: T1`. Before T1 is built, `goal.py
next` prints T1 and not T2, and `goal.py --plan <copy with T1 parked [!]> resume` says `no ready
task; T2 needs T1 (parked)`; after `[T1]` commits, `next` prints T2 (AC2). The script runs one
`gate.py baseline` on the plan gate before T1. At the end `.runs/E-1/checks.jsonl` holds exactly one
`baseline`, two `check` and two `receipt` lines, each with the exact command, a numeric
`duration_s` and the verdict (`RECORDED`, `PASS`, `PASS`), and the last stdout line of every
`check`, `receipt` and `baseline` starts `budget:` (AC4). The final PASS line names both (AC9). Do
not change scripts.

## Decisions

- 2026-10-13 design: the founder chose a 600-second task-gate budget, the full gate every third
  task commit and at close, and a fresh builder per task (founder).
- 2026-10-13 design: where the full gate takes over 600 s it runs only at close, alone, never
  mid-milestone; every third task commit applies only where it takes 600 s or less (founder).
- 2026-10-13 design review R5, R7, R10: builders keep their isolated worktree; a lane is a dispatch
  order, not a reused worktree, because a fresh worktree from HEAD already carries committed
  dependencies (scratch-repository check) and reuse would drop isolation (default; parked as a question).
- 2026-10-13 plan review R9: the background full gate, which now runs mid-milestone only where it
  takes 600 s or less, may overlap a task check; waiting for it would stall the loop for its length,
  and the slowdown is recorded in `checks.jsonl` per run for the next review (default). Two task
  checks never overlap.
- 2026-10-13 approval: at most four builders at once on this machine (founder).
- 2026-10-13 approval: a fresh isolated worktree per task. A task is done only when the chief
  commits it on the goal branch, and an isolated builder dispatched from this branch started at its
  tip (35b8448), not at main, so a fresh worktree carries every committed dependency (founder).
- 2026-10-13 approval: no Gradle test-result reuse. Up-to-date state lives in each checkout's own
  `.gradle/` and `build/`; targeted gates rerun their tests anyway, so a task check forces its test
  tasks with `--rerun` and keeps compilation incremental; receipts and baselines keep
  `--rerun-tasks` (founder).
- 2026-10-13 approval: T5 added and built first. The repository gate failed at approval on two
  `goal.py packet` tests that scanned this machine's 26 GB of Codex session files and passed the
  fixture's 120 s timeout; with a scratch home the same test took 7 s (founder).
- 2026-10-13 approval: the founder approved and told the chief to place `goal/S-6/approved`
  (founder).

## Parked
