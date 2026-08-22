#!/usr/bin/env python3
"""Break-test for plan_waves.py — proves the checks run, in the scope the methodology documents.

A guard nobody has watched fail is not evidence of anything. Every case below reproduces a defect
that was LIVE in this file's sibling, so a regression re-breaks a named case instead of returning a
green schedule for a plan that still says two agents own one file.

  1  W7 fires on the QUALIFIED `F-7/T1` subject, and on the bare `T1`
                                             <- W7 matched only the bare form, never the qualified
                                                one the methodology tells people to write
  2  `--milestone M<n> --commit REV` actually RUNS the commit check
                                             <- the flag was accepted and the check was never called
  3  W4's printed remedy, applied VERBATIM, silences the finding
                                             <- the remedy told the reader to declare `serialises:`,
                                                which W4 never reads
  4  under `--milestone`, the DOCUMENTED plan-local `serialises: [T6]` silences W6
                                             <- qualify() never qualified `serialises`, so the only
                                                spelling the reference page shows matched nothing

CASE 3 IS THE ONE WORTH COPYING. It does not hardcode a remedy: it reads the `needs:` and
`serialises:` clauses out of the tool's OWN message, rewrites the plan with exactly those, and
re-runs. A remedy naming a key the rule does not read cannot survive that, and neither can a remedy
that merely moves a finding from W4 to W6 while both tasks still own one file. Advice a checker
prints is part of the checker; this is the assertion that treats it that way.

WHAT THIS DOES NOT COVER. Every case drives the INSTALLED sibling as a process, through argv.
Nothing here imports it. The wave computation itself, the overlap relation, the cycle rule and the
size rule are covered by the vendored suite and are deliberately not duplicated here. Cases 1 and 2
build a real git repository in a temporary directory; nothing here writes inside this repository.

Run:  python3 plan_waves_selftest.py      (exit 0 = every case passes)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "plan_waves.py"

PRD = "---\ntitle: A product\nstatus: approved\nupdated: 2026-01-01\n---\n\n# A product\n"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def run(root: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *extra],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, proc.stdout + proc.stderr


def report(root: Path, *extra: str) -> dict:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--json", *extra],
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_stdout": proc.stdout, "_stderr": proc.stderr}


def rules(payload: dict) -> list[str]:
    return [item.get("rule") for item in payload.get("findings", [])]


def messages(payload: dict, rule: str) -> list[str]:
    return [item.get("message") for item in payload.get("findings", [])
            if item.get("rule") == rule]


def task(ident: str, writes: str, needs: str = "", serialises: str = "",
         lane: str = "light", covers: str = "AC-1") -> str:
    lines = [f"task: {ident}", f"title: work for {ident}", f"lane: {lane}"]
    if needs:
        lines.append(f"needs: {needs}")
    if serialises:
        lines.append(f"serialises: {serialises}")
    lines += [f"writes: [{writes}]", f"covers: [{covers}]"]
    return "\n```task\n" + "\n".join(lines) + "\n```\n"


def make_root(tmp: Path) -> Path:
    root = tmp / "repo"
    for part in ("specs", "plans", "milestones"):
        (root / "docs" / "product" / part).mkdir(parents=True)
    (root / "docs" / "product" / "prd.md").write_text(PRD, encoding="utf-8")
    return root


def write_plan(root: Path, ident: str, *blocks: str, slug: str = "thing") -> Path:
    path = root / "docs" / "product" / "plans" / f"{ident}-{slug}.md"
    path.write_text(f"---\nid: {ident}\n---\n\n# {ident} — plan\n" + "".join(blocks),
                    encoding="utf-8")
    return path


def write_spec(root: Path, ident: str, milestone: str | None = None, slug: str = "thing",
               tags: dict | None = None) -> None:
    """`tags` marks a criterion with the optional priority tag: `{2: "P1"}` -> `AC-2 ... [P1]`.

    The criteria are written WRAPPED over two lines, because that is how the real corpus writes
    them and because the tag then lands on a line that carries no `AC-<n>` at all — a reader that
    scanned one line at a time would find no tag here and this case would pass on nothing.
    """
    lines = ["---", f"id: {ident}", f"title: feature {ident}", "prd: docs/product/prd.md",
             "status: approved", "updated: 2026-01-01"]
    if milestone:
        lines.append(f"milestone: {milestone}")
    lines += ["---", "", f"# {ident} — feature", ""]
    if tags is not None:
        lines += ["## Acceptance criteria", ""]
        for number in sorted(tags):
            mark = f" [{tags[number]}]" if tags[number] else ""
            lines += [f"**AC-{number}** When request {number} arrives, given the store is",
                      f"reachable, result {number} is recorded.{mark}", ""]
    (root / "docs" / "product" / "specs" / f"{ident}-{slug}.md").write_text(
        "\n".join(lines), encoding="utf-8")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True).stdout


def init_repo(root: Path) -> None:
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "selftest@example.invalid")
    git(root, "config", "user.name", "selftest")
    git(root, "add", ".")
    git(root, "commit", "-qm", "chore: the plan itself")


def stray_commit(root: Path, subject: str, path: str) -> str:
    """A commit whose subject names a task and whose content is OUTSIDE that task's `writes`."""
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("stray\n", encoding="utf-8")
    git(root, "add", path)
    git(root, "commit", "-qm", subject)
    return git(root, "rev-parse", "HEAD").strip()


