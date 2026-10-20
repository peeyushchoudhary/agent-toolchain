"""Behaviour-level facts about the skill's prose: the files exist, what they name exists, nothing
retired is named, the reviewer and the scout cannot edit, and each reference and agent body stays
within its word ceiling.

No prose is pinned here; the always-loaded ceiling is install/tests/test_size.py.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[2]
ENTRY = SKILL / "SKILL.md"
BUILDER = SKILL / "agents" / "builder.md"
REVIEWER = SKILL / "agents" / "reviewer.md"
SCOUT = SKILL / "agents" / "scout.md"
DESIGN = SKILL / "references" / "design.md"
PLANNING = SKILL / "references" / "planning.md"
ROLES = SKILL / "references" / "roles.md"
SECURITY = SKILL / "references" / "security-checklist.md"
CLOSE = SKILL / "references" / "close.md"
MODULES = SKILL / "references" / "modules.md"
MIGRATIONS = SKILL / "references" / "test-migrations.md"
REPOSITORY = SKILL / "references" / "repository.md"
BUILDER_TOML = SKILL / "agents" / "builder.toml"
ALWAYS_LOADED = (REPO / "install" / "global.md", REPO / "AGENTS.md", ENTRY)
SKILL_FILES = (ENTRY, BUILDER, REVIEWER, SCOUT, DESIGN, PLANNING, ROLES, SECURITY, CLOSE, MODULES, REPOSITORY, MIGRATIONS)

# Word ceilings of the on-demand references (D30); words are whitespace-separated tokens.
REFERENCE_WORDS = {PLANNING: 400, ROLES: 150, SECURITY: 150, CLOSE: 400, MODULES: 200, REPOSITORY: 900, MIGRATIONS: 400}
PLANNING_RULES_WORDS = 200
# Word ceilings of the agent files' bodies, the text after the closing frontmatter line (D30).
AGENT_BODY_WORDS = {BUILDER: 400, REVIEWER: 350, SCOUT: 200}

# Named by the rules, delivered by a later task of the same goal. Anything else must exist.
NOT_YET_BUILT = frozenset()

# Machinery the v7 shape removed (D29), and the launcher and Stop hook v7.1 removed (D30). The rules must not send a session to any of it.
RETIRED = ("execution-methodology/methodology.md", "references/run.md",
           "references/migrate.md", "agent-personas", "sync_personas", "review.py", "run_goal",
           "goal-session", "graphify", "graph-navigation", "progressive-disclosure",
           "validate_disclosure", "check_github", "install_hooks", "identifier_guard", "push_guard",
           "preflight", "goal.py guard", "goal.py attempt", "goal.py evidence", "goal.py start",
           "run.sh", "stop-hook")

LINK = re.compile(r"\]\(([^)\s]+)\)")
SKILL_PATH = re.compile(r"(?<![\w/.-])((?:scripts|references|agents)/[\w.-]+\.(?:py|md|sh))")


def named_paths(path: Path, text: str | None = None) -> list[tuple[str, Path]]:
    """(label, resolved path) for every relative link and skill-relative path a file names."""
    text = path.read_text(encoding="utf-8") if text is None else text
    out = []
    for target in LINK.findall(text):
        target = target.split("#", 1)[0]
        if target and not re.match(r"^[a-z]+:", target):
            resolved = (path.parent / target).resolve()
            label = resolved.relative_to(SKILL).as_posix() if SKILL in resolved.parents else target
            out.append((label, resolved))
    return out + [(m, SKILL / m) for m in SKILL_PATH.findall(text)]


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = lines.index("---", 1)
    return dict(l.split(":", 1) for l in lines[1:end] if ":" in l)


class FilesAndNames(unittest.TestCase):
    def test_the_always_loaded_files_and_the_skill_files_exist(self):
        for path in ALWAYS_LOADED + SKILL_FILES:
            self.assertTrue(path.is_file(), path)

    def test_every_path_the_skill_names_resolves(self):
        for path in SKILL_FILES:
            for label, resolved in named_paths(path):
                with self.subTest(file=path.name, named=label):
                    self.assertTrue(resolved.exists() or label in NOT_YET_BUILT,
                                    f"{path.name} names {label}, which does not exist")

    def test_the_entry_links_the_reviewer_and_the_design_page(self):
        linked = {resolved for _label, resolved in named_paths(ENTRY)}
        self.assertLessEqual({REVIEWER.resolve(), DESIGN.resolve()}, linked)

    def test_the_path_detector_sees_a_missing_path(self):
        # Guard the guard: a file naming a missing path must be reported, not skipped.
        text = "[x](does-not-exist.md), [ok](design.md) and `scripts/nope.py`\n"
        missing = [label for label, resolved in named_paths(DESIGN, text) if not resolved.exists()]
        self.assertEqual(sorted(missing), ["references/does-not-exist.md", "scripts/nope.py"])

    def test_current_instructions_use_existing_session_resume(self):
        # AC12: the founder's open session resumes a goal; nothing a session loads first, nor the Codex
        # runbook's summary, names a launcher or a Stop hook as current.
        self.assertIn("goal.py resume", ENTRY.read_text(encoding="utf-8"))
        runbook = REPO / "docs" / "runbooks" / "codex.md"
        texts = [(p, p.read_text(encoding="utf-8")) for p in ALWAYS_LOADED + SKILL_FILES]
        texts.append((runbook, runbook.read_text(encoding="utf-8").split("---", 2)[1]))
        for path, text in texts:
            for name in ("run.sh", "Stop hook", "stop-hook"):
                with self.subTest(file=path.name, named=name):
                    self.assertNotIn(name, text)

    def test_the_design_review_judges_against_the_spec(self):
        review = DESIGN.read_text(encoding="utf-8").split("## Design review", 1)[1]
        self.assertIn("`spec.md`", review)

    def test_the_builder_may_change_the_tests_the_plan_lists(self):
        text = BUILDER.read_text(encoding="utf-8")
        self.assertNotIn("leave every other test as it is", text)
        self.assertIn("change another test only where `tests-may-change` lists it", text)

    def test_no_always_loaded_or_skill_file_names_retired_machinery(self):
        for path in ALWAYS_LOADED + SKILL_FILES:
            text = path.read_text(encoding="utf-8")
            for name in RETIRED:
                with self.subTest(file=path.name, retired=name):
                    self.assertIsNone(re.search(r"(?<![\w-])" + re.escape(name), text),
                                      f"{path.name} names retired {name}")


class EntryPoint(unittest.TestCase):
    def test_direct_execution_includes_loop_tests(self):
        run = subprocess.run([sys.executable, __file__, "-v", "Loop"], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("test_the_loop_runs_the_tasks_gate", run.stderr)


class Frontmatter(unittest.TestCase):
    def test_the_skill_is_model_invocable_in_both_harnesses(self):
        # D31 reversed the 2026-08-22 user-invoked gate: the approval tag is the human gate, so the
        # session loads the skill itself. Neither harness's opt-out may come back.
        meta = frontmatter(ENTRY)
        self.assertEqual(meta.get("name", "").strip(), "execution-methodology")
        self.assertTrue(meta.get("description", "").strip())
        self.assertNotIn("disable-model-invocation", meta)
        self.assertFalse((SKILL / "agents" / "openai.yaml").exists(), "Codex's allow_implicit_invocation sidecar")

    def test_roles_agent_files_and_goal_review_name_the_same_reviewer_models(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        import goal
        roles = ROLES.read_text(encoding="utf-8")
        row = next(l for l in roles.splitlines() if l.startswith("| Reviewer"))
        self.assertEqual(goal.REVIEWERS["codex"][1:], (frontmatter(REVIEWER)["model"].strip(),
                                                       frontmatter(REVIEWER)["effort"].strip()))
        for chief, (cli, model, effort) in goal.REVIEWERS.items():
            with self.subTest(chief=chief):
                self.assertIn(f"`{model}`", row)
                self.assertIn(f"when {chief.capitalize()} is chief", row.split(f"`{model}`", 1)[1].split("|")[0])
                self.assertIn(f"`{effort}`", row)

    def test_the_reviewer_and_the_scout_are_read_only(self):
        for path in (REVIEWER, SCOUT):
            with self.subTest(file=path.name):
                tools = {t.strip() for t in frontmatter(path).get("tools", "").split(",") if t.strip()}
                self.assertTrue(tools)
                self.assertLessEqual(tools, {"Read", "Grep", "Glob"}, tools)


class Budgets(unittest.TestCase):
    def test_each_reference_is_within_its_word_ceiling(self):
        for path, ceiling in REFERENCE_WORDS.items():
            with self.subTest(file=path.name):
                self.assertLessEqual(len(path.read_text(encoding="utf-8").split()), ceiling)

    def test_each_agent_body_is_within_its_word_ceiling(self):
        for path, ceiling in AGENT_BODY_WORDS.items():
            with self.subTest(file=path.name):
                lines = path.read_text(encoding="utf-8").splitlines()
                body = lines[lines.index("---", 1) + 1:]
                self.assertLessEqual(len(" ".join(body).split()), ceiling)

    def test_the_chiefs_planning_rules_are_within_their_word_ceiling(self):
        text = PLANNING.read_text(encoding="utf-8")
        rules = re.search(r"^## Chief's planning rules\n(.*?)(?=^## )", text, re.M | re.S)
        self.assertIsNotNone(rules, "planning.md has no ## Chief's planning rules section")
        self.assertLessEqual(len(rules.group(1).split()), PLANNING_RULES_WORDS)



def loop_step(n: int) -> str:
    """The text of step n of the entry's per-task loop, continuation lines included."""
    loop = ENTRY.read_text(encoding="utf-8").split("## The loop, per task", 1)[1].split("\n## ", 1)[0]
    m = re.search(rf"^{n}\. (.*?)(?=^\d+\. |\Z)", loop, re.M | re.S)
    return " ".join(m.group(1).split()) if m else ""


