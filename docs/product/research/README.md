# SWE Agent research and replanning

**Status: dated rationale with current checkpoint routing.** Approved current authority lives in the
[F-2 specification](../specs/F-2-goal-directed-autonomy.md),
[M2 milestone](../milestones/M2-goal-directed-autonomy.md),
[design](../../architecture/goal-directed-execution.md) and
[implementation plan](../plans/F-2-goal-directed-autonomy.md). Published executable behavior lives
in `install/`; the plan records the accepted release candidate and durable publication conditions.

## Current status

The two file-disjoint core-first implementation tasks are accepted, byte-consistent across their 13
candidate/public/installed-Claude/installed-Codex mappings, and installed through the existing
installer. The repository gate and installed scheduler checks pass; the implementation candidate
was sealed and independently accepted, and a fresh normal-configuration native Codex read-only
activation run passes. Claude skills, hooks and personas are statically verified; authenticated
Claude inference is deferred. The final documentation tree is sealed and independently accepted.
Exact-tree seal and independent acceptance remain required conditions for guarded conditional
branch push, pull request and merge. Existing pinned consumer bindings remain unchanged; tag and
deployment are excluded, and the one-week review remains future.

Private frozen reports and failed verdicts remain immutable evidence. The replacement does not
relabel them as passing; it makes their retired approach non-authoritative for current execution.

## Research record

| Read | Status and contents |
| --- | --- |
| [Velocity and quality replan](velocity-and-quality-replan.md) | Requirements intake and direction; read through the approved F-2 artifacts |
| [Implementation audit](implementation-audit.md) | Dated assessment of concrete gaps and observed evidence |
| [Earlier autonomy proposal](autonomy-proposal.md) | Background proposal; superseded where it describes native-first execution |
| [Earlier economics and pilot](economics-and-pilot.md) | Background analysis; pre-rollout pilot direction superseded |
| [External research](external-research.md) | Dated external sources, checked 2026-09-30 |
| [Safety and verification](safety-and-verification.md) | Dated safety assessment; no current activation claim |
| [Stage boundary companion](../plans/goal-directed-autonomy-task-boundaries.md) | Non-authoritative exact mapping for the approved plan |

## Publication and review

1. Existing guarded publication may conditionally push the branch or open and merge its pull
   request only while exact-tree seal and independent acceptance remain valid.
2. Review business value after one week from existing evidence, without a pilot or new apparatus.
