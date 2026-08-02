#!/usr/bin/env python3
"""commit-time guard: private identifiers must not enter a deliberately-public repository.

push_guard.py blocks what a *push* makes permanent. This blocks what a *commit* makes permanent,
which is a different set: a credential can be rotated, but an identifier is a fact about the world
and cannot be. Once a private project name, a home directory path, or an account handle is in a
public repository's history, rewriting the branch does not recall the clones, the forks, or the
mirrors — so the only place to stop it is before the object is written.

  BLOCK  an absolute home path in a staged line, a staged path, or the commit message
  BLOCK  the local git identity (author email, author name, remote account segment)
  BLOCK  any name on the private deny-list
  BLOCK  with exit 2 when the deny-list is absent, unreadable or empty — a check that did not run

WHY THE DENY-LIST LIVES OUTSIDE THE PUBLIC REPOSITORY
------------------------------------------------------
The deny-list names private projects. A deny-list of private project names, COMMITTED to the public
repository, publishes exactly the thing it exists to keep private — with the added insult of
collecting them in one file for the reader's convenience. So it is not committed there, and it is
not a gitignored path inside it either:

  a .gitignore rule is a default that `git add -f` overrides in one keystroke, and nothing about
  the file's location makes the mistake impossible. A file that lives outside the public work tree
  cannot be committed to it at all — `git add` cannot reach above the work tree.

Hence ~/.claude/private-identifiers.txt: one identifier per line, `#` comments and blanks ignored.

BE PRECISE ABOUT WHAT THAT DOES AND DOES NOT GUARANTEE. This used to read "never inside any
repository", and that is false: ~/.claude is itself a git repository, whose .gitignore is an
allow-list (`/*`, then explicit un-ignores), so the deny-list sits there under exactly the
`git add -f`-overridable default this section calls strictly weaker. What keeps it out of history
today is additionally that ~/.claude has no remote — a current state, not a construction.

The claim that survives, and the only one worth making, is RELATIVE: the deny-list is outside the
DELIBERATELY-PUBLIC repository this guard is installed in, and no operation in that work tree —
`git add -f` included — can reach it. That is the threat this guard exists for, and it is met by
construction. Anyone hardening ~/.claude itself should treat its own .gitignore as a default, not
as a boundary.

The same reasoning applies to this file: nothing below names a project, an account, a person, or a
path. Every rule here is either a PATTERN (`/Users/<segment>`) or a RUNTIME LOOKUP
(`git config user.email`). Patterns and lookups are safe to publish; lists are not.

If you find yourself needing to write a real project name into this file, into the selftest, into a
fixture, or into a comment to make a rule work — stop. That is the failure this guard exists to
prevent, and it has a solution that does not require it.

AN ABSENT DENY-LIST IS A CHECK THAT DID NOT RUN, AND IS EXIT 2
---------------------------------------------------------------
This used to be exit 0 with a printed note, and that was a fail-open. MEASURED: with the deny-list
moved aside, a staged file containing a real private project name exited 0 and was committable; with
the deny-list present, the same fixture exited 1. So the single most likely condition in practice —
a fresh clone, a new machine, a renamed file, a `$HOME` that differs — silently switched off the
half of the guard that this whole design exists for, while the other half kept reporting success.
The note was real and the note was accurate. It made no difference: a hook acts on an exit code, and
the exit code said clean. STATING a gap is not CLOSING one.

The objection to fixing it is that a contributor to the public repository has no deny-list and never
will, so absence-is-fatal would block their every commit until they deleted the guard. That
objection does not survive contact with how this guard is reached. Git hooks are not carried by a
clone — `install_hooks.py` writes into `.git/hooks`, which no clone, fetch or pull reproduces. This
guard therefore cannot run on a machine where somebody has not deliberately run
`install_hooks.py --public` against this work tree. Being invoked at all IS the declaration that
this repository is deliberately public and that private names must be kept out of it. There is no
population of surprised contributors; there is one person who asked for the check and then does not
have the file the check needs.

Nor does the guard need to ask the repository whether it is public. It cannot see that declaration
anyway — the declaration lives in the hook that invoked it, not in the work tree — and conditioning
on a signal inside the work tree would put the fail-open back one level down, where a repository
could switch its own scan off from the inside. The invocation is the condition, and it is already
satisfied by the time this file has an opinion.

THERE IS NO OPT-OUT, AND THAT IS THE FIX — BY CONSTRUCTION, NOT BY VALIDATION
------------------------------------------------------------------------------
The first attempt at the above kept an escape hatch for the one honest case — a public repository
whose owner genuinely has no private names — spelled as a single declaration line in the file. That
hatch was itself a fail-open, and it was measured three times:

  a one-character transposition of the declaration + a real private name staged   ->  exit 0
  a BOM in front of the only real entry                                           ->  exit 0
  the same file without the BOM                                                   ->  exit 1

Delete the file and it was 2. Empty the file and it was 2. Comment the line out and it was 2.
MISTYPE it and it was 0 — because a misspelled directive is an ordinary deny-list ENTRY, long enough
to be legal and matching nothing that exists, so the file looked populated and the run looked clean.
The hatch turned a typo into a silently disabled guard, which is the exact defect the exit-2 rule was
written to end, reintroduced one level down.

So the hatch is gone, and no validated replacement takes its place. That distinction is the whole
point: a rule enforced by VALIDATING a feature can regress, because the validation can be evaded, and
this one was. A rule enforced by the ABSENCE of the feature cannot, because there is no misspelling
of a syntax that does not exist. Do not reintroduce a checked, canonicalised, fuzzy-matched or
otherwise "safe" variant of the declaration line. The safety came from deleting it.

A DENY-LIST IS THEREFORE MANDATORY. Missing is 2, empty is 2, no usable entries is 2, and none of
those is ever 0. An entry that begins `!` is refused too — entries are identifiers, not directives,
and refusing them is what stops a file left over from the old regime from reading as populated.

The lockout objection does not apply here, and it is worth being precise about why, because the same
objection is sometimes correct. A block is dangerous when its stated remedy cannot clear it — the
push guard's `git fetch` case, where doing the suggested thing left the block in place. This block's
remedy is "create this file, at this path, one identifier per line", it is one step, and the message
below states the path, the format, and where a fresh machine gets the file back. A block a person can
clear in ten seconds is not a lockout.

The cost of being wrong in each direction settles the rest. Wrongly exiting 2 costs one message and
one ten-second file creation. Wrongly exiting 0 puts a private project name in a public repository's
history, permanently, and rewriting the branch does not recall the clones. Those are not comparable.

WHAT AN EXIT 2 HERE DOES AND DOES NOT MEAN. It does NOT mean "the private-name check was skipped and
the generic rules still ran". The deny-list is loaded BEFORE any scanning, so a run that cannot load
it is VOIDED ENTIRELY — no home-path scan, no identity scan, no output about either. An earlier
revision of this file claimed the generic rules were "unaffected in every case" and "never skipped";
that was false as written and is struck. The generic rules need no file, but they never get the
chance to run, because nothing is scanned at all.

EXIT CONTRACT — identical to push_guard.py, deliberately
--------------------------------------------------------
  0  scanned, nothing found        1  a finding        2  the check could not run

A scan that did not run must never read as clean. Every failure of the guard itself is a 2.

WHY THIS DOES NOT IMPORT push_guard.py
---------------------------------------
It shares that file's exit contract, its GuardError, its fail-closed discipline and its `_decode`
rationale, and those are re-stated below rather than imported. Not for want of trying: push_guard.py
validates its secret-pattern set in its MODULE BODY and raises SystemExit(2) there when it cannot
load one. Importing it would make a commit fail, with push-flavoured wording about a pattern set
this guard never uses, because of a defect in a push-time concern. A commit-time guard must not
inherit a push-time guard's availability. push_guard.py is also not editable from here, so the
helpers cannot be lifted into a shared module without touching it; if that constraint is ever
lifted, `GuardError`, `_decode` and `git` are the three to extract, unchanged.

INVOCATION — two modes, one script, because a pre-commit hook cannot see the message
-------------------------------------------------------------------------------------
  identifier_guard.py --staged            scan the staged diff and the staged paths   (pre-commit)
  identifier_guard.py --message <path>    scan a commit message file                  (commit-msg)

git runs `pre-commit` BEFORE the message exists, so that hook physically cannot inspect it; the
message is first available to `commit-msg`, as the path in $1. Two hooks are therefore unavoidable.
One SCRIPT with two modes is the choice, and it is not merely tidy: the rule set, the deny-list
loader, the redaction and the exit contract have to be identical in both, and two files would drift
the first time a rule was added to one of them. A rule that fires in a file and not in the message
is the same hole either way round.

Install with `install_hooks.py <root> --public`. This guard is for repositories that are
DELIBERATELY PUBLIC. Do not install it in a private repository: there it blocks nothing that
matters and trains its user to reach for --no-verify.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

DENYLIST_ENV = "PD_PRIVATE_IDENTIFIERS"
DEFAULT_DENYLIST = Path.home() / ".claude" / "private-identifiers.txt"

# Where a fresh machine gets the deny-list back. Named in every fatal message, because a block whose
# remedy is not stated is the lockout this design is accused of and is not. This file is vendored
# into a deliberately-public repository, so the remedy names the machine's restore documentation and
# nothing else: no repository name, account, or URL belongs here — see the module docstring on what
# is safe to publish.
RESTORE_DOC = "~/.claude/docs/RESTORE.md"

# `/Users/<segment>` and `/home/<segment>`. Written as one alternation on purpose: this literal must
# not match ITSELF, and it does not — the text `/Users` here is followed by `|`, never by `/`. Any
# example of a home path anywhere in this repository must use an angle-bracket placeholder
# (`/Users/<name>`), which cannot match because `<` is not in the segment class.
#
# IGNORECASE, like every rule `literal_rule` builds. This was the one rule compiled without it, and
# the gap was reachable: macOS and Windows filesystems are case-insensitive, so `/users/<name>/x` is
# a path that resolves, that a tool prints and that a human types — and it exited 0. Measured before
# the flag: `/users/<name>/secret` staged clean. `PLACEHOLDER_SEGMENTS` is consulted through
# `.lower()` already, so the exemptions did not have to change. The self-match argument above holds
# under the flag too: `/users` and `/home` in lower case appear nowhere in this file followed by `/`.
HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._-]{2,})", re.IGNORECASE)

# Segments that are placeholders or machine accounts rather than a person. Kept deliberately short:
# every entry is a hole, so the bar is "this string identifies nobody".
PLACEHOLDER_SEGMENTS = frozenset({
    "anything", "example", "home", "me", "name", "root", "runner", "shared", "someone", "user",
    "username", "you", "youruser", "yourname", "your-name",
})

# Derived values this generic. Matching them would flag half the English language, and a guard that
# cries wolf is a guard that gets bypassed. If a real git identity is one of these, the guard says
# so rather than silently skipping it.
TOO_GENERIC = frozenset({
    "admin", "example", "git", "github", "gitlab", "local", "localhost", "main", "master", "none",
    "null", "origin", "root", "test", "user", "users", "home",
})

MIN_DERIVED_LEN = 4      # below this, a substring match is noise rather than signal
MIN_DENYLIST_LEN = 3     # below this, a deny-list entry matches most files — that is a broken list

# Runs of these inside a deny-list entry match any run of them (or none) in the scanned text, so a
# single entry covers the spaced, hyphenated, underscored and squashed spellings of one name.
SEPARATORS = "-_. "

# The commit-message file `commit-msg` receives holds more than the message: git's own instruction
# comments, and — under `commit -v` — the entire staged diff below a scissors line. git strips both
# before writing the commit, so scanning them would report findings that are not going anywhere
# (and, for the verbose diff, duplicate every finding the staged scan already made).
SCISSORS = re.compile(r"^\s*#\s*-+\s*>8\s*-+")

# Prepended to EVERY git invocation. `core.quotepath` is on by default and makes git print a path
# containing any non-ASCII byte as a C-quoted string — `"docs/\303\251t\303\251.md"` — so a private
# name written in anything but ASCII arrives at the scanner as octal escapes and matches nothing.
# Turning it off is not cosmetic; it is the difference between scanning the path and scanning a
# transliteration of it. Passed as `-c` rather than read and checked, because the guard must not
# depend on how the repository it is defending has configured itself.
GIT_OVERRIDES = ("-c", "core.quotepath=false")


class GuardError(RuntimeError):
    """A check could not complete.

    Never downgrade this to a clean result. The entire failure class this guard exists to prevent is
    a check that silently did not run being reported as a check that passed. Same class, same name
    and same meaning as push_guard.py's.
    """


def _decode(raw: bytes) -> str:
    """Decode git output so that undecodable bytes cannot hide a scan.

    Verbatim from push_guard.py, and for the identical reason: git calls a file text on the absence
    of NUL in its first 8000 bytes, so a diff readily carries latin-1 or Shift-JIS bytes that are
    not valid UTF-8. Under `text=True` that raises UnicodeDecodeError out of `subprocess.run` — a
    traceback and the interpreter's exit 1, the code reserved for a finding. A mangled character
    cannot conceal an identifier; an undecodable diff conceals the entire scan.

    Note the asymmetry with `read_denylist` below, which decodes STRICTLY. Different direction of
    risk: mangling the text being scanned costs at most one garbled character, while mangling the
    deny-list silently weakens the matcher.
    """
    return raw.decode("utf-8", errors="replace")


def git(*args: str, timeout: int = 60, tolerate_failure: bool = False) -> str:
    """Run git. Any failure voids the check unless the caller explicitly opted out.

    `tolerate_failure=True` means "a non-zero exit is itself the answer I am asking for". Exactly
    one call site is entitled to it — `rev-parse --verify HEAD` on a repository with no commits yet,
    where failure means "no HEAD". It defaults to False and must stay that way: push_guard.py
    carried the opposite default once, and five call sites read the resulting empty string as a
    clean scan.
    """
    try:
        return _decode(subprocess.run(["git", *GIT_OVERRIDES, *args], capture_output=True,
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
        raise GuardError(f"`git {' '.join(args[:2])}` could not execute: {exc}") from exc
    except subprocess.SubprocessError as exc:
        raise GuardError(f"`git {' '.join(args[:2])}` could not execute: {exc}") from exc


def redact(text: str) -> str:
    """Show enough of a match to locate it, never enough to republish it.

    The finding is printed to a local terminal, so this is not a confidentiality boundary in the way
    the deny-list's location is. It is a hygiene one: hook output gets pasted into transcripts, issue
    comments and agent reports, and a guard whose OUTPUT carries the identifier in full has moved the
    leak rather than stopped it. The file and line number are what make a finding actionable; the
    full string never was.
    """
    if len(text) <= 4:
        return text[0] + "…"
    return text[:2] + "…" + text[-1]


def display_path(path: Path | str) -> str:
    """A filesystem path as it is safe to PRINT: no real home segment, ever.

    Every fatal message below names the deny-list's path, because a block whose remedy omits the path
    is not actionable. The default path is `$HOME/.claude/private-identifiers.txt`, and printing it
    verbatim publishes the account segment — the very rule `home_path_rule` blocks other people's
    files for carrying. The guard's own output was the one place exempt from its own rule, and hook
    output is pasted into transcripts and agent reports exactly like any other text.

    `~` is substituted for the real home first, which covers the default and every override under it.
    Anything left that still looks like a home path — an override elsewhere on the disk, another
    user's tree — is redacted through the same rule the scanner uses, so there is no second spelling
    to keep in sync.
    """
    text = str(path)
    home = str(Path.home())
    if home and (text == home or text.startswith(home + os.sep)):
        text = "~" + text[len(home):]
    return HOME_PATH.sub(lambda m: m.group(0).replace(m.group(1), redact(m.group(1))), text)


def remedy(path: Path) -> str:
    """The one-step way out of every fatal deny-list state, stated identically in all of them.

    Named parts, all three load-bearing: the PATH so there is nothing to guess, the FORMAT so the file
    can be written correctly first time, and the DOC that describes how a fresh machine restores it —
    no clone of this public repository brings it. A block is only a lockout when doing the suggested
    thing does not clear it; this clears it.
    """
    return (f"Create {display_path(path)} — one identifier per line, `#` comments and blank lines "
            f"ignored, nothing else — or point {DENYLIST_ENV} at where yours lives. The file is "
            f"per-machine and no clone of a public repository brings it: see {RESTORE_DOC} for how "
            f"this machine restores it.")


class Rule:
    """One matcher: a name for the report, and a compiled pattern.

    `sensitive` marks a rule whose pattern was BUILT from a private value. Nothing about such a rule
    may be printed beyond its name and a redacted match — not the term, not its length, not its
    index in the list.
    """

    def __init__(self, name: str, pattern: re.Pattern[str], sensitive: bool = False) -> None:
        self.name = name
        self.pattern = pattern
        self.sensitive = sensitive

    def find(self, text: str) -> str | None:
        m = self.pattern.search(text)
        return m.group(0) if m else None


def literal_rule(name: str, term: str, sensitive: bool = False) -> Rule:
    """A case-insensitive SUBSTRING matcher for one literal term.

    No word boundaries, deliberately, and this is the one design choice here most likely to be
    "tidied" later. A private name is routinely embedded in a longer token — a repository slug
    concatenated with a suffix, a branch name, a package name, a directory. Requiring a boundary
    after the term makes every one of those spellings pass, which is the direction of error that
    publishes something. Requiring none costs an occasional false positive on an unrelated word,
    which costs a re-read. The length floors above are what keep that occasional.
    """
    parts = [re.escape(ch) for ch in term]
    # Collapse each run of separators into "any run of separators, or none", so one entry covers
    # `two words`, `two-words`, `two_words` and `twowords` without four entries and without the
    # author having to think about it.
    pattern = ""
    i = 0
    while i < len(term):
        if term[i] in SEPARATORS:
            while i < len(term) and term[i] in SEPARATORS:
                i += 1
            pattern += f"[{re.escape(SEPARATORS)}]*"
            continue
        pattern += parts[i]
        i += 1
    return Rule(name, re.compile(pattern, re.IGNORECASE), sensitive=sensitive)


def home_path_rule() -> Rule:
    class HomeRule(Rule):
        def find(self, text: str) -> str | None:
            for m in self.pattern.finditer(text):
                if m.group(1).lower() in PLACEHOLDER_SEGMENTS:
                    continue
                return m.group(0)
            return None

    return HomeRule("absolute home path", HOME_PATH)


def git_config(key: str) -> str:
    """Read one git config value, or "" if it is not set.

    `--get` consults the repository, then the user's global config, then the system's, which is
    exactly the resolution git itself would use to stamp a commit. Exit 1 means "not set" and is an
    answer; anything else is a failure and voids the check via `git()`.
    """
    try:
        proc = subprocess.run(["git", "config", "--get", key],
                              capture_output=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GuardError(f"`git config --get {key}` timed out — the scan did not run") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise GuardError(f"`git config --get {key}` could not execute: {exc}") from exc
    if proc.returncode > 1:
        raise GuardError(f"`git config --get {key}` exited {proc.returncode}: the local identity "
                         f"could not be read, so it could not be checked for")
    return _decode(proc.stdout).strip()


def account_from_remote(url: str) -> str:
    """The account segment of a remote URL, or "".

    Purely textual — no network. The guard runs at commit time; a lookup that reaches a server would
    make every commit depend on connectivity and would leak the repository's existence to that
    server on every commit. Three shapes cover what git writes:

      git@host:ACCOUNT/repo.git        ssh://git@host/ACCOUNT/repo        https://host/ACCOUNT/repo
    """
    url = url.strip()
    if not url:
        return ""
    scp = re.match(r"^[^/]+@[^/:]+:([^/]+)/", url)
    if scp:
        return scp.group(1)
    proto = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?[^/]+/([^/]+)/", url)
    if proto:
        return proto.group(1)
    return ""


def derived_rules(notes: list[str]) -> list[Rule]:
    """Rules built from the LOCAL git identity. Derived every run; nothing here is hardcoded.

    A hardcoded email or account name would be the same defect as a committed deny-list, one value
    smaller. These are looked up, so this file publishes the QUESTION ("what is the author email?")
    and never the answer.

    The author's display name is included as well as the email. It is identifying content by the
    same standard, it is the value most likely to be pasted into a doc by hand, and it comes from
    the same lookup. Its individual whitespace-separated parts are matched too when they are long
    enough to be distinctive, because a first name alone in a document identifies just as well.
    """
    rules: list[Rule] = []
    seen: set[str] = set()

    def add(name: str, value: str) -> None:
        v = value.strip()
        if not v:
            return
        if len(v) < MIN_DERIVED_LEN or v.lower() in TOO_GENERIC:
            # Stated, never silent. A skipped rule is a rule that is not running, and the founder is
            # the only one who can decide whether that matters.
            notes.append(f"{name} ({redact(v)}) is too short or too generic to match on — "
                         f"not checked")
            return
        if v.lower() in seen:
            return
        seen.add(v.lower())
        rules.append(literal_rule(name, v, sensitive=True))

    email = git_config("user.email")
    add("git author email", email)
    if "@" in email:
        add("git author email local-part", email.split("@", 1)[0])

    name = git_config("user.name")
    add("git author name", name)
    for part in re.split(r"\s+", name):
        if len(part) >= 5:
            add("git author name part", part)

    account = account_from_remote(git_config("remote.origin.url"))
    if account:
        add("remote account name", account)
    else:
        notes.append("no origin remote with a parseable account segment — the account-name rule "
                     "has nothing to check for (the other rules still ran)")

    return rules


def read_denylist(path: Path) -> list[Rule]:
    """Load the private deny-list. It is MANDATORY, and every way of not loading it is exit 2.

    ABSENT is not a clean scan and no longer reads as one. It used to append a note and return no
    rules, and `report` then exited 0 — the fail-open documented at length in the module docstring,
    reproduced by measurement. Absence is the MOST likely failure, not the least: this file is
    per-machine and never travels with a clone. A guard whose most likely failure mode is silent
    disablement is not a guard. The full argument, including why a public repository's contributors
    are not locked out by this, is in the module docstring.

    PRESENT-BUT-EMPTY is broken for the reason it always was. An empty list is what a truncated
    write, a bad merge or an interrupted edit leaves behind, and it disables the rule while looking
    exactly like a healthy install — the same failure push_guard.py's empty-SECRET_PATTERNS probe
    exists to catch, in the same directory, one guard over.

    THERE IS NO WAY TO SAY "DELIBERATELY NONE", and that is deliberate. A declaration line used to
    exist for it; a one-character typo in that line made it an ordinary entry, the file read as
    populated, and a staged private name exited 0. The full argument, and the reason no validated
    replacement is acceptable either, is in the module docstring. The consequence here is that this
    function has exactly one success path: at least one usable entry.

    AN ENTRY THAT CANNOT MATCH IS REFUSED RATHER THAN COMPILED. Three shapes reach that state, and
    all three used to become rules that silently fired on nothing:

      begins `!`      a leftover directive from the removed syntax, or a misspelling of one. Refused
                      by shape, not by comparison against a known word — the point is that the file
                      has no directives at all, so anything shaped like one is a mistake.
      has a backslash a shell-escaped spelling (`Two\\ Words`) pasted from a command line. The
                      matcher escapes it literally, so the rule looks for a backslash in the scanned
                      text and never finds one. This was in the real list, inert, for months.
      separators only compiles to `[-_. ]*`, which matches the empty string at every position and
                      therefore returns an empty match the scanner treats as no match.

    A deny-list that silently accepts entries which can never fire is a deny-list nobody can audit:
    it looks longer than it is, and the entry that is not working is the one you believe in.

    Decoded as utf-8-SIG, and strictly. Strictly, unlike `_decode`, because a mojibake entry does not
    match the name it was meant to match and the failure is silent. `-sig` because a BOM is otherwise
    a decoded character glued to the FIRST entry, which is a real, measured miss: with a BOM the only
    entry in a file stopped matching and the run exited 0, and without it the same file exited 1.
    Editors on this platform write BOMs without being asked.

    One identifier per line, `#` comments and blanks ignored. If a richer format ever seems
    necessary, it is not — a deny-list that needs a schema has stopped being a deny-list.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise GuardError(
            f"there is no private deny-list at {display_path(path)}, and it is not optional — "
            f"private names were NOT checked for, so nothing was scanned and this run is not a "
            f"clean result. {remedy(path)} The private-name check did not run") from exc
    except OSError as exc:
        raise GuardError(f"the private deny-list at {display_path(path)} exists but could not be "
                         f"read ({exc}) — the private-name check did not run") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GuardError(f"the private deny-list at {display_path(path)} is not valid UTF-8 "
                         f"({exc}) — an entry that does not decode does not match, so the check "
                         f"did not run") from exc

    def refuse(lineno: int, why: str) -> GuardError:
        # The entry is NEVER echoed. It is private, and a message that prints it to explain why it
        # is unusable has published it to make a point about formatting.
        return GuardError(f"the private deny-list at {display_path(path)} has an unusable entry on "
                          f"line {lineno}: {why}. An entry that cannot match makes the list look "
                          f"longer than it is, so it is refused rather than compiled into a rule "
                          f"that never fires — fix or remove that line. The private-name check did "
                          f"not run")

    rules: list[Rule] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        if len(entry) < MIN_DENYLIST_LEN:
            raise refuse(lineno, f"it is only {len(entry)} characters, and an entry that short "
                                 f"matches most files, so the guard would block every commit "
                                 f"(entries must be at least {MIN_DENYLIST_LEN} characters)")
        if entry.startswith("!"):
            raise refuse(lineno, "it begins with `!`. Entries are identifiers, not directives — "
                                 "this file has no directive syntax and no way to switch the "
                                 "private-name check off")
        if "\\" in entry:
            raise refuse(lineno, "it contains a backslash, which is matched literally, so the rule "
                                 "would look for a backslash in the scanned text. Write the name "
                                 "unescaped — spaces, hyphens, underscores and dots are already "
                                 "interchangeable")
        if all(ch in SEPARATORS for ch in entry):
            raise refuse(lineno, "it is nothing but separator characters, which compile to a "
                                 "pattern that matches the empty string everywhere and therefore "
                                 "nothing anywhere")
        rules.append(literal_rule("private deny-list entry", entry, sensitive=True))

    if not rules:
        raise GuardError(f"the private deny-list at {display_path(path)} exists but contains no "
                         f"usable entries, and an empty list is not a clean guard — it checks for "
                         f"nothing while looking installed, which is exactly what an interrupted "
                         f"write, a bad merge and a file emptied by hand all leave behind. There "
                         f"is no way to declare that a repository deliberately has no private "
                         f"names; if that is genuinely true, this guard should not be installed "
                         f"here at all. {remedy(path)} The private-name check did not run")
    return rules