class Loop(unittest.TestCase):
    """v7.2 (D32): each task's own gate, the full-gate cadence, dispatch by dependency."""

    def test_the_loop_runs_the_tasks_gate(self):
        self.assertIn("the task's gate", loop_step(5))

    def test_step_5_names_the_modules_next_derives(self):
        # v7.3 (D33): a task without a gate: line runs the modules goal.py next derives from the map.
        step = loop_step(5)
        for words in ("`gate:`", "the modules `goal.py next` names", "--modules", "the plan's"):
            self.assertIn(words, step)

    def test_the_full_gate_runs_every_third_task_and_a_due_sample_waits(self):
        step = loop_step(8)
        for words in ("every third task commit", "newest", "600 s", "only at close"):
            self.assertIn(words, step)

    def test_background_gate_worktree_is_removed_when_run_finishes(self):
        self.assertIn("remove that worktree when the run ends", loop_step(8))

    def test_at_most_four_builders_run_at_once(self):
        self.assertIn("four builders", loop_step(3))

    def test_dispatch_waits_for_committed_dependencies(self):
        step = loop_step(3)
        self.assertIn("needs", step)
        self.assertIn("committed", step)

    def test_the_chief_applies_only_to_a_clean_checkout(self):
        step = loop_step(4)
        self.assertIn("clean", step)
        self.assertIn("apply", step)

    def test_both_builder_files_check_their_worktree(self):
        for path in (BUILDER, BUILDER_TOML):
            with self.subTest(file=path.name):
                text = " ".join(path.read_text(encoding="utf-8").split())
                self.assertIn("merge-base --is-ancestor", text)
                self.assertIn("the chief's checkout", text)
        self.assertEqual(frontmatter(BUILDER).get("isolation", "").strip(), "worktree")


def flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class Close(unittest.TestCase):
    """v7.3 (D33): the composed full gate at close, and the one retry of a failed module."""

    def test_close_names_migration_proofs(self):
        text = flat(CLOSE)
        self.assertIn(MIGRATIONS.resolve(), {resolved for _label, resolved in named_paths(CLOSE)})
        for words in ("goal.py migration-proofs --goal <id>", "--count none", "full_gate", "e2e",
                      "merge review", "goal.py done"):
            self.assertIn(words, text)
        self.assertLess(text.index("goal.py migration-proofs"), text.index("goal.py done"))

    def test_close_composes_the_full_gate_from_modules_and_states_the_retry(self):
        text = flat(CLOSE)
        for words in ("`full_gate: modules`", "receipt --goal <id> --modules all", "keeps passed modules",
                      "retries a failed one once", "second failure needs a fix commit"):
            self.assertIn(words, text)

    def test_close_merges_tags_the_head_then_cleans_up(self):
        # S-8 (D34), AC7: merge, tag the PR's head, push the tag, then remove what origin/main holds.
        text = flat(CLOSE)
        at = 0
        for words in ("goal.py done", "`gh pr merge <n> --merge`", "`git tag goal/<id>/<milestone> <head>`",
                      "`git push --atomic origin goal/<id>/approved goal/<id>/<milestone>`",
                      "`goal.py cleanup --goal <id> --apply`"):
            found = text.find(words, at)
            self.assertGreaterEqual(found, 0, f"{words} missing or out of order")
            at = found + len(words)
        sentence = next((s for s in re.split(r"(?<=\.) ", text) if "`--delete-branch`" in s), "")
        self.assertIn("only when the milestone is the goal's last", sentence)

    def test_close_handles_reapproval_after_published_approval(self):
        # S-9 merge review R1: a re-approval that moved a pushed approval tag pushes it with a lease,
        # atomically with the milestone tag, so the remote is never left half closed.
        step = next(s for s in re.split(r"(?=\b\d\. )", flat(CLOSE)) if s.startswith("3. "))
        for words in ("--atomic", "re-approval moved", "--force-with-lease=refs/tags/goal/<id>/approved:<sha>",
                      "git ls-remote", "both tags go, or neither"):
            self.assertIn(words, step)

    def test_the_loop_records_builder_and_sample_worktrees(self):
        # S-8 (D34), AC7: every worktree the chief makes is recorded, so cleanup may remove it.
        self.assertIn("goal.py own --goal <id> <path>", loop_step(3))
        self.assertIn("goal.py own", loop_step(8))

    def test_the_loop_removes_the_builders_worktree_and_branch(self):
        # S-9, AC4: the chief removes a builder's branch with its worktree.
        self.assertIn("remove its worktree and branch after the commit", loop_step(4))


