#!/usr/bin/env python3
"""Break-test for push_guard.py — proves the guard fails, and fails closed.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
that was live in this file, so a regression re-breaks a named test instead of silently un-guarding
a push.

  1  clean range                              exit 0
  2  credential in a small range              exit 1
  3  credential in a >40 MB range             exit 1   <- the 143 MB push that scanned nothing
  4  oversized blob, PD_MAX_FILE_MB=99999     exit 1   <- the env override that is now gone
  5  git times out                            GuardError, never a clean result
  6  git's own `<remote> <url>` argv          exit 1 on a planted key, and no argument error
  7  remote oid absent from the object store  exit 2   <- the force-push that scanned nothing
  8  undecodable bytes in the diff            exit 1, the key still found, no traceback
  9  payload line that is not four fields     exit 2
 10  `git cat-file` fails during the size gate exit 2
 11  a real `git push` through the real hook  push fails, remote ref never created
 12  `git log` fails INSIDE a valid range     exit 2   <- git()'s carve-out, which case 7 never reaches
 13  the object store cannot be READ          exit 2, and it does not say "run git fetch"
 14  an unexpected crash, and a Ctrl-C        exit 2, never the exit 1 reserved for a finding
 15  a direct push to refs/heads/main         exit 1; the escape hatch tests its VALUE, and every
                                             negative and unrecognised spelling fails CLOSED
 16  a SHA-256 repository's 64-zero null oid  first push still exits 0, and still gets scanned
 17  the repo declares its own files binary   exit 1  <- the scan switched off from INSIDE the repo
 18  the pattern set cannot load, or is empty exit 2  <- a crash and an empty set, both before main()

Cases 8 and 17 are the in-repository class: they attack the guard with content that arrives with a
clone, rather than with something the founder's machine controls (argv, stdin, PATH, the object
store, an env var). Case 8 was the first — committed latin-1 bytes concealed the ENTIRE scan behind
a traceback. Case 17 extends the class from "content git cannot decode" through "content git
refuses to diff" (`-diff`, a NUL byte) to "content the matcher mis-splits" (an embedded \x0b, which
`str.splitlines()` treats as a line break and `git` does not). All three reach the same signature:
exit 0, no output, credential on the remote.

What these cases DO NOT cover, stated plainly because an overstated coverage claim in a break-test
is the same failure one layer up. Cases 1-4, 6-10, 12, 13 and 15-17 drive the guard as a process
through `run_guard()`. Cases 5, 14 and 18 do NOT: they load push_guard.py via importlib. Case 5
calls `pg.git()` directly and proves the raise and nothing downstream of it; case 14 calls
`pg.main()` with `pg.run` replaced, so it proves the handler chain and nothing upstream of it; case
18 never gets as far as a callable, because the failure it reproduces happens while the module body
is still executing. All three load THIS FILE'S SIBLING — the installed guard, not a copy. Case 11
is the only case that executes the shell wrapper, and it invokes the INSTALLED guard at the path the
hook template hardcodes, not necessarily this file's sibling.

Cases 12 and 13 exist because case 7 does not reach what it appears to. `base_for` calls
`object_exists` BEFORE any range command runs, so case 7 exits 2 through that raise — `git()`'s
CalledProcessError branch, the actual subject of the fix, was executed by no assertion at all, and
defaulting `tolerate_failure` back to True left every one of them green.

Run:  python3 push_guard_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "push_guard.py"
ZERO = "0" * 40

# Split so this file does not itself carry a literal the scanner matches. Without the split, the
# repository holding this test trips its own guard, and the only way past is the --no-verify habit
# the guard exists to prevent. Same reasoning as SECRET_PATTERNS in validate_disclosure.py.
FAKE_AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"

failures: list[str] = []


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def new_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    sh("git", "init", "-q", "-b", "feature", cwd=repo)
    sh("git", "config", "user.email", "selftest@example.invalid", cwd=repo)
    sh("git", "config", "user.name", "selftest", cwd=repo)
    (repo / "README.md").write_text("# selftest\n")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    return repo


def run_guard(repo: Path, env: dict[str, str] | None = None,
              argv: list[str] | None = None, remote_oid: str = ZERO,
              payload: str | None = None) -> tuple[int, str]:
    """Feed the guard a standard pre-push payload for a brand-new branch.

    argv defaults to how git ACTUALLY invokes the hook — `<remote-name> <remote-url>` — rather than
    to no arguments. Testing the no-argument form is testing a call that never happens.

    `remote_oid` overrides the fourth payload field; `payload` overrides the whole line.
    """
    head = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
    if payload is None:
        payload = f"refs/heads/feature {head} refs/heads/feature {remote_oid}\n"
    if argv is None:
        argv = ["origin", "git@github.com:example/repo.git"]
    proc = subprocess.run([sys.executable, str(GUARD), *argv], cwd=repo, input=payload,
                          capture_output=True, text=True, env={**os.environ, **(env or {})})
    return proc.returncode, proc.stdout + proc.stderr


def git_shim(tmp: Path, label: str, fail_when: str, message: str, code: int = 128) -> str | None:
    """A PATH entry whose `git` forwards to the real binary except for ONE command, which it fails.

    Returns a $PATH value, or None (having recorded a failure) if git is not on PATH at all.

    Failing one subcommand rather than all of git is what makes these cases realistic: every
    command the guard needs in order to *reach* the failure still works, so the case proves the
    guard's response to a partial failure and not merely its response to a broken machine.

    `fail_when` is an sh condition evaluated with git's arguments in "$@".
    """
    real_git = shutil.which("git")
    if not real_git:
        check(f"{label} git on PATH", False, "git not found")
        return None
    shim = tmp / f"shim-{label.split()[0]}"
    shim.mkdir()
    (shim / "git").write_text(
        "#!/bin/sh\n"
        f"if {fail_when}; then\n"
        f'  echo "{message}" >&2\n'
        f"  exit {code}\n"
        "fi\n"
        f'exec {real_git} "$@"\n')
    (shim / "git").chmod(0o755)
    return f"{shim}{os.pathsep}{os.environ['PATH']}"


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def case_clean() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "app.py").write_text("print('hello')\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add app", cwd=repo)
        code, out = run_guard(repo)
        check("1 clean range exits 0", code == 0, f"got {code}: {out[:200]}")


def case_small_secret() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add config", cwd=repo)
        code, out = run_guard(repo)
        check("2 credential in a small range exits 1", code == 1, f"got {code}")
        check("2 names the credential", "AWS access key" in out, out[:200])


def case_large_range_secret() -> None:
    """The regression that mattered: 143 MB pushed, content scan skipped, exit 0.

    Every file stays under MAX_FILE_MB so the size rule cannot fire — if this case passes, it
    passes because the *content* scan ran on a range far past the old 40 MB cap.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        filler = ("x" * 80 + "\n") * 115_000            # ~9 MB, under the 10 MB blob limit
        for i in range(6):                              # ~54 MB total, past the old 40 MB cap
            (repo / f"bulk{i}.txt").write_text(filler)
        (repo / "leaked.py").write_text(f'KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "bulk import", cwd=repo)

        code, out = run_guard(repo)
        check("3 credential in a >40 MB range exits 1", code == 1, f"got {code}")
        check("3 names the credential, not just the size", "AWS access key" in out, out[:200])
        check("3 no 'skipping the content scan' anywhere",
              "skipping the content scan" not in out, out[:200])


def case_env_override_ignored() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "big.bin").write_text("y" * (11 * 1024 * 1024))   # 11 MB > the 10 MB limit
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add big", cwd=repo)

        code, out = run_guard(repo, env={"PD_MAX_FILE_MB": "99999"})
        check("4 PD_MAX_FILE_MB=99999 does not raise the limit", code == 1, f"got {code}")
        check("4 still reports the 10 MB limit", "limit 10 MB" in out, out[:200])


