---
summary: Explicit immutable-test migrations and inherited pytest-environment isolation for current module gates.
read-when: Planning or reviewing the narrow exception for a frozen test route that has a named current successor.
covers: []
last-verified: 2026-10-20
---
# S-11 spec: Explicit test migrations and isolated gate execution

**Users and problem.** Founders and coding agents need to replace obsolete
frozen test routes without rewriting history or silently reducing checks.
Today every existing module command change is forbidden, including an explicit
replacement approved by the founder. Module commands also inherit pytest
options that can narrow execution or load an unintended plugin.

**What changes for the user.** A narrowly declared migration can preserve the
original bytes and require named current successors. All undeclared shrinkage
still fails. Gates isolate inherited pytest controls without editing each
module command or installed copy.

**Acceptance criteria.**

- AC1 WHEN an existing module command changes, THE SYSTEM SHALL accept only an
  exact migration declared before goal approval, binding its original command,
  prospective command, immutable original source identities and mandatory named
  successor/preservation evidence. Ordinary maps keep the current rule.
- AC2 WHEN that migration is accepted, THE SYSTEM SHALL verify original files
  remain unchanged and required current successors actually passed on the exact
  candidate tree. Preservation, unavailable historical environments and behavioral
  replay remain distinct claims. An unavailable replay cannot be labeled passed.
- AC3 WHEN any declaration, file, command or evidence is missing, stale,
  mismatched or introduced after approval, THE SYSTEM SHALL refuse the exception.
  Unrelated test removal, changed interpreters/counts, removed needs or lost
  shared/path coverage remain forbidden; intermediate commits cannot launder them.
- AC4 WHEN a gate command starts, THE SYSTEM SHALL remove inherited
  `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTEST_XDIST_WORKER` and
  `PYTEST_XDIST_WORKER_COUNT`. Hostile ambient settings cannot narrow executed
  tests or load a plugin; explicit command and interpreter selection remain intact.
- AC5 WHEN the goal closes, THE SYSTEM SHALL provide fresh full/E2E evidence,
  unchanged legacy rejection tests, required other-vendor review and DONE on
  the accepted tree, with public rules matching executable behavior.

**Non-goals.** Automatic test retirement, arbitrary command edits, new skips or
expected-failure markers, baseline expansion, approval-tag workarounds, altered
installed guards, publishing, merging or installation.

**Constraints.** Standard-library Python, existing goal/gate/receipt interfaces,
one milestone, generic fixtures and no private project facts. Authored source
changes are reviewed before any separate release or installation decision.
