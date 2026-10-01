# Cost, accuracy and velocity pilot — 2026-09-30

**Status: earlier proposal retained as background rationale. Its pre-rollout pilot and cheaper-model
promotion recommendations are superseded by the [quality and velocity replan](velocity-and-quality-replan.md).
They are not part of the current intended rollout. Savings and quality improvements remain unmeasured.**

Optimize accepted and integrated outcomes per native cash/allowance unit and elapsed time. Token
price, commit count, churn and benchmark rank describe different things; none alone measures that
outcome.

## Current evidence

[measurements.md](../measurements.md) records dated price snapshots, an unmeasured architect model
pilot and a twelve-case reasoning smoke test. The smoke test did not cover long coding sessions,
implementation quality, permissions, elapsed delivery time or rare defects. Historical cold
cross-harness review cost roughly 1.7 times its matched in-harness comparison. That is a dated
experiment, not a universal multiplier.

The historical fleet observation also associates warm controllers with more delivered commits and
fewer stalled sessions. Tasks and projects differ, so the association does not establish causality.
It supports testing a warm chief, role-specific context and bounded handoffs before buying more
orchestration.

The installed parent selects GPT-6.1 Sol at `xhigh`; several generated persona defaults remain on
older assignments. Parent and subagent settings are distinct. Neither choice was changed during
this assessment.

Current standard API pricing for GPT-6.1 Sol is $2 uncached input, $0.10 cache read, $2.50 cache write
and $10 output per million tokens. Large-input, fast-mode and regional premiums can change the
arithmetic. This is API pricing, not subscription billing or realized cost in this workspace.
[Official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

An illustrative 40,000 uncached-input/8,000-output request costs $0.16 at those standard rates,
excluding tool fees and other modifiers. It is a token-mix example, not an estimate per accepted
task. Rework, rejected outputs and idle founder time belong in the comparison.

## Routing candidates

| Work | Pilot candidate | Evidence needed before changing defaults |
| --- | --- | --- |
| Chief, complex implementation, ordinary review | Current role assignment versus GPT-6.1 Sol | Matched task acceptance, defects, latency and full usage |
| Bounded implementation in Claude Code | Current assignment versus Claude Sonnet 5.5 | Task acceptance, escalation, latency and actual consumption |
| Mechanical source location and small bounded transformations | Available lower-cost model such as GPT-6 Luna | Escalation correctness and missed-reference checks |
| Test execution | Deterministic scripts; agent interprets actual results | No invented pass, skipped/zero-test detection, correct failure routing |
| Architecture, migration, security and acceptance | Keep current assignment until a dedicated challenge set exists | Boundary defects, rare deny paths, independent verdicts |
| Routine controller decisions | Current effort versus a lower effort in a separate experiment | Correct admission, recovery and stop decisions |

Changing model and effort together hides which caused a difference. Promote per role, not by
blanket roster replacement. Preserve persona ownership and permission boundaries independently
of model economics. Actual availability must be checked in the client/account used for the pilot.

Sonnet 5.5's standard API rates are $2 input, $0.20 cache read and $10 output per million tokens,
the same headline rates as Sonnet 5. Its announced savings depend on fewer tokens per task, which
needs local verification. [Anthropic announcement](https://www.anthropic.com/claude-sonnet-5-5).
Run each persona pilot in its own harness; this proposal does not reintroduce cross-harness dispatch.

## Context and local execution

Load the complete common rules plus only the relevant stage/task paths. Keep stable instructions
and tool definitions in a stable order; put task-specific context afterward where the harness
permits. Preserve a compact recovery pointer and decisions, while trimming repeated raw logs from
model context. Small output does not mean throwing away the external raw evidence.

Caching requires matching prefixes; do not pad requests merely to reach a threshold. Measure cache
reads, writes and uncached input separately, since cache creation can cost more than an uncached
read. API documentation supports this direction, while native-client cache behavior still needs
observation. [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching),
[Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).

Reuse independent successful gate evidence only while its source, command, runtime and relevant
environment remain valid. The writer's diagnostics and the judge's independent run serve different
purposes. Remove repeats of unchanged judge evidence; retain the required independent run. Run
preflight immediately before an expensive gate, keep one heavy gate active, and investigate wider
concurrency only when the critical path and machine capacity justify it.

## Measurement without another process system

The existing assessment owner joins session, task, Git, trace, seal, acceptance and validation
identifiers in the existing task distillation. Begin with a read-only extraction from available
logs and receipts. Do not invent another ledger or store full prompts in this public repository.
If essential fields are missing, propose a narrow extension to existing handoff/receipt metadata
through the owning design route. Missing observations remain unknown.

| Measure | Definition |
| --- | --- |
| First-pass acceptance | Accepted on first independent review / all attempted tasks |
| Final acceptance | Eventually independently accepted / all attempted tasks |
| Regressions | Confirmed defects and escaped regressions by severity / integrated tasks |
| Economics | Actual cash / accepted task; allowance / accepted task reported separately |
| Usage | Uncached input, cache reads, cache writes and output / accepted task |
| Delivery | Dispatch-to-acceptance and acceptance-to-integration elapsed distributions |
| Interruptions | Founder, quota and gate wait minutes; question counts classified by cause |
| Redundant verification | Same-input repeat runs / total gate runs, with invalidation reasons |

## Pilot design

Use 24–40 representative frozen tasks, stratified by role, complexity and safety, plus three
representative milestones for the chief workflow. Pair old and candidate runs on the same source,
tool/runtime inputs, resources and criteria. Randomize order and blind independent verdicts. Count
tool/model failures and stopped tasks in the denominator. Use separate checkouts when testing
alternative implementations; serialize heavy service gates on the laptop.

Include interruption recovery, multi-module edits, plausible but nonexistent APIs, review repairs,
stale evidence, permission denials and integration regressions. Use hidden defect cases and a held
out set; a matching test name is insufficient. Real task-specific evaluations and calibrated
pass/fail or paired judgement follow [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

Report paired differences and uncertainty. A small pilot can reject a bad candidate and reveal
cost/wait patterns; it cannot establish rare-defect safety or broad statistical non-inferiority.
Require no missed critical/safety case, unchanged local gates, zero avoidable routine approval
questions and a favorable observed economics/velocity tradeoff before bounded promotion. Retain
current specialist defaults when evidence is insufficient. Actual savings remain unknown until
usage and accepted outcomes can be joined.
