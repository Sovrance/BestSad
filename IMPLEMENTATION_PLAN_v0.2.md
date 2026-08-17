# Bestsad v0.2 Implementation Plan

Work breakdown for a coding agent. Milestones are ordered so that the **cheap falsifiers come first**: M1–M5 can already kill the thesis, and nothing expensive is built until they pass.

Each milestone lists acceptance tests. A milestone is not done until its acceptance tests pass and its artifacts are content-addressed in the ledger.

---

## M0 — Repository skeleton

Build the tree in spec §28. Add `docs/adr/`, `docs/research/negative_results/`, `docs/preregistrations/`.

**Acceptance:** CI runs; `docs/adr/0001-record-architecture-decisions.md` exists; the hidden evaluator lives in a separate repo or protected namespace with no import path from the candidate side.

---

## M1 — Semantic Kernel K0 + reference interpreter

Implement K0 per spec §8 with a deterministic reference interpreter returning `Value | Trap` plus an execution trace hash.

**Acceptance:**
- Differential test: 10⁵ procedurally generated programs, interpreter is deterministic across runs and platforms.
- Trap behaviour is total: no program produces an undefined result.
- **Gate G0 (semantic anchor) satisfied.** Nothing downstream may start before this.

---

## M2 — BSIR + canonical semantic hash

Node model, canonicalization, hashing (spec §9). Human projection implemented but explicitly non-canonical (P8).

**Acceptance:**
- Semantically equivalent graphs that differ only in projection hash identically.
- Semantically distinct graphs collide at a rate consistent with the hash width.
- Round-trip: BSIR → projection → BSIR is identity on the canonical hash.
- A test asserts that no code path treats the human projection as canonical semantics.

---

## M3 — Task generator + E0 baseline + variance measurement

Procedural generator for families F1–F8 (curriculum) and F9–F12 (held-out compositional). Fresh seeds per instance. Run the E0 baseline.

**Acceptance:**
- Held-out families are structurally compositional, not just unseen seeds.
- Adversarially similar tasks exist where a shortcut primitive should fail.
- **Variance measured**, not assumed. Power analysis for the pre-registered minimum interesting effect is computable from this output.
- **Gate G2 (baseline reproducibility) satisfied.**

---

## M4 — Evaluator + integrity plane

Frozen hidden benchmark, evolving curriculum, adversarial integrity suite (spec §20). Sandbox per §27.

**Acceptance:**
- Red-team test: a deliberately malicious candidate attempting to read hidden tests, touch evaluator state, reach the network, or persist across resets **fails on every vector**, and the integrity monitor fires.
- Hardcoded-test-pattern detection catches a planted hardcoding candidate.
- Contamination controls: canary strings absent from candidate-visible surfaces; time-partitioned split honoured.
- **Gate G1 (evaluator integrity) satisfied.**

---

## M5 — Confound control plane ⚠️ highest-value milestone

Implement conditions F, G, H, I as first-class experimental conditions (spec §40), not as afterthoughts.

- **F** compression-matched: surface shortening over K0 with no new semantics; token count matched to E within a reported tolerance.
- **G** human-expert DSL: harness for a blind, time-boxed human-authored DSL; frozen before evaluation.
- **H** scaffolding matcher: equalizes grammar-description token budget, worked-example count and difficulty, retry/repair policy, decoding constraints across conditions; **logs the delivered budget per condition**.
- **I** search-only baseline: meters the compute consumed by genome evolution in D and spends exactly that on additional search/sampling in condition A.

**Acceptance:**
- Compute meter reconciles: `compute(I) == compute(A) + compute(evolution in D)` within a stated tolerance.
- Scaffolding matcher reports residual difference in tokens per condition.
- Condition F provably introduces no new semantics: its genome's primitive set is identical to A's under semantic hash.
- Harness can run a condition that **beats the treatment** and report it without special-casing.

---

## M6 — Abstraction discovery + primitive lifecycle

Extraction, anti-unification, utility scoring, promotion evidence (spec §11). Condition C uses a real MDL-optimal extractor, not a strawman.

**Acceptance:**
- Reuse is measured directly per spec H2, never inferred from accuracy.
- Promotion requires the evidence set in §11.1; no automatic CORE promotion (§11.2).
- Suspicious-primitive rule (§22.2) fires on a planted shortcut primitive.
- **Gate G3 (abstraction controls) satisfied.**

---

## M7 — MDL Semantic Gain (SG-v2)

Implement spec §21.4 with a fixed, pre-registered coding scheme and `kappa`.

**Acceptance:**
- A primitive that only compresses the training corpus scores ≤ 0.
- A primitive that shortens held-out solution descriptions by more than its own description cost scores > 0.
- Coding scheme and `kappa` are committed before EXP-001 and hashed into the run manifest.

---

## M8 — Causal attribution plane

Per-primitive direct/indirect effects, paired ablations, concentration test (spec §42).

**Acceptance:**
- Ablation re-expands call sites to the K0 equivalent correctly (verified by semantic hash equality).
- Concentration stop rule implemented and testable on synthetic data where the gain is deliberately concentrated in one shortcut primitive.
- Report includes null and negative primitives.

---

## M9 — Statistics and reporting

Pre-registration tooling (hash + timestamp + append-only amendments), BH-FDR, bootstrap CIs, per-compute curves, per-seed publication.

**Acceptance:**
- Reporting pipeline **refuses to emit a confirmatory report** without a committed pre-registration hash.
- Reporting pipeline refuses to emit a capability claim when F, H, or I is missing or unbeaten.
- `compression_ratio` and `capability_delta` cannot be emitted separately.

---

## M10 — EXP-001 stage S2/S3 execution

Run A–I on ablation nodes A0–A4 per spec §43.

**Acceptance:** the staged gate in §43 is evaluated honestly, and the outcome — including a null — is written to `docs/research/negative_results/` with the implied search-space constraint.

---

## Deferred behind gates (do not build early)

- **M11** equality-saturation engine integration (adopt, don't build) — needed for A4/H6.
- **M12** MLIR lowering path + translation validation — needed for the machine leg.
- **M13** tokenizer node A5, adapted model A6, combination A7 — **gated on S2 and S3 passing**. This is the first materially expensive milestone.
- **M14** compiler policy evolution A8, cross-model transfer H9 — gated on S4.

---

## Cost note

The EXP-001 domain is synthetic and generated from K0, and evolutionary search cost is dominated by inference sampling rather than training. S1–S3 are therefore expected to be inference-bound and moderate on a small open-weight model; M13 onward introduces fine-tuning and is where cost changes character. **This is a planning inference, not a measured figure** — replace it with E0's measured numbers as soon as M3 lands.
