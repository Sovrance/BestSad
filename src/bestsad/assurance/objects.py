"""Canonical assurance objects (integration spec §1.1–§1.3).

The lesson this protocol encodes, in one sentence: **producers of evidence are not allowed to
promote their own conclusions**. A claim is a versioned object with dependencies, evidence, a
warrant, and a lifecycle enforced by something other than whatever produced it.

Every object here is content-addressed. Identity is derived from content, so a claim that is
edited becomes a *different* claim rather than a quietly mutated one, and any certificate
naming the old content id goes stale by construction rather than by anyone remembering to
check.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


def content_id(payload: Mapping[str, Any], prefix: str = "cid") -> str:
    """Content identifier: a hash of the canonical JSON form."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}:{hashlib.sha256(blob.encode()).hexdigest()[:32]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    """Convert dataclass output into plain JSON types.

    `asdict` keeps tuples as tuples. `json.dumps` tolerates that, but schema validation of the
    in-memory record does not — a tuple is not a JSON array — so records validated before being
    written would pass or fail depending on which side of serialization they were checked on.
    """
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, Enum):
        return value.value
    return value


# --- lifecycle (§1.2) -------------------------------------------------------------------------


class ClaimState(str, Enum):
    """The required lifecycle. Historical states are never rewritten (§1.2)."""

    PROPOSED = "PROPOSED"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    PROMOTED = "PROMOTED"
    CONTESTED = "CONTESTED"
    STALE = "STALE"
    QUARANTINED = "QUARANTINED"
    INVALIDATED = "INVALIDATED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED = "REJECTED"


#: Forward transitions a producer may take on its own.
PRODUCER_TRANSITIONS: dict[ClaimState, frozenset[ClaimState]] = {
    ClaimState.PROPOSED: frozenset({ClaimState.OBSERVED, ClaimState.REJECTED}),
    ClaimState.OBSERVED: frozenset({ClaimState.VERIFIED, ClaimState.REJECTED,
                                    ClaimState.INCONCLUSIVE}),
    ClaimState.VERIFIED: frozenset({ClaimState.CONTESTED, ClaimState.INCONCLUSIVE}),
}

#: Transitions only a policy gate may take. PROMOTED is deliberately unreachable by a producer.
GATE_ONLY_TRANSITIONS: frozenset[ClaimState] = frozenset(
    {ClaimState.PROMOTED, ClaimState.QUARANTINED, ClaimState.INVALIDATED, ClaimState.STALE}
)

#: States that must never enter an execution context, even though they stay queryable (§1.7).
NON_EXECUTABLE_STATES: frozenset[ClaimState] = frozenset(
    {ClaimState.STALE, ClaimState.QUARANTINED, ClaimState.INVALIDATED, ClaimState.REJECTED,
     ClaimState.CONTESTED, ClaimState.INCONCLUSIVE}
)


# --- warrant model (§1.3) ---------------------------------------------------------------------


class Warrant(str, Enum):
    """Why a claim is believed.

    Deliberately **not** ordered. The integration spec warns that Atlas's E0/E1/E3 numbering may
    be kept as profile labels but that product code should consume the semantic warrant rather
    than assume a universal numeric ordering — because the orderings genuinely differ by claim
    class. A FORMAL proof outranks a benchmark for semantic equivalence; for "this abstraction
    helps", a controlled EMPIRICAL result is what counts and a proof is not even available.

    Sufficiency is therefore declared per claim class in `claims.py`, never by comparing two
    warrants directly.
    """

    FORMAL = "FORMAL"
    RIGOROUS_COMPUTATION = "RIGOROUS_COMPUTATION"
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    CORROBORATED = "CORROBORATED"
    EMPIRICAL = "EMPIRICAL"
    HEURISTIC = "HEURISTIC"
    ASSERTED = "ASSERTED"


#: Warrants that can never on their own support a promotion, whatever the claim class (§1.7:
#: "external corroboration is never silently upgraded to internal proof").
NEVER_SUFFICIENT_ALONE: frozenset[Warrant] = frozenset({Warrant.HEURISTIC, Warrant.ASSERTED})


class DependencyType(str, Enum):
    SEMANTIC_ROOT = "semantic_root"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    ASSUMPTION = "assumption"
    POLICY = "policy"
    SCHEMA = "schema"
    ARTIFACT = "artifact"
    MODEL = "model"


# --- objects ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceObject:
    """An observation, test, proof artifact, benchmark result, or external corroboration."""

    evidence_id: str
    kind: str
    source: str
    content_hash: str
    method: str
    warrant: Warrant
    captured_at: str = field(default_factory=utc_now)
    validity: str = "current"
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict:
        data = _jsonable(asdict(self))
        data["warrant"] = self.warrant.value
        return data

    @property
    def is_external(self) -> bool:
        return self.source.startswith("external:")


@dataclass(frozen=True, slots=True)
class AssumptionObject:
    """An environmental or semantic condition whose change invalidates descendants (§1.6)."""

    assumption_id: str
    content_id: str
    scope: str
    description: str = ""
    active_from: str = field(default_factory=utc_now)
    status: str = "active"

    def to_record(self) -> dict:
        return _jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """`from_id` depends on `to_id`; `required_state` is what `to_id` must be in."""

    from_id: str
    to_id: str
    dependency_type: DependencyType
    required_state: str = "active"

    def to_record(self) -> dict:
        data = _jsonable(asdict(self))
        data["dependency_type"] = self.dependency_type.value
        return data


@dataclass(frozen=True, slots=True)
class ClaimObject:
    """A falsifiable proposition the system may come to rely on."""

    claim_id: str
    statement: str
    claim_class: str
    scope: Mapping[str, Any]
    subject_refs: tuple[str, ...]
    producer: str
    warrant: Warrant
    status: ClaimState = ClaimState.PROPOSED
    evidence_refs: tuple[str, ...] = ()
    dependency_refs: tuple[str, ...] = ()
    assumption_refs: tuple[str, ...] = ()
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    detail: Mapping[str, Any] = field(default_factory=dict)

    def body(self) -> dict:
        """The content the claim's identity is taken over — everything but its mutable status."""
        return {
            "statement": self.statement,
            "claim_class": self.claim_class,
            "scope": dict(self.scope),
            "subject_refs": list(self.subject_refs),
            "producer": self.producer,
            "warrant": self.warrant.value,
            "evidence_refs": sorted(self.evidence_refs),
            "dependency_refs": sorted(self.dependency_refs),
            "assumption_refs": sorted(self.assumption_refs),
            "source_hashes": dict(self.source_hashes),
        }

    def content_id(self) -> str:
        return content_id(self.body(), "claim")

    def to_record(self) -> dict:
        data = _jsonable(asdict(self))
        data["warrant"] = self.warrant.value
        data["status"] = self.status.value
        data["content_id"] = self.content_id()
        return data


@dataclass(frozen=True, slots=True)
class AssuranceCertificate:
    """A machine-verifiable statement of *why* a claim may be promoted.

    §1.7: "a certificate file existing on disk never implies the claim is trusted." A
    certificate is an input to the promotion predicate, not a substitute for it.
    """

    certificate_id: str
    claim_id: str
    verifier: str
    status: str  # "PASS" | "FAIL" | "INCONCLUSIVE"
    warrant: Warrant
    evidence_refs: tuple[str, ...] = ()
    dependency_refs: tuple[str, ...] = ()
    warrant_statement: str = ""
    hashes: Mapping[str, str] = field(default_factory=dict)
    issued_at: str = field(default_factory=utc_now)

    def to_record(self) -> dict:
        data = _jsonable(asdict(self))
        data["warrant"] = self.warrant.value
        return data

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """An append-only decision from the policy gate, separate from the evidence producer."""

    decision_id: str
    claim_id: str
    from_state: ClaimState
    to_state: ClaimState
    reason: str
    actor: str
    policy: str
    timestamp: str = field(default_factory=utc_now)

    def to_record(self) -> dict:
        data = _jsonable(asdict(self))
        data["from_state"] = self.from_state.value
        data["to_state"] = self.to_state.value
        return data
