#!/usr/bin/env python3
"""Break-test for identifier_guard.py — proves the guard blocks, and fails closed when it cannot.

A guard nobody has watched fail is not evidence of anything. Every rule below is asserted in BOTH
directions: a fixture that must be blocked, and a near-identical fixture that must pass. One
direction alone is worthless here — "block everything" satisfies every must-block assertion, and
"block nothing" satisfies every must-pass one, and both are guards this file would otherwise call
green.

   1  a clean staged commit                          exit 0
   2  an absolute home path in staged content        exit 1   (and a placeholder path exits 0)
   3  an absolute home path in the commit MESSAGE    exit 1   <- pre-commit cannot see the message
   4  a deny-listed name in staged content           exit 1
   5  a deny-listed name in the commit MESSAGE       exit 1
   6  a deny-listed name in a staged PATH            exit 1   <- no line of content to match
   7  the local git identity (email, name, account)  exit 1
   8  NO deny-list installed                         exit 2   <- absent is a check that did not run
   9  a deny-list that cannot be read or is broken   exit 2, never a silent pass
  10  an identifier already in history               exit 0   <- the scan is about the NEXT commit
  11  the rule set is broken or empty                exit 2   <- matched nothing against everything
  12  an unexpected crash, and a Ctrl-C              exit 2, never the exit 1 reserved for a finding
  13  real `git commit`s through real installed hooks
  14  the output does not republish what it redacts
  15  argv: --help, an unknown flag, no mode at all
  16  content the DIFF FORMAT disguises as a header    exit 1   <- a measured bypass, `++` lines
  17  the WRAPPER with no guard file on disk           exit 2   <- absence must block, not skip
  18  a DECLARED-empty deny-list                       exit 0   <- the only way to say "none", said

EVERY IDENTIFIER IN THIS FILE IS SYNTHETIC. Nothing below is a real project, a real account, a real
person or a real path — and that is a hard constraint, not a nicety. This file is committed to a
public repository, so a fixture built from a real private name would leak it exactly as a committed
deny-list would, with the added excuse of being "just a test". If a rule cannot be tested without a
real name, the rule is wrong. See identifier_guard.py's module docstring.

`PD_PRIVATE_IDENTIFIERS` is set on EVERY invocation below, including the cases that want no
deny-list at all (where it points at a path that does not exist). Nothing here may read the real
deny-list on this machine: a test that passes because of a local file is not a test, and a test that
PRINTS a real entry is the leak this guard exists to stop.

The ONE exception is case 8's default-location assertion, which must unset the variable to exercise
the `~/.claude/private-identifiers.txt` fallback at all. It redirects `HOME` to an empty temporary
directory instead, and asserts before running that no deny-list exists under it — a strictly
stronger isolation than the variable, since it also removes the real file from the guard's reach.

Run:  python3 identifier_guard_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "identifier_guard.py"

# Synthetic throughout. "zarquon" and "blorptastic" are nonsense words; the account and email are on
# .invalid, the one TLD guaranteed by RFC 2606 never to resolve.
SYNTH_PROJECT = "zarquon-widget"
SYNTH_PROJECT_TWO = "Blorptastic Engine"
SYNTH_ACCOUNT = "quuxifier-labs"
SYNTH_EMAIL = "selftest@example.invalid"
SYNTH_NAME = "Grimblewort Fnordling"
# Deliberately unrelated to SYNTH_NAME. The first draft reused the synthetic SURNAME as the home
# segment, so the fixture path matched the author-name rule as well as the home-path rule — and
# every home-path assertion stayed green with the home-path rule deleted outright. Measured: the
# RED run scored 1 instead of 0. A fixture that satisfies two rules tests neither.
#
# Split, for the same reason push_guard_selftest.py splits its synthetic AWS key: unsplit, this
# file carries a literal absolute home path, the guard blocks the commit that installs its own
# break-test, and the only way past is the --no-verify habit the guard exists to prevent. Every
# home path anywhere else in this file is a placeholder or a machine account by construction.
SYNTH_HOME = "/Users" + "/hoopfrabjous"

# The one spelling of deliberate emptiness. Written out here rather than imported, because a test
# that imports the value under test cannot tell a rename from a rewrite — it would stay green if the
# guard silently started honouring something else. Case 18 asserts this literal equals the guard's
# own `NO_PRIVATE_IDENTIFIERS`, which catches the rename loudly and in one place.
DECLARE_NONE = "!no-private-identifiers"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def new_repo(tmp: Path, remote_url: str | None = None) -> Path:
    """A throwaway repo whose identity is synthetic and LOCAL, so it shadows the real one.

    `git config user.email` in the repo outranks the global value, so the derived-identity rules see
    the synthetic identity and never the machine's own. That is what lets case 7 assert a positive
    finding without this file ever holding a real address.
    """
    repo = tmp / "repo"
    repo.mkdir(parents=True)
    sh("git", "init", "-q", "-b", "feature", cwd=repo)
    sh("git", "config", "user.email", SYNTH_EMAIL, cwd=repo)
    sh("git", "config", "user.name", SYNTH_NAME, cwd=repo)
    if remote_url:
        sh("git", "remote", "add", "origin", remote_url, cwd=repo)
    (repo / "README.md").write_text("# selftest\n")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    return repo


def write_denylist(tmp: Path, entries: list[str] | None = None, raw: bytes | None = None) -> Path:
    path = tmp / "private-identifiers.txt"
    if raw is not None:
        path.write_bytes(raw)
    else:
        body = "# synthetic deny-list — one identifier per line\n\n"
        body += "".join(f"{e}\n" for e in (entries if entries is not None else []))
        path.write_text(body, encoding="utf-8")
    return path


def run_guard(repo: Path, *args: str, denylist: Path | str | None,
              env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run the guard. `denylist=None` UNSETS the variable — see the module docstring's exception.

    Passing None is only legitimate together with a redirected HOME, and the one case that does it
    asserts the redirected home holds no deny-list before running.
    """
    child = {**os.environ, "PD_PRIVATE_IDENTIFIERS": str(denylist), **(env or {})}
    if denylist is None:
        child.pop("PD_PRIVATE_IDENTIFIERS", None)
    proc = subprocess.run([sys.executable, str(GUARD), *args], cwd=repo,
                          capture_output=True, text=True, env=child)
    return proc.returncode, proc.stdout + proc.stderr


