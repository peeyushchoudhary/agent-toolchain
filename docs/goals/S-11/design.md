---
summary: A goal-local approval-frozen test migration declaration, exact-tree proof requirements and shared gate environment isolation.
read-when: Implementing or reviewing S-11's optional immutable-test migration and subprocess environment changes.
covers: []
last-verified: 2026-10-20
---
# S-11 design

## Structure

Add one optional artifact, `docs/goals/<id>/test-migrations.json`, and one small
authored helper, `scripts/migrations.py`. Goals without that artifact retain
D38's current behavior. The artifact is automatically protected, must exist at
approval, and supplies no operational authority or automatic test retirement.

Keep the module-map schema and selector unchanged. `goal.py` validates the
approved declaration, admits only its exact command substitution, checks frozen
sources throughout the goal and requires proof receipts at close. Existing
`gate.py` receipts supply the evidence. The common gate subprocess runner strips
four inherited pytest controls. There is no new executor, receipt type or registry
outside the goal.

## Interfaces

### 1. Optional declaration

The filename is fixed; no new plan frontmatter field or arbitrary manifest path.
Its closed JSON shape is:

```json
{
  "version": 1,
  "migrations": [{
    "module": "legacy",
    "before": "python3 -m unittest tests/test_old.py tests/test_keep.py",
    "after": "python3 -m unittest tests/test_keep.py tests/test_current.py",
    "originals": [{"path": "tests/test_old.py", "sha256": "<64 lowercase hex>"}],
    "successors": ["tests/test_current.py"],
    "historical_claim": "BYTES_ONLY",
    "reason": "The old host profile is unavailable; current behavior has a named successor."
  }]
}
```

Reject duplicate JSON keys, unknown fields, non-integer/wrong versions, empty
lists/strings, duplicate module/path entries, invalid hashes and noncanonical
relative paths. `historical_claim` must be exactly the string `BYTES_ONLY`;
every other value or type is invalid, including `REPLAYED`. Paths cannot contain parent/dot segments, backslashes, control
characters or shell expansion/operator characters. Original source objects must be
tracked regular Git blobs (`100644` or `100755`), never symlinks or untracked files.

This first protocol supports only literal Python test-file commands:

- Interpreter: `python3` or `./py`, unchanged between commands. These cover a
  standard Python entry point and a repository-owned Python wrapper; additional
  executable paths are outside version 1's bounded grammar.
- Prefix: `-m pytest -q`, or `-m unittest` with an optional `-q`.
- Remaining arguments: unique canonical relative `.py` files only. No discovery,
  filters, shell operators, variable expansion or additional options.

`before` must equal that module's command at approval. The module must be a test
module, not `count: none`. Every declared original must occur in `before` and
be absent from `after`. `after` must be exactly the same parsed prefix, followed
by the unchanged retained file sequence, followed by the declared successor
sequence. Successors are nonempty and new to the old command. Only this exact
substitution is permitted; count, module removal, needs and path/shared losses
still use the existing D38 checks. A changed `replaces` cannot accompany an exception.

The preservation command is generated from the approved original paths and
hashes, using the same interpreter with `-c` and a fixed standard-library-only
version-1 code template. Pass the original `(path, sha256)` pairs as canonical
JSON (`separators=(",", ":")`, declaration order), and construct all arguments
with `shlex.join`. The template checks actual regular file bytes and rejects
symlinked files/ancestors; missing/unreadable/mismatched files print
`preservation: FAIL` and exit 1, otherwise print `preservation: PASS` and exit 0.
It uses explicit conditions, never Python `assert` (which optimization can disable).
There is no project-specific checker source to create, approve or install.
The generated command is part of version 1's durable interface and is shown at
approval. Its arguments are `[interpreter, "-c", PRESERVE_V1, pairs_json]`, with
`PRESERVE_V1` exactly the following text including its final newline:

