#!/usr/bin/env python3
"""pre-push guard: the three mistakes that a push makes permanent.

Everything else in this toolkit is recoverable — a bad commit is amended, a broken route is fixed
on the next commit. A push is different: it hands the content to a server that keeps it, and for
the three cases below the damage survives any later cleanup of the local branch.

  BLOCK  a credential in the pushed diff   — rotating a leaked key is the only real fix
  BLOCK  a file over the size limit        — git history keeps it forever; the clone never shrinks
  BLOCK  a direct push to the default branch — milestone work lands through a PR, not sideways
  warn   a newly added .env-style file     — sometimes deliberate, so it asks rather than stops
  warn   source changed, README untouched  — the front-page question, asked while it is cheap

Reads the standard pre-push payload on stdin: `<local ref> <local oid> <remote ref> <remote oid>`.

For an intentional main push, use `PD_ALLOW_MAIN_PUSH=1 git push`. Secret and size findings must
be fixed before pushing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Module-scope code runs before `main` is even defined, so nothing here is covered by main()'s
# handler chain and the invariant below it — "a crash must not be able to impersonate a finding, nor
# a finding a crash" — does not reach any of it. Three sites are outside that chain: the
# `Path(__file__).resolve()` above (OSError on an unreadable cwd), the two `re.compile` calls below,
# and this import. The first two are literals in THIS file: breaking them breaks `--help` and the
# break-test on the next run, and no edit to another file can reach them.
#
# This import is the one that is reachable by editing a DIFFERENT file, which is why it is the one
# wrapped. A syntax error, a bad regex literal, a rename, or a half-finished install of
# validate_disclosure.py all raise here. Uncaught, that produced a traceback and the interpreter's
# exit 1 — the code reserved for "a credential was found" — which the composed hook turns into a
# blocked push with no `pre-push BLOCKED` framing and nothing the founder can act on.
#
# It fails closed, so that half is not a hole; the defect is the unactionable message and the wrong
# exit code. Broad `except Exception` on purpose: the failure modes here are not confined to
# ImportError (SyntaxError and re.error are the likely ones), and every one of them means the same
# thing — the check cannot run.
#
# The probe is the half that does NOT fail closed on its own. `SECRET_PATTERNS = ()` imports
# perfectly: the scan loop in `secrets()` iterates zero times, `secrets()` returns [], and the guard
# exits 0 with no output having matched nothing against everything — the same signature as a clean
# push. Nothing else in this file or that one validates the set's shape, and an empty tuple is what
# a bad merge, a truncated write, or a refactor that moves the constant leaves behind. So: assert
# the set actually matches a known-good synthetic key before trusting it. The literal is split for
# the same reason validate_disclosure.py splits its own — unsplit, this file trips the guard it is,
# and the only way past is the --no-verify habit the guard exists to prevent.
try:
    from validate_disclosure import SECRET_PATTERNS  # noqa: E402
    _PROBE = "AKIA" + "IOSFODNN7EXAMPLE"
    if not any(re.search(_pat, _PROBE) for _, _pat in SECRET_PATTERNS):
        raise ValueError(f"SECRET_PATTERNS holds {len(SECRET_PATTERNS)} entr"
                         f"{'y' if len(SECRET_PATTERNS) == 1 else 'ies'} and none of them matches a "
                         f"known-good synthetic AWS key — the pattern set is empty or broken, so "
                         f"the scan would match nothing against everything")
except Exception as _exc:                                                   # noqa: BLE001
    traceback.print_exc()
    print(f"\n  pre-push BLOCKED: the guard could not load a WORKING set of secret patterns from "
          f"validate_disclosure.py ({type(_exc).__name__}: {_exc}).\n"
          f"\n  This is not a clean result — the check did not run. Repair or reinstall "
          f"validate_disclosure.py, then push again.\n  Do not push past it.\n", file=sys.stderr)
    raise SystemExit(2) from _exc

DEFAULT_BRANCHES = ("refs/heads/main", "refs/heads/master")

# Not configurable, deliberately. A limit chosen at the call site is a limit that will eventually be
# chosen at its weakest — this was `float(os.environ.get("PD_MAX_FILE_MB", "10"))`, which also
# raised ValueError at import time on any non-numeric value, crashing the guard instead of
# reporting.
MAX_FILE_MB = 10.0

ENV_FILE = re.compile(r"(^|/)\.env(\.|$)")
ENV_ALLOWED = re.compile(r"\.env\.(example|sample|template|defaults)$")

# The only spellings that open the escape hatch. An allow-list rather than a deny-list of "0",
# "false", "no", "off" and "": a deny-list has to anticipate every way a human might write "no", and
# the one it forgets fails OPEN. This way the unanticipated value blocks, which is the harmless
# direction to be wrong in.
AFFIRMATIVE = frozenset({"1", "true", "yes", "on"})


def env_allows(name: str) -> bool:
    """Does this environment variable hold an AFFIRMATIVE value?

    Presence is not consent. This was `not os.environ.get("PD_ALLOW_MAIN_PUSH")`, which tests
    whether the variable is set to any non-empty string — so `PD_ALLOW_MAIN_PUSH=0` and
    `PD_ALLOW_MAIN_PUSH=false` both OPENED the escape hatch. That is not merely a loose test; it is
    an inversion. A founder who writes `=0` is being explicit that they do NOT want the escape, and
    the guard handed them exactly the bypass they were refusing — silently, with exit 0, on the one
    push a direct-to-main block exists to stop.

    Unrecognised values fail closed. `PD_ALLOW_MAIN_PUSH=maybe` is a typo or a misunderstanding, and
    the safe reading of an instruction nobody can parse is "do not disable the safety check". The
    cost of failing closed is a push that blocks and a founder who re-reads the message; the cost of
    failing open is an unreviewed commit on main that a PR would have caught.
    """
    return os.environ.get(name, "").strip().lower() in AFFIRMATIVE


class GuardError(RuntimeError):
    """A check could not complete.

    Never downgrade this to a clean result. The entire failure class this guard exists to prevent is
    a check that silently did not run being reported as a check that passed.
    """


def _decode(raw: bytes) -> str:
    """Decode git output so that undecodable bytes cannot hide a scan.

    git classifies a file as text on the absence of NUL in its first 8000 bytes, so `log -p` readily
    emits latin-1 or Shift-JIS source bytes that are not valid UTF-8. Under `text=True` that raised
    `UnicodeDecodeError` out of `subprocess.run` — a traceback and exit 1, the code reserved for a
    finding. A mangled character cannot conceal a credential; an undecodable diff concealed the
    entire scan. So: replace, never raise.
    """
    return raw.decode("utf-8", errors="replace")


def is_null_oid(oid: str) -> bool:
    """git's "this ref does not exist" sentinel: an all-zero object id.

    Length-agnostic on purpose. This was `ZERO = "0" * 40` compared with `==`, which is correct only
    for SHA-1. In a repository created with `--object-format=sha256` the null oid is 64 zeros, so
    every one of those comparisons was False for a brand-new branch: the guard read the null oid as
    a real remote tip, `object_exists("0" * 64)` answered False, and the FIRST PUSH OF EVERY BRANCH
    was hard-blocked with a message telling the founder to run `git fetch` — which cannot clear it,
    because there is nothing on the remote to fetch. A block whose stated remedy does not clear it
    is exactly how `--no-verify` becomes a reflex. Deletion detection broke the same way.
    """
    return not oid.strip("0")


def git(*args: str, timeout: int = 60, tolerate_failure: bool = False) -> str:
    """Run git. Any failure voids the check unless the caller explicitly opted out.

    `tolerate_failure=True` means "a non-zero exit is itself the answer I am asking for", and
    exactly one call site is entitled to it: `rev-parse <root>^` on a repository's first commit,
    where failure means "no parent". It defaults to False and must stay that way.

    This parameter used to be the *default*: `CalledProcessError` returned "" unconditionally,
    justified by that one call site and applied to all six. The other five read the empty string as
    a clean result — including the size gate and the secret scan. A `git push --force` after a
    rebase hands the hook a remote oid the local object store lacks, `rev-list` and `log -p` both
    exit 128, and the guard reported a clean push having scanned nothing. Do not re-invert this.
    """
    try:
        return _decode(subprocess.run(["git", *args], capture_output=True,
                                      timeout=timeout, check=True).stdout)
    except subprocess.CalledProcessError as exc:
        if tolerate_failure:
            return ""
        detail = _decode(exc.stderr or b"").strip().splitlines()
        raise GuardError(f"`git {' '.join(args)}` failed (exit {exc.returncode})"
                         f"{': ' + detail[0] if detail else ''} — the scan did not run") from exc
    except subprocess.TimeoutExpired as exc:
        raise GuardError(f"`git {' '.join(args[:2])}` timed out after {timeout}s — "
                         f"the scan did not run") from exc
    except FileNotFoundError as exc:
        raise GuardError("git is not on PATH — the guard cannot verify anything") from exc
    except OSError as exc:
        # Broader than FileNotFoundError on purpose: PermissionError (git present, not executable),
        # ENOMEM on fork, EMFILE. All of them mean the check did not execute.
        raise GuardError(f"`git {' '.join(args[:2])}` could not execute: {exc}") from exc
    except subprocess.SubprocessError as exc:
        raise GuardError(f"`git {' '.join(args[:2])}` could not execute: {exc}") from exc


def object_exists(oid: str) -> bool:
    """Is this oid a commit in the LOCAL object store?

    Deliberately not `git(..., tolerate_failure=True)`. This is a boolean probe whose false answer
    is carried by an exit status, not a caller turning a failure into an empty string — the shape
    that produced the fail-open above. Only the environment failures raise.

    "Absent" and "could not be determined" are DIFFERENT answers. `return proc.returncode == 0`
    collapsed them: exit 1 means "no such object", but exit 128 means the question could not be
    asked at all — a corrupt loose object, an unreadable `.git/objects`, a promisor fetch that
    failed. Both fail closed, so this was never a hole. It was worse in a subtler way: the caller's
    message says "Run `git fetch` and push again", and no `git fetch` repairs an object store. A
    block whose stated remedy leaves it in place is the one situation that genuinely argues for
    `--no-verify`, which is the habit this guard exists to prevent.

    The probe is `-e <oid>`, NOT `-e <oid>^{commit}`. Measured, because the exit codes are not what
    they look like: the `^{commit}` peel is resolved by rev-parse, which reports an ABSENT object as
    exit 128 "Not a valid object name" — indistinguishable from an unreadable store, and the reason
    the first attempt at this split told a user with a merely-unfetched remote tip that their object
    store was corrupt. Bare `-e` is the honest probe: 0 present, 1 absent, >1 could not determine.

    What bare `-e` gives up is the type check, and it gives up nothing that matters. A corrupt
    LOOSE object answers 0 here (`-e` proves presence, not readability), so this returns True and
    the range is attempted — whereupon `rev-list` exits 128 and `git()` raises, naming the command
    that failed. Still exit 2, still an accurate message, one step later.
    """
    try:
        proc = subprocess.run(["git", "cat-file", "-e", oid],
                              capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GuardError(f"`git cat-file -e {oid}` timed out — the scan did not run") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise GuardError(f"`git cat-file -e {oid}` could not execute: {exc}") from exc
    if proc.returncode > 1:
        detail = _decode(proc.stderr or b"").strip().splitlines()
        raise GuardError(
            f"`git cat-file -e {oid[:12]}` exited {proc.returncode}: this repository's object "
            f"store could not be READ, so nothing can be scanned"
            f"{' — git said: ' + detail[0] if detail else ''}. This is not a missing object and "
            f"`git fetch` will not fix it — check the permissions on .git/objects, then `git fsck`")
    return proc.returncode == 0


def base_for(local: str, remote: str) -> str | None:
    """What this push actually adds. None means 'no sane base' — scan nothing rather than everything.

    For an existing remote branch the base is obvious. For a brand-new branch, anything already on
    another remote-tracking ref is by definition already pushed, so `--not --remotes` is the range
    that isolates the new work; falling back to full history would re-flag the whole repository.
    """
    if not is_null_oid(remote):
        # `git push` runs ls-remote first and hands the hook the remote's ACTUAL current oid, which
        # need not exist locally — a force-push after a rebase, or a branch a second machine has
        # advanced. Using it unchecked as a range endpoint made every later `rev-list`/`log -p` exit
        # 128, which the old carve-out turned into "no findings". An unscannable range is not a
        # clean one.
        if not object_exists(remote):
            raise GuardError(
                f"the remote is at {remote[:12]}, which is not in this repository's object store, "
                f"so the pushed range cannot be computed and nothing can be scanned. "
                f"Run `git fetch` and push again")
        return remote
    new_commits = git("rev-list", "--reverse", local, "--not", "--remotes").split()
    if not new_commits:
        return None
    # The root commit of a brand-new repository has no parent; there is nothing to diff against.
    # The only `git()` call permitted to tolerate a non-zero exit: "no parent" is the answer,
    # delivered as exit 128. (`object_exists` above also reads a non-zero exit as data, but it is
    # not a `git()` call and it does not turn a failure into an empty string.)
    return git("rev-parse", f"{new_commits[0]}^", tolerate_failure=True).strip() or None


def changed_files(base: str | None, local: str) -> list[str]:
    if not base:
        return []
    return [f for f in git("diff", "--name-only", "--diff-filter=d", base, local).splitlines()
            if f.strip()]


def added_files(base: str | None, local: str) -> list[str]:
    if not base:
        return []
    return [f for f in git("diff", "--name-only", "--diff-filter=A", base, local).splitlines()
            if f.strip()]


def oversized(base: str | None, local: str) -> list[tuple[str, float]]:
    """Blobs introduced by this push that exceed the limit, by real object size."""
    rng = [f"{base}..{local}"] if base else [local, "--not", "--remotes"]
    # `rev-list --objects` emits "<sha>" for commits and "<sha> <path>" for trees and blobs — and
    # the root tree of each commit comes through as "<sha> " with an empty path, which a naive
    # two-way unpack chokes on.
    entries: dict[str, str] = {}
    for ln in git("rev-list", "--objects", *rng).splitlines():
        sha, _, path = ln.partition(" ")
        if sha and path.strip():
            entries[sha] = path
    if not entries:
        return []
    query = ("\n".join(entries) + "\n").encode("utf-8")
    try:
        out = _decode(subprocess.run(
            ["git", "cat-file", "--batch-check=%(objecttype) %(objectsize) %(objectname)"],
            input=query, capture_output=True, timeout=300, check=True).stdout)
    except subprocess.TimeoutExpired as exc:
        raise GuardError("`git cat-file` timed out — the size check did not run") from exc
    except (subprocess.SubprocessError, OSError) as exc:
        # Unlike `git()`, there is no question here that git answers legitimately with failure:
        # every object in `entries` came from `rev-list` moments ago. A failure voids the check.
        raise GuardError(f"`git cat-file` could not run: {exc}") from exc
    limit = MAX_FILE_MB * 1024 * 1024
    big: list[tuple[str, float]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[0] != "blob":
            continue
        size = int(parts[1])
        if size > limit:
            big.append((entries.get(parts[2], parts[2]), size / 1024 / 1024))
    return sorted(set(big), key=lambda t: -t[1])


def secrets(base: str | None, local: str) -> list[tuple[str, str, str]]:
    """(file, pattern name, redacted line) for added lines only.

    Scans every commit in the range, not the net diff. A secret added in one commit and removed in
    the next still ships to the server inside the pushed objects and stays recoverable there, but a
    `git diff base..local` cancels the two out and reports nothing. Verified: the net-diff version
    of this function missed exactly that case.

    Added lines only: a secret already on the remote is history, and re-flagging it on every later
    push would train the founder to pass --no-verify by reflex.

    There is no size cap. There used to be one — above 40 MB this printed "skipping the content
    scan" and returned no findings, and a 143 MB push reached a remote entirely unscanned. The
    stated rationale was that scanning costs more than it catches, but the expensive half is
    `git log -p`, which has already run by the time the size is known: the cap paid the full cost
    and then discarded the result. Scanning a large string in Python is the cheap part.
    """
    rng = [f"{base}..{local}"] if base else [local, "--not", "--remotes"]
    # `--text` is load-bearing, not a tidy-up. Without it, `log -p` emits `Binary files a/x and b/x
    # differ` and NO `+` lines at all for any path git classifies as binary — so this function sees
    # nothing to match, `oversized()` finds nothing under the limit, and `run()` returns 0. A clean
    # exit, no output, credential on the remote.
    #
    # What makes that severe is WHERE the switch lives: the repository being scanned owns it. Two
    # triggers, both of which arrive with a clone — a NUL byte in the first 8000 bytes (git's own
    # text heuristic), or a `.gitattributes` entry unsetting the `diff` attribute. `printf '* -diff'
    # > .gitattributes` disables the only credential control on the machine, from inside the thing
    # being pushed, with nothing in the output distinguishing it from a clean scan. It does not need
    # malice either: a repo that legitimately marks a data directory `-diff` silently loses secret
    # scanning for those paths forever.
    #
    # Verified, because the attribute could plausibly have outranked the flag: with `* -diff`
    # committed, `grep -c '^+.*AKIA'` over this command returns 0 without `--text` and 1 with it.
    #
    # This is the same trade `_decode` already settled one layer out, and the argument transfers
    # verbatim: a mangled character cannot conceal a credential, but an unreadable diff concealed the
    # entire scan. The cost is that a genuinely binary blob now arrives for the matcher to walk —
    # which is the cheap half, exactly as the size-cap removal above found.
    #
    # `--text` ADMITS that content; the `split("\n")` below is what makes the matcher actually see
    # it, and the two are one fix. See the comment on the loop — do not remove either half believing
    # the other covers it.
    #
    # `--no-textconv` and `--no-ext-diff` are belt-and-braces on the same in-repository threat, and
    # they are free. A `textconv` or `diff` driver makes `git log -p` show the CONVERTER'S output
    # instead of the blob, and `--text` does not gate that — a driver that emits nothing produces a
    # diff with no `+` lines for exactly the paths it is configured for. The half of that setup that
    # names the driver lives in `.gitattributes` and travels with a clone; the half that defines what
    # the driver runs lives in git config and does NOT, so this is capped at a repository the founder
    # has already configured locally rather than a bare clone. Capped, not zero, and the flags cost
    # nothing — they also document that this call wants the stored bytes and nothing else.
    diff = git("log", "-p", "--text", "--no-textconv", "--no-ext-diff",
               "--unified=0", "--no-merges", "--format=%H", *rng, timeout=300)

    hits: list[tuple[str, str, str]] = []
    current = "?"
    # `split("\n")`, NOT `splitlines()`. This is the other half of `--text` and it is load-bearing in
    # exactly the same way. `str.splitlines()` breaks on \x0b \x0c \x1c \x1d \x1e \r \x85 U+2028 and
    # U+2029 in addition to \n; git uses \n and nothing else to separate diff lines. So a single `+`
    # line containing any of those bytes was split into fragments, and the `startswith("+")` filter
    # below then DISCARDED every fragment after the first — the credential read out of the object
    # store and then thrown away.
    #
    # Measured, on `b"\x00\x0b" + b'AWS_KEY = "AKIA...' `: splitlines() yields ['+\x00', 'AWS_KEY =
    # "AKIA…'] and the matcher never sees the key; split("\n") yields one fragment and it does.
    #
    # Before `--text` this was a rare edge case on text files. After `--text` it is the load-bearing
    # half, because the content `--text` newly admits is BINARY, which contains one of those bytes
    # with probability near 1. The signature is identical to the hole `--text` closed: exit 0, no
    # output, credential on the remote. A `+++ b/` path header can be split the same way, which
    # additionally mis-attributes surviving findings to "?".
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for name, pattern in SECRET_PATTERNS:
            m = re.search(pattern, line)
            if m:
                shown = m.group(0)
                redacted = shown[:6] + "…" + shown[-2:] if len(shown) > 12 else shown[:4] + "…"
                hits.append((current, name, redacted))
                break
    return hits


def readme_stale(base: str | None, local: str) -> bool:
    if not base:
        return False
    files = changed_files(base, local)
    if not files or any(Path(f).name.lower() == "readme.md" for f in files):
        return False
    top = {f.split("/")[0] for f in files if "/" in f}
    return bool(top - {"docs", ".github", ".claude", "graphify-out"})


def main() -> int:
    """Entry point. Exit 0 clean, 1 blocking finding, 2 the check could not run."""
    # `verify.sh` probes this script with `--help`. There is no argparse here, so that flag used to
    # fall straight through to the stdin read below: an interactive `./verify.sh` hung until Ctrl-D,
    # and a non-interactive one returned 0 having exercised nothing at all.
    #
    # Narrowed to a STANDALONE invocation. `any()` over all of argv meant `push_guard.py origin
    # --help` printed the docstring and returned 0 with stdin never read — the last argv-shaped path
    # to exit 0 without scanning. The guard's contract is that the only way to exit 0 is to have
    # scanned. `verify.sh` calls `--help` alone and is unaffected.
    args = sys.argv[1:]
    if len(args) == 1 and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    # git invokes this hook as `pre-push <remote-name> <remote-url>` and the installed hook forwards
    # "$@", so TWO POSITIONAL ARGUMENTS ARE NORMAL. They are ignored — the refs arrive on stdin.
    #
    # A previous revision of this function rejected any argv at all. That returned 2 on every real
    # push, in every repository on the machine, and the only way past it was --no-verify — the exact
    # habit this guard exists to prevent. Reject unrecognised *flags* only.
    unknown = [a for a in args if a.startswith("-")]
    if unknown:
        print(f"push_guard.py does not recognise {' '.join(unknown)}. It takes git's pre-push "
              f"positionals and reads the payload on stdin.", file=sys.stderr)
        return 2

    try:
        return run()
    except GuardError as exc:
        print(f"\n  pre-push BLOCKED: {exc}\n"
              f"\n  This is not a clean result — the check did not complete. Fix the environment "
              f"and re-run.\n  Do not push past it.\n", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # Ctrl-C is a check that did not run, not a finding — and it is a NORMAL thing to do here.
        # The scan buffers the whole pushed range before it matches anything, so on a large push it
        # stalls for a long time with no output; interrupting it produced a traceback and the
        # interpreter's exit 1, the code reserved for "a credential was found". Caught explicitly
        # because KeyboardInterrupt derives from BaseException, so the catch-all below never saw it.
        print("\n  pre-push BLOCKED: interrupted (Ctrl-C) — the check did not complete.\n"
              "\n  This is not a clean result — nothing in the range was scanned. Push again to "
              "run it.\n", file=sys.stderr)
        return 2
    except Exception as exc:                                            # noqa: BLE001
        # Exit 1 is reserved for "a blocking finding was found". Anything unexpected — the
        # MemoryError from a very large range, an OSError the git() wrapper never saw — used to
        # escape as a traceback, and the interpreter's exit 1 presented a check that could not run
        # as a check that ran and failed the push. A crash must not be able to impersonate a
        # finding, nor a finding a crash. `traceback` is imported at module scope on purpose: this
        # handler must survive a MemoryError, which is exactly when an import can fail.
        traceback.print_exc()
        print(f"\n  pre-push BLOCKED: the guard crashed ({type(exc).__name__}: {exc}).\n"
              f"\n  This is not a clean result — the check did not complete. Fix the environment "
              f"and re-run.\n  Do not push past it.\n", file=sys.stderr)
        return 2


def run() -> int:
    payload = [ln.split() for ln in sys.stdin.read().splitlines() if ln.strip()]
    if not payload:
        return 0

    blocking: list[str] = []
    warnings: list[str] = []

    for parts in payload:
        if len(parts) != 4:
            # Not `continue`. An unparseable line means the guard does not know what is being
            # pushed, and a ref it could not parse is a ref it did not scan — reported, until now,
            # as clean and with no output at all.
            raise GuardError(f"unparseable pre-push payload line ({len(parts)} fields, expected 4): "
                             f"{' '.join(parts)!r}")
        local_ref, local_oid, remote_ref, remote_oid = parts
        if is_null_oid(local_oid):         # a branch deletion pushes nothing to inspect
            continue
        if local_oid == remote_oid:        # already there; git can still call us with a no-op ref
            continue

        if remote_ref in DEFAULT_BRANCHES and not is_null_oid(remote_oid) \
                and not env_allows("PD_ALLOW_MAIN_PUSH"):
            blocking.append(
                f"direct push to {remote_ref}. Milestone work lands through a pull request:\n"
                f"      git switch -c milestone/<name> && git push -u origin HEAD && gh pr create\n"
                f"      Deliberate exception: PD_ALLOW_MAIN_PUSH=1 git push\n"
                f"      (1/true/yes/on open it; anything else — including 0, false, no, off — "
                f"leaves it closed.)")

        base = base_for(local_oid, remote_oid)

        for path, mb in oversized(base, local_oid):
            blocking.append(f"{path} is {mb:.1f} MB (limit {MAX_FILE_MB:g} MB). Git keeps it in "
                            f"history forever — every future clone pays for it.")

        for path, name, shown in secrets(base, local_oid):
            blocking.append(f"{path}: looks like a {name} ({shown}). If it is real, rotate it — "
                            f"removing the line does not remove it from history.")

        for path in added_files(base, local_oid):
            if ENV_FILE.search(path) and not ENV_ALLOWED.search(path):
                warnings.append(f"{path} is a new .env-style file. Confirm it holds no secrets.")

        # The README advisory is about branch work becoming a PR. A tag names a commit; it never
        # becomes a PR, and an archive tag exists precisely to preserve a superseded snapshot, so
        # "update the front page" is never the right response to it. The security checks above still
        # run for tags — a tag can introduce a commit that is on no branch, which is exactly when an
        # unscanned secret or oversized blob would otherwise reach the remote.
        if not remote_ref.startswith("refs/tags/") and readme_stale(base, local_oid):
            warnings.append("source changed but README.md did not — confirm the front page is "
                            "still true before this becomes a PR.")

    for w in warnings:
        print(f"  pre-push warn: {w}")

    if blocking:
        print("\n  pre-push BLOCKED:")
        for b in blocking:
            print(f"    - {b}")
        print("\n  Fix the reported finding before pushing.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
