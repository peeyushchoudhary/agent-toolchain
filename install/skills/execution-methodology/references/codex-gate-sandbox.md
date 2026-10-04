# Read-only gate execution in Codex

How a read-only `test-judge` runs a write-producing gate without touching the source referent.
The isolated-copy protocol remains the route for source-writing gates.

Ordinary tests whose writes stay inside disposable temporary fixtures need no gate isolation;
run them under the judge's existing permissions with source cache/bytecode output disabled as
needed. This does not authorize a judge to write the source. Sandbox self-tests that cannot nest
under the read-only judge use the existing authorized controller host path and capture. The judge
independently verifies that capture's exact command, referent, unchanged-source result, counts,
failures, and limits; it does not run an unsandboxed source-writing gate or acquire write tools.

A write-producing gate is never run directly against the source referent by a read-only
`test-judge`. The controller freezes writers and selects a committed tree or `HEAD` plus a canonical
manifest covering path, type, mode, content/link hash, base SHA, tracked deletions, and non-ignored
untracked files. It materializes a manifest-equal standalone copy below a fresh temporary root,
without a source `.git` relationship, shared object store, hard links, ignored outputs, unresolved
external objects, or escaping symlinks.

After comparing the source and copy manifests, the controller supplies a custom inner permission
profile. Because the outer judge is read-only, it requests approval for the **exact sandbox-launch**
command only. The approved nested sandbox launch is:

```text
env CODEX_HOME=<temporary-home> codex sandbox -p gate -P copy-write -C <copy> -- <exact gate argv>
```

Approval moves only the launcher outside the outer boundary; the gate never runs unsandboxed. The
launcher immediately enters the inner profile, which grants source read, copy write, and network
disabled.

The evidence names the referent and manifest hash, sandbox and gate commands, exit code, verbatim
failures, counts/skips, and the unchanged-source recheck. Ambiguous identity, a manifest mismatch,
nested-sandbox failure, cached/zero/skipped execution, a required bypass, or failed cleanup of
owned runtime resources blocks sealing. Preserve original run-specific result directories while
trace receipts still need their absolute paths and timestamps. With `gate-sandbox`, use its existing
`--keep` for that retention; it skips automatic compose cleanup, so the controller must separately
remove and verify owned runtime resources before sealing. Record the retained root and trace
consumption; remove only that root after its evidence is no longer required. Never relocate XML
and infer receipt equivalence. Without declared evidence retention, failure to remove the exact
temporary root blocks sealing. The judge remains read-only; the standalone copy is the only
writable boundary. Plain nested execution cannot widen the outer sandbox, and plain unsandboxed gate
execution is forbidden. Exact `--rerun-tasks` is the sole Gradle freshness flag — `cleanTest` is
not.
