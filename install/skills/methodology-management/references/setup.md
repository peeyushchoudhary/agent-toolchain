# Set up a project

Preserve the existing onboarding procedure while selecting only work the project actually lacks.
Inspect its real code, commands, documentation, git state and tooling. Use
`migrate_to_standard.py` in plan mode if layout migration is needed; inspect code callers before
accepting path moves and isolate existing dirty work.

Propose the concrete setup: real AGENTS/CLAUDE route, area guides and check commands; required
README links; hooks; a domain-persona or justified base-only decision; methodology adoption or
explicit deferral; project overlay and approved runtime identity. Derive claims from evidence and
ask for missing substantive choices together. Existing setup authorization remains valid; do not
ask again for its individual mechanical steps.

Before applying the approved plan, preview every generated project path:

```bash
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py" <repo>
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/install_hooks.py" <repo> --scope project --preview --json
python3 "$HOME/.claude/skills/agent-personas/scripts/sync_personas.py" --repo <repo> --scope project --preview --json
python3 "$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py" --repo <repo> --status-json
```

Apply the authorized plan using the same owners and explicit project scope. Rendering with
`sync_methodology.py --repo <repo>` is an adoption action and requires the recorded adoption
decision; setup may instead record a deliberate deferral. Use full structured status to verify
runtime dependencies, the overlay and routes in both harnesses. Preserve project-specific content
and authorizations. Remote creation, visibility, pushes, merges, global changes outside scope and
deployments need their own session authority.

Run conformance and the repository's actual local check gate. Prove a representative guard rejects
a broken fixture in an isolated checkout; report exclusions and checks that could not run. A route
render alone is not setup completion. Record outcomes in the existing repository route and
maintained docs, not a new project database.
