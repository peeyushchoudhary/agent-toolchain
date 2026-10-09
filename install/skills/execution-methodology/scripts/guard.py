#!/usr/bin/env python3
"""guard.py --staged | --message FILE | --pre-push [REMOTE URL] | --self-test

A commit (staged diff and paths, or message) may not add an absolute home path, the local git
identity, a name on the mandatory private list ($PD_PRIVATE_IDENTIFIERS, else
~/.claude/private-identifiers.txt; one name per line, `#` comments; case and separators ignored) or
a secret. A push may not carry a secret or a blob over 10 MB, nor move an existing main or master
unless PD_ALLOW_MAIN_PUSH is 1/true/yes/on. Exit 0 clean, 1 finding, 2 could not run (not clean).
"""
from __future__ import annotations

import itertools
import os
import re
import subprocess
import sys
import traceback
import unicodedata
from pathlib import Path

LIST_ENV = "PD_PRIVATE_IDENTIFIERS"
HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._-]{2,})", re.IGNORECASE)
# The path token right before a HOME_PATH match. A relative one (core/users/X) makes the match a
# later segment of that path, not a home; an absolute one (/System/Volumes/Data/Users/x) or a flag
# (-I/Users/x) does not.
TOKEN_BEFORE = re.compile(r"[A-Za-z0-9._/-]*$")
PLACEHOLDERS = frozenset({"anything", "example", "home", "me", "name", "root", "runner", "shared",
                          "someone", "user", "username", "you", "youruser", "yourname", "your-name"})
TOO_GENERIC = frozenset({"admin", "example", "git", "github", "gitlab", "local", "localhost", "main",
                         "master", "none", "null", "origin", "root", "test", "user", "users", "home"})
# Unicode categories Pd and Zs, by codepoint because half are invisible; test_guard.py checks the
# list against the running interpreter. A run of separators in an entry matches any run, or none.
SEPARATORS = "-_. " + "".join(chr(c) for c in (
    0x00A0, 0x058A, 0x05BE, 0x1400, 0x1680, 0x1806, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005,
    0x2006, 0x2007, 0x2008, 0x2009, 0x200A, 0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x202F,
    0x205F, 0x2E17, 0x2E1A, 0x2E3A, 0x2E3B, 0x2E40, 0x2E5D, 0x3000, 0x301C, 0x3030, 0x30A0, 0xFE31,
    0xFE32, 0xFE58, 0xFE63, 0xFF0D, 0x10D6E, 0x10EAD))
