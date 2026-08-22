#!/usr/bin/env python3
r"""Break-test for trace_check.py — proves an ordinary method name is not read as a criterion id.

A guard nobody has watched fail is not evidence of anything. The case below reproduces a defect
found by mutating this file's sibling and watching the skill's own `unittest discover` stay green.

  1  a clean corpus traces clean, and the run SAYS what it read
  2  a test named `sends__AC1Foo` is counted as UNATTRIBUTABLE, and invents no criterion

WHAT MADE CASE 2 REAL, measured rather than imagined. Dropping the RIGHT word boundary from CITE_RE
—  `AC-?(\d+[A-Z]?)(?![A-Za-z0-9])` -> `AC-?(\d+[A-Z]?)` — leaves the vendored suite GREEN. The
LEFT boundary is covered; the right one was covered by nothing. With it gone, `sends__AC1Foo` reads
as criterion `AC-1F`, because `[A-Z]?` then eats the `F`: the unattributable count drops from 1 to
0 and the run raises a finding about a criterion no document has ever declared. A checker that
invents an id is worse than one that misses it — it sends a reader to look for something that does
not exist.

WHY THE FIXTURE NAME HAS TWO UNDERSCORES. The left boundary already refuses `testAC1Foo`, because
`t` is alphanumeric. Only a name where the id position is legitimately reachable — the carrier
convention's own `__` separator — reaches the right boundary at all. A fixture that cannot reach
the rule it names proves nothing about it, and `testAC1Foo` was the first attempt here.

A GREEN MUTATION WITH NO CASE, recorded rather than papered over. Making PARAMETERISED_RE inert
(`resends__F7_AC2[2]` keeps its `[2]`) also leaves the suite green, and it IS a real gap. But no
case here can fail against it: CITE_RE's own right boundary accepts `AC2[2]` — `[` is not
alphanumeric — so through every path this script exposes at the command line, the stripped and
unstripped names behave identically. Reaching it needs the `--commit` body matcher against a
source tree, which this file does not build. Asserting the parameterised name traces correctly
would pass against the defect, which makes it decoration; it is left out and named here instead.

WHAT THIS DOES NOT COVER. Both cases drive the INSTALLED sibling as a process, over a corpus and a
REAL evidence receipt produced by start_junit_run.py and verify_junit.py — not a hand-written one,
so the case cannot pass against a receipt shape the verifier would reject. The T1-T6 rules, the
withdrawal register and the T7 body check are covered by the vendored suite and are not duplicated
here. Nothing here writes inside the repository.

Run:  python3 trace_check_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "trace_check.py"

SPEC = """---
id: F-7
title: Resend a pending invite
prd: docs/product/prd.md
status: approved
updated: 2026-01-14
---

# F-7 — Resend a pending invite

## Acceptance criteria
**AC-1** When an admin resends a pending invite, given it has not expired, the system sends a new
mail to the same address.
**AC-2** When an admin resends twice inside five minutes, the system refuses and states the time
the next resend is allowed.
"""

PLAN = """---
feature: F-7
title: Resend a pending invite
spec: docs/product/specs/F-7-resend.md
status: approved
updated: 2026-01-14
---

# F-7 — implementation and validation plan

## Validation plan

### Coverage map

| AC | level | task | note |
|---|---|---|---|
| AC-1 | unit | T1 | |
| AC-2 | unit | T1 | |

### Planned tests

```test
covers: AC-1
assert: sends at 09:20
and_not: does not send when the invite is already accepted
```

### Not tested, and why

