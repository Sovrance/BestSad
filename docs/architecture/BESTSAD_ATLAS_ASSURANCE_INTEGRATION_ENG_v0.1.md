<!--
Source: BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.docx, supplied 2026-08-23.
Converted to Markdown for version control; the .docx is the authoritative original.
Tables and code blocks in the original lost some formatting in conversion — where this
file and the .docx disagree, the .docx governs.
-->

Bestsad Semantic Assurance & Experimental Claim Integration

Engineering Specification v0.1 — Atlas assurance machinery extracted into the machine-native language research program

# Executive intent

Bestsad already has the critical scientific boundaries: K0 as trusted semantic kernel, BSIR canonical semantic hashes, a hidden evaluator/integrity plane, pre-registration, confound controls, primitive promotion evidence, causal ablation, and content-addressed ledgers. This design turns those separate safeguards into one claim/evidence/dependency protocol so that every evolved primitive, genome, compiler transformation, and experimental capability claim has an explicit assurance lifecycle.

The goal is not to make Bestsad more conservative about exploration. Candidate representations may evolve aggressively. The goal is to make the boundary between 'invented', 'works on examples', 'semantics preserved', and 'experimentally supported capability gain' machine-enforced.

# 1. Shared reusable assurance protocol extracted from Atlas

Both integrations SHALL implement the same assurance semantics, even though their domain objects differ. The core lesson from Atlas is that producers of evidence are not allowed to promote their own conclusions. A claim is a versioned object with dependencies, evidence, a warrant, and an independently enforced lifecycle.

## 1.1 Canonical assurance objects

| Object | Purpose | Minimum fields |
|---|---|---|
| ClaimObject | A falsifiable proposition or guarantee that the system may rely on. | claim_id, statement, scope, subject_refs, producer, created_at, status |
| EvidenceObject | An observation, test, proof artifact, benchmark result, or external corroboration. | evidence_id, kind, source, content_hash, method, captured_at, validity |
| DependencyEdge | Declares that a claim/certificate depends on another claim, policy, model, source, schema, or artifact. | from_id, to_id, dependency_type, required_state |
| AssuranceCertificate | Machine-verifiable result explaining why a claim may be promoted. | certificate_id, claim_id, evidence_refs, dependency_refs, warrant, verifier, hashes |
| AssumptionObject | Explicit environmental or semantic condition whose change can invalidate descendants. | assumption_id, value/content_id, scope, active_from, status |
| PromotionDecision | Append-only decision from the policy gate, separate from the evidence producer. | decision_id, claim_id, from_state, to_state, reason, actor/policy, timestamp |

## 1.2 Claim lifecycle

The required lifecycle is:

PROPOSED  -> OBSERVED  -> VERIFIED  -> PROMOTED  -> {CONTESTED | STALE | QUARANTINED | INVALIDATED}  -> optionally VERIFIED/PROMOTED again only by a new promotion decision

Historical states are never rewritten. A rejected or invalidated claim remains queryable with its original evidence and the event that invalidated it.

## 1.3 Warrant model

| Warrant | Meaning | Examples |
|---|---|---|
| FORMAL | Kernel-checked or exact symbolic theorem/identity. | Lean theorem; canonical hash equality with proven semantics. |
| RIGOROUS_COMPUTATION | Numerical result with sound outward bounds or equivalent machine-rigorous guarantee. | Interval arithmetic; verified model checking. |
| DIRECT_OBSERVATION | Measured event from an authenticated/attested source. | Telemetry, signed sensor event, audit record. |
| CORROBORATED | Independent sources or implementations agree, with independence recorded. | Two telemetry systems; independent compiler/evaluator. |
| EMPIRICAL | Controlled experiment/benchmark with declared statistics and confounds. | A/B benchmark, pre-registered experiment. |
| HEURISTIC | Useful exploration not safe for trusted promotion by itself. | LLM judgment, floating scan, similarity score. |
| ASSERTED | Human/agent assertion without sufficient independent warrant. | User statement, generated hypothesis. |

Atlas E0/E1/E3 values may be preserved as profile-specific labels, but product code should consume the semantic warrant rather than assuming a universal numeric ordering.

## 1.4 Promotion predicate

