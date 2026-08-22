#!/usr/bin/env python3
"""Break-test for spec_check.py — proves it READ the corpus, rather than exiting 0 over silence.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
that was LIVE in this file's sibling, and each one has the same signature: a clean exit 0 from a
checker that inspected nothing.

  1  a criterion written `AC-1 When ...`, with no bold, is READ
                                   <- AC_RE demanded `**AC-1**`. It first matched 0 of 416
                                      criteria; it then missed a whole repository's 521.
  2  specs named `specs/<slug>/spec.md` are COUNTED and SAID OUT LOUD
                                   <- the schema bound `docs/product/specs/F-*.md` only, so 233
                                      documents were read by nothing and the run exited 0
  3  rule F runs on a document with NO front-matter block at all
                                   <- gating F on `not doc.front_error` would have run it on
                                      nothing anywhere: 0 of 23 real feature specs carry a `---`
                                      block, which was 100% of the real corpus

THE SHAPE OF ALL THREE. None of them is a wrong answer; each is an ABSENT answer wearing an exit 0.
That is why case 2 asserts on OUTPUT rather than on the exit code — the exit code was correct
throughout, and correct is exactly what made the defect invisible. Every case here is paired: a
positive that must be found and a negative that must not, so no case can pass against a checker
that has started reporting everything.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process, through argv, in a
temporary directory. The individual EARS rules, the front-matter subset parser, the milestone
register and the surface check are covered by the vendored suite and are deliberately not
duplicated here. Nothing here writes inside the repository.

Run:  python3 spec_check_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "spec_check.py"

PRD = "---\ntitle: A product\nstatus: approved\nupdated: 2026-01-01\n---\n\n# A product\n"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def build(tmp: Path, files: dict[str, str]) -> Path:
    root = tmp / "repo"
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def run(root: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *extra],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def rules(root: Path) -> list[str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--json"],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [f"UNPARSEABLE:{proc.stdout[:120]}{proc.stderr[:120]}"]
    return [item.get("rule") for item in payload.get("findings", [])]


def spec(body: str, ident: str = "F-1") -> str:
    return (f"---\nid: {ident}\ntitle: Orders\nprd: docs/product/prd.md\n"
            f"status: approved\nupdated: 2026-01-01\n---\n\n# {ident} — Orders\n\n"
            f"## Acceptance criteria\n\n{body}\n")


def case_bold_is_a_house_style_not_an_identity() -> None:
    """A criterion is identified by its id and its sentence, never by its emphasis."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # The NEGATIVE half: an unbolded criterion that is already EARS-shaped. A matcher that
        # cannot see it reports nothing here too, so this half alone proves nothing — which is
        # precisely how the defect survived. It is paired with the positive half below.
        good = build(tmp / "good", {
            "docs/product/prd.md": PRD,
            "docs/product/specs/F-1-orders.md": spec(
                "AC-1 When an operator lists orders, given the ledger has entries, "
                "the response names every entry."),
        })
        found = rules(good)
        check("1a an unbolded EARS criterion raises no criterion finding",
              "C1" not in found, f"rules: {found}")

        # The POSITIVE half, and the one that kills a bold-only matcher: the SAME unbolded
        # spelling, this time not EARS-shaped. Silence here means the criterion was never read.
        bad = build(tmp / "bad", {
            "docs/product/prd.md": PRD,
            "docs/product/specs/F-1-orders.md": spec("AC-1 The system should be fast."),
        })
        found = rules(bad)
        check("1b an unbolded criterion that is NOT EARS-shaped is found, so it was read",
              "C1" in found, f"rules: {found}")

        # And the house style still works, so relaxing the marker did not break the other spelling.
        bold = build(tmp / "bold", {
            "docs/product/prd.md": PRD,
            "docs/product/specs/F-1-orders.md": spec("**AC-1** The system should be fast."),
        })
        found = rules(bold)
        check("1c the bold spelling is still read", "C1" in found, f"rules: {found}")


def case_a_repository_that_names_its_specs_differently_is_told() -> None:
    """The exit code was RIGHT the whole time. That is what made 233 unread documents invisible."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root = build(tmp, {
            "docs/product/prd.md": PRD,
            "docs/product/specs/orders/spec.md": spec("AC-1 The system should be fast."),
            "docs/product/specs/billing/spec.md": spec("AC-1 The system should be fast.", "F-2"),
        })
        code, out = run(root)
        check("2a the run says how many documents under specs/ nothing read",
              "2 document(s) under docs/product/specs/" in out, out[:400])
        check("2b it says an exit 0 cannot distinguish the two cases",
              "exit 0 cannot tell you" in out, out[:400])
        check("2c and it does not charge the repository with a defect for its naming",
              "not a defect" in out, out[:400])

        # The negative half: a repository using the bound naming says none of this.
        named = build(tmp / "named", {
            "docs/product/prd.md": PRD,
            "docs/product/specs/F-1-orders.md": spec(
                "AC-1 When an operator lists orders, given the ledger has entries, "
                "the response names every entry."),
        })
        code, out = run(named)
        check("2d a repository using the bound naming is not told about unread documents",
              "document(s) under docs/product/specs/" not in out, out[:400])


def case_rule_f_reads_a_document_with_no_front_matter() -> None:
    """`## Horizontals` is BODY. Body is readable with or without a `---` block."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        persona = ("---\nname: security-reviewer\ncovers: [security]\n---\n\n"
                   "# security reviewer\n")
        horizontals = ("# F-2 — Payments\n\n## Horizontals\n\n"
                       "- **Security:** moves — the auth boundary changes\n"
                       "- **Privacy:** unchanged\n")
        root = build(tmp, {
            "docs/product/prd.md": PRD,
            "docs/product/specs/F-2-payments.md": horizontals,
            "docs/agents/personas/security-reviewer.md": persona,
        })
        found = rules(root)
        check("3a the missing front matter is reported once, as B1", "B1" in found,
              f"rules: {found}")
        check("3b and rule F STILL binds the concern the body declares", "F3" in found,
              f"rules: {found}")

        code, out = run(root)
        check("3c the reach line counts the rows F actually read",
              "2 labelled concern row(s), 2 live" in out, out[:600])
        check("3d and says how many documents had no `---` block to read `reviewed_by:` from",
              "1 document(s) carry no `---` block" in out, out[:600])

        # The negative half. Without it, case 3 would pass against a rule F that demands a
        # reviewer for every row it sees. A row that OPENS by declaring itself inapplicable is
        # exempt, and the exemption has to survive the missing front matter too.
        quiet = build(tmp / "quiet", {
            "docs/product/prd.md": PRD,
            "docs/product/specs/F-2-payments.md":
                "# F-2 — Payments\n\n## Horizontals\n\n"
                "- **Security:** N/A — this feature touches no auth boundary\n",
            "docs/agents/personas/security-reviewer.md": persona,
        })
        check("3e a row that declares itself inapplicable demands no reviewer",
              "F3" not in rules(quiet), f"rules: {rules(quiet)}")


def main() -> int:
    if not SCRIPT.exists():
        print(f"spec_check.py not found at {SCRIPT}", file=sys.stderr)
        return 2

    print("spec_check break-test")
    for case in (case_bold_is_a_house_style_not_an_identity,
                 case_a_repository_that_names_its_specs_differently_is_told,
                 case_rule_f_reads_a_document_with_no_front_matter):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the corpus was read, and the run says so out loud")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
