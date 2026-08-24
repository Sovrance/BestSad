"""Bestsad-specific claim classes (integration spec §2) and their builders (§9, §10).

Each class declares what evidence it needs *before* promotion, which warrants can carry it, and
which experimental conditions must be present. Sufficiency is declared here per class rather
than by comparing warrants on a global scale — for semantic equivalence a proof outranks a
benchmark, while for "this abstraction helps" a controlled experiment is what counts and a proof
is not even available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .objects import (
    ClaimObject,
    ClaimState,
    EvidenceObject,
    Warrant,
    content_id,
)

SEMANTIC_EQUIVALENCE = "semantic_equivalence"
PRIMITIVE_SAFETY = "primitive_safety"
PRIMITIVE_UTILITY = "primitive_utility"
GENOME_VALIDITY = "genome_validity"
COMPILER_CORRECTNESS = "compiler_correctness"
CAPABILITY = "capability"
NEGATIVE_RESULT = "negative_result"
EXTERNAL_TRANSFER = "external_transfer"


@dataclass(frozen=True, slots=True)
class ClaimClass:
    name: str
    description: str
    required_evidence_kinds: tuple[str, ...]
    sufficient_warrants: frozenset[Warrant]
    required_conditions: tuple[str, ...] = ()
    requires_statistics: bool = False
    requires_concentration_test: bool = False
    note: str = ""


CLAIM_CLASSES: dict[str, ClaimClass] = {
    SEMANTIC_EQUIVALENCE: ClaimClass(
        name=SEMANTIC_EQUIVALENCE,
        description="Primitive P is equivalent to a K0 expansion.",
        required_evidence_kinds=("semantic_hash", "differential_test"),
        # Differential testing alone is CORROBORATED, not FORMAL: §6 warns against labelling a
        # sampled equivalence check as a proof. FORMAL requires an exhaustive domain or a proof.
        sufficient_warrants=frozenset({Warrant.FORMAL, Warrant.RIGOROUS_COMPUTATION,
                                       Warrant.CORROBORATED}),
        note="Round-trip and procedural differential testing corroborate; they do not prove.",
    ),
    PRIMITIVE_SAFETY: ClaimClass(
        name=PRIMITIVE_SAFETY,
        description="P cannot escape the sandbox or reach evaluator state.",
        required_evidence_kinds=("integrity_suite", "sandbox_policy"),
        sufficient_warrants=frozenset({Warrant.FORMAL, Warrant.DIRECT_OBSERVATION,
                                       Warrant.CORROBORATED}),
    ),
    PRIMITIVE_UTILITY: ClaimClass(
        name=PRIMITIVE_UTILITY,
        description="P improves verified held-out composition.",
        required_evidence_kinds=("reuse_metric", "semantic_gain", "paired_ablation"),
        sufficient_warrants=frozenset({Warrant.EMPIRICAL}),
        requires_statistics=True,
    ),
    GENOME_VALIDITY: ClaimClass(
        name=GENOME_VALIDITY,
        description="Genome G uses only admitted primitives and canonical semantics.",
        required_evidence_kinds=("primitive_certificates", "genome_hash"),
        sufficient_warrants=frozenset({Warrant.FORMAL, Warrant.RIGOROUS_COMPUTATION}),
    ),
    COMPILER_CORRECTNESS: ClaimClass(
        name=COMPILER_CORRECTNESS,
        description="Lowering BSIR to a target preserves semantics.",
        required_evidence_kinds=("translation_validation", "reference_comparison"),
        sufficient_warrants=frozenset({Warrant.FORMAL, Warrant.RIGOROUS_COMPUTATION}),
    ),
    CAPABILITY: ClaimClass(
        name=CAPABILITY,
        description="Evolved representation improves generalized computational capability.",
        required_evidence_kinds=("preregistration", "condition_manifest", "compute_ledger",
                                 "causal_attribution"),
        sufficient_warrants=frozenset({Warrant.EMPIRICAL}),
        # §8: the F/H/I rule lives in the promotion predicate, not in report formatting.
        required_conditions=("F", "H", "I"),
        requires_statistics=True,
        requires_concentration_test=True,
    ),
    NEGATIVE_RESULT: ClaimClass(
        name=NEGATIVE_RESULT,
        description="EXP-001 does not support the target effect.",
        required_evidence_kinds=("experiment_manifest", "report"),
        sufficient_warrants=frozenset({Warrant.EMPIRICAL}),
        requires_statistics=True,
        # A null result needs a *valid* experiment, not a passing one. It does not need F/H/I to
        # have been beaten — only to have been run — because the claim being made is about the
        # absence of an effect, and §9 makes that promotable knowledge rather than a failure.
        note="A negative result is promotable knowledge: a supported constraint on the search "
             "space, not a failure of the assurance system.",
    ),
    EXTERNAL_TRANSFER: ClaimClass(
        name=EXTERNAL_TRANSFER,
        description="Gain transfers across model or task family.",
        required_evidence_kinds=("independent_run", "pinned_versions"),
        sufficient_warrants=frozenset({Warrant.EMPIRICAL, Warrant.CORROBORATED}),
        requires_statistics=True,
    ),
}


def make_evidence(
    kind: str,
    source: str,
    method: str,
    warrant: Warrant,
    payload: Mapping[str, Any],
    *,
    validity: str = "current",
) -> EvidenceObject:
    """Build a content-addressed evidence object."""
    digest = content_id(dict(payload), "ev")
    return EvidenceObject(
        evidence_id=digest,
        kind=kind,
        source=source,
        content_hash=digest,
        method=method,
        warrant=warrant,
        validity=validity,
        detail=dict(payload),
    )


def make_claim(
    claim_class: str,
    statement: str,
    *,
    producer: str,
    warrant: Warrant,
    subject_refs: Sequence[str] = (),
    scope: Mapping[str, Any] | None = None,
    evidence: Sequence[EvidenceObject] = (),
    dependencies: Sequence[str] = (),
    assumptions: Sequence[str] = (),
    source_hashes: Mapping[str, str] | None = None,
    claim_id: str | None = None,
    detail: Mapping[str, Any] | None = None,
    status: ClaimState = ClaimState.PROPOSED,
) -> ClaimObject:
    if claim_class not in CLAIM_CLASSES:
        raise KeyError(f"unknown claim class {claim_class!r}; have {sorted(CLAIM_CLASSES)}")
    claim = ClaimObject(
        claim_id=claim_id or "",
        statement=statement,
        claim_class=claim_class,
        scope=dict(scope or {}),
        subject_refs=tuple(subject_refs),
        producer=producer,
        warrant=warrant,
        status=status,
        evidence_refs=tuple(e.evidence_id for e in evidence),
        dependency_refs=tuple(dependencies),
        assumption_refs=tuple(assumptions),
        source_hashes=dict(source_hashes or {}),
        detail=dict(detail or {}),
    )
    if claim_id:
        return claim
    # Identity from content, so an edited claim is a different claim (§1.6).
    from dataclasses import replace

    return replace(claim, claim_id=claim.content_id())


def missing_evidence_kinds(claim: ClaimObject, evidence: Sequence[EvidenceObject]) -> list[str]:
    """Which of the claim class's required evidence kinds are absent."""
    spec = CLAIM_CLASSES.get(claim.claim_class)
    if spec is None:
        return []
    present = {e.kind for e in evidence if e.evidence_id in set(claim.evidence_refs)}
    return [kind for kind in spec.required_evidence_kinds if kind not in present]
