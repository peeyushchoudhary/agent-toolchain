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
