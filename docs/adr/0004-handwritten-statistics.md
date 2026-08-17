# ADR 0004 — Hand-written statistics rather than SciPy

**Status:** Provisional
**Date:** 2026-08-17
**Governs:** spec §36 build-versus-adopt rule; `AGENTS.md` build-versus-adopt

## Context

The build-versus-adopt rule says: if you are about to hand-write a component that exists in
mature form, stop and write an ADR justifying it. SciPy is mature, and it supplies Welch's
t-test, the t distribution, and bootstrap resampling. This ADR is that justification.

M9 needs: Welch's t-test, a one-sided non-inferiority test, Benjamini–Hochberg FDR control, a
percentile bootstrap, and a two-sample power calculation over measured variance.

## Decision

Implement these in the standard library (`src/bestsad/stats/inference.py`), and do not depend
on SciPy or NumPy.

Three reasons, in order of weight:

1. **The evaluator image must be hermetic and small.** Spec §27.3 requires pinned versions and
   recorded hashes, and the evaluator runs candidate-adjacent code under a restricted policy. A
   SciPy/NumPy stack is a large native dependency surface to pin, hash, and audit for a handful
   of formulas — and native extension code is precisely what the audit-hook sandbox (ADR-0005)
   cannot supervise.
2. **Reproducibility of published intervals.** Spec §26.2 requires per-seed values to be
   published so any reader can recompute. A seeded pure-Python percentile bootstrap reproduces
   *exactly* on any machine; a library bootstrap reproduces exactly only if the reader pins the
   same version and RNG implementation.
3. **The quantity of code is small and exactly specified.** Roughly 200 lines, every one of
   which is a formula with a closed-form check.

The cost is accepted deliberately: hand-written statistics can be wrong in ways a library is
not. The mitigation is that **every function is tested against an independently computed
value**, not against itself — the Welch example in `tests/stats/test_inference.py` carries
hand-computed expectations (t = −2.035662, df = 15.4979), and the quantile and t-CDF functions
are checked against published table values. Two of those expectations were wrong when first
written from memory and were corrected against an independent hand computation; that is the
process working, and it is the reason the tests assert numbers rather than properties.

## Consequences

- `pip install bestsad` pulls in `jsonschema` only.
- Anything needing a distribution not implemented here (e.g. exact permutation tests, mixed
  models) is a reason to revisit, not to quietly add an approximation.

## Revisit trigger

Re-open when the analysis needs a method whose implementation is not a short closed form —
hierarchical models across seeds and families would qualify. At that point adopt the library
and keep these implementations as cross-checks rather than deleting them.
