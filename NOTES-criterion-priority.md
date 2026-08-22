# Criterion priority — working notes (agent/criterion-priority)

**TOP 3 SO FAR:** (1) priority is NOT hidden in prose — 1 of 406 / 20 of 589 criteria, all scope nouns; (2) any rule on a new optional field is green on day one by construction; (3) the tiebreak is reachable and safe only INSIDE a feature.

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
