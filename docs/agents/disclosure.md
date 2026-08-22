<!-- progressive-disclosure standard v1.2 -->
# How the route works here

**Authority: current.** Generated against standard v1.2 and edited in place — never regenerated, per
[../architecture/repository-standard.md](../architecture/repository-standard.md).

## The four layers, in this repository

1. `AGENTS.md` — the contract, at most 400 words. `CLAUDE.md` is one line: `@AGENTS.md`.
2. [README.md](README.md) — the route index: task, one guide, one command.
3. The area directories below `docs/`, one hop from [../README.md](../README.md).
4. The tooling in `install/`, which is what actually runs and outranks every document above.

## Where things live

| Directory | Holds | Authority |
| --- | --- | --- |
| `docs/agents/` | the route, the installed inventory, the persona roster | current |
| `docs/architecture/` | how the system is built: the operating model, the repository standard | current |
| `docs/product/` | intent read through shipped behaviour: measurements, the weekly record | current; measurements are dated |
| `docs/decisions/` | accepted decision records | current |
| `docs/runbooks/` | operational procedures: onboarding, adoption, Codex, GitHub | current |
| `docs/archive/` | superseded material | NOT authoritative |

## Depth is the constraint, and it is checked

`validate_disclosure.py` warns `too-deep` past two hops from an entry file. Moving these documents
into area directories spends one of those hops, so [../README.md](../README.md) links every document
DIRECTLY rather than only linking the six area indexes. Add a document by adding a row there in the
same commit; a document reachable only through its area index sits three hops out and the validator
says so.

## Running it

```bash
python3 install/skills/progressive-disclosure/scripts/validate_disclosure.py . --standard
./install/verify.sh          # runs the line above, in the repository section
```

The exit code is the verdict. `status` is `partial` on any run not also given `--vs`, and `partial`
carries exit 1 when the checks that ran found an error.
