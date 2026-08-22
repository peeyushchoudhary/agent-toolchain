#!/usr/bin/env python3
"""Break-test for milestone_seal.py — proves the receipt is checked, not merely found.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
found by mutating this file's sibling and watching the skill's own `unittest discover` stay green,
so a regression re-breaks a named case instead of silently sealing a milestone.

  1  record a passing gate, then verify it                  exit 0, receipt bound to HEAD's tree
  2  a receipt FOUND by name but recording another tree      exit 1  <- the name is not the proof
  3  `## Validation strategy` is not the gate section        the gate is not read out of it
  4  the LAST `Gate:` line in the section is the gate        an earlier one is prose, not a command
  5  a receipt whose JSON is not an object                   exit 2, never the 1 reserved for
                                                             "no valid receipt"
  6  --record together with --verify                         refused; it must not silently verify

WHAT MADE THESE CASES REAL, measured rather than imagined. Each mutation below was applied to
milestone_seal.py and each left the vendored suite GREEN:
    delete the `receipt.get("tree") != tree` re-check in verify()        green
    `inside = line.strip().lower() == GATE_SECTION` -> `"validation" in ...`  green
    `Gate:` last-line-wins -> first-line-wins                            green
    `if not isinstance(receipt, dict)` -> dead                           green
    `if sum(modes) != 1` -> `if sum(modes) < 1`                          green
Case 2 is the sharpest of them. verify()'s own comment says "Every field is re-checked against the
question that was asked, rather than trusted because the FILENAME matched" — and the command and
exit re-checks ARE tested, while the TREE re-check, the one the whole tree-versus-commit argument
rests on, was tested by nothing. Case 6 is the same shape as a plan_waves.py defect already on the
record: a flag accepted and then not acted on.

TWO PROPERTIES THIS FILE DELIBERATELY LEAVES UNTESTED, and says so rather than writing decoration.
Truncating the command digest in the receipt NAME from 12 hex characters to 2 also leaves the suite
green, but no honest case distinguishes the two lengths without brute-forcing a collision, and a
case pinned to a hand-found collision tests the collision rather than the rule. Replacing the
write-then-rename with a direct write also leaves the suite green, but reproducing it needs a
process killed between the two calls, which this file cannot arrange without leaving a stray
process behind. Both are recorded here as known gaps, not covered.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process. `XDG_STATE_HOME` is
redirected into a temporary directory, so no case can read or write the operator's real receipts.
Nothing here writes inside the repository.

Run:  python3 milestone_seal_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "milestone_seal.py"
GATE = "true"                       # a gate command that exists everywhere and exits 0

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def run(state: Path, *args: str) -> tuple[int, str]:
    env = {**os.environ, "XDG_STATE_HOME": str(state), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=env)
    return proc.returncode, proc.stdout + proc.stderr


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def new_repo(root: Path, section: str) -> Path:
    """A repository with one milestone document whose validation section is `section`."""
    repo = root / "repo"
    (repo / "docs" / "product" / "milestones").mkdir(parents=True)
    (repo / "docs" / "product" / "milestones" / "M1-example.md").write_text(section,
                                                                           encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "selftest@example.invalid")
    git(repo, "config", "user.name", "selftest")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "milestone")
    return repo


def receipt_file(state: Path, tree: str, command: str) -> Path:
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:12]
    return state / "execution-methodology" / "milestone-seals" / f"{tree}-{digest}.json"


SECTION = f"""# M1 example

## Cross-feature validation
The journeys no single feature's suite can prove.
Gate: {GATE}
"""


def case_record_then_verify() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state"
        repo = new_repo(root, SECTION)
        tree = git(repo, "rev-parse", "HEAD^{tree}").strip()

        code, out = run(state, "--root", str(repo), "--gate", "M1")
        check("1a --gate prints the declared command", code == 0 and out.strip() == GATE,
              f"got {code}: {out[:200]}")

        code, out = run(state, "--root", str(repo), "--record", "M1")
        check("1b a passing gate records", code == 0, f"got {code}: {out[:300]}")
        check("1c the receipt is written where verify will look for it",
              receipt_file(state, tree, GATE).is_file(),
              str(receipt_file(state, tree, GATE)))

        code, out = run(state, "--verify", "--tree", tree, "--command", GATE)
        check("1d verify finds it", code == 0, f"got {code}: {out[:200]}")

        code, out = run(state, "--verify", "--tree", "0" * 40, "--command", GATE)
        check("1e a different tree has no receipt", code == 1, f"got {code}")


def case_receipt_names_the_tree_but_records_another() -> None:
    """The name is a lookup key, not a proof. Deleting the re-check left the suite green."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state"
        repo = new_repo(root, SECTION)
        tree = git(repo, "rev-parse", "HEAD^{tree}").strip()
        check("2a a real receipt exists first",
              run(state, "--root", str(repo), "--record", "M1")[0] == 0)

        # The file KEEPS the name derived from (tree, command) — so it is found — and records a
        # different tree inside. This is what a stale receipt edited by hand, or carried across a
        # rebase, looks like on disk.
        target = receipt_file(state, tree, GATE)
        receipt = json.loads(target.read_text(encoding="utf-8"))
        receipt["tree"] = "1" * 40
        target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

        code, out = run(state, "--verify", "--tree", tree, "--command", GATE)
        check("2b a receipt recording another tree is not a valid receipt", code == 1,
              f"got {code}: {out[:300]}")
        check("2c and it says which tree the receipt actually records",
              "1111" in out, out[:300])


