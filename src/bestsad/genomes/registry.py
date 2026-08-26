"""Language Genome and primitive registry (spec §10, §11).

A genome is the unit of evolution. Its invariants (spec §10.2) are enforced here rather than
documented and hoped for:

1. every primitive references a K0 lowering or a previously verified primitive expansion;
2. no cyclic macro expansion;
3. every changed semantic mapping produces a new semantic identifier;
4. surface aliases may change without the semantic identifier changing;
5. fitness is immutable once recorded for a specific environment and benchmark manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from ..bsir.canonicalize import term_semantic_hash
from ..kernel import Kernel, OpSig, Program, Term, Ty
from ..kernel.types import parse_type

#: Maturity states a `Primitive` may carry. Kept in step with `abstraction.lifecycle.ORDER`,
#: which is the definition; this is a literal rather than an import because `lifecycle` imports
#: `Primitive` from here, and a test asserts the two agree so the duplication cannot drift.
#:
#: CANONICAL is new in SRE v0.1 (ADR 0017). It has to be admissible here as well as returnable
#: from `promote`: a promotion result that no `Primitive` can hold is a state the system can
#: compute and then not store.
MATURITIES = ("EXP", "OBS", "SPEC", "VER", "CANONICAL", "CORE")


class GenomeInvariantViolation(Exception):
    """A genome invariant (spec §10.2) was violated."""


@dataclass(frozen=True, slots=True)
class Primitive:
    """A genome primitive: a macro over K0 with a declared signature (spec §11).

    `semantic_id` is derived from the *expansion*, so two primitives with different names and
    the same meaning share it (invariant 3/4): renaming is free, remeaning is not.
    """

    primitive_id: str
    params: tuple[str, ...]
    expansion: Term
    input_types: tuple[Ty, ...]
    output_type: Ty
    maturity: str = "EXP"
    display_names: tuple[str, ...] = ()
    parent_primitive_ids: tuple[str, ...] = ()
    origin: str = "unspecified"
    effects: tuple[str, ...] = ("Pure",)

    def __post_init__(self) -> None:
        if self.maturity not in MATURITIES:
            raise GenomeInvariantViolation(f"unknown maturity {self.maturity!r}")

    @property
    def semantic_id(self) -> str:
        params = tuple(zip(self.params, self.input_types))
        return term_semantic_hash(self.expansion, params)[:24]

    @property
    def signature(self) -> OpSig:
        return OpSig(
            op=self.primitive_id,
            params=tuple(self.input_types),
            ret=self.output_type,
            family="primitive",
            doc=f"genome primitive ({self.origin})",
        )

    @property
    def size(self) -> int:
        """Expansion size — the primitive's own description cost in nodes."""
        return self.expansion.size()

    def to_record(self, kernel_version: str) -> dict:
        """Serialize to `schemas/primitive_record.schema.json`.

        One exception, and it is deliberate: a record whose `maturity` is `CANONICAL` validates
        against `schemas/sre/primitive-record-sre-v0.1.schema.json` instead. The delivered v0.2
        schema is pinned by `MANIFEST_SHA256.txt` and is not edited, so the newer state lives in
        an extension (ADR 0017). Every other state validates against both.
        """
        return {
            "primitive_id": self.primitive_id,
            "semantic_id": self.semantic_id,
            "display_names": list(self.display_names),
            "maturity": self.maturity,
            "kernel_version": kernel_version,
            "input_types": [str(t) for t in self.input_types],
            "output_types": [str(self.output_type)],
            "effects": list(self.effects),
            "lowering": {
                "params": list(self.params),
                "expansion": str(self.expansion),
                "target": "K0",
            },
            "semantic_hash": self.semantic_id,
            "parent_primitive_ids": list(self.parent_primitive_ids),
        }


