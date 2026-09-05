---
name: methodology-management
description: Assess, set up, repair, migrate, or upgrade a repository's execution methodology. Use for methodology maintenance requests and explicitly routed setup gaps. Ordinary implementation follows the project's execution route.
disable-model-invocation: true
---

# Manage the execution methodology

This explicit entry point preserves the onboarding and migration invocation boundary. Session
checks and implicit read-only conformance report gaps; they do not invoke this skill or start a
promotion procedure. The user invokes methodology-management to coordinate maintenance. Existing
authorization carries through its bounded steps.

Inspect the target repository and current authorization. Ask the methodology owner for structured
status, then run conformance for the requested scope:

```bash
python3 "$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py" --repo <repo> --status-json
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" <repo> --json
```

Read each payload and finding, not only the exit code. Distinguish the project-approved runtime,
installed source, and available candidate. An unanswered check is not a pass.

Load one relevant procedure:

- Assessment or repair: [references/assessment.md](references/assessment.md).
- New setup or adoption: [references/setup.md](references/setup.md).
- Product-document migration: [references/migration.md](references/migration.md).
- Methodology/model upgrade or changed policy: [references/upgrades.md](references/upgrades.md).

Keep existing validators and generators authoritative. Preview exact project/global paths and any
removals. Preserve project overlays, adoption decisions, custom files and the approved runtime. A
version or digest change is not routine repair without provenance and authority.

Present substantive choices together with a recommendation, evidence and impact. Execute
already-authorized mechanical work without repeated confirmation, verify the actual result, and
report remaining gaps. Assessment alone authorizes no application; new adoption, policy/model
changes and external actions need session authority.

If execution was requested, return to the approved project route. Do not load maintenance
procedures during ordinary governed work. Shared runtime rules remain in execution-methodology.
