# Repository front matter

`README.md` is part of the delivered v0.2 package and its hash is pinned in
`MANIFEST_SHA256.txt` (see `CONTRIBUTING.md`, "Do not modify the delivered v0.2 package").
Repository-specific notes therefore live here rather than being appended to it.

That rule was broken once, quietly, and this file is the repair: the licence and assurance
sections below were added directly to `README.md` in commits `0cd728e` and `02e3b79`, which
made `sha256sum -c MANIFEST_SHA256.txt` fail without anything noticing. The check now runs as
`tests/integrity/test_delivered_package.py`, so the next such edit fails a test instead of
drifting for a week. A pinned hash that nothing verifies is not a control.

## Licensing

**Proprietary. All rights reserved.** See `LICENSE`.

This repository contains unpublished research materials and is confidential. No license to use,
copy, modify, or distribute is granted except by separate written agreement with the owner.

The license does not relax the scientific reporting obligations recorded in this package — the
claims register (spec §45), the requirement that a capability claim carry conditions F, H and I,
and the requirement to preserve negative results all continue to bind any authorised user. A
license to use the instrument is not a license to misrepresent what it measured.

## Assurance protocol

Every evolved primitive, genome, and experimental capability claim carries an explicit,
machine-enforced assurance lifecycle:
`docs/architecture/BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md`.

The rule it exists to enforce is that **producers of evidence cannot promote their own
conclusions**. K0, BSIR, the evaluator, the sandbox policy, the MDL coding scheme and the
pre-registration are content-addressed roots; a change to any of them stales its descendants
automatically. Query it with `bestsad assure roots`, `bestsad assure stale`,
`bestsad primitive explain <id>`, and `bestsad report <run-id> --confirmatory`, which exits
non-zero when promotion dependencies do not hold.

## Agent guidance since the delivered package

`AGENTS.md` is pinned like `README.md`, so what follows is where its invariants meet the code
that has landed since v0.2. It adds to `AGENTS.md`; it changes nothing in it.

### The K0 twin (`k0rs/`) and invariant 1

Invariant 1 — *do not modify the trusted semantic kernel K0* — names `src/bestsad/kernel/`,
and since 2026-09-16 there is a second implementation of K0 in the repository: `k0rs/`, a Rust
twin verified with Kani (BEST-VERIF-05, ADR-0020, merged in PR #10). Read the invariant this
way now:

- **The Python reference is still the definition of correctness.** The twin is a second reading
  of K0 checked against the first, never the other way round (ADR-0002, ADR-0020). If the two
  disagree, the twin is wrong by definition and is fixed; the reference does not move.
- **The twin is under invariant 1 too.** `k0rs/build.rs` refuses to compile a twin whose kernel
  hash differs from the Python `KERNEL_VERSION_HASH`, and the `K0 twin parity` job re-runs the
  full M1 corpus (10⁵ programs, identical `Value | Trap(kind)` *and* identical step count) on
  every change. A change to `k0rs/` that alters what any K0 program computes is a change to K0,
  and needs the same ADR invariant 1 would demand of the Python — which is to say, do not.
- **Do not widen K0 through the twin.** Adding an operation, a limit or a trap kind to `k0rs/`
  changes the descriptor, changes the hash, and fails the build. That is the control working.
- **What Kani proves is bounded and narrow, and the record says so.** Nineteen harnesses in
  `k0rs/src/proofs.rs` cover the integer bound, arithmetic totality, the zero-divisor trap,
  `mod`'s sign and magnitude, comparisons, the list bound, fuel accounting and the ADR-0008
  cost model — the twin's pure step functions, not its evaluator. ADR-0020's second amendment
  lists what was tried and removed. Never describe a Kani run as a proof of K0, of the evaluator,
  or of twin–reference agreement; the last is `CORROBORATED` by the sweep, and the assurance
  plane refuses a Kani result as promotion evidence without internal corroboration attached.
- **Every harness has a 60 s budget.** `scripts/kani_gate.py` fails a harness over it. A harness
  that will not verify in budget is split, or removed and its property pinned by a test; it is
  never loosened, and `kani::unwind` bounds are never raised to make a proof pass.

For the "definition of done" bullet *property/differential tests against the K0 reference
interpreter where semantics are involved*: `tests/verify/test_k0_twin.py` and
`tests/verify/test_encoder_agrees_with_reference.py` are the two worked examples. Both draw the
same corpus the M1 sweep draws and compare against `bestsad.kernel` on the reference's own
`same_outcome`.

### Build-versus-adopt, applied

Z3 (ADR-0019) and Kani (ADR-0020) were adopted, not written. The SMT encoder in
`src/bestsad/verify/smt/` and the twin in `k0rs/` are BestSad's own because they are BestSad's
semantics; the solver and the model checker underneath them are not.

## Where things are

| Path | What it holds |
|---|---|
| `*_v0.2.md`, `*_v0.2.csv`, `*_v0.2.bib`, `schemas/` | The delivered package. Read-only; hashes pinned. |
| `src/bestsad/` | The instrument. `src/bestsad/kernel/` is K0 and is frozen (invariant 1). |
| `k0rs/` | The Rust twin of K0 (ADR-0020): hash-pinned at build, checked against the reference on every change, 19 Kani harnesses. Under invariant 1 as above. |
| `scripts/` | `ci_local.py` reproduces every CI gate locally (ADR-0021); `kani_gate.py` holds the twin's proofs to budget and ingests them as evidence. |
| `tests/` | Acceptance tests, named after the milestone or invariant they discharge. |
| `docs/adr/` | Architecture decisions, including every disclosed residual. Append-only: amend, never rewrite. |
| `docs/architecture/` | Engineering documents and work-order status (assurance integration, verification plane). |
| `docs/experiments/` | Run status and reports. |
| `docs/research/negative_results/` | Never deleted (P7, spec §44). |
| `docs/preregistrations/` | Hashed and committed before the run they govern. |
| `CONTRIBUTING.md` | Branch and pull-request workflow; the rules above. |