SECRET_PATTERNS = (  # name, pattern, a probe it must match (split: this file does not self-match)
    ("AWS access key id", r"\bAKIA[0-9A-Z]{16}\b", "AKIA" + "IOSFODNN7EXAMPLE"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{36,}", "ghp_" + "a1" * 18),
    ("Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b", "AIza" + "b2" * 17 + "c"),
    ("Slack token", r"\bxox[baprs]-[0-9A-Za-z-]{10,}", "xoxb-" + "d3" * 5),
    ("Stripe live key", r"\bsk_live_[0-9a-zA-Z]{20,}", "sk_live_" + "e4" * 10),
    ("private key block", r"-----BEGIN (?:[A-Z ]+ )?PRIVATE" + r" KEY-----",
     "-----BEGIN RSA PRIV" + "ATE KEY-----"),
)
SCISSORS = re.compile(r"^\s*#\s*-+\s*>8\s*-+")
EDITOR_MARKER = re.compile(r"^(\S) Please enter the commit message")
MAX_BLOB = 10 * 1024 * 1024
DEFAULT_BRANCHES = ("refs/heads/main", "refs/heads/master")
AFFIRMATIVE = frozenset({"1", "true", "yes", "on"})
HOME_RULE = ("absolute home path", HOME_PATH, "home")
DIFF = ("--text", "--no-textconv", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", "-U0",
        "--no-color")  # the repository being scanned cannot switch the scan off or move its headers


class GuardError(RuntimeError):
    """The check could not complete: exit 2."""


def secret_rules() -> list:
    try:
        return [(name, re.compile(p), "secret") for name, p, _ in SECRET_PATTERNS]
    except re.error:
        return []  # check_rules() then refuses to run


SECRET_RULES = secret_rules()


def check_rules() -> None:
    """Fail closed (old push case 18): every secret rule is present, live and matches its probe."""
    rules = {r[0]: r for r in SECRET_RULES}
    for name, _, probe in SECRET_PATTERNS or (("any secret rule", "", ""),):
        if name not in rules or rules[name][1].search("") or not find(rules[name], probe):
            raise GuardError(f"the secret rule set is unusable ({name} is missing, dead or misses "
                             f"its probe), so nothing was scanned")


def run_git(args, codes=(0,), stdin: str | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=false", *args], capture_output=True,
                           timeout=300, input=None if stdin is None else stdin.encode())
    except (OSError, subprocess.SubprocessError) as exc:
        raise GuardError(f"`git {' '.join(args[:2])}` could not run ({type(exc).__name__})") from exc
    if p.returncode not in codes:
        why = p.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GuardError(f"`git {' '.join(args[:2])}` exited {p.returncode}"
                         f"{': ' + display(why[0]) if why else ''}; the scan did not run")
    return p.returncode, p.stdout.decode("utf-8", "replace")


def git(*args: str, stdin: str | None = None) -> str:
    return run_git(args, stdin=stdin)[1]


def display(text) -> str:
    """Text as it is safe to print: the real home as `~`, any other home segment redacted."""
    text, home = str(text), str(Path.home())
    if len(home) > 1:
        text = re.sub(re.escape(home) + r"(?![A-Za-z0-9._-])", "~", text)
    return HOME_PATH.sub(lambda m: m[0][:-len(m[1])] + m[1][0] + "…", text)


def literal(term: str) -> re.Pattern[str]:
    sep = f"[{re.escape(SEPARATORS)}]*"
    return re.compile("".join(sep if is_sep else re.escape("".join(run)) for is_sep, run
                              in itertools.groupby(term, lambda c: c in SEPARATORS)), re.IGNORECASE)


def find(rule, text: str) -> str | None:
    for m in rule[1].finditer(text):
        if not m[0]:
            continue
        if rule[2] == "home":
            before = TOKEN_BEFORE.search(text[:m.start()])[0]
            if m[1].lower() in PLACEHOLDERS or (before and before[0] not in "/-"):
                continue  # a placeholder, or a later segment of a relative path
        return m[0]
    return None


def shown(rule, found: str) -> str:
    return found[:4] + "…" if rule[2] == "secret" else display(found) if rule[2] == "home" \
        else found[0] + "…"


def scan(text: str, where: str, rules, hits: list[str]) -> None:
    """One finding per location: the first rule that fires. Never prints a private value whole."""
    for rule in rules:
        found = find(rule, text)
        if found:
            for r in rules:
                if r[2] != "secret":
                    where = r[1].sub(lambda m: shown(r, m[0]) if find(r, m[0]) else m[0], where)
            hits.append(f"{rule[0]}: {where} ({shown(rule, found)})")
            return


def scan_diff(diff: str, rules, hits: list[str]) -> None:
    """Added lines of a -U0 diff. Hunk state, not a `+++` prefix test: `++x` content is scanned."""
    current, lineno, in_hunk = "?", 0, False
    for line in diff.split("\n"):  # never splitlines(): git separates diff lines with \n only
        if in_hunk and line[:1] in ("+", "-", " ", "\\"):
            if line[0] == "+":
                scan(line[1:], f"{current}:{lineno}", rules, hits)
                lineno += 1
            continue
        in_hunk = False
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)", line)
            lineno, in_hunk = (int(m[1]) if m else 0), True


def identity_rules(notes: list[str]) -> list:
    def config(key: str) -> str:
        return run_git(["config", "--get", key], codes=(0, 1))[1].strip()
    email, name, url = config("user.email"), config("user.name"), config("remote.origin.url")
    m = re.match(r"^[^/]+@[^/:]+:([^/]+)/", url) or \
        re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?[^/]+/([^/]+)/", url)
    values = [("git author email", email), ("git author email local-part", email.split("@")[0]),
              ("git author name", name), *[("git author name part", p) for p in name.split()
                                           if len(p) >= 5], ("remote account name", m[1] if m else "")]
    rules, seen = [], set()
    for label, value in values:
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        if len(value) < 4 or value.lower() in TOO_GENERIC:
            notes.append(f"{label} ({value[0]}…) is too short or generic to match on; not checked")
        else:
            rules.append((label, literal(value), "private"))
    return rules


def usable(c: str) -> bool:
    """ASCII printable, a folded separator, or a letter, digit or mark in any script."""
    return c in SEPARATORS or (c.isprintable() if c.isascii() else unicodedata.category(c)[0] in "LNM")


