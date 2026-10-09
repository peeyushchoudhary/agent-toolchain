# README visual assets

Current visual summaries for the [front page](../../../README.md). The linked methodology and
executable tools remain behavioral authority.

## Architecture

The front page draws the architecture as a Mermaid diagram, so a rename shows up in a diff and the
validator can compare the boxes with the prose beside them. Its text equivalent sits under the
diagram on the front page. In words: a goal trio (spec, design, plan) receives one approval; the
driver and Stop hook start and sustain the chief session; the chief dispatches builders and runs the
deterministic gate; a cross-vendor review judges design, plan and acceptance; each milestone ends in
one merge. A decision the plan does not settle goes to escalation. The picture does not show
deployment, which is a separate, explicitly authorized step. The
[execution methodology](../../../install/skills/execution-methodology/methodology.md) owns exact
order.

## Skill surface chart

`skill-surface.svg` is an authored text graphic. It shows one segment for each of the four skills in
the [published inventory](../../README.md#what-is-published-and-what-is-not):
`execution-methodology`, drawn twice as wide as the others because it carries the lifecycle, then
`agent-personas`, `progressive-disclosure` and `graph-navigation`.

## Regeneration and review

`skill-surface.svg` is edited by hand; the Mermaid diagram is edited in the front page. Both work in
GitHub Markdown with no external assets. [prompts.json](prompts.json) holds prompts for optional
raster versions of the architecture and execution flow; none is generated, because a raster diagram
cannot be diffed and a private name inside one is invisible to the identifier guard. If one is
generated later, declare it with the SHA-256 contract in the
[standard](../../../install/skills/progressive-disclosure/references/standard.md), inspect the pixels
for accuracy and private identifiers, and keep the text description current.
