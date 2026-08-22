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

## 3. The founder ruling, read in full — I DID make the exit binding at pre-push

Read: `check_review_budget.py` module docstring :2-:21 and the FAMILY VIEW comment at :1140.
The ruling (2026-08-20) says, exactly: "The tool is run BY the orchestrator, on inputs the
orchestrator controls ... **No in-process control can bind its own operator**", and "THE BINDING
CONTROL IS A HUMAN READING THE RECEIPT AT THE MERGE GATE."

My reading, and why a pre-push hook is not the thing forbidden:
* The ruling binds a party relationship, not an exit code. It forbids the tool pretending to bind
  the ORCHESTRATOR that invokes it pre-dispatch and writes the very filenames it reads.
* The ruling itself states the exit code's purpose: "it FAILS LOUDLY on the shapes it can see, so
  that drift costs a deliberate act rather than an oversight — the exit code is a tripwire against
  forgetting, not a gate against intent." A pre-push hook is that tripwire at the last cheap moment.
* The ruling NAMES the merge gate as where spend is adjudicated. A push is what opens the PR. The
  hook does not replace the human; it puts the receipt in front of them before the content leaves.
* It claims nothing the KNOWN-OPEN list retracts. Rename, delete, move or out-scope the artifact and
  the hook goes quiet, exactly as the tool does. The wiring says so in its own words and does not
  say "closed".
So: BOUND at pre-push, and the module docstring keeps saying it does not bind its operator. Both are
true, because they are about two different parties.

## 4. Day-one cost, MEASURED before writing a line of code

Live workspace `analysis/.workspace/toolchain-remediation` (319 files), classified with the tool's
OWN discriminators:
| class | files | over 30 lines |
|---|---|---|
| prose + round marker + `kind_of=="review"` (charged verdicts) | 24 | **24** (2,555 excess lines, longest 388) |
| prose + marker-free + `looks_like_a_verdict()` (JUDGE_NAME_TOKENS) | 9 | **9** (longest 290) |
| prose `work` kinds (fix/impl/analysis) | 3 | not capped |
| non-prose evidence (.xml/.txt/.diff/.tsx) | 4 | not capped |
| everything else marker-free (109 `-report`, 31 `-review`, 18 `-diff`, ...) | 277 | not capped |

**So the honest day-one number for the verdict cap is 33 files, not 121.** The 121-over-150 figure
counts every `reports/*.md`; most carry no round marker and no judge name, so neither the counter
nor this cap can call them verdicts. They are the `-report` class methodology:454 bans by prose,
and banning it mechanically is a DIFFERENT rule with a different break-test — not smuggled in here.
`-review` and `-audit` stay out of the marker-free set because `JUDGE_NAME_TOKENS` (:326) already
excludes them by name as ordinary nouns; overriding that would be inventing a class.

## 5. Implemented — the cap (commit 2)

`check_review_budget.py`: `VERDICT_LINE_CAP = 30`, `verdict_lines()` (fails open on any unreadable
file), `charge_the_verdict_cap()` called from exactly two sites, new error `VERDICT_OVER_CAP`, new
warnings `VERDICT_GRANT_APPLIED` / `DUPLICATE_VERDICT_GRANT`, receipt key `verdict_lines` carrying
EVERY verdict measured (not only breaches) so the cap is checkable against the directory it read.
Bookkeeping (`charged`, `charged_files`, `round_width`) runs BEFORE the cap at both sites — the
"suppression must never run ahead of the bookkeeping it does not intend to skip" rule this file has
recorded four occurrences of.

Smoke test on a synthetic workspace: `-r1-reviewer.md` 40 lines -> ERROR; `-r1-fix-report.md`
40 lines -> silent; `-r1-opinion.md` (unrecognised kind) 40 lines -> charged, NOT capped;
`T2-security.md` 40 lines marker-free -> ERROR + MISSING_ROUND_MARKER; 20-line verdict -> clean.

## 6. The valve — `verdict:<artifact>`, a fourth row type

`ROUND-GRANTS.tsv` is operator data: it is NOT in this repo (`install.sh:76-80` carries it across
installs), it lives in the installed skill, and it already holds round-grant rows. The verdict cap
gets its own row type there:
    SUBJECT<TAB>verdict:<artifact-filename><TAB><granting-commit><TAB><date><TAB><reason>
Keyed on the ARTIFACT, not on (subject, round): the finding is the length of one file, and a pair
key would excuse every verdict filed at that round including ones nobody read. Suppresses
VERDICT_OVER_CAP for that filename and nothing else. The error message prints the exact row,
pre-filled with subject, filename and today's date, so the first person blocked reaches for the
ledger and not for the off switch.
NOTE FOR THE OPERATOR (not fixable from this repo): the header comment inside the installed
ROUND-GRANTS.tsv still says `FORMAT SUBJECT<TAB>r<N>|terminal<TAB>...`. It was already stale — it
does not mention `terminal-spent` either. The script docstring is the authority and is now current.

## 7. Implemented — binding at pre-push (commit 3)

`push_guard.py`: `WORKSPACE_ANCHORS = {sdd, .workspace, workspaces}`, depth-4 `scandir` walk (no
symlinks, skips `.git`/`node_modules`/...), `review_workspaces()`, `review_budget_findings()`, wired
into `run()` beside the product checks with its own adoption predicate and its own loud escape hatch
`PD_ALLOW_REVIEW_BUDGET=1`. `checker()` gained an `applies=` parameter so the "check did not run"
message names the right adoption fact (product dir vs review workspace).
Verified end-to-end on a throwaway git repo: workspace with r5 + 40-line verdict -> rc=1 with the
receipt inline; no workspace -> rc=0 SILENT; escape hatch -> rc=0 and prints that it did not run;
clean workspace -> rc=0 silent.
The guard never reads an artifact name — it hands the anchor dir whole to check_review_budget.py.
That is deliberate: a second classifier in the hook would drift from the first.

## 8. Break-tests (commit 4)

`scripts/check_review_budget_selftest.py` case 4, 15 checks, all pass. PAIRED ON LENGTH — two files
of the same length in one directory, differing only in what the tool already decided they are:
4a-4d verdict blocks / fix-report of identical length does not; 4e `-test-judge` free; 4f `.txt`
never measured; 4g-4h the two polarities in one file (charged AND uncapped); 4i-4j 30 passes, 31
fails; 4k-4l marker-free `-security.md` capped, marker-free `-review.md` not; 4m over-cap verdict
STILL spends its round; 4n-4o receipt reports every length and the cap itself, so test literal and
script constant cannot drift.
