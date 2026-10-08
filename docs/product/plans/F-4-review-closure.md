---
goal: F-4
title: Review closure that ends in fixes, not in grants
spec: docs/product/specs/F-4-review-closure.md
design: docs/architecture/review-closure.md
status: approved
updated: 2026-10-08
gate: rc=0; for d in execution-methodology agent-personas progressive-disclosure; do [ -d install/skills/$d/tests ] || continue; python3 -m unittest discover -s install/skills/$d/tests -t install/skills/$d/tests || rc=1; done; exit $rc
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
e2e: python3 install/skills/execution-methodology/tests/smoke_goal.py --harness claude && python3 install/skills/execution-methodology/tests/smoke_goal.py --harness codex && python3 install/skills/execution-methodology/tests/smoke_review_closure.py
run: {network: true, session_hours: 2}
grants: [local-commit]
---

# F-4 plan — review closure

**Branch.** `v6-followups`, stacked on `v6-lean-execution` at `goal/F-3/M4`. F-5 follows F-4 on
the same branch, because both edit `run.md`, the decisions and the measurements. Only local
commits are granted. Merge, push and global install are the founder's.

**Commit rules.** Every task commit leaves the gate green and passes the installed pre-commit
route and identifier checks. `tests-may-change` lists exactly the existing tests each task may
edit.

## M1 — corrections keep reasons, fix families, and confirm test-closed fixes without a grant

criteria: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7
acceptance: [all]
proofs:
- AC-3: e2e
- AC-2, AC-3, AC-7: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_review*.py'
- AC-1, AC-4, AC-5, AC-6: full_gate

**Sizing exception.** M1 has three tasks, below the minimum of four. The goal is three small
rule changes, and splitting them further would add only dispatch overhead. No walking skeleton is
needed: T1 is proven by its unit tests, and T2 and T3 are text.

### [ ] T1 — `review.py`: test-closed confirmation, the family question and acceptance coverage
- writes: install/skills/execution-methodology/scripts/review.py, install/skills/execution-methodology/tests/test_review_closure.py, install/skills/execution-methodology/tests/smoke_review_closure.py
- needs: —
- covers: AC-2, AC-3, AC-4, AC-7
- risk: boundary
- builder: judgement
- tests-may-change: —

Implement the design's Interfaces section:
- `--closed-by` with its three admission conditions and its refusals (exit 1, nothing consumed);
- the uncounted confirmation in `admit()`, recorded under `confirmations` in `rounds.json` and as
  `confirmation:` in the verdict header;
- the per-round `review/<key>-r<n>.files.json` digests;
- the packet text that names the tests;
- the rereview family instruction, for every round above 1;
- the acceptance diff filtered only by a declared partition, and the coverage line in the
  acceptance packet.

The new tests go in `test_review_closure.py` and cover:
- admission at the cap;
- each refusal: no verdict, a PASS verdict, a second confirmation, a test unchanged since the last
  round, a missing path, and use together with `--founder-grant`;
- the record in `rounds.json` and in the header;
- an unchanged tracked test outside the last round's diff, which is refused;
- a deleted path, recorded as `null`, whose review still completes;
- history numbering staying sequential across a confirmation;
- the counted rounds left after a confirmation;
- the founder grant still admitting exactly one round past the cap after a confirmation;
- the family sentence in a round-2 packet and its absence in round 1;
- confirmation under the subject lock;
- a single-partition acceptance with `--subject` paths, whose diff still covers the whole
  milestone and whose packet lists the paths as reading context;
- a multi-partition acceptance, whose diff is filtered to the partition's paths;
- the coverage line's two counts, including `0 of <m>` for an empty diff.

Every unit test uses a stub judge, and none calls a real CLI. The existing tests stay unchanged and
green.

`smoke_review_closure.py` is the end-to-end proof, and it runs the real cross-vendor judge.
- It builds a temporary fixture repository with one planted defect, and runs round 1, which must
  BLOCK.
- It applies a fix and a test that reproduces the defect, then runs `--closed-by` with that test.
- It asserts that the confirmation is recorded and uncounted, and that the judge saw the named
  tests.

It costs two real judge calls.
The methodology and persona code stays at or under 2,500 lines, with about 127 lines of headroom;
the coverage changes are expected to take about 10 of them.

`risk: boundary` applies because `review.py`'s flags, `rounds.json` and the verdict header are
interfaces that the driver, `goal.py` and every later goal depend on.

### [ ] T2 — rules text: Keep list, class and family closure, confirmation, oracle tests
- writes: install/skills/execution-methodology/methodology.md, install/skills/execution-methodology/references/run.md, install/skills/execution-methodology/references/review.md, install/skills/execution-methodology/references/planning.md
- needs: T1
- covers: AC-1, AC-2, AC-3, AC-4, AC-6
- risk: none
- builder: routine
- tests-may-change: —

Write the design's Rules-text section:
- the `run.md` dispatch step gains the Keep list and the builder's stop rule;
- the `review.md` Closure section makes step 1 executable with `--closed-by`, adds the
  open-input class step and the family step, and restates the cap arithmetic;
