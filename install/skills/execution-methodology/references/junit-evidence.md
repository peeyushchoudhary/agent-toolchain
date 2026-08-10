# JUnit executed-test evidence

The nonce-receipt protocol that proves a Gradle/JUnit gate *ran*, fresh, and produced exactly the
declared tests. Moved verbatim from the methodology body in v3.0; the protocol and tooling are
unchanged from v1.5.

## The protocol

For JUnit, console output is not the count. Create a new start artifact immediately before the test
task:

```bash
python3 start_junit_run.py --results RESULT_DIR --output START.json
```

It contains a 256-bit nonce, timestamp, exact result path, and hashes of any direct XML already
present. Run the task with cache bypassed, then invoke:

```bash
python3 verify_junit.py --results RESULT_DIR --start-receipt START.json \
    --expect FQCN=N [--expect FQCN=N ...] --output RECEIPT.json
```

Every direct XML file must have both mtime and ctime strictly after the start boundary. The verifier
records the start hash and nonce and creates a consumption marker, so a valid pre-existing result or
a reused run receipt cannot certify a later invocation. Each expected class must have exactly its
declared testcase count — not merely a nonzero or aggregate minimum. JUnit failures, errors, and
skips all fail evidence verification. Cleaning remains good hygiene, but it is no longer the
freshness security boundary.

Exact `--rerun-tasks` is the sole Gradle freshness flag. `clean`, `cleanTest`, qualified clean
tasks, exclusions, properties, option operands, and every other token do not count.

## What this evidence does and does not detect

The shared JUnit result verifier binds the exact direct-XML directory to a single-use
nonce/timestamp start boundary, proves required classes and counts from XML, rejects ambiguous or
inconsistent results, and emits a new JSON receipt bound to that start artifact.

JUnit evidence detects accidental pre-existing, same-content, unchanged, malformed, replayed,
failed, errored, skipped, or count-inconsistent results. It does not detect a cache restore that
writes plausible valid XML after the boundary. Exact runner rerun settings prevent cache use;
Gradle requires exact `--rerun-tasks`. It is **not tamper-resistant** against a deliberate local
writer controlling both XML and evidence files; it is a freshness and consistency check inside that
trust boundary, not hostile-writer attestation.
