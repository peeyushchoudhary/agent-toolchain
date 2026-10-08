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
| Graph setup | `graph-navigation/scripts/graph_view.py setup` (new), run by `references/run.md`'s Starting steps and `references/migrate.md`'s step 4 | installs the guarded refresh hooks where git runs them, first; builds nothing unless `graphify-out/` is ignored; then runs `graphify update . --force` from the graph root when the guard was missing, the graph is missing, neither its `built_at_commit` nor setup's stamp is HEAD, or its `.graphify_root` is neither absent nor `.`, stamping HEAD after a finished rebuild, and otherwise trusts the graph |
| Both harnesses | `install/install.sh` | Codex gets the existing `graphify-session-lessons.sh` and the query advisor |
| Stale area guides | `progressive-disclosure/scripts/validate_disclosure.py` | a new `stale-guide` WARN beside `unscoped-dir`, which runs at commit, in the gate and at session start |
| Codex route check | `install/install.sh` | Codex also gets `disclosure-check.sh` at SessionStart |
| Planning rule | `execution-methodology/references/planning.md` | a task that changes what a guide states writes the guide |
| Refresh hooks in git | `progressive-disclosure/scripts/install_hooks.py` (changed) | F-3 M4's guard stays; it installs without a graph in the main checkout, and `--graph-only` runs only the graph step |
| Bounded graph calls | `graph-navigation/scripts/graph_view.py view` (new) | one command for the chief in either harness: setup's trust rule, a forced refresh, then `explain` and `affected`, each under an in-process timeout |
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
worktree root.** Only an explicit `graphify update . --force` from setup or `view` creates a
graph, a full code build that needs no LLM. F-3 M4's guard in `install_hooks.py`, below, enforces
this. Once the guard is in place, it keeps a graph complete, so setup and `view` can trust a graph
whose `built_at_commit` is HEAD.

A graph built before the guard cannot be trusted that way: an older unguarded hook leaves a
partial graph whose `built_at_commit` is HEAD. Setup therefore checks the guard before it looks at
the graph, and a guard it finds missing forces one full rebuild, whatever the graph says (founder,
2026-10-08).

**Setup instead of a status hook.** Graph setup is a step of methodology setup (founder,
2026-10-08): migration and every goal start run `graph_view.py setup`, which installs missing
refresh hooks and rebuilds an untrusted code graph itself. Nothing checks per session. Drift
between goal starts (new commits) is handled where it matters, by `graph_view.py view` applying
the same trust rule before every use.

**The graph directory is ignored.** Setup requires `graphify-out/` to be ignored by git. Without
the ignore, setup's `graphify-out/` makes every receipt fail with "tree not clean" and every guard
report outside writes. This repository ignores `/graphify-out/` wholesale, and `migrate.md`'s step
4 adds the same line next to `/.runs/`. D11's split, which commits `reflections/` and `memory/`,
stays an option for a project that wants it; the plan's Queue holds what that costs. Setup checks
the ignore (step 6 below) and builds nothing without it. A project that commits part of
`graphify-out/` under D11's split fails that check, so setup builds nothing there until Queue (a)
is decided.

## Interfaces

