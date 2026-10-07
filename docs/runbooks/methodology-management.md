# Methodology management routes

**Retired in v6 (F-3).** The skills, procedures and scripts named below no longer ship; a v5.1
project migrates with [migrate.md](../../install/skills/execution-methodology/references/migrate.md).
This page is kept as history until the documentation rewrite.

**Authority: historical routing (v5.1).** This page mapped maintenance intent to one procedure; it
does not restate those procedures.

| Requested intent | Entry | Owning procedure |
| --- | --- | --- |
| Assess status or repair approved generated drift | `methodology-management` | `references/assessment.md` (retired) |
| Set up or adopt a project | `methodology-management`, or explicit compatibility name `project-onboarding` | `references/setup.md` (retired) |
| Migrate product documents | `methodology-management`, or explicit compatibility name `project-migration` | `references/migration.md` (retired) |
| Compare or apply a methodology/model candidate | `methodology-management` | `references/upgrades.md` (retired) |
| Read-only conformance assessment | `project-conformance` may be selected implicitly | Existing conformance checker; requested repair returns to management assessment |

Onboarding and migration disable model-initiated invocation in both harnesses. Their compatibility
entries carry the user's target and authorization into management without requiring another
invocation. Conformance may assess read-only, but never starts setup, migration, adoption or
upgrade.

Begin maintenance with owning structured readiness:

```bash
python3 "$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py" --repo <repo> --status-json
```

Only `current` is ready for governed execution. The payload distinguishes the project-approved
runtime, installed source, route, overlay and declared dependencies. An approved older bundle can
remain current; a global-source or candidate difference does not replace it.

Repository hook/persona work uses `--scope project --preview --json`. Global work uses explicit
`--scope global`; combined recovery uses explicit `--scope all`. Preview and apply consume the
same plan, and unmanaged content is preserved. Installation, project adoption, model activation,
publication and deployment remain separately authorized outcomes.
