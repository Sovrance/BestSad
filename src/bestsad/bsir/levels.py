"""BSIR levels and the annotation that carries them (design §7.1).

BSIR becomes a stack rather than a single representation:

===========  ==========================================================================
BSIR-0       kernel operations, directly interpretable by K0
BSIR-1       typed graph: complete result types, effects, regions, proof obligations
BSIR-2       recovered structures -- map/fold/scan, recursion, state machines
BSIR-3       learned abstractions: `prim:*` families and discovered algebraic laws
BSIR-4       language grammar: an evolved language and its lowering/lifting rules
===========  ==========================================================================

**Level metadata is carried outside every hash** (ADR 0013). `LevelAnnotation` is a separate
object keyed by graph, not a field on `Graph` or `Node`, and nothing here feeds
`semantic_hash`, `structural_hash`, or the content-addressed node ids in `graph.py`.

That separation is the whole point. A level is a *claim about* a graph — "this has been
recognised as structural" — and claims change as analyzers improve. If the level were inside
the identity, re-running a better motif miner would give an existing program a new semantic
hash, which would invalidate every certificate naming it. The compatibility rule in §7.1 says
semantic identity binds to the canonical lower representation; this module is how that stays
true while still letting a graph say which level it has been recognised at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from .nodes import Graph


class BSIRLevel(IntEnum):
    """The five BSIR levels. Ordered, so `level >= BSIRLevel.STRUCTURAL` is meaningful."""

    KERNEL = 0
    TYPED = 1
    STRUCTURAL = 2
    ABSTRACTION = 3
    LANGUAGE = 4

    @property
    def label(self) -> str:
        return f"BSIR-{int(self)}"


#: Levels at which a graph is directly interpretable by K0 without further lowering.
DIRECTLY_EXECUTABLE = frozenset({BSIRLevel.KERNEL, BSIRLevel.TYPED})


@dataclass(frozen=True, slots=True)
class LevelAnnotation:
    """What level a graph has been recognised at, and on what basis.

    `semantic_root` is the graph's canonical semantic hash — the binding required by §7.1's
    compatibility rule. An annotation whose root does not match the graph it is attached to is
    stale, and `verify_binding` says so rather than letting it be used.
    """

    semantic_root: str
    level: BSIRLevel
    recognised_by: str
    proof_obligation_ids: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def verify_binding(self, graph: Graph) -> bool:
        """True when this annotation actually describes `graph`."""
        return bool(graph.semantic_hash) and graph.semantic_hash == self.semantic_root

    @property
    def is_directly_executable(self) -> bool:
        return self.level in DIRECTLY_EXECUTABLE

    @property
    def has_open_obligations(self) -> bool:
        return bool(self.proof_obligation_ids)


def annotate(
    graph: Graph,
    level: BSIRLevel,
    recognised_by: str,
    *,
    proof_obligation_ids: tuple[str, ...] = (),
    detail: dict[str, Any] | None = None,
) -> LevelAnnotation:
    """Annotate `graph` at `level` without modifying it.

    The graph is returned untouched by construction: this function does not take a mutable
    reference for any purpose other than reading `semantic_hash`.
    """
    return LevelAnnotation(
        semantic_root=graph.semantic_hash,
        level=level,
        recognised_by=recognised_by,
        proof_obligation_ids=proof_obligation_ids,
        detail=dict(detail or {}),
    )


def infer_level(graph: Graph) -> BSIRLevel:
    """The highest level a graph's *contents* justify on their own.

    This is a syntactic floor, not a recognition result. It answers "what is unavoidably true
    here" — a graph containing `prim:*` operations is at least BSIR-3 because those are learned
    abstractions — and deliberately does not try to recognise structure, which is what the
    reverse-recovery pipeline is for. A graph with no primitives reports TYPED when every node
    carries a result type and KERNEL otherwise; claiming STRUCTURAL requires an analyzer, and
    an analyzer records its claim in a `LevelAnnotation`.
    """
    if any(node.op_semantic_id.startswith("prim:") for node in graph.nodes.values()):
        return BSIRLevel.ABSTRACTION
    if graph.nodes and all(node.result_types for node in graph.nodes.values()):
        return BSIRLevel.TYPED
    return BSIRLevel.KERNEL
