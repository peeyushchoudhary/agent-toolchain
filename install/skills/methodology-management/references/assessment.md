# Assess and repair

Read the project route, git state and current session authority. Obtain structured runtime status
from the methodology owner, then run the existing conformance aggregator for the requested scope:

```bash
python3 "$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py" --repo <repo> --status-json
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" <repo> --json
```

Conformance delegates personas, routing, hooks, identifier guard, methodology, GitHub, plugins,
preflight and product definition to their existing checkers. Inspect every finding and every check
that did not run.

Distinguish approved-target generated drift from source changes, unmanaged content, missing
dependencies and unavailable tools. Show project versus machine-global impact. A repair may restore
only the exact approved target and only within existing authorization; unknown provenance,
deletions and wider effects are substantive decisions. Do not re-render from an available candidate
just because it is newer.

For a repository-only repair, preview the owning operations explicitly:

```bash
python3 "$HOME/.claude/skills/agent-personas/scripts/sync_personas.py" --repo <repo> --scope project --preview --json
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/install_hooks.py" <repo> --scope project --preview --json
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" <repo>
```

Apply only the operations already authorized and use `--scope project` for the persona and hook
owners. `check_conformance.py --fix` remains the user's bounded mechanical repair request; it may
repair only what the approved status identifies as repairable and must reverify. Confirm the
preview equals the actual write set, preserve dirty and unmanaged files, run affected checks, and
show remaining findings. A second unchanged run must make no unnecessary writes. Read-only
assessment requires no additional approval; it does not authorize applying a repair.
