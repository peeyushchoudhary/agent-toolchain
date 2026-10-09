# Planning a goal

1. Interview the founder until users, problem and criteria are plain.
2. Write `docs/goals/<id>/spec.md`.
3. Send a scout ([roles.md](roles.md)) for the files, patterns and tests involved.
4. Write `design.md` when `touches:` names anything but `none` ([design.md](design.md)).
5. Write `plan.md` in the skill's format: one-session tasks, each with `writes`, `reads`,
   `tests-may-change` and the test it adds; `goal.py lint` passes.
6. Ask at most five questions, as `- Q:` lines under Parked; at approval each answer becomes a
   Decisions line.
7. The other vendor reviews the design, then the plan; resolve findings in them.
8. The founder approves: tag `goal/<id>/approved`.

## Chief's planning rules

MUST
- Cut each task to one session: `writes`, `tests-may-change`, a `reads:` line of `path#anchor` identifiers that includes the pattern to copy, and one named test; a fresh session restarts from the plan alone.
- Write each acceptance criterion as behaviour a human can verify; the task's named test is its instance.
- State in each task what the builder must not do: widen scope, touch other tests, add configuration or dependencies.
- Put every magic value, signature, path and test name in the task text; the packet carries identifiers, never pasted text.
- Resolve contradictions between spec, design and plan before dispatch; a choice the plan does not settle is a Decisions line or a `- Q:` line.
- Hand the reviewer the diff and the criteria, never the builder's report; run the gate yourself.

SHOULD
- Give a refactor the goal needs its own task before the feature task.
- Over-explain user-visible effects; under-specify incidental implementation.

AVOID
- "Consider several approaches", "be thorough", "double-check", or any verification step beyond the named gate.
- A task whose test is "it works": name the file and the assertion.

## Templates

`spec.md`, at most 400 words, or the two lines `What changes for the user: nothing` and the
criteria as the goal's tests:

```
# <id> spec: <title>
**Users and problem.** <who; what fails today>
**What changes for the user.** <the visible difference>
**Acceptance criteria.**
- AC1 WHEN <event> THE SYSTEM SHALL <behaviour>.
**Non-goals.** <out of scope>
**Constraints.** <stack, data, privacy>
```

`design.md`: `## Structure`, `## Interfaces`, `## Data touched`, `## Smallest change`,
`## Rejected options`.

Every `docs/` page but the index and `docs/goals/**` starts:

```
---
summary: <at most 120 words>
read-when: <one line>
covers: [src/area/**]
last-verified: YYYY-MM-DD
---
```
