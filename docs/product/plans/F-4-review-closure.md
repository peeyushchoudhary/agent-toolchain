---
goal: F-4
title: Review closure that ends in fixes, not in grants
spec: docs/product/specs/F-4-review-closure.md
design: docs/architecture/review-closure.md
status: approved
updated: 2026-10-07
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

criteria: AC-1, AC-2, AC-3, AC-4, AC-5
acceptance: [all]
proofs:
- AC-3: e2e
- AC-2, AC-3: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_review*.py'
- AC-1, AC-4, AC-5: full_gate

**Sizing exception.** M1 has three tasks, below the minimum of four. The goal is three small
rule changes, and splitting them further would add only dispatch overhead. No walking skeleton is
needed: T1 is proven by its unit tests, and T2 and T3 are text.

### [ ] T1 — `review.py`: test-closed confirmation and the family question
- writes: install/skills/execution-methodology/scripts/review.py, install/skills/execution-methodology/tests/test_review_closure.py, install/skills/execution-methodology/tests/smoke_review_closure.py
- needs: —
- covers: AC-2, AC-3, AC-4
- risk: boundary
- builder: judgement
- tests-may-change: —

Implement the design's Interfaces section:
- `--closed-by` with its three admission conditions and its refusals (exit 1, nothing consumed);
- the uncounted confirmation in `admit()`, recorded under `confirmations` in `rounds.json` and as
  `confirmation:` in the verdict header;
- the per-round `review/<key>-r<n>.files.json` digests;
- the packet text that names the tests;
- the rereview family instruction, for every round above 1.

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
- confirmation under the subject lock.

Every unit test uses a stub judge, and none calls a real CLI. The existing tests stay unchanged and
green.

`smoke_review_closure.py` is the end-to-end proof, and it runs the real cross-vendor judge.
- It builds a temporary fixture repository with one planted defect, and runs round 1, which must
  BLOCK.
- It applies a fix and a test that reproduces the defect, then runs `--closed-by` with that test.
- It asserts that the confirmation is recorded and uncounted, and that the judge saw the named
  tests.

It costs two real judge calls.
The methodology and persona code stays at or under 2,500 lines, with about 127 lines of headroom.

`risk: boundary` applies because `review.py`'s flags, `rounds.json` and the verdict header are
interfaces that the driver, `goal.py` and every later goal depend on.

### [ ] T2 — rules text: Keep list, family closure and confirmation
- writes: install/skills/execution-methodology/methodology.md, install/skills/execution-methodology/references/run.md, install/skills/execution-methodology/references/review.md
- needs: T1
- covers: AC-1, AC-2, AC-3, AC-4
- risk: none
- builder: routine
- tests-may-change: —

Write the design's Rules-text section:
- the `run.md` dispatch step gains the Keep list and the builder's stop rule;
- the `review.md` Closure section makes step 1 executable with `--closed-by`, adds the family step,
  and restates the cap arithmetic;
- the `methodology.md` Review paragraph gets one sentence.

The text must match T1's flags and file names exactly. `run.md` is at the 3,000-word role-load
budget, so the additions are offset by trims in `run.md` that lose no rule. Verify with
`install/tests/test_size.py`.

### [ ] T3 — records to current state
- writes: docs/architecture/lean-execution.md, docs/decisions/decisions.md, docs/product/measurements.md
- needs: T2
- covers: AC-5
- risk: none
- builder: routine
- tests-may-change: —

- **`lean-execution.md`:** the review section states the Keep list, family closure and the
  uncounted test-closed confirmation as current state. It names the per-round digests in the
  `review.py` row.
- **`decisions.md`:** a new decision, D28, gives the reason (F-3's five founder grants for extra
  rounds, and the M4 regression) and the alternatives it beat (cap 3, advisor grants, pre-fix test
  execution), in a few lines.
- **`measurements.md`:** an "F-3 review rounds — 2026-10-08" section. `.runs/` is not committed,
  so the source is the F-3 plan's Decisions and this goal's spec. Give these numbers:
  - M3 acceptance: 5 rounds per partition, 3 of them founder-granted;
  - T9 security: 4 rounds, 2 founder-granted;
  - M4 acceptance: rounds 1–3 on the same defect family, 2 founder-granted;
  - founder grants for extra rounds: 7 in all.

  Use no private identifiers.

## Grants requested

- `local-commit` on `v6-followups`.

## Decisions

- 2026-10-08, T3 (default): `measurements.md` records F-3's final counts, not the counts this plan
  quoted before F-3 M4 closed. M4 acceptance ran 5 rounds, 3 of them founder-granted, and rounds 2–4
  blocked on one defect family: deciding where git runs hooks. F-3 had 8 founder decisions for
  extra rounds, admitting 11 granted rounds across 4 subjects. The spec's Why is left as approved;
  Q1 asks the founder whether to correct it.

## Queue

- Q1 (blocks nothing): the spec's Why quotes F-3's counts as of M4 round 3 ("M4 4 rounds, 2
  granted; 7 founder decisions"). Options: re-approve a one-line correction to the final counts
  (M4 5 rounds, 3 granted; 8 decisions), or leave it, since `measurements.md` records the final
  numbers. Recommendation: correct it at merge.
