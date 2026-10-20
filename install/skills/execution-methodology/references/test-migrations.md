# Immutable-test migrations (D41)

Optional `docs/goals/<id>/test-migrations.json` has closed keys `version: 1`,
`migrations: [...]`; each entry has `module`, `before`, `after`, `originals`
(`path`, 64-hex lowercase `sha256`), `successors`, `historical_claim: "BYTES_ONLY"`,
`reason`. Lists/strings are nonempty; reject unknown/duplicate keys, wrong types,
duplicate modules/paths, malformed hashes and noncanonical paths. Originals are
tracked regular Git blobs (100644/100755), never symlinks.

Only literal `python3` or `./py` commands: `-m pytest -q`, or `-m unittest`
with optional `-q`, then unique relative `.py` files. No discovery, filters,
operators, expansion or extra options. Interpreter/prefix stay unchanged.
`before` equals the approved test-module command (never `count: none`); `after` keeps retained files in
order, then appends declared new successors, removing exactly the originals.
Successors become tracked regular files when applied.

Declare before approval against the committed map/sources. After approval only
the tag's declaration authorizes substitution; declaration/originals are implicitly
protected through every commit, including mutate/restore. A third command is
forbidden even if restored. Module/count/needs/path/shared losses and changed
`replaces` remain rejected. Unapplied declarations need no proofs.

Retrieve exact version-1 JSON descriptors without executing anything:
`goal.py migration-proofs --goal <id>`. No declaration yields an empty list;
invalid metadata fails. Descriptors carry `kind`, `module`, `command`, Boolean `tests`;
commands use `shlex.join`. For applied migrations, run through `gate.py receipt --goal <id>`:

- module: `--modules <module>`;
- each successor alone: `--cmd <exact command>`;
- generated preservation: `--cmd <exact command> --count none` (`tests: false`).

Preservation uses the approved interpreter and generated standard-library byte/hash
check (explicit conditions, never assertions), rejects missing/unreadable/changed/symlinked inputs, and allows zero tests.
Every receipt binds HEAD's tree and exact command/module: PASS, exit 0,
nonnegative integer counts, empty reasons, zero failed/skipped and no baseline
failures. Test proofs require positive executed counts. Missing, stale,
contradictory or count-none test evidence refuses DONE. Leave migrations with
skips/baseline failures unapplied/parked. Existing full/E2E receipts and review remain mandatory.

Preservation is goal-scoped through close; it authorizes no deletion or permanent
cross-goal retention. BYTES_ONLY proves neither historical replay nor semantic equivalence;
the founder/reviewer assesses successor coverage. A re-approval trusts the local
approval tag: keeping an old declaration against an already-replaced baseline
fails; a separately founder-approved baseline omitting it inherits no proofs.
No cryptographic identity/history-rewrite protection is added; chiefs/builders
cannot re-tag or remove the declaration to close the original goal.

Both gate modes remove inherited `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`,
`PYTEST_XDIST_WORKER`, `PYTEST_XDIST_WORKER_COUNT`; explicit command assignments,
interpreters and unrelated environment remain unchanged. This is no general startup sandbox.
