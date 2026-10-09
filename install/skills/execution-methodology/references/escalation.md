# Escalation

An unattended run meets choices the plan did not settle. Escalation exists so the run can keep
moving on reversible choices, buy judgement for consequential ones, and leave the founder's
decisions with the founder. It never widens scope or buys an extra review round.

## Ladder

| Situation | Action |
| --- | --- |
| A reversible choice inside the approved outcome: naming, test level, local structure, ordering | Take the smallest option consistent with existing patterns, log it in `Decisions`, continue. |
| A consequential choice: unspecified behaviour with several valid designs, or a task parked after its attempts | **Advisor**, below. |
| Advisor not confident, or the choice is costly to reverse | **Council**, below. |
| A review still blocked after its rereview | Queue it for the founder with the advisor's recommendation attached. It is never closed automatically. |
| A change to criteria, scope or a durable interface; any safety-policy change; any external or irreversible action (merge, deploy, data deletion, paid service, credentials) | **Never escalated.** Queue it, block only the dependent tasks, continue with the rest. |

The never-escalated classes stay with the founder because a model's confidence does not make an
irreversible or policy-changing act safe, and the founder approved the scope and criteria, not a
process for changing them.

## Advisor

One read-only call to the stronger model in the advisor persona, with `GOAL_ROLE=judge`. Send:

- the question, in one or two sentences;
- the options considered;
- the constraints: the relevant criteria and design sections, by path;
- the evidence paths: failing output, the diff, earlier attempts.

The advisor returns a recommendation, a confidence level (high, medium or low) and whether the
choice is reversible. Its verdict goes to `.runs/<goal>/verdicts/`.

- **High confidence and reversible:** adopt it and log it in `Decisions` as "advisor". A parked
  task then gets one new attempt, judged by its deterministic check and guard.
- **Otherwise:** go to the council.

## Council

Three independent read-only members spanning both vendors: two advisors and a reviewer. Each gets
the same packet and answers once, without seeing the others. The chief then synthesises.

- **Unanimous and reversible:** adopt it and log it in `Decisions` as "council".
- **Otherwise:** park the item, queue it for the founder with the members' answers, and continue
  with independent work.

Members answer independently so that each adds its own judgement instead of echoing the first
answer.

## What an escalation may unblock

An advisor or council result may unblock only an item whose closure is then deterministic, decided
by its gate and guard, or a pure choice between options inside the approved outcome. It never
closes a review finding, never replaces an acceptance verdict and never stands in for founder
approval. Those need the evidence a model's opinion cannot supply.

## Limits

- One advisor call and one council per item. A rephrased question about the same item is the same
  item.
- At most three councils per milestone. A milestone that needs more is telling you the plan is
  under-specified; queue that observation.
- Missing approval is never inferred from silence.
- Every default and every escalation result appears in the merge explainer, so the founder can
  reverse it before merging.

## Logging

A `Decisions` entry is dated, names the task, and says what was chosen over what and how:

```
- 2026-10-07 T3: chose X over Y (reversible; default). Advisor: —.
- 2026-10-07 T5: chose A over B (reversible; advisor, high). Verdict: verdicts/T5-advisor.md.
```

A `Queue` entry names what it blocks, the options and a recommendation:

```
- [blocks T5] <question>, options, recommendation
```
