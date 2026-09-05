# Adopt the methodology in an existing project

This document is retained as a compatibility route for existing links. The maintained procedure is
the [management setup procedure](../../install/skills/methodology-management/references/setup.md);
the concise public interface and authority boundaries are in
[onboarding-a-project.md](onboarding-a-project.md).

Invoke `methodology-management` for setup or adoption. It assesses first, presents the concrete
project-scoped preview, and carries existing authorization through bounded mechanical steps.
`project-onboarding` remains an explicitly invoked compatibility name in both harnesses. Neither
entry creates a remote, changes visibility, pushes, installs globally or adopts a methodology
without the corresponding session authority.

Use `--scope project --preview --json` for hook and persona plans. Verify the owning
`sync_methodology.py --repo <repo> --status-json` payload, conformance report and project gate.
The approved runtime inventory and project overlay determine readiness; an available newer source
does not become the execution fallback.
