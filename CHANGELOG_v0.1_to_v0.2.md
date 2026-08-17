# Changelog: Bestsad v0.1 → v0.2

All v0.1 content is preserved. v0.2 is additive and corrective, never subtractive: no v0.1 hypothesis, principle, or gate was removed.

---

## Added hypotheses

| ID | Hypothesis | Why |
|---|---|---|
| H13 | Compression is not capability | Tokenizer studies show token compression moves speed, effective context and memory far more than it moves code-generation accuracy. Bestsad must not bank a compression win as a capability win. |
| H14 | Scaffolding invariance | Models reach very high parse validity on unseen DSLs from prompt material alone. Without equalized scaffolding, "evolved language wins" may be prompt engineering. |
| H15 | Representation beats extra search | Evolutionary coding agents reach strong results with the language held fixed. That is the rival explanation, and it must be a condition rather than a citation. |

## Added experimental conditions (mandatory for EXP-001)

- **F** compression-matched (no new semantics, token count matched to E)
- **G** human-expert DSL, blind-authored and time-boxed — a reference class, not a control
- **H** scaffolding-matched across all conditions, with delivered budget logged
- **I** search-only baseline given exactly the compute that genome evolution consumed in D

## Changed

| Area | v0.1 | v0.2 | Rationale |
|---|---|---|---|
| Semantic Gain (§21.4) | Ratio of capability delta over description/learning/verification cost | MDL formulation over *held-out solution* description length, with training-corpus savings discounted by `kappa` | The v0.1 form rewarded corpus compression, which H13 declines to count. MDL generalization results give a principled alternative. |
| Primary endpoint (§24.6) | Verified OOD solve rate per compute, unseen seeds and held-out families | Same metric, but scored on **verified compositional** held-out families | Published results show verified synthesis collapsing by roughly an order of magnitude from single-function to compositional tasks. That is where a real representational effect should show and a compression artifact should not. |
| Ablation ladder (§25) | A5 model fine-tune → A6 tokenizer | A5 tokenizer (frozen model), A6 adapted model (original tokenizer), A7 combination, A8 compiler | v0.1 introduced fine-tuning before tokenizer change, making the two inseparable. The split makes open question 15 answerable. |
| Statistics (§26) | Seeds, distributions, best-of-N disclosure, compute ledger | Adds pre-registration requirement, compute-matching policy with per-compute curves, BH-FDR control, power and non-inferiority sizing | v0.1 had reproducibility discipline but no inferential discipline; H1–H15 × A0–A8 implies dozens of comparisons. |
| Tooling (§36) | Generic recommendations | Explicit adopt list plus a build-vs-adopt ADR rule | Bestsad's contribution is integration, not reimplementation. |
| Open questions (§34) | 20 unlabelled questions | Each tagged OPEN / PARTIAL / LEAN-NEG / TESTABLE-NOW | Several are already partly answered externally; two lean against Bestsad's optimistic reading and should be planned for accordingly. |

## Added sections

- **Spec §39** Prior-art positioning and novelty claim, with a per-component table of what may not be claimed
- **Spec §40** Confound control plane (C1 compute, C2 compression, C3 scaffolding, C4 contamination) and residual-disclosure rule
- **Spec §41** Evidence taxonomy: what is supported, contested, and unproven
- **Spec §42** Causal attribution plane: per-primitive mediation and the gain-concentration stop rule
- **Spec §43** Staged funding gates S1–S5 for EXP-001
- **Spec §44** Negative-result ledger
- **Spec §45** Claims register (prohibited claims)
- **Companion Part II, §§29–37** prior-art audit, the adverse library-learning literature, proof methodology, three-way fit, adversarial review, build-vs-adopt register, 30 new annotated sources

## Added artifacts

- `AGENTS.md`
- `IMPLEMENTATION_PLAN_v0.2.md`
- `BESTSAD_PREREGISTRATION_EXP001_v0.2.md`
- `schemas/preregistration.schema.json`
- `schemas/control_condition.schema.json`
- `schemas/causal_attribution.schema.json`
- `schemas/compute_ledger.schema.json`
- Source ledger extended from 47 to 77 entries (S48–S77)

## Status changes

- Companion §22's ten-part gap now carries a v0.2 re-audit note: it **still holds as an integration claim**, but items 3, 6, 7 and 10 have credible standalone instantiations elsewhere and items 1 and 4 have near-misses. It is decaying evidence and must be re-swept before every Gate transition.
- The balance of evidence is recorded explicitly: *supported* that constrained canonical representations reduce error rates and IR grounding improves robustness; *contested* that learned abstractions improve generalized capability at matched compute; *unproven* the strong Bestsad thesis.

## Not changed

The trusted semantic kernel, the evaluator trust boundary, the definition of correctness, design principles P1–P10, the trust/mutability model, gates G0–G6, and the v0.1 non-goals all stand unmodified.
