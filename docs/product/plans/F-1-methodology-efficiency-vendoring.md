---
feature: F-1
milestone: M1
status: approved
updated: 2026-09-18
---

# F-1 implementation plan — accepted-source vendoring

## Frozen source

- Accepted source head: `c2a2afc2bbc6d586d382c9f6d5b791ac45a67a71`.
- Accepted source tree: `c34f4224c29c5b1980cc1cb6dfbb7d360fc61a48`.
- Source gate: `python3 scripts/check.py`, exit 0, `SOURCE GATE PASS`.
- Source seal receipt SHA-256: `0aebfaf3f825d31d943ae5506be92ad81e12e320339c2b069a8b5db5a813fa59`.

Accepted file hashes:

| Public destination | SHA-256 |
| --- | --- |
| `install/skills/execution-methodology/SKILL.md` | `db1754e9c1055c4e53c2204b9500fc75a2f9fb37f7b6063c365ef3987f31f528` |
| `install/skills/execution-methodology/methodology.md` | `d1a8b54c00dc0bc57811eb1b08c3149f7e2f433e30fd35020eef8267eb5c7fdb` |
| `install/skills/execution-methodology/references/execution-loop.md` | `048e7a3ac4de2e27fe5c568bbe57911ab49cb14cae0b1778854c25d8be0d6c03` |
| `install/skills/execution-methodology/references/task-card.md` | `c0e35e9bf72d04ea14873ef612ac6d4379d8e53e9651386533b3261bad123f3b` |
| `install/skills/execution-methodology/scripts/sync_methodology.py` | `41e8f3a256782e82ee19325b00e750ddf57362902ea00c8da8d846fd6c9e49b5` |
| `install/skills/execution-methodology/tests/test_methodology_policy.py` | `d6859abb1c23805ed01c512b7a050222d23aab85262dc1d86a873c5d350feb73` |
| `install/skills/execution-methodology/tests/test_runtime_status.py` | `4f94e7d1681fc78f981b6504ba4288089277bb3be98fc1cebf635616e80d734b` |
| `install/skills/execution-methodology/tests/test_execution_loop.py` | `f9dd85e8e72031598d8968bca597f223718bec23fa4378bb58b65137478bca76` |
| `install/skills/methodology-management/references/assessment.md` | `0aff60114aef4af97192c74ab5d3698b490d094eae489380c5e9dbfdda2ed52b` |
| `README.md` | `a1d28abeeb82f1e8aa46511936ee208a66459b734d27c0da8731233965e3f280` (source reference; public prose is adapted, not copied) |
| `install/skills/agent-personas/SKILL.md` | `e17dfe40a870314da27cd60482ef797aff7ad9e083fbfa04fb28a77e356f39a0` |
| `install/skills/agent-personas/references/roster.md` | `c0b3ed9fe2e2e773d4e9a5a7f5f1d3fdd9269adb413bd2c191022e0a8e0cc233` |

The task partition keeps runtime changes with the tests that recognize them. A disposable original-
partition check ran 103 tests and failed two old loop assertions when the new loop arrived before
its accepted test. The recut retains the same twelve total destinations and no task exceeds five.

```task
task: T1
title: Vendor accepted execution router and runtime tests
lane: full
needs: []
writes: [install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/methodology.md, install/skills/execution-methodology/scripts/sync_methodology.py, install/skills/execution-methodology/tests/test_methodology_policy.py, install/skills/execution-methodology/tests/test_runtime_status.py]
covers: [AC-1, AC-3, AC-5, AC-7, AC-9, AC-10]
serialises: []
```

```task
task: T2
title: Vendor accepted loop assessment and README
lane: full
needs: [T1]
writes: [install/skills/execution-methodology/references/execution-loop.md, install/skills/execution-methodology/references/task-card.md, install/skills/execution-methodology/tests/test_execution_loop.py, install/skills/methodology-management/references/assessment.md, README.md]
covers: [AC-3, AC-4, AC-6, AC-8, AC-9]
serialises: []
```

```task
task: T3
title: Vendor accepted persona router
lane: full
needs: [T2]
writes: [install/skills/agent-personas/SKILL.md, install/skills/agent-personas/references/roster.md]
covers: [AC-2, AC-5, AC-7, AC-8]
serialises: []
```

## Validation

- T1: from `install/skills/execution-methodology`, run `python3 -m unittest tests.test_methodology_policy tests.test_runtime_status`.
- T2: from the same directory, run `python3 -m unittest tests.test_execution_loop tests.test_methodology_policy` and prove the portable fixture resolves no source-only ledger.
- T3: run the complete persona list and read-only global/project previews; compare bytes with baseline.
- Final candidate: from `install/`, run `./install.sh --dry-run && ./verify.sh` once and persist its complete stdout/stderr.

Every source/destination pair is hash-checked. The five known public persona variants and every
other persona/model/effort/permission file remain unchanged. No command installs or adopts anything.
