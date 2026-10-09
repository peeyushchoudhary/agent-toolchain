<!-- Merge checklist. A markdown template, NOT a workflow: this repository runs no hosted CI. -->

## What changed, and why

## Local proof

- [ ] `cd install && ./install.sh --dry-run && ./verify.sh` — the last line is `verify: PASS`
- [ ] For a goal milestone: `goal.py done` prints `DONE`, and the body below is `goal.py packet`

## Documents

- [ ] Every document this change adds or moves has a row in `docs/README.md`
- [ ] No count, path or roster is restated in prose where it is already derived somewhere else
- [ ] The always-loaded files (`install/global.md`, `AGENTS.md`, the skill's `SKILL.md`) stay under
      the size test's ceiling
