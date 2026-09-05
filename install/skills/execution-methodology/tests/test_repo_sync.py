from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "sync_methodology.py"
SOURCE = SKILL / "methodology.md"
VALIDATOR = (Path.home() / ".claude" / "skills" / "progressive-disclosure"
             / "scripts" / "validate_disclosure.py")
TARGET_REL = Path("docs") / "agents" / "execution" / "methodology.md"
OVERLAY_REL = Path("docs") / "agents" / "execution" / "overlay.md"
REVIEWER = SKILL.parent / "agent-personas" / "personas" / "reviewer.md"
PERSONA_GUIDE = REVIEWER.parents[1] / "SKILL.md"


def write_overlay(repo: Path, text: str, encoding: str = "utf-8") -> None:
    """Overlay lives in a subdirectory now; tests must create it before writing."""
    dest = repo / OVERLAY_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding=encoding)




def installed_version() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    return re.search(r'^METHODOLOGY_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE).group(1)


class MethodologySyncTest(unittest.TestCase):
    def run_sync(self, repo: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo), *extra],
            capture_output=True,
            text=True,
        )

    def make_repo(self, root: Path) -> Path:
        """A repo with a route index that already links the rendered methodology.

        Every test using this helper is about rendering/staleness, not routing, so it starts
        routed. Routing itself (missing link, missing README) has its own dedicated tests below.
        """
        repo = root / "project"
        (repo / "docs" / "agents").mkdir(parents=True)
        (repo / "docs" / "agents" / "README.md").write_text(
            "# Agent guide\n\n"
            "| Lane | Read next |\n"
            "| --- | --- |\n"
            "| Spec, design, plan, or executing a plan | "
            "[execution/methodology.md](execution/methodology.md) |\n",
            encoding="utf-8",
        )
        return repo

    def test_process_budget_contract_is_version_5_1(self) -> None:
        """The stamp and the rules it stamps move together.

        A version pin on its own only proves someone edited a constant. v4.0's substance is the
        process ceiling, so the published text has to carry it in both files a repository can
        reach — the skill entry point and the rendered methodology. The version left behind at
        1.4 while its rules shipped is the recorded reason this asserts more than the number.

        The pin moves to 5.1 with the 5 September 2026 lane and review reconciliation. The BUDGET
        assertions below do not move: v5.1 changes lane admission and where the review contract is
        owned, not what process is allowed to cost, and a version bump that quietly relaxed the
        ceiling is exactly what this test exists to catch.
        """
        self.assertEqual(installed_version(), "5.1")
        for relative in ("SKILL.md", "methodology.md"):
            with self.subTest(relative=relative):
                body = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertIn("ratio_meter.py", body)
                self.assertIn("weekly_review.py", body)
                self.assertIn("10%", body)

    def test_pre_gate_adversarial_review_contract_is_published(self) -> None:
        body = " ".join(SOURCE.read_text(encoding="utf-8").split())
        self.assertIn("fresh, isolated, read-only `reviewer`", body)
        self.assertIn("only named artifact paths, never the author conversation", body)
        self.assertIn("`PASS` is valid; there is no finding quota", body)
        self.assertIn(
            "criterion or invariant, a reachable trigger or state sequence, the observable "
            "consequence, artifact evidence, severity, and the smallest correction or human "
            "decision",
            body,
        )
        self.assertIn("one correction and one scoped rereview", body)
        self.assertIn("Design recurrence returns to Gate 1", body)
        self.assertIn("plan recurrence returns to Gate 2", body)
        self.assertIn('`fork_turns: "none"`', body)
        self.assertIn("equivalent fresh-thread primitive", body)
        self.assertIn("Prompt wording alone does not establish isolation", body)
        self.assertIn("persisted original finding or report path", body)
        self.assertIn("correction or diff path", body)
        self.assertIn("corrected artifact path", body)
        self.assertIn("governing frozen artifact paths", body)
        self.assertIn(
            "defaults to Implementation unless Design or Plan is explicitly named",
            body,
        )

        execution_route = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("[methodology.md](methodology.md)", execution_route)
        persona_route = " ".join(PERSONA_GUIDE.read_text(encoding="utf-8").split())
        self.assertIn(
            "The `execution-methodology` skill owns stage order, lane admission, review packets "
            "and rounds, gates, and terminal states",
            persona_route,
        )

        reviewer = " ".join(REVIEWER.read_text(encoding="utf-8").split())
        self.assertIn("**Design** — before Gate 1", reviewer)
        self.assertIn("**Plan** — before Gate 2", reviewer)
        self.assertIn("**Implementation** — after code is written", reviewer)
        self.assertIn(
            "For design and plan review, arrive fresh and isolated. Receive named artifact paths, "
            "not the author conversation",
            reviewer,
        )
        self.assertIn(
            "criterion or invariant, the reachable trigger or state sequence, the observable "
            "consequence, artifact evidence, severity, and the smallest correction or human "
            "decision",
            reviewer,
        )
        self.assertIn("Never invent a defect to satisfy a quota: `PASS` is valid", reviewer)
        self.assertIn(
            "On a scoped rereview, inspect the correction and the causal area it touches",
            reviewer,
        )
        self.assertIn("Do not author or apply the correction yourself", reviewer)
        self.assertIn("widen the rereview into a consensus loop", reviewer)
        self.assertIn("fresh-thread primitive", reviewer)
        self.assertIn("persisted original finding or report path", reviewer)
        self.assertIn("correction or diff path", reviewer)
        self.assertIn("corrected artifact path", reviewer)
        self.assertIn("governing frozen artifact paths", reviewer)
        self.assertIn(
            "defaults to Implementation unless Design or Plan is explicitly named",
            reviewer,
        )

    def test_render_then_check_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            generated = self.run_sync(repo)
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            self.assertTrue((repo / TARGET_REL).is_file())

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("in sync", checked.stdout)

    def test_rendering_twice_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.run_sync(repo)
            first = (repo / TARGET_REL).read_text(encoding="utf-8")

            again = self.run_sync(repo)

            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("already up to date", again.stdout)
            self.assertEqual(first, (repo / TARGET_REL).read_text(encoding="utf-8"))

    def test_hand_edit_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.run_sync(repo)
            target = repo / TARGET_REL
            target.write_text(target.read_text(encoding="utf-8") + "\nsmuggled rule\n",
                              encoding="utf-8")

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn("STALE", checked.stdout)
            self.assertIn("stale or hand-edited", checked.stdout)

    def test_missing_rendered_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn("(missing)", checked.stdout)

    def test_render_warns_when_the_readme_does_not_link_the_rendered_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "docs" / "agents" / "README.md").write_text(
                "# Agent guide\n\nNo route to the methodology here.\n", encoding="utf-8")

            generated = self.run_sync(repo)

            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            self.assertIn("WARNING", generated.stdout)
            self.assertIn("nothing routes to it", generated.stdout)
            self.assertIn("[execution/methodology.md](execution/methodology.md)", generated.stdout)
            self.assertTrue((repo / TARGET_REL).is_file())

    def test_check_errors_when_the_readme_does_not_link_the_rendered_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "docs" / "agents" / "README.md").write_text(
                "# Agent guide\n\nNo route to the methodology here.\n", encoding="utf-8")
            self.run_sync(repo)

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn("ERROR", checked.stdout)
            self.assertIn("nothing routes", checked.stdout)

    def test_check_errors_when_the_readme_does_not_exist_at_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "docs" / "agents" / "README.md").unlink()
            self.run_sync(repo)

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn("does not exist", checked.stdout)

    def test_check_passes_once_the_route_row_is_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "docs" / "agents" / "README.md").write_text(
                "# Agent guide\n\nNo route to the methodology here.\n", encoding="utf-8")
            self.run_sync(repo)
            self.assertEqual(self.run_sync(repo, "--check").returncode, 1)

            (repo / "docs" / "agents" / "README.md").write_text(
                "# Agent guide\n\n"
                "| Lane | Read next |\n"
                "| --- | --- |\n"
                "| Spec, design, plan, or executing a plan | "
                "[execution/methodology.md](execution/methodology.md) |\n",
                encoding="utf-8")

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("in sync", checked.stdout)

    def test_route_check_does_not_auto_edit_the_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / "docs" / "agents" / "README.md").write_text(
                "# Agent guide\n\nNo route to the methodology here.\n", encoding="utf-8")

            before = (repo / "docs" / "agents" / "README.md").read_text(encoding="utf-8")
            self.run_sync(repo)
            self.run_sync(repo, "--check")
            after = (repo / "docs" / "agents" / "README.md").read_text(encoding="utf-8")

            self.assertEqual(before, after)

    def test_overlay_is_appended_under_its_own_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            write_overlay(repo, 
                "Run `./scripts/agent-context.sh backend` before any task.\n",
                encoding="utf-8",
            )

            generated = self.run_sync(repo)

            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            rendered = (repo / TARGET_REL).read_text(encoding="utf-8")
            self.assertIn("## Repository-specific execution rules", rendered)
            self.assertTrue(rendered.rstrip().endswith("before any task."), rendered[-200:])
            self.assertLess(rendered.index("## Principles"),
                            rendered.index("## Repository-specific execution rules"))
            self.assertEqual(self.run_sync(repo, "--check").returncode, 0)

    def test_editing_the_overlay_makes_the_rendered_copy_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            write_overlay(repo, "Gate: `make check`.\n", encoding="utf-8")
            self.run_sync(repo)
            write_overlay(repo, "Gate: `make verify`.\n", encoding="utf-8")

            checked = self.run_sync(repo, "--check")

            self.assertEqual(checked.returncode, 1)
            self.assertIn("STALE", checked.stdout)

    def test_an_unmanaged_hand_written_file_is_never_clobbered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / TARGET_REL).parent.mkdir(parents=True, exist_ok=True)
            (repo / TARGET_REL).write_text("# My own execution notes\n", encoding="utf-8")

            generated = self.run_sync(repo)

            self.assertEqual(generated.returncode, 2)
            self.assertIn("refusing to overwrite", generated.stderr)
            self.assertEqual((repo / TARGET_REL).read_text(encoding="utf-8"),
                             "# My own execution notes\n")
            self.assertEqual(self.run_sync(repo, "--check").returncode, 1)

    def test_render_identity_depends_on_normalized_source_bytes_not_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "execution-methodology"
            shutil.copytree(SKILL, skill)
            script = skill / "scripts" / "sync_methodology.py"
            source = skill / "methodology.md"

            def copied_sync(repo: Path, *extra: str) -> subprocess.CompletedProcess:
                return subprocess.run(
                    [sys.executable, str(script), "--repo", str(repo), *extra],
                    capture_output=True,
                    text=True,
                )

            first_repo = self.make_repo(root / "first")
            second_repo = self.make_repo(root / "second")
            first_mtime = datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp()
            second_mtime = datetime(2026, 8, 25, 12, tzinfo=timezone.utc).timestamp()

            os.utime(source, (first_mtime, first_mtime))
            first = copied_sync(first_repo)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            first_render = (first_repo / TARGET_REL).read_bytes()

            os.utime(source, (second_mtime, second_mtime))
            second = copied_sync(second_repo)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            second_render = (second_repo / TARGET_REL).read_bytes()

            self.assertEqual(first_render, second_render)
            checked = copied_sync(first_repo, "--check")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            rendered = first_render.decode("utf-8")
            match = re.search(r"<!-- execution-methodology: (\{[^\r\n]*\}) -->", rendered)
            self.assertIsNotNone(match, rendered[:400])
            normalized = source.read_text(encoding="utf-8").strip()
            expected_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            self.assertEqual(
                json.loads(match.group(1)),
                {"v": installed_version(), "source_sha256": expected_digest},
            )

            source.write_text(normalized + "\n\nA changed rule.\n", encoding="utf-8")
            stale = copied_sync(first_repo, "--check")
            self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
            self.assertIn("STALE", stale.stdout)

            changed = copied_sync(second_repo)
            self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
            changed_render = (second_repo / TARGET_REL).read_text(encoding="utf-8")
            changed_match = re.search(
                r"<!-- execution-methodology: (\{[^\r\n]*\}) -->", changed_render
            )
            self.assertIsNotNone(changed_match, changed_render[:400])
            changed_digest = json.loads(changed_match.group(1))["source_sha256"]
            self.assertNotEqual(changed_digest, expected_digest)

            overridden = copied_sync(first_repo, "--rendered", "2026-08-24")
            self.assertEqual(overridden.returncode, 2)
            self.assertIn("unrecognized arguments: --rendered 2026-08-24", overridden.stderr)

    def test_generated_banner_names_the_source_and_forbids_hand_editing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.run_sync(repo)

            first_line = (repo / TARGET_REL).read_text(encoding="utf-8").splitlines()[0]

            self.assertIn("GENERATED", first_line)
            self.assertIn("execution-methodology/methodology.md", first_line)
            self.assertIn("do not hand-edit", first_line)

    def test_an_empty_overlay_is_rejected_rather_than_rendered_as_a_blank_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            write_overlay(repo, "\n  \n", encoding="utf-8")

            generated = self.run_sync(repo)

            self.assertEqual(generated.returncode, 2)
            self.assertIn("is empty", generated.stderr)

    def test_list_reports_the_version_and_the_repo_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.run_sync(repo)

            listed = self.run_sync(repo, "--list")

            self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
            self.assertIn(f"version     {installed_version()}", listed.stdout)
            normalized = SOURCE.read_text(encoding="utf-8").strip()
            expected_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            self.assertIn(f"source sha  {expected_digest}", listed.stdout)
            self.assertIn(f"[v{installed_version()}]", listed.stdout)

    def test_public_junit_guidance_says_skips_fail_evidence(self) -> None:
        # v3.0 moved the JUnit evidence protocol out of the methodology body; the guidance now
        # binds in the reference files, and the body must still route readers to them.
        for relative in ("references/junit-evidence.md", "references/task-card.md"):
            with self.subTest(relative=relative):
                text = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertIn(
                    "failures, errors, and skips all fail",
                    text,
                    f"{relative} must say failures, errors, and skips fail JUnit evidence",
                )
        for relative in ("SKILL.md", "methodology.md"):
            with self.subTest(relative=relative):
                text = (SKILL / relative).read_text(encoding="utf-8")
                self.assertIn("junit-evidence.md", text,
                              f"{relative} must route readers to the JUnit evidence reference")

    def test_junit_trust_boundary_and_nested_sandbox_are_published_consistently(self) -> None:
        # v3.0 surface map: the trust boundary lives in the JUnit evidence reference, the nested
        # sandbox in the Codex gate reference, and the task-card reference carries both because a
        # card author needs both. methodology.md and SKILL.md must route to the references.
        for relative in ("references/junit-evidence.md", "references/task-card.md"):
            with self.subTest(relative=relative):
                body = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertIn("not tamper-resistant", body)
                self.assertIn("local writer", body)
        for relative in ("references/codex-gate-sandbox.md", "references/task-card.md"):
            with self.subTest(relative=relative):
                body = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertIn("nested sandbox", body)
                self.assertIn("codex sandbox -p gate -P copy-write", body)
        for relative in ("SKILL.md", "methodology.md", "references/task-card.md",
                         "references/junit-evidence.md", "references/codex-gate-sandbox.md"):
            with self.subTest(relative=relative):
                body = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertNotIn("cleanTest qualifies", body)
        for relative in ("SKILL.md", "methodology.md"):
            with self.subTest(relative=relative):
                text = (SKILL / relative).read_text(encoding="utf-8")
                self.assertIn("codex-gate-sandbox.md", text,
                              f"{relative} must route readers to the Codex gate reference")

    def test_approved_outer_launch_inner_profile_and_cache_boundary_are_explicit(self) -> None:
        # v3.0 surface map: launch/profile detail binds in the Codex gate reference, the cache
        # boundary in the JUnit evidence reference; the task-card reference carries both.
        for relative in ("references/codex-gate-sandbox.md", "references/task-card.md"):
            with self.subTest(relative=relative):
                body = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertRegex(body, r"approved.*nested|nested.*approved|exact sandbox-launch")
                self.assertIn("source read", body)
                self.assertIn("copy write", body)
                self.assertIn("network disabled", body)
                self.assertIn("--rerun-tasks", body)
        for relative in ("references/junit-evidence.md", "references/task-card.md"):
            with self.subTest(relative=relative):
                body = " ".join((SKILL / relative).read_text(encoding="utf-8").split())
                self.assertIn("cache restore", body)
                self.assertIn("--rerun-tasks", body)


