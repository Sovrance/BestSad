# Implementation status against `IMPLEMENTATION_PLAN_v0.2.md`

Last updated: 2026-08-17.

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

## Not complete

**M10 — EXP-001 stage S2/S3 execution.** The runner (`bestsad.experiments.exp001`) and the
analysis and certification path (`bestsad.experiments.analysis`) are written, and stage S1 has
been executed end to end. **S2 and S3 have not been run**, so:

- no result exists, and none should be quoted;
- the runner's S2/S3 paths are not yet covered by an end-to-end test;
- no negative-result record has been written, because there is no finding to record yet.

The blocker is wall-clock cost, not design: a single condition-seed takes ~100 s at the current
budget, and S2 is 8 conditions × the seed count. The next step is a timed profile and a budget
that makes the full staged run practical, then the run itself.

When it does run, note what it will and will not mean. Per **ADR-0007**, the model role is
filled by an enumerative synthesizer, not a language model. Any output is **Claim Level 0/E —
exploratory instrument validation**. It cannot bear on H2, H13, H14 or H15, all of which are
claims about a *model*, and spec §45's prohibited claims apply in full.

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
