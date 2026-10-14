---
summary: How to bring a product repository to the layout the skill's `references/repository.md` sets, by hand on a branch at a milestone boundary: check every reader of a path first, move still-read content out of tool folders, untrack tool output, keep one home per kind with archive rows for copied history, drop retired tooling, add the `CLAUDE.md` twins and the gate line, rewrite the README to its seven sections, then add `docs.py links` and run the gate in a fresh worktree. The rollback, which keeps what was untracked.
read-when: Migrating a product repository to the repository rules, or untracking or archiving paths in one
covers: []
last-verified: 2026-10-14
---

# Migrating a repository's layout

Migrate one product repository at a time, at a milestone boundary, on a branch, following the
Lifecycle rules of the skill's
[references/repository.md](../../install/skills/execution-methodology/references/repository.md#lifecycle):

1. **Readers first.** For each path to move, archive or untrack, `git grep -n` its path, its
   directory and its basename across all tracked files, Markdown included, and run `docs.py links`.
   A path something reads or cites stays, unless every reader is repointed in the same commit.
   Code, build roots, records and domain content are never moved or renamed.
2. **Move the content.** Move whatever a tool folder holds that is still read into its home,
   repointing its readers, and delete the `!` re-include for it.
3. **Untrack tool output.** Add it to `.gitignore`, then `git rm -r --cached` it.
4. **One home per kind.** Bring each kind to one home, keeping the home already cited.
   - Replace copied history with one row in `docs/archive/README.md` naming a commit or tag pushed
     to `origin`.
   - Before deleting the copy, confirm `git cat-file -e <ref>:<path>` for each path.
5. **Retired tooling.** Drop gate steps, Make targets, PR-template lines and tracked hooks that call
   or name tools the skill no longer installs.
6. **Agent files.** Add each missing `CLAUDE.md` twin, and move the gate into the root
   `AGENTS.md`'s first 15 lines.
7. **The README.** Rewrite `README.md` to the seven sections, with its `covers` comment.
8. **Verify.**
   - Add `docs.py links` to the gate, and commit.
   - Run the full gate in a fresh worktree of that commit (`git worktree add --detach <dir>
     HEAD`), not in the working tree, where untracked files still sit on disk.
   - Run `docs.py lint`, `docs.py links` and `docs.py stale` there too.

Rollback: copy the untracked paths aside, `git revert` the migration, then restore them.