def self_probe(rules: list[Rule], denylist_count: int) -> None:
    """Prove the assembled rule set actually matches before trusting it to find nothing.

    Borrowed wholesale from push_guard.py's SECRET_PATTERNS probe, and it earns its place for the
    same reason: an empty or broken matcher set imports perfectly, iterates zero times, and exits 0
    having matched nothing against everything — indistinguishable, in the output, from a clean
    commit. The home-path probe is a synthetic string that appears nowhere real. The deny-list is
    probed structurally (count only), because probing an entry against itself would require holding
    the entry — which `literal_rule` already guarantees by construction.
    """
    probe = "/Users/" + "synthetic-probe-segment"
    home = [r for r in rules if r.name == "absolute home path"]
    if not home or not home[0].find(probe):
        raise GuardError("the absolute-home-path rule does not match a known-good synthetic home "
                         "path — the pattern set is broken, so the scan would match nothing "
                         "against everything")
    # WHAT THIS USED TO TEST AND COULD NOT REACH: `r.pattern.pattern == ""`. No entry can produce an
    # empty pattern — a blank line is skipped before it becomes a rule — so the check was dead, while
    # the failure it was aimed at was live one shape over. A separator-only entry compiles to
    # `[-_. ]*`, which is not the empty pattern but behaves worse than it: it matches the empty
    # string at position 0 of every text, `find` gets `""` back, `""` is falsy, and the rule reports
    # no match against anything for ever. The condition is therefore "matches the empty string",
    # which covers the empty pattern too, and is reachable.
    #
    # `read_denylist` already refuses these at parse time. This stays as the backstop that also
    # covers the DERIVED rules, which come from git config and are not parsed by that function: a
    # `user.name` of `-_-_` is four characters, is not in TOO_GENERIC, and would otherwise compile to
    # exactly this dead rule.
    dead = [r.name for r in rules if r.pattern.search("") is not None]
    if dead:
        raise GuardError(f"a rule ({dead[0]}) compiled to a pattern that matches the empty string, "
                         f"so it reports no match against every possible text — that rule is dead "
                         f"and the rule set cannot be trusted")
    if denylist_count and not any(r.name == "private deny-list entry" for r in rules):
        raise GuardError(f"{denylist_count} deny-list entries were loaded but none reached the "
                         f"rule set — the private-name check did not run")


