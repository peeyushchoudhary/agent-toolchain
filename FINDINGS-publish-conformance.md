# Publish project-conformance + ninth check — findings

TOP 3 SO FAR: (in progress)

## Part 1 — four coordinated edits
in progress

## Part 2 — ninth check `product definition`
in progress

## Things that moved and were re-verified
in progress

## Machine copy: what could not be published as-is
in progress
## F1 — the prompt's premise is wrong: project-conformance DOES ship tests
`~/.claude/skills/project-conformance/tests/test_conformance.py` exists, 989 lines.
The task brief said "NO tests directory". It has one. So the question is not "what does
verify.sh do with a skill that ships none" but "does this suite pass from the VENDORED
position". `docs/agents/what-gets-installed.md` records that `agent-personas`' suite is
deliberately NOT vendored because it resolves a sibling `docs/` that does not exist under
`install/`. Must test the same failure mode here before vendoring the tests dir.

## F2 — the vendored-drift baseline is prose, not a data file
It is `docs/agents/what-gets-installed.md`, section "Re-vendoring: what is left behind on
purpose", the paragraph beginning "`check_toolchain.py --vendored <repo>` therefore reports
**5 criticals at `a008768`, all expected**". Two of the five are exactly this gap:
`install/skills/.gitignore` and `install/skills/README.md`, "differing by one line each —
both `project-conformance`". Closing the gap removes those two -> baseline becomes 3.

## F3 — a FIFTH place the docs say a new skill must be listed: MIRRORED_SKILLS
`docs/agents/what-gets-installed.md`: "A new skill goes in **one** list to be watched and
mirrored: `MIRRORED_SKILLS` in `check_toolchain.py`". That tuple
(check_toolchain.py:228-229) names 6 skills. But the copy in this repo is a VENDORED mirror
of `~/.claude`. Editing it here without editing the machine copy MANUFACTURES A NEW
vendored-drift critical. Decision: do not edit it; document it instead.

## F4 — machine copy is publishable as-is
Grepped SKILL.md + check_conformance.py + test_conformance.py for an absolute-home-path pattern, the operator
name, the 15 project directory names under Projects/, emails, and http URLs. Only hits:
`~/.claude/...` and `~/.codex/...` (generic tool paths, already all over this repo) and
`t@example.invalid` in a test fixture. Nothing to redact.

## F5 — the repo's own pre-commit identifier guard is live in this worktree
First attempt to commit this findings file was BLOCKED because the file quoted an absolute
home-path pattern literally. Guard works; write findings without literal home paths.

## F6 — the vendored suite RUNS and PASSES from the vendored position (56 tests OK)
`cd install/skills/project-conformance && python3 -m unittest discover -s tests` -> `Ran 56
tests ... OK`. That is exactly what `verify.sh`'s `run_one_suite` does (it runs `<skill>/tests`
from inside `<skill>`). So unlike `agent-personas`, this suite does NOT need a sibling `docs/`
and there is no reason to leave it behind. VENDOR THE TESTS DIRECTORY.
Caveat, measured: with `HOME=$(mktemp -d)` the same suite is `FAILED (failures=15, errors=7,
skipped=3)`. The suite drives the REAL installed checkers (`sync_personas.py`,
`validate_disclosure.py`, `install_hooks.py`, `check_toolchain.py`) out of `$HOME/.claude`.
verify.sh already declares this exposure in its own `HOME: ... INHERITED, not declared` context
line. Needs comparison against the existing suites before claiming it is new.

