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

The chief records each builder and full-gate sample worktree it uses with `goal.py own --goal <id>
<path>` (AC4). After a milestone's merge and tag, `goal.py cleanup --goal <id>` considers only
those recorded worktrees and their branches. It lists the ones whose commit and staged changes
`origin/main` holds, removes them under `--apply`, and prints why each other recorded item stays.
Anything unrecorded, whichever session made it, is untouched (AC5, AC6). The skill says when to
run `own`; `close.md` closes a milestone in four steps:
- `done` prints DONE on the PR's head;
- merge with `gh pr merge <n> --merge`, plus `--delete-branch` at the goal's last milestone;
- tag `goal/<id>/<milestone>` at that head and push the tag;
- run `goal.py cleanup --goal <id> --apply`.

D34 records it (AC7). `gate.py --modules` refuses an empty selection and a blank module test
command before running anything (AC1, AC2). `gate.run` closes its pipe (AC3). The three stale
architecture pages are re-verified (AC8). Spec: [spec.md](spec.md). Design: [design.md](design.md).

## Tasks

### [x] T1 — `gate.py --modules` refuses an empty selection and a blank test command
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

### [x] T2 — `gate.run` closes its output pipe
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

### [x] T3 — `goal.py own` records a goal's worktrees; `goal.py cleanup` removes what `origin/main` holds
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-8/design.md#interfaces, docs/goals/S-8/design.md#data-touched, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
Design Interfaces 3, 4 and 5, exactly. Their record format, rule order, line shapes and exit codes
are the contract.

**Placement.**
- Add `cmd_own(ctx, a)` and `cmd_cleanup(ctx, a)`, with their helpers, to `goal.py`.
- Add `own` (a positional `path`) and `cleanup` (`--apply`, `store_true`) to the subparser loop in
  `main`. The goal resolves through the existing `find_ctx`, like every other subcommand.
- Refusals raise `PlanError`, so `main` prints `goal.py: <text>` and exits 2.
- The record lives in the main worktree, at `<main>/.runs/<id>/worktrees.jsonl` (Interface 3),
  not at `ctx.runs`, so every checkout shares it.

**Constraints.**
- Use git through the existing `git()` helper. Use `subprocess.run` where a non-zero exit is a
  decision rather than an error (`merge-base --is-ancestor`, `diff --quiet`, `apply --check`), and
  for the fetch: `git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main` with
  `timeout=120`. Standard library only.
- No `fetch --prune` and no `git worktree prune`.
- Do not touch `gate.py`, the fixture or any other command.

**Tests: new class `CleanupTest`.**
- **Setup.**
  - Each test makes a bare repository with `git init --bare` and adds it as `origin` of a
    `Repo()`.
  - It appends `/.claude/` to `.gitignore` and commits, so `Repo.commit()`'s `git add -A` never
    stages a nested worktree.
  - It pushes `main`, a second branch `elsewhere` and a tag `v-old` on a pushed `main` commit,
    then deletes the tag locally. All through `self.repo.git(...)`.
  - A builder is simulated by `git worktree add -b worktree-agent-<x>
    <repo>/.claude/worktrees/agent-<x>` and a staged change there.
  - Landing its work means writing the same file on `main`, committing and pushing.
  - Every assertion on a kept or removed item checks its full output line, not only that it
    exists.
- `test_own_records_only_linked_worktrees_of_this_repository` (AC4).
  - `own` on a linked worktree prints `own: <path> (worktree-agent-a)` and appends one line with
    `path`, `branch`, `head` and `at` to `<repo>/.runs/F-9/worktrees.jsonl`.
  - `own` on the same path again appends nothing.
  - `own` on the main checkout, a plain directory, and another repository's worktree each exit 2
    with `is not a linked worktree of this repository`.