def redact_location(where: str, rule: Rule) -> str:
    """Redact the LOCATION column with the rule's own pattern, not with the matched string.

    Not decoration. When the match is in a PATH the location string IS the identifier, and printing
    `path docs/<private-name>.md` beside a carefully abbreviated match republishes it in the next
    column. When the match is in a LINE the location is `<file>:<lineno>`, and the file is very often
    named after the same private thing the line mentions.

    THE BUG THIS REPLACES: `where.replace(found, shown)`. `str.replace` is exact — case-sensitive and
    separator-sensitive — while every matcher here is neither. `zarquon-widget` found in a line did
    not replace `Zarquon_Widget` in the path, so the location column printed in full precisely the
    identifier the match column was redacting. Every other spelling the deny-list is built to catch
    was a spelling this line failed to redact.

    Substituting with the rule's own pattern removes the second spelling entirely: whatever the rule
    can match, the rule redacts, in every case and separator variant, with no rule left to keep in
    sync. Empty matches are passed through untouched — `re.sub` would otherwise splice a redaction
    marker between every character — and `self_probe` has already refused any rule that can produce
    one.
    """
    return rule.pattern.sub(lambda m: redact(m.group(0)) if m.group(0) else "", where)


def scan(text: str, where: str, rules: list[Rule], hits: list[tuple[str, str, str]]) -> None:
    """Record at most ONE finding per location: the first rule to fire.

    Not thoroughness for its own sake. A staged file that mentions a private project mentions it
    forty times, and forty near-identical lines of output is a wall the founder scrolls past. One
    finding per line, every line reported.
    """
    for rule in rules:
        found = rule.find(text)
        if found:
            hits.append((redact_location(where, rule), rule.name, redact(found)))
            return


