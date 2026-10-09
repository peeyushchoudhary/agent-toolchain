# S-2 spec: methodology v7.1

**Users and problem.** The founder (approves, merges) and the chief session (plans, dispatches). After
S-1 the Outcome is the whole specification, packets carry no reading list, roles are undeclared,
and exhaustive knowledge must be loaded whole.

**What changes for the user.** Bounded documents (spec, design when an interface is touched, plan)
cite exhaustive pages by section; tasks name what builders read; roles declare model and effort;
long pages carry a summary and load by anchor.

**Acceptance criteria.**

- AC1 WHEN a task has `writes:` and no `reads:` THE SYSTEM SHALL fail `goal.py lint`.
- AC2 WHEN `spec.md` is absent, over 400 words, or lacking a required heading outside the
  two-line form, or `touches:` names anything but `none` and `design.md` is absent, THE SYSTEM
  SHALL fail `goal.py lint`.
- AC3 WHEN a `[Tn]` commit after approval changes `spec.md` or the Interfaces or Data touched
  section of `design.md` THE SYSTEM SHALL report it under `done` row 4, unlisted in `protected:`.
- AC4 WHEN an `ACn` of `spec.md` appears in no task of `plan.md` THE SYSTEM SHALL fail `goal.py lint`.
- AC5 WHEN a page under `docs/`, other than the index and `docs/goals/**`, lacks `summary` (≤120
  words), `read-when`, `covers` or `last-verified`, or `docs/README.md` differs from the generated
  index, THE SYSTEM SHALL fail `docs.py lint`.
- AC6 WHEN a `reads:` entry names `path#anchor` THE SYSTEM SHALL print its file and line range,
  and fail when the anchor does not exist.
- AC7 WHEN a page declares `covers:` THE SYSTEM SHALL generate the pointer files for both
  harnesses, never over an existing unmarked file, and `docs.py lint` SHALL fail on a hand-edited one.
- AC8 WHEN commits since a page's `last-verified` touched a path under its `covers:` THE SYSTEM
  SHALL list the page.
- AC9 WHEN the skill installs THE SYSTEM SHALL place builder, reviewer and scout agent files, with
  model and effort, for both harnesses; uninstall SHALL remove only those.
- AC10 WHEN `goal.py packet --approval` runs THE SYSTEM SHALL write one HTML page from spec,
  design and plan.
- AC11 Always-loaded prose SHALL stay at or under 1,350 words; cost SHALL be recorded per session
  and never enforced.

**Non-goals.** Agent memory scopes; a graph or wiki; a model-judged done; a second reviewer; a
dollar budget; `run.sh`'s permissions.

**Constraints.** Python 3 standard library and bash; both harnesses served from `install/`; no
private facts in this public repository.
