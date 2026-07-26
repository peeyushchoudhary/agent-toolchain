# SWE Agent — repository contract

Documentation and tooling for working with coding agents across projects. No runtime, no build.
Start at [docs/README.md](docs/README.md) and open only what your task needs.

## What this repository is

A description of a working setup, not a proposal. Every claim should be true of the tooling in
`install/`, and every number should be traceable to [docs/measurements.md](docs/measurements.md).

## Before changing anything

1. `install/skills/` and `install/hooks/` are **vendored copies** of what lives in `~/.claude`.
   Change the source, then re-vendor — editing the copy makes the two disagree silently.
2. Prefer the installed tooling over prose that describes it. When they differ, the tooling is right
   and the prose needs fixing.
3. This is a public repository. It must contain no project names, personal paths, account
   identifiers, or anything specific to one person's work.

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
