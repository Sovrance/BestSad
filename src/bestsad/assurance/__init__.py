"""Semantic assurance and experimental claim protocol.

Implements `docs/architecture/BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md`: one
claim/evidence/dependency protocol so that every evolved primitive, genome, and experimental
capability claim has an explicit, machine-enforced assurance lifecycle.

The point is not to make exploration more conservative — candidate representations may still
evolve aggressively. It is to make the boundary between "invented", "works on examples",
"semantics preserved", and "experimentally supported capability gain" something the machine
enforces rather than something a reader has to reconstruct.
"""

from .claims import (
    CAPABILITY,
    CLAIM_CLASSES,
    COMPILER_CORRECTNESS,
    EXTERNAL_TRANSFER,
    GENOME_VALIDITY,
    NEGATIVE_RESULT,
    PRIMITIVE_SAFETY,
    PRIMITIVE_UTILITY,
    SEMANTIC_EQUIVALENCE,
    ClaimClass,
    make_claim,
    make_evidence,
    missing_evidence_kinds,
)
from .graph import (
    DependencyGraph,
    InvalidationEvent,
    propagate_invalidation,
    unsatisfied_dependencies,
)
from .integration import (
    ASSURANCE_LIFECYCLE,
    ASSURANCE_TO_MATURITY,
    GATE_ONLY_LIFECYCLE_STEPS,
    LifecycleViolation,
    MATURITY_TO_ASSURANCE,
    advance_lifecycle,
    capability_claim,
    experiment_envelope,
    genome_envelope,
    negative_result_claim,
    primitive_effect_claims,
    primitive_envelope,
    primitive_safety_claim,
    semantic_equivalence_claim,
)
from .ledger import AssuranceLedger, LedgerEvent, LedgerViolation
from .objects import (
    NEVER_SUFFICIENT_ALONE,
    NON_EXECUTABLE_STATES,
    AssumptionObject,
    AssuranceCertificate,
    ClaimObject,
    ClaimState,
    DependencyEdge,
    DependencyType,
    EvidenceObject,
    PromotionDecision,
    Warrant,
    content_id,
)
from .promotion import (
    PolicyGate,
    PromotionContext,
    PromotionRefused,
    PromotionVerdict,
    SelfPromotionRefused,
    evaluate,
    producer_may_transition,
)
from .roots import (
    ALL_ROOTS,
    BENCHMARK_ROOT,
    BSIR_ROOT,
    CODING_SCHEME_ROOT,
    EVALUATOR_ROOT,
    K0_ROOT,
    PREREGISTRATION_ROOT,
    SANDBOX_POLICY_ROOT,
    SemanticRoots,
    current_roots,
)

__all__ = [
    "ALL_ROOTS", "ASSURANCE_LIFECYCLE", "ASSURANCE_TO_MATURITY", "AssumptionObject",
    "AssuranceCertificate", "AssuranceLedger", "BENCHMARK_ROOT", "BSIR_ROOT", "CAPABILITY",
    "CLAIM_CLASSES", "CODING_SCHEME_ROOT", "COMPILER_CORRECTNESS", "ClaimClass", "ClaimObject",
    "ClaimState", "DependencyEdge", "DependencyGraph", "DependencyType", "EVALUATOR_ROOT",
    "EXTERNAL_TRANSFER", "EvidenceObject", "GATE_ONLY_LIFECYCLE_STEPS", "GENOME_VALIDITY",
    "InvalidationEvent", "K0_ROOT", "LedgerEvent", "LedgerViolation", "LifecycleViolation",
    "MATURITY_TO_ASSURANCE", "NEGATIVE_RESULT", "NEVER_SUFFICIENT_ALONE",
    "NON_EXECUTABLE_STATES", "PREREGISTRATION_ROOT", "PRIMITIVE_SAFETY", "PRIMITIVE_UTILITY",
    "PolicyGate", "PromotionContext", "PromotionDecision", "PromotionRefused",
    "PromotionVerdict", "SANDBOX_POLICY_ROOT", "SEMANTIC_EQUIVALENCE", "SelfPromotionRefused",
    "SemanticRoots", "Warrant", "advance_lifecycle", "capability_claim", "content_id",
    "current_roots", "evaluate", "experiment_envelope", "genome_envelope", "make_claim",
    "make_evidence", "missing_evidence_kinds", "negative_result_claim",
    "primitive_effect_claims", "primitive_envelope", "primitive_safety_claim",
    "producer_may_transition", "propagate_invalidation", "semantic_equivalence_claim",
    "unsatisfied_dependencies",
]
