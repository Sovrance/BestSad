# Implementation status against `IMPLEMENTATION_PLAN_v0.2.md`

Last updated: 2026-08-23.

## Complete, with acceptance tests passing

| Milestone | State | Acceptance evidence |
|---|---|---|
| **M0** Repository skeleton | Done | Tree per spec §28 mapped onto `src/` (ADR-0003); `docs/adr/`, `docs/research/negative_results/`, `docs/preregistrations/` exist; CI defined in `.github/workflows/ci.yml`; hidden evaluator has no import path from the candidate side (`tests/integrity/test_trust_boundary.py`) |
| **M1** K0 + reference interpreter | Done | `tests/kernel/` — determinism within and across processes (varying `PYTHONHASHSEED`), totality, trap taxonomy, pinned kernel hash. Full 10⁵-program sweep marked `slow`, run as its own CI job. **Gate G0 satisfied.** |
| **M2** BSIR + canonical semantic hash | Done | `tests/bsir/` — projection-invariant hashing, alpha-normalisation, zero collisions over 4000 programs, four projections round-tripping to an identical canonical hash, explicit P8 non-canonicality test |
| **M3** Task generator + E0 + variance | Done | `tests/tasks/` and `Exp001Runner.stage_s1`; families F1–F8 curriculum, F9–F12 structurally held out, adversarial siblings; variance **measured**, and a degenerate zero-variance measurement is refused rather than reported as infinite power |
| **M4** Evaluator + integrity plane | Done | `tests/integrity/` — every vector in `AGENTS.md` invariant 2 attempted and blocked, monitor fires on each, planted hardcoding candidate detected, canary absent from candidate-visible surfaces. **Gate G1 satisfied** *subject to ADR-0005's disclosed residual* |
| **M5** Confound control plane | Done | `tests/conditions/` — compute reconciliation `compute(I) == compute(A) + compute(evolution in D)`, scaffolding residual disclosed per condition, condition F proven to add no new semantics under semantic hash |
| **M6** Abstraction discovery + lifecycle | Done | `tests/abstraction/` — semantic dedup, anti-unification, three distinct selection regimes, suspicious-primitive rule, `promote()` that can never return CORE. **Gate G3 satisfied** |
| **M7** MDL Semantic Gain (SG-v2) | Done | `tests/mdl/` — training-only compression scores ≤ 0, held-out shortening scores > 0, coding scheme hashed |
| **M8** Causal attribution plane | Done | `tests/causal/` — ablation verified by semantic-hash equality, concentration stop rule fires on a planted shortcut and not on a general primitive, null and negative primitives reported |
| **M9** Statistics and reporting | Done | `tests/stats/` — every refusal in the report gate asserted; statistics checked against independently hand-computed values |
| **M10** EXP-001 S2/S3 execution | Done | E0 (16 seeds) → pre-registration committed → S2 (8 conditions × 32 seeds) → S3 (condition G + per-primitive mediation). Report in `docs/experiments/EXP-001-DR-report.md`; negative result in `docs/research/negative_results/`; end-to-end coverage in `tests/experiments/`. **Gate G6 satisfied** — the ledger is not empty |

## The M10 result, in one paragraph

Outcome **`h0_consistent`**, Claim Level 1. The treatment moved the primary endpoint by +0.0052
(95% CI −0.0260 to +0.0391) against a pre-registered threshold of +0.05; **no control was
beaten**; and the human-expert DSL beat both treatments by ~9.5× the margin they hold over the
baseline — the falsification signal spec §24.9 names explicitly. The reporting gate refused any
capability claim and certified the run as consistent with H0. Per **ADR-0007** this is
instrument validation, not evidence about any language model: H2, H13, H14 and H15 remain
untested, and spec §45 applies in full.

The run exposed two defects, both caught by the instrument's own checks and both now fixed and
regression-tested: condition I was over-funded 2.8× (the §26.6 reconciliation caught it), and
checkpoint keys collided across configurations. It also established that **confound control C1 is
not implementable against a saturating enumerative searcher** — condition I was measured across a
7.8× compute range and returned an identical solve rate every time.

## Assurance integration (`BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1`)

Layered over M0–M10 rather than replacing any of it. Eight P0/P1 work orders complete, two P2
deferred with the compiler milestones they annotate — status in
`docs/architecture/ASSURANCE_WORK_ORDERS.md`, all ten §14 acceptance criteria in
`tests/assurance/test_acceptance.py`.

The change with the widest blast radius: the "no capability claim without F, H and I" rule moved
out of report formatting and into a central promotion predicate (ADR-0010), so it now binds
anything that consumes a claim rather than only a report. The existing 38 report-gate tests pass
unchanged through the new path.

Run against the real EXP-001-DR results, the protocol produced the asymmetry it is designed to:
the **capability claim is INCONCLUSIVE** (certificate FAIL; all three required controls
unbeaten) while the **negative-result claim is PROMOTED** with the search-space constraint it
implies. `artifacts/assurance_ledger.json`.

## Deferred behind gates, as the plan requires

M11 (equality saturation — adopt, don't build), M12 (MLIR + translation validation), M13
(tokenizer / adapted model — gated on S2 and S3), M14 (compiler policy evolution, cross-model
transfer — gated on S4). None started, correctly.

## Standing residuals

Disclosed here so they travel with any result (spec §40.3):

1. **ADR-0005** — the candidate sandbox is an in-process audit hook, not a kernel sandbox, and
   `hidden_evaluator/` shares a checkout. Production needs an immutable evaluator image, process
   isolation, and the assets relocated. No result above Claim Level 1 until then.
2. **ADR-0006** — condition C's MDL extractor ranks candidates independently rather than
   searching for a jointly optimal library, and counts nodes rather than bits. This makes the
   control *weaker* than it should be, which biases toward the treatment — the wrong direction —
   and must be disclosed with any D-beats-C comparison.
3. **ADR-0007** — `compression_ratio` uses a surface-token proxy, not a model tokenizer.
4. The synthesizer cannot capture outer variables in closures, so some tasks are unreachable in
   *every* condition. Equal across conditions, but it lowers the ceiling.
