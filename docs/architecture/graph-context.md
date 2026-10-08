---
id: F-5
title: Folder routes and graph-backed context for goal runs
spec: docs/product/specs/F-5-graph-context.md
status: approved
updated: 2026-10-08
---

# F-5 design — folder routes and graph-backed context

## Structure

| Concern | Owner | Change |
| --- | --- | --- |
| Graph setup | `graph-navigation/scripts/graph_view.py setup` (new), run by `references/run.md`'s Starting steps and `references/migrate.md`'s step 4 | installs the guarded refresh hooks where git runs them, first; builds nothing unless `graphify-out/` is ignored; then runs a full `graphify update . --force` from the graph root once per checkout (no graph, an unparsable one, a foreign `.graphify_root`, or no stamp of setup's own build), records that build in a stamp, and claims nothing about completeness |
| Both harnesses | `install/install.sh` | Codex gets the existing `graphify-session-lessons.sh` and the query advisor |
| Stale area guides | `progressive-disclosure/scripts/validate_disclosure.py` | a new `stale-guide` WARN beside `unscoped-dir`, which runs at commit, in the gate and at session start |
| Codex route check | `install/install.sh` | Codex also gets `disclosure-check.sh` at SessionStart |
| Planning rule | `execution-methodology/references/planning.md` | a task that changes what a guide states writes the guide |
| Refresh hooks in git | `progressive-disclosure/scripts/install_hooks.py` (changed) | F-3 M4's guard stays; it installs without a graph in the main checkout, and `--graph-only` runs only the graph step |
| Bounded graph calls | `graph-navigation/scripts/graph_view.py view` (new) | one command for the chief in either harness: the advisory label, a forced refresh only on `--refresh`, then `explain` and `affected`, each under an in-process timeout |
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
HEAD. Such a graph looks current by its build commit, and `affected` then silently misses most of
the code.

**A hook refreshes only an existing graph at the worktree root**: F-3 M4's guard in
`install_hooks.py`, below, enforces this, so a guarded hook never creates a graph. That keeps the
hazard from recurring, but it does not make any graph provably complete. graphify's post-commit
hook re-extracts only `HEAD~1..HEAD`, so one skipped refresh leaves a gap that later refreshes
never fill, while `built_at_commit` still reaches HEAD. Rounds 5 and 6 found no state that proves
completeness. F-5 therefore makes no completeness claim (founder, 2026-10-08): **graph output is
advisory context, labelled with its build commit and its distance from HEAD, and the agent
confirms what it uses with grep or by reading the code.** The advisory contract, under
Interfaces, states this as properties.

**Setup instead of a status hook.** Graph setup is a step of methodology setup (founder,
2026-10-08): migration and every goal start run `graph_view.py setup`, which installs missing
refresh hooks and builds the graph once per checkout. Nothing checks per session. Drift between
goal starts is shown where it matters, by the label `graph_view.py view` prints at every use, and
`view --refresh` rebuilds on request.

**The graph directory is ignored.** Setup requires `graphify-out/` to be ignored by git. Without
the ignore, setup's `graphify-out/` makes every receipt fail with "tree not clean" and every guard
report outside writes. This repository ignores `/graphify-out/` wholesale, and `migrate.md`'s step
4 adds the same line next to `/.runs/`. D11's split, which commits `reflections/` and `memory/`,
stays an option for a project that wants it; the plan's Queue holds what that costs. Setup and
`view` check the ignore (A5 below) and write nothing under an unignored graph directory. A project
that commits part of `graphify-out/` under D11's split fails that check, so setup builds nothing
there until Queue (a) is decided.

## Interfaces

**`graph_view.py setup [--root <worktree>] [--no-bound]`.** `--root` defaults to the git top
level of the cwd. `--no-bound` lifts the 600-second bound on the build, and nothing else.

**Printed commands.** Every command setup or `view` prints repeats its own invocation:
`<rerun>` is `python3 <graph_view.py>`, the absolute path of the script, then the same subcommand
and arguments, with `--root` always given as the absolute worktree root even when it was
defaulted. For `view` that keeps `--refresh` and any `--out <dir> <Symbol> ...`. The retry line
adds `--no-bound` to `<rerun>`.

**One failure line.** A build that times out and a build that exits nonzero print the same line,
whose retry is `<rerun> --no-bound` in both cases:
`graph build <reason>; retry with: <rerun> --no-bound`, where `<reason>` is
`timed out after <s> s` or `failed (exit <n>)`, and `<s>` is 600 for setup and 120 for
`view --refresh`. A nonzero exit prints the retry too, so one tested command follows either
failure; after a failure that persists, the retry prints the same line again.
Every git query runs with `cwd` at the worktree root, a timeout of 5 s, the repository-location
variables (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` and the like) dropped, and `GIT_CONFIG`
dropped, which only `git config` reads. git's other config-environment variables are kept, so the
query sees what a running git sees, matching `install_hooks.py`.

Steps, in order: hooks, then the ignore check, then the build. Each prints at most one line:

| Step | Condition | Action, or line |
| --- | --- | --- |
| 1 | `graphify` not on PATH | `graphify not installed; graph context off (install with: uv tool install graphifyy)`; stop |
| 2 | always | find the graph root: the directory holding a parsing `graphify-out/graph.json`, at the worktree root or under one child (the `install_hooks.graphify_root` rule, duplicated in about eight lines so `graph-navigation` stays independent of the skill), else the worktree root |
| 3 | `core.hooksPath` configured (`git config --get` does not exit 1) | `graph refresh hooks not installed while core.hooksPath is configured; refresh on request with: python3 <graph_view.py> view --root <worktree> --refresh`; go to step 6 |
| 4 | the graph is under a child directory | `graph under <child>/ is not refreshed by git hooks; refresh on request with: python3 <graph_view.py> view --root <worktree> --refresh`; go to step 6 |
| 5 | `post-commit` or `post-checkout` in `git rev-parse --git-path hooks` lacks `# graph-guard-start` immediately before `# graphify-hook-start` | run `install_hooks.py --graph-only <main checkout>` under a 120-second bound, where `<main checkout>` is the worktree root, or in a linked worktree the parent of `git rev-parse --git-common-dir`; print its result line. Both hooks are checked because each carries a graphify block that could create a graph unguarded (AC-7) |
| 6 | `git check-ignore -q <graph root>/graphify-out/`, run at the worktree root with the git environment above, does not exit 0 | `graphify-out/ is not ignored; add /<graph root>/graphify-out/ to .gitignore, then rerun: <rerun>` (`/graphify-out/` for the worktree root); stop, writing nothing under it |
| 7 | one of A2's build conditions holds | first the symlink check (A5): when it refuses, print its line and stop. Then delete the stamp (A2). Then run `graphify update . --force` with its cwd at the graph root, under an in-process 600-second bound unless `--no-bound`. On exit 0 within the bound, write the stamp (A2) and print `graph built: <reason>`. On a timeout or a nonzero exit, print the failure line above and write no stamp |

When no step prints a line, setup prints `graph ready`. It exits 0 in every case and never blocks a
goal start. Its writes are graphify's own `graphify-out/`, the stamp and its deletion (step 7)
and, through `install_hooks.py`, the graph blocks and their guards (step 5). Under `core.hooksPath`, or with a
child graph, setup installs nothing; hooks under `core.hooksPath` stay F-3 Queue Q7's.

**The advisory contract.** Setup and `view` share it; `<g>` is the graph root's `graphify-out/`.

1. **A1, no completeness claim.** Nothing in F-5 claims a graph is complete or fresh. Graph output
   is advisory context, and the agent confirms what it uses with grep or by reading the code.
   Every graph result `view` prints, and every output file it writes, carries A4's label.
   graphify's post-commit hook re-extracts only `HEAD~1..HEAD` (`hooks.py`, about line 236), so
   one skipped refresh leaves a gap that later refreshes never fill while `built_at_commit` still
   reaches HEAD. No state F-5 can read rules that out.
2. **A2, setup builds once per checkout.** Setup runs a full `graphify update . --force` from the
   graph root, bounded, only when one of these holds:
   - there is no graph;
   - `graph.json` does not parse;
   - `.graphify_root` is neither absent nor exactly `.`;
   - `<g>/.graph_view_complete` is missing or does not parse.

   Before starting any build, setup and `view --refresh` delete `<g>/.graph_view_complete`.
   After the build exits 0 within its bound, they write a new stamp as
   `{"head": <HEAD's full commit id>, "sha256": <hex of graph.json's bytes>}`. A timeout or
   failure therefore always leaves no stamp, even when an older valid stamp existed and graphify
   had already rewritten `.graphify_root` to `.`, so the next setup builds again ("stamp
   missing"); it prints the failure line. Otherwise setup builds nothing, however far behind HEAD
   the graph is. The stamp records the last full build by setup or `view --refresh`; it is not a
   trust signal.
3. **A3, the guard stays.** Setup installs the guard as before (steps 3–5: `--graph-only`, the
   `core.hooksPath` rule, the child-graph rule), so hooks keep the advisory graph roughly current.
   The guard plays no part in any claim.
4. **A4, `view` never rebuilds on its own.** It first prints a label:
   `graph built at <short built_at_commit> (<B> commits behind HEAD, <A> ahead); advisory —
   confirm with grep`, on one line, where `<A>` and `<B>` are the left and right counts of
   `git rev-list --left-right --count <built_at_commit>...HEAD`. `, <A> ahead` is omitted when
   `<A>` is 0, so a graph built at an ancestor reads `(<B> commits behind HEAD)`; a graph built
   on a branch HEAD has left, or one HEAD has moved behind, shows both counts.
   - When `built_at_commit` is missing or unknown to git, the label reads
     `graph build commit unknown; advisory — confirm with grep`.
   - When the stamp's `head` equals HEAD and its `sha256` matches the bytes `view` read, the
     label adds `full build by setup at HEAD`.
   - **One read.** `view` reads `graph.json` once into memory. The label, the stamp comparison and
     every result come from those bytes: it writes them to a snapshot in a new temporary
     directory outside the repository, passes `--graph <snapshot>` to `explain` and `affected`
     (both accept it in graphify 0.8.49), and removes the snapshot before it exits. A hook that
     replaces `graph.json` meanwhile changes neither the label nor the results.
   - `view --refresh` first runs the same full forced build, stamp deletion and stamp as A2,
     under `view`'s 120-second bound unless `--no-bound`, and reads the graph after it.
   - Without a graph, `view` prints its no-graph line.
5. **A5, ignored only, and no symlinks.** Neither setup nor `view` writes anything, build, stamp
   or refresh, under a graph directory that `git check-ignore -q` does not report ignored. Each
   prints the step-6 line and exits 0, and `view` then falls back to its no-graph output. Before
   any build, setup and `view --refresh` also `lstat` `<g>` itself and each existing entry
   directly inside it; when any is a symlink, they print
   `graph build refused: <path> is a symlink; remove it, then rerun: <rerun>`, delete nothing,
   build nothing and exit 0, and `view` goes on with the existing graph. graphify 0.8.49 writes
   its artifacts with `Path.write_text` (`watch.py`, about line 819 for `GRAPH_REPORT.md`), which
   follows a symlink, so a build could otherwise overwrite the tracked file it points to. The
   check runs once, before the build; a symlink created while graphify runs is not defended.
6. **A6, unchanged.** Exit codes (0 in every case) and the `GRAPHIFY_*` drop are as below.

**The command.** Every graphify call from `setup` and `view` runs with its cwd at the graph root,
`.` as its path argument, and every inherited `GRAPHIFY_*` variable dropped. A build is
`graphify update . --force`.
- **`.`, from the graph root.** graphify records its path argument, as typed, in
  `graphify-out/.graphify_root`. Any other spelling would trigger A2's build at every goal start
  and make F-3's guard skip every hook refresh.
- **`--force`.** Without it, graphify refuses to write a graph that lost nodes it cannot attribute
  to a re-extracted or deleted file, and exits 1. That refusal was measured on a large
  repository's full update and on 44 of 1,928 hook refreshes in one log. A retry without
  `--force` would not clear it.
- **`GRAPHIFY_*` dropped.** The only output location graphify is given is then the default
  `graphify-out/` under the graph root, which is also the only output the hook guard refreshes.

F-5 promises only what setup and `view` control: the command and its cwd, the `GRAPHIFY_*` drop,
the stamp, the path recorded in `.graphify_root`, the label, the printed lines and exit 0. What a
build or a hook refresh puts in the graph is graphify's behaviour. T6's oracle test records it for
graphify 0.8.49 and guarantees nothing.

The 600-second bound fits a full code build of a large repository: 44–59 s were measured on one of
2,932 code files, and warm and cold full updates measured the same (`measurements.md`). A2 builds
once per checkout, so most goal starts pay only setup's checks. A build cut off by the bound writes
no stamp, so the next setup builds again.

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

**`graph_view.py view`.** Usage:
`graph_view.py view --root <project> [--refresh [--no-bound]] [--out <dir> <Symbol> ...]`.
- It finds the graph root by the rule above. With no parsing graph, it prints its no-graph line.
- When the graph directory is not ignored (A5), it prints setup's step-6 line, writes nothing
  under it and falls back to its no-graph output.
- It never rebuilds on its own. With `--refresh`, it first runs A5's symlink check, deletes the
  stamp, runs A2's full forced build from the graph root under a 120-second bound (none with
  `--no-bound`) and writes the stamp after exit 0. On a timeout or a nonzero exit it prints the
  failure line, for example
  `graph build timed out after 120 s; retry with: python3 <graph_view.py> view --root <root> --refresh --no-bound`,
  and goes on with the existing graph. With `--refresh` and no symbols, it only refreshes.
- It reads `graph.json` once (A4), prints A4's label, then, per symbol, runs
  `graphify explain` and `graphify affected --depth 2` from the graph root against the snapshot,
  each with a 60-second timeout, and writes `<out>/<Symbol>.txt` with the label as its first line.
- It prints one line per output path, or one line naming why it fell back: no graph, graphify
  missing, timeout or error.
- It exits 0 in every case, because the fallback is the route.
- It writes only under `<out>`, its temporary snapshot outside the repository, and, with
  `--refresh`, the stamp and graphify's own output under an ignored `graphify-out/`.
- Python 3.10+, standard library only. It sits in the published `graph-navigation` skill, outside
  the methodology's code budget; no size test covers that skill (`test_size.py` counts only
  `execution-methodology`, `agent-personas` and `progressive-disclosure`), and `setup` and `view`
  together are expected at about 260 lines: dropping the freshness rule and the automatic refresh
  saves about 30, and the symlink check, the single read and the printed-command builder add about
  30. `verify.sh` runs the new `tests/` directory.

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
- **Advisory, labelled.** Graph output is advisory. `view`'s label says when the graph was built
  and how many commits it is behind HEAD, and ahead when it is. Confirm every dependent you rely
  on with grep or by reading the code; a dependent the graph misses is still a dependent. Add
  `--refresh` when the label shows the graph too far from HEAD to help; it needs no LLM and
  rebuilds code only. Doc staleness is reported, not rebuilt.
- **Symbols, not prose.** Name the symbols the task or correction changes. Run
  `graphify explain "<Symbol>"` and `graphify affected "<Symbol>" --depth 2`, and save the output
  as `.runs/<goal>/context/<task>-<symbol>.txt`. Follow the `graph-navigation` ladder when a
  symbol misses.
- **Packets carry paths.** The packet lists those files. Every dependent in the `affected` output
  is a candidate for F-4's Keep list. The chief keeps a candidate when an earlier verdict,
  Decision or test explains why the dependent relies on the behaviour, and the code confirms it.
- **Acceptance.** For the milestone's changed symbols, save one `affected` file and name it in the
  acceptance note. A judge reads it as advisory and checks what it relies on against the code;
  judges never run graphify.
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
  change is a guard that keeps hooks from creating a partial graph. Setup builds once per
  checkout, and `view` labels what it shows instead of deciding whether to trust it.
- **Use:** rules text only. The chief already writes packets, and `affected` is a single command.
- **Measure:** one record. It turns the "worth it?" question into a number before the founder makes
  graphs a default anywhere.

## Rejected options

- **Auto-build an LLM-backed graph:** it spends LLM tokens without consent. Setup builds only the
  code graph, which needs no LLM.
- **A per-session status hook:** setup belongs to methodology setup (founder, 2026-10-08), and a
  per-session check adds noise to every session while `view` already labels the graph at use.
- **A full update at every setup:** it measured 44–59 s on a large repository at every goal
  start, warm or cold, and would still prove nothing about the graph between goal starts.
- **Prove a graph complete or fresh** (rounds 4–6: always rebuild, guard history, a pending
  marker, a HEAD stamp, a guard-gated `built_at_commit`): graphify's post-commit hook refreshes
  only `HEAD~1..HEAD`, so one skipped refresh leaves a gap no later state reveals. Every proxy
  failed a reviewer's trigger (founder, 2026-10-08).
- **Rebuild automatically in `view` when it looks stale:** staleness by commit count does not
  measure the gap either, and an automatic rebuild puts up to a minute on a large repository into
  dispatch. The label and `--refresh` leave the call to the chief.
- **Refresh without `--force`:** a rebuild that loses nodes graphify cannot attribute exits 1 and
  writes nothing.
- **Pass the graph root's path to graphify:** graphify records the path as typed in
  `.graphify_root`, so any spelling but `.` triggers A2's build every time and makes the hook
  guard skip.
- **Print `graphify update . --force` as the timeout fix:** it writes no stamp, so the next bounded
  setup builds again and can time out again. The printed fix is the invocation itself, with its
  own `--root` and arguments, without the bound.
- **A bounded retry for a nonzero exit, unlike the timeout's:** two retry commands for one build
  made the failure contract inconsistent (round 7). Both print `<rerun> --no-bound`.
- **Keep a stamp across a failed build:** a valid old stamp would then hide a build that failed
  after graphify rewrote `.graphify_root`, and the next setup would build nothing.
- **Label from one read and query from another:** a hook can replace `graph.json` between them, so
  the label would describe a different graph from the results.
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
