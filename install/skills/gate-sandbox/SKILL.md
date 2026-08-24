---
name: gate-sandbox
description: Use when a write-producing verification gate must run against a frozen referent without touching the source checkout — a milestone gate, a compose-backed e2e suite, any command a read-only judge cannot run directly. Ships a readiness phase that proves the machine is ready before an attempt is spent, and a launcher that runs the exact gate argv inside an enforced macOS profile against a manifest-equal standalone copy. Not for ordinary test runs; those need no isolation.
disable-model-invocation: true
---

# Running a write-producing gate without touching the referent

A gate that writes cannot run in the source checkout: the run would dirty the tree it is supposed to
be judging, and no receipt from it could name what was tested. The methodology's answer is a
**manifest-equal standalone copy** under an enforced profile. This skill is the executable form of
that answer.

It ships **machinery only**. Every project fact — which checkout, which branch, which gate command,
which ports, which images — arrives from configuration that lives outside this repository. There is
no project name, path, or referent anywhere in these scripts, and
[`tests/selftest.sh`](tests/selftest.sh) asserts it rather than trusting it.

## Two phases, and the order is the point

| | |
| --- | --- |
| [`scripts/readiness.sh`](scripts/readiness.sh) | **Preparation.** Is this machine able to run the gate at all? |
| [`scripts/gate.sh`](scripts/gate.sh) | **The attempt.** Runs the exact gate argv and persists a receipt. |

Readiness checks two classes, and the second was added only after its absence cost an attempt.
**Provisioning** — port free, image present, cache populated, offline install resolves — and
**runtime behaviours**: whether the profile permits what a real suite does once it is already
running. Every provisioning check passed on the run that then failed 1,142 times on an agent-attach
denial, because no provisioning fact models it. When adding a check, ask which class it is in; a
whole class can be missing while the section list looks complete.

Readiness exists because a gate attempt that dies on a busy port or a missing base image has cost
the full price of the attempt and returned nothing — no test counts, no verdict, nothing that can be
recorded. Those runs look like failures in a ledger and are not: they are provisioning blocks. So
`gate.sh` **refuses to start** unless readiness passes, and `--force` writes that fact into the
receipt rather than passing silently.

Both phases build their environment through the same four functions — `make_copy`, `provision_root`,
`write_profile`, `sandboxed`. Nothing constructs an environment inline. A readiness check that proves
something about a *different* environment than the gate runs in has proven nothing, and with two
separate scripts that drift costs nothing to introduce and everything to detect.

## What the profile enforces, and what it does not

Provable, and asserted in both directions by the selftest:

- the source checkout is **readable and not writable**
- writes land only under the run root and the shared cache root
- **host egress is denied**
- the container daemon is reachable over **one literal socket path**, not a subpath or a wildcard

Not enforced, and this matters more than the list above:

> The container daemon runs **outside** this sandbox. Image pulls, build steps, and container egress
> are constrained by nothing here. A receipt from this launcher may say *host network denied*. It
> may never say *the gate ran offline*.

Anyone who needs the second sentence has to earn it separately — digest-pinned base images, verified
offline dependency inputs, and a demonstrated daemon/builder egress control. Say what was enforced,
never what was hoped.

## Configuration

Three layers, each overriding the last: **derived** (what the machine works out for itself) →
**host file** (`$GATE_HOME/host.env`, per machine) → **project file** (per project). The split is
what lets a project move between machines; collapsing them into one file produces configuration that
cannot be moved.

`GATE_HOME` defaults to `~/.claude/gate`. The project file is found, in order: `--config <path>`,
then `$GATE_CONFIG`, then `$GATE_HOME/projects/<checkout-basename>.env` — so both scripts run with
no arguments from inside a configured project, and a launcher that needs arguments to be correct is
one that gets run incorrectly.

**Never write configuration into the installed skill directory.** `install.sh` stages a fresh copy
and replaces the skill wholesale on every run; anything added inside it is destroyed by the next
install. That is not hypothetical — it is the bug that deleted an entire test suite before
`PRESERVE_ACROSS_INSTALLS` existed.

