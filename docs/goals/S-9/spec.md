# S-9 spec: S-8's follow-ups, and the pilot's end

**Users and problem.** Chiefs on v7.3 repositories. Several things fail today:
- Appending a decision after the last protected one fails done row 4. The blank line before the
  new heading counts as part of the protected section, which S-8 hit.
- Cleanup without an `origin` quotes git's last stderr line, `and the repository exists.`.
- `gate.py`'s usage text omits its `--modules` refusals.
- Builder branches outlive their worktrees, and the approval tag stays local unless pushed by hand.
- The pilot's stop rule still reads as current, though S-3 and S-6 to S-8 put mechanism in
  `install/` after S-2.

**What changes for the user.**
- A new decision appends normally.
- The chief removes each builder's branch with its worktree.
- The close pushes the approval tag with the milestone tag.
- D35 ends the pilot and its stop rule.

**Acceptance criteria.**
- AC1 WHEN a commit appends a section after the last protected section, with a blank line before
  its heading, THE SYSTEM SHALL pass done row 4; a changed line inside a protected section SHALL
  still fail it.
- AC2 WHEN `goal.py cleanup` cannot fetch THE SYSTEM SHALL quote git's first `fatal:` line, and
  git's last stderr line only when no line starts `fatal:`.
- AC3 THE `gate.py` usage text SHALL say that `--modules` refuses an empty selection and a module
  with a blank test command.
- AC4 THE skill SHALL say to remove a builder's worktree and branch after its task's commit, and
  to push `goal/<id>/approved` with `goal/<id>/<milestone>` at the close.
- AC5 THE decisions record SHALL hold D35: the pilot and D29's stop rule have ended, and changes
  to `install/` are ordinary goals the founder approves. D29's table row SHALL name D35.
- AC6 `methodology.md` SHALL state the stop rule only as ended rationale, and
  `repository-standard.md` SHALL call `docs/goals/modules.json` a current-state file. WHEN T4 has
  committed, `docs.py stale .` SHALL list no page.

**Non-goals.**
- Any automatic revert trigger in place of the stop rule.
- Teaching `cleanup` to judge a builder's worktree against task commits.
- The frozen S-8 design's wording.

**Constraints.** Standard library and `git`. The always-loaded files stay within 1,350 words.
