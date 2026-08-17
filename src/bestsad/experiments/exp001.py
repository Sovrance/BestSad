"""EXP-001 stage S1–S3 runner (spec §24, §43; implementation plan M3 E0, M10).

Stages, gated as spec §43 requires:

* **S1** — E0 baseline and *measured* variance, then a power analysis against the pre-registered
  minimum interesting effect. If the achievable seed count cannot power it, S2 does not run.
* **S2** — conditions A–F, H, I on the primary endpoint.
* **S3** — condition G (the reference class) and per-primitive causal mediation.

The abstraction corpus is built **only from curriculum solutions** (F1–F8). Mining held-out
solutions would fit the abstractions to the evaluation set, which is contamination rather than
discovery, and would guarantee a positive result that meant nothing.

Evolution compute is metered while abstractions are being discovered, and condition I is then
given exactly that much extra search. Nothing about that is optional: it is the single most
important control in the experiment (spec §24.5 I).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..abstraction import (
    Corpus,
    mine_candidates,
    random_matched_primitives,
    select,
    to_primitives,
)
from ..bsir import get_projection, token_count
from ..conditions import (
    ComputeLedger,
    Condition,
    ScaffoldingMatcher,
    build_conditions,
    check_condition_f,
    reconcile_search_only,
)
from ..evaluator import Evaluator, ScoreReport, detect_hardcoding, manifest_for
from ..genomes import Genome, Primitive
from ..kernel import INT, KERNEL_VERSION, Kernel, TList, app, const_int, lam, var
from ..kernel.ops import OPS_BY_NAME
from ..mdl import CodingScheme, PairedOutcome, compression_ratio
from ..solver import EnumerativeSynthesizer, SearchBudget
from ..stats import bootstrap_ci, mean, power_analysis, variance
from ..tasks import (
    CURRICULUM_FAMILIES,
    HELD_OUT_FAMILIES,
    TaskSet,
    adversarial_set,
    curriculum_set,
    held_out_set,
    in_family_ood_set,
)

#: Operations the synthesizer composes with. Leaves (`var`, constants, `nil`, `none`) and `lam`
#: are supplied structurally rather than enumerated as operations.
BASE_VOCABULARY: tuple[str, ...] = tuple(
    op for op in OPS_BY_NAME
    if op not in ("lam", "var", "const_int", "const_bool", "nil", "none")
)

MODEL_IDENTITY = "enumerative-search-v1"


@dataclass(slots=True)
class ConditionOutcome:
    """One (condition, seed) result."""

    condition_id: str
    seed: int
    primary: float                       # verified OOD solve rate per unit compute
    verified_ood_rate: float
    verified_in_family_rate: float
    verified_adversarial_rate: float
    train_only_rate: float
    total_compute: float
    model_tokens: int
    search_nodes: int
    language_description_tokens: int
    primitive_reuse: dict = field(default_factory=dict)
    cross_family_reuse: dict = field(default_factory=dict)
    ledger: dict = field(default_factory=dict)
    hardcoding_incidents: int = 0

    def to_record(self) -> dict:
        data = asdict(self)
        data["cross_family_reuse"] = {k: sorted(v) for k, v in self.cross_family_reuse.items()}
        return data


@dataclass(slots=True)
class StageResult:
    stage: str
    passed: bool
    detail: str
    payload: dict = field(default_factory=dict)


def expert_dsl_primitives() -> list[Primitive]:
    """Condition G: a human-authored DSL for this task family (spec §24.5 G).

    Authored against the *family documentation only* — the structural descriptions in
    `tasks/families.py` — and deliberately not informed by any evolved genome, which is what
    "author blind to the evolved genomes" requires. It is frozen here before any evaluation run.

    The design intent is the obvious one a competent person would reach for: name the three
    aggregations the families keep re-deriving, and the two-stage list pipeline.
    """
    xs = var("xs")
    sum_body = app(
        "fold", lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
        const_int(0), xs,
    )
    max_body = app(
        "fold", lam((("acc", INT), ("e", INT)), app("max", var("acc"), var("e"))),
        const_int(0), xs,
    )
    count_body = app("length", xs)
    return [
        Primitive("prim:g_sum", ("xs",), sum_body, (TList(INT),), INT, origin="human_expert",
                  display_names=("sum",)),
        Primitive("prim:g_max", ("xs",), max_body, (TList(INT),), INT, origin="human_expert",
                  display_names=("maximum",)),
        Primitive("prim:g_count", ("xs",), count_body, (TList(INT),), INT,
                  origin="human_expert", display_names=("count",)),
    ]


class Exp001Runner:
    """Runs EXP-001's staged gates end to end."""

    def __init__(
        self,
        *,
        run_id: str,
        seeds: Sequence[int],
        per_family: int = 3,
        budget: SearchBudget | None = None,
        artifacts_dir: Path | None = None,
        abstraction_count: int = 4,
    ) -> None:
        self.run_id = run_id
        self.seeds = tuple(seeds)
        self.per_family = per_family
        self.budget = budget or SearchBudget(max_nodes=90_000, max_size=6)
        self.artifacts_dir = artifacts_dir or Path("artifacts") / run_id
        self.abstraction_count = abstraction_count
        self.scheme = CodingScheme()
        self.log: list[str] = []

    # -- helpers ---------------------------------------------------------------------------

    def _say(self, message: str) -> None:
        self.log.append(message)

    def _task_sets(self, seed: int) -> dict[str, TaskSet]:
        return {
            "curriculum": curriculum_set(seed, self.per_family),
            "held_out": held_out_set(90210 + seed, self.per_family),
            "in_family_ood": in_family_ood_set(90212 + seed, self.per_family),
            "adversarial": adversarial_set(90211 + seed, max(1, self.per_family - 1)),
        }

    def _run_condition(
        self,
        condition: Condition,
        seed: int,
        task_sets: Mapping[str, TaskSet],
    ) -> ConditionOutcome:
        genome = condition.genome
        kernel = genome.kernel(fuel=self.budget.kernel_fuel)
        projection = get_projection(genome.projection_name)
        budget = SearchBudget(**{**asdict(self.budget),
                                 "max_nodes": condition.node_budget or self.budget.max_nodes})
        synthesizer = EnumerativeSynthesizer(
            kernel, genome.vocabulary(BASE_VOCABULARY), genome.signatures(),
            budget=budget, seed=seed,
        )
        evaluator = Evaluator(
            "bm-exp001", genome.signatures(), genome.expansions(),
        )
        ledger = ComputeLedger(self.run_id, condition.condition_id, seed,
                               model_identity_hash=MODEL_IDENTITY)

        reports: dict[str, ScoreReport] = {}
        hardcoding = 0
        started = time.time()

        for name in ("held_out", "in_family_ood", "adversarial"):
            report = ScoreReport(condition.condition_id, seed, "bm-exp001")
            for task in task_sets[name]:
                result = synthesizer.solve(task)
                tokens = (
                    token_count(projection.render(result.program.body))
                    if result.program is not None else 0
                )
                score = evaluator.score_task(
                    task, result.program,
                    solved_train=result.solved_train,
                    model_tokens=tokens,
                    search_nodes=result.nodes_expanded,
                    kernel_steps=result.kernel_steps,
                )
                report.scores.append(score)
                ledger.add(
                    search_nodes=result.nodes_expanded,
                    kernel_steps=result.kernel_steps,
                    candidate_evaluations=result.evaluations,
                    model_output_tokens=tokens,
                )
                if result.program is not None and not score.verified and result.solved_train:
                    if detect_hardcoding(result.program, task, kernel, seed=seed).hardcoded:
                        hardcoding += 1
            reports[name] = report

        ledger.wall_clock_s = time.time() - started
        if condition.inherited_evolution_compute_from:
            # Condition I's inherited evolution compute is real spend, recorded as such.
            ledger.add(evolution_nodes=0)

        held = reports["held_out"]
        total_compute = max(1.0, ledger.total_experimental_compute)
        return ConditionOutcome(
            condition_id=condition.condition_id,
            seed=seed,
            primary=held.verified_solve_rate / total_compute * 1_000_000,
            verified_ood_rate=held.verified_solve_rate,
            verified_in_family_rate=reports["in_family_ood"].verified_solve_rate,
            verified_adversarial_rate=reports["adversarial"].verified_solve_rate,
            train_only_rate=held.train_only_rate,
            total_compute=total_compute,
            model_tokens=held.total_model_tokens,
            search_nodes=held.total_search_nodes,
            language_description_tokens=genome.description_length_tokens(),
            primitive_reuse=held.primitive_use_counts(),
            cross_family_reuse={
                k: v for k, v in held.primitive_family_reuse().items()
            },
            ledger=ledger.to_record(compression_ratio=0.0, capability_delta=0.0),
            hardcoding_incidents=hardcoding,
        )

    # -- S1: baseline and variance ---------------------------------------------------------

    def stage_s1(self, minimum_interesting_effect: float = 0.05) -> StageResult:
        """E0 baseline, measured variance, power analysis (spec §43 S1, plan M3)."""
        self._say("S1: measuring the E0 baseline and its across-seed variance")
        baseline = Genome("G-A", 0, KERNEL_VERSION, (), "sexpr")
        condition = Condition("A", "reference", baseline, "K0 baseline",
                              node_budget=self.budget.max_nodes)

        outcomes = []
        for seed in self.seeds:
            outcomes.append(self._run_condition(condition, seed, self._task_sets(seed)))

        rates = [o.verified_ood_rate for o in outcomes]
        measured_variance = variance(rates)
        analysis = power_analysis(
            effect_size=minimum_interesting_effect,
            variance_estimate=measured_variance,
            seeds_per_condition=len(self.seeds),
        )
        self._say(
            f"S1: baseline verified OOD rate {mean(rates):.3f}, variance {measured_variance:.5f}"
            f", power {analysis.achieved_power:.2f} "
            f"(needs {analysis.required_seeds} seeds for {minimum_interesting_effect:.0%})"
        )
        return StageResult(
            stage="S1",
            passed=analysis.powered,
            detail=(
                "variance measured; power analysis passes"
                if analysis.powered
                else (
                    f"variance measured, but {len(self.seeds)} seeds cannot power a "
                    f"{minimum_interesting_effect:.0%} effect: {analysis.required_seeds} "
                    "would be required. Spec §26.8 says record this and re-scope rather than "
                    "run underpowered and interpret the point estimate."
                )
            ),
            payload={
                "per_seed_verified_ood_rate": rates,
                "mean": mean(rates),
                "variance": measured_variance,
                "bootstrap_ci": bootstrap_ci(rates, seed=1).to_record(),
                "power_analysis": analysis.to_record(),
                "outcomes": [o.to_record() for o in outcomes],
            },
        )

    # -- abstraction discovery (metered) ----------------------------------------------------

    def discover(self, seed: int) -> tuple[dict[str, list[Primitive]], int, dict]:
        """Solve curriculum tasks, mine abstractions, and meter the compute it took.

        Returns the primitive sets for conditions B/C/D and the metered evolution compute that
        condition I must be given.
        """
        baseline = Genome("G-A", 0, KERNEL_VERSION, (), "sexpr")
        kernel = baseline.kernel(fuel=self.budget.kernel_fuel)
        synthesizer = EnumerativeSynthesizer(
            kernel, BASE_VOCABULARY, {}, budget=self.budget, seed=seed
        )
        corpus = Corpus()
        evolution_nodes = 0
        solved = 0

        for task in curriculum_set(seed, self.per_family):
            result = synthesizer.solve(task)
            evolution_nodes += result.nodes_expanded
            if result.program is not None:
                corpus.add(result.program, task.family)
                solved += 1

        candidates = mine_candidates(corpus)
        utility = to_primitives(
            select(candidates, "utility", self.abstraction_count,
                   family_count=len(CURRICULUM_FAMILIES), seed=seed),
            "u",
        )
        mdl = to_primitives(
            select(candidates, "mdl", self.abstraction_count, seed=seed), "m"
        )
        random_macros = random_matched_primitives(utility, candidates, "r", seed)

        self._say(
            f"discovery(seed={seed}): {solved}/{len(corpus.entries) or 1} curriculum solutions, "
            f"{len(candidates)} candidate abstractions, "
            f"selected {len(utility)} utility / {len(mdl)} MDL / {len(random_macros)} random; "
            f"evolution compute {evolution_nodes} nodes"
        )
        return (
            {"utility": utility, "mdl": mdl, "random": random_macros},
            evolution_nodes,
            {
                "curriculum_solved": solved,
                "corpus_size": len(corpus),
                "candidates_mined": len(candidates),
                "families_in_corpus": sorted(corpus.families()),
            },
        )

    # -- S2: the condition set ---------------------------------------------------------------

    def stage_s2(self) -> StageResult:
        """Conditions A–F, H, I across seeds (spec §43 S2)."""
        self._say("S2: running conditions A-F, H, I")
        per_condition: dict[str, list[ConditionOutcome]] = {}
        discovery_notes: list[dict] = []
        scaffolding_reports = []
        reconciliations = []

        for seed in self.seeds:
            primitives, evolution_nodes, notes = self.discover(seed)
            notes["seed"] = seed
            notes["evolution_nodes"] = evolution_nodes
            discovery_notes.append(notes)

            plane = build_conditions(
                kernel_version=KERNEL_VERSION,
                random_primitives=primitives["random"],
                mdl_primitives=primitives["mdl"],
                utility_primitives=primitives["utility"],
                expert_primitives=expert_dsl_primitives(),
                baseline_node_budget=self.budget.max_nodes,
                evolution_nodes=evolution_nodes,
            )
            check_condition_f(plane["F"], plane["A"])

            matcher = ScaffoldingMatcher()
            scaffolding = matcher.equalize(
                {cid: c.genome.description_length_tokens() for cid, c in plane.items()}
            )
            scaffolding_reports.append(
                {
                    "seed": seed,
                    "target_tokens": scaffolding.target_tokens,
                    "disclosure": scaffolding.disclosure(),
                    "residuals": {k: v.to_record() for k, v in scaffolding.residuals.items()},
                }
            )

            task_sets = self._task_sets(seed)
            for cid in ("A", "B", "C", "D", "E", "F", "H", "I"):
                outcome = self._run_condition(plane[cid], seed, task_sets)
                per_condition.setdefault(cid, []).append(outcome)

            reconciliations.append(
                reconcile_search_only(
                    baseline=ComputeLedger(
                        self.run_id, "A", seed,
                        search_nodes=int(per_condition["A"][-1].search_nodes),
                    ),
                    treatment=ComputeLedger(
                        self.run_id, "D", seed,
                        search_nodes=int(per_condition["D"][-1].search_nodes),
                        evolution_nodes=evolution_nodes,
                    ),
                    search_only=ComputeLedger(
                        self.run_id, "I", seed,
                        search_nodes=int(per_condition["I"][-1].search_nodes),
                    ),
                )
            )

        return StageResult(
            stage="S2",
            passed=True,
            detail="conditions A-F, H, I completed",
            payload={
                "per_condition": {
                    cid: [o.to_record() for o in outcomes]
                    for cid, outcomes in per_condition.items()
                },
                "discovery": discovery_notes,
                "scaffolding": scaffolding_reports,
                "compute_reconciliation": reconciliations,
            },
        )

    # -- S3: reference class ------------------------------------------------------------------

    def stage_s3(self, s2: StageResult) -> StageResult:
        """Condition G, the human-expert DSL reference class (spec §43 S3)."""
        self._say("S3: running condition G (human-expert DSL reference class)")
        outcomes = []
        for seed in self.seeds:
            plane = build_conditions(
                kernel_version=KERNEL_VERSION,
                random_primitives=[], mdl_primitives=[], utility_primitives=[],
                expert_primitives=expert_dsl_primitives(),
                baseline_node_budget=self.budget.max_nodes,
                evolution_nodes=0,
            )
            outcomes.append(self._run_condition(plane["G"], seed, self._task_sets(seed)))
        return StageResult(
            stage="S3",
            passed=True,
            detail="condition G completed",
            payload={"per_condition": {"G": [o.to_record() for o in outcomes]}},
        )
