---
id: F-5
title: Folder routes and graph-backed context for goal runs
prd: docs/product/README.md
status: approved
updated: 2026-10-08
milestone: M1
edge_cases: [first-run, unmigrated-project, harness-switch]
---

# F-5 — Folder routes and graph-backed context for goal runs

## Why

graphify is installed for both harnesses on the founder's machine, but goal runs do not use it.

- **No setup.** Nothing in methodology setup builds a project's graph or installs its refresh
  hooks. Whether a worktree has a usable graph depends on what someone ran by hand. Only the
  session preflight lists graphify, as an optional tool.
- **A hook can build a partial graph.** graphify's post-commit hook does not check that a graph
  exists. In a worktree without one, a commit creates a graph that holds only the changed files
  and records HEAD as its commit, so it looks current while `affected` misses most of the code.
  This was verified on 2026-10-08 with graphify 0.8.49 and git 2.54. The same run confirmed that
  refreshes stay in their own worktree: graphs are untracked, and git runs hooks from the
  committing worktree's root.
- **Codex has no graph hooks.** Claude Code gets the graphify lessons hook and the query advisor.
  The installer gives Codex only the goal hooks.
- **The methodology never uses the graph.** The execution methodology and the personas do not
  mention it. The chief builds packets by reading and grepping.
- **Folder routes are checked for existence, not for truth.** Each source folder has a scoped
  `AGENTS.md`/`CLAUDE.md` that routes to an area guide, and `validate_disclosure.py` warns when one
  is missing or too long. Nothing notices when a folder's code moves on and its area guide still
  describes the old code. Goal runs do not put these files in front of builders or judges, and
  Codex sessions do not run `disclosure-check.sh` at all.

F-3 shows what that costs. A correction builder removed a `core.hooksPath` skip whose reason it
did not know, and M4 acceptance caught the regression in two rounds.

A dependency view of the code a task touches (`graphify affected`, `graphify explain`) is the
input that tells a packet's author what else relies on that code. F-4's Keep list then states why.

## Outcome

- Graph setup is part of methodology setup. Migration and every goal start, in either harness,
  leave this worktree with a code graph and guarded refresh hooks where git runs them, or print
  one line saying what is missing and the command that finishes it by hand.
- Each worktree keeps its own graph. Git hooks refresh only an existing graph at the worktree
  root, never create one, and never touch another worktree's graph.
- Folder routes stay true. A task that changes what a folder's area guide says updates the guide in
  the same commit, and a guide that falls behind its folder's code is reported.
- A packet's context starts at the route, from the folder's entry file to its area guide, and
  adds the graph's dependency view where a current graph exists.
- Where a current graph exists, task packets and acceptance carry its dependency view.
- Where it does not, nothing changes. graphify stays optional to the core.

## Actors

- **Founder:** installed graphify, and decides per project whether to build an LLM-backed graph
  (`/graphify`).
- **Chief:** runs graph setup at goal start, refreshes a stale graph before use, and puts graph
  output into packets.
- **Builders:** read the paths in their packet.
- **Judges:** read the dependency view the chief attaches. They never run graphify themselves.

## Journeys

1. **Setup, at migration and at every goal start.** The chief runs `graph_view.py setup`. With
   graphify on PATH, it:
   - builds this worktree's code graph with `graphify update .` (code only, no LLM) when no graph
     exists at the worktree root or under a child directory;
   - installs the guarded refresh hooks, touching only `post-commit` and `post-checkout`, when they
     are missing where git runs hooks and `core.hooksPath` is unset. From a linked worktree, it
     installs them in the main checkout, whose hooks directory the worktrees share;
   - when `core.hooksPath` is configured, says that hooks will not refresh the graph and that
     `graph_view.py` refreshes it before each use.

   Without graphify, it prints one line and does nothing else. It never blocks the goal start.
   Between goal starts, nothing checks per session: `graph_view.py` refreshes a stale graph before
   every use.
2. **Dispatch.** For each folder in the task's writes, the packet lists the nearest scoped
   entry file and the area guide it routes to, as paths. This happens with or without a graph.
   If one of those guides is reported behind its folder's code, the chief first confirms it
   against the code, or the graph's `explain` output, and adds it to the task's update list.
3. **Dispatch with a graph.** Before writing a packet, the chief checks the graph:
   - if it is stale, the chief runs `graphify update .`, which needs no LLM;
   - for the symbols the task or correction changes, the chief runs `graphify explain` and
     `graphify affected` and saves the output under `.runs/<goal>/context/`;
   - the packet passes those paths, and the dependents seed F-4's Keep list.
4. **Dispatch without a graph.** The route as above, then the chief reads and greps.
5. **Update.** A task that changes a folder's layout, commands, interfaces or invariants
   updates that folder's area guide in the same commit. A task that adds a source folder adds
   its scoped entry pair. The plan puts those files in the task's `writes`.
6. **Acceptance with a graph.** The chief saves `affected` output for the milestone's changed
   symbols and names that file in the acceptance note. The judge reads it.