def empty_tree() -> str:
    """The empty-tree oid for THIS repository's object format.

    Not the familiar sha1 constant. A repository created with `--object-format=sha256` has a
    different empty tree, and hardcoding the 40-hex one made the first-commit path fail there —
    push_guard.py shipped the same class of bug against the null oid.
    """
    return git("hash-object", "-t", "tree", os.devnull).strip()


def staged_base() -> str:
    """What the index is diffed against: HEAD, or the empty tree before the first commit."""
    head = git("rev-parse", "--verify", "-q", "HEAD", tolerate_failure=True).strip()
    return head or empty_tree()


def scan_staged(rules: list[Rule]) -> list[tuple[str, str, str]]:
    """Added lines and newly-introduced paths in the index.

    ADDED LINES ONLY, and only paths that this commit ADDS or RENAMES INTO. An identifier already in
    history is already committed; re-reporting it on every subsequent commit that touches the file
    teaches --no-verify faster than any single false positive. The job here is to stop the NEXT one.

    A PATH is scanned as well as content, and that is not redundant: `docs/<private-name>.md` leaks
    the name in the tree listing with no line of content to match.

    `--text --no-textconv --no-ext-diff` for exactly push_guard.py's reason — without them a
    repository can switch its own scan off from the inside, via a `.gitattributes` `-diff` entry or
    a NUL byte in the first 8000 bytes, producing no `+` lines at all and a silent exit 0.
    """
    base = staged_base()
    hits: list[tuple[str, str, str]] = []

    for path in git("diff", "--cached", "--name-only", "--diff-filter=AR",
                    base).splitlines():
        if path.strip():
            scan(path, f"path {path}", rules, hits)

    # `--src-prefix`/`--dst-prefix` PINNED, not inherited. The header parser below keys on `+++ b/`,
    # and `b/` is only the default: `diff.mnemonicPrefix=true` writes `+++ i/<path>` for the index,
    # and `diff.noprefix=true` writes `+++ <path>` with none at all. MEASURED with mnemonicPrefix
    # set: a staged file carrying a deny-listed name was still blocked, but the finding was
    # attributed to `?:1` — the file name gone from the report, which is the half of a finding that
    # makes it actionable. Command-line prefixes override every config spelling of this, including
    # `diff.srcPrefix`/`diff.dstPrefix`, so the parser's assumption is now guaranteed rather than
    # assumed. The repository being defended does not get a vote on the guard's parser.
    diff = git("diff", "--cached", "--text", "--no-textconv", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/",
               "--unified=0", "--no-color", base, timeout=300)

    current = "?"
    lineno = 0
    # HUNK STATE, not a prefix test, and this is the correction of a MEASURED BYPASS.
    #
    # The loop used to skip any line starting `+++`, on the theory that such a line is always a file
    # header. It is not. A header only occurs OUTSIDE a hunk; inside one, `+++ x` is an added line
    # whose content begins `++ x` — and the skip discarded it unscanned. Reproduced: a file whose
    # single line is `++ /Users/<name>/secret` staged as `+++ /Users/<name>/secret`, and the guard
    # exited 0 while the same line with one `+` exited 1. Realistic carriers are not exotic: a
    # committed `.patch` or `.diff` whose own header is `+++ /Users/<name>/b`, and `++i;` in C, C++,
    # Java, JavaScript, Go and Rust.
    #
    # Tracking the state is exact rather than heuristic. Every line inside a hunk begins `+`, `-`,
    # ` ` or `\`, so a line beginning `diff --git ` can only be the start of the next file's header,
    # and no content line can be mistaken for one. Outside a hunk nothing is content, so header
    # lines there are simply not scanned — including `+++ /dev/null`, which now needs no special
    # case because it never appears inside a hunk.
    #
    # `split("\n")`, NOT `splitlines()` — the other half of `--text`, and load-bearing for the same
    # measured reason as in push_guard.py. `str.splitlines()` also breaks on \x0b \x0c \x1c \x1d
    # \x1e \r \x85 U+2028 and U+2029; git separates diff lines with \n and nothing else. A `+` line
    # containing any of those was split into fragments, and the `startswith("+")` filter then
    # discarded every fragment after the first — the content read out of the object store and then
    # thrown away.
    in_hunk = False
    for line in diff.split("\n"):
        if not in_hunk:
            if line.startswith("+++ b/"):
                current = line[6:]
            elif line.startswith("@@"):
                m = re.match(r"@@ -\S+ \+(\d+)", line)
                lineno = int(m.group(1)) if m else 0
                in_hunk = True
            continue
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
            continue
        if not line.startswith("+"):
            continue
        scan(line[1:], f"{current}:{lineno}", rules, hits)
        lineno += 1
    return hits


