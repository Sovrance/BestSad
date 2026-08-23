# EXP-001-DR run report

**Run:** `EXP-001-DR-2026-08-23` · **Claim level:** 1 · **Outcome:** `h0_consistent`
**Pre-registration:** `c8b93c6c89debfde1d5b1d60bc5514d9234fc337c464a5854300240941220a60` (committed before S2/S3; verified at analysis time)

> **This is not EXP-001.** The model role is a deterministic enumerative synthesizer, not a
> language model (ADR-0007). Nothing here bears on H2, H13, H14 or H15 for a model, and spec
> §45's prohibited claims apply in full. What it does establish is that the instrument runs
> end to end, that its controls bind, and three constraints on the search space — recorded in
> `docs/research/negative_results/2026-08-23-EXP-001-DR-abstractions-null.md`.

## Headline

The treatment moved the primary endpoint by **+0.0052** (95% CI −0.0260 to +0.0391, p = 0.76)
against a pre-registered threshold of **+0.05**. **No control was beaten.** The human-expert
DSL beat both treatments by ~9.5× the margin they hold over the baseline. The reporting gate
certified the run as **consistent with H0**, and refused any capability claim.

## E0 baseline and power

Measured before the pre-registration was written, as spec §26.8 requires.

| | |
|---|---|
| Baseline verified compositional OOD rate | 0.2448 (95% CI 0.208–0.271) |
| Measured variance | 0.005064 |
| Seeds | 32 (raised from 8 so the spec's 5-point threshold stayed intact) |
| Achieved power | 0.8025 against a target of 0.80 |

## Results

| Condition | Verified OOD | Tokens | Search nodes | Adversarial | Train-only |
|---|---:|---:|---:|---:|---:|
| A | 0.2370 | 103 | 204627 | 0.010 | 0.096 |
| B | 0.2292 | 100 | 205486 | 0.010 | 0.102 |
| C | 0.2344 | 100 | 204152 | 0.010 | 0.099 |
| D | 0.2422 | 104 | 201259 | 0.010 | 0.104 |
| E | 0.2422 | 65 | 201259 | 0.010 | 0.104 |
| F | 0.2370 | 64 | 204627 | 0.010 | 0.096 |
| G | 0.2917 | 126 | 181053 | 0.109 | 0.138 |
| H | 0.2422 | 65 | 201259 | 0.010 | 0.104 |
| I | 0.2370 | 102 | 145444 | 0.010 | 0.094 |

Per-seed values for every condition are published in `artifacts/report.json`
(`per_seed_published`), not summarised away.

### Primary endpoint

| Comparison | Effect | 95% CI | p | Meets pre-registered ≥5 points? |
|---|---:|---|---:|---|
| D vs A | +0.0052 | [−0.0260, +0.0391] | 0.76 | no |
| E vs A | +0.0052 | [−0.0260, +0.0391] | 0.76 | no |

### Control gates — evaluated before any claim

| Control | Confound | Beaten? | Effect | p |
|---|---|---|---:|---:|
| F compression-matched | C2 | **no** | +0.0052 | 0.76 |
| H scaffolding-matched | C3 | **no** | +0.0000 | 1.00 |
| I search-only | C1 | **no** | +0.0052 | 0.76 |
| B random macros | — | no | +0.0130 | 0.46 |
| C MDL macros | — | no | +0.0078 | 0.65 |
| G human-expert DSL | reference class | G **beats** D by +0.0495 | +0.0495 | 0.022 |

### Compression and capability, reported as a pair (§21.6)

| Condition | compression_ratio | capability_delta | Classification |
|---|---:|---:|---|
| D | 0.98 | +0.0052 | capability_candidate |
| E | **1.57** | +0.0052 | **efficiency_only** |

Condition F reached essentially the same compression (64 vs 65 tokens) carrying **no new
semantics**, and scored exactly A's solve rate. The token saving belongs to the projection.

### Secondary family, BH-FDR at q = 0.05

| Endpoint | p | BH critical value | Verdict |
|---|---:|---:|---|
| language_description_length | 6.66e-16 | 0.0083 | rejected |
| in_family_ood_rate | 0.202 | 0.0167 | not rejected |
| search_nodes | 0.602 | 0.0250 | not rejected |
| train_only_rate | 0.705 | 0.0333 | not rejected |
| generation_tokens | 0.776 | 0.0417 | not rejected |
| adversarial_rate | 1 | 0.0500 | not rejected |

Only language description length survives correction — the evolved genomes are *longer*, which
is a cost, not a capability.

## Residual confound disclosure (§40.3)

- **C1 compute — NOT satisfied, 75% residual.** Condition I is given the compute and cannot
  absorb it: a bounded-depth enumerative search saturates. Measured at 145k / 282k / 1,135k
  nodes — a 7.8× range — it returned **0.2370 every time**, identical to A, so the residual does
  not affect the conclusion. The general finding is that control C1 is not implementable against
  a saturating searcher; for a model it is.
- **C2 compression — satisfied.** F's primitive set is identical to A's under semantic hash.
- **C3 scaffolding — satisfied**, equalised to within 57 tokens, padded not truncated, delivered
  budget logged per condition.
- **C4 contamination — satisfied.** Structurally disjoint held-out families; abstractions mined
  only from curriculum solutions; instances generated fresh from seeds.
- **Standing:** ADR-0005 (sandbox is not a kernel boundary), ADR-0006 (condition C's extractor is
  weaker than it should be — biased *toward* the treatment), ADR-0007 (surface-token proxy).

## Per-primitive attribution (§42)

15 recurring abstractions ablated: **3 positive, 0 negative, 12 null**. Concentration test
**passed** (top-1 share 0.40, `attributable`) — the small effect is not carried by one
shortcut-shaped primitive, it is simply small. The full table, nulls included, is in
`artifacts/attribution.json`; selective reporting would be a protocol violation.

**Cross-seed stability (§34 Q2):** 28 distinct abstractions over 32 seeds; 13 appeared in
exactly one seed, the most stable in 20 of 32 (62%). Discovery is markedly seed-sensitive.

## Staged funding gates (§43), evaluated honestly

| Stage | Gate to proceed | Verdict |
|---|---|---|
| **S1** E0 baseline + variance | Variance measured; power analysis passes for the pre-registered minimum interesting effect | **passed** — variance 0.005064 measured over 16 seeds; 32 seeds give power 0.8025 for a 5-point effect |
| **S2** A–E plus F, H, I | Pre-registered primary effect met, FDR-corrected, across the pre-registered seed count; no control matches treatment | **failed** — effect +0.0052 against a +0.05 threshold, and all three of F, H and I match the treatment |
| **S3** G reference class; per-primitive mediation | Concentration test passed; D/E margin over A not dwarfed by G's margin over D/E | **failed** — the concentration test passed, but G's margin over D/E (+0.0495) is ~9.5× D/E's margin over A (+0.0052), which is exactly the dwarfing the gate is written to catch |
| **S4** tokenizer / adapted model | S2 **and** S3 both passed | **not reached** — correctly not started |
| **S5** compiler evolution, cross-model transfer | S4 passed | **not reached** |

The expensive arms stay gated. That is the staging working: S2 and S3 cost roughly two hours of
CPU between them and stopped the program from spending anything on fine-tuning.

## Defects this run exposed

Both were caught by the instrument's own checks, and both are fixed and regression-tested:

1. **Condition I was over-funded 2.8×** — `node_budget` is per-task, inherited evolution compute
   is a total. The §26.6 reconciliation check caught it. This is precisely what that check is for.
2. **Checkpoint keys collided across configurations** — keyed on the genome alone, so a re-run of
   condition I under a corrected budget returned a stale record in zero seconds. A checkpoint
   that returns the wrong answer instantly is worse than no checkpoint.
