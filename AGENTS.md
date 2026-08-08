# SWE Agent — repository contract

Documentation and executable tooling for coding-agent work across projects; there is no application
runtime or build artifact. Start at [docs/README.md](docs/README.md) and open only what the task
needs.

## Boundaries and authority

This public repository must contain no project names, personal paths, account identifiers, or
private business facts.

<!-- public-exception: {"reason":"documentation and tooling repo, deliberately public so the setup is checkable by anyone; no project names or personal data belong here by invariant","date":"2026-07-30"} -->

Published behaviour comes from `install/`. Edits to vendored skills and hooks originate in their
maintained source and are re-vendored as described in
[what-gets-installed.md](docs/what-gets-installed.md). Executable tooling and tests override prose.
Claims need executable or documented evidence; measurements route to
[measurements.md](docs/measurements.md).

Keep false starts and reversals as labelled rationale, never as current authority. `gh`, `ripgrep`,
and `graphify` remain optional to the core. This documentation/tooling repository deliberately uses
its task index instead of a product repository's agent-doc taxonomy; see
[D13](docs/decisions.md#d13--this-repository-uses-a-documentation-tooling-taxonomy).

## Goal-bound execution

Before implementation or a review repair, bind the dispatch to the approved outcome or a named
invariant and state its observable delta. Classify every finding. Recurrence of the same causal
mechanism after one independently reviewed repair returns to the plan gate; renaming an attempt does
not reset it. Distinct safety findings may still block. Budgets trigger human review only and never
change a test, review, safety, or acceptance verdict. A vague request becomes a proposed outcome
capsule for approval, not immediate implementation or automatic refusal.

## Verification

Run `cd install && ./install.sh --dry-run && ./verify.sh`, then
`python3 ~/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py .`. The default route
check must report zero findings in the families it runs.