def scan_message(path: Path, rules: list[Rule]) -> list[tuple[str, str, str]]:
    """The commit message, as `commit-msg` receives it.

    Skips `#` comment lines and everything below a scissors line, because git strips both before the
    message is stored — reporting them would block a commit over text that was never going to be in
    it, and under `commit -v` would additionally duplicate every finding the staged scan just made.

    Read with errors="replace" rather than strictly: an editor that saved the message in a non-UTF-8
    encoding must not be able to skip the scan, and a mangled character cannot conceal a name.
    """
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        raise GuardError(f"the commit message file {path} could not be read ({exc}) — "
                         f"the message was not scanned") from exc

    hits: list[tuple[str, str, str]] = []
    for lineno, line in enumerate(text.split("\n"), 1):
        if SCISSORS.match(line):
            break
        if line.lstrip().startswith("#"):
            continue
        scan(line, f"commit message:{lineno}", rules, hits)
    return hits


def report(hits: list[tuple[str, str, str]], notes: list[str], mode: str) -> int:
    for note in notes:
        print(f"  {mode} note: {note}")
    if not hits:
        return 0
    print(f"\n  {mode} BLOCKED: private identifiers must not enter a public repository.")
    for where, rule, shown in hits:
        print(f"    - {where}: {rule} ({shown})")
    print("\n  A commit is permanent in a way a working file is not: rewriting the branch does not\n"
          "  recall a clone. Remove the identifier, or move the content to a file that is not\n"
          "  committed, then commit again. Do not commit past it.\n")
    return 1


