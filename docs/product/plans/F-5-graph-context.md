---
goal: F-5
title: Folder routes and graph-backed context for goal runs
spec: docs/product/specs/F-5-graph-context.md
design: docs/architecture/graph-context.md
status: draft
updated: 2026-10-08
gate: rc=0; for d in execution-methodology agent-personas progressive-disclosure; do [ -d install/skills/$d/tests ] || continue; python3 -m unittest discover -s install/skills/$d/tests -t install/skills/$d/tests || rc=1; done; python3 -m unittest discover -s install/tests -t install/tests || rc=1; exit $rc
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
e2e: python3 install/skills/execution-methodology/tests/smoke_goal.py --harness claude && python3 install/skills/execution-methodology/tests/smoke_goal.py --harness codex && python3 install/tests/smoke_graph_hooks.py --harness claude && python3 install/tests/smoke_graph_hooks.py --harness codex
run: {network: true, session_hours: 2}
grants: [local-commit]
---

# F-5 plan — folder routes and graph-backed context

**Branch.** `v6-followups`, after F-4's `goal/F-4/M1`. Both goals edit `run.md`, the decisions
and the measurements. Only local commits are granted. Merge, push, global install, and any LLM-backed
graph build in a private project are the founder's.

**Commit rules.** Every task commit leaves the gate green and passes the installed pre-commit
route and identifier checks. `tests-may-change` lists exactly the existing tests each task may
edit.

## M1 — folder routes stay true, setup provides the graph, and goal runs use both

criteria: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7
acceptance: [all]
proofs:
- AC-1: python3 -m unittest discover -s install/skills/graph-navigation/tests -t install/skills/graph-navigation/tests
- AC-2: python3 -m unittest discover -s install/tests -t install/tests -p 'test_install.py'
- AC-1, AC-7: python3 -m unittest discover -s install/skills/progressive-disclosure/tests -t install/skills/progressive-disclosure/tests -p 'test_install_hooks_*.py'
- AC-1, AC-2, AC-7: e2e
- AC-6: python3 -m unittest discover -s install/skills/progressive-disclosure/tests -t install/skills/progressive-disclosure/tests -p 'test_validate_disclosure*.py'
- AC-3: python3 -m unittest discover -s install/skills/graph-navigation/tests -t install/skills/graph-navigation/tests
- AC-3, AC-4, AC-5: full_gate

### [ ] T2 — both harnesses get the graph hooks
- writes: install/install.sh, install/verify.sh, install/README.md, install/tests/test_install.py, install/tests/smoke_graph_hooks.py, install/hooks/graphify-query-advisor.py, docs/agents/what-gets-installed.md
- needs: T6, T7
- covers: AC-1, AC-2, AC-6, AC-7
- risk: boundary
- builder: judgement
- tests-may-change: install/tests/test_install.py

Do the following:
- Register `disclosure-check.sh` for Codex at SessionStart, as Claude Code already has it.
- Register the existing `graphify-session-lessons.sh` for Codex at SessionStart, unchanged, as
  Claude Code already has it.
- Add `graphify-query-advisor.py` to the Codex `PreToolUse` list with no matcher. Make the advisor
  read the shell command from both harnesses' payload shapes, and exit silently on any other
  tool.
- Write `install/tests/smoke_graph_hooks.py`, the real-harness proof.
  - For each harness, it builds a fixed fixture under `~/.cache/graph-smoke/<harness>`: a git
    repository with a `graph.json` and saved lessons, and project-level hooks registering
    `disclosure-check.sh`, `graphify-session-lessons.sh` and the advisor.
  - The fixture also has a source folder without a scoped entry file, so `disclosure-check.sh`
    has a finding to report.
  - It runs one short real session and asserts three things: `disclosure-check.sh`'s route
    finding reached the session's context, the lessons digest was injected, and a prose
    `graphify query` drew the advisor's ladder.
  - When the real `graphify` is on PATH, it also checks AC-1 and AC-7 against graphify itself,
    and is the only owner of the cross-worktree check. In a throwaway repository with a graph in
    the main checkout and two linked worktrees, using a temporary HOME, it runs
    `graph_view.py setup` in worktree A: A gets its own graph, and the guarded hooks are in the
    shared hooks directory. A commit in worktree B then leaves A's graph and the main checkout's
    unchanged. Without graphify, this part prints a skip line and passes.
  - `--prepare` builds the Codex fixture and prints the one-time trust step, as `smoke_goal.py`
    does. That step is the founder's (see Grants).
- Update the installer tests for both harnesses, and the two docs that list installed hooks.

