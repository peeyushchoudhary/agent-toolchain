"""`stale-guide`: an area guide behind its folder's non-doc commits is a WARN, nothing more.

Every case builds a temporary git repository and a temporary HOME, and runs the real CLI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate_disclosure.py"
ROOT_ENTRY = "# Contract\n\nRoute: [index](docs/agents/README.md)\n"
INDEX = '# Index\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n'


class Repo:
    def __init__(self, case: unittest.TestCase, *, git: bool = True, commit_root: bool = True):
        self.case = case
        self.is_git = git
        self.root = Path(tempfile.mkdtemp(prefix="pd-stale-")).resolve()
        self.home = Path(tempfile.mkdtemp(prefix="pd-stale-home-"))
        case.addCleanup(shutil.rmtree, self.root, True)
        case.addCleanup(shutil.rmtree, self.home, True)
        self.env = {**os.environ, "HOME": str(self.home), "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull, "PYTHONDONTWRITEBYTECODE": "1",
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        self.write("AGENTS.md", ROOT_ENTRY)
        self.write("docs/agents/README.md", INDEX)
        if git:
            self.git("init", "-q")
            if commit_root:
                self.commit("root")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd or self.root, env=self.env,
                           capture_output=True, text=True)
        self.case.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, rel: str, text: str = "x\n") -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, msg: str, *paths: str) -> None:
        self.git("add", "-A", *paths)
        self.git("commit", "-q", "-m", msg, "--allow-empty")

    def area(self, folder: str = "src", guide: str = "guide.md") -> None:
        self.write(f"{folder}/AGENTS.md", f"# Area\n\n[guide]({guide})\n")
        self.write(f"{folder}/{guide}", "# Guide\n")
        self.write(f"{folder}/code.py", "a = 1\n")
        if self.is_git:
            self.commit("area")

    def run(self, *flags: str, root: Path | None = None) -> tuple[int, str]:
        p = subprocess.run([sys.executable, str(VALIDATOR), str(root or self.root), *flags],
                           capture_output=True, text=True, env=self.env, timeout=120)
        return p.returncode, p.stdout + p.stderr


def stale_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if "[stale-guide]" in ln]


class StaleGuideTest(unittest.TestCase):
    def test_guide_behind_code_warns_with_count(self):
        r = Repo(self)
        r.area()
        r.write("src/code.py", "a = 2\n"); r.commit("c1")
        r.write("src/code.py", "a = 3\n"); r.commit("c2")
        rc, out = r.run()
        lines = stale_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("src/guide.md", lines[0])
        self.assertIn("2 commit(s) to src since the guide last changed", lines[0])
        self.assertIn("WARN", lines[0])

    def test_warn_never_changes_the_exit_code(self):
        r = Repo(self)
        r.area()
        _, before = r.run()
        rc0, _ = r.run()
        r.write("src/code.py", "a = 2\n"); r.commit("c1")
        rc, out = r.run()
        self.assertEqual(len(stale_lines(out)), 1, out)
        self.assertEqual(rc, rc0)
        self.assertNotIn("ERROR", "\n".join(stale_lines(out)))
        rc_hook, hook_out = r.run("--hook")
        self.assertEqual(rc_hook, rc0)
        self.assertIn("WARN [stale-guide]", hook_out)

    def test_guide_updated_after_code_is_silent(self):
        r = Repo(self)
        r.area()
        r.write("src/code.py", "a = 2\n"); r.commit("c1")
        r.write("src/guide.md", "# Guide v2\n"); r.commit("guide")
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_doc_only_commits_are_silent(self):
        r = Repo(self)
        r.area()
        r.write("src/notes.md", "n\n"); r.write("src/deep/more.md", "m\n"); r.commit("docs")
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_non_md_doc_file_counts_as_code(self):
        r = Repo(self)
        r.area()
        r.write("src/notes.txt", "n\n"); r.commit("txt")
        self.assertEqual(len(stale_lines(r.run()[1])), 1)

    def test_commit_mixing_md_and_code_counts_once(self):
        r = Repo(self)
        r.area()
        r.write("src/notes.md", "n\n"); r.write("src/code.py", "a = 9\n"); r.commit("mixed")
        self.assertIn("1 commit(s)", stale_lines(r.run()[1])[0])

    def test_commits_elsewhere_are_not_counted(self):
        r = Repo(self)
        r.area()
        r.write("other/code.py", "b\n"); r.commit("elsewhere")
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_uncommitted_guide_is_skipped(self):
        r = Repo(self)
        r.write("src/AGENTS.md", "# Area\n\n[guide](guide.md)\n")
        r.write("src/code.py", "a\n"); r.commit("code")
        r.write("src/guide.md", "# Guide\n")
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_outside_a_git_repository_is_skipped(self):
        r = Repo(self, git=False)
        r.area()
        rc, out = r.run()
        self.assertEqual(stale_lines(out), [])
        self.assertNotIn("Traceback", out)

    def test_repository_with_no_commits_is_skipped(self):
        r = Repo(self, commit_root=False)
        r.write("src/AGENTS.md", "# Area\n\n[guide](guide.md)\n")
        r.write("src/guide.md", "# Guide\n"); r.write("src/code.py", "a\n")
        rc, out = r.run()
        self.assertEqual(stale_lines(out), [])
        self.assertNotIn("Traceback", out)

    def test_guide_linked_from_two_entry_files_in_one_folder_warns_once(self):
        r = Repo(self)
        r.area()
        r.write("src/CLAUDE.md", "# Area\n\n[guide](guide.md)\n"); r.commit("claude")
        r.write("src/guide.md", "# Guide v2\n"); r.commit("guide")
        r.write("src/code.py", "a = 2\n"); r.commit("c1")
        self.assertEqual(len(stale_lines(r.run()[1])), 1)

    def test_guide_linked_from_two_folders_warns_once_per_folder_that_contains_it(self):
        # `src/AGENTS.md` and `src/sub/AGENTS.md` both link `src/sub/guide.md`: it lies under both,
        # so each folder's own commit count is its own finding (stated behaviour: one per entry
        # folder). A folder that does not contain the guide gets none.
        r = Repo(self)
        r.write("src/AGENTS.md", "# A\n\n[g](sub/guide.md)\n")
        r.write("src/sub/AGENTS.md", "# B\n\n[g](guide.md)\n")
        r.write("src/sub/guide.md", "# G\n"); r.write("src/top.py", "t\n"); r.commit("all")
        r.write("src/top.py", "t2\n"); r.commit("top")
        out = stale_lines(r.run()[1])
        self.assertEqual(len(out), 1, out)
        self.assertIn("1 commit(s) to src ", out[0])
        r.write("src/sub/code.py", "c\n"); r.commit("sub")
        self.assertEqual(len(stale_lines(r.run()[1])), 2)

    def test_guide_outside_the_folder_is_not_an_area_guide(self):
        r = Repo(self)
        r.write("docs/shared.md", "# Shared\n")
        r.write("src/AGENTS.md", "# Area\n\n[shared](../docs/shared.md)\n")
        r.write("src/code.py", "a\n"); r.commit("all")
        r.write("src/code.py", "b\n"); r.commit("c1")
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_folder_with_spaces_in_its_path(self):
        r = Repo(self)
        r.area("my area")
        r.write("my area/code.py", "a = 2\n"); r.commit("c1")
        out = stale_lines(r.run()[1])
        self.assertEqual(len(out), 1, out)
        self.assertIn("my area/guide.md", out[0])

    def test_guide_link_with_a_space_is_not_parsed_as_a_link(self):
        # MD_LINK takes no whitespace in a target, so a spaced guide filename is never linked and
        # `stale-guide` cannot see it; the existing route checks are unchanged by that.
        r = Repo(self)
        r.write("src/AGENTS.md", "# Area\n\n[g](<my guide.md>)\n")
        r.write("src/my guide.md", "# G\n"); r.write("src/code.py", "a\n"); r.commit("all")
        r.write("src/code.py", "b\n"); r.commit("c1")
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_renamed_guide_uses_the_rename_commit(self):
        r = Repo(self)
        r.area()
        r.write("src/code.py", "a = 2\n"); r.commit("c1")
        r.git("mv", "src/guide.md", "src/area-guide.md")
        r.write("src/AGENTS.md", "# Area\n\n[guide](area-guide.md)\n"); r.commit("rename")
        r.write("src/code.py", "a = 3\n"); r.commit("c2")
        out = stale_lines(r.run()[1])
        self.assertEqual(len(out), 1, out)
        self.assertIn("src/area-guide.md", out[0])
        self.assertIn("1 commit(s)", out[0])

    def test_shallow_clone_does_not_crash(self):
        r = Repo(self)
        r.area()
        for i in range(3):
            r.write("src/code.py", f"a = {i + 5}\n"); r.commit(f"c{i}")
        clone = Path(tempfile.mkdtemp(prefix="pd-stale-clone-")) / "c"
        self.addCleanup(shutil.rmtree, clone.parent, True)
        r.git("clone", "-q", "--depth", "1", r.root.as_uri(), str(clone), cwd=r.home)
        rc, out = r.run(root=clone)
        self.assertNotIn("Traceback", out)
        self.assertLessEqual(len(stale_lines(out)), 1)

    def test_unreachable_last_commit_is_skipped(self):
        r = Repo(self)
        r.area()
        r.write("src/code.py", "a = 2\n"); r.commit("c1")
        sha = r.git("log", "-1", "--format=%H", "--", "src/guide.md").strip()
        objects = r.root / ".git" / "objects" / sha[:2] / sha[2:]
        os.chmod(objects, 0o644)
        objects.unlink()
        rc, out = r.run()
        self.assertEqual(stale_lines(out), [])
        self.assertNotIn("Traceback", out)

    def test_linked_worktree(self):
        r = Repo(self)
        r.area()
        wt = Path(tempfile.mkdtemp(prefix="pd-stale-wt-")) / "wt"
        self.addCleanup(shutil.rmtree, wt.parent, True)
        r.git("worktree", "add", "-q", "-b", "side", str(wt))
        (wt / "src" / "code.py").write_text("a = 2\n")
        r.git("add", "-A", cwd=wt)
        r.git("commit", "-q", "-m", "wt change", cwd=wt)
        out = stale_lines(r.run(root=wt)[1])
        self.assertEqual(len(out), 1, out)
        self.assertEqual(stale_lines(r.run()[1]), [])

    def test_root_entry_file_is_not_scoped(self):
        # `D` as the repository root: only scoped entry files are checked, so a guide linked from
        # the root contract never warns, however many commits the repository has.
        r = Repo(self)
        r.write("AGENTS.md", ROOT_ENTRY + "[g](docs/agents/README.md)\n")
        r.commit("root")
        r.write("lib.py", "x\n"); r.commit("code")
        self.assertEqual(stale_lines(r.run()[1]), [])


if __name__ == "__main__":
    unittest.main()
