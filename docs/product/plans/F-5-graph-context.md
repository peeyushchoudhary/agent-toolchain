---
goal: F-5
title: Folder routes and graph-backed context for goal runs
spec: docs/product/specs/F-5-graph-context.md
design: docs/architecture/graph-context.md
status: draft
updated: 2026-10-08
gate: rc=0; for d in execution-methodology agent-personas progressive-disclosure graph-navigation; do [ -d install/skills/$d/tests ] || continue; python3 -m unittest discover -s install/skills/$d/tests -t install/skills/$d/tests || rc=1; done; python3 -m unittest discover -s install/tests -t install/tests || rc=1; exit $rc
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

**Milestone close.** The `e2e`'s two Codex smokes, `smoke_goal.py --harness codex` and
`smoke_graph_hooks.py --harness codex`, have Codex trust bound to the main checkout's path (F-3
Queue Q6). Run the `e2e` receipt from the main checkout, detached at F-5's head, then copy the
receipt into this worktree's `.runs/F-5/receipts/`, as F-4 did. Both checkouts hold the same
committed tree at that commit.

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
    and is the only owner of the cross-worktree check. In a throwaway repository that ignores
    `/graphify-out/`, with a graph in
    the main checkout and two linked worktrees, using a temporary HOME, it runs
    `graph_view.py setup` in worktree A: A gets its own graph, and the guarded hooks are in the
    shared hooks directory. A second setup in A prints `graph ready` and rebuilds nothing. A
    commit in worktree B then leaves A's graph and the main checkout's unchanged. Without
    graphify, this part prints a skip line and passes.
  - The Codex fixture's hook commands name this checkout's own `install/` paths, as
    `smoke_goal.py`'s do, so a pass proves the checked-out code. The trust is therefore bound to
    the checkout's path, which the milestone-close step handles.
  - Its trust pre-check compares the hook hash Codex stored for each fixture hook with the hash of
    the fixture's current hook entry, not only the key, and reports the fixture untrusted on a
    mismatch, so a stale trust is reported instead of the hooks being skipped silently. T2
    confirms how Codex computes that hash in the real-harness run and fixes it in a test.
  - `--prepare` builds the Codex fixture and prints the one-time trust step, as `smoke_goal.py`
    does. That step is the founder's (see Grants).
- Update the installer tests for both harnesses, and the two docs that list installed hooks.

`risk: boundary` applies because the installer writes the founder's harness configuration.

### [ ] T7 — hooks install without a graph in the main checkout, and `--graph-only`
- writes: install/skills/progressive-disclosure/scripts/install_hooks.py, install/skills/progressive-disclosure/tests/test_install_hooks_scope.py, install/skills/progressive-disclosure/tests/test_install_hooks_graph_only.py, install/skills/progressive-disclosure/tests/test_install_hooks_guard.py
- needs: —
- covers: AC-1, AC-7, AC-5
- risk: safety
- builder: judgement
- tests-may-change: install/skills/progressive-disclosure/tests/test_install_hooks_scope.py, install/skills/progressive-disclosure/tests/test_install_hooks_guard.py

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

It also closes F-3 Queue Q8: the uninstall cells of `test_install_hooks_guard.py`'s mode matrix
start from a guarded fixture too, so they prove an existing guard is removed.

### [ ] T3 — the setup, dispatch and acceptance steps
- writes: install/skills/execution-methodology/references/context.md, install/skills/execution-methodology/references/run.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/references/review.md, install/skills/execution-methodology/references/migrate.md
- needs: T5, T6
- covers: AC-1, AC-3, AC-5, AC-6
- risk: none
- builder: routine
- tests-may-change: —

Write the design's Rules-text section:
- the setup step in `run.md`'s Starting steps, and its sentence in `migrate.md`'s step 4;
- `/graphify-out/` beside `/.runs/` in `migrate.md`'s step-4 `.gitignore` bullet;
- the route step in `run.md`'s dispatch step, plus a pointer to `context.md`;
- the guides sentence in `review.md`'s Acceptance section;
- the update rule in `planning.md`, as one sentence;
- `context.md` itself, graph-only, at most 450 words: graph calls go only through
  `graph_view.py`, `view` applies the trust rule and its forced refresh, and a fallback line from
  it means the route and grep.