### Project file schema

| Key | Required | Meaning |
| --- | --- | --- |
| `GATE_REPO` | yes | absolute path to the checkout |
| `GATE_ARGV` | yes | the **exact** gate command, one string; changing it changes the gate |
| `GATE_BRANCH` | no | refuse to run on any other branch |
| `GATE_REFERENT` | no | pin a commit; empty binds whatever `HEAD` is, and still rechecks it |
| `GATE_PORTS` | no | ports that must be free before an attempt |
| `GATE_IMAGES` | no | container images that must already be present locally |
| `GATE_LOCKFILES` | no | paths that must be byte-identical between source and copy |
| `GATE_CACHES` | no | bash array of cache **kinds** to import — never paths |
| `GATE_OFFLINE_STEPS` | no | bash array of `label\|seconds\|command` offline probes |
| `GATE_HOME_SEED` | no | host paths to copy into the sandbox `HOME` |
| `GATE_PROJECT_PREFIX` | no | compose project prefix; lowercase, `-`/`_` only |
| `GATE_EVIDENCE_ROOT` | no | where receipts are kept; defaults under `$GATE_HOME` |
| `GATE_MIN_HEAP_MB` | no | heap a JVM must be able to reserve **and touch**; unset skips the check |

### Host file schema

Everything here is derived when absent, so the file may be empty on an ordinary machine. Pinning a
value is how you stop derivation from silently choosing a different runtime later — and a gate whose
runtime changed without anyone noticing is not the same gate.

| Key | Meaning |
| --- | --- |
| `GATE_DOCKER_SOCKET` | the daemon socket, granted to the profile by literal path |
| `GATE_DOCKER_PLUGINS` | directory holding the compose/buildx CLI plugins |
| `GATE_JAVA_HOME` | JDK for JVM projects; `env -i` strips the inherited one |
| `GATE_RUN_ROOT` | where run roots and the shared cache clone live |
| `GATE_CACHE_PATH_<kind>` | host location of each cache kind |
| `GATE_JAVA_TOOL_OPTIONS` | JVM options inside the sandbox; defaults to `-Djava.net.preferIPv4Stack=true -Djdk.attach.allowAttachSelf=true`. Override and you own both — each fixes a distinct denial |
| `GATE_DARWIN_TEMP_DIR` | the per-user temp directory the JVM uses regardless of `TMPDIR`; derived, and only worth setting if derivation is wrong |
| `GATE_LANG` | locale inside the sandbox; defaults to `en_US.UTF-8` |
| `GATE_EXTRA_PATH` | extra `PATH` entries for a toolchain in an unusual place |

A project names cache **kinds** (`gradle`, `pnpm`, `uv`, `playwright`, `npm`, `cargo`, `go`,
`maven`); the host file owns where each one lives. That is the boundary that keeps a project file
portable.

### What a probe command can reference

Probe commands in `GATE_OFFLINE_STEPS` run inside the sandbox and can use anything the environment
carries, including:

| Variable | Meaning |
| --- | --- |
| `GATE_CACHE_DIR_<kind>` | the provisioned cache directory for that kind |

That exists for toolchains whose cache location is **not settable by environment at all** — pnpm is
the example below. Reference it in the probe and pass whatever flag the tool requires, rather than
hardcoding a path this skill already knows. Single-quote the array element so it reaches the sandbox
unexpanded; the config file is sourced by the launcher, where the variable is not set.

## Seven traps that cost real time

**The run root must be a physical path.** macOS matches *resolved* paths, and both natural homes for
a run root are symlinks — `/tmp` → `/private/tmp`, and `$TMPDIR`'s `/var` → `/private/var`. A
profile granting write to the logical path grants it to a path the kernel does not recognise, so
every write is denied while the profile reads as though it permits them. It presents as *the copy is
not writable*, which sends you to look at the copy.

