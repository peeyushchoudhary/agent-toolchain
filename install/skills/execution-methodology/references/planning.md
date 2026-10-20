# Planning a goal

1. Interview the founder for users, problem and criteria.
2. Write `docs/goals/<id>/spec.md`.
3. Send a scout ([roles.md](roles.md)) for the files, patterns and tests involved.
4. Write `design.md` when `touches:` names anything but `none` ([design.md](design.md)).
5. Write `plan.md` in the skill's format: one-session tasks with `writes`, `reads`,
   `tests-may-change`, the test each adds, `needs:` and a `gate:` under 600 s alone covering the
   module's build, the named test and the tests the writes reach. Lacking `docs/goals/modules.json`,
   draft it by [modules.md](modules.md), committed with the plan; prefer its derived gates to `gate:`
   lines. Time the plan's `gate` once; `goal.py lint` passes.
6. Ask at most five `- Q:` lines under Parked; answers become Decisions lines.
7. The other vendor reviews design, then plan; resolve findings there.
8. The founder tags `goal/<id>/approved`, or tells the chief; never the chief alone.

## Chief's planning rules

MUST
- Cut each task to one session: `writes`, `tests-may-change`, `reads:` as `path#anchor` identifiers including the pattern to copy, one named test; fresh sessions restart from the plan alone.
- Write each criterion as behaviour a human can verify; a task's named test is its instance.
- State what each task's builder must not do: widen scope, touch other tests, add configuration or dependencies.
- Put every magic value, signature, path and test name in the task text; packets carry identifiers, not text.
- Resolve spec, design and plan contradictions before dispatch; an unsettled choice is a Decisions or `- Q:` line.
- Hand the reviewer the diff and criteria, never the builder's report; run the gate yourself.
- Give a milestone that changes what the repository ships a last task writing `README.md`'s Current state.

SHOULD
- Give a needed refactor its own task before the feature task.
- Over-explain user-visible effects; under-specify the incidental.

AVOID
- "Consider several approaches", "be thorough", "double-check", or any verification step beyond the named gate.

## Templates

`spec.md`, at most 400 words, or `What changes for the user: nothing` and the criteria as tests:

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

Declare [test migrations](test-migrations.md) before approval. Frontmatter, layout, README and records: [repository.md](repository.md).