@dataclass(slots=True)
class Genome:
    """A language genome (spec §10.1)."""

    genome_id: str
    generation: int
    kernel_version: str
    primitives: tuple[Primitive, ...] = ()
    projection_name: str = "sexpr"
    representation_policy: dict = field(default_factory=dict)
    parent_genome_ids: tuple[str, ...] = ()
    lineage_events: tuple[dict, ...] = ()
    fitness_vector: dict = field(default_factory=dict)
    novelty_vector: dict = field(default_factory=dict)
    environment_hash: str = ""
    created_at: str = ""
    _fitness_locked: bool = False

    # -- invariants ------------------------------------------------------------------------

    def validate(self, kernel: Kernel) -> None:
        """Check spec §10.2 invariants 1 and 2."""
        ids = [p.primitive_id for p in self.primitives]
        if len(set(ids)) != len(ids):
            raise GenomeInvariantViolation("duplicate primitive ids")

        known: set[str] = set()
        for primitive in self.primitives:
            for node in primitive.expansion.walk():
                if not node.op.startswith("prim:"):
                    continue
                if node.op == primitive.primitive_id:
                    raise GenomeInvariantViolation(
                        f"{primitive.primitive_id} expands to itself (invariant 2)"
                    )
                if node.op not in known:
                    raise GenomeInvariantViolation(
                        f"{primitive.primitive_id} references {node.op}, which is not a "
                        "previously defined primitive (invariant 1)"
                    )
            known.add(primitive.primitive_id)

    def record_fitness(self, vector: Mapping[str, float]) -> None:
        """Invariant 5: fitness is immutable once recorded."""
        if self._fitness_locked:
            raise GenomeInvariantViolation(
                "fitness is immutable once recorded for a given environment and benchmark "
                "manifest (spec §10.2 invariant 5)"
            )
        self.fitness_vector = dict(vector)
        self._fitness_locked = True

    # -- derived views ---------------------------------------------------------------------

    @property
    def primitive_ids(self) -> tuple[str, ...]:
        return tuple(p.primitive_id for p in self.primitives)

    def signatures(self) -> dict[str, OpSig]:
        return {p.primitive_id: p.signature for p in self.primitives}

    def expansions(self) -> dict[str, tuple[tuple[str, ...], Term]]:
        return {p.primitive_id: (p.params, p.expansion) for p in self.primitives}

    def kernel(self, **kwargs) -> Kernel:
        return Kernel(self.expansions(), **kwargs)

    def vocabulary(self, base_ops: Sequence[str]) -> tuple[str, ...]:
        return tuple(base_ops) + self.primitive_ids

    def description_length_tokens(self, projection_name: str | None = None) -> int:
        """`language_description_length` (spec §21.1): the cost of *stating* the language.

        A genome that adds primitives pays for them here, which is what stops "add more
        primitives" from being a free move.
        """
        from ..bsir.projections import get_projection, token_count

        projection = get_projection(projection_name or self.projection_name)
        total = token_count(projection.describe_grammar())
        for primitive in self.primitives:
            total += token_count(projection.render(primitive.expansion)) + len(primitive.params)
        return total

    def to_record(self) -> dict:
        """Serialize to `schemas/language_genome.schema.json`."""
        return {
            "genome_id": self.genome_id,
            "parent_genome_ids": list(self.parent_genome_ids),
            "generation": self.generation,
            "kernel_version": self.kernel_version,
            "primitive_ids": list(self.primitive_ids),
            "representation_policy": dict(self.representation_policy),
            "projection_policy": {"projection": self.projection_name},
            "fitness_vector": {k: float(v) for k, v in self.fitness_vector.items()},
            "novelty_vector": {k: float(v) for k, v in self.novelty_vector.items()},
            "lineage_events": list(self.lineage_events),
            "environment_hash": self.environment_hash,
            "created_at": self.created_at,
        }

    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "kernel": self.kernel_version,
                "projection": self.projection_name,
                "primitives": sorted(p.semantic_id for p in self.primitives),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def base_genome(kernel_version: str, projection_name: str = "sexpr") -> Genome:
    """Condition A's genome: plain K0, no primitives."""
    return Genome(
        genome_id=f"G0-{projection_name}",
        generation=0,
        kernel_version=kernel_version,
        primitives=(),
        projection_name=projection_name,
        environment_hash="",
    )
