#!/usr/bin/env python3
"""Verify fresh JUnit XML results and write machine-readable, tree-local evidence.

The caller creates a new single-use start receipt immediately before the test task with
`start_junit_run.py`. This verifier requires every direct XML file's mtime and ctime to be strictly
after that receipt's boundary and records its SHA-256 and nonce. Every verification attempt consumes
the receipt atomically before XML inspection, whether the attempt passes or fails. Passing a
module, build, or repository root cannot discover stale nested results. The output must be new and
outside the results directory.

This detects accidental stale, unchanged, malformed, replayed, failed, errored, skipped, and
count-inconsistent results. It is not tamper-resistant against a deliberate local writer that
controls both the XML and evidence files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from start_junit_run import FORMAT as START_FORMAT


class VerificationError(Exception):
    pass


def integer_attr(suite: ET.Element, name: str, source: Path) -> int:
    raw = suite.get(name)
    if raw is None:
        raise VerificationError(f"{source.name}: testsuite {suite.get('name')!r} lacks {name!r}")
    try:
        value = int(raw)
    except ValueError as exc:
        raise VerificationError(
            f"{source.name}: testsuite {suite.get('name')!r} has non-integer {name}={raw!r}"
        ) from exc
    if value < 0:
        raise VerificationError(f"{source.name}: {name} cannot be negative")
    return value


def leaf_suites(root: ET.Element, source: Path) -> list[ET.Element]:
    if root.tag == "testsuite":
        return [root]
    if root.tag == "testsuites":
        suites = list(root.findall("./testsuite"))
        if suites:
            return suites
    raise VerificationError(
        f"{source.name}: root must be testsuite or testsuites with direct testsuite children"
    )


def load_start_receipt(path: Path) -> tuple[dict[str, object], str]:
    if not path.is_file():
        raise VerificationError(f"start receipt does not exist: {path}")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"start receipt is unparseable: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != START_FORMAT:
        raise VerificationError(f"start receipt has the wrong format: {path}")
    nonce = payload.get("nonce")
    started = payload.get("started_at_unix_ns")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise VerificationError("start receipt nonce must be 32 random bytes encoded as hex")
    if not isinstance(started, int) or started <= 0:
        raise VerificationError("start receipt started_at_unix_ns must be a positive integer")
    stat = path.stat()
    # A copied old receipt can retain mtime, but not ctime. Both filesystem timestamps must sit
    # immediately after the claimed creation boundary. Five seconds permits slow filesystems while
    # refusing a receipt recreated later to make an old nonce look new.
    maximum = started + 5_000_000_000
    if not (started <= stat.st_mtime_ns <= maximum and started <= stat.st_ctime_ns <= maximum):
        raise VerificationError(
            "start receipt filesystem timestamps do not match its claimed creation boundary"
        )
    return payload, hashlib.sha256(raw).hexdigest()


def verify(results: Path, expected: dict[str, int],
           start: dict[str, object]) -> dict[str, object]:
    if start.get("result_directory") != str(results):
        raise VerificationError(
            "result directory does not match the exact directory bound into the start receipt"
        )
    preexisting = start.get("preexisting_xml_sha256")
    if not isinstance(preexisting, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in preexisting.items()):
        raise VerificationError("start receipt has an invalid preexisting XML snapshot")
    if not results.is_dir():
        raise VerificationError(f"result directory does not exist: {results}")
    files = sorted(results.glob("*.xml"))
    if not files:
        raise VerificationError(f"no XML result files directly inside {results}")

    identities: dict[str, str] = {}
    classes: set[str] = set()
    class_counts: Counter[str] = Counter()
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in files:
        stat = path.stat()
        boundary = int(start["started_at_unix_ns"])
        if stat.st_size == 0:
            raise VerificationError(f"zero-byte XML result file: {path.name}")
        current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if current_hash in preexisting.values():
            raise VerificationError(
                f"{path.name}: content is identical to XML present before run start"
            )
        if stat.st_mtime_ns <= boundary:
            raise VerificationError(
                f"{path.name}: mtime is not after run start; pre-existing/same-time XML is stale"
            )
        if stat.st_ctime_ns <= boundary:
            raise VerificationError(
                f"{path.name}: ctime predates the run start; pre-existing valid XML is stale"
            )
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as exc:
            raise VerificationError(f"unparseable XML result file {path.name}: {exc}") from exc
        file_totals = {name: 0 for name in totals}
        for suite in leaf_suites(root, path):
            identity = (suite.get("name") or "").strip()
            if not identity:
                raise VerificationError(f"{path.name}: testsuite has no identity/name")
            if identity in identities:
                raise VerificationError(
                    f"duplicate suite identity {identity!r} in {identities[identity]} and {path.name}"
                )
            identities[identity] = path.name

            cases = list(suite.findall("./testcase"))
            observed = {
                "tests": len(cases),
                "failures": sum(1 for case in cases if case.find("./failure") is not None),
                "errors": sum(1 for case in cases if case.find("./error") is not None),
                "skipped": sum(1 for case in cases if case.find("./skipped") is not None),
            }
            declared = {name: integer_attr(suite, name, path) for name in totals}
            if declared != observed:
                raise VerificationError(
                    f"{path.name}: count inconsistency for suite {identity!r}: "
                    f"declared {declared}, observed {observed}"
                )
            for name in totals:
                file_totals[name] += declared[name]
            for case in cases:
                fqcn = (case.get("classname") or "").strip()
                if not fqcn:
                    raise VerificationError(
                        f"{path.name}: testcase {case.get('name')!r} has no classname"
                    )
                classes.add(fqcn)
                class_counts[fqcn] += 1
        if root.tag == "testsuites" and any(root.get(name) is not None for name in totals):
            aggregate = {name: integer_attr(root, name, path) for name in totals}
            if aggregate != file_totals:
                raise VerificationError(
                    f"{path.name}: aggregate count inconsistency: declared {aggregate}, "
                    f"observed {file_totals}"
                )
        for name in totals:
            totals[name] += file_totals[name]

    if totals["tests"] == 0:
        raise VerificationError("zero tests were recorded")
    if totals["skipped"]:
        raise VerificationError(
            f"JUnit results contain skipped tests: skipped={totals['skipped']}"
        )
    if totals["failures"] or totals["errors"]:
        raise VerificationError(
            f"JUnit results are not green: failures={totals['failures']}, errors={totals['errors']}"
        )
    for fqcn, count in expected.items():
        observed = class_counts[fqcn]
        if observed != count:
            raise VerificationError(
                f"expected class {fqcn} expected exactly {count} testcase(s), observed {observed}"
            )

    return {
        "result_directory": str(results),
        "result_file_count": len(files),
        "distinct_classes": sorted(classes),
        **totals,
        "expected_class_counts": dict(sorted(expected.items())),
        "observed_class_counts": dict(sorted(class_counts.items())),
        "verified_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True,
                        help="exact directory containing this run's direct XML files")
    parser.add_argument("--expect", action="append", required=True, metavar="FQCN=N",
                        help="exact testcase classname count; repeat for more than one class")
    parser.add_argument("--start-receipt", required=True,
                        help="new single-use receipt created immediately before the test task")
    parser.add_argument("--output", required=True, help="new JSON evidence file outside results")
    args = parser.parse_args()

    results = Path(args.results).expanduser().resolve()
    start_receipt = Path(args.start_receipt).expanduser().resolve()
    consumed = Path(str(start_receipt) + ".consumed")
    output = Path(args.output).expanduser().resolve()
    expected: dict[str, int] = {}
    for value in args.expect:
        fqcn, separator, raw_count = value.rpartition("=")
        if (not separator
                or not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+", fqcn)
                or not raw_count.isdigit()):
            parser.error(f"--expect must be FQCN=N with a positive integer, got {value!r}")
        count = int(raw_count)
        if count < 1:
            parser.error(f"--expect count must be positive, got {value!r}")
        if fqcn in expected:
            parser.error(f"duplicate --expect class is not permitted: {fqcn}")
        expected[fqcn] = count
    if output.exists():
        parser.error(f"--output already exists; delete stale evidence first: {output}")
    if consumed.exists():
        parser.error(f"--start-receipt was already consumed: {consumed}")
    if output == results or results in output.parents:
        parser.error("--output must be outside the result directory")
    if start_receipt == results or results in start_receipt.parents:
        parser.error("--start-receipt must be outside the result directory")
    if output in (start_receipt, consumed):
        parser.error("--output must be distinct from the start receipt and consumption marker")
    if not output.parent.is_dir():
        parser.error(f"--output parent does not exist: {output.parent}")

    # Consumption is the first state change of a verification attempt. It is exclusive and happens
    # before reading XML, so a failed attempt cannot be repaired and replayed under the same nonce.
    try:
        with consumed.open("x", encoding="utf-8") as stream:
            json.dump({
                "attempted_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "output": str(output),
                "start_receipt": str(start_receipt),
            }, stream, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        parser.error(f"--start-receipt was already consumed: {consumed}")
    except OSError as exc:
        print(f"ERROR: cannot consume start receipt {start_receipt}: {exc}", file=sys.stderr)
        return 2

    try:
        start, start_hash = load_start_receipt(start_receipt)
        payload = verify(results, expected, start)
    except (VerificationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload.update({
        "start_receipt": str(start_receipt),
        "start_receipt_sha256": start_hash,
        "run_nonce": start["nonce"],
        "started_at_utc": start["started_at_utc"],
        "started_at_unix_ns": start["started_at_unix_ns"],
    })
    try:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError as exc:
        print(f"ERROR: cannot write {output}: {exc}", file=sys.stderr)
        return 2
    print(f"PASS: verified {payload['tests']} tests from {payload['result_file_count']} XML file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