### Gate
`./gradlew test`
"""

CLEAN_CASES = [("com.x.ResendTest", "sendsMail__F7_AC1"),
               ("com.x.ResendTest", "refuses__F7_AC2")]

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], capture_output=True,
                          text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def corpus(tmp: Path, cases: list[tuple[str, str]]) -> tuple[Path, Path] | None:
    """A repository, and a REAL evidence receipt over XML written between start and verify."""
    root = tmp / "repo"
    results = root / "build" / "test-results" / "test"
    work = root / ".work"
    results.mkdir(parents=True)
    work.mkdir()
    (root / "docs" / "product" / "specs").mkdir(parents=True)
    (root / "docs" / "product" / "plans").mkdir(parents=True)
    (root / "docs" / "product" / "specs" / "F-7-resend.md").write_text(SPEC, encoding="utf-8")
    (root / "docs" / "product" / "plans" / "F-7-resend.md").write_text(PLAN, encoding="utf-8")

    start, receipt = work / "start.json", work / "evidence.json"
    proc = script("start_junit_run.py", "--results", str(results), "--output", str(start))
    if proc.returncode != 0:
        check("0 the run-start receipt was created", False, proc.stdout + proc.stderr)
        return None

    classes: dict[str, list[str]] = {}
    for fqcn, name in cases:
        classes.setdefault(fqcn, []).append(name)
    for fqcn, names in classes.items():
        body = "".join(f'  <testcase classname="{fqcn}" name="{name}" time="0.01"/>\n'
                       for name in names)
        (results / f"TEST-{fqcn}.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<testsuite name="{fqcn}" tests="{len(names)}" skipped="0" failures="0" '
            f'errors="0">\n{body}</testsuite>\n', encoding="utf-8")
    expects = [arg for fqcn, names in classes.items()
               for arg in ("--expect", f"{fqcn}={len(names)}")]
    proc = script("verify_junit.py", "--results", str(results), "--start-receipt", str(start),
                  "--output", str(receipt), *expects)
    if proc.returncode != 0:
        check("0 the evidence receipt was verified", False, proc.stdout + proc.stderr)
        return None
    return root, receipt


def trace(root: Path, receipt: Path) -> dict:
    proc = script("trace_check.py", "--root", str(root), "--evidence", str(receipt), "--json")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_stdout": proc.stdout[:300], "_stderr": proc.stderr[:300]}


def case_a_clean_corpus_traces_clean() -> None:
    """The positive control. Without it, case 2 would pass against a script that read nothing."""
    with tempfile.TemporaryDirectory() as td:
        built = corpus(Path(td), CLEAN_CASES)
        if built is None:
            return
        report = trace(*built)
        check("1a a covered corpus raises no finding", report.get("count") == 0,
              str(report.get("findings"))[:300])
        check("1b and the run says how many testcases it actually read",
              report.get("testcases") == 2, str(report.get("testcases")))
        check("1c every one of them carried an id, so none is unattributable",
              report.get("unattributable") == 0, str(report.get("unattributable")))
        check("1d the summary states the limit of what an executed id proves",
              "not that it asserts anything" in (report.get("summary") or ""),
              str(report.get("summary"))[:300])


def case_an_ordinary_method_name_invents_no_criterion() -> None:
    with tempfile.TemporaryDirectory() as td:
        built = corpus(Path(td), CLEAN_CASES + [("com.x.ResendTest", "sends__AC1Foo")])
        if built is None:
            return
        report = trace(*built)
        check("2a a name that merely LOOKS like an id is counted as unattributable",
              report.get("unattributable") == 1, str(report)[:300])
        check("2b it is not silently dropped — the testcase count still includes it",
              report.get("testcases") == 3, str(report.get("testcases")))
        check("2c and no finding is raised about a criterion no document declares",
              report.get("count") == 0, str(report.get("findings"))[:400])


def main() -> int:
    for name in ("trace_check.py", "start_junit_run.py", "verify_junit.py"):
        if not (SCRIPTS / name).exists():
            print(f"{name} not found at {SCRIPTS / name}", file=sys.stderr)
            return 2

    print("trace_check break-test")
    for case in (case_a_clean_corpus_traces_clean,
                 case_an_ordinary_method_name_invents_no_criterion):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — an id is read where one is written, and nowhere else")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