@unittest.skipUnless(VALIDATOR.is_file(), "progressive-disclosure validator is not installed")
class ValidatorMarkerTest(unittest.TestCase):
    """The validator's awareness of the rendered methodology.

    HOME is redirected so the *installed* version is whatever the fixture says, rather than whatever
    happens to be on this machine.
    """

    def make_home(self, root: Path, version: str) -> Path:
        home = root / "home"
        scripts = home / ".claude" / "skills" / "execution-methodology" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "sync_methodology.py").write_text(
            f'METHODOLOGY_VERSION = "{version}"\n', encoding="utf-8")
        return home

    def make_repo(self, root: Path, marker: str | None) -> Path:
        repo = root / "project"
        agents = repo / "docs" / "agents"
        agents.mkdir(parents=True)
        (repo / "AGENTS.md").write_text("# Entry\n\nRoute: [index](docs/agents/README.md)\n",
                                        encoding="utf-8")
        (agents / "README.md").write_text("# Route index\n", encoding="utf-8")
        if marker is not None:
            (agents / "execution").mkdir(parents=True, exist_ok=True)
            (agents / "execution" / "methodology.md").write_text(f"{marker}\n\n# Execution methodology\n",
                                                 encoding="utf-8")
        return repo

    def findings(self, home: Path, repo: Path) -> tuple[list[dict], list[dict]]:
        r = subprocess.run(
            [sys.executable, str(VALIDATOR), str(repo), "--json"],
            capture_output=True, text=True, env={**os.environ, "HOME": str(home)},
        )
        self.assertEqual(r.stderr, "", r.stderr)
        payload = json.loads(r.stdout)
        return payload["errors"], payload["warnings"]

    def kinds(self, items: list[dict]) -> set[str]:
        return {i["kind"] for i in items if i["kind"].startswith("execution-")}

    def test_missing_rendered_file_is_silent_because_adoption_check_owns_it(self) -> None:
        """The disclosure validator must say NOTHING about an unadopted repository.

        It cannot tell the difference between "has not adopted yet" and "deliberately deferred with
        a recorded reason" — only `--adoption-check` can, and it reports all four states. When both
        spoke, an unadopted repo was warned twice and a deferred repo was contradicted: it printed
        its recorded deferral and was then told off for the decision it had just recorded.

        A rendered copy that IS present is still this validator's business: the marker checks and
        the MAJOR-drift error below only fire when the file exists, so they never double-report.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            errors, warns = self.findings(self.make_home(root, "1.0"),
                                          self.make_repo(root, None))

            self.assertEqual(self.kinds(errors), set())
            self.assertEqual(self.kinds(warns), set())

    def test_current_version_produces_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = '<!-- execution-methodology: {"v":"1.0","rendered":"2026-07-28"} -->'
            errors, warns = self.findings(self.make_home(root, "1.0"),
                                          self.make_repo(root, marker))

            self.assertEqual(self.kinds(errors), set())
            self.assertEqual(self.kinds(warns), set())

    def test_major_version_behind_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = '<!-- execution-methodology: {"v":"1.4","rendered":"2026-07-28"} -->'
            errors, warns = self.findings(self.make_home(root, "2.0"),
                                          self.make_repo(root, marker))

            self.assertEqual(self.kinds(errors), {"execution-version-drift"})
            self.assertEqual(self.kinds(warns), set())

    def test_minor_version_behind_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = '<!-- execution-methodology: {"v":"1.0","rendered":"2026-07-28"} -->'
            errors, warns = self.findings(self.make_home(root, "1.3"),
                                          self.make_repo(root, marker))

            self.assertEqual(self.kinds(errors), set())
            self.assertEqual(self.kinds(warns), {"execution-version-drift"})

    def test_a_malformed_marker_is_reported_and_never_raises(self) -> None:
        for marker in ('<!-- execution-methodology: {not json} -->',
                       '<!-- execution-methodology: {"v":"banana"} -->',
                       '<!-- execution-methodology: ["1.0"] -->',
                       '<!-- execution-methodology: {"v":"1.0"} -->\n'
                       '<!-- execution-methodology: {"v":"1.0"} -->'):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                errors, warns = self.findings(self.make_home(root, "1.0"),
                                              self.make_repo(root, marker))

                self.assertEqual(self.kinds(errors) | self.kinds(warns),
                                 {"execution-marker-invalid"})

    def test_a_rendered_file_without_a_marker_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root, None)
            (repo / "docs" / "agents" / "execution").mkdir(parents=True, exist_ok=True)
            (repo / "docs" / "agents" / "execution" / "methodology.md").write_text("# Execution\n",
                                                                   encoding="utf-8")

            errors, warns = self.findings(self.make_home(root, "1.0"), repo)

            self.assertEqual(self.kinds(errors), set())
            self.assertEqual(self.kinds(warns), {"execution-marker-missing"})

    def test_an_uninstalled_skill_produces_no_finding_at_all(self) -> None:
        """A machine without the skill must not have its commits nagged."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()

            errors, warns = self.findings(home, self.make_repo(root, None))

            self.assertEqual(self.kinds(errors) | self.kinds(warns), set())

    def test_an_unrouted_repository_produces_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "project"
            repo.mkdir()
            (repo / "AGENTS.md").write_text("# Entry\n", encoding="utf-8")

            errors, warns = self.findings(self.make_home(root, "1.0"), repo)

            self.assertEqual(self.kinds(errors) | self.kinds(warns), set())

    def test_the_real_renderer_output_satisfies_the_real_validator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root, None)
            generated = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(repo)],
                capture_output=True, text=True,
            )
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)

            errors, warns = self.findings(self.make_home(root, installed_version()), repo)

            self.assertEqual(self.kinds(errors) | self.kinds(warns), set())