def case_git_invocation() -> None:
    """The regression that broke every push on this machine.

    git runs the hook as `pre-push <remote-name> <remote-url>` and the installed hook forwards
    "$@". A revision that rejected any argv returned 2 on every real push in every repository, and
    the only way past was --no-verify. That this was not caught is the point: the whole break-test
    invoked the guard the way nothing ever invokes it.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        # A PLANTED KEY, not a clean file. "exit 0 under git's argv" passes against a guard that
        # reads no stdin and scans nothing — including `main(): return 0`. Asserting a positive
        # finding means stdin must have been read and the range must have been scanned, so this
        # case cannot go green against a collapsed main().
        (repo / "app.py").write_text(f'KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add app", cwd=repo)

        code, out = run_guard(repo, argv=["origin", "git@github.com:example/repo.git"])
        check("6a git's argv reaches a real scan, not just exit 0",
              code == 1 and "AWS access key" in out, f"got {code}: {out[:200]}")
        check("6b does not report an argument error",
              "does not recognise" not in out and "takes no arguments" not in out, out[:200])

        code, out = run_guard(repo, argv=["--nonsense"])
        check("6c an unrecognised flag still exits 2", code == 2, f"got {code}")
        check("6d the flag rejection names the flag and says why",
              "does not recognise" in out and "--nonsense" in out, out[:200])

        # N4: `--help` mixed with positionals must NOT short-circuit to exit 0 unscanned.
        code, out = run_guard(repo, argv=["origin", "--help"])
        check("6e `--help` alongside a positional does not exit 0 unscanned", code != 0,
              f"got {code}: {out[:200]}")


def case_timeout_fails_closed() -> None:
    """A timed-out scan must raise, not return an empty diff with zero findings."""
    spec = importlib.util.spec_from_file_location("push_guard_under_test", GUARD)
    pg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pg)

    def always_timeout(*_a, **kw):
        raise subprocess.TimeoutExpired(cmd="git", timeout=kw.get("timeout", 1))

    original = pg.subprocess.run
    pg.subprocess.run = always_timeout
    try:
        pg.git("log", "-p")
    except pg.GuardError as exc:
        check("5a a timeout raises GuardError", True)
        check("5b the message says the scan did not run", "did not run" in str(exc), str(exc))
        return
    except Exception as exc:                                    # noqa: BLE001
        check("5c a timeout raises GuardError, not some other exception", False,
              f"raised {type(exc).__name__}")
        return
    finally:
        pg.subprocess.run = original
    check("5d a timeout does not return normally", False,
          "returned normally — this is the fail-open bug")


def case_missing_remote_oid() -> None:
    """The force-push that scanned nothing and said nothing.

    `git push` runs ls-remote first and hands the hook the remote's ACTUAL oid, which need not be in
    the local object store — routine after a rebase, or when a second machine advanced the branch.
    That oid became the range endpoint unchecked, so `rev-list --objects` and `log -p` both exited
    128, the CalledProcessError carve-out turned both into "", and the guard reported a clean push
    having scanned nothing. A planted key is in this range: exit 0 here means the hole is back.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add config", cwd=repo)

        absent = "1" * 40                      # well-formed, and not an object in this repository
        code, out = run_guard(repo, remote_oid=absent)
        check("7a an absent remote oid is not a clean scan", code == 2, f"got {code}: {out[:200]}")
        check("7b it says the range could not be computed",
              "object store" in out and "cannot be computed" in out, out[:300])
        check("7c it never claims the range was clean", "pre-push BLOCKED" in out, out[:200])


