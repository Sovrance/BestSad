# ADR 0020 — A Rust twin of K0, verified with Kani (gated; not started)

**Status:** Provisional — the gate below has not fired, and no authorisation has been recorded
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
