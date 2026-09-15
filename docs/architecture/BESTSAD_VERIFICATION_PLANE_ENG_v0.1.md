# BestSad Verification Plane — Engineering Document v0.1

**Document ID:** BESTSAD-VERIF-ENG-v0.1
**Proposed repo path:** `docs/architecture/BESTSAD_VERIFICATION_PLANE_ENG_v0.1.md`
**Status:** Proposed — not yet adopted. Adoption requires ADR-0019 (§4) to be accepted first.
**Applies to:** BestSad package v0.2.0 (`pyproject.toml`), branch `v1`
**Audience:** the implementing coding agent (Codex/Cursor); reviewers of the assurance ledger
**Governs:** spec §19 (V0–V6 verification ladder), §19.1 (verification score); ADR-0002, ADR-0008, ADR-0014, ADR-0018; `BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md` §6 (warrants) and BEST-ASSURE-10
**Source of recommendations:** research report *"Kani and Verified Computation for AI-Generated Low-Level Code: A Strategic Assessment for BestSad"* (2026-09-15), adjudicated against the actual codebase in §1 below.

---

## 0. Read this first (agent instructions)

1. Read `AGENTS.md` in full before touching anything. Invariant 1 — *do not modify K0, the evaluator trust boundary, or the definition of correctness* — binds every work order below. This document **adds evidence about K0**; it never changes K0.
2. Every work order here is **additive**. If a work order appears to require editing `src/bestsad/kernel/`, stop: you have misread it. The only kernel-adjacent edits permitted are new test files under `tests/kernel/`.
3. The build-versus-adopt rule in `AGENTS.md` applies. You will adopt an SMT solver (Z3) and, if gated in, a model checker (Kani). You will not write either.
4. Work orders must be executed in the order given. BEST-VERIF-01 (the ADR) blocks all others.
5. Commit after each work order with the message prefix `[BEST-VERIF-NN]` and push to remote, per the repository owner's standing instruction that agents stay in sync.
6. Claims that a gate passed must state **where it ran** and **which gates reported `UNAVAILABLE`** (ADR-0018). There are no CI runners. `scripts/ci_local.py` is the gate runner.

---

## 1. Adjudication: what the research report recommended vs. what the codebase permits

The report recommended a four-stage adoption of Kani → Verus → LLM-proposed harnesses → ISLE-style verified lowering, beginning with "Kani as a mandatory CI gate on K0." That recommendation was written against the v0.1 architecture summary ("Rust/Python/TypeScript codebase") and **does not survive contact with the repository as shipped**:

| Report recommendation | Finding in the codebase | Disposition |
|---|---|---|
| Stage 0: Kani on K0 | K0 is Python and **normative** (ADR-0002, Accepted-Provisional). There is no Rust in the package. Kani verifies Rust MIR only. | **Rejected as written.** Reframed as BEST-VERIF-05: a Rust *twin* of K0, gated behind ADR-0002's own revisit trigger, verified with Kani, checked against the Python reference under the M1 differential test. The Python reference does not move. |
| Kani harnesses as the "independent evaluator oracle" for EXP-001 | The evaluator (`src/bestsad/evaluator/`) is a benchmark-execution plane behind a trust boundary, not a property prover. The place where a solver-backed oracle is actually *missing* is `src/bestsad/bsir/equivalence.py`, Tier 2, which returns `UNKNOWN` with `symbolic_equivalence_unproven` and the note "symbolic solver adapter is not implemented (P1)". | **Accepted, relocated.** The oracle belongs in the equivalence tiers (spec V4), where ADR-0014 lowering obligations and BEST-ASSURE-04 semantic certificates already consume it. BEST-VERIF-02. |
| Stage 1: Verus for functional correctness of K0 | Same objection as Kani (Rust only). Verus on a Rust twin is a Stage-2 option after BEST-VERIF-05, not before. | **Deferred.** Recorded as a follow-on in §6; no work order. |
| Stage 3: LLM-proposed harnesses/specs as untrusted proposers | The assurance plane already has the right primitives: `EvidenceObject.is_external`, `NEVER_SUFFICIENT_ALONE`, `Warrant.FORMAL` vs `CORROBORATED` (`src/bestsad/assurance/claims.py`, `integration.py`). What is missing is the adapter (BEST-ASSURE-10, "Partial") and a **non-vacuity** requirement. | **Accepted.** BEST-VERIF-03 and BEST-VERIF-04. |
| Stage 4: ISLE-style declarative lowering + translation validation | BSLD is already declarative with `proof_obligations` (ADR-0014). M12 (MLIR + Alive2-style TV) is correctly deferred behind gates (`IMPLEMENTATION_PLAN_v0.2.md` line 137; `ASSURANCE_WORK_ORDERS.md`). | **Already aligned; no new work.** §6 records the design constraints M12 must inherit. |
| Two independent engines corroborating each property | Sound principle; the assurance plane's warrant model supports it. | **Accepted** as the definition of `FORMAL` for solver-backed evidence: one engine gives `FORMAL` with `is_external=True`; the claim is promotable only with the existing dynamic-tier corroboration attached (§3.3). |