def case_undecodable_bytes() -> None:
    """An undecodable diff used to hide the ENTIRE scan behind a traceback and exit 1.

    git calls a file text when its first 8000 bytes hold no NUL, so `log -p` readily emits latin-1
    source bytes. Under `text=True` that raised UnicodeDecodeError out of subprocess.run — exit 1,
    the code reserved for a finding, with a traceback and no instruction. The fix decodes with
    errors="replace": a mangled character cannot conceal a credential, so the scan simply runs.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "latin.py").write_bytes(b"# caf\xe9 is not valid UTF-8\nvalue = 1\n")
        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "undecodable bytes beside a key", cwd=repo)

        code, out = run_guard(repo)
        check("8a undecodable bytes no longer hide the scan",
              code == 1 and "AWS access key" in out, f"got {code}: {out[:300]}")
        check("8b no traceback reaches the user",
              "Traceback" not in out and "UnicodeDecodeError" not in out, out[:300])


def case_malformed_payload() -> None:
    """A payload line that is not four fields was `continue` — that ref went entirely unscanned."""
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add config", cwd=repo)
        head = sh("git", "rev-parse", "HEAD", cwd=repo).strip()

        code, out = run_guard(repo, payload=f"refs/heads/feature {head} refs/heads/feature\n")
        check("9a a three-field payload line is not a clean result", code == 2, f"got {code}")
        check("9b the message names the offending line",
              "unparseable pre-push payload line" in out and "3 fields" in out, out[:300])


def case_cat_file_failure() -> None:
    """`git cat-file` failing mid-size-gate must void the check, at the process level.

    A PATH shim forwards every git call to the real binary except the size gate's --batch-check,
    which it fails. This is the `oversized()` raise at close range: it has never been executed by
    the guard *process* in any previous revision of this suite.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "app.py").write_text("print('ok')\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add app", cwd=repo)

        # Every cat-file EXCEPT the `-e` existence probe, i.e. exactly the size gate's
        # --batch-check. Naming the probe explicitly keeps this case independent of case 13, which
        # fails the probe and nothing else.
        path = git_shim(Path(td), "10", '[ "$1" = "cat-file" ] && [ "$2" != "-e" ]',
                        "simulated cat-file failure", code=3)
        if path is None:
            return
        code, out = run_guard(repo, env={"PATH": path})
        check("10a a cat-file failure in the size gate exits 2", code == 2, f"got {code}: {out[:300]}")
        check("10b it names cat-file and does not report clean",
              "cat-file" in out and "did not complete" in out, out[:300])


LEGACY_HOOK_MARK = "legacy pre-push hook ran"


def _remote_ref(bare: Path) -> str:
    p = subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/heads/feature"],
                       cwd=bare, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def _push_through_real_hook(tmp: Path, ih, preseed: str | None) -> dict[str, object]:
    """Two real pushes — one clean, one with a planted key — through a real installed hook.

    The hook is composed by `ih.write_hook()` itself rather than by hand. Hand-composing it
    reimplemented the function under test, so `write_hook`'s placement logic went untested: swapping
    its two branches so a pre-existing hook lands AFTER our block left every assertion in this file
    green, and in a repository that already had a pre-push hook that reordering decides whether our
    block runs at all.
    """
    sh("git", "init", "-q", "--bare", str(tmp / "remote.git"), cwd=tmp)
    repo = new_repo(tmp)
    sh("git", "remote", "add", "origin", str(tmp / "remote.git"), cwd=repo)

    hook = repo / ".git" / "hooks" / "pre-push"
    if preseed is not None:
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(preseed)
        hook.chmod(0o755)
    action = ih.write_hook(hook, ih.PRE_PUSH.format(begin=ih.BEGIN, end=ih.END))

    # First: a genuinely clean push must SUCCEED. A guard that blocks everything would satisfy every
    # "must block" assertion in this file, so the suite has to pin the other direction through the
    # real wrapper too — that is the failure mode a153b47 actually shipped.
    (repo / "app.py").write_text("print('ok')\n")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "clean work", cwd=repo)
    clean = subprocess.run(["git", "push", "origin", "feature"], cwd=repo,
                           capture_output=True, text=True)
    clean_oid = _remote_ref(tmp / "remote.git")

    # Second: the remote ref now EXISTS, so git hands the hook a real remote oid and `base_for`
    # takes its object_exists() branch — the path an absent oid must be distinguished from.
    (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "planted key", cwd=repo)
    keyed = subprocess.run(["git", "push", "origin", "feature"], cwd=repo,
                           capture_output=True, text=True)
    return {"action": action, "hook": hook.read_text(),
            "clean_rc": clean.returncode, "clean_out": clean.stdout + clean.stderr,
            "clean_oid": clean_oid,
            "keyed_rc": keyed.returncode, "keyed_out": keyed.stdout + keyed.stderr,
            "final_oid": _remote_ref(tmp / "remote.git")}


