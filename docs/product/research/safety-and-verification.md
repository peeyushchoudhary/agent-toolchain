# Safety and verification — 2026-09-30

**Status: dated findings and proposal limits. This is not release or pilot acceptance.**

Fewer interruptions should come from carrying valid authority and avoiding unnecessary permission
crossings. They should not depend on disabling the sandbox, accepting a failed gate or granting
blanket command/network permissions.

## Threat assumptions and capability limits

### Executable configuration

[gate_config.sh](../../../install/skills/gate-sandbox/scripts/gate_config.sh), lines 131–150,
sources host and project `.env` files before the nested sandbox is created. This is executable
trusted configuration, not a safe data parser. A hostile config can run commands at the launcher's
outer permission level; after-execution value validation does not prevent that. Actual impact also
depends on the enclosing harness permissions. No hostile-config exploit was executed here.

Keep those files controller-owned outside reviewed repositories and bind their exact bytes for an
approved run. Never accept a repository-provided replacement as harmless configuration. If
untrusted configuration must be admitted, a non-executable schema and no-follow/path checks require
a separate interface change. Replacing the current trusted configuration format is conditional,
not a prerequisite for every ordinary task.

### Docker daemon authority

[gate_lib.sh](../../../install/skills/gate-sandbox/scripts/gate_lib.sh), lines 320–356, permits one
daemon socket, and lines 507–527 execute the declared gate. A permitted daemon is outside the
nested profile. A malicious gate may ask it to mount host files or use container egress; the selected
source-integrity check cannot detect unrelated host reads/writes. The skill already documents
container egress, but its confinement claim needs an explicit daemon/bind-mount limitation.

This is a boundary limit under hostile-gate assumptions, not evidence that normal local gates have
exfiltrated data. [Anthropic sandbox-runtime](https://github.com/anthropics/sandbox-runtime) also
warns about Docker socket authority. Treat current Docker-backed gates as trusted-code execution.
For untrusted gates, first prove an isolated daemon/VM with constrained mounts, credentials and
egress; do not claim a host profile alone provides that isolation.

### Judges and non-shell tools

[Persona selection](../../../install/skills/agent-personas/SKILL.md), lines 50–64, explicitly
admits Codex dispatch remains instruction-bound. The renderer emits a filesystem sandbox but no
native dispatch disablement. Current [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
documents `agents.enabled` and role config layers. Test a judge role with agents disabled in the
actual client before changing the renderer or claiming enforcement.

Read-only filesystem access also does not constrain web, apps, MCP traffic or plugin lifecycle
hooks. Restrict the production review surface to named artifacts and needed tools; retain a distinct
research profile for intentional web research. Test child-tool exposure, denied reads/writes and
network/tool routes explicitly. A string in generated TOML is not proof the active client applies it.
No indirect-writer or data-exfiltration exploit was executed in this assessment.

## Approval boundary

| Action | Proposal |
| --- | --- |
| Covered workspace edits, declared tests, scratch artifacts, bounded recovery | Continue inside existing authority and permissions. |
| Local commits | Continue only when the observed Gate 2 decision grants them. |
| Known required registry/service/command | May be explicitly authorized once with narrow scope; preserve host enforcement. |
| Materially safer alternative after a denied action | Continue only when it respects the denial and original authority. |
| New secrets use, destination, global configuration, privileged capability or destructive effect | Request authority when not already explicitly covered; do not broaden a prior grant by inference. |
| Push, PR, merge, provider activation, production writes and deployment | Use their distinct explicit authorization; a milestone pass does not grant them. |

Avoid broad `python`, `bash`, `curl` or arbitrary-shell prefix grants. [Official auto-review guidance](https://learn.chatgpt.com/docs/sandboxing/auto-review)
recommends narrow roots/prefixes and a materially safer alternative after denial. An automatic
reviewer is not a deterministic safety guarantee.

## Observed local checks

Entry route check exited zero with an existing over-budget warning; the cross-project standard was
not requested by that entry command. Runtime status was `unadopted`, `ready=false`, no approved
inventory, with `methodology_unadopted`. These observations grant no adoption.

Installed CLI: Codex 0.157.1; Claude Code 2.1.281. Codex automatic approval review and Claude auto
mode are selected. Configuration absence is not an inferred effective permission policy; the
active session's enforced permissions remain controlling.

The owning machine toolchain checker exited 2: 19 tracking checks could not run, three warnings
and two informational findings. The direct failure was permission denied creating a machine-home
Git index lock. Its text says another process held the lock, which is not established by that
error. Disabling optional Git locks did not resolve it. No approval escalation or global repair was
performed. Plugin hooks/shadowed agent names need classification; their presence is not proof of
malicious behavior.

Independent baseline command: `cd install && ./install.sh --dry-run && ./verify.sh`, against
`f6eca7c` before the research documentation changes. It exited **1**. The repository line reported
**PASS with six checks not run**; the machine line reported **FAIL**. Of four discovered suites,
three passed and one failed. The verifier reported 1,700 tests discovered, 1,698–1,700 executed,
0–2 skipped and two skip events. Its exact unit says assertions; this is not a count of individual
assert statements or comprehensive correctness proof.

The failing `gate-sandbox` suite ran 38 tests with two failures. Execution-methodology reported
1,150–1,152 passing executions, progressive-disclosure 446 and project-conformance 64. Six published
skills had no vendored suite. The verifier attributes the failing suite to the machine because the
suite reads home state. Targeted traceback inspection ran `tests.test_selftest_suite`: three tests,
one passed and two failed. Its shell checks produced empty results because nested
`sandbox-exec` failed with `sandbox_apply: Operation not permitted`. The separate
`tests.test_evidence_supervisor` run passed all 29 tests. This infrastructure denial is distinct
from the installed-layer Git lock errors. A repository PASS line does not mean the complete command
passed, and sandbox assertions not executed here remain unproved.

An independent isolated probe invoked the actual seal CLI in a disposable fixture: after its gate
mutated tracked source, record returned zero, created one receipt, and verify returned zero. A second
probe executed the actual terminal branch of `gate.sh` with child exit zero and failed integrity:
it printed nonpass and exited zero. The probe command exited zero because both defects reproduced;
no full sandbox gate or exploit was executed by that probe. Source implementation stayed unchanged.

No baseline result seals this documentation proposal or the safety claims above.

Independent Design review initially blocked on approval provenance and a stale baseline-cause
account. After one correction, a fresh scoped rereview returned **PASS**, with current-client
approval capability and complete local validation explicitly unproved. This verdict concerns the
research proposal; it does not approve implementation, prove client compatibility or change the
failed baseline result.

## Required proof for implementation

The proposed changes need focused failure-injection tests, authority admission/expiry tests,
freshness/unknown-evidence cases, compaction and interruption recovery, independent review and the
existing area gate. Final milestone readiness requires the full declared local gate against the
accepted referent, followed by independent acceptance. Keep machine drift, source correctness and
unknown checks separately visible. No code fix, installation, adoption or model activation is
included in this research deliverable.
