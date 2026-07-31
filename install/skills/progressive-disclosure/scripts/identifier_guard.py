#!/usr/bin/env python3
"""commit-time guard: private identifiers must not enter a deliberately-public repository.

push_guard.py blocks what a *push* makes permanent. This blocks what a *commit* makes permanent,
which is a different set: a credential can be rotated, but an identifier is a fact about the world
and cannot be. Once a private project name, a home directory path, or an account handle is in a
public repository's history, rewriting the branch does not recall the clones, the forks, or the
mirrors — so the only place to stop it is before the object is written.

  BLOCK  an absolute home path in a staged line, a staged path, or the commit message
  BLOCK  the local git identity (author email, author name, remote account segment)
  BLOCK  any name on the private deny-list, if a deny-list is installed
  state  that the deny-list was NOT found, when it is absent — an absent list is not a clean scan

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


def read_denylist(path: Path, notes: list[str]) -> list[Rule]:
    """Load the private deny-list. Absent is allowed and announced; broken is exit 2.

    ABSENT is a legitimate state — this file is per-machine and never travels with a clone, so the
    guard has to work without it. It must not crash, and it must not pass in silence: a run with no
    deny-list checked strictly less than a run with one, and the difference has to be visible or the
    founder cannot tell the two apart.

    PRESENT-BUT-EMPTY is NOT the same state and is treated as broken. An empty list is what a
    truncated write, a bad merge or an interrupted edit leaves behind, and it disables the rule while
    looking exactly like a healthy install — the same failure push_guard.py's empty-SECRET_PATTERNS
    probe exists to catch, in the same directory, one guard over. Emptiness that is DELIBERATE is
    expressed by deleting the file, which produces the announcement above.

    Decoded strictly, unlike `_decode`. A mojibake deny-list entry does not match the name it was
    meant to match, and the failure is silent; refusing to run is the only honest response.

    One identifier per line, `#` comments and blanks ignored. If a richer format ever seems
    necessary, it is not — a deny-list that needs a schema has stopped being a deny-list.
    """
    if not path.exists():
        # Not "the generic rules ABOVE": `report` prints every note before anything else, so there
        # is nothing above this line to refer to.
        notes.append(f"no private deny-list at {path} — it was NOT found, so private names were "
                     f"NOT checked for. The generic rules still ran.")
        return []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GuardError(f"the private deny-list at {path} exists but could not be read ({exc}) — "
                         f"the private-name check did not run") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GuardError(f"the private deny-list at {path} is not valid UTF-8 ({exc}) — an entry "
                         f"that does not decode does not match, so the check did not run") from exc

    rules: list[Rule] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        if len(entry) < MIN_DENYLIST_LEN:
            # The entry is NOT echoed. It is private, and a message that prints it to prove it is
            # too short has published it to make a point about length.
            raise GuardError(f"the private deny-list at {path} has an entry on line {lineno} of "
                             f"only {len(entry)} characters. An entry that short matches most "
                             f"files, so the guard would block every commit — fix the line "
                             f"(entries must be at least {MIN_DENYLIST_LEN} characters). The "
                             f"private-name check did not run")
        rules.append(literal_rule("private deny-list entry", entry, sensitive=True))

    if not rules:
        raise GuardError(f"the private deny-list at {path} exists but contains no usable entries. "
                         f"An empty list silently checks for nothing while looking installed — if "
                         f"that is deliberate, DELETE the file, which the guard reports honestly. "
                         f"The private-name check did not run")
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
    if any(r.sensitive and r.pattern.pattern == "" for r in rules):
        raise GuardError("a rule compiled to an empty pattern, which matches everywhere and "
                         "therefore nowhere useful — the rule set is broken")
    if denylist_count and not any(r.name == "private deny-list entry" for r in rules):
        raise GuardError(f"{denylist_count} deny-list entries were loaded but none reached the "
                         f"rule set — the private-name check did not run")


def scan(text: str, where: str, rules: list[Rule], hits: list[tuple[str, str, str]]) -> None:
    """Record at most ONE finding per location: the first rule to fire.

    Not thoroughness for its own sake. A staged file that mentions a private project mentions it
    forty times, and forty near-identical lines of output is a wall the founder scrolls past. One
    finding per line, every line reported.
    """
    for rule in rules:
        found = rule.find(text)
        if found:
            shown = redact(found)
            # The LOCATION is redacted too, with the same substitution. It is not decoration: when
            # the match is in a PATH rather than in a line, the location string contains the very
            # identifier the finding is redacting, and printing `path docs/<private-name>.md`
            # alongside a carefully abbreviated match republishes it in the next column.
            hits.append((where.replace(found, shown), rule.name, shown))
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

    diff = git("diff", "--cached", "--text", "--no-textconv", "--no-ext-diff",
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
    denylist = read_denylist(denylist_path, notes)
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
