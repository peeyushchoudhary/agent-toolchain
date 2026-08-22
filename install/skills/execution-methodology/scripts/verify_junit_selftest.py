#!/usr/bin/env python3
"""Break-test for verify_junit.py — proves the freshness gates fire, one gate at a time.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
found by mutating this file's sibling and watching the skill's own `unittest discover` stay green,
so a regression re-breaks a named case instead of silently accepting stale evidence.

  1  a real run start, real fresh XML                       exit 0, and the receipt is consumed
  2  a stale results tree MOVED into place, its files
     carrying a future mtime                                exit 1  <- the ctime gate, alone
  3  a receipt hand-written later around an old boundary    exit 1  <- the 5-second window
  4  --output written INSIDE the results directory          refused, and nothing is written there

WHAT MADE THESE CASES REAL, measured rather than imagined. Each mutation below was applied to
verify_junit.py and each left the vendored suite GREEN:
    `if stat.st_ctime_ns <= boundary:` -> dead                    green
    `maximum = started + 5_000_000_000` -> 5_000_000_000_000_000  green
    `if output == results or results in output.parents:` -> dead  green
Six other gates were mutated and went RED — the replay-by-hash check, the skipped-test check, the
--expect count check, the testsuites aggregate check, the zero-tests check and the duplicate-suite
check are all genuinely covered, so this file deliberately writes no case for them. Duplicating a
covered gate here would inflate the case count without adding evidence.

WHY CASE 2 IS BUILT THE WAY IT IS, because the construction is the whole finding. The ctime gate
sits behind two others: a pre-existing file is normally caught by its SHA-256 being in the start
receipt's snapshot, and a copied file is normally caught by its mtime. Reaching ctime and only
ctime needs all three of: the results directory absent at run start (so the snapshot is empty), a
future mtime (so the mtime gate cannot fire), and `rename` rather than `copy` (rename preserves
ctime; a write or a `utime` would reset it). That is a stale results tree from a machine with a
skewed clock, moved into place after the run started — the one arrangement that defeats every
other check in the file.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process. Nothing here
imports it, so nothing here proves anything about a partially edited module, and nothing here
proves the protocol against a deliberate local writer — verify_junit.py's own docstring already
disclaims that. Nothing here writes inside the repository.

Run:  python3 verify_junit_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFY = HERE / "verify_junit.py"
START = HERE / "start_junit_run.py"

SUITE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="ExampleSuite" tests="1" failures="0" errors="0" skipped="0">
  <testcase classname="com.example.ExampleTest" name="passes"/>
</testsuite>
"""

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def run(script: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def start(results: Path, receipt: Path) -> int:
    code, _ = run(START, "--results", str(results), "--output", str(receipt))
    return code


def verify(results: Path, receipt: Path, output: Path,
           expect: str = "com.example.ExampleTest=1") -> tuple[int, str]:
    return run(VERIFY, "--results", str(results), "--expect", expect,
               "--start-receipt", str(receipt), "--output", str(output))


def case_fresh_run_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        receipt = root / "start.json"
        check("1a a run start is created", start(results, receipt) == 0)
        # The XML must be written strictly after the boundary. time_ns resolution on some
        # filesystems is coarser than one nanosecond, so the write is separated deliberately.
        time.sleep(0.05)
        (results / "TEST-example.xml").write_text(SUITE_XML, encoding="utf-8")
        output = root / "evidence.json"
        code, out = verify(results, receipt, output)
        check("1b fresh XML after a real run start verifies", code == 0, f"got {code}: {out[:300]}")
        if code != 0:
            return
        payload = json.loads(output.read_text(encoding="utf-8"))
        check("1c the evidence carries the run nonce, not just a count",
              payload.get("run_nonce") == json.loads(receipt.read_text(encoding="utf-8"))["nonce"])
        check("1d the evidence records the observed test count", payload.get("tests") == 1,
              repr(payload.get("tests")))
        check("1e the start receipt is consumed, so it cannot be replayed",
              Path(str(receipt) + ".consumed").is_file())


def case_moved_stale_tree_with_future_mtime() -> None:
    """The ctime gate, reached with every other gate stepped around. See the module docstring."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        staging = root / "staging"
        staging.mkdir()
        stale = staging / "TEST-example.xml"
        stale.write_text(SUITE_XML, encoding="utf-8")
        future = time.time() + 3600                      # a skewed clock, an hour ahead
        os.utime(stale, (future, future))

        results = root / "results"                       # ABSENT at run start: empty snapshot
        receipt = root / "start.json"
        check("2a the run starts against a directory that does not exist yet",
              start(results, receipt) == 0)
        time.sleep(0.05)
        staging.rename(results)                          # rename preserves ctime; copy would not

        moved = results / "TEST-example.xml"
        boundary = json.loads(receipt.read_text(encoding="utf-8"))["started_at_unix_ns"]
        info = moved.stat()
        check("2b the setup really does defeat the mtime gate",
              info.st_mtime_ns > boundary, "mtime is not after the boundary; case 2 proves nothing")
        check("2c and really does leave ctime behind the boundary",
              info.st_ctime_ns <= boundary,
              "ctime moved; this filesystem cannot express the case and it proves nothing")

        output = root / "evidence.json"
        code, out = verify(results, receipt, output)
        check("2d a moved-in stale results tree is refused", code == 1, f"got {code}: {out[:300]}")
        check("2e the reason names ctime and calls the XML stale",
              "ctime" in out and "stale" in out, out[:300])
        check("2f and no evidence file is written for it", not output.exists())


def case_receipt_written_later_than_its_boundary() -> None:
    """A receipt is not trusted because it PARSES. Its own file timestamps must agree with it."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        genuine = root / "genuine.json"
        check("3a a genuine receipt is created first", start(results, genuine) == 0)
        payload = json.loads(genuine.read_text(encoding="utf-8"))

        # A receipt written NOW that claims a boundary from an hour ago: the nonce is well formed,
        # the format is right, the JSON parses. Only the filesystem timestamps disagree.
        payload["started_at_unix_ns"] = payload["started_at_unix_ns"] - 3600 * 1_000_000_000
        forged = root / "forged.json"
        forged.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        time.sleep(0.05)
        (results / "TEST-example.xml").write_text(SUITE_XML, encoding="utf-8")
        output = root / "evidence.json"
        code, out = verify(results, forged, output)
        check("3b a receipt whose file is newer than its claimed boundary is refused",
              code == 1, f"got {code}: {out[:300]}")
        check("3c the reason is the timestamp disagreement, not the XML",
              "filesystem timestamps" in out, out[:300])
        check("3d and no evidence file is written for it", not output.exists())
        check("3e the forged receipt is still consumed — a failed attempt is spent, not repairable",
              Path(str(forged) + ".consumed").is_file())


def case_output_inside_the_results_directory() -> None:
    """Evidence written into the results directory becomes pre-existing content for the next run."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        receipt = root / "start.json"
        check("4a a run start is created", start(results, receipt) == 0)
        time.sleep(0.05)
        (results / "TEST-example.xml").write_text(SUITE_XML, encoding="utf-8")

        inside = results / "evidence.json"
        code, out = verify(results, receipt, inside)
        check("4b --output inside the result directory is refused", code != 0, f"got {code}")
        check("4c it says the output must be outside", "outside" in out, out[:300])
        check("4d and the results directory is not polluted", not inside.exists())

        nested = results / "nested" / "evidence.json"
        nested.parent.mkdir()
        code, out = verify(results, receipt, nested)
        check("4e a NESTED path inside the result directory is refused too", code != 0,
              f"got {code}")
        check("4f the receipt was never consumed by a refused invocation",
              not Path(str(receipt) + ".consumed").exists(),
              "an argument error must not spend the receipt")


def main() -> int:
    for script in (VERIFY, START):
        if not script.exists():
            print(f"{script.name} not found at {script}", file=sys.stderr)
            return 2

    print("verify_junit break-test")
    for case in (case_fresh_run_passes, case_moved_stale_tree_with_future_mtime,
                 case_receipt_written_later_than_its_boundary,
                 case_output_inside_the_results_directory):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — every freshness gate this file claims to hold was watched holding it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
