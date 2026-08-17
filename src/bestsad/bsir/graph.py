"""Term <-> BSIR graph conversion with content-addressed node identity, and `BSIR.verify`
(spec §29.2).

Node ids are the first 16 hex characters of the node's canonical semantic hash, so structurally
identical subterms share a node: the graph is a DAG, and structure sharing is automatic rather
than an optimization pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..kernel.interpreter import Kernel
from ..kernel.ops import OPS_BY_NAME, OpSig
from ..kernel.terms import Program, Term
from ..kernel.typecheck import TypeError_, Typechecker
from ..kernel.types import Ty
from .canonicalize import canonical_serialization, semantic_hash
from .nodes import Graph, Node

import hashlib


def _node_id(term: Term) -> str:
    return hashlib.sha256(canonical_serialization(term).encode()).hexdigest()[:16]


def to_graph(program: Program, kernel: Kernel | None = None) -> Graph:
    """Build a content-addressed BSIR graph from a program."""
    graph = Graph(
        params=program.params,
        result_type=program.result_type,
        semantic_hash=semantic_hash(program, kernel),
    )
    body = kernel.expand(program.body) if kernel is not None else program.body

    def visit(term: Term) -> str:
        operands = tuple(visit(a) for a in term.args)
        nid = _node_id(term)
        if nid not in graph.nodes:
            sig: OpSig | None = OPS_BY_NAME.get(term.op)
            graph.add(
                Node(
                    node_id=nid,
                    op_semantic_id=term.op,
                    operands=operands,
                    result_types=(),
                    effect_set=frozenset({"Trap"} if sig and sig.traps else {"Pure"}),
                    attributes=term.attrs,
                    semantic_hash=nid,
                )
            )
        return nid

    graph.root = visit(body)
    return graph


def from_graph(graph: Graph) -> Program:
    """Rebuild a program from a BSIR graph."""

    def build(nid: str) -> Term:
        node = graph.nodes[nid]
        return Term(node.op_semantic_id, tuple(build(o) for o in node.operands), node.attributes)

    return Program(params=graph.params, body=build(graph.root), result_type=graph.result_type)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Result of `BSIR.verify` — verification layers V0 and V1 (spec §19)."""

    ok: bool
    layer: str
    detail: str = ""
    result_type: Ty | None = None

    def __bool__(self) -> bool:
        return self.ok


def verify(
    program: Program,
    primitives: Mapping[str, OpSig] | None = None,
) -> VerificationReport:
    """`BSIR.verify(graph)` — structural (V0) and type/effect (V1) validation (spec §29.2)."""
    # V0: parse/structural validity.
    for term in program.body.walk():
        sig = OPS_BY_NAME.get(term.op)
        if sig is None:
            if not term.op.startswith("prim:"):
                return VerificationReport(False, "V0", f"unknown operation {term.op!r}")
            if primitives is None or term.op not in primitives:
                return VerificationReport(False, "V0", f"unregistered primitive {term.op!r}")
            sig = primitives[term.op]
        if term.op != "lam" and len(term.args) != sig.arity:
            return VerificationReport(
                False, "V0", f"{term.op} arity {len(term.args)} != {sig.arity}"
            )

    # V1: static semantics.
    try:
        result_type = Typechecker(primitives).check_program(program)
    except TypeError_ as exc:
        return VerificationReport(False, "V1", str(exc))
    return VerificationReport(True, "V1", "", result_type)
