# Velocity and quality replanning direction — 2026-09-30

**Status: draft requirements direction. Not a frozen spec, design, plan, activation decision or
implementation approval.**

The [F-2 candidate definition](../specs/F-2-goal-directed-autonomy.md) and
[M2 candidate milestone](../milestones/M2-goal-directed-autonomy.md) were revised after an advisory
overhead audit. They remain draft and require their actual review closure and founder Gates 1 and 2.

## Why this is being replanned

The desired outcome is multiple accepted, integrated business-value deliveries each week, faithful
to closed product and UX intent and supported by passing validation. The earlier proposal made
matched model-routing and economics pilots part of the route to promotion. That ordering does not
serve the revised priority, so there will be no pre-rollout benchmark or cheaper-model pilot.

Usage and cost remain delivery constraints to optimize after quality and velocity. Quota survival
for a calendar week is not a success criterion. A cheaper API rate does not establish lower
subscription consumption or better accepted-work economics. Usage must be observed in its native
unit during delivery; plan guidance says model, context, reasoning, tools and caching can affect
usage ([usage limits](https://learn.chatgpt.com/docs/pricing#what-are-the-usage-limits-for-my-plan)).

Frequent approval requests are costly when no meaningful product choice exists. Requirements,
design and planning can also miss the real user journey, cross-layer consumers, or UX authority.
Those gaps cause adjacent fixes, repeated review and delayed visible outcomes. The revised workflow
must expose them before dispatch and let approved routine work continue.

The existing workflow already has one scheduling owner, Git-derived progress, light and full task
lanes, fresh independent judges, bounded repair and local gates. Replanning should preserve those
controls while closing evidence and authority gaps. A printed nonpass must not return success, and
a gate that changes the source it tested must not receive a successful milestone seal.

## Confirmed direction

- Before requirements closure, the product steward reads approved existing project evidence and
  uses founder brainstorming and interviews to probe actors, problem, outcome, priorities,
  non-goals, literal journeys and states, privacy and other constraints, dependencies, real existing
  consumers and local verification prerequisites. Facts and assumptions are distinguished;
  contradictions, alternatives and tradeoffs are challenged. Decisions update existing product
  artifacts without an interview form, transcript, score, counter or board.
- Planning closes whole-product goals, journeys, shared constraints and dependencies, then fully
  plans one coherent milestone batch. Uncertain future features remain roadmap context rather than
  detailed frozen scope. Each milestone keeps its own seal, acceptance and publication tuple; batch
  coverage grants no future-milestone, merge, tag or deployment authority. Merge requires the
  milestone's matching explicit standing conditional Gate 3 founder grant.
- Product UX design is a separate milestone or set of milestones, and one UX milestone may group
  multiple features. It first closes or expands branding as needed, including palette and logo;
  then brainstorms user journeys with the founder; then presents variations journey by journey,
  iterates with the founder and finishes with an approved design. That approved design is
  authoritative implementation input rather than reference material.
- Requirements, technical design and plan receive thorough independent challenge from only the
  relevant lenses before their founder gate. Councils are targeted to conflicting evidence or
  cross-domain risk rather than required for every task. Implementation planning follows the
  approved UX design and preserves it through observable fidelity validation.
- The chief remains the sole scheduling owner, watches ready work, sends concise context paths and
  complete rules, delegates most implementation, routes review and validation to fresh independent
  judges, and critically checks their claims through bound evidence. Required independent review
  and validation cannot be omitted.
- Each task binds to a frozen criterion and observable outcome. Work uses the narrowest existing
  production path and earliest end-to-end vertical slice; speculative abstractions, unused future
  configuration, extra alternatives and preference-only review blockers are excluded. Repairs test
  the smallest causal hypothesis and proof before a broader rebuild.
- Once the reviewed design and plan are approved, execution continues toward accepted, sealed and
  reviewably published milestone completion. Time, checkpoints and session boundaries do not create
  an expiry or paused-resource gate; revocation, invalid scope, finite resource exhaustion and
  genuine blockers still stop affected work.
- After a failed correction, the controller diagnoses the causal path and tries a materially
  different approach within the closed outcome, design, UX and safety boundaries. A stronger
  native-approved model or higher effort may be used as soon as concrete causal evidence justifies
  it; other expert lenses remain need-based. If approaches A and B fail, a targeted council is
  mandatory and a fresh independent reviewer passes the technical replan before C starts.
  If C fails, the founder receives the decision packet; no fourth approach starts automatically and
  no failure becomes a pass.
- A milestone proceeds through implementation, independent review, local end-to-end validation, a
  trustworthy seal and independent acceptance. It then pushes the milestone branch and opens its
  pull request automatically. When its plan is closed and an explicit standing conditional Gate 3
  founder grant matches, it merges only after quality gates, seal and fresh acceptance; PASS alone
  creates no authority. Tag and deployment remain separate manual founder decisions. After merge
  the chief continues the next fully approved milestone. Independent approved work may continue
  around a genuine merge blocker, but stacked pull requests are not authorized.
- The delivered behavior covers the maintained SWE Agent source and both installed Codex and Claude
  workflows, each operating through its native harness. Private-project bindings are upgraded
  separately later and are neither activated nor changed by this rollout.

## Candidate observable outcomes

**Unapproved feature-spec inputs:**

1. When a weekly review runs, it identifies the accepted, integrated outcomes that created visible
   user or business value, their elapsed delivery, defects and rework. It does not use commit,
   session or document counts as substitutes.
2. When a feature or grouped feature set needs UX, implementation planning does not start until its
   UX milestone has completed the branding, founder journey brainstorming, journey-specific
   variations and iteration sequence and recorded the approved design as authoritative input.
   Candidate closure checks include important states, responsive behavior, accessibility and the
   integration inputs implementation needs; their exact content comes from the approved design.
3. When a cross-layer behavior is planned, the plan names the visible journey and every known
   producer, registry, configuration, substitute, provider and verification consumer needed to
   deliver it.
4. When an approved milestone starts or resumes, ready work continues until accepted, sealed,
   conditionally merged under its matching founder grant, or until revocation or a genuine blocker,
   while retaining finite resources, fresh independent review and executable validation.
5. When concrete causal evidence justifies it, a stronger native-approved model or higher effort
   may be used immediately. When approaches A and B fail, a targeted council and fresh independent
   reviewer PASS on the replan are mandatory before C. If C fails, the founder receives the packet
   before any fourth approach; the lineage and failed verdicts remain visible.
6. When a local gate reports an integrity, cleanup or evidence failure, the gate returns nonpass.
   When tracked source or bound inputs change, seal recording and verification are refused with the
   mismatch visible.
7. When the complete local gate passes, a genuine seal records the bound candidate and evidence.
   Fresh independent acceptance then judges the required journey against that same sealed candidate
   before its branch is pushed and pull request opened. A matching explicit conditional Gate 3 grant
   permits merge only while quality gates, seal and acceptance still hold; PASS alone grants
   nothing. Tag and deployment retain separate manual authorization.
8. When one week of real use has elapsed and at each weekly review thereafter, the review also
   reports interruptions, quota waits and native usage evidence. It does not infer subscription
   consumption from API prices or substitute a synthetic benchmark for real delivery.

This requirements task does not generate branding or UX assets; those belong to the approved UX
milestone execution.

## Process-overhead audit rationale

In the 2026-09-30 audit, four fresh advisory seats found duplicate cards, reports, reviews and
unchanged-state checks in the candidate plan. The revision reduced the proposed route from 12 Full
cards to 7 Full stage cards plus 1 Light dispatch, from 12 semantic reviews to 6, and from 10
security reviews to 5. These historical counts are rationale, not a latency claim.

The retained controls are the complete Full schema for actual durable or safety changes, exact
write boundaries, one chief owner, one compact report and joint review per logical task, valid
same-referent evidence reuse, final installed routing, and one genuine integrated gate, seal and
acceptance. The audit is advice rather than a formal verdict or founder approval. Current scope and
checkpoint status live in [F-2](../specs/F-2-goal-directed-autonomy.md),
[M2](../milestones/M2-goal-directed-autonomy.md), the
[design](../../architecture/goal-directed-execution.md) and the
[plan](../plans/F-2-goal-directed-autonomy.md); they record accepted installed implementation while
M2 remains unsealed and unaccepted, with no publication claimed.
