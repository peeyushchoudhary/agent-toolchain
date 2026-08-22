# Criterion priority — working notes (agent/criterion-priority)

**TOP 3 SO FAR:** (1) `[P1]` trailing tag measured invisible to spec_check on 995 real criteria (0 new, 0 lost); spec-kit's `(P1)` after the id raises a false C1 on every marked line; (2) priority CAN reach `--ready` for free (`milestone_features` already opens every spec) but only as a WITHIN-FEATURE tiebreak, never in the primary key; (3) no spec_check rule: zero of 1005 criteria carry priority, so every candidate rule is green on day one.

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

### M4 — Does priority reach the dispatcher? YES, and the plumbing already exists
- `--ready` REFUSES to run without `--milestone` (ids are plan-local otherwise), and
  `milestone_features()` already opens **every** `docs/product/specs/F-*.md` with its own `Doc` to
  read `milestone:`. Reading the criterion lines of those same already-open documents costs one
  extra pass over files the run has loaded anyway. No new file walk, no new argument.
- `covers: [AC-4, AC-7]` is already on every task and `W5` already fails a task whose `covers` is
  empty, so **every dispatchable task already names its criteria**. The join is `covers` -> `AC-n`
  -> `[Pn]` in that feature's spec. Nothing new has to be authored on the task side.
- Current order: `sorted(key=lambda t: (-rank[t], t.ident))` where `rank` = transitive downstream
  count. `unlocks()` records the measurement: id-order was no faster than the wave barrier and at
  five writers SLOWER; rank-order is 11-22% faster. **Priority must not touch the primary key.**
  A P1 leaf ahead of a P3 task that unlocks twenty lengthens the makespan and gives back the
  measured 11-22%.

### M5 — WHERE priority may sit in the key, and what breaks
The safe insertion is `(-rank, FEATURE(ident), priority, ident)`.
Ids are qualified `F-<id>/T<n>`, and `/` (0x2F) sorts below `0` (0x30) and below `A`, so sorting by
feature-prefix then ident is IDENTICAL to sorting by ident. **Inserting priority between them
reorders tasks only WITHIN one feature and cannot move one feature ahead of another.**
That is the answer to "two tasks cover criteria of different priority":
- Same task, several criteria: the task takes the BEST (lowest) priority it covers. The task has to
  run for that criterion to close, so the criterion's rank is the task's floor.
- Two tasks, same feature: the spec author ranked those against each other. Honour it.
- Two tasks, different features: NOT COMPARED, deliberately. Nobody ranked feature against feature
  in a spec; the milestone is the document that does that, and it is the one place ordering already
  lives. A cross-feature priority key would let one spec adopting the notation silently demote every
  feature that has not — the "unprioritised looks like all-P1" inversion, arriving through the
  dispatcher instead of through a checker.
- Unmarked criteria inside a feature that DOES mark some: sort after the marked ones, and only
  inside that feature. A feature that marks nothing is bit-for-bit unchanged.