class AdoptionCheckTest(unittest.TestCase):
    """`--adoption-check`: four states, one voice, and never a non-zero exit.

    It runs at session start. Every case here asserts exit 0 — a reporter that can fail a session is
    a reporter that will eventually be switched off.
    """

    ROUTE = ("# Agent guide\n\n"
             "| Lane | Read next |\n"
             "| --- | --- |\n"
             "| Spec, design, plan, or executing a plan | "
             "[execution/methodology.md](execution/methodology.md) |\n")

    def run_check(self, repo: Path) -> subprocess.CompletedProcess:
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo), "--adoption-check"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0,
                         f"--adoption-check must always exit 0\n{r.stdout}{r.stderr}")
        return r

    def make_repo(self, root: Path, readme: str | None = None) -> Path:
        repo = root / "project"
        (repo / "docs" / "agents").mkdir(parents=True)
        (repo / "docs" / "agents" / "README.md").write_text(
            self.ROUTE if readme is None else readme, encoding="utf-8")
        return repo

    def render(self, repo: Path) -> None:
        r = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def marker(self, reason: str | None = "pilot repo; adopting after the current milestone",
               stamp: str | None = "2026-01-15", mode: str = "deferred") -> str:
        payload: dict = {"mode": mode}
        if reason is not None:
            payload["reason"] = reason
        if stamp is not None:
            payload["date"] = stamp
        return (self.ROUTE + "\n<!-- execution-methodology: "
                + json.dumps(payload, separators=(",", ":")) + " -->\n")

    # 1. adopted and current

    def test_adopted_and_current_prints_absolutely_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.render(repo)

            r = self.run_check(repo)

            self.assertEqual(r.stdout, "")
            self.assertEqual(r.stderr, "")

    def test_a_current_repo_stays_silent_even_with_an_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            write_overlay(repo, "Gate: `make check`.\n")
            self.render(repo)

            self.assertEqual(self.run_check(repo).stdout, "")

    # 2. adopted but stale

    def test_stale_render_names_the_path_and_the_re_render_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            self.render(repo)
            target = repo / TARGET_REL
            target.write_text(target.read_text(encoding="utf-8") + "\nsmuggled rule\n",
                              encoding="utf-8")

            out = self.run_check(repo).stdout

            self.assertIn("AGENT CONTEXT:", out)
            self.assertIn("docs/agents/execution/methodology.md", out)
            self.assertIn(f"--repo {repo.resolve()}", out)
            self.assertIn("Re-render:", out)

    def test_a_stale_overlay_edit_is_reported_as_stale_not_unadopted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            write_overlay(repo, "Gate: `make check`.\n")
            self.render(repo)
            write_overlay(repo, "Gate: `make verify`.\n")

            out = self.run_check(repo).stdout

            self.assertIn("out of date", out)
            self.assertNotIn("has not been adopted", out)

    def test_an_unmanaged_file_is_stale_and_says_to_move_it_aside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            (repo / TARGET_REL).parent.mkdir(parents=True, exist_ok=True)
            (repo / TARGET_REL).write_text("# My own execution notes\n", encoding="utf-8")

            out = self.run_check(repo).stdout

            self.assertIn("out of date", out)
            self.assertIn("Move it aside", out)

    # 3. deliberately deferred

    def test_a_valid_deferral_is_one_quiet_line_with_its_reason_and_age(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker())

            out = self.run_check(repo)

            self.assertEqual(len(out.stdout.strip().splitlines()), 1, out.stdout)
            self.assertIn("deliberately deferred", out.stdout)
            self.assertIn("since 2026-01-15", out.stdout)
            self.assertIn("adopting after the current milestone", out.stdout)
            self.assertRegex(out.stdout, r"\(\d+ days?\)")

    def test_a_deferral_never_suppresses_an_already_rendered_copy(self) -> None:
        """A repo that rendered and then drifted is stale, marker or not."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker())
            self.render(repo)
            target = repo / TARGET_REL
            target.write_text(target.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

            self.assertIn("out of date", self.run_check(repo).stdout)

    def test_a_marker_inside_a_code_fence_is_documentation_not_a_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fenced = (self.ROUTE + "\nRecord a deferral like this:\n\n```\n"
                      '<!-- execution-methodology: {"mode":"deferred","reason":"x",'
                      '"date":"2026-01-15"} -->\n```\n')
            repo = self.make_repo(Path(tmp), fenced)

            out = self.run_check(repo).stdout

            self.assertIn("has not been adopted", out)
            self.assertNotIn("deliberately deferred", out)

    # 4. unadopted, and the markers that do not count as decisions

    def test_unadopted_warns_and_offers_both_ways_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))

            out = self.run_check(repo).stdout

            self.assertIn("AGENT CONTEXT:", out)
            self.assertIn("has not been adopted", out)
            self.assertIn(f"--repo {repo.resolve()}", out)
            self.assertIn('"mode":"deferred"', out)
            self.assertIn("never automatic", out)

    def test_an_empty_reason_is_not_a_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker(reason="   "))

            out = self.run_check(repo).stdout

            self.assertIn("has not been adopted", out)
            self.assertIn("no reason", out)
            self.assertNotIn("deliberately deferred", out)

    def test_a_missing_reason_is_not_a_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker(reason=None))

            out = self.run_check(repo).stdout

            self.assertIn("has not been adopted", out)
            self.assertIn("no reason", out)

    def test_a_deferral_without_a_date_cannot_age_and_is_not_a_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker(stamp=None))

            out = self.run_check(repo).stdout

            self.assertIn("has not been adopted", out)
            self.assertIn("date", out)

    def test_malformed_markers_are_reported_and_never_raise(self) -> None:
        cases = {
            "not-json": self.ROUTE + "\n<!-- execution-methodology: {not json} -->\n",
            "not-an-object": self.ROUTE + '\n<!-- execution-methodology: ["deferred"] -->\n',
            "wrong-mode": self.marker(mode="skipped"),
            "bad-date": self.marker(stamp="2026-13-99"),
            "two-markers": self.marker() + self.marker(reason="second"),
            "multiline": (self.ROUTE + '\n<!-- execution-methodology: {"mode":"deferred",\n'
                          '"reason":"x","date":"2026-01-15"} -->\n'),
        }
        for name, readme in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                repo = self.make_repo(Path(tmp), readme)

                out = self.run_check(repo).stdout

                self.assertIn("has not been adopted", out)
                self.assertNotIn("deliberately deferred", out)

    def test_a_repo_with_no_route_at_all_is_unadopted_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "bare"
            repo.mkdir()

            self.assertIn("has not been adopted", self.run_check(repo).stdout)

    def test_a_nonexistent_repo_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(Path(tmp) / "gone"),
                 "--adoption-check"],
                capture_output=True, text=True)

            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout, "")

    # the contract with the gate mode

    def test_adoption_check_does_not_change_the_check_mode(self) -> None:
        """--check remains the mode that fails a gate; --adoption-check must not soften it."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker())

            gate = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--check"],
                                  capture_output=True, text=True)

            self.assertEqual(gate.returncode, 1)
            self.assertIn("(missing)", gate.stdout)

    def test_the_check_never_writes_anything_into_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp), self.marker())
            before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))

            self.run_check(repo)

            self.assertEqual(before,
                             sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")))


# --- persona configuration ------------------------------------------------------------------------
# Adoption renders the methodology AND reports the repository's persona configuration, because doing
# only the first is what the fleet already did: measured over four repositories, a project's own
# domain validators are cited 100 times at review time, 5 times on a spec and 0 times on a PRD or a
# milestone, and spec_check's rule F reports `RULE F CHECKED NOTHING` in every one of them because no
# persona declares a `covers:`.
#
# THESE TESTS ARE WRITTEN AGAINST THE SHAPES THE REAL REPOSITORIES ACTUALLY WRITE, not against the
# shape that is easiest to assert. Seven checkers in this toolchain passed their own fixtures and
# were inert against the corpus; the last one matched a bare `T1` where the methodology tells authors
# to write `F-7/T1`. So one test below uses `docs/product/specs/<slug>/spec.md` — the layout one real
# repository uses for all 65 of its specs, and the layout rule F's path filter does not bind — and
# another applies the proposal this script prints and asserts the result is readable by the parser
# that has to read it. A proposal nobody can apply is the same defect wearing different clothes.

PERSONA_REL = Path("docs") / "agents" / "personas"

PERSONA = """---
name: {name}
description: Use when a change touches {name}'s territory.
{covers}writes: no
claude.model: opus
claude.tools: Read, Grep, Glob
codex.sandbox: read-only
---

You hold one invariant.
"""

HORIZONTALS = """# {title}

## Horizontals

| Concern | Disposition |
| --- | --- |
{rows}
"""


def persona(repo: Path, name: str, covers: str | None = None) -> Path:
    """One persona overlay in the repository's own pool, with or without a `covers:` key."""
    directory = repo / PERSONA_REL
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.md"
    line = f"covers: [{covers}]\n" if covers else ""
    path.write_text(PERSONA.format(name=name, covers=line), encoding="utf-8")
    return path


def product_doc(repo: Path, relative: str, rows: dict[str, str]) -> Path:
    """A product document carrying a `## Horizontals` table, at whatever path is asked for."""
    path = repo / "docs" / "product" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"| {label} | {disposition} |" for label, disposition in rows.items())
    path.write_text(HORIZONTALS.format(title=path.stem, rows=body), encoding="utf-8")
    return path


