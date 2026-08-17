# ADR 0002 — Python-first implementation for the research instrument

**Status:** Provisional
**Date:** 2026-08-17
**Governs:** spec §36 (recommended first implementation choices)

## Context

Spec §36 recommends "Rust or a Rust/Python split for core + experiment orchestration". That
recommendation is explicitly labelled an engineering default, not a research conclusion.

The instrument's cost profile, per §43 and the implementation plan's cost note, is expected to
be **inference-bound**, not interpreter-bound: the dominant cost of S1–S3 is model sampling,
not the reference interpreter. The components that must be fast are the ones that are not yet
built (the e-graph engine, M11, which spec §36 says to adopt rather than write; and the MLIR
lowering path, M12).

The components that must be *auditable* are the ones being built now: the K0 reference
interpreter, the canonical semantic hash, the confound control plane, and the statistics. A
reviewer's ability to read the control plane and confirm that condition I really does spend
condition D's evolution compute matters more at this stage than its throughput.

## Decision

Implement M0–M10 as a single Python package (`src/bestsad/`), Python ≥ 3.11, with dependencies
limited to `jsonschema` (schema validation) and `pytest` (tests).

The K0 reference interpreter is written in Python and is the **normative** implementation for
v0.2. Should a faster kernel be introduced later in another language, it becomes a second
implementation that must agree with this one under the M1 differential test — the reference
does not move to the new language by default, because moving the semantic anchor is exactly
the thing spec §8.4 says starts a new experiment lineage.

## Consequences

- The whole instrument is readable end to end without a toolchain build.
- The differential sweep (M1: 10⁵ programs) runs in minutes rather than seconds. Acceptable at
  this scale; it is marked `slow` and runs at reduced count by default in CI with the full
  count run explicitly.
- If the interpreter later becomes the bottleneck, the mitigation is a second implementation
  checked against this one, not a rewrite of the anchor.

## Revisit trigger

Re-open this ADR when either:

1. measured E0 numbers (M3) show reference execution exceeding ~10% of total experimental
   compute, or
2. M11/M12 land and the Python/native boundary starts crossing per-node rather than per-run.
