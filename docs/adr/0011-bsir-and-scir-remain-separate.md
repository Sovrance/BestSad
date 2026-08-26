# ADR 0011 — BSIR and SCIR remain separate IRs

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** SRE v0.1 ADR-SRE-001; BestSad-SAISES Semantic Reconstruction Architecture v0.1 §15
**Applies to:** this repository's half of the shared architecture

## Context

The v0.1 semantic reconstruction architecture spans two systems. BestSad's BSIR represents
*computation* semantics: what a program means when the kernel runs it. SAISES' SCIR represents
*change* semantics: what a patch does to resources, authority, capabilities and interfaces.

Both are semantic graphs with content-addressed identity, both carry provenance, and both feed
evidence into an admission decision. The structural similarity is a standing invitation to
unify them into one opcode set, and the design document rejects that invitation explicitly
(§2, non-goal 1).

## Decision

BSIR and SCIR remain separate intermediate representations with independent opcode
vocabularies. They share only the SRE-Core meta-model — facts, assumptions, provenance,
traces, equivalence classes, counterexamples and certificate references — and share it as
schema contracts, not as a common instruction set.

Nothing in `src/bestsad/` defines, imports, or depends on an SCIR opcode.

## Consequences

- The two vocabularies can evolve at their own pace. A new K0 operation does not force a
  version bump on a Go analyzer that has no concept of kernel arithmetic.
- A shared opcode set would have had to be the union of both domains, and a union vocabulary
  is under-constrained in both: every BSIR consumer would carry cases for `DELEGATE` and
  `CHANGE_POLICY` that the kernel can never produce, and every SCIR consumer would carry cases
  for `fold` and `trap` that a repository diff can never produce. Exhaustiveness checks stop
  meaning anything at that point.
- The cost is duplicated meta-model plumbing in two languages. That is accepted, and ADR 0012
  records why it is preferred to the alternative.

## Revisit trigger

If a third system needs semantic reconstruction and its vocabulary genuinely overlaps one of
these two by more than roughly half, the separation is worth re-examining — but the test is
overlap in *operations*, not overlap in *shape*. Shape similarity is what the SRE-Core
meta-model already captures.