class Planning(unittest.TestCase):
    """v7.3 (D33), AC8: the planner drafts the module map with the plan, by references/modules.md."""

    def test_planning_drafts_the_map_with_the_plan(self):
        self.assertIn(MODULES.resolve(), {resolved for _label, resolved in named_paths(PLANNING)})
        self.assertIn("committed with the plan", flat(PLANNING))
        text = flat(MODULES)
        for words in ("`docs/goals/modules.json`", "build files", "`replaces`", '`count: "none"`',
                      "tests switched off", "Commit it with the plan", "--modules all", "gate.py coverage",
                      "`full_gate: modules`", "Decisions line naming the module that runs each non-test check",
                      "Prefer derived gates"):
            self.assertIn(words, text)

    def test_frozen_test_migration_contract_is_explicit(self):
        for path in (ENTRY, PLANNING, MODULES, CLOSE):
            with self.subTest(file=path.name):
                self.assertIn(MIGRATIONS.resolve(), {resolved for _label, resolved in named_paths(path)})
        text = flat(MIGRATIONS)
        for words in ("test-migrations.json", "version", "originals", "sha256", "successors",
                      "historical_claim", "BYTES_ONLY", "reason", "python3", "./py",
                      "-m pytest -q", "-m unittest", "retained", "approval", "protected",
                      "third command", "count", "needs", "shared", "replaces",
                      "goal.py migration-proofs --goal <id>", "--modules <module>",
                      "--cmd <exact command>", "--count none", "receipt", "positive",
                      "zero failed/skipped", "baseline", "HEAD", "goal-scoped",
                      "re-approval", "replay", "semantic equivalence", "full/E2E", "review"):
            with self.subTest(required=words):
                self.assertIn(words, text)


def sentence(path: Path, words: str) -> str:
    """The first sentence of path, its lines joined, that holds words."""
    return next((s for s in re.split(r"(?<=\.) ", flat(path)) if words in s), "")


class Repository(unittest.TestCase):
    """S-10, AC5: the repository rules every repository follows ship as references/repository.md."""

    def test_the_reference_carries_the_readme_layout_and_lifecycle(self):
        text = REPOSITORY.read_text(encoding="utf-8")
        for heading in ("## The README", "## Layout", "## Agent files", "## Lifecycle"):
            self.assertIn(heading, text.splitlines())
        self.assertLessEqual(len(text.split()), 900)
        self.assertIn("`git grep`", text)

    def test_repository_rules_preserve_required_generated_pointers(self):
        self.assertIn("pointer files", sentence(REPOSITORY, "Generated files a gate checks"))

    def test_naming_rule_allows_required_interface_filenames(self):
        rule = sentence(REPOSITORY, "lowercase")
        for words in ("`AGENTS.md`", "`CLAUDE.md`", "`README.md`", "keep their spelling"):
            self.assertIn(words, rule)

    def test_module_rule_preserves_non_test_gate_modules(self):
        self.assertIn(MODULES.resolve(), {resolved for _label, resolved in named_paths(REPOSITORY)})
        self.assertNotIn("selector", REPOSITORY.read_text(encoding="utf-8"))

    def test_lessons_record_can_retain_retired_component_rationale(self):
        self.assertIn("may name removed components", sentence(REPOSITORY, "`docs/agents/lessons.md`"))


if __name__ == "__main__":
    unittest.main()
