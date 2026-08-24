"""Dependency graph and invalidation propagation (integration spec §1.5, §4).

Invalidation is graph-based. When a dependency changes or becomes untrusted, descendants are
recomputed as STALE or QUARANTINED. The engine **shall not** delete the old claim, silently
downgrade it, or leave a previously promoted derivative active — all three are ways for a system
to keep serving conclusions whose foundations have moved.

The graph shape the integration spec draws:

    K0 content id -> primitive equivalence cert -> admitted primitive -> genome
                  -> experiment result -> capability claim
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .objects import ClaimState, DependencyEdge, DependencyType


@dataclass
class DependencyGraph:
    """Edges point from dependent to dependency: `from_id` needs `to_id`."""

    edges: list[DependencyEdge] = field(default_factory=list)

    def add(self, edge: DependencyEdge) -> None:
        self.edges.append(edge)

    def depends_on(self, node: str) -> list[DependencyEdge]:
        return [e for e in self.edges if e.from_id == node]

    def dependents_of(self, node: str) -> list[str]:
        return [e.from_id for e in self.edges if e.to_id == node]

    def descendants(self, node: str) -> list[str]:
        """Everything transitively downstream of `node`, breadth-first, cycle-safe."""
        seen: set[str] = set()
        order: list[str] = []
        queue = deque(self.dependents_of(node))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            order.append(current)
            queue.extend(self.dependents_of(current))
        return order

    def roots_of(self, node: str) -> list[str]:
        """The assumption roots `node` ultimately rests on — the explainable dependency path
        §1.7 requires every promoted claim to have."""
        found: set[str] = set()
        seen: set[str] = set()
        queue = deque([node])
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            outgoing = self.depends_on(current)
            if not outgoing and current != node:
                found.add(current)
            for edge in outgoing:
                if edge.dependency_type in (DependencyType.SEMANTIC_ROOT,
                                            DependencyType.ASSUMPTION):
                    found.add(edge.to_id)
                queue.append(edge.to_id)
        return sorted(found)


@dataclass(frozen=True, slots=True)
class InvalidationEvent:
    """One node's transition caused by an upstream change. Append-only; never a deletion."""

    node_id: str
    new_state: ClaimState
    cause: str
    root_cause: str

    def to_record(self) -> dict:
        return {
            "node_id": self.node_id,
            "new_state": self.new_state.value,
            "cause": self.cause,
            "root_cause": self.root_cause,
        }


def propagate_invalidation(
    graph: DependencyGraph,
    changed_node: str,
    *,
    reason: str,
    quarantine: bool = False,
) -> list[InvalidationEvent]:
    """Mark every descendant of `changed_node` STALE (or QUARANTINED).

    `quarantine=True` is for integrity events — a hidden-test leak, an evaluator defect, a
    suspected exploit. Those are not merely out of date; they are not to be trusted at all until
    someone looks. Ordinary root movement (a kernel version bump) is STALE: the result may well
    still hold, it simply has not been re-established.
    """
    state = ClaimState.QUARANTINED if quarantine else ClaimState.STALE
    return [
        InvalidationEvent(
            node_id=node,
            new_state=state,
            cause=reason,
            root_cause=changed_node,
        )
        for node in graph.descendants(changed_node)
    ]


def unsatisfied_dependencies(
    graph: DependencyGraph,
    node: str,
    states: Mapping[str, ClaimState | str],
) -> list[dict]:
    """Dependencies of `node` that are not in their required state."""
    problems = []
    for edge in graph.depends_on(node):
        actual = states.get(edge.to_id)
        if actual is None:
            problems.append(
                {"dependency": edge.to_id, "type": edge.dependency_type.value,
                 "required": edge.required_state, "actual": "missing"}
            )
            continue
        actual_value = actual.value if isinstance(actual, ClaimState) else str(actual)
        if actual_value != edge.required_state:
            problems.append(
                {"dependency": edge.to_id, "type": edge.dependency_type.value,
                 "required": edge.required_state, "actual": actual_value}
            )
    return problems