def stage(repo: Path, name: str, content: str) -> None:
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    sh("git", "add", "-A", cwd=repo)


def message_file(tmp: Path, text: str) -> Path:
    path = tmp / "COMMIT_EDITMSG"
    path.write_text(text, encoding="utf-8")
    return path


def case_clean() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])
        stage(repo, "app.py", "print('hello')\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("1a a clean staged commit exits 0", code == 0, f"got {code}: {out[:300]}")
        check("1b a clean run says nothing about being blocked", "BLOCKED" not in out, out[:300])

        code, out = run_guard(repo, "--message", str(message_file(tmp, "feat: add a thing\n")),
                              denylist=deny)
        check("1c a clean commit message exits 0", code == 0, f"got {code}: {out[:300]}")


def case_home_path() -> None:
    """A path is the leak that survives every review, because it looks like context."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        stage(repo, "notes.md", f"run it from {SYNTH_HOME}/code/thing\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("2a an absolute home path in staged content is blocked", code == 1,
              f"got {code}: {out[:300]}")
        check("2b it names the rule and the file", "absolute home path" in out and "notes.md" in out,
              out[:300])

        # /home as well as /Users — the rule is about the shape, not about one operating system.
        stage(repo, "notes.md", "run it from /home" + "/hoopfrabjous/code\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("2c a /home path is blocked too", code == 1, f"got {code}: {out[:300]}")

        # The other direction. A placeholder is how documentation is SUPPOSED to write a home path,
        # and a guard that blocks the correct spelling teaches people to stop writing docs.
        stage(repo, "notes.md",
              "run it from /Users/<name>/code, or /home/$USER/code, or ~/code\n"
              "CI checks out under /home/runner/work\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("2d placeholder and machine-account home paths are NOT blocked", code == 0,
              f"got {code}: {out[:300]}")

        # CASE. HOME_PATH was the one rule compiled without re.IGNORECASE while every literal_rule
        # got it, and macOS and Windows filesystems are case-insensitive — so `/users/<name>/x` is a
        # path that resolves, that tools print and that people type. Measured before the fix:
        # exit 0, missed.
        stage(repo, "notes.md", "see " + SYNTH_HOME.lower() + "/code\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("2e a lower-case /users/ home path is blocked (HOME_PATH is case-insensitive)",
              code == 1, f"got {code}: {out[:300]}")

        stage(repo, "notes.md", "see " + "/HOME" + "/hoopfrabjous/code\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("2f an upper-case /HOME/ home path is blocked too", code == 1,
              f"got {code}: {out[:300]}")

        # And the exemptions survive the flag: PLACEHOLDER_SEGMENTS is consulted through .lower(),
        # so a placeholder in a different case must still pass rather than newly blocking.
        stage(repo, "notes.md", "CI checks out under /HOME/RUNNER/work\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("2g placeholder segments are still exempt under the case-insensitive rule", code == 0,
              f"got {code}: {out[:300]}")


def case_home_path_in_message() -> None:
    """The message half. pre-commit runs before this text exists, so only commit-msg can see it."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        msg = message_file(tmp, f"fix: correct the loader\n\nfound it under {SYNTH_HOME}/src\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=deny)
        check("3a an absolute home path in the commit message is blocked", code == 1,
              f"got {code}: {out[:300]}")
        check("3b it names the message and the line", "commit message:" in out
              and "absolute home path" in out, out[:300])

        # And the staged scan cannot substitute for it: the same repo with a CLEAN index passes
        # --staged while the message is dirty. This is the whole reason two hooks exist.
        stage(repo, "app.py", "print('hello')\n")
        code, _ = run_guard(repo, "--staged", denylist=deny)
        check("3c --staged does not and cannot catch a message-only leak", code == 0, f"got {code}")


