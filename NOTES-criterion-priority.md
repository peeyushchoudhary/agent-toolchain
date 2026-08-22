# Criterion priority — working notes (agent/criterion-priority)

**TOP 3 SO FAR:** (1) `[P1]` trailing tag, measured invisible to spec_check on 995 real criteria; (2) BUILT the within-feature tiebreak in `plan_waves --ready` (8 vendored tests + 1 selftest case, verified to fail under all three wrong designs); (3) NO RULE — 0 task blocks, 0 milestones, 0 `covers:` anywhere in reach, so no new rule can be red today.

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

### M6 — BUILT: the tiebreak, with a case that dies under all three wrong designs
`plan_waves.py`: `criterion_priorities()` reads the tag through **spec_check's own `criteria()`
fold** (no second `AC-<n>` regex — that pattern is on record as too strict four times), and
`ready_set` key becomes `(-rank, feature, priority, ident)`. `--ready` JSON gains a `priority`
object: `{}` says the specs marked nothing, which is a different statement from "read and changed
nothing". `case_priority_is_the_tiebreak_and_only_inside_the_feature` in `plan_waves_selftest.py`,
seven assertions, and VERIFIED to fail under each wrong design:
- old key `(-rank, ident)` -> 5c and 5g fail (the tag reaches nothing).
- global key `(-rank, priority, ident)` -> **5e fails**: a P1 in the SECOND feature jumps the whole
  of the first, i.e. the first spec to adopt the notation promotes itself over every spec that has
  not.
- priority ahead of `unlocks` -> 5g fails: the measured 11-22% is handed back.
5d reads the tag off a WRAPPED criterion line, which carries no `AC-<n>` at all — a line-at-a-time
reader passes every other assertion and fails that one.
All eleven selftests still pass.

### M7 — NO RULE, and the evidence is that no rule CAN be red here
The red-today hunt, run to exhaustion against the four sibling repos:
- ` ```task ` fenced blocks in the whole tree: **0**. `covers:` on a task: **0**. Milestone
  documents: **0**. `threatens:` in a deferral register: **0**. The entire plan/milestone half of
  this methodology has **no instance anywhere in reach**, so the strongest candidate — "a task's
  `covers:` names a criterion its spec never defines or has withdrawn", which genuinely nothing
  checks today (spec_check never reads plans, plan_waves never reads criterion ids) — has nothing
  to fire on. It is a real gap and it is not RED TODAY.
- On the spec side, 22 of 24 real specs in repo A carry **no `---` block at all** (B1), and repo B's
  233 spec documents are not named `F-*.md`, so no front-matter rule can reach them either.
So: **no `spec_check` rule, and therefore no new case in `spec_check_selftest.py`.** The notation
ships with the template and the dispatcher, and the checker opens with zero findings on 1005 real
criteria — which is the whole point of it being optional.

### M8 — suite state, and one thing the next seat must know
- Vendored suite: **1055 tests, 8 new**, all green except `test_both_harness_copies_are_byte_
  identical` x2. Those two are PRE-EXISTING and not mine: local `main` (a25f09a) is behind the
  repo's checked-out branch, and `check_review_budget.py` changed in `40db635`/`67b203a`, so the
  worktree copy differs from `~/.codex`. Same test passes when run from the repo's own working tree.
- All eleven selftests green.
- The `~/.codex` mirror is compared BY BYTES by that test. Anything shipped here must be installed
  into the mirror or that test starts failing for the next seat as well.
- REPO CONVENTION found in `40db635..`: commit `b4ccc82` "working notes do not ship at the repo
  root" deleted a sibling seat's running-findings file for exactly this reason. This file is
  therefore deleted in the last commit of the branch; every finding in it is in a commit message,
  in `references/specs.md`, or in a test name, and git log keeps the file itself.

### M9 — deliberately NOT built
- No `spec_check` rule and no new `spec_check_selftest.py` case (M7 is why).
- No `priority:` front-matter key. `withdrawn: [3, 9]` earns its second index of criterion numbers
  because the body deletes the text; here the criterion stays, so a front-matter list would be a
  second copy of an id that goes stale silently — the restatement failure this page already names.
- Spec-kit's `Independent Test` field: NOT imported. The coverage map plus `trace_check.py` bind a
  criterion to a test that RAN.
- No `Why this priority` prose block. It is unenumerable and unfalsifiable, and the rank plus the
  criterion sentence already say what a dispatcher needs.
- No `P0`. Three values, closed, mirroring `severity:`.
- No default. Absent is absent, never P1 and never last-across-features.
