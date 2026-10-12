---
goal: S-6
title: Methodology v7.2 — each task's gate chosen at planning, the full gate every third task in the background, builders in dependency lanes
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D31, docs/goals/S-6/design.md#interfaces, docs/goals/S-6/design.md#data-touched]
---

## Outcome

A task names its own gate and the tasks it needs (AC1); `goal.py next` lists every ready task
(AC2); `lint` warns about a bad `needs`, unchained tasks sharing writes and a slow default gate
(AC3, AC5). `gate.py` records every run's duration in the main worktree's
`.runs/<id>/checks.jsonl` with a budget line (AC4) and lets a task check reuse Gradle's up-to-date
results while receipts still rerun everything (AC6). The skill tells the chief to run the full gate
every third task commit and at close in its own worktree, at most three builders in lane worktrees
reused per `needs` chain, a fresh builder per task (AC7); the builder works only in the worktree its
packet names (AC8). The e2e proves `next` and the record in both harnesses (AC9). Decision record:
D32; design [design.md](design.md); spec [spec.md](spec.md).

## Tasks

### [ ] T1 — v7.2 in words: D32, the 2026-10-13 measurements, the loop, lanes and the builder file
writes: docs/decisions/decisions.md, docs/product/measurements.md, docs/architecture/methodology.md, docs/README.md, AGENTS.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/agents/builder.toml, install/skills/execution-methodology/tests/test_rules.py
reads: docs/goals/S-6/design.md#structure, docs/goals/S-6/design.md#interfaces, docs/decisions/decisions.md#d31--the-skill-is-model-invocable-the-chief-is-the-root-session-never-a-subagent, docs/product/measurements.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_rules.py' && python3 -m unittest discover -s install/tests -t install/tests -p 'test_size.py' && python3 install/skills/execution-methodology/scripts/docs.py lint .
Built by the chief. D32 records the decision with the measured numbers anonymised (repository A to
D; no project name). `measurements.md` gains a dated 2026-10-13 section: chief gate runs, medians,
p90, chief hours, gate share of the task cycle, the overlapped-gate ratio, plan widths and critical
paths, worktrees left behind. `SKILL.md`: the plan format shows `gate:` and `needs:`; the loop says
`goal.py next` lists ready tasks, at most three builders at once, one lane worktree per `needs`
chain made with `git worktree add --detach .claude/worktrees/lane-<n> <branch>`, moved between
tasks with `reset --hard` then `checkout --detach <branch>`, removed at close; step 5 runs the
task's gate; every third task commit, the chief starts the full-gate receipt in its own worktree in
the background and stops dispatching on a FAIL. The milestone-close section moves to
`references/close.md` with one pointer line left, keeping the always-loaded total at or under
1,350 words. `planning.md` step 5: each task gets a `gate:` under 600 s alone (the touched module's
build, the named test, `tests-may-change`, the test modules the scout says the writes reach) and a
`needs:` line; run the plan gate once while planning. `builder.md` and `builder.toml` drop
`isolation: worktree` and say: work only in the worktree the packet names, start every shell
command with `cd` to it, run the task's gate there (AC8). `test_rules.py` asserts the skill names
the task's gate, the every-third full gate, the three-builder cap and the lane reset to the branch
(AC7), and that neither builder file carries worktree isolation. Do not touch scripts or other tests.

### [ ] T2 — `goal.py`: task `gate:` and `needs:`, ready tasks, lint warnings, the gate column
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-6/design.md#interfaces, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py'
Interfaces 1, 2, 3 and 7. `FIELD_RE` takes `gate` (the rest of the line, unsplit) and `needs`;
`frozen_view` drops both under a task header; `widenings` compares all five fields and row 3's
message reads "changes a task field without adding a Decisions line". `cmd_next` prints every ready
task in plan order with ` · gate: <cmd>` when set, the blocked lines and exit codes of Interface 2;
`resume` names the first ready task. `cmd_lint` prints `lint: warning: …` lines (unknown or later
`needs`; unchained same-milestone pairs whose `writes` overlap; a task without `gate:` when the last
`check` line for the plan gate in `.runs/<id>/checks.jsonl` took over 600 s) before the verdict and
never changes the exit code. `packet --approval`'s table gains a Gate column. Tests in `test_goal.py`,
copying `LintTest.test_lint_names_each_planted_defect` and the fixture's `plan_text`:
`test_next_lists_every_ready_task` (T1 and T2 independent, T3 needs T1: next prints T1 and T2, then
after T1 ticks, T2 and T3) (AC2); `test_a_task_gate_is_parsed_and_shown` (AC1);
`test_needs_and_overlap_warn_without_failing` (AC3); `test_slow_default_gate_warns` with a written
`checks.jsonl` line of 700 s (AC5); `test_changing_a_task_gate_needs_a_decisions_line` (row 3). Do
not change `gate.py`.

### [ ] T3 — `gate.py`: the checks record, the budget line, `.runs/` in the main worktree, caching in `check`
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-6/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py'
Interfaces 4, 5 and 6. `run()` returns its wall time; `check`, `receipt` and `baseline` under a goal
append one JSON line to `.runs/<id>/checks.jsonl`; `summary()` ends with the budget line (600 s for
`check`, 1800 s otherwise), and `cmd_receipt` prints it after the rerun line. `runs_root(root)` is
the parent of the absolute `--git-common-dir`; `receipt_path`, `active_goal`, `run`'s log directory,
`load_baseline`, `cmd_baseline` and the record use it. The `--rerun-tasks` reason applies only when
the label is not `check`; a `check` whose output has Gradle's `actionable tasks:` line with
`up-to-date` or `from cache` adds the information line `  - cached: <k> of <n> Gradle tasks reused`.
Tests in `test_gate.py`, copying `CheckTest.test_pass_writes_log_and_no_receipt`:
`test_every_run_appends_to_the_checks_record` (check, receipt, baseline each add one line with its
label and duration) (AC4); `test_the_summary_ends_with_the_budget_line`;
`test_a_run_in_a_linked_worktree_records_in_the_main_worktree` (`git worktree add`, receipt there,
receipt and record under the main worktree's `.runs/`) (AC4); `test_check_accepts_gradle_reuse_and_
receipt_does_not` replacing `test_gradle_needs_rerun_tasks` (AC6). Do not change `goal.py`.

### [ ] T4 — `e2e_run.sh`: ready tasks and the checks record in both harnesses
writes: install/skills/execution-methodology/tests/e2e_run.sh
reads: install/skills/execution-methodology/tests/e2e_run.sh, docs/goals/S-6/design.md#interfaces
tests-may-change: install/skills/execution-methodology/tests/e2e_run.sh
needs: T2, T3
gate: install/skills/execution-methodology/tests/e2e_run.sh
For each harness, before T1 is built, `goal.py next` prints both E-1 tasks (they are independent);
after the two `gate.py check` runs and the receipts, `.runs/E-1/checks.jsonl` holds two `check`
lines and two `receipt` lines, each with a `duration_s`, and every `check` output ends with a
`budget:` line (AC9, proving AC2 and AC4). The final PASS line names both. Do not change scripts.

## Decisions

## Parked

- Q: Background full gate every third task commit and at close (founder, 2026-10-13). Bounds a
  missed reach failure to two tasks; confirm three.
- Q: Lane cap of three builders on this machine; confirm or name the number.
