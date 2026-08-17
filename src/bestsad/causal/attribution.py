"""Causal attribution plane (spec §42; implementation plan M8).

Stage-level ablation answers "which stage carried the gain". It does not answer "which
primitive carried the gain", which is the question a reviewer asks and the question the
promotion pipeline needs.

For each promoted primitive `p`:

* **Direct effect** — outcome change when `p` is ablated: removed, and its call sites
  re-expanded to the K0 equivalent, with the search budget held fixed.
* **Indirect effect** — outcome change when `p` is retained but its call sites are forced to
  the expanded form, isolating whether the benefit is the abstraction itself or merely its
  availability during search.
* **Interaction** — paired ablations for primitives that co-occur above a threshold.

Then the **concentration test**: if more than a pre-registered share of the gain (default 80%)
is carried by fewer than two primitives, *and* those primitives are shortcut- or
compression-shaped, the result is recorded as consistent with H0 regardless of the aggregate
effect size.

Spec §42.3: the full table is published, including primitives with null and negative effects.
Selective reporting of the primitives that worked is a protocol violation, so `AttributionTable`
has no filtering method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..genomes.registry import Primitive
from ..kernel import Kernel, Program, Term
from ..stats.inference import Interval, bootstrap_difference_ci


def ablate(program: Program, primitive_id: str, kernel: Kernel) -> Program:
    """Remove one primitive by re-expanding its call sites to the K0 equivalent.

    M8 acceptance requires this to be verified by semantic-hash equality: the ablated program
    must denote the same function as the original. Ablation that changed the meaning would make
    every direct effect meaningless.
    """
    def rewrite(term: Term) -> Term:
        if term.op == primitive_id:
            expanded = kernel.expand(term)
            return rewrite(expanded)
        if not term.args:
            return term
        return Term(term.op, tuple(rewrite(a) for a in term.args), term.attrs)

    return Program(program.params, rewrite(program.body), program.result_type)


def expand_all(program: Program, kernel: Kernel) -> Program:
    """Force every call site to its expanded form (the indirect-effect construction)."""
    return Program(program.params, kernel.expand(program.body), program.result_type)


@dataclass(frozen=True, slots=True)
class PrimitiveEffect:
    """Per-primitive causal estimates — `schemas/causal_attribution.schema.json`."""

    primitive_id: str
    semantic_hash: str
    direct_effect: Interval
    indirect_effect: Interval
    cross_family_reuse: int
    shortcut_shaped: bool
    compression_shaped: bool
    semantic_gain_v2: float
    paired_ablations: tuple[dict, ...] = ()

    def to_record(self) -> dict:
        return {
            "primitive_id": self.primitive_id,
            "semantic_hash": self.semantic_hash,
            "direct_effect": {
                "estimate": self.direct_effect.point,
                "ci_low": self.direct_effect.low,
                "ci_high": self.direct_effect.high,
            },
            "indirect_effect": {
                "estimate": self.indirect_effect.point,
                "ci_low": self.indirect_effect.low,
                "ci_high": self.indirect_effect.high,
            },
            "paired_ablations": list(self.paired_ablations),
            "cross_family_reuse": self.cross_family_reuse,
            "shortcut_shaped": self.shortcut_shaped,
            "compression_shaped": self.compression_shaped,
            "semantic_gain_v2": self.semantic_gain_v2,
        }


@dataclass(frozen=True, slots=True)
class ConcentrationTest:
    top1_share: float
    top2_share: float
    threshold: float
    passed: bool
    verdict: str
    rationale: str = ""

    def to_record(self) -> dict:
        return {
            "top1_share": self.top1_share,
            "top2_share": self.top2_share,
            "threshold": self.threshold,
            "passed": self.passed,
            "verdict": self.verdict,
        }


@dataclass(slots=True)
class AttributionTable:
    """The full per-primitive table. Published entire, including nulls and negatives."""

    experiment_id: str
    effects: list[PrimitiveEffect] = field(default_factory=list)
    concentration: ConcentrationTest | None = None

    def to_record(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "primitive_effects": [e.to_record() for e in self.effects],
            "concentration_test": (
                self.concentration.to_record() if self.concentration else None
            ),
        }

    def summary_counts(self) -> dict[str, int]:
        positive = sum(1 for e in self.effects if e.direct_effect.point > 0)
        negative = sum(1 for e in self.effects if e.direct_effect.point < 0)
        return {
            "total": len(self.effects),
            "positive": positive,
            "negative": negative,
            "null": len(self.effects) - positive - negative,
        }


def concentration_test(
    effects: Sequence[PrimitiveEffect],
    *,
    threshold: float = 0.80,
) -> ConcentrationTest:
    """Spec §42.2's stop rule.

    Two conditions must both hold for the H0-consistent verdict: the gain is concentrated in
    fewer than two primitives, **and** those primitives are shortcut- or compression-shaped.
    Concentration alone is not disqualifying — one genuinely general abstraction carrying the
    result is a fine outcome. Concentration in a primitive that only ever fires on one family is
    the pattern the rule is aimed at.
    """
    positive = [e for e in effects if e.direct_effect.point > 0]
    total_gain = sum(e.direct_effect.point for e in positive)
    if total_gain <= 0:
        return ConcentrationTest(
            0.0, 0.0, threshold, True, "attributable",
            "no positive per-primitive gain to concentrate",
        )

    ranked = sorted(positive, key=lambda e: -e.direct_effect.point)
    top1 = ranked[0].direct_effect.point / total_gain
    top2 = sum(e.direct_effect.point for e in ranked[:2]) / total_gain

    concentrated = top1 > threshold or (len(ranked) < 2 and top1 >= 1.0)
    carriers = ranked[:1] if top1 > threshold else ranked[:2]
    suspect = any(e.shortcut_shaped or e.compression_shaped for e in carriers)

    if concentrated and suspect:
        return ConcentrationTest(
            top1, top2, threshold, False, "h0_consistent_concentrated_shortcut",
            f"{top1:.0%} of the gain is carried by one primitive, and it is "
            f"{'shortcut' if carriers[0].shortcut_shaped else 'compression'}-shaped",
        )
    if concentrated:
        return ConcentrationTest(
            top1, top2, threshold, True, "attributable",
            f"{top1:.0%} of the gain is concentrated, but the carrying primitive is neither "
            "shortcut- nor compression-shaped",
        )
    return ConcentrationTest(top1, top2, threshold, True, "attributable", "gain is distributed")


def paired_ablation(
    primitive_a: str,
    primitive_b: str,
    *,
    both_removed: Sequence[float],
    a_removed: Sequence[float],
    b_removed: Sequence[float],
    neither_removed: Sequence[float],
    seed: int = 0,
) -> dict:
    """Interaction between two co-occurring primitives (spec §42.1).

    The interaction is the departure from additivity: if removing both costs more than the sum
    of removing each alone, the two are doing something together that neither does apart.
    """
    from ..stats.inference import mean

    effect_a = mean(neither_removed) - mean(a_removed)
    effect_b = mean(neither_removed) - mean(b_removed)
    effect_both = mean(neither_removed) - mean(both_removed)
    interaction = effect_both - (effect_a + effect_b)
    ci = bootstrap_difference_ci(neither_removed, both_removed, seed=seed)
    return {
        "primitive_a": primitive_a,
        "primitive_b": primitive_b,
        "effect_a": effect_a,
        "effect_b": effect_b,
        "effect_both": effect_both,
        "interaction": interaction,
        "joint_ci": ci.to_record(),
    }


def build_attribution(
    experiment_id: str,
    *,
    primitives: Sequence[Primitive],
    with_primitive: Mapping[str, Sequence[float]],
    without_primitive: Mapping[str, Sequence[float]],
    forced_expansion: Mapping[str, Sequence[float]],
    cross_family_reuse: Mapping[str, int],
    semantic_gains: Mapping[str, float],
    shortcut_flags: Mapping[str, bool],
    compression_flags: Mapping[str, bool],
    threshold: float = 0.80,
    seed: int = 0,
) -> AttributionTable:
    """Assemble the full attribution table from per-seed outcome vectors."""
    table = AttributionTable(experiment_id=experiment_id)
    for primitive in primitives:
        pid = primitive.primitive_id
        direct = bootstrap_difference_ci(
            with_primitive.get(pid, []), without_primitive.get(pid, []), seed=seed
        )
        indirect = bootstrap_difference_ci(
            with_primitive.get(pid, []), forced_expansion.get(pid, []), seed=seed + 1
        )
        table.effects.append(
            PrimitiveEffect(
                primitive_id=pid,
                semantic_hash=primitive.semantic_id,
                direct_effect=direct,
                indirect_effect=indirect,
                cross_family_reuse=cross_family_reuse.get(pid, 0),
                shortcut_shaped=shortcut_flags.get(pid, False),
                compression_shaped=compression_flags.get(pid, False),
                semantic_gain_v2=semantic_gains.get(pid, 0.0),
            )
        )
    table.concentration = concentration_test(table.effects, threshold=threshold)
    return table
