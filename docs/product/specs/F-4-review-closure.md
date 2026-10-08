---
id: F-4
title: Review closure that ends in fixes, not in grants
prd: docs/product/README.md
status: approved
updated: 2026-10-08
milestone: M1
edge_cases: [repeated-failure, founder-unavailable]
---

# F-4 — Review closure that ends in fixes, not in grants

## Why

F-3 was the first goal executed under v6. Its review rounds terminated as designed, but the
patterns below made them end in founder grants rather than in fixes. Every blocking finding that
was checked locally reproduced, so the cost came from how findings were fixed, not from the
reviewer.

- **Corrections lost the reasons behind existing behaviour.** A correction packet said what to
  change and not what to keep. A T9 builder removed a `core.hooksPath` skip that existed for a
  reason, and the M4 acceptance review caught the resulting regression one milestone later.
- **Corrections fixed instances of a defect family.** The T9 security review blocked in rounds 1–3
  on three different paths by which hook writes could leave the project. Each correction closed one
  path. The family closed only when the design changed, in round 4. M4 acceptance then blocked
  in rounds 2–4 on one question, where git runs hooks: an empty `core.hooksPath`, then three
  path forms (a trailing space, a missing component, a case-insensitive name), then `GIT_CONFIG`.
  It closed when the claim shrank to "install only when `core.hooksPath` is unset". In both
  families the input space was open (environment, configuration, paths, an external tool's
  rules), so a top-effort reviewer always found one more instance.
- **Code re-implemented an external tool's rules and tested its own guesses.** M4's checks
  emulated git (`strip`, `resolve`, path equality, dropped variables), and their tests asserted
  the emulation. A test comparing the decision with git's own answer under the same environment
  would have failed locally in round 1, at no review cost.
- **Designs printed fix commands nobody ran.** F-5's design blocked three rounds running on a
  printed remediation that did not clear the condition it named.
- **A review packet can silently narrow the milestone.** M4's round 1 reviewed only the files
  passed as `--subject`, because on acceptance those paths also filter the diff.
- **Test-proven fixes still spent the round cap.** v6 says a blocking finding turned into a test
  that fails before and passes after needs no rereview. But acceptance and risk reviews need a
  fresh PASS on the new tree, so in practice every test-closed fix spent a capped round.

F-3's evidence, from `.runs/F-3/verdicts/rounds.json` and the plan's Decisions:

- M3 acceptance needed 5 rounds per partition, 3 of them founder-granted.
- T9's security review needed 4 rounds, 2 of them founder-granted.
- M4 acceptance needed 5 rounds, 3 of them founder-granted; rounds 2–4 were one defect family.
- Of F-3's 11 blocking rounds, 6 found a further instance of a family already found, and 1 was a
  correction that removed an earlier fix.
- v6 targets two founder touchpoints per milestone: goal approval and merge. F-3 added eight
  founder decisions, admitting 11 rounds past the cap.

## Outcome

- A correction carries the reasons for what it must keep.
- A defect family is fixed at the family level: at the first finding when the input space is
  open, and at the latest when a rereview marks a repeat.
- Code that predicts an external tool's behaviour is tested against the tool, and every printed
  fix command is tested to clear its condition.
- An acceptance packet reviews the whole milestone unless a declared partition narrows it.
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
2. **Open input space.** A blocking finding's trigger lies in an open input space: environment
   or configuration, filesystem paths, an external tool's behaviour, or concurrency. The first
   correction already targets the class. Its packet states the invariant, or the narrower claim,
   that makes the whole class impossible, and lists the sibling triggers it considered; the
   builder tests them.
3. **Same family.** In a rereview, the judge marks any blocking finding that is a new instance of a
   finding under rereview: the same mechanism on a different path. The chief then corrects the
   family, not the instance, and records the family fix in Decisions. A family fix that changes
   the design, the scope or a durable interface goes to the founder.
4. **Planning against an external tool.** A task whose code predicts what an external tool will
   do carries an oracle test: it runs the tool under the same environment over the setups the
   code must handle, and compares. A design or task that prints a fix command carries a test that
   runs the command and shows the condition clears.
