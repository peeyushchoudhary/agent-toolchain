# NOTES — cap the output (verdict line cap + binding pre-push exit)

**TOP 3 SO FAR:** in progress.

## 1. The cap: which number, read where
in progress

## 2. Verdict vs evidence: how the classes were told apart
in progress

## 3. Binding at pre-push: the founder ruling, read in full
in progress

## 4. The valve: ROUND-GRANTS.tsv
in progress

## 5. Day-one cost to the live workspace
in progress

## 6. Break-test (house shape)
in progress

## 1. The cap: which number, read where  — SETTLED

`methodology.md:460` (`install/skills/execution-methodology/methodology.md`), the paragraph
"**The caps are gate-enforced, not advisory.**": "Card 150 lines, verdict 30 lines, distillation 5
lines, workspace 50 files or 500 KB, ledger 500 lines before rotation."
=> **verdict cap = 30 lines. Not invented; quoted.**

Two supporting lines, same file:
* :450 "**Verdicts, not reports, from judges.** Thirty lines, structured, persisted once — and named
  `<subject>-r<N>-<kind>.md`." — gives BOTH the number and the filename grammar the check keys on.
* :454 "**No reports.** A report is a verdict that outgrew thirty lines. The class is banned wherever
  a verdict, a ledger line, or a commit message can carry the finding — which is everywhere except a
  spec, a design, or a decision record". So the exemptions are already named in prose: spec, design,
  decision record. Those live in the TRACKED tree, not in a dated workspace, so a workspace-scoped
  check does not touch them.

## 2. Verdict vs evidence — SETTLED, and the discriminator already existed

I did not invent a classifier. `check_review_budget.py` already answers "is this a judgement?"
because it must, to charge a round. The verdict cap reuses that exact answer, so cap and charge can
never disagree:

* `REVIEW_KIND_TOKENS` (:166) — a judgement. `kind_of()` (:522) returns `"review"`.
* `WORK_KIND_TOKENS` (:170) — fix brief, impl report, analysis, scout, notes: NOT a judgement.
* `EVIDENCE_KIND_TOKENS = {"test"}` (:325) — the measured inversion: `-test-judge` runs a command
  and reports an exit code, 114 PASS / 2 FAIL / 1 none over 124 artifacts, block rate 0.02 vs 0.16
  for `reviewer`. Evidence.
* `NON_PROSE_SUFFIXES = {.xml,.txt,.diff,.tsx}` (:349) — JUnit XML, probe log, source file. Evidence.

So the rule binds: **prose suffix + round marker + `kind_of() == "review"`** — precisely the set the
tool already charges a round for, minus one deliberate exclusion below. Everything else is untouched.

**THE POLARITY IS INVERTED ON PURPOSE, and this is the whole safety argument.**
Charging fails CLOSED: `kind is None` (UNCLASSIFIED_ROUND_ARTIFACT) is charged as a review so a
round is never lost. Capping must fail OPEN: an unknown kind is NOT capped. Reason: the cost of a
wrong charge is one round of budget; the cost of a wrong cap is a judge deleting a finding to fit
30 lines. Those are not symmetric harms. Unknown kind => count it, never cap it.
Same for `MISSING_ROUND_MARKER` names: warned about already, not capped here.
