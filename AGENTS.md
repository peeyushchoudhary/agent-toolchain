# SWE Agent — repository contract

Documentation and executable tooling for coding-agent work across projects; there is no application
runtime or build artifact. Start at [docs/README.md](docs/README.md) and open only what the task
needs.

## Boundaries and authority

This public repository must contain no project names, personal paths, account identifiers, or
private business facts — in commit messages as well as files: no `Claude-Session:` trailers here.
Nothing enforces the commit-message half; it is a rule, not a guard.

<!-- public-exception: {"reason":"documentation and tooling repo, deliberately public so the setup is checkable by anyone; no project names or personal data belong here by invariant","date":"2026-07-30"} -->

Published behaviour comes from `install/`. Edits to vendored skills and hooks originate in their
maintained source and are re-vendored; see
[what-gets-installed.md](docs/agents/what-gets-installed.md). Executable tooling and tests override
prose. Claims need executable or documented evidence; measurements route to
[measurements.md](docs/product/measurements.md).

Keep false starts and reversals as labelled rationale, never as current authority. `gh`, `ripgrep`,
and `graphify` remain optional to the core. This repository complies with the standard it ships;
see [D17](docs/decisions/decisions.md#d17--this-repository-complies-with-the-standard-it-ships).

## Goal-bound execution

Execution is goal-bound: bind every dispatch to the approved outcome or a named invariant, state its
observable delta, and classify every finding. Judges are independent and structurally unable to
edit; a builder never approves their own work. Execution continues through approved completion by
default. Technical corrections follow the owning gate's approved causal recovery; renaming an
attempt does not reset it. Failed checks block acceptance and integration. Numeric review spend
triggers technical diagnosis and never changes a verdict or requires founder permission by itself.

The rest of the review contract — freshness and its harness primitive, what a blocker needs, one
correction and one scoped rereview, apply-and-close, escalation and its default action, the
over-engineering ceiling — is owned by the execution methodology, routed through
[operating-model.md](docs/architecture/operating-model.md). See the
[superseding recovery decision](docs/decisions/decisions.md#d27--approved-completion-and-technical-recovery)
for the change to D14. Substantive product, UX, design and plan decisions and external actions
outside existing grants still require founder authority.

## Verification

Run `cd install && ./install.sh --dry-run && ./verify.sh`. Its repository verdict line must be
PASS; it runs `validate_disclosure.py --standard` against this repository, so the route check is
no longer a separate command.
