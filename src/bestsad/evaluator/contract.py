"""Evaluator public contract and scoring (spec §20, §29.7).

The evaluator is the only component that touches hidden test data. Everything a candidate is
allowed to know is in this module; everything a candidate is *not* allowed to know lives behind
`hidden_evaluator/` and is reached only through `HiddenBenchmark`.

Correctness is defined here and is frozen (`AGENTS.md` invariant 1): a candidate program solves
a task when, for every hidden input, its outcome under the trusted K0 interpreter equals the
reference's outcome — same value, or the same trap kind. Nothing else counts as solving, and
this rule is never relaxed to make a condition look better.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from ..kernel import Kernel, Program
from ..kernel.ops import OpSig
from ..bsir.graph import verify as bsir_verify
from ..tasks.families import Task
from ..tasks.generator import TaskSet

SCORING_CONTRACT_VERSION = "scoring-1.0.0"


@dataclass(frozen=True, slots=True)
class TaskScore:
    task_id: str
    family: str
    attempted: bool
    solved_train: bool
    verified: bool
    reason: str = ""
    hidden_passed: int = 0
    hidden_total: int = 0
    emitted_size: int = 0
    model_tokens: int = 0
    search_nodes: int = 0
    kernel_steps: int = 0
    primitives_used: tuple[str, ...] = ()


@dataclass(slots=True)
class ScoreReport:
    """A signed/hashed fitness vector (spec §29.7)."""

    condition_id: str
    seed: int
    benchmark_manifest_id: str
    scores: list[TaskScore] = field(default_factory=list)
    integrity_findings: list[dict] = field(default_factory=list)

    # -- aggregate metrics --

    @property
    def verified_solve_rate(self) -> float:
        return _rate(sum(1 for s in self.scores if s.verified), len(self.scores))

    def verified_rate_for(self, families: Sequence[str]) -> float:
        subset = [s for s in self.scores if s.family in families]
        return _rate(sum(1 for s in subset if s.verified), len(subset))

    @property
    def train_only_rate(self) -> float:
        """Solved the visible examples but failed the hidden set — the overfitting signal."""
        return _rate(
            sum(1 for s in self.scores if s.solved_train and not s.verified), len(self.scores)
        )

    @property
    def total_model_tokens(self) -> int:
        return sum(s.model_tokens for s in self.scores)

    @property
    def total_search_nodes(self) -> int:
        return sum(s.search_nodes for s in self.scores)

    @property
    def total_kernel_steps(self) -> int:
        return sum(s.kernel_steps for s in self.scores)

    def primitive_use_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for score in self.scores:
            if not score.verified:
                continue
            for prim in score.primitives_used:
                counts[prim] = counts.get(prim, 0) + 1
        return counts

    def primitive_family_reuse(self) -> dict[str, set[str]]:
        """Which families each primitive was used in — measured directly, never inferred from
        accuracy (spec H2, and the M6 acceptance criterion)."""
        out: dict[str, set[str]] = {}
        for score in self.scores:
            if not score.verified:
                continue
            for prim in score.primitives_used:
                out.setdefault(prim, set()).add(score.family)
        return out

    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "condition": self.condition_id,
                "seed": self.seed,
                "benchmark": self.benchmark_manifest_id,
                "scores": [asdict(s) for s in self.scores],
            },
            sort_keys=True,
            default=list,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


class Evaluator:
    """Scores candidate programs against a task set.

    The evaluator holds its own `Kernel`, separate from any kernel a candidate or a search used,
    so a mutated kernel on the candidate side cannot change what counts as correct.
    """

    def __init__(
        self,
        benchmark_manifest_id: str,
        primitives: Mapping[str, OpSig] | None = None,
        expansions: Mapping[str, tuple[tuple[str, ...], object]] | None = None,
        *,
        fuel: int = 20_000,
    ) -> None:
        self.benchmark_manifest_id = benchmark_manifest_id
        self.primitives = dict(primitives or {})
        # The evaluator expands primitives itself rather than trusting a candidate-supplied
        # expansion: a primitive is a macro over K0, and the evaluator checks the K0 meaning.
        self.kernel = Kernel(dict(expansions or {}), fuel=fuel)

    def score_task(
        self,
        task: Task,
        candidate: Program | None,
        *,
        solved_train: bool = False,
        model_tokens: int = 0,
        search_nodes: int = 0,
        kernel_steps: int = 0,
    ) -> TaskScore:
        base = dict(
            task_id=task.task_id,
            family=task.family,
            attempted=candidate is not None,
            solved_train=solved_train,
            model_tokens=model_tokens,
            search_nodes=search_nodes,
            kernel_steps=kernel_steps,
            hidden_total=len(task.hidden_inputs),
        )
        if candidate is None:
            return TaskScore(verified=False, reason="no candidate", **base)

        report = bsir_verify(candidate, self.primitives)
        if not report.ok:
            return TaskScore(verified=False, reason=f"failed {report.layer}: {report.detail}",
                             **base)

        passed = 0
        for inputs in task.hidden_inputs:
            expected = self.kernel.execute(task.reference, list(inputs))
            actual = self.kernel.execute(candidate, list(inputs))
            if expected.same_outcome(actual):
                passed += 1

        primitives_used = tuple(
            sorted({t.op for t in candidate.body.walk() if t.op.startswith("prim:")})
        )
        verified = passed == len(task.hidden_inputs)
        return TaskScore(
            verified=verified,
            reason="" if verified else f"hidden {passed}/{len(task.hidden_inputs)}",
            hidden_passed=passed,
            emitted_size=candidate.body.size(),
            primitives_used=primitives_used,
            **base,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkManifest:
    """Provenance for a benchmark (spec §30, `schemas/benchmark_manifest.schema.json`)."""

    benchmark_manifest_id: str
    benchmark_class: str
    generator_version: str
    kernel_version: str
    task_families: tuple[str, ...]
    seed_commitment: str | None
    family_holdouts: tuple[str, ...]
    integrity_policy: dict
    scoring_contract_version: str = SCORING_CONTRACT_VERSION

    def to_dict(self) -> dict:
        data = asdict(self)
        data["task_families"] = list(self.task_families)
        data["family_holdouts"] = list(self.family_holdouts)
        return data


def manifest_for(task_set: TaskSet, benchmark_class: str, holdouts: Sequence[str]) -> BenchmarkManifest:
    from ..kernel.spec import KERNEL_VERSION

    seed_commitment = hashlib.sha256(
        f"{task_set.generator_version}:{task_set.seed_base}:{','.join(task_set.families)}".encode()
    ).hexdigest()
    return BenchmarkManifest(
        benchmark_manifest_id=f"bm-{seed_commitment[:12]}",
        benchmark_class=benchmark_class,
        generator_version=task_set.generator_version,
        kernel_version=KERNEL_VERSION,
        task_families=tuple(task_set.families),
        seed_commitment=seed_commitment,
        family_holdouts=tuple(holdouts),
        integrity_policy={
            "candidate_network_access": False,
            "candidate_filesystem": "ephemeral scratch only",
            "hidden_assets_readable_by_candidate": False,
            "canary_checked": True,
        },
    )
