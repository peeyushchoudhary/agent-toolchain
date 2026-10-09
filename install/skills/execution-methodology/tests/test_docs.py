"""Tests for docs.py: frontmatter lint, the generated index, `reads:` resolution.

Each case builds a throwaway repository (fixtures/goal_fixture.py) holding goal F-9, adds pages under
docs/ with frontmatter and the index in docs/README.md, and plants one defect lint or reads must name.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import SCRIPTS, Repo, plan_text  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
import docs  # noqa: E402

DOCS = SCRIPTS / "docs.py"


def page(summary="How the fixture is built.", when="changing the fixture", covers="[src/a/**, tests/test_a.py]",
         verified="2026-10-01"):
    keys = (("summary", summary), ("read-when", when), ("covers", covers), ("last-verified", verified))
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in keys if v is not None) + "---\n\n# A page\n\nBody.\n"


INDEX = ("| Page | Read when |\n|---|---|\n| [design.md](design.md) | changing the fixture |\n"
         "| [runbooks/run.md](runbooks/run.md) | running the fixture |\n")
README = f"# Documentation\n\nProse above the table.\n\n{INDEX}\nProse below, with a | pipe.\n"

RECORD = """# Record

## D17 — Zeta rule (v2)

Text.

### Detail

```
## not a heading
```

## D18: Other, thing!

Two.
"""


class DocsCase(unittest.TestCase):
    plan = None

    def setUp(self):
        self.repo = Repo(self.plan, files={"docs/record.md": RECORD})
        self.addCleanup(self.repo.cleanup)

    def docs(self, *args):
        return self.repo.run(DOCS, *args)

    def assertDocs(self, code, *args, texts=()):
        res = self.docs(*args)
        self.assertEqual(res.returncode, code, res.stdout + res.stderr)
        for text in texts:
            self.assertIn(text, res.stdout + res.stderr)
        return res.stdout


class LintTest(DocsCase):
    def setUp(self):
        super().setUp()
        self.repo.git("rm", "-q", "docs/record.md")
        self.repo.write("docs/design.md", page())
        self.repo.write("docs/runbooks/run.md", page(when="running the fixture", covers="[]"))
        self.repo.write("docs/README.md", README)
        self.repo.commit("docs with frontmatter")

    def lint_with(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit("plant")
        return self.docs("lint")

    def test_the_fixture_docs_lint_clean(self):
        self.assertDocs(0, "lint", texts=("docs.py lint: PASS",))

    def test_index_contract_with_surrounding_prose(self):
        self.assertEqual(self.assertDocs(0, "index"), INDEX)
        self.repo.write("docs/README.md", README.replace("Prose above", "Other prose above")
                        .replace("Prose below", "| not the table\n\nOther prose below"))
        self.repo.commit("prose changed around the table")
        self.assertDocs(0, "lint")

    def test_a_page_without_last_verified_fails(self):
        res = self.lint_with("docs/design.md", page(verified=None))
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("docs/design.md: no last-verified", res.stdout)
        res = self.lint_with("docs/design.md", page(verified="2026-13-01"))
        self.assertIn("docs/design.md: last-verified '2026-13-01' is not a YYYY-MM-DD date", res.stdout)

    def test_a_121_word_summary_fails(self):
        self.assertEqual(self.lint_with("docs/design.md", page(summary=" ".join(["word"] * 120))).returncode, 0)
        res = self.lint_with("docs/design.md", page(summary=" ".join(["word"] * 121)))
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("docs/design.md: summary is 121 words, over 120", res.stdout)

    def test_an_index_missing_a_row_fails(self):
        res = self.lint_with("docs/runbooks/new.md", page(when="adding a page"))
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("docs/README.md: index lacks | [runbooks/new.md](runbooks/new.md) | adding a page |", res.stdout)

    def test_a_covers_glob_that_escapes_the_repository_fails(self):
        res = self.lint_with("docs/design.md", page(covers="[src/**, ../outside/**, /etc/**, src/../../x]"))
        self.assertEqual(res.returncode, 1, res.stdout)
        for bad in ("../outside/**", "/etc/**", "src/../../x"):
            self.assertIn(f"docs/design.md: covers entry '{bad}' is not repository-relative", res.stdout)
        self.assertNotIn("'src/**'", res.stdout)

    def test_an_unreadable_root_exits_2(self):
        outside = Path(tempfile.mkdtemp(prefix="docsfx-"))
        self.addCleanup(shutil.rmtree, outside, True)
        self.assertDocs(2, "lint", str(outside))
        self.assertDocs(2, "index", str(outside / "missing"))


class ReadsTest(DocsCase):
    plan = (plan_text()
            .replace("writes: src/a/**, tests/**\n", "writes: src/a/**, tests/**\nreads: docs/record.md#d17--zeta-rule-v2, "
                     "docs/record.md#detail, docs/record.md#D18, docs/record.md#d18-other-thing, docs/design.md, fixture\n")
            .replace("writes: src/c/**\n", "writes: src/c/**\nreads: docs/record.md#nope, docs/missing.md, "
                     "docs/missing.md#d17, docs/design.md\n"))

    def test_a_reads_line_with_all_three_entry_kinds(self):
        out = self.assertDocs(0, "reads", "T1", "--goal", "F-9")
        self.assertEqual(out.splitlines(), ["docs/record.md:3-12", "docs/record.md:7-12", "docs/record.md:13-15",
                                            "docs/record.md:13-15", "docs/design.md", "term: fixture"])

    def test_a_heading_with_punctuation_resolves_by_slug_and_by_dnn(self):
        self.assertEqual(docs.slug("D18: Other, thing!"), "d18-other-thing")
        self.assertEqual(docs.resolve(self.repo.dir, "docs/record.md#d18-other-thing"), (True, "docs/record.md:13-15"))
        self.assertEqual(docs.resolve(self.repo.dir, "docs/record.md#d18"), (True, "docs/record.md:13-15"))
        self.assertEqual(docs.resolve(self.repo.dir, "docs/record.md#d1")[0], False)

    def test_an_anchor_that_does_not_exist_fails(self):
        out = self.assertDocs(1, "reads", "T3", "--goal", "F-9")
        self.assertEqual(out.splitlines(), ["error: docs/record.md#nope: no heading matches #nope",
                                            "error: docs/missing.md: no such file",
                                            "error: docs/missing.md#d17: no such file", "docs/design.md"])

    def test_no_such_task_or_goal_exits_2(self):
        self.assertDocs(2, "reads", "T9", "--goal", "F-9", texts=("no task T9",))
        self.assertDocs(2, "reads", "T1", "--goal", "F-0", texts=("plan not found",))


if __name__ == "__main__":
    unittest.main()
