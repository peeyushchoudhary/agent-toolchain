# Per-project initialisation

The maintained setup procedure is
[methodology-management/references/setup.md](../../install/skills/methodology-management/references/setup.md).
The explicitly invoked `project-onboarding` skill is a compatibility route to that procedure in
both harnesses; it carries the user's target and existing authority forward without asking for a
second invocation. A session check may report missing setup, but never starts adoption.

This page records the public interface and authority boundary. It does not duplicate the setup
procedure.

## Inspect and preview

Start from the repository's own route and a clean, isolated view of existing work. Obtain the
methodology owner's structured status and preview each repository-only generator:

```bash
python3 "$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py" --repo . --status-json
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py" .
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/install_hooks.py" . --scope project --preview --json
python3 "$HOME/.claude/skills/agent-personas/scripts/sync_personas.py" --repo . --scope project --preview --json
```

Read the JSON operations and findings, not only exit codes. Project scope touches only repository
hooks/configuration and both project agent trees. It does not synchronize global skills, settings
or agents. Preview writes nothing. Preserve unmanaged files and inspect code callers before
accepting a documentation move.

The setup owner coordinates the route, real local commands, hooks, the project-persona or justified
base-only decision, and methodology adoption or deliberate deferral. It also distinguishes the
project-approved runtime, installed source and any available candidate. A newer source or digest is
not permission to replace an approved runtime.

## Apply only the approved scope

After the concrete setup is authorized, use the same owners with explicit project scope:

```bash
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/install_hooks.py" . --scope project
python3 "$HOME/.claude/skills/agent-personas/scripts/sync_personas.py" --repo . --scope project
```

`sync_methodology.py --repo .` is a separate adoption action. Run it only when the project has an
approved adoption decision; otherwise record a real deferral reason and date. Remote creation,
visibility changes, pushes, merges, global synchronization and deployment require their own
authority. Never invent a persona reason, review status, ownership or methodology provenance.

## Verify

```bash
python3 "$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py" --repo . --status-json
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" .
make check
```

Only runtime state `current` is ready for governed execution. Conformance exit 2 means a check did
not run. Setup completion also requires the repository's real local gate and a representative
isolated guard failure; it does not imply pilot, release or deployment readiness.
