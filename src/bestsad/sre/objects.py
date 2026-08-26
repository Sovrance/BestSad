"""SRE-Core meta-model objects, BestSad's native (Python) implementation.

These are the objects both systems share (design §6). They are deliberately thin: SRE-Core is
a meta-model for provenance and evidence, not a place to put analysis logic. BSIR opcodes do
not appear here and SCIR opcodes must not (ADR 0011).

Every object serializes to the shared wire form via ``to_wire`` and its id is the content
address of that form, so an object built in Python and the same object built in Go carry the
same id.

On assumptions: BestSad already has an `Assumption` object with its own schema, and v0.1 does
not replace it. SRE facts reference assumptions *by id*, so the existing assumption machinery
and its invalidation semantics remain the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .ids import content_id, with_content_id

FactStatus = Literal["SUPPORTED", "CONTRADICTED", "UNKNOWN", "AMBIGUOUS", "INDETERMINATE"]

Verdict = Literal[
    "EQUIV_CANONICAL", "EQUIV_SYMBOLIC", "EQUIV_DYNAMIC", "NON_EQUIV", "UNKNOWN"
]

CounterexampleKind = Literal[
    "DIVERGENT_RESULT", "DIVERGENT_TRAP", "DIVERGENT_EFFECT", "TYPE_MISMATCH"
]


@dataclass(frozen=True, slots=True)
class Producer:
    """Which analyzer, at which version, emitted a derived object."""

    id: str
    version: str

    def to_wire(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Content-addressed reference to source, IR, trace, dataset, or certificate bytes."""

    kind: str
    digest: str
    media_type: str | None = None
    uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind, "digest": self.digest}
        if self.media_type is not None:
            payload["mediaType"] = self.media_type
        if self.uri is not None:
            payload["uri"] = self.uri
        if self.metadata:
            payload["metadata"] = self.metadata
        return with_content_id(payload)

    @property
    def id(self) -> str:
        return content_id(self.to_wire())


@dataclass(frozen=True, slots=True)
class Fact:
    """A derived assertion, carrying what it depends on and what could invalidate it.

    ``status`` is five-valued on purpose. Collapsing UNKNOWN, AMBIGUOUS and INDETERMINATE into
    a single "false" is how a question that was never asked becomes indistinguishable from one
    that was asked and answered no (design P3).
    """

    predicate: str
    status: FactStatus
    producer: Producer
    inputs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "predicate": self.predicate,
            "status": self.status,
            "producer": self.producer.to_wire(),
            "inputs": list(self.inputs),
            "assumptions": list(self.assumptions),
        }
        if self.evidence_refs:
            payload["evidenceRefs"] = list(self.evidence_refs)
        if self.detail:
            payload["detail"] = self.detail
        return with_content_id(payload)

    @property
    def id(self) -> str:
        return content_id(self.to_wire())


@dataclass(frozen=True, slots=True)
class Counterexample:
    """A concrete witness of non-equivalence (design P5)."""

    kind: CounterexampleKind
    witness: dict[str, Any]
    left_outcome: dict[str, Any] | None = None
    right_outcome: dict[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind, "witness": self.witness}
        if self.left_outcome is not None:
            payload["leftOutcome"] = self.left_outcome
        if self.right_outcome is not None:
            payload["rightOutcome"] = self.right_outcome
        if self.evidence_refs:
            payload["evidenceRefs"] = list(self.evidence_refs)
        if self.detail:
            payload["detail"] = self.detail
        return with_content_id(payload)

    @property
    def id(self) -> str:
        return content_id(self.to_wire())


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    """Append-only output of one analysis pass.

    ``coverage`` is required rather than optional: a pass that does not say what it reached is
    routinely read as having reached everything, and that reading is the one this field exists
    to prevent. An empty mapping asserts nothing.
    """

    producer: Producer
    inputs: tuple[str, ...]
    facts: tuple[str, ...]
    coverage: dict[str, Any]
    unresolved: tuple[dict[str, Any], ...] = ()

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "producer": self.producer.to_wire(),
            "inputs": list(self.inputs),
            "facts": list(self.facts),
            "coverage": self.coverage,
        }
        if self.unresolved:
            payload["unresolved"] = list(self.unresolved)
        return with_content_id(payload)

    @property
    def id(self) -> str:
        return content_id(self.to_wire())