def case_gate_section_is_matched_exactly() -> None:
    """`## Validation strategy` is prose for a human. Its `Gate:`-shaped line is not a command."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state"
        repo = new_repo(root, """# M1 example

## Validation strategy
Gate: rm -rf /nowhere-this-must-never-run

## Notes
Nothing else.
""")
        code, out = run(state, "--root", str(repo), "--gate", "M1")
        check("3a a document with no cross-feature section declares no gate", code == 2,
              f"got {code}: {out[:300]}")
        check("3b and the command under the human section is not printed as one",
              "rm -rf" not in out, out[:300])
        check("3c the remedy names the section to add",
              "Cross-feature validation" in out, out[:300])


def case_last_gate_line_wins() -> None:
    """A `Gate:` earlier in the section is being quoted or explained, not declared."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state"
        repo = new_repo(root, """# M1 example

## Cross-feature validation
Write the command on the last line, like `Gate: ./gradlew test`.
Gate: quoted-example-never-run
Gate: true
""")
        code, out = run(state, "--root", str(repo), "--gate", "M1")
        check("4a the LAST Gate line is the operative one", code == 0 and out.strip() == "true",
              f"got {code}: {out[:200]}")
        check("4b the earlier one is not what gets sealed",
              "quoted-example-never-run" not in out, out[:200])


def case_unreadable_receipt_is_a_two() -> None:
    """"There is no valid receipt" and "I could not find out" are different sentences."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state"
        tree = "a" * 40
        target = receipt_file(state, tree, GATE)
        target.parent.mkdir(parents=True)

        target.write_text("[]\n", encoding="utf-8")
        code, out = run(state, "--verify", "--tree", tree, "--command", GATE)
        check("5a a receipt that is valid JSON but not an object exits 2", code == 2,
              f"got {code}: {out[:300]}")
        check("5b it says so in words, with no traceback",
              "Traceback" not in out and "JSON object" in out, out[:300])

        target.write_text("{not json\n", encoding="utf-8")
        code, out = run(state, "--verify", "--tree", tree, "--command", GATE)
        check("5c a receipt that is not JSON at all also exits 2", code == 2, f"got {code}")
        check("5d and never the exit 1 reserved for an absent receipt",
              code != 1 and "Traceback" not in out, out[:300])


def case_two_modes_is_refused() -> None:
    """A flag accepted and then not acted on is the failure this toolkit keeps finding."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        state = root / "state"
        repo = new_repo(root, SECTION)
        tree = "b" * 40
        code, out = run(state, "--root", str(repo), "--record", "M1",
                        "--verify", "--tree", tree, "--command", GATE)
        check("6a --record together with --verify is refused", code == 2, f"got {code}")
        check("6b it says exactly one mode may be chosen",
              "exactly one" in out, out[:300])
        check("6c and it did NOT quietly run the verify half instead of recording",
              not receipt_file(state, tree, GATE).exists()
              and "no gate receipt" not in out, out[:300])


def main() -> int:
    if not SCRIPT.exists():
        print(f"milestone_seal.py not found at {SCRIPT}", file=sys.stderr)
        return 2
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("git is not available; this break-test needs a real repository", file=sys.stderr)
        return 2

    print("milestone_seal break-test")
    for case in (case_record_then_verify, case_receipt_names_the_tree_but_records_another,
                 case_gate_section_is_matched_exactly, case_last_gate_line_wins,
                 case_unreadable_receipt_is_a_two, case_two_modes_is_refused):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the seal is decided by the receipt's contents, not by its name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
