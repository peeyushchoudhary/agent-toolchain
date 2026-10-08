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
- AC-1, AC-7: python3 -m unittest discover -s install/skills/graph-navigation/tests -t install/skills/graph-navigation/tests
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
- needs: T5, T6, T7
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
  - The fixture also has a source folder whose scoped entry file links an area guide, with one
    commit to a non-doc file in that folder after the guide's last commit, so this tree's
    `stale-guide` has a finding to report.
  - **This checkout's validator, by a HOME override inside the hook command.**
    `disclosure-check.sh` loads its validator from `$HOME/.claude/skills/progressive-disclosure/`,
    so an installed copy that predates T5 would answer instead of this tree. At every run the
    smoke copies this checkout's `install/skills/progressive-disclosure/` afresh to
    `<fixture-home>/.claude/skills/progressive-disclosure/`, and the fixture registers the hook
    as `env HOME=<fixture-home> bash <checkout>/install/hooks/disclosure-check.sh`. Only the hook
    process sees that HOME; the harness keeps its own, so its login is untouched, and the command
    string stays fixed, so Codex's stored trust hash still matches.
  - It runs one short real session and asserts three things: the line
    `stale-guide <guide>: 1 commit(s) to <folder> since the guide last changed` reached the
    session's context, the lessons digest was injected, and a prose `graphify query` drew the
    advisor's ladder. No pre-existing route warning satisfies the first assertion, because no
    validator before T5 prints `stale-guide`.
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
  `graph_view.py`; graph output is advisory, and dispatch checks it against the code with grep or
  a read before relying on it; `view` labels the graph and never rebuilds it, and
  `view --refresh` rebuilds only when asked; a fallback line from it means the route and grep.

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
- covers: AC-1, AC-3, AC-7
- risk: safety
- builder: judgement
- tests-may-change: —

Implement the design's `graph_view.py setup` and `graph_view.py view` interfaces: the step order
(hooks, the ignore check, then the build), the advisory contract A1–A6, the printed commands and
the one failure line, `--no-bound`, `view`'s label, single read and `--refresh`, and the command
(cwd at the graph root, `update . --force`, every `GRAPHIFY_*` dropped). Add `/graphify-out/` to
this repository's `.gitignore`, beside `/.runs/`, with a one-line reason; setup requires the
graph directory to be ignored. `risk: safety` applies because a build writes through any
symlinked artifact, which A5's refusal closes.

The stub-`graphify` tests use temporary repositories, a temporary HOME, and a stub that records
its cwd, argv and environment. Like graphify 0.8.49, it writes its path argument into
`.graphify_root` first, then `graph.json` with `built_at_commit` and `GRAPH_REPORT.md`, writing
through symlinks as `Path.write_text` does, and it can be told to hang or fail after writing
`.graphify_root`. Its `explain` and `affected` honour `--graph <path>` and print the
`built_at_commit` they read. Simpler than graphify, it refuses with exit 1 any graph with fewer
nodes than the existing one unless `--force` is given; the oracle test below records graphify's
real rule.

Tests in `test_graph_view.py`, each named:
- **Labels (A4).**
  - `test_label_behind_by_n`: a graph built at an ancestor with three commits since prints
    `graph built at <A> (3 commits behind HEAD); advisory — confirm with grep`, on stdout and as
    the first line of every output file.
  - `test_label_ahead_of_head`: a graph built at a descendant of HEAD (HEAD checked out two
    commits back) prints `(0 commits behind HEAD, 2 ahead)`.
  - `test_label_diverged`: a graph built on a branch with two commits HEAD lacks, HEAD three
    commits past the merge base, prints `(3 commits behind HEAD, 2 ahead)`.
  - `test_label_unknown_commit`: `built_at_commit` missing, and set to a commit git does not know,
    each print `graph build commit unknown; advisory — confirm with grep`.
  - `test_label_full_build_at_head`: a stamp whose `head` is HEAD and whose `sha256` matches adds
    `full build by setup at HEAD`; a mismatched sha256, or a stamp at an older commit, does not.
- **One read (A4).** `test_view_single_read`: the stub's `explain` replaces `graph.json` with a
  graph built at another commit before it answers; the label, the stamp comparison and every
  result still name the first read's `built_at_commit`, the stub received `--graph` naming a
  snapshot outside the repository, and the snapshot is gone after `view` exits.
- **No automatic rebuild (A4).** `test_view_never_rebuilds_on_its_own`: over a graph 50 commits
  behind, an unparsable stamp and a missing stamp, `view` runs no `update` and writes no stamp.