def case_w7_reads_the_qualified_subject() -> None:
    """The defect: W7 matched a bare `T1` and never the `F-7/T1` the methodology documents."""
    with tempfile.TemporaryDirectory() as td:
        root = make_root(Path(td))
        write_spec(root, "F-7")
        write_plan(root, "F-7", task("T1", "src/reminders/**"), task("T2", "src/other/**"))
        init_repo(root)

        for label, subject in (("bare `T1`", "feat(T1): reminders"),
                               ("qualified `F-7/T1`", "feat(F-7/T1): reminders")):
            rev = stray_commit(root, subject, f"src/elsewhere/{label.split()[0]}.py")
            payload = report(root, "--commit", rev)
            check(f"1 a {label} subject reaches W7", "W7" in rules(payload),
                  f"rules: {rules(payload)}")
            text = " ".join(messages(payload, "W7"))
            check(f"1 the {label} finding names the file that strayed",
                  "src/elsewhere" in text, text[:250])


def case_milestone_commit_actually_runs_the_check() -> None:
    """The defect: `--milestone --commit` accepted the flag and never called the check.

    A silent exit 0 is exactly what a flag that is parsed and then ignored looks like, so the
    assertion is a POSITIVE finding: the run must report W7 by name.
    """
    with tempfile.TemporaryDirectory() as td:
        root = make_root(Path(td))
        write_spec(root, "F-1", milestone="M2")
        write_plan(root, "F-1", task("T1", "src/one/**"), slug="one")
        (root / "docs" / "product" / "milestones" / "M2-checkout.md").write_text(
            "---\nmilestone: M2\ntitle: the milestone\nstatus: building\nupdated: 2026-01-01\n"
            "---\n\n# M2 — the milestone\n", encoding="utf-8")
        init_repo(root)
        rev = stray_commit(root, "feat(F-1/T1): one", "src/elsewhere/thing.py")

        payload = report(root, "--milestone", "M2", "--commit", rev)
        check("2a --milestone --commit reports W7 rather than exiting quietly",
              "W7" in rules(payload), f"rules: {rules(payload)}")
        check("2b and names the file the commit wrote outside the task's declaration",
              "src/elsewhere" in " ".join(messages(payload, "W7")),
              " ".join(messages(payload, "W7"))[:250])

        code, out = run(root, "--milestone", "M2", "--commit", rev)
        check("2c the exit code is a finding, not a clean run", code == 1, f"got {code}")


def case_w4_remedy_applied_verbatim_silences_it() -> None:
    """Advice a checker prints is part of the checker, so the advice is what gets executed here."""
    with tempfile.TemporaryDirectory() as td:
        root = make_root(Path(td))
        write_spec(root, "F-7")
        write_plan(root, "F-7", task("T1", "src/shared/**"), task("T2", "src/shared/**"))

        payload = report(root)
        check("3a two tasks in one wave writing one path are found", "W4" in rules(payload),
              f"rules: {rules(payload)}")
        text = " ".join(messages(payload, "W4"))
        if "W4" not in rules(payload):
            return

        needs = re.search(r"`needs: \[([^\]]+)\]`", text)
        serialises = re.search(r"`serialises: \[([^\]]+)\]`", text)
        check("3b the remedy states a needs edge to add", needs is not None, text[:250])
        check("3c and a serialises declaration to add", serialises is not None, text[:250])
        if not (needs and serialises):
            return

        # Applied to T2, exactly as the message directs: `needs: [T1]` on `T2`, `serialises: [T1]`.
        write_plan(root, "F-7",
                   task("T1", "src/shared/**"),
                   task("T2", "src/shared/**",
                        needs=f"[{needs.group(1)}]", serialises=f"[{serialises.group(1)}]"))
        after = rules(report(root))
        check("3d following the printed remedy VERBATIM silences W4", "W4" not in after,
              f"still: {after}")
        check("3e and does not merely move the finding to W6 with both tasks still on one path",
              "W6" not in after, f"still: {after}")
        code, _ = run(root)
        check("3f so the plan the remedy produces exits 0", code == 0, f"got {code}")