**Word budget.** `run.md`'s role load is 2,999 of 3,000 words at `goal/F-4/M1`. Every word T3 adds
to `run.md` is offset by a trim in `run.md` that loses no rule. The builder's report lists each
trim beside the rule it keeps, so acceptance can check that none is lost. Without a graph, every
role's load must stay at or under 3,000 words, and so must `context.md`'s own load (`SKILL.md`,
`methodology.md` and `context.md`, 1,545 words before it). Verify with
`install/tests/test_size.py`.

T3 adds no code: `execution-methodology` plus `agent-personas` stays at 2,500 of 2,500 lines.

### [ ] T5 — the `stale-guide` warning
- writes: install/skills/progressive-disclosure/scripts/validate_disclosure.py, install/skills/progressive-disclosure/tests/test_validate_disclosure_stale_guide.py, install/tests/test_size.py
- needs: —
- covers: AC-6, AC-5
- risk: none
- builder: routine
- tests-may-change: install/tests/test_size.py

Implement the design's `stale-guide` interface. It reuses the existing scoped-entry discovery and
link parsing.

The tests use temporary git repositories and cover:
- a guide behind its folder's code, which warns with the count;
- a guide updated after the code, which is silent;
- doc-only commits to the folder, which are silent;
- an uncommitted guide, and a directory outside a git repository, which are both skipped;
- that the check never raises an ERROR and never changes the exit code by itself.

`test_size.py`'s AC-13 ceiling changes from 5,470 to 5,520, and only that number changes; with
T7, `progressive-disclosure` stays at or under it. Expected: 5,453 at `goal/F-4/M1`, plus about 30
here and about 15 in T7, about 5,500 of 5,520. The amendment adds no `progressive-disclosure`
code.

### [ ] T6 — the bounded graph runner and graph setup
- writes: install/skills/graph-navigation/scripts/graph_view.py, install/skills/graph-navigation/tests/test_graph_view.py, install/skills/graph-navigation/SKILL.md, .gitignore
- needs: T7
- covers: AC-1, AC-3
- risk: none
- builder: judgement
- tests-may-change: —

Implement the design's `graph_view.py setup` and `graph_view.py view` interfaces: the step order
(guard first, the ignore check, then trust), the trust rule, the stamp, the pending marker, and
the command (cwd at the graph root, `update . --force`, every `GRAPHIFY_*` dropped). Add
`/graphify-out/` to this repository's `.gitignore`, beside `/.runs/`, with a one-line reason;
setup requires the graph directory to be ignored.

The stub-`graphify` tests use temporary repositories, a temporary HOME, and a stub that records
its cwd, argv and environment. Like graphify, it writes its path argument into `.graphify_root`
before it writes `graph.json`.
Simpler than graphify, it refuses with exit 1 any graph with fewer nodes than the existing one
unless `--force` is given; the oracle test below pins graphify's real rule. Like graphify, it
exits 0 and leaves `graph.json` untouched when the code graph is unchanged.

`setup` tests cover:
- graphify missing, which prints its line and does nothing else;
- no graph, which runs `update . --force` with its cwd at the worktree root; a `graph.json` that
  does not parse, which counts as no graph;
- the trust rule: a HEAD-built graph with the guard in place, which builds nothing and prints
  `graph ready`; `built_at_commit` not HEAD, which rebuilds; `.graphify_root` absent, which trusts,
  and `.graphify_root` holding an absolute path or `sub`, which rebuilds;
- a child graph, rebuilt with its cwd at the child and `.` as the path, never `<child>`;
- the guard missing, then the rebuild: with a HEAD-built graph and unguarded hooks,
  `install_hooks.py --graph-only` runs before the rebuild, and the rebuild runs whatever the graph
  says; a second setup then finds the guard and builds nothing;
- the pending marker: a guard-forced rebuild that times out leaves `.graphify_root` reading
  `rebuild-pending` and `graph.json` unchanged, also when the stub replaced the marker with `.`
  before hanging, and the next setup rebuilds; a guard-forced rebuild that succeeds leaves `.`,
  and the next setup builds nothing; `view` over a marked graph whose refresh fails leaves the
  marker;