def case_end_to_end_push() -> None:
    """The seam that broke every push on this machine, tested the way git actually drives it.

    The bug was never inside push_guard.py — it was a mismatch between the guard's argv contract and
    the shell wrapper that invokes it, and no case executed the wrapper. This one does the real
    thing: a bare remote, the PRE_PUSH template rendered from install_hooks.py and chmod'd into
    .git/hooks/pre-push, a planted key, and a genuine `git push`. It covers the wrapper, the argv
    shape, the stdin payload and the exit-code plumbing in one case.

    NOTE: the template hardcodes $HOME/.claude/.../push_guard.py, so this case exercises the
    INSTALLED guard. If that is not this file's sibling, the case says so rather than passing.
    """
    spec = importlib.util.spec_from_file_location(
        "install_hooks_under_test", GUARD.parent / "install_hooks.py")
    ih = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ih)

    hooked = Path(os.path.expanduser(
        "~/.claude/skills/progressive-disclosure/scripts/push_guard.py"))
    if hooked.resolve() != GUARD.resolve():
        check("11 the hook template points at the guard under test", False,
              f"template runs {hooked}, this suite tests {GUARD}")
        return

    with tempfile.TemporaryDirectory() as td:
        r = _push_through_real_hook(Path(td), ih, preseed=None)
        check("11a a genuinely clean push succeeds through the real hook", r["clean_rc"] == 0,
              f"got {r['clean_rc']}: {str(r['clean_out'])[:300]}")
        check("11b the clean push actually created the remote ref", r["clean_oid"] != "",
              str(r["clean_out"])[:300])
        check("11c a real `git push` of a planted key FAILS", r["keyed_rc"] != 0,
              f"got {r['keyed_rc']}: {str(r['keyed_out'])[:300]}")
        check("11d the guard's finding reached the user through the wrapper",
              "AWS access key" in str(r["keyed_out"]), str(r["keyed_out"])[:300])
        check("11e a resolvable remote oid is scanned, not rejected as absent",
              "object store" not in str(r["keyed_out"]), str(r["keyed_out"])[:300])
        check("11f the remote ref did not advance to the key commit",
              r["final_oid"] == r["clean_oid"], f"remote moved to {r['final_oid']}")

    # The co-resident-hook variant. `write_hook` promises to preserve a hook the user already had,
    # and a preserved hook that never executes is not preserved — so this asserts BOTH halves: our
    # block still blocks, and the pre-existing hook still runs on the same push. Nothing tested
    # either before, which is why swapping write_hook's two branches went unnoticed.
    with tempfile.TemporaryDirectory() as td:
        r = _push_through_real_hook(
            Path(td), ih, preseed=f'#!/bin/sh\necho "{LEGACY_HOOK_MARK}" >&2\n')
        check("11g a pre-existing pre-push hook is preserved in the composed hook",
              r["action"] == "updated (existing hook preserved)"
              and LEGACY_HOOK_MARK in str(r["hook"]), f"{r['action']}: {str(r['hook'])[:300]}")
        check("11h a clean push still succeeds with a co-resident hook", r["clean_rc"] == 0,
              f"got {r['clean_rc']}: {str(r['clean_out'])[:300]}")
        check("11i the pre-existing hook still RUNS, it is not merely preserved in the text",
              LEGACY_HOOK_MARK in str(r["keyed_out"]), str(r["keyed_out"])[:300])
        check("11j the guard still blocks a planted key beside a co-resident hook",
              r["keyed_rc"] != 0 and "AWS access key" in str(r["keyed_out"]),
              f"got {r['keyed_rc']}: {str(r['keyed_out'])[:300]}")
        check("11k the remote ref did not advance, co-resident hook or not",
              r["final_oid"] == r["clean_oid"], f"remote moved to {r['final_oid']}")


