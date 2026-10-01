---
feature: F-2
title: Deliver goal-directed milestone autonomy
spec: docs/product/specs/F-2-goal-directed-autonomy.md
milestone: M2
status: building
updated: 2026-10-01
---

# F-2 implementation and validation plan — goal-directed autonomy

## Approach

Change the existing methodology in two file-disjoint logical tasks. T1 delivers the core workflow
and retains scheduler safety while removing the arbitrary exact-write-count ceiling. T2 makes the
existing gate and seal fail closed. Each task begins in maintained source, projects accepted bytes
to the declared public paths under the same task identity, and receives one complete review. After
both tasks, documentation custody, installation, the full local gate, seal, acceptance and any
conditionally authorized publication close the milestone through existing owners.

## Frozen interfaces

No new interface is introduced. The existing plan task keys remain `task`, `title`, `lane`, `needs`,
`writes`, `covers` and optional `serialises`. Exact normalized nonempty writes, nonempty coverage,
dependency validity, overlap detection, commit-scope checking, task-count limits and the Full-card
schema retain their current behavior. The only scheduler policy change is removal of the fixed
five-write-path rejection.

## Tasks

```task
task: T1
title: Carry closed product context through chief-owned execution and causal recovery
lane: full
needs: []
writes: [install/skills/execution-methodology/methodology.md, install/skills/execution-methodology/references/execution-loop.md, install/skills/execution-methodology/references/specs.md, install/skills/execution-methodology/references/task-card.md, install/skills/execution-methodology/scripts/plan_waves.py, install/skills/execution-methodology/tests/test_execution_loop.py, install/skills/execution-methodology/tests/test_methodology_policy.py, install/skills/execution-methodology/tests/test_plan_waves.py]
covers: [AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-10, AC-11, J-1, J-2]
serialises: []
```

- **Tests:** focused scheduler cases prove exact-path lists above five are accepted while blank or
  non-normalized writes, empty coverage, overlaps, commit-scope violations, task-count breaches and
  invalid Full cards remain findings; workflow tests prove persistent authority, Light/Full routing,
  A/B/C recovery, same-cause lineage and the three overengineering questions.
- **Area check:** from both maintained and public execution-methodology roots, run
  `python3 -m unittest discover -s tests -t tests`.
- **Dependencies:** none; T1 and T2 may run concurrently because their write sets are disjoint.
- **Stops:** a new interface or mode, weakened scheduler invariant, changed Full schema, missing
  existing native read-only review route, or an unapproved scope/safety decision.

```task
task: T2
title: Make declared-gate verdict and milestone-seal freshness fail closed
lane: full
needs: []
writes: [install/skills/gate-sandbox/scripts/gate.sh, install/skills/gate-sandbox/tests/selftest.sh, install/skills/gate-sandbox/tests/test_selftest_suite.py, install/skills/execution-methodology/scripts/milestone_seal.py, install/skills/execution-methodology/tests/test_milestone_seal.py]
covers: [AC-7, AC-9, AC-10, J-3]
serialises: []
```

- **Tests:** failure injection proves a child success plus terminal integrity failure exits nonzero;
  seal tests reject candidate, source, input, command, runtime or evidence drift after the gate and
  accept the unchanged fresh case.
- **Area check:** from maintained and public gate-sandbox roots, run
  `python3 -m unittest discover -s tests -t tests`; from maintained and public execution-methodology
  roots, run the milestone-seal test module and then its complete suite.
- **Dependencies:** none; T2 and T1 may run concurrently because their write sets are disjoint.
- **Stops:** any fail-open terminal branch, a receipt that survives relevant post-gate drift, a new
  runner or receipt schema, or a change outside the five declared paths.

The two task blocks are canonical. The maintained source paths are the same paths with the leading
`install/` removed. Exact source/public mappings and closure stages are in the
[stage companion](goal-directed-autonomy-task-boundaries.md). A builder may narrow a write set after
confirming a listed file is unchanged; widening requires plan review.

T1 and T2 are accepted. Four focused installed scheduler tests pass, and the real installed
scheduler accepts T1's eight exact normalized paths while retaining the other declared checks.

## Current checkpoint

The accepted candidate was projected to maintained source and the public package, then installed
through the existing installer. All 13 candidate/public/installed-Claude/installed-Codex mappings
are byte-equal. `cd install && ./install.sh --dry-run && ./verify.sh` exits zero with repository and
machine PASS. A fresh native Codex normal-configuration read-only run returned `ACTIVATION PASS` for
checkpoint continuation, ready-set selection and refusal, dependent-only stops, the publication
boundary and same-cause A/B/C recovery.

Claude skills, hooks, personas and bytes are statically verified; authenticated Claude inference is
deferred. M2 has not been sealed or accepted. Publication, tag and deployment did not occur, and
existing pinned consumer bindings were not changed.

## Validation plan

### Coverage map

| Criterion | Level | Owner |
| --- | --- | --- |
| AC-1–AC-6, AC-10–AC-11, J-1–J-2 | unit + methodology area | T1 |
| AC-7, AC-9, J-3 | failure injection + gate/seal area | T2 |
| AC-8 | byte comparison + existing installer verification | closure |

### End-to-end set

1. **Core delivery:** a closed, approved task enters the ready set, receives the correct lane,
   review and validation, and reaches an accepted result without routine reapproval.
2. **Causal recovery:** the same cause survives A and B, requires targeted council plus fresh replan
   PASS before C, and ends without a fourth attempt after C failure.
3. **Valid closure:** maintained/public bytes agree, the existing installer verifies them, and the
   full gate, seal and fresh acceptance bind one unchanged candidate.

### Not tested, and why

Consumer bindings, hosted continuation, tag and deployment are outside M2. Conditional publication
uses existing guarded tooling and is verified only after the local closure conditions hold.

### Documentation, installation and closure

T1 and T2 passed their complete source/public reviews, and the existing installer and repository
gate passed without adding installer implementation. Current-state documentation records that
accepted and installed checkpoint. The remaining closure work is to seal and verify the unchanged
candidate and obtain fresh acceptance against the same referent. Existing guarded publication may
act only after that closure and only within a still-valid conditional grant. The one-week
business-value review uses the existing evidence record.

### Gate

`cd install && ./install.sh --dry-run && ./verify.sh`

## Trace and stops

T1 and T2 are the only implementation tasks. Documentation, mechanical projection, installation
and closure do not create duplicate cards or reviews. A changed frozen outcome, widened production
write set, new interface, new safety claim, failed area check, failed full gate, stale seal, failed
acceptance, revoked authority or unavailable required resource stops the affected path. The same
cause retains its A/B/C lineage across renamed attempts.
