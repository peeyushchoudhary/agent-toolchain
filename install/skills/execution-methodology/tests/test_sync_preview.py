from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
PERSONAS = SKILL.parent / "agent-personas"
GATE_SANDBOX = SKILL.parent / "gate-sandbox"
TARGET_REL = Path("docs/agents/execution/methodology.md")
OVERLAY_REL = Path("docs/agents/execution/overlay.md")
RUNTIME_REL = Path("docs/agents/execution/runtime.json")


class SyncPreviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = self.root / "skills"
        shutil.copytree(SKILL, self.bundle / "execution-methodology")
        shutil.copytree(PERSONAS, self.bundle / "agent-personas")
        shutil.copytree(GATE_SANDBOX, self.bundle / "gate-sandbox")
        self.script = self.bundle / "execution-methodology/scripts/sync_methodology.py"
        self.repo = self.root / "project"
        self.repo.mkdir()
        self.fake_home = self.root / "home"
        self.fake_home.mkdir()
        (self.fake_home / "unmanaged-global").write_text("unchanged\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_owner(self, *args: str, repo: Path | None = None,
                  timeout: float = 10, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        command = [sys.executable, str(self.script), "--repo", str(repo or self.repo), *args]
        command_env = {**os.environ, "HOME": str(self.fake_home)}
        if env is not None:
            command_env.update(env)
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              env=command_env)

    def preview(self, *, repo: Path | None = None, env: dict[str, str] | None = None
                ) -> tuple[subprocess.CompletedProcess, dict]:
        result = self.run_owner("--scope", "project", "--preview", "--json",
                                repo=repo, env=env)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"preview stdout was not exactly JSON: {exc}\n{result.stdout}{result.stderr}")
        self.assertEqual(result.stdout.count("\n"), 1)
        return result, payload

    def project_snapshot(self) -> dict[str, tuple]:
        snapshot = {}
        for path in sorted(self.repo.rglob("*")):
            relative = path.relative_to(self.repo).as_posix()
            info = path.lstat()
            value = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode),
                     info.st_mtime_ns, info.st_size)
            if stat.S_ISREG(info.st_mode):
                value += (path.read_bytes(),)
            elif stat.S_ISLNK(info.st_mode):
                value += (os.readlink(path),)
            snapshot[relative] = value
        return snapshot

    def file_snapshot(self, root: Path) -> dict[str, tuple]:
        snapshot = {}
        for path in sorted(root.rglob("*")):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                value = (info.st_mode, info.st_mtime_ns, path.read_bytes())
            elif stat.S_ISLNK(info.st_mode):
                value = (info.st_mode, info.st_mtime_ns, os.readlink(path))
            else:
                continue
            snapshot[path.relative_to(root).as_posix()] = value
        return snapshot

    def assert_receipt_matches_application(self, receipt: dict) -> None:
        before = self.file_snapshot(self.repo)
        global_before = self.file_snapshot(self.fake_home)
        applied = self.run_owner("--scope", "project")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        after = self.file_snapshot(self.repo)
        expected_changed = {row["path"] for row in receipt["operations"]
                            if row["action"] != "mkdir"}
        actual_changed = {path for path in set(before) | set(after)
                          if before.get(path) != after.get(path)}
        self.assertEqual(actual_changed, expected_changed)
        self.assertEqual(self.file_snapshot(self.fake_home), global_before)
        for operation in receipt["operations"]:
            path = self.repo / operation["path"]
            if operation["action"] == "mkdir":
                self.assertTrue(path.is_dir())
                continue
            self.assertEqual(path.read_text(encoding="utf-8"), operation["content"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             operation["after_sha256"])

    def write_route(self) -> None:
        route = self.repo / "docs/agents/README.md"
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text("# Route\n\n[methodology](execution/methodology.md)\n", encoding="utf-8")
        (self.repo / "custom.txt").write_text("unmanaged custom content\n", encoding="utf-8")

    def test_absent_tree_preview_is_pure_and_matches_application(self) -> None:
        before = self.project_snapshot()
        result, receipt = self.preview()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.project_snapshot(), before)
        self.assertEqual(set(receipt), {"schema_version", "scope", "repo", "can_apply",
                                        "operations", "findings"})
        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual(receipt["scope"], "project")
        self.assertEqual(receipt["repo"], str(self.repo.resolve()))
        self.assertTrue(receipt["can_apply"])
        self.assertEqual(receipt["operations"][:3], [
            {"action": "mkdir", "path": "docs"},
            {"action": "mkdir", "path": "docs/agents"},
            {"action": "mkdir", "path": "docs/agents/execution"},
        ])
        self.assertEqual([row["path"] for row in receipt["operations"][3:]],
                         [TARGET_REL.as_posix(), RUNTIME_REL.as_posix()])
        self.assertTrue(all(row["action"] == "create" for row in receipt["operations"][3:]))
        self.assertEqual(receipt["findings"][0]["code"], "route_invalid")
        self.assertEqual(receipt["findings"][0]["severity"], "warning")
        self.assert_receipt_matches_application(receipt)

    def test_adopted_update_overlay_and_noop_preview_match_application(self) -> None:
        self.write_route()
        overlay = self.repo / OVERLAY_REL
        overlay.parent.mkdir(parents=True, exist_ok=True)
        overlay.write_text("Gate: make check\n", encoding="utf-8")
        created, first = self.preview()
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assert_receipt_matches_application(first)
        self.assertIn("Gate: make check", (self.repo / TARGET_REL).read_text(encoding="utf-8"))

        noop, receipt = self.preview()
        self.assertEqual(noop.returncode, 0, noop.stderr)
        self.assertEqual(receipt["operations"], [])

        source = self.bundle / "execution-methodology/methodology.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nPreview fixture change.\n",
                          encoding="utf-8")
        before_overlay = overlay.read_bytes()
        updated, receipt = self.preview()
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertEqual([row["action"] for row in receipt["operations"]], ["update", "update"])
        self.assertTrue(all(row["before_sha256"] for row in receipt["operations"]))
        self.assert_receipt_matches_application(receipt)
        self.assertEqual(overlay.read_bytes(), before_overlay)

    def test_raw_byte_difference_cannot_collapse_through_replacement_decoding(self) -> None:
        self.write_route()
        source = self.bundle / "execution-methodology/methodology.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nReplacement marker: \ufffd\n",
                          encoding="utf-8")
        rendered = self.run_owner("--scope", "project")
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        target = self.repo / TARGET_REL
        valid = target.read_bytes()
        self.assertIn("\ufffd".encode(), valid)
        invalid = valid.replace("\ufffd".encode(), b"\xff", 1)
        target.write_bytes(invalid)

        result, receipt = self.preview()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["path"] for row in receipt["operations"]],
                         [TARGET_REL.as_posix()])
        self.assertEqual(receipt["operations"][0]["before_sha256"],
                         hashlib.sha256(invalid).hexdigest())
        self.assert_receipt_matches_application(receipt)

    def test_unmanaged_outputs_empty_overlay_and_missing_dependency_refuse_equally(self) -> None:
        cases = ("methodology", "inventory", "empty-overlay", "dependency")
        for case in cases:
            with self.subTest(case=case):
                self.tearDown()
                self.setUp()
                self.write_route()
                execution = self.repo / TARGET_REL.parent
                execution.mkdir(parents=True, exist_ok=True)
                if case == "methodology":
                    (self.repo / TARGET_REL).write_text("owner rules\n", encoding="utf-8")
                elif case == "inventory":
                    (self.repo / RUNTIME_REL).write_text("{}\n", encoding="utf-8")
                elif case == "empty-overlay":
                    (self.repo / OVERLAY_REL).write_text("\n", encoding="utf-8")
                else:
                    (self.bundle / "execution-methodology/references/execution-loop.md").unlink()
                before = self.project_snapshot()

                preview_result, receipt = self.preview()
                apply_result = self.run_owner("--scope", "project")

                self.assertEqual(preview_result.returncode, 2)
                self.assertFalse(receipt["can_apply"])
                self.assertEqual(receipt["operations"], [])
                self.assertEqual(receipt["findings"][0]["code"], "render_refused")
                self.assertEqual(apply_result.returncode, 2)
                self.assertEqual(self.project_snapshot(), before)

    def test_approved_repair_accepts_unchanged_regular_hardlinked_overlay(self) -> None:
        self.write_route()
        external = self.root / "authored-overlay.md"
        external.write_text("Gate: make check\n", encoding="utf-8")
        overlay = self.repo / OVERLAY_REL
        overlay.parent.mkdir(parents=True, exist_ok=True)
        os.link(external, overlay)
        rendered = self.run_owner("--scope", "project")
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        target = self.repo / TARGET_REL
        target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
        status_result = self.run_owner("--status-json")
        self.assertEqual(status_result.returncode, 0, status_result.stdout + status_result.stderr)
        status = json.loads(status_result.stdout)
        authorization = {
            "identity": status["approved"],
            "overlay_expected_sha256": status["overlay"]["expected_sha256"],
        }
        before = (external.read_bytes(), external.stat().st_mtime_ns,
                  overlay.read_bytes(), overlay.stat().st_mtime_ns)

        repaired = self.run_owner(
            "--repair-approved", json.dumps(authorization, separators=(",", ":")))

        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertIn("repaired approved runtime", repaired.stdout)
        self.assertEqual((external.read_bytes(), external.stat().st_mtime_ns,
                          overlay.read_bytes(), overlay.stat().st_mtime_ns), before)
        current = self.run_owner("--status-json")
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
        self.assertEqual(json.loads(current.stdout)["state"], "current")

    def test_preview_refuses_symlink_hardlink_and_fifo_destinations_without_touching_them(self) -> None:
        for kind in ("directory-symlink", "file-symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                self.tearDown()
                self.setUp()
                outside = self.root / "outside"
                outside.mkdir()
                execution = self.repo / TARGET_REL.parent
                if kind == "directory-symlink":
                    execution.parent.mkdir(parents=True)
                    execution.symlink_to(outside, target_is_directory=True)
                else:
                    execution.mkdir(parents=True)
                    destination = self.repo / TARGET_REL
                    external = outside / "external"
                    if kind == "file-symlink":
                        external.write_text("outside\n", encoding="utf-8")
                        destination.symlink_to(external)
                    elif kind == "hardlink":
                        self.write_route()
                        rendered = self.run_owner("--scope", "project")
                        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
                        external.write_bytes(destination.read_bytes())
                        destination.unlink()
                        os.link(external, destination)
                    else:
                        os.mkfifo(destination)
                outside_before = {p.name: (p.lstat().st_mtime_ns, p.read_bytes())
                                  for p in outside.iterdir() if p.is_file()}

                preview_result, receipt = self.preview()
                apply_result = self.run_owner("--scope", "project", timeout=3)

                self.assertEqual(preview_result.returncode, 2)
                self.assertFalse(receipt["can_apply"])
                self.assertEqual(receipt["operations"], [])
                self.assertEqual(apply_result.returncode, 2)
                self.assertEqual(outside_before, {p.name: (p.lstat().st_mtime_ns, p.read_bytes())
                                                  for p in outside.iterdir() if p.is_file()})

    def test_preview_is_project_scoped_and_suppresses_bytecode(self) -> None:
        sentinel_home = self.fake_home
        sentinel = sentinel_home / "global-sentinel"
        sentinel.write_text("unchanged\n", encoding="utf-8")
        for cache in list(self.bundle.rglob("__pycache__")):
            shutil.rmtree(cache)
        env = dict(os.environ)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env["HOME"] = str(sentinel_home)
        bundle_before = self.file_snapshot(self.bundle)
        project_before = self.project_snapshot()
        global_before = self.file_snapshot(sentinel_home)

        result, receipt = self.preview(env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(receipt["can_apply"])
        self.assertEqual(self.file_snapshot(self.bundle), bundle_before)
        self.assertEqual(self.project_snapshot(), project_before)
        self.assertEqual(self.file_snapshot(sentinel_home), global_before)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged\n")
        self.assertEqual(list(self.bundle.rglob("__pycache__")), [])
        self.assertEqual(list(self.repo.rglob("__pycache__")), [])
        self.assertEqual(list(sentinel_home.rglob("__pycache__")), [])

    def test_git_provenance_does_not_refresh_index(self) -> None:
        checkout = self.root / "checkout"
        checkout.mkdir()
        self.bundle.rename(checkout / "skills")
        self.bundle = checkout / "skills"
        self.script = self.bundle / "execution-methodology/scripts/sync_methodology.py"
        commands = (["git", "init", "-q"], ["git", "add", "skills"],
                    ["git", "-c", "user.name=Preview Test", "-c",
                     "user.email=preview@example.invalid", "commit", "-qm", "fixture"])
        for command in commands:
            result = subprocess.run(command, cwd=checkout, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        declared = self.bundle / "execution-methodology/methodology.md"
        info = declared.stat()
        os.utime(declared, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        index = checkout / ".git/index"
        before = (index.read_bytes(), index.stat().st_mtime_ns, index.stat().st_mode)

        result, receipt = self.preview()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(receipt["can_apply"])
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns, index.stat().st_mode), before)

    def test_invalid_preview_cli_modes_refuse_without_writes(self) -> None:
        invalid = (
            ("--scope", "global", "--preview", "--json"),
            ("--preview", "--json"),
            ("--scope", "project", "--json"),
            ("--scope", "project", "--preview", "--json", "--check"),
            ("--scope", "project", "--preview", "--json", "--status-json"),
            ("--scope", "project", "--preview", "--json", "--list"),
            ("--scope", "project", "--preview", "--json", "--adoption-check"),
            ("--scope", "project", "--preview", "--json", "--repair-approved", "{}"),
        )
        for args in invalid:
            with self.subTest(args=args):
                before = self.project_snapshot()
                result = self.run_owner(*args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertNotEqual(result.stderr, "")
                self.assertEqual(self.project_snapshot(), before)

    def test_invalid_root_has_structured_refusal(self) -> None:
        missing = self.root / "missing/../project-that-does-not-exist"
        result, receipt = self.preview(repo=missing)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(receipt["repo"], str(missing.resolve(strict=False)))
        self.assertFalse(receipt["can_apply"])
        self.assertEqual(receipt["operations"], [])
        self.assertEqual(receipt["findings"][0]["code"], "render_refused")


if __name__ == "__main__":
    unittest.main()
