# SWE Agent — repository contract

Documentation and executable tooling for coding-agent work across projects; there is no application
runtime or build artifact. Start at [docs/README.md](docs/README.md) and open only what the task
needs.

## Boundaries and authority

This public repository must contain no project names, personal paths, account identifiers, or
private business facts — in commit messages as well as files: no `Claude-Session:` trailers here.
Nothing enforces the commit-message half; it is a rule, not a guard.

Published behaviour comes from `install/`, which is the single authored source for the skills and
hooks; edit it there, never in an installed copy. Executable tooling and tests override prose.
Claims need executable or documented evidence; measurements route to
[measurements.md](docs/product/measurements.md).

Keep false starts and reversals as labelled rationale, never as current authority. `gh`, `ripgrep`,
and `graphify` remain optional to the core. This repository complies with the standard it ships;
see [D17](docs/decisions/decisions.md#d17--this-repository-complies-with-the-standard-it-ships).

## Methodology

This repository follows methodology v6, lean goal execution: a goal is a spec, a design and a plan,
and the founder's routine touchpoints are exactly goal approval and merge per milestone. Scripts
compute done, scope and test integrity; review runs where it has measured yield, and the reviewer
comes from the other vendor at design, plan and acceptance. A builder never approves their own
work, and judges cannot edit. Decisions the plan does not settle are defaulted, escalated or queued.
The rules are in the
[execution methodology](install/skills/execution-methodology/methodology.md) and the
[design](docs/architecture/lean-execution.md). Substantive product decisions and external actions
outside existing grants still need the founder.

## Verification

The repository gate is `cd install && ./install.sh --dry-run && ./verify.sh`; its last line,
`verify: PASS`, is the verdict. During a goal, run it through `gate.py receipt`: a failure recorded
in the goal's baseline is not attributed to the change, and a new one is. It includes the link
check: every relative link in `AGENTS.md`, `README.md` and `docs/` must resolve.
