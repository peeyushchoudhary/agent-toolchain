---
id: F-5
title: Folder routes and graph-backed context for goal runs
prd: docs/product/README.md
status: draft
updated: 2026-10-08
milestone: M1
edge_cases: [first-run, unmigrated-project, harness-switch, partial-graph, stale-graph, unknown-build-commit, diverged-build-commit, concurrent-refresh, failed-build-after-stamp, shrinking-rebuild, timeout, unignored-graph, symlinked-artifact]
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
  adds the graph's dependency view where a graph exists.
- Where a graph exists, task packets and acceptance carry its dependency view as advisory
  context. Each view states how far the graph is behind HEAD, and the agent confirms what it uses
  with grep or by reading the code. F-5 never claims a graph is complete or current.
- Where no graph exists, nothing changes. graphify stays optional to the core.

## Actors

- **Founder:** installed graphify, and decides per project whether to build an LLM-backed graph
  (`/graphify`).
- **Chief:** runs graph setup at goal start, refreshes the graph when it chooses to, and puts
  labelled graph output into packets.
- **Builders:** read the paths in their packet.
- **Judges:** read the dependency view the chief attaches. They never run graphify themselves.

## Journeys

1. **Setup, at migration and at every goal start.** The chief runs `graph_view.py setup`. With
   graphify on PATH, it:
   - **Hooks.** When the guarded refresh hooks are missing where git runs hooks and
     `core.hooksPath` is unset, it installs them, touching only `post-commit` and `post-checkout`.
     From a linked worktree, it installs them in the main checkout, whose hooks directory the
     worktrees share. When `core.hooksPath` is configured, it says that hooks will not refresh the
     graph and that `graph_view.py view --refresh` refreshes it on request. Hooks keep the graph
     roughly current; they are not evidence of anything.
   - **Ignore.** When the graph directory is not ignored by git, it names the `.gitignore` entry
     to add and writes nothing under it.
   - **Build once per checkout.** It runs a full `graphify update . --force` from the graph root,
     code only and with no LLM, when there is no graph, the graph does not parse, its
     `.graphify_root` is neither absent nor `.`, or setup has not yet recorded a full build of it.
     Otherwise it builds nothing, however far behind HEAD the graph is. It claims nothing about
     the graph's completeness. A build that fails leaves no record of a full build, so the next
     setup builds again, and every failure prints one retry command for this same checkout. When
     the graph directory or anything directly in it is a symlink, it names the path and builds
     nothing, so a build cannot write through it into a tracked file.

   Without graphify, it prints one line and does nothing else. It never blocks the goal start.
   Between goal starts, nothing checks per session. The project ignores `graphify-out/`;
   migration adds that line to its `.gitignore`, and setup names the missing entry and builds
   nothing until it is there.
2. **Dispatch.** For each folder in the task's writes, the packet lists the nearest scoped
   entry file and the area guide it routes to, as paths. This happens with or without a graph.
   If one of those guides is reported behind its folder's code, the chief first confirms it
   against the code, or the graph's `explain` output, and adds it to the task's update list.
3. **Dispatch with a graph.** Before writing a packet, the chief runs `graph_view.py view`:
   - for the symbols the task or correction changes, it runs `graphify explain` and
     `graphify affected` and saves the output under `.runs/<goal>/context/`, each file headed by
     a label saying when the graph was built, how many commits it is behind HEAD (and ahead, when
     it is), and that it is advisory;
   - it never rebuilds on its own; the chief adds `--refresh` when the label shows the graph too
     far behind to be useful, which runs a full build that needs no LLM;
   - the packet passes those paths, and the dependents seed F-4's Keep list as candidates. The
     chief and the builder confirm each one with grep or by reading the code before relying on
     it.
4. **Dispatch without a graph.** The route as above, then the chief reads and greps.
5. **Update.** A task that changes a folder's layout, commands, interfaces or invariants
   updates that folder's area guide in the same commit. A task that adds a source folder adds
   its scoped entry pair. The plan puts those files in the task's `writes`.
6. **Acceptance with a graph.** The chief saves `affected` output for the milestone's changed
   symbols and names that file in the acceptance note. The judge reads it as advisory, under its
   label, and checks what it relies on against the code.