def case_denylist_in_content() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT, SYNTH_PROJECT_TWO])

        stage(repo, "docs/notes.md", f"ported from the {SYNTH_PROJECT} loader\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("4a a deny-listed name in staged content is blocked", code == 1,
              f"got {code}: {out[:300]}")
        check("4b it says which rule fired", "private deny-list entry" in out, out[:300])

        # Separator- and case-insensitive: one entry has to cover every spelling of the name, or the
        # founder has to remember four spellings at exactly the moment they are not thinking about
        # it. `Blorptastic Engine` must catch blorptastic-engine and BlorptasticEngine.
        for spelling in ("blorptastic-engine", "Blorptastic_Engine", "BLORPTASTICENGINE",
                         "blorptastic.engine"):
            stage(repo, "docs/notes.md", f"see the {spelling} repo\n")
            code, out = run_guard(repo, "--staged", denylist=deny)
            check(f"4c the spelling {spelling!r} of a deny-listed name is still caught", code == 1,
                  f"got {code}: {out[:300]}")

        # And the other direction, so this is not passing because everything is blocked.
        stage(repo, "docs/notes.md", "ported from the upstream loader\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("4d an unrelated word is not blocked", code == 0, f"got {code}: {out[:300]}")


def case_denylist_in_message() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        msg = message_file(tmp, f"feat: reuse the {SYNTH_PROJECT} approach\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=deny)
        check("5a a deny-listed name in the commit message is blocked", code == 1,
              f"got {code}: {out[:300]}")

        # git strips `#` comments and everything below a `commit -v` scissors line before writing
        # the commit, so blocking on them would block a commit over text that was never going into
        # it — and under `commit -v` would duplicate every staged finding.
        msg = message_file(tmp, "feat: a clean subject\n"
                                f"# on branch feature — the {SYNTH_PROJECT} template\n"
                                "# ------------------------ >8 ------------------------\n"
                                f"diff --git a/x b/x\n+see {SYNTH_PROJECT}\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=deny)
        check("5b comment lines and the scissors tail are not scanned", code == 0,
              f"got {code}: {out[:300]}")


def case_denylist_in_path() -> None:
    """A filename leaks in the tree listing with no line of content to match."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        stage(repo, f"docs/{SYNTH_PROJECT}-migration.md", "nothing sensitive in the body\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("6a a deny-listed name in a staged PATH is blocked", code == 1,
              f"got {code}: {out[:300]}")
        check("6b the finding is attributed to the path, not to a line", "path " in out, out[:300])


def case_derived_identity() -> None:
    """Derived at runtime from git config — never hardcoded, in the guard or in this file."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp, remote_url=f"git@github.com:{SYNTH_ACCOUNT}/public-thing.git")
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        stage(repo, "docs/contact.md", f"mail {SYNTH_EMAIL} about it\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("7a the git author email is blocked", code == 1 and "git author email" in out,
              f"got {code}: {out[:300]}")

        stage(repo, "docs/contact.md", f"written by {SYNTH_NAME}\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("7b the git author name is blocked", code == 1 and "git author name" in out,
              f"got {code}: {out[:300]}")

        stage(repo, "docs/contact.md", f"clone from github.com/{SYNTH_ACCOUNT}/other\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("7c the remote account segment is blocked", code == 1
              and "remote account name" in out, f"got {code}: {out[:300]}")

        # Same three rules, over an https remote — git writes both shapes and the parser must read
        # both without a network call of any kind.
        repo2 = new_repo(tmp / "two", remote_url=f"https://github.com/{SYNTH_ACCOUNT}/thing.git")
        stage(repo2, "docs/contact.md", f"clone from {SYNTH_ACCOUNT}/thing\n")
        code, out = run_guard(repo2, "--staged", denylist=deny)
        check("7d an https remote's account segment parses and is blocked", code == 1,
              f"got {code}: {out[:300]}")

        stage(repo, "docs/contact.md", "mail the maintainers about it\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("7e unrelated prose is not blocked by the identity rules", code == 0,
              f"got {code}: {out[:300]}")


def case_missing_denylist() -> None:
    """An ABSENT deny-list is a check that did not run. Exit 2, not 0.

    THIS CASE IS THE INVERSION OF WHAT IT USED TO ASSERT, and the reversal is the point. It formerly
    demanded exit 0 with a printed note, on the reasoning that the deny-list is per-machine and never
    travels with a clone, so the guard has to keep working without it. The note was written, printed,
    and accurate — and it changed nothing, because a git hook acts on an exit code. MEASURED, on the
    real machine, with the real list moved out of reach: a staged file containing a real private
    project name exited 0 and was committable; the identical fixture with the list present exited 1.
    The most likely condition in practice — a fresh clone, a new machine, a renamed file, a different
    `$HOME` — silently disabled the half of the guard the whole design exists for.

    "It has to keep working without it" was the true premise with the wrong conclusion. Working
    without the list means the generic rules still run and the run still refuses to read as clean,
    which is exit 2 — asserted below in both directions, because a guard that exits 2 unconditionally
    would satisfy the must-block half of this case and nothing else.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        absent = tmp / "there-is-no-list-here.txt"

        stage(repo, "app.py", "print('hello')\n")
        code, out = run_guard(repo, "--staged", denylist=absent)
        check("8a a missing deny-list exits 2, not 0 — even on otherwise clean content", code == 2,
              f"got {code}: {out[:300]}")
        check("8b it says the private-name check did not run and is not a clean result",
              "did not run" in out and "not a clean result" in out, out[:300])
        check("8c it names both ways out: install a list, or DECLARE there are none",
              DECLARE_NONE in out and "Deleting the file is not how that is said" in out, out[:300])

        # THE FOUNDER'S FIXTURE, in synthetic form: content that a present deny-list would catch,
        # with the deny-list absent. This is the exact commit that used to be waved through.
        stage(repo, "docs.md", f"we should mention {SYNTH_PROJECT} here\n")
        code, out = run_guard(repo, "--staged", denylist=absent)
        check("8d content a present deny-list would catch is NOT committable when it is absent",
              code == 2, f"got {code}: {out[:300]}")
        present = write_denylist(tmp, [SYNTH_PROJECT])
        code, out = run_guard(repo, "--staged", denylist=present)
        check("8e the same fixture with the list PRESENT is exit 1 — so 8d is about absence, "
              "not about the fixture", code == 1, f"got {code}: {out[:300]}")

        # The generic rules are unaffected by any of this: they are patterns and a runtime lookup,
        # and they need no file. A guard that stopped assembling them would also exit 2 here, so the
        # note is asserted rather than the code — it proves they ran, which a 2 alone does not.
        code, out = run_guard(repo, "--staged", denylist=absent)
        check("8f it does not claim the generic rules were skipped too",
              "private-name check did not run" in out, out[:300])

        msg = message_file(tmp, "fix: nothing of interest\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=absent)
        check("8g the MESSAGE mode fails closed on an absent list as well", code == 2,
              f"got {code}: {out[:300]}")

        # THE DEFAULT LOCATION, not just the override. `PD_PRIVATE_IDENTIFIERS` unset with HOME
        # redirected at an empty directory is the fresh-clone / new-machine case exactly, and it is
        # the one path the env-var fixtures above cannot reach. See the module docstring.
        fakehome = tmp / "fakehome"
        (fakehome / ".claude").mkdir(parents=True)
        check("8h the redirected home really holds no deny-list (fixture precondition)",
              not (fakehome / ".claude" / "private-identifiers.txt").exists(), str(fakehome))
        code, out = run_guard(repo, "--staged", denylist=None, env={"HOME": str(fakehome)})
        check("8i absence at the DEFAULT location fails closed too, not only under the override",
              code == 2, f"got {code}: {out[:300]}")


def case_broken_denylist() -> None:
    """Unreadable, undecodable, empty, or absurdly short — all exit 2, none a silent pass."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        stage(repo, "app.py", "print('hello')\n")           # otherwise clean, so 2 is not a finding

        unreadable = write_denylist(tmp, [SYNTH_PROJECT])
        os.chmod(unreadable, 0o000)
        try:
            code, out = run_guard(repo, "--staged", denylist=unreadable)
            if os.geteuid() == 0:
                print("  skip  9a-9b unreadable deny-list (running as root reads anything)")
            else:
                check("9a an unreadable deny-list exits 2, not 0", code == 2,
                      f"got {code}: {out[:300]}")
                check("9b it says the private-name check did not run",
                      "did not run" in out and "not a clean result" in out, out[:300])
        finally:
            os.chmod(unreadable, 0o644)

        undecodable = write_denylist(tmp, raw=b"# list\nzarquon-\xff\xfewidget\n")
        code, out = run_guard(repo, "--staged", denylist=undecodable)
        check("9c a deny-list that is not valid UTF-8 exits 2", code == 2, f"got {code}: {out[:300]}")
        check("9d it explains that an entry that does not decode does not match",
              "does not decode" in out or "not valid UTF-8" in out, out[:300])

        # PRESENT-BUT-EMPTY is the dangerous one: nothing raises, the loop runs zero times, and the
        # guard would exit 0 having checked for nothing while looking perfectly installed.
        empty = write_denylist(tmp, [])
        code, out = run_guard(repo, "--staged", denylist=empty)
        check("9e an empty deny-list is not a clean guard — it exits 2", code == 2,
              f"got {code}: {out[:300]}")
        check("9f it says how to express deliberate emptiness (the declaration line)",
              DECLARE_NONE in out and "DELIBERATE" in out, out[:300])
        check("9g deleting the file is NOT offered as the way to say it — that is case 8's exit 2",
              "delete the file" not in out.lower(), out[:300])

        short_entry = "qz"
        short = write_denylist(tmp, [short_entry])
        code, out = run_guard(repo, "--staged", denylist=short)
        check("9h an entry too short to be an identifier exits 2", code == 2,
              f"got {code}: {out[:300]}")
        # Asserted DIRECTLY, with no `or` escape. The previous form was
        # `entry not in out.split("only")[0] or "entry on line" in out`, and both clauses passed
        # while the entry was echoed in full: rewording the message so the entry landed after the
        # word "only" satisfied the first, and the second is true of every version of the message.
        # An `or` added to survive rewording instead survived the defect it was guarding.
        #
        # The deny-list PATH is removed first, and only the path: it is a random temp directory that
        # could contain a two-character string by chance, which would be noise rather than a leak.
        scrubbed = out.replace(str(short), "<denylist>")
        check("9i the too-short entry is NOT echoed in the message",
              short_entry not in scrubbed, scrubbed[:300])

        # A directory where a file was expected: a plausible fat-finger, and it must not read clean.
        (tmp / "as-a-dir").mkdir()
        code, out = run_guard(repo, "--staged", denylist=tmp / "as-a-dir")
        check("9j a directory in place of the deny-list exits 2", code == 2,
              f"got {code}: {out[:300]}")


def case_history_is_not_reflagged() -> None:
    """The scan is about the NEXT commit. Re-flagging history is how --no-verify becomes a habit."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        # Committed WITHOUT the guard — the repository as it is found, not as it would have been.
        (repo / f"{SYNTH_PROJECT}-legacy.md").write_text(f"the old {SYNTH_PROJECT} notes\n")
        sh("git", "add", "-A", cwd=repo)
        sh("git", "commit", "-qm", "legacy", cwd=repo)

        stage(repo, f"{SYNTH_PROJECT}-legacy.md", f"the old {SYNTH_PROJECT} notes\nplus a line\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("10a an identifier already in history is not re-flagged on every later commit",
              code == 0, f"got {code}: {out[:300]}")

        # But a NEW line carrying it still blocks — this is "added lines only", not "modified files
        # are exempt".
        stage(repo, "fresh.md", f"a new mention of {SYNTH_PROJECT}\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("10b a newly ADDED line carrying the same name still blocks", code == 1,
              f"got {code}: {out[:300]}")


def _load_guard(name: str):
    spec = importlib.util.spec_from_file_location(name, GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_broken_rule_set() -> None:
    """A rule set that matches nothing is indistinguishable, in the output, from a clean commit.

    push_guard.py learned this one file over: `SECRET_PATTERNS = ()` imports perfectly, iterates
    zero times, and exits 0 having matched nothing against everything. The same shape is available
    here through a bad edit to HOME_PATH, so the guard probes its own rule set against a synthetic
    home path before trusting it to find nothing.
    """
    import re as _re
    ig = _load_guard("identifier_guard_broken_rules")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        deny = write_denylist(tmp, [SYNTH_PROJECT])
        original = ig.HOME_PATH
        # A regex that compiles, imports and matches nothing — the realistic shape of a bad edit.
        ig.HOME_PATH = _re.compile(r"(?!x)x")
        buf = io.StringIO()
        try:
            os.environ["PD_PRIVATE_IDENTIFIERS"] = str(deny)
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = ig.main(["--staged"])
        finally:
            ig.HOME_PATH = original
        out = buf.getvalue()
        check("11a a home-path rule that matches nothing exits 2, not 0", code == 2,
              f"got {code}: {out[:300]}")
        check("11b it says the pattern set is broken rather than reporting nothing",
              "pattern set is broken" in out, out[:300])


def case_crash_and_interrupt() -> None:
    """main()'s handler chain. A crash must not impersonate a finding, nor a finding a crash."""
    ig = _load_guard("identifier_guard_crash")

    def main_with(raised: BaseException) -> tuple[int | None, str]:
        def boom(_args):
            raise raised

        original = ig.run
        ig.run = boom
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = ig.main(["--staged"])
        except BaseException as escaped:                                # noqa: BLE001
            return None, f"{type(escaped).__name__} escaped main(): {escaped}"
        finally:
            ig.run = original
        return code, buf.getvalue()

    code, out = main_with(MemoryError("simulated"))
    check("12a an unexpected crash exits 2, never the 1 reserved for a finding", code == 2,
          f"got {code}: {out[:300]}")
    check("12b it names the crash", "the guard crashed" in out and "MemoryError" in out, out[:300])

    code, out = main_with(KeyboardInterrupt())
    check("12c Ctrl-C exits 2, not 1", code == 2, f"got {code}: {out[:300]}")
    check("12d it says the check did not complete", "did not complete" in out, out[:300])


def case_end_to_end_commit() -> None:
    """Real `git commit`s, through hooks composed by install_hooks.py itself.

    The bug this shape catches is never inside the guard: it is a mismatch between the guard's argv
    contract and the shell wrapper that invokes it, and no in-process case executes the wrapper.
    push_guard.py shipped exactly that once — a revision that rejected any argv returned 2 on every
    push on the machine, and the only way past was --no-verify.

    The hooks are rendered by `ih.write_hook` rather than written by hand: hand-composing them would
    reimplement the function under test, and `write_hook`'s placement logic is what decides whether
    our block runs at all in a repository that already had a hook.

    NOTE: the templates hardcode $HOME/.claude/.../identifier_guard.py, so this case exercises the
    INSTALLED guard. If that is not this file's sibling, the case says so rather than passing.
    """
    ih = _load_install_hooks()

    hooked = Path(os.path.expanduser(
        "~/.claude/skills/progressive-disclosure/scripts/identifier_guard.py"))
    if hooked.resolve() != GUARD.resolve():
        check("13 the hook templates point at the guard under test", False,
              f"templates run {hooked}, this suite tests {GUARD}")
        return

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])
        env = {**os.environ, "PD_PRIVATE_IDENTIFIERS": str(deny)}

        ih.write_hook(repo / ".git" / "hooks" / "pre-commit",
                      ih.PRE_COMMIT.format(begin=ih.BEGIN, end=ih.END, flags=" --readme",
                                           identifier=ih.PRE_COMMIT_IDENTIFIER))
        ih.write_hook(repo / ".git" / "hooks" / "commit-msg",
                      ih.COMMIT_MSG.format(begin=ih.BEGIN, end=ih.END))

        def commit(message: str) -> tuple[int, str]:
            sh("git", "add", "-A", cwd=repo)
            p = subprocess.run(["git", "commit", "-m", message], cwd=repo,
                               capture_output=True, text=True, env=env)
            return p.returncode, p.stdout + p.stderr

        # A genuinely clean commit must SUCCEED through the real wrapper. "Blocks everything"
        # satisfies every other assertion here.
        (repo / "app.py").write_text("print('ok')\n")
        rc, out = commit("feat: add app")
        check("13a a clean commit succeeds through the real hooks", rc == 0, f"got {rc}: {out[:400]}")
        head_after_clean = sh("git", "rev-parse", "HEAD", cwd=repo).strip()

        (repo / "leak.md").write_text(f"see {SYNTH_HOME}/code\n")
        rc, out = commit("docs: add notes")
        check("13b a real commit of a staged home path FAILS", rc != 0, f"got {rc}: {out[:400]}")
        check("13c the finding reached the user through the pre-commit wrapper",
              "absolute home path" in out, out[:400])
        sh("git", "reset", "-q", cwd=repo)
        (repo / "leak.md").unlink()

        (repo / "fine.md").write_text("nothing to see\n")
        rc, out = commit(f"docs: notes from {SYNTH_PROJECT}")
        check("13d a real commit whose MESSAGE carries a deny-listed name FAILS", rc != 0,
              f"got {rc}: {out[:400]}")
        check("13e the finding reached the user through the commit-msg wrapper",
              "private deny-list entry" in out, out[:400])

        check("13f no blocked commit was created", sh("git", "rev-parse", "HEAD", cwd=repo).strip()
              == head_after_clean, "HEAD moved on a blocked commit")

        # --public off must take BOTH halves away again, and leave the route check behind.
        ih.write_hook(repo / ".git" / "hooks" / "pre-commit",
                      ih.PRE_COMMIT.format(begin=ih.BEGIN, end=ih.END, flags=" --readme",
                                           identifier=""))
        removed = ih.remove_hook_block(repo / ".git" / "hooks" / "commit-msg")
        rc, out = commit(f"docs: notes from {SYNTH_PROJECT}")
        check("13g dropping --public removes both halves", rc == 0 and removed == "removed",
              f"got {rc} / {removed}: {out[:400]}")
        check("13h and the route-check block survived the removal",
              ih.BEGIN in (repo / ".git" / "hooks" / "pre-commit").read_text(), "block gone")


def case_output_does_not_republish() -> None:
    """A guard whose OUTPUT carries the identifier in full has moved the leak, not stopped it.

    Hook output gets pasted into transcripts, issues and agent reports. The file and line number are
    what make a finding actionable; the whole string never was. The PATH case is the sharp one — the
    location column is where the identifier reappears if only the match is redacted.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        stage(repo, "docs/notes.md", f"ported from the {SYNTH_PROJECT} loader\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("14a a content finding does not print the identifier in full",
              code == 1 and SYNTH_PROJECT not in out, out[:400])

        stage(repo, f"docs/{SYNTH_PROJECT}.md", "body\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("14b a PATH finding does not print the identifier in the location column either",
              code == 1 and SYNTH_PROJECT not in out, out[:400])

        msg = message_file(tmp, f"feat: from {SYNTH_PROJECT}\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=deny)
        check("14c a message finding does not print the identifier in full",
              code == 1 and SYNTH_PROJECT not in out, out[:400])


def case_argv() -> None:
    """A malformed invocation is a check that did not run, not a clean one."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])
        # Something that WOULD be found, so "exit 2 because it scanned nothing" cannot be confused
        # with "exit 2 because argv was rejected before scanning".
        stage(repo, "notes.md", f"see {SYNTH_HOME}/code\n")

        code, out = run_guard(repo, "--help", denylist=deny)
        check("15a --help exits 0", code == 0, f"got {code}")
        check("15b --help does not print anything that looks like a finding",
              "BLOCKED" not in out, out[:200])

        code, _ = run_guard(repo, "--nonsense", denylist=deny)
        check("15c an unrecognised flag exits 2, not 0 and not 1", code == 2, f"got {code}")

        code, _ = run_guard(repo, denylist=deny)
        check("15d no mode at all exits 2 rather than silently scanning nothing", code == 2,
              f"got {code}")

        code, out = run_guard(repo, "--staged", "--message", "x", denylist=deny)
        check("15e the two modes are mutually exclusive", code == 2, f"got {code}")

        # Not a git repository at all: the scan cannot run, so it must not report clean.
        code, out = run_guard(tmp, "--staged", denylist=deny)
        check("15f outside a git repository the scan exits 2, never 0", code == 2,
              f"got {code}: {out[:300]}")


def _load_install_hooks():
    spec = importlib.util.spec_from_file_location("install_hooks_under_test_ig",
                                                  GUARD.parent / "install_hooks.py")
    ih = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ih)
    return ih


