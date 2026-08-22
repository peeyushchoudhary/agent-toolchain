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
in progress

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