def private_rules() -> list:
    path = Path(os.environ.get(LIST_ENV) or Path.home() / ".claude" / "private-identifiers.txt")
    where = display(path.expanduser())
    fix = (f"create {where} with one name per line (`#` comments) or point {LIST_ENV} at it; "
           f"private names were not checked")
    try:
        text = path.expanduser().read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        state = "does not exist" if isinstance(exc, FileNotFoundError) else \
            f"could not be read as UTF-8 ({type(exc).__name__})"
        raise GuardError(f"the private-name list at {where} {state}: {fix}") from None
    rules = []
    for n, line in enumerate(text.splitlines(), 1):
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        bad = ("is under 3 characters" if len(entry) < 3 else "begins with `!`; there are no "
               "directives and no off switch" if entry[0] == "!" else "contains a backslash"
               if "\\" in entry else next((f"contains U+{ord(c):04X} ({unicodedata.name(c, '?')})"
                                           for c in entry if not usable(c)), None)
               or ("is only separators" if all(c in SEPARATORS for c in entry) else None))
        if bad:
            raise GuardError(f"the private-name list at {where}, line {n}, {bad}; fix that line "
                             f"(the entry is not shown). The private-name check did not run")
        rules.append(("private name", literal(entry), "private"))
    if not rules:
        raise GuardError(f"the private-name list at {where} contains no usable entries: {fix}")
    return rules


def commit_rules(notes: list[str]) -> list:
    rules = [HOME_RULE, *identity_rules(notes), *private_rules(), *SECRET_RULES]
    dead = [r[0] for r in rules if r[1].search("")]
    if dead:
        raise GuardError(f"a rule ({dead[0]}) matches the empty string, so that rule is dead "
                         f"and nothing it covers was checked")
    return rules


def staged(rules) -> list[str]:
    head = run_git(["rev-parse", "--verify", "-q", "HEAD"], codes=(0, 1))[1].strip()
    base = head or git("hash-object", "-t", "tree", os.devnull).strip()
    hits: list[str] = []
    for path in git("diff", "--cached", "--name-only", "-z", "--diff-filter=AR", base).split("\0"):
        if path:
            scan(path, f"path {path}", rules, hits)
    scan_diff(git("diff", "--cached", *DIFF, base), rules, hits)
    return hits


def message(path: str, rules) -> list[str]:
    try:
        text = Path(path).read_bytes().decode("utf-8", "replace")
    except OSError as exc:
        raise GuardError(f"the commit message file {display(path)} could not be read "
                         f"({type(exc).__name__}); the message was not scanned") from None
    # Scan every line Git keeps; when unsure, scan it (a reported template comment is a nuisance, a
    # missed retained line is a leak). As in Git: verbatim and whitespace keep every line; strip drops
    # core.commentChar lines; scissors cuts at the scissors line, and the default also drops comment
    # lines, but both only when Git opened the message in an editor. Without an editor (-m, -F,
    # --no-edit) scissors and the default keep every line. "Edited" needs all of: the template marker,
    # Git's edit file COMMIT_EDITMSG, a commit hook Git ran (GIT_INDEX_FILE set) and no GIT_EDITOR=:
    # (Git sets that when no editor is used). The marker alone never drops a line.
    lines, hits, comment = text.split("\n"), [], None
    mode = run_git(["config", "--get", "commit.cleanup"], codes=(0, 1))[1].strip() or "default"
    marker = next((m for m in map(EDITOR_MARKER.match, lines) if m), None)
    edited = bool(marker) and Path(path).name == "COMMIT_EDITMSG" and \
        "GIT_INDEX_FILE" in os.environ and os.environ.get("GIT_EDITOR") != ":"
    if mode == "strip":
        char = run_git(["config", "--get", "core.commentChar"], codes=(0, 1))[1].strip()
        comment = char if len(char) == 1 else "#"
    elif mode in ("default", "scissors") and edited:
        cut = marker[1]
        lines = list(itertools.takewhile(lambda ln: not SCISSORS.match(ln.replace(cut, "#", 1)), lines))
        comment = cut if mode == "default" else None
    for n, line in enumerate(lines, 1):
        if not (comment and line.lstrip().startswith(comment)):
            scan(line, f"commit message:{n}", rules, hits)
    return hits