**Net:** the report's strategic conclusion (generator/checker split; verification as the trust layer for agent-written code; fail-closed on unsupported features) is adopted. Its tool sequencing is replaced by the work orders in §3, which are ordered by what the existing code is already asking for.

---

## 2. Design

### 2.1 Placement

```
src/bestsad/
  verify/                     # NEW package — the verification plane
    __init__.py
    smt/
      __init__.py
      encode.py               # K0 term → SMT encoding under K0 v1.0.0 semantics (ADR-0008)
      solver.py               # Z3 adapter; probe, timeouts, resource accounting
      bounds.py               # bounded-domain policy (list length, unrolling), declared per contract
    external.py               # external prover result ingestion → EvidenceObject (BEST-ASSURE-10)
    vacuity.py                # non-vacuity / mutation witness check for any solver-backed claim
  bsir/equivalence.py         # Tier 2 wired to verify.smt (edit: replace the UNKNOWN stub only)
schemas/
  sre/analyzer-result.schema.json   # existing; reused for solver results
  verification_score.schema.json    # NEW — spec §19.1 coverage/cost record
tests/verify/                 # NEW
docs/adr/0019-adopt-z3-for-symbolic-equivalence.md   # NEW (BEST-VERIF-01)
docs/adr/0020-rust-k0-twin-under-kani.md             # NEW, provisional (BEST-VERIF-05)
scripts/ci_local.py           # add gate "verify" (G-V); mirror check must still pass
.github/workflows/ci.yml      # add job "verification (Gate G-V)"; kept in sync per ADR-0018
```

`verify/` is a **consumer** of `kernel/` and `bsir/`. It imports from them. Nothing in `kernel/`, `bsir/canonicalize.py`, `evaluator/`, or `hidden_evaluator/` imports from `verify/`. `tests/integrity/test_trust_boundary.py` must continue to pass unchanged; add `verify` to whatever module allowlist that test enforces on the candidate side only if the test requires it, and document why.

### 2.2 Trust posture (the generator/checker split, made concrete)

| Role | Who | Trusted? |
|---|---|---|
| Proposer of a candidate program, primitive, or lowering | search side, coding agent, LLM | **No** |
| Proposer of a *specification*, harness, or equivalence contract | coding agent, LLM, human | **No** — a spec is untrusted until BEST-VERIF-04 shows it is non-vacuous |
| Checker | Z3 via `verify/smt` (Tier 2); K0 reference interpreter (Tier 3); Kani (BEST-VERIF-05 only) | Trusted *for the property it checks, within the declared scope* |
| Arbiter of promotion | `assurance/promotion.py` `PolicyGate` (ADR-0010) | Trusted; unchanged by this document |

Consequence: a green solver result produced from an agent-written contract is **not** promotable evidence until the same contract has refuted a known-bad witness (BEST-VERIF-04). This is the ADR-0014 "deliberately incorrect lowering is a testable fixture" pattern generalized to every solver-backed claim.

### 2.3 K0 semantics the encoder must reproduce exactly (from ADR-0008 and `kernel/ops.py`)

The encoder is a second reading of K0. Any divergence from the Python reference is a **bug in the encoder**, never a reason to touch the reference. The following are semantics, hashed into `KERNEL_VERSION_HASH`, and each needs an explicit encoding decision and a pinning test:

