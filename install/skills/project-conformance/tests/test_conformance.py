#!/usr/bin/env python3
"""Tests for `check_conformance.py`.

WHAT THESE TESTS ARE FOR. Every claim this skill makes about itself that CAN be asserted is
asserted here rather than written into prose, because on this programme every mechanised fix held
first try and every prose-only one came back. In particular the two claims most likely to rot:

  * "the advertised persona-drift remedy is a no-op" — driven against the REAL `sync_personas.py`
    with a real fixture, so the day agent-personas fixes it, this suite fails and the skill's
    wording gets corrected instead of quietly lying.
  * "this file reimplements no conformance rule" — held by AST over the source, not by promise.

Every fixture is built here from generic content, never copied from a real project: the skill is
vendored into a public repository and a fixture carrying a real project's shape would carry its
identity too. Each fixture is validated against the real checkers before anything is concluded from
it — an absence claim needs a positive control more than a presence claim does — and every mutation
asserts `modified != original` before the mutated tree is trusted.

Run with the 3.14 interpreter, not `/usr/bin/python3`:
    /opt/homebrew/bin/python3 skills/project-conformance/tests/test_conformance.py
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "check_conformance.py"
PY = sys.executable or "python3"

_spec = importlib.util.spec_from_file_location("check_conformance", SCRIPT)
cc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# Registered BEFORE exec: `@dataclass` resolves `cls.__module__` through `sys.modules`, and a
# module executed without being registered there fails with an opaque AttributeError on 3.14.
sys.modules["check_conformance"] = cc
_spec.loader.exec_module(cc)

SYNC_PERSONAS = cc.SYNC_PERSONAS


def runtime_status(state: str, **changes) -> dict:
    identity = {
        "version": "5.1",
        "source_sha256": "a" * 64,
        "runtime_sha256": "b" * 64,
        "bundle_root": "/approved/skills",
    }
    payload = {
        "schema_version": 1,
        "state": state,
        "ready": state == "current",
        "approved": identity,
        "installed": dict(identity),
        "route": {"valid": state == "current", "detail": ""},
        "overlay": {
            "valid": True,
            "sha256": None,
            "expected_sha256": None,
            "detail": "",
        },
        "dependencies": [{
            "path": "execution-methodology/methodology.md",
            "stage": "common",
            "status": "current",
            "expected_sha256": "c" * 64,
            "actual_sha256": "c" * 64,
        }],
        "findings": [],
        "repair_candidates": [],
    }
    payload.update(changes)
    return payload


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------

UNPROTECTED_SOURCE = """\
---
name: widget-safety-validator
description: Use when a change touches widget safety limits.
writes: no
claude.model: opus
claude.effort: high
claude.disallowedTools: Write, Edit, NotebookEdit, Bash
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---

