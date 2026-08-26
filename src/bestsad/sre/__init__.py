"""SRE-Core v0.1 — the meta-model BestSad shares with SAISES.

Shared: facts, assumptions (by reference), provenance, traces, equivalence classes,
counterexamples, certificate references. Not shared: opcodes. BSIR stays BestSad's computation
IR and SCIR stays SAISES' change IR (ADR 0011).

This package is a boundary, not a replacement. Nothing here supersedes BestSad's assurance
graph, promotion predicate, evaluator contract, or existing schemas.
"""

from .ids import (
    ContentIdError,
    as_content_id,
    bare_digest,
    canonical_json,
    content_id,
    with_content_id,
)
from .objects import (
    AnalyzerResult,
    ArtifactRef,
    Counterexample,
    CounterexampleKind,
    Fact,
    FactStatus,
    Producer,
    Verdict,
)
from .schema import SchemaUnavailable, is_valid, load, validate

__all__ = [
    "AnalyzerResult",
    "ArtifactRef",
    "ContentIdError",
    "Counterexample",
    "CounterexampleKind",
    "Fact",
    "FactStatus",
    "Producer",
    "SchemaUnavailable",
    "Verdict",
    "as_content_id",
    "bare_digest",
    "canonical_json",
    "content_id",
    "is_valid",
    "load",
    "validate",
    "with_content_id",
]