| Item | K0 v1.0.0 rule | Encoding requirement |
|---|---|---|
| `Int` | mathematical, `|x| ≤ 2^64`, else trap `VALUE_TOO_LARGE` | Use the SMT `Int` theory (not bit-vectors — wraparound would be a semantic lie). Every arithmetic result carries a trap guard `|r| > 2^64`. |
| `div`, `mod` | truncate toward zero; `mod` sign of dividend; zero divisor traps `DIVISION_BY_ZERO` | Do **not** use Z3's `div`/`mod` directly (Euclidean). Encode truncation explicitly: `q = sign(a)*sign(b)*(|a| div |b|)`, `r = a - b*q`. Pin with a test over all sign combinations against the Python reference. |
| `and`, `or` | strict — both operands evaluated; `and(false, 1/0)` traps | Trap propagation is *not* short-circuited. Encode outcome as `Trap if trap(a) ∨ trap(b) else (a ∧ b)`. `if` is the only non-strict op: `trap(c) ∨ (c ? trap(t) : trap(e))`. |
| Lists | `LIST_LEN_LIMIT = 4096`; `cons`/`append`/`range` trap `LIST_TOO_LONG` | Bounded unrolling: the contract declares `solver_scope` with a list bound `N ≤ 4096` (default `N = 8`). Lists are encoded as (length, element array) with `length ≤ N`. Results are **bounded** proofs and are recorded as such (§2.4). |
| `head`, `tail`, `index` | total; `Option`/empty on out-of-range | Encode as total functions; no trap. |
| `eq` | structural equality at any single ground type | Type-directed encoding; fuel charged by size is a *resource* matter (below). |
| `map`, `filter`, `fold`, `lam` | K0 has no recursion; `lam` is legal only in HOF operand position | Inline the lambda body at each unrolled position. No fixed points required. |
| Fuel, depth | `DEFAULT_FUEL = 100_000`, `DEFAULT_DEPTH_LIMIT = 256`; fuel is a resource bound (ADR-0008 residual) | **Out of scope in v0.1.** The equivalence contract must record the assumption `fuel_and_depth_traps_excluded`. A program pair that agrees on value-or-trap-kind under every input in the bounded domain but differs only in fuel exhaustion is reported `EQUIV_SYMBOLIC` *with that assumption listed*, never silently. |
| Observable | `observable_contract_ref = "outcome:value-or-trap-kind"` | The encoded outcome is a sum type `Value(v) | Trap(kind)`; equivalence is equality of that sum, kind included. |

Six trap kinds are closed (ADR-0008). The encoder must reject (fail closed, `UNKNOWN`, reason recorded) any term whose op is not in `K0_OPS` or whose trap set is not one of the six.

### 2.4 Verdict, warrant, and scope

`EquivalenceResult.verdict = "EQUIV_SYMBOLIC"` is emitted **only** when the solver returns `unsat` for the negated equivalence over the declared bounded domain. It carries:

- `scope`: the `EquivalenceContract` wire form including `solver_scope` (list bound, int bound, timeout, unrolling depth) — already a field on the contract.
- `assumptions`: at minimum `["fuel_and_depth_traps_excluded", "list_length_le_<N>"]`.
- `evidenceRefs`: content ID of the `analyzer-result` record (`schemas/sre/analyzer-result.schema.json`) holding the SMT-LIB2 text, solver version, and wall/CPU time.

Warrant mapping into the assurance plane (`assurance/integration.py::semantic_equivalence_claim`):

| Solver outcome | Verdict | Warrant | `is_external` |
|---|---|---|---|
| `unsat`, domain exhaustive for the declared types (finite, e.g. Bool-only) | `EQUIV_SYMBOLIC` | `FORMAL` | `True` |
| `unsat`, domain bounded (lists ≤ N) | `EQUIV_SYMBOLIC` | `FORMAL` **on the bounded claim only**; the claim object's `scope` is the bounded domain | `True` |
| `sat` with model | `NON_EQUIV` + `counterexampleRef` (`schemas/sre/counterexample.schema.json`) | `DIRECT_OBSERVATION` after the counterexample is *re-executed on the K0 reference* and confirmed | — |
| `sat` but re-execution on K0 disagrees with the model | **encoder bug**; raise, do not report | — | — |
| `unknown` / timeout / unsupported op | `UNKNOWN`, `unresolved=("symbolic_equivalence_unproven",)`, reason recorded | — | — |