- `test_cleanup_removes_only_recorded_work_main_holds` (AC5, AC6). Recorded:
  - `agent-a`, whose staged change has landed;
  - a detached sample worktree, under a temporary directory, at a pushed commit, clean.

  Not recorded:
  - a clean worktree `other-session` at a pushed commit;
  - a merged branch `old-goal`.

  Then `elsewhere` is deleted on `origin`. The dry run:
  - prints `cleanup: dry run for F-9 against origin/main at <sha10>`;
  - prints `remove` lines for the two worktrees and for branch `worktree-agent-a`;
  - ends with `cleanup: 3 to remove, 0 kept`.

  Afterwards:
  - `refs/remotes/origin/elsewhere` and the absence of tag `v-old` are unchanged;
  - every worktree and branch still exists;
  - the unrecorded items never appear in the output.

  `--apply` removes exactly the three, and a second `--apply` prints `cleanup: 0 removed, 0 kept`.
- `test_cleanup_from_another_checkout_uses_the_ownership_record` (AC5). Record `agent-a` from the
  main checkout, then run `cleanup` with the working directory set to the detached sample worktree,
  which is recorded too. It prints `remove worktree <agent-a path> (merged)` and `keep worktree
  <sample path>: in use here`.
- `test_cleanup_keeps_recorded_work_main_lacks` (AC6). These are recorded, and after `--apply` each
  prints `keep worktree <path>: <reason>` and still exists:
  - `locked`, on a locked worktree that also holds an untracked file: the first rule wins;
  - `untracked files`;
  - `staged changes not in origin/main`, with `git -C <wt> diff --cached` unchanged afterwards;
  - `1 commit(s) not in origin/main`;
  - `submodules`, from a gitlink added by `git update-index --add --cacheinfo 160000,<sha>,sub`;
  - `unstaged changes`, from a file with content `A`, then `B` staged, then `A` restored in the
    working file. The staged `B` is still in the index afterwards.
- `test_cleanup_keeps_recorded_branches_that_moved` (AC6). Record `worktree-agent-c` and
  `worktree-agent-d`, landed and clean, then remove both worktrees by hand with `git worktree
  remove`.
  - Switch the main checkout to `worktree-agent-c`.
  - Add an unpushed commit to `worktree-agent-d` with `git commit-tree` and `git update-ref`.

  `--apply` prints:
  - `gone worktree <path>` for each;
  - `keep branch worktree-agent-c: current branch`;
  - `keep branch worktree-agent-d: 1 commit(s) not in origin/main`.

  Both branches still exist.
- `test_cleanup_retries_a_branch_whose_removal_failed` (AC6). Record `worktree-agent-b`, landed and
  clean, and create the file `<git common dir>/refs/heads/worktree-agent-b.lock` so that `git branch
  -D` fails.
  - The first `--apply` prints `removed worktree <path> (merged)` and `cleanup: could not remove
    branch worktree-agent-b:`, and exits 1. The record has no `branch_removed` line.
  - After the lock file is deleted, the next `--apply` prints `removed branch worktree-agent-b
    (merged)` and exits 0.
- `test_cleanup_completes_records_and_refuses_without_origin_main` (AC5).
  - With no record file, cleanup prints `cleanup: 0 to remove, 0 kept`.
  - A recorded worktree removed by hand whose branch was deleted by hand prints only `gone
    worktree <path>`, and a second run prints nothing for it.
  - A `Repo()` without a remote exits 2, and stderr starts `goal.py: cleanup needs origin/main:`.

### [ ] T4 — The loop and the close in words: `own`, merge, tag, cleanup; D34
writes: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, docs/decisions/decisions.md, AGENTS.md
reads: docs/goals/S-8/design.md#interfaces, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py, docs/decisions/decisions.md#d33--methodology-v73-a-test-module-map-picks-task-gates-composes-the-full-gate-and-retries-a-failed-module-once-s-7
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
needs: T3
Design Interface 6.

**`SKILL.md`, the loop.**
- Step 3 adds: record each builder's worktree with `goal.py own --goal <id> <path>` once the
  builder reports it.
- Step 8 adds: record the sample worktree the same way.

The always-loaded files total 1,324 of 1,350 words today (`install/tests/test_size.py`). Both
additions together stay within 20 words, and nothing else in `SKILL.md` changes.

**`close.md`, "Milestone close".** Replace "the founder merges and tags." with these steps, in
this order and in these words:
1. `goal.py done` prints DONE on the PR's head; that commit is the milestone's.
2. Once the founder says to merge, run `gh pr merge <n> --merge`, adding `--delete-branch` only
   when the milestone is the goal's last.