- **`--refresh` (A4).** `test_view_refresh_rebuilds_and_stamps`: runs one `update . --force` from
  the graph root, writes the stamp, and the label then adds `full build by setup at HEAD`; with
  no symbols it only refreshes. `test_view_refresh_failure_line`: a hanging refresh (bound
  shortened), and separately a failing one, each delete the old stamp, write none, print
  `graph build <reason>; retry with: python3 <graph_view.py> view --root <worktree> --refresh
  --out <dir> <Symbol> --no-bound` and go on with the existing graph; running the printed
  command writes the stamp and the symbol's file (planning.md's tested-fix-command rule).
- **A2's triggers, each building once and stamping:** `test_setup_builds_without_graph`,
  `test_setup_builds_unparsable_graph`, `test_setup_builds_foreign_graphify_root` (an absolute
  path, and `sub`), `test_setup_builds_without_stamp` (a parsing graph at HEAD with no stamp, and
  one with an unparsable stamp).
- **The no-build control.** `test_setup_no_build_with_stamp`: a parsing graph, `.graphify_root`
  absent or `.`, and a stamp, even with the graph 20 commits behind HEAD and a sha256 that no
  longer matches; setup runs no `update` and prints `graph ready`.
- **The one failure line (A2, design's Printed commands).** `test_setup_timeout_writes_no_stamp`:
  a hanging build (bound shortened) writes no stamp and prints
  `graph build timed out after <s> s; retry with: python3 <graph_view.py> setup --root
  <worktree> --no-bound`; running that printed command writes the stamp, and a further setup
  prints `graph ready` (tested-fix-command rule). `test_setup_failure_line`: a failing build
  prints the same line with `failed (exit <n>)` and the same retry command; the retry, once the
  stub is fixed, writes the stamp.
- **Stale stamp after a failed build (A2).** `test_failed_build_deletes_old_stamp`: a valid stamp
  from an earlier build and a foreign `.graphify_root` start a build; the stub writes `.` into
  `.graphify_root` and then fails, once with a nonzero exit and once by hanging past the bound.
  Each time no stamp remains, and the next setup builds again (its reason names the missing
  stamp) instead of printing `graph ready`.
- **`--root` in the fix line.** `test_fix_line_repeats_root`: `setup --root B`, run from worktree
  A, times out on B's build; the printed command names `--root <B>`, running it from A writes B's
  stamp, and A's graph directory is unchanged. The same holds for the ignore line and the symlink
  line, each run from A with `--root B`.
- **Symlinked artifacts (A5).** `test_symlinked_artifact_refused`: `graphify-out/GRAPH_REPORT.md`
  is a symlink to a tracked file. Setup, and `view --refresh`, each print
  `graph build refused: <path> is a symlink; remove it, then rerun: <rerun>`, run no `update`,
  leave the old stamp and the tracked file byte for byte, and exit 0; the tree is clean. The same
  refusal holds when `graphify-out/` itself is a symlink to a directory outside the repository,
  with `.gitignore` ignoring `/graphify-out` so the ignore check passes, and nothing is written in
  the target. Removing the symlink and running the printed command builds and writes the stamp
  (tested-fix-command rule).
- **Both hooks checked (A3, AC-7).** `test_setup_checks_post_checkout_guard`: `post-commit`
  carries the guard immediately before graphify's block while `post-checkout` has graphify's
  block unguarded; setup runs `install_hooks.py --graph-only`, and both hooks then carry the
  guard. With both guarded, setup installs nothing.
- **Ignore check (A5), both commands.** `test_setup_unignored_writes_nothing` and
  `test_view_unignored_writes_nothing`, at the root and for a child graph: each prints the entry
  line, writes nothing under the graph directory, leaves tracked graph artifacts byte for byte,
  and exits 0; `view` falls back to its no-graph output, also with `--refresh`. The setup test
  then adds exactly the printed entry to `.gitignore`, reruns setup, and the line is gone
  (tested-fix-command rule). Every other test's repository ignores `graphify-out/`.

The other `setup` tests cover:
- graphify missing, which prints its line and does nothing else;
- a build with its cwd at the worktree root when there is no graph;
- a child graph, built with its cwd at the child and `.` as the path, never `<child>`;
- missing or unguarded refresh hooks, which run `install_hooks.py --graph-only` on the main
  checkout, from the main checkout and from a linked worktree; `core.hooksPath` configured, and a
  child graph, which print their lines and install nothing (A3);
- every inherited `GRAPHIFY_*` variable, `GRAPHIFY_OUT` among them, absent from the stub's
  environment;
- an inherited `GIT_DIR` pointing elsewhere, and `GIT_CONFIG` pointing at an empty file while
  `GIT_CONFIG_COUNT` sets `core.hooksPath`, which do not change the answer;
- exit 0 in every case.

The other `view` tests cover:
- a graph, which writes a file per symbol, each headed by the label;
- `--refresh` over a graph whose rebuild has fewer nodes, which the stub refuses without
  `--force`; the refresh writes the smaller graph and stamps it;
- no graph, and graphify missing, each of which prints a fallback line;
- a hanging `affected`, which times out and falls back, with the timeout shortened for the test;
- exit 0 in every case;
- no writes outside `--out`, the removed snapshot and, with `--refresh`, an ignored
  `graphify-out/`.

**Oracle test** (planning.md's oracle-test rule), `test_oracle_setup_build_then_label`. When the
real `graphify` is on PATH, it runs graphify under setup's environment (cwd at the graph root,
`GRAPHIFY_*` dropped, a temporary HOME) in a temporary git repository that ignores
`/graphify-out/`:
- one `graph_view.py setup` builds the graph; `.graphify_root` reads `.`, `built_at_commit` is
  HEAD, and the stamp's `head` is HEAD and its `sha256` matches `graph.json`;
- a second setup builds nothing and prints `graph ready`;
- after one more commit, made with `GRAPHIFY_OUT` set so the hook skips, `view` prints
  `graph built at <short> (1 commits behind HEAD); advisory — confirm with grep` and runs no
  `update`;
- a rebuild that graphify's shrink check refuses exits 1 without `--force` and leaves
  `graph.json` unchanged, while `update . --force` writes the smaller graph. In 0.8.49 a deleted
  file does not trip the check (`_check_shrink` exempts explicit deletions and nodes of
  re-extracted files); an injected node marked `_origin: ast` whose `source_file` is an existing
  non-code file does.

It records, without asserting, whether an injected node without `_origin` survives a forced build,
printing one line with graphify's version. Without graphify, it prints a skip line naming why.

Add one line to `SKILL.md` naming `setup` and `view` for goal runs.

Expected size: `graph_view.py` about 260 lines: the advisory label saves about 30 against the
freshness rule, and the symlink check, the single read and the printed-command builder add about
30. No ceiling in `test_size.py` covers `graph-navigation`.

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
  alternatives it beat. It states the advisory contract (A1–A6), and that this repository
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
    and without `--force` it can exit 1 without writing. (The rebuild condition is superseded
    below by round 5, then by round 6's advisory contract; `--force` stays.)
  - **Partial-graph protection.** Setup checks and installs the guard first. A guard missing at
    this setup forces one full rebuild, whatever the graph says; later setups trust a HEAD-built
    graph. This keeps the protection the round-4 "always" correction gave, because a partial graph
    left by an older unguarded hook has `built_at_commit` equal to HEAD. (Superseded below by
    round 5, then by round 6: the guard plays no part in any claim.)
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
    path as typed into `.graphify_root`.
  - (default) `view` never rebuilds on its own; `view --refresh` runs setup's bounded forced build
    and stamp (AC-3), over a plain `update` that can leave every `view` failing for the rest of
    the goal.
  - (default) T6's oracle test runs real graphify and skips with a line without it. It pins
    graphify 0.8.49's shrink rule, after finding that a plain deletion is exempt from the check.
    Node survival under `--force` is recorded, not asserted (round 5, decision 2).
  - (default) The design's "incremental refresh" statement is removed, and the design states only
    the measured cost, with no cache mechanism (round 6); the spec's Journey 1, AC-1, the design's
    Structure row and step table, and T6 state one rule.
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
    `routine`, because it carries the advisory contract, its label and an oracle test.
    Round 7 sets T6's `risk: safety`, for A5's symlink refusal.
  - (default) T3 offsets every `run.md` addition with a trim that loses no rule; `run.md` is at
    2,999 of 3,000 words.
  - (default) Setup prints `graph built: <reason>` on a build, the failure line on a timeout or a
    nonzero exit, and `graph ready` when it builds nothing.
  - (default) The failure line's fix command is the invocation itself with `--no-bound`, over
    `graphify update . --force`. A by-hand graphify build writes no completion stamp, so the next
    bounded setup would rebuild and could time out again, and the printed command would not clear
    the condition (planning.md's tested-fix-command rule). `--no-bound` lifts only the bound, and
    the build it runs writes the stamp. Round 7 made it one line for both causes, carrying the
    invocation's own `--root` and arguments, for setup and `view --refresh` alike.
  - (default, round 6) A stamp that does not parse counts as missing, so setup builds.
  - (default) Under `core.hooksPath`, or with a child graph, setup installs nothing and builds only
    under A2's conditions; hooks under `core.hooksPath` stay F-3 Queue Q7's.
  - The `rebuild-pending` marker and the `.graph_view_head` stamp, earlier defaults of this
    amendment, are superseded by round 5, then by round 6's advisory contract. Their evidence
    stands:
    - graphify 0.8.49 writes `.graphify_root` after extraction but before clustering and the graph
      write (`watch.py`, about lines 671–677), so a run cut off late has already replaced it;
    - 2026-10-08, in a throwaway repository with a temporary HOME: after a commit to a non-code
      file, `graphify update . --force` exited 0 and `built_at_commit` stayed at the earlier
      commit, because a forced update that finds the code graph unchanged leaves `graph.json` as
      it was.
  - (default, corrected by the controller) Setup runs `git check-ignore -q` on the graph root's
    `graphify-out/`. When it is not ignored, setup prints the `.gitignore` entry to add, builds
    nothing and exits 0.

- 2026-10-08: approval-tag sequence for the amendment, superseding the round-4 entry's placement
  sentence, which said F-5's documents are unchanged between `goal/F-4/M1` and the approved tag.
  The sequence is: the amendment commits; the founder-granted design and plan review runs;
  the founder re-approves; `goal/F-5/approved` goes on the re-approved commit; a baseline is
  recorded; F-5 starts.

- 2026-10-08: founder decisions on the amendment review's round 5. The granted design and plan
  reviews blocked with six findings each; ten were one family, completeness inferred from guard
  history, which fails whenever the guard came from elsewhere. (Superseded by round 6 below:
  decision 1 entirely, and decision 2's cache sentence, which now states only the measured cost.
  Decision 2's narrowing of AC-1 to what setup controls stands.)
  1. **Completeness: trust only setup's own build.** The guard-history trigger, the
     `rebuild-pending` marker and the HEAD stamp give way to the design's completeness contract,
     P1–P6. A graph is complete only with `graphify-out/.graph_view_complete`, which holds HEAD
     and `graph.json`'s sha256 and is written only after a full forced update by setup or `view`
     exits 0 within its bound. Setup and `view` rebuild exactly when a graph is not fresh. Guarded
     hooks keep a complete graph complete (graphify's `hooks.py` and `watch.py`, cited in the
     design). Nothing is written under an unignored graph directory. The guard keeps hooks
     refreshing and is never evidence of completeness. T6 maps each round-5 finding to a property
     and a named test.
  2. **Narrow AC-1.** AC-1 and the design promise only what setup controls: the command and its
     cwd, the `GRAPHIFY_*` drop, the stamp, `.graphify_root`, the printed lines and exit 0. Which
     nodes survive `--force` is graphify's behaviour, which the oracle test records and does not
     guarantee. The cache sentence states the measured fact: warm and cold full updates cost the
     same, although graphify reuses cached extractions for unchanged files.
  3. **Round 6.** One more granted design and plan review follows this correction; the controller
     runs it. Re-approval and the tag follow its pass, in the sequence above.

- 2026-10-08, before round 6: (default, from the controller) P2's branch (a), `built_at_commit`
  equal to HEAD, now also requires P4's premise to hold at the time of the check:
  `core.hooksPath` unset, the graph not under a child directory, and the guard immediately before
  graphify's `post-commit` block. A guarded hook never creates a graph, so with the guard in place
  a deleted graph cannot reappear partial at HEAD. Without it, only the stamp branch (b) counts.
  This closes the drafted assumption that a graph deleted while its stamp was kept, then rebuilt
  by an unguarded hook, would pass P2. The guard enables branch (a) only and never establishes
  completeness (P6). T6 adds the deleted-graph cases, under `core.hooksPath` and with a child
  graph, and a guarded control. (Superseded by round 6 below: the advisory contract has no
  branch (a), and nothing trusts a graph.)

- 2026-10-08: founder decisions on the amendment review's round 6. Design and plan blocked again:
  P2's branch (a) accepted a partial graph once `core.hooksPath` was unset after the check (D1,
  PL2), and a commit whose refresh was skipped, followed by a guarded refresh, left that commit's
  file missing from a graph P2 trusted (D2, PL1). Two prose claims were also wrong: that a failed
  hook rebuild leaves `graph.json` unchanged (D3, PL3), and that every update re-extracts
  everything (D4).
  1. **An advisory graph, honestly labelled.** F-5 no longer claims any graph is complete or
     current. The design's contract is A1–A6: graph output is advisory and the agent confirms it
     with grep or a read (A1); setup builds once per checkout, only without a graph, with an
     unparsable `graph.json`, a foreign `.graphify_root`, or no parsing stamp, and the stamp
     records setup's last full build, not trust (A2); the guard stays and plays no part in any
     claim (A3); `view` never rebuilds on its own, labels every result with its build commit and
     its distance behind HEAD, and rebuilds only on `--refresh` (A4); nothing is written under an
     unignored graph directory (A5); exit codes and the `GRAPHIFY_*` drop are unchanged (A6).
  2. **Criteria changes, founder-approved.** The founder approved these changes to the spec's
     criteria: AC-1 (setup builds once per checkout and claims nothing about completeness), AC-3
     (`view`'s label, no automatic rebuild, `--refresh` on request, `context.md`'s advisory rule),
     Journeys 1, 3 and 6, the Outcome, the Actors line on refreshing, and the Non-goals (no
     completeness claim, no automatic rebuild). Every criterion that promised a fresh or complete
     graph is withdrawn in that wording.
  3. **Round 7.** One more granted design and plan review follows this correction; the controller
     runs it. Re-approval and the tag follow its pass, in the sequence above. (Superseded by
     round 7 below: re-approval follows the controller's verification, not a pass.)

- 2026-10-08: founder decisions on the amendment review's round 7. Design and plan blocked on
  eight findings, three on the design and five on the plan.
  1. **Fix all eight, each with a planned test.** The design's A-list and Interfaces carry each
     fix, and T6, or the named task, names its test:
     - a failed or timed-out build leaves no stamp, because setup and `view --refresh` delete it
       before any build (A2; `test_failed_build_deletes_old_stamp`);
     - setup and `view --refresh` refuse to build when `graphify-out/` or an entry directly in it
       is a symlink (A5; `test_symlinked_artifact_refused`), so T6 is `risk: safety`;
     - the label counts both sides, `<B> commits behind HEAD, <A> ahead` (A4;
       `test_label_ahead_of_head`, `test_label_diverged`, `test_label_behind_by_n`);
     - `view` reads `graph.json` once and derives the label and every result from those bytes
       through a `--graph` snapshot (A4; `test_view_single_read`);
     - every printed command repeats the invocation's own `--root` and arguments (Printed
       commands; `test_fix_line_repeats_root`);
     - setup checks `post-checkout` as well as `post-commit` for the guard (step 5;
       `test_setup_checks_post_checkout_guard`);
     - T2's smoke runs this checkout's `validate_disclosure.py` and `disclosure-check.sh` through
       a HOME override inside the fixture's hook command, and asserts the `stale-guide` line
       (T2; T2 now needs T5);
     - one failure line for a timeout and a nonzero exit, whose retry is `<rerun> --no-bound` in
       both (One failure line; `test_setup_timeout_writes_no_stamp`, `test_setup_failure_line`,
       `test_view_refresh_failure_line`).
  2. **Verification, then re-approval, with no round 8.** The controller verifies the fixes;
     re-approval and the tag follow, in the sequence above. T6's task review and M1's
     cross-vendor acceptance re-judge each of the eight against the code.
  3. **Criteria changes.** AC-1 (both hooks, the symlink refusal, stamp deletion, the one failure
     line, `<rerun>`) and AC-3 (the two-sided label, the single read, `view --refresh`'s failure
     line) change with these fixes, as the founder's decision to fix all eight requires; the
     spec's `edge_cases` add diverged-build-commit, concurrent-refresh,
     failed-build-after-stamp and symlinked-artifact.

## Queue

- (a) (blocks nothing; founder decides later) In adopting projects that commit
  `graphify-out/reflections/`, graphify's post-commit hook rewrites `reflections/LESSONS.md` in the
  background. A commit just before a review or receipt can then make the round exit 2 on drift, or
  fail the receipt with "the run changed the working tree". Options: ignore `graphify-out/`
  wholesale, as this repository does; or stop committing `reflections/`. Either supersedes part of
  D11. Recommendation: ignore wholesale, which matches this repository and `migrate.md`'s step 4.
- (b) (blocks nothing; founder decides later) graphify's own hook never passes `--force`, so a
  hook-refreshed graph refuses some shrinks and falls behind: 44 of 1,928 in a real log. Options:
  `migrate.md`'s step 4 advises `GRAPHIFY_FORCE=1` in the hook environment; or rely on `view`'s
  label and `--refresh`. Recommendation: rely on the label, because a refused refresh leaves
  `built_at_commit` behind HEAD, the label shows how many commits behind, and the chief runs
  `view --refresh` when that distance matters.
