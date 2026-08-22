<!-- Merge checklist. A markdown template, NOT a workflow: this repository runs no hosted CI. -->

## What changed, and why

## Local proof

- [ ] `./install/verify.sh` — the REPOSITORY verdict line is PASS
- [ ] `python3 install/skills/progressive-disclosure/scripts/validate_disclosure.py . --standard`
      exits 0
- [ ] The vendored skill suites are green under the interpreter named in the verify.sh output

## Documents

- [ ] Every document this change adds or moves has a row in `docs/README.md`, so it stays two hops
      from an entry file
- [ ] No count, path or roster is restated in prose where it is already derived somewhere else
- [ ] `AGENTS.md` is still at or under 400 words
