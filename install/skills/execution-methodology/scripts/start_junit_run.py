#!/usr/bin/env python3
"""Create a single-use run-start receipt before launching a JUnit test task."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


FORMAT = "execution-methodology-junit-start-v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True,
                        help="exact directory the test task will populate with direct XML files")
    parser.add_argument("--output", required=True, help="new JSON start receipt")
    args = parser.parse_args()
    results = Path(args.results).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    consumed = Path(str(output) + ".consumed")
    if output.exists():
        parser.error(f"--output already exists; a run start must be newly created: {output}")
    if consumed.exists():
        parser.error(f"consumption marker already exists; choose a new receipt path: {consumed}")
    if not output.parent.is_dir():
        parser.error(f"--output parent does not exist: {output.parent}")

    existing_xml = {}
    if results.exists() and not results.is_dir():
        parser.error(f"result directory path exists but is not a directory: {results}")
    if results.is_dir():
        for path in sorted(results.glob("*.xml")):
            existing_xml[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    started_ns = time.time_ns()
    payload = {
        "format": FORMAT,
        "nonce": secrets.token_hex(32),
        "result_directory": str(results),
        "preexisting_xml_sha256": existing_xml,
        "started_at_unix_ns": started_ns,
        "started_at_utc": datetime.fromtimestamp(
            started_ns / 1_000_000_000, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
    }
    try:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        parser.error(f"--output was created concurrently; refusing to overwrite: {output}")
    except OSError as exc:
        print(f"ERROR: cannot create {output}: {exc}", file=sys.stderr)
        return 2
    print(f"START: {output} nonce={payload['nonce']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