def case_documented_serialises_is_qualified_under_milestone() -> None:
    """The reference page documents `serialises: [T6]`. That spelling must be the one that works."""
    with tempfile.TemporaryDirectory() as td:
        root = make_root(Path(td))
        (root / "docs" / "product" / "milestones" / "M2-checkout.md").write_text(
            "---\nmilestone: M2\ntitle: the milestone\nstatus: building\nupdated: 2026-01-01\n"
            "---\n\n# M2 — the milestone\n", encoding="utf-8")
        write_spec(root, "F-1", milestone="M2", slug="one")
        write_spec(root, "F-2", milestone="M2", slug="two")
        # Two features, one shared path, held apart by a cross-feature dependency edge: the W6
        # shape. Only a `serialises:` declaration may silence it.
        write_plan(root, "F-1", task("T6", "src/shared/**"), slug="one")

        write_plan(root, "F-2", task("T6", "src/shared/**", needs="[F-1/T6]"), slug="two")
        before = rules(report(root, "--milestone", "M2"))
        check("4a a cross-feature pair on one path is found as W6", "W6" in before,
              f"rules: {before}")

        write_plan(root, "F-2",
                   task("T6", "src/shared/**", needs="[F-1/T6]", serialises="[F-1/T6]"),
                   slug="two")
        qualified = rules(report(root, "--milestone", "M2"))
        check("4b the explicitly qualified `serialises: [F-1/T6]` silences it",
              "W6" not in qualified, f"still: {qualified}")

        # THE DEFECT ITSELF: the spelling the reference page actually shows. Inside ONE feature's
        # plan the documented form is plain `serialises: [T1]`, and under `--milestone` every id in
        # the graph is qualified — so an unqualified entry matched nothing at all, and the only
        # spelling that worked was the `F-1/T1` the documentation never mentions. Measured on a
        # 51-task graph rebuilt from real fleet plans, the documented form left the finding
        # standing. A key that works only when written the way the documentation does not say is a
        # key that does nothing.
        write_plan(root, "F-1",
                   task("T1", "src/inner/**"),
                   task("T2", "src/inner/**", needs="[T1]", serialises="[T1]"),
                   slug="one")
        write_plan(root, "F-2", task("T9", "src/two/**"), slug="two")
        documented = rules(report(root, "--milestone", "M2"))
        check("4c a plan-local `serialises: [T1]` — the DOCUMENTED spelling — silences W6 "
              "under --milestone, where every id is qualified",
              "W6" not in documented, f"still: {documented}")

        write_plan(root, "F-1",
                   task("T1", "src/inner/**"),
                   task("T2", "src/inner/**", needs="[T1]"),
                   slug="one")
        undeclared = rules(report(root, "--milestone", "M2"))
        check("4d and without it the pair is still reported, so 4c is not passing on silence",
              "W6" in undeclared, f"rules: {undeclared}")


