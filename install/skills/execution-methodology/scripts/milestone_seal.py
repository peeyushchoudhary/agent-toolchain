#!/usr/bin/env python3
"""Record and verify that a milestone's cross-feature gate RAN AND PASSED against a known tree.

A feature's own suite proves the feature. It cannot prove the journey that crosses three features,
because no single feature owns it — and that journey is the whole reason a milestone exists. So a
milestone document declares one command under `## Cross-feature validation`:

    ## Cross-feature validation
    The journeys no single feature's suite can prove.
    Gate: ./gradlew :app:e2eTest

Sealing the milestone — moving it to `status: shipped` — is the claim that the command passed. This
script is what turns that claim into evidence, and the pre-push guard is what refuses the seal
without it.

WHAT THE EVIDENCE IS BOUND TO, AND WHY THAT IS THE TREE. A receipt says "this exact command exited 0
against this exact content". The content is named by HEAD's TREE object id, not by the commit id: a
commit id changes on every amend, rebase and re-message, and re-running a ten-minute end-to-end
suite because a commit message was fixed is how a gate gets bypassed. The tree does not change when
the content does not, so an unchanged tree keeps its evidence and any real edit destroys it. Adding
one character to one file gives a new tree sha, no receipt, and a blocked seal.

WHY THERE IS NO NONCE HERE, ARGUED AGAINST references/junit-evidence.md RATHER THAN AGAINST NOTHING.
That protocol needs a start artifact and a 256-bit nonce because the thing it certifies — a
directory of JUnit XML — is written by a DIFFERENT process, so "were these files produced by the run
I just asked for, or were they already sitting there" is a real and unanswerable question without a
boundary marker. Here the recorder EXECUTES the command and reads its exit status directly from the
child process it spawned, so there is no third-party artifact whose freshness has to be established.
The only axis left to spoof is which content the command ran against, and the tree sha closes it.
Reusing the nonce machinery would add a start artifact, a consumption marker and a second file to
every seal, and would answer a question this shape does not ask.

WHAT THE WORKING TREE HAS TO BE. Clean. HEAD's tree describes what is committed; an uncommitted edit
means the command ran against content the tree sha does not name, and the receipt would then certify
something that was never tested. Refused rather than warned about.

WHERE THE RECEIPT LIVES: OUTSIDE THE REPOSITORY, always. Not `.gitignore`d inside it — outside it.
Two reasons, and the second is the one that decided it. First, a gate's evidence is not part of the
product, and every file a process adds to a repository is a cost paid on every future read of that
directory. Second, evidence that cannot be committed cannot be committed BY ACCIDENT: a receipt
travelling in a clone would let a colleague's push be sealed by a run that happened on someone
else's machine, against a suite that has never executed on theirs. A `.gitignore` line is a request;
a path outside the worktree is a fact. It also means neither this script nor the guard that calls it
ever writes inside the repository under test.

WHAT THIS EVIDENCE DOES NOT DETECT, stated plainly because an overstated evidence claim is worse
than none. It is not tamper-resistant: anyone who can run this script can write the receipt file by
hand, and the trust boundary is the same one junit-evidence.md draws — a freshness and consistency
check inside the operator's own machine, never hostile-writer attestation. It does not expire, so a
receipt stays valid while its tree does; if the environment around the repository changes (a
dependency, a service, a runner) the content is unchanged and the receipt still stands. Re-running
the gate is one command and always available. And it certifies the command's EXIT STATUS, so a gate
command that exits 0 without testing anything produces a receipt that means exactly that much.

Usage:
  milestone_seal.py --root DIR --record M<n>                 run the gate, receipt it on success
  milestone_seal.py --root DIR --verify --tree SHA --command CMD    is there a valid receipt?
  milestone_seal.py --root DIR --gate M<n>                   print the declared command and exit

Exit codes: 0 recorded / valid / printed, 1 the gate failed or no valid receipt exists, 2 the
question could not be answered — a missing document, an undeclared gate, a dirty tree, an
unreadable receipt directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MILESTONE_ID_RE = re.compile(r"^M\d+$")
MILESTONE_DIR = ("docs", "product", "milestones")
# The heading is matched case-insensitively on its exact text. A looser match ("any heading
# containing validation") would pick up a `## Validation strategy` section written for a human and
# treat the first `Gate:`-shaped line under it as an executable command.
GATE_SECTION = "## cross-feature validation"
GATE_RE = re.compile(r"^Gate:\s*(\S.*?)\s*$")
RECEIPT_VERSION = 1


class SealError(Exception):
    """The question could not be answered. Never downgraded to "no evidence": exit 2, not 1.

    "There is no valid receipt" and "I could not find out whether there is one" are different
    sentences, and collapsing them is the failure mode every checker in this toolkit is built
    against. The first is a finding the operator clears by running the gate; the second is an
    environment fault, and reporting it as the first sends them to re-run a suite that will not
    change the answer.
    """


def receipt_dir() -> Path:
    """`$XDG_STATE_HOME/execution-methodology/milestone-seals`, or the XDG default beneath $HOME.

    State, not config and not cache: a cache may be cleared at any moment by anything, and evidence
    that a janitor process is entitled to delete is evidence that will be missing on the one push
    that needed it.
    """
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "execution-methodology" / "milestone-seals"


def receipt_path(tree: str, command: str) -> Path:
    """One receipt per (tree, command) pair.

    The command is hashed into the NAME rather than only stored inside the file, so two milestones
    sealed from one tree — which is normal when a repository takes two milestones together — do not
    overwrite each other's evidence. It is recorded in full inside the file as well, and `verify`
    compares that full string: a truncated digest names the file, it never decides the match.
    """
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:12]
    return receipt_dir() / f"{tree}-{digest}.json"


def git(root: Path, *args: str) -> str:
    """Run git inside `root`. Any failure is a SealError; nothing here reads a failure as data."""
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=120,
                              check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise SealError(f"`git {' '.join(args)}` failed (exit {exc.returncode})"
                        f"{': ' + detail[0] if detail else ''}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SealError(f"`git {' '.join(args[:2])}` timed out") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise SealError(f"`git {' '.join(args[:2])}` could not execute: {exc}") from exc
    return proc.stdout.decode("utf-8", "replace")


def milestone_document(root: Path, milestone: str) -> Path:
    """The one file for `M<n>`. Two files claiming the id is an error, never a first-match.

    `M3-payments.md` and `M3-billing.md` in one repository is a real state — a rename half-done, or
    two people naming the same milestone — and picking whichever sorts first would seal against a
    gate the operator never read. plan_waves.py reports the same collision as W6; this refuses to
    guess for the same reason.
    """
    directory = root.joinpath(*MILESTONE_DIR)
    found = sorted(p for p in directory.glob(f"{milestone}-*.md")) if directory.is_dir() else []
    if not found:
        raise SealError(f"no milestone document at {'/'.join(MILESTONE_DIR)}/{milestone}-<slug>.md")
    if len(found) > 1:
        names = ", ".join(p.name for p in found)
        raise SealError(f"{len(found)} documents claim {milestone} ({names}) — exactly one may")
    return found[0]


def gate_command(text: str) -> str | None:
    """The `Gate:` line under `## Cross-feature validation`, or None if the section declares none.

    The LAST such line in the section wins, deliberately. The section is prose that ends in the
    command, so a `Gate:` appearing earlier is being quoted or explained rather than declared, and
    the operator's eye lands on the last line as the operative one. A document that means to declare
    two gates is declaring one command; `&&` composes them and keeps a single exit status, which is
    the thing a receipt can actually bind to.
    """
    inside, found = False, None
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.strip().lower() == GATE_SECTION
            continue
        if inside:
            match = GATE_RE.match(line.strip())
            if match:
                found = match.group(1)
    return found


def declared_gate(root: Path, milestone: str) -> tuple[Path, str]:
    """(document, command). A milestone with no declared gate cannot be sealed, and that is a 2.

    Not a finding: the guard's finding is "the gate did not pass", and this document cannot answer
    whether it passed because it never said what it is. The remedy is an edit to the document, so
    the message names the section to add rather than a command to run.
    """
    path = milestone_document(root, milestone)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SealError(f"cannot read {path}: {exc}") from exc
    command = gate_command(text)
    if not command:
        raise SealError(f"{path.name} declares no gate: add a `## Cross-feature validation` section "
                        f"ending in a line of the form `Gate: <command>`")
    return path, command


def record(root: Path, milestone: str) -> int:
    path, command = declared_gate(root, milestone)
    dirty = [ln for ln in git(root, "status", "--porcelain").splitlines() if ln.strip()]
    if dirty:
        shown = "\n".join(f"    {ln}" for ln in dirty[:10])
        more = f"\n    ... and {len(dirty) - 10} more" if len(dirty) > 10 else ""
        raise SealError(f"the working tree is not clean, so HEAD's tree does not describe what "
                        f"would be tested:\n{shown}{more}\n  Commit or stash first, then record.")
    tree = git(root, "rev-parse", "HEAD^{tree}").strip()
    head = git(root, "rev-parse", "HEAD").strip()

    print(f"milestone {milestone} ({path.name})")
    print(f"  tree    {tree}")
    print(f"  gate    {command}")
    print(f"  running the gate; a receipt is written only if it exits 0\n", flush=True)
    # `shell=True` because the declared gate is a COMMAND LINE — `./gradlew :app:e2eTest && npm run
    # e2e` — and re-implementing a shell to avoid saying so would break the composition the docstring
    # above tells operators to use. The command comes from a document in the repository the operator
    # is sealing, so this executes content from the tree; it does so ONLY under this explicit,
    # human-typed `--record` invocation, never from the push guard, which is the reason the guard
    # verifies a receipt instead of running the gate itself.
    try:
        completed = subprocess.run(command, shell=True, cwd=str(root), check=False)
    except OSError as exc:
        raise SealError(f"the gate command could not be started: {exc}") from exc
    if completed.returncode != 0:
        print(f"\n  gate FAILED (exit {completed.returncode}). No receipt written — "
              f"{milestone} cannot be sealed until it passes.")
        return 1

    receipt = {"version": RECEIPT_VERSION, "milestone": milestone, "document": path.name,
               "tree": tree, "head": head, "command": command, "exit": 0,
               "recorded": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    target = receipt_path(tree, command)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written whole and then moved into place: a receipt half-written by an interrupted run
        # would be unreadable JSON, which `verify` reports as a 2 — an environment fault the
        # operator cannot act on — rather than the absence it actually is.
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
    except OSError as exc:
        raise SealError(f"the gate PASSED but its receipt could not be written to {target}: {exc}")
    print(f"\n  gate PASSED. Receipt: {target}")
    print(f"  It is valid while the pushed content stays at tree {tree[:12]}; any edit ends it.")
    return 0


def verify(tree: str, command: str) -> int:
    """0 a valid receipt, 1 none. The caller is the push guard, so the output is its finding text."""
    target = receipt_path(tree, command)
    if not target.is_file():
        print(f"no gate receipt for tree {tree[:12]} and this command")
        return 1
    try:
        receipt = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise SealError(f"cannot read the receipt at {target}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SealError(f"the receipt at {target} is not readable JSON: {exc}") from exc
    if not isinstance(receipt, dict):
        raise SealError(f"the receipt at {target} is not a JSON object")
    # Every field is re-checked against the question that was asked, rather than trusted because the
    # FILENAME matched. The name carries a 12-hex-digit prefix of the command digest, which is a
    # lookup key and not a proof; a receipt whose stored command differs from the declared one is a
    # receipt for a different gate no matter what it is called.
    if receipt.get("tree") != tree:
        print(f"the receipt at {target.name} records tree {str(receipt.get('tree'))[:12]}, "
              f"not the pushed {tree[:12]}")
        return 1
    if receipt.get("command") != command:
        print(f"the receipt at {target.name} records a different gate command")
        return 1
    if receipt.get("exit") != 0:
        print(f"the receipt at {target.name} records exit {receipt.get('exit')}, not a pass")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: the current dir)")
    parser.add_argument("--record", metavar="M<n>", help="run the milestone's gate and receipt a pass")
    parser.add_argument("--gate", metavar="M<n>", help="print the declared gate command and exit")
    parser.add_argument("--verify", action="store_true", help="is there a valid receipt?")
    parser.add_argument("--tree", help="with --verify: the tree object id being pushed")
    parser.add_argument("--command", help="with --verify: the declared gate command")
    args = parser.parse_args()

    modes = [bool(args.record), bool(args.gate), args.verify]
    if sum(modes) != 1:
        parser.error("choose exactly one of --record M<n>, --gate M<n>, --verify")
    if args.verify and not (args.tree and args.command):
        parser.error("--verify needs --tree SHA and --command CMD")
    for value in (args.record, args.gate):
        if value and not MILESTONE_ID_RE.match(value):
            # Rejected rather than answered with silence: `--record 3` matches no document, and an
            # empty run reads exactly like "that milestone has nothing to do".
            parser.error(f"a milestone id is M<number>, not {value!r}")

    root = Path(args.root).expanduser()
    if not args.verify and not root.is_dir():
        print(f"ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        if args.verify:
            return verify(args.tree.strip(), args.command)
        if args.gate:
            _, command = declared_gate(root.resolve(), args.gate)
            print(command)
            return 0
        return record(root.resolve(), args.record)
    except SealError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
