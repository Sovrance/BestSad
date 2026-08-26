# ADR 0017 — CANONICAL maturity state, added by extension rather than by editing the delivered schema

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** `src/bestsad/abstraction/lifecycle.py`, `schemas/sre/primitive-record-sre-v0.1.schema.json`
**Relates to:** ADR 0009 (assurance/maturity reconciliation), spec §11.1–11.2

## Context

The SRE v0.1 design adds a CANONICAL maturity state between VER and CORE, linked to recovered
semantic signatures (design §4, §7.4). Two things made this less mechanical than it sounds.

**First, what CANONICAL means.** VER means "verified" — reused across families, positive
semantic gain, verification evidence recorded. CORE means the kernel changed. CANONICAL had to
be a claim narrower than either, and the natural one is about *identity*: the primitive's
recovered semantic signature has been proved equivalent to its K0 expansion, so the primitive
and its expansion are one semantic object.

**Second, where the state list lives.** `schemas/primitive_record.schema.json` encodes the
maturity enum and is one of the seventeen files pinned by `MANIFEST_SHA256.txt`.
`CONTRIBUTING.md` and spec §31.1 forbid editing it, and `tests/integrity/test_delivered_package.py`
enforces that. The first implementation of this ADR edited the enum in place and the integrity
gate rejected it — correctly. That gate exists so a specification cannot be quietly rewritten to
match an implementation, which is exactly what adding a state to it would have been.

## Decision

**CANONICAL requires a canonical-tier equivalence proof, and nothing weaker.**
`PromotionEvidence` gains `semantic_signature` and `equivalence_verdict`, and
`has_canonical_identity` requires both a signature and a verdict of `EQUIV_CANONICAL`. A
primitive whose signature agrees with its expansion on sampled evidence (`EQUIV_DYNAMIC`)
stays at VER, with a rationale naming the tier it fell short of.

The reason sampled evidence is refused here specifically: CANONICAL licenses treating the
primitive and its expansion as interchangeable everywhere. Evidence that they agree on a tested
domain does not support a claim about every domain, and the whole tier discipline in
`bsir/equivalence.py` exists so that this distinction survives contact with a promotion gate.

**The delivered schema is not edited.** The extension lives in
`schemas/sre/primitive-record-sre-v0.1.schema.json`, which re-declares the maturity enum with
CANONICAL added and conditionally requires the two evidence fields when that state is claimed.
A record at CANONICAL validates against the extension; a record at any v0.2 state validates
against both.

The conditional requirement is deliberately duplicated between schema and code. The promotion
predicate refuses to *return* CANONICAL without a proof, and the schema refuses to *accept* a
record claiming it without one, so a hand-written or externally produced record cannot bypass
the rule by not going through `promote`.

**On the assurance ladder** (ADR 0009), CANONICAL maps to `CORE_ELIGIBLE` — the last state
before CORE on both ladders — and `ASSURANCE_TO_MATURITY["CORE_ELIGIBLE"]` moves from `VER` to
`CANONICAL`. Eligibility is not promotion: `request_core_promotion` still refuses
unconditionally, and the `CORE_ELIGIBLE -> CORE` step remains gate-only.

## Consequences

- A primitive can now reach the state just below CORE automatically, because the claim it makes
  is checkable. CORE still cannot, because "this should become kernel" is a research judgement.
- Two schemas describe primitive records, which is a real cost. It is the cost the delivered-
  package rule is designed to impose, and the alternative — a spec that silently tracks the
  implementation — is the failure mode the rule exists to prevent.
- Consumers reading `maturity` must handle a sixth value. `ORDER` is the single place the
  sequence is defined, so ordering comparisons keep working.

## Revisit trigger

If a future delivered package (v0.3) is issued, CANONICAL should be folded into the delivered
primitive record schema at that point and this extension retired.
