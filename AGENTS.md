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

Before the design and plan gates, cast the existing read-only `reviewer` in fresh context with named
artifact paths and no author rationale. `PASS` is valid. A blocker needs a frozen criterion or
invariant, a reachable trigger, an observable consequence, and artifact evidence; preferences and
invented requirements do not block. Permit one correction and one scoped rereview, then
apply-and-close: the orchestrator applies the final verdict's named smallest correction and closes.
Only safety-class findings and scope changes return to a human gate, and every escalation brief
names a default action. A finding demanding more than the spec requires is over-engineering and
non-blocking.
For Codex, fresh review means `fork_turns: "none"`; another harness uses its equivalent fresh-thread
primitive, never prompt wording alone. A scoped rereview receives paths to the persisted original
finding, correction or diff, corrected artifact, and governing frozen artifacts. Post-code review
defaults to Implementation unless Design or Plan is explicitly named.

## Verification

Run `cd install && ./install.sh --dry-run && ./verify.sh`, then
`python3 ~/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py .`. The default route
check must report zero findings in the families it runs.
