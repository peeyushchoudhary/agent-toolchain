# README restructure — working notes

TOP 3 SO FAR:
1. A routed historical record contaminates the disclosure graph — moving the changelog into
   docs/ with its links intact re-routed README.md back in at depth 3 and put the FRONT PAGE
   under a 1200-word guide budget. Links into `install/` must become code spans.
2. No existing routed doc could receive the 2,520-word record: three sit at 1,199-1,200 of
   1,200. `RECORD_NAME` had to learn the accreting-improvement class, with a test pinning both
   halves (a long record does not warn, a long non-record still does).
3. `test_readme_diagram` hardcodes the literal `"## Architecture\n"`. Renaming that heading —
   which `README_SECTIONS` allows — turns the suite red. Kept the heading, moved the section.

STATUS: COMPLETE. README 4910 -> 2895 words. All gates green.







---

## Baseline (measured)

- README.md: 4910 words total.
- Section word counts (body only):
  - preamble 104
  - `## Quickstart` 27
  - `## Current state` 739  (one wall of prose, 2 paragraphs)
  - `## The problem` 111
  - `## Product requirements` 112
  - `## Components` 272
  - `## Architecture` 465
  - `## Documentation` 136
  - `## Working in this repository` 113
  - `## Weekly improvements` 2520  (9 entries, 51% of the page)
  - `## What this is not` 202
  - `## README design choices` 70
  - `## Licence` 3
- `validate_disclosure.py .` -> rc 0, 0 findings. `--readme` -> rc 0, 0 findings.

## Constraint verification (read the code, not the claim)

1. Working notes must NOT live in `docs/`: `check_orphans` warns `orphan-doc` for any
   unlinked .md in a routed dir. Notes moved to `.wip/`.
2. Word budget: `--guide-budget` default 1200, applied per routed doc at depth>=1.
   EXEMPT class is `is_record_file()` -> `RECORD_NAME` regex
   `^(measurements|benchmarks|decisions|adr|rulings)(?:[-_][a-z0-9]+)?\.md$`.
   A record file gets NO word budget, only an informational entry-count note above
   `LESSONS_ENTRY_NOTE_AT = 24` entries.
   => A new `docs/weekly-improvements.md` at ~2500 words WOULD warn `over-budget`
      unless it is recognised as a record. This is the decision point for step 3.
3. README contract sections are matched by loose regex (`README_SECTIONS`), so headings
   may be renamed within the allowed alternatives. Required questions: overview,
   current-state, requirements, architecture, components, run, contributing.
4. `readme-diagram-drift`: every quoted node label in the mermaid fence must appear
   verbatim (casefold) in the REST of the architecture section body.
   `section_body` = lines under the first heading matching the architecture pattern,
   up to the next heading of the SAME OR SHALLOWER level.
   => If the diagram leads the page under a different heading, that heading must still
      match the architecture regex, and the stage table must stay in the same section.

## Baseline gates (all green before any edit)

| Gate | Result |
|---|---|
| `validate_disclosure.py .` | rc 0, 0 findings |
| `validate_disclosure.py . --readme` | rc 0, 0 findings |
| execution-methodology suite | Ran 1031, OK (skipped=2) |
| progressive-disclosure suite | Ran 387, OK |
| `install.sh --dry-run` | rc 0 |
| `verify.sh` | rc 0, PASS |

Note: the suites are NOT discoverable from the repo root
(`Start directory is not importable`). Run them from the skill directory:
`cd install/skills/<skill> && python3 -m unittest discover -s tests`.

5. `verify.sh check_prose_agrees` reads `install/skills/.gitignore` allowlist ->
   six skills: progressive-disclosure, agent-personas, agent-persona-factory,
   execution-methodology, graph-navigation, project-onboarding. Each must appear
   verbatim somewhere in the ROOT `README.md`. It also checks the spelled persona
   count word ("fourteen") against the file count in
   `install/skills/agent-personas/personas/`.
   => Any rewrite must keep all six literal skill names and the word "fourteen"
      next to "persona" on the front page.

## Finding: the destination budget forbids the obvious move

Routed guide word counts today (budget 1200 at depth >= 1):

| Doc | Words |
|---|---|
| docs/onboarding-a-project.md | 1200 |
| docs/progressive-disclosure.md | 1200 |
| docs/what-gets-installed.md | 1199 |
| docs/decisions.md | 1185 (record, exempt) |
| docs/agent-personas.md | 1178 |
| docs/measurements.md | 2274 (record, exempt) |

=> The 2520-word weekly record cannot move into ANY existing routed doc. Three of
them are within 1 word of the wall. It needs a new file, and that file must be
recognised as a RECORD or it warns `over-budget` on arrival.

## Decision (step 3)

- New file `docs/improvements-weekly.md` holds ALL EIGHT entries verbatim, newest
  first. Nothing is deleted.
- `RECORD_NAME` in `validate_disclosure.py` gains the accreting-record class it is
  missing: `improvements`, `changelog`, `history`. The code comment beside it already
  warns that the last fix named the FILE rather than the CLASS; naming only
  `improvements` would repeat that mistake.
- The front page keeps the three most recent entries CONDENSED, each linking to its
  full text in the record. A verbatim copy on both pages would be two sources that
  drift, which this repository already treats as a defect.
- Entry-count note fires above 24 entries. Eight entries: no note.

## Decision (step 1/2)

- Lead the page with the mermaid diagram. The architecture heading regex accepts
  `## How it works`, so the diagram section can sit first and still satisfy the
  contract. The stage table must stay in the SAME section as the fence or
  `readme-diagram-drift` fires on every node label.
- `## Current state` (739 words, one wall) becomes short subsections plus tables.
  Every claim survives.

