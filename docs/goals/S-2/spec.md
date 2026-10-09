# S-2 spec: methodology v7.1

**Users and problem.** The founder and the chief session. The Outcome is the whole
specification, packets have no reading list, roles are undeclared, exhaustive knowledge loads
whole, goals run headless.

**What changes for the user.** Bounded documents (spec, design, plan) cite exhaustive pages by
section; tasks name what builders read; roles declare model and effort; long pages load by anchor;
goals run in the founder's own session.

**Acceptance criteria.**

- AC1 WHEN a task of a goal with a `spec.md` has `writes:` and no `reads:` THE SYSTEM SHALL fail
  `goal.py lint`.
- AC2 WHEN `spec.md` is absent before approval, over 400 words or lacking a required heading
  (two-line form excepted), or `touches:` is not `none` without `design.md`, THE SYSTEM SHALL fail
  `goal.py lint`.
- AC3 WHEN a `[Tn]` commit after approval changes `spec.md` or the design's Interfaces or Data
  touched THE SYSTEM SHALL report it under `done` row 4 unlisted.
- AC4 WHEN an `ACn` appears in no task of `plan.md` THE SYSTEM SHALL fail `goal.py lint`.
- AC5 WHEN a `docs/` page (index and `docs/goals/**` excepted) lacks `summary` (≤120 words),
  `read-when`, `covers` or `last-verified`, or the index table is not the generated one, THE SYSTEM
  SHALL fail `docs.py lint`.
- AC6 WHEN a `reads:` entry names `path#anchor` THE SYSTEM SHALL print its line range, failing on
  a missing anchor.
- AC7 WHEN a page declares `covers:` THE SYSTEM SHALL generate both harnesses' pointer files,
  never over an unmarked file, and fail lint when hand-edited.
- AC8 WHEN a commit after a page's `last-verified` touched its `covers:` THE SYSTEM SHALL list
  the page.
- AC9 WHEN the skill installs THE SYSTEM SHALL place builder, reviewer and scout agents with
  model and effort in both harnesses; uninstall SHALL remove only those, unedited.
- AC10 WHEN `goal.py packet --approval` runs THE SYSTEM SHALL write one HTML page from the three
  documents.
- AC11 Always-loaded prose SHALL stay at or under 1,350 words; cost SHALL be summed from the
  harness transcripts (`goal.py cost`), never enforced.
- AC12 WHEN the founder asks the session to run a goal THE SYSTEM SHALL resume it there from
  `goal.py resume`, with no launcher, loop or Stop hook.

**Non-goals.** Agent memory; a graph or wiki; a model-judged done; a second reviewer; a dollar
budget.

**Constraints.** Standard-library Python 3 and bash; one `install/` source for both harnesses; no
private facts.
