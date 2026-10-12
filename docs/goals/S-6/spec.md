# S-6 spec: task gates chosen at planning, builder lanes

**Users and problem.** Chief sessions on four v7.1 repositories (`measurements.md`, 2026-10-13).
Each task runs the whole suite twice: 24 chief-hours in four days, 40% of a task cycle on two
repositories. Hand-narrowed gates hid failures. Builders run in dependency lanes with no plan
field ordering them, and worktrees pile up (128).

**What changes for the user.** A task names its gate and the tasks it needs; `next` lists the ready
ones; runs record their duration; `lint` warns about slow, unordered or overlapping tasks. The full
gate runs every third task and at close, in the background. Up to three builders work at once, each
in a fresh worktree removed after its commit.

**Acceptance criteria.**

- AC1 WHEN a task has a `gate:` line THE SYSTEM SHALL use and show it; otherwise the plan's.
- AC2 WHEN `next` or `resume` runs THE SYSTEM SHALL name the open active-milestone tasks whose
  `needs` are ticked, or the blocking task when none is.
- AC3 WHEN `needs` names a non-task or later task, or two unchained tasks share `writes`, THE SYSTEM
  SHALL warn at `lint` without failing it.
- AC4 WHEN `check`, `receipt` or `baseline` runs under a goal THE SYSTEM SHALL record its command,
  duration and verdict in `.runs/<id>/checks.jsonl` (or under `--runs`) and end with a
  budget line (600 s for `check`, 1800 s otherwise).
- AC5 WHEN a task lacks a `gate:` line and the plan gate's last `check` exceeded 600 s THE SYSTEM
  SHALL warn at `lint`.
- AC6 WHEN `check` runs Gradle reusing up-to-date results THE SYSTEM SHALL count only tests that ran
  and report the reuse, and SHALL fail results restored from a build cache; `receipt` and
  `baseline` SHALL require a full rerun.
- AC7 WHEN the skill is read THE SYSTEM SHALL state within 1,350 always-loaded words the task's
  gate, the every-third full gate, at most three builders and dispatch after `needs` commit.
- AC8 WHEN a builder's worktree is the chief's checkout or lacks its packet's commit THE SYSTEM
  SHALL stop the builder, in both harnesses.
- AC9 WHEN `e2e_run.sh` runs THE SYSTEM SHALL prove AC2 and AC4 in both harnesses.

**Non-goals.** Tool-seeded `tests-may-change`; faster repository gates; two task checks at once;
reusing a worktree or a builder across tasks.

**Constraints.** Standard-library Python 3; no downstream repository, person or path named;
instructions over mechanism (D29, D30).
