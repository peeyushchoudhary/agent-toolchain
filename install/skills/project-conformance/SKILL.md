---
name: project-conformance
description: Assess whether an existing project still conforms to its approved methodology. Use for a requested health check or relevant reported drift; assessment is read-only.
---

Run `scripts/check_conformance.py <repo> --json` in read-only mode for the requested scope and
report its findings, unanswered checks and repair plan. Do not invoke setup, adoption or migration
implicitly. For an explicitly requested repair, carry the existing authorization to the
[management repair procedure](../methodology-management/references/assessment.md) from the same
harness's installed skills root;
for an unrequested repair or promotion, report the management invocation and proposed scope. This
entry retains implicit assessment without creating a second checker or maintenance procedure.
