# README restructure — working notes

TOP 3 SO FAR: in progress

## Baseline measurements
in progress

## Constraint verification
in progress

## What moved where
in progress

## Template changes
in progress

## Refused to cut
in progress

## Validation results
in progress

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
