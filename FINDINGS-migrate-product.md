# migrate_to_standard.py --- docs/product/ mode

TOP 3 SO FAR: (in progress)

## 1. Reading the existing migrator
`install/skills/progressive-disclosure/scripts/migrate_to_standard.py`, 492 lines, stdlib only.
- `plan_moves(root)` -> list[(src,dst)]; `plan_creates(root, moves)` -> list[(path, body)].
- `rewrite_links(root, moves, apply)` resolves each link against the ORIGINAL dir via an inverse
  move table (`map_path(f, inverse)`), then `os.path.relpath(mapped, f.parent)`. Reusable as-is for
  the product mode: it only needs the moves list.
- `backup(root)` copies docs/, AGENTS.md, CLAUDE.md to `../.<name>-docs-backup-<stamp>`.
- `main()` prints plan, returns 0 on dry run; refuses `--apply` on a dirty tree unless `--force`.
- **It has NO selftest and NO test file.** `ls scripts/` shows `push_guard_selftest.py`,
  `identifier_guard_selftest.py` but no `migrate_to_standard_selftest.py`. So requirement 6 =
  "it has none, say so and add the smallest honest one".

## 1b. What the schema actually binds (spec_check.py)
- `Doc.is_spec` = `self.path.match("docs/product/specs/F-*.md")` -- path glob, nothing else.
- `Doc.looks_like_a_spec` = under `docs/product/specs/` and not spec/prd/milestone. Counted into
  `binding.unbound_specs`, printed as a *note*, never a finding. That is the silence to close.
- `ID_RE = re.compile(r"^F-\d+[A-Z]?$")` -- so `FED-C1` can NEVER be the `id:` value. Confirms the
  brief: area id survives in the H1 title + filename slug; `F-<n>` is only the machine key.
- `SPEC_KEYS` required = `("id","title","prd","status","updated")`; optional includes
  `depends, withdrawn, decisions, edge_cases, milestone, reviewed_by, severity, regresses`.
- `STATUSES = ("draft","approved","building","shipped","dropped")`.
- B3 filename rule: `doc.path.name.startswith(id + "-") or doc.path.stem == id`. So `F-7-<slug>.md`.
- D3: `prd:` must resolve relative to root OR to the spec's own dir -- else finding
  "`prd: X` does not resolve to a file, so this spec has no parent".
- `check_updated` compares `updated:` against the file's git commit date (dirty paths exempt).

## 2. Corpus survey (real repo copy)
CORPUS = `~/Documents/Claude/Projects/Loomaya`, validated on a COPY at `/tmp/loomaya-copy`
(`git clone --local --no-hardlinks`, 21 MB, HEAD e8ea7b0). Original never touched.

BASELINE `spec_check.py --root .` on the copy, exit 0, ZERO findings, one note line:
    ... 0 spec/PRD/milestone document(s) of 236 under docs/product, 0 with a `## Horizontals`
    section, 0 labelled concern row(s), 0 live -- RULE F CHECKED NOTHING ...
    233 document(s) under docs/product/specs/ are not named `F-<n>-<slug>.md`,
    so NOTHING here read them.
This is the exact "0 findings mistaken for clean" state the brief describes.

SHAPE OF THE 233 under `docs/product/specs/`:
    65  <slug>/spec.md      <- the spec-shaped ones
    80  README.md
    65  plan.md
     4  AGENTS.md / CLAUDE.md
    19  area pages + eval material (feed.md, trust.md, evals/**, rubrics, ...)
Only the 65 may be renamed. plan.md/README.md are siblings of a spec and must be left alone.

**THE 64/65 SPLIT IS REAL AND MEASURED.** Every `spec.md` H1 is `<AREA-ID> — <Title>`, e.g.
`# FED-C1 - Health-only ingestion boundary`. 64 of 65 carry a matchable area id.
The one that does NOT: `docs/product/specs/met-metric-tree/spec.md`, H1 = `MET - Metric tree and
guardrails` -- an area with no ordinal. That is exactly the "64 of them" in the brief.
The mode must REFUSE to invent an id for it and hand it to a human.

## 3. Design of the docs/product mode
in progress

## 4. Implementation
in progress

## 5. Validation numbers (word count, link check, spec_check before/after)
in progress

## 6. Break test
in progress

## 7. NOT automated
in progress