`NEVER_SUFFICIENT_ALONE` continues to apply: an external `FORMAL` warrant never promotes by itself (BEST-ASSURE-10 intent, "external corroboration is never silently upgraded to internal proof"). The Tier 3 dynamic result on the same contract is attached as the internal corroboration.

### 2.5 Resource accounting

Solver time is compute. `verify/smt/solver.py` charges the compute ledger (spec §26.4) with `solver_wall_s`, `solver_cpu_s`, and a `solver_calls` counter via the same `_charge` path `equivalence.py` uses for kernel steps. A verification score record (spec §19.1) is emitted per claim: `verification_coverage` (fraction of the declared domain covered: 1.0 for exhaustive, else the bound ratio stated numerically, never estimated) and `verification_cost` (the charged resources).

---

## 3. Work orders

Priority: P0 must complete before any solver-backed evidence enters the ledger. P1 completes the plane. P2 is gated.

### BEST-VERIF-01 (P0) — ADR-0019: adopt Z3 for the symbolic equivalence tier

**Deliverable:** `docs/adr/0019-adopt-z3-for-symbolic-equivalence.md`, status *Provisional* until BEST-VERIF-02's acceptance tests pass, then *Accepted*.

**Must state:**
- Context: `equivalence.py` Tier 2 is a stub; ADR-0014 obligations and BEST-ASSURE-04 certificates cannot reach `FORMAL` without it; spec V4 names "SMT or exhaustive bounded checks".
- Decision: add `z3-solver` as an **optional** dependency group `[project.optional-dependencies] verify = ["z3-solver>=4.12"]`. Core dependencies stay `jsonschema` only (ADR-0002). Absence of Z3 makes Tier 2 return `UNKNOWN` with reason `solver_unavailable` and makes Gate G-V report `UNAVAILABLE` — never `OK`, never `FAIL` (ADR-0018 pattern).
- Build-vs-adopt justification (AGENTS.md): Z3 is on the companion's adopt list category "symbolic checks: SMT for bounded subsets" (spec line ~1521). Bespoke solving is prohibited.
- Consequences: bounded proofs are labelled bounded; fuel/depth excluded in v0.1; encoder divergence from the reference is an encoder bug.
- Revisit trigger: if > 20% of equivalence obligations in a run time out at the declared budget, revisit bounds/strategy (the report's threshold).

**Acceptance:** ADR present; `pip install -e ".[dev,verify]"` succeeds; `pip install -e ".[dev]"` still succeeds with no Z3 and the full non-slow suite passes.

### BEST-VERIF-02 (P0) — Symbolic equivalence tier (spec V4)

**Deliverable:** `src/bestsad/verify/smt/{encode,solver,bounds}.py`; edit `src/bestsad/bsir/equivalence.py` to replace the `require_proof` stub with a call into the adapter. **No other edit to `equivalence.py`.** Tier 1 (canonical) and Tier 3 (dynamic) are untouched.

**Interface (proposed; keep existing dataclasses):**

```python
# src/bestsad/verify/smt/solver.py
@dataclass(frozen=True, slots=True)
class SymbolicResult:
    status: Literal["equiv", "non_equiv", "unknown"]
    model: dict[str, Any] | None          # concrete K0 input values on non_equiv
    assumptions: tuple[str, ...]
    scope: dict[str, Any]                 # bound N, int_abs_limit, timeout_ms, unroll_depth
    analyzer_result_id: str               # sha256 content ID of the stored analyzer-result
    wall_s: float
    cpu_s: float

def check_equivalence(left: Program, right: Program, contract: EquivalenceContract,
                      *, ledger=None, timeout_ms: int = 5_000) -> SymbolicResult: ...
def probe() -> bool:  # True only if z3 imports AND solves a trivial query
```

**Encoding rules:** §2.3, verbatim. The encoder is type-directed off `kernel/typecheck.py` results; untyped or ill-typed programs return `unknown` (fail closed).

**Counterexample discipline:** on `non_equiv`, the returned model is converted to K0 values, both programs are executed on the **reference interpreter** (`kernel/interpreter.py`) with the contract's fuel, and the disagreement must reproduce. If it does not, raise `EncoderDivergence` — this is the single most important test in the plane, because it is how the encoder is kept honest against the anchor.

**Acceptance tests (`tests/verify/`):**
1. `test_encoder_agrees_with_reference.py` — for every op in `K0_OPS` and for 10⁴ random programs from `kernel/random_programs.py` (reuse M1's generator; mark full count `slow`), enumerate the bounded domain, evaluate on the reference and on the encoding (by solving for the output), assert identical `Value|Trap(kind)`. **This is a differential test against K0 per AGENTS.md "definition of done".**
2. `test_div_mod_truncation.py` — all four sign combinations × zero divisor, symbolic vs reference.
3. `test_strict_and_or_trap_propagation.py` — `and(false, div(1,0))` is `Trap(DIVISION_BY_ZERO)` symbolically; `if(false, div(1,0), 0)` is `Value(0)`.
4. `test_int_bound_trap.py` — `mul` chain exceeding 2^64 yields `Trap(VALUE_TOO_LARGE)`, and the solver *finds* the witness when asked for non-equivalence against a bounded-safe program.
5. `test_symbolic_tier_verdicts.py` — identical-hash programs short-circuit at Tier 1 (unchanged); two syntactically different, semantically equal programs (commutative reordering, which `canonicalize.py` deliberately does not normalize) reach `EQUIV_SYMBOLIC` with the bounded assumptions listed; a planted incorrect pair yields `NON_EQUIV` with a `counterexampleRef` that re-executes correctly.
6. `test_fail_closed.py` — an op outside `K0_OPS`, a program exceeding the unroll bound, and a solver timeout each yield `UNKNOWN` with a recorded reason; none yields `EQUIV_*`.
7. `test_solver_unavailable.py` — with `z3` import monkeypatched away, Tier 2 returns `UNKNOWN(solver_unavailable)` and no exception escapes.
8. `test_wire_conformance.py` — every emitted `EquivalenceResult`, `analyzer-result`, and `counterexample` validates against `schemas/sre/*.schema.json` (extend `tests/sre/test_wire_conformance.py` or mirror it).
9. `test_compute_ledger_charged.py` — solver time appears in the ledger; a Tier 1 hit charges zero solver time (preserving the existing comment in `equivalence.py`).

**Determinism:** Z3 must be constructed with a fixed seed and `set_param("sat.random_seed", 0)`, `("smt.random_seed", 0)`; record the solver version in the analyzer result. Document that solver *timing* is nondeterministic and that only the verdict is compared across runs (AGENTS.md definition of done requires naming the source of nondeterminism).

### BEST-VERIF-03 (P1) — External prover adapter (closes BEST-ASSURE-10)

**Deliverable:** `src/bestsad/verify/external.py` and wiring so that `semantic_equivalence_claim(proof_ref=...)` in `assurance/integration.py` can be handed a *structured* external result rather than an opaque reference.

**Supported result formats in v0.1:**
- BestSad SMT analyzer result (from BEST-VERIF-02) — provenance `internal-solver`, `is_external=True` (the solver is a third-party engine even when we drive it).
- Kani JSON report (`cargo kani --output-format json`) — provenance `kani`; only meaningful once BEST-VERIF-05 exists, but the parser is cheap and lets an agent-run Kani result on the twin be ingested without special-casing later.
- Generic: `{tool, version, verdict, artifact_sha256, scope, assumptions}` — for Alive2 or Lean outputs when M12/V6 arrive.

Each ingested result becomes an `EvidenceObject` with `warrant=FORMAL`, `is_external=True`, `method` naming the tool and version, and `content_hash` of the raw artifact. `NEVER_SUFFICIENT_ALONE` is enforced by the existing predicate; do not bypass it.

**Acceptance:** extend `tests/assurance/test_acceptance.py` with an eleventh criterion: *an external FORMAL result alone does not promote; the same result plus the Tier 3 corroboration on the same contract does; a stale contract (K0 hash mismatch) fails closed* (reuse the pattern of `test_10_stale_semantic_certificates_fail_closed_for_core_use`). Update `docs/architecture/ASSURANCE_WORK_ORDERS.md` BEST-ASSURE-10 from *Partial* to *Done*, naming the adapter.

### BEST-VERIF-04 (P1) — Non-vacuity of specifications (the LLM-spec trust hole)

**Deliverable:** `src/bestsad/verify/vacuity.py`.

**Rule:** no solver-backed `EQUIV_SYMBOLIC` or contract proof is promotable unless the *same contract* has produced `NON_EQUIV` (or a failed proof) against at least one **mutant** of the program pair. Mutants are generated deterministically from a seed by single-op substitution within the same type signature (e.g., `lt`→`le`, `add`→`sub`, swapping `if` branches). If every mutant is also reported equivalent, the contract is **vacuous** and the claim is refused with reason `contract_vacuous`.

This is the generalization of ADR-0014's incorrect-lowering fixture and is the control that makes agent- or LLM-authored contracts acceptable at all: the proposer cannot pass by writing a contract that accepts everything.

**Acceptance (`tests/verify/test_vacuity.py`):** a contract with a trivially-true observable (e.g., scope restricted to an empty domain) is detected as vacuous; a sound contract survives; the vacuity record is attached to the claim's `evidenceRefs`. Also **verify the fixture ADR-0014 references**: `tests/languages/test_incorrect_lowering_is_caught.py` is named in the ADR but is **not present** in the delivered package (only `tests/languages/test_bsld_lowering.py` is). Either the test exists under another name — then correct the ADR — or it is missing — then write it as part of this work order and record the gap in `docs/experiments/STATUS.md` standing residuals. Do not leave an ADR pointing at a test that does not exist.

### BEST-VERIF-05 (P2, gated) — Rust twin of K0 verified with Kani

**Gate:** do **not** start until *either* ADR-0002 revisit trigger fires (reference execution > ~10% of experimental compute, or M11/M12 land with per-node crossing) *or* the repository owner explicitly authorizes the twin as a verification asset for the machine leg. Record the authorization in the ADR.

**Deliverable:** `docs/adr/0020-rust-k0-twin-under-kani.md` (provisional) and, when gated in, a crate at `k0rs/` (workspace root, outside `src/` so the Python package layout in ADR-0003 is unchanged).

**What Kani will and will not prove about the twin (do not overstate in the ADR):**

| Property | Kani harness | Warrant when green |
|---|---|---|
| Every K0 op is total: returns `Value` or `Trap(kind)`, never panics, for all inputs within bounds | `#[kani::proof]` per op with `kani::any()` operands, list length bounded via `kani::unwind(N)` | `FORMAL`, bounded, external |
| Integer bound: no result with `|r| > 2^64` escapes without `VALUE_TOO_LARGE` | proof over `i128` representation with explicit bound check (Kani's overflow checks catch the representation; the K0 bound is a user assertion) | `FORMAL` |
| List bound: no list exceeds 4096 without `LIST_TOO_LONG` | user assertion in `cons`/`append`/`range` harnesses | `FORMAL`, bounded |
| Fuel monotonicity: fuel never increases; charged fuel equals the ADR-0008 cost model | `#[kani::ensures]` contract on the step function | `FORMAL` — this is the one property the *Python* reference cannot get from any tool today, and the strongest argument for the twin |
| Agreement with the Python reference | **not a Kani property.** M1 differential sweep over the same 10⁵-program corpus, both implementations, identical `Value|Trap(kind)` | `CORROBORATED` (sampled) — the reference remains the anchor |
| Aliasing/provenance UB, concurrency | Kani does not check these | Miri in the Rust test loop; no concurrency exists in K0 |

The twin's `KERNEL_VERSION_HASH` must be computed from the same descriptor and must equal the Python constant; a mismatch is a build failure. If the two implementations ever disagree, the **Python reference wins** and the twin is fixed (ADR-0002).

**Acceptance:** `cargo kani` green on all harnesses within a 60 s per-harness budget (harnesses exceeding it are split, not loosened); M1 sweep parity; ADR-0020 states plainly that Kani proofs are bounded and which UB classes are unchecked.

### BEST-VERIF-06 (P1) — Gate G-V

**Deliverable:** new job `verification (Gate G-V)` in `.github/workflows/ci.yml` running `pytest -q tests/verify`, and the matching entry in `scripts/ci_local.py` `GATES` with a **probe** `("z3", [python, "-c", "import z3; ..."])` so that a machine without Z3 reports `UNAVAILABLE` (exit 2 overall), per ADR-0018. `tests/integrity/test_local_gates_mirror_ci.py` must pass unchanged — it is the check that `ci.yml` and `ci_local.py` cannot drift.

Update `docs/experiments/STATUS.md` with a "Verification plane" section listing G-V and, until BEST-VERIF-05 is gated in, the standing residual: *K0 has no machine-checked proof of its own implementation; its assurance rests on the M1 differential sweep (CORROBORATED) and on the encoder-vs-reference differential test (BEST-VERIF-02 #1).*

---

## 4. ADR-0019 skeleton (agent fills in; do not omit sections)

```
# ADR 0019 — Adopt Z3 as the symbolic-equivalence engine (spec V4)
**Status:** Provisional
**Date:** <commit date>
**Governs:** src/bestsad/verify/smt/, bsir/equivalence.py Tier 2, spec §19 V4, §19.1
**Relates to:** ADR-0002 (dependency discipline), ADR-0008 (semantics encoded), ADR-0014 (obligations discharged), ADR-0018 (UNAVAILABLE gate)
## Context   — the stub; the obligations it leaves open; the build-vs-adopt rule
## Decision  — optional dependency group; fail-closed on absence; bounded proofs labelled bounded; fuel excluded
## What is lost, stated plainly — bounded ≠ unbounded; encoder is a second reading of K0; solver nondeterministic in time
## Consequences
## Revisit trigger — >20% timeouts; V6 mechanized proof becomes available; fuel modelling needed for a claim
```

---

## 5. Out of scope for v0.1 (recorded so they are not "obvious improvements" re-proposed)

- Modelling fuel and depth traps symbolically. Excluded by assumption; a claim needing them is `UNKNOWN`.
- Any change to `canonicalize.py` normalization. The symbolic tier exists precisely so that canonicalization can stay deliberately incomplete (ADR-0013).
- Verus, Creusot, Prusti, Aeneas. All Rust-only; all downstream of BEST-VERIF-05.
- Lean/Coq mechanization (spec V6). Companion §11 and the adopt list point at Alive2-family tooling for the compiler leg first.
- LLM-*generated* harnesses as a feature. Agents may write contracts today; BEST-VERIF-04 is what makes that safe. No tooling is built to solicit them.

---

## 6. Constraints M12 (MLIR lowering + translation validation) must inherit

Recorded here because M12 is deferred and its authors will otherwise rediscover these:

1. Lowering rules are declarative data with attached proof obligations (ADR-0014) — the same shape as Cranelift's ISLE, which was designed so rules could be SMT-checked. Keep it that way; do not embed code in descriptors.
2. Translation validation is per-instance refinement checking (Alive2 model), not a whole-compiler proof. `verify/external.py` (BEST-VERIF-03) is where an Alive2 verdict is ingested; nothing new is needed in the assurance plane.
3. The ADR-0008 choice of truncated division was made *for* this leg. Any target whose `div` differs must reconcile in the lowering, with an obligation, not in K0.
4. If a Rust twin exists (BEST-VERIF-05), it — not the Python reference — is the natural executor for the machine leg, but its agreement with the reference remains a corroborated, not proven, fact.

---

## 7. Discrepancies found while preparing this document (for the owner)

1. ADR-0014 cites `tests/languages/test_incorrect_lowering_is_caught.py`; the delivered package does not contain it (BEST-VERIF-04 resolves).
2. `ASSURANCE_WORK_ORDERS.md` and `STATUS.md` are dated 2026-08-23; ADR-0018 is dated 2026-08-26 and ADR-0005 was narrowed 2026-08-24. STATUS should carry the ADR-0018 gate-runner change. Minor, but a reviewer reading STATUS alone will believe CI is live.
3. The research report's Stage 0 ("Kani on K0") was written without the package and is superseded by §1 of this document. Do not implement the report directly.

---

## 8. Definition of done for this document

- BEST-VERIF-01 through -04 and -06 complete; -05 has its provisional ADR and nothing else.
- `scripts/ci_local.py --fresh-venv` reports every gate `OK` or `UNAVAILABLE`, with the `UNAVAILABLE` list stated in the final commit message, and none `FAIL`.
- `KERNEL_VERSION_HASH` unchanged (`tests/kernel/test_frozen.py` green). If it changed, the work is rejected in full — that is the invariant.
- `artifacts/assurance_ledger.json` regenerated from EXP-001-DR still yields *capability claim INCONCLUSIVE, negative-result claim PROMOTED*. The verification plane must not move a result it did not produce.
