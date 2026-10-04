# M2 stage and task boundaries

**Authority: non-authoritative companion.** The canonical task blocks live in
[the F-2 plan](F-2-goal-directed-autonomy.md). This page records exact maintained/public mappings
and the ordered closure stages so a dispatch does not invent paths or a second implementation route.

## T1 — core workflow

Maintained source writes:

- `skills/execution-methodology/methodology.md`
- `skills/execution-methodology/references/execution-loop.md`
- `skills/execution-methodology/references/specs.md`
- `skills/execution-methodology/references/task-card.md`
- `skills/execution-methodology/scripts/plan_waves.py`
- `skills/execution-methodology/tests/test_execution_loop.py`
- `skills/execution-methodology/tests/test_methodology_policy.py`
- `skills/execution-methodology/tests/test_plan_waves.py`

Public writes are those same eight paths under `install/`. Each declared projection is byte-equal.
The one T1 review sees the maintained change and its public projection together. Projection does not
create another task, card or verdict.

## T2 — gate and seal integrity

Maintained source writes:

- `skills/gate-sandbox/scripts/gate.sh`
- `skills/gate-sandbox/tests/selftest.sh`
- `skills/gate-sandbox/tests/test_selftest_suite.py`
- `skills/execution-methodology/scripts/milestone_seal.py`
- `skills/execution-methodology/tests/test_milestone_seal.py`

Public writes are those same five paths under `install/`. Each declared projection is byte-equal.
The one T2 review sees the maintained change and its public projection together. T1 and T2 share no
write path and may proceed concurrently.

## Current checkpoint

See [the repository's current state](../../../README.md#current-state) for implementation,
validation and remaining limits.

## Ordered stages

1. **Governing closure:** freeze the approved F-2 specification, design, M2 milestone and plan.
2. **Implementation:** dispatch T1 and T2 to separate source builders with their complete rules,
   exact writes, tests, area checks and stops.
3. **Projection and review:** project each accepted source delta to its exact public paths, prove
   byte equality, run the affected public checks, and obtain one fresh complete semantic review per
   logical task plus applicable safety review.
4. **Documentation custody:** update routed current-state documentation from the accepted behavior.
   Do not copy private reports or claim installation or closure before it occurs.
5. **Existing installation:** use the repository's current installer and sync owners. Do not add a
   runner, adapter, service, mode, schema, ledger, model default, permission profile, activation
   lock or consumer binding.
6. **Local closure:** run `cd install && ./install.sh --dry-run && ./verify.sh`; seal and verify the
   unchanged candidate; obtain fresh independent acceptance against the same referent.
7. **Conditional publication:** only after local closure, use existing guarded tooling for the
   actions named by the still-valid grant. Tag and deployment remain separate.
8. **Business-value review:** after one week, read existing evidence for accepted outcomes, quality,
   elapsed delivery, defects, rework, interruptions, quota waits, usage and unknowns. Add no pilot
   or measurement apparatus.

## Recovery boundary

For the same cause, A and B may revise the causal hypothesis and proof. Before C, use a targeted
expert council and require a fresh independent PASS on the technical replan. C failure returns the
decision packet to the founder and starts no fourth approach. Renaming the task, fixture, diagnostic
or stage never resets the lineage.

At an existing recovery or handoff boundary, a proposed new control must identify the approved
criterion it serves, why the existing owner is insufficient and the delivery outcome it unblocks.
Failure to answer is a reason to simplify or use the existing route, not to add machinery.

## Stops

Stop affected work for an unapproved outcome, a widened write set, a new interface or safety claim,
missing required native read-only review, nonpass evidence, source/public byte drift, failed area or
full gate, stale seal, failed acceptance, revoked authority or unavailable required resource.
Preserve all prior failed evidence and continue unrelated work only after proving independence.
