# ADR 0020 — A Rust twin of K0, verified with Kani (gated; not started)

**Status:** Accepted (2026-09-16, on the owner's authorisation; see the amendment)
**Date:** 2026-09-15
**Governs:** a future crate at `k0rs/` (workspace root, outside `src/`, so the Python package
layout of ADR-0003 is unchanged); the Kani ingestion path in `src/bestsad/verify/external.py`
**Relates to:** ADR-0002 (the Python reference is normative), ADR-0008 (the semantics the twin
must reproduce), ADR-0019 (the symbolic tier the twin would corroborate), ADR-0016 (the
invariant-1 lesson: do not move the frozen boundary for a good reason)
**Work order:** BEST-VERIF-05 in `docs/architecture/BESTSAD_VERIFICATION_PLANE_ENG_v0.1.md`

## Context

The research report that motivated the verification plane recommended "Kani as a mandatory CI
gate on K0". K0 is Python (ADR-0002) and Kani verifies Rust MIR, so that recommendation does
not survive contact with the package as shipped; the adjudication in the verification-plane
document (§1) reframes it as this ADR. The idea it keeps is real: a bounded model checker can
establish properties of an *implementation* that neither the differential sweep (M1) nor the
symbolic tier (ADR-0019) can, because both of those check programs *against* K0 rather than
checking K0 itself.

The twin is not free. It is a second implementation of the semantic anchor, and ADR-0002 is
explicit that a faster kernel "becomes a second implementation that must agree with this one
under the M1 differential test — the reference does not move". Two implementations of K0 are
two places for K0 to be wrong, and the whole program rests on there being one place that is
right by definition.

## Decision

**Do not start the twin until one of two things happens**, and record which one here when it
does:

1. ADR-0002's own revisit trigger fires — measured reference execution exceeds ~10% of total
   experimental compute, or M11/M12 land and the Python/native boundary starts crossing
   per-node rather than per-run; or
2. the repository owner explicitly authorises the twin as a verification asset for the machine
   leg (M12), independent of performance.

Until then this ADR is the whole deliverable of BEST-VERIF-05. The Kani ingestion path
(`verify/external.py::from_kani_report`, BEST-VERIF-03) already exists, and is cheap, so an
agent-run Kani result on the twin can be ingested without special-casing later; it accepts a
stated report shape and refuses anything else, and it will need calibrating against a real
report when one exists.

**When gated in**, the twin is built as follows, and these are commitments rather than
suggestions:

- The crate lives at `k0rs/`, outside `src/`. It computes `KERNEL_VERSION_HASH` from the same
  descriptor as `kernel/spec.py`, and a mismatch is a build failure.
- If the two implementations ever disagree, **the Python reference wins** and the twin is
  fixed (ADR-0002). Agreement is established by the M1 differential sweep over the same
  10⁵-program corpus, both implementations, identical `Value | Trap(kind)`, and is recorded as
  `CORROBORATED` (sampled), never as proved.
- Every `cargo kani` harness carries a 60 s budget. A harness that exceeds it is split, not
  loosened; a loosened bound is a weaker claim wearing the old label.
- The twin's results enter the assurance plane through `verify/external.py` with provenance
  `kani`, `warrant=FORMAL`, `is_external=True`, and are subject to the same corroboration rule
  as every other external proof (BEST-VERIF-03).

## What Kani would and would not prove — stated now so the ADR cannot overstate it later

| Property | Harness shape | Warrant when green |
|---|---|---|
| Every K0 op is total: returns `Value` or `Trap(kind)`, never panics, for all inputs within bounds | `#[kani::proof]` per op with `kani::any()` operands, list length bounded via `kani::unwind(N)` | `FORMAL`, **bounded**, external |
| Integer bound: no result with `\|r\| > 2^64` escapes without `VALUE_TOO_LARGE` | proof over an `i128` representation with an explicit bound check; Kani's overflow checks cover the representation, the K0 bound is a user assertion | `FORMAL` |
| List bound: no list exceeds 4096 without `LIST_TOO_LONG` | user assertion in the `cons`/`append`/`range` harnesses | `FORMAL`, bounded |
| Fuel monotonicity: fuel never increases, and charged fuel equals the ADR-0008 cost model | `#[kani::ensures]` contract on the step function | `FORMAL` — the one property the Python reference cannot get from any tool today, and the strongest argument for the twin |
| Agreement with the Python reference | **not a Kani property.** M1 differential sweep, both implementations | `CORROBORATED` (sampled); the reference remains the anchor |
| Aliasing/provenance UB, concurrency | Kani does not check these | Miri in the Rust test loop; K0 has no concurrency |

Every Kani proof above is *bounded*: `kani::unwind(N)` bounds loops, and `kani::any()` over a
bounded representation bounds values. A green `cargo kani` run says nothing about inputs
beyond those bounds, and the assurance record must carry the bounds, exactly as the symbolic
tier's records do (ADR-0019). Unchecked UB classes — aliasing, provenance — are named so that
"Kani green" is never read as "memory-safe by proof".

## Consequences

- Nothing changes in the package today. `k0rs/` does not exist; no build depends on `cargo`;
  Gate G-V does not run Kani.
- The K0 assurance residual stays as `docs/experiments/STATUS.md` states it: K0 has no
  machine-checked proof of its own implementation; its assurance rests on the M1 differential
  sweep (`CORROBORATED`) and on the encoder-versus-reference differential test (BEST-VERIF-02).
- If the twin is built, it — not the Python reference — is the natural executor for the machine
  leg, but its agreement with the reference remains a corroborated, not proven, fact (design
  §6.4).

## Revisit trigger

Either gate condition above. When one fires, amend this ADR with the date, the trigger that
fired, and (for condition 2) the owner's authorisation, then move it to *Accepted* before any
Rust is written. Verus, Creusot, Prusti and Aeneas are downstream of this ADR and are not
options until it is accepted (design §5).

## Amendment (2026-09-16) — gate condition 2 fired; the twin is authorised

The repository owner authorised the twin on 2026-09-16 ("Start BEST-VERIF-05, I authorize the
K0 twin"): gate condition 2 above, explicit authorisation as a verification asset for the machine
leg, independent of performance. Condition 1 (ADR-0002's compute trigger) has **not** fired and
is not claimed. This ADR moves to *Accepted* before any Rust is written, as the revisit trigger
required, and the commitments in "Decision" bind the implementation at `k0rs/`.

Two clarifications the implementation forced:

- Kani function contracts (`#[kani::ensures]`) are an unstable feature. The fuel property is
  proved with plain `#[kani::proof]` harnesses over the step function's `tick` and `charge`
  and over the per-op cost function, asserting the ADR-0008 cost model directly, rather than
  with contract attributes.
- The differential criterion between twin and reference is identical `Value | Trap(kind)`
  **and identical step count** on every case of the M1 corpus. The step count is the ADR-0008
  cost model observed end to end, so agreement on it is stronger than the outcome alone; the
  execution trace hash is not reproduced by the twin and is not compared.

## Amendment (2026-09-16, later the same day) — the crate exists; what Kani actually proved

`k0rs/` now exists (Rust, edition 2021, outside `src/`; `cargo build`, `cargo test`, `cargo
clippy -D warnings` and `cargo +nightly miri test` all clean). What follows replaces the
"Consequences" bullet that said nothing changes in the package, and states the proof surface as
it turned out, not as the table above hoped.

**Hash.** `k0rs/src/descriptor.rs` rebuilds the canonical descriptor (kernel version, the four
limits, the 40 operations with their signatures, strictness, attributes and traps) byte for byte
— 4524 bytes, identical to `json.dumps(kernel_descriptor(), sort_keys=True,
separators=(",", ":"))` — and `build.rs` refuses to compile the crate unless its SHA-256 equals
the Python `KERNEL_VERSION_HASH` (`9aa25728…3165`). `k0rs hash` prints it;
`bestsad.verify.twin.probe()` refuses any binary whose hash differs.

**Agreement with the reference (corroborated, not proven).** `tests/verify/test_k0_twin.py`
runs both implementations over one program per operation on the enumerated small domain, the
named edge cases (the 2^64 bound inclusive, `range` at 4096/4097, truncating `div`/`mod`, a
too-large literal, depth 300, fuel 0–3), and the M1 corpus drawn exactly as
`tests/kernel/test_differential.py::_sweep` draws it (seed 20260817, `Kernel(fuel=20_000)`):
the default 3000 everywhere and the full 10⁵ in the `K0 twin parity (BEST-VERIF-05)` job.
Criterion: identical `Value | Trap(kind)` **and identical step count** on every case. Result
on the full 10⁵: zero disagreements. Trace hashes are not compared (they are the Python
evaluator's record order, not K0). The Python reference remains normative.

**What Kani proved** (`k0rs/src/proofs.rs`, 19 harnesses, `cargo kani` 0.67.0 / CBMC, all
green, slowest 2.3 s against the 60 s budget; `scripts/kani_gate.py` holds the budget in CI and
ingests the run through `verify/external.py::from_kani_report`):

| Property (ADR-0008) | Harness(es) | Bound |
|---|---|---|
| The integer bound is exactly `\|v\| <= 2^64`; beyond it `value_too_large` | `bounded_is_exactly_the_k0_bound` | all of `i128` |
| `add sub mul neg abs min max` are total on bounded operands: a bounded value or `value_too_large`, never a panic; `neg`/`abs` never trap within the bound; `min`/`max` pick an operand | one harness per op | operands in `[-2^64, 2^64]` |
| `div`/`mod` trap `division_by_zero` exactly on a zero divisor, and on a nonzero divisor are total and bounded | `div_and_mod_trap_exactly_on_a_zero_divisor`, `div_by_…`, `mod_by_…` | as above |
| `mod` has the dividend's sign and is smaller in magnitude than the divisor | `mod_result_…` (two) | as above |
| `lt le gt ge` never trap and are the integer order | `comparisons_…` | as above |
| The list bound is exactly 4096; `range` traps `list_too_long` beyond it and otherwise charges `max(0, hi - lo)` | `list_length_check_…`, `range_span_…` | all lengths / bounded operands |
| Fuel never comes back; `tick` adds one and `charge` adds exactly its units; both trap `fuel_exhausted` exactly when the budget is exceeded; zero units is a no-op | `tick_…`, `charge_…` | all `u64` states |
| The per-op cost model is ADR-0008's: `cons` len, `tail` max(0, len-1), `append` la+lb, `map`/`filter`/`fold` len, nothing else charges | `cost_model_is_adr_0008` | lengths ≤ 4096 |
| A scalar cell and an empty list cost one unit under `eq` | `scalar_cells_cost_one`, `an_empty_list_costs_one` | — |

Every one of these is a proof about a *pure function* the evaluator calls, over the whole
stated domain, with Kani's own panic, overflow and unwinding checks on. None of them is a proof
about the evaluator as a whole.

**What Kani did not prove, and why.** Each of the following was written, run and timed; each
exceeded the 60 s budget by more than an order of magnitude and was removed rather than
loosened:

- Anything that reaches `Kernel::eval` or `apply_first_order` — even `add(1, 2)` on concrete
  inputs. CBMC unwinds the evaluator's recursion at every call site of every arm and models
  every `Vec<Value>` and `Box<Value>` (and their drop glue) on a symbolic heap.
- "`div` truncates toward zero" stated as a relation between quotient and operands
  (`a - q*b` has the dividend's sign and is smaller than `b`; or `q == a / b`). It needs a
  second 128-bit divider or a 128-bit multiplier; cadical, kissat and z3 all timed out, and so
  did a 20-bit-operand restatement. The rounding direction of `div` is therefore Rust's `/`
  by construction and is pinned by `tests/semantics.rs` and the sweep, not by Kani.
- `eq`'s cost on compound values (`Just`, `Pair`, a two-element list), recursively or with an
  explicit worklist.

So the "per-op totality" row of the table above holds for the integer, comparison, length
and fuel functions; totality of the evaluator on *values* (type dispatch, closures,
higher-order operations) rests on `tests/semantics.rs`, Miri, and the 10⁵ differential sweep
with step-count parity. The assurance residual in `docs/experiments/STATUS.md` is restated
accordingly: K0 now has bounded machine-checked proofs of its arithmetic, bounds and fuel
accounting *in the twin*; it still has no machine-checked proof of its evaluator, in either
implementation.

**Unchecked by Kani, as the table above already said:** aliasing and provenance UB (Miri runs
the Rust test loop: clean), concurrency (none in K0), and anything outside the stated bounds.
Kani's checks are bounded model checking; a green run is evidence within its `unwind` and
`assume` bounds and nothing beyond them, and `from_kani_report` records those bounds in the
evidence's `assumptions`.

**One thing the harnesses found in themselves:** the first version of
`bounded_is_exactly_the_k0_bound` used `v.abs()`, which overflows on `i128::MIN`; Kani failed
it. A harness must not contain the arithmetic it exists to check the kernel avoids.

**Consequences, revised.** `cargo` is now a build dependency of two CI jobs and two local
gates (`k0-twin-parity`, `k0-twin-proofs`), never of the Python package: `tests/verify/
test_k0_twin.py` skips when no twin can be found or built, and the local gates report
`UNAVAILABLE` (ADR-0021 semantics). The Python reference does not move; the twin is the
executor of choice for the machine leg only with its agreement re-established by the parity
job on every change.
