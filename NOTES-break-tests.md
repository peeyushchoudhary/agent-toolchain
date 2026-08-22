# Break-tests for execution-methodology checkers

TOP 3 SO FAR: N4 milestone_seal verify() never re-checks the tree it was asked about (green); N2 a start receipt can be silently OVERWRITTEN (green); N1 three checkers ship mode 0644 against a bare documented invocation. 20 uncovered gates found across 6 scripts so far.

## 0. Method
in progress

## 1. Script inventory / verification of the list
in progress

## 2. Placement decision (selftest script vs tests/)
in progress

## 3. Per-script real defects found (mutation log)
in progress

## 4. Scripts with NO real case, and why
in progress

## 5. NEW live defects discovered
in progress

## 6. Validation results
in progress

## 0. Method  (UPDATED)
Baseline: execution-methodology `unittest discover` = 1014 tests, OK (skipped=2), 95s.
Mutation harness: patch one line in a checker, re-run only the checker's own test module(s).
If the suite stays GREEN under a mutation that changes real behaviour, that mutation is a
REAL uncovered defect and earns a break-test case. If the suite goes RED, the case is already
covered by unittest and does NOT need a duplicate break-test case.

## 2. Placement decision (DECIDED)
House precedent = `*_selftest.py` SCRIPT beside the checker (progressive-disclosure has exactly
two: push_guard_selftest.py, identifier_guard_selftest.py). Both are hand-runnable, exit 0/1/2.
CRITICAL OBSERVATION (a finding in its own right): `install/verify.sh` runs
`python3 -m unittest discover -s tests -t tests` per skill. It does NOT run the two existing
selftest scripts. So the house precedent's own break-tests are executed by NOTHING automated —
they only run when a human types the command. A break-test nobody runs is the same failure the
doctrine names one layer up ("a guard nobody has watched fail is not evidence of anything").
DECISION: keep the script shape (hand-runnable, matches precedent) AND add a thin
`tests/test_<name>_selftest.py` that subprocess-runs the script and asserts rc==0, so
`unittest discover` — and therefore verify.sh — executes every case.

## 5. NEW live defects discovered  (N1)
### N1 — three of the eleven checkers are NOT EXECUTABLE, and every documented invocation is the bare form
`ratio_meter.py`, `trace_check.py`, `weekly_review.py` are mode `0644`. The other eight are `0755`.
All eleven carry `#!/usr/bin/env python3`.
SKILL.md documents them as bare commands, e.g.:
    ratio_meter.py --range main..HEAD
    weekly_review.py --repo PATH --weeks 8
and references/execution-loop.md step 8 / the milestone block documents:
    trace_check.py --root . --evidence <receipt> --commit <range>
    ratio_meter.py --repo . --range <range>
Measured: `./ratio_meter.py --help` -> rc=126, "Permission denied".
NOT ONE of the 1014 tests asserts the mode bit, and verify.sh does not check it either — the whole
suite invokes the scripts as `python3 <path>`, which is exactly the invocation the docs do NOT use.
Class: the same class as push_guard's case 6 ("the break-test invoked the guard the way nothing
ever invokes it"), inverted — here the SUITE invokes it a way the DOCS never tell a reader to.

