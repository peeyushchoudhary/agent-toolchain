# Migrate product documents

Use when conformance identifies product-definition layout or schema gaps. First inspect the
conformance findings, then run the owning migrator in report mode:

```bash
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" <repo> --only "product definition"
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py" <repo> --product
```

Read each move, derived metadata value, refusal and skipped document before applying anything.
Apply only within an authorized change set in a clean isolated checkout when needed:

```bash
python3 "$HOME/.claude/skills/progressive-disclosure/scripts/migrate_to_standard.py" <repo> --product --apply
```

Preserve prose and history, rewrite affected links, and verify body content and link resolution. Do
not invent review history, statuses, ownership or a deferral reason. Resolve substantive metadata
from the document/history or the founder's decision. Account for the existing spec date/commit rule
in the migration commit.

Methodology adoption is a separate state decision; migration does not imply upgrading its version.
After migration run product-definition checks, structured runtime status, affected route checks and
the repository gate. Report the limited scope of a narrowed check. Existing migrator and checker
implementations remain the authorities.
