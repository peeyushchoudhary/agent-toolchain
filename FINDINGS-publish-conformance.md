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

## F7 — measured comparison: this suite is HOME-coupled, the other two are not
Same clean `HOME=$(mktemp -d)`, run from the vendored position:
| suite | inherited HOME | empty HOME |
|---|---|---|
| progressive-disclosure | (green) | Ran 395 ... FAILED (failures=1, skipped=9) |
| execution-methodology  | (green) | Ran 1070 ... OK (skipped=12) |
| project-conformance    | Ran 56 ... OK | Ran 56 ... FAILED (failures=15, errors=7, skipped=3) |
Cause: `check_conformance.py` ORCHESTRATES — it reimplements nothing and shells out to the real
installed `sync_personas.py`, `validate_disclosure.py`, `install_hooks.py`,
`check_toolchain.py` under `$HOME/.claude`. Its suite therefore drives real installed tools.
DECISION: vendor the tests anyway (they are green in the vendored position, which is what
`verify.sh` actually runs, and they are the only disaster recovery for 989 lines of test), and
RECORD the empty-HOME numbers in what-gets-installed.md rather than papering them.
Leaving them out would instead ADD a vendored-drift critical (baseline 4, not 3).

## F8 — the four edits are committed (5eb0ea4)
1. `install/skills/project-conformance/` — SKILL.md (166), scripts/check_conformance.py (1599),
   tests/test_conformance.py (989). Copied with rsync, `__pycache__`/`*.pyc` excluded. Not rewritten.
2. `install/skills/.gitignore` — `!/project-conformance` added; the comment's "six skills" -> "seven".
3. `install/skills/README.md` — one row in "What is here".
4. `docs/agents/what-gets-installed.md` — skills table row, scripts table row, "six published
   ones" -> "seven", the Codex `skills/` row, AND the vendored-drift baseline paragraph (5 -> 3).
PLUS two the brief did not list but the gates require:
5. `docs/README.md` — the gap paragraph rewritten (the gap is closed) + "Six skills" -> "Seven".
6. `README.md` (front page) — a Components row. REQUIRED: verify.sh `check_prose_agrees` fails
   any declared skill not named on the front page.

## F9 — pre-commit warned, did not block
`docs/agents/what-gets-installed.md: 1579 words > 1200 budget at depth 1` — WARN from the
disclosure validator. Not blocking, but it is a real prose-budget regression caused by the
baseline rewrite. Trim before finishing.

## F10 — install.sh re-verified: `7 of 7 declared skill(s) installed` / `7 of 7 mirrored`
`cd install && ./install.sh --dry-run`. It derives the roster from the allowlist, so the one
line in `.gitignore` moved both numbers with no edit to install.sh.
NOTE the mirror line: install.sh mirrors 7 to `~/.codex/skills`, but `check_toolchain.py`'s
`MIRRORED_SKILLS` still watches 6. Those two disagree now. Documented in what-gets-installed.md
rather than silently fixed, because check_toolchain.py here is a vendored mirror (see F3).

## F11 — spec_check.py measured on the four onboarded repositories (RED on all four)
Anonymised (public repo). `docs/product/specs/` exists in exactly four of the 17 directories
under the projects dir; those are the four.
| repo | spec_check exit | findings | no_front_matter | unbound (no rule binds) | docs/product |
|---|---|---|---|---|---|
| A | 0 | 0 | 0 | **233** | yes |
| B | 1 | 21 | 1 | 0 | yes |
| C | 1 | 22 | **22** | 1 | yes |
| D | 1 | 3 | 3 | 1 | yes |
Repo A is the case that proves the check is needed: spec_check EXITS 0 there, and 233 documents
under `docs/product/specs/` are named in a shape no schema rule and no persona binding reads.
An exit code alone calls that repository clean.

## F12 — `unbound_specs` is NOT in spec_check's JSON payload
`binding_payload()` carries `no_front_matter` but not `unbound_specs`. The unbound count is
only PRINTED, in `Binding.note()` / `unbound_line()`, on a non-`--json` run. And `binding` is
absent from the JSON entirely when the repo has no `docs/agents/personas/` pool.
Adding the key to spec_check.py is the obvious fix and is REFUSED for the F3 reason: that file
is a vendored mirror of the installed one, so editing it here manufactures vendored drift.
The ninth check therefore invokes spec_check TWICE — `--json` for structure, plain for the
note line — and says so in its docstring.

## F13 — THE NINTH CHECK IS RED ON ALL FOUR. Real numbers.
`check_conformance.py <repo> --only "product definition"` — exit 1, DOES NOT CONFORM, on all four.
| repo | docs/product | docs under it | bound by a schema rule | no front matter | unbound in specs/ | verdict |
|---|---|---|---|---|---|---|
| A | yes | 236 | **0** | n/a | **233** | DOES NOT CONFORM (exit 1) |
| B | yes | 8 | 1 | 1 of 1 | 0 | DOES NOT CONFORM (exit 1) |
| C | yes | 24 | 22 | **22 of 22** | 1 | DOES NOT CONFORM (exit 1) |
| D | yes | 5 | 3 | 3 of 3 | 1 | DOES NOT CONFORM (exit 1) |
Repo A is the strongest case: `spec_check.py` alone EXITS 0 there. 236 documents sit under
docs/product, not one is bound by a schema rule, and 233 of them are in specs/ under a name
no rule reads. Eight checks and spec_check's own exit code all call that repository clean.
Every run prints `REPAIR PLAN ... (nothing is mechanically repairable here)`. The check owns
no `Repair` object, so `--fix` cannot touch a product document. That is deliberate and the
docstring says why: front matter carries `reviewed_by:`, and generating it forges a review.

## F14 — break-test written AND PROVED TO BREAK
`install/skills/project-conformance/scripts/product_definition_selftest.py`, stdlib only,
exit 0/1, hermetic (builds a throwaway `PROJECT_CONFORMANCE_HOME` holding only
execution-methodology/scripts; never reads or writes the real home, never writes in the repo).
17 assertions, 4 cases, each PAIRED with a green control:
 1 missing `docs/product/` is a finding, not a clean run (control: same fixture with it -> exit 0)
 2 specs no rule binds are counted THOUGH spec_check.py exits 0 (control asserts spec_check
   really does exit 0 on the fixture, so the case cannot silently stop reproducing)
 3 `--fix` on a red repo changes no byte under docs/ and prints an empty repair plan
 4 spec_check.py absent -> exit 2 COULD NOT BE CHECKED, never CONFORMS
Break proof, both mutations reverted afterwards:
 MUTATION A `elif unbound:` -> `elif False:`  => 5 assertions FAIL, rc=1
 MUTATION B missing-layer verdict DOES_NOT_CONFORM -> CONFORMS => 1 assertion FAILS, rc=1
 RESTORED => rc=0.

