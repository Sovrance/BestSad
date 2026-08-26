"""Semantic graph diff, independent of projection syntax (plan §2, `bsir/diff.py`).

A textual diff of two projections answers "what characters changed", which is a question about
a view (ADR 0013). This module answers "what changed about the meaning": which nodes exist on
one side and not the other, which operations were substituted, and whether the change touched
the effect surface.

Because node ids are content-addressed, set difference over ids *is* the structural diff --
there is no matching heuristic and no edit-distance threshold to tune. What the diff adds on
top is classification: an added node that can trap is a different kind of change from an added
node that cannot, and a consumer deciding whether to require extra evidence cares which.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..kernel.ops import OPS_BY_NAME
from .nodes import Graph


@dataclass(frozen=True, slots=True)
class SemanticDiff:
    """Difference between two BSIR graphs, in semantic rather than textual terms."""

    left_root: str
    right_root: str
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    added_ops: tuple[str, ...] = ()
    removed_ops: tuple[str, ...] = ()
    added_effects: frozenset[str] = frozenset()
    removed_effects: frozenset[str] = frozenset()
    added_trap_kinds: frozenset[str] = frozenset()
    removed_trap_kinds: frozenset[str] = frozenset()
    root_changed: bool = False

    @property
    def is_empty(self) -> bool:
        """True when the two graphs are structurally identical.

        Note what this does *not* mean: two graphs can differ structurally and still agree
        semantically, so a non-empty diff is not evidence of non-equivalence. Use
        `equivalence.equivalent` for that question.
        """
        return not self.added and not self.removed and not self.root_changed

    @property
    def touches_effect_surface(self) -> bool:
        """True when the change alters what can go wrong.

        K0's effect lattice is only `Pure`/`Trap`, which is too coarse to be useful on its own:
        `add` traps on overflow and `div` traps on a zero divisor, so replacing one with the
        other adds no *effect* while adding an entirely new failure mode. Trap kinds come from
        the frozen operation table and give the distinction the lattice cannot, so both are
        consulted here.
        """
        return bool(
            self.added_effects
            or self.removed_effects
            or self.added_trap_kinds
            or self.removed_trap_kinds
        )

    def summary(self) -> dict[str, Any]:
        return {
            "added_nodes": len(self.added),
            "removed_nodes": len(self.removed),
            "shared_nodes": len(self.shared),
            "added_ops": list(self.added_ops),
            "removed_ops": list(self.removed_ops),
            "added_effects": sorted(self.added_effects),
            "removed_effects": sorted(self.removed_effects),
            "added_trap_kinds": sorted(self.added_trap_kinds),
            "removed_trap_kinds": sorted(self.removed_trap_kinds),
            "root_changed": self.root_changed,
            "touches_effect_surface": self.touches_effect_surface,
        }


def diff(left: Graph, right: Graph) -> SemanticDiff:
    """Diff two BSIR graphs by content-addressed node identity."""
    left_ids, right_ids = set(left.nodes), set(right.nodes)
    added = tuple(sorted(right_ids - left_ids))
    removed = tuple(sorted(left_ids - right_ids))
    shared = tuple(sorted(left_ids & right_ids))

    def ops(graph: Graph, ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({graph.nodes[i].op_semantic_id for i in ids}))

    def effects(graph: Graph, ids: tuple[str, ...]) -> frozenset[str]:
        out: set[str] = set()
        for i in ids:
            out |= set(graph.nodes[i].effect_set)
        return frozenset(out)

    def trap_kinds(graph: Graph, ids: tuple[str, ...]) -> frozenset[str]:
        out: set[str] = set()
        for i in ids:
            sig = OPS_BY_NAME.get(graph.nodes[i].op_semantic_id)
            if sig is not None:
                out |= set(sig.traps)
        return frozenset(out)

    left_effects = effects(left, tuple(left_ids))
    right_effects = effects(right, tuple(right_ids))
    left_traps = trap_kinds(left, tuple(left_ids))
    right_traps = trap_kinds(right, tuple(right_ids))

    return SemanticDiff(
        left_root=left.semantic_hash,
        right_root=right.semantic_hash,
        added=added,
        removed=removed,
        shared=shared,
        added_ops=ops(right, added),
        removed_ops=ops(left, removed),
        added_effects=right_effects - left_effects,
        removed_effects=left_effects - right_effects,
        added_trap_kinds=right_traps - left_traps,
        removed_trap_kinds=left_traps - right_traps,
        root_changed=left.root != right.root,
    )