- `graphify-out/` not ignored, at the root and for a child graph: setup prints the entry, builds
  nothing and exits 0; the test then adds exactly the printed entry to `.gitignore`, reruns setup,
  and the line is gone (planning.md's tested-fix-command rule). Every other test's repository
  ignores `graphify-out/`;
- missing or unguarded refresh hooks, which run `install_hooks.py --graph-only` on the main
  checkout, from the main checkout and from a linked worktree;
- `core.hooksPath` configured, and a child graph, which print their lines, install nothing and
  never fire the guard trigger;
- a hanging build, which times out (the bound shortened for the test), prints the manual line and
  continues; a failing build, which prints its line;
- the printed fix command: after a timed-out build, running `graphify update . --force` in the
  printed directory over a graph that shrank, then setup again, prints `graph ready`
  (planning.md's tested-fix-command rule); over a graph the command leaves unchanged, the next
  setup rebuilds once and writes the stamp, and the setup after it prints `graph ready`;
- the stamp: after a non-code commit, where the stub exits 0 and leaves `graph.json` and
  `built_at_commit` unchanged, setup rebuilds once and writes `.graph_view_head` holding HEAD's
  full commit id, and the next setup trusts the graph without rebuilding; `view` does the same;
  a failed or timed-out rebuild writes no stamp, and the next setup rebuilds;
- every inherited `GRAPHIFY_*` variable, `GRAPHIFY_OUT` among them, absent from the stub's
  environment;
- an inherited `GIT_DIR` pointing elsewhere, and `GIT_CONFIG` pointing at an empty file while
  `GIT_CONFIG_COUNT` sets `core.hooksPath`, which do not change the answer;
- exit 0 in every case.

`view` tests cover:
- a fresh graph, which writes a file per symbol;
- a stale graph, where `update . --force` runs first from the graph root;
- `view` stale with a shrink: a new commit whose rebuild has fewer nodes, which the stub refuses
  without `--force`; the refresh writes the smaller graph, `built_at_commit` is HEAD, and the next
  `view` runs no `update`;
- no graph, and graphify missing, each of which prints a fallback line;
- a hanging `update`, and a hanging `affected`, each of which times out and falls back, with the
  timeouts shortened for the test;
- exit 0 in every case;
- no writes outside `--out` and `graphify-out/`.

**Oracle test** (planning.md's oracle-test rule). When the real `graphify` is on PATH, one test
runs it under setup's environment (cwd at the graph root, `GRAPHIFY_*` dropped, a temporary HOME)
in a temporary git repository. It builds a graph, injects a node without `_origin` into
`graph.json`, and runs `graphify update . --force`. It asserts that the node survives, that
`.graphify_root` reads `.`, and that `built_at_commit` is HEAD. It then builds a rebuild that
graphify's shrink check refuses, and asserts that `update .` without `--force` exits 1 and leaves
`graph.json` unchanged, while `update . --force` writes the smaller graph. In graphify 0.8.49 a
deleted file does not trip the check (`_check_shrink` exempts explicit deletions and nodes of
re-extracted files); an injected node marked `_origin: ast` whose `source_file` is an existing
non-code file does. It writes `rebuild-pending` into `.graphify_root`, runs `update . --force`,
and asserts that `.graphify_root` reads `.` afterwards. It commits a change to a non-code file,
runs `graph_view.py setup`, and asserts that `update . --force` exits 0 with `built_at_commit`
unchanged (the reproduction in Decisions), that `.graph_view_head` holds HEAD's full commit id,
and that a second setup prints `graph ready`. It finally runs the timeout line's command and
shows the next setup ends trusted, as the stub test does. Without graphify, it prints a skip line
naming why.

Add one line to `SKILL.md` naming `setup` and `view` for goal runs.

Expected size: `graph_view.py` about 265 lines. No ceiling in `test_size.py` covers
`graph-navigation`.

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

**Rebuild cost.** Add a section headed `graphify rebuild cost — 2026-10-08` (level 2) to
`measurements.md`, with the body below as written. Its figures were measured before F-5 on
clones, and repositories are named only by size.

```markdown
A full `graphify update` (code only, no LLM) and a freshness check, timed on a 15-core laptop.
No LLM tokens are used; the cost is wall-clock time and memory.

| Repository | Code files | Full update | Freshness check | Peak memory |
|---|---|---|---|---|
| small | 49 | ~1 s | 0.04 s | 118 MB |
| medium | 402 | ~10–13 s | 0.11 s | ~800 MB |
| large | 2,932 | 44–59 s | 0.25 s | up to 1.6 GB |

- A warm update costs the same as a cold one.
- On the large repository, without `--force`, the update exits 1 and writes nothing when the
  rebuild has fewer nodes.
- A real hook log on one machine showed 44 of 1,928 background rebuilds refused this way.
```

**Records.**
- `decisions.md`: D29, folder routes kept true plus graph-backed context, with its reason and the
  alternatives it beat. It states setup's guard-first trust rule, and that this repository
  ignores `graphify-out/` wholesale while D11's split stays a project's option.
- **Also measure:** `stale-guide` findings on this repository at HEAD, as a count.
- `lean-execution.md`: the graph's place in dispatch and acceptance, as current state.

## Grants requested

- `local-commit` on `v6-followups`.
- **A founder action, once:** trust the Codex graph-smoke fixture's hooks in Codex
  (`smoke_graph_hooks.py --harness codex --prepare` prints the step). This is the same kind of
  step as F-3 Q1. Until it is done, the Codex half of the e2e stops early with that instruction.
  The trust is bound to the main checkout's path, from which the milestone-close step runs.

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

- 2026-10-08: founder decisions on design and plan round 4, which blocked on a partial graph left
  by an older unguarded hook (setup trusted it), on `GRAPHIFY_OUT` reaching graphify from setup,
  on T7's write set missing the guard test, and on the line budget (17 lines of headroom after F-3
  M4, not 112). Corrections: setup always runs a full `graphify update` (superseded below by the
  trust rule); graphify calls drop `GRAPHIFY_*`; T7 writes the guard test. The founder raised
  `progressive-disclosure`'s AC-13 ceiling to 5,520 (T5 changes `test_size.py`) and approved F-5
  as corrected, without a further round. `goal/F-5/approved` is placed when F-5 starts, on the
  commit after `goal/F-4/M1`, because F-5 runs after F-4 on this branch and its frozen-input base
  must follow F-4's commits; F-5's documents are unchanged in between (superseded below by the
  amendment's sequence).

- 2026-10-08: founder decisions on the amendment, before F-5 starts (the setup-step decision is
  also in the F-4 plan's Decisions).
  - **Trust rule.** Setup rebuilds only when the graph is missing, its `built_at_commit` is not
    HEAD, or `.graphify_root` is neither absent nor `.`, and the rebuild passes `--force`. This
    replaces "setup always runs a full update": a full update costs 44–59 s on a large repository,
    and without `--force` it can exit 1 without writing.
  - **Partial-graph protection.** Setup checks and installs the guard first. A guard missing at
    this setup forces one full rebuild, whatever the graph says; later setups trust a HEAD-built
    graph. This keeps the protection the round-4 "always" correction gave, because a partial graph
    left by an older unguarded hook has `built_at_commit` equal to HEAD.
  - **`.gitignore`.** This repository ignores `/graphify-out/` wholesale, and `migrate.md`'s step 4
    adds it next to `/.runs/`. D11's split stays an option for projects that want it. Without the
    ignore, setup's `graphify-out/` makes every receipt "tree not clean" and every guard "outside
    writes".
  - **Grants.** The root-cause analysis of repeated grants is done; its R1–R4 go to a later goal.
    The amendment gets one founder-granted design and plan review under the current practice, with
    the used grants archived first.

- 2026-10-08: the amendment's defaults, from an independent plan evaluation. Each is reversible
  and inside the outcome.
  - (default) Every graphify call runs with its cwd at the graph root, argv `update . --force` for
    a rebuild, and every `GRAPHIFY_*` dropped, over passing the root's path: graphify writes the
    path as typed into `.graphify_root`. AC-1's fix command is `graphify update . --force`, over
    one that can exit 1 on a shrink.
  - (default) `view`'s refresh uses the same trust rule and forced command (AC-3), over a plain
    `update` that can leave every `view` failing for the rest of the goal.
  - (default) `--force` keeps semantic nodes; T6's oracle test checks it against real graphify and
    skips with a line without it. The plan pins graphify 0.8.49's shrink rule in that test, after
    finding that a plain deletion is exempt from the check.
  - (default) The design's cache and incremental statements are removed; the spec's Journey 1,
    AC-1, the design's Structure row and step table, and T6 state one rule.
  - (default) The rebuild-cost measurements go into `measurements.md` through T4's text.
  - (default) The `gate:` loop includes `graph-navigation`.
  - (default) The `e2e` receipt is run from the main checkout, detached at F-5's head, and copied
    into this worktree's `.runs/F-5/receipts/` (F-3 Queue Q6).
  - (default, corrected by the controller) T2's Codex fixture builds its hook commands from the
    checkout's own `install/` paths, as `smoke_goal.py` does, over installed paths. Installed paths
    would make the founder's global install a precondition of closing the milestone, before
    merge. The milestone-close `e2e` runs from the main checkout instead, and the hash-comparing
    trust pre-check stays, so a stale trust is reported, not skipped.
  - (default) `.gitignore` goes in T6, which brings in setup; T6's builder is `judgement`, over
    `routine`, because it carries the trust rule and an oracle test.
  - (default) T3 offsets every `run.md` addition with a trim that loses no rule; `run.md` is at
    2,999 of 3,000 words.
  - (default) Setup prints `graph rebuilt: <reason>` on a rebuild and a failure line on a nonzero
    exit, and its fix line names the graph root it must run in.
  - (default) Under `core.hooksPath`, or with a child graph, setup installs nothing and applies the
    trust rule alone; hooks under `core.hooksPath` stay F-3 Queue Q7's.
  - (default, corrected by the controller) Before a rebuild forced by a missing guard, setup
    writes `rebuild-pending` into `.graphify_root`. A finished rebuild leaves `.`, so an unfinished
    one is retried by the next setup and skipped by the hook guard. graphify replaces
    `.graphify_root` before it writes the graph, so setup, and `view` when it read the marker,
    write it again after a timeout or failure.
  - (default, adopted by the controller) After a rebuild that exits 0, setup and `view` write
    HEAD's full commit id to `graphify-out/.graph_view_head`. The stale trigger becomes "neither
    `built_at_commit` nor the stamp equals HEAD"; the guard, no-graph and `.graphify_root`
    triggers (`rebuild-pending` included) are unchanged. A timeout or failure writes no stamp.
    This was chosen over trusting `built_at_commit` alone and over diffing extracted files since
    it. In graphify 0.8.49, a forced update that finds the code graph unchanged does not advance
    `built_at_commit`, so trusting it alone rebuilds at every setup after a non-code commit.
    Diffing still loops after prose-only Markdown edits, which graphify extracts as code. The
    stamp records that this checkout's graph was rebuilt, or confirmed, at HEAD. It lives in the
    ignored `graphify-out/`. Evidence, 2026-10-08: in a throwaway repository with a temporary HOME,
    after a commit to a non-code file, `graphify update . --force` exited 0 and `built_at_commit`
    stayed at the earlier commit.
  - (default, corrected by the controller) Setup runs `git check-ignore -q` on the graph root's
    `graphify-out/`. When it is not ignored, setup prints the `.gitignore` entry to add, builds
    nothing and exits 0.

- 2026-10-08: approval-tag sequence for the amendment, superseding the round-4 entry's placement
  sentence, which said F-5's documents are unchanged between `goal/F-4/M1` and the approved tag.
  The sequence is: the amendment commits; the founder-granted design and plan review runs;
  the founder re-approves; `goal/F-5/approved` goes on the re-approved commit; a baseline is
  recorded; F-5 starts.

## Queue

- (a) (blocks nothing; founder decides later) In adopting projects that commit
  `graphify-out/reflections/`, graphify's post-commit hook rewrites `reflections/LESSONS.md` in the
  background. A commit just before a review or receipt can then make the round exit 2 on drift, or
  fail the receipt with "the run changed the working tree". Options: ignore `graphify-out/`
  wholesale, as this repository does; or stop committing `reflections/`. Either supersedes part of
  D11. Recommendation: ignore wholesale, which matches this repository and `migrate.md`'s step 4.
- (b) (blocks nothing; founder decides later) graphify's own hook never passes `--force`, so a
  hook-refreshed graph refuses some shrinks and goes stale: 44 of 1,928 in a real log. Options:
  `migrate.md`'s step 4 advises `GRAPHIFY_FORCE=1` in the hook environment; or rely on setup and
  `view` forcing. Recommendation: rely on setup and `view`, because a refused refresh leaves
  `built_at_commit` behind HEAD, which their trust rule already rebuilds.
