#!/usr/bin/env python3
"""Break-test for the `product definition` check in check_conformance.py.

Every case below is a defect SHAPE this file's siblings actually produced, and all of them have one
signature: a clean exit 0 from a checker that inspected nothing. That is the whole reason the ninth
check exists — the eight before it can be satisfied at once on a repository with no
product-definition layer, and the only thing `--fix` then repairs is the methodology render, which
is the DOCUMENT DESCRIBING the layer that is not there.

  1  `docs/product/` missing is a FINDING, not a clean run
                        <- a linter pointed at a directory that does not exist reports nothing and
                           exits 0, which is indistinguishable from a clean repository
  2  specs named `specs/<slug>/spec.md` are COUNTED and NAMED, though spec_check.py exits 0
                        <- measured on a real repository: 236 documents under docs/product, 0 bound
                           by any schema rule, 233 of them in specs/ under a name nothing reads.
                           spec_check.py exits 0 there. The exit code is not the answer.
  3  `--fix` NEVER touches a product document, on a repository this check calls red
                        <- the check owns no Repair, so the repair plan cannot grow a spec by
                           accident. Front matter carries `reviewed_by:`; generating it forges a
                           review record.
  4  spec_check.py absent is COULD NOT BE CHECKED (exit 2), never CONFORMS
                        <- a missing callee that returned a clean verdict is the false green this
                           whole file is built against.

EVERY CASE IS PAIRED. Case 1 and case 2 each carry a green control built from the same fixture, so
no case can pass against a check that has started reporting everything.

HERMETIC. `check_conformance.py` resolves its callees under `PROJECT_CONFORMANCE_HOME`, so each
case builds a throwaway home holding only `execution-methodology/scripts` and points the tool at
it. Nothing here reads or writes the real `~/.claude`, and nothing writes inside this repository.

Run:  python3 product_definition_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check_conformance.py"
# The vendored sibling this check calls. `../..` is the skills directory in both the installed and
# the vendored layout, which is why the fake home below can be built from either.
SPEC_SCRIPTS = HERE.parent.parent / "execution-methodology" / "scripts"

CHECK = "product definition"
PRD = "---\ntitle: A product\nstatus: approved\nupdated: 2026-01-01\n---\n\n# A product\n"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def fake_home(tmp: Path) -> Path:
    """A home holding exactly one skill: the one this check calls."""
    home = tmp / "home"
    target = home / ".claude" / "skills" / "execution-methodology"
    target.mkdir(parents=True)
    shutil.copytree(SPEC_SCRIPTS, target / "scripts")
    return home


def build(tmp: Path, name: str, files: dict[str, str]) -> Path:
    root = tmp / name
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


def conformance(root: Path, home: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), str(root), "--only", CHECK, *extra],
                          capture_output=True, text=True,
                          env={**os.environ,
                               "PROJECT_CONFORMANCE_HOME": str(home),
                               "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def spec_check_alone(root: Path, home: Path) -> int:
    """What the owning checker says on its own, which is the number the defect hid behind."""
    script = home / ".claude" / "skills" / "execution-methodology" / "scripts" / "spec_check.py"
    proc = subprocess.run([sys.executable, str(script), "--root", str(root)],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode


def case_1_missing_layer(tmp: Path, home: Path) -> None:
    print("case 1: `docs/product/` missing is a finding, not a clean run")
    absent = build(tmp, "c1-absent", {"README.md": "# A repository\n"})
    rc, out = conformance(absent, home)
    check("a repository with no docs/product does NOT conform", rc == 1, f"exit {rc}")
    check("and the report says so in those words",
          "`docs/product/` does not exist" in out, out[:300])
    check("and it names the remedy without offering to perform it",
          "remedy:" in out and "NOTHING HERE REWRITES A PRODUCT DOCUMENT" in out)

    # THE PAIR. The same tool, the same flags, one directory different.
    present = build(tmp, "c1-present", {"docs/product/prd.md": PRD})
    rc, out = conformance(present, home)
    check("the control: the same fixture WITH docs/product conforms", rc == 0, out[:400])


def case_2_unbound_specs(tmp: Path, home: Path) -> None:
    print("case 2: specs no rule binds are counted, though spec_check.py exits 0")
    red = build(tmp, "c2-unbound", {"docs/product/prd.md": PRD,
                                    "docs/product/specs/login/spec.md": "# Login\n\nIt logs in.\n"})
    owner_rc = spec_check_alone(red, home)
    check("the control that makes this case worth having: spec_check.py alone exits 0 here",
          owner_rc == 0, f"spec_check.py exited {owner_rc}, so this fixture no longer "
                         f"reproduces the silence being tested")
    rc, out = conformance(red, home)
    check("the ninth check does NOT inherit that 0", rc == 1, f"exit {rc}")
    check("and it states the COUNT rather than a general complaint",
          "1 document(s) under docs/product/specs/ are not named" in out, out[:400])
    check("and it says why an exit 0 could not be trusted",
          "inspected none of them" in out, out[:400])

    # THE PAIR. Same directory, a name a rule binds.
    green = build(tmp, "c2-bound", {"docs/product/prd.md": PRD,
                                    "docs/product/specs/F-1-login.md":
                                        "---\nid: F-1\nstatus: approved\n---\n\n# Login\n"})
    rc, out = conformance(green, home)
    check("the control: a spec named `F-<n>-<slug>.md` raises no unbound finding",
          "are not named" not in out, out[:400])


def case_3_fix_touches_no_product_document(tmp: Path, home: Path) -> None:
    print("case 3: --fix never touches a product document")
    red = build(tmp, "c3-fix", {"docs/product/prd.md": PRD,
                                "docs/product/specs/login/spec.md": "# Login\n\nIt logs in.\n"})
    before = {p: p.read_bytes() for p in sorted((red / "docs").rglob("*")) if p.is_file()}
    check("the control: this fixture really is red before --fix runs",
          conformance(red, home)[0] == 1)
    rc, out = conformance(red, home, "--fix")
    check("the repair plan is empty and says so",
          "(nothing is mechanically repairable here)" in out, out[:400])
    after = {p: p.read_bytes() for p in sorted((red / "docs").rglob("*")) if p.is_file()}
    check("no file under docs/ changed, and none appeared or vanished", before == after,
          f"{sorted(k.name for k in set(before) ^ set(after))} differ")
    check("--fix did not turn the red into a green", rc == 1, f"exit {rc}")


def case_4_missing_callee(tmp: Path, home: Path) -> None:
    print("case 4: a missing spec_check.py is COULD NOT BE CHECKED, never CONFORMS")
    empty = tmp / "c4-home"
    (empty / ".claude" / "skills").mkdir(parents=True)
    root = build(tmp, "c4-repo", {"docs/product/prd.md": PRD})
    rc, out = conformance(root, empty)
    check("exit 2, which outranks both other verdicts", rc == 2, f"exit {rc}")
    check("the check reports COULD NOT BE CHECKED", "COULD NOT BE CHECKED" in out, out[:400])
    check("and the run refuses to be read as a pass",
          "not a check that passed" in out, out[:400])


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        home = fake_home(tmp)
        case_1_missing_layer(tmp, home)
        case_2_unbound_specs(tmp, home)
        case_3_fix_touches_no_product_document(tmp, home)
        case_4_missing_callee(tmp, home)
    print()
    if failures:
        print(f"{len(failures)} case(s) FAILED: {', '.join(failures)}")
        return 1
    print("every case passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
