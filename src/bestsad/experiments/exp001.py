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

import hashlib
import json
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
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
        data["reproducibility_digest"] = self.reproducibility_digest()
        return data

    def reproducibility_digest(self) -> str:
        """Content hash of everything except wall-clock timing.

        Wall clock must be logged (spec §26.4) and can never be reproduced exactly, so a naive
        record comparison always reports a difference and replay verification becomes useless.
        This digest is what Gate G2's "replay works" is actually checked against: it covers
        every scientific quantity and no timing field.
        """
        data = asdict(self)
        data.pop("ledger", None)
        data["cross_family_reuse"] = {k: sorted(v) for k, v in self.cross_family_reuse.items()}
        payload = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:32]


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


def _discovery_job(payload: tuple) -> tuple:
    """Worker entry point for abstraction discovery on one seed.

    Checkpointed via pickle rather than JSON: the payload contains `Primitive` objects, whose
    expansions are K0 terms. Serializing those to JSON and back would need a term parser that
    round-trips attributes exactly, and a silent mismatch there would change what condition D
    actually is.
    """
    seed, kwargs, run_id, checkpoint_dir = payload
    path = Path(checkpoint_dir) / f"discovery_seed{seed}.pkl" if checkpoint_dir else None
    if path is not None and path.exists():
        with path.open("rb") as handle:
            return pickle.load(handle)

    runner = Exp001Runner(run_id=run_id, seeds=(seed,), **kwargs)
    primitives, evolution_nodes, notes = runner.discover(seed)
    result = (seed, primitives, evolution_nodes, notes, runner.log)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(result, handle)
    return result


