# Assurance integration — work-order status

Tracks `BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md` §13 against what is built.
Last updated: 2026-08-23.

| WO | Pri | Deliverable | Gate | State |
|---|---|---|---|---|
| BEST-ASSURE-01 | P0 | Shared claim/evidence/certificate schemas + content IDs | Schema and canonical-hash tests | **Done** — `assurance/objects.py`, 8 schemas in `schemas/`, `tests/assurance/test_schemas_and_ledger.py` |
| BEST-ASSURE-02 | P0 | Central promotion gate integrated with primitive lifecycle | Candidate cannot self-promote | **Done** — `assurance/promotion.py`, `PolicyGate` refuses to act for the producer; `advance_lifecycle` gates the last three steps (ADR-0009) |
| BEST-ASSURE-03 | P0 | Dependency graph rooted at K0/BSIR/evaluator/prereg | Invalidation propagation | **Done** — `assurance/roots.py`, `assurance/graph.py`; roots are *computed* from the live system, never stored |
| BEST-ASSURE-04 | P1 | M1/M2 semantic certificates + trace evidence | Semantic-root staleness tests | **Done** — `semantic_equivalence_claim()`; warrant is CORROBORATED for sampled differential testing, FORMAL only when exhaustive or proved (§6) |
| BEST-ASSURE-05 | P1 | M4 evaluator integrity certificate integration | Leak event invalidates descendants | **Done** — `EVALUATOR_ROOT` + `SANDBOX_POLICY_ROOT`; a leak quarantines rather than merely stales |
| BEST-ASSURE-06 | P1 | M5 F/G/H/I dependencies in promotion predicate | Missing control blocks capability claim | **Done** — moved out of report formatting (ADR-0010); both *missing* and *unbeaten* block |
| BEST-ASSURE-07 | P1 | M6/M8 primitive evidence and causal claim objects | Shortcut concentration quarantine | **Done** — `primitive_effect_claims()`; concentration result feeds the predicate |
| BEST-ASSURE-08 | P1 | M9 confirmatory report consumes promoted ClaimObject | Report cannot bypass gate | **Done** — `ReportGate._assurance_verdict`; `bestsad report --confirmatory` exits non-zero without a promoted claim |
| BEST-ASSURE-09 | P2 | Compiler/BSIR assurance annotations | Stale primitive rejected by lowering | **Deferred** — see below |
| BEST-ASSURE-10 | P2 | External formal/translation-validation adapters | External proof provenance preserved | **Partial** — see below |

## Why the two P2 items are not built

**BEST-ASSURE-09** annotates a compiler IR that does not exist yet. M11 (equality saturation)
and M12 (MLIR lowering + translation validation) are deferred behind gates in the implementation
plan, and S4/S5 were not reached — the EXP-001-DR run ended H0-consistent. Building assurance
annotations for a lowering path before the lowering path exists would produce a schema fitted to
a guess. The *predicate* it needs is already in place: §14's tenth acceptance test
(`test_10_stale_semantic_certificates_fail_closed_for_core_use`) proves a stale certificate
fails closed, so the compiler will inherit fail-closed behaviour rather than needing its own.

**BEST-ASSURE-10** is partially covered. The warrant model distinguishes external corroboration
from internal proof, `EvidenceObject.is_external` marks provenance, and `NEVER_SUFFICIENT_ALONE`
enforces §1.7's "external corroboration is never silently upgraded to internal proof". What is
absent is an adapter for any *specific* external prover — there is no Lean or Alive2 in the
dependency set to adapt to. `semantic_equivalence_claim(proof_ref=...)` accepts a reference and
records it with FORMAL warrant and external provenance; wiring a real prover is a matter of
producing that reference.

## §15 rollout against M0–M14

| Milestone | Assurance addition | State |
|---|---|---|
| M0 | Schemas, ledger claim namespace, promotion policy ADR | Done (ADR-0009, ADR-0010) |
| M1 | K0 content ID + semantic-anchor certificate + trace evidence | Done |
| M2 | BSIR canonicalization assumption root + equivalence certificates | Done |
| M3 | Baseline/variance claims with exact generator/model manifests | Done — evidence carries the E0 run id |
| M4 | Evaluator-integrity certificate as hard dependency | Done |
| M5 | F/G/H/I as promotion dependencies, not report-time checks | Done |
| M6 | Primitive lifecycle uses the central assurance gate | Done |
| M7 | SG-v2 produces evidence with coding-scheme content ID | Done |
| M8 | Per-primitive causal ClaimObjects and invalidation graph | Done |
| M9 | Confirmatory report generated only from promoted claims | Done |
| M10 | EXP-001 outputs both positive and negative ClaimObjects | Done — see below |
| M11–M14 | Future compiler/model evolution consumes stale-safe certificates | Deferred with M11–M14 |

## The M10 ledger, on real data

`artifacts/assurance_ledger.json` is built from the completed EXP-001-DR run. It contains both
claim kinds the milestone calls for, and they came out differently:

- The **capability claim** is `INCONCLUSIVE`. The predicate refused it on two independent
  grounds: its certificate is FAIL, and all three of F, H and I matched or beat the treatment.
- The **negative-result claim** is `PROMOTED`. It carries the search-space constraint the run
  implies, and a certificate recording that the experiment itself was valid.

That asymmetry is §9 working as designed: "A negative result is not a failure of the assurance
system; it becomes a supported constraint on the search space."

Query it:

```
bestsad assure roots
bestsad report EXP-001-DR-2026-08-23 --confirmatory
bestsad primitive explain prim:u0
bestsad assure stale
```
