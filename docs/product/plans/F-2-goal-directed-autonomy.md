---
feature: F-2
title: Deliver goal-directed milestone autonomy
spec: docs/product/specs/F-2-goal-directed-autonomy.md
milestone: M2
status: shipped
updated: 2026-10-06
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
  runner or receipt schema, or a write outside the admitted exact paths.

The two task blocks are canonical. The maintained source paths are the same paths with the leading
`install/` removed. Exact source/public mappings and closure stages are in the
[stage companion](goal-directed-autonomy-task-boundaries.md). A builder may narrow a write set after
confirming a listed file is unchanged. The chief may propose necessary companion tests, fixtures,
existing callers and mechanical baseline cleanup within the approved feature or module seam as one
exact scoped plan amendment. A fresh independent review must pass before added paths are written;
the chief then regenerates the dispatch or card and reruns admission. Forbidden paths, unrelated
work and material boundary changes remain outside that grant. The execution loop owns the detailed
dependency, overlap and safety checks.

## Current checkpoint

See [the repository's current state](../../../README.md#current-state) for implementation,
validation and remaining limits.

## Validation plan

### Coverage map

| Criterion | Level | Owner |
| --- | --- | --- |
| AC-1–AC-6, AC-10–AC-11, J-1–J-2 | unit + methodology area | T1 |
| AC-7, AC-9, J-3 | failure injection + gate/seal area | T2 |
| AC-8 | byte comparison + existing installer verification | closure |

### End-to-end set

1. **Core delivery:** a closed, approved task enters the ready set, receives the correct lane,
   review and validation, and reaches an accepted result without routine reapproval or timer renewal.
   Explicit deadlines and actual exhaustion still stop affected work.
2. **Causal recovery:** technical corrections in Design, Plan and Implementation retain the same
   cause through A and B, require targeted council plus fresh replan PASS before C, and end without
   a fourth attempt after C failure. Substantive founder choices remain at their gates.
3. **Valid closure:** maintained/public bytes agree, the existing installer verifies them, and the
   full gate, seal and fresh acceptance bind one unchanged candidate.

### Not tested, and why

Consumer bindings, hosted continuation, tag and deployment are outside M2. Conditional publication
uses existing guarded tooling and is verified only after the local closure conditions hold.

### Documentation, installation and closure

Documentation, installation and local closure use their existing owners. Existing guarded
publication may conditionally push the branch or open and merge its pull request only while
exact-tree seal and independent acceptance remain valid. The one-week business-value review uses
the existing evidence record.

### Gate

`cd install && ./install.sh --dry-run && ./verify.sh`

## Trace and stops

T1 and T2 are the only implementation tasks. Documentation, mechanical projection, installation
and closure do not create duplicate cards or reviews. A changed frozen outcome, unadmitted
production write, new interface, changed safety promise, revoked authority or unavailable required
resource stops the affected path for its owner. Failed area/full checks, stale seals and failed
acceptance block integration and closure while unchanged technical correction follows approved
recovery. Numeric review spend prompts diagnosis without changing a verdict. Equivalent or stronger
proof returns to its proof owner and independent test judge; confirmation must preserve coverage,
assertions, freshness, gate obligations and evidence identity, including original failed/skipped
receipts. The same cause retains its A/B/C lineage across renamed attempts. See
[D27](../../decisions/decisions.md#d27--approved-completion-and-technical-recovery) and the execution
methodology for the owning recovery and admission rules.
