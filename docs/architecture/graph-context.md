---
id: F-5
title: Folder routes and graph-backed context for goal runs
spec: docs/product/specs/F-5-graph-context.md
status: draft
updated: 2026-10-08
---

# F-5 design — folder routes and graph-backed context

## Structure

| Concern | Owner | Change |
| --- | --- | --- |
| Graph setup | `graph-navigation/scripts/graph_view.py setup` (new), run by `references/run.md`'s Starting steps and `references/migrate.md`'s step 4 | builds this worktree's code graph when there is none, and installs the guarded refresh hooks where git runs them |
| Both harnesses | `install/install.sh` | Codex gets the existing `graphify-session-lessons.sh` and the query advisor |
| Stale area guides | `progressive-disclosure/scripts/validate_disclosure.py` | a new `stale-guide` WARN beside `unscoped-dir`, which runs at commit, in the gate and at session start |
| Codex route check | `install/install.sh` | Codex also gets `disclosure-check.sh` at SessionStart |
| Planning rule | `execution-methodology/references/planning.md` | a task that changes what a guide states writes the guide |
| Refresh hooks in git | `progressive-disclosure/scripts/install_hooks.py` (changed) | F-3 M4's guard stays; it installs without a graph in the main checkout, and `--graph-only` runs only the graph step |
| Bounded graph calls | `graph-navigation/scripts/graph_view.py view` (new) | one command for the chief in either harness: freshness, refresh, then `explain` and `affected`, each under an in-process timeout |
| Use in a goal run | `execution-methodology/references/context.md` (new), `references/run.md` (pointer) | the dispatch and acceptance steps |
| Records | `lean-execution.md`, `decisions.md`, `measurements.md` | current state, and the numbers |

graphify integration stays in our own hooks and skills. graphify's platform installers are not
used.

## Per-worktree graphs

Each worktree has its own graph. `graphify-out/` is untracked (D11), so every worktree, the main
checkout included, holds its own copy or none. All worktrees share one hooks directory, but git
runs a hook with its cwd at the root of the worktree that committed, and graphify's hook rebuilds
the cwd's `graphify-out/`. A refresh therefore touches only the committing worktree's graph.

This was verified on 2026-10-08 with graphify 0.8.49 and git 2.54, in a throwaway repository with
two linked worktrees. A commit in one worktree left the main checkout's graph and the other
worktree unchanged, and a commit in the main checkout left both worktrees unchanged.

The same run showed a hazard. graphify's post-commit hook does not check that a graph exists, and
its incremental rebuild creates `graphify-out/` when it is missing. A commit in a worktree without
a graph therefore produced a graph holding only the changed files, with `built_at_commit` equal to
HEAD. Such a graph passes the freshness check, and `affected` then silently misses most of the
code.

The fix narrows what a hook may do: **a hook refreshes only an existing, complete graph at the
worktree root.** Only an explicit `graphify update .` creates a graph, a full code build that
needs no LLM. F-3 M4's guard in `install_hooks.py`, below, enforces this, and it is what keeps a
graph complete, so the freshness check can trust `built_at_commit`.

**Setup instead of a status hook.** Graph setup is a step of methodology setup (founder,
2026-10-08): migration and every goal start run `graph_view.py setup`, which builds a missing
code graph and installs missing refresh hooks itself. Nothing checks per session. Drift between
goal starts (a stale graph, new commits) is handled where it matters, by `graph_view.py view`
refreshing a stale graph before every use.

## Interfaces

