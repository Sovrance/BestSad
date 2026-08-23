"""The confound control plane: conditions A–I as first-class objects (spec §24.5, §40).

Controls are not afterthoughts (implementation plan M5). Each condition carries its role, the
confound it controls, its genome, its compute allocation, and its disclosed residual — and the
harness can run a condition that **beats the treatment** and report it without special-casing,
which is the M5 acceptance criterion and the reason the roles are data rather than code paths.

| ID | Role                 | Controls | What it asks                                   |
|----|----------------------|----------|------------------------------------------------|
| A  | reference            | —        | plain K0                                        |
| B  | lower-bound control  | —        | are random macros just as good?                 |
| C  | lower-bound control  | —        | is MDL/frequency extraction just as good?       |
| D  | treatment            | —        | do utility-selected abstractions help?          |
| E  | treatment            | —        | ...and does a compact projection add to that?   |
| F  | confound control     | C2       | is the gain just shorter tokens?                |
| G  | reference class      | —        | is it beating a real design, or only bare K0?   |
| H  | confound control     | C3       | is it representation, or prompt engineering?    |
| I  | confound control     | C1       | is it representation, or just more search?      |
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from ..genomes.registry import Genome, Primitive

ROLES = ("reference", "treatment", "lower_bound_control", "confound_control", "reference_class")
CONFOUNDS = ("C1_compute", "C2_compression", "C3_scaffolding", "C4_contamination", None)


@dataclass(frozen=True, slots=True)
class ResidualConfound:
    measure: str
    value: float
    unit: str

    def to_record(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Condition:
    """One experimental condition — `schemas/control_condition.schema.json`."""

    condition_id: str
    role: str
    genome: Genome
    description: str
    controls_confound: str | None = None
    introduces_new_semantics: bool = False
    human_authored: bool = False
    author_blind_to_genomes: bool | None = None
    matched_to_condition: str | None = None
    inherited_evolution_compute_from: str | None = None
    compute_tolerance: float = 0.05
    residual_confound: ResidualConfound | None = None
    node_budget: int | None = None
    #: Extra enumeration depth. Condition I exists to spend D's evolution compute on *additional
    #: search* (spec §24.5 I). A bounded-depth enumerator saturates: once it has enumerated
    #: every term up to its depth limit, more nodes buy nothing, and the control is handed a
    #: budget it cannot absorb. For an enumerative searcher, "more search" means deeper search,
    #: which is the faithful analogue of more sampling for a model.
    search_depth_bonus: int = 0
    scaffolding: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")
        if self.controls_confound not in CONFOUNDS:
            raise ValueError(f"unknown confound {self.controls_confound!r}")

    @property
    def is_control(self) -> bool:
        return self.role in ("confound_control", "lower_bound_control")

    @property
    def is_treatment(self) -> bool:
        return self.role == "treatment"

    def to_record(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "role": self.role,
            "controls_confound": self.controls_confound,
            "genome_id": self.genome.genome_id,
            "description": self.description,
            "scaffolding": self.scaffolding,
            "compute_allocation": {
                "matched_to_condition": self.matched_to_condition,
                "inherited_evolution_compute_from": self.inherited_evolution_compute_from,
                "tolerance": self.compute_tolerance,
            },
            "residual_confound": (
                self.residual_confound.to_record() if self.residual_confound else None
            ),
            "introduces_new_semantics": self.introduces_new_semantics,
            "human_authored": self.human_authored,
            "author_blind_to_genomes": self.author_blind_to_genomes,
        }


class ConditionPlaneError(Exception):
    """A condition definition violates the control plane's rules."""


def check_condition_f(condition_f: Condition, condition_a: Condition) -> dict:
    """M5 acceptance: condition F provably introduces no new semantics.

    The check is exact and structural: F's genome must have a primitive set identical to A's
    under semantic hash. F is allowed to differ from A *only* in its projection — that is what
    makes it a compression-matched control rather than a second treatment.
    """
    a_semantics = sorted(p.semantic_id for p in condition_a.genome.primitives)
    f_semantics = sorted(p.semantic_id for p in condition_f.genome.primitives)
    identical = a_semantics == f_semantics
    if not identical:
        raise ConditionPlaneError(
            "condition F introduces semantics absent from condition A: F is the "
            "compression-matched control and must be a pure surface transformation "
            "(spec §24.5 F). Its primitive set must be identical to A's under semantic hash."
        )
    if condition_f.introduces_new_semantics:
        raise ConditionPlaneError("condition F is flagged as introducing new semantics")
    return {
        "identical_primitive_semantics": identical,
        "primitive_semantic_ids": f_semantics,
        "projection_differs": condition_f.genome.projection_name
        != condition_a.genome.projection_name,
    }


