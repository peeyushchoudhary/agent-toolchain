# Criterion priority — working notes (agent/criterion-priority)

**TOP 3 SO FAR:** (1) `[P1]` trailing tag verified invisible to spec_check on 995 real criteria (0 new, 0 lost findings); spec-kit's `(P1)` after the id would have raised a false C1 on every marked criterion; (2) priority is not hidden in prose (1/406, 20/589); (3) any rule on a new optional field is green on day one by construction.

## 0. Design basis (p_sdd finding, per-story priority)
in progress

## 1. Notation chosen
in progress

## 2. Rule? (RED-TODAY search)
in progress

## 3. Does priority reach the dispatcher (plan_waves --ready)?
in progress

## 4. Deliberately not built
in progress

## 5. Changes shipped
in progress

### M1 — measured corpus (2026, four private sibling repos, anonymised A-D + this one)
- Criteria parsed by `spec_check.criteria()`: repo A **406**, repo B **589**, repo C **10**, repo D **0**. This repo has no `docs/product/` at all.
- Criteria whose text carries ANY prose priority word (P0/P1/priority/MVP/must-have/...):
  repo A **1 of 406**, repo B **20 of 589**, and every repo B hit is the word "MVP" used as a
  scope noun, not as a rank. **Priority is not hiding in prose.** There is no de-facto notation to
  formalise and no drift to catch.
- Horizontal tags (`[authz]` `[audit]` `[money]` `[pii]` `[a11y]`), which `references/specs.md`
  documents on the criterion line: **0 occurrences in 1005 real criteria.** A documented inline tag
  convention already has zero adoption in this corpus. Any second inline tag inherits that number.

### M2 — a rule keyed on a NEW optional field cannot be red today, by construction
Zero specs carry priority today, so every candidate rule (`priority names a withdrawn number`,
`P1 criterion covered by no task`, `priority values not contiguous`) is GREEN on every one of the
1005 criteria on the day it ships. That is the sibling seat's exact warning — "would have passed its
own tests and been the tenth inert checker" — arrived at from the measurement side.

### M3 — NOTATION CHOSEN: `[P1]` as a trailing tag on the criterion line
```markdown
**AC-3** When a refund is retried, given the first attempt settled, no second refund is issued. [P1]
AC-7 When the export is empty, given no rows match, the file is written with a header only. [P3]
```
Values: `[P1]` `[P2]` `[P3]`, and no more values than that. `[P1]` = "if only one criterion in this
spec ships, this one". Optional per criterion and per spec.

**Why this slot and not spec-kit's `(Priority: P1)` after the id:** MEASURED. The tag was appended to
every criterion line in two real repositories — **406 + 589 = 995 real criteria** — and
`spec_check.py` returned the SAME exit code and the IDENTICAL finding set, 0 new and 0 lost, in both.
The notation is invisible to all eleven instruments as they stand.
A marker after the id is NOT: `**AC-1 (P1)** When ...` makes `AC_RE` hand `(P1)** When ...` to
`EARS_RE`, which fails, so **every marked criterion raises a false C1** and the shape checks go
inert on the marked lines. Adopting spec-kit's exact placement would have required changing the one
regex whose over-strictness has already been recorded as wrong four times.
The trailing bracket is also the slot `references/specs.md` ALREADY documents for `[authz]` `[audit]`
`[money]` `[pii]` `[a11y]`, so this is a second value in an existing convention, not a new site.
