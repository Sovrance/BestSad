# ADR 0014 — BSLD is declarative and its lowering is evidence-bound

**Status:** Accepted (amended 2026-09-15)
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
  `tests/languages/test_bsld_lowering.py::IncorrectLoweringIsCaught` builds one and asserts it
  is caught (see the amendment below for the path this ADR originally named).
- Descriptors stay cheap to write and cheap to review, because they contain no control flow.
- The cost: expressive power is limited to what the lowering templates can say. That limit is
  deliberate in v0.1 and should be raised only with a matching increase in obligation
  checking.

## Revisit trigger

If descriptor templates prove too weak for a language the search actually invents, the
extension to consider first is richer *templates*, not descriptor-embedded code.

## Amendment (2026-09-15) — the fixture's real name, and its generalisation

The first version of this ADR cited `tests/languages/test_incorrect_lowering_is_caught.py`. No
file of that name has ever existed in the package; the fixture was delivered as the test class
`IncorrectLoweringIsCaught` in `tests/languages/test_bsld_lowering.py`, and the text above now
says so. An ADR pointing at a test that does not exist is a control that cannot be checked, and
the discrepancy was found while adjudicating `BESTSAD_VERIFICATION_PLANE_ENG_v0.1.md` (§7.1).

Two things were added in the same work order (BEST-VERIF-04) that extend the fixture's idea:

- `tests/verify/test_symbolic_tier_verdicts.py` asserts the lying descriptor is *also* caught
  by the symbolic tier (ADR-0019), with a re-executed counterexample, and that the honest but
  commuted descriptor -- which sampled evidence could not discharge under
  `require_proof=True` -- is now discharged by a proof.
- `src/bestsad/verify/vacuity.py` generalises the pattern: rather than one hand-written
  incorrect lowering, mutants of the program pair are generated from a seed and the same
  contract must refute at least one of them before its proof may be promoted. A contract that
  accepts every mutant is vacuous, and the claim is refused with reason `contract_vacuous`.
  This is the control that makes an agent- or LLM-authored contract acceptable at all.
