# Persona authoring

Read this before adding or editing a persona, or changing the judge policy in the renderer.

## Rules for a source

- At most 300 words, and at most five sources in the pool, so that a role's whole brief stays
  small enough to read every time it is loaded.
- Calm prose. Give the reason for each boundary, because a reason lets the role decide a case the
  rule did not foresee; emphasis does not.
- Point to the execution methodology for rules it owns (review classes, verdict format, escalation)
  rather than restating them, so there is one copy to keep true.

## Why the judge boundary has this shape

- **The set is fixed in code.** A `writes: no` line is something a persona says about itself. If
  the protected set were derived from it, one edit to that line would remove a judge from every
  check. So membership lives in `JUDGING_PERSONA_NAMES`, and `writes:` is checked against it in both
  directions.
- **An allow-list is the policy.** A deny-list is open to every tool added after it was written;
  earlier versions missed `Monitor`, a shell, that way. A judge names the tools it needs and gets no
  others.
- **The deny-list stays as a second check.** It catches a name added to an allow-list by mistake.
  The two must agree, and disagreement is an error, not something to reconcile silently.
- **Dispatch is denied with writing.** A judge that can start or message another agent can have
  that agent write for it.
- **No judge holds a shell.** A shell can write any file, so a read-only judge with Bash is not
  read-only. Gates are run by the chief, not by judges.
- **Codex has no tool list.** Its boundary is the OS sandbox, so judges render with
  `sandbox_mode = "read-only"`. Codex has no key that denies dispatch; the one-shot judge calls in
  the review reference avoid the question by loading no integrations at all.
- **Rejected, never corrected.** Rendering the right thing from a source that claims otherwise
  would hide the disagreement in the file a human reads.

## Changing routing

Model and effort change only in frontmatter, and `tests/test_routing.py` holds the design's routing
table; change both together, with the design. Keep `xhigh` to reviewer acceptance, the only place
the design allows it.
