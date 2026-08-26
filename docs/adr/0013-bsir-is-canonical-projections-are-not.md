# ADR 0013 — BSIR is canonical semantics; projections are never authoritative

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** SRE v0.1 ADR-BS-001; spec §9.4; design principle P8
**Relates to:** `src/bestsad/bsir/projections.py`, `tests/bsir/test_projection_is_not_canonical.py`

## Context

This repository already holds the substance of this decision: `semantic_hash` is taken over
normalized BSIR, and a test asserts that no code path treats a projection as semantics. What
v0.1 adds is a second surface — BSLD-described languages (ADR 0014) — and a second consumer,
SAISES, which will read BestSad equivalence results without being able to see how they were
produced.

Both additions create new places where a surface form could be mistaken for the truth.

## Decision

BSIR is the canonical semantic object. Every surface representation — the human projection, a
BSLD-described evolved language, a rendered listing in a report — is a *view*. A view may be
generated from BSIR and may be lowered into BSIR, but no view is ever the input to a semantic
identity, an equivalence verdict, or a promotion decision.

Concretely, and enforceably:

- `semantic_hash` is computed only from canonicalized BSIR, and its definition does not change
  in v0.1. Existing hashes are preserved; `tests/sre/test_semantic_hash_is_preserved.py` pins
  representative digests as literals.
- `structural_hash` exists for the narrow question "is this literally the same text" and is
  never accepted where semantics are meant.
- BSIR level metadata (ADR-adjacent, see `src/bestsad/bsir/levels.py`) is carried *outside*
  node and graph hashes, so annotating a graph with its level cannot move its identity.

## Consequences

- Adding a surface language is cheap and safe: it cannot affect the identity of any program
  that already exists.
- An equivalence verdict exported to SAISES refers to semantic roots, so its meaning does not
  depend on the consumer being able to read BestSad's projection syntax.
- Anything that genuinely needs surface identity has to say so by reaching for
  `structural_hash`, which is a visible, greppable act rather than an accident.
