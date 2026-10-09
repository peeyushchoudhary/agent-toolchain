---
summary: The layout this repository keeps: where each kind of file belongs, from the contract and `install/` to the product, architecture, decision, runbook, goal and archive pages and the generated pointer files. Which pages are dated records and which state only what is true now. What enforces the standard in `install/verify.sh`: the link check, the dangling-name check, `docs.py lint` and the always-loaded size ceiling. And the smaller minimum a product repository needs.
read-when: Adding, moving or removing a file, or deciding where something belongs
covers: [docs/**]
last-verified: 2026-10-09
---

# Repository standard

The layout this repository keeps:

```
README.md                      front page for a human
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
docs/archive/                  pointers to tags; nothing current
.claude/rules/<page-slug>.md   generated: one pointer file per page with a non-empty covers; the
                               slug is the page's path under docs/ with `/` as `--`
AGENTS.md pointer block        generated: in the nearest marked AGENTS.md, the pages covering that
                               directory; docs/AGENTS.md holds only this page's block, since the
                               root AGENTS.md is a table of contents under the 1,350-word ceiling
```

**Generated files.** The index table, the pointer files and the block between
`<!-- docs.py pointers -->` and `<!-- /docs.py pointers -->` are written by `docs.py` from each
page's frontmatter (`summary` of at most 120 words, `read-when`, `covers`, `last-verified`), never
by hand.

**Records and pages.** `decisions.md`, `measurements.md` and `docs/goals/**` are records: dated
entries that may name removed components as rationale. Every other page states what is true now;
history stays in git and its tags.

**Enforcement** is in `install/verify.sh`, not a validator script: the link check (every relative
link in `AGENTS.md`, `README.md` and `docs/` resolves, decision anchors included), `docs.py lint`
(every page but the index and `docs/goals/**` carries the four frontmatter keys, the index table
is the generated one, and `docs.py pointers --check` finds no pointer file a regeneration would
change) and the dangling-name check (no file outside the records names a deleted component).
`docs.py stale` lists the pages whose covered paths were committed after their `last-verified` day
as a warning that never fails the gate. The size test caps
`AGENTS.md`, `install/global.md` and the skill's `SKILL.md` at 200 lines each and 1,350 words
together. Review checks the layout itself.

A product repository needs less: `AGENTS.md`, `CLAUDE.md`, `docs/product/prd.md` with at least its
frontmatter `summary`, `docs/goals/<id>/spec.md` and `plan.md` (with `design.md` unless `touches`
is `none`), `/.runs/` in `.gitignore`, `docs.py lint` in its gate, and the guard hooks from
`git-hooks.sh`.