class PersonaConfigurationTest(unittest.TestCase):
    """Adopting the methodology in a repository also reports that repository's persona configuration."""

    def run_sync(self, repo: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), *extra],
                              capture_output=True, text=True)

    def make_repo(self, root: Path) -> Path:
        repo = root / "project"
        (repo / "docs" / "agents").mkdir(parents=True)
        (repo / "docs" / "agents" / "README.md").write_text(
            "| Lane | Read next |\n| --- | --- |\n"
            "| Executing a plan | [execution/methodology.md](execution/methodology.md) |\n",
            encoding="utf-8")
        return repo

    def test_a_repository_with_no_pool_is_told_so_plainly_and_is_not_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            result = self.run_sync(repo, "--check")
            self.assertIn("no docs/agents/personas/", result.stdout)
            self.assertIn("has not adopted persona overlays", result.stdout)
            # The render is what --check gates. A repository that never adopted overlays is in a
            # legitimate state, and the exit code must carry the render's verdict alone.
            self.assertNotIn("UNOWNED", result.stdout)

    def test_it_names_the_personas_and_which_of_them_declare_covers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "tenancy-validator", covers="tenancy")
            persona(repo, "money-validator")
            product_doc(repo, "specs/F-1-thing.md",
                        {"Tenancy / isolation": "per-tenant rows", "Money handling": "invoices"})
            out = self.run_sync(repo, "--check").stdout
            self.assertIn("2 persona(s) in docs/agents/personas/, 1 with `covers:`", out)
            self.assertIn("tenancy-validator", out)
            self.assertRegex(out, r"money-validator\s+-- declares no `covers:`")
            self.assertRegex(out, r"tenancy-validator\s+covers: tenancy")

    def test_it_names_the_concerns_nobody_owns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "tenancy-validator", covers="tenancy")
            product_doc(repo, "specs/F-1-thing.md",
                        {"Tenancy / isolation": "per-tenant rows",
                         "Money handling": "invoices",
                         "Audit trail": "every write"})
            out = self.run_sync(repo, "--check").stdout
            self.assertIn("2 of 3 live concern(s) owned by nobody", out)
            self.assertIn("UNOWNED  Money handling", out)
            self.assertIn("UNOWNED  Audit trail", out)
            self.assertNotIn("UNOWNED  Tenancy", out)

    def test_a_concern_declared_inapplicable_is_not_a_concern_nobody_owns(self) -> None:
        """`N/A — invites are free.` is a decision, not an unowned invariant.

        Measured: no row in the 805 real ones writes a bare `N/A`; all 45 real exemptions open with
        the declaration. Counting them would put 45 phantom invariants in front of a reader.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "tenancy-validator")
            product_doc(repo, "specs/F-1-thing.md",
                        {"Money handling": "N/A — this feature moves no money",
                         "Audit trail": "every write"})
            out = self.run_sync(repo, "--check").stdout
            self.assertIn("1 of 1 live concern(s) owned by nobody", out)
            self.assertIn("UNOWNED  Audit trail", out)
            self.assertNotIn("Money handling", out)

    def test_it_reads_the_carrier_where_a_real_repository_writes_it(self) -> None:
        """THE ANTI-INERTNESS TEST. One real repository writes every one of its 65 specs as
        `docs/product/specs/<slug>/spec.md`. Rule F binds documents by path — `specs/F-*.md`, the
        PRD, `milestones/M*.md` — so it binds NONE of them, and 545 live concern rows sit outside
        it. A configuration report that copied that path filter would tell that repository it has
        no concerns. So the scan reads the carrier wherever it is authored, AND says which rows rule
        F cannot reach, because telling someone to bind a persona that will never be demanded is
        the same silence with more words.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "plane-validator")
            product_doc(repo, "specs/c11-moderation/spec.md",
                        {"Tenancy / isolation": "one plane per credential"})
            out = self.run_sync(repo, "--check").stdout
            self.assertIn("UNOWNED  Tenancy / isolation", out)
            self.assertIn("(in no document rule F binds)", out)
            self.assertIn("1 of them appear only in documents rule F does not bind", out)

    def test_it_proposes_a_line_that_the_parser_which_must_read_it_can_read(self) -> None:
        """Apply the proposal exactly as printed, then check the binding is live.

        The proposal names a file and a line. If that line lands outside the front matter block,
        `read_persona_overlay` never sees it, the report keeps saying `declares no covers:`, and
        the advice is a loop. This applies it mechanically and re-runs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = persona(repo, "money-validator")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            out = self.run_sync(repo, "--check").stdout
            match = re.search(r"docs/agents/personas/money-validator\.md:(\d+)\s+insert before",
                              out)
            self.assertIsNotNone(match, f"no insertion point was proposed:\n{out}")
            lines = path.read_text(encoding="utf-8").splitlines()
            lines.insert(int(match.group(1)) - 1, "covers: [money handling]")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            after = self.run_sync(repo, "--check").stdout
            self.assertIn("1 with `covers:`", after)
            self.assertIn("every live concern in this product definition is owned by a persona",
                          after)

    def test_it_writes_nothing_into_a_persona(self) -> None:
        """Scripts here write nothing, and a `covers:` line is a judgement about which validator
        holds which invariant. A script that guesses it produces a binding nobody decided."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            path = persona(repo, "money-validator")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            before = path.read_bytes()
            for mode in (("--check",), ("--adoption-check",), ()):
                with self.subTest(mode=mode):
                    self.run_sync(repo, *mode)
                    self.assertEqual(before, path.read_bytes(),
                                     "the persona file changed; this script writes nothing")

    def test_adoption_check_reports_the_persona_state_and_still_exits_zero(self) -> None:
        """It is a state report. The methodology's own onboarding step says read the text, never
        the exit code, and a session hook that can fail is a session hook somebody removes."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "money-validator")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            # Render first, so the methodology half of the state is current and silent: what is
            # left is the persona half alone.
            self.assertEqual(0, self.run_sync(repo).returncode)
            result = self.run_sync(repo, "--adoption-check")
            self.assertEqual(0, result.returncode)
            self.assertIn("persona configuration is incomplete", result.stdout)
            self.assertIn("Money handling", result.stdout)
            self.assertIn("no persona here declares `covers:`", result.stdout)

    def test_adoption_check_stays_silent_when_there_is_nothing_to_configure(self) -> None:
        """Silence is the reward for a healthy repository, and a line printed at every session
        start in every repository it does not apply to is a line somebody mutes."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "money-validator", covers="money handling")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            self.assertEqual(0, self.run_sync(repo).returncode)
            result = self.run_sync(repo, "--adoption-check")
            self.assertEqual(0, result.returncode)
            self.assertEqual("", result.stdout.strip())

    def test_adoption_check_says_nothing_about_personas_when_there_is_no_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            self.assertEqual(0, self.run_sync(repo).returncode)
            result = self.run_sync(repo, "--adoption-check")
            self.assertEqual(0, result.returncode)
            self.assertEqual("", result.stdout.strip())

    def test_adoption_check_exits_zero_in_every_persona_state(self) -> None:
        states = ("none", "unbound", "bound", "unreadable")
        for state in states:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                repo = self.make_repo(Path(tmp))
                product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
                if state == "unbound":
                    persona(repo, "money-validator")
                elif state == "bound":
                    persona(repo, "money-validator", covers="money handling")
                elif state == "unreadable":
                    directory = repo / PERSONA_REL
                    directory.mkdir(parents=True, exist_ok=True)
                    (directory / "broken.md").write_text("no front matter here\n", encoding="utf-8")
                self.assertEqual(0, self.run_sync(repo, "--adoption-check").returncode)

    def test_a_persona_that_cannot_be_read_is_reported_not_skipped(self) -> None:
        """A pool half-read is how a rule goes inert while looking green."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            directory = repo / PERSONA_REL
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "broken.md").write_text("no front matter here\n", encoding="utf-8")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            out = self.run_sync(repo, "--check").stdout
            self.assertIn("broken", out)
            self.assertIn("unreadable", out)

    def test_the_persona_report_never_changes_the_exit_code(self) -> None:
        """`--check` gates the RENDER. spec_check's rule F already owns the binding, and one file
        answering to two checkers with two opinions is a thing this toolchain refuses on purpose."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "money-validator")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            self.assertEqual(0, self.run_sync(repo).returncode)
            checked = self.run_sync(repo, "--check")
            self.assertIn("UNOWNED  Money handling", checked.stdout)
            self.assertEqual(0, checked.returncode,
                             "an unowned concern failed the render gate; it is a decision to make, "
                             "not a drift to repair")

    def test_list_carries_the_persona_state_for_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(Path(tmp))
            persona(repo, "money-validator")
            product_doc(repo, "specs/F-1-thing.md", {"Money handling": "invoices"})
            result = self.run_sync(repo, "--list")
            self.assertEqual(0, result.returncode)
            self.assertIn("personas", result.stdout)
            self.assertIn("1 of 1 live concern(s) owned by nobody", result.stdout)


