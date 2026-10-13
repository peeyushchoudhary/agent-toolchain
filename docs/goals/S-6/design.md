# S-6 design: task gates chosen at planning, builder lanes

## Structure

Three changes to the shipped skill, each in an existing file or command, and the words that tell
the chief to use them.

- **The plan carries two more task fields.** `gate:` names the command that validates the task;
  `needs:` names the earlier tasks it builds on. Both are parsed like `writes:` and read at the
  parent like it: changing either after approval is a plan-only commit with a Decisions line.
- **`gate.py` records every run and stops recompiling for a task check.** Each `check`, `receipt`
  and `baseline` appends one line to `.runs/<id>/checks.jsonl`, and the summary ends with a budget
  line. `--runs <dir>` lets a run made in another worktree record into the chief's `.runs/`. A
  `check` may force only its test tasks (`--rerun`), so compilation stays incremental and no test
  result is reused; a `receipt` or `baseline` still forces every task (`--rerun-tasks`).
- **`goal.py` schedules and warns.** `next` prints every ready task; `resume` says when open tasks
  are blocked; `lint` warns about `needs` errors, unchained overlapping write sets and a slow
  default gate; the approval page shows each task's gate.
- **Words.** The chief dispatches up to four builders on ready tasks, each in its own isolated
  worktree branched from the chief's HEAD, so a task dispatched after its `needs` are committed
  builds on them. Where the full gate runs in 600 s or less, it also runs every third task commit
  in a separate worktree, one at a time; where it runs longer, only at close. The builder stops when its worktree lacks the commit its packet names.

## Interfaces

1. **Task fields.** `FIELD_RE` gains `gate` and `needs`. As with `writes:` today, any task-body line
   starting `gate:` or `needs:` is a field; no shipped plan and no pilot plan has such a line in a
   task body (checked 2026-10-13). `gate:` is the rest of the line, never split, so commas and `#`
   survive; `needs:` is a comma list. `parse_plan` stores `task["gate"]` (string, empty when absent)
   and `task["needs"]` (list). `frozen_view` drops both lines under a task header; `widenings`
   compares `writes`, `tests-may-change`, `reads`, `gate` and `needs`, so done row 3 requires a
   Decisions line for a changed gate or needs, with the message "changes a task field without
   adding a Decisions line". A goal approved under v7.1 whose history edited such a line without a
   Decisions line would now fail row 3; none exists.
2. **`goal.py next` and `resume`.** A `needs` entry is a dependency only when it names a task in the
   plan; anything else is a lint warning and ignored. Ready = state `[ ]`, in the active milestone,
   every dependency ticked `[x]` (in any milestone). `next` prints one line per ready task in plan
   order, `T3 — <title>`, plus ` · gate: <cmd>` when the task has its own gate, and exits 0. When
   open tasks remain and none is ready, it prints `no ready task: T4 needs T2 (parked)` (or
   `(open)`) per blocked task and exits 1; with no open task, the existing message and exit 1.
   `resume` names the first ready task; when open tasks remain and none is ready it says `Next: no
   ready task; T4 needs T2 (parked)` and never `close the milestone`.