def case_scan_command_fails_inside_a_valid_range() -> None:
    """git()'s CalledProcessError branch — the actual subject of the fix, and case 7 never reaches it.

    Case 7 hands the guard a remote oid that is absent from the object store, so `base_for` raises
    from `object_exists` BEFORE `rev-list` or `log -p` runs. Exit 2 arrives, but through the wrong
    door: with `tolerate_failure` defaulted back to True — the exact fail-open this card was written
    to close — every assertion in this file stayed green.

    So this case gives the guard a real, RESOLVABLE remote oid, lets `object_exists` succeed, and
    fails `git log` inside the range with a PATH shim. That is the residual real-world shape: a
    corrupt or missing object *inside* an otherwise computable range, or a partial clone whose
    filtered blob cannot be fetched. A planted key is in that range; exit 0 or 1 here means the
    empty string came back from `git()` and was read as a clean scan.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        base = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add config", cwd=repo)

        path = git_shim(Path(td), "12", '[ "$1" = "log" ]',
                        "fatal: unable to read object 4b825dc: is corrupt")
        if path is None:
            return
        code, out = run_guard(repo, remote_oid=base, env={"PATH": path})
        check("12a a git command failing inside the range is not a clean scan", code == 2,
              f"got {code}: {out[:300]}")
        check("12b the message names the failing command and says the scan did not run",
              "`git log" in out and "the scan did not run" in out, out[:300])
        check("12c it reached git()'s carve-out, not the object_exists gate",
              "object store" not in out, out[:300])


def case_object_store_unreadable() -> None:
    """"Absent" and "could not be determined" must not be the same answer.

    `object_exists` returned `proc.returncode == 0`, so exit 1 ("no such object") and exit 128 ("the
    object store could not be read") both became False and both produced the message "Run `git
    fetch` and push again". Fail-closed either way — but no `git fetch` repairs a corrupt or
    unreadable .git/objects, and a block whose stated remedy leaves it in place is the one situation
    that genuinely argues for --no-verify.

    The trigger in the wild is `chmod 000 .git/objects`, a failed promisor fetch, or a corrupt loose
    object. A shim reproduces it deterministically and without leaving a 000-mode directory behind
    on a machine where the suite might be interrupted.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        base = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
        (repo / "app.py").write_text("print('ok')\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add app", cwd=repo)

        path = git_shim(Path(td), "13", '[ "$1" = "cat-file" ] && [ "$2" = "-e" ]',
                        "fatal: unable to read .git/objects: Permission denied")
        if path is None:
            return
        code, out = run_guard(repo, remote_oid=base, env={"PATH": path})
        check("13a an unreadable object store is not a clean scan", code == 2,
              f"got {code}: {out[:300]}")
        check("13b it says the store could not be READ, and relays git's reason",
              "could not be READ" in out and "Permission denied" in out, out[:300])
        check("13c it does NOT prescribe `git fetch`, which cannot repair an object store",
              "Run `git fetch` and push again" not in out, out[:300])

    # And the same class of damage without any shim at all. `git cat-file -e <oid>` proves an object
    # is PRESENT, not that it is READABLE, so a corrupt loose object answers 0 and object_exists
    # returns True — this asserts the guard still fails closed one step later, when rev-list cannot
    # walk the range. Real corruption, no simulation, inside a throwaway repo.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        base = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
        (repo / "app.py").write_text("print('ok')\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add app", cwd=repo)

        loose = repo / ".git" / "objects" / base[:2] / base[2:]
        if not loose.exists():
            check("13 the base commit is a loose object", False, f"{loose} not found")
            return
        loose.chmod(0o644)
        loose.write_bytes(b"not a zlib stream")

        code, out = run_guard(repo, remote_oid=base)
        check("13d a genuinely corrupt object in the range is not a clean scan", code == 2,
              f"got {code}: {out[:300]}")
        check("13e it names the command that could not walk the range",
              "the scan did not run" in out and "did not complete" in out, out[:300])


def case_crash_and_interrupt_fail_closed() -> None:
    """main()'s handler chain below `except GuardError` — in-process, like case 5.

    Every process-level case that reaches an error raises GuardError, which the FIRST except clause
    handles, so deleting the catch-all outright left all 30 assertions green. The earlier proof of
    it lived in a scratch file that was never part of this suite — evidence that expires the moment
    nobody re-runs it, which is the whole reason this suite exists.

    KeyboardInterrupt is here for the same reason and is not covered by the catch-all: it derives
    from BaseException, so `except Exception` never saw it and Ctrl-C during a long scan produced a
    traceback and exit 1 — the code reserved for "a credential was found".
    """
    spec = importlib.util.spec_from_file_location("push_guard_crash_test", GUARD)
    pg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pg)

    def main_with(raised: BaseException) -> tuple[int | None, str]:
        """Call pg.main() with run() replaced by something that raises. Returns (code, output)."""
        def boom() -> int:
            raise raised

        original_run, original_argv = pg.run, sys.argv
        pg.run, sys.argv = boom, ["push_guard.py", "origin", "git@github.com:example/repo.git"]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = pg.main()
        except BaseException as escaped:                             # noqa: BLE001
            # Not a crash of this suite: an exception escaping main() IS the defect under test,
            # so it has to be reported as a failed assertion rather than kill the run.
            return None, f"{type(escaped).__name__} escaped main(): {escaped}"
        finally:
            pg.run, sys.argv = original_run, original_argv
        return code, buf.getvalue()

    code, out = main_with(MemoryError("simulated"))
    check("14a an unexpected crash exits 2, never the 1 reserved for a finding", code == 2,
          f"got {code}: {out[:300]}")
    check("14b it names the crash and does not report a clean or found result",
          "the guard crashed" in out and "MemoryError" in out, out[:300])

    code, out = main_with(KeyboardInterrupt())
    check("14c Ctrl-C during the scan exits 2, not 1", code == 2, f"got {code}: {out[:300]}")
    check("14d it says the check did not complete", "did not complete" in out, out[:300])


