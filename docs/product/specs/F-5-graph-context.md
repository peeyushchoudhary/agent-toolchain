---
id: F-5
title: Folder routes and graph-backed context for goal runs
prd: docs/product/README.md
status: draft
updated: 2026-10-08
milestone: M1
edge_cases: [first-run, unmigrated-project, harness-switch]
---

# F-5 — Folder routes and graph-backed context for goal runs

## Why

graphify is installed for both harnesses on the founder's machine, but goal runs do not use it.

- **No status.** Nothing reports, per project, whether a graph exists, whether it is current, or
  whether its refresh hooks are where git runs hooks. Only the session preflight lists graphify,
  as an optional tool.
- **A hook can build a partial graph.** graphify's post-commit hook does not check that a graph
  exists. In a worktree without one, a commit creates a graph that holds only the changed files
  and records HEAD as its commit, so it looks current while `affected` misses most of the code.
  This was verified on 2026-10-08 with graphify 0.8.49 and git 2.54. The same run confirmed that
  refreshes stay in their own worktree: graphs are untracked, and git runs hooks from the
  committing worktree's root.
- **Codex has no graph hooks.** Claude Code gets the graphify session hook and the query advisor.
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

- In every session, in either harness, the agent knows whether this worktree has a usable graph
  and, if not, the one command that fixes it.
- Each worktree keeps its own graph. Git hooks refresh only an existing graph at the worktree
  root, never create one, and never touch another worktree's graph.
- Folder routes stay true. A task that changes what a folder's area guide says updates the guide in
  the same commit, and a guide that falls behind its folder's code is reported.
- A packet's context starts at the route, from the folder's entry file to its area guide, and
  adds the graph's dependency view where a current graph exists.
- Where a current graph exists, task packets and acceptance carry its dependency view.
- Where it does not, nothing changes. graphify stays optional to the core.

## Actors

- **Founder:** installed graphify, and decides per project whether to build a graph.
- **Chief:** refreshes a stale graph and puts graph output into packets.
- **Builders:** read the paths in their packet.
- **Judges:** read the dependency view the chief attaches. They never run graphify themselves.

## Journeys

