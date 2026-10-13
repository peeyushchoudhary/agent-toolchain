# S-8 spec: post-merge cleanup, and S-7's four follow-ups

**Users and problem.** Chiefs on v7.3 repositories. Nothing removes what a merged milestone left:
one project holds 9 builder worktrees and 14 merged branches. S-7 left four follow-ups: `gate.py`
runs a module whose test command is blank; `--modules ""` prints `no module  in`; a `gate.run`
test prints a ResourceWarning; three pages fail `docs.py stale`.

**What changes for the user.** After a milestone merges, `goal.py cleanup --goal <id>` lists the
worktrees and branches that milestone created whose work `origin/main` holds; `--apply` removes
them. Other sessions' worktrees are never touched. The goal's last merge also deletes the remote
branch. Two refusals read plainly, and the pages are current.

**Acceptance criteria.**
- AC1 WHEN `--modules` names no module THE SYSTEM SHALL exit 2 with `gate.py: --modules needs
  module names, as in a,b, or all`, running nothing.
- AC2 WHEN a named module's test command is blank THE SYSTEM SHALL exit 2 with `gate.py: module
  <name> has no test command in docs/goals/modules.json`, running nothing, writing no receipt.
- AC3 WHEN a test calls `gate.run` THE SYSTEM SHALL leave no file unclosed.
- AC4 WHEN `goal.py cleanup --goal <id>` runs THE SYSTEM SHALL list for removal only worktrees at
  a commit of the milestone (after the previous milestone's tag, or from the approval tag, up to
  the milestone's tag) with no changes or changes already in `origin/main`, the branches they had
  checked out, and at the goal's last milestone the goal branch; it SHALL touch nothing else, and
  without `--apply` remove nothing.
- AC5 WHEN a milestone's item has changes not in `origin/main`, untracked files or a lock, or is
  the current branch, THE SYSTEM SHALL keep it and print why; WHEN the milestone's tag is not in
  `origin/main` it SHALL refuse with exit 2.
- AC6 WHEN `goal.py cleanup --apply` runs twice THE SYSTEM SHALL find nothing to remove the second
  time.
- AC7 WHEN the chief closes a milestone THE SKILL SHALL say: merge with `gh pr merge <n> --merge`,
  adding `--delete-branch` at the goal's last milestone; push the milestone tag; run `goal.py
  cleanup --goal <id> --apply`. D34 records it.
- AC8 WHEN T5 commits, `docs.py stale .` SHALL list no page.

**Non-goals.** Leftovers of earlier goals or other sessions; remote branches but the merged
goal's; squash merges; other repositories.

**Constraints.** Standard library and `git`; `gh` stays optional. Only what `origin/main`
holds is removed.
