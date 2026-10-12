# S-6 design: task validation chosen at planning, the full gate off the task path, builder lanes

## Structure

Three changes to the shipped skill, each in an existing file or command, and the words that tell
the chief to use them.

- **The plan carries two more task fields.** `gate:` names the command that validates the task;
  `needs:` names the earlier tasks it builds on. Both are parsed like `writes:` and read at the
  parent like it: changing either after approval is a plan-only commit with a Decisions line.
- **`gate.py` records every run and judges caching by purpose.** Each `check`, `receipt` and
  `baseline` appends one line to `.runs/<id>/checks.jsonl`, and the summary ends with a budget
  line. `.runs/` resolves in the main worktree, so a run in a lane or the full-gate worktree lands
  in the same record. A Gradle command may reuse up-to-date test results in `check`; a `receipt`
  or `baseline` must still force a full rerun.
- **`goal.py` schedules and warns.** `next` prints every ready task; `lint` warns about `needs`
  errors, unchained overlapping write sets and a slow default gate; the approval page shows each
  task's gate.
- **Words.** The loop runs up to three builders, one lane worktree per `needs` chain, a fresh
  builder per task; the full gate runs every third task commit in its own worktree, in the
  background, and at close. The builder works only in the worktree its packet names.

## Interfaces

1. **Task fields.** `FIELD_RE` gains `gate` and `needs`. `gate:` is one command string (the rest
   of the line, never split on commas); `needs:` is a comma list of task ids. `parse_plan` stores
   `task["gate"]` (string, empty when absent) and `task["needs"]` (list). `frozen_view` drops both
   lines under a task header; `widenings` compares `writes`, `tests-may-change`, `reads`, `gate`
   and `needs`, so done row 3 requires a Decisions line for a changed gate or needs. The message
   becomes "changes a task field without adding a Decisions line".
2. **`goal.py next`.** Ready = state `[ ]`, in the active milestone, every id in `needs` ticked
   `[x]`. Prints one line per ready task in plan order, `T3 — <title>`, with ` · gate: <cmd>` when
   the task has its own gate. Exit 0 when at least one is ready; when none is ready but open tasks
   remain, prints `no ready task: T4 needs T2 (open)` per blocked task and exits 1; when none is
   open, the existing message and exit 1. `resume` names the first ready task.
3. **Lint warnings.** `lint` returns errors as today and prints warnings as `lint: warning: <text>`
   before the verdict line; warnings never change the exit code. Warnings: `T4 needs T9, which is
   not an earlier task` (unknown, itself or later in plan order); `T2 and T5 overlap in writes and
   neither needs the other` (pairs in the same milestone, `overlap()` on `writes`, no path through
   `needs` either way); `T3 has no gate line and the plan gate's last check took <n> s (budget 600
   s)` (last line of `.runs/<id>/checks.jsonl` whose command equals the plan's `gate` and whose
   label is `check`; absent file or line, no warning).
4. **Checks record.** `run()` measures wall time. Under a goal, `check`, `receipt` and `baseline`
   append `{"label", "command", "tree", "duration_s", "verdict", "finished_at"}` to
   `.runs/<id>/checks.jsonl` (`verdict` is `RECORDED` for a baseline). The summary's last line is
   `budget: ok (<n> s of 600 s)` or `budget: <n> s over 600 s` for `check`, 1800 s for `receipt`
   and `baseline`. A `check` with no goal writes no record and prints the budget line.
5. **Where `.runs/` lives.** `runs_root(root)` is the parent of `git rev-parse --path-format=absolute
   --git-common-dir` (the main worktree); every `.runs` path in `gate.py` (logs, receipts,
   baseline, active, checks) is under it. `goal.py done` reads receipts there too. The tree a
   receipt binds to is still the running worktree's `HEAD^{tree}`.
6. **Caching.** `evaluate` adds the reason `gradle command without --rerun-tasks may report cached
   results` only when the label is not `check`. For `check`, when the output holds Gradle's
   `<n> actionable tasks: … up-to-date` or `from cache`, the summary adds `  - cached: <k> of <n>
   Gradle tasks reused` as information, not a reason. Zero tests executed stays a FAIL in every
   mode: a scoped gate whose tests all came from cache did not test the task.
7. **Approval page.** The task table gains a Gate column: the task's `gate:` or `plan gate`.
8. **Builder file.** `agents/builder.md` drops `isolation: worktree`; its body says: work only in
   the worktree the packet names, start every shell command with `cd <that path>`, run the task's
   gate there. `agents/builder.toml` gets the same body. The chief creates lanes with `git worktree
   add --detach .claude/worktrees/lane-<n> <branch>`; between tasks `git -C <lane> reset --hard`
   then `git -C <lane> checkout --detach <branch>` (a reset to the lane's own HEAD leaves it on the
   old base); at close `git worktree remove <lane>`, never `--force` without a Decisions line.
   `.claude/worktrees/` goes in `.git/info/exclude`, so lanes never dirty the tree.

## Data touched

Two new plan fields; one new append-only file, `.runs/<id>/checks.jsonl`; `.runs/` moves to the main
worktree for runs made in other worktrees (identical for runs in the main one). No receipt or
baseline format changes. No downstream repository is edited.

## Smallest change

Fields are parsed by the existing `FIELD_RE` path; `next` reuses `next_task`'s milestone filter;
warnings reuse `overlap()`; the record is one `open(..., "a")`; the cache rule is one condition on
the existing reason. Everything else is words: the lane cycle, the cap of three, the every-third
full gate and the 600-second planning budget are instructions in `SKILL.md` and
`references/planning.md`, judged by the plan reviewer and the founder, not by `done`.

## Rejected options

- **Continue one builder per lane** with `SendMessage`: its context grows across tasks, `maxTurns`
  across continuations is undocumented, and the rule that a session restarts from the plan alone
  would no longer hold. The founder chose a fresh builder per task in a reused worktree.
- **Keep `isolation: worktree` and copy files between worktrees**: every dispatch makes a new
  worktree; 128 were left behind in four days.
- **A full gate per task tree**: one pilot repository's full gate runs 37 to 99 minutes and overlapped gates ran up
  to 3.7× slower; every third task bounds a missed reach failure to two tasks.
- **Caching in receipts**: a receipt is the milestone's evidence; an undeclared Gradle input (one
  pilot repository found a docs file its tests read, another reads a manifest through a system
  property) would let a stale PASS certify a tree it never ran.
- **A `gate_budget` key or a budget error**: the council's verdict; a warning and a recorded
  duration carry the signal without halting a passing gate.
- **Two chief gates at once**: the gate is the chief's one serial step; running two doubles the
  load the measurements show slows both.
- **A lane tool** (`goal.py lane`): three git commands in the skill do it; tools only where
  judgement cannot.

## Trade-offs for the founder

- A reach failure the scoped gate misses now surfaces at the next every-third full gate, up to two
  tasks later, instead of at the task. The full gate in the slowest repositories becomes a
  background cost while builders run.
- `check` trusts Gradle's up-to-date checks. A test that reads an undeclared file passes from
  cache until the next full gate, which always reruns.
- Lanes cap at three builders on this machine; more would need a second machine or slower gates.
