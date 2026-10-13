# S-8 design: post-merge cleanup, and S-7's four follow-ups

## Structure

Two new `goal.py` subcommands, two refusals and one closed pipe in `gate.py`, the loop and the
close in words, and three re-verified pages.

- **`goal.py own --goal <id> <path>`.** The chief records each worktree it uses for the goal: a
  builder's, once the builder reports its worktree, and a full-gate sample's, once created. The
  record is ownership. Neither a commit nor a location proves which session made a worktree; the
  chief's record does.
- **`goal.py cleanup --goal <id>`.** It runs after a milestone's merge and tag, in any checkout of
  the repository, and considers only the goal's recorded worktrees and their branches. It removes,
  under `--apply`, those whose commits and changes `origin/main` holds. Anything unrecorded,
  whichever session made it, is never inspected, printed or changed.
- **Placement.** Both live in `goal.py`, because `docs/goals/modules.json` maps exact script paths
  and is protected; a new script file would sit outside every module until the founder changed the
  map.
- **`gate.py`.** `named_modules` refuses an empty selection and a blank test command before
  anything runs. `run()` opens its process with `with subprocess.Popen(...)`, so the pipe closes.
- **Words.** `SKILL.md` steps 3 and 8 record worktrees with `goal.py own`. `close.md` gives the
  tag, merge and cleanup sequence. D34 records the decision.
- **Pages.** `methodology.md`, `personas.md` and `repository-standard.md` are re-verified against
  the v7.3 skill plus this goal. Their `last-verified` is set to the day of that commit.

## Interfaces

1. **`gate.py --modules`** (durable). After parsing, `named_modules(root, wanted)`:
   - with no non-blank name in `wanted` split on `,`, raises
     `RuntimeError("--modules needs module names, as in a,b, or all")`;
   - for the first selected module, in map order, whose `test` is blank after `strip()`, raises
     `RuntimeError(f"module {name} has no test command in {modmap.MAP}")`.
   `check_modules` and `receipt_modules` both call it first, and `main` prints `gate.py: <text>` to
   stderr and exits 2. Nothing runs, no line goes to `checks.jsonl` and no receipt is written.
2. **`gate.run`** keeps its signature, output, return value and readings; only the process handle
   is a context manager.
3. **The record** (durable). `.runs/<id>/worktrees.jsonl`, one JSON object per line, written only
   by `goal.py`:
   - `{"path": <absolute real path>, "branch": <short name or null>, "head": <sha>, "at": <ISO
     time>}` for `own`;
   - `{"path": <path>, "removed": <ISO time>}` once cleanup removed the worktree;
   - `{"path": <path>, "branch_removed": <ISO time>}` once it removed the branch.

   An entry with both later lines is finished. A path recorded twice keeps its first entry.
4. **`goal.py own --goal <id> <path>`** (durable). The path, resolved, must be a linked worktree
   in `git worktree list --porcelain` of this repository: not the main worktree, and not the one
   containing the current directory. Otherwise: `goal.py: <path> is not a linked worktree of this
   repository`, exit 2. It appends the `own` line and prints `own: <path> (<branch or detached>)`.
5. **`goal.py cleanup --goal <id> [--apply]`** (durable). `main` resolves the goal with `find_ctx`.
   - **Base.**
     - `git fetch origin refs/heads/main:refs/remotes/origin/main`, with a 120 s timeout. It
       updates that one ref and prunes nothing.
     - On failure or timeout: `goal.py: cleanup needs origin/main: <git's last stderr line or
       "timed out">`, exit 2, with nothing else done.
     - The base `B` is `refs/remotes/origin/main`.
   - **Scope.** The unfinished entries of `.runs/<id>/worktrees.jsonl`, in record order. No record
     file means nothing in scope.
   - **A recorded worktree still in `git worktree list`** gets the first rule that holds:
     1. it is the main worktree or contains the current directory → keep, `in use here`;
     2. `locked` → keep, `locked`;
     3. its HEAD not an ancestor of `B` → keep, `<n> commit(s) not in origin/main`;
     4. `git -C <wt> ls-files -s` lists a mode-160000 entry → keep, `submodules`;
     5. `git -C <wt> status --porcelain` shows a `??` line → keep, `untracked files`;
     6. `git -C <wt> diff --quiet` fails → keep, `unstaged changes`;
     7. `git -C <wt> diff --cached --binary` empty → remove, `merged`;
     8. that staged diff reverse-applies to `B`'s tree → remove, `changes already in origin/main`.
        The check is a temporary index from `git read-tree B`, under a `tempfile.mkdtemp()`
        directory removed afterwards, then `git apply --cached --check -R`;
     9. otherwise keep, `staged changes not in origin/main`.
   - **A recorded worktree no longer listed** is printed as `gone worktree <path>`, gets its
     `removed` line under `--apply`, and has no rules applied.
   - **Its recorded branch**, once the worktree is removed or gone, gets the first rule that
     holds:
     - the branch no longer exists → `branch_removed` line, not printed;
     - it is the current branch → keep, `current branch`;
     - it is checked out in any worktree → keep, `checked out`;
     - its tip is not an ancestor of `B` → keep, `<n> commit(s) not in origin/main`;
     - otherwise remove, `merged`.

     A kept worktree keeps its branch unprinted.
   - **Output.**
     - The first line is `cleanup: <dry run|apply> for <id> against origin/main at <sha10>`.
     - Then one line per decision, in record order:
       - `remove worktree <path> (<reason>)` in a dry run, or `removed worktree <path>
         (<reason>)` with `--apply`;
       - `keep worktree <path>: <reason>`;
       - the same two shapes with `branch <name>`.
     - `<path>` is relative to the root when inside it, else absolute.
     - The last line is `cleanup: <r> to remove, <k> kept` in a dry run, or `cleanup: <r> removed,
       <k> kept` with `--apply`.
   - **Removal**, with `--apply` only:
     1. `git worktree remove --force <path>`. Ignored files go with it (founder, 2026-10-13).
     2. `git branch -D <name>` once the worktree is gone. A branch whose removal fails keeps its
        unfinished entry, so the next run retries it.

     There is no `git worktree prune`. A failed git call prints `cleanup: could not remove
     <what>: <git's last stderr line>`, the run continues, and the exit is 1. Otherwise the exit
     is 0, in both modes.
