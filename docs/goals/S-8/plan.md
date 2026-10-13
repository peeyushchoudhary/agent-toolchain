---
goal: S-8
title: Post-merge cleanup of worktrees and branches, and S-7's four follow-ups
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4, T5], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface, data]
protected: [docs/decisions/decisions.md#D1-D33, docs/goals/S-8/design.md#interfaces, docs/goals/S-8/design.md#data-touched]
---

## Outcome

`goal.py cleanup --goal <id>` runs after a milestone's merge and tag. It considers only what that
milestone created: worktrees at one of its commits, the branches they had checked out, and the
goal branch at the goal's last milestone. It lists those whose work `origin/main` holds and removes
them under `--apply`; the rest of the milestone's items are listed with the reason they stay. Every
other worktree and branch, whichever session made it, is untouched (AC4–AC6). `close.md` closes a
milestone in three steps:
- merge with `gh pr merge <n> --merge`, plus `--delete-branch` at the goal's last milestone;
- push the milestone tag;
- run `goal.py cleanup --goal <id> --apply`.

D34 records it (AC7). `gate.py --modules` refuses an empty selection and a blank module test
command before running anything (AC1, AC2). `gate.run` closes its pipe (AC3). The three stale
architecture pages are re-verified (AC8). Spec: [spec.md](spec.md). Design: [design.md](design.md).

## Tasks

### [ ] T1 — `gate.py --modules` refuses an empty selection and a blank test command
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-8/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
Design Interface 1. In `named_modules(root, wanted)`, after the map loads:
- **Empty selection.** When `[n.strip() for n in wanted.split(",") if n.strip()]` is empty, raise
  `RuntimeError("--modules needs module names, as in a,b, or all")`. This replaces today's
  `no module  in` path for `""` and `","`.
- **Blank test command.** After the selection is known, raise
  `RuntimeError(f"module {name} has no test command in {modmap.MAP}")` for the first selected
  module, in map order, whose `spec["test"].strip()` is empty.

`main` already turns `RuntimeError` into `gate.py: <text>` on stderr and exit 2. Do not change
`modmap.py`, the map format or any other refusal.

Tests in class `ModulesTest`, copying `test_command_key_collision_cannot_reopen_spent_retry`'s
use of `self.repo.gate(...)`:
- `test_empty_module_selection_is_refused` (AC1): for `""` and `","`, `check` and `receipt` exit 2
  with the AC1 text on stderr; `self.logs()` is unchanged and `.runs/F-9/checks.jsonl` gains no
  line.
- `test_blank_module_test_is_refused_without_running` (AC2): write a map whose module `b` has
  `"test": "  "`. Then `check --modules all` and `receipt --modules b` exit 2 with `gate.py: module b
  has no test command in docs/goals/modules.json`; no log is written and no receipt file is
  created.

### [ ] T2 — `gate.run` closes its output pipe
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-8/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
needs: T1
Design Interface 2. In `run()`, open the process as `with subprocess.Popen(...) as proc:` inside
the existing `with open(log, "w") as fh:`. The body stays the same, so the pipe and the process
close on exit. Signature, return value and readings stay unchanged; nothing else in `gate.py`
changes.

Test in class `ReceiptTest`: `test_run_closes_its_output_pipe` (AC3). Under
`warnings.catch_warnings(record=True)` with `warnings.simplefilter("always")`, call
`gate.run(self.repo.dir, "true", "F-9", "check")`, then `gc.collect()`. No recorded warning is a
`ResourceWarning`. Import `gc` and `warnings` at the top of the file. The test fails before the
change.

### [ ] T3 — `goal.py cleanup --goal <id>`: list, then remove what the milestone created
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-8/design.md#interfaces, docs/goals/S-8/design.md#data-touched, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
Design Interface 3, exactly. Its rules, order, line shapes and exit codes are the contract.

**Placement.**
- Add `cmd_cleanup(ctx, a) -> int` and the helpers it needs to `goal.py`.
- Add `cleanup` to the subparser loop, with `--milestone` and `--apply` (`store_true`). It
  resolves the goal through the existing `find_ctx`, like every other subcommand.
- Raise `PlanError` for the refusals, so `main` prints `goal.py: <text>` and exits 2.
- Milestone order comes from `ctx.plan["milestones"]`, and tags from `ctx.tag(...)` or `git tag`.

**Constraints.**
- Use git through the existing `git()` helper, plus `subprocess.run` where a non-zero exit is a
  decision rather than an error (`merge-base --is-ancestor`, `apply --check`). Standard library
  only.
- The temporary index for the reverse-apply test is a file under `tempfile.mkdtemp()`, passed as
  `GIT_INDEX_FILE` and removed afterwards.
- Do not touch `gate.py`, the fixture or any other command.

**Tests: new class `CleanupTest`.**
- **Setup.** Each test makes a bare repository with `git init --bare` and adds it as `origin` of a
  `Repo()`. The fixture plan has M1 `[T1, T2]` and M2 `[T3]`. Builders and samples are worktrees
  under `<repo>/.claude/worktrees/` and a temporary directory. Pushing `main`, then `git remote
  set-head origin main`, all goes through `self.repo.git(...)`.
- **Milestone commits.** Commit on a goal branch `goal-f9`, tag `goal/F-9/M1`, merge it into `main`
  with `--no-ff` and push; repeat for M2.
- `test_cleanup_removes_only_what_the_milestone_created` (AC4, AC6). After M2's merge, these are
  removed:
  - a worktree `agent-a` on branch `worktree-agent-a` at an M2 commit, whose staged change the
    merged M2 also makes;
  - a detached sample worktree at an M2 commit;
  - the branch `goal-f9`, once switched away from it.

  These are untouched and absent from the output:
  - a worktree on branch `other-session` at a commit before the approval tag, merged and clean;
  - a detached worktree at `main`'s merge commit;
  - a branch `old-goal` merged into `main`.

  A dry run prints `cleanup: dry run for F-9 M2 against origin/main at <sha10>`, four `remove`
  lines (two worktrees, `worktree-agent-a` and `goal-f9`) and `cleanup: 4 to remove, 0 kept`, and
  removes nothing. `--apply` removes exactly those four, and a second `--apply` prints `cleanup: 0
  removed, 0 kept`.
- `test_cleanup_keeps_the_milestones_unfinished_work` (AC5). After M1's merge, run with
  `--milestone M1`:
  - an M1-commit worktree with a staged change not in `origin/main` → `changes not in
    origin/main`;
  - one with an untracked file → `untracked files`;
  - a locked one → `locked`;
  - `goal-f9`, an earlier milestone's branch → `the next milestone continues on it`;
  - after M2's merge, run with `goal-f9` checked out: `goal-f9` → `current branch`.

  After `--apply`, every one of them still exists.
- `test_cleanup_refuses_without_origin_or_merge` (AC5). These exit 2, with stderr starting as
  quoted:
  - a `Repo()` without a remote: `goal.py: cleanup needs origin:`;
  - a milestone tag not merged into `origin/main`: `goal.py: goal/F-9/M1 is not in origin/main`;
  - no milestone tag: `goal.py: cleanup needs the tag`.

### [ ] T4 — The close in words: merge, tag, cleanup; D34
writes: install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, docs/decisions/decisions.md, AGENTS.md
reads: docs/goals/S-8/design.md#interfaces, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, docs/decisions/decisions.md#d33--methodology-v73-a-test-module-map-picks-task-gates-composes-the-full-gate-and-retries-a-failed-module-once-s-7
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
needs: T3
Design Interface 4.

**`close.md`, "Milestone close".** Replace "the founder merges and tags." with the merge and its
aftermath. Once the founder says to merge:
1. `gh pr merge <n> --merge`, adding `--delete-branch` when the milestone is the goal's last;
2. push the milestone tag `goal/<id>/<milestone>`;
3. `goal.py cleanup --goal <id> --apply`, which removes only what that milestone created.

It keeps "Next milestone: same branch." `close.md` stays within its 400-word ceiling.

**D34 in `docs/decisions/decisions.md`.**
- Add the section `## D34 — Post-merge cleanup: the close removes what origin/main holds (S-8)`
  after D33, in D33's shape (Chose, Why, Rejected). It summarises design Interfaces 3 and 4 and
  the founder's answers of 2026-10-13: a subcommand; scope narrowed to what the milestone
  created; `--delete-branch` at merge; cleanup right after the merge and tags.
- Add a D34 table row dated 2026-10-13, `standing`.
- Extend the frontmatter `summary` with one D34 clause.
- D1–D33 stay byte-identical.

**`AGENTS.md`.** Add the D34 link after D33 in the Decisions line.

Test in class `Close`: `test_close_merges_tags_then_cleans_up` (AC7). `flat(CLOSE)` contains:
- `` `gh pr merge <n> --merge` ``;
- `` `--delete-branch` ``;
- `goal's last`;
- `` `goal.py cleanup --goal <id> --apply` ``.

Do not touch `SKILL.md`, which already sends the close to `close.md`.

### [ ] T5 — Re-verify the three stale architecture pages
writes: docs/architecture/methodology.md, docs/architecture/personas.md, docs/architecture/repository-standard.md, docs/README.md, .claude/rules/**
reads: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/agents/reviewer.md, install/skills/execution-methodology/agents/scout.md, docs/goals/modules.json
tests-may-change: none
needs: T1, T2, T3, T4
gate: python3 install/skills/execution-methodology/scripts/docs.py stale . && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
AC8. Read each page against the files in `reads:` and correct every statement they contradict. Known
gaps:
- **`methodology.md`.** Its Rollback names "the v7.1 tree" and "v7.1-only files"; it should name
  the current tree and give `goal/S-6/M1` as the way back to v7.2. Its close bullet gains the merge,
  tag and cleanup step.
- **`repository-standard.md`.** Its layout block lists `docs/goals/modules.json`, the test-module
  map (D33).
- **`personas.md`.** It is checked line by line against the three agent files.

Set each page's `last-verified` to the day of this commit. If a `summary` changes, run `docs.py
index .` and `docs.py pointers .`, and commit their output. Change no other page, no frontmatter
key but `summary` and `last-verified`, and no file under `install/`.

## Decisions

- 2026-10-13 planning: the founder chose:
  - a `goal.py cleanup` subcommand, dry run by default, with `--apply`;
  - scope: first everything provably merged. The founder then narrowed it to what the merged
    milestone created, because a live session's worktree with nothing unsaved would otherwise
    qualify;
  - deleting the remote goal branch at merge with `gh pr merge --delete-branch`;
  - cleanup right after the merge and tags (founder).
- 2026-10-13 planning: `--delete-branch` is used only at a goal's last milestone. It also deletes
  the local branch and switches the checkout, and an earlier milestone's goal branch carries the
  next milestone (default).
- 2026-10-13 planning: a worktree belongs to the milestone when its HEAD is one of the
  milestone's commits: the previous milestone's tag, or the approval tag, through the milestone's
  tag. A builder starts at the chief's HEAD and a sample at a task commit; other sessions' and
  goals' worktrees start elsewhere. Location (`.claude/worktrees/`) and session locks were
  rejected as proof of ownership (default).
- 2026-10-13 planning: cleanup lives in `goal.py`, not a new script. `docs/goals/modules.json` maps
  exact script paths and is protected, so a new file would sit outside every module (default).
- 2026-10-13 planning: T1–T4 carry no `gate:` line and run the modules `goal.py next` derives from
  the map. T5 runs `docs.py stale` and the repository's non-test checks, because `verify.sh` only
  warns on a stale page (default).
- 2026-10-13 planning: the plan gate `cd install && ./verify.sh` took 231 s in S-7's last full-gate
  receipts, under the 600 s budget, so it was not timed again (default).
- 2026-10-13 planning: AC8 is judged at T5's commit. `methodology.md` covers `install/**`, so a
  later fix commit under `install/` makes it stale again, and only `verify.sh`'s warning reports
  that (default).
- 2026-10-13 planning: the e2e is S-7's `e2e_run.sh`, receipted with `--count none`. Cleanup is
  git-only and harness-independent, and `CleanupTest` exercises it against real repositories
  (default).

## Parked

- Q: S-8 keeps `full_gate` as the single command. Should it use `full_gate: modules` instead, the
  first real use of the composed gate? Default: the single command.
