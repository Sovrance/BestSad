# Implementation status against `IMPLEMENTATION_PLAN_v0.2.md`

Last updated: 2026-09-15.

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

## How the gates run (ADR-0018, 2026-08-26)

There are no GitHub Actions runners and, by owner decision, there will not be. Every check on
GitHub has been red since ~2026-08-24 for a reason unrelated to the code, and a permanently red
check carries no information. `ci.yml` stays as the description of the gates;
`scripts/ci_local.py` is what executes them, mirroring every job and every `pytest` invocation
(`tests/integrity/test_local_gates_mirror_ci.py` fails if the two drift). A gate whose tooling
is missing reports `UNAVAILABLE` and the run `INCOMPLETE`, never `OK`. Any claim that gates
passed must say **where they ran** and **which gates did not run**. On a machine without a
Docker daemon the evaluator-image gate does not run, so the spec §27.2 assertion that the built
image carries no hidden evaluation assets is unverified there — and is reported as such on every
run rather than dropped.

## Verification plane (`BESTSAD_VERIFICATION_PLANE_ENG_v0.1`, 2026-09-15)

| WO | Deliverable | State |
|---|---|---|
| BEST-VERIF-01 | ADR-0019: adopt Z3, optional `verify` dependency group | Done |
| BEST-VERIF-02 | Symbolic equivalence tier (spec V4): `src/bestsad/verify/smt/`, Tier 2 of `bsir/equivalence.py` | Done — `tests/verify/`, nine acceptance tests |
| BEST-VERIF-03 | External prover adapter, closes BEST-ASSURE-10 | Done — `verify/external.py`, acceptance test 11 |
| BEST-VERIF-04 | Non-vacuity of specifications | Done — `verify/vacuity.py`; ADR-0014 fixture path corrected |
| BEST-VERIF-05 | Rust twin of K0 under Kani | **Gated** — ADR-0020 (provisional) and nothing else, per the work order |
| BEST-VERIF-06 | Gate G-V | Done — job `verification (Gate G-V)` in `ci.yml`; gate `verify` in `scripts/ci_local.py` with a probe that asks Z3 to *solve* |

**Gate G-V** runs `pytest -q tests/verify` with `.[dev,verify]` installed. Without a usable
solver it reports `UNAVAILABLE` (exit 2 overall), per ADR-0018. In the `tests` gate, which
installs no solver, the solver-backed modules skip visibly and `test_solver_unavailable.py`
asserts the tier returns `UNKNOWN(solver_unavailable)` with nothing escaping.

What an `EQUIV_SYMBOLIC` verdict is: the solver returned `unsat` for the negated equivalence
over the contract's declared bounded domain. It carries `fuel_and_depth_traps_excluded` and
`list_length_le_<N>` (default `N = 8`), the analyzer-result content id holding the SMT-LIB2
text, solver version and timing, and a spec §19.1 verification score whose coverage is a stated
bound ratio (1.0 for Int/Bool-only domains under the exact integer bound; `8/4096` for list
domains), never an estimate. A `NON_EQUIV` from the solver has been re-executed on the K0
reference interpreter first; a model that does not reproduce raises `EncoderDivergence` and
reports nothing. In the assurance plane the proof is `FORMAL` with `is_external=True` and
promotes only with the Tier 3 differential result on the same contract attached, and only if
the contract has refuted at least one generated mutant of the pair (`verify/vacuity.py`).

**Standing residual (until BEST-VERIF-05 is gated in):** *K0 has no machine-checked proof of
its own implementation. Its assurance rests on the M1 differential sweep (`CORROBORATED`) and
on the encoder-versus-reference differential test (BEST-VERIF-02, test 1: every K0 operation
over the enumerated small domain and 10⁴ random programs, evaluated on the reference and through
the encoding by solving for the output, identical `Value | Trap(kind)`).* The encoder is a
second reading of K0 and is checked against the first, not the other way round.