3. **Lint warnings.** `lint` returns errors as today and prints warnings as `lint: warning: <text>`
   before the verdict line; warnings never change the exit code. Warnings: `T4 needs T9, which is
   not an earlier task` (not a task, itself, or later in plan order); `T2 and T5 overlap in writes
   and neither needs the other` (same milestone, `overlap()` on `writes`, no path through `needs`
   either way, walked with a visited set); `T3 has no gate line and the plan gate's last check took
   <n> s (budget 600 s)` (the last line of `.runs/<id>/checks.jsonl` with label `check` and the
   plan's exact `gate` command; no file or no line, no warning).
4. **Checks record.** `run()` measures wall time. Under a goal, `check`, `receipt` and `baseline`
   append `{"label", "command", "tree", "duration_s", "verdict", "finished_at"}` to
   `<runs>/<id>/checks.jsonl` (`verdict` is `RECORDED` for a baseline that ran). Each command's last
   stdout line, after any `receipt superseded:`, rerun, `receipt:` or `baseline:` line, is
   `budget: ok (<n> s of 600 s)` or `budget: <n> s over 600 s` for `check`, 1800 s for `receipt`
   and `baseline`. A `check` with no goal writes no record and prints the budget line.
5. **`--runs <dir>`.** `check`, `receipt` and `baseline` take an optional `--runs` directory; every
   `.runs` path they use (logs, receipts, baseline, `active`, the record) is under it. The default
   is `<root>/.runs`, today's location, so nothing moves and no v7.1 evidence is stranded. The tree a
   receipt binds to, the clean-tree refusal and the change-during-run snapshot stay those of the
   worktree the command runs in. `goal.py` is unchanged: it reads its own checkout's `.runs/`, which
   is where `--runs` points.
6. **Gradle.** A task gate runs targeted tests, whose inputs the task changed, so reusing test
   results gains almost nothing; the cost today is `--rerun-tasks`, which recompiles every module
   before a few tests. `check` therefore accepts a Gradle command with `--rerun` (Gradle's per-task
   option, which forces the test task it follows and leaves compilation incremental) or
   `--rerun-tasks`; with neither, the existing reason, reworded `gradle command without --rerun or
   --rerun-tasks may report cached results`. `check` counts what ran, as today: JUnit XML written
   during the run (the existing mtime filter) and console counts. When Gradle's `<n> actionable
   tasks:` line reports `from cache`, the restored XML looks fresh but did not run, and nothing tells
   it apart from XML that did, so `check` counts no JUnit XML for that run (console counts only)
   and adds the FAIL reason `test results restored from the build cache did not run; add
   --no-build-cache`. `receipt` keeps requiring `--rerun-tasks`; a `baseline` naming Gradle without
   it is refused: exit 1, nothing recorded.
7. **Approval page.** The task table gains a Gate column: the task's `gate:` or `plan gate`.
8. **Builders.** `agents/builder.md` and `.toml` keep their isolation: the harness starts each
   builder's shell and file tools in its own worktree, so a command without a path cannot reach the
   chief's checkout. Each gains one MUST line: before the first edit, confirm that `git rev-parse
   --show-toplevel` is not the chief's checkout the packet names, and that the commit the packet
   names is an ancestor of HEAD (`git merge-base --is-ancestor <sha> HEAD`); otherwise stop and say
   so. This catches a harness that did not isolate. The packet names the chief's checkout path and
   its HEAD at dispatch. Before applying a builder's diff, the chief confirms its own checkout is
   clean (`git status --porcelain`, `.runs/` aside); a dirty checkout means something wrote there,
   and the chief stops to find it before applying anything. After committing `[Tn]`, the chief removes that builder's worktree;
   `--force` is allowed there because its staged diff is the commit, and nowhere else without a
   Decisions line.
9. **Background full gate.** It runs mid-milestone only where the plan's `full_gate` takes 600 s or
   less: its last `full_gate` line in `checks.jsonl`, or the `baseline` the chief records at approval
   on that command, says how long it took. There, at every third task commit since the last full gate
   started, the chief adds a detached worktree at that commit and runs `gate.py receipt --name
   full_gate --runs <chief .runs>` in it in the background. One runs at a time: a sample due while
   one runs starts on the newest task commit as soon as it finishes, so no sample is dropped, only
   delayed. Where the full gate takes longer, it runs only at close, alone, with no builder running;
   the task gates carry the reached test modules and the task's focused e2e instead. Before each dispatch and each commit the chief reads a finished
   run's verdict; a FAIL stops dispatch until a fix commit has a passing check. The worktree is
   removed when the run ends.

## Data touched

Two new plan fields; one new append-only file, `.runs/<id>/checks.jsonl`. No receipt or baseline
format changes and no location changes unless `--runs` is passed. No downstream repository is
edited.

## Smallest change

Fields are parsed by the existing `FIELD_RE` path; `next` reuses `next_task`'s milestone filter;
warnings reuse `overlap()`; the record is one `open(..., "a")`; `--runs` replaces one path root; the
Gradle rule widens one condition and adds one output check. The dispatch cap, the every-third full
gate and the 600-second planning budget are instructions in `SKILL.md` and
`references/planning.md`, judged by the plan reviewer and the founder, not by `done`.

## Rejected options

- **One reused worktree per lane** (the founder's first choice, evaluated here). A dependent task
  needs no reused worktree: an isolated worktree branches from the chief's HEAD (Claude with
  `worktree.baseRef: head`, Codex with `codex exec --worktree`), so a task dispatched after its
  `needs` are committed starts on them, and the builder's base check catches a stale base. Reuse
  buys warm build caches only, and costs the confinement isolation gives: without it, Claude's file
  tools and Codex's sandbox stay rooted in the chief's checkout, and a lane under the repository is
  hidden only where `.git/info/exclude` applies, never in a linked checkout. Parked as a question.
- **Continuing one builder per lane**: its context grows across tasks and `maxTurns` across
  continuations is undocumented.
- **Moving `.runs/` to the common Git directory's parent**: strands receipts and baselines that
  v7.1 goals keep in linked worktrees, and is not the main worktree when the Git directory is
  separate or absorbed.
- **A full gate per task tree**: one pilot repository's full gate runs 37 to 99 minutes, and
  overlapped gates ran up to 3.7× slower.
- **Every third task commit in every repository**: where the full gate takes 37 to 99 minutes and a
  task about 23, the next sample is due before the last one ends, so one would run nearly nonstop
  beside the builders and slow every other run. That repository's seal history (13 full-gate
  receipts: 5 setup aborts in 2 to 8 minutes, 6 real failures after 41 to 99 minutes, 2 passes)
  shows the cost is failures found late, which a scoped gate carrying the reached modules and the
  task's focused e2e addresses without the overlap (founder, 2026-10-13).
- **Reusing Gradle test results in a task check**: a targeted gate's tests have changed inputs and
  rerun anyway, so reuse gains almost nothing, and a test reading an undeclared file could pass
  stale (founder, 2026-10-13). In receipts or baselines it would let a stale result stand in for
  the milestone's evidence.
- **A `gate_budget` key or a budget error**: the council's verdict; a recorded duration and a
  warning carry the signal without halting a passing gate.
- **A lane tool**: dispatch order is the `next` output plus a cap in words.

## Trade-offs for the founder

- A reach failure the scoped gate misses surfaces at the next full gate: in a fast-gate repository
  within a few tasks; in a slow-gate repository only at close, where a failure costs one more full
  run after its fix. Dispatch stops at the first FAIL seen.
- Each builder starts with cold build output in a fresh worktree; the chief's checkout stays warm.
- At most four builders and one background full gate on this machine; overlapped gates run slower,
  and the record shows by how much.
