#!/usr/bin/env python3
"""Break-test for validate_card.py — proves a repository's OWN persona pool is castable.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
that was LIVE in this file's sibling.

  1  a repository persona declaring `writes: yes` can be cast
        VALID_PERSONAS was exactly ("developer", "senior-developer"). A repository installs its own
        domain personas as overlays and a card could name NONE of them: the pool a repository had
        actually adopted was unreachable from the artifact that dispatches work.
  2  a JUDGE — `writes: no` — cannot be cast to implement
        The opposite over-correction, and it is measured: across four repositories there are 289
        real `persona:` casts, 287 the base pair and 2 naming a judge. Those 2 are the case the
        rule exists to catch. A judge's whole value is that it cannot change what it judges.
  3  a persona file that declares no `writes:` at all is treated as a judge
        Fail closed in the direction that costs a rename rather than a lost guarantee.
  4  with no pool directory the base pair still works, and a stranger is still refused
  5  the pool is read from the REPOSITORY, never from $HOME

CASES 1 AND 2 ARE ONE ASSERTION IN TWO HALVES. Widening the allow-list to "any persona" passes
case 1 and fails case 2; the hardcoded pair does the reverse. Only reading `writes:` out of the
pool passes both, which is why the split is read from the files rather than restated in a second
list that could drift from the first.

EVERY ASSERTION IS ON THE `[persona]` FINDING, NOT ON THE EXIT CODE. The fixture card is realistic
rather than minimal, so it carries other findings of its own; keying on the exit code would let an
unrelated error make a case pass or fail. The rule under test is named in every assertion.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process, through argv, in a
temporary directory. The path rules, the validation-command rules and the phase rules are covered
by the vendored suite and are not duplicated here. Nothing here writes inside the repository.

Run:  python3 validate_card_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "validate_card.py"

CARD = """\
id: EX-01
title: Widget dispatch is idempotent
goal: The widget cannot be dispatched twice.
persona: {persona}

prerequisites: []

exclusive_writes:
  - backend/core/src/main/java/com/acme/core/**

forbidden_paths:
  - backend/app/**

context_acquisition:
  - "./scripts/agent-context.sh backend"

frozen_values:
  - "Money is an integer count of minor units."

invariants:
  - "A duplicate dispatch fails closed."

instructions:
  - "Implement idempotent widget dispatch."

tests:
  - "Retain: backend/core/src/test/java/com/acme/core/DispatchTest.java :: com.acme.core.DispatchTest"

gate_risk: none

validation:
  - cwd: backend
    argv:
      - ./gradlew
      - :core:test

stop_conditions:
  - "a migration is required"

handoff: chief-of-staff

commit_subject: "feat(core): close the duplicate window"
"""

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def persona_findings(tmp: Path, persona: str, pool: dict[str, str] | None,
                     home_pool: dict[str, str] | None = None) -> str:
    """Every `[persona]` line this card produces, joined. Empty means the cast was accepted."""
    repo = tmp / "repo"
    (repo / "cards").mkdir(parents=True)
    (repo / "cards" / "EX-01.yaml").write_text(CARD.format(persona=persona), encoding="utf-8")
    if pool is not None:
        directory = repo / "docs" / "agents" / "personas"
        directory.mkdir(parents=True)
        for name, text in pool.items():
            (directory / f"{name}.md").write_text(text, encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    if home_pool is not None:
        directory = home / "docs" / "agents" / "personas"
        directory.mkdir(parents=True)
        for name, text in home_pool.items():
            (directory / f"{name}.md").write_text(text, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(repo / "cards" / "EX-01.yaml"), "--repo", str(repo)],
        capture_output=True, text=True,
        env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"})
    out = proc.stdout + proc.stderr
    return "\n".join(line for line in out.splitlines() if "[persona]" in line)


def overlay(writes: str | None) -> str:
    body = "---\n"
    if writes is not None:
        body += f"writes: {writes}\n"
    return body + "---\n\n# a persona overlay\n"


POOL = {"payments-specialist": overlay("yes"), "contract-judge": overlay("no")}


def case_repository_implementer_is_castable() -> None:
    with tempfile.TemporaryDirectory() as td:
        found = persona_findings(Path(td), "payments-specialist", POOL)
        check("1a a repository persona declaring `writes: yes` is castable", not found, found[:300])


def case_judge_cannot_be_cast_to_implement() -> None:
    with tempfile.TemporaryDirectory() as td:
        found = persona_findings(Path(td), "contract-judge", POOL)
        check("2a a persona declaring `writes: no` is refused", "ERROR" in found, found[:300])
        check("2b the message says WHY the refusal is the point, not just that it is a rule",
              "writes: no" in found and "verdict" in found, found[:400])
        check("2c and it lists the implementers this repository actually has, so the fix is named",
              "payments-specialist" in found and "senior-developer" in found, found[:400])


def case_a_persona_that_declares_nothing_is_a_judge() -> None:
    """Fail closed in the direction that costs a rename rather than a lost guarantee."""
    with tempfile.TemporaryDirectory() as td:
        pool = {"quiet-persona": overlay(None)}
        found = persona_findings(Path(td), "quiet-persona", pool)
        check("3a a persona overlay with no `writes:` line cannot be cast to implement",
              "ERROR" in found, found[:300])


def case_the_base_pair_survives_an_empty_pool() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        check("4a `senior-developer` is castable in a repository with no pool at all",
              not persona_findings(tmp / "a", "senior-developer", None), "")
        check("4b `developer` too", not persona_findings(tmp / "b", "developer", None), "")
        stranger = persona_findings(tmp / "c", "widget-wrangler", None)
        check("4c a name in neither the base pair nor a pool is still refused",
              "ERROR" in stranger, stranger[:300])


def case_the_pool_is_the_repositorys_not_the_machines() -> None:
    """A check that consults the machine gives one answer locally and another in CI."""
    with tempfile.TemporaryDirectory() as td:
        found = persona_findings(Path(td), "payments-specialist", None,
                                 home_pool={"payments-specialist": overlay("yes")})
        check("5a a persona that exists only under $HOME does not make the cast valid",
              "ERROR" in found, found[:300])


def main() -> int:
    if not SCRIPT.exists():
        print(f"validate_card.py not found at {SCRIPT}", file=sys.stderr)
        return 2

    print("validate_card break-test")
    for case in (case_repository_implementer_is_castable, case_judge_cannot_be_cast_to_implement,
                 case_a_persona_that_declares_nothing_is_a_judge,
                 case_the_base_pair_survives_an_empty_pool,
                 case_the_pool_is_the_repositorys_not_the_machines):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — the repository's own pool is castable, and its judges are not")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
