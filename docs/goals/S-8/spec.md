# S-8 spec: post-merge cleanup, and S-7's four follow-ups

**Users and problem.** Chiefs and the founder on v7.3 repositories. After a milestone PR merges,
nothing removes what the goal left: on 2026-10-13 one project held 9 builder worktrees and 14
local branches already in `origin/main`. S-7 also left four follow-ups: `gate.py` runs a map
module whose test command is blank; `--modules ""` prints `no module  in`; a `gate.run` test
prints a ResourceWarning; three architecture pages fail `docs.py stale`.

**What changes for the user.** `goal.py cleanup` lists every worktree and local branch whose work
is provably in `origin/main`, and `--apply` removes them; anything else is listed with the reason
it stays. A milestone's close deletes the remote goal branch at its goal's last merge, then runs
cleanup. Two refusals read plainly, and the pages are current.

**Acceptance criteria.**
- AC1 WHEN `--modules` names no module THE SYSTEM SHALL exit 2 with `gate.py: --modules needs
  module names, as in a,b, or all`, running nothing.
- AC2 WHEN a named module's test command is blank THE SYSTEM SHALL exit 2 with `gate.py: module
  <name> has no test command in docs/goals/modules.json`, running nothing, writing no receipt.
- AC3 WHEN a test calls `gate.run` in-process THE SYSTEM SHALL leave no file unclosed.
- AC4 WHEN `goal.py cleanup` runs THE SYSTEM SHALL fetch `origin` with `--prune` and list for
  removal each worktree, but the main and the current one, whose commit is in `origin/main` and
  whose changes are none or already there, and each local branch whose tip is in `origin/main`,
  but the default and the current branch; without `--apply` it SHALL remove nothing.
- AC5 WHEN an item has unmerged commits, changes not in `origin/main`, untracked files or a lock,
  or is the current or default branch, THE SYSTEM SHALL keep it and print why.
- AC6 WHEN `goal.py cleanup --apply` runs twice THE SYSTEM SHALL find nothing to remove the second
  time.
- AC7 WHEN the chief closes a milestone THE SKILL SHALL say: merge with `gh pr merge <n> --merge`,
  adding `--delete-branch` at the goal's last milestone; push the milestone tag; run `goal.py
  cleanup --apply`. D34 records it.
- AC8 WHEN T5 commits, `docs.py stale .` SHALL list no page.

**Non-goals.** Remote branches but the merged goal's; squash-merged branches (listed as
unmerged); other repositories.

**Constraints.** Standard library and `git` only; `gh` stays optional. Only what
`origin/main` already holds is removed.
