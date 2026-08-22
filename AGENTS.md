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
edit; a builder never approves their own work. Same-cause recurrence after one independently
reviewed repair returns to its gate — renaming an attempt does not reset it — while distinct safety
findings may still block. Budgets trigger human review only; they never change a test, review,
safety, or acceptance verdict.

The rest of the review contract — freshness and its harness primitive, what a blocker needs, one
correction and one scoped rereview, apply-and-close, escalation and its default action, the
over-engineering ceiling — is stated in [operating-model.md](docs/architecture/operating-model.md),
[D14](docs/decisions/decisions.md#d14--bounded-repairs-and-review) and the execution methodology. It
was a fourth copy here. `execution-methodology/SKILL.md` says why that is not a saving: "it was
restated here once already, and one copy was corrected while this one kept the falsified rule."

## Verification

Run `cd install && ./install.sh --dry-run && ./verify.sh`. Its repository verdict line must be
PASS; it runs `validate_disclosure.py --standard` against this repository, so the route check is
no longer a separate command.
