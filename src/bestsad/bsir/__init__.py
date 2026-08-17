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
from .graph import VerificationReport, from_graph, to_graph, verify
from .nodes import Graph, MutationRegion, Node
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
    "CompactProjection",
    "Graph",
    "GraphProjection",
    "HumanProjection",
    "MutationRegion",
    "Node",
    "PROJECTIONS",
    "Projection",
    "SExprProjection",
    "VerificationReport",
    "alpha_normalize",
    "canonical_program",
    "canonical_serialization",
    "from_graph",
    "get_projection",
    "semantic_hash",
    "structural_hash",
    "term_semantic_hash",
    "to_graph",
    "token_count",
    "tokenize",
    "verify",
]
