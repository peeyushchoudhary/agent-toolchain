---
id: F-4
title: Review closure that ends in fixes, not in grants
prd: docs/product/README.md
status: approved
updated: 2026-10-07
milestone: M1
edge_cases: [repeated-failure, founder-unavailable]
---

# F-4 — Review closure that ends in fixes, not in grants

## Why

F-3 was the first goal executed under v6. Its review rounds terminated as designed, but three
patterns made them end in founder grants rather than in fixes:

- **Corrections lost the reasons behind existing behaviour.** A correction packet said what to
  change and not what to keep. A T9 builder removed a `core.hooksPath` skip that existed for a
  reason, and the M4 acceptance review caught the resulting regression one milestone later.
- **Corrections fixed instances of a defect family.** The T9 security review blocked in rounds 1–3
  on three different paths by which hook writes could leave the project. Each correction closed one
  path. The family closed only when the design changed, in round 4. M4 acceptance then blocked
  in rounds 1 and 2 on two values of `core.hooksPath`: one set to a path, then one set to an
  empty string. Both came from one mechanism: the check read a config value instead of asking git
  where it runs hooks.
- **Test-proven fixes still spent the round cap.** v6 says a blocking finding turned into a test
  that fails before and passes after needs no rereview. But acceptance and risk reviews need a
  fresh PASS on the new tree, so in practice every test-closed fix spent a capped round.

F-3's evidence, from `.runs/F-3/verdicts/rounds.json` and the plan's Decisions:

- M3 acceptance needed 5 rounds per partition, 3 of them founder-granted.
- T9's security review needed 4 rounds, 2 of them founder-granted.
- M4 acceptance needed 4 rounds on one defect family, 2 of them founder-granted.
- v6 targets two founder touchpoints per milestone: goal approval and merge. F-3 added seven
  founder decisions to admit extra rounds.

## Outcome

- A correction carries the reasons for what it must keep.
- A repeated defect family is fixed at the family level.
- One test-proven confirmation per review subject does not spend the round cap.

The cap still guarantees that every review loop ends.

## Actors

- **Chief:** writes correction packets, runs `review.py` and decides the next correction.
- **Builder:** implements a correction.
- **Judge:** a read-only reviewer from the other vendor.
- **Founder:** grants a round past the cap. That role is unchanged.

## Journeys

1. **Correction with reasons.** A review blocks, and the chief writes a correction packet. The
   packet has a **Keep** list: the behaviours in the code the correction touches that earlier
   verdicts, Decisions or tests established, each with its reason. A builder who cannot fix the
   finding without removing a Keep item stops and reports.
2. **Same family.** In a rereview, the judge marks any blocking finding that is a new instance of a
   finding under rereview: the same mechanism on a different path. The chief then corrects the
   family, not the instance, and records the family fix in Decisions. A family fix that changes
   the design, the scope or a durable interface goes to the founder.
3. **Test-closed confirmation.** Every blocking finding of the last round is closed by a named test
   that the correction added or changed. The chief runs the rereview with `--closed-by` and those
   tests. `review.py` checks the claim and records the round as a confirmation that does not count
   toward the cap. This happens at most once per subject.

## Acceptance criteria

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | `references/run.md` requires every correction packet to carry a Keep list: behaviours established by earlier verdicts, Decisions or tests in the code the correction touches, each with its reason. A builder who must remove a Keep item stops and reports instead. | full gate; acceptance review of the rules text |
| AC-2 | A rereview packet asks the judge to mark each blocking finding that is a new instance of a finding under rereview. `references/review.md` says the next correction then targets the family, records it in Decisions, and goes to the founder when it changes the design, the scope or a durable interface. | `test_review*.py` |
| AC-3 | `review.py --closed-by TEST...` admits a rereview that does not count toward the cap, at most once per subject, only when (a) the subject's last verdict is BLOCK and (b) every named test file differs from its content in that verdict's tree. The confirmation is recorded in `rounds.json` and the verdict header, and the packet names the tests. Anything else is refused with exit 1, and the founder grant is unchanged. | `test_review*.py` |
| AC-4 | The size budgets in `install/tests/test_size.py` hold unchanged (rules ≤ 1,500 words, any one role's load ≤ 3,000, methodology and persona code ≤ 2,500 lines), and the repository gate passes. | full gate |
| AC-5 | `docs/decisions/decisions.md` records the decision, its reason and the alternative it beat. `docs/product/measurements.md` records F-3's round and grant counts with date and source. `docs/architecture/lean-execution.md` states the new closure rules as current state. | full gate; acceptance review |

## Non-goals

- Running a test against the pre-fix tree to prove that it failed before. The judge checks that
  the tests reproduce the finding.
- Raising the cap, letting an advisor grant rounds, or changing the founder grant.
- Changing where review runs, or who judges.
- The code-context mechanism: the progressive-disclosure route and task packets stay as they are,
  and graphify stays optional.
- A global install, a merge or a push.

## Non-functional constraints

- Python 3.10+, standard library only.
- The changes to the rules text are word-neutral across `SKILL.md`, `methodology.md` and
  `references/run.md`, because `run.md` sits at the 3,000-word role-load budget.
