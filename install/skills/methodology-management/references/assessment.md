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

## Observe execution in the existing task distillation

This source-home route already names `docs/LEDGER.md` as its durable record. That file requires one
distillation per task and its real entries use the task heading, `Commit` and `Status`, then
`Interfaces produced`, `Deferrals`, `Verification actually run`, and `Surprises`. Weekly or ad hoc
assessment updates that existing `docs/LEDGER.md` task distillation; it does not add an assessment
row, assessment id, parallel ledger, report, schema, or status record.

Join the existing session, milestone, task, Git, trace, seal, acceptance, and validation receipt
identifiers by citing their source artifacts in those existing sections. Keep `Commit` and `Status`
as the task's Git and outcome summary. Put observed accepted-to-integrated delay, first-pass
acceptance, validation receipts, and checks that did or did not run under `Verification actually
run`. Keep produced interfaces under `Interfaces produced` and owned unfinished work under
`Deferrals`. Put defects, escaped regressions, waits, and avoidable reruns or stops under
`Surprises`, with links back to the existing identifiers that support them.

Unknown stays unknown: absence is not zero and must not be inferred from a nearby timestamp or
receipt. The existing TC-01 distillation is the fixture for that treatment: its `Verification
actually run` section records missing gate output as not recorded and identifies the repository's
existence as an inference rather than an observation. Usage and cash remain separate units; record
each only when its existing source supplies it, and do not convert or combine them without a sourced
conversion.

This is a reading of joined source artifacts in an existing record. A qualitative assessment may
explain the observations, but it cannot turn missing data into an outcome or approve a process
change.