def run(args: argparse.Namespace) -> int:
    notes: list[str] = []
    rules: list[Rule] = [home_path_rule()]
    rules.extend(derived_rules(notes))

    denylist_path = Path(os.environ.get(DENYLIST_ENV) or DEFAULT_DENYLIST).expanduser()
    denylist = read_denylist(denylist_path)
    rules.extend(denylist)
    self_probe(rules, len(denylist))

    if args.message is not None:
        return report(scan_message(Path(args.message), rules), notes, "commit-msg")
    return report(scan_staged(rules), notes, "pre-commit")


def main(argv: list[str] | None = None) -> int:
    """Entry point. 0 clean, 1 finding, 2 the check could not run.

    argparse exits 2 on an unrecognised argument and 0 on --help, which is already this contract —
    a malformed invocation is a check that did not run, not a clean one.
    """
    ap = argparse.ArgumentParser(
        prog="identifier_guard.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true",
                      help="scan the staged diff and staged paths (pre-commit)")
    mode.add_argument("--message", metavar="PATH",
                      help="scan a commit message file (commit-msg, the path in $1)")
    args = ap.parse_args(argv)

    try:
        return run(args)
    except GuardError as exc:
        print(f"\n  commit BLOCKED: {exc}\n"
              f"\n  This is not a clean result — the check did not complete. Fix the environment "
              f"and commit again.\n  Do not commit past it.\n", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # BaseException, so the catch-all below never sees it. Ctrl-C is a check that did not run,
        # and without this it left the interpreter's exit 1 — the code reserved for a finding.
        print("\n  commit BLOCKED: interrupted (Ctrl-C) — the check did not complete.\n"
              "\n  This is not a clean result — nothing was scanned. Commit again to run it.\n",
              file=sys.stderr)
        return 2
    except Exception as exc:                                            # noqa: BLE001
        # A crash must not be able to impersonate a finding, nor a finding a crash. `traceback` is
        # imported at module scope so this handler survives a MemoryError.
        traceback.print_exc()
        print(f"\n  commit BLOCKED: the guard crashed ({type(exc).__name__}: {exc}).\n"
              f"\n  This is not a clean result — the check did not complete. Fix the environment "
              f"and commit again.\n  Do not commit past it.\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