def case_direct_push_to_default_branch() -> None:
    """One of the three things the module docstring says this guard exists to block.

    Deleting the block left all 30 assertions green — no case pushed to refs/heads/main. The
    remote oid must be a real one: a brand-new default branch is not what this rule is about.

    15d onward exist because 15a-15c did not catch the defect they were closest to. They drove the
    escape hatch with exactly two spellings — unset and `=1` — which are the two that happen to
    behave correctly under a PRESENCE test. `not os.environ.get("PD_ALLOW_MAIN_PUSH")` is true when
    unset and false when `=1`, so both assertions passed against a guard in which
    `PD_ALLOW_MAIN_PUSH=0` and `PD_ALLOW_MAIN_PUSH=false` ALSO bypassed the block. A break-test that
    exercises only the inputs that work is not a break-test; it is a demonstration. So every
    spelling below is asserted individually, and the negative ones are asserted first-class rather
    than as an afterthought, because the negative direction is where the inversion lived: a founder
    typing `=0` to be explicit that they do NOT want the escape was handed the escape.

    The fixture needs TWO commits. `base_for` calls `object_exists(remote_oid)` before anything
    else, so a payload whose remote oid is not a real local object exits 2 through that raise and
    never reaches the direct-push block at all — the assertions would then be green against a code
    path they never executed, which is the same vacuity this case is here to fix.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        base = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
        (repo / "app.py").write_text("print('ok')\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add app", cwd=repo)
        head = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
        payload = f"refs/heads/main {head} refs/heads/main {base}\n"

        code, out = run_guard(repo, payload=payload)
        check("15a a direct push to refs/heads/main is blocked", code == 1, f"got {code}: {out[:300]}")
        check("15b it names the PR route and the deliberate exception",
              "pull request" in out and "PD_ALLOW_MAIN_PUSH" in out, out[:300])

        code, out = run_guard(repo, payload=payload, env={"PD_ALLOW_MAIN_PUSH": "1"})
        check("15c PD_ALLOW_MAIN_PUSH=1 is a real way past it, not just documented", code == 0,
              f"got {code}: {out[:300]}")

        # A message that advertises only `=1` while the code accepts four spellings is a smaller
        # version of the same defect: the text stops describing the guard.
        _, blocked_out = run_guard(repo, payload=payload)
        check("15d the message says which values open the hatch and which leave it closed",
              "1/true/yes/on" in blocked_out and "0, false, no, off" in blocked_out,
              blocked_out[:400])

        # Affirmative — each of these must BYPASS. Case and surrounding whitespace are normalised,
        # because `PD_ALLOW_MAIN_PUSH=" 1"` out of a shell variable is a real way to type it.
        for value in ("1", "true", "yes", "on", "TRUE", "On", " 1 ", "\tyes\n"):
            code, out = run_guard(repo, payload=payload, env={"PD_ALLOW_MAIN_PUSH": value})
            check(f"15e PD_ALLOW_MAIN_PUSH={value!r} is affirmative and bypasses the block",
                  code == 0, f"got {code}: {out[:300]}")

        # Negative — each of these must BLOCK. Under the presence test every one of them bypassed.
        for value in ("0", "false", "no", "off", "FALSE", "Off", "", " 0 ", "\tfalse\n"):
            code, out = run_guard(repo, payload=payload, env={"PD_ALLOW_MAIN_PUSH": value})
            check(f"15f PD_ALLOW_MAIN_PUSH={value!r} means NOT allowed and still blocks",
                  code == 1, f"got {code}: {out[:300]}")

        # Unrecognised — fail closed. A value nobody can parse is not consent to skip the check,
        # and a deny-list of negatives would have let every one of these through.
        for value in ("maybe", "banana", "2", "-1", "yes please", "true story", "null", "None"):
            code, out = run_guard(repo, payload=payload, env={"PD_ALLOW_MAIN_PUSH": value})
            check(f"15g PD_ALLOW_MAIN_PUSH={value!r} is unrecognised and fails CLOSED",
                  code == 1, f"got {code}: {out[:300]}")

        # The hatch is scoped to this one rule. A secret in the range is not a thing the founder can
        # wave through, and an escape hatch that quietly widens is how a targeted exception becomes
        # a global --no-verify.
        (repo / "creds.txt").write_text(f"aws_key = {FAKE_AWS_KEY}\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add creds", cwd=repo)
        tip = sh("git", "rev-parse", "HEAD", cwd=repo).strip()
        code, out = run_guard(repo, payload=f"refs/heads/main {tip} refs/heads/main {base}\n",
                              env={"PD_ALLOW_MAIN_PUSH": "1"})
        check("15h an affirmative value waives ONLY the direct-push rule, not the secret scan",
              code == 1 and "creds.txt" in out, f"got {code}: {out[:300]}")


def case_sha256_repository() -> None:
    """The null oid is 64 zeros under SHA-256, and the guard compared against a 40-char literal.

    Every comparison was False for a brand-new branch, so the guard read the null oid as a real
    remote tip, found it absent from the object store, and HARD-BLOCKED the first push of every
    branch with a message telling the founder to `git fetch` — which cannot clear it, because there
    is nothing on the remote to fetch. Fail-closed, and far worse than a hole: a block whose stated
    remedy does not work is the one thing that reliably teaches --no-verify.

    Asserting exit 0 on a clean first push AND exit 1 on a keyed one, because "blocks everything"
    would satisfy the second on its own.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        init = subprocess.run(["git", "init", "-q", "--object-format=sha256", "-b", "feature"],
                              cwd=repo, capture_output=True, text=True)
        if init.returncode != 0:
            check("16 this git supports --object-format=sha256", False, init.stderr[:200])
            return
        sh("git", "config", "user.email", "selftest@example.invalid", cwd=repo)
        sh("git", "config", "user.name", "selftest", cwd=repo)
        (repo / "README.md").write_text("# selftest\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "init", cwd=repo)

        null256 = "0" * 64
        code, out = run_guard(repo, remote_oid=null256)
        check("16a a first push in a SHA-256 repo is not hard-blocked", code == 0,
              f"got {code}: {out[:300]}")
        check("16b it does not tell the founder to fetch a branch that does not exist yet",
              "git fetch" not in out, out[:300])

        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "add config", cwd=repo)
        code, out = run_guard(repo, remote_oid=null256)
        check("16c and the scan still runs — a planted key in a SHA-256 repo is still found",
              code == 1 and "AWS access key" in out, f"got {code}: {out[:300]}")


