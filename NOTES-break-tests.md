# Break-tests for execution-methodology checkers

TOP 3 SO FAR: N1 three checkers are mode 0644 while every documented invocation is the bare `script.py ...` form (rc=126); 2 & 3 pending mutation runs

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