**Gate record for this work (2026-09-15).** `scripts/ci_local.py --fresh-venv` on the
authoring container (no Docker daemon): `tests`, `integrity` (G1), `kernel-sweep` (G0),
`assurance`, `schemas`, `verify` (G-V) all **PASS**; `evaluator-image` **UNAVAILABLE**
(`docker info` cannot reach a daemon), overall INCOMPLETE, exit 2. Separately, the GitHub Actions
run for PR #8 (run 35007331423, head `78b8a65`) executed all seven `ci.yml` jobs with real
durations and every job succeeded, including the evaluator-image gate — the first genuine
Actions run since #27 (2026-08-24). That is ADR-0018's revisit trigger ("if runners return");
whether to mark ADR-0018 superseded is the owner's call and is not made here.

Discrepancies the verification-plane document recorded for the owner (§7), and their state:
(1) the ADR-0014 fixture path — corrected by amendment, the fixture is
`tests/languages/test_bsld_lowering.py::IncorrectLoweringIsCaught`; (2) this file and
`ASSURANCE_WORK_ORDERS.md` predated ADR-0018 — both now carry it; (3) the research report's
"Kani on K0" was written without the package — superseded by the document's §1 and ADR-0020.

## Deferred behind gates, as the plan requires

M11 (equality saturation — adopt, don't build), M12 (MLIR + translation validation), M13
(tokenizer / adapted model — gated on S2 and S3), M14 (compiler policy evolution, cross-model
transfer — gated on S4). None started, correctly.

## Standing residuals

Disclosed here so they travel with any result (spec §40.3):

1. **ADR-0005** (narrowed 2026-08-24, not closed) — **condition jobs now run behind the
   boundary.** `Exp001Runner._map_jobs` routes every `(condition, seed)` job through
   `run_isolated`: separate process, kernel-enforced CPU/address-space/file-size/core-dump
   limits, cleared environment, no inherited descriptors, JSON rather than pickle across the
   boundary, and the audit hook denying the hidden assets. Isolation is on by default, moves no
   reproducibility digest, refuses to fall back silently if the platform cannot provide it, and
   stops the run rather than dropping a cell when a job trips a limit or its integrity monitor
   fires. The limits and which stages were isolated are recorded in the run's provenance.
   **Still outstanding:** *abstraction discovery is not isolated* — it returns `Primitive`
   objects whose expansions are K0 terms, and the boundary carries JSON only; serialising terms
   would need the round-tripping parser `_discovery_job` warns would silently change what
   condition D is. No experiment has yet been run inside the evaluator image, there is no
   declared seccomp allowlist, and `hidden_evaluator/` still shares a checkout — a separate
   process on the same host reads the same disk. **No result above Claim Level 1** until the
   assets are relocated and a run records the image digest it executed under. EXP-001-DR itself
   was produced before any of this and remains a host-run result.
2. ~~**ADR-0006** — condition C's MDL extractor ranks candidates independently and counts nodes
   rather than bits.~~ **Discharged 2026-08-24.** Rebuilt as a joint two-part MDL search in bits;
   condition C re-run on all 32 seeds gives an identical per-seed solve rate, so the D-versus-C
   comparison was not an artefact of a weakened control.
3. **ADR-0007** — `compression_ratio` uses a surface-token proxy, not a model tokenizer.
4. ~~The synthesizer cannot capture outer variables in closures, so some tasks are unreachable
   in *every* condition. Equal across conditions, but it lowers the ceiling.~~ **Discharged
   2026-08-24, and the premise did not survive measurement.** Capture is implemented, and a
   second and larger reach defect was found while testing it: observational-equivalence pruning
   could not distinguish two variables of the same type, so `ge L0 n` collapsed onto the
   constant `true` — which had silently degraded *every* two-argument closure the solver has
   ever built. Both are fixed. A four-arm ablation attributes the whole training-side gain
   (24/32 → 27/32) to the probe fix, with capture adding nothing on top, and **held-out solve
   rate is unchanged at 5/16 in all four arms**: search reach was not what limited
   generalization. Recorded in `docs/research/negative_results/`. Note `SYNTHESIZER_VERSION`
   now participates in checkpoint fingerprints, and EXP-001-DR was produced by the older,
   narrower searcher.