promotable(claim, certificate) iff:  certificate.status == PASS  AND certificate.promotion_state == PROMOTED  AND all required dependency states are satisfied  AND all source/content hashes are current  AND all required assumptions match active assumption IDs  AND governing consent/security policy allows the claim  AND no quarantine/invalidation event is active  AND a policy gate distinct from the producer authorized promotion

## 1.5 Invalidation propagation

Invalidation is graph-based. When a dependency changes or becomes untrusted, descendants are recomputed as STALE or QUARANTINED. The engine SHALL not delete the old claim, silently downgrade it, or leave a previously promoted derivative active.

dependency X invalidated        |        +--> claim B -> STALE                 |                 +--> claim C -> STALE                          |                          +--> cached context / compiled artifact -> blocked until rebuilt

## 1.6 Content-addressed roots

Foundational semantics, policies, evaluator versions, schemas, model versions, normalization/configuration objects, and preregistrations SHALL be identified by content IDs. A content-ID change automatically makes dependent certificates stale.

## 1.7 Non-negotiable engineering invariants

Evidence producers cannot set final promotion state.

Quarantine is enforced at the write/promotion boundary, not by convention in individual scripts.

A certificate file existing on disk never implies the claim is trusted.

Every promoted claim has an explainable dependency path to evidence and active assumptions.

External corroboration is never silently upgraded to internal proof.

Uncertainty and rival explanations are first-class states, not errors to be hidden.

A stale or invalidated claim may remain historically visible but must not silently enter execution context.

Every material transition is append-only and auditable.

# 2. Bestsad-specific claim classes

| Claim class | Example | Required evidence before promotion |
|---|---|---|
| Semantic equivalence | Primitive P is equivalent to a K0 expansion. | Canonical semantic hash/proof/translation validation; differential tests are corroboration unless exhaustive. |
| Primitive safety | P cannot escape sandbox or access evaluator state. | Integrity suite + sandbox policy + source/content hashes. |
| Primitive utility | P improves verified held-out composition. | Reuse/SG-v2 metrics, paired ablation, matched controls. |
| Genome validity | Genome G only uses admitted primitives and canonical semantics. | Primitive certificates + genome hash + kernel version. |
| Compiler correctness | Lowering BSIR→target preserves semantics. | Translation validation/proof + reference interpreter comparison. |
| Capability claim | Evolved representation improves generalized computational capability. | Pre-registration + conditions F/G/H/I + statistics + compute ledger + causal attribution. |
| Negative/null result | EXP-001 does not support target effect. | Complete experiment manifest and honest report; this is promotable knowledge. |
| External transfer | Gain transfers across model/task family. | Independent held-out run with pinned model/evaluator versions. |

# 3. Assurance metadata on existing Bestsad artifacts

Do not replace the existing genome/primitive/experiment schemas. Add an `assurance` envelope and shared claim ledger.

Primitive  semantic_hash  lifecycle_state  ...  assurance:    claim_ids[]    certificate_refs[]    dependency_refs[]    kernel_content_id    evaluator_content_id    promotion_stateGenome  ...  assurance:    primitive_certificate_refs[]    semantic_root    experiment_claim_refs[]ExperimentRun  ...  assurance:    preregistration_content_id    evaluator_content_id    condition_manifest_id    compute_ledger_id    claim_ids[]    report_certificate_ref

## 3.1 New schemas

schemas/  claim.schema.json  evidence.schema.json  assurance-certificate.schema.json  dependency-edge.schema.json  assumption.schema.json  promotion-decision.schema.json  semantic-equivalence-certificate.schema.json  capability-claim-certificate.schema.json

# 4. Semantic root and invalidation graph

K0, the reference interpreter, BSIR canonicalization rules, evaluator version, hidden benchmark manifest, coding scheme/kappa, and pre-registration are content-addressed assumption roots. A change to any root automatically stales descendant primitive/genome/experiment claims.

K0 semantic kernel content ID        |        +--> primitive equivalence cert                 |                 +--> admitted primitive                          |                          +--> genome                                   |                                   +--> experiment result                                            |                                            +--> capability claim

This directly prevents the Atlas failure mode where regenerated outputs from rejected foundational semantics could look promotable.

# 5. Primitive lifecycle convergence

Integrate assurance with the existing primitive lifecycle rather than creating a second promotion system.