def case_repo_controlled_binary_classification() -> None:
    """The repository being scanned decides what the scanner can read.

    `git log -p` emits `Binary files a/x and b/x differ` and NO `+` lines at all for any path git
    classifies as binary, so `secrets()` sees nothing to match and `run()` returns 0 — a clean exit,
    no output, credential on the remote. Two triggers, both of which travel WITH the repository:

      * a `.gitattributes` entry unsetting the `diff` attribute (`* -diff`), and
      * a NUL byte in the first 8000 bytes, which is git's own text/binary heuristic.

    Neither needs malice. A repository that legitimately marks a data directory `-diff`, or a source
    file that happens to carry an embedded NUL, loses secret scanning for those paths permanently
    and silently — and nothing in the output distinguishes it from a clean scan.

    `--text` on the `log -p` forces textual diffs regardless of classification. It is the same
    argument `_decode` already settled one layer out: a mangled character cannot conceal a
    credential, but an unreadable diff concealed the entire scan.

    But admitting the content is only HALF the path, and the third block below is the other half.
    `--text` hands the matcher a genuinely binary line, and binary content contains a byte that
    `str.splitlines()` treats as a line break with probability near 1 — \x0b, \x0c, \x1c, \x1d,
    \x1e or \r. `splitlines()` splits the `+` line there and the `if not line.startswith("+")`
    filter then DISCARDS every fragment past the first, so the credential is thrown away after
    being read. Same exit 0, same empty output. `split("\n")` is the only correct split here,
    because `\n` is the only byte git itself uses to separate diff lines.

    Asserting exit 1 AND the credential named AND the PATH it was found in AND the absence of the
    "did not complete" framing. The path assertion is not decoration: without it every assertion
    here is satisfied by the string "AWS access key" appearing anywhere in the output, including
    from a finding attributed to "?" because the `+++ b/` header was itself mis-split. And this must
    land as a FINDING, not as a crash that happens to be non-zero — the guard's own invariant is
    that a crash must not impersonate a finding, nor a finding a crash.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / ".gitattributes").write_text("* -diff\n")
        (repo / "config.py").write_text(f'AWS_KEY = "{FAKE_AWS_KEY}"\n')
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "mark everything binary, beside a key", cwd=repo)

        code, out = run_guard(repo)
        check("17a a committed `* -diff` does not switch the secret scan off", code == 1,
              f"got {code}: {out[:300]}")
        check("17b the credential is still named under `-diff`", "AWS access key" in out, out[:300])
        check("17c the finding is attributed to the file that holds it, not to `?`",
              "config.py" in out, out[:300])
        check("17d it lands as a finding, not as a crash that happens to be non-zero",
              "did not complete" not in out and "Traceback" not in out, out[:300])

    # The same hole through git's own text/binary heuristic rather than an attribute — no
    # .gitattributes involved, so this cannot pass merely because attribute handling was special-cased.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "config.py").write_bytes(
            b"\x00\x00\x00\x00" + f'AWS_KEY = "{FAKE_AWS_KEY}"\n'.encode())
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "NUL byte ahead of a key", cwd=repo)

        code, out = run_guard(repo)
        check("17e a NUL byte ahead of the key does not switch the secret scan off", code == 1,
              f"got {code}: {out[:300]}")
        check("17f the credential is still named past the NUL", "AWS access key" in out, out[:300])

    # Two bytes more than the block above, and it is the difference between admitting the content
    # and matching it. \x0b is a line break to `str.splitlines()` and is NOT one to git, so the
    # single `+` line git emitted arrives as ['+\x00', 'AWS_KEY = "AKIA…'] — and the second
    # fragment, the one holding the key, does not start with `+` and is dropped. Measured on this
    # exact input before the fix: splitlines() leaves the key invisible to the matcher, split("\n")
    # leaves it visible. Any of \x0b \x0c \x1c \x1d \x1e \r does it; \x0b is simply the first.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(Path(td))
        (repo / "config.py").write_bytes(
            b"\x00\x0b" + f'AWS_KEY = "{FAKE_AWS_KEY}"\n'.encode())
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "NUL then a vertical tab ahead of a key", cwd=repo)

        code, out = run_guard(repo)
        check("17g a splitlines-only line break inside a binary line does not hide the key",
              code == 1, f"got {code}: {out[:300]}")
        check("17h the credential is still named past the embedded \\x0b",
              "AWS access key" in out, out[:300])
        check("17i and it is still attributed to config.py, not to `?`",
              "config.py" in out, out[:300])


def _exec_guard_isolated(module_name: str, prepare) -> tuple[int | None, str]:
    """Execute the INSTALLED guard's module body with the import environment `prepare` sets up.

    The failures case 18 reproduces happen while push_guard.py's module body is still running, so
    there is no `main()` to call and no process-level entry point that reaches them with the real
    sibling on the path — `run_guard()` would just import the healthy validate_disclosure.py.
    `PYTHONPATH` cannot shadow it either: push_guard.py puts its own directory at `sys.path[0]`
    before the import, so a path-based override always loses.

    `sys.meta_path` is the seam that works, because it is consulted BEFORE any path-based finder.
    `prepare` runs with sys.modules and sys.meta_path already saved, and both are restored here
    whatever it does — a leaked finder would poison every later import in this process.

    Returns (exit code from SystemExit, captured output). A code of None means the module body
    completed without exiting, which for both variants below is itself the defect.
    """
    saved_meta = sys.meta_path[:]
    saved_mod = sys.modules.get("validate_disclosure")
    saved_path = sys.path[:]
    buf = io.StringIO()
    try:
        sys.modules.pop("validate_disclosure", None)
        prepare()
        spec = importlib.util.spec_from_file_location(module_name, GUARD)
        module = importlib.util.module_from_spec(spec)
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                spec.loader.exec_module(module)
        except SystemExit as exc:
            return (exc.code if isinstance(exc.code, int) else 1), buf.getvalue()
        except BaseException as escaped:                                # noqa: BLE001
            return None, (f"{type(escaped).__name__} escaped the module body: {escaped}\n"
                          + buf.getvalue())
        return None, buf.getvalue()
    finally:
        sys.meta_path[:] = saved_meta
        sys.path[:] = saved_path
        sys.modules.pop("validate_disclosure", None)
        if saved_mod is not None:
            sys.modules["validate_disclosure"] = saved_mod


def case_pattern_set_unusable() -> None:
    """The guard's secret patterns live in a DIFFERENT file, and neither failure has an entry point.

    Two ways the pattern set stops working, both of which land before `main()` is even defined and
    therefore outside every handler in it:

      a) validate_disclosure.py cannot be imported — mid-edit syntax error, a bad regex literal, a
         rename, a half-finished install. Unwrapped, this produced a traceback and the interpreter's
         exit 1 — the code RESERVED for "a credential was found" — so the composed hook blocked the
         push with no `pre-push BLOCKED` framing and nothing the founder could act on.
      b) SECRET_PATTERNS imports cleanly and is EMPTY. Nothing raises: the scan loop iterates zero
         times, `secrets()` returns [], and the guard exits 0 with no output having matched nothing
         against everything. This is the worse of the two, because (a) at least fails closed.

    Both run the installed guard, exactly as cases 5 and 14 do — not a copy. A test of a copy would
    prove the copy has the wrapper.
    """
    class Blocker:
        """A meta-path finder that turns one module name into a mid-edit syntax error."""

        def find_spec(self, name, path=None, target=None):               # noqa: D102, ANN001
            if name == "validate_disclosure":
                raise SyntaxError("simulated mid-edit validate_disclosure.py")
            return None

    def block() -> None:
        sys.meta_path.insert(0, Blocker())

    code, out = _exec_guard_isolated("push_guard_import_broken", block)
    check("18a an unimportable validate_disclosure.py exits 2, not the 1 reserved for a finding",
          code == 2, f"got {code}: {out[:300]}")
    check("18b it uses the guard's own framing and says the check did not run",
          "pre-push BLOCKED" in out and "did not run" in out, out[:300])
    check("18c it names the file to repair, so the message is actionable",
          "validate_disclosure.py" in out, out[:300])

    def empty_patterns() -> None:
        stub = importlib.util.module_from_spec(
            importlib.util.spec_from_loader("validate_disclosure", loader=None))
        stub.SECRET_PATTERNS = ()
        sys.modules["validate_disclosure"] = stub

    code, out = _exec_guard_isolated("push_guard_patterns_empty", empty_patterns)
    check("18d an EMPTY SECRET_PATTERNS is not a clean guard — it exits 2", code == 2,
          f"got {code}: {out[:300]}")
    check("18e it says the check did not run rather than reporting nothing at all",
          "pre-push BLOCKED" in out and "did not run" in out, out[:300])


def main() -> int:
    if not GUARD.exists():
        print(f"push_guard.py not found at {GUARD}", file=sys.stderr)
        return 2

    print("push_guard break-test")
    # Execution order matches the case numbers, and the case numbers match the docstring table. An
    # earlier revision ran 5 last and printed "1 2 3 4 6 5", so a reader could not tell whether a
    # case was missing or merely displaced.
    for case in (case_clean, case_small_secret, case_large_range_secret,
                 case_env_override_ignored, case_timeout_fails_closed, case_git_invocation,
                 case_missing_remote_oid, case_undecodable_bytes, case_malformed_payload,
                 case_cat_file_failure, case_end_to_end_push,
                 case_scan_command_fails_inside_a_valid_range, case_object_store_unreadable,
                 case_crash_and_interrupt_fail_closed, case_direct_push_to_default_branch,
                 case_sha256_repository, case_repo_controlled_binary_classification,
                 case_pattern_set_unusable):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the guard blocks every case it is supposed to block")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
