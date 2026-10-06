"""AC-8 and AC-9: routing lives only in persona frontmatter and matches the design table."""

from __future__ import annotations

import re
import unittest

from support import SKILL, load_module

sp = load_module()

OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"
FABLE = "claude-fable-5-1"
SOL, ASTRA, LUNA = "gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"

# The design's "Roles and routing" table: (claude model, effort, codex model, effort).
# A variant overrides only what it names; mechanical effort is inherited from the default.
ROUTING = {
    ("chief", None): (OPUS, "medium", SOL, "medium"),
    ("builder", None): (SONNET, "medium", SOL, "medium"),
    ("builder", "judgement"): (OPUS, "high", SOL, "high"),
    ("builder", "mechanical"): (HAIKU, "medium", LUNA, "medium"),
    ("reviewer", None): (OPUS, "high", SOL, "high"),
    ("reviewer", "acceptance"): (OPUS, "xhigh", SOL, "xhigh"),
    ("security-reviewer", None): (OPUS, "high", SOL, "high"),
    ("advisor", None): (FABLE, "high", ASTRA, "high"),
}


class RoutingTest(unittest.TestCase):
    def test_the_pool_is_exactly_the_five_roles(self) -> None:
        names = {p.stem for p in sp.pool_sources()}
        self.assertEqual(names, {"builder", "reviewer", "security-reviewer", "advisor", "chief"})
        self.assertEqual(names, set(sp.BASE_PERSONA_NAMES))
        self.assertLessEqual(len(names), 5)

    def test_routing_matches_the_design_table(self) -> None:
        for (name, variant), (cm, ce, xm, xe) in ROUTING.items():
            meta, _ = sp.load(name)
            with self.subTest(name=name, variant=variant):
                self.assertEqual(sp.routing(meta, variant),
                                 {"claude": {"model": cm, "effort": ce},
                                  "codex": {"model": xm, "effort": xe}})

    def test_every_declared_variant_is_in_the_table(self) -> None:
        for name in sp.BASE_PERSONA_NAMES:
            meta, _ = sp.load(name)
            declared = {k.split(".")[1] for k in meta if k.startswith("variant.")}
            self.assertEqual(declared, {v for (n, v) in ROUTING if n == name and v}, name)

    def test_no_xhigh_except_reviewer_acceptance(self) -> None:
        for name in sp.BASE_PERSONA_NAMES:
            meta, _ = sp.load(name)
            for key, value in meta.items():
                if value == "xhigh":
                    self.assertEqual((name, key.split(".")[:2]),
                                     ("reviewer", ["variant", "acceptance"]), key)

    def test_builder_defaults_to_the_mid_tier(self) -> None:
        meta, _ = sp.load("builder")
        self.assertEqual(sp.routing(meta)["claude"], {"model": SONNET, "effort": "medium"})

    def test_chief_is_a_routing_profile_and_never_spawnable(self) -> None:
        for name in sp.BASE_PERSONA_NAMES:
            meta, _ = sp.load(name)
            self.assertEqual(sp.spawnable(meta), name != "chief", name)

    def test_judging_set_is_the_read_only_roles(self) -> None:
        self.assertEqual(sp.JUDGING_PERSONA_NAMES, {"reviewer", "security-reviewer", "advisor"})
        self.assertTrue(sp.JUDGING_PERSONA_NAMES < sp.BASE_PERSONA_NAMES)
        for name in sp.BASE_PERSONA_NAMES:
            meta, _ = sp.load(name)
            self.assertEqual(meta["writes"] == "no", name in sp.JUDGING_PERSONA_NAMES, name)

    def test_an_unknown_variant_is_refused(self) -> None:
        meta, _ = sp.load("builder")
        with self.assertRaises(sp.PersonaError):
            sp.routing(meta, "turbo")

    def test_each_source_is_at_most_300_words(self) -> None:
        for path in sorted((SKILL / "personas").glob("*.md")):
            words = len(re.findall(r"\S+", path.read_text(encoding="utf-8")))
            self.assertLessEqual(words, 300, path.name)


if __name__ == "__main__":
    unittest.main()
