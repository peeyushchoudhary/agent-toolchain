# Read-only gate execution in Codex

How a read-only `test-judge` runs a write-producing gate without touching the source referent.
Moved verbatim from the methodology body in v3.0; the protocol is unchanged.

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
nested-sandbox failure, cached/zero/skipped execution, a required bypass, or failure to remove the
exact temporary root blocks sealing. The judge remains read-only; the standalone copy is the only
writable boundary. Plain nested execution cannot widen the outer sandbox, and plain unsandboxed gate
execution is forbidden. Exact `--rerun-tasks` is the sole Gradle freshness flag — `cleanTest` is
not.
