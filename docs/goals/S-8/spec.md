# S-8 spec: post-merge cleanup, and S-7's four follow-ups

**Users and problem.** Chiefs on v7.3 repositories. Nothing removes what a merged milestone left:
one project holds 9 builder worktrees and 14 merged branches. S-7 left four follow-ups: `gate.py`
runs a module with a blank test command; `--modules ""` prints `no module  in`; a test prints a
ResourceWarning; three pages fail `docs.py stale`.

**What changes for the user.** The chief records each builder and sample worktree it uses with
`goal.py own`. After a merge, `goal.py cleanup --goal <id>` lists the recorded worktrees and
branches whose work `origin/main` holds; `--apply` removes them. Nothing unrecorded is touched. The
goal's last merge deletes its branch.

**Acceptance criteria.**
- AC1 WHEN `--modules` names no module THE SYSTEM SHALL exit 2 with `gate.py: --modules needs
  module names, as in a,b, or all`, running nothing.
- AC2 WHEN a named module's test command is blank THE SYSTEM SHALL exit 2 with `gate.py: module
  <name> has no test command in docs/goals/modules.json`, running nothing, writing no receipt.
- AC3 WHEN a test calls `gate.run` THE SYSTEM SHALL leave no file unclosed.
- AC4 WHEN `goal.py own --goal <id> <path>` names a linked worktree of the repository THE SYSTEM
  SHALL record its path and branch for the goal, and otherwise exit 2.
- AC5 WHEN `goal.py cleanup --goal <id>` runs THE SYSTEM SHALL fetch only `main` and list for
  removal each recorded worktree whose commit and staged changes `origin/main` holds, with its
  branch; it SHALL touch nothing unrecorded, and without `--apply` remove nothing.
- AC6 WHEN a recorded worktree is locked or holds untracked files, unstaged changes, submodules,
  or commits or staged changes not in `origin/main`, or its branch is current, THE SYSTEM SHALL
  keep it and print why; a second `--apply` SHALL find nothing new.
- AC7 THE SKILL SHALL say to run `goal.py own` on each builder's and sample's worktree, and at a
  milestone's close: merge with `gh pr merge <n> --merge`, adding `--delete-branch` at the goal's
  last milestone; push the milestone tag; run `goal.py cleanup --goal <id> --apply`. D34 records
  it.
- AC8 WHEN T5 has committed, `docs.py stale .` SHALL list no page.

**Non-goals.** Unrecorded leftovers, earlier goals' included; remote branches but the merged
goal's; repositories whose base branch is not `main`.

**Constraints.** Standard library and `git`; `gh` stays optional. Only what `origin/main` holds,
plus ignored files in a recorded worktree, is removed.
