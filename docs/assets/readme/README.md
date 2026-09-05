# README visual assets

Current visual summaries for the [front page](../../../README.md). The linked methodology and
executable tools remain behavioral authority.

## Architecture text description

Project knowledge supplies the repository route, `AGENTS.md`, documentation and lessons. The
route feeds two workflows: **Execution** handles approved work and evidence; **Management**
coordinates assessment, maintenance and explicit adoption. Focused helper tools support both.
The selected harness is **Claude Code or Codex**, which produces code, documentation and evidence.
There is no cross-harness dispatch. Lessons return from the results to repository knowledge.
The footer reads: “Local execution. Explicit adoption. Durable history.”

## Execution flow text description

The numbered overview is: approved outcome → repository route → scoped task → build → independent
review → local checks → milestone PR and merge. Review findings return to the builder for
correction; lessons return from the merged work to the repository route. Design, plan and merge
retain human approval. Checks progress through relevant tests and area gates to local E2E for
milestone readiness; the picture does not require full E2E for every individual task. Deployment
is a separate, explicitly authorized step. This is an overview; the
[execution procedure](../../../install/skills/execution-methodology/methodology.md) owns exact order.

## Skill surface chart

The editable SVG uses proportional widths of 20%, 50% and 30% for two primary workflows, five
focused helpers and three compatibility/read-only routes. These groups total the ten skills in
the [published inventory](../../README.md#what-is-published-and-what-is-not).

## Regeneration and review

`architecture.png` and `execution-flow.png` were generated with the built-in ImageGen tool. The
[exact prompts](prompts.json) preserve their labels, arrows and intended style. `skill-surface.svg`
is an authored text graphic. All assets are local to this repository and work in GitHub Markdown.

When behavior changes, compare every label and arrow with this description and the owning docs,
regenerate affected imagery, inspect the pixels for accuracy and private identifiers, and update
the architecture image SHA-256 declaration in the root README. A hash proves file identity, not
semantic correctness or privacy; those require visual review.
