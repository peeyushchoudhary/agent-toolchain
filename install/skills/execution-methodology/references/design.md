# Design page

Write one whenever the plan's `touches:` names anything but `none` (data, auth, external,
interface, ui). One page, `docs/goals/<id>/design.md`, current decisions only:

1. **Structure**: the components the goal adds or changes, and how they connect.
2. **Interfaces**: each interface the Outcome names, with its shape; which ones are durable.
3. **Data touched**: what is read, written, migrated or deleted; backfill and rollback.
4. **Smallest change**: the least that delivers the Outcome, on existing patterns.
5. **Rejected options**: one line each, the option and why not.

## Design review

Whenever `design.md` exists, the other vendor's reviewer ([../agents/reviewer.md](../agents/reviewer.md))
reads it and `plan.md` only, once, before the plan review, and answers:

- Does the structure deliver the Outcome without a second way of doing something that exists?
- Is every durable interface named, and is any break stated in the Outcome?
- Can data be lost, corrupted or exposed, including during migration, rollback or partial failure?
- Who can reach each new capability, and where is that checked?
- Is there a smaller change that meets the Outcome?
- Was any option rejected for a wrong reason?

Resolve its blocking findings in the design before the approval tag.

Builders read Interfaces: a task that builds on one names `docs/goals/<id>/design.md#interfaces`
in its `reads:`.
