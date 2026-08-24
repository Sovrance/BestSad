"""Append-only assurance ledger (integration spec §12, §1.7).

Every material transition is append-only and auditable. Pre-registration amendments, evaluator
changes, primitive promotions and claim invalidations are immutable events.

Two rules the implementation enforces rather than documents:

* **A claim's history is never rewritten.** Recording a new state appends an event; the earlier
  states stay queryable with the evidence that supported them. A rejected or invalidated claim
  remains answerable — you can still ask what it said and what unseated it.
* **A producer cannot write a gate-only state.** `record_state` refuses; only `apply_decision`,
  which takes a `PromotionDecision` from a `PolicyGate`, can move a claim to PROMOTED.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from .graph import DependencyGraph, InvalidationEvent, propagate_invalidation
from .objects import (
    AssumptionObject,
    AssuranceCertificate,
    ClaimObject,
    ClaimState,
    DependencyEdge,
    EvidenceObject,
    PromotionDecision,
    content_id,
    utc_now,
)
from .promotion import producer_may_transition


class LedgerViolation(Exception):
    """An attempt to mutate history, or to write a state the writer may not write."""


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_id: str
    kind: str
    subject_id: str
    payload: dict
    recorded_at: str = ""

    def to_record(self) -> dict:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "payload": self.payload,
            "recorded_at": self.recorded_at,
        }


@dataclass
class AssuranceLedger:
    """Content-addressed, append-only store of claims, evidence, certificates and decisions."""

    events: list[LedgerEvent] = field(default_factory=list)
    claims: dict[str, ClaimObject] = field(default_factory=dict)
    evidence: dict[str, EvidenceObject] = field(default_factory=dict)
    certificates: dict[str, AssuranceCertificate] = field(default_factory=dict)
    assumptions: dict[str, AssumptionObject] = field(default_factory=dict)
    graph: DependencyGraph = field(default_factory=DependencyGraph)

    # -- append ---------------------------------------------------------------------------

    def _append(self, kind: str, subject_id: str, payload: dict) -> LedgerEvent:
        event = LedgerEvent(
            event_id=content_id(
                {"kind": kind, "subject": subject_id, "n": len(self.events), "payload": payload},
                "event",
            ),
            kind=kind,
            subject_id=subject_id,
            payload=payload,
            recorded_at=utc_now(),
        )
        self.events.append(event)
        return event

    def add_evidence(self, evidence: EvidenceObject) -> EvidenceObject:
        existing = self.evidence.get(evidence.evidence_id)
        if existing is not None and existing.content_hash != evidence.content_hash:
            raise LedgerViolation(
                f"evidence {evidence.evidence_id} already recorded with a different content hash"
            )
        self.evidence[evidence.evidence_id] = evidence
        self._append("evidence_recorded", evidence.evidence_id, evidence.to_record())
        return evidence

    def add_assumption(self, assumption: AssumptionObject) -> AssumptionObject:
        self.assumptions[assumption.assumption_id] = assumption
        self._append("assumption_recorded", assumption.assumption_id, assumption.to_record())
        return assumption

    def add_claim(self, claim: ClaimObject) -> ClaimObject:
        if claim.claim_id in self.claims:
            raise LedgerViolation(
                f"claim {claim.claim_id} already exists; a changed claim is a new claim "
                "(content-addressed identity), never an edit of this one"
            )
        self.claims[claim.claim_id] = claim
        for dep in claim.dependency_refs:
            from .objects import DependencyType

            self.graph.add(DependencyEdge(claim.claim_id, dep, DependencyType.CLAIM))
        for assumption in claim.assumption_refs:
            from .objects import DependencyType

            self.graph.add(
                DependencyEdge(claim.claim_id, assumption, DependencyType.SEMANTIC_ROOT)
            )
        self._append("claim_proposed", claim.claim_id, claim.to_record())
        return claim

    def add_certificate(self, certificate: AssuranceCertificate) -> AssuranceCertificate:
        if certificate.claim_id not in self.claims:
            raise LedgerViolation(
                f"certificate names unknown claim {certificate.claim_id}"
            )
        self.certificates[certificate.certificate_id] = certificate
        self._append("certificate_issued", certificate.certificate_id, certificate.to_record())
        return certificate

    # -- state transitions ------------------------------------------------------------------

    def record_state(self, claim_id: str, to_state: ClaimState, *, actor: str,
                     reason: str = "") -> ClaimObject:
        """A producer-side transition. Refuses any gate-only state."""
        from dataclasses import replace

        claim = self.claims[claim_id]
        if not producer_may_transition(claim.status, to_state):
            raise LedgerViolation(
                f"{actor!r} may not move claim {claim_id} from {claim.status.value} to "
                f"{to_state.value}. States {sorted(s.value for s in _gate_only())} are reachable "
                "only through a PolicyGate decision (§1.7)."
            )
        updated = replace(claim, status=to_state)
        self.claims[claim_id] = updated
        self._append(
            "state_recorded",
            claim_id,
            {"from": claim.status.value, "to": to_state.value, "actor": actor,
             "reason": reason},
        )
        return updated

    def apply_decision(self, decision: PromotionDecision) -> ClaimObject:
        """Apply a policy-gate decision. The only route to PROMOTED."""
        from dataclasses import replace

        claim = self.claims[decision.claim_id]
        if claim.producer == decision.actor:
            raise LedgerViolation(
                f"decision actor {decision.actor!r} is the claim's own producer (§1.7)"
            )
        updated = replace(claim, status=decision.to_state)
        self.claims[decision.claim_id] = updated
        self._append("promotion_decision", decision.claim_id, decision.to_record())
        return updated

    def invalidate_from(self, node_id: str, *, reason: str,
                        quarantine: bool = False) -> list[InvalidationEvent]:
        """Propagate invalidation from a changed root. Nothing is deleted (§1.5)."""
        from dataclasses import replace

        events = propagate_invalidation(self.graph, node_id, reason=reason,
                                        quarantine=quarantine)
        for event in events:
            claim = self.claims.get(event.node_id)
            if claim is None:
                continue
            self.claims[event.node_id] = replace(claim, status=event.new_state)
        self._append(
            "invalidation_propagated",
            node_id,
            {"reason": reason, "quarantine": quarantine,
             "affected": [e.to_record() for e in events]},
        )
        return events

    # -- query ------------------------------------------------------------------------------

    def history(self, subject_id: str) -> list[LedgerEvent]:
        return [e for e in self.events if e.subject_id == subject_id]

    def claims_in_state(self, state: ClaimState) -> list[ClaimObject]:
        return [c for c in self.claims.values() if c.status is state]

    def stale(self) -> list[ClaimObject]:
        return [
            c for c in self.claims.values()
            if c.status in (ClaimState.STALE, ClaimState.QUARANTINED, ClaimState.INVALIDATED)
        ]

    def certificate_for(self, claim_id: str) -> AssuranceCertificate | None:
        matches = [c for c in self.certificates.values() if c.claim_id == claim_id]
        return matches[-1] if matches else None

    def dependency_states(self) -> dict[str, ClaimState | str]:
        states: dict[str, ClaimState | str] = {
            cid: claim.status for cid, claim in self.claims.items()
        }
        for aid, assumption in self.assumptions.items():
            states[aid] = assumption.status
        for eid in self.evidence:
            states[eid] = "active"
        return states

    def explain(self, claim_id: str) -> dict:
        """The explainable dependency path §1.7 requires for every promoted claim."""
        claim = self.claims[claim_id]
        return {
            "claim": claim.to_record(),
            "certificate": (
                self.certificate_for(claim_id).to_record()
                if self.certificate_for(claim_id) else None
            ),
            "evidence": [
                self.evidence[e].to_record() for e in claim.evidence_refs if e in self.evidence
            ],
            "roots": self.graph.roots_of(claim_id),
            "dependencies": [e.to_record() for e in self.graph.depends_on(claim_id)],
            "history": [e.to_record() for e in self.history(claim_id)],
        }

    # -- persistence --------------------------------------------------------------------------

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "events": [e.to_record() for e in self.events],
                    "claims": {k: v.to_record() for k, v in self.claims.items()},
                    "evidence": {k: v.to_record() for k, v in self.evidence.items()},
                    "certificates": {k: v.to_record() for k, v in self.certificates.items()},
                    "assumptions": {k: v.to_record() for k, v in self.assumptions.items()},
                    "dependency_edges": [e.to_record() for e in self.graph.edges],
                },
                indent=1,
                sort_keys=True,
                default=str,
            )
        )
        return path


def _gate_only():
    from .objects import GATE_ONLY_TRANSITIONS

    return GATE_ONLY_TRANSITIONS
