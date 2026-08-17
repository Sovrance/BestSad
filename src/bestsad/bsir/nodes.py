"""BSIR node model (spec §9.3).

BSIR is the canonical Bestsad semantic object. Its defining property (spec §9.4) is that the
semantic hash is derived from **normalized BSIR, not surface syntax**: two surface forms that
normalize to the same BSIR receive the same content identity when their semantics are
identical.

Design principle P8 is load-bearing here — the human projection is a *view*, never the
canonical semantics. `tests/bsir/test_projection_is_not_canonical.py` asserts that no code
path treats a projection as semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..kernel.terms import Term
from ..kernel.types import Ty


@dataclass(frozen=True, slots=True)
class Node:
    """One BSIR node, carrying the fields spec §9.3 requires."""

    node_id: str
    op_semantic_id: str
    operands: tuple[str, ...]
    result_types: tuple[Ty, ...]
    effect_set: frozenset[str]
    attributes: tuple[tuple[str, Any], ...] = ()
    region_ids: tuple[str, ...] = ()
    source_projection: str | None = None
    semantic_hash: str = ""
    proof_obligation_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class Graph:
    """A BSIR graph: nodes keyed by id, plus the root and the typed parameter list."""

    nodes: dict[str, Node] = field(default_factory=dict)
    root: str = ""
    params: tuple[tuple[str, Ty], ...] = ()
    result_type: Ty | None = None
    semantic_hash: str = ""

    def add(self, node: Node) -> str:
        self.nodes[node.node_id] = node
        return node.node_id

    def __len__(self) -> int:
        return len(self.nodes)


@dataclass(frozen=True, slots=True)
class MutationRegion:
    """A semantically meaningful editable region (spec §9.5, §9.6).

    Candidate mutation operates on these rather than on the whole executable graph, and every
    region carries a validity envelope: a candidate violating it is rejected *before* expensive
    evaluation.
    """

    region_id: str
    root_node_id: str
    input_types: tuple[Ty, ...]
    output_type: Ty
    max_size: int
    permitted_ops: frozenset[str]
    effect_limit: frozenset[str] = frozenset({"Pure", "Trap"})

    def admits(self, term: Term, *, size: int | None = None) -> bool:
        """Cheap pre-evaluation validity check (spec §9.6)."""
        actual = term.size() if size is None else size
        if actual > self.max_size:
            return False
        return term.ops_used() <= self.permitted_ops