`risk: boundary` applies because the installer writes the founder's harness configuration.

### [ ] T7 — hooks install without a graph in the main checkout, and `--graph-only`
- writes: install/skills/progressive-disclosure/scripts/install_hooks.py, install/skills/progressive-disclosure/tests/test_install_hooks_scope.py, install/skills/progressive-disclosure/tests/test_install_hooks_graph_only.py
- needs: —
- covers: AC-1, AC-7, AC-5
- risk: safety
- builder: judgement
- tests-may-change: install/skills/progressive-disclosure/tests/test_install_hooks_scope.py

Drop `install_graph_hook`'s requirement that the main checkout has a graph at its root; F-3 M4's
guard makes the blocks no-ops wherever no graph exists. The child-graph skip stays: with a graph
only under a child, nothing is installed. Add `--graph-only`, which runs only `install_graph_hook`
and touches no other hook, and refuse it with `--uninstall`, `--check`, `--scope` or `--public`.

Keep, unchanged, each for its F-3 reason:
- writes only through `_commit_hook`, `_destination_error` and `_commit_file` (T9 security,
  rounds 1–2);
- rendering in the sandbox with `GIT_*` dropped (T9 security, round 3);
- install only when `core.hooksPath` is unset, with the query dropping the repository-location
  variables and `GIT_CONFIG` (M4, rounds 3–4);
- the guard before every graphify block, existing blocks guarded in place, and the child-graph
  skip (M4, after the tag);
- `--uninstall` stripping through the checked path whatever `core.hooksPath` says;
- `graphify_root`'s exclusions;
- our own pre-commit, commit-msg and pre-push hooks, untouched (F-3 Q7).

`test_install_hooks_scope.py` changes only where it asserts "skipped — no graph". The new
`test_install_hooks_graph_only.py` uses real git, a temporary HOME and a stub `graphify`. It
covers:
- installing from a main checkout without a graph, which writes the guarded blocks;
- the child-graph skip, still installing nothing;
- `--graph-only`, which writes only `post-commit` and `post-checkout` and leaves existing
  `pre-commit`, `commit-msg` and `pre-push` content byte for byte;
- `--graph-only` with `core.hooksPath` configured, which writes nothing;
- each refused combination, which exits nonzero and writes nothing.

The cross-worktree check is T2's smoke, against real graphify. The change is about 15 non-test
lines. `risk: safety` applies because the change widens where git
hooks are written: every project with graphify installs them.

### [ ] T3 — the setup, dispatch and acceptance steps
- writes: install/skills/execution-methodology/references/context.md, install/skills/execution-methodology/references/run.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/review.md, install/skills/execution-methodology/references/migrate.md
- needs: T5, T6
- covers: AC-1, AC-3, AC-5, AC-6
- risk: none
- builder: routine
- tests-may-change: —

Write the design's Rules-text section:
- the setup step in `run.md`'s Starting steps, and its sentence in `migrate.md`'s step 4;
- the route step in `run.md`'s dispatch step, plus a pointer to `context.md`;
- the guides sentence in `review.md`'s Acceptance section;
- the update rule in `planning.md`, as one sentence;
- `context.md` itself, graph-only, at most 450 words: graph calls go only through
  `graph_view.py`, and a fallback line from it means the route and grep.

`run.md`'s additions are offset by trims in `run.md` that lose no rule. Without a graph, every
role's load must stay at or under 3,000 words. Verify with `install/tests/test_size.py`.

### [ ] T5 — the `stale-guide` warning
- writes: install/skills/progressive-disclosure/scripts/validate_disclosure.py, install/skills/progressive-disclosure/tests/test_validate_disclosure_stale_guide.py
- needs: —
- covers: AC-6, AC-5
- risk: none
- builder: routine
- tests-may-change: —

Implement the design's `stale-guide` interface. It reuses the existing scoped-entry discovery and
link parsing.

The tests use temporary git repositories and cover:
- a guide behind its folder's code, which warns with the count;
- a guide updated after the code, which is silent;
- doc-only commits to the folder, which are silent;
- an uncommitted guide, and a directory outside a git repository, which are both skipped;
- that the check never raises an ERROR and never changes the exit code by itself.

`progressive-disclosure` stays at or under its AC-13 ceiling of 5,470 lines, together with T7.

### [ ] T6 — the bounded graph runner and graph setup
- writes: install/skills/graph-navigation/scripts/graph_view.py, install/skills/graph-navigation/tests/test_graph_view.py, install/skills/graph-navigation/SKILL.md
- needs: T7
- covers: AC-1, AC-3
- risk: none
- builder: routine
- tests-may-change: —