5. **Acceptance packet.** The chief runs acceptance for a milestone. Paths passed with
   `--subject` are reading context; only a declared partition narrows the diff. The packet states how many of the milestone's
   changed files the diff covers, so a narrowed or empty diff is visible to the chief and the judge.
6. **Test-closed confirmation.** Every blocking finding of the last round is closed by a named test
   that the correction added or changed. The chief runs the rereview with `--closed-by` and those
   tests. `review.py` checks the claim and records the round as a confirmation that does not count
   toward the cap. This happens at most once per subject.

## Acceptance criteria

| ID | Criterion | Proof |
| --- | --- | --- |
| AC-1 | `references/run.md` requires every correction packet to carry a Keep list: behaviours established by earlier verdicts, Decisions or tests in the code the correction touches, each with its reason. A builder who must remove a Keep item stops and reports instead. | full gate; acceptance review of the rules text |
| AC-2 | A rereview packet asks the judge to mark each blocking finding that is a new instance of a finding under rereview. `references/review.md` says the next correction then targets the family, records it in Decisions, and goes to the founder when it changes the design, the scope or a durable interface. It also says that a first finding whose trigger lies in an open input space (environment or configuration, filesystem paths, an external tool's behaviour, concurrency) is corrected at the class: the packet states the invariant or narrower claim and the sibling triggers, and the builder tests them. | `test_review*.py`; acceptance review of the rules text |
| AC-3 | `review.py --closed-by TEST...` admits a rereview that does not count toward the cap, at most once per subject, only when (a) the subject's last verdict is BLOCK and (b) every named test file differs from its content at the subject's last round: the digest that round recorded for it, else the blob in that round's verdict tree, else absence (a new file). The confirmation is recorded in `rounds.json` and the verdict header, and the packet names the tests. Anything else is refused with exit 1, and the founder grant is unchanged. | `test_review*.py` |
| AC-4 | The size budgets in `install/tests/test_size.py` hold unchanged (rules ≤ 1,500 words, any one role's load ≤ 3,000, methodology and persona code ≤ 2,500 lines), and the repository gate passes. | full gate |
| AC-5 | `docs/decisions/decisions.md` records the decision, its reason and the alternative it beat. `docs/product/measurements.md` records F-3's round and grant counts with date and source. `docs/architecture/lean-execution.md` states the new closure rules as current state. `docs/agents/lessons.md` records how git locates hooks and what graphify's hook does in a linked worktree, as F-3 and F-5 established them. | full gate; acceptance review |
| AC-6 | `references/planning.md` requires an oracle test for code that predicts an external tool's behaviour (the tool run under the same environment over the setups the code must handle) and a test for every fix command a design or task prints (it runs the command and shows the condition clears). | full gate; acceptance review of the rules text |
| AC-7 | For acceptance, `review.py` narrows the diff only to a declared partition's paths; other `--subject` paths are reading context. Every acceptance packet states how many of the milestone's changed files its diff covers. | `test_review*.py` |

## Non-goals

- Running a test against the pre-fix tree to prove that it failed before. The judge checks that
  the tests reproduce the finding.
- Raising the cap, letting an advisor grant rounds, or changing the founder grant.
- Rating findings by likelihood or impact, so that a real but rare correctness finding is queued
  instead of blocking. Class-level correction removes most of the need, and the rating would
  invite real defects through. Founder decision, 2026-10-08.
- Carrying a PASS forward to a new tree when the change misses a partition's paths. F-3 spent
  four PASS rounds on re-closes, but the rule needs its own design and a measurement first; it is
  queued.
- Changing where review runs, or who judges.
- The code-context mechanism: the progressive-disclosure route and task packets stay as they are,
  and graphify stays optional.
- A global install, a merge or a push.

## Non-functional constraints

- Python 3.10+, standard library only.
- The changes to the rules text are word-neutral across `SKILL.md`, `methodology.md` and
  `references/run.md`, because `run.md` sits at the 3,000-word role-load budget.
