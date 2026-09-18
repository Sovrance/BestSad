# Assurance integration — work-order status

Tracks `BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md` §13 against what is built.
Last updated: 2026-09-18 (the status documents that record the verification plane and the twin are all on `v1`, PRs #11–#17, see the record under the P2 items; the Kani adapter of BEST-ASSURE-10 has a real producer: the K0 twin of BEST-VERIF-05, merged in PR #10; BEST-ASSURE-10 itself was closed 2026-09-15 by BEST-VERIF-03; the gate runner of ADR-0018 is dated 2026-08-26 and ADR-0021 superseded ADR-0018 on 2026-09-15).

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
| BEST-ASSURE-10 | P2 | External formal/translation-validation adapters | External proof provenance preserved | **Done** (2026-09-15) — `src/bestsad/verify/external.py` (BEST-VERIF-03): structured ingestion of the BestSad SMT analyzer result, a Kani report, and a generic prover record into `FORMAL` evidence with `is_external=True`; `semantic_equivalence_claim(external_proof=...)`; the promotion predicate refuses an external proof without internal corroboration; acceptance test 11. Since 2026-09-16 the Kani adapter has a real producer: `scripts/kani_gate.py` ingests every `cargo kani` run on the K0 twin (BEST-VERIF-05, ADR-0020) through `from_kani_report` |

## The two P2 items

**BEST-ASSURE-09** annotates a compiler IR that does not exist yet. M11 (equality saturation)
and M12 (MLIR lowering + translation validation) are deferred behind gates in the implementation
plan, and S4/S5 were not reached — the EXP-001-DR run ended H0-consistent. Building assurance
annotations for a lowering path before the lowering path exists would produce a schema fitted to
a guess. The *predicate* it needs is already in place: §14's tenth acceptance test
(`test_10_stale_semantic_certificates_fail_closed_for_core_use`) proves a stale certificate
fails closed, so the compiler will inherit fail-closed behaviour rather than needing its own.
**Still deferred.**

**BEST-ASSURE-10** was *Partial* until 2026-09-15: the warrant model distinguished external
corroboration from internal proof, `EvidenceObject.is_external` marked provenance, and
`NEVER_SUFFICIENT_ALONE` enforced §1.7 for HEURISTIC/ASSERTED warrants — but the only
external-proof path was an opaque `proof_ref` that earned `FORMAL` and promoted alone, and there
was no prover to adapt to. **Done** by BEST-VERIF-03 (`BESTSAD_VERIFICATION_PLANE_ENG_v0.1.md`):

- `src/bestsad/verify/external.py` ingests three result shapes — the BestSad SMT analyzer
  result from the symbolic tier (provenance `internal-solver`, and still external: the engine
  is Z3), a Kani report of a stated shape (provenance `kani`; the K0 twin of BEST-VERIF-05
  gated in on 2026-09-16, see below), and a generic `{tool, version, verdict, artifact_sha256, scope,
  assumptions, kernel_version_hash}` record for Alive2 or Lean when M12/V6 arrive. Each becomes
  an `EvidenceObject` with `warrant=FORMAL`, `is_external=True`, `method` naming the tool and
  version, and `content_hash` of the raw artifact.
- `semantic_equivalence_claim(external_proof=...)` records the proof's provenance, scope and
  assumptions in the claim's scope, alongside whether the Tier 3 differential result on the
  same contract is attached as internal corroboration. The opaque `proof_ref` path is held to
  the same rule.
- `assurance/promotion.py` — the one predicate — refuses a claim whose proof is external and
  carries no internal corroboration. `NEVER_SUFFICIENT_ALONE` is unchanged; this is the same
  §1.7 rule applied to a warrant that *can* promote once corroborated.
- A result produced against a different K0 records the root id it actually holds for
  (`roots.k0_root_id`), and the predicate's source-hash check refuses it — the pattern of
  acceptance test 10.

Acceptance: `tests/assurance/test_acceptance.py::test_11_*` — an external FORMAL result alone
does not promote; the same result plus the Tier 3 corroboration does; a stale contract fails
closed. `tests/verify/test_external.py` covers the three ingestion shapes.

**The Kani adapter has a producer (2026-09-16).** BEST-VERIF-05 was gated in on the owner's
authorisation (ADR-0020, amended twice) and merged in PR #10: `k0rs/` is a Rust twin of K0 whose
build refuses to compile unless its kernel hash equals the Python `KERNEL_VERSION_HASH`, and
`k0rs/src/proofs.rs` carries 19 Kani harnesses (all green, slowest 2.3 s of the 60 s budget). What
this changes for the assurance plane, and what it does not:

- `scripts/kani_gate.py` runs `cargo kani`, converts the text output with
  `verify/twin.py::kani_report_from_output` (Kani 0.67 has no JSON output format, so the "Kani
  JSON report" the adapter was written against is now produced by this bridge rather than by
  Kani), and ingests it through `from_kani_report` on every run of the `K0 twin proofs` CI job.
  The report carries the bounds as `assumptions`; the evidence is `FORMAL`, `is_external=True`,
  bounded, exactly as §1.7 and BEST-ASSURE-10 require.
- The proofs are about the twin's pure step functions (integer bound, arithmetic totality, the
  zero-divisor trap, `mod`'s sign and magnitude, comparisons, the list bound, fuel accounting,
  the ADR-0008 cost model). Nothing reaching the evaluator verified within budget; ADR-0020's
  second amendment lists what was tried and removed. So no K0 *evaluator* claim gains a
  `FORMAL` warrant from this, in either implementation.