3. `git tag goal/<id>/<milestone> <head>` at that head commit, not at the checkout `gh` switched,
   then `git push origin goal/<id>/<milestone>`.
4. Run `goal.py cleanup --goal <id> --apply`. It removes only the worktrees recorded with `own`,
   and their branches, whose work `origin/main` holds.

It keeps "Next milestone: same branch." `close.md` stays within its 400-word ceiling.

**D34 in `docs/decisions/decisions.md`.**
- Add the section `## D34 — Post-merge cleanup: the chief records its worktrees and removes what
  origin/main holds (S-8)` after D33, in D33's shape (Chose, Why, Rejected).
- It summarises design Interfaces 3 to 6 and the founder's answers of 2026-10-13: a subcommand;
  scope narrowed from everything merged to recorded worktrees; ignored files in a recorded
  worktree are disposable; `--delete-branch` at the goal's last merge; cleanup right after the
  merge and tag.
- Add a D34 table row dated 2026-10-13, `standing`, and one D34 clause in the frontmatter
  `summary`.
- D1–D33 stay byte-identical.

**`AGENTS.md`.** Add the D34 link after D33 in the Decisions line.

**Tests in class `Close`.**
- `test_close_merges_tags_the_head_then_cleans_up` (AC7). In `flat(CLOSE)`, these appear, each
  after the one before:
  1. `goal.py done`;
  2. `` `gh pr merge <n> --merge` ``;
  3. `` `git tag goal/<id>/<milestone> <head>` ``;
  4. `` `git push origin goal/<id>/<milestone>` ``;
  5. `` `goal.py cleanup --goal <id> --apply` ``.

  The sentence holding `` `--delete-branch` `` also holds `only when the milestone is the goal's
  last`.
- `test_the_loop_records_builder_and_sample_worktrees` (AC7). `loop_step(3)` contains `goal.py own
  --goal <id> <path>`, and `loop_step(8)` contains `goal.py own`. Use the existing `loop_step`
  helper; `SKILL` is the skill directory and `ENTRY` its `SKILL.md`.