You check that widget safety limits hold.
"""


def build_repo(root: Path) -> Path:
    """A minimal repository with a route, a project judge, and a git history.

    Deliberately generic: a widget library. Nothing here names a project, a person, or a path
    outside the temporary directory it is built in.
    """
    (root / "docs" / "agents" / "personas").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "AGENTS.md").write_text(
        "# Widget Library — repository contract\n\n"
        "Start at [docs/agents/README.md](docs/agents/README.md).\n\n"
        "## Verification\n\n```bash\nmake check\n```\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (root / "README.md").write_text("# Widget Library\n", encoding="utf-8")
    (root / "Makefile").write_text("check:\n\t@echo ok\n", encoding="utf-8")
    (root / "src" / "w.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs" / "agents" / "README.md").write_text(
        "# Agent route\n\n| Task | Guide | Command |\n|---|---|---|\n"
        "| Anything | [AGENTS.md](../../AGENTS.md) | `make check` |\n\n"
        "Personas: [personas.md](personas.md)\n", encoding="utf-8")
    (root / "docs" / "agents" / "personas.md").write_text(
        "# Project personas\n\nOne specialist: `widget-safety-validator`.\n", encoding="utf-8")
    (root / "docs" / "agents" / "personas" / "widget-safety-validator.md").write_text(
        UNPROTECTED_SOURCE, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, capture_output=True)
    render(root)
    return root


def render(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(SYNC_PERSONAS), "--scope", "project", "--repo", str(repo)],
                          capture_output=True, text=True)


def conformance(repo: Path, *args: str, home: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if home is not None:
        env["PROJECT_CONFORMANCE_HOME"] = str(home)
    return subprocess.run([PY, str(SCRIPT), str(repo), *args],
                          capture_output=True, text=True, env=env)


def tree_hash(root: Path, skip_git_internals: bool = True) -> dict[str, str]:
    """Content hash of every file under `root`.

    `.git` is excluded EXCEPT `.git/hooks`, and that exclusion is stated rather than hidden: git
    itself writes to `.git` on read-only commands — `git status` refreshes the index stat cache —
    so hashing it would measure git, not this tool. The claim these tests support is therefore
    precise: the read-only path changes no repository CONTENT and no installed hook. `.git/hooks`
    is included because that is the one part of `.git` this tool's `--fix` can legitimately touch,
    so it must be shown untouched on the read-only path.
    """
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if skip_git_internals and parts and parts[0] == ".git" and parts[1:2] != ("hooks",):
            continue
        out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = build_repo(self.tmp / "widget-lib")


class RuntimeStatusConsumerTest(Fixture):
    def owner_run(self, payload: dict | None, *, rc: int = 0, out: str | None = None) -> cc.Run:
        stdout = json.dumps(payload) if out is None and payload is not None else (out or "")
        return cc.Run([PY, str(cc.SYNC_METHODOLOGY), "--repo", str(self.repo), "--status-json"],
                      True, rc, stdout, "")

    def test_missing_runtime_status_stdout_is_not_a_pass(self):
        with mock.patch.object(cc, "run", return_value=self.owner_run(None, out="")):
            check = cc.check_methodology(self.repo)
        self.assertIs(check.verdict, cc.Verdict.NOT_RUN)
        self.assertIn("printed no JSON", check.why_not_run)
        self.assertEqual(check.repairs, [])

    def test_source_changed_status_is_reported_and_fix_cannot_upgrade_it(self):
        status = runtime_status(
            "source_changed",
            ready=False,
            route={"valid": True, "detail": ""},
            findings=[{
                "code": "source_changed",
                "severity": "warning",
                "message": "installed source differs from the approved runtime",
                "path": None,
            }],
        )
        with mock.patch.object(cc, "run", return_value=self.owner_run(status)):
            check = cc.check_methodology(self.repo)
        self.assertIs(check.verdict, cc.Verdict.DOES_NOT_CONFORM)
        self.assertEqual(check.repairs, [], "--fix turned changed source into an implicit upgrade")
        self.assertIn("installed source differs", check.findings[0].detail)

    def test_all_non_current_states_are_reported_without_promotion(self):
        for state in ("legacy", "source_changed", "unadopted", "deferred", "unmanaged"):
            with self.subTest(state=state):
                status = runtime_status(state, ready=False,
                                        route={"valid": True, "detail": ""})
                with mock.patch.object(cc, "run", return_value=self.owner_run(status)):
                    check = cc.check_methodology(self.repo)
                self.assertIs(check.verdict, cc.Verdict.DOES_NOT_CONFORM)
                self.assertEqual(check.repairs, [])
                self.assertTrue(check.findings)

    def test_contradictory_current_keeps_owner_findings_and_fails_closed(self):
        status = runtime_status(
            "current",
            route={"valid": False, "detail": "route missing"},
            findings=[{"code": "route_missing", "severity": "error",
                       "message": "execution route is absent", "path": "AGENTS.md"}],
        )
        with mock.patch.object(cc, "run", return_value=self.owner_run(status)):
            check = cc.check_methodology(self.repo)
        self.assertIs(check.verdict, cc.Verdict.NOT_RUN)
        self.assertIn("current has an invalid route", check.why_not_run)
        self.assertIn("execution route is absent", check.findings[0].detail)

    def test_unknown_schema_and_malformed_nested_types_fail_closed(self):
        cases = [
            runtime_status("current", schema_version=2),
            runtime_status("current", dependencies="not-an-array"),
            runtime_status("current", ready=False),
            runtime_status(
                "repairable", ready=False, route={"valid": False, "detail": "missing"},
                repair_candidates=[{"action": "render_approved", "paths": ["x"]}]),
        ]
        for status in cases:
            with self.subTest(status=status):
                with mock.patch.object(cc, "run", return_value=self.owner_run(status)):
                    check = cc.check_methodology(self.repo)
                self.assertIs(check.verdict, cc.Verdict.NOT_RUN)
                self.assertEqual(check.repairs, [])

    def test_only_repairable_accepts_repository_local_owner_candidates(self):
        target = self.repo / "docs/agents/execution/methodology.md"
        status = runtime_status(
            "repairable", ready=False, route={"valid": True, "detail": ""},
            findings=[{"code": "generated_drift", "severity": "error",
                       "message": "generated output differs", "path": str(target)}],
            repair_candidates=[{"action": "render_approved",
                                "paths": ["docs/agents/execution/methodology.md"]}],
        )
        with mock.patch.object(cc, "run", return_value=self.owner_run(status)):
            check = cc.check_methodology(self.repo)
        self.assertIs(check.verdict, cc.Verdict.DOES_NOT_CONFORM)
        self.assertEqual(check.repairs[0].files, [target.resolve()])

        status["repair_candidates"][0]["paths"] = ["../outside"]
        with mock.patch.object(cc, "run", return_value=self.owner_run(status)):
            escaped = cc.check_methodology(self.repo)
        self.assertIs(escaped.verdict, cc.Verdict.NOT_RUN)
        self.assertEqual(escaped.repairs, [])

    def test_current_is_the_only_conforming_runtime_state(self):
        with mock.patch.object(cc, "run", return_value=self.owner_run(runtime_status("current"))):
            check = cc.check_methodology(self.repo)
        self.assertIs(check.verdict, cc.Verdict.CONFORMS)
        self.assertEqual(check.repairs, [])

    def test_inspection_error_exit_two_preserves_owner_finding(self):
        status = runtime_status(
            "invalid", ready=False, approved=None, installed=None,
            route={"valid": False, "detail": "repository unreadable"}, dependencies=[],
            findings=[{"code": "inspection_error", "severity": "error",
                       "message": "repository unreadable", "path": None}],
        )
        with mock.patch.object(cc, "run", return_value=self.owner_run(status, rc=2)):
            check = cc.check_methodology(self.repo)
        self.assertIs(check.verdict, cc.Verdict.NOT_RUN)
        self.assertIn("repository unreadable", check.findings[0].detail)

    def test_repair_carries_planned_identity_through_owner_and_postcheck(self):
        target = self.repo / "docs/agents/execution/methodology.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("damaged\n", encoding="utf-8")
        repairable = runtime_status(
            "repairable", ready=False, route={"valid": True, "detail": ""},
            findings=[{"code": "generated_drift", "severity": "error",
                       "message": "generated output differs", "path": str(target)}],
            repair_candidates=[{"action": "render_approved", "paths": [str(target)]}],
        )
        current = runtime_status("current")
        calls = []

        def owner(argv, timeout=cc.TIMEOUT):
            calls.append(argv)
            if "--status-json" in argv:
                payload = repairable if len([c for c in calls if "--status-json" in c]) == 1 else current
                return self.owner_run(payload)
            self.assertIn("--repair-approved", argv)
            frozen = json.loads(argv[argv.index("--repair-approved") + 1])
            self.assertEqual(frozen, {
                "identity": repairable["approved"],
                "overlay_expected_sha256": repairable["overlay"]["expected_sha256"],
            })
            target.write_text("approved\n", encoding="utf-8")
            return cc.Run([str(arg) for arg in argv], True, 0, "", "")

        with mock.patch.object(cc, "run", side_effect=owner):
            repair = cc.check_methodology(self.repo).repairs[0]
            changed, note = repair.apply()
        self.assertEqual(changed, [target.resolve()])
        self.assertIn("approved runtime", note)
        self.assertEqual(sum("--status-json" in call for call in calls), 2)

    def test_repair_refuses_source_swap_instead_of_promoting_new_identity(self):
        target = self.repo / "docs/agents/execution/methodology.md"
        runtime = self.repo / "docs/agents/execution/runtime.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("damaged\n", encoding="utf-8")
        runtime.write_text("approved inventory X\n", encoding="utf-8")
        repairable = runtime_status(
            "repairable", ready=False, route={"valid": True, "detail": ""},
            findings=[{"code": "generated_drift", "severity": "error",
                       "message": "generated output differs", "path": str(target)}],
            repair_candidates=[{"action": "render_approved", "paths": [str(target)]}],
        )
        before = (target.read_bytes(), runtime.read_bytes())
        calls = []

        def owner(argv, timeout=cc.TIMEOUT):
            calls.append(argv)
            if "--status-json" in argv:
                return self.owner_run(repairable)
            self.assertEqual(json.loads(argv[argv.index("--repair-approved") + 1]), {
                "identity": repairable["approved"],
                "overlay_expected_sha256": repairable["overlay"]["expected_sha256"],
            })
            return cc.Run([str(arg) for arg in argv], True, 2, "",
                          "approved identity changed; refusing repair")

        with mock.patch.object(cc, "run", side_effect=owner):
            repair = cc.check_methodology(self.repo).repairs[0]
            changed, note = repair.apply()

        self.assertEqual(changed, [])
        self.assertTrue(note.startswith("FAILED"), note)
        self.assertEqual((target.read_bytes(), runtime.read_bytes()), before)
        self.assertEqual(sum("--status-json" in call for call in calls), 1)

    def test_repair_postcheck_rejects_current_different_identity(self):
        target = self.repo / "docs/agents/execution/methodology.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("damaged\n", encoding="utf-8")
        repairable = runtime_status(
            "repairable", ready=False, route={"valid": True, "detail": ""},
            repair_candidates=[{"action": "render_approved", "paths": [str(target)]}],
        )
        changed_identity = dict(repairable["approved"])
        changed_identity["source_sha256"] = "d" * 64
        promoted = runtime_status("current", approved=changed_identity,
                                  installed=dict(changed_identity))
        status_calls = 0

        def owner(argv, timeout=cc.TIMEOUT):
            nonlocal status_calls
            if "--status-json" in argv:
                status_calls += 1
                return self.owner_run(repairable if status_calls == 1 else promoted)
            target.write_text("new identity\n", encoding="utf-8")
            return cc.Run([str(arg) for arg in argv], True, 0, "repaired\n", "")

        with mock.patch.object(cc, "run", side_effect=owner):
            repair = cc.check_methodology(self.repo).repairs[0]
            _, note = repair.apply()

        self.assertTrue(note.startswith("FAILED"), note)
        self.assertIn("frozen approved identity", note)

    def test_repair_postcheck_rejects_changed_planned_overlay_identity(self):
        target = self.repo / "docs/agents/execution/methodology.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("damaged\n", encoding="utf-8")
        repairable = runtime_status(
            "repairable", ready=False, route={"valid": True, "detail": ""},
            overlay={"valid": True, "sha256": "e" * 64,
                     "expected_sha256": "e" * 64, "detail": ""},
            repair_candidates=[{"action": "render_approved", "paths": [str(target)]}],
        )
        promoted = runtime_status(
            "current",
            overlay={"valid": True, "sha256": "f" * 64,
                     "expected_sha256": "f" * 64, "detail": ""},
        )
        status_calls = 0

        def owner(argv, timeout=cc.TIMEOUT):
            nonlocal status_calls
            if "--status-json" in argv:
                status_calls += 1
                return self.owner_run(repairable if status_calls == 1 else promoted)
            frozen = json.loads(argv[argv.index("--repair-approved") + 1])
            self.assertEqual(frozen["overlay_expected_sha256"], "e" * 64)
            target.write_text("repaired\n", encoding="utf-8")
            return cc.Run([str(arg) for arg in argv], True, 0, "repaired\n", "")

        with mock.patch.object(cc, "run", side_effect=owner):
            repair = cc.check_methodology(self.repo).repairs[0]
            _, note = repair.apply()

        self.assertTrue(note.startswith("FAILED"), note)
        self.assertIn("frozen approved identity", note)


class ScopedOwnerConsumerTest(Fixture):
    def test_hook_plan_uses_sibling_owner_and_project_scope_only(self):
        hook = (self.repo / ".git/hooks/pre-push").resolve()
        payload = {"schema_version": 1, "scope": "project",
                   "operations": [{"action": "create", "path": str(hook)}], "findings": []}
        owner = cc.Run([], True, 0, json.dumps(payload), "")
        with mock.patch.object(cc, "run", return_value=owner) as invoked:
            check = cc.check_hooks(self.repo)
        argv = invoked.call_args.args[0]
        self.assertEqual(Path(argv[1]), cc.PD / "install_hooks.py")
        self.assertIn("--scope", argv)
        self.assertEqual(argv[argv.index("--scope") + 1], "project")
        self.assertIn("--preview", argv)
        self.assertEqual(check.repairs[0].files, [hook])
        self.assertTrue(all(self.repo.resolve() in path.parents for path in check.repairs[0].files))

    def test_hook_preview_rejects_a_global_path(self):
        payload = {"schema_version": 1, "scope": "project",
                   "operations": [{"action": "update", "path": str(Path.home() / ".codex/x")}],
                   "findings": []}
        with mock.patch.object(cc, "run",
                               return_value=cc.Run([], True, 0, json.dumps(payload), "")):
            check = cc.check_hooks(self.repo)
        self.assertIs(check.verdict, cc.Verdict.NOT_RUN)
        self.assertEqual(check.repairs, [])


class RealRuntimeOwnerIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-runtime-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.skills = self.tmp / "skills"
        shutil.copytree(SKILL.parent, self.skills)
        self.owner = self.skills / "execution-methodology/scripts/sync_methodology.py"
        self.checker = self.skills / "project-conformance/scripts/check_conformance.py"
        self.fake_home = self.tmp / "home"
        (self.fake_home / ".claude/agents").mkdir(parents=True)
        (self.fake_home / ".codex/agents").mkdir(parents=True)
        (self.fake_home / ".claude/agents/sentinel.md").write_text("same\n", encoding="utf-8")
        (self.fake_home / ".codex/agents/sentinel.toml").write_text("same\n", encoding="utf-8")
        self.env = dict(os.environ, HOME=str(self.fake_home),
                        CODEX_HOME=str(self.fake_home / ".codex"))

    def repo(self, name: str) -> Path:
        repo = self.tmp / name
        (repo / "docs/agents").mkdir(parents=True)
        (repo / "docs/agents/README.md").write_text(
            "# Route\n\n[methodology](execution/methodology.md)\n", encoding="utf-8")
        return repo

    def owner_run(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([PY, str(self.owner), "--repo", str(repo), *args],
                              capture_output=True, text=True, env=self.env)

    def status(self, repo: Path) -> dict:
        result = self.owner_run(repo, "--status-json")
        self.assertIn(result.returncode, (0, 2), result.stdout + result.stderr)
        return json.loads(result.stdout)

    def conform(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([PY, str(self.checker), str(repo), "--only", "methodology", *args],
                              capture_output=True, text=True, env=self.env)

    def render(self, repo: Path) -> None:
        result = self.owner_run(repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_owner_states_are_consumed_without_a_second_classifier(self):
        unadopted = self.repo("unadopted")
        self.assertEqual(self.status(unadopted)["state"], "unadopted")
        self.assertEqual(self.conform(unadopted, "--json").returncode, 1)

        deferred = self.repo("deferred")
        (deferred / "docs/agents/README.md").write_text(
            '# Route\n<!-- execution-methodology: {"mode":"deferred",'
            '"reason":"finish current milestone","date":"2026-09-05"} -->\n', encoding="utf-8")
        self.assertEqual(self.status(deferred)["state"], "deferred")
        self.assertEqual(self.conform(deferred, "--json").returncode, 1)

        unmanaged = self.repo("unmanaged")
        target = unmanaged / "docs/agents/execution/methodology.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Owner-authored rules\n", encoding="utf-8")
        self.assertEqual(self.status(unmanaged)["state"], "unmanaged")
        self.assertEqual(json.loads(self.conform(unmanaged, "--json").stdout)["repair_plan"], [])

        legacy = self.repo("legacy")
        legacy_target = legacy / "docs/agents/execution/methodology.md"
        legacy_target.parent.mkdir(parents=True)
        legacy_target.write_text(
            '<!-- GENERATED by execution-methodology/scripts/sync_methodology.py from '
            'execution-methodology/methodology.md — do not hand-edit this file; edit the '
            "methodology, or this repo's docs/agents/execution/overlay.md. -->\n"
            '<!-- execution-methodology: {"v":"5.0","source_sha256":"abc"} -->\n',
            encoding="utf-8")
        self.assertEqual(self.status(legacy)["state"], "legacy")
        self.assertEqual(json.loads(self.conform(legacy, "--json").stdout)["repair_plan"], [])

        adopted = self.repo("adopted")
        self.render(adopted)
        self.assertEqual(self.status(adopted)["state"], "current")
        self.assertEqual(self.conform(adopted, "--json").returncode, 0)
        adopted_target = adopted / "docs/agents/execution/methodology.md"
        adopted_target.write_text(adopted_target.read_text() + "\ndamaged\n", encoding="utf-8")
        self.assertEqual(self.status(adopted)["state"], "repairable")
        self.assertTrue(json.loads(self.conform(adopted, "--json").stdout)["repair_plan"])

    def test_real_missing_and_changed_runtime_never_become_repairs(self):
        changed = self.repo("changed")
        self.render(changed)
        dependency = self.skills / "execution-methodology/references/execution-loop.md"
        dependency.write_text(dependency.read_text() + "\nchanged\n", encoding="utf-8")
        payload = self.status(changed)
        self.assertEqual(payload["state"], "source_changed")
        report = json.loads(self.conform(changed, "--json").stdout)
        self.assertEqual(report["repair_plan"], [])

        dependency.unlink()
        payload = self.status(changed)
        self.assertEqual(payload["state"], "source_changed")
        self.assertTrue(any(row["status"] == "missing" for row in payload["dependencies"]))
        self.assertEqual(json.loads(self.conform(changed, "--json").stdout)["repair_plan"], [])

    def test_real_corrupted_inventory_fails_closed_and_approved_fix_is_stable_and_local(self):
        corrupt = self.repo("corrupt")
        self.render(corrupt)
        (corrupt / "docs/agents/execution/runtime.json").write_text("{bad json\n", encoding="utf-8")
        result = self.conform(corrupt, "--json")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["verdict"], "could not be checked")
        self.assertIn("inspection_error", json.dumps(report["findings"]))

        repair = self.repo("repair")
        self.render(repair)
        target = repair / "docs/agents/execution/methodology.md"
        target.write_text(target.read_text() + "\ndamaged\n", encoding="utf-8")
        global_before = tree_hash(self.fake_home, skip_git_internals=False)
        first = self.conform(repair, "--fix")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(self.status(repair)["state"], "current")
        self.assertEqual(tree_hash(self.fake_home, skip_git_internals=False), global_before)
        repo_before = tree_hash(repair)
        second = self.conform(repair, "--fix")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("nothing was changed by this run", second.stdout)
        self.assertEqual(tree_hash(repair), repo_before)
        self.assertEqual(tree_hash(self.fake_home, skip_git_internals=False), global_before)


# ---------------------------------------------------------------------------------------------
# The three states, and the aggregation that must not lose one
# ---------------------------------------------------------------------------------------------


class AggregationTest(unittest.TestCase):
    def test_aggregate_never_collapses_not_run_into_a_pass(self):
        """Exhaustive over every combination of three checks. NOT_RUN always wins.

        Written exhaustively rather than as three examples because the defect it guards is a
        precedence bug, and precedence bugs hide in the combination nobody wrote a case for — a
        run with real findings AND a broken checker is exactly the one that would otherwise report
        `does not conform`, which reads as "we looked, here is the list".
        """
        V = cc.Verdict
        for a in V:
            for b in V:
                for c in V:
                    checks = [cc.Check(n, v) for n, v in zip("abc", (a, b, c))]
                    overall, code = cc.aggregate(checks)
                    if V.NOT_RUN in (a, b, c):
                        self.assertIs(overall, V.NOT_RUN, (a, b, c))
                        self.assertEqual(code, 2, (a, b, c))
                    elif V.DOES_NOT_CONFORM in (a, b, c):
                        self.assertIs(overall, V.DOES_NOT_CONFORM, (a, b, c))
                        self.assertEqual(code, 1, (a, b, c))
                    else:
                        self.assertIs(overall, V.CONFORMS, (a, b, c))
                        self.assertEqual(code, 0, (a, b, c))

    def test_there_are_exactly_three_states_and_no_boolean_shortcut(self):
        self.assertEqual(len(list(cc.Verdict)), 3)
        self.assertEqual({v.value for v in cc.Verdict},
                         {"conforms", "does not conform", "could not be checked"})

    def test_a_not_run_check_is_named_in_the_report_and_in_json(self):
        checks = [cc.Check("personas", cc.Verdict.CONFORMS),
                  cc.Check("route", cc.Verdict.NOT_RUN, why_not_run="the validator is not here")]
        overall, code = cc.aggregate(checks)
        text = cc.report(Path("/x"), checks, overall, code)
        self.assertIn("COULD NOT BE CHECKED", text)
        self.assertIn("the validator is not here", text)
        self.assertIn("has NOT been shown to conform", text)
        data = json.loads(cc.as_json(Path("/x"), checks, overall, code))
        self.assertEqual(data["exit"], 2)
        self.assertEqual([e["check"] for e in data["not_run"]], ["route"])
        self.assertEqual(data["counts"]["could not be checked"], 1)


# ---------------------------------------------------------------------------------------------
# The condition this skill exists for
# ---------------------------------------------------------------------------------------------


class UnprotectedJudgeTest(Fixture):
    def test_red_an_unprotected_project_judge_does_not_conform(self):
        """RED. Names the persona AND the emitted artifact, because the artifact is the claim.

        The positive control is in `test_green_...` below: the same fixture, one key added to the
        source, reports CONFORMS. Without that pair, a checker that never fires would pass this.
        """
        r = conformance(self.repo, "--only", "personas")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("DOES NOT CONFORM", r.stdout)
        self.assertIn("widget-safety-validator", r.stdout)
        self.assertIn(str(self.repo / ".claude" / "agents" / "widget-safety-validator.md"),
                      r.stdout)
        self.assertIn("UNPROTECTED in the emitted artifact", r.stdout)
        # The specific capabilities, not just the word. A deny-list of Write/Edit/NotebookEdit/Bash
        # still grants these, which is the whole finding.
        self.assertIn("Agent", r.stdout)
        self.assertIn("Monitor", r.stdout)

    def test_green_after_fix_it_conforms_and_a_second_fix_changes_nothing(self):
        before = (self.repo / "docs/agents/personas/widget-safety-validator.md").read_text()
        first = conformance(self.repo, "--only", "personas", "--fix")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        after = (self.repo / "docs/agents/personas/widget-safety-validator.md").read_text()
        self.assertNotEqual(after, before, "the fixture was not actually mutated")
        self.assertIn("CONFORMS", first.stdout)

        snapshot = tree_hash(self.repo)
        second = conformance(self.repo, "--only", "personas", "--fix")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("nothing was changed by this run", second.stdout)
        self.assertEqual(tree_hash(self.repo), snapshot,
                         "the second --fix changed something; it must be idempotent")

    def test_the_repair_is_at_the_source_because_a_re_render_alone_fixes_nothing(self):
        """The reason the repair edits the persona SOURCE, proved rather than asserted in prose.

        `restrict_for_roster` returns an off-roster meta untouched, so re-rendering emits exactly
        the same open artifact while `sync_personas` exits 0. If this ever stops being true the
        repair can be simplified — and this test will say so by failing.
        """
        artifact = self.repo / ".claude" / "agents" / "widget-safety-validator.md"
        before = artifact.read_bytes()
        r = render(self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(artifact.read_bytes(), before,
                         "a bare re-render changed the artifact; the repair's premise has moved")
        after = conformance(self.repo, "--only", "personas")
        self.assertEqual(after.returncode, 1,
                         "a bare re-render made an unprotected judge conform, which it must not")

    def test_the_plan_names_every_file_the_fix_touches(self):
        """Diff the enumerated set against the actually-changed set. Changed must be a subset.

        A superset would mean the report surprised the operator, which in a repository holding
        health data is worse than the tool not existing. Equality is NOT required: a plan may name
        a file a repair turns out not to need, and naming one file too many is the safe direction.
        """
        plan_run = conformance(self.repo, "--only", "personas", "--json")
        self.assertEqual(plan_run.returncode, 1, plan_run.stdout + plan_run.stderr)
        # Resolved on both sides: on macOS the temp root is `/var/...`, a symlink to
        # `/private/var/...`, and `main` resolves the repo path while the fixture does not.
        planned = {cc._key(Path(f))
                   for r in json.loads(plan_run.stdout)["repair_plan"] for f in r["files"]}
        self.assertTrue(planned, "nothing was planned, so this proves nothing")

        before = tree_hash(self.repo)
        fixed = conformance(self.repo, "--only", "personas", "--fix")
        self.assertEqual(fixed.returncode, 0, fixed.stdout + fixed.stderr)
        after = tree_hash(self.repo)
        actually_changed = {cc._key(self.repo / p) for p in set(before) | set(after)
                            if before.get(p) != after.get(p)}
        self.assertTrue(actually_changed, "nothing changed, so this proves nothing")
        self.assertLessEqual(actually_changed, planned,
                             f"changed outside the plan: {sorted(actually_changed - planned)}")

    def test_a_hand_written_allow_list_is_never_overwritten(self):
        """A judge whose allow-list a human wrote is reported, not silently narrowed."""
        src = self.repo / "docs/agents/personas/widget-safety-validator.md"
        original = src.read_text()
        src.write_text(original.replace("claude.disallowedTools:",
                                        "claude.tools: Read, Agent\nclaude.disallowedTools:"))
        self.assertNotEqual(src.read_text(), original)
        render(self.repo)
        r = conformance(self.repo, "--only", "personas", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["repair_plan"], [], "a human-written policy was scheduled for edit")
        self.assertIn("will not overwrite it", json.dumps(data["findings"]))


# ---------------------------------------------------------------------------------------------
# The advertised remedy that is a no-op
# ---------------------------------------------------------------------------------------------


class MechanicalRepairTest(Fixture):
    """The two repairs that are not the persona one, exercised end to end on a fixture."""

    def orphan(self) -> list[Path]:
        """Delete the persona SOURCE, leaving its two rendered artifacts orphaned.

        This is the case `prune` DELETES. The pre-existing `test_fix_never_deletes_an_agent_file`
        plants an UNMANAGED file instead, which the renderer explicitly PRESERVES — so it passed
        against a stub of the deletion logic and constrained nothing.
        """
        (self.repo / "docs/agents/personas/widget-safety-validator.md").unlink()
        artifacts = [self.repo / ".claude/agents/widget-safety-validator.md",
                     self.repo / ".codex/agents/widget-safety-validator.toml"]
        for a in artifacts:
            self.assertTrue(a.is_file(), "the fixture has no artifact to orphan")
        return artifacts

    def test_an_orphan_is_reported_as_a_deletion_and_never_repaired(self):
        artifacts = self.orphan()
        r = conformance(self.repo, "--only", "personas", "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        named = {cc._key(Path(f)) for finding in data["findings"] for f in finding["files"]}
        for a in artifacts:
            self.assertIn(cc._key(a), named, "an orphan was not named")
        self.assertIn("DELETES THIS FILE", json.dumps(data["findings"]))
        self.assertEqual(data["repair_plan"], [],
                         "a repair was offered for a case whose repair deletes files")

    def test_fix_does_not_delete_an_orphan_and_does_not_claim_nothing_happened(self):
        artifacts = self.orphan()
        r = conformance(self.repo, "--only", "personas", "--fix")
        for a in artifacts:
            self.assertTrue(a.is_file(), f"--fix deleted {a}")
        self.assertNotEqual(r.returncode, 0, "a run that could not repair reported success")

    def test_the_pre_write_guard_refuses_even_when_the_repair_was_already_planned(self):
        """The window between reading the report and typing `--fix`.

        `check_personas` withholds the repair when an orphan exists, but that decision is made at
        report time. This drives `_apply_render` directly against a tree that acquired an orphan
        afterwards — the only way to exercise the guard that makes the never-deletes refusal TRUE
        rather than merely intended, and the reason the post-hoc contract check is not the only
        defence.
        """
        artifacts = self.orphan()
        changed, note = cc._apply_render(self.repo)
        self.assertEqual(changed, [])
        self.assertIn("refusing to run the renderer", note)
        self.assertIn("would be DELETED", note)
        for a in artifacts:
            self.assertTrue(a.is_file(), f"the guard let {a} be deleted")

    def test_persona_fix_changes_project_only_and_leaves_global_snapshot_exact(self):
        fake_home = self.tmp / "home"
        global_claude = fake_home / ".claude" / "agents"
        global_codex = fake_home / ".codex" / "agents"
        global_claude.mkdir(parents=True)
        global_codex.mkdir(parents=True)
        (global_claude / "sentinel.md").write_text("unchanged\n", encoding="utf-8")
        (global_codex / "sentinel.toml").write_text("unchanged\n", encoding="utf-8")
        artifact = self.repo / ".claude" / "agents" / "widget-safety-validator.md"
        artifact.write_text(artifact.read_text() + "\ndrifted\n", encoding="utf-8")
        before = tree_hash(fake_home, skip_git_internals=False)
        result = subprocess.run(
            [PY, str(SCRIPT), str(self.repo), "--only", "personas", "--fix"],
            capture_output=True, text=True,
            env=dict(os.environ, HOME=str(fake_home), CODEX_HOME=str(fake_home / ".codex")))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tree_hash(fake_home, skip_git_internals=False), before,
                         "project persona repair changed machine-global state")

    def test_absent_hooks_are_reported_and_installed(self):
        before = conformance(self.repo, "--only", "hooks", "--json")
        self.assertEqual(before.returncode, 1, before.stdout + before.stderr)
        data = json.loads(before.stdout)
        self.assertTrue(data["findings"], "the fixture already has hooks; it proves nothing")
        self.assertTrue(data["repair_plan"])

        fixed = conformance(self.repo, "--only", "hooks", "--fix")
        self.assertIn("hooks installed", fixed.stdout)
        after = json.loads(conformance(self.repo, "--only", "hooks", "--json").stdout)
        self.assertLess(len(after["findings"]), len(data["findings"]),
                        "the repair installed nothing")
        # Whatever remains must be the graph hook, which `install_hooks.py` deliberately skips in a
        # repository with no graph — and it must NOT be offered as a repair, or the tool would
        # promise the same no-op fix forever.
        for f in after["findings"]:
            self.assertIn("graph", f["detail"].lower(), f)
            self.assertIn("will NOT install this one", f["remedy"])
        self.assertEqual(after["repair_plan"], [],
                         "a repair that cannot succeed is still being offered")

        snapshot = tree_hash(self.repo)
        conformance(self.repo, "--only", "hooks", "--fix")
        self.assertEqual(tree_hash(self.repo), snapshot, "the hooks repair is not idempotent")

    def test_an_unadopted_methodology_is_reported_and_never_adopted(self):
        """Adoption is deliberate. `--fix` must report it and change nothing."""
        r = conformance(self.repo, "--only", "methodology", "--json")
        data = json.loads(r.stdout)
        if data["verdict"] == "could not be checked":
            self.skipTest("the methodology renderer is not installed on this machine")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("methodology_unadopted", json.dumps(data["findings"]))
        self.assertEqual(data["repair_plan"], [], "--fix scheduled an adoption")

        snapshot = tree_hash(self.repo)
        conformance(self.repo, "--only", "methodology", "--fix")
        self.assertEqual(tree_hash(self.repo), snapshot, "--fix adopted the repository")
        self.assertFalse((self.repo / "docs/agents/execution/methodology.md").exists())


class StuckRedCheckTest(Fixture):
    def plant_unmanaged(self) -> Path:
        f = self.repo / ".claude" / "agents" / "rogue-judge.md"
        f.write_text("---\nname: rogue-judge\ndescription: hand written\n---\n\nI judge.\n",
                     encoding="utf-8")
        return f

    def test_explicit_project_preview_reports_unmanaged_and_preserves_it(self):
        planted = self.plant_unmanaged()
        preview = subprocess.run(
            [PY, str(SYNC_PERSONAS), "--scope", "project", "--repo", str(self.repo),
             "--preview", "--json"], capture_output=True, text=True)
        self.assertEqual(preview.returncode, 2, preview.stdout + preview.stderr)
        payload = json.loads(preview.stdout)
        self.assertEqual(payload["operations"], [])
        self.assertIn("unmanaged_persona", json.dumps(payload["findings"]))
        self.assertTrue(planted.is_file())

    def test_the_report_states_the_working_remedy_and_not_the_no_op_one(self):
        self.plant_unmanaged()
        r = conformance(self.repo, "--only", "personas")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("rogue-judge.md", r.stdout)
        self.assertIn("preserves unmanaged content", r.stdout)
        self.assertIn("delete the file", r.stdout)
        self.assertIn("give it a persona source", r.stdout)

    def test_fix_never_deletes_an_agent_file(self):
        planted = self.plant_unmanaged()
        r = conformance(self.repo, "--only", "personas", "--fix")
        self.assertTrue(planted.is_file(), "--fix deleted a file a human wrote")
        self.assertNotEqual(r.returncode, 0)

    def test_the_no_op_remedy_string_never_reaches_the_report(self):
        """The route check relays validator errors verbatim; persona-drift must be dropped.

        Relaying it would print `run \\`sync_personas.py --repo .\\`` in the one report whose job is
        to state the remedy that works. Asserted end-to-end with the drift actually planted, and
        with a positive control that the route check is otherwise producing findings — otherwise a
        route check that crashed would pass this.
        """
        self.plant_unmanaged()
        r = conformance(self.repo, "--only", "route", "--json")
        data = json.loads(r.stdout)
        route = [c for c in data["checks"] if c["name"] == "route"]
        self.assertEqual(len(route), 1)
        self.assertTrue(data["findings"] or data["not_run"],
                        "the route check produced nothing at all; this proves nothing")
        blob = json.dumps(data)
        self.assertNotIn("persona-drift", blob)
        self.assertNotIn("sync_personas.py --repo .", blob)


# ---------------------------------------------------------------------------------------------
# A checker that cannot run
# ---------------------------------------------------------------------------------------------


class CouldNotBeCheckedTest(Fixture):
    def fake_home(self, *, break_preflight: bool) -> Path:
        """A HOME whose toolchain is broken in one specific, named way."""
        home = self.tmp / ("home-broken-preflight" if break_preflight else "home-empty")
        (home / ".claude" / "hooks").mkdir(parents=True)
        if break_preflight:
            pf = home / ".claude" / "hooks" / "preflight.sh"
            pf.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            pf.chmod(0o000)
            self.assertFalse(os.access(pf, os.X_OK), "the fixture is not actually broken")
        return home

    def test_a_missing_checker_is_could_not_be_checked_and_exit_2(self):
        home = self.fake_home(break_preflight=False)
        r = conformance(self.repo, home=home)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("COULD NOT BE CHECKED", r.stdout)
        self.assertNotIn("VERDICT: CONFORMS", r.stdout)
        self.assertIn("has NOT been shown to conform", r.stdout)

    def test_a_non_executable_checker_is_could_not_be_checked_not_a_finding(self):
        home = self.fake_home(break_preflight=True)
        r = conformance(self.repo, "--only", "preflight", "--json", home=home)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["verdict"], "could not be checked")
        self.assertEqual([e["check"] for e in data["not_run"]], ["preflight"])
        self.assertEqual(data["findings"], [],
                         "a checker that could not run must not also produce findings")
        self.assertIn("not executable", data["not_run"][0]["why"])

    def test_the_positive_control_the_same_checker_runs_against_the_real_home(self):
        """Without this, the two tests above would pass against a checker that never works."""
        r = conformance(self.repo, "--only", "preflight", "--json")
        data = json.loads(r.stdout)
        self.assertEqual(data["not_run"], [], data)
        self.assertIn(data["verdict"], ("conforms", "does not conform"))

    def test_an_unimportable_persona_module_is_not_run_rather_than_a_pass(self):
        """The module this file CALLS for its definition of "restricted" is not always there.

        An older `sync_personas.py` without `absent_restrictions` must produce `could not be
        checked`, never a pass and never a private fallback definition — a fallback would be the
        second copy of the rule that this whole design exists to prevent.
        """
        stub = self.tmp / "stub_sync_personas.py"
        stub.write_text("JUDGING_PERSONA_NAMES = frozenset()\n", encoding="utf-8")
        original, cc._sp_cache = cc.SYNC_PERSONAS, None
        cc.SYNC_PERSONAS = stub
        try:
            with self.assertRaises(cc.Unavailable) as ctx:
                cc.personas_module()
            self.assertIn("absent_restrictions", str(ctx.exception))
            check = cc.check_personas(self.repo)
            self.assertIs(check.verdict, cc.Verdict.NOT_RUN)
        finally:
            cc.SYNC_PERSONAS, cc._sp_cache = original, None

    def test_a_persona_module_that_exits_on_import_does_not_kill_the_run(self):
        stub = self.tmp / "exiting_sync_personas.py"
        stub.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        original, cc._sp_cache = cc.SYNC_PERSONAS, None
        cc.SYNC_PERSONAS = stub
        try:
            with self.assertRaises(cc.Unavailable):
                cc.personas_module()
        finally:
            cc.SYNC_PERSONAS, cc._sp_cache = original, None

    def test_an_undefined_exit_code_from_a_callee_is_not_run(self):
        r = cc.Run(["x"], ok=True, rc=7)
        self.assertTrue(r.undefined_rc((0, 1, 2)))
        self.assertFalse(cc.Run(["x"], ok=True, rc=1).undefined_rc((0, 1, 2)))

    def test_the_run_chokepoint_never_raises(self):
        for argv in ([str(self.tmp / "nope")], [PY, str(self.tmp / "nope.py")],
                     [str(self.repo)]):
            got = cc.run(argv)
            self.assertIsInstance(got, cc.Run)
            if not got.ok:
                self.assertTrue(got.why, argv)


# ---------------------------------------------------------------------------------------------
# The read-only path
# ---------------------------------------------------------------------------------------------


class ReadOnlyTest(Fixture):
    def test_the_default_path_writes_nothing(self):
        """Content-hash the tree before and after, and assert equality. Not inspection.

        Every check runs, including the ones that shell out to git and to `gh`. The exclusion of
        `.git` internals is stated in `tree_hash` and `.git/hooks` is deliberately INCLUDED, since
        that is the one part of `.git` this tool can legitimately write.
        """
        before = tree_hash(self.repo)
        self.assertGreater(len(before), 10, "the fixture is too small to prove anything")
        r = conformance(self.repo)
        self.assertIn(r.returncode, (0, 1, 2))
        self.assertEqual(tree_hash(self.repo), before,
                         "the read-only path modified the repository")

    def test_the_json_path_writes_nothing_either(self):
        before = tree_hash(self.repo)
        conformance(self.repo, "--json")
        self.assertEqual(tree_hash(self.repo), before)

    def test_the_positive_control_the_hash_notices_a_change(self):
        """An equality assertion is worthless without proof it can fail."""
        before = tree_hash(self.repo)
        (self.repo / "src" / "w.py").write_text("x = 2\n", encoding="utf-8")
        self.assertNotEqual(tree_hash(self.repo), before)

    def test_fix_and_json_together_are_refused(self):
        r = conformance(self.repo, "--json", "--fix")
        self.assertEqual(r.returncode, 2)
        self.assertIn("must be read before the repair", r.stderr)


# ---------------------------------------------------------------------------------------------
# Scope, selection, and the machine-global tag
# ---------------------------------------------------------------------------------------------


class ReportingTest(Fixture):
    def test_a_plugin_finding_is_tagged_machine_global_in_prose_and_in_json(self):
        r = conformance(self.repo, "--only", "plugin surface", "--json")
        data = json.loads(r.stdout)
        if data["verdict"] == "could not be checked":
            self.skipTest("the plugin enumeration did not run on this machine")
        for f in data["findings"]:
            self.assertEqual(f["scope"], "machine-global", f)
        if data["findings"]:
            text = conformance(self.repo, "--only", "plugin surface").stdout
            self.assertIn("[machine-global]", text)
            self.assertIn("Fixing it here changes nothing", text)

    def test_every_finding_carries_a_scope_and_only_plugins_are_machine_global(self):
        r = conformance(self.repo, "--json")
        for f in json.loads(r.stdout)["findings"]:
            self.assertIn(f["scope"], ("repository", "machine-global"), f)
            if f["scope"] == "machine-global":
                self.assertEqual(f["check"], "plugin surface", f)

    def test_only_never_lets_a_narrowed_run_read_like_a_full_one(self):
        r = conformance(self.repo, "--only", "preflight")
        self.assertIn("SELECTION:", r.stdout)
        self.assertIn("NOT RUN BY REQUEST and therefore unknown", r.stdout)
        data = json.loads(conformance(self.repo, "--only", "preflight", "--json").stdout)
        self.assertEqual(len(data["excluded_by_request"]), len(cc.CHECK_NAMES) - 1)

    def test_a_full_run_declares_nothing_excluded(self):
        data = json.loads(conformance(self.repo, "--json").stdout)
        self.assertEqual(data["excluded_by_request"], [])
        self.assertEqual({c["name"] for c in data["checks"]}, set(cc.CHECK_NAMES))

    def test_an_unknown_only_name_is_a_usage_error_not_a_silent_empty_run(self):
        r = conformance(self.repo, "--only", "nonsense")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no such check", r.stderr)

    def test_a_not_applicable_check_puts_its_reason_in_a_note_not_in_findings(self):
        """A conforming check must not contribute to the findings array.

        The identifier guard is not in force in a private repository, and saying so is information
        the reader needs — but it is not a finding, and a consumer that counts `findings` would
        report a problem this repository does not have.
        """
        data = json.loads(conformance(self.repo, "--only", "identifier guard", "--json").stdout)
        guard = next(c for c in data["checks"] if c["name"] == "identifier guard")
        self.assertEqual(guard["verdict"], "conforms")
        self.assertIn("not applicable", guard["note"])
        self.assertEqual(data["findings"], [])
        self.assertIn("note:", conformance(self.repo, "--only", "identifier guard").stdout)

    def test_the_report_names_the_repair_plan_before_any_repair(self):
        r = conformance(self.repo, "--only", "personas")
        plan_at = r.stdout.index("REPAIR PLAN")
        self.assertNotIn("APPLYING", r.stdout)
        self.assertIn("named before anything is touched", r.stdout[plan_at:plan_at + 200])


# ---------------------------------------------------------------------------------------------
# Structural: this file orchestrates and reimplements nothing
# ---------------------------------------------------------------------------------------------


class CalleeContractTest(Fixture):
    """H3, M6, M7, M8, M9 — each one a place this file read a callee's output wrongly."""

    def test_a_public_repository_reaches_the_identifier_guard_branch(self):
        """H3. The public branch was dead code and no fixture existed that would have noticed.

        `install_hooks.py --check` renders this through `declaration_line`, which returns
        `YES ({where}, dated {date})`. The old reader tested for the lowercase literal
        `repository declares itself PUBLIC: yes`, which matches in NO repository — so the deny-list
        liveness probe never ran, a public repo was told in writing it was not public, and a check
        that examined nothing returned CONFORMS.
        """
        declare = subprocess.run(
            [PY, str(cc.PD / "install_hooks.py"), str(self.repo), "--public",
             "--scope", "project"],
            capture_output=True, text=True)
        self.assertEqual(declare.returncode, 0, declare.stdout + declare.stderr)
        states = cc._hook_states(subprocess.run(
            [PY, str(cc.PD / "install_hooks.py"), str(self.repo), "--check"],
            capture_output=True, text=True).stdout)
        # The fixture is proved public before anything is concluded from it.
        self.assertTrue(cc._declares_public(states), states.get(cc.PUBLIC_KEY))
        self.assertTrue(states[cc.PUBLIC_KEY].startswith("YES"),
                        "the callee's casing changed; re-derive the parse")

        r = conformance(self.repo, "--only", "identifier guard", "--json")
        data = json.loads(r.stdout)
        guard = next(c for c in data["checks"] if c["name"] == "identifier guard")
        self.assertNotIn("not applicable", guard["note"],
                         "a PUBLIC repository was told the guard is not in force")

    def test_the_old_lowercase_literal_would_have_matched_nothing(self):
        """The RED, kept as an assertion so the bug cannot be reintroduced by a rewrite."""
        rendered = "YES (docs/agents/README.md, dated 2026-08-02)"
        self.assertFalse(f"repository declares itself PUBLIC: {rendered}".find(
            "repository declares itself PUBLIC: yes") >= 0)
        self.assertTrue(cc._declares_public({cc.PUBLIC_KEY: rendered}))

    def test_a_non_critical_github_severity_is_not_a_non_conformance(self):
        """M8. `exception` is an APPROVED public-exception waiver, and `exit_code` returns 0 for it.

        Flattening every entry of `findings` into a non-conformance made a deliberately-public
        repository report `github DOES NOT CONFORM` on every run, with no remedy that could clear
        it, because the thing being reported was an approval.
        """
        r = conformance(self.repo, "--only", "github", "--json")
        data = json.loads(r.stdout)
        for f in data["findings"]:
            self.assertNotIn("[exception]", f["detail"])
        gh = next(c for c in data["checks"] if c["name"] == "github")
        if data["verdict"] == "does not conform":
            self.assertTrue(data["findings"], "non-conformance with no finding attached")
        # Nothing is silenced: non-critical severities must still be visible somewhere.
        self.assertIsInstance(gh["note"], str)

    def test_a_partial_route_keeps_its_findings_instead_of_discarding_them(self):
        """M9. `partial` outranks `findings` in the callee's status, so returning NOT_RUN with an
        empty list threw away every real route error. The verdict stays safe; the report must not
        go blank."""
        broken = self.repo / "docs" / "agents" / "README.md"
        original = broken.read_text()
        broken.write_text(original + "\n[dead](./nowhere.md)\n")
        self.assertNotEqual(broken.read_text(), original)
        data = json.loads(conformance(self.repo, "--only", "route", "--json").stdout)
        self.assertTrue(data["findings"] or data["verdict"] == "does not conform",
                        f"a broken link produced no finding: {data}")
        if data["verdict"] == "could not be checked":
            self.assertTrue(data["findings"],
                            "NOT_RUN discarded the findings the families that DID run produced")


class StructureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))

    def check_functions(self) -> list[ast.FunctionDef]:
        out = [n for n in ast.walk(self.tree)
               if isinstance(n, ast.FunctionDef) and n.name.startswith("check_")]
        self.assertGreaterEqual(len(out), 7, "the positive control: checks were not found at all")
        return out

    def test_no_conformance_rule_is_defined_in_this_file(self):
        """Every check must delegate — to `run()` or to the persona module — never decide alone.

        Held by AST rather than by the module docstring's promise, because the docstring is the
        thing that would go stale the first time someone adds a check inline "just this once".
        """
        for fn in self.check_functions():
            calls = {n.func.id for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            self.assertTrue(
                {"run", "personas_module"} & calls,
                f"{fn.name} reaches no checker — it is deciding conformance on its own")

    def test_no_check_classifies_a_callee_by_an_inline_string_literal(self):
        """L12. The old AST test asked only that *a* call existed somewhere in each `check_`.

        `check_methodology` satisfied that while deciding a four-state machine from three
        substrings typed inline — the exact shape the "reimplements nothing" test was supposed to
        catch. Classification vocabulary must now live in a module-level table, where it is visible
        as the coupling it is, so this asserts no `check_` function contains an `in` comparison
        against a bare string literal.
        """
        offenders = []
        for fn in self.check_functions():
            for node in ast.walk(fn):
                if not isinstance(node, ast.Compare):
                    continue
                for op, operand in zip(node.ops, node.comparators):
                    if isinstance(op, ast.In) and isinstance(operand, ast.Constant) \
                            and isinstance(operand.value, str):
                        offenders.append((fn.name, node.lineno, operand.value[:40]))
                    if isinstance(op, ast.In) and isinstance(node.left, ast.Constant) \
                            and isinstance(node.left.value, str) and len(node.left.value) > 3:
                        offenders.append((fn.name, node.lineno, node.left.value[:40]))
        self.assertEqual(offenders, [],
                         f"a callee's output is being classified by an inline literal: {offenders}")

    def test_runtime_states_match_the_frozen_interface(self):
        self.assertEqual(cc.RUNTIME_STATES, {
            "current", "repairable", "legacy", "source_changed", "unadopted", "deferred",
            "unmanaged", "invalid",
        })

    def test_no_tool_name_is_written_as_a_literal_in_this_file(self):
        """The allow-list `--fix` writes is derived from the pool, never typed here.

        Tool names are read out of `agent-personas` at run time. A literal here would be a second
        copy of the roster's policy, drifting from the day it was written. The vocabulary is
        derived from the live module so the test cannot go stale either.
        """
        sp = cc.personas_module()
        vocabulary = set(sp.JUDGE_DENIED_TOOLS)
        for src in sp.pool_sources():
            meta, _ = sp.parse(src)
            vocabulary |= set(sp._tools(meta.get("claude.tools")))
            vocabulary |= set(sp._tools(meta.get("claude.disallowedTools")))
        self.assertGreater(len(vocabulary), 5, "the positive control: no vocabulary was derived")
        source = SCRIPT.read_text(encoding="utf-8")
        # Strings only. Prose in docstrings legitimately names `Agent` and `Monitor` when
        # explaining the finding; what must not appear is a tool name in executable code.
        offenders = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.strip() in vocabulary:
                    offenders.append((node.lineno, node.value))
        self.assertEqual(offenders, [], f"tool names hard-coded in {SCRIPT.name}: {offenders}")
        self.assertIn("judging_floor", source)

    def test_the_judging_floor_is_derived_and_contains_no_denied_tool(self):
        sp = cc.personas_module()
        floor = cc.judging_floor(sp)
        self.assertTrue(floor, "the floor is empty; it would grant a judge nothing at all")
        self.assertFalse(set(floor) & set(sp.JUDGE_DENIED_TOOLS))
        # It really is the intersection of the roster's own allow-lists, not a guess.
        for src in sp.pool_sources():
            meta, _ = sp.parse(src)
            if meta.get("name") in sp.JUDGING_PERSONA_NAMES:
                self.assertLessEqual(set(floor), set(sp._tools(meta.get("claude.tools"))),
                                     f"the floor exceeds what {meta['name']} is trusted with")

    def test_nothing_here_is_wired_to_an_automatic_invocation(self):
        """This skill is the founder's instrument. It must not appear in any hook or settings.

        Asserted against the real machine because the risk is a future edit elsewhere, and this is
        the only place that would notice. `--fix` reaching a session-start path would mean an agent
        writing into a project repository, which is the absolute constraint this skill exists under.
        """
        home = cc.HOME
        haystacks = [home / ".claude" / "settings.json"]
        haystacks += list((home / ".claude" / "hooks").glob("*")) if (home / ".claude" / "hooks").is_dir() else []
        looked = 0
        for p in haystacks:
            if not p.is_file():
                continue
            looked += 1
            self.assertNotIn("check_conformance", p.read_text(encoding="utf-8", errors="replace"),
                             f"{p} invokes this skill automatically")
        self.assertGreater(looked, 0, "the positive control: nothing was actually examined")


class SkillDocTest(unittest.TestCase):
    def test_compatibility_route_names_the_checker_and_management_repair(self):
        doc = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scripts/check_conformance.py", doc)
        self.assertIn("methodology-management/references/assessment.md", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
