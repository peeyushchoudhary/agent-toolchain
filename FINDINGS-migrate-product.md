# migrate_to_standard.py --- docs/product/ mode

TOP 3 SO FAR: M1 `rewrite_links()` in the SHIPPED migrator only repairs links whose TARGET moved, never links whose SOURCE moved -- reproduced live on the existing runbook move, it writes a broken link today; M2 Loomaya baseline is exit 0 / 0 findings / 233 unbound, and 64 of 65 spec.md files yield an area id while `met-metric-tree` yields none and must be refused; M3 `check_updated` (A4) will fire on every migrated spec once the migration is COMMITTED, because git log then returns the migration date -- the dirty-tree exemption hides it only until commit.

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

## M1 -- LIVE DEFECT IN THE SHIPPED MIGRATOR (found before writing any new code)
`rewrite_links()` computes `mapped = map_path(old_abs, moves)` and does `if mapped is None:
continue`. `map_path` only answers "did this TARGET move". So a link from a file that ITSELF
moved to a directory-neighbour that did NOT move is never repaired.
This is not hypothetical for the product mode (65 files each rise one directory); it is live in
the migrator's EXISTING runbook move. Reproduced end-to-end at `/tmp/repro-relink`:

    docs/RUNBOOK-deploy.md      -> "See [the design](architecture/design.md)."
    docs/architecture/design.md -> exists

    $ migrate_to_standard.py . --apply --no-create
        moved  docs/RUNBOOK-deploy.md -> docs/runbooks/runbook-deploy.md
    $ cat docs/runbooks/runbook-deploy.md
        See [the design](architecture/design.md).      <- UNCHANGED
    $ ls docs/runbooks/architecture/design.md
        No such file or directory                      <- BROKEN BY THE MIGRATION

The tool whose headline promise is "every markdown link rewritten" breaks one, today, in its
default move set. FIX (one branch, no new function): keep `origin = map_path(f, inverse)`, which is
non-None exactly when THIS FILE moved; when the target did not move but `origin` is not None, use
`old_abs` unchanged as `mapped` and let the existing `if new_rel == bare: continue` guard drop the
no-ops. This is the case the break test must cover.

## 3. Design of the docs/product mode
`--product` selects the mode; the existing structure planner is untouched and the two do not mix.

DERIVATION, all from what the document already says:
  id       H1 `^<AREA-ID> - <Title>$`. Area id kept in the title and the filename; the `id:` value
           is `F-<n>` ONLY because `ID_RE = ^F-\d+[A-Z]?$` refuses anything else.
           `n` continues from the highest existing `F-<n>` in the corpus, assigned in sorted-path
           order so a re-run is stable. NO area id in the H1 => THE WHOLE DOCUMENT IS SKIPPED and
           reported; without an id there is no legal filename either, so half-migrating it would
           be worse than leaving it.
  title    the H1 verbatim, quoted. `FED-C1` survives here.
  prd      1) `docs/product/prd.md` if it exists; else 2) the first resolving `.md` link on the
           document's own `Product spec:` / `PRD:` / `Parent:` line; else 3) REFUSED.
           Emitted root-relative (D3 accepts root-relative first).
  status   first word of the document's own `Status:` line if it is one of
           draft|approved|building|shipped|dropped; else REFUSED.
  updated  `git log -1 --format=%cs -- <original path>`; else REFUSED.
A refused optional field is written as the literal `TODO`, never guessed. `TODO` is chosen on
purpose: an EMPTY value passes `check_keys` and `if target and ...` silently, whereas `TODO` fires
B3/B4/D3 and puts the gap in front of a human. The plan lists every refusal by name.

SELECTION (what counts as spec-shaped):
  under `docs/product/specs/`, suffix `.md`, NOT already matching `F-*.md`,
  basename not in {README,AGENTS,CLAUDE,index}.md,
  AND (basename == `spec.md` OR the H1 starts with an area id).
