# AGENTS.md — instructions for a coding agent working on Bestsad

You are implementing a **research instrument**, not a product. Its purpose is to produce a trustworthy answer to a question that may well come back negative. A correct null result is a success; a positive result obtained by skipping a control is a failure that wastes the whole program.

## Read in this order

1. `README.md` — what this package is.
2. `BESTSAD_RESEARCH_ARCHITECTURE_EXPERIMENTAL_SPEC_v0.2.md` — the normative spec. §§39–45 are new in v0.2 and are the parts most often skipped; do not skip them.
3. `BESTSAD_PREREGISTRATION_EXP001_v0.2.md` — must be completed and committed before any evaluation run.
4. `IMPLEMENTATION_PLAN_v0.2.md` — your work breakdown, with acceptance tests.
5. `BESTSAD_RESEARCH_COMPANION_v0.2.md` — why the design is shaped this way. Read Part II (§§29–37) before proposing design changes; most "obvious improvements" were already considered and rejected for stated reasons.

## Invariants you may never violate

1. **Do not modify the trusted semantic kernel K0, the evaluator trust boundary, or the definition of correctness.** Everything else may evolve. This is the single rule the whole program rests on.
2. **Never give the evolutionary/search side any read path to the frozen hidden benchmark.** Not through imports, not through logs, not through error messages, not through a shared filesystem. If you find such a path, stop and report it as an integrity finding.
3. **Never report a capability claim without conditions F, H, and I.** Compression-matched, scaffolding-matched, and compute-matched-search-only. See spec §40.
4. **Never conflate `compression_ratio` with `capability_delta`.** They are reported as a pair, always. See spec §21.6.
5. **No confirmatory claim without a committed, hashed, timestamped pre-registration.** See spec §26.5.
6. **Never delete a negative result, a quarantined candidate, or a failed run.** See spec §44 and §22.3.
7. **Do not make any claim on the prohibited list** in spec §45.

## Build-versus-adopt

Bestsad's contribution is integration and methodology. If you are about to hand-write a component that exists in mature form (e-graph engine, compiler IR substrate, translation validator, autotuner cost model, MDL abstraction extractor, evolutionary search loop), **stop and write an ADR justifying it instead**. See companion §34 for the adopt list.

## Definition of done for any component

- Deterministic given a seed, or explicitly documented as nondeterministic with the source of nondeterminism named.
- Emits its compute usage into the compute ledger (spec §26.4).
- Emits a content-addressed artifact manifest (spec §26.9).
- Has property/differential tests against the K0 reference interpreter where semantics are involved.
- Runs inside the candidate sandbox with no network access when executing generated programs.

## Definition of done for any experiment

- Pre-registration committed before first evaluation run.
- Per-seed values published, not just aggregates.
- Per-compute curves, not single matched points.
- FDR correction applied across the declared secondary family.
- Per-primitive causal mediation table published including null and negative effects.
- Residual confounds quantified and disclosed.

## What to do when you are unsure

Write an ADR under `docs/adr/`, state the options and the trade-off, and mark the decision as provisional. Do not silently choose. Do not widen the semantics of K0 to make something easier — that is the one shortcut that invalidates everything downstream.

## Escalate to a human when

- A control condition beats a treatment condition (this is a real finding, not a bug — do not "fix" it).
- You find a path from candidate code to evaluator state.
- A primitive shows very high task-specific gain and near-zero cross-family reuse (spec §22.2).
- The power analysis says the achievable seed count cannot support the pre-registered effect size.
