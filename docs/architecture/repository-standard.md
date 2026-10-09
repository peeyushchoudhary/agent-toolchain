# Repository standard

The layout this repository keeps:

```
README.md                  front page for a human
AGENTS.md                  the contract, at most 300 words; CLAUDE.md is the one line @AGENTS.md
install/                   the single authored source of everything installed
docs/README.md             the index: every page, one line each
docs/architecture/         how it works and why
docs/decisions/            decisions.md, one record
docs/product/              measurements
docs/runbooks/             procedures
docs/goals/<id>/plan.md    one per goal
docs/archive/              pointers to tags; nothing current
```

**Records and pages.** `decisions.md`, `measurements.md` and `docs/goals/**` are records: dated
entries that may name removed components as rationale. Every other page states what is true now;
history stays in git and its tags.

**Enforcement** is in `install/verify.sh`, not a validator script: the link check (every relative
link in `AGENTS.md`, `README.md` and `docs/` resolves, decision anchors included) and the
dangling-name check (no file outside the records names a deleted component). The size test caps
`AGENTS.md`, `install/global.md` and the skill's `SKILL.md` at 200 lines each and 1,350 words
together. Review checks the layout itself.

A product repository needs less: `AGENTS.md`, `CLAUDE.md`, `docs/goals/<id>/plan.md`, `/.runs/` in
`.gitignore`, and the guard hooks from `git-hooks.sh`.
