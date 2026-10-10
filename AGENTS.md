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

Keep false starts and reversals as labelled rationale, never as current authority. `gh` and `ripgrep`
remain optional to the core. This repository complies with the standard it ships;
see [D17](docs/decisions/decisions.md#d17--this-repository-complies-with-the-standard-it-ships).

## Methodology

- Rules: [the execution-methodology skill](install/skills/execution-methodology/SKILL.md) (v7.1).
- Goals: [docs/goals/](docs/goals/), each a `spec.md`, a `design.md` unless `touches` is `none`,
  and a `plan.md`.
- Pages: frontmatter on each; `docs.py` generates the index and pointer files, never hand-edited.
- Design and accepted risks: `docs/architecture/methodology.md`.
- Decisions: [D29](docs/decisions/decisions.md#d29--simplified-goal-execution-methodology-v7-one-look-per-artifact-a-mechanical-gate-two-touchpoints),
  [D30](docs/decisions/decisions.md#d30--methodology-v71-context-roles-and-planning-documents-s-2),
  [D31](docs/decisions/decisions.md#d31--the-skill-is-model-invocable-the-chief-is-the-root-session-never-a-subagent).

## Verification

The repository gate is `cd install && ./install.sh --dry-run && ./verify.sh`; its last line,
`verify: PASS`, is the verdict. During a goal, run it through `gate.py receipt`: a failure recorded
in the goal's baseline is not attributed to the change, and a new one is. It includes the link
check: every relative link in `AGENTS.md`, `README.md` and `docs/` must resolve.
