# Documentation

When a page and the tooling in `install/` disagree, the tooling is right.
Installing: [install/README.md](../install/README.md).

Each goal's spec, design and plan are in `goals/<id>/`. The table below is generated: change a
page's `read-when`, then print it with `docs.py index`.

| Page | Read when |
|---|---|
| [architecture/methodology.md](architecture/methodology.md) | Changing anything under `install/`, or asking how a goal runs, what v7 replaced, its risks or its rollback |
| [architecture/personas.md](architecture/personas.md) | Changing a line of an agent file, or asking why a persona says what it says |
| [architecture/repository-standard.md](architecture/repository-standard.md) | Adding, moving or removing a file, or deciding where something belongs |
| [archive/README.md](archive/README.md) | Looking for superseded material, a removed decision's text or the v6 tree |
| [decisions/decisions.md](decisions/decisions.md) | Making or citing a decision, or asking why the methodology is the way it is |
| [product/measurements.md](product/measurements.md) | Citing a number, recording a measurement, or applying the pilot's stop rule |
| [product/prd.md](product/prd.md) | Deciding whether a change belongs in the methodology, or what `install/` must keep doing |
| [runbooks/codex.md](runbooks/codex.md) | Running Codex as the chief or as the other vendor's reviewer |
| [runbooks/github.md](runbooks/github.md) | Creating a repository, merging a milestone, or installing the guard in a clone |
| [runbooks/migrate-v5.md](runbooks/migrate-v5.md) | Migrating a v5.1 project, or deciding whether `--retire-v5` may run |