- `planning.md`'s Writing tasks section gains the oracle-test and tested-fix-command rules;
- the `methodology.md` Review paragraph gets one sentence.

The text must match T1's flags and file names exactly. `run.md` is at the 3,000-word role-load
budget, so the additions are offset by trims in `run.md` that lose no rule. `review.md` and
`planning.md` have about 600 and 390 words of role-load headroom. Verify with
`install/tests/test_size.py`.

### [ ] T3 — records to current state
- writes: docs/architecture/lean-execution.md, docs/decisions/decisions.md, docs/product/measurements.md, docs/agents/lessons.md
- needs: T2
- covers: AC-5
- risk: none
- builder: routine
- tests-may-change: —

- **`lean-execution.md`:** the review section states the Keep list, family closure and the
  uncounted test-closed confirmation as current state. It names the per-round digests in the
  `review.py` row.
- **`decisions.md`:** a new decision, D28, gives the reason (F-3's eight founder decisions admitting
  11 rounds past the cap, six blocking rounds that were further instances of a known family, and
  the M4 regression) and the alternatives it beat (cap 3, advisor grants, pre-fix test execution,
  impact rating), in a few lines.
- **`measurements.md`:** an "F-3 review rounds — 2026-10-08" section. `.runs/` is not committed,
  so the source is the F-3 plan's Decisions and this goal's spec. Give these numbers:
  - M3 acceptance: 5 rounds per partition, 3 of them founder-granted;
  - T9 security: 4 rounds, 2 founder-granted;
  - M4 acceptance: 5 rounds, 3 founder-granted, rounds 2–4 one defect family;
  - blocking rounds: 11, of which 6 were further instances of a family already found and 1 a
    correction that removed an earlier fix;
  - founder decisions admitting extra rounds: 8, for 11 rounds past the cap.

  Use no private identifiers.
- **`lessons.md`:** two durable facts, each with its evidence.
  - git runs hooks from the directory `git rev-parse --git-path hooks` names. With `core.hooksPath`
    unset, linked worktrees share the main checkout's hooks directory; a relative `core.hooksPath`
    resolves inside each worktree. `GIT_CONFIG` changes only what `git config` reads. A claim about
    where hooks run is safest narrowed to "`core.hooksPath` is unset".
  - git runs a hook from the root of the worktree that ran the command, so graphify's hook
    refreshes only that worktree's untracked graph. In a worktree without a graph, graphify's
    post-commit hook creates one holding only the changed files.

## Grants requested

- `local-commit` on `v6-followups`.

## Decisions

- 2026-10-08, T3 (default, superseded the same day by the amendment below): `measurements.md`
  records F-3's final counts rather than those quoted before F-3 M4 closed.
- 2026-10-08: founder decisions after the review-round analysis. F-4 is amended with four
  learnings before execution: class correction at the first open-input finding (AC-2), oracle
  tests and tested fix commands (AC-6), and acceptance coverage
  (AC-7); the spec's counts are corrected to F-3's final numbers. The amendment gets one
  founder-granted review round of design and plan, then re-approval. Likelihood or impact rating
  of findings is declined. `goal/F-4/approved` moves to the re-approved commit.
- 2026-10-08: the amendment's review round (round 3) blocked on four findings, all corrected
  without changing scope: AC-3's wording now matches the design's admission rule; the empty-diff
  refusal is dropped, because existing fixtures judge clean trees and the coverage line already
  shows an empty diff; D28 quotes the final counts; the hooks lesson says a relative
  `core.hooksPath` resolves inside each worktree. Re-approval goes to the founder.
- 2026-10-08: the founder re-approved F-4 as corrected, without a further review round.

- 2026-10-08, T1 (default): for `--closed-by`, a test path the last round did not record counts as
  changed exactly when git says so (`git diff --quiet <verdict tree> -- <path>` exits 1), with git's
  filters applied; recorded paths compare raw-byte SHA-256 as designed. Chosen over a
  re-implemented blob hash, which T1's boundary review round 1 showed disagrees with git under
  `core.autocrlf`. A line-ending-only change git ignores does not admit a confirmation.

- 2026-10-08: founder decision on T1's boundary review round 2, which blocked on two repeats of
  round 1's findings, both marked `family:` by the judge: a round with `--diff HEAD..HEAD` did not
  record a test with uncommitted edits, and a pruned verdict tree read as "path absent". The class
  fix: every round records every path that differs from its verdict tree, plus untracked files,
  whatever the range, so an unrecorded path is identical to the verdict tree; a missing tree or a
  failed git call refuses. The founder approved the one-sentence design change (Interfaces,
  per-round digests) and one founder-granted scoped boundary round (round 3);
  `goal/F-4/approved` moves to this commit.

## Queue

- Q2 (blocks nothing): carry a PASS forward to a new tree when the change misses a partition's
  paths. F-3 spent four PASS rounds on re-closes. Options: design it as its own goal after a
  measurement of re-close cost across goals; or keep re-closing. Recommendation: measure first,
  over F-4 and F-5.
