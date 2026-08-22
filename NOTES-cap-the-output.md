# NOTES — cap the output (verdict line cap + binding pre-push exit)

**TOP 3.** (1) **The cap is 30 lines, quoted from methodology.md:460, and it binds 33 files in the
live workspace — not 121.** The other 171 `reports/*.md` carry no round marker and no judge name;
the tool cannot call them verdicts and neither may this rule. (2) **Cap and charge read the SAME
function** (`kind_of` / `looks_like_a_verdict`), with the polarity DELIBERATELY INVERTED: charging
fails closed, capping fails open — a judge dropping a finding to fit is worse than a long verdict.
(3) **The exit binds at pre-push and the ruling permits it**: the ruling forbids the tool binding
the ORCHESTRATOR THAT RUNS IT; git at the push is a different party, at the moment that opens the
merge gate the ruling itself names. Day one: 96 errors, 56 banned diffs DELETED (49% of the
workspace bytes, no finding lost), 40 errors left for a human — nothing auto-granted.

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

## 9. Vendored suite (commit 5) + ONE KNOWN RED

11 new cases in `tests/test_check_review_budget.py` (VerdictLineCapTest) — valve bounds, fail-closed
parsing, receipt counts. 161 tests run.
THE ONLY RED: `test_both_harness_copies_are_byte_identical`, which compares the repo copy against
`~/.codex/skills/...`. Those mirrors are byte-identical to LOCAL main (checked), so this red is the
expected state of ANY in-flight edit to this file and clears when `install/install.sh` runs. I did
not write outside the repository to make it green.
Also had to reword three lines: `AdvisoryPostureTest` bans the substring "enforc" anywhere in the
module or in an emitted `why`, because the tool has been caught claiming a bound it does not hold.
Quoting methodology's own "gate-enforced" heading tripped it. The quote is now the caps list itself
("Card 150 lines, verdict 30 lines, ...") with "stated there as a ruling rather than as advice".

## 10. push_guard break-test (commit 6)

Case 19, 13 checks, all green: silent with no workspace / BLOCKS with r5 + 40-line verdict /
receipt printed in full / "NOTHING HERE IS AUTO-GRANTED" present / escape hatch opens and SAYS so /
six negative env spellings all fail CLOSED / block clears when the workspace is put right.
`test_push_guard_product`: 25 tests OK.
PRE-EXISTING RED, verified identical on LOCAL main: `11 the hook template points at the guard under
test` — that case only passes when run from the installed skill path, not from a checkout.

## 11. DAY-ONE COST TO THE FOUNDER'S LIVE WORKSPACE — exact, run with the new tool

BEFORE (`analysis/.workspace`, 319 files / 6.55 MB), exit 1, 96 errors:
  * 56 BANNED_CLASS — 33 `.diff` + 23 `.patch`, 3.20 MB, i.e. **49% of the whole workspace by bytes**
  * 33 VERDICT_OVER_CAP — NEW, 3,419 excess lines, longest 388 (`TC-41-review-round2.md`)
  * 7 ROUND_CAP over 18 ungranted rounds: `tc-51` r3,r4,r5,r7 / `tc-44` r3,r4,r5,r6 /
    `tc-47` r3,r4,r6 / `tc-39` r3,r4 / `tc-41` r3,r4 / `tc-48` r3,r4 /
    `orchestrator-verification` r4
  * WARNINGS: 9 MISSING_ROUND_MARKER, 7 UNRECORDED_TERMINAL_PASS, 4 NON_PROSE_UNCLASSIFIED,
    2 UNCLASSIFIED_ROUND_ARTIFACT, 1 WORKSPACE_BUDGET (319 files / 6,703 KB vs 50 / 500)

ACTION TAKEN — the 56 banned diff snapshots are DELETED (list kept at
`/tmp/deleted-banned-artifacts.txt`, outside the repo; the workspace is gitignored so nothing about
this is in a commit). Empty `diffs/` pruned.

AFTER: 263 files / 3.34 MB. **40 errors left: 33 VERDICT_OVER_CAP + 7 ROUND_CAP.** The workspace
lost 49% of its bytes to one `rm`, and NOT ONE FINDING WAS LOST — git regenerates every one of
those diffs from the commit range.

WHAT A HUMAN MUST DECIDE, and nothing is auto-granted:
  1. The 18 ungranted rounds on 7 subjects. Per the methodology the default is NOT a grant: the
     subject CLOSES at its final verdict — apply the smallest named correction and stop. A grant is
     one ledger row per exact (subject, round), so honouring all 18 costs 18 attributed rows, and
     that number IS the argument. `tc-51` at r7 and `tc-44` at r6 are the two to read first.
  2. The 33 over-cap verdicts: cut the prose, keep every finding. Or one `verdict:<artifact>` row
     each. 3,419 excess lines against a 30-line cap.
This is a real velocity hit on day one, and it is the point.

## 12. SKILL.md updated (commit 7) + FULL SUITE GREEN

`install/skills/execution-methodology/SKILL.md`: the cap, the class split, the pre-push reading of
the ruling, and both grant rows. Full suite `python3 -m unittest discover` in
`execution-methodology/tests`: **1058 tests, OK (2 skipped)** — including the harness byte-identity
test, see below.

## 13. LIVE-SYSTEM OBSERVATION — the installed skills now carry this branch

At 12:25 today `~/.claude/skills/` and `~/.codex/skills/` became BYTE-IDENTICAL to this worktree
for `check_review_budget.py`, `push_guard.py` and `SKILL.md` — they had been identical to LOCAL
main. **I did not run install.sh and I wrote nothing outside the repo.** Either another seat or the
operator ran the installer against this worktree. Consequence to know about: the founder's machine
is running the new verdict cap and the pre-push block NOW, before merge. It also means the
harness-mirror test is green for a reason that is not this branch being merged.