**Never interpolate a probe into `sh -c`.** A probe carrying its own quotes produced a syntax error,
and every check depending on it then reported failure of **the subject** — "source is writable",
"daemon unreachable". That is the most expensive shape a test can fail in, because it accuses the
subject instead of itself. Scripts are written to a file and executed.

**A fresh `HOME` hides the Docker CLI plugins.** Compose and buildx live under `~/.docker/cli-plugins`,
so an isolated `HOME` makes them vanish — which reads as a broken daemon and is really a missing
lookup path. The runtime's own plugin directory is exposed through a throwaway config; the real
`~/.docker/config.json` carries registry auth and must never enter the sandbox.

**A JVM binds IPv4 loopback through a dual-stack socket.** The kernel therefore sees
`::ffff:127.0.0.1`, which no `(local ip "localhost:*")` filter matches — so every Gradle daemon
failed to start under a filtered rule, reporting *Unable to start the daemon process*, which sends
you to look at the daemon. Measured with a control: the JVM's bind to `127.0.0.1` was denied while
its bind to `::1` succeeded, and Python's bind to `127.0.0.1` succeeded. The difference is the
socket, not the address. `network-bind` and `network-inbound` must BOTH be unfiltered; each alone
still denies it, and `(local ip "*:*")` does not help. Outbound stays restricted.

**A JVM's temp directory is not `$TMPDIR`, and loading an agent into itself needs two grants.**
`java.io.tmpdir` comes from `confstr(_CS_DARWIN_USER_TEMP_DIR)`, so it keeps pointing at
`/var/folders/.../T` no matter what `TMPDIR` is set to — measured, not assumed. The agent-attach
handshake happens there: the target binds `<darwin-temp>/.java_pid<pid>` and the client writes
`.attach_pid<pid>`. Every inline mock maker does this on first use, so one denial becomes one
failure per mocked class, with an exception naming the mocking library — the whole search goes to
the test code. Three separate things are required, and each alone leaves the failure looking
untouched: `file-write*` **and** `network-outbound` on those paths (the client connecting to a unix
socket is an outbound operation, not a file one), plus `-Djdk.attach.allowAttachSelf=true`, since
the JVM's own refusal reports *Can not attach to current VM* and arrives first. The pattern must
**not** be anchored at the end: the socket is bound under a suffixed temporary name and renamed into
place, so `[0-9]+$` matches the final name and not the one created — which fails as *target process
doesn't respond within 10500ms*, i.e. as a hung JVM rather than a denied write.

**`$TMPDIR` is reaped, and it takes files while leaving directories.** The shared cache clone lives
there, so a day later the tree still has its shape and almost none of its contents — measured:
gradle held 594 of 117,347 files, pnpm held 2 of 123,756. The `.provisioned` marker survived, so
provisioning reported *shared caches reused* and every offline step then failed as though the
project were misconfigured: a wrapper trying to download, a missing tarball, a missing wheel. None
of it looked like a cache problem. A file census is recorded at clone time and checked on reuse;
`--refresh-caches` rebuilds. Trusting a marker over the thing it stands for is the same defect
whatever the marker is.

**A cache setting the tool ignores looks exactly like one it honours.** pnpm's store location is
settable by `--store-dir` and nothing else — not `PNPM_STORE_PATH`, not `npm_config_store_dir`, and
not a `store-dir=` line in `.npmrc`, `.config/pnpm/rc` or `.config/npm/npmrc`. All five were tried
and silently ignored. With a real HOME the default store is correct anyway, so the setting appears
to work everywhere except the fresh HOME this sandbox insists on. Asserting the path *exists* is
necessary and insufficient; `check_cache_agreement` asks the **tool** where its cache is.

## Verifying

```sh
tests/selftest.sh
```

Hermetic: it builds its own git repository and its own configuration, so it runs on any machine and
reads none of the operator's real config.

It is a **break-test** suite, and it has been mutation-tested. One finding is recorded in the profile
itself: deleting `(deny file-write*)` changes nothing, because `(deny default)` is what denies
writes. The behavioural checks could not tell which line they depended on, so the deny-default line
is now asserted structurally — the one line whose removal opens everything.