def case_missing_guard_is_not_a_skip() -> None:
    """A guard that is not on disk must BLOCK, not skip. The invariant, enforced from outside.

    identifier_guard.py's governing rule is "a scan that did not run must never read as clean", and
    the script honours it on every path inside itself. The wrapper did not: `if [ -f ] … fi` meant a
    missing or renamed guard produced exit 0 and no output at all — the most likely failure of the
    guard, reading as the cleanest possible commit, three files away from the sentence forbidding it.

    Not hypothetical: install.sh's install_tree replaces the skill directory wholesale, so a file
    present in ~/.claude but absent from the packaged skill is deleted by a re-install.

    Exercised by running the RENDERED hook directly rather than through `git commit`, because git
    collapses every non-zero hook exit into its own 1 — the 1-vs-2 distinction the template claims
    is only observable at the hook's own boundary.
    """
    ih = _load_install_hooks()
    real = '"$HOME/.claude/skills/progressive-disclosure/scripts/identifier_guard.py"'

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])
        env = {**os.environ, "PD_PRIVATE_IDENTIFIERS": str(deny)}
        missing = tmp / "no-guard-here" / "identifier_guard.py"

        def render(label: str, template: str, **kw: str) -> tuple[str, str]:
            """(hook as installed, hook with the guard path pointed at nothing)."""
            good = template.format(begin=ih.BEGIN, end=ih.END, **kw)
            bad = good.replace(real, f'"{missing}"')
            check(f"17-setup ({label}) the template resolves the guard through $HOME/.claude/…",
                  bad != good,
                  "the substitution found nothing — this case would test the wrong thing")
            return good, bad

        def run_hook(text: str, *argv: str, deny_override: Path | None = None) -> tuple[int, str]:
            path = repo / ".git" / "hooks" / "under-test"
            path.write_text(text, encoding="utf-8")
            e = dict(env)
            if deny_override is not None:
                e["PD_PRIVATE_IDENTIFIERS"] = str(deny_override)
            p = subprocess.run(["sh", str(path), *argv], cwd=repo, capture_output=True,
                               text=True, env=e)
            return p.returncode, p.stdout + p.stderr

        good_pre, bad_pre = render("pre-commit", ih.PRE_COMMIT, flags=" --readme",
                                   identifier=ih.PRE_COMMIT_IDENTIFIER)
        stage(repo, "app.py", "print('hello')\n")

        rc, out = run_hook(good_pre)
        check("17a the pre-commit wrapper exits 0 on a clean index when the guard IS present",
              rc == 0, f"got {rc}: {out[:300]}")

        rc, out = run_hook(bad_pre)
        check("17b a MISSING guard makes pre-commit exit 2, not 0", rc == 2, f"got {rc}: {out[:400]}")
        check("17c and it says the content was not scanned rather than saying nothing",
              "BLOCKED" in out and "NOT been scanned" in out, out[:400])

        # 1 and 2 must stay distinguishable through the wrapper: `|| exit 1` collapsed them.
        stage(repo, "leak.md", f"see {SYNTH_HOME}/code\n")
        rc, out = run_hook(good_pre)
        check("17d a finding is exit 1 through the wrapper", rc == 1, f"got {rc}: {out[:300]}")

        # And a guard that COULD NOT RUN stays a 2 through the same wrapper. `|| exit 1` collapsed
        # the two, contradicting the template's own comment; the code is now propagated.
        # Written into its own directory so it cannot clobber `deny`, which the rest of the case
        # still needs.
        (tmp / "emptylist").mkdir()
        rc, out = run_hook(good_pre, deny_override=write_denylist(tmp / "emptylist", []))
        check("17e a guard that could not run stays exit 2 through the wrapper, not 1", rc == 2,
              f"got {rc}: {out[:300]}")

        sh("git", "reset", "-q", cwd=repo)
        (repo / "leak.md").unlink()

        good_msg, bad_msg = render("commit-msg", ih.COMMIT_MSG)
        msg = message_file(tmp, "feat: a clean subject\n")

        rc, out = run_hook(good_msg, str(msg))
        check("17f the commit-msg wrapper exits 0 on a clean message when the guard IS present",
              rc == 0, f"got {rc}: {out[:300]}")

        rc, out = run_hook(bad_msg, str(msg))
        check("17g a MISSING guard makes commit-msg exit 2, not 0", rc == 2, f"got {rc}: {out[:400]}")
        check("17h and it says the MESSAGE was not scanned",
              "BLOCKED" in out and "not been scanned" in out.lower(), out[:400])


