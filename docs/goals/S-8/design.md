# S-8 design: post-merge cleanup, and S-7's four follow-ups

## Structure

One new `goal.py` subcommand, two refusals and one closed pipe in `gate.py`, the close in words,
and three re-verified pages.

- **`goal.py cleanup --goal <id>`.** It runs after a milestone's merge and tag, in any checkout of
  the repository. It considers only what that milestone created: worktrees at one of the
  milestone's commits, the branches they had checked out, and the goal branch at the goal's last
  milestone. Of those it removes, under `--apply`, the ones whose work `origin/main` holds. Every
  other worktree and branch, whichever session made it, is out of scope and never printed. It lives in
  `goal.py` because `docs/goals/modules.json` maps exact script paths and is protected; a new
  script file would sit outside every module until the founder changed the map.
- **`gate.py`.** `named_modules` refuses an empty selection and a blank test command before
  anything runs. `run()` opens its process with `with subprocess.Popen(...)`, so the pipe closes.
- **Words.** `close.md` gives the merge, tag and cleanup sequence (`SKILL.md` already sends the
  close there), and D34 records the decision.
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
3. **`goal.py cleanup --goal <id> [--milestone <M>] [--apply]`** (durable). `main` dispatches it
   with `find_ctx(plan, goal)`, so `--goal` or `--plan` names the goal even when no milestone is
   open.
   - **Milestone.** `--milestone` defaults to the last milestone, in the plan's order, whose tag
     `goal/<id>/<M>` exists. No such tag → `goal.py: cleanup needs the tag goal/<id>/<M>; tag the
     merged milestone first`, exit 2.
   - **Base.** `git fetch --prune origin`. On failure: `goal.py: cleanup needs origin: <git's last
     stderr line>`, exit 2. The base `B` is `refs/remotes/origin/HEAD` resolved, else
     `refs/remotes/origin/main`. Neither present is the same exit 2 with `no origin/HEAD or
     origin/main`. The milestone tag not an ancestor of `B` → `goal.py: goal/<id>/<M> is not in
     <B>; merge the milestone first`, exit 2.
   - **The milestone's commits.**
     - The lower bound `L` is the previous milestone's tag in plan order, or `goal/<id>/approved`
       for the first milestone, or when that tag is missing.
     - The set `S` is `L` itself plus `git rev-list L..goal/<id>/<M>`.
     - A builder's worktree starts at the chief's HEAD at dispatch, and a full-gate sample at a
       task commit, so both point into `S`. A worktree made by another session or another goal
       does not.
   - **Worktrees in scope**, from `git worktree list --porcelain`: those whose HEAD commit is in
     `S`, except the main worktree, the one containing the current directory, and `prunable`
     entries (left to step 3). In this order, the first rule that holds decides:
     1. `locked` → keep, `locked`;
     2. any `??` line in `git -C <wt> status --porcelain` → keep, `untracked files`;
     3. `git -C <wt> diff HEAD --binary` empty → remove, `merged`;
     4. that diff reverse-applies to `B`'s tree (a temporary index from `git read-tree B`, then
        `git apply --cached --check -R`) → remove, `changes already in <B>`;
     5. otherwise keep, `changes not in <B>`.
   - **Branches in scope.**
     - Each branch checked out in an in-scope worktree.
     - At the goal's last milestone, each local branch whose tip is the milestone tag's commit.
       At an earlier milestone, that branch is kept with `the next milestone continues on it`.
     - In scope, the current branch is kept (`current branch`), and so is a branch whose worktree
       is kept (`checked out in a kept worktree`). The rest are removed, `merged`, since their
       tips are in `S` and so in `B`.
   - **Output.** First line `cleanup: <dry run|apply> for <id> <M> against <B> at <sha10>`. Then
     one line per in-scope item, worktrees then branches, each in git's order:
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
   3. It runs `goal.py cleanup --goal <id> --apply`.
   An earlier milestone keeps the goal branch, which the next milestone continues on.

## Data touched

- **Deleted, under `--apply` only.** The milestone's own worktree directories, including their
  ignored files, the branches they had checked out, the goal branch at the goal's last milestone,
  and stale worktree records. Only these, and only when `B` already holds their commits and
  changes.
- **Remote.** The merged goal branch on GitHub, through `--delete-branch` at the goal's last
  milestone. A removed local branch is recoverable from `B` or from the `goal/<id>/<milestone>`
  tag.
- **Unchanged.** Every worktree and branch outside the milestone's commits, whichever session made
  it. Also receipts, `.runs/`, tags, other remotes, and every remote branch but the merged goal's.

## Smallest change

- **Cleanup** is git plumbing in one function and one subparser. The reverse-apply test reuses
  `git apply`, and the porcelain output is git's own.
- **The follow-ups** are two checks in one function and one `with` statement.

## Rejected options

- **Instructions only.** The pilot left 118 worktrees under instructions alone (2026-10-11
  review); the founder chose a subcommand.
- **Everything provably merged, repository-wide.** This was the founder's first answer on
  2026-10-13. A live session's worktree with nothing unsaved would qualify, and could be removed
  while that session works in it. The founder narrowed the scope to what the milestone created
  (founder).
- **Ownership by location (`.claude/worktrees/` only).** Every session's builders use that
  folder, so location does not prove ownership, and sample worktrees live elsewhere.
- **Ownership by sessions locking their worktrees.** Nothing makes a session lock what it uses. A
  lock still keeps a worktree.
- **Content comparison by file hash, or `git cherry`.** Neither proves that uncommitted builder
  changes are in `B`; a reverse apply on `B`'s tree does.
- **Squash-merge detection.** It needs patch-id heuristics, and with a squash merge the milestone
  tag is not in `B`, so cleanup refuses.
- **A separate `cleanup.py`.** The protected map covers exact script paths, so a new file would sit
  outside every module until the founder changed the map.
- **`git push --delete` for the remote branch.** It is a separate push. `--delete-branch` makes the
  deletion part of the merge the founder authorises.

## Trade-offs for the founder

- **`--delete-branch` also deletes the local branch.** When the goal branch is checked out, `gh`
  switches the checkout to the default branch, which is why it is used only at the goal's last
  milestone.
- **Older leftovers stay.** The worktrees and branches of earlier goals, and of goals run before
  S-8, are out of scope; the founder removes them by hand once.
- **Two sessions on one goal.** A second session working the same milestone could own a worktree
  at one of its commits. The methodology runs one chief per goal, and a lock keeps a worktree.
- **Ignored files in a removed worktree** (caches, `.runs/` written there) go with it. Samples write
  `.runs` to the chief's checkout through `--runs`.