1. **Session start, either harness.** The session hook reports at most one line per problem:
   - graphify is missing although the project has a graph, with the install command
     (`uv tool install graphifyy`, or `pipx install graphifyy`);
   - the graph is behind HEAD, with the count of changed code files and `graphify update .`;
   - the graph's refresh hooks are missing or unguarded, with `install_hooks.py <main checkout>`
     when `core.hooksPath` is unset. That command works from any worktree. When `core.hooksPath`
     is configured, the installer cannot place the hooks (F-3 Q7), so the line says so and gives
     the manual refresh, `graphify update .`;
   - graphify is installed but this worktree has no graph, with `graphify update .` (code only,
     no LLM), and `/graphify` named as the LLM-cost option that adds docs.

   The hooks lines apply to a graph at the worktree root. They also report hooks installed
   before the guard as unguarded, so existing installs get the fix.

   With a current graph and its hooks in place, the hook prints only the lessons digest, as today.
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
| AC-1 | `install/hooks/graphify-session.py` replaces `graphify-session-lessons.sh` and keeps its lessons digest. It reports the conditions in Journey 1, each as one line with its fixing command, and says "this worktree" because each worktree's graph is its own. It reads `built_at_commit` from `graph.json`, and locates the hooks with `git rev-parse --git-path hooks`, which in a linked worktree is the shared hooks directory. Hooks without the AC-7 guard count as unguarded. Its fix command names the main checkout. It drops repository-location `GIT_*` variables and `GIT_CONFIG`, which only `git config` reads, and keeps git's other config-environment variables. It writes nothing outside `graphify-out/`, and that only through `graphify reflect --if-stale`, as today. It never blocks and exits 0 on any error. | `test_graphify_session.py` |
| AC-2 | `install.sh` registers the graphify session hook, `disclosure-check.sh` and the query advisor for Codex as it does for Claude Code. The advisor is registered for Codex without a matcher, as Codex's PreToolUse hooks are, and ignores payloads that carry no shell command. `install.sh` retires `graphify-session-lessons.sh`. The installer tests cover both harnesses, and a real-harness smoke shows each hook's output reaching a Claude Code session and a Codex session. | `install/tests`; e2e |
| AC-3 | The route steps hold on every run. `references/run.md`'s dispatch step lists the scoped entry files and area guides for the task's folders, word-neutrally. `references/review.md`'s acceptance names the guides for touched folders. The graph steps of Journeys 3 and 6 live in a new `references/context.md`, which is loaded only when a graph exists. Those steps call graphify only through `graph-navigation/scripts/graph_view.py`. It enforces a 120-second bound on `update` and a 60-second bound on each `explain` and `affected` in-process, the same in both harnesses, and on timeout falls back to the route and grep. `test_graph_view.py` proves the bounds and the fallback. | `test_graph_view.py`; full gate; acceptance review |
| AC-4 | `docs/product/measurements.md` records the following, dated, on this repository in a temporary copy: the `graphify update` wall time, the node and edge counts, and the size of `affected` output for three symbols. `lean-execution.md` and `decisions.md` state the graph's role as current state. | full gate; acceptance review |
| AC-5 | The size budgets in `install/tests/test_size.py` hold, and the repository gate passes. | full gate |
| AC-6 | `validate_disclosure.py` reports `stale-guide` (WARN) for an area guide whose folder has commits to non-doc files after the guide's last commit. The report names the guide, the folder and the commit count. `disclosure-check.sh` surfaces it at session start, and both run for Codex as for Claude Code. `references/run.md` makes the route the first part of every packet's context, and `references/review.md` has the acceptance note name the guides for touched folders. `references/planning.md` puts a folder's area guide in the `writes` of any task that changes what the guide states. | `test_validate_disclosure*.py`; `install/tests`; full gate |
| AC-7 | F-3 M4's guard (`# graph-guard-start`, written by `install_hooks.py` before each graphify block, and added to existing unguarded blocks) keeps a hook from creating a graph or refreshing one outside the worktree root. F-5 adds: with graphify on PATH and `core.hooksPath` unset, the installer installs the guarded blocks whether or not the main checkout has a graph, so the install command printed in any worktree works. A test with real git shows a commit in one worktree leaves every other worktree's graph and the main checkout's unchanged. F-3's checked-path writes, sandbox render, unset-only rule (with `GIT_CONFIG` dropped) and child-graph skip are unchanged. | `test_install_hooks_scope.py`, `test_install_hooks_worktrees.py`; e2e |

## Non-goals

- Building a graph automatically, or committing one: D11 keeps graphs uncommitted. AC-7's guard
  extends this to git hooks: only an explicit `graphify update .` creates a graph.
- Refreshing a graph that is not at the worktree root from a hook: a child-directory graph, or one
  redirected by `.graphify_root`, is refreshed by hand or by `graph_view.py`.
- Keeping per-worktree graph state, or key-symbol lines, in folder `.md` files. Area guides stay
  route and intent.
- Running graphify's own platform installers (`graphify install`, `graphify claude install`),
  which write into harness configuration and `CLAUDE.md`.
- Giving judges a shell or graphify access. They read what the chief attaches.
- Semantic, LLM-backed rebuilds of documentation in the run loop. The session hook keeps
  reporting stale docs, as `disclosure-check.sh` does today.
- Measuring a private product repository. That is the founder's to run, and the record stays
  anonymous.
- Changing our own hooks under `core.hooksPath` (F-3 Queue Q7).
- Generating area guides from the graph. A guide states intent and invariants, which a graph
  cannot supply; the graph only helps the chief check a guide against the code.
- Turning `stale-guide` into an error. A guide can be right while its folder's code changes.

## Non-functional constraints

- Python 3.10+, standard library only. Every graphify call is optional, bounded by a timeout,
  and fails silently to the no-graph path.
- Without a graph, every role's load stays within the 3,000-word budget, with F-4's additions.
- With a graph, the dispatching or accepting chief also loads `context.md`, at most 450 words, for
  about 3,450 words in all. This exception is approved here, and it is paid only when a graph
  exists.
