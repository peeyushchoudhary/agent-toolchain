"""Drift guards between the configuration the scripts READ and the schema the SKILL.md DOCUMENTS.

Both of these have exactly one failure mode worth automating: someone adds a knob and documents it
but never reads it, or reads it and never documents it. Neither is visible in a diff, both are
found by a reader at the worst possible moment — when a configuration key silently does nothing.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SKILL = ROOT / "SKILL.md"

CONFIG_SH = (SCRIPTS / "gate_config.sh").read_text()
ALL_SH = "\n".join(p.read_text() for p in sorted(SCRIPTS.glob("*.sh")))


class CacheKindMapping(unittest.TestCase):
    """A cache kind with a host-path default but no in-sandbox variable is a silent half-feature.

    The clone would happen, disk would be spent, and the toolchain inside the sandbox would never be
    told where its cache went — so it would rebuild from nothing and look merely slow.
    """

    def kinds_with_a_host_default(self):
        return set(re.findall(r'\$\{GATE_CACHE_PATH_([A-Za-z0-9]+):=', CONFIG_SH))

    def kinds_with_a_sandbox_variable(self):
        body = CONFIG_SH.split("gate_cache_env_vars()", 1)[1].split("\n}", 1)[0]
        kinds = set()
        for line in body.splitlines():
            m = re.match(r"\s*([a-z0-9|]+)\)\s", line)
            if m:
                kinds.update(m.group(1).split("|"))
        return kinds

    def test_every_kind_with_a_host_default_is_exposed_in_the_sandbox(self):
        missing = self.kinds_with_a_host_default() - self.kinds_with_a_sandbox_variable()
        self.assertEqual(
            missing, set(),
            f"cache kind(s) {sorted(missing)} are cloned but never exposed to the toolchain that "
            f"needs them — the cache would be provisioned and then ignored",
        )

    def test_every_exposed_kind_has_somewhere_to_come_from(self):
        missing = self.kinds_with_a_sandbox_variable() - self.kinds_with_a_host_default()
        self.assertEqual(
            missing, set(),
            f"cache kind(s) {sorted(missing)} map to a sandbox variable but no host path default "
            f"exists, so naming them in GATE_CACHES warns and does nothing",
        )

    def test_there_is_at_least_one_kind(self):
        """Guards the parsers themselves. Both sets being empty makes the two tests above pass
        vacuously, which is the shape in which a broken regex reads as a clean result."""
        self.assertTrue(self.kinds_with_a_host_default(), "parsed no cache kinds — the regex broke")


class DocumentedSchema(unittest.TestCase):
    """The SKILL.md schema table against the keys the scripts actually consume."""

    def documented(self):
        found = set(re.findall(r"^\| `(GATE_[A-Z_]+)", SKILL.read_text(), re.M))
        return {k for k in found if not k.startswith("GATE_CACHE_PATH")}

    def consumed(self):
        # Keys the scripts read or default. GATE_CACHE_PATH_* is deliberately excluded: it is the
        # host layer's per-kind path, documented as a concept rather than as N table rows.
        found = set(re.findall(r"\bGATE_[A-Z_]+\b", ALL_SH))
        return {k for k in found if not k.startswith("GATE_CACHE_PATH")}

    # Names that are machinery rather than configuration: they are set BY the scripts, not read
    # from a config file, so they have no place in a schema a user writes.
    INTERNAL = {"GATE_LIB_DIR", "GATE_CONFIG_PATH", "GATE_CONFIG", "GATE_HOME", "GATE_RC"}

    def test_every_documented_key_is_actually_read(self):
        orphans = self.documented() - self.consumed()
        self.assertEqual(
            orphans, set(),
            f"SKILL.md documents {sorted(orphans)}, which no script reads — setting them would do "
            f"nothing, and a reader has no way to find that out",
        )

    def test_every_configuration_key_is_documented(self):
        undocumented = self.consumed() - self.documented() - self.INTERNAL
        self.assertEqual(
            undocumented, set(),
            f"the scripts read {sorted(undocumented)}, which SKILL.md never mentions — an "
            f"undocumented knob is one nobody sets and everybody is surprised by",
        )


class NoProjectFacts(unittest.TestCase):
    """The invariant that lets this skill be published at all."""

    def test_no_absolute_user_home_appears_in_the_shipped_scripts(self):
        hits = []
        for p in sorted(SCRIPTS.glob("*.sh")) + [SKILL]:
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if re.search(r"/Users/[a-z]|/home/[a-z]", line):
                    hits.append(f"{p.name}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "hardcoded home path(s) in a published skill:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