def _job(payload: tuple) -> dict:
    """Worker entry point: run one (condition, seed) and return its record.

    A separate process per job. Each job is a pure function of `(condition, seed, sizing,
    budget)` — the synthesizer is deterministic given those — so running them concurrently
    produces byte-identical records to running them in sequence. Parallelism here buys wall
    clock and changes nothing about the result, which is the only kind of speed-up this
    instrument can accept.

    Completed jobs are written to `checkpoint_dir` and reused on a later run. A full staged run
    takes hours, dominated by condition I — which is expensive *by design*, since it must be
    given the entire compute genome evolution consumed in D. Losing all of it to one interruption
    would be an accident of engineering, not a scientific constraint, so it is checkpointed.
    """
    condition, seed, kwargs, run_id, checkpoint_dir = payload
    # The key must cover everything that changes the result, not just the genome. Condition I's
    # genome is empty and identical across configurations, so a key built from the genome alone
    # collides between runs with different search budgets or depths — and silently serves a
    # record produced under the *other* configuration. A checkpoint that returns the wrong
    # answer instantly is worse than no checkpoint at all.
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "genome": condition.genome.content_hash(),
                "node_budget": condition.node_budget,
                "depth_bonus": condition.search_depth_bonus,
                "budget": asdict(kwargs["budget"]),
                "per_family": kwargs.get("per_family"),
                "in_family": kwargs.get("in_family_per_family"),
                "adversarial": kwargs.get("adversarial_per_family"),
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:12]
    key = f"{condition.condition_id}_{fingerprint}_seed{seed}"
    path = Path(checkpoint_dir) / f"{key}.json" if checkpoint_dir else None
    if path is not None and path.exists():
        return json.loads(path.read_text())

    runner = Exp001Runner(run_id=run_id, seeds=(seed,), **kwargs)
    record = runner._run_condition(condition, seed, runner._task_sets(seed)).to_record()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, default=str))
    return record


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
        in_family_per_family: int | None = None,
        adversarial_per_family: int | None = None,
        workers: int = 1,
        checkpoint_dir: Path | None = None,
    ) -> None:
        self.run_id = run_id
        self.seeds = tuple(seeds)
        # `per_family` sizes the curriculum and the held-out set, which carries the primary
        # endpoint. The secondary sets can be sized independently: they inform secondary
        # endpoints only, and every task in them costs the full node budget when unsolved.
        self.per_family = per_family
        self.in_family_per_family = (
            per_family if in_family_per_family is None else in_family_per_family
        )
        self.adversarial_per_family = (
            max(1, per_family - 1) if adversarial_per_family is None else adversarial_per_family
        )
        self.workers = max(1, workers)
        self.checkpoint_dir = checkpoint_dir
        self.budget = budget or SearchBudget(max_nodes=90_000, max_size=6)
        self.artifacts_dir = artifacts_dir or Path("artifacts") / run_id
        self.abstraction_count = abstraction_count
        self.scheme = CodingScheme()
        self.log: list[str] = []

    # -- helpers ---------------------------------------------------------------------------

    def _say(self, message: str) -> None:
        self.log.append(message)

    def tasks_per_seed(self) -> int:
        """How many tasks each condition is scored on per seed.

        Condition I's inherited evolution compute is a total and must be spread across these
        (spec §26.6), which is what keeps its reconciliation identity true.
        """
        sets = self._task_sets(self.seeds[0])
        return sum(len(sets[name]) for name in ("held_out", "in_family_ood", "adversarial"))

    def _task_sets(self, seed: int) -> dict[str, TaskSet]:
        return {
            "curriculum": curriculum_set(seed, self.per_family),
            "held_out": held_out_set(90210 + seed, self.per_family),
            "in_family_ood": in_family_ood_set(90212 + seed, self.in_family_per_family),
            "adversarial": adversarial_set(90211 + seed, self.adversarial_per_family),
        }

    def _sizing(self) -> dict:
        """The constructor arguments a worker needs to reproduce this runner's task sizing."""
        return {
            "per_family": self.per_family,
            "in_family_per_family": self.in_family_per_family,
            "adversarial_per_family": self.adversarial_per_family,
            "budget": self.budget,
            "abstraction_count": self.abstraction_count,
        }

    def _map_jobs(self, jobs: Sequence[tuple[Condition, int]]) -> list[dict]:
        """Run `(condition, seed)` jobs, in parallel when `workers > 1`."""
        checkpoint = str(self.checkpoint_dir) if self.checkpoint_dir else None
        payloads = [
            (condition, seed, self._sizing(), self.run_id, checkpoint)
            for condition, seed in jobs
        ]
        if self.workers == 1:
            return [_job(p) for p in payloads]
        with ProcessPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(_job, payloads))

    def _run_condition(
        self,
        condition: Condition,
        seed: int,
        task_sets: Mapping[str, TaskSet],
    ) -> ConditionOutcome:
        genome = condition.genome
        kernel = genome.kernel(fuel=self.budget.kernel_fuel)
        projection = get_projection(genome.projection_name)
        budget = SearchBudget(**{
            **asdict(self.budget),
            "max_nodes": condition.node_budget or self.budget.max_nodes,
            "max_size": self.budget.max_size + condition.search_depth_bonus,
        })
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

        records = self._map_jobs([(condition, seed) for seed in self.seeds])
        rates = [float(r["verified_ood_rate"]) for r in records]
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
                "outcomes": records,
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
        per_condition: dict[str, list[dict]] = {}
        jobs: list[tuple[Condition, int]] = []
        evolution_by_seed: dict[int, int] = {}
        discovery_notes: list[dict] = []
        scaffolding_reports = []
        reconciliations = []

        checkpoint = str(self.checkpoint_dir) if self.checkpoint_dir else None
        payloads = [(seed, self._sizing(), self.run_id, checkpoint) for seed in self.seeds]
        if self.workers == 1:
            discoveries = [_discovery_job(p) for p in payloads]
        else:
            with ProcessPoolExecutor(max_workers=self.workers) as pool:
                discoveries = list(pool.map(_discovery_job, payloads))

        for seed, primitives, evolution_nodes, notes, worker_log in discoveries:
            notes["seed"] = seed
            notes["evolution_nodes"] = evolution_nodes
            discovery_notes.append(notes)
            self.log.extend(worker_log)

            plane = build_conditions(
                kernel_version=KERNEL_VERSION,
                random_primitives=primitives["random"],
                mdl_primitives=primitives["mdl"],
                utility_primitives=primitives["utility"],
                expert_primitives=expert_dsl_primitives(),
                baseline_node_budget=self.budget.max_nodes,
                evolution_nodes=evolution_nodes,
                tasks_per_seed=self.tasks_per_seed(),
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

            for cid in ("A", "B", "C", "D", "E", "F", "H", "I"):
                jobs.append((plane[cid], seed))
            evolution_by_seed[seed] = evolution_nodes

        records = self._map_jobs(jobs)
        for record in records:
            per_condition.setdefault(record["condition_id"], []).append(record)

        for seed in self.seeds:
            def nodes(cid: str) -> int:
                return int(
                    next(r["search_nodes"] for r in per_condition[cid] if r["seed"] == seed)
                )

            reconciliations.append(
                reconcile_search_only(
                    baseline=ComputeLedger(self.run_id, "A", seed, search_nodes=nodes("A")),
                    treatment=ComputeLedger(
                        self.run_id, "D", seed,
                        search_nodes=nodes("D"),
                        evolution_nodes=evolution_by_seed[seed],
                    ),
                    search_only=ComputeLedger(self.run_id, "I", seed, search_nodes=nodes("I")),
                )
            )

        return StageResult(
            stage="S2",
            passed=True,
            detail="conditions A-F, H, I completed",
            payload={
                "per_condition": per_condition,
                "discovery": discovery_notes,
                "scaffolding": scaffolding_reports,
                "compute_reconciliation": reconciliations,
            },
        )

    # -- S3: reference class ------------------------------------------------------------------

    def stage_s3(self, s2: StageResult) -> StageResult:
        """Condition G, the human-expert DSL reference class (spec §43 S3)."""
        self._say("S3: running condition G (human-expert DSL reference class)")
        plane = build_conditions(
            kernel_version=KERNEL_VERSION,
            random_primitives=[], mdl_primitives=[], utility_primitives=[],
            expert_primitives=expert_dsl_primitives(),
            baseline_node_budget=self.budget.max_nodes,
            evolution_nodes=0,
        )
        records = self._map_jobs([(plane["G"], seed) for seed in self.seeds])
        return StageResult(
            stage="S3",
            passed=True,
            detail="condition G completed",
            payload={"per_condition": {"G": records}},
        )