### [ ] T5 — Re-verify the three stale architecture pages
writes: docs/architecture/methodology.md, docs/architecture/personas.md, docs/architecture/repository-standard.md, docs/README.md, .claude/rules/**
reads: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/agents/builder.md, install/skills/execution-methodology/agents/reviewer.md, install/skills/execution-methodology/agents/scout.md, docs/goals/modules.json
tests-may-change: none
needs: T1, T2, T3, T4
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
AC8. Read each page against the files in `reads:` and correct every statement they contradict. Known
gaps:
- **`methodology.md`.** Its Rollback names "the v7.1 tree" and "v7.1-only files"; it should name
  the current tree and give `goal/S-6/M1` as the way back to v7.2. Its close bullet gains the merge,
  tag and cleanup step.
- **`repository-standard.md`.** Its layout block lists `docs/goals/modules.json`, the test-module
  map (D33).
- **`personas.md`.** It is checked line by line against the three agent files.

Set each page's `last-verified` to the day of this commit. After committing, the chief runs
`python3 install/skills/execution-methodology/scripts/docs.py stale .`, which must print `docs.py
stale: PASS`. It compares commit times, so it cannot pass before the commit, and the chief
records its output in a Decisions line. If a `summary` changes, run `docs.py
index .` and `docs.py pointers .`, and commit their output. Change no other page, no frontmatter
key but `summary` and `last-verified`, and no file under `install/`.

## Decisions

- 2026-10-13 planning: the founder chose:
  - a `goal.py cleanup` subcommand, dry run by default, with `--apply`;
  - scope: first everything provably merged. The founder then narrowed it to what the milestone
    created, because a live session's worktree with nothing unsaved would otherwise qualify. After
    the design review, the founder made it the worktrees the chief records with `goal.py own`;
  - deleting the remote goal branch at merge with `gh pr merge --delete-branch`;
  - cleanup right after the merge and tags (founder).
- 2026-10-13 planning: `--delete-branch` is used only at a goal's last milestone. It also deletes
  the local branch and switches the checkout, and an earlier milestone's goal branch carries the
  next milestone (default).
- 2026-10-13 design review (BLOCK, 12 blocking and 3 non-blocking), resolved in the design.
  - **Founder's answers.**
    - Ownership is the chief's record (`goal.py own`), not the milestone's commit range (R1, R2,
      R3, R14).
    - Ignored files in a recorded worktree are disposable (R5).
    - AC8 is checked right after T5's commit (R11, R12).
  - **Defaults.**
    - A worktree is kept when its unstaged changes would hide staged content (R4), and when it
      holds submodules (R6).
    - The base is `origin/main` alone (R7).
    - The fetch takes only `main`, prunes nothing, and times out at 120 s (R8, R13).
    - No `git worktree prune` (R9).
    - The tag names the PR's head commit, not the checkout `gh` switched (R10).
    - The file-comparison option is rejected for the reason R15 gives (default).
- 2026-10-13 plan review (BLOCK, 6 blocking and 3 non-blocking), resolved in the plan and design.
  - **T5.** The after-commit check expects `docs.py stale: PASS`, which `docs.py` prints when no
    page is stale (R1).
  - **T4.** Its tests use `loop_step()` and an ordered check of the close's steps, including the
    tag push (R2, R9).
  - **The record.** It lives in the main worktree's `.runs/`, so cleanup from any checkout finds it
    (R3).
  - **The fetch.** It adds `--no-tags` (R4).
  - **T3's tests.** They now cover:
    - a real `git branch -D` failure, through a ref lock file (R5);
    - recorded branches that became current or gained a commit after their worktree went (R6);
    - first-rule precedence, `in use here`, an absent record, a completed record, and each
      reason's full line (R7);
    - an ignored `/.claude/` in the fixture (R8).
  - **Not tested.** The fetch timeout and a failed `git worktree remove` are untested, because
    neither is reproducible without faking git (default).
- 2026-10-13 planning: cleanup lives in `goal.py`, not a new script. `docs/goals/modules.json` maps
  exact script paths and is protected, so a new file would sit outside every module (default).
- 2026-10-13 planning: T1–T4 carry no `gate:` line and run the modules `goal.py next` derives from
  the map. T5's gate is `test_docs.py` and the repository's non-test checks, and `docs.py stale`
  runs after its commit (default).
- 2026-10-13 planning: the plan gate `cd install && ./verify.sh` took 231 s in S-7's last full-gate
  receipts, under the 600 s budget, so it was not timed again (default).
- 2026-10-13 approval: the founder approved the plan and left the `full_gate: modules` question
  unanswered, so `full_gate` stays the single command (default).
- 2026-10-13 planning: the e2e is S-7's `e2e_run.sh`, receipted with `--count none`. Cleanup is
  git-only and harness-independent, and `CleanupTest` exercises it against real repositories
  (default).
- 2026-10-13 T1: the empty-selection refusal comes before the map and unknown-module checks, so
  `--modules ""` gives the AC1 text even without a map. The blank check reads `spec["test"]`
  directly, since `modmap.load` rejects a non-string test. The module docstring's `--modules` lines
  do not mention the two refusals (follow-up) (default).
- 2026-10-13 T2: built by the chief, as a trivial task. The new test failed before the change, and
  `test_gate.py` no longer prints a ResourceWarning (default).- 2026-10-13 T3:
  - **Paths in output.** The checkout cleanup runs from prints as an absolute path, and `own`
    prints and stores the resolved absolute path. A second `own` of a recorded path prints its line
    and appends nothing.
  - **Record writes.** Records are written only under `--apply`.
  - **Dry run.** A worktree the dry run would remove no longer counts as checking out its branch.
  - **Counts.** A failed removal counts as neither removed nor kept.
  - **Directory gone.** A recorded worktree that git still lists but whose directory is gone
    (`prunable` or missing) is removed with reason `directory gone`. This runs `git worktree remove
    --force <path>` for that path only, and its branch rules follow. The lock and `in use here`
    rules come first, so a locked worktree on an absent drive is kept. The chief added that order
    and `test_cleanup_keeps_a_locked_worktree_whose_directory_is_gone` (default).
  - **Follow-ups.**
    - With no `origin`, the refusal quotes git's last stderr line, not its `fatal:` line.
    - A finished path that is re-created and owned again is ignored.

## Parked
