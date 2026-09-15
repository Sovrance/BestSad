# ADR 0019 — Adopt Z3 as the symbolic-equivalence engine (spec V4)

**Status:** Provisional
**Date:** 2026-09-15
**Governs:** `src/bestsad/verify/smt/`, `src/bestsad/bsir/equivalence.py` Tier 2, spec §19 V4,
§19.1
**Relates to:** ADR-0002 (dependency discipline), ADR-0008 (the semantics encoded), ADR-0014
(the obligations discharged), ADR-0018 (the `UNAVAILABLE` gate pattern)
**Work order:** BEST-VERIF-01 in `docs/architecture/BESTSAD_VERIFICATION_PLANE_ENG_v0.1.md`

## Context

`bsir/equivalence.py` declares five verdicts and produces four. `EQUIV_SYMBOLIC` — "a solver
proved equal outcomes within a declared contract" — has been a stub since BS-SRE-001: a caller
asking for a proof (`require_proof=True`) gets `UNKNOWN` with the obligation
`symbolic_equivalence_unproven` left open and the note "symbolic solver adapter is not
implemented (P1)". That was the right thing to return, and it leaves real debts unpaid:

- ADR-0014 makes a BSLD lowering evidence-bound. A lowering that is correct but not
  canonically identical to its reference — commutative reordering is the standing example,
  since `canonicalize.py` deliberately does not normalise it (ADR-0013) — can be discharged
  today only with sampled Tier 3 evidence, and `discharge_with(require_proof=True)` refuses
  that. The obligation is honest and permanently open.
- BEST-ASSURE-04 semantic certificates can reach `FORMAL` only on an exhaustive domain or a
  proof artifact. Nothing in the package produces the second.
- Spec V4 names the tier explicitly: "SMT or exhaustive bounded checks when supported".

The build-versus-adopt rule in `AGENTS.md` applies squarely. SMT solving is a mature component;
the companion's adopt list has the entry "symbolic checks: SMT for bounded subsets" (spec line
~1521). Writing a bespoke decision procedure for K0 terms would be the failure mode the rule
exists to prevent, and the result would be less trustworthy than the thing it replaced.

## Decision

**Adopt Z3, as an optional dependency.** `pyproject.toml` gains

```
[project.optional-dependencies]
verify = ["z3-solver>=4.12"]
```

Core dependencies stay `jsonschema` only, as ADR-0002 requires. `pip install -e ".[dev]"`
continues to install no solver and the full non-slow suite continues to pass without one.

**Absence fails closed, and says so.** When `z3` cannot be imported, or imports but cannot
solve a trivial query, Tier 2 returns `UNKNOWN` with reason `solver_unavailable`, and Gate
G-V (`scripts/ci_local.py`, BEST-VERIF-06) reports `UNAVAILABLE` — never `OK`, never `FAIL`.
This is the ADR-0018 distinction between "did not run" and "ran and found a problem", applied
to a tool rather than a runner.

**Bounded proofs are labelled bounded.** The solver works over a declared `solver_scope`: a
list-length bound `N ≤ 4096` (default 8), an integer magnitude bound (default the K0 bound,
`2^64`, which is exact), a timeout, and an unrolling depth. An `EQUIV_SYMBOLIC` verdict
carries the assumptions `fuel_and_depth_traps_excluded` and `list_length_le_<N>` at minimum,
and its `scope` is the bounded domain. The warrant it earns in the assurance plane is `FORMAL`
*on the bounded claim*, with `is_external=True` because the engine is third-party even when
BestSad drives it.

**Fuel and depth are excluded in v0.1.** The encoder models value-or-trap-kind for the six
closed trap kinds of ADR-0008 with two exceptions: `fuel_exhausted` and `depth_exceeded` are
resource bounds, not value semantics, and modelling them symbolically would require encoding
the ADR-0008 cost model exactly. A pair that agrees everywhere except in fuel exhaustion is
reported `EQUIV_SYMBOLIC` *with that assumption listed*, never silently, and BEST-VERIF-04's
non-vacuity check is the control that catches a contract whose whole domain falls under the
exclusion.

**The encoder is a second reading of K0, and K0 is the anchor.** `verify/smt/encode.py`
reproduces ADR-0008's semantics — bounded mathematical integers rather than bit-vectors,
truncated division with the dividend's sign on `mod`, strict `and`/`or` with the first trap
winning, `if` as the single non-strict operation, total `head`/`tail`/`index`. Any divergence
between the encoder and `kernel/interpreter.py` is a bug in the encoder, never a reason to
touch the reference. Two controls keep it honest: a differential test against the reference
over random programs, and a counterexample discipline under which every `sat` model is
re-executed on the reference and must reproduce the disagreement — if it does not, the
adapter raises `EncoderDivergence` rather than reporting anything.

## What is lost, stated plainly

1. **Bounded is not unbounded.** A proof over lists of length ≤ 8 says nothing about length 9.
   The record states the bound numerically (`verification_coverage`, spec §19.1) and never
   estimates coverage it did not check. Integer-only and Bool-only domains are exhaustive and
   are recorded as coverage 1.0.
2. **Two readings of K0 now exist.** The interpreter remains normative (ADR-0002). The encoder
   is checked against it, not the other way round, and the check is sampled — the encoder's
   agreement with the reference is `CORROBORATED`, not proved.
3. **Solver timing is nondeterministic.** The verdict is deterministic given the fixed seeds
   (`sat.random_seed=0`, `smt.random_seed=0`) and the recorded solver version; wall and CPU
   time are not, and they are stored in the analyzer-result record, so that record's content
   id varies between runs. Only the verdict is compared across runs. This names the source of
   nondeterminism as `AGENTS.md`'s definition of done requires.
4. **An external engine sits inside the trust chain.** Z3 is trusted for the property it
   checks within the declared scope, and for nothing else. Its result never promotes alone:
   `NEVER_SUFFICIENT_ALONE` and the corroboration rule in BEST-VERIF-03 require the Tier 3
   dynamic result on the same contract alongside it.

## Consequences

- `equivalence.py` changes in exactly one place: the `require_proof` branch calls the adapter
  instead of returning the stub. Tier 1 and Tier 3 are untouched.
- `verify/` is a consumer of `kernel/` and `bsir/`. Nothing in `kernel/`, `bsir/canonicalize.py`,
  `evaluator/`, or `hidden_evaluator/` imports from it, and `KERNEL_VERSION_HASH` is unchanged.
- Solver time is compute and is charged to the compute ledger (spec §26.4) as
  `solver_wall_s`, `solver_cpu_s` and `solver_calls`, folded into `verifier_time_s` on the wire.
- A machine without Z3 loses one gate and one verdict, and both say so.

## Revisit trigger

- More than 20% of the equivalence obligations in a run time out at the declared budget:
  revisit the bounds, the unrolling strategy, or the encoding (the research report's
  threshold).
- A V6 mechanised proof of K0 becomes available: the bounded symbolic tier becomes
  corroboration for it rather than the strongest evidence.
- A claim needs fuel or depth modelled: that is a new encoding decision and a new ADR, not a
  relaxation of the assumption.

Status moves from *Provisional* to *Accepted* when BEST-VERIF-02's acceptance tests pass
under Gate G-V.