def case_diff_shape() -> None:
    """Content the DIFF FORMAT disguises as a header. A measured bypass, not a hypothetical.

    `git diff` prefixes every added line with `+`, so an added line whose own content starts `++`
    arrives as `+++ …` — indistinguishable, to a prefix test, from the `+++ b/<path>` file header.
    The loop used to skip any line starting `+++` and therefore never scanned it. Reproduced against
    the guard as it stood: a file whose single line was `++ <home path>` exited 0, while the same
    content behind one `+` exited 1.

    The carriers are ordinary. A committed `.patch` or `.diff` fixture has `+++ <path>` in its BODY;
    `++i;` opens a line in C, C++, Java, JavaScript, Go and Rust. Both are exactly the content a
    repository about tooling accumulates.

    The fix tracks hunk state rather than testing prefixes, so the assertions below also pin the
    thing that could break in exchange: file attribution across a multi-file diff, and deletions,
    whose `+++ /dev/null` header must still not be read as content.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)
        deny = write_denylist(tmp, [SYNTH_PROJECT])

        stage(repo, "incr.c", f"++ {SYNTH_HOME}/secret\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("16a a line whose CONTENT begins '++' is scanned, not skipped as a header", code == 1,
              f"got {code}: {out[:300]}")
        check("16b the finding is attributed to the file and line, not to '?'",
              "incr.c:1" in out, out[:300])

        # The other direction, so 16a is not passing because everything is blocked.
        stage(repo, "incr.c", "++counter;\n++total;\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("16c a clean line beginning '++' is still not blocked", code == 0,
              f"got {code}: {out[:300]}")

        # The realistic carrier: a committed patch fixture whose own body is a diff header.
        stage(repo, "fixtures/sample.patch",
              "diff --git a/x b/x\n"
              "--- a/x\n"
              f"+++ {SYNTH_HOME}/b\n"
              "@@ -0,0 +1 @@\n"
              "+hello\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("16d a committed .patch whose body carries a '+++ <home path>' header is blocked",
              code == 1, f"got {code}: {out[:300]}")

        # Hunk-state tracking must not lose the current filename across files. A clean first file
        # and a dirty second one: the finding has to name the SECOND.
        sh("git", "reset", "-q", cwd=repo)
        for p in ("incr.c", "fixtures/sample.patch"):
            (repo / p).unlink(missing_ok=True)
        stage(repo, "aaa-clean.md", "nothing of interest here\n")
        stage(repo, "zzz-dirty.md", f"see {SYNTH_HOME}/code\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("16e in a multi-file diff the finding is attributed to the right file",
              code == 1 and "zzz-dirty.md:1" in out and "aaa-clean.md" not in out, f"got {code}: {out[:300]}")

        # A DELETION emits `+++ /dev/null` and only `-` lines. It must produce no finding — the
        # removed content is not entering anything — and must not crash.
        sh("git", "commit", "-qm", "add files", cwd=repo)
        (repo / "zzz-dirty.md").unlink()
        sh("git", "add", "-A", cwd=repo)
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("16f deleting a file carrying an identifier is not a finding", code == 0,
              f"got {code}: {out[:300]}")


def case_declared_empty_denylist() -> None:
    """`!no-private-identifiers` — the only spelling of deliberate emptiness, and it must be said.

    Case 8 makes absence fatal. That would be a trap for the one honest case — a public repository
    whose owner genuinely has no private names — without a way to say so, so there is one, and its
    single design requirement is that NO ACCIDENT CAN PRODUCE IT. A deleted file is what a fresh
    clone looks like; an empty file is what a truncated write looks like; a line of text that says
    what it means is what a decision looks like. All three are asserted here, against each other.

    The declaration is not free and this case does not pretend otherwise: 18d asserts that a name a
    deny-list would have caught is NOT caught under a declaration. That is the cost of the escape
    hatch, stated as a test rather than left to be discovered, and it is why 18b requires the run to
    announce the declaration on every commit rather than passing in silence.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)

        ig = _load_guard("identifier_guard_declaration")
        check("18a the guard's declaration constant is the string this file tests",
              ig.NO_PRIVATE_IDENTIFIERS == DECLARE_NONE,
              f"guard says {ig.NO_PRIVATE_IDENTIFIERS!r}, test says {DECLARE_NONE!r}")

        declared = write_denylist(tmp, [DECLARE_NONE])
        stage(repo, "app.py", "print('hello')\n")
        code, out = run_guard(repo, "--staged", denylist=declared)
        check("18b a declared-empty deny-list is a clean run", code == 0, f"got {code}: {out[:300]}")
        check("18c and it SAYS the names were skipped by declaration, not by default",
              "declaration rather than by default" in out, out[:300])

        stage(repo, "docs.md", f"we should mention {SYNTH_PROJECT} here\n")
        code, out = run_guard(repo, "--staged", denylist=declared)
        check("18d under a declaration a would-be deny-listed name is NOT caught — the stated cost",
              code == 0, f"got {code}: {out[:300]}")

        # The half that keeps 18d from being a hole: the generic rules are untouched by any of this.
        stage(repo, "docs.md", f"see {SYNTH_HOME}/code\n")
        code, out = run_guard(repo, "--staged", denylist=declared)
        check("18e the generic rules STILL fire under a declaration", code == 1,
              f"got {code}: {out[:300]}")
        msg = message_file(tmp, f"fix: from {SYNTH_HOME}/code\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=declared)
        check("18f and they still fire on the MESSAGE under a declaration", code == 1,
              f"got {code}: {out[:300]}")

        sh("git", "reset", "-q", cwd=repo)
        (repo / "docs.md").unlink()
        stage(repo, "app.py", "print('hello')\n")

        # A declaration ALONGSIDE entries is what merging two machines' lists produces. Honouring
        # either half would be picking, unprompted, whether to check for private names at all.
        both = write_denylist(tmp, [DECLARE_NONE, SYNTH_PROJECT])
        code, out = run_guard(repo, "--staged", denylist=both)
        check("18g a declaration alongside real entries is a contradiction, exit 2", code == 2,
              f"got {code}: {out[:300]}")
        check("18h and it says the private-name check did not run", "did not run" in out, out[:300])

        # Spelling. Case-insensitive and comment/blank tolerant, because those are how a human
        # actually writes the line — but nothing that merely RESEMBLES it counts.
        upper = write_denylist(tmp, [DECLARE_NONE.upper()])
        code, out = run_guard(repo, "--staged", denylist=upper)
        check("18i the declaration is case-insensitive", code == 0, f"got {code}: {out[:300]}")

        commented = tmp / "commented.txt"
        commented.write_text(f"# no private names on this machine\n\n  {DECLARE_NONE}  \n",
                             encoding="utf-8")
        code, out = run_guard(repo, "--staged", denylist=commented)
        check("18j surrounding comments, blanks and whitespace do not break it", code == 0,
              f"got {code}: {out[:300]}")

        # A COMMENTED-OUT declaration is not a declaration. This is the near-miss that matters: the
        # `#`-strip runs first, so `# !no-private-identifiers` leaves an empty line and the file is
        # the empty one — exit 2, not a quiet pass.
        commented_out = tmp / "commented-out.txt"
        commented_out.write_text(f"# {DECLARE_NONE}\n", encoding="utf-8")
        code, out = run_guard(repo, "--staged", denylist=commented_out)
        check("18k a declaration inside a COMMENT does not count — exit 2", code == 2,
              f"got {code}: {out[:300]}")

        # And a misspelling is an entry, not a declaration: it is long enough to be a valid
        # identifier, so it silently becomes a rule rather than a pass. The file is therefore a
        # normal populated list and exits 0 here — but the DECLARATION path was not taken, which is
        # what 18m proves by showing the announcement is absent.
        typo = write_denylist(tmp, ["!no-private-identifier"])
        code, out = run_guard(repo, "--staged", denylist=typo)
        check("18l a misspelled declaration does not silently disable the check", code == 0,
              f"got {code}: {out[:300]}")
        check("18m and it is treated as an entry, not as a declaration",
              "declaration rather than by default" not in out, out[:300])


def main() -> int:
    if not GUARD.exists():
        print(f"identifier_guard.py not found at {GUARD}", file=sys.stderr)
        return 2

    print("identifier_guard break-test")
    for case in (case_clean, case_home_path, case_home_path_in_message, case_denylist_in_content,
                 case_denylist_in_message, case_denylist_in_path, case_derived_identity,
                 case_missing_denylist, case_broken_denylist, case_history_is_not_reflagged,
                 case_broken_rule_set, case_crash_and_interrupt, case_end_to_end_commit,
                 case_output_does_not_republish, case_argv, case_diff_shape,
                 case_missing_guard_is_not_a_skip, case_declared_empty_denylist):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the guard blocks every case it is supposed to block, and passes the rest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
