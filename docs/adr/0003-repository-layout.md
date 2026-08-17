# ADR 0003 — Repository layout maps spec §28 onto a `src/` package

**Status:** Accepted
**Date:** 2026-08-17
**Governs:** spec §28, and the M0 acceptance test on evaluator separation

## Context

Spec §28 gives a logical repository tree with top-level components (`kernel/`, `bsir/`,
`genomes/`, `evolution/`, `abstraction/`, `eqsat/`, `compiler/`, `verification/`, `evaluator/`,
`models/`, `experiments/`, `telemetry/`, `schemas/`, `tests/`).

Taken literally as Python packages, those names would be claimed at the top level of the
import namespace — `import kernel`, `import compiler`, `import models` — which collides with
common third-party and stdlib-adjacent names and makes the instrument unsafe to install
alongside anything else.

Separately, §28 states the hidden frozen evaluator "should ideally live in a separate
repository or protected service namespace so the evolutionary agent cannot inspect it", and
M0's acceptance test requires that there be **no import path from the candidate side**.

## Decision

1. The §28 component names are preserved exactly, as subpackages of a single distribution
   package: `src/bestsad/kernel/`, `src/bestsad/bsir/`, and so on. The logical tree is
   unchanged; only its root moves.
2. `docs/` and `schemas/` stay at the repository root, as §28 shows them.
3. The frozen hidden evaluator assets live in a top-level `hidden_evaluator/` directory that
   is **not part of the installed package** and is not importable from `bestsad.*`. It stands
   in for the separate repository §28 asks for, so that the boundary is testable in one
   checkout during development.
4. A test (`tests/integrity/test_trust_boundary.py`) asserts statically that no module under
   `src/bestsad/` imports `hidden_evaluator`, and that the only process permitted to read
   those assets is the evaluator process described in ADR-0005.

Point 3 is a **development convenience with a real weakening attached**: a single checkout
means an attacker with filesystem access has the assets. That residual is disclosed here and
in `hidden_evaluator/README.md`, and the production deployment must move the directory to a
separate repository or service namespace before any result is treated above Claim Level 1.

## Consequences

- `pip install -e .` yields one importable name, `bestsad`.
- The trust boundary is mechanically checked rather than assumed.
- The one-checkout arrangement is a known, written-down residual, not a silent shortcut.
