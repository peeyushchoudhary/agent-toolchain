# S-6 spec: task gates chosen at planning, builder lanes

**Users and problem.** Chief sessions on four v7.1 repositories (`measurements.md`, 2026-10-13).
Each task runs the whole suite twice: 24 chief-hours in four days, 40% of a task cycle on two
repositories. Hand-narrowed gates hid failures. Builders already run in dependency lanes, but no
plan field orders them, and every dispatch leaves a worktree (128 so far).

**What changes for the user.** A task names its gate and the tasks it needs; `next` lists the ready
ones; runs record their duration; `lint` warns about slow, unordered or overlapping tasks. The full
gate runs every third task and at close, in the background. Up to three builders work in lane
worktrees the chief reuses and removes.

**Acceptance criteria.**

- AC1 WHEN a task has a `gate:` line THE SYSTEM SHALL treat it as that task's gate and show it on
  the approval page; otherwise the plan's.
- AC2 WHEN `next` runs THE SYSTEM SHALL name every open active-milestone task whose `needs` are
  ticked.
- AC3 WHEN `needs` names an unknown or later task, or two unchained tasks share `writes`, THE SYSTEM
  SHALL warn at `lint` without failing it.
- AC4 WHEN `check`, `receipt` or `baseline` runs under a goal in any worktree THE SYSTEM SHALL
  append its command, duration and verdict to the main worktree's `.runs/<id>/checks.jsonl` and
  end with a budget line (600 s for `check`, 1800 s otherwise).
- AC5 WHEN a task lacks a `gate:` line and the plan gate's last `check` exceeded 600 s THE SYSTEM
  SHALL warn at `lint`.
- AC6 WHEN `check` runs Gradle reusing up-to-date results THE SYSTEM SHALL accept it and report the
  reuse; `receipt` and `baseline` SHALL still require a full rerun.
- AC7 WHEN the skill is read THE SYSTEM SHALL state within 1,350 always-loaded words the task's
  gate, the every-third full gate, at most three builders and the lane cycle.
- AC8 WHEN the builder file is installed in either harness THE SYSTEM SHALL carry no worktree
  isolation and SHALL confine the builder to the worktree its packet names.
- AC9 WHEN `e2e_run.sh` runs THE SYSTEM SHALL prove AC2 and AC4 in both harnesses.

**Non-goals.** Tool-seeded `tests-may-change`; faster repository gates; two chief gates at once;
continuing a builder across tasks.

**Constraints.** Standard-library Python 3; no downstream repository, person or path named;
instructions over mechanism (D29, D30).