def case_priority_is_the_tiebreak_and_only_inside_the_feature() -> None:
    """The defect: the ready set's LAST key was `task.ident`, so nothing the spec said about which
    criteria were the point could reach the dispatcher, and the operator supplied the order from
    memory. Priority is now that last key — and the three assertions below are the three ways
    putting it anywhere else goes wrong.
    """
    with tempfile.TemporaryDirectory() as td:
        root = make_root(Path(td))
        (root / "docs" / "product" / "milestones" / "M2-two-features.md").write_text(
            "---\nmilestone: M2\ntitle: the milestone\nstatus: building\nupdated: 2026-01-01\n"
            "---\n\n# M2 — the milestone\n", encoding="utf-8")
        write_spec(root, "F-1", milestone="M2", slug="one", tags={1: "", 2: "", 3: ""})
        write_spec(root, "F-2", milestone="M2", slug="two", tags={1: "", 2: ""})
        # Disjoint writes throughout, so every task is legal beside every other and the emitted
        # order is the ORDER and not the collision rule showing through.
        write_plan(root, "F-1",
                   task("T1", "src/one/a/**", covers="AC-1"),
                   task("T2", "src/one/b/**", covers="AC-2"),
                   task("T3", "src/one/c/**", covers="AC-3"), slug="one")
        write_plan(root, "F-2",
                   task("T1", "src/two/a/**", covers="AC-1"),
                   task("T2", "src/two/b/**", covers="AC-2"), slug="two")
        init_repo(root)
        rev = git(root, "rev-parse", "HEAD").strip()

        flat = report(root, "--milestone", "M2", "--since", rev, "--ready")
        expected = ["F-1/T1", "F-1/T2", "F-1/T3", "F-2/T1", "F-2/T2"]
        check("5a with no criterion marked, the ready set is exactly the order it was before",
              flat.get("ready") == expected, f"got {flat.get('ready')}")
        check("5b and the run says so: `priority` is empty, so 5a is not passing on silence",
              flat.get("priority") == {}, f"got {flat.get('priority')}")

        # AC-3 is the criterion this feature exists for, and T3 is the task that closes it.
        write_spec(root, "F-1", milestone="M2", slug="one", tags={1: "P3", 2: "", 3: "P1"})
        marked = report(root, "--milestone", "M2", "--since", rev, "--ready")
        check("5c the marked criterion reaches the dispatcher: T3 now leads its feature",
              marked.get("ready") == ["F-1/T3", "F-1/T1", "F-1/T2", "F-2/T1", "F-2/T2"],
              f"got {marked.get('ready')}")
        check("5d and the tag is read off the WRAPPED line, where no `AC-<n>` appears",
              marked.get("priority") == {"F-1/T1": "P3", "F-1/T3": "P1"},
              f"got {marked.get('priority')}")

        # TRAP ONE: the LATER feature adopts the notation and the earlier one has not. Under a
        # priority key compared across features, `F-2/T1` would jump the whole of F-1 — so the
        # first spec in a milestone to write a tag would promote itself over every feature that had
        # not written one, and unmarked would silently mean last. Nobody ranked feature against
        # feature in a spec; the milestone does that, and it does it by id.
        write_spec(root, "F-1", milestone="M2", slug="one", tags={1: "", 2: "", 3: ""})
        write_spec(root, "F-2", milestone="M2", slug="two", tags={1: "P1", 2: ""})
        across = report(root, "--milestone", "M2", "--since", rev, "--ready")
        check("5e a P1 in the SECOND feature does not jump the first: priority is never compared "
              "across features", across.get("ready") == expected, f"got {across.get('ready')}")
        check("5f and it was genuinely read, so 5e is not passing on an unread tag",
              across.get("priority") == {"F-2/T1": "P1"}, f"got {across.get('priority')}")

        write_spec(root, "F-1", milestone="M2", slug="one", tags={1: "P3", 2: "", 3: "P1"})
        write_spec(root, "F-2", milestone="M2", slug="two", tags={1: "", 2: ""})

        # TRAP TWO: priority must not outrank the measured throughput key. T2 now unlocks T9, so
        # it leads the feature even though T3 is the P1 — 11%-22% of makespan is not for sale to a
        # tag. The P1 still leads everything T2 does not unlock.
        write_plan(root, "F-1",
                   task("T1", "src/one/a/**", covers="AC-1"),
                   task("T2", "src/one/b/**", covers="AC-2"),
                   task("T3", "src/one/c/**", covers="AC-3"),
                   task("T9", "src/one/d/**", needs="[T2]", covers="AC-2"), slug="one")
        ranked = report(root, "--milestone", "M2", "--since", rev, "--ready")
        check("5g a task that unlocks another still outranks the P1: `unlocks` stays the first key",
              ranked.get("ready", [])[:2] == ["F-1/T2", "F-1/T3"], f"got {ranked.get('ready')}")


def main() -> int:
    if not SCRIPT.exists():
        print(f"plan_waves.py not found at {SCRIPT}", file=sys.stderr)
        return 2
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("git is not available; cases 1 and 2 need a real repository", file=sys.stderr)
        return 2

    print("plan_waves break-test")
    for case in (case_w7_reads_the_qualified_subject,
                 case_milestone_commit_actually_runs_the_check,
                 case_w4_remedy_applied_verbatim_silences_it,
                 case_documented_serialises_is_qualified_under_milestone,
                 case_priority_is_the_tiebreak_and_only_inside_the_feature):
        case()

    print()
    if failures:
        print(f"FAIL — {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("PASS — every rule ran in the scope it claims, and its own remedy works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