```python
import hashlib, json, pathlib, sys
bad = []
for path, digest in json.loads(sys.argv[1]):
    p = pathlib.Path(path)
    try:
        good = (p.is_file() and not any(q.is_symlink() for q in (p, *p.parents))
                and hashlib.sha256(p.read_bytes()).hexdigest() == digest)
    except OSError:
        good = False
    if not good:
        bad.append(path)
print('preservation: FAIL ' + ', '.join(bad) if bad else 'preservation: PASS')
sys.exit(1 if bad else 0)
```

The protocol claims byte preservation only; it cannot certify historical replay
or semantic equivalence. The founder/reviewer evaluates the reason and current
behavioral coverage.

### 2. Helper boundary

`migrations.py` is standard-library-only and does not import `goal` or `gate`.
Public functions:

- `parse(text, baseline_map, read) -> list[dict]`: validate the closed declaration,
  command delta and original identities. `read(path)` returns
  `(git_mode, bytes)` or `None` from the approved tree. Parsed records retain
  the baseline count and map `replaces` as derived internal values, never as
  additional artifact keys, so `allowed` can reject accompanying changes.
- `allowed(entries, current_map, read) -> set[str]`: verify frozen identities at
  HEAD and identify modules whose current command equals the exact declared
  replacement. A declared module may still have its original command before
  activation; any third command is invalid. Activated successor paths must be
  tracked regular blobs too.
- `proofs(entry) -> list[dict]`: deterministic required receipt descriptors
  (`kind`, `module`, `command`, `tests`). `kind` is `module`, `successor` or
  `preservation`; `module` is the module name for `kind: module` and `null`
  otherwise; `command` is the exact string; `tests` is a Boolean, true for
  module/successor and false for preservation. It means positive executed count
  is mandatory, never a test count or path list. Module key construction remains
  owned by `gate.module_key`.
- `proof_ok(descriptor, receipt, tree) -> bool`: enforce the exact-tree,
  exact-command, module and zero-failure proof requirements below.

The additive CLI `goal.py migration-proofs --goal <id>` executes nothing and
prints one JSON object: `{"version": 1, "migrations": [{"module": "legacy",
"applied": false, "proofs": [<descriptors above>]}]}`. Before approval it validates
the working declaration against the committed map/sources; after approval it
uses the frozen declaration and validates the current map/sources. It emits all
required descriptors even while unapplied, so a caller can deserialize and pass
the exact command bytes to `gate.py receipt`. Module descriptors use
`--modules <module>`; successor descriptors use `--cmd <exact command>`;
preservation descriptors require `--cmd <exact command> --count none` because
`tests: false` permits zero executed tests. The descriptor's command string is
unchanged by these gate flags. No declaration yields an empty
`migrations` list. Invalid metadata exits 1 with a diagnostic and no JSON object.
Approval HTML and normal packets show these same commands. This is an additional
read-only output on the existing goal CLI, not another runner.

Invalid input raises `MigrationError(ValueError)`; callers report it as a finding.
No malformed or unavailable declaration silently becomes an empty allowance.

### 3. Approval and completion

Before approval, lint validates the declaration against the current committed
map and tracked source objects. After approval, only the artifact at the approval
tag can authorize an exception. A newly added artifact, changed body or missing
approved source refuses. The artifact, original sources
are implicit protected paths; existing per-commit checks detect even a change
later restored. For each migrating module, map-edit commits must retain either
the approved original or the exact replacement command; a third command cannot
be restored into a valid exception. Approval rendering shows the declaration
and evidence limits. A local approval tag remains the existing trust root: this
adds no cryptographic identity or history-rewrite protection. If re-approval
moves to a map already using `after` but retains the old declaration, `before`
no longer equals the new baseline and lint/DONE refuse it. If a separately
Founder-approved new baseline omits that declaration, no exception or migration
proof is inherited: it is a new baseline under the existing approval trust model.
A chief/builder cannot use re-tagging or removing the artifact after approval to
close the original goal. Preventing a Founder-authorized baseline replacement is
outside this protocol; no hidden approval-history registry is introduced.

