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
| Status at session start | `install/hooks/graphify-session.py` (new; replaces `graphify-session-lessons.sh`) | reports the graph's state and keeps the lessons digest |
| Both harnesses | `install/install.sh` | Codex gets the session hook and the query advisor; the old hook is retired |
| Stale area guides | `progressive-disclosure/scripts/validate_disclosure.py` | a new `stale-guide` WARN beside `unscoped-dir`, which runs at commit, in the gate and at session start |
| Codex route check | `install/install.sh` | Codex also gets `disclosure-check.sh` at SessionStart |
| Planning rule | `execution-methodology/references/planning.md` | a task that changes what a guide states writes the guide |
| Refresh hooks in git | `progressive-disclosure/scripts/install_hooks.py` (unchanged) | it already installs the graph refresh only when `core.hooksPath` is unset; the status line points to it |
| Bounded graph calls | `graph-navigation/scripts/graph_view.py` (new) | one command for the chief in either harness: freshness, refresh, then `explain` and `affected`, each under an in-process timeout |
| Use in a goal run | `execution-methodology/references/context.md` (new), `references/run.md` (pointer) | the dispatch and acceptance steps |
| Records | `lean-execution.md`, `decisions.md`, `measurements.md` | current state, and the numbers |

graphify integration stays in our own hooks and skills. graphify's platform installers are not
used.

## Interfaces

**`graphify-session.py`, a SessionStart hook for both harnesses.**

Input:
- **project root:** `CLAUDE_PROJECT_DIR`, else the git top level of the cwd, else the cwd;
- **graph root:** the project root, or one non-symlinked, non-dot child that resolves inside the
  root, holding `graphify-out/graph.json`. This is the same rule as `install_hooks.graphify_root`,
  duplicated in eight lines because the hook must run without the skill.

Every git call runs with `cwd` at the project root, with a timeout of 5 s, and with the
repository-location variables dropped (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` and the
like) and `GIT_CONFIG`, which only `git config` reads. git's other config-environment variables
are kept, so the hooks query sees what a running git sees, matching `install_hooks.py`.
`graphify reflect --if-stale` runs with a timeout of 20 s. A timeout drops that
check or the digest silently.

Checks, in order. Each produces at most one line:

| Condition | Line |
| --- | --- |
| a graph exists, `graphify` is not on PATH | `graph present but graphify is not installed; install with: uv tool install graphifyy (or pipx install graphifyy)` |
| `graphify` on PATH, no graph | `no graphify graph; build one with /graphify (LLM cost), or ignore` |
| the graph's `built_at_commit` is not HEAD, and code files changed since | `graph is N code file(s) behind HEAD; refresh with: graphify update <graph root>` |
| a graph exists, `core.hooksPath` is unset, and `post-commit` in git's hooks directory (`git rev-parse --git-path hooks`, which is the shared directory in a linked worktree) has no `# graphify-hook-start` | `graph refresh hooks missing; install with: python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py <main checkout>`. `<main checkout>` is the project root, or, in a linked worktree, the parent of `git rev-parse --git-common-dir`, because `install_hooks.py` installs from the main checkout only. |
| a graph exists, and `core.hooksPath` is configured (`git config --get` does not exit 1) | `graph refresh hooks cannot be installed while core.hooksPath is configured; refresh by hand with: graphify update <graph root>` |

The hooks rule matches `install_hooks.py`: refresh hooks are installed only when `core.hooksPath`
is unset (F-3 M4).

**"Code files"** are the paths in `git diff --name-only <built_at_commit> HEAD` with a source-code
suffix. graphify's `update` re-extracts code only. A missing or unknown `built_at_commit` counts
as stale, and the line says "unknown".

**Output.**
- Claude Code: `hookSpecificOutput.additionalContext`.
- Codex: the same JSON shape on stdout, which Codex's SessionStart hook accepts. T2 confirms this
  in a smoke run.

The status lines come first, then the lessons digest, capped at 4,000 characters as today. With
nothing to report, the hook prints nothing.

Any exception prints nothing and exits 0.

The only write is `graphify reflect --if-stale`, which writes to `graphify-out/` as today, and
only when a graph exists.

**`stale-guide`, in `validate_disclosure.py`.** For each scoped entry file in a directory `D`:
- take the area guides it links to;
- let `g` be the last commit touching a guide (`git log -1 --format=%H -- <guide>`);
- let `n` be `git rev-list --count g..HEAD -- D`, excluding `*.md` under `D`.

When `n > 0`, it reports one WARN: `stale-guide <guide>: <n> commit(s) to <D> since the guide last
changed`. It never raises an ERROR.

It uses the existing scoped-file discovery and link parsing. It is skipped outside a git
repository, and for a guide that has never been committed. Expected size: about 30 lines, inside
`progressive-disclosure`'s AC-13 headroom of 131 lines.

**`graph_view.py`.** Usage: `graph_view.py --root <project> --out <dir> <Symbol> ...`.
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
  the methodology's code budget.

**`install.sh`, Codex.** The Codex `WANT` list gains:
- `("SessionStart", None, …, "hooks/disclosure-check.sh")`, which surfaces `stale-guide` with the
  other route findings;
- `("SessionStart", None, …, "hooks/graphify-session.py")`;
- `("PreToolUse", None, …, "hooks/graphify-query-advisor.py")`.

The advisor entry has no matcher, as Codex's PreToolUse hooks on this machine already do, so it
fires for every tool. The advisor reads the shell command from the payload and exits silently when
there is none. T2 confirms the shape of Codex's payload in the real-harness smoke and fixes it in a
test.

`graphify-session-lessons.sh` joins the retire list.

## Rules text

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

**Load.** Without a graph, every role stays within the 3,000-word budget. With a graph, the
dispatching or accepting chief also reads `context.md`, about 3,450 words in all. The spec approves
this exception explicitly. Folding `context.md` into `run.md` would put the cost on every run,
including the many without a graph.

## Smallest-sufficient-change trace

- **Folder routes:** they already exist and are already loaded by proximity. The gap is truth, so
  the change is one WARN in the existing checker, one planning sentence, and the route as the
  first item of the packet.
- **Detect:** one hook, reusing the existing SessionStart slot that already runs graphify-related
  work. There is no new skill and no new script under a budgeted skill.
- **Both harnesses:** two entries in the existing Codex `WANT` list.
- **Refresh:** the commit-time refresh exists; F-3 made its installation safe. The chief refreshes
  a stale graph before dispatch, and the session hook names the command.
- **Use:** rules text only. The chief already writes packets, and `affected` is a single command.
- **Measure:** one record. It turns the "worth it?" question into a number before the founder makes
  graphs a default anywhere.

## Rejected options

- **Auto-build a graph when none exists:** it spends LLM tokens without consent, and writes into
  every project.
- **Auto-run `graphify update` in the session hook:** it adds latency to every session start. The
  chief runs it when dispatching, where it pays off.
- **Give judges graphify:** the Claude judge has no shell by design, and judge isolation outranks
  convenience. The chief attaches the output instead.
- **A graph-status script in a budgeted skill:** it would duplicate the hook's checks and spend the
  code budget.
- **graphify's own `install --platform`:** it writes harness config and `CLAUDE.md` outside our
  installer's control.
- **Generate area guides from the graph:** a guide states intent and invariants, which a graph
  cannot supply.
- **`stale-guide` as an ERROR:** a guide can stay correct while its folder's code changes, and an
  error would train agents to make cosmetic touches to guides.
- **An LLM wiki:** a second, unverifiable copy of the truth. The route and the graph are both
  derived from the repository.