def pre_push(payload: str, name: str = "") -> list[str]:
    git("rev-parse", "--show-toplevel")  # a push from outside a work tree is not scanned clean
    hits: list[str] = []
    # a new ref skips only what the destination already has; another remote's history is not public
    known = name in git("remote").split() and not re.search(r"[*?\[]", name)
    for parts in (raw.split() for raw in payload.splitlines() if raw.strip()):
        if len(parts) != 4:
            raise GuardError(f"unparseable pre-push payload line ({len(parts)} fields, expected 4)")
        _, local, ref, remote = parts
        if not local.strip("0") or local == remote:
            continue  # a deletion, or nothing new
        if ref in DEFAULT_BRANCHES and remote.strip("0") and \
                os.environ.get("PD_ALLOW_MAIN_PUSH", "").strip().lower() not in AFFIRMATIVE:
            hits.append(f"direct push: {ref} (use a pull request; PD_ALLOW_MAIN_PUSH=1/true/yes/on "
                        f"waives this rule only; 0, false, no, off or anything else does not)")
        if not remote.strip("0"):
            rng = [local, "--not", f"--remotes={name}"] if known else [local]
        elif run_git(["cat-file", "-e", remote], codes=(0, 1))[0] == 1:
            raise GuardError(f"the remote tip {remote[:12]} is not in the local object store, so "
                             f"the pushed range cannot be computed; run `git fetch` and push again")
        else:
            rng = [f"{remote}..{local}"]
        objects = {oid: name for oid, _, name in (ln.partition(" ") for ln in
                                                  git("rev-list", "--objects", *rng).splitlines()) if name}
        if objects:
            sizes = git("cat-file", "--batch-check=%(objecttype) %(objectsize) %(objectname)",
                        stdin="\n".join(objects) + "\n")
            for kind, size, oid in (ln.split() for ln in sizes.splitlines() if len(ln.split()) == 3):
                if kind == "blob" and int(size) > MAX_BLOB:
                    hits.append(f"blob over 10 MB: {objects[oid]} ({int(size) / 2**20:.1f} MB, "
                                f"limit 10 MB)")
        # -m: a merge is diffed against each parent, so content only its resolution adds is seen
        scan_diff(git("log", "-p", "-m", *DIFF, "--format=%H", *rng), SECRET_RULES, hits)
    return list(dict.fromkeys(hits))  # a line seen against both parents is one finding


def self_test() -> int:
    rules = [HOME_RULE, ("private name", literal("zarquon-widget"), "private"), *SECRET_RULES]
    cases = [("/Users" + "/hoopfrabjous/x", 1), ("/HOME" + "/hoopfrabjous", 1), ("Zarquon Widget", 1),
             ("ZARQUON_WIDGET", 1), ("zarquonwidget", 1), ("key " + "AKIA" + "IOSFODNN7EXAMPLE", 1),
             ("-----BEGIN RSA PRIV" + "ATE KEY-----", 1), ("/Users/<name>/code", 0),
             ("/home/runner/work, /home/$USER", 0), ("the upstream loader", 0),
             ("app/core/" + "users/UserDtos.java", 0), ("cc -I/Users" + "/hoopfrabjous/include", 1),
             ("/System/Volumes/Data/Users" + "/hoopfrabjous", 1)]
    failed = [text for text, want in cases if bool(next((1 for r in rules if find(r, text)), 0)) != want]
    hits: list[str] = []
    scan_diff("+++ b/f.c\n@@ -0,0 +1,2 @@\n+++counter;\n+++ /Users" + "/hoopfrabjous/b\n", rules, hits)
    if hits != ["absolute home path: f.c:2 (/Users/h…)"]:
        failed.append(f"diff shape: {hits}")
    print(*(f"guard self-test FAIL: {display(f)}" for f in failed),
          "guard self-test: " + ("FAIL" if failed else f"PASS ({len(cases) + 1} fixtures)"), sep="\n")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    a = sys.argv[1:] if argv is None else argv
    try:
        if a in (["-h"], ["--help"]):
            print(__doc__)
            return 0
        check_rules()
        if a == ["--self-test"]:
            return self_test()
        notes: list[str] = []
        if a[:1] == ["--pre-push"] and len(a) <= 3 and not any(x.startswith("-") for x in a[1:]):
            hits = pre_push(sys.stdin.read(), *a[1:2])
        elif a == ["--staged"]:
            hits = staged(commit_rules(notes))
        elif len(a) == 2 and a[0] == "--message":
            hits = message(a[1], commit_rules(notes))
        else:
            print("usage: " + __doc__.splitlines()[0], file=sys.stderr)
            return 2
    except (GuardError, KeyboardInterrupt) as exc:
        print(f"guard could not run: {str(exc) or 'interrupted'}. This is not a clean result.",
              file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - a crash must never read as clean or as a finding
        print(display(traceback.format_exc()), file=sys.stderr, end="")
        print(f"guard could not run: the guard crashed ({type(exc).__name__}); the check did not "
              f"complete.", file=sys.stderr)
        return 2
    for line in [f"guard note: {n}" for n in notes] + [f"guard BLOCKED: {h}" for h in hits]:
        print(line)
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
