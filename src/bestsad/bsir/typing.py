"""Populating BSIR-1 node result types, and reporting where they cannot be populated.

BSIR-1 is "the typed graph" (design §7.1). `to_graph` alone cannot build it: node ids are
content-addressed over the term, so structurally identical subterms collapse into one node,
while types are a property of an *occurrence* rather than of structure.

Those two facts collide in ordinary programs::

    map(lam(v: Bool). v,
        map(lam(v: Int). eq(v, v), range(0, 3)))

Both lambdas bind `v`, both bodies serialize to `var[name=v]`, and the graph therefore holds
one node that is `Bool` at one occurrence and `Int` at the others.

This module refuses to guess. A node is typed when every occurrence agrees; when they disagree
the node is left untyped and listed in `TypingReport.ambiguous` with all observed types. See
ADR 0016 for why picking a winner and why splitting the node were both rejected.

Getting the per-occurrence types requires observing K0's inference, and AGENTS.md invariant 1
protects that code. `_RecordingTypechecker` below subclasses `Typechecker` and overrides
`infer`, which is enough because every recursive call inside the kernel already goes through
`self.infer` -- so a subclass sees each subterm without one line of `src/bestsad/kernel`
changing. ADR 0016 records why this replaced an earlier version that added a hook to the
kernel itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..kernel.interpreter import Kernel
from ..kernel.ops import OPS_BY_NAME, OpSig
from ..kernel.terms import Program, Term
from ..kernel.typecheck import TypeError_, Typechecker
from ..kernel.types import Ty
from .graph import _node_id
from .nodes import Graph, Node


class _RecordingTypechecker(Typechecker):
    """`Typechecker` that remembers the type inferred at every subterm occurrence.

    Nothing in the kernel changes. `Typechecker.infer` recurses through `self.infer`, so
    overriding it here intercepts every occurrence; the unifier is handed in as an argument,
    so the recorded types can be resolved once inference has finished.

    Resolution is deferred on purpose. A type observed mid-inference may still be an unresolved
    type variable that a later constraint pins down, so reading it at call time would report
    `T` where the answer is `Int`.
    """

    def __init__(self, primitives: Mapping[str, OpSig] | None = None) -> None:
        super().__init__(primitives)
        self._seen: list[tuple[Term, Ty]] = []
        self._unifier = None

    def infer(self, term: Term, env, u, *, in_hof_operand: bool) -> Ty:
        self._unifier = u
        ty = super().infer(term, env, u, in_hof_operand=in_hof_operand)
        self._seen.append((term, ty))
        return ty

    def resolved_occurrences(self) -> list[tuple[Term, Ty]]:
        """Every recorded occurrence, with its type resolved against the final substitution."""
        if self._unifier is None:
            return []
        return [(term, self._unifier.resolve(ty)) for term, ty in self._seen]


@dataclass(frozen=True, slots=True)
class TypingReport:
    """What the typing pass established, and what it could not.

    `ambiguous` maps node id -> the distinct types observed at its occurrences. A non-empty
    mapping is a fact about the program, not a failure of the pass.
    """

    typed_nodes: int
    total_nodes: int
    ambiguous: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    failure: str | None = None

    @property
    def complete(self) -> bool:
        """True when every node carries a result type — the BSIR-1 condition."""
        return self.failure is None and self.typed_nodes == self.total_nodes

    @property
    def coverage(self) -> dict[str, object]:
        """Coverage in the shape SRE `AnalyzerResult.coverage` expects."""
        return {
            "typed_nodes": self.typed_nodes,
            "total_nodes": self.total_nodes,
            "ambiguous_nodes": len(self.ambiguous),
            "complete": self.complete,
            **({"failure": self.failure} if self.failure else {}),
        }


def _effects_for(op: str, primitives: Mapping[str, OpSig] | None) -> frozenset[str]:
    """Effect set for an operation.

    K0 has only `Pure` and `Trap`, so this reduces to "can this operation trap". Primitives are
    macros over K0 (spec §5 P2/P9) and inherit their declared signature's trap set.
    """
    sig = OPS_BY_NAME.get(op)
    if sig is None and primitives is not None:
        sig = primitives.get(op)
    if sig is None:
        # An unregistered primitive. `verify` rejects these; here, refusing to claim purity is
        # the conservative reading — an unknown operation is not evidence of no effects.
        return frozenset({"Unknown"})
    return frozenset({"Trap"} if sig.traps else {"Pure"})


def type_graph(
    graph: Graph,
    program: Program,
    *,
    kernel: Kernel | None = None,
    primitives: Mapping[str, OpSig] | None = None,
) -> TypingReport:
    """Populate `result_types` and `effect_set` on `graph`'s nodes in place.

    `graph` must have been built from `program` by `to_graph` under the same kernel, so that
    node ids line up. Nodes are replaced rather than mutated because `Node` is frozen.

    A program that does not typecheck leaves the graph untouched and returns a report carrying
    the failure: an ill-typed program has no node types to populate, and inventing some would
    be worse than reporting none.
    """
    body = kernel.expand(program.body) if kernel is not None else program.body
    typed_program = Program(params=program.params, body=body, result_type=program.result_type)

    checker = _RecordingTypechecker(primitives)
    try:
        checker.check_program(typed_program)
    except TypeError_ as exc:
        return TypingReport(
            typed_nodes=0, total_nodes=len(graph.nodes), ambiguous={}, failure=str(exc)
        )

    observed: dict[str, dict[str, Ty]] = {}
    for term, ty in checker.resolved_occurrences():
        observed.setdefault(_node_id(term), {})[str(ty)] = ty

    ambiguous: dict[str, tuple[str, ...]] = {}
    typed = 0
    for node_id, node in list(graph.nodes.items()):
        types = observed.get(node_id, {})
        effects = _effects_for(node.op_semantic_id, primitives)
        if len(types) == 1:
            (only,) = types.values()
            result_types: tuple[Ty, ...] = (only,)
            typed += 1
        else:
            # Zero types: the node was never reached by inference (unreachable in a
            # well-typed program, but not worth asserting away). More than one: a genuine
            # occurrence conflict, recorded rather than resolved (ADR 0016).
            result_types = ()
            if len(types) > 1:
                ambiguous[node_id] = tuple(sorted(types))
        graph.nodes[node_id] = Node(
            node_id=node.node_id,
            op_semantic_id=node.op_semantic_id,
            operands=node.operands,
            result_types=result_types,
            effect_set=effects,
            attributes=node.attributes,
            region_ids=node.region_ids,
            source_projection=node.source_projection,
            semantic_hash=node.semantic_hash,
            proof_obligation_ids=node.proof_obligation_ids,
        )

    return TypingReport(
        typed_nodes=typed, total_nodes=len(graph.nodes), ambiguous=ambiguous, failure=None
    )


def typed_graph(
    program: Program,
    *,
    kernel: Kernel | None = None,
    primitives: Mapping[str, OpSig] | None = None,
) -> tuple[Graph, TypingReport]:
    """Build a BSIR graph from `program` and type it in one step."""
    from .graph import to_graph

    graph = to_graph(program, kernel)
    return graph, type_graph(graph, program, kernel=kernel, primitives=primitives)