Implicit preservation lasts through this goal's protected history and close.
This protocol grants no permanent cross-goal retention policy; later goals need
their own protected paths or repository freeze policy. It never deletes originals
or authorizes their deletion, and the current module paths still retain them.

Keep `map_shrinks`' existing three-argument behavior. Its goal-aware caller may
exclude only an exact authorized `test` substitution from row 5; every other
finding stays. Structural admission does not require receipts at commit time:
code must be committed before exact-tree receipts can be produced. DONE row 7
adds the required proof checks for applied migrations:

1. A PASS module receipt for the exact replacement command and module.
2. A PASS command receipt for each successor file alone, using the same parsed
   Python prefix and `shlex.join` to construct the command deterministically.
3. A PASS command receipt for the exact generated preservation command.

All receipts bind the current tree and exact command. Test receipts require exit
0, positive executed count, zero failed/skipped and no baseline failures. The
preservation receipt allows zero tests but requires exit 0, zero failures and
no skipped tests or baseline failures. Numeric fields must have nonnegative integer counts and an integer exit code;
verdict must be PASS and reasons empty. Missing, stale, contradictory,
count-none test evidence or
another module's receipt cannot satisfy a requirement. Existing full/E2E receipts
and review remain mandatory. Packets show the required commands and proof gaps.
Version 1 is intentionally ineligible for a replacement module that still has
platform skips or baseline failures: leave that migration unapplied/parked rather
than waive the zero-skip, zero-baseline rule.

### 4. Subprocess environment

In `gate.run`, copy `os.environ` and remove only `PYTEST_ADDOPTS`,
`PYTEST_PLUGINS`, `PYTEST_XDIST_WORKER` and `PYTEST_XDIST_WORKER_COUNT` before
`Popen`. Both command and module modes already share this runner. Preserve
unrelated environment, command text, interpreter, receipt keys and count parsing.
An explicit assignment inside the approved command remains explicit command
behavior. This is not a general Python startup sandbox.

Tests use actual standard-library child processes and inspect the inherited
environment; no optional pytest dependency, new skip or fabricated library claim.

## Data touched

Authored helper, goal/gate scripts, their existing unittest files, module ownership
growth, E2E and current rules/documentation. Existing goals/receipts/declarations
and installed files are not migrated. No source deletion, new dependency, public
provider action or real-home installation occurs. Generic fixture metadata stays
inside disposable repositories. Rollback is a normal source revert; old tooling
continues to reject changed commands and never silently trusts this new artifact.

## Smallest change

Build the pure helper and environment fix independently. Integrate only after
both commits; grow the existing modmap module's paths to cover the new helper,
keeping every existing module command. Split structural admission from
DONE/presentation integration before the installed E2E. Append migration tests to `test_modmap.py`.
Use the current receipt model and extend the existing live-flow E2E. Rules and
README reconciliation are the last task. A new on-demand 400-word
`references/test-migrations.md` holds the protocol; existing modules/planning/
close references link to it inside their unchanged ceilings. SKILL.md's DONE
row 7 gains a same-word-count proof link, retaining the 1350-word loaded limit. Standard full validation and installed
round-trip tests retain their existing coverage.

## Rejected options

- Relax every command change: enables unrelated test loss.
- Put mutable declarations in Decisions or task fields: those can change after approval.
- Re-tag approval to hide a shrink: loses the reviewed baseline.
- Require proof before committing: receipts require a clean committed tree.
- Trust a full-gate PASS alone: it does not identify the named successor population.
- Add environment prefixes to maps: duplicates runner policy and changes receipt keys.
- Rewrite frozen tests or synthesize a historical environment: confuses preservation with replay.
- General shell/build-tool migration parser: unnecessary for the first narrow Python-file protocol.