### N2 — start_junit_run.py: the receipt's SINGLE-USE property is asserted by SHAPE only
Mutation log (run = the script's own mapped test modules):
  S1  `output.open("x")` -> `open("w")`                      GREEN — suite passes
  S6  delete the `if output.exists(): parser.error(...)` precheck  GREEN — suite passes
  S1+S6 TOGETHER (both layers removed at once)               GREEN — suite passes, 2436 tests OK
        => a start receipt can be SILENTLY OVERWRITTEN and nothing in 1014 tests notices.
        Overwriting the receipt resets `started_at_unix_ns`, which is the entire staleness
        boundary verify_junit.py trusts. This is the replay the design says it forbids.
  S5  `"nonce": secrets.token_hex(32)` -> `"nonce": "0" * 64` GREEN — suite passes
        => the nonce is checked for SHAPE (`[0-9a-f]{64}`) by verify_junit and for nothing else.
        A constant nonce makes every run carry the same run identity; no test compares two.
  S2  delete the `.consumed` marker precheck                 GREEN — suite passes
  S3  never snapshot pre-existing XML                        RED — covered
  S4  nonce shortened to 16 bytes                            RED — covered (regex catches it)

### N3 — verify_junit.py: three real gates have NO test at all
  M2  `if stat.st_ctime_ns <= boundary:` -> dead             GREEN — suite passes
        => the `touch`ed stale file. mtime forward, ctime old: an OLD green XML file made to
        look fresh with `os.utime` passes verification. This gate is the ONLY thing that
        catches it and nothing exercises it.
  M3  receipt fs-timestamp window 5s -> 5,000,000s           GREEN — suite passes
        => a receipt hand-written later with an old `started_at_unix_ns` is accepted.
  M7  `--output must be outside the result directory` -> dead GREEN — suite passes
        => evidence written INTO the results dir, where it becomes pre-existing content for
        the next run.
  M1 replay-by-hash, M4 skipped, M5 expect-count, M6 aggregate, M8 zero-tests,
  M9 duplicate-suite-identity                                RED — all covered

### N4 — milestone_seal.py: SEVEN documented properties, none of them tested
  MS1  `verify()`: delete the `receipt.get("tree") != tree` re-check     GREEN — suite passes
       The docstring above that block says: "Every field is re-checked against the question that
       was asked, rather than trusted because the FILENAME matched." The command and exit
       re-checks ARE tested (MS2, MS3 both RED). The TREE re-check — the one the whole
       tree-vs-commit argument rests on — is tested by nothing.
  MS6  `inside = line.strip().lower() == GATE_SECTION` -> substring match GREEN — suite passes
       The docstring argues this case explicitly: "A looser match ('any heading containing
       validation') would pick up a `## Validation strategy` section written for a human and
       treat the first `Gate:`-shaped line under it as an executable command." Untested.
  MS7  `Gate:` LAST-line-wins -> first-line-wins                          GREEN — suite passes
       Also a deliberately argued property ("The LAST such line in the section wins,
       deliberately"), also untested.
  MS9  command digest in the receipt NAME `[:12]` -> `[:2]`              GREEN — suite passes
       The docstring's reason for hashing the command into the name is that "two milestones
       sealed from one tree ... do not overwrite each other's evidence". Nothing tests two
       receipts from one tree.
  MS11 `if not isinstance(receipt, dict)` -> dead                        GREEN — suite passes
       A receipt whose JSON is `[]` then raises AttributeError out of `verify()`; Python exits 1,
       which is the code RESERVED for "no valid receipt". The script's own SealError docstring
       forbids exactly this collapse ("exit 2, not 1").
  MS12 `if sum(modes) != 1` -> `< 1`                                     GREEN — suite passes
       `--record M1 --verify --tree T --command C` is then accepted, takes the verify branch,
       and NEVER RECORDS. Same class as the already-on-record plan_waves defect
       "`--milestone --commit` accepted the flag and never called the check".
  MS10 atomic write-then-rename removed                                  GREEN — but see s.4
  Covered (RED, no case needed): MS2 command re-check, MS3 exit re-check, MS4 dirty-tree refusal,
  MS5 two-documents-claim-the-id, MS8 tree-not-commit binding.

### N5 — weekly_review.py is the BEST-covered script; only two real cases
  WR11 `share_text` `{value:5.3f}` -> `{value:5.2f}`                     GREEN — suite passes
       The function's own docstring is the specification: "Three decimals, not two: a week
       printed as `0.10  BREACH` argues with its own marker." Nothing tests it, so the report
       can be made to contradict its own PASS/BREACH column and stay green.
  WR9  weekly BREACH marker `> ceiling` -> `>= ceiling`                  GREEN — suite passes
       The exact-ceiling boundary is tested nowhere.
  Covered (RED): WR1 empty-weeks-not-averaged, WR2 dead band, WR3 all-repos-unreadable -> 2,
  WR5 name-not-path, WR6 --weeks<1, WR7 --ceiling range, WR8 insufficient history,
  WR10 "there is no exit 1".
  (WR4 was a no-op edit and is discarded, not a result.)

### N6 — trace_check.py: two uncovered, six covered
  TC4  CITE_RE loses its RIGHT boundary `(?![A-Za-z0-9])`                GREEN — suite passes
       Consequence: a test method named `testAC1Foo` matches as criterion `AC-1F`, because
       `AC-?(\d+[A-Z]?)` then eats the `F`. A phantom criterion id is invented out of an
       ordinary method name and traced as if it were real. The LEFT boundary is tested (TC3
       RED); the right one is tested by nothing.
  TC8  `PARAMETERISED_RE` made inert                                     GREEN — suite passes
       Its own comment gives the case: `resends__F7_AC2[2]` -> `resends__F7_AC2`. A JUnit
       parameterised test name keeps its `[2]` suffix, so the executed-test identity no longer
       matches, and coverage that RAN reads as coverage that did not.
  Covered (RED): TC1 normalise leading zeros, TC2 nearest-qualifier inheritance, TC3 left
  boundary, TC5 coverage-map heading anchoring, TC6 not-tested heading anchoring, TC7 draft
  specs excluded from LIVE.

### N7 — sync_methodology.py: four uncovered
  SM3  `strip_code` stops stripping INLINE code                          GREEN — suite passes
       The function's docstring is the specification: "A repository that documents the marker —
       in its own route index, under a fence — must not thereby be reported as having deferred."
       The FENCE half is tested (SM2 RED). The INLINE-backtick half is tested by nothing, so a
       README that merely MENTIONS the marker in backticks is read as a deferral DECISION.
  SM5  `if total > 1:` -> dead (two markers, first wins)                 GREEN — suite passes
       The error text says "keep exactly one"; nothing tests that two are refused.
  SM8  `FENCE_RE` `^\s{0,3}(?:```|~~~)` -> `^(?:```)`                   GREEN — suite passes
       An indented fence (a fenced block inside a list item) and a `~~~` fence both stop
       toggling the fenced state, so everything inside them is read as prose.
  SM9  marker regex `\{[^\r\n]*\}` -> `\{.*?\}` with DOTALL semantics GREEN — suite passes
       A multi-line marker is accepted although the error text says it "must be one single-line
       JSON object".
  Covered (RED): SM1 is_ours, SM2 fenced-code stripping, SM4 deferral reason, SM7 overlay
  appended, SM10 deferral date format.
  (SM6 was a comment-only edit and is discarded, not a result.)

## 2. Placement decision — IMPLEMENTED
`scripts/<name>_selftest.py` (house shape, hand-runnable, exit 0/1/2)
  + `tests/test_break_tests.py`, which DISCOVERS `scripts/*_selftest.py` and runs each as a
    subprocess test method, so verify.sh executes them. Roster is discovered, never listed;
    an empty roster fails.

## 3. Per-script cases WRITTEN so far
  start_junit_run_selftest.py   5 cases / 21 assertions — watched fail under 5 mutations
  verify_junit_selftest.py      4 cases / 22 assertions — watched fail under 3 mutations
  milestone_seal_selftest.py    6 cases / 20 assertions — watched fail under 4 of 5 mutations
    (the 5th, the loose gate heading, needed the mutation stated the way the docstring states the
     risk — `"validation" in line` — which IS green under the suite and IS caught here)

### CORRECTION to N7 — SM9 RETRACTED
The "multi-line marker accepted" mutation was a NO-OP: dropping `[^\r\n]` from MARKER_RE without
adding `re.DOTALL` changes no behaviour, because `.` does not match a newline by default. Re-run
with `re.DOTALL` the suite goes RED, so the single-line rule IS covered. No case written for it.
A green run against a no-op edit is not a finding; recording the retraction because a retraction
is evidence too. sync_methodology's real uncovered set is SM3, SM5, SM8 — three, not four.

## 3. Per-script cases WRITTEN (running)
  start_junit_run_selftest.py   5 cases / 21 assertions — fails under 5 of 5 mutations
  verify_junit_selftest.py      4 cases / 22 assertions — fails under 3 of 3
  milestone_seal_selftest.py    6 cases / 20 assertions — fails under 5 of 5
  sync_methodology_selftest.py  4 cases / 11 assertions — fails under 3 of 3
  plan_waves_selftest.py        4 cases / 17 assertions — fails under 4 of 4 (all four are
                                defects that were LIVE in the repo, from the seed set)
NOTE on plan_waves case 4: the FIRST version of it stayed green with `qualify()`'s serialises
qualification removed — it asserted a true statement that was not the defect. Rewritten to the
in-feature pair, where the documented plan-local spelling must silence W6 under --milestone.
A case that cannot fail against the defect it names is decoration; caught by always watching
each case fail before keeping it.