**`graph_view.py setup [--root <worktree>]`.** `--root` defaults to the git top level of the cwd.
Every git query runs with `cwd` at the worktree root, a timeout of 5 s, the repository-location
variables (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` and the like) dropped, and `GIT_CONFIG`
dropped, which only `git config` reads. git's other config-environment variables are kept, so the
query sees what a running git sees, matching `install_hooks.py`.

Steps, in order. Each prints at most one line:

| Step | Condition | Action, or line |
| --- | --- | --- |
| 1 | `graphify` not on PATH | `graphify not installed; graph context off (install with: uv tool install graphifyy)`; stop |
| 2 | no `graphify-out/graph.json` that parses, at the worktree root or under one child (the `install_hooks.graphify_root` rule, duplicated in about eight lines so `graph-navigation` stays independent of the skill) | run `graphify update .` under an in-process 600-second bound. On timeout: `graph build timed out after 600 s; build by hand with: graphify update .`, then continue |
| 3 | `core.hooksPath` configured (`git config --get` does not exit 1) | `graph refresh hooks not installed while core.hooksPath is configured; graph_view.py refreshes the graph before each use`; stop |
| 4 | the graph is under a child directory | `graph under <child>/ is not refreshed by git hooks; graph_view.py refreshes it before each use`; stop |
| 5 | `post-commit` in `git rev-parse --git-path hooks` lacks `# graph-guard-start` immediately before `# graphify-hook-start` | run `install_hooks.py --graph-only <main checkout>` under a 120-second bound, where `<main checkout>` is the worktree root, or in a linked worktree the parent of `git rev-parse --git-common-dir`; print its result line |

With nothing to do, it prints `graph ready`. It exits 0 in every case and never blocks a goal
start. Its writes are graphify's own `graphify-out/` (step 2) and, through `install_hooks.py`,
the graph blocks and their guards (step 5).

The 600-second bound fits a full code build of a large repository, which runs once per worktree;
later refreshes are incremental. A build cut off by the bound leaves no `graph.json`, or one that
does not parse, which setup and `view` treat as no graph.

**Why setup runs `--graph-only`, not the full installer, and does not only print the command.**
The full `install_hooks.py` also rewrites `pre-commit`, `commit-msg` and `pre-push` and decides
the identifier guard, which migration owns with its preview. Printing only would leave setup
half-done at every goal start, which the founder's direction rules out.

**The guard, from F-3 M4.** `install_hooks.py` already writes its own marked block,
`# graph-guard-start` … `# graph-guard-end`, immediately before each of graphify's `post-commit`
and `post-checkout` blocks, and adds it to existing unguarded blocks. In the hook's cwd the guard
requires `${GRAPHIFY_OUT:-graphify-out}/graph.json`, and a `.graphify_root` that is absent or
exactly `.`; otherwise it runs `exit 0`. graphify's blocks stay byte for byte, and `--uninstall`
strips the guards with them. A graph under a child directory gets an honest skip, because the
hook runs at the worktree root. F-5 relies on all of this and changes two things.

- `install_graph_hook` stops requiring a graph. With graphify on PATH and `core.hooksPath` unset,
  it installs the guarded blocks whether or not the main checkout has a graph, because the guard
  makes them no-ops wherever no graph exists. `--no-graph` still opts out.
- `--graph-only` runs only `install_graph_hook`, with its `core.hooksPath` query, its guarding of
  existing blocks and its checked-path writes, and touches no other hook. It cannot be combined
  with `--uninstall`, `--check`, `--scope` or `--public`.

Expected size: about 15 non-test lines. Together with `stale-guide`, that fits `progressive-disclosure`'s AC-13 headroom,
112 lines at `goal/F-3/M4` (5,358 of 5,470).

**`stale-guide`, in `validate_disclosure.py`.** For each scoped entry file in a directory `D`:
- take the area guides it links to;
- let `g` be the last commit touching a guide (`git log -1 --format=%H -- <guide>`);
- let `n` be `git rev-list --count g..HEAD -- D`, excluding `*.md` under `D`.

When `n > 0`, it reports one WARN: `stale-guide <guide>: <n> commit(s) to <D> since the guide last
changed`. It never raises an ERROR.

It uses the existing scoped-file discovery and link parsing. It is skipped outside a git
repository, and for a guide that has never been committed. Expected size: about 30 lines, which
fits the AC-13 headroom together with the guard.

**`graph_view.py view`.** Usage: `graph_view.py view --root <project> --out <dir> <Symbol> ...`.
- It finds the graph root by the rule above, and reads `built_at_commit`.
- When code files changed since that commit, it runs `graphify update <graph root>`, with a
  120-second timeout.
- Per symbol, it runs `graphify explain` and `graphify affected --depth 2`, each with a 60-second
  timeout, and writes `<out>/<Symbol>.txt`.
- It prints one line per output path, or one line naming why it fell back: no graph, graphify
  missing, timeout or error.
- It exits 0 in every case, because the fallback is the route.
- It writes only under `<out>` and, through `update`, under `graphify-out/`.
- Python 3.10+, standard library only. It sits in the published `graph-navigation` skill, outside
  the methodology's code budget; no size test covers that skill today, and `setup` and `view`
  together are expected at about 220 lines. `verify.sh` runs the new `tests/` directory.

**`install.sh`, Codex.** The Codex `WANT` list gains:
- `("SessionStart", None, …, "hooks/disclosure-check.sh")`, which surfaces `stale-guide` with the
  other route findings;
- `("SessionStart", None, …, "hooks/graphify-session-lessons.sh")`, the hook Claude Code already
  has, unchanged;
- `("PreToolUse", None, …, "hooks/graphify-query-advisor.py")`.

The advisor entry has no matcher, as Codex's PreToolUse hooks on this machine already do, so it
fires for every tool. The advisor reads the shell command from the payload and exits silently when
there is none. T2 confirms the shape of Codex's payload in the real-harness smoke and fixes it in a
test.

## Rules text

**At setup:**
- **`run.md`'s Starting steps** gain one step, after marking the goal active: run
  `python3 <graph-navigation>/scripts/graph_view.py setup`. Its words are offset by a trim in
  `run.md`.
- **`migrate.md`'s step 4** gains one sentence: run the same command once the hooks are in place.

**On every run, with or without a graph:**
- **`run.md`'s dispatch step:** for each folder in the task's writes, the packet lists the nearest
  scoped entry file and the area guide it routes to. If `stale-guide` names one of those guides,
  the chief checks it against the code before relying on it, then fixes it inside the task if the
  writes allow, or queues the fix. This replaces words trimmed elsewhere in `run.md`.
- **`review.md`'s Acceptance section:** the acceptance note names the guides for the touched
  folders, so the judge checks that they are still true.
- **`planning.md`:** a task that changes a folder's layout, commands, interfaces or invariants
  carries that folder's area guide in its `writes`. A task that adds a source folder carries the new
  scoped pair. This is one sentence.

**Only with a graph:** `references/context.md`, a new reference of at most 450 words, covers:

- **Bounded calls.** The chief runs graphify only through `graph_view.py`, never directly. A
  shell tool's own limit is not a process timeout; Codex's, for one, only yields. `graph_view.py`
  enforces the bounds in-process, and a timeout means falling back to the route and grep.
- **Freshness first.** Read `built_at_commit`. When the graph is behind HEAD on code files, run
  `graphify update <graph root>` before using it. `update` needs no LLM. Doc staleness is
  reported, not rebuilt.
- **Symbols, not prose.** Name the symbols the task or correction changes. Run
  `graphify explain "<Symbol>"` and `graphify affected "<Symbol>" --depth 2`, and save the output
  as `.runs/<goal>/context/<task>-<symbol>.txt`. Follow the `graph-navigation` ladder when a
  symbol misses.
- **Packets carry paths.** The packet lists those files. Every dependent in the `affected` output
  is a candidate for F-4's Keep list. The chief keeps a candidate when an earlier verdict,
  Decision or test explains why the dependent relies on the behaviour.
- **Acceptance.** For the milestone's changed symbols, save one `affected` file and name it in the
  acceptance note. A judge reads it; judges never run graphify.
- **No graph, or graphify missing.** Read and grep as before. Nothing blocks on the graph.

`run.md`'s dispatch step also points to `context.md` for the graph case.

**Load.** Without a graph, every role stays within the 3,000-word budget, `run.md`'s new Starting
step included. With a graph, the dispatching or accepting chief also reads `context.md`, about
3,450 words in all; no session hook adds to it. The spec approves
this exception explicitly. Folding `context.md` into `run.md` would put the cost on every run,
including the many without a graph.

## Smallest-sufficient-change trace

- **Folder routes:** they already exist and are already loaded by proximity. The gap is truth, so
  the change is one WARN in the existing checker, one planning sentence, and the route as the
  first item of the packet.
- **Setup:** one subcommand beside the graph runner the chief already needs, called from two
  existing setup steps. There is no new hook, no new skill and no script under a budgeted skill.
- **Both harnesses:** three entries in the existing Codex `WANT` list.
- **Refresh:** the commit-time refresh exists, and F-3 made its installation safe. The only
  change is a guard that keeps hooks from creating a partial graph. The chief refreshes a stale
  graph before use, and setup installs the hooks.
- **Use:** rules text only. The chief already writes packets, and `affected` is a single command.
- **Measure:** one record. It turns the "worth it?" question into a number before the founder makes
  graphs a default anywhere.

## Rejected options

- **Auto-build an LLM-backed graph:** it spends LLM tokens without consent. Setup builds only the
  code graph, which needs no LLM.
- **A per-session status hook:** setup belongs to methodology setup (founder, 2026-10-08), and a
  per-session check adds noise to every session while `graph_view.py` already refreshes before use.
- **Give judges graphify:** the Claude judge has no shell by design, and judge isolation outranks
  convenience. The chief attaches the output instead.
- **Setup inside a budgeted skill:** it would spend the methodology's code budget, and
  `graph-navigation` already owns the graph calls.
- **Setup runs the full `install_hooks.py`:** it also rewrites `pre-commit`, `commit-msg` and
  `pre-push` and decides the identifier guard, which migration owns.
- **graphify's own `install --platform`:** it writes harness config and `CLAUDE.md` outside our
  installer's control.
- **Generate area guides from the graph:** a guide states intent and invariants, which a graph
  cannot supply.
- **`stale-guide` as an ERROR:** a guide can stay correct while its folder's code changes, and an
  error would train agents to make cosmetic touches to guides.
- **An LLM wiki:** a second, unverifiable copy of the truth. The route and the graph are both
  derived from the repository.
- **Wrap graphify's block in our own `if` or subshell:** `graphify hook uninstall` removes only the
  text between its markers, and would leave a dangling wrapper that breaks the hook.
- **Rely on `GRAPHIFY_SKIP_HOOK`:** graphify's post-commit block honours it, but its post-checkout
  block does not, so the guard would have to differ between the two hooks.
- **Per-worktree graph state, or key-symbol lines, in folder `.md` files:** committed files are
  identical in every worktree on a branch, so per-worktree state would go stale. Area guides stay
  route and intent (founder decision 2026-10-08).