## Acceptance criteria

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | `graph-navigation/scripts/graph_view.py setup` does Journey 1. With graphify on PATH it always runs `graphify update <graph root>` (the worktree root when there is no graph), so it never trusts a graph an older unguarded hook may have left partial, under an in-process 600-second bound; on timeout it prints `graph build timed out after 600 s; build by hand with: graphify update .` and continues. When `post-commit` in `git rev-parse --git-path hooks` lacks `# graph-guard-start` before `# graphify-hook-start` and `core.hooksPath` is unset, it runs `install_hooks.py --graph-only <main checkout>` (the parent of `git rev-parse --git-common-dir`), which writes only the graph blocks and their guards. With `core.hooksPath` configured, it prints the manual-refresh line; without graphify, one line. Its git queries drop the repository-location `GIT_*` variables and `GIT_CONFIG` and keep git's other config variables. Every graphify call it and `view` make drops every inherited `GRAPHIFY_*` variable, so graphify writes only the default `graphify-out/` under the graph root. It exits 0 in every case. `references/run.md`'s Starting steps and `references/migrate.md`'s step 4 run it. No SessionStart hook reports graph status. | `test_graph_view.py`; `test_install_hooks_*.py`; e2e |
| AC-2 | `install.sh` registers `disclosure-check.sh`, the existing `graphify-session-lessons.sh` and the query advisor for Codex as it does for Claude Code. The advisor is registered for Codex without a matcher, as Codex's PreToolUse hooks are, and ignores payloads that carry no shell command. The installer tests cover both harnesses, and a real-harness smoke shows each hook's output reaching a Claude Code session and a Codex session. | `install/tests`; e2e |
| AC-3 | The route steps hold on every run. `references/run.md`'s dispatch step lists the scoped entry files and area guides for the task's folders, word-neutrally. `references/review.md`'s acceptance names the guides for touched folders. The graph steps of Journeys 3 and 6 live in a new `references/context.md`, which is loaded only when a graph exists. Those steps call graphify only through `graph-navigation/scripts/graph_view.py`. It enforces a 120-second bound on `update` and a 60-second bound on each `explain` and `affected` in-process, the same in both harnesses, and on timeout falls back to the route and grep. `test_graph_view.py` proves the bounds and the fallback. | `test_graph_view.py`; full gate; acceptance review |
| AC-4 | `docs/product/measurements.md` records the following, dated, on this repository in a temporary copy: the `graphify update` wall time, the node and edge counts, and the size of `affected` output for three symbols. `lean-execution.md` and `decisions.md` state the graph's role as current state. | full gate; acceptance review |
| AC-5 | The size budgets in `install/tests/test_size.py` hold, with `progressive-disclosure`'s AC-13 ceiling raised from 5,470 to 5,520 non-test lines by founder decision (2026-10-08), and the repository gate passes. | full gate |
| AC-6 | `validate_disclosure.py` reports `stale-guide` (WARN) for an area guide whose folder has commits to non-doc files after the guide's last commit. The report names the guide, the folder and the commit count. `disclosure-check.sh` surfaces it at session start, and both run for Codex as for Claude Code. `references/run.md` makes the route the first part of every packet's context, and `references/review.md` has the acceptance note name the guides for touched folders. `references/planning.md` puts a folder's area guide in the `writes` of any task that changes what the guide states. | `test_validate_disclosure*.py`; `install/tests`; full gate |
| AC-7 | F-3 M4's guard (`# graph-guard-start`, written by `install_hooks.py` before each graphify block, and added to existing unguarded blocks) keeps a hook from creating a graph or refreshing one outside the worktree root. F-5 adds: with graphify on PATH and `core.hooksPath` unset, the installer installs the guarded blocks whether or not the main checkout has a graph, so setup works from any worktree; and `--graph-only` runs only that graph step, leaving every other hook untouched. A smoke with real git and real graphify shows that setup builds a linked worktree's graph and that a commit in another worktree leaves it unchanged. F-3's checked-path writes, sandbox render, unset-only rule (with `GIT_CONFIG` dropped) and child-graph skip are unchanged. | `test_install_hooks_scope.py`, `test_install_hooks_worktrees.py`; e2e |

## Non-goals

- Building an LLM-backed graph automatically, or committing any graph: D11 keeps graphs
  uncommitted. Setup builds only the code graph, which needs no LLM, and only at migration or goal
  start. AC-7's guard keeps git hooks from creating a graph at all.
- A per-session status check. Setup belongs to methodology setup (founder, 2026-10-08), and
  `graph_view.py` refreshes a stale graph before every use.
- Refreshing a graph that is not at the worktree root from a hook: a child-directory graph, or one
  redirected by `.graphify_root`, is refreshed by hand or by `graph_view.py`.
- Keeping per-worktree graph state, or key-symbol lines, in folder `.md` files. Area guides stay
  route and intent.
- Running graphify's own platform installers (`graphify install`, `graphify claude install`),
  which write into harness configuration and `CLAUDE.md`.
- Giving judges a shell or graphify access. They read what the chief attaches.
- Semantic, LLM-backed rebuilds of documentation in the run loop. `graphify-session-lessons.sh`
  and `disclosure-check.sh` keep reporting what they report today.
- Measuring a private product repository. That is the founder's to run, and the record stays
  anonymous.
- Changing our own hooks under `core.hooksPath` (F-3 Queue Q7).
- Generating area guides from the graph. A guide states intent and invariants, which a graph
  cannot supply; the graph only helps the chief check a guide against the code.
- Turning `stale-guide` into an error. A guide can be right while its folder's code changes.

## Non-functional constraints

- Python 3.10+, standard library only. Every graphify call is optional, bounded by a timeout,
  and fails to the no-graph path with one line.
- Without a graph, every role's load stays within the 3,000-word budget, with F-4's additions.
- With a graph, the dispatching or accepting chief also loads `context.md`, at most 450 words, for
  about 3,450 words in all. This exception is approved here, and it is paid only when a graph
  exists.