Implement the design's `graph_view.py setup` and `graph_view.py view` interfaces. Their tests use
temporary repositories and a stub `graphify`.

`setup` tests cover:
- graphify missing, which prints its line and does nothing else;
- no graph, which runs `graphify update .`; a graph at the root, or under a child, which builds
  nothing; a `graph.json` that does not parse, which counts as no graph;
- a hanging build, which times out (the bound shortened for the test), prints the manual line and
  continues;
- missing or unguarded refresh hooks, which run `install_hooks.py --graph-only` on the main
  checkout, from the main checkout and from a linked worktree;
- `core.hooksPath` configured, and a child graph, which print their lines and install nothing;
- an inherited `GIT_DIR` pointing elsewhere, and `GIT_CONFIG` pointing at an empty file while
  `GIT_CONFIG_COUNT` sets `core.hooksPath`, which do not change the answer;
- exit 0 in every case, and `graph ready` when nothing is needed.

`view` tests cover:
- a fresh graph, which writes a file per symbol;
- a stale graph, where `update` runs first;
- no graph, and graphify missing, each of which prints a fallback line;
- a hanging `update`, and a hanging `affected`, each of which times out and falls back, with the
  timeouts shortened for the test;
- exit 0 in every case;
- no writes outside `--out` and `graphify-out/`.

Add one line to `SKILL.md` naming `setup` and `view` for goal runs.

### [ ] T4 — measurements and records
- writes: docs/product/measurements.md, docs/decisions/decisions.md, docs/architecture/lean-execution.md
- needs: T2, T3, T5, T6, T7
- covers: AC-4
- risk: none
- builder: routine
- tests-may-change: —

**Measure.** In a temporary copy of this repository, never the checkout:
- build a code graph;
- time `graphify update .` after a one-file change;
- record the node and edge counts;
- record the size, in lines and characters, of `graphify affected` output for three symbols:
  `install_graph_hook`, `admit` and `verify`.

Record them dated under "graphify on this repository".

**Records.**
- `decisions.md`: D29, folder routes kept true plus graph-backed context, with its reason and the
  alternatives it beat.
- **Also measure:** `stale-guide` findings on this repository at HEAD, as a count.
- `lean-execution.md`: the graph's place in dispatch and acceptance, as current state.

## Grants requested

- `local-commit` on `v6-followups`.
- **A founder action, once:** trust the Codex graph-smoke fixture's hooks in Codex
  (`smoke_graph_hooks.py --harness codex --prepare` prints the step). This is the same kind of
  step as F-3 Q1. Until it is done, the Codex half of the e2e stops early with that instruction.

## Decisions

- 2026-10-08: founder decisions at the approval presentation. Design and plan each get one
  founder-granted confirmation review (round 3) of the round-2 corrections and of the edit that
  aligns the hooks query with F-3 M4 (`GIT_CONFIG` dropped); approval follows if both pass. The
  with-graph role-load exception (about 3,450 words) stated in the spec is accepted.

- 2026-10-08: founder decisions on design round 3, which blocked because the install command did
  not work from a linked worktree whose main checkout had no graph.
  - The founder chose the per-worktree model, verified with graphify 0.8.49 and git 2.54: each
    worktree keeps its own untracked graph, and the shared hooks refresh only the committing
    worktree's graph.
  - Hooks refresh only an existing graph at the worktree root, through a guard that
    `install_hooks.py` writes before graphify's blocks. This closes the partial-graph hazard the
    verification found. On the founder's instruction the guard moved into F-3 M4 the same day,
    because M4's installer already writes graphify's blocks; F-5's T7 keeps only installing
    without a graph in the main checkout (AC-7).
  - The installer installs without a graph in the main checkout, which closes the round-3 finding.
  - Area guides stay route and intent, with no key-symbol lines and no per-worktree state.
  - Design and plan each get one more founder-granted confirmation review (round 4) before
    approval.

- 2026-10-08: founder direction after the per-worktree redraft: graphify setup belongs to
  execution-methodology setup, not to a hook that checks every session. T1 and
  `graphify-session.py` are dropped; `graphify-session-lessons.sh` stays as it is. Setup is
  `graph_view.py setup` (T6), run by `run.md`'s Starting steps and `migrate.md`'s step 4 (T3); it
  installs refresh hooks through a new `install_hooks.py --graph-only` (T7), because the full
  installer also rewrites the other hooks, which migration owns. The round-4 confirmation review
  of design and plan is still pending before approval.

## Queue
