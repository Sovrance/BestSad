# Negative result: EXP-001-DR (EXP-001-DR-2026-08-23)

**Recorded:** 2026-08-23
**Outcome class:** `h0_consistent`
**Claim level:** 1
**Pre-registration hash:** `c8b93c6c89debfde1d5b1d60bc5514d9234fc337c464a5854300240941220a60`

Spec §44 makes this record a deliverable, not a courtesy. Gate G6 is not satisfied if the
negative-result ledger is empty after a stage completes with null findings.

## Hypothesis under test

**H2 (abstraction discovery), as instantiated for a deterministic enumerative synthesizer.** Do utility-selected, semantics-preserving abstractions mined from curriculum solutions improve the verified *compositional* out-of-distribution solve rate on held-out families F9-F12, at matched compute, matched scaffolding, and against a compression-matched control?

This is **not** a test of H2 for a language model. Per ADR-0007 the model role is filled by an enumerative searcher, so the result speaks to the instrument and to search, not to models.

## Conditions run

A, B, C, D, E, F, G, H, I

Seeds per condition: **32**. Per-seed values are published in the run report rather than
summarised away.

## Result

| Condition | Verified compositional OOD solve rate | Model-side tokens |
|---|---:|---:|
| A  K0 baseline | 0.2370 | 103 |
| B  random macros (count/size matched) | 0.2292 | 100 |
| C  MDL-extracted macros | 0.2344 | 100 |
| **D  utility-selected abstractions** | **0.2422** | 104 |
| **E  D + compact projection** | **0.2422** | 65 |
| F  compression-matched, no new semantics | 0.2370 | 64 |
| G  human-expert DSL | **0.2917** | 126 |
| H  scaffolding-matched | 0.2422 | 65 |
| I  search-only, compute-matched | 0.2370 | 102 |

**Primary endpoint.** D vs A: **+0.0052** (95% CI -0.0260 to +0.0391, p = 0.76). E vs A is identical. The pre-registered minimum interesting effect was +0.05, so the observed effect is roughly one tenth of the threshold and its interval comfortably spans zero.

**Every control gate failed to be beaten.** F (+0.0052, p = 0.76), H (+0.0000, p = 1.00) and I (+0.0052, p = 0.76). Under the pre-registered analysis plan this alone forecloses a capability claim, whatever the A-comparison had shown.

**The reference class beat both treatments.** G exceeds D/E by +0.0495 (p = 0.022) — roughly **9.5x** the margin D/E hold over A. Spec 24.9 names this exact pattern as a falsification signal: 'condition G dominating D/E by a margin larger than D/E's margin over A'. G also solved adversarial siblings at 0.109 against 0.010 for every evolved condition, so its advantage is generalisation, not a shortcut.

**Compression moved; capability did not.** E compressed model-side tokens 1.57x over A with a capability delta of +0.005, inside the 0.02 non-inferiority margin — classified `efficiency_only`, never a capability result. Condition F reproduced almost exactly the same compression (64 vs 65 tokens) while introducing **no new semantics at all**, and landed on precisely A's solve rate. The token saving is attributable to the projection, not to the abstractions.

**Per-primitive attribution.** 15 abstractions recurred in at least two seeds and were ablated: 3 positive, 0 negative, 12 null. The concentration test passed (top-1 share 0.40, verdict `attributable`) — the small effect is not carried by one shortcut-shaped primitive; it is simply small.

**Cross-seed abstraction stability (spec 34 Q2).** 28 distinct abstractions across 32 seeds; **13 appeared in exactly one seed** and the most stable appeared in 20 of 32 (62%). Discovery is markedly seed-sensitive, consistent with the library-learning literature the companion cites.

## Confound controls satisfied