DISCOVERED -> CANDIDATE -> SEMANTICS_VERIFIED -> EXPERIMENTALLY_SUPPORTED -> CORE_ELIGIBLE -> COREAny dependency failure: -> STALE or QUARANTINEDOnly a promotion gate may perform:SEMANTICS_VERIFIED -> EXPERIMENTALLY_SUPPORTED -> CORE_ELIGIBLE -> CORE

The abstraction discovery/evolution agent may propose primitives and attach evidence, but cannot write CORE eligibility.

# 6. K0/BSIR assurance integration

Every semantic-equivalence certificate names the K0 content ID and BSIR canonicalization version.

Human projection is never the semantic root; it can be evidence/visualization only.

Round-trip/procedural differential testing remains required, but should not be mislabeled FORMAL unless the checked domain is exhaustive or a proof exists.

A canonical semantic-hash collision or canonicalization defect invalidates all dependent primitive certificates.

Execution trace hashes become evidence objects linked to the exact interpreter version.

# 7. Evaluator integrity as an assurance root

M4's hidden evaluator/integrity plane becomes a first-class AssumptionObject. Capability claims require the exact evaluator content ID, sandbox policy, contamination checks and benchmark manifest.

capability claim promotable only if:  preregistration current  AND evaluator integrity PASS  AND no contamination event  AND required conditions complete  AND compute/scaffolding matching within tolerance  AND statistics gate PASS  AND source hashes current  AND policy gate approves

If a hidden-test leak or evaluator defect is discovered later, the dependency graph marks all affected experiment claims stale automatically without deleting their historical results.

# 8. Confound controls F/G/H/I become dependency requirements

| Condition | Assurance interpretation | Capability-claim effect |
|---|---|---|
| F Compression-matched | Assumption/evidence that gains are not mere token shortening. | Missing/failed F blocks representation-capability promotion. |
| G Human-expert DSL | Strong competing baseline evidence. | Claim must report whether evolved language beats it; no special-casing. |
| H Scaffolding-matched | Delivered prompt/examples/retry budgets are evidence objects. | Residual mismatch taints or blocks claim according to preregistration. |
| I Search-only | Compute ledger demonstrates equalized search opportunity. | Unmatched compute blocks causal representation claim. |

The existing rule that reporting refuses a capability claim when F, H or I is missing should move from report formatting into the central promotion predicate.

# 9. Capability Claim Object

{  "claim_id": "claim:exp001:representation-capability",  "statement": "Evolved representation improves verified compositional OOD synthesis",  "scope": {...},  "treatment_condition": "D",  "comparators": ["A","F","G","H","I"],  "effect_metric": "...",  "preregistration_content_id": "...",  "semantic_kernel_content_id": "...",  "evaluator_content_id": "...",  "compute_ledger_id": "...",  "evidence_refs": [...],  "causal_attribution_refs": [...],  "warrant": "EMPIRICAL",  "status": "VERIFIED|PROMOTED|INCONCLUSIVE|REJECTED",  "promotion_state": "...",  "source_hashes": {...}}

Null/negative claims use the same structure. A negative result is not a failure of the assurance system; it becomes a supported constraint on the search space.

# 10. Causal attribution and primitive-level claims

M8 paired ablations should emit claim/evidence objects for each primitive rather than only a final table.

primitive P  -> direct-effect claim  -> indirect-effect claim  -> ablation-equivalence certificate  -> gain-concentration evidence  -> suspicious-primitive flags  -> lifecycle promotion decision

If one shortcut primitive explains most of the apparent gain, the top-level capability claim becomes INCONCLUSIVE/QUARANTINED according to the pre-registered concentration rule.

# 11. Compiler and future machine-native language runtime

The assurance protocol should become part of Bestsad's eventual compiler IR rather than just experiment metadata. An evolved primitive may carry proof obligations, effects, resource bounds, provenance and semantic-equivalence certificate references.

primitive <id> {  semantics_root: <K0-content-id>  requires: [...]  guarantees: [...]  effects: [...]  resource_contract: {...}  equivalence_certificate: <content-id>  evidence: [...]  lifecycle: SEMANTICS_VERIFIED}

A compiler/runtime must refuse to treat a stale primitive certificate as CORE. This enables controlled self-modification: language evolution is fast, semantic promotion is independently gated.

# 12. API/CLI and ledger

bestsad assure claim show <id>bestsad assure graph <id>bestsad assure verify <artifact>bestsad assure stalebestsad primitive explain <id>bestsad experiment claims <run-id>bestsad report --confirmatory <run-id>   # hard-fails if promotion dependencies fail

