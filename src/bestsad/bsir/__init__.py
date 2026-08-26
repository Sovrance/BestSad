"""Bestsad Semantic IR — the canonical scientific representation (spec §9).

BSIR is the canonical semantic object; projections are views over it (P8), and MLIR (M12) is
an execution substrate below it, not a definition of its semantics.
"""

from .canonicalize import (
    alpha_normalize,
    canonical_program,
    canonical_serialization,
    semantic_hash,
    structural_hash,
    term_semantic_hash,
)
from .diff import SemanticDiff, diff
from .equivalence import (
    EquivalenceContract,
    EquivalenceResult,
    canonical_equivalent,
    enumerate_domain,
    equivalent,
)
from .graph import VerificationReport, from_graph, to_graph, verify
from .levels import BSIRLevel, LevelAnnotation, annotate, infer_level
from .nodes import Graph, MutationRegion, Node
from .typing import TypingReport, type_graph, typed_graph
from .projections import (
    CompactProjection,
    GraphProjection,
    HumanProjection,
    PROJECTIONS,
    Projection,
    SExprProjection,
    get_projection,
    token_count,
    tokenize,
)

__all__ = [
    "BSIRLevel",
    "CompactProjection",
    "EquivalenceContract",
    "EquivalenceResult",
    "Graph",
    "GraphProjection",
    "HumanProjection",
    "LevelAnnotation",
    "MutationRegion",
    "Node",
    "PROJECTIONS",
    "Projection",
    "SExprProjection",
    "SemanticDiff",
    "TypingReport",
    "VerificationReport",
    "alpha_normalize",
    "annotate",
    "canonical_equivalent",
    "canonical_program",
    "canonical_serialization",
    "diff",
    "enumerate_domain",
    "equivalent",
    "from_graph",
    "get_projection",
    "infer_level",
    "semantic_hash",
    "structural_hash",
    "term_semantic_hash",
    "to_graph",
    "token_count",
    "tokenize",
    "type_graph",
    "typed_graph",
    "verify",
]
