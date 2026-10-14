# Repository rules

The rules every repository follows: its README, its layout, its agent files, and how a path moves
or retires. A repository's own layout page says how it applies them.

## The README

`README.md` is the front page for a human. It has seven sections, in this order, each heading
worded freely:

1. **Overview:** what it is and the problem, in a first sentence of at most 120 characters.
2. **Current state:** the stage and what this tree ships, with a link to `docs/goals/`.
3. **Product requirements:** a link table, never the PRD's text.
4. **Architecture:** a Mermaid diagram at system level, or a link to `docs/architecture/`.
5. **Components:** one row each, with its responsibility, entry point and page.
6. **Run locally:** from a fresh clone to a running system.
7. **Working in this repository:** agents read `AGENTS.md`; then the gate, and how work lands.

The README never states commit hashes, run IDs, goal or approval state, counts the code can
change, or the methodology version.

Its first line outside a fence that matches `<!-- covers: [<globs>] -->` names the
repository-relative paths it describes. Quoted globs keep their commas, and later matching lines are
ignored. `docs.py stale` warns when a covered path was committed after the README's own last
commit. A README without the line is never stale.

## Layout

- Code goes where the build file declares it. `docs/goals/modules.json` is drafted and kept as
  [modules.md](modules.md) says, its `count: "none"` module for the non-test checks included.
- New paths are lowercase with unique names, except goal ids and the names a tool or convention
  fixes (`README.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `Makefile`, build files), which keep
  their spelling. Existing names are never renamed.
- One home per kind: decisions in one record, in-flight work in `docs/goals/`, history in
  `docs/archive/`. Where a kind has two homes, the one already cited is kept.
- Tool output is a tool's working files and run state: a plugin's plans and specs, code-graph
  output, scratch workspaces, `.runs/`. It is never tracked. What it holds that is still read moves
  out first, and is never re-included with a `!` rule.
- Generated files a gate checks are not tool output and stay tracked, among them `docs.py`'s
  pointer files and generated types or schemas.

Every `docs/` page but the index and `docs/goals/**` starts:

```
---
summary: <at most 120 words>
read-when: <one line>
covers: [src/area/**]
last-verified: YYYY-MM-DD
---
```

**The product minimum.** A product repository needs less: `AGENTS.md`, `CLAUDE.md`,
`docs/product/prd.md` with at least its frontmatter `summary`, `docs/goals/<id>/spec.md` and
`plan.md` (with `design.md` unless `touches` is `none`), `/.runs/` in `.gitignore`, `docs.py lint`
and `docs.py links` in its gate, and the guard hooks from `git-hooks.sh`.

## Agent files

- `AGENTS.md` is authored. Every `AGENTS.md` has a sibling `CLAUDE.md` holding the line
  `@AGENTS.md`, which `docs.py links` checks.
- The root `AGENTS.md` names the gate within its first 15 lines.
- A tracked hook names only things that exist.
- A gate step calls only tooling the repository holds or the skill ships.

## Lifecycle

- **Records.** Decisions, measurements, goals and `docs/agents/lessons.md` are dated records, cited
  by anchor, that may name removed components as rationale. Every other page states what is true
  now. Records are never moved.
- **Finished goals.** A finished goal stays in place, and nothing is copied into it. Review output
  stays in `.runs/`.
- **Supersession** goes in a status cell, never in a rewrite of the text.
- **Archive entries.** An archive entry is one row in `docs/archive/README.md`, never a copy. The
  row names a commit or tag pushed to `origin` whose tree holds the removed content, which
  `git cat-file -e <ref>:<path>` confirms.
- **Moving or untracking a path.**
  1. First, `git grep` across all tracked files, Markdown included, for the path, its directory and
     its basename, and run `docs.py links`.
  2. A path something reads or cites stays, unless every reader is repointed in the same commit.
  3. Commit, then run the full gate in a fresh worktree of that commit (`git worktree add
     --detach`), never in the working tree, where an untracked file still sits on disk.
  4. Code and domain content are never moved.
- **Rollback after untracking.** Copy the untracked paths aside, `git revert`, then restore them.
