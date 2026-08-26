# ADR 0014 — BSLD is declarative and its lowering is evidence-bound

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** SRE v0.1 ADR-BS-002; design §7.2
**Relates to:** `src/bestsad/languages/`

## Context

BSLD lets an evolved language declare its operations and how they lower to BSIR, without
BestSad trusting a language-specific compiler. The whole point is that a machine-invented
language need not be human-readable (P8) — but that only works if the lowering itself is
checkable, because a lowering is exactly where a language could lie about what it means.

An unchecked lowering is worse than no lowering. It launders an arbitrary claim into a
canonical semantic hash, and everything downstream then treats that hash as truth.

## Decision

A BSLD descriptor is declarative data — JSON/YAML — not code. It names operations, their
operand and result types, their effects, and a lowering template into BSIR. Self-modifying
descriptor semantics are out of scope for v0.1.

Every descriptor operation carries `proof_obligations`. Lowering a program through a
descriptor produces, alongside the BSIR graph, the set of obligations that lowering discharged
or deferred. `lowering_semantic_equivalence` is the obligation that the lowered BSIR means
what the descriptor says the operation means.

An obligation is never discharged by the descriptor asserting it. It is discharged by
evidence — a tiered equivalence result (ADR-adjacent, `src/bestsad/bsir/equivalence.py`)
against a reference lowering, differential execution, or a proof — and an undischarged
obligation is recorded as such and travels with the graph.

## Consequences

- A descriptor that lowers `zq` to something other than `map` cannot make that lowering true
  by declaring it. The obligation stays open, and any consumer requiring a discharged
  obligation refuses it.
- Deliberately incorrect lowerings are a testable fixture rather than a hypothetical:
  `tests/languages/test_incorrect_lowering_is_caught.py` builds one and asserts it is caught.
- Descriptors stay cheap to write and cheap to review, because they contain no control flow.
- The cost: expressive power is limited to what the lowering templates can say. That limit is
  deliberate in v0.1 and should be raised only with a matching increase in obligation
  checking.

## Revisit trigger

If descriptor templates prove too weak for a language the search actually invents, the
extension to consider first is richer *templates*, not descriptor-embedded code.
