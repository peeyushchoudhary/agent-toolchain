---
name: project-onboarding
description: Compatibility entry for explicitly requested project onboarding. The maintained setup procedure is coordinated by methodology-management.
disable-model-invocation: true
---

This explicit invocation selects the
[management setup procedure](../methodology-management/references/setup.md) from the same harness's
installed skills root. Carry forward the user's request, target and existing authority;
do not ask them to invoke another skill. Preserve the setup proposal and adoption decisions,
explicit project-scoped writes, verification and external-action boundaries. Ordinary discovery
reports missing setup without invoking this entry.

### 6 — Record the deliberate methodology decision

Continue with the management setup procedure. Use
`sync_methodology.py --repo <repo> --adoption-check` to identify the existing adoption decision,
then use the management procedure's structured status before changing it. Do not render or adopt
merely because a candidate is available.

## Verify

Delegate the final read-only assessment to
`check_conformance.py <repo>`. If that checker is absent or any check does not run, report
`NOT CHECKED`; do not replace it with hand-rolled partial checks.