- **C2 compression (condition F): satisfied.** F's primitive set is identical to A's under semantic hash, verified structurally before the run.
- **C3 scaffolding (condition H): satisfied.** Equalised to within 57 tokens of the common target, padded rather than truncated, delivered budget logged per condition.
- **C4 contamination: satisfied.** Held-out families are structurally disjoint from the curriculum, not merely unseen seeds; abstractions were mined only from curriculum solutions; instances do not exist until a seed generates them.
- **C1 compute (condition I): NOT satisfied — disclosed residual of 75%.** See below.

## Why this is not a failure of the instrument

**Condition I could not be compute-matched, and the reason is structural.**

The reconciliation check `compute(I) == compute(A) + compute(evolution in D)` failed on all 32 seeds. It caught two distinct defects, both now fixed and regression-tested:

1. `node_budget` is a *per-task* budget while inherited evolution compute is a *total*, so condition I was initially handed a full extra evolution budget on every one of its 26 tasks — 2.8x over the identity.
2. A checkpoint keyed on the genome alone collided across configurations, and served a stale record for a re-run under a corrected budget.

After both fixes the residual inverted: condition I now *underspends* by 75%. It is given the compute and cannot absorb it. A bounded-depth enumerative search saturates — once every term up to its depth limit has been enumerated, additional nodes buy nothing. Granting an extra level of depth did not close the gap either.

**This does not threaten the conclusion, and the run says so quantitatively.** Condition I was measured at three budgets spanning 145k, 282k and 1,135k search nodes — a 7.8x range straddling both sides of the matched target — and returned **0.2370 at every one**, identical to A. No amount of additional search in the baseline language changed the outcome, so the direction and size of the compute residual are immaterial here.

The finding that generalises: **confound control C1 is not implementable against a saturating enumerative searcher.** For a language model it is, because additional sampling always consumes additional compute. This is a limit of the stand-in model in ADR-0007, not of the protocol.

## Search-space constraint this implies

Recorded against open question 20 (what negative results should permanently constrain future Bestsad search spaces).

1. **Frequency- and utility-ranked subtree extraction over solved curriculum programs does not, on its own, produce abstractions that transfer to structurally held-out compositional families.** Three selection regimes — random, MDL-compression-optimal, and counterfactual-utility — landed within 1.3 percentage points of each other and of the bare kernel. Where the regimes differ in principle, they did not differ in effect. Future search should not assume that a better *ranking* over the same candidate pool is the missing ingredient; the constraint appears to lie in the candidate pool itself, which is built from subtrees of programs the searcher could already solve.

2. **A hand-designed DSL of three obvious aggregations beat every evolved genome.** The abstractions a competent person writes down first (`sum`, `maximum`, `count`) outperformed 32 seeds of automated discovery. Any future claim of discovery value must clear this reference class, not merely the bare kernel — which is exactly why spec 40.2 requires G to be reported alongside A.

3. **Abstractions mined from solved curriculum programs are bounded by what the searcher already solves.** The held-out families that stayed unsolved (F9, F11, F12) need compositional depth the baseline never reached, so no subtree of a baseline solution could encode them. Mining solutions cannot yield abstractions for problems outside the solvable set. This is the sharpest constraint the run implies, and it applies to any wake-sleep-shaped pipeline, not just this one.

## What would change the answer

- **Run EXP-001 proper, with a language model.** The three findings above concern search. H13, H14 and H15 are claims about models and remain untested: conditions F and H were constructed and reconciled here but cannot be *interpreted*, because a synthesizer is insensitive to surface form except through token counting.
- **Widen the candidate pool beyond subtrees of solved programs** — constraint 3 above predicts this is where the ceiling is. Candidates derived from task structure or from failed search frontiers would test it directly.
- **Strengthen condition C before it is trusted as a lower bound.** ADR-0006's extractor ranks candidates independently rather than searching for a jointly optimal library. Here it hardly matters — C, B and D are within noise of each other — but a future run where D beats C must not rest on a weakened C.
- **Replace the compute-matching control for saturating searchers**, or accept that C1 is only testable against a model whose compute scales with sampling.
