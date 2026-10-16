---
summary: How this repository applies the rules the skill's `references/repository.md` sets for every repository: where each kind of file belongs, from the contract and `install/` to the product, architecture, decision, runbook, goal and archive pages and the generated pointer files. Which pages are dated records, `docs/agents/lessons.md` among them where one exists, and which state only what is true now. What enforces the standard in `install/verify.sh`: `docs.py links`, the dangling-name check, `docs.py lint` and the always-loaded size ceiling. The product minimum is in the reference.
read-when: Adding, moving or removing a file, or deciding where something belongs
covers: [docs/**]
last-verified: 2026-10-16
---

# Repository standard

The layout this repository keeps:

```
README.md                      front page for a human: the seven sections of the skill's
                               references/repository.md
AGENTS.md                      the contract, at most 300 words; CLAUDE.md is the one line @AGENTS.md
install/                       the single authored source of everything installed
docs/README.md                 prose, then the index table docs.py index prints: one line per page
docs/architecture/             how it works and why
docs/decisions/                decisions.md, one record
docs/product/prd.md            the product: users, jobs, principles, surface, non-goals
docs/product/features/         one page per feature
docs/product/measurements.md   dated numbers
docs/runbooks/                 procedures
docs/goals/<id>/               spec.md, design.md unless touches is none, plan.md; one per goal
docs/goals/modules.json        the test-module map (D33): each module's paths, needs and test
                               command; approved with a plan, protected after; a task
                               whose writes name it may grow it, never shrink it (D38)
docs/archive/                  pointers to tags; nothing current
.claude/rules/<page-slug>.md   generated: one pointer file per page with a non-empty covers; the
                               slug is the page's path under docs/ with `/` as `--`
AGENTS.md pointer block        generated: in the nearest AGENTS.md, which must carry the markers (an
                               unmarked one is reported, never written), the pages covering that
                               directory; docs/AGENTS.md holds only this page's block, since the
                               root AGENTS.md is a table of contents under the 1,350-word ceiling
```

The rules every repository follows (the README, the layout, the agent files, the lifecycle and the
product minimum) are the skill's
[references/repository.md](../../install/skills/execution-methodology/references/repository.md);
this page is how this repository applies them.

**Generated files.** The index table, the pointer files and the block between
`<!-- docs.py pointers -->` and `<!-- /docs.py pointers -->` are written by `docs.py` from each
page's frontmatter (`summary` of at most 120 words, `read-when`, `covers`, `last-verified`), never
by hand.

**Records and pages.** `decisions.md`, `measurements.md`, `docs/goals/<id>/**` and, in a
repository that has one, `docs/agents/lessons.md` are records: dated entries that may name removed
components as rationale.
`docs/goals/modules.json` states the current map. Every other page states what is true now; history
stays in git and its tags.

**Enforcement** is in `install/verify.sh`, not a validator script: the link check `docs.py links`
(every relative link in `AGENTS.md`, `README.md` and `docs/` resolves, anchors included, and each
`AGENTS.md` has its `CLAUDE.md` twin), `docs.py lint` (every page but the index and `docs/goals/**`
carries the four frontmatter keys, the index table is the generated one, and `docs.py pointers
--check` finds no pointer file a regeneration would change) and the dangling-name check (no file
outside the records names a deleted component). `docs.py stale` lists the pages whose covered paths
were committed after their `last-verified` day as a warning that never fails the gate. The size
test caps `AGENTS.md`, `install/global.md` and the skill's `SKILL.md` at 200 lines each and 1,350
words together. Review checks the layout itself.

A product repository needs less: the product minimum in
[references/repository.md](../../install/skills/execution-methodology/references/repository.md#layout).