def build_conditions(
    *,
    kernel_version: str,
    base_projection: str = "sexpr",
    compact_projection: str = "compact",
    random_primitives: Sequence[Primitive],
    mdl_primitives: Sequence[Primitive],
    utility_primitives: Sequence[Primitive],
    expert_primitives: Sequence[Primitive],
    baseline_node_budget: int,
    evolution_nodes: int,
    tasks_per_seed: int = 1,
) -> dict[str, Condition]:
    """Assemble the full condition set A–I.

    Conditions H and I are constructed from A/E rather than being separate languages:
    H is the scaffolding-equalized variant set, and I is A with D's evolution compute added to
    its search budget.
    """

    def genome(gid: str, primitives: Sequence[Primitive], projection: str) -> Genome:
        return Genome(
            genome_id=gid,
            generation=0 if not primitives else 1,
            kernel_version=kernel_version,
            primitives=tuple(primitives),
            projection_name=projection,
        )

    conditions: dict[str, Condition] = {}

    conditions["A"] = Condition(
        condition_id="A",
        role="reference",
        genome=genome("G-A", (), base_projection),
        description="K0 baseline language",
        node_budget=baseline_node_budget,
    )
    conditions["B"] = Condition(
        condition_id="B",
        role="lower_bound_control",
        genome=genome("G-B", random_primitives, base_projection),
        description="K0 + random macros, matched to D by count and size",
        node_budget=baseline_node_budget,
        matched_to_condition="D",
    )
    conditions["C"] = Condition(
        condition_id="C",
        role="lower_bound_control",
        genome=genome("G-C", mdl_primitives, base_projection),
        description="K0 + MDL/frequency-extracted macros",
        node_budget=baseline_node_budget,
        matched_to_condition="D",
    )
    conditions["D"] = Condition(
        condition_id="D",
        role="treatment",
        genome=genome("G-D", utility_primitives, base_projection),
        description="K0 + utility-selected abstractions",
        node_budget=baseline_node_budget,
    )
    conditions["E"] = Condition(
        condition_id="E",
        role="treatment",
        genome=genome("G-E", utility_primitives, compact_projection),
        description="D + compact projection",
        node_budget=baseline_node_budget,
    )
    conditions["F"] = Condition(
        condition_id="F",
        role="confound_control",
        controls_confound="C2_compression",
        genome=genome("G-F", (), compact_projection),
        description=(
            "compression-matched: the compact projection applied over plain K0, so token "
            "count moves toward E's while the semantics stay identical to A's"
        ),
        introduces_new_semantics=False,
        node_budget=baseline_node_budget,
        matched_to_condition="E",
    )
    conditions["G"] = Condition(
        condition_id="G",
        role="reference_class",
        genome=genome("G-G", expert_primitives, base_projection),
        description="human-expert DSL, authored blind to the evolved genomes and time-boxed",
        human_authored=True,
        author_blind_to_genomes=True,
        node_budget=baseline_node_budget,
    )
    conditions["H"] = Condition(
        condition_id="H",
        role="confound_control",
        controls_confound="C3_scaffolding",
        genome=genome("G-H", utility_primitives, compact_projection),
        description=(
            "scaffolding-matched variant of E: identical genome, with grammar-description "
            "budget, worked examples, retry policy and decoding constraints equalized to the "
            "common target across all conditions"
        ),
        node_budget=baseline_node_budget,
    )
    conditions["I"] = Condition(
        condition_id="I",
        role="confound_control",
        controls_confound="C1_compute",
        genome=genome("G-I", (), base_projection),
        description=(
            "search-only compute-matched: condition A given the entire compute consumed by "
            "genome evolution in D, spent on additional search in the baseline language"
        ),
        # `node_budget` is a *per-task* search budget, but the evolution compute it inherits is
        # a *total* across the whole seed. Adding the total to every task hands condition I one
        # full extra evolution budget per task — 26x too much at the current task count — and
        # the §26.6 identity compute(I) == compute(A) + compute(evolution in D) fails. The
        # inherited total is therefore spread across the tasks it has to cover.
        node_budget=baseline_node_budget + max(1, evolution_nodes // max(1, tasks_per_seed)),
        search_depth_bonus=1,
        inherited_evolution_compute_from="D",
        matched_to_condition="D",
    )
    return conditions


#: The controls a capability claim may not be made without (`AGENTS.md` invariant 3).
REQUIRED_CONTROLS: tuple[str, ...] = ("F", "H", "I")
