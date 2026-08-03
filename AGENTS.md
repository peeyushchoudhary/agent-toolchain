# SWE Agent — repository contract

Documentation and tooling for working with coding agents across projects. No runtime, no build.
Start at [docs/README.md](docs/README.md) and open only what your task needs.

## What this repository is

A description of a working setup, not a proposal. Every claim should be true of the tooling in
`install/`, and every number should be traceable to [docs/measurements.md](docs/measurements.md).

## Before changing anything

1. `install/skills/` and `install/hooks/` are **vendored copies** of what lives in `~/.claude`.
   Change the source, then re-vendor — editing the copy makes the two disagree silently. **A
   re-vendor is not a whole-tree copy: `agent-personas/tests/` is excluded deliberately**, because
   its fixtures resolve a document as a sibling of the skill tree and that path does not exist in
   the vendored layout, so restoring it publishes a suite that fails where it sits and that no gate
   runs. The exclusion, its measurement, and the expected drift it leaves behind are in
   [docs/what-gets-installed.md](docs/what-gets-installed.md), "Re-vendoring". Read that section
   before re-vendoring, not after.
2. Prefer the installed tooling over prose that describes it. When they differ, the tooling is right
   and the prose needs fixing.
3. This is a public repository. It must contain no project names, personal paths, account
   identifiers, or anything specific to one person's work.

This repository is public on purpose, and the marker below is that decision — see
[docs/progressive-disclosure.md](docs/progressive-disclosure.md) for what it means and how the
forge check reads it.

<!-- public-exception: {"reason":"documentation and tooling repo, deliberately public so the setup is checkable by anyone; no project names or personal data belong here by invariant","date":"2026-07-30"} -->

## Invariants

- **No identifying content.** No usernames, absolute home paths, real project names, or business
  specifics. Examples are illustrative and generic.
- **Claims are evidenced.** A cost or benchmark figure needs a source in `docs/measurements.md`. A
  "this was a problem" claim needs the concrete failure it came from.
- **Mistakes stay in.** The false starts and reversals are the most useful content here; do not
  tidy them into a clean narrative.
- **Optional dependencies stay optional.** `gh`, `ripgrep`, and `graphify` must never be required
  for the core to work.

## Verification

```bash
cd install && ./install.sh --dry-run && ./verify.sh
```

Then check every internal link resolves. If the progressive-disclosure validator is installed, run
it against this repository — a repository teaching route validation should pass its own check.
