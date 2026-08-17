# Bestsad-EXP-001 Pre-Registration (template + instance) v0.2

**Status:** TEMPLATE — fields marked `<<FILL>>` must be completed, committed, hashed, and timestamped **before the first evaluation run**. After that commit, this file is append-only: corrections are added as dated amendments, never edits.

**Normative under:** Architecture Spec v0.2 §26.5. A run without a committed pre-registration is exploratory (Claim Level E) and may not be described as confirming anything.

---

## 1. Identity

| Field | Value |
|---|---|
| Experiment ID | Bestsad-EXP-001 |
| Pre-registration hash | `<<FILL: sha256 of this file at commit>>` |
| Timestamp (UTC) | `<<FILL>>` |
| Kernel version | K0 `<<FILL>>` |
| Model identity + hash | `<<FILL>>` |
| Evaluator image digest | `<<FILL>>` |
| Analysis code revision | `<<FILL>>` |

---

## 2. Research question

Can automatically evolved semantics-preserving abstractions improve **verified compositional out-of-distribution** program synthesis for a fixed model and fixed semantic kernel, at matched total compute, matched in-context scaffolding, and against a compression-matched control?

## 3. Hypotheses under test

Primary: **H2** (abstraction discovery), evaluated against **H13** (compression is not capability), **H14** (scaffolding invariance), and **H15** (representation beats extra search).

## 4. Conditions

| ID | Condition | Role |
|---|---|---|
| A | K0 baseline | reference |
| B | K0 + random macros, count/size matched | lower-bound control |
| C | K0 + MDL/frequency-extracted macros | lower-bound control |
| D | K0 + utility-selected abstractions | **treatment** |
| E | D + compact projection | **treatment** |
| F | Compression-matched, no new semantics | confound control (C2) |
| G | Human-expert DSL, author blind to genomes | reference class |
| H | Scaffolding-matched variants of A–E | confound control (C3) |
| I | A + all compute spent by D's evolution, spent on search | confound control (C1) |

Model weights identical across all conditions. Compute matched per spec §26.6.

**Condition G authoring protocol:** author is blind to evolved genomes; time-box `<<FILL: hours>>`; author sees the same task-family documentation the evolution saw; the DSL is frozen before any evaluation run.

## 5. Endpoints

**Primary (exactly one):** `verified_ood_solve_rate_per_compute` on held-out compositional families F9–F12.

**Secondary family (FDR-controlled at q = 0.05, Benjamini–Hochberg):** raw verified solve rate; in-family OOD solve rate; search nodes expanded; generation tokens; primitive reuse rate; cross-family reuse; verification cost; language description length; `compression_ratio`; `capability_delta`.

**Exploratory (no inferential claims):** everything else.

## 6. Minimum interesting effect

Pre-registered as one or both of:

- ≥ 5 percentage points absolute improvement in verified compositional OOD solve rate at matched total compute; **or**
- ≥ 15% reduction in total experimental compute at a pre-registered non-inferior solve rate, margin δ = `<<FILL>>` percentage points, one-sided non-inferiority.

Thresholds are project operating values, not literature constants. Revisit after E0 variance is measured.

## 7. Sample size and power

| Field | Value |
|---|---|
| Seeds per condition | `<<FILL: from power analysis, not convenience>>` |
| Variance estimate source | E0 measured variance, run `<<FILL>>` |
| Target power | 0.80 (default) |
| Alpha (primary) | 0.05, two-sided unless non-inferiority framing declared |
| Framing per arm | `<<FILL: superiority / non-inferiority>>` |

Non-inferiority is preferred to equivalence wherever the scientific question is genuinely "no worse," because equivalence framing requires materially larger samples at the same margin and power.

**If the achievable seed count cannot power the minimum interesting effect, record that here and re-scope. Do not run underpowered and interpret the point estimate.**

## 8. Analysis plan

1. Compute per-seed primary endpoint for every condition.
2. Report median, mean, per-seed values, and bootstrap CIs. Publish per-seed data.
3. Primary test: D and E versus A, at matched compute.
4. **Control gates, evaluated before any claim:** the treatment must beat F, H-equalized variants, and I. Failing any one of these means no capability claim, regardless of the A-comparison.
5. Reference comparison: D/E versus G, reported alongside D/E versus A.
6. Secondary family with BH-FDR at q = 0.05.
7. Per-primitive causal mediation (spec §42) with the concentration stop rule at 80% / fewer than two primitives.
8. Per-compute curves, not single points.

## 9. Stopping rule

`<<FILL>>` — fixed in advance. No data-dependent stopping. If a run is aborted for infrastructure reasons, record the abort and its cause; aborted runs are reported, not silently discarded.

## 10. Exclusion criteria

A run/seed is excluded only for pre-specified infrastructure failure (sandbox crash, evaluator image mismatch, ledger corruption). Exclusion for unfavourable results is prohibited. All exclusions listed with cause in the final report.

## 11. Residual confound disclosure

| Confound | Control | Residual (to be filled post-run) |
|---|---|---|
| C1 compute | condition I | `<<FILL>>` |
| C2 compression | condition F | `<<FILL>>` |
| C3 scaffolding | condition H | `<<FILL: e.g. "equalized to within N tokens">>` |
| C4 contamination | frozen hidden benchmark, fresh seeds, family holdouts | `<<FILL>>` |

## 12. Declared outcome interpretations

Committed **in advance**, so the result cannot be re-narrated afterwards:

- **Positive:** primary effect met, FDR-corrected, all control gates passed, concentration test passed. → Proceed to stage S4.
- **Efficiency-only:** compression improved, capability within non-inferiority margin. → Reported as an efficiency result. Not a capability claim.
- **Null:** effect below threshold. → Record in the negative-result ledger with the implied search-space constraint.
- **H0-consistent despite aggregate effect:** any control matches treatment, or the concentration test fails with shortcut-shaped primitives. → Recorded as consistent with H0.

## 13. Amendments

| Date | Amendment | Rationale | Pre- or post-data |
|---|---|---|---|
| | | | |