## Acceptance criteria

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | `graph-navigation/scripts/graph_view.py setup` does Journey 1. With graphify on PATH, `core.hooksPath` unset and the graph not under a child directory, when `post-commit` or `post-checkout` in `git rev-parse --git-path hooks` lacks `# graph-guard-start` immediately before `# graphify-hook-start`, it runs `install_hooks.py --graph-only <main checkout>` (the parent of `git rev-parse --git-common-dir`), which writes only the graph blocks and their guards. With `core.hooksPath` configured, it prints the manual-refresh line and installs nothing. The guard keeps hooks refreshing the graph and plays no part in any claim. When `git check-ignore -q <graph root>/graphify-out/`, run with the same dropped `GIT_*` variables, does not exit 0, it prints `graphify-out/ is not ignored; add /<graph root>/graphify-out/ to .gitignore, then rerun: <rerun>` (`/graphify-out/` for the worktree root), writes nothing under that directory and exits 0; adding that entry clears the line. Otherwise it runs `graphify update . --force` from the graph root (the worktree root when there is no graph), under an in-process 600-second bound, only when there is no graph, `graph.json` does not parse, `.graphify_root` is neither absent nor exactly `.`, or the stamp `graphify-out/.graph_view_complete` is missing or does not parse. In every other case it builds nothing, however far behind HEAD the graph is, and prints `graph ready`. Before any build, it refuses when `graphify-out/` or any entry directly inside it is a symlink (checked with `lstat`), printing `graph build refused: <path> is a symlink; remove it, then rerun: <rerun>`, building and deleting nothing and leaving the symlink's target unchanged. Otherwise it deletes the stamp before the build, and after the build exits 0 within the bound it writes a new stamp as `{"head": <HEAD's full commit id>, "sha256": <hex of graph.json's bytes>}`, a record of the last full build and not a trust signal; a timeout or failure therefore always leaves no stamp, and the next setup builds. On a timeout or a nonzero exit it prints the one failure line, `graph build <reason>; retry with: <rerun> --no-bound`, where `<reason>` is `timed out after 600 s` or `failed (exit <n>)`, and continues. `<rerun>` is `python3 <graph_view.py> setup --root <worktree>`, with the script's absolute path, the absolute worktree root even when `--root` was defaulted, and the invocation's other arguments. Running the printed command builds without the bound and writes the stamp, after which setup prints `graph ready`. Nothing setup prints claims the graph is complete or current. Without graphify, one line. Its git queries drop the repository-location `GIT_*` variables and `GIT_CONFIG` and keep git's other config variables. Every graphify call it and `view` make runs with its cwd at the graph root and `.` as its path argument, and drops every inherited `GRAPHIFY_*` variable, so the only output location graphify is given is the default `graphify-out/` under the graph root, and the path it records in `.graphify_root` is `.`. Which nodes a forced build keeps is graphify's behaviour, which the oracle test records and F-5 does not guarantee. It exits 0 in every case. `references/run.md`'s Starting steps and `references/migrate.md`'s step 4 run it, and step 4 adds `/graphify-out/` to the project's `.gitignore` next to `/.runs/`. This repository's `.gitignore` ignores `/graphify-out/`. No SessionStart hook reports graph status. | `test_graph_view.py`, with its oracle test against real graphify; `test_install_hooks_*.py`; e2e |
| AC-2 | `install.sh` registers `disclosure-check.sh`, the existing `graphify-session-lessons.sh` and the query advisor for Codex as it does for Claude Code. The advisor is registered for Codex without a matcher, as Codex's PreToolUse hooks are, and ignores payloads that carry no shell command. The installer tests cover both harnesses, and a real-harness smoke shows each hook's output reaching a Claude Code session and a Codex session. | `install/tests`; e2e |
| AC-3 | The route steps hold on every run. `references/run.md`'s dispatch step lists the scoped entry files and area guides for the task's folders, word-neutrally. `references/review.md`'s acceptance names the guides for touched folders. The graph steps of Journeys 3 and 6 live in a new `references/context.md`, which is loaded only when a graph exists and says that graph output is advisory and is checked against the code before it is relied on. Those steps call graphify only through `graph-navigation/scripts/graph_view.py`. `view` never rebuilds on its own, however stale the graph. It first prints, and heads every output file with, the label `graph built at <short built_at_commit> (<B> commits behind HEAD, <A> ahead); advisory — confirm with grep`, where `<A>` and `<B>` are the left and right counts of `git rev-list --left-right --count <built_at_commit>...HEAD` and `, <A> ahead` is omitted when `<A>` is 0. When `built_at_commit` is missing or unknown to git, the label reads `graph build commit unknown; advisory — confirm with grep`. When the stamp's `head` is HEAD and its `sha256` matches the graph bytes `view` read, the label adds `full build by setup at HEAD`. `view` reads `graph.json` once, and the label and every `explain` and `affected` result come from those same bytes, so a graph replaced during the call changes neither. `view --refresh` first applies setup's symlink refusal and stamp deletion, then runs the same full forced build as setup, under a 120-second bound unless `--no-bound`, and writes the stamp after an exit 0; on a timeout or a nonzero exit it prints setup's failure line with `<reason>` `timed out after 120 s` or `failed (exit <n>)` and `<rerun>` `python3 <graph_view.py> view --root <worktree> --refresh` plus the invocation's `--out` and symbols, writes no stamp, and goes on with the existing graph. Without a graph, `view` prints its no-graph line. When the graph directory is not ignored, `view` prints setup's ignore line, writes nothing under it and falls back to its no-graph output. It enforces a 60-second bound on each `explain` and `affected` in-process, the same in both harnesses, and on timeout falls back to the route and grep. `test_graph_view.py` proves the labels (behind, ahead, diverged, unknown), the single read, the absence of an automatic rebuild, `--refresh`, the bounds, the failure line, the symlink refusal, the fallback and the ignore check. | `test_graph_view.py`; full gate; acceptance review |
| AC-4 | `docs/product/measurements.md` records the following, dated, on this repository in a temporary copy: the `graphify update` wall time, the node and edge counts, and the size of `affected` output for three symbols. It also records, dated and with repositories named only as small, medium or large, the cost of a full `graphify update` and of a freshness check, and the peak memory of the update. `lean-execution.md` and `decisions.md` state the graph's role as current state. | full gate; acceptance review |
| AC-5 | The size budgets in `install/tests/test_size.py` hold, with `progressive-disclosure`'s AC-13 ceiling raised from 5,470 to 5,520 non-test lines by founder decision (2026-10-08), and the repository gate passes. | full gate |
| AC-6 | `validate_disclosure.py` reports `stale-guide` (WARN) for an area guide whose folder has commits to non-doc files after the guide's last commit. The report names the guide, the folder and the commit count. `disclosure-check.sh` surfaces it at session start, and both run for Codex as for Claude Code. `references/run.md` makes the route the first part of every packet's context, and `references/review.md` has the acceptance note name the guides for touched folders. `references/planning.md` puts a folder's area guide in the `writes` of any task that changes what the guide states. | `test_validate_disclosure*.py`; `install/tests`; full gate |
| AC-7 | F-3 M4's guard (`# graph-guard-start`, written by `install_hooks.py` before each graphify block, and added to existing unguarded blocks) keeps a hook from creating a graph or refreshing one outside the worktree root. F-5 adds: with graphify on PATH and `core.hooksPath` unset, the installer installs the guarded blocks whether or not the main checkout has a graph, so setup works from any worktree; and `--graph-only` runs only that graph step, leaving every other hook untouched. A smoke with real git and real graphify shows that setup builds a linked worktree's graph and that a commit in another worktree leaves it unchanged. F-3's checked-path writes, sandbox render, unset-only rule (with `GIT_CONFIG` dropped) and child-graph skip are unchanged. | `test_install_hooks_scope.py`, `test_install_hooks_worktrees.py`; e2e |

## Non-goals

- Building an LLM-backed graph automatically, or committing any graph. This repository ignores
  `graphify-out/` wholesale, and migration adds the same ignore. D11's split, which commits
  `reflections/` and `memory/`, stays an option for a project that wants it. Setup builds only the
  code graph, which needs no LLM, and only at migration or goal start. AC-7's guard keeps git
  hooks from creating a graph at all.
- A per-session status check. Setup belongs to methodology setup (founder, 2026-10-08), and
  `view` labels how far behind the graph is at every use.
- Claiming a graph is complete or current. A skipped hook refresh leaves a gap that later
  refreshes never fill, and no state F-5 can read proves otherwise (founder, 2026-10-08). Graph
  output stays advisory.
- Rebuilding automatically before a use. `view` rebuilds only on `--refresh`.
- Refreshing a graph that is not at the worktree root from a hook: a child-directory graph, or one
  redirected by `.graphify_root`, is refreshed by hand or by `view --refresh`.
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
