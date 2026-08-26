"""Primitive lifecycle and promotion evidence (spec §11.1, §11.2).

Maturity states are EXP → OBS → SPEC → VER → CANONICAL → CORE. Promotion requires evidence, and
**CORE is never automatic**: a kernel change invalidates every controlled comparison, so it
requires a new research phase and explicit human review (spec §11.2). `promote` refuses to
return CORE at all.

CANONICAL is new in SRE v0.1 (design §4, §7.4). It sits between VER and CORE and means
something narrower than either: the primitive's identity has been pinned to a recovered
semantic signature, and that signature has been *proved* equivalent to its K0 expansion.

The word "proved" is doing the work. A primitive reaches CANONICAL only on a canonical-tier
equivalence verdict — identical normalized BSIR. Sampled agreement (`EQUIV_DYNAMIC`) is
explicitly not enough, however many cases it covers, because CANONICAL is the state that
licenses treating the primitive and its expansion as one semantic object. Accepting sampled
evidence there would let a primitive that merely happens to agree on the tested domain become
interchangeable with its expansion everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..genomes.registry import Primitive

ORDER = ("EXP", "OBS", "SPEC", "VER", "CANONICAL", "CORE")

#: The only equivalence verdict that licenses CANONICAL. See the module docstring.
CANONICAL_EVIDENCE_VERDICT = "EQUIV_CANONICAL"


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    """The evidence set spec §11.1 says promotion should consider.

    Every field is recorded even when it does not gate the current step, because §11.1's list is
    also the answer to open question 13 — which maturity evidence predicts realized reuse — and
    that question is answerable as a by-product of EXP-001 only if the evidence was written down
    at the time.
    """

    primitive_id: str
    reuse_count: int = 0
    reuse_diversity: int = 0
    cross_family_utility: float = 0.0
    cross_model_transfer: float | None = None
    semantic_gain: float = 0.0
    verification_cost: float = 0.0
    failure_rate: float = 0.0
    runtime_benefit: float = 0.0
    alias_collisions: int = 0
    adversarial_incidents: int = 0
    semantic_signature: str | None = None
    equivalence_verdict: str | None = None

    @property
    def has_canonical_identity(self) -> bool:
        """True when a recovered signature is backed by a canonical-tier equivalence proof.

        Both halves are required. A signature without a verdict is an unverified claim about
        identity; a verdict without a signature has nothing to attach itself to.
        """
        return bool(self.semantic_signature) and (
            self.equivalence_verdict == CANONICAL_EVIDENCE_VERDICT
        )

    def to_record(self) -> dict:
        return {
            "primitive_id": self.primitive_id,
            "reuse_count": self.reuse_count,
            "reuse_diversity": self.reuse_diversity,
            "cross_family_utility": self.cross_family_utility,
            "cross_model_transfer": self.cross_model_transfer,
            "semantic_gain": self.semantic_gain,
            "verification_cost": self.verification_cost,
            "failure_rate": self.failure_rate,
            "runtime_benefit": self.runtime_benefit,
            "alias_collisions": self.alias_collisions,
            "adversarial_incidents": self.adversarial_incidents,
            "semantic_signature": self.semantic_signature,
            "equivalence_verdict": self.equivalence_verdict,
        }


class PromotionRefused(Exception):
    """A promotion was requested that the lifecycle rules do not permit."""


def promote(primitive: Primitive, evidence: PromotionEvidence) -> tuple[str, str]:
    """Return `(maturity, rationale)` — the highest state the evidence supports.

    Never returns CORE. Automated search may *propose* a CORE candidate, but promoting one is a
    kernel change, and a kernel change starts a new experiment lineage (spec §8.4, §11.2).

    May return CANONICAL, but only on a canonical-tier equivalence proof (SRE v0.1). That is a
    statement about semantic identity, which is checkable, rather than about research
    readiness, which is not — which is why it can be automated while CORE cannot.
    """
    if evidence.adversarial_incidents > 0:
        return "EXP", "adversarial incidents recorded; held at EXP pending inspection"

    if evidence.reuse_count < 2:
        return "EXP", "fewer than two recorded uses"

    if evidence.reuse_diversity < 2:
        return (
            "OBS",
            "reused, but within a single task family — cross-family evidence is missing, and "
            "single-family concentration is the §22.2 suspicion pattern",
        )

    if evidence.semantic_gain <= 0:
        return (
            "OBS",
            "reused across families but Semantic Gain is not positive: it does not shorten "
            "held-out solutions by more than it costs to state",
        )

    if evidence.failure_rate > 0.1:
        return "SPEC", "specified, but failure rate above 10% blocks verification"

    if evidence.verification_cost <= 0:
        return "SPEC", "specified; no verification evidence recorded yet"

    if evidence.has_canonical_identity:
        return (
            "CANONICAL",
            "verified, and its recovered semantic signature is proved equivalent to its K0 "
            "expansion at the canonical tier",
        )

    if evidence.semantic_signature and evidence.equivalence_verdict:
        return (
            "VER",
            f"verified; a semantic signature is recorded but its equivalence evidence is "
            f"{evidence.equivalence_verdict}, and CANONICAL requires a canonical-tier proof",
        )

    return "VER", "reused across families, positive semantic gain, verification evidence present"


def request_core_promotion(primitive: Primitive) -> None:
    """Spec §11.2: no automatic CORE promotion."""
    raise PromotionRefused(
        f"{primitive.primitive_id}: CORE promotion is a kernel change. It invalidates every "
        "controlled comparison made against the current kernel (spec §8.4) and requires a new "
        "research phase with explicit review — it is never an automated step (spec §11.2)."
    )


@dataclass
class LifecycleLedger:
    """Append-only record of maturity transitions (P5, P7)."""

    events: list[dict] = field(default_factory=list)

    def record(self, primitive_id: str, before: str, after: str, rationale: str) -> None:
        self.events.append(
            {
                "primitive_id": primitive_id,
                "from": before,
                "to": after,
                "rationale": rationale,
            }
        )

    def for_primitive(self, primitive_id: str) -> list[dict]:
        return [e for e in self.events if e["primitive_id"] == primitive_id]
