# S-8 design: post-merge cleanup, and S-7's four follow-ups

## Structure

One new `goal.py` subcommand, two refusals and one closed pipe in `gate.py`, the close in words,
and three re-verified pages.

- **`goal.py cleanup`.** It runs in any checkout of the repository and needs no goal or plan. It
  fetches `origin`, decides from git alone what `origin/main` already holds, prints one line per
  worktree and local branch, and removes the provable ones only under `--apply`. It lives in
  `goal.py` because `docs/goals/modules.json` maps exact script paths and is protected; a new
  script file would sit outside every module until the founder changed the map.
- **`gate.py`.** `named_modules` refuses an empty selection and a blank test command before
  anything runs. `run()` opens its process with `with subprocess.Popen(...)`, so the pipe closes.
- **Words.** `close.md` gives the merge, tag and cleanup sequence, `SKILL.md`'s milestone close
  names cleanup in one clause, and D34 records the decision.
- **Pages.** `methodology.md`, `personas.md` and `repository-standard.md` are re-verified against
  the v7.3 skill plus this goal, and their `last-verified` set to the day of that commit.

## Interfaces

1. **`gate.py --modules`** (durable). After parsing, `named_modules(root, wanted)`:
   - with no non-blank name in `wanted` split on `,`, raises
     `RuntimeError("--modules needs module names, as in a,b, or all")`;
   - for each selected module whose `test` is blank after `strip()`, raises
     `RuntimeError(f"module {name} has no test command in {modmap.MAP}")` for the first in map
     order.
   `main` already prints `gate.py: <text>` to stderr and exits 2. Nothing runs, no line goes to
   `checks.jsonl` and no receipt is written.
2. **`gate.run`** keeps its signature and return value; only the process handle is a context
   manager.
3. **`goal.py cleanup [--apply]`** (durable). `main` dispatches it before `find_ctx`, with the
   repository root from `git rev-parse --show-toplevel` in the current directory.
   - **Base.** `git fetch --prune origin`. On failure: `goal.py: cleanup needs origin: <git's last
     stderr line>`, exit 2. The base `B` is `refs/remotes/origin/HEAD` resolved, else
     `refs/remotes/origin/main`; neither present is the same exit 2 with `no origin/HEAD or
     origin/main`. The default branch is `B` without `origin/`.
   - **Worktrees**, from `git worktree list --porcelain`, skipping the first (main) entry and the
     one containing the current directory. In this order, the first rule that holds decides:
     1. `prunable` → left to step 5, not printed;
     2. `locked` → keep, `locked`;
     3. HEAD not an ancestor of `B` → keep, `<n> commit(s) not in <B>`;
     4. any `??` line in `git -C <wt> status --porcelain` → keep, `untracked files`;
     5. `git -C <wt> diff HEAD --binary` empty → remove, `merged`;
     6. that diff reverse-applies to `B`'s tree (a temporary index from `git read-tree B`, then
        `git apply --cached --check -R`) → remove, `changes already in <B>`;
     7. otherwise keep, `changes not in <B>`.
   - **Branches**, from `refs/heads/`. These are kept: the default branch (`default branch`), the
     current branch (`current branch`), and a branch checked out in a kept worktree (`checked out
     in a kept worktree`). A tip that is an ancestor of `B` → remove, `merged`. Otherwise keep,
     `<n> commit(s) not in <B>`.
   - **Output.** First line `cleanup: <dry run|apply> against <B> at <sha10>`. Then one line per
     decision, worktrees then branches, each in git's order:
     - `remove worktree <path> (<reason>)` in a dry run, or `removed worktree <path> (<reason>)`
       with `--apply`;
     - `keep worktree <path>: <reason>`;
     - the same two shapes with `branch <name>`.

     `<path>` is relative to the root when inside it, else absolute. The last line is `cleanup:
     <r> to remove, <k> kept` in a dry run, or `cleanup: <r> removed, <k> kept` with `--apply`.
   - **Removal**, with `--apply` only:
     1. `git worktree remove --force <path>` per worktree;
     2. `git branch -D <name>` per branch, after its worktree is gone;
     3. `git worktree prune`.

     A failed git call prints `cleanup: could not remove <what>: <git's last stderr line>`, the
     run continues, and the exit is 1. Otherwise the exit is 0, in both modes.
4. **The close, in words** (durable).
   1. Once the founder says to merge, the chief runs `gh pr merge <n> --merge`, with
      `--delete-branch` when the milestone is the goal's last.
   2. It pushes the milestone tag.
   3. It runs `goal.py cleanup --apply`.
   An earlier milestone keeps the goal branch, which the next milestone continues on.

## Data touched

- **Deleted, under `--apply` only.** Local worktree directories, including their ignored files,
  local branch refs, and stale worktree records. Only these, and only when `B` already holds their
  commits and changes.
- **Remote.** The merged goal branch on GitHub, through `--delete-branch` at the goal's last
  milestone. A removed local branch is recoverable from `B` or from the `goal/<id>/<milestone>`
  tag.
- **Unchanged.** Receipts, `.runs/`, tags, other remotes and every remote branch but the merged
  goal's.

## Smallest change

- **Cleanup** is git plumbing in one function and one subparser. The reverse-apply test reuses
  `git apply`, and the porcelain output is git's own.
- **The follow-ups** are two checks in one function and one `with` statement.

## Rejected options

- **Instructions only.** The pilot left 118 worktrees under instructions alone (2026-10-11
  review); the founder chose a subcommand.
- **This goal's leftovers only.** Older leftovers would need hand removal; the founder chose
  everything provably merged.
- **Content comparison by file hash, or `git cherry`.** Neither proves that uncommitted builder
  changes are in `B`; a reverse apply on `B`'s tree does.
- **Squash-merge detection.** It needs patch-id heuristics. Squash-merged branches stay listed as
  unmerged.
- **A separate `cleanup.py`.** The protected map covers exact script paths, so a new file would sit
  outside every module until the founder changed the map.
- **`git push --delete` for the remote branch.** It is a separate push. `--delete-branch` makes the
  deletion part of the merge the founder authorises.

## Trade-offs for the founder

- **`--delete-branch` also deletes the local branch.** When the goal branch is checked out, `gh`
  switches the checkout to the default branch, which is why it is used only at the goal's last
  milestone.
- **A goal between milestones.** A branch whose milestone just merged is "merged" until new work
  lands. It is kept only while it is the current branch. If deleted, `git switch -c <branch>
  goal/<id>/<milestone>` restores it.
- **Ignored files in a removed worktree** (caches, `.runs/` written there) go with it. Samples write
  `.runs` to the chief's checkout through `--runs`.