- Agreement between the twin and the Python reference stays `CORROBORATED`: the full M1 corpus
  (10⁵ programs, identical `Value | Trap(kind)` and identical step count) in the `K0 twin
  parity` job, never a proof. The Python reference remains normative (ADR-0002); if the two
  disagree, the twin is fixed. The promotion rule above is unchanged: a Kani result is external
  and promotes only with internal corroboration attached.

The standing residual in `docs/experiments/STATUS.md` is restated accordingly: K0 has bounded
machine-checked proofs of its arithmetic, bounds and fuel accounting in the twin, and no
machine-checked proof of its evaluator.

**Where this is recorded (PRs #11–#17, all merged into `v1` by the owner with every `ci.yml`
job green).** The verification plane and the twin changed what four status documents say, and
each was updated in its own pull request rather than left to drift; each later update that
recorded those pull requests went the same way:

| PR | Document | What it records | Merged (UTC) | Head |
|---|---|---|---|---|
| #11 | this file | the paragraph above: the Kani adapter's producer, what the proofs do and do not cover | 2026-09-16 16:02 | `7f7c4bd` |
| #12 | `docs/experiments/STATUS.md` | the merge record for PRs #8–#11 (contents, merge times, heads, job counts) and the restated K0 residual | 2026-09-16 22:53 | `1fe341b` |
| #13 | `CONTRIBUTING.md` | the draft-PR convention as exercised across #8–#12; the two twin checks in the pre-push list; genuine CI runs since #8; the `contents: read` workflow token | 2026-09-17 14:10 | `0aa37f2` |
| #14 | `REPOSITORY.md` | agent guidance for the twin under invariant 1 — the Python reference stays normative, the twin is hash-pinned and parity-checked, Kani's proofs are bounded and narrow, harnesses are split or removed, never loosened. Placed here because `AGENTS.md` is a delivered v0.2 document pinned in `MANIFEST_SHA256.txt` and is not edited | 2026-09-17 15:41 | `76ec5e4` |
| #15 | this file | this record, for PRs #11–#14 | 2026-09-18 01:01 | `ca30270` |
| #16 | `docs/experiments/STATUS.md` | the merge record extended to PRs #12–#15 | 2026-09-18 01:08 | `670256e` |
| #17 | `CONTRIBUTING.md` | PRs #13–#16 as further instances of the draft-PR convention, one file each | 2026-09-18 01:26 | `43eba75` |

The pattern these seven follow is the one BEST-ASSURE-10 itself insists on: a status file that
says something is done points at the evidence (the PR, the head, the jobs that ran), so the claim
can be checked without trusting the file.

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
