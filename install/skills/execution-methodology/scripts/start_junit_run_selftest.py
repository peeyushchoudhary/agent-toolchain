#!/usr/bin/env python3
"""Break-test for start_junit_run.py — proves the run-start receipt is actually single-use.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
found by mutating this file's sibling and watching the vendored suite stay green, so a regression
re-breaks a named case instead of silently un-guarding a receipt.

  1  a first receipt is created, and its shape is the shape verify_junit demands   exit 0
  2  a SECOND run against the same --output is refused, and the FIRST receipt's
     bytes are unchanged                                    <- overwriting resets the boundary
  3  two receipts written in one second carry DIFFERENT nonces
                                                            <- a constant nonce passes the shape
  4  an existing consumption marker is refused, and no receipt file is left behind
  5  a pre-existing XML file is snapshotted by NAME and SHA-256

WHAT MADE THESE CASES REAL, measured rather than imagined. Each line below is a mutation applied to
start_junit_run.py; each ran the skill's own `unittest discover` and each left it GREEN:
    `output.open("x")` -> `output.open("w")`                     green
    delete the `if output.exists(): parser.error(...)` precheck  green
    BOTH OF THE ABOVE AT ONCE                                    green — 2436 tests, OK
    `"nonce": secrets.token_hex(32)` -> `"nonce": "0" * 64`      green
    delete the `.consumed` precheck                              green
So the receipt could be silently overwritten, and the nonce could be a constant, and nothing in the
suite said a word. Overwriting the receipt rewrites `started_at_unix_ns`, which is the entire
staleness boundary verify_junit.py trusts — it is the replay the protocol says it forbids.

WHAT THIS DOES NOT COVER, stated plainly because an overstated coverage claim in a break-test is the
same failure one layer up. Every case drives the INSTALLED sibling as a process, through argv, in a
temporary directory. Nothing here imports it, so nothing here proves anything about a partially
edited module. Case 3 proves two nonces DIFFER; it is not a randomness test and cannot be one.
Nothing here writes inside the repository.

Run:  python3 start_junit_run_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "start_junit_run.py"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def case_first_receipt() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        receipt = root / "start.json"
        code, out = run("--results", str(results), "--output", str(receipt))
        check("1a a first receipt exits 0", code == 0, f"got {code}: {out[:200]}")
        check("1b the receipt file exists", receipt.is_file())
        if not receipt.is_file():
            return
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        check("1c it declares the format verify_junit.py requires",
              payload.get("format") == "execution-methodology-junit-start-v1",
              repr(payload.get("format")))
        check("1d the nonce is 32 random bytes as 64 lowercase hex digits",
              isinstance(payload.get("nonce"), str)
              and re.fullmatch(r"[0-9a-f]{64}", payload["nonce"]) is not None,
              repr(payload.get("nonce")))
        check("1e it binds the EXACT resolved result directory",
              payload.get("result_directory") == str(results.resolve()),
              repr(payload.get("result_directory")))
        check("1f started_at_unix_ns is a positive integer boundary",
              isinstance(payload.get("started_at_unix_ns"), int)
              and payload["started_at_unix_ns"] > 0,
              repr(payload.get("started_at_unix_ns")))


def case_second_run_cannot_overwrite() -> None:
    """The defect: `open("w")` plus a deleted precheck, and 2436 tests stayed green.

    Asserting "the second run is non-zero" ALONE is not enough — a script that overwrote the file
    and then errored would still pass that. The bytes on disk are compared before and after, so
    this case fails against any revision that writes first and complains second.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        receipt = root / "start.json"
        code, _ = run("--results", str(results), "--output", str(receipt))
        check("2a the first run succeeds so there is something to protect", code == 0, f"got {code}")
        before = receipt.read_bytes()

        code, out = run("--results", str(results), "--output", str(receipt))
        check("2b a second run against the same --output is refused", code != 0, f"got {code}")
        check("2c it says the receipt must be newly created",
              "already exists" in out, out[:200])
        after = receipt.read_bytes()
        check("2d the FIRST receipt's bytes are unchanged — no overwrite happened",
              after == before,
              "the receipt was rewritten; the staleness boundary moved")
        first = json.loads(before)
        second = json.loads(after)
        check("2e the run nonce did not move", first["nonce"] == second["nonce"])
        check("2f the staleness boundary did not move",
              first["started_at_unix_ns"] == second["started_at_unix_ns"])


def case_nonces_differ() -> None:
    """A constant nonce passes verify_junit's `[0-9a-f]{64}` shape check and every vendored test.

    Two receipts, written back to back into the same directory. `secrets.token_hex(32)` collides
    with probability 2**-256; a hardcoded or time-seeded nonce collides every time.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        nonces = []
        boundaries = []
        for index in range(3):
            receipt = root / f"start-{index}.json"
            code, out = run("--results", str(results), "--output", str(receipt))
            if code != 0:
                check(f"3a receipt {index} was created", False, f"got {code}: {out[:200]}")
                return
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            nonces.append(payload["nonce"])
            boundaries.append(payload["started_at_unix_ns"])
        check("3b three receipts written back to back carry three DISTINCT nonces",
              len(set(nonces)) == 3, f"{len(set(nonces))} distinct: {nonces}")
        check("3c no nonce is a constant filler value",
              all(set(n) != {"0"} for n in nonces), str(nonces))
        check("3d each receipt carries its own boundary, so they are not one receipt copied",
              len(set(boundaries)) == 3, str(boundaries))


def case_consumed_marker_refused() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        receipt = root / "start.json"
        Path(str(receipt) + ".consumed").write_text("{}\n", encoding="utf-8")
        code, out = run("--results", str(results), "--output", str(receipt))
        check("4a a path whose consumption marker exists is refused", code != 0, f"got {code}")
        check("4b it names the marker as the reason", "consum" in out.lower(), out[:200])
        check("4c and no receipt is left behind at that path", not receipt.exists(),
              "a receipt was created at a path that is already spent")


def case_preexisting_xml_snapshot() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "results"
        results.mkdir()
        stale = results / "TEST-old.xml"
        stale.write_bytes(b"<testsuite name='old' tests='0'/>\n")
        digest = hashlib.sha256(stale.read_bytes()).hexdigest()
        receipt = root / "start.json"
        code, out = run("--results", str(results), "--output", str(receipt))
        check("5a a directory with pre-existing XML still starts a run", code == 0,
              f"got {code}: {out[:200]}")
        if code != 0:
            return
        snapshot = json.loads(receipt.read_text(encoding="utf-8"))["preexisting_xml_sha256"]
        check("5b the pre-existing file is snapshotted by name", "TEST-old.xml" in snapshot,
              str(snapshot))
        check("5c and by content, so a replay of it is detectable",
              snapshot.get("TEST-old.xml") == digest, str(snapshot))


def main() -> int:
    if not SCRIPT.exists():
        print(f"start_junit_run.py not found at {SCRIPT}", file=sys.stderr)
        return 2

    print("start_junit_run break-test")
    for case in (case_first_receipt, case_second_run_cannot_overwrite, case_nonces_differ,
                 case_consumed_marker_refused, case_preexisting_xml_snapshot):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the run-start receipt is created once, is unique, and cannot be overwritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
