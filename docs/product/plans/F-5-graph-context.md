---
goal: F-5
title: Folder routes and graph-backed context for goal runs
spec: docs/product/specs/F-5-graph-context.md
design: docs/architecture/graph-context.md
status: draft
updated: 2026-10-08
gate: rc=0; for d in execution-methodology agent-personas progressive-disclosure; do [ -d install/skills/$d/tests ] || continue; python3 -m unittest discover -s install/skills/$d/tests -t install/skills/$d/tests || rc=1; done; python3 -m unittest discover -s install/tests -t install/tests || rc=1; exit $rc
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
e2e: python3 install/skills/execution-methodology/tests/smoke_goal.py --harness claude && python3 install/skills/execution-methodology/tests/smoke_goal.py --harness codex
run: {network: true, session_hours: 2}
grants: [local-commit]
---

# F-5 plan — folder routes and graph-backed context

**Branch.** `v6-followups`, after F-4's `goal/F-4/M1`. Both goals edit `run.md`, the decisions
and the measurements. Only local commits are granted. Merge, push, global install, and any graph
build in a private project are the founder's.

**Commit rules.** Every task commit leaves the gate green and passes the installed pre-commit
route and identifier checks. `tests-may-change` lists exactly the existing tests each task may
edit.

## M1 — folder routes stay true, every session knows the graph's state, and goal runs use both

criteria: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
acceptance: [all]
proofs:
- AC-1: python3 -m unittest discover -s install/tests -t install/tests -p 'test_graphify_session.py'
- AC-2: python3 -m unittest discover -s install/tests -t install/tests -p 'test_install.py'
- AC-6: python3 -m unittest discover -s install/skills/progressive-disclosure/tests -t install/skills/progressive-disclosure/tests -p 'test_validate_disclosure*.py'
- AC-3, AC-4, AC-5: full_gate

### [ ] T1 — the graphify session hook
- writes: install/hooks/graphify-session.py, install/tests/test_graphify_session.py
- needs: —
- covers: AC-1, AC-5
- risk: safety
- builder: judgement
- tests-may-change: —

Implement the design's `graphify-session.py` interface. Its tests use a temporary git repository,
a temporary HOME and a stub `graphify` on PATH. They cover:
- each of the four status lines;
- the silent clean case;
- the lessons digest, kept;
- a missing or unknown `built_at_commit`;
- doc-only changes, which are not counted as code;
- an inherited `GIT_DIR` pointing elsewhere, which does not change the answer;
- a hooks dir moved by `core.hooksPath`;
- malformed `graph.json`, which prints nothing and exits 0;
- the timeout path.

`risk: safety` applies because the hook runs in every session of every project, inside both
harnesses, and executes git and graphify there.

### [ ] T2 — both harnesses get the graph hooks
- writes: install/install.sh, install/verify.sh, install/README.md, install/tests/test_install.py, docs/agents/what-gets-installed.md, install/hooks/graphify-session-lessons.sh
- needs: T1
- covers: AC-2, AC-6
- risk: boundary
- builder: judgement
- tests-may-change: install/tests/test_install.py

Do the following:
- Register `disclosure-check.sh` for Codex at SessionStart, as Claude Code already has it.
- Register `graphify-session.py` for both harnesses, replacing `graphify-session-lessons.sh` in
  the Claude list and adding it to the Codex list.
- Add `graphify-query-advisor.py` to the Codex `PreToolUse` list under Codex's shell-tool name.
  Find that name from a real Codex hook payload in the trusted smoke fixture, without writing
  `~/.codex`, and record the evidence in the task report. If Codex has no such event, keep the
  advisor Claude-only and record why.
- Delete `graphify-session-lessons.sh` and add it to the retire list.
- Update the installer tests for both harnesses, and the two docs that list installed hooks.

`risk: boundary` applies because the installer writes the founder's harness configuration.

### [ ] T3 — the dispatch and acceptance steps
- writes: install/skills/execution-methodology/references/context.md, install/skills/execution-methodology/references/run.md, install/skills/execution-methodology/references/planning.md
- needs: T1, T5
- covers: AC-3, AC-5, AC-6
- risk: none
- builder: routine
- tests-may-change: —

Write `context.md` from the design's Rules-text section, in about 450 words, with the route first and the graph after it. Add the update rule to `planning.md` in one sentence. Then, and add the one
pointer sentence to `run.md`'s dispatch step. That sentence must be offset by a trim in `run.md`,
which F-4 left at the budget. Verify with `install/tests/test_size.py`.

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

`progressive-disclosure` stays at or under its AC-13 ceiling of 5,470 lines.

### [ ] T4 — measurements and records
- writes: docs/product/measurements.md, docs/decisions/decisions.md, docs/architecture/lean-execution.md
- needs: T2, T3, T5
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

## Decisions

## Queue
