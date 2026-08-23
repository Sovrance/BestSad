"""Per-primitive causal mediation for EXP-001 stage S3 (spec §42; plan M8).

Stage-level ablation says which *stage* carried a gain. This says which *primitive* did — the
question a reviewer asks and the one the promotion pipeline needs.

Two complications this module has to handle honestly rather than paper over:

**Primitives are not the same object across seeds.** Discovery runs per seed, so "primitive 0"
on seed 3 need not mean anything like "primitive 0" on seed 7. Effects are therefore grouped by
**semantic id**, and the number of seeds each semantic id appears in is reported as a
first-class outcome — spec §34 question 2 asks whether machine-discovered abstractions are
stable across seeds and says to treat cross-seed identity as a reported result, not a footnote.

**The indirect effect is structurally zero for this instrument.** Spec §42.1 defines it as the
outcome change when a primitive is retained but its call sites are forced to the expanded form,
separating "the abstraction itself" from "its availability during search". Expansion preserves
semantics and the evaluator scores semantics, so for a synthesizer whose only channel is search
depth this quantity is exactly zero by construction. It is computed and reported as zero with
that reason attached, rather than being dressed up as an independent measurement — the
informative content is the *reason*, which is that any benefit here is availability during
search rather than the abstraction appearing in the output.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Mapping, Sequence

from ..causal import AttributionTable, PrimitiveEffect, concentration_test
from ..conditions import Condition
from ..evaluator import suspicious_primitive
from ..genomes import Genome, Primitive
from ..kernel import KERNEL_VERSION
from ..stats import Interval, bootstrap_difference_ci, mean
from .exp001 import Exp001Runner, _job


def collect_primitives(runner: Exp001Runner) -> dict[int, list[Primitive]]:
    """Re-derive each seed's utility-selected primitives. Discovery is deterministic, so this
    reproduces exactly what the S2 run used."""
    out: dict[int, list[Primitive]] = {}
    for seed in runner.seeds:
        primitives, _nodes, _notes = runner.discover(seed)
        out[seed] = primitives["utility"]
    return out


def cross_seed_stability(by_seed: Mapping[int, Sequence[Primitive]]) -> dict:
    """How often each discovered abstraction recurs across seeds (spec §34 Q2)."""
    seeds_by_semantic: dict[str, list[int]] = {}
    exemplar: dict[str, Primitive] = {}
    for seed, primitives in by_seed.items():
        for primitive in primitives:
            seeds_by_semantic.setdefault(primitive.semantic_id, []).append(seed)
            exemplar.setdefault(primitive.semantic_id, primitive)
    total_seeds = len(by_seed)
    return {
        "distinct_abstractions": len(seeds_by_semantic),
        "total_seeds": total_seeds,
        "recurrence": {
            sid: {
                "seeds": sorted(seeds),
                "seed_count": len(seeds),
                "fraction_of_seeds": len(seeds) / total_seeds if total_seeds else 0.0,
                "expansion_size": exemplar[sid].size,
                "arity": len(exemplar[sid].params),
            }
            for sid, seeds in seeds_by_semantic.items()
        },
        "exemplars": exemplar,
    }


def run_attribution(
    runner: Exp001Runner,
    *,
    treatment_records: Sequence[dict],
    min_seeds: int = 2,
    seed: int = 0,
) -> tuple[AttributionTable, dict]:
    """Ablate each recurring abstraction and estimate its direct effect.

    `treatment_records` are condition D's per-seed records from S2 — the "with primitive" arm.
    The "without" arm re-runs condition D on the same seeds with that one abstraction removed
    and its call sites re-expanded to K0, holding the search budget fixed (spec §42.1).
    """
    by_seed = collect_primitives(runner)
    stability = cross_seed_stability(by_seed)
    exemplars = stability.pop("exemplars")

    with_by_seed = {int(r["seed"]): float(r["verified_ood_rate"]) for r in treatment_records}

    jobs: list[tuple[Condition, int]] = []
    job_index: list[tuple[str, int]] = []
    for sid, info in stability["recurrence"].items():
        if info["seed_count"] < min_seeds:
            continue
        for s in info["seeds"]:
            remaining = [p for p in by_seed[s] if p.semantic_id != sid]
            genome = Genome(f"G-D-minus-{sid[:8]}", 1, KERNEL_VERSION, tuple(remaining), "sexpr")
            jobs.append(
                (
                    Condition(
                        condition_id="D_ablated",
                        role="treatment",
                        genome=genome,
                        description=f"condition D with abstraction {sid[:8]} ablated",
                        node_budget=runner.budget.max_nodes,
                    ),
                    s,
                )
            )
            job_index.append((sid, s))

    records = runner._map_jobs(jobs) if jobs else []
    without: dict[str, dict[int, float]] = {}
    for (sid, s), record in zip(job_index, records):
        without.setdefault(sid, {})[s] = float(record["verified_ood_rate"])

    table = AttributionTable(experiment_id=runner.run_id)
    for sid, info in stability["recurrence"].items():
        seeds = [s for s in info["seeds"] if s in without.get(sid, {})]
        if not seeds:
            continue
        with_values = [with_by_seed[s] for s in seeds if s in with_by_seed]
        without_values = [without[sid][s] for s in seeds if s in with_by_seed]
        direct = bootstrap_difference_ci(with_values, without_values, seed=seed)

        primitive = exemplars[sid]
        # Shortcut-shaped: concentrated in one family. Compression-shaped: a large expansion
        # that mostly buys surface length rather than structure.
        families = set()
        for record in treatment_records:
            for pid, used_families in record.get("cross_family_reuse", {}).items():
                if pid.startswith("prim:"):
                    families.update(used_families)
        suspicion = suspicious_primitive(sid, max(0.0, direct.point), sorted(families))

        table.effects.append(
            PrimitiveEffect(
                primitive_id=primitive.primitive_id,
                semantic_hash=sid,
                direct_effect=direct,
                # Structurally zero for this instrument — see the module docstring.
                indirect_effect=Interval(0.0, 0.0, 0.0),
                cross_family_reuse=len(families),
                shortcut_shaped=suspicion.suspicious,
                compression_shaped=primitive.size >= 8 and len(primitive.params) <= 1,
                semantic_gain_v2=0.0,
            )
        )

    table.concentration = concentration_test(table.effects)
    stability["ablation_jobs"] = len(jobs)
    stability["indirect_effect_note"] = (
        "Indirect effect is identically zero here: expansion preserves semantics and the "
        "evaluator scores semantics, so forcing call sites to the expanded form cannot change "
        "a verified solve rate. Any benefit in this instrument is availability during search, "
        "not the abstraction appearing in the emitted program."
    )
    return table, stability
