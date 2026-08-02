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
   8  NO deny-list installed                         exit 2   <- the list is MANDATORY; nothing ran
   9  a deny-list that cannot be read or is broken   exit 2, never a silent pass
  10  an identifier already in history               exit 0   <- the scan is about the NEXT commit
  11  the rule set is broken or empty                exit 2   <- matched nothing against everything
  12  an unexpected crash, and a Ctrl-C              exit 2, never the exit 1 reserved for a finding
  13  real `git commit`s through real installed hooks
  14  the output does not republish what it redacts
  15  argv: --help, an unknown flag, no mode at all
  16  content the DIFF FORMAT disguises as a header    exit 1   <- a measured bypass, `++` lines
  17  the WRAPPER with no guard file on disk           exit 2   <- absence must block, not skip
  18  there is NO opt-out, by construction             exit 2   <- the removed hatch stays removed

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
import unicodedata
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

# THE REMOVED OPT-OUT. This string used to be a directive meaning "deliberately no private names",
# and honouring it was a fail-open: a one-character transposition made it an ordinary entry, the file
# read as populated, and a staged private name exited 0. It is kept here ONLY as the thing case 18
# proves is gone — from the guard's source, from its namespace, and from its behaviour. A literal, so
# that reintroducing the feature under any name cannot make this file green by importing it.
REMOVED_OPT_OUT = "!no-private-identifiers"
# A one-character transposition of it. Under the old code this was a legal entry that matched
# nothing, so the run passed while the guard checked for nothing.
MISTYPED_OPT_OUT = "!no-private-identifer"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def sh(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def new_repo(tmp: Path, remote_url: str | None = None, user_name: str = SYNTH_NAME) -> Path:
    """A throwaway repo whose identity is synthetic and LOCAL, so it shadows the real one.

    `git config user.email` in the repo outranks the global value, so the derived-identity rules see
    the synthetic identity and never the machine's own. That is what lets case 7 assert a positive
    finding without this file ever holding a real address.

    `user_name` is overridable for exactly one caller: case 11's dead-rule probe needs an identity
    that compiles to a pattern matching the empty string, which no deny-list entry can be any more
    (`read_denylist` refuses that shape at parse time) and which therefore has to arrive from git
    config to reach the probe at all.
    """
    repo = tmp / "repo"
    repo.mkdir(parents=True)
    sh("git", "init", "-q", "-b", "feature", cwd=repo)
    sh("git", "config", "user.email", SYNTH_EMAIL, cwd=repo)
    sh("git", "config", "user.name", user_name, cwd=repo)
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
    without the list means refusing to read as clean, which is exit 2 — asserted below in both
    directions, because a guard that exits 2 unconditionally would satisfy the must-block half of
    this case and nothing else.

    IT IS NOT "the private-name half was skipped and the generic half ran". The deny-list loads
    before anything is scanned, so an absent list VOIDS THE WHOLE RUN. An earlier revision of the
    guard claimed the generic rules were "unaffected in every case" and "never skipped"; 8i now
    asserts the opposite of that claim, by staging content the generic rules WOULD have caught and
    requiring that no such finding is reported.

    (This sentence said "8f" until it was corrected. 8f is the RESTORE.md pointer; the reference went
    stale when 8e was deleted and the letters below it shifted up by one. Recorded rather than
    quietly fixed because it is the same prose-disagrees-with-assertion defect this whole case exists
    to punish, occurring inside the fix for it — an assertion letter in a comment is a reference with
    no compiler behind it, and the only thing keeping it true is somebody re-reading it.)
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
        # THE REMEDY, in full, because a block whose way out is not stated is the lockout this
        # design is accused of being. Three parts, each asserted separately so a reworded message
        # that quietly drops one fails here rather than in somebody's terminal at 1 a.m. No
        # repository name belongs here — this file is vendored into a public repository.
        check("8c the message names the path it looked at, so there is nothing to guess",
              str(absent) in out, out[:600])
        check("8d it names the one-identifier-per-line format",
              "one identifier per line" in out, out[:600])
        check("8f it points at the restore doc", "RESTORE.md" in out, out[:600])

        # THE FOUNDER'S FIXTURE, in synthetic form: content that a present deny-list would catch,
        # with the deny-list absent. This is the exact commit that used to be waved through.
        stage(repo, "docs.md", f"we should mention {SYNTH_PROJECT} here\n")
        code, out = run_guard(repo, "--staged", denylist=absent)
        check("8g content a present deny-list would catch is NOT committable when it is absent",
              code == 2, f"got {code}: {out[:300]}")
        present = write_denylist(tmp, [SYNTH_PROJECT])
        code, out = run_guard(repo, "--staged", denylist=present)
        check("8h the same fixture with the list PRESENT is exit 1 — so 8g is about absence, "
              "not about the fixture", code == 1, f"got {code}: {out[:300]}")

        # THE RUN IS VOIDED, NOT SHRUNK. The predecessor of this assertion checked that the output
        # contained "private-name check did not run" — a string the message it was reading always
        # contains, whatever the guard does. It could not fail, so it established nothing.
        #
        # What is actually worth pinning is the claim the guard used to make and that is false: that
        # the generic rules run anyway. Stage a home path, which the generic rules catch with no
        # deny-list involved, and require that NO such finding appears — because loading the list
        # happens before any scanning, so nothing was scanned at all.
        stage(repo, "docs.md", f"see {SYNTH_HOME}/code\n")
        code, out = run_guard(repo, "--staged", denylist=absent)
        check("8i an absent list VOIDS the run rather than shrinking it — the generic rules do not "
              "report either", code == 2 and "absolute home path" not in out, f"got {code}: {out[:400]}")
        code, out = run_guard(repo, "--staged", denylist=present)
        check("8j the same home path IS reported once the list loads — so 8i is about the void, "
              "not about the fixture", code == 1 and "absolute home path" in out,
              f"got {code}: {out[:300]}")

        sh("git", "reset", "-q", cwd=repo)
        (repo / "docs.md").unlink()
        stage(repo, "app.py", "print('hello')\n")

        msg = message_file(tmp, "fix: nothing of interest\n")
        code, out = run_guard(repo, "--message", str(msg), denylist=absent)
        check("8k the MESSAGE mode fails closed on an absent list as well", code == 2,
              f"got {code}: {out[:300]}")

        # THE DEFAULT LOCATION, not just the override. `PD_PRIVATE_IDENTIFIERS` unset with HOME
        # redirected at an empty directory is the fresh-clone / new-machine case exactly, and it is
        # the one path the env-var fixtures above cannot reach. See the module docstring.
        fakehome = tmp / "fakehome"
        (fakehome / ".claude").mkdir(parents=True)
        check("8l the redirected home really holds no deny-list (fixture precondition)",
              not (fakehome / ".claude" / "private-identifiers.txt").exists(), str(fakehome))
        code, out = run_guard(repo, "--staged", denylist=None, env={"HOME": str(fakehome)})
        check("8m absence at the DEFAULT location fails closed too, not only under the override",
              code == 2, f"got {code}: {out[:300]}")
        # And the message that says so does not print the home directory it was looking under. This
        # is the guard's own output being held to the guard's own rule: the default path is
        # `$HOME/.claude/private-identifiers.txt`, and printing it verbatim publishes the account
        # segment that `home_path_rule` blocks everyone else's files for carrying.
        check("8n the message abbreviates the home segment rather than printing it",
              str(fakehome) not in out and "~/.claude/private-identifiers.txt" in out, out[:500])


def case_broken_denylist() -> None:
    """Unreadable, undecodable, empty, or unusable — all exit 2, none a silent pass.

    "Unusable" is the group that grew. An entry the matcher compiles into a rule that can never fire
    is worse than no entry at all: the list looks longer than it is, and the line you are relying on
    is the one doing nothing. Three shapes reach that state, all three were reachable, and one of
    them was sitting inert in the real deny-list on this machine.
    """
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
        check("9f it states the one-step remedy rather than only the complaint",
              "one identifier per line" in out and "RESTORE.md" in out,
              out[:600])
        # There is nothing to "declare". The message must not offer an opt-out, because there is
        # none, and a message that gestures at one teaches the reader to go looking for the syntax
        # that was removed for being a fail-open.
        check("9g no opt-out is offered — the removed declaration is not mentioned, and the "
              "message says outright that there is no way to switch the check off",
              REMOVED_OPT_OUT not in out and "no way to declare" in out.lower(), out[:600])
        # Asserted on the STEM, not on one phrasing. The previous form was `"delete the file" not in
        # out.lower()`, which pinned a single exact wording: "delete this file", "deleting it" and
        # "you may delete the list" all satisfied it while saying the forbidden thing. The stem
        # covers every inflection, and no legitimate message here wants it — the refusals say
        # "remove that line", and the deny-list's own header comment used to say "DELETE this file"
        # and was wrong.
        check("9h deleting the file is NOT offered as a way out either — that is case 8's exit 2",
              "delet" not in out.lower(), out[:300])

        short_entry = "qz"
        short = write_denylist(tmp, [short_entry])
        code, out = run_guard(repo, "--staged", denylist=short)
        check("9i an entry too short to be an identifier exits 2", code == 2,
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
        check("9j the too-short entry is NOT echoed in the message",
              short_entry not in scrubbed, scrubbed[:300])

        # A directory where a file was expected: a plausible fat-finger, and it must not read clean.
        (tmp / "as-a-dir").mkdir()
        code, out = run_guard(repo, "--staged", denylist=tmp / "as-a-dir")
        check("9k a directory in place of the deny-list exits 2", code == 2,
              f"got {code}: {out[:300]}")

        # A BACKSLASH ENTRY. `Two\ Words` is what pasting a shell-escaped name produces, and the
        # matcher escapes the backslash literally — so the rule hunts for a backslash in the scanned
        # text and never finds one. This exact shape was sitting inert in the real deny-list on this
        # machine, duplicating a plain entry that was doing the actual work, so nothing looked wrong.
        # It must be refused, not compiled: an accepted entry that cannot fire is unauditable.
        escaped = write_denylist(tmp, [SYNTH_PROJECT_TWO.replace(" ", "\\ ")])
        code, out = run_guard(repo, "--staged", denylist=escaped)
        check("9l an entry containing a backslash is refused, not compiled into a dead rule",
              code == 2, f"got {code}: {out[:400]}")
        check("9m it says so without echoing the entry",
              "backslash" in out and SYNTH_PROJECT_TWO.split()[0] not in out, out[:400])

        # And the other direction, so 9l is about the backslash and not about the name: the same
        # name written plainly loads and fires.
        plain = write_denylist(tmp, [SYNTH_PROJECT_TWO])
        stage(repo, "notes.md", f"the {SYNTH_PROJECT_TWO} rewrite\n")
        code, out = run_guard(repo, "--staged", denylist=plain)
        check("9n the same name written UNESCAPED loads and blocks", code == 1,
              f"got {code}: {out[:300]}")
        sh("git", "reset", "-q", cwd=repo)
        (repo / "notes.md").unlink()
        stage(repo, "app.py", "print('hello')\n")

        # A SEPARATOR-ONLY entry passes the length floor and compiles to `[-_. ]*`, which matches the
        # empty string at position 0 of every text. The scanner reads that empty match as no match,
        # so the rule is dead everywhere while the file looks populated.
        sep_only = write_denylist(tmp, ["-_-"])
        code, out = run_guard(repo, "--staged", denylist=sep_only)
        check("9o an entry of nothing but separators is refused", code == 2, f"got {code}: {out[:400]}")
        # PINNED TO THE PARSE-TIME REFUSAL SPECIFICALLY. Two independent mechanisms return 2 for this
        # fixture — `read_denylist`'s separator-only check and `self_probe`'s matches-the-empty-string
        # backstop — so `code == 2` alone stayed green with EITHER of them deleted. The message is
        # what distinguishes them: only the parser says "unusable entry on line N". The probe's own
        # half is pinned independently by 11d, which reaches it through a DERIVED rule that the
        # parser never sees.
        # The distinguishing string has to be chosen with care: BOTH messages say "matches the empty
        # string", because the parser's refusal explains the same underlying defect the probe detects.
        # "that rule is dead" belongs only to the probe, and "unusable entry on line" only to the
        # parser, so the pair separates them.
        check("9o2 and it is the PARSER that refused it, not the probe catching it downstream",
              "unusable entry on line" in out and "separator characters" in out
              and "that rule is dead" not in out, out[:400])

        # A BOM must not disable the first entry. The file is mandatory now, so this is no longer a
        # 0-vs-2 question — it is a 1-vs-0 one, which is worse: the list loads, the run looks
        # healthy, and the first name in it silently stops matching. MEASURED before the fix: with a
        # BOM the guard exited 0 on content the same file without a BOM blocked.
        bom = write_denylist(tmp, raw=b"\xef\xbb\xbf" + f"{SYNTH_PROJECT}\n".encode("utf-8"))
        stage(repo, "notes.md", f"ported from the {SYNTH_PROJECT} loader\n")
        code, out = run_guard(repo, "--staged", denylist=bom)
        check("9p a BOM does not disable the first deny-list entry", code == 1,
              f"got {code}: {out[:300]}")
        nobom = write_denylist(tmp, raw=(SYNTH_PROJECT + "\n").encode("utf-8"))
        code, out = run_guard(repo, "--staged", denylist=nobom)
        check("9q the same file without a BOM blocks too — so 9p is about the BOM, not the fixture",
              code == 1, f"got {code}: {out[:300]}")
        sh("git", "reset", "-q", cwd=repo)
        (repo / "notes.md").unlink()
        stage(repo, "app.py", "print('hello')\n")

        # THE INVISIBLE-AND-LOOKALIKE CLASS. Every entry below compiles into a syntactically perfect
        # rule that then hunts for a character no ordinary file contains, so the list looks longer
        # than it is and the line you are relying on does nothing. MEASURED before the fix, each of
        # these five with the plain ASCII spelling staged: EXIT 0, committable, override confirmed in
        # effect. The characters are written as escapes, never as themselves — a test file carrying a
        # literal zero-width space is one careless editor away from being the bug it is testing.
        #
        # TWO OUTCOMES, deliberately different. A Unicode DASH or SPACE is FOLDED — the entry works —
        # because the author cannot see the difference between it and a hyphen and should not have
        # to. Everything else is REFUSED, because there is no ASCII character it plausibly stood for.
        stage(repo, "notes.md", f"ported from the {SYNTH_PROJECT} loader\n")
        en_dash = write_denylist(tmp, [SYNTH_PROJECT.replace("-", "\u2013")])   # EN DASH
        code, out = run_guard(repo, "--staged", denylist=en_dash)
        check("9r an entry written with an en dash still matches the ASCII hyphen in the content",
              code == 1, f"got {code}: {out[:400]}")
        sh("git", "reset", "-q", cwd=repo)
        (repo / "notes.md").unlink()
        stage(repo, "app.py", "print('hello')\n")
        # The other direction, so 9r is not passing because the guard blocks everything: the same
        # folded entry against content that does not contain the name is a clean run.
        code, out = run_guard(repo, "--staged", denylist=en_dash)
        check("9s the same folded entry on unrelated content is exit 0, so 9r is a real match",
              code == 0, f"got {code}: {out[:400]}")

        for label, char, entry in (
                ("a zero-width space", "U+200B", SYNTH_PROJECT.replace("-", "\u200b")),
                ("a soft hyphen", "U+00AD", SYNTH_PROJECT.replace("-", "\u00ad")),
                ("an interior tab", "U+0009", SYNTH_PROJECT.replace("-", "\t")),
                ("a non-leading BOM", "U+FEFF", SYNTH_PROJECT + "\ufeff")):
            path = write_denylist(tmp, [entry])
            code, out = run_guard(repo, "--staged", denylist=path)
            check(f"9t an entry containing {label} is refused, not compiled into a dead rule",
                  code == 2, f"got {code}: {out[:400]}")
            # The CHARACTER is named — the author cannot see it, so "there is a bad character
            # somewhere in line 2" would be unactionable — and the ENTRY still is not echoed.
            check(f"9u it names {char} without echoing the entry",
                  char in out and SYNTH_PROJECT.split("-")[0] not in out, out[:400])

        # A NON-ASCII LETTER IS NOT REFUSED, and this is the assertion that keeps the rule above from
        # being quietly widened into "ASCII only". `GIT_OVERRIDES` turns core.quotepath off precisely
        # so a name in a non-Latin script survives the trip from git to the scanner; a blanket
        # ASCII-only rule would break that real, documented case to close a theoretical one.
        accented = "Zarqu\u00f6n-Widget"     # LATIN SMALL LETTER O WITH DIAERESIS
        stage(repo, "notes.md", f"ported from the {accented} loader\n")
        code, out = run_guard(repo, "--staged", denylist=write_denylist(tmp, [accented]))
        check("9v a non-ASCII LETTER in an entry is accepted and matches — the rule is not "
              "ASCII-only", code == 1, f"got {code}: {out[:400]}")
        sh("git", "reset", "-q", cwd=repo)
        (repo / "notes.md").unlink()
        stage(repo, "app.py", "print('hello')\n")

        # THE FOLDED SET IS A HARDCODED LIST IN THE GUARD, because computing it costs a full sweep of
        # the codepoint space on every commit. A hardcoded list is a list that goes stale: a Unicode
        # update that adds a dash character would leave it un-folded and silently un-matchable, which
        # is the exact defect this whole block exists for. So the list is checked against the running
        # interpreter's own Unicode data here, where staleness is a test failure rather than a dead
        # entry somebody trusts.
        ig = _load_guard("identifier_guard_separators")
        expected = {chr(c) for c in range(sys.maxunicode + 1)
                    if unicodedata.category(chr(c)) in ("Pd", "Zs")} | set("-_. ")
        check("9w the folded separator set is exactly Pd | Zs plus the ASCII four, for THIS "
              "interpreter's Unicode version", set(ig.SEPARATORS) == expected,
              f"missing {sorted(ord(c) for c in expected - set(ig.SEPARATORS))}, "
              f"extra {sorted(ord(c) for c in set(ig.SEPARATORS) - expected)}")


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
        # This case runs the guard IN-PROCESS, so the deny-list override has to be set on this
        # interpreter's own environment rather than on a child's — and it must be put back. It was
        # not: `os.environ["PD_PRIVATE_IDENTIFIERS"] = str(deny)` leaked into every later case, and
        # into `case_end_to_end_commit`'s and `case_missing_guard_is_not_a_skip`'s `{**os.environ}`
        # copies, pointing them at a temporary directory this case had already deleted. Harmless
        # only because both of those set the variable again themselves; a case that did not would
        # have inherited a stale path and failed for a reason nothing in it explains. Test isolation
        # is not a nicety in a file whose whole subject is state that silently disables a check.
        previous = os.environ.get("PD_PRIVATE_IDENTIFIERS")
        # A regex that compiles, imports and matches nothing — the realistic shape of a bad edit.
        ig.HOME_PATH = _re.compile(r"(?!x)x")
        buf = io.StringIO()
        try:
            os.environ["PD_PRIVATE_IDENTIFIERS"] = str(deny)
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = ig.main(["--staged"])
        finally:
            ig.HOME_PATH = original
            if previous is None:
                os.environ.pop("PD_PRIVATE_IDENTIFIERS", None)
            else:
                os.environ["PD_PRIVATE_IDENTIFIERS"] = previous
        out = buf.getvalue()
        check("11a a home-path rule that matches nothing exits 2, not 0", code == 2,
              f"got {code}: {out[:300]}")
        check("11b it says the pattern set is broken rather than reporting nothing",
              "pattern set is broken" in out, out[:300])
        check("11c the case restored the environment it borrowed",
              os.environ.get("PD_PRIVATE_IDENTIFIERS") == previous,
              f"leaked {os.environ.get('PD_PRIVATE_IDENTIFIERS')!r}")

    # THE DEAD-RULE PROBE, WHICH HAD NO TEST AT ALL. `self_probe` refuses any rule whose pattern
    # matches the empty string — a rule that reports no match against every possible text, for ever.
    # MEASURED: deleting those five lines outright left this suite fully green, so the branch was
    # unpinned code inside the function whose entire job is proving that no rule is dead.
    #
    # It has to be reached through a DERIVED rule. `read_denylist` refuses separator-only entries at
    # parse time (9o), so the deny-list can no longer deliver one; git config can, and is not parsed
    # by that function. `_-_-` is four characters, so it clears MIN_DERIVED_LEN, and it is not in
    # TOO_GENERIC, so it is not skipped with a note — it compiles straight to `[<separators>]*`.
    # Its parts are four characters too, below the 5-character floor, so exactly one dead rule is
    # produced and the assertion is about that rule and nothing else.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp, user_name="_-_-")
        stage(repo, "app.py", "print('hello')\n")            # clean, so a 2 is not a finding
        deny = write_denylist(tmp, [SYNTH_PROJECT])
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("11d a git identity that compiles to a rule matching the EMPTY STRING exits 2",
              code == 2, f"got {code}: {out[:400]}")
        check("11e and it says the rule is dead rather than reporting a clean scan",
              "matches the empty string" in out and "that rule is dead" in out, out[:400])
        # The other direction, so 11d is about the identity and not about the fixture: an ordinary
        # identity on the identical index and the identical deny-list is a clean run.
        ordinary = new_repo(tmp / "ordinary")
        stage(ordinary, "app.py", "print('hello')\n")
        code, out = run_guard(ordinary, "--staged", denylist=deny)
        check("11f the same index under an ordinary git identity is exit 0", code == 0,
              f"got {code}: {out[:400]}")


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

    check("12b2 the traceback itself is printed, not swallowed — a crash must stay diagnosable",
          "Traceback (most recent call last)" in out, out[:300])
    # THE TRACEBACK IS THE GUARD'S OWN OUTPUT AND IS HELD TO THE GUARD'S OWN RULE. Every frame of a
    # traceback out of identifier_guard.py names identifier_guard.py, which lives under the real home
    # directory — so `traceback.print_exc()` published the account segment on every crash, in the one
    # piece of output most certain to be pasted verbatim into an issue or an agent report. This was
    # reproducible on the machine, in this very fixture's captured output, until `format_exc` was
    # routed through `display_path`. `GUARD` is this suite's own resolved path, so the assertion is
    # about the running interpreter's real home rather than a fixture's.
    #
    # SKIPPED, LOUDLY, WHEN THE GUARD IS NOT UNDER $HOME. A copy of this suite run out of tree — from
    # a scratch directory, a worktree, a mutation harness — produces frames that never mention the
    # home directory, so these two would pass without exercising anything, which is worse than not
    # running. The installed guard IS under $HOME (case 13 refuses to proceed otherwise, and the hook
    # templates hardcode the path), so in the configuration that ships, this runs.
    real_home = Path.home()
    if GUARD.is_relative_to(real_home):
        check("12e the crash traceback does not print the real home directory in its frames",
              str(real_home) not in out, out[-800:])
        check("12f and the home segment is abbreviated to `~` rather than merely redacted, so the "
              "frames stay readable", "~/.claude" in out, out[-800:])
        check("12g and it is still locatable — the guard's own file name survives",
              "identifier_guard.py" in out, out[-800:])
    else:
        print(f"  skip  12e-12g the guard under test is not under $HOME ({GUARD}), so a traceback "
              f"from it cannot exercise the home-path redaction")

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

        # THE SPELLING MISMATCH, which is the one the old redaction missed. The location column used
        # to be scrubbed with `where.replace(found, shown)` — an EXACT substitution, case- and
        # separator-sensitive, standing in for matchers that are neither. So a line spelled
        # `zarquon-widget` inside a file named `Zarquon_Widget.md` had its match column redacted and
        # its location column printed in full: every alternative spelling the deny-list exists to
        # catch was a spelling the redaction failed to cover. Measured: the path appeared verbatim.
        sh("git", "reset", "-q", cwd=repo)
        for stale in ("docs/notes.md", f"docs/{SYNTH_PROJECT}.md"):
            (repo / stale).unlink(missing_ok=True)
        variant_dir = SYNTH_PROJECT.replace("-", "_").title()          # Zarquon_Widget
        stage(repo, f"docs/{variant_dir}/notes.md", f"the {SYNTH_PROJECT} loader\n")
        code, out = run_guard(repo, "--staged", denylist=deny)
        check("14d the location column is redacted case- and separator-insensitively, not by an "
              "exact replace", code == 1 and variant_dir not in out, f"got {code}: {out[:400]}")
        check("14e and the finding is still locatable — the surviving path and line are printed",
              "docs/" in out and "notes.md:1" in out, out[:400])

        # THE ONE `{path}` THAT WAS NOT ROUTED THROUGH `display_path`. `scan_message`'s read-failure
        # message interpolated the raw path, and the OSError's own `str` repeats it — so pointing
        # `--message` at anything unreadable under the real home printed the account segment twice.
        # A directory is the realistic way to get there: a wrapper that passes `$GIT_DIR` or a
        # half-written `$1`. Asserted against the REAL home, because that is the value at risk; the
        # fixtures elsewhere in this file redirect HOME and would not catch it.
        real_home = Path.home()
        unreadable_msg = real_home / ".claude"          # exists, is a directory, is under $HOME
        if unreadable_msg.is_dir():
            code, out = run_guard(repo, "--message", str(unreadable_msg), denylist=deny)
            check("14f an unreadable commit-message PATH is abbreviated, not printed in full",
                  code == 2 and str(real_home) not in out, f"got {code}: {out[:400]}")
            check("14g and it still says which file and that the message was not scanned",
                  "~/.claude" in out and "was not scanned" in out, out[:400])
        else:
            print("  skip  14f-14g no directory under $HOME to point --message at")


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

        # THE REPOSITORY DOES NOT GET A VOTE ON THE GUARD'S PARSER. The header parser keys on
        # `+++ b/`, and `b/` is only git's DEFAULT prefix: `diff.mnemonicPrefix` writes `+++ i/…`
        # for the index and `diff.noprefix` writes no prefix at all. Both are ordinary settings a
        # person turns on for readability. MEASURED with mnemonicPrefix set, before the fix: the
        # finding still fired but was attributed to `?:1` — the file name, which is the half of a
        # finding that makes it actionable, silently gone. `--src-prefix`/`--dst-prefix` on the
        # command line override every config spelling of this.
        for setting in ("diff.mnemonicPrefix", "diff.noprefix"):
            sh("git", "config", setting, "true", cwd=repo)
            # Content deliberately unlike any file already in history: identical content would be
            # detected as a RENAME, which emits no `+` lines and would make this case pass for the
            # wrong reason. (The first draft did exactly that.)
            stage(repo, "cfg-leak.md", f"{setting} fixture, path {SYNTH_HOME}/code/thing\n")
            code, out = run_guard(repo, "--staged", denylist=deny)
            check(f"16g a finding survives `{setting}=true` WITH its file attribution",
                  code == 1 and "cfg-leak.md:1" in out, f"got {code}: {out[:300]}")
            sh("git", "reset", "-q", cwd=repo)
            (repo / "cfg-leak.md").unlink()
            sh("git", "config", "--unset", setting, cwd=repo)


def case_no_opt_out() -> None:
    """THE OPT-OUT IS GONE, AND STAYS GONE. Asserted against the source, the namespace, and the exits.

    WHAT THIS CASE REPLACES. It used to assert that a declaration line — `!no-private-identifiers`
    as a deny-list's only content — was a clean run, the sanctioned way to say "this repository
    genuinely has no private names". Two of its assertions, 18l and 18m, covered the misspelling of
    that line. 18l was named "a misspelled declaration does not silently disable the check" and
    asserted `code == 0`, establishing the exact opposite of its own name: a one-character
    transposition made the directive an ordinary entry, long enough to be legal and matching nothing
    that exists, so the file read as populated and a staged private name was committable. Delete the
    file: 2. Empty it: 2. Comment it out: 2. Mistype it: 0. Both assertions are deleted rather than
    re-pointed, because the path they described no longer exists.

    WHY REMOVAL RATHER THAN VALIDATION, which is what this case now pins. A rule enforced by checking
    a feature can regress, because the check can be evaded — and this one was, by a typo. A rule
    enforced by the ABSENCE of the feature cannot: there is no misspelling of a syntax that does not
    exist. So the assertions below are deliberately not "the guard rejects bad declarations". They
    are "the guard has no concept of a declaration": no constant in its namespace, no such string in
    its source, and every file that used to express one now exits 2 like any other unusable list.

    That is also why 18b reads the guard's SOURCE. A behavioural assertion alone would stay green if
    someone reintroduced a checked, canonicalised or fuzzy-matched variant that happened to reject
    these three fixtures. Absence of the string is the property that was bought.
    """

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        repo = new_repo(tmp)

        ig = _load_guard("identifier_guard_no_opt_out")
        # NOT "the constant is not called NO_PRIVATE_IDENTIFIERS". That pinned one NAME, and the
        # feature is not a name — reintroducing it as `OPT_OUT_MARKER` or `DELIBERATELY_NONE` would
        # have kept this green. The property is that the guard's namespace holds no directive-shaped
        # STRING at all: nothing beginning `!`, and nothing spelling the removed syntax whatever it
        # is bound to. `DENYLIST_ENV` and the rest are ordinary strings and are unaffected.
        directive_like = sorted(
            attr for attr, value in vars(ig).items()
            if isinstance(value, str)
            and (value.strip().startswith("!") or REMOVED_OPT_OUT in value.lower()
                 or "no-private-identifiers" in value.lower()))
        check("18a the guard's namespace holds no directive-shaped string under any name",
              not directive_like and not hasattr(ig, "NO_PRIVATE_IDENTIFIERS"),
              f"directive-shaped constants: {directive_like}")
        source = GUARD.read_text(encoding="utf-8")
        check("18b the removed directive appears nowhere in the guard's source, not even as a "
              "string it rejects", REMOVED_OPT_OUT not in source,
              "the opt-out syntax is back in the source")

        stage(repo, "app.py", "print('hello')\n")

        # THE THREE FILES THAT USED TO MEAN "deliberately none", each now an unusable list. The
        # content is otherwise clean, so a 2 here is the LIST being refused, not a finding.
        for label, entries in (("the exact former declaration", [REMOVED_OPT_OUT]),
                               ("its upper-case spelling", [REMOVED_OPT_OUT.upper()]),
                               ("the one-character misspelling", [MISTYPED_OPT_OUT])):
            path = write_denylist(tmp, entries)
            code, out = run_guard(repo, "--staged", denylist=path)
            check(f"18c a deny-list whose only line is {label} exits 2", code == 2,
                  f"got {code}: {out[:400]}")

        # THE FIXTURE THE OLD 18l WAVED THROUGH, restated as it should always have read: the
        # misspelled directive AND a private name staged. This was exit 0 — committable — because
        # the typo counted as an entry and the file therefore counted as populated.
        stage(repo, "docs.md", f"we should mention {SYNTH_PROJECT} here\n")
        typo = write_denylist(tmp, [MISTYPED_OPT_OUT])
        code, out = run_guard(repo, "--staged", denylist=typo)
        check("18d a private name staged under a MISTYPED directive is not committable", code == 2,
              f"got {code}: {out[:400]}")
        check("18e the refusal is about the entry, and does not echo it",
              "begins with `!`" in out and MISTYPED_OPT_OUT not in out, out[:400])

        # And a real list catches the same fixture, so 18d is about the directive rather than the
        # content — the both-directions rule this file is built on.
        real = write_denylist(tmp, [SYNTH_PROJECT])
        code, out = run_guard(repo, "--staged", denylist=real)
        check("18f the same fixture under a REAL list is exit 1, not 2", code == 1,
              f"got {code}: {out[:300]}")

        # A directive ALONGSIDE real entries used to be a special "contradiction" branch. There is
        # no contradiction to detect any more: the `!` line is simply an unusable entry, and one
        # unusable entry voids the list. Same exit, one fewer concept.
        both = write_denylist(tmp, [REMOVED_OPT_OUT, SYNTH_PROJECT])
        code, out = run_guard(repo, "--staged", denylist=both)
        check("18g a directive alongside real entries voids the list", code == 2,
              f"got {code}: {out[:300]}")
        check("18h and it says the private-name check did not run", "did not run" in out, out[:300])

        # A COMMENTED-OUT directive was already nothing, and still is: the `#`-strip runs first, so
        # the file is the empty one. Exit 2 by the empty-list path rather than the `!` path.
        commented_out = tmp / "commented-out.txt"
        commented_out.write_text(f"# {REMOVED_OPT_OUT}\n", encoding="utf-8")
        code, out = run_guard(repo, "--staged", denylist=commented_out)
        check("18i a directive inside a comment is an empty list — exit 2", code == 2,
              f"got {code}: {out[:300]}")
        # PINNED TO WHICH MECHANISM. Two paths return 2 for this fixture and they mean different
        # things: the `#`-strip running FIRST (so the file is simply empty), or the `!` refusal
        # firing on a line that should never have reached it. `code == 2` alone could not tell them
        # apart, and this case's whole subject is that a commented-out directive is nothing at all.
        check("18i2 and it is the EMPTY-LIST path, not the `!` refusal — the comment strip ran first",
              "contains no usable entries" in out and "begins with `!`" not in out, out[:400])

        # THE OTHER DIRECTION, so none of the above is passing because everything exits 2: an
        # ordinary populated list on the same otherwise-clean index is a clean run.
        sh("git", "reset", "-q", cwd=repo)
        (repo / "docs.md").unlink()
        stage(repo, "app.py", "print('hello')\n")
        code, out = run_guard(repo, "--staged", denylist=write_denylist(tmp, [SYNTH_PROJECT]))
        check("18j an ordinary populated list on clean content is still exit 0", code == 0,
              f"got {code}: {out[:300]}")


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
                 case_missing_guard_is_not_a_skip, case_no_opt_out):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the guard blocks every case it is supposed to block, and passes the rest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
