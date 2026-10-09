# install/

The single authored source for the skill, the installer and the gate; nothing is vendored from
`~/.claude`. Edit here, run `./verify.sh`, then `./install.sh`. What installs where:
[README.md](README.md).

<!-- docs.py pointers -->
[docs/architecture/methodology.md](../docs/architecture/methodology.md), read when: Changing anything under `install/`, or asking how a goal runs, what v7 replaced, its risks or its rollback
- docs/architecture/methodology.md#shape
- docs/architecture/methodology.md#what-it-replaced
- docs/architecture/methodology.md#accepted-risks
- docs/architecture/methodology.md#rollback

[docs/architecture/personas.md](../docs/architecture/personas.md), read when: Changing a line of an agent file, or asking why a persona says what it says
- docs/architecture/personas.md#what-each-file-guards-against
- docs/architecture/personas.md#adopted-lines-and-their-evidence
- docs/architecture/personas.md#left-out-and-where-it-lives-instead
- docs/architecture/personas.md#harness-caveats
<!-- /docs.py pointers -->