## Done: record class widened + archive created

- `docs/improvements-weekly.md` created: 2551 words, all EIGHT entries verbatim,
  `###` demoted to `##`, links retargeted (`docs/x` -> `x`, `install/x` -> `../install/x`).
- `RECORD_NAME` widened to `measurements|benchmarks|decisions|adr|rulings|improvements|changelog|history`
  with the measured justification written beside it.
- New test file `install/skills/progressive-disclosure/tests/test_record_budget.py`,
  8 tests, all pass. It pins BOTH halves: a long record does not warn, and a long
  non-record still does. Without the control half, "widen the class" and "delete the
  budget" are indistinguishable from outside.
  => progressive-disclosure suite goes 387 -> 395.

## Finding: a routed record contaminates the disclosure graph

First attempt retargeted the moved entries' links to `../README.md` and `../install/...`.
Result, measured:

```
routed docs: 23  max depth: 4
WARN [over-budget] README.md: 2899 words > 1200 budget at depth 3
WARN [over-budget] install/skills/execution-methodology/methodology.md: 8611 words
WARN [too-deep]   install/skills/graph-navigation/SKILL.md: 4 hops
WARN [over-budget] install/skills/project-onboarding/SKILL.md: 1686 words
WARN [too-deep]   install/skills/project-onboarding/SKILL.md: 4 hops
WARN [over-budget] .../references/execution-loop.md: 4314 words
WARN [too-deep]   .../references/execution-loop.md: 4 hops
```

The validator DELIBERATELY does not seed the crawl from README.md, with a comment
saying seeding it "would mark everything it mentions as routed". A routed historical
record has the same property and nobody had noticed: it links to everything it has
ever touched, so it re-routed the README back into the graph at depth 3 and put the
front page under a 1200-word guide budget.

Fix: in the record, links into `install/` become code spans holding the same path.
Links into `docs/` stay links (those targets are routed at depth 1 already, so they
add no new depth). The reason is written into the record's own header.
Back to `routed docs: 18  max depth: 2`, 0 findings.

## Finding: one test hardcodes the architecture heading

`test_readme_diagram.CorpusTest.test_putting_the_exported_image_back_is_refused`
asserts the literal string `"## Architecture\n"` is present in the real README.
Renaming the section to `## How it works` — which `README_SECTIONS` accepts — turned
the suite red. REFUSED to weaken the test. Kept the heading `## Architecture` and
moved the whole section to the top instead. The diagram still leads; nothing was
relaxed to fit the edit.

## Template changes (step 4)

`install/skills/execution-methodology/references/readme.md` (676 -> 1282 words):
- New `## The first screen` section: bold sentence, four-row at-a-glance table,
  then the mermaid diagram. Diagram leads; prose follows.
- Section order in the fenced example now matches our own front page:
  Architecture (diagram + stage table) -> Running locally -> Components ->
  Current state (subsectioned, with `### Not shipped`) -> Product requirements ->
  Working in this repository -> Recent <record>.
- `Current state` example is now subsectioned with a `What ships today` table,
  instead of one prose block plus a two-column table.
- New rule **A record does not live on the front page**, carrying BOTH things that
  bit here: check the destination word budget first, and check the record's
  outbound links because they join the disclosure graph.
- New rule **Break a wall of prose into subsections**, stating that restructuring
  is not culling.
- New rule **No badges**, split out of the old "nothing here is generated".
- Measured evidence written in: 4,900 words, half a changelog, 739 in one paragraph,
  every section present and correct.

`install/skills/progressive-disclosure/references/standard.md` README contract:
- Added "the diagram goes in the first screen, above the prose" with the same
  measured basis.
- Added "a record does not live on the front page", naming the budget exemption and
  the graph-contamination trap, and linking the template.

## Final gates

| Gate | Before | After |
|---|---|---|
| README.md words | 4910 | 2895 |
| `## Weekly improvements` share | 2520 words / 51% | 470 words / 16% (`## Recent improvements`) |
| validate_disclosure (no flags) | 0 findings | 0 findings |
| validate_disclosure --readme | 0 findings | 0 findings |
| execution-methodology suite | 1031 OK | 1031 OK |
| progressive-disclosure suite | 387 OK | 395 OK (+8 new record-class tests) |
| install.sh --dry-run | rc 0 | rc 0 |
| verify.sh | rc 0 PASS | rc 0 PASS |

## Refused to cut

- Every claim in the old `## Current state` (20 distinct claims counted by hand)
  survives, including the ones that make the repository look worse: receipts are not
  tamper-resistant, `project-conformance` is an unpublished gap, no application
  release exists, and the round count is advisory because a checker run by the party
  it binds cannot bind that party.
- All eight weekly entries are in `docs/improvements-weekly.md` verbatim. Nothing
  was summarised away; the front-page summaries are IN ADDITION to the full text.
- Refused to weaken `test_readme_diagram` to allow a renamed architecture heading.
- Refused to add badges or any marketing line.

## What moved where

| From | To |
|---|---|
| README `## Weekly improvements`, all 8 entries, 2520 words | `docs/improvements-weekly.md`, verbatim, `###` demoted to `##` |
| README `## Weekly improvements` | README `## Recent improvements`: a 3-row index table + 3 summaries, 470 words |
| README `## Architecture` (was 7th) | README 2nd, directly under the title block — diagram leads |
| README `## Current state`, 739 words in one paragraph | 8 `###` subsections, 3 tables, same 20 claims |
| nothing | README title block: a 4-row at-a-glance table |
| nothing | `docs/README.md`: one index row for the record |

Base commit: afacd28. Local `main` advanced to 5453737 while this branch worked, so
diff against afacd28, not against main.
