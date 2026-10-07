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

- In every session, in either harness, the agent knows whether the project has a usable graph
  and, if not, the one command that fixes it.
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
   - graphify is missing although the project has a graph;
   - the graph is behind HEAD, with the count of changed code files and `graphify update .`;
   - the graph's refresh hooks are missing where git runs hooks, with `install_hooks.py .`;
   - graphify is installed but the project has no graph, with the build command.

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
| AC-1 | `install/hooks/graphify-session.py` replaces `graphify-session-lessons.sh` and keeps its lessons digest. It reports the four conditions in Journey 1, each as one line with its fixing command. It reads `built_at_commit` from `graph.json`, locates the hooks with `git rev-parse --git-path hooks`, and runs with no inherited `GIT_*` variables. It writes nothing outside `graphify-out/`, and that only through `graphify reflect --if-stale`, as today. It never blocks and exits 0 on any error. | `test_graphify_session.py` |
| AC-2 | `install.sh` registers the graphify session hook and the query advisor for Codex as it does for Claude Code, retires `graphify-session-lessons.sh`, and the installer tests cover both harnesses. | `install/tests` |
| AC-3 | A new `references/context.md` holds the route- and graph-backed dispatch, update and acceptance steps of Journeys 2–6. `references/run.md` points to it from its dispatch step, word-neutrally. | full gate; acceptance review |
| AC-4 | `docs/product/measurements.md` records the following, dated, on this repository in a temporary copy: the `graphify update` wall time, the node and edge counts, and the size of `affected` output for three symbols. `lean-execution.md` and `decisions.md` state the graph's role as current state. | full gate; acceptance review |
| AC-5 | The size budgets in `install/tests/test_size.py` hold, and the repository gate passes. | full gate |
| AC-6 | `validate_disclosure.py` reports `stale-guide` (WARN) for an area guide whose folder has commits to non-doc files after the guide's last commit. The report names the guide, the folder and the commit count. `disclosure-check.sh` surfaces it at session start, and both run for Codex as for Claude Code. `references/context.md` makes the route the first part of every packet's context, and the acceptance note names the guides for touched folders. `references/planning.md` puts a folder's area guide in the `writes` of any task that changes what the guide states. | `test_validate_disclosure*.py`; `install/tests`; full gate |

## Non-goals

- Building a graph automatically, or committing one: D11 keeps graphs uncommitted.
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
- `run.md` stays within the 3,000-word role-load budget together with F-4's additions.
