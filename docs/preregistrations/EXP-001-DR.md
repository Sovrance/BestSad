# Bestsad-EXP-001-DR — Pre-Registration (instrument dry run)

**Committed before the first evaluation run of stages S2/S3.** Append-only from this point:
corrections are added as dated amendments, never edits. Editing the body invalidates the hash
below, which is what makes "committed in advance" checkable rather than asserted.

| Field | Value |
|---|---|
| Experiment ID | `EXP-001-DR` |
| Pre-registration hash (SHA-256) | `c8b93c6c89debfde1d5b1d60bc5514d9234fc337c464a5854300240941220a60` |
| Timestamp (UTC) | `2026-08-23T16:26:35+00:00` |
| Kernel version | `K0-1.0.0` |
| Model identity | `enumerative-search-v1` |
| Evaluator image digest | `not-containerised-see-ADR-0005` |

The machine-readable document is `EXP-001-DR.json`; this file is a rendering of it. If the two
disagree, the JSON is authoritative — it is what the hash covers.

## What this experiment is, and what it is not

This is **not** EXP-001. The model role is filled by a deterministic enumerative synthesizer,
not a language model (ADR-0007). Consequently:

- Results are **Claim Level 0/E — exploratory instrument validation**.
- They **cannot** bear on H2, H13, H14 or H15, every one of which is a claim about a *model*.
  Conditions F and H can be constructed and reconciled here, but not interpreted: a synthesizer
  is insensitive to surface form except through token counting, so compression and scaffolding
  have no mechanism by which to act on it.
- Spec §45's prohibited claims apply in full.

`BESTSAD_PREREGISTRATION_EXP001_v0.2.md` remains an unfilled template, deliberately. The real
EXP-001 is a separate, model-based experiment and needs its own pre-registration.

## Research question (for the dry run)

Under matched compute, matched scaffolding, and a compression-matched control, do
utility-selected abstractions change the verified compositional OOD solve rate of a fixed
enumerative synthesizer on families F9–F12?

## Conditions

| ID | Role | Controls | Description |
|---|---|---|---|
| A | reference | — | K0 baseline language |
| B | lower_bound_control | — | K0 + random macros, matched to D by count and size |
| C | lower_bound_control | — | K0 + MDL/frequency-extracted macros |
| D | treatment | — | K0 + utility-selected abstractions |
| E | treatment | — | D + compact projection |
| F | confound_control | C2_compression | compression-matched, no new semantics |
| G | reference_class | — | human-expert DSL, authored blind to the evolved genomes |
| H | confound_control | C3_scaffolding | scaffolding-matched variant of E |
| I | confound_control | C1_compute | A plus all compute D's evolution consumed |

Model identity is the same across all conditions. Compute matched per spec §26.6.

## Endpoints

**Primary (exactly one):** `verified_ood_solve_rate_per_compute on held-out compositional families F9-F12`

**Secondary family** (Benjamini–Hochberg FDR at q = 0.05),
declared here and not chosen afterwards: in_family_ood_rate, adversarial_rate, search_nodes, generation_tokens, language_description_length, train_only_rate.

**Exploratory** (no inferential claims): primitive_reuse, cross_family_reuse, hardcoding_incidents.

## Minimum interesting effect

**≥ 5%** absolute improvement in
verified compositional OOD solve rate at matched total compute.

Spec §24.8's provisional >=5 percentage-point threshold, retained rather than relaxed. E0 measured variance 0.005064 implies 32 seeds are required to power it; the seed count was raised to 32 rather than weakening the threshold to suit the budget.

## Sample size and power

| Field | Value |
|---|---|
| Seeds per condition | 32 |
| Variance source run | `E0-2026-08-17` |
| Measured variance | 0.005064 |
| Baseline OOD solve rate | 0.2448 (95% CI 0.208–0.271) |
| Target power | 0.8 |
| Achieved power | 0.8025 |
| Alpha (primary) | 0.05, two-sided |
| Framing | superiority |
| Powered | True |

Variance is **measured**, not assumed: E0 ran the baseline across 16 seeds before this document
was written. Note that a zero-variance measurement would have *failed* this gate rather than
passing it vacuously — n identical values are one observation repeated, not n independent ones.

## Analysis plan

1. Per-seed primary endpoint for every condition; per-seed values published.
2. Median, mean, and bootstrap CIs, all seeded for exact reproducibility.
3. Primary test: D and E versus A at matched compute.
4. **Control gates, evaluated before any claim:** the treatment must beat F, H and I. Failing
   any one means no capability claim, regardless of the A-comparison.
5. Reference comparison: D/E versus G, reported alongside D/E versus A.
6. Secondary family with BH-FDR at q = 0.05.
7. Per-primitive causal mediation with the concentration stop rule at 80% / fewer than two
   primitives.
8. Per-compute curves, not single points.

## Stopping rule

Fixed: 32 seeds per condition, all conditions run to completion. No interim analysis, no data-dependent stopping. Aborted runs are recorded with their cause, never silently discarded.

## Exclusion criteria

sandbox crash; evaluator image mismatch; ledger corruption; Exclusion for unfavourable results is prohibited; all exclusions listed with cause.

## Declared outcome interpretations

Committed in advance so the result cannot be re-narrated afterwards.

- **Positive:** primary effect met, FDR-corrected, all control gates passed, concentration test passed -> would proceed to S4 in a model-based experiment; here it licenses only the statement that the instrument can detect an effect of this size
- **Efficiency-only:** compression improved with capability inside the non-inferiority margin -> reported as an efficiency result, never as a capability result
- **Null:** effect below threshold -> recorded in docs/research/negative_results/ with the search-space constraint it implies
- **H0-consistent:** any of F, H, I matches or beats the treatment, or the concentration test fails with shortcut-shaped primitives -> recorded as consistent with H0 regardless of the aggregate effect size

## Residual confound disclosure

To be completed post-run for C1 (compute), C2 (compression), C3 (scaffolding) and C4
(contamination). Standing residuals that apply regardless of outcome are listed in
`docs/experiments/STATUS.md` and ADRs 0005, 0006 and 0007.

## Amendments

| Date | Amendment | Rationale | Pre- or post-data |
|---|---|---|---|
| | | | |
