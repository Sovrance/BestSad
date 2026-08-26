"""Wiring the assurance protocol onto Bestsad's existing objects (spec §3, §5–§10).

The integration spec is explicit that this must not become a second promotion system: "integrate
assurance with the existing primitive lifecycle rather than creating a second promotion system"
(§5). So the existing schemas are untouched and the existing maturity ladder keeps its meaning —
this module adds an `assurance` envelope alongside, and maps between the two ladders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..genomes.registry import Genome, Primitive
from .claims import (
    CAPABILITY,
    GENOME_VALIDITY,
    NEGATIVE_RESULT,
    PRIMITIVE_SAFETY,
    PRIMITIVE_UTILITY,
    SEMANTIC_EQUIVALENCE,
    make_claim,
    make_evidence,
)
from .objects import ClaimObject, ClaimState, EvidenceObject, Warrant, content_id
from .roots import (
    BENCHMARK_ROOT,
    BSIR_ROOT,
    CODING_SCHEME_ROOT,
    EVALUATOR_ROOT,
    K0_ROOT,
    PREREGISTRATION_ROOT,
    SANDBOX_POLICY_ROOT,
    SemanticRoots,
)

# --- §5 primitive lifecycle convergence -------------------------------------------------------

#: The assurance ladder from §5, and the spec §11 maturity it corresponds to.
#:
#: The two ladders were designed separately and do not have the same joints. Rather than replace
#: spec §11's EXP/OBS/SPEC/VER/CANONICAL/CORE — which is normative, and which the primitive record schema
#: encodes — the assurance states map onto it. The mapping is deliberately *not* a bijection:
#: assurance distinguishes "semantics verified" from "experimentally supported", which spec §11
#: rolls into VER, and that distinction is the point of the whole protocol.
ASSURANCE_LIFECYCLE: tuple[str, ...] = (
    "DISCOVERED",
    "CANDIDATE",
    "SEMANTICS_VERIFIED",
    "EXPERIMENTALLY_SUPPORTED",
    "CORE_ELIGIBLE",
    "CORE",
)

MATURITY_TO_ASSURANCE: dict[str, str] = {
    "EXP": "CANDIDATE",
    "OBS": "CANDIDATE",
    "SPEC": "SEMANTICS_VERIFIED",
    "VER": "SEMANTICS_VERIFIED",
    # CANONICAL is the last state before CORE on both ladders, so it lands on CORE_ELIGIBLE.
    # It is *not* CORE: a proved canonical identity says the primitive and its expansion are
    # one semantic object, which is a precondition for a kernel change and not a licence for
    # one (SRE v0.1, ADR 0017).
    "CANONICAL": "CORE_ELIGIBLE",
    "CORE": "CORE",
}

ASSURANCE_TO_MATURITY: dict[str, str] = {
    "DISCOVERED": "EXP",
    "CANDIDATE": "EXP",
    "SEMANTICS_VERIFIED": "VER",
    "EXPERIMENTALLY_SUPPORTED": "VER",
    "CORE_ELIGIBLE": "CANONICAL",
    "CORE": "CORE",
}

#: Transitions only a promotion gate may make (§5).
GATE_ONLY_LIFECYCLE_STEPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("SEMANTICS_VERIFIED", "EXPERIMENTALLY_SUPPORTED"),
        ("EXPERIMENTALLY_SUPPORTED", "CORE_ELIGIBLE"),
        ("CORE_ELIGIBLE", "CORE"),
    }
)


class LifecycleViolation(Exception):
    """An actor attempted a lifecycle step it is not permitted to make."""


def advance_lifecycle(
    current: str, target: str, *, actor_is_gate: bool
) -> str:
    """Move a primitive along the assurance lifecycle, enforcing who may do what (§5).

    The abstraction discovery/evolution agent may propose primitives and attach evidence, but
    cannot write CORE eligibility — so the last three steps require a gate.
    """
    if current not in ASSURANCE_LIFECYCLE or target not in ASSURANCE_LIFECYCLE:
        raise LifecycleViolation(f"unknown lifecycle state: {current!r} -> {target!r}")
    if (current, target) in GATE_ONLY_LIFECYCLE_STEPS and not actor_is_gate:
        raise LifecycleViolation(
            f"{current} -> {target} may only be performed by a promotion gate (§5); an "
            "evidence producer may propose and attach evidence but not promote itself"
        )
    forward = ASSURANCE_LIFECYCLE.index(target) > ASSURANCE_LIFECYCLE.index(current)
    if not forward:
        raise LifecycleViolation(
            f"{current} -> {target} is not a forward transition; regressions are recorded as "
            "STALE or QUARANTINED invalidation events, never as a rewritten lifecycle"
        )
    return target


# --- §3 assurance envelope --------------------------------------------------------------------


def primitive_envelope(
    primitive: Primitive,
    *,
    roots: SemanticRoots,
    claim_ids: Sequence[str] = (),
    certificate_refs: Sequence[str] = (),
    dependency_refs: Sequence[str] = (),
    assurance_state: str | None = None,
) -> dict:
    """The `assurance` envelope added alongside an existing primitive record (§3).

    Does not replace `Primitive.to_record()`; it accompanies it.
    """
    return {
        "claim_ids": list(claim_ids),
        "certificate_refs": list(certificate_refs),
        "dependency_refs": list(dependency_refs),
        "kernel_content_id": roots.get(K0_ROOT),
        "bsir_content_id": roots.get(BSIR_ROOT),
        "evaluator_content_id": roots.values.get(EVALUATOR_ROOT, ""),
        "promotion_state": assurance_state or MATURITY_TO_ASSURANCE.get(
            primitive.maturity, "CANDIDATE"
        ),
        "declared_maturity": primitive.maturity,
    }


def genome_envelope(
    genome: Genome,
    *,
    roots: SemanticRoots,
    primitive_certificate_refs: Sequence[str] = (),
    experiment_claim_refs: Sequence[str] = (),
) -> dict:
    return {
        "primitive_certificate_refs": list(primitive_certificate_refs),
        "semantic_root": roots.get(K0_ROOT),
        "experiment_claim_refs": list(experiment_claim_refs),
        "genome_content_hash": genome.content_hash(),
    }


def experiment_envelope(
    *,
    roots: SemanticRoots,
    preregistration_content_id: str,
    condition_manifest_id: str,
    compute_ledger_id: str,
    claim_ids: Sequence[str] = (),
    report_certificate_ref: str | None = None,
) -> dict:
    return {
        "preregistration_content_id": preregistration_content_id,
        "evaluator_content_id": roots.values.get(EVALUATOR_ROOT, ""),
        "condition_manifest_id": condition_manifest_id,
        "compute_ledger_id": compute_ledger_id,
        "claim_ids": list(claim_ids),
        "report_certificate_ref": report_certificate_ref,
    }


# --- §6 semantic-equivalence claims ------------------------------------------------------------


def semantic_equivalence_claim(
    primitive: Primitive,
    *,
    roots: SemanticRoots,
    producer: str,
    differential_cases: int,
    exhaustive: bool = False,
    proof_ref: str | None = None,
) -> tuple[ClaimObject, list[EvidenceObject]]:
    """Claim that a primitive is equivalent to its K0 expansion.

    Warrant follows §6: a differential test over a sampled domain is CORROBORATED, not FORMAL.
    FORMAL requires the checked domain to be exhaustive, or an actual proof artifact. Labelling
    sampled testing as a proof is the specific mislabelling §6 warns about, and it would let a
    primitive reach CORE eligibility on evidence that cannot bear it.
    """
    hash_evidence = make_evidence(
        kind="semantic_hash",
        source="bestsad.bsir.canonicalize",
        method="canonical semantic hash of the expansion under alpha-normalisation",
        warrant=Warrant.FORMAL,
        payload={
            "primitive_id": primitive.primitive_id,
            "semantic_id": primitive.semantic_id,
            "bsir_content_id": roots.get(BSIR_ROOT),
            "kernel_content_id": roots.get(K0_ROOT),
        },
    )
    differential = make_evidence(
        kind="differential_test",
        source="bestsad.kernel.interpreter",
        method=("exhaustive differential execution" if exhaustive
                else "sampled differential execution against the K0 reference interpreter"),
        warrant=Warrant.RIGOROUS_COMPUTATION if exhaustive else Warrant.CORROBORATED,
        payload={"cases": differential_cases, "exhaustive": exhaustive},
    )
    evidence = [hash_evidence, differential]

    if proof_ref:
        evidence.append(
            make_evidence(
                kind="proof_artifact", source=f"external:{proof_ref}",
                method="mechanized proof", warrant=Warrant.FORMAL,
                payload={"proof_ref": proof_ref},
            )
        )
        warrant = Warrant.FORMAL
    elif exhaustive:
        warrant = Warrant.RIGOROUS_COMPUTATION
    else:
        warrant = Warrant.CORROBORATED

    claim = make_claim(
        SEMANTIC_EQUIVALENCE,
        f"Primitive {primitive.primitive_id} is semantically equivalent to its K0 expansion.",
        producer=producer,
        warrant=warrant,
        subject_refs=(primitive.primitive_id,),
        scope={"kernel_version": primitive.kernel_version if hasattr(primitive, "kernel_version")
               else "K0"},
        evidence=evidence,
        assumptions=(K0_ROOT, BSIR_ROOT),
        source_hashes={K0_ROOT: roots.get(K0_ROOT), BSIR_ROOT: roots.get(BSIR_ROOT)},
    )
    return claim, evidence


def primitive_safety_claim(
    primitive: Primitive, *, roots: SemanticRoots, producer: str, vectors_blocked: Sequence[str]
) -> tuple[ClaimObject, list[EvidenceObject]]:
    """Claim that a primitive cannot escape the sandbox or reach evaluator state (§2)."""
    evidence = [
        make_evidence(
            kind="integrity_suite", source="tests/integrity",
            method="red-team suite: every vector attempted and blocked",
            warrant=Warrant.DIRECT_OBSERVATION,
            payload={"vectors_blocked": sorted(vectors_blocked)},
        ),
        make_evidence(
            kind="sandbox_policy", source="bestsad.evaluator.sandbox",
            method="policy content id", warrant=Warrant.DIRECT_OBSERVATION,
            payload={"sandbox_policy_content_id": roots.values.get(SANDBOX_POLICY_ROOT, "")},
        ),
    ]
    claim = make_claim(
        PRIMITIVE_SAFETY,
        f"Primitive {primitive.primitive_id} cannot reach evaluator state or escape the sandbox.",
        producer=producer,
        warrant=Warrant.CORROBORATED,
        subject_refs=(primitive.primitive_id,),
        evidence=evidence,
        assumptions=(SANDBOX_POLICY_ROOT, EVALUATOR_ROOT),
        source_hashes={SANDBOX_POLICY_ROOT: roots.values.get(SANDBOX_POLICY_ROOT, "")},
    )
    return claim, evidence


# --- §9 capability claim, §10 per-primitive claims ----------------------------------------------


def capability_claim(
    *,
    roots: SemanticRoots,
    producer: str,
    statement: str,
    treatment_condition: str,
    comparators: Sequence[str],
    effect_metric: str,
    effect: float,
    ci: tuple[float, float],
    preregistration_content_id: str,
    compute_ledger_id: str,
    causal_attribution_refs: Sequence[str],
    evidence: Sequence[EvidenceObject],
) -> ClaimObject:
    """The Capability Claim Object of §9. Null results use the same structure (§9)."""
    return make_claim(
        CAPABILITY,
        statement,
        producer=producer,
        warrant=Warrant.EMPIRICAL,
        subject_refs=(treatment_condition,),
        scope={
            "treatment_condition": treatment_condition,
            "comparators": list(comparators),
            "effect_metric": effect_metric,
        },
        evidence=evidence,
        assumptions=(K0_ROOT, BSIR_ROOT, EVALUATOR_ROOT, BENCHMARK_ROOT,
                     PREREGISTRATION_ROOT, CODING_SCHEME_ROOT),
        source_hashes={k: v for k, v in roots.values.items()},
        detail={
            "effect": effect,
            "ci_low": ci[0],
            "ci_high": ci[1],
            "preregistration_content_id": preregistration_content_id,
            "compute_ledger_id": compute_ledger_id,
            "causal_attribution_refs": list(causal_attribution_refs),
        },
    )


def negative_result_claim(
    *,
    roots: SemanticRoots,
    producer: str,
    statement: str,
    search_space_constraint: str,
    preregistration_content_id: str,
    evidence: Sequence[EvidenceObject],
    outcome_class: str,
) -> ClaimObject:
    """A null or H0-consistent finding as promotable knowledge (§9, spec §44)."""
    return make_claim(
        NEGATIVE_RESULT,
        statement,
        producer=producer,
        warrant=Warrant.EMPIRICAL,
        scope={"outcome_class": outcome_class},
        evidence=evidence,
        assumptions=(K0_ROOT, EVALUATOR_ROOT, PREREGISTRATION_ROOT),
        source_hashes={k: v for k, v in roots.values.items()},
        detail={
            "search_space_constraint": search_space_constraint,
            "preregistration_content_id": preregistration_content_id,
        },
    )


def primitive_effect_claims(
    effects: Sequence[Any],
    *,
    roots: SemanticRoots,
    producer: str,
) -> list[tuple[ClaimObject, list[EvidenceObject]]]:
    """Per-primitive causal claims (§10).

    M8's paired ablations emit claim/evidence objects per primitive rather than only a final
    table — so a primitive's measured effect is itself an assurance object that can be depended
    on, contested, and invalidated.
    """
    out = []
    for effect in effects:
        evidence = [
            make_evidence(
                kind="paired_ablation", source="bestsad.causal.attribution",
                method="ablation by call-site re-expansion, verified by semantic-hash equality",
                warrant=Warrant.EMPIRICAL,
                payload={
                    "primitive_id": effect.primitive_id,
                    "direct_effect": effect.direct_effect.point,
                    "ci_low": effect.direct_effect.low,
                    "ci_high": effect.direct_effect.high,
                },
            ),
            make_evidence(
                kind="reuse_metric", source="bestsad.evaluator.contract",
                method="cross-family reuse measured directly, not inferred from accuracy",
                warrant=Warrant.DIRECT_OBSERVATION,
                payload={"cross_family_reuse": effect.cross_family_reuse},
            ),
            make_evidence(
                kind="semantic_gain", source="bestsad.mdl.semantic_gain",
                method="SG-v2 under the pre-registered coding scheme",
                warrant=Warrant.RIGOROUS_COMPUTATION,
                payload={"semantic_gain_v2": effect.semantic_gain_v2,
                         "coding_scheme": roots.values.get(CODING_SCHEME_ROOT, "")},
            ),
        ]
        claim = make_claim(
            PRIMITIVE_UTILITY,
            f"Primitive {effect.primitive_id} contributes a direct effect of "
            f"{effect.direct_effect.point:+.4f} on verified compositional OOD solve rate.",
            producer=producer,
            warrant=Warrant.EMPIRICAL,
            subject_refs=(effect.primitive_id,),
            evidence=evidence,
            assumptions=(K0_ROOT, EVALUATOR_ROOT, CODING_SCHEME_ROOT),
            source_hashes={k: v for k, v in roots.values.items()},
            detail={
                "shortcut_shaped": effect.shortcut_shaped,
                "compression_shaped": effect.compression_shaped,
            },
        )
        out.append((claim, evidence))
    return out