6. **The loop and the close, in words** (durable).
   - **Loop step 3:** when a builder reports its worktree, `goal.py own --goal <id> <path>`.
   - **Loop step 8:** the same, for the detached sample worktree it creates.
   - **Close.**
     1. `goal.py done` prints DONE on the PR's head; that commit is the milestone's.
     2. Once the founder says to merge, the chief runs `gh pr merge <n> --merge`, adding
        `--delete-branch` when the milestone is the goal's last.
     3. It tags `goal/<id>/<milestone>` at that head commit, never at the checkout after `gh`
        switched it, and pushes the tag.
     4. It runs `goal.py cleanup --goal <id> --apply`.

     An earlier milestone keeps the goal branch, which the next milestone continues on.

## Data touched

- **New file.** `.runs/<id>/worktrees.jsonl`, append-only. `.runs/` is ignored and local.
- **Updated ref.** `refs/remotes/origin/main`, by the fetch, in both modes.
- **Deleted, under `--apply` only.**
  - Recorded worktrees whose commit and staged changes `origin/main` holds, together with their
    ignored files.
  - Their recorded branches, when the tip is in `origin/main` and no worktree has them checked
    out.
- **Remote.** The merged goal branch on GitHub, through `--delete-branch` at the goal's last
  milestone. A removed branch's commits stay in `origin/main` and under the milestone tag.
- **Unchanged.**
  - Every unrecorded worktree and branch, other remote-tracking refs, stale worktree records,
    tags and receipts.
  - Ignored files in kept worktrees.

## Smallest change

- **`own`** appends one line after one `git worktree list`.
- **`cleanup`** is git plumbing over the record. The reverse-apply test reuses `git apply`.
- **The follow-ups** are two checks in one function and one `with` statement.

## Rejected options

- **Instructions only.** The pilot left 118 worktrees under instructions alone (2026-10-11
  review); the founder chose a subcommand.
- **Everything provably merged, repository-wide.** The founder's first answer on 2026-10-13. A
  live session's clean worktree would qualify, and could be removed while that session works in
  it. The founder narrowed the scope (founder).
- **Ownership by commit range** (the milestone's commits). Another session can make a worktree on
  the goal branch, and a branch at the milestone's commit need not be the goal branch (design
  review R1, R2). The founder chose the record (founder).
- **Ownership by location or session locks.** Every session's builders share `.claude/worktrees/`,
  and nothing makes a session lock what it uses. A lock still keeps a recorded worktree.
- **The combined `diff HEAD`.** Staged content can hide behind an unstaged change that restores
  the old file (design review R4). Unstaged changes keep the worktree, and the staged diff is
  checked on its own.
- **Comparing changed files' contents and modes with `B`.** It proves preservation for a subset,
  but it rejects changes that sit beside later edits on `main`. The reverse apply covers that case
  and stays one git call.
- **`fetch --prune` or `git worktree prune`.** Both change refs or records outside the goal's
  scope (design review R8, R9).
- **`origin/HEAD` as the base.** A stale symbolic ref could name another branch (design review
  R7). The base is `origin/main`, and other default branches are a non-goal.
- **A separate script file.** The protected map covers exact script paths.
- **`git push --delete` for the remote branch.** It is a separate push. `--delete-branch` makes the
  deletion part of the merge the founder authorises.

## Trade-offs for the founder

- **A forgotten `own`** leaves that worktree for hand removal; it never deletes another session's
  work (founder, 2026-10-13).
- **Ignored files in a recorded worktree** (`build/`, `node_modules`, caches) are removed with it.
  A builder or a sample holds no durable data (founder, 2026-10-13).
- **Older leftovers stay.** Worktrees from before S-8, or never recorded, are removed by hand once.
- **`--delete-branch` also deletes the local branch.** When the goal branch is checked out, `gh`
  switches the checkout to the default branch. That is why it is used only at the goal's last
  milestone, and why the tag names the head commit rather than the checkout.
- **Pages go stale again.** AC8 is checked right after T5's commit. A later merge-review fix under
  `install/**` brings back the warning for `methodology.md`, and the next goal re-verifies it
  (founder, 2026-10-13).
