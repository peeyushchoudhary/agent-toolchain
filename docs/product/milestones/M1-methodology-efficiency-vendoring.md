---
milestone: M1
title: Publish smaller complete execution routes
status: building
updated: 2026-09-18
---

# M1 — Publish smaller complete execution routes

## Goal

The public install bundle matches the accepted maintained-source behavior, retains every existing
control and persona assignment, and passes the complete local repository verification.

## Success criteria

- All accepted source/destination hashes match.
- Controller and reviewer complete-route reductions remain evidenced.
- Runtime identity fails closed for a missing or changed router.
- Persona list and preview outputs remain byte-identical; all persona/model files stay unchanged.
- Public repository verification passes on the exact accepted candidate.

## Cross-feature validation

The dry-run installer and repository verifier exercise the complete published bundle without
installing it.

Gate: cd install && ./install.sh --dry-run && ./verify.sh

## Deferred

No M1 deferrals are approved at bootstrap.

## Where it stops

No publication, merge, global installation, project adoption, model activation, or pilot.