Nothing outside `docs/` is ever proposed for rename. `plan.md` is excluded because its H1 reads
`Plan - FED-C1 ...` -- the id is not first -- which is checked against all 233 real documents.

## 4. Implementation
in progress

## 5. Validation numbers -- MEASURED ON /tmp/loomaya-copy (a COPY; original never touched)

PLAN (`migrate_to_standard.py . --product`, exit 0, writes nothing), 270 lines:
    bound today: 0 document(s) match docs/product/specs/F-*.md
    spec-shaped and bound by nothing: 65
    move   docs/product/specs/fed-c1-health-only/spec.md
           ->  docs/product/specs/F-1-fed-c1-health-only.md
           + id: F-1   title: "FED-C1 - Health-only ingestion boundary"
             prd: docs/product/specs/feed.md   status: draft   updated: 2026-08-13
    ... 64 of these ...
    NOT MIGRATED -- 1 document(s) a human has to decide:
    skip   docs/product/specs/met-metric-tree/spec.md
           no feature id in the H1 'MET - Metric tree and guardrails'
    verification:
      body words   before 102901   after 102901   IDENTICAL
      links        checked 1254   broken 0
    DRY RUN -- 64 rename(s) plus header. Nothing written.

APPLY (`--product --apply`, exit 0): 64 `git mv` + 64 prepends + **140 relink edits**.
    after --apply:
      body words   before 102901   after 102901   IDENTICAL
      links        checked 1254   broken 0
The 140 relinks are the M1 fix earning its keep: 64 spec files rose out of their directory and
76 sibling README/plan files pointed INTO them. Without the fix most of those 140 would be silent
breakage.

spec_check BEFORE:
    exit 0, ZERO findings
    "0 spec/PRD/milestone document(s) of 236 under docs/product, 0 with a `## Horizontals`
     section, 0 labelled concern row(s), 0 live -- RULE F CHECKED NOTHING
     ... 233 document(s) under docs/product/specs/ are not named `F-<n>-<slug>.md`,
     so NOTHING here read them."

spec_check AFTER:
    exit 1, ONE finding:
      docs/product/specs/F-46-pth-c2-protocol-authoring.md:145  C2  this trigger and precondition
      already appear on line 135; one situation, two answers
    "64 spec/PRD/milestone document(s) of 236 under docs/product, 64 with a `## Horizontals`
     section, 576 labelled concern row(s), 538 live ... 169 document(s) ... not named ..."

    0 -> 64 documents READ.  0 -> 576 concern rows visible to rule F, 538 of them live.
    233 -> 169 unbound, and the 169 left are READMEs, plans and area pages that are correctly
    NOT specs. ZERO B1/B2/B3/B4/D3 findings: the header the mode writes satisfies the schema on
    the first run, so the one finding that survives is about the PROSE, not the plumbing.
    The brief predicted "a single parent-link finding". I got a single CONTENT finding instead,
    because `prd:` was derived from the parent link each document already carried rather than
    left unresolved.

## 5b. M3 CONFIRMED BY MEASUREMENT -- the A4 trap after the migration is COMMITTED
Right after `--apply` the tree is dirty, `check_updated` exempts every path, and spec_check reports
1 finding. I then committed the migration in the copy and re-ran:
    `spec_check --root . --json` -> 65 finding(s): Counter({'A4': 64, 'C2': 1})
    docs/product/specs/F-1-fed-c1-health-only.md:6  A4  `updated: 2026-08-13` disagrees with the
    last commit touching this file (2026-08-22)
So the honest pair of numbers is: **1 finding uncommitted, 65 committed (64 A4 + 1 C2).**
The terminal only shows 40 ("... 65 finding(s) in total, 25 not shown"), which is why the count
must be read from `--json`.
I did NOT paper over this by writing today's date into `updated:`. Today's date would claim the
CONTENT changed today, and the whole point of this mode is that the content did not change at all.
The plan and the apply output both print the NOTE naming the choice and the remedy.

## 6. Break test
in progress

## 7. NOT automated
in progress
