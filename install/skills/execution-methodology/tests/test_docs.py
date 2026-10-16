"""Tests for docs.py: frontmatter lint, the generated index, `reads:` resolution, pointers, staleness.

Each case builds a throwaway repository (fixtures/goal_fixture.py) holding goal F-9, adds pages under
docs/ with frontmatter and the index in docs/README.md, and plants one defect lint, reads, pointers
or stale must name.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures.goal_fixture import SCRIPTS, Repo, env, plan_text  # noqa: E402

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
        self.assertDocs(0, "pointers")
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

    def test_mapping_metadata_fails_lint(self):
        res = self.lint_with("docs/design.md", page(summary="{a: b}", when="{c: d}", verified="{value: invalid}"))
        self.assertEqual(res.returncode, 1, res.stdout)
        for key in ("summary", "read-when", "last-verified"):
            self.assertIn(f"docs/design.md: {key} is not one line", res.stdout)

    def test_an_unreadable_root_exits_2(self):
        outside = Path(tempfile.mkdtemp(prefix="docsfx-"))
        self.addCleanup(shutil.rmtree, outside, True)
        self.assertDocs(2, "lint", str(outside))
        self.assertDocs(2, "index", str(outside / "missing"))

    def test_install_rollout_with_an_existing_claude_page(self):
        row = "|---|---|\n| [CLAUDE.md](CLAUDE.md) | changing the agent files |\n"
        self.repo.write("docs/CLAUDE.md", page(when="changing the agent files", covers="[]"))
        res = self.lint_with("docs/README.md", README.replace("|---|---|\n", row))
        self.assertEqual(res.returncode, 0, res.stdout)
        self.repo.write("docs/CLAUDE.md", "@AGENTS.md\n")
        res = self.lint_with("docs/README.md", README)
        self.assertEqual(res.returncode, 0, res.stdout)


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

    def test_extensionless_file_resolves_as_path(self):
        self.repo.write("Makefile", "all:\n")
        self.assertEqual(docs.resolve(self.repo.dir, "Makefile"), (True, "Makefile"))
        self.assertEqual(docs.resolve(self.repo.dir, "fixture"), (True, "term: fixture"))

    def test_duplicate_heading_anchor_resolves(self):
        self.repo.write("docs/dup.md", "# D\n\n## Examples\n\nOne.\n\n## Examples\n\nTwo.\n")
        self.assertEqual(docs.resolve(self.repo.dir, "docs/dup.md#examples"), (True, "docs/dup.md:3-6"))
        self.assertEqual(docs.resolve(self.repo.dir, "docs/dup.md#examples-1"), (True, "docs/dup.md:7-9"))

    def test_fenced_heading_does_not_end_range(self):
        self.repo.write("docs/tilde.md", "# T\n\n## Interfaces\n\nOne.\n\n~~~\n## Example\n~~~\n\n"
                        "Contract text.\n\n## Data touched\n\nTwo.\n")
        self.assertEqual(docs.resolve(self.repo.dir, "docs/tilde.md#interfaces"), (True, "docs/tilde.md:3-12"))

    def test_no_such_task_or_goal_exits_2(self):
        self.assertDocs(2, "reads", "T9", "--goal", "F-9", texts=("no task T9",))
        self.assertDocs(2, "reads", "T1", "--goal", "F-0", texts=("plan not found",))


class LinksTest(DocsCase):
    def links_with(self, readme, **files):
        for rel, text in {"README.md": readme, **files}.items():
            self.repo.write(rel, text)
        self.repo.commit("links")
        return self.docs("links")

    def test_links_anchors_and_twins_pass(self):
        self.repo.write("AGENTS.md", "root\n")
        self.repo.write("CLAUDE.md", "@AGENTS.md\n")
        res = self.links_with("[a](docs/record.md#d17--zeta-rule-v2)\n[b](docs/record.md#d18-other-thing)\n"
                              "[c](docs/record.md#detail)\n[d](<docs/record.md>)\n[e](docs/record.md \"Title\")\n"
                              "![f](docs/record.md)\n")
        self.assertEqual((res.returncode, res.stdout), (0, "docs.py links: PASS\n"), res.stderr)

    def test_bad_links_and_anchors_are_listed(self):
        res = self.links_with("[a](docs/none.md)\n[b](docs/record.md#d17--nonexistent)\n[c](docs/record.md#d17)\n"
                              "[d](#nowhere)\n`[e](docs/none.md)`\n```\n[f](docs/none.md)\n```\n")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: docs/none.md", "README.md:2: docs/record.md#d17--nonexistent",
                                                   "README.md:3: docs/record.md#d17", "README.md:4: #nowhere",
                                                   "docs.py links: FAIL (4)"])

    def test_rendered_destinations_with_spaces_encoding_titles_and_images(self):
        self.repo.path("docs/user").mkdir()
        res = self.links_with("[a](<docs/user guide.md> \"Guide\")\n[b](docs/user%20guide.md)\n"
                              "![c](docs/user%20guide.md)\n[d](docs/a(b).md)\n[e](<docs/user guide2.md>)\n"
                              "[f](docs/a(c).md)\n", **{"docs/user guide.md": "# Guide\n", "docs/a(b).md": "# AB\n"})
        self.assertEqual(res.stdout.splitlines(), ["README.md:5: docs/user guide2.md", "README.md:6: docs/a(c).md",
                                                   "docs.py links: FAIL (2)"])

    def test_link_targets_resolve_within_the_repository(self):
        outside, back = f"{self.repo.dir}/docs/record.md", f"../{self.repo.dir.name}/docs/record.md"
        res = self.links_with(f"[a]({outside})\n[b](/docs/record.md#detail)\n[c]({back})\n[d](docs/../../x.md)\n",
                              **{"docs/sub.md": "[e](/README.md)\n[f](../docs/record.md)\n"})
        self.assertEqual(res.stdout.splitlines(), [f"README.md:1: {outside}", f"README.md:3: {back}",
                                                   "README.md:4: docs/../../x.md", "docs.py links: FAIL (3)"])

    def test_destination_after_opening_whitespace_is_checked(self):
        res = self.links_with("[a]( missing.md)\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: missing.md", "docs.py links: FAIL (1)"])

    def test_defined_reference_link_to_missing_target_fails(self):
        res = self.links_with("See [guide][manual] and [the record][record].\n\n[manual]: missing.md\n"
                              "[record]: docs/record.md \"Record\"\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:3: missing.md", "docs.py links: FAIL (1)"])

    def test_footnote_prose_is_not_a_link_destination(self):
        res = self.links_with("A claim.[^1]\n\n[^1]: Explanation.\n[^note]:\n  More prose.\n")
        self.assertEqual((res.returncode, res.stdout), (0, "docs.py links: PASS\n"))

    def test_decision_shorthand_is_not_a_rendered_anchor(self):
        res = self.links_with("[c](docs/record.md#d17)\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: docs/record.md#d17", "docs.py links: FAIL (1)"])
        self.assertEqual(docs.resolve(self.repo.dir, "docs/record.md#d17"), (True, "docs/record.md:3-12"))

    def test_code_spans_require_matching_complete_backtick_runs(self):
        res = self.links_with("``[a](docs/none.md)`\n\n``[b](docs/none.md)``\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: docs/none.md", "docs.py links: FAIL (1)"])

    def test_multiline_destinations_are_checked(self):
        res = self.links_with("[guide](\nmissing.md)\n[a](\n  docs/record.md#detail)\n\n[manual]:\nmissing2.md\n"
                              "[record]:\n  docs/record.md \"Record\"\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:2: missing.md", "README.md:7: missing2.md",
                                                   "docs.py links: FAIL (2)"])

    def test_multiline_code_span_cannot_hide_a_live_link(self):
        res = self.links_with("`start\nend` [x](missing.md) `tail\n\n`one\n\ntwo` [y](docs/none.md)\n# A `x\n"
                              "[a](missing3.md) `\n\n- one `x\n- [b](missing4.md) `\n\n| `c | d\n| [e](missing5.md) ` |\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:2: missing.md", "README.md:6: docs/none.md",
                                                   "README.md:8: missing3.md", "README.md:11: missing4.md",
                                                   "README.md:14: missing5.md", "docs.py links: FAIL (5)"])

    def test_escaped_backticks_do_not_hide_links(self):
        res = self.links_with("\\` [x](missing.md) \\`\n\n[a\\](docs/none.md)\n\n`a\\` [c](none2.md) `\n\n"
                              "\\\\`[d](docs/none.md)`\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: missing.md", "README.md:5: none2.md",
                                                   "docs.py links: FAIL (2)"])

    def test_an_escaped_opening_bracket_is_not_a_link(self):
        res = self.links_with("An escaped \\[not a link](missing.md), \\[x\\](gone.md) and ![i](none.png),\n"
                              "[a [nested] text](docs/none.md) then [real](README.md).\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: none.png", "README.md:2: docs/none.md",
                                                   "docs.py links: FAIL (2)"])

    def test_duplicate_suffix_collisions_match_rendered_anchors(self):
        self.assertEqual(docs.anchors([(1, 1, "X"), (3, 1, "X"), (5, 1, "X-1")]), ["x", "x-1", "x-1-1"])
        res = self.links_with("[a](docs/x.md#x)\n[b](docs/x.md#x-1)\n[c](docs/x.md#x-1-1)\n",
                              **{"docs/x.md": "# X\n\n# X\n\n# X-1\n"})
        self.assertEqual((res.returncode, res.stdout), (0, "docs.py links: PASS\n"))

    def test_anchors_follow_rendered_heading_content(self):
        page = ("---\ntitle: x\n---\n# [Guide](../README.md)\n\n## Setup <em>now</em>\n\n<!--\n## Hidden\n-->\n\n"
                "### [x] T1 — `a <b>` task\n\n## ![logo](record.md) Brand\n\nSetext Title\n============\n\n"
                "Second one\n---\n\n- item\n---\n\n> quoted\n===\n")
        names = ("guide", "guidereadmemd", "setup-now", "hidden", "x-t1--a-b-task", "logo-brand", "setext-title",
                 "second-one", "item", "quoted", "title-x")
        res = self.links_with("".join(f"[{k}](docs/h.md#{a})\n" for k, a in enumerate(names, 1)), **{"docs/h.md": page})
        self.assertEqual(res.stdout.splitlines(), [f"README.md:{k}: docs/h.md#{a}" for k, a in enumerate(names, 1)
                                                   if k in (2, 4, 9, 10, 11)] + ["docs.py links: FAIL (5)"])
        self.assertEqual(docs.resolve(self.repo.dir, "docs/h.md#setext-title"), (True, "docs/h.md:16-26"))

    def test_percent_encoded_fragments_resolve(self):
        res = self.links_with("# Guide\n\n[x](#%67uide)\n[y](docs/record.md#%64etail)\n[z](#%6Eope)\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:5: #%6Eope", "docs.py links: FAIL (1)"])

    def test_fence_with_trailing_text_does_not_expose_headings(self):
        res = self.links_with("[a](#hidden)\n\n```\n```example\n## Hidden\n```\n")
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: #hidden", "docs.py links: FAIL (1)"])

    def test_shorter_fence_does_not_expose_example_headings(self):
        res = self.links_with("[a](docs/fence.md#inside)\n[b](docs/fence.md#after)\n",
                              **{"docs/fence.md": "# F\n\n````\n```\n## Inside\n```\n````\n\n## After\n"})
        self.assertEqual(res.stdout.splitlines(), ["README.md:1: docs/fence.md#inside", "docs.py links: FAIL (1)"])
        self.assertEqual(docs.resolve(self.repo.dir, "docs/fence.md#after"), (True, "docs/fence.md:9-9"))

    def test_agents_md_twins(self):
        self.repo.write("sub/AGENTS.md", "rules\n")
        self.assertDocs(1, "links", texts=("sub/CLAUDE.md: missing; it holds the line @AGENTS.md", "docs.py links: FAIL (1)"))
        self.repo.write("sub/CLAUDE.md", "hello\n")
        self.assertDocs(1, "links", texts=("sub/CLAUDE.md: no @AGENTS.md line",))
        self.repo.path("sub/CLAUDE.md").unlink()
        self.repo.write("sub/real.md", "@AGENTS.md\n")
        os.symlink("real.md", self.repo.path("sub/CLAUDE.md"))
        self.assertDocs(1, "links", texts=("sub/CLAUDE.md: no @AGENTS.md line",))
        self.repo.path("sub/CLAUDE.md").unlink()
        self.repo.path("sub/CLAUDE.md").mkdir()
        self.assertDocs(1, "links", texts=("sub/CLAUDE.md: no @AGENTS.md line",))
        self.repo.path("sub/CLAUDE.md").rmdir()
        self.repo.write("sub/CLAUDE.md", "# Sub\n@AGENTS.md\n")
        self.assertDocs(0, "links", texts=("docs.py links: PASS",))


RULE = """---
paths: ["src/a/**", "tests/test_a.py"]
---
<!-- generated by docs.py pointers; edit the page's frontmatter instead -->
[docs/design.md](../../docs/design.md), read when: changing the fixture
- docs/design.md#shape
- docs/design.md#shape-1
"""


class PointersTest(DocsCase):
    def setUp(self):
        super().setUp()
        self.repo.git("rm", "-q", "docs/record.md")
        self.repo.write("docs/design.md", page() + "\n## Shape\n\nOne.\n\n### Detail\n\n## Shape\n\nTwo.\n")
        self.repo.write("docs/runbooks/run.md", page(when="running the fixture", covers="[]"))
        self.repo.write("docs/README.md", README)
        self.repo.commit("docs with frontmatter")

    def test_first_generation_writes_the_rule_file_and_a_new_agents_md(self):
        out = self.assertDocs(0, "pointers")
        self.assertEqual(out.splitlines(), [".claude/rules/design.md: written", "src/a/AGENTS.md: written",
                                            "src/a/CLAUDE.md: written", "tests/AGENTS.md: written",
                                            "tests/CLAUDE.md: written", "docs.py pointers: PASS"])
        self.assertEqual(self.repo.read(".claude/rules/design.md"), RULE)
        self.assertEqual(self.repo.read("tests/CLAUDE.md"), "@AGENTS.md\n")
        self.assertEqual(self.repo.read("tests/AGENTS.md"),
                         "<!-- docs.py pointers -->\n[docs/design.md](../docs/design.md), read when: changing the fixture\n"
                         "- docs/design.md#shape\n- docs/design.md#shape-1\n<!-- /docs.py pointers -->\n")
        self.assertDocs(0, "pointers", "--check")
        self.assertDocs(0, "lint")

    def test_first_generation_into_a_directory_holding_an_unmarked_agents_md(self):
        self.repo.write("src/AGENTS.md", "# src\n\nHand-written.\n")
        self.assertDocs(1, "pointers", texts=("src/AGENTS.md: no pointer markers", "docs.py pointers: FAIL (1)"))
        self.assertEqual(self.repo.read("src/AGENTS.md"), "# src\n\nHand-written.\n")
        self.assertFalse(self.repo.path("src/a/AGENTS.md").exists())
        self.assertEqual(self.repo.read(".claude/rules/design.md"), RULE)
        self.assertDocs(1, "pointers", "--check", texts=("src/AGENTS.md: no pointer markers",))

    def test_a_hand_edited_pointer_is_caught_by_check_and_lint(self):
        self.assertDocs(0, "pointers")
        self.repo.commit("pointers")
        self.repo.edit(".claude/rules/design.md", "changing the fixture", "never")
        self.repo.edit("tests/AGENTS.md", "- docs/design.md#shape-1\n", "")
        res = self.assertDocs(1, "pointers", "--check")
        self.assertEqual(res.splitlines(), [".claude/rules/design.md: would change", "tests/AGENTS.md: would change",
                                            "docs.py pointers: FAIL (2)"])
        self.assertIn("never", self.repo.read(".claude/rules/design.md"))  # --check writes nothing
        self.assertDocs(1, "lint", texts=(".claude/rules/design.md: would change", "docs.py lint: FAIL (2)"))
        self.assertDocs(0, "pointers")
        self.assertEqual(self.repo.read(".claude/rules/design.md"), RULE)

    def test_an_agents_md_with_other_content_keeps_it_around_the_block(self):
        text = "# src\r\n\nAbove.\n<!-- docs.py pointers -->\nstale line\n<!-- /docs.py pointers -->\n\nBelow.\n"
        self.repo.write("src/AGENTS.md", text)
        self.assertDocs(0, "pointers")
        self.assertEqual(self.repo.path("src/AGENTS.md").read_bytes().decode(), text.replace(
            "stale line\n", "[docs/design.md](../docs/design.md), read when: changing the fixture\n"
            "- docs/design.md#shape\n- docs/design.md#shape-1\n"))
        self.assertFalse(self.repo.path("src/a/AGENTS.md").exists())

    def test_two_pages_mapping_to_the_same_file_share_one_block(self):
        self.repo.write("docs/runbooks/run.md", page(when="running the fixture", covers="[src/b/*.py]"))
        self.repo.write("src/AGENTS.md", "<!-- docs.py pointers -->\n<!-- /docs.py pointers -->\n")
        self.assertDocs(0, "pointers")
        self.assertEqual(self.repo.read("src/AGENTS.md"), (
            "<!-- docs.py pointers -->\n[docs/design.md](../docs/design.md), read when: changing the fixture\n"
            "- docs/design.md#shape\n- docs/design.md#shape-1\n\n"
            "[docs/runbooks/run.md](../docs/runbooks/run.md), read when: running the fixture\n<!-- /docs.py pointers -->\n"))
        self.assertTrue(self.repo.path(".claude/rules/runbooks--run.md").is_file())

    def test_a_page_that_drops_covers_loses_its_pointers(self):
        self.assertDocs(0, "pointers")
        self.repo.write(".claude/rules/mine.md", "---\npaths: [src/**]\n---\nHand-written rule.\n")
        self.repo.commit("pointers")
        self.repo.write("docs/design.md", page(covers="[]"))
        out = self.assertDocs(0, "pointers")
        self.assertIn(".claude/rules/design.md: removed", out)
        self.assertFalse(self.repo.path(".claude/rules/design.md").exists())
        self.assertTrue(self.repo.path(".claude/rules/mine.md").is_file())
        for rel in ("src/a/AGENTS.md", "tests/AGENTS.md"):
            self.assertEqual(self.repo.read(rel), "<!-- docs.py pointers -->\n<!-- /docs.py pointers -->\n")
        self.assertDocs(0, "pointers", "--check")

    def test_wildcard_paths_are_valid_yaml(self):
        self.assertDocs(0, "pointers")
        line = self.repo.read(".claude/rules/design.md").split("---\n")[1].strip()
        self.assertTrue(line.startswith("paths: "), line)
        self.assertEqual(json.loads(line[len("paths: "):]), ["src/a/**", "tests/test_a.py"])  # a JSON list is YAML
        self.assertIn('"src/a/**"', line, "an unquoted ** is a YAML alias, not a glob")

    def test_colliding_page_slugs_preserve_both_pointers(self):
        self.repo.write("docs/a/b.md", page(when="a slash", covers="[src/b/**]"))
        self.repo.write("docs/a-b.md", page(when="a dash", covers="[src/c/**]"))
        self.repo.commit("two pages whose names differ by a slash")
        self.assertDocs(0, "pointers", texts=(".claude/rules/a--b.md: written", ".claude/rules/a-b.md: written"))
        self.assertIn("read when: a slash", self.repo.read(".claude/rules/a--b.md"))
        self.assertIn("read when: a dash", self.repo.read(".claude/rules/a-b.md"))
        self.assertDocs(0, "pointers", "--check")

    def test_two_pages_naming_one_rule_file_are_refused(self):
        self.repo.write("docs/a/b.md", page(when="a slash", covers="[src/b/**]"))
        self.repo.write("docs/a--b.md", page(when="two dashes", covers="[src/c/**]"))
        self.repo.commit("two pages naming one rule file")
        self.assertDocs(1, "pointers", texts=(".claude/rules/a--b.md: named by both docs/a--b.md and docs/a/b.md",
                                              "docs.py pointers: FAIL (1)"))
        self.assertFalse(self.repo.path(".claude/rules/a--b.md").exists())
        self.assertEqual(self.repo.read(".claude/rules/design.md"), RULE)

    def test_an_agents_md_under_docs_is_a_pointer_target_not_a_page(self):
        self.repo.write("docs/AGENTS.md", "<!-- docs.py pointers -->\n<!-- /docs.py pointers -->\n")
        self.repo.write("docs/runbooks/run.md", page(when="running the fixture", covers="[docs/**]"))
        self.repo.commit("a page covering docs/ itself")
        self.assertDocs(0, "pointers", texts=("docs/AGENTS.md: written", ".claude/rules/runbooks--run.md: written"))
        self.assertEqual(self.repo.read("docs/AGENTS.md"), (
            "<!-- docs.py pointers -->\n[docs/runbooks/run.md](runbooks/run.md), read when: running the fixture\n"
            "<!-- /docs.py pointers -->\n"))
        self.assertDocs(0, "lint", texts=("docs.py lint: PASS",))  # no frontmatter wanted, no index row
        self.assertEqual(self.assertDocs(0, "index"), INDEX)

    def test_a_destination_symlinked_outside_the_repository_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix="docsfx-"))
        self.addCleanup(shutil.rmtree, outside, True)
        os.symlink(outside, self.repo.path(".claude"))
        os.symlink(outside / "AGENTS.md", self.repo.path("tests/AGENTS.md"))
        out = self.assertDocs(1, "pointers")
        self.assertIn(".claude/rules/design.md: resolves outside the repository", out)
        self.assertIn("tests/AGENTS.md: resolves outside the repository", out)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue(self.repo.path("src/a/AGENTS.md").is_file())

    def test_twin_symlink_cannot_write_outside_repository(self):
        outside = Path(tempfile.mkdtemp(prefix="docsfx-"))
        self.addCleanup(shutil.rmtree, outside, True)
        self.repo.path("src/a").mkdir(parents=True)
        os.symlink(outside / "CLAUDE.md", self.repo.path("src/a/CLAUDE.md"))
        out = self.assertDocs(0, "pointers", texts=("src/a/AGENTS.md: written",))
        self.assertNotIn("src/a/CLAUDE.md", out)
        self.assertFalse(os.path.lexists(outside / "CLAUDE.md"))


class StaleTest(DocsCase):
    def setUp(self):
        super().setUp()
        self.repo.git("rm", "-q", "docs/record.md")
        self.repo.write("src/a/x.py", "X = 1\n")
        self.commit_at("2026-10-01T09:00:00+02:00", "a covered change before the page's re-verification")
        self.repo.write("docs/design.md", page(covers="[src/a/**]"))
        self.repo.write("docs/runbooks/run.md", page(when="running the fixture", covers="[src/z/**]"))
        self.repo.write("docs/README.md", README)
        self.commit_at("2026-10-01T10:00:00+02:00", "pages verified")

    def commit_at(self, when, msg):
        self.repo.git("add", "-A")
        subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "--date", when, "-m", msg],
                       cwd=self.repo.dir, env=env(GIT_COMMITTER_DATE=when), capture_output=True, text=True, check=True)

    def test_a_covered_change_the_same_day_before_and_after_the_page_commit(self):
        self.assertDocs(0, "stale", texts=("docs.py stale: PASS",))
        self.repo.write("src/a/y.py", "Y = 1\n")
        self.commit_at("2026-10-01T10:01:00+02:00", "a covered change after it")
        out = self.assertDocs(1, "stale")
        self.assertEqual(out.splitlines(), ["docs/design.md: 2026-10-01T10:01:00+02:00 after last-verified 2026-10-01",
                                            "docs.py stale: 1 stale"])

    def test_a_covered_change_on_a_later_day_is_stale_and_one_without_commits_is_not(self):
        self.repo.write("src/a/x.py", "X = 2\n")
        self.commit_at("2026-10-02T08:00:00+02:00", "next day")
        out = self.assertDocs(1, "stale")
        self.assertIn("docs/design.md: 2026-10-02T08:00:00+02:00 after last-verified 2026-10-01", out)
        self.assertNotIn("docs/runbooks/run.md", out)

    def readme_stale(self, readme, change, minute):
        """stale's README.md lines once README.md is committed at 10:<minute> and a change one minute later."""
        self.repo.write("README.md", readme)
        self.commit_at(f"2026-10-01T10:{minute:02d}:00+02:00", "readme")
        self.repo.write(change, f"V = {minute}\n")
        self.commit_at(f"2026-10-01T10:{minute + 1:02d}:00+02:00", "a change")
        return [l for l in self.docs("stale").stdout.splitlines() if l.startswith("README.md")]

    def test_a_readme_covers_comment(self):
        self.repo.write("README.md", "# R\n\n<!-- covers: [src/a/**] -->\n")
        self.commit_at("2026-10-01T10:00:00+02:00", "readme")
        self.assertDocs(0, "stale", texts=("docs.py stale: PASS",))
        self.repo.write("src/a/y.py", "Y = 1\n")
        self.commit_at("2026-10-01T10:01:00+02:00", "a covered change after it")
        self.assertIn("README.md: 2026-10-01T10:01:00+02:00 after README.md's last commit 2026-10-01T10:00:00+02:00",
                      self.assertDocs(1, "stale").splitlines())
        self.assertEqual(self.readme_stale("# R\n", "src/a/z.py", 2), [])

    def test_readme_covers_preserves_quoted_globs_and_ignores_examples(self):
        self.assertEqual(len(self.readme_stale('# R\n<!-- covers: ["src/a,b/**"] -->\n', "src/a,b/x.py", 2)), 1)
        self.assertEqual(self.readme_stale("# R\n```\n<!-- covers: [src/a/**] -->\n```\n", "src/a/x.py", 4), [])
        self.assertEqual(self.readme_stale("<!-- covers: [src/z/**] -->\n<!-- covers: [src/a/**] -->\n",
                                           "src/a/x.py", 6), [])
        self.assertEqual(self.readme_stale("<!-- covers: [src/a/** -->\n", "src/a/x.py", 8), [])
        self.assertEqual(self.readme_stale("<!-- covers: src/a/** -->\n", "src/a/x.py", 10), [])


if __name__ == "__main__":
    unittest.main()