class ToolchainCarriesNoProjectIdentityTest(unittest.TestCase):
    """This skill directory is about to become its own repository.

    It serves private repositories and must carry nothing that identifies them — no registry of
    projects, no project name, no path that reaches one. A named project would be a leak; a *list*
    of projects would also be a design failure, because adoption is evaluated per repository against
    the repository the check is invoked on, never looked up centrally.

    The needles are assembled from fragments so that this file, which is itself scanned, does not
    trip its own check. Anything reaching a project has to go through the fleet root or an absolute
    home path, so those are what this forbids — generic enough to survive projects that do not
    exist yet.
    """

    FORBIDDEN = {
        "the fleet root, whose next path segment is always a project name":
            "Documents/" + "Claude/" + "Projects",
        "an absolute macOS home path, which names the machine's user":
            "/Us" + "ers/",
        "an absolute Linux home path":
            "/ho" + "me/",
        "a tilde path into the documents tree":
            "~/Doc" + "uments",
    }

    SCANNED = (".md", ".py", ".json", ".sh", ".txt", ".yaml", ".yml", ".toml", ".cfg")

    def test_no_file_in_the_skill_reaches_a_project(self) -> None:
        hits: list[str] = []
        for path in sorted(SKILL.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() not in self.SCANNED:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for why, needle in self.FORBIDDEN.items():
                if needle in text:
                    line = next((i for i, ln in enumerate(text.splitlines(), 1) if needle in ln), 0)
                    hits.append(f"{path.relative_to(SKILL).as_posix()}:{line} contains "
                                f"{needle!r} — {why}")
        self.assertEqual(hits, [], "\n".join(hits))

    def test_the_scan_actually_covers_this_skill(self) -> None:
        """A scan that silently matches nothing proves nothing."""
        scanned = [p for p in SKILL.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts
                   and p.suffix.lower() in self.SCANNED]
        self.assertGreaterEqual(len(scanned), 5, scanned)
        self.assertIn("methodology.md", [p.name for p in scanned])

    def test_the_needles_would_actually_fire(self) -> None:
        for why, needle in self.FORBIDDEN.items():
            with self.subTest(why=why):
                self.assertTrue(needle and needle in f"prefix{needle}suffix")


if __name__ == "__main__":
    unittest.main()