All decisions append to the existing content-addressed ledger. Pre-registration amendments, evaluator changes, primitive promotions and claim invalidations are immutable events.

# 13. Implementation work orders

| WO | Priority | Deliverable | Gate |
|---|---|---|---|
| BEST-ASSURE-01 | P0 | Shared claim/evidence/certificate schemas + content IDs | Schema and canonical-hash tests |
| BEST-ASSURE-02 | P0 | Central promotion gate integrated with primitive lifecycle | Candidate cannot self-promote |
| BEST-ASSURE-03 | P0 | Dependency graph rooted at K0/BSIR/evaluator/prereg | Invalidation propagation |
| BEST-ASSURE-04 | P1 | M1/M2 semantic certificates + trace evidence | Semantic-root staleness tests |
| BEST-ASSURE-05 | P1 | M4 evaluator integrity certificate integration | Leak event invalidates descendants |
| BEST-ASSURE-06 | P1 | M5 F/G/H/I dependencies in promotion predicate | Missing control blocks capability claim |
| BEST-ASSURE-07 | P1 | M6/M8 primitive evidence and causal claim objects | Shortcut concentration quarantine |
| BEST-ASSURE-08 | P1 | M9 confirmatory report consumes promoted ClaimObject | Report cannot bypass gate |
| BEST-ASSURE-09 | P2 | Compiler/BSIR assurance annotations | Stale primitive rejected by lowering |
| BEST-ASSURE-10 | P2 | External formal/translation-validation adapters | External proof provenance preserved |

# 14. Acceptance tests

A primitive generated by the evolution agent cannot promote itself to CORE.

Changing K0 or BSIR semantic-root content ID stales every dependent primitive/genome claim.

A hidden-evaluator integrity failure invalidates affected capability claims.

Missing F, H or I prevents a confirmatory capability claim even if treatment accuracy is high.

Condition G may beat the treatment and the system reports it without special handling.

An ablated primitive re-expands to K0-equivalent semantics before causal effect is accepted.

A compression-only primitive can be useful but cannot be promoted as generalized capability evidence.

A null EXP-001 produces a promoted negative-result ClaimObject when the experiment is valid.

Report generation consumes the central promotion predicate rather than duplicating its own rules.

Stale semantic certificates make compiler/runtime CORE use fail closed.

# 15. Rollout against current M0-M14 plan

| Current milestone | Assurance addition |
|---|---|
| M0 | Add schemas, ledger claim namespace, promotion policy ADR. |
| M1 | K0 content ID + semantic-anchor certificate + trace evidence. |
| M2 | BSIR canonicalization assumption root + semantic-equivalence certificates. |
| M3 | Baseline/variance claims with exact task-generator/model manifests. |
| M4 | Evaluator-integrity certificate as hard dependency. |
| M5 | F/G/H/I become promotion dependencies, not report-time checks. |
| M6 | Primitive lifecycle uses central assurance gate. |
| M7 | SG-v2 calculation produces evidence artifact with coding-scheme content ID. |
| M8 | Per-primitive causal ClaimObjects and invalidation graph. |
| M9 | Confirmatory report is generated only from promoted top-level claims. |
| M10 | EXP-001 outputs both positive and negative ClaimObjects. |
| M11-M14 | Future compiler/model evolution consumes stale-safe semantic certificates. |

# 16. Definition of done

Bestsad has one central claim/evidence/promotion path across semantics and experiments.

K0/BSIR/evaluator/preregistration are content-addressed dependency roots.

Primitive lifecycle cannot bypass assurance.

Capability claims are impossible without required controls and statistics.

Null/negative results are first-class certified knowledge.

Compiler evolution can later consume semantic certificates directly.

External proof/validation systems preserve provenance and cannot silently strengthen warrant.

# 17. Repository references used for this design

Sovrance/BestSad, current branch:

README.md — trusted semantic kernel/evaluator boundary and contested thesis.

IMPLEMENTATION_PLAN_v0.2.md — M1 K0, M2 BSIR, M4 evaluator integrity, M5 confound controls, M6 primitive lifecycle, M8 causal attribution, M9 reporting gates.

BESTSAD_RESEARCH_ARCHITECTURE_EXPERIMENTAL_SPEC_v0.2.md — normative experimental architecture referenced by the implementation plan.