**`graph_view.py setup [--root <worktree>]`.** `--root` defaults to the git top level of the cwd.
Every git query runs with `cwd` at the worktree root, a timeout of 5 s, the repository-location
variables (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` and the like) dropped, and `GIT_CONFIG`
dropped, which only `git config` reads. git's other config-environment variables are kept, so the
query sees what a running git sees, matching `install_hooks.py`.

Steps, in order: the guard first, then the trust rule. Each prints at most one line:

| Step | Condition | Action, or line |
| --- | --- | --- |
| 1 | `graphify` not on PATH | `graphify not installed; graph context off (install with: uv tool install graphifyy)`; stop |
| 2 | always | find the graph root: the directory holding a parsing `graphify-out/graph.json`, at the worktree root or under one child (the `install_hooks.graphify_root` rule, duplicated in about eight lines so `graph-navigation` stays independent of the skill), else the worktree root |
| 3 | `core.hooksPath` configured (`git config --get` does not exit 1) | `graph refresh hooks not installed while core.hooksPath is configured; graph_view.py refreshes the graph before each use`; go to step 6 |
| 4 | the graph is under a child directory | `graph under <child>/ is not refreshed by git hooks; graph_view.py refreshes it before each use`; go to step 6 |
| 5 | `post-commit` in `git rev-parse --git-path hooks` lacks `# graph-guard-start` immediately before `# graphify-hook-start` | the guard is missing: run `install_hooks.py --graph-only <main checkout>` under a 120-second bound, where `<main checkout>` is the worktree root, or in a linked worktree the parent of `git rev-parse --git-common-dir`; print its result line. Step 7 then rebuilds |
| 6 | `git check-ignore -q <graph root>/graphify-out/`, run at the worktree root with the git environment above, does not exit 0 | `graphify-out/ is not ignored; add /<graph root>/graphify-out/ to .gitignore, then rerun setup` (`/graphify-out/` for the worktree root); stop, building nothing |
| 7 | the guard was missing at step 5; or there is no parsing graph; or neither its `built_at_commit` nor the stamp is HEAD; or its `.graphify_root` is neither absent nor exactly `.` (`rebuild-pending` included) | when the guard was missing, first write `rebuild-pending` into `graphify-out/.graphify_root` (creating `graphify-out/` if needed, never touching `graph.json`). Run `graphify update . --force` with its cwd at the graph root, under an in-process 600-second bound. On exit 0, write the stamp and print `graph rebuilt: <reason>`. After a timeout or a nonzero exit, write the marker again if this rebuild was guard-forced. On timeout: `graph build timed out after 600 s; build by hand in <graph root> with: graphify update . --force`. On a nonzero exit: `graph build failed (exit <n>); build by hand in <graph root> with: graphify update . --force`. `<graph root>` is relative to the worktree root, `.` for the root itself |

When no step prints a line, setup prints `graph ready`. It exits 0 in every case and never blocks a
goal start. Its writes are graphify's own `graphify-out/`, the marker and the stamp (step 7) and,
through
`install_hooks.py`, the graph blocks and their guards (step 5). Under `core.hooksPath`, or with a
child graph, setup installs nothing and the guard trigger never fires; hooks under
`core.hooksPath` stay F-3 Queue Q7's. While step 5 cannot install the guard (it fails, or the main
checkout's graph is under a child, which `install_hooks.py` skips), every setup rebuilds. That
costs time and is safe.

**The trust rule.** A graph is trusted when all three hold:
- `graph.json` parses;
- its `built_at_commit` or the stamp `graphify-out/.graph_view_head` equals HEAD's full commit id;
- its `.graphify_root` is absent or exactly `.`.

At setup, a guard that step 5 found missing also forces a rebuild. `view` applies the rule
without that condition. A trusted graph costs a freshness check of well under a second; an
untrusted one costs a full rebuild.

**The stamp.** After a rebuild that exits 0 within its bound, setup and `view` write HEAD's full
commit id to `graphify-out/.graph_view_head`. A timeout or failure writes no stamp. The stamp is
needed because a forced update that finds the code graph unchanged exits 0 but leaves `graph.json`
as it was, `built_at_commit` included (graphify 0.8.49, `watch.py`'s "No code-graph topology
changes" and "No code-graph changes" paths). Trusting `built_at_commit` alone would then rebuild
at every setup and every `view` after a non-code commit. The stamp records that this checkout's
graph was rebuilt, or confirmed, at HEAD. It lives in `graphify-out/`, which is ignored, so it
never dirties the tree.

**The pending marker.** A rebuild forced by a missing guard must not be lost to a timeout, since
the previous graph may be partial and built at HEAD. graphify writes its path argument into
`.graphify_root` on every full run that finds code files, success included (graphify 0.8.49,
`watch.py`, about lines 671–677). It writes it after extraction but before clustering and the
graph write, so a run cut off late can already have replaced the marker with `.`. Setup therefore
writes `rebuild-pending` before the run and writes it again after a timeout or nonzero exit.
- A finished rebuild leaves `.graphify_root` reading `.`, and the graph is trusted.
- An unfinished one leaves `rebuild-pending`. The next setup's existing `.graphify_root` trigger
  rebuilds, `view` rebuilds before use, and F-3's guard skips hook refreshes of that graph,
  because `.graphify_root` is not `.`.
- *Assumption (default): a crash that kills setup itself after graphify has replaced the marker,
  and before the graph is written, is not covered.*

**The command.** Every graphify call from `setup` and `view` runs with its cwd at the graph root,
`.` as its path argument, and every inherited `GRAPHIFY_*` variable dropped. A rebuild is
`graphify update . --force`.
- **`.`, from the graph root.** graphify writes its path argument, as typed, into
  `graphify-out/.graphify_root`. Any other spelling would fail the trust rule at every goal start
  and make F-3's guard skip every hook refresh.
- **`--force`.** Without it, graphify refuses to write a graph that lost nodes it cannot attribute
  to a re-extracted or deleted file, and exits 1. That refusal was measured on a large
  repository's full update and on 44 of 1,928 hook refreshes in one log. The graph then stays
  stale, and a printed fix command without `--force` would not clear the condition. `--force`
  only bypasses that node-count check. A full update drops only nodes marked `_origin: ast` and
  the nodes of deleted files, so semantic (LLM) nodes for files that still exist survive.
- **`GRAPHIFY_*` dropped.** graphify then writes only the default `graphify-out/` under the graph
  root, which is also the only output the hook guard refreshes.

These are predictions about graphify 0.8.49, so T6 carries an oracle test that runs real graphify
under the same environment, the marker's behaviour included.

The 600-second bound fits a full code build of a large repository: 44–59 s were measured on one of
2,932 code files (`measurements.md`). Every rebuild is a full one, and a warm run costs the same as
a cold one; the trust rule, not a cache, keeps the cost off most goal starts. A first build cut off
by the bound leaves no `graph.json`, or one that does not parse, which setup and `view` treat as no
graph. A rebuild cut off by the bound leaves the previous graph; when the rebuild was forced by a
missing guard, the pending marker above keeps that graph untrusted.

**Why setup runs `--graph-only`, not the full installer, and does not only print the command.**
The full `install_hooks.py` also rewrites `pre-commit`, `commit-msg` and `pre-push` and decides
the identifier guard, which migration owns with its preview. Printing only would leave setup
half-done at every goal start, which the founder's direction rules out.

**The guard, from F-3 M4.** `install_hooks.py` already writes its own marked block,
`# graph-guard-start` … `# graph-guard-end`, immediately before each of graphify's `post-commit`
and `post-checkout` blocks, and adds it to existing unguarded blocks in every install mode. The
guard exits whenever `GRAPHIFY_OUT` is set, to any value; otherwise, in the hook's cwd, it
requires the default `graphify-out/graph.json` and a `.graphify_root` that is absent or exactly
`.`. graphify's blocks stay byte for byte, and every uninstall mode strips the guards with them. A graph under a child directory gets an honest skip, because the
hook runs at the worktree root. F-5 relies on all of this and changes two things.

- `install_graph_hook` stops requiring a graph. With graphify on PATH and `core.hooksPath` unset,
  it installs the guarded blocks whether or not the main checkout has a graph, because the guard
  makes them no-ops wherever no graph exists. `--no-graph` still opts out.
- `--graph-only` runs only `install_graph_hook`, with its `core.hooksPath` query, its guarding of
  existing blocks and its checked-path writes, and touches no other hook. It cannot be combined
  with `--uninstall`, `--check`, `--scope` or `--public`.

Expected size: about 15 non-test lines. With `stale-guide` (about 30), `progressive-disclosure`
reaches about 5,500 of its AC-13 ceiling. F-3 M4's guard work left 5,453 of 5,470, so the founder
raised the ceiling to 5,520 (2026-10-08); T5 changes `test_size.py` accordingly.

**`stale-guide`, in `validate_disclosure.py`.** For each scoped entry file in a directory `D`:
- take the area guides it links to;
- let `g` be the last commit touching a guide (`git log -1 --format=%H -- <guide>`);
- let `n` be `git rev-list --count g..HEAD -- D`, excluding `*.md` under `D`.

When `n > 0`, it reports one WARN: `stale-guide <guide>: <n> commit(s) to <D> since the guide last
changed`. It never raises an ERROR.

It uses the existing scoped-file discovery and link parsing. It is skipped outside a git
repository, and for a guide that has never been committed. Expected size: about 30 lines, within the
raised AC-13 ceiling of 5,520 together with T7.

**`graph_view.py view`.** Usage: `graph_view.py view --root <project> --out <dir> <Symbol> ...`.
- It finds the graph root by the rule above, and applies the trust rule without the guard
  condition.
- When the graph is not trusted, it runs `graphify update . --force` from the graph root, with a
  120-second timeout. A rebuild that graphify would refuse as a shrink therefore refreshes the
  graph instead of leaving every later `view` on a stale one. When `.graphify_root` read
  `rebuild-pending` and the refresh times out or exits nonzero, `view` writes the marker again.
- Per symbol, it runs `graphify explain` and `graphify affected --depth 2` from the graph root,
  each with a 60-second timeout, and writes `<out>/<Symbol>.txt`.
- It prints one line per output path, or one line naming why it fell back: no graph, graphify
  missing, timeout or error.
- It exits 0 in every case, because the fallback is the route.
- It writes only under `<out>`, the marker, the stamp after a refresh that exits 0, and, through
  `update`, under `graphify-out/`.
- Python 3.10+, standard library only. It sits in the published `graph-navigation` skill, outside
  the methodology's code budget; no size test covers that skill (`test_size.py` counts only
  `execution-methodology`, `agent-personas` and `progressive-disclosure`), and `setup` and `view`
  together are expected at about 265 lines. `verify.sh` runs the new `tests/` directory.

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
  `run.md`, which sits at 2,999 of its 3,000-word role load.
- **`migrate.md`'s step 4** gains `/graphify-out/` beside `/.runs/` in the `.gitignore` bullet,
  and one sentence: run the same command once the hooks are in place.

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
- **Freshness first.** `graph_view.py view` applies the trust rule and, for an untrusted graph,
  runs `graphify update . --force` from the graph root before using it. `update` needs no LLM and
  rebuilds code only. Doc staleness is reported, not rebuilt.
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
  change is a guard that keeps hooks from creating a partial graph. Setup and `view` share one
  trust rule and one forced command, so a trusted graph costs a freshness check and nothing else.
- **Use:** rules text only. The chief already writes packets, and `affected` is a single command.
- **Measure:** one record. It turns the "worth it?" question into a number before the founder makes
  graphs a default anywhere.

## Rejected options

- **Auto-build an LLM-backed graph:** it spends LLM tokens without consent. Setup builds only the
  code graph, which needs no LLM.
- **A per-session status hook:** setup belongs to methodology setup (founder, 2026-10-08), and a
  per-session check adds noise to every session while `graph_view.py` already refreshes before use.
- **A full update at every setup:** every update is a full re-extraction, 44–59 s on a large
  repository at every goal start. The guard-first trust rule gives the same protection against a
  partial graph.
- **Trust a graph by `built_at_commit` alone:** an older unguarded hook leaves a partial graph
  whose `built_at_commit` is HEAD, and a forced update that finds the code graph unchanged does
  not advance it.
- **Trust when no extracted file changed since `built_at_commit`:** graphify extracts Markdown as
  code, so a prose-only edit would still rebuild at every setup.
- **Install the guard only after a rebuild succeeds:** the founder chose guard first
  (2026-10-08). The pending marker closes the cut-off rebuild that order leaves open.
- **Rely on graphify to keep the marker after a failed run:** graphify replaces `.graphify_root`
  before it writes the graph, so setup and `view` rewrite the marker after a timeout or failure.
- **Refresh without `--force`:** a rebuild that loses nodes graphify cannot attribute exits 1 and
  writes nothing, so the graph stays stale and the printed fix command does not clear it.
- **Pass the graph root's path to graphify:** graphify stores the path as typed in
  `.graphify_root`, so any spelling but `.` fails the trust rule and the hook guard.
- **Rely on graphify's cache for a cheap refresh:** a full update re-extracts everything, and a
  warm run costs the same as a cold one.
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
