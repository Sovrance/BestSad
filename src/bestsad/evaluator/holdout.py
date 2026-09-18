"""Sealed hidden tests, transcript leak detection, and the twin-gap probe (roadmap §6).

Putting a language model in the loop adds failure modes the enumerative searcher did not have.
The 2025–2026 reward-hacking record is one of models editing tests, patching scorers and
hardcoding expected outputs; the analogue here is a *feedback loop* that shows the model the
very inputs it is scored on. Three defences, each small:

* **Sealed tier.** `HoldoutPolicy.split` partitions a task's hidden inputs into a *feedback*
  tier — the only hidden inputs any repair or scaffolding variant may ever surface to a model
  — and a *sealed* tier that no candidate-visible surface may carry. The split is a pure
  function of the task id, so it is the same in every condition and every process. Correctness
  is unchanged: a task is solved when **every** hidden input agrees (`contract.py`, invariant
  1); the tiers are a diagnostic, not a relaxation.
* **Transcript leak check.** `transcript_leak_findings` scans everything the model saw for the
  canary and for sealed inputs. The candidate sandbox stops a *process* reaching the hidden
  assets; this stops a *prompt* carrying them, which the sandbox cannot see.
* **Twin-gap probe.** `twin_gap` compares pass rates on the feedback tier against the sealed
  tier. A model that has seen (or memorised) what it is scored on scores higher on the tier it
  could see; the gap is the standing public-versus-held-out probe the roadmap asks for, and it
  is reported under confound C4 with a declared flag threshold.

`contamination_probe` is the fourth item and needs a model: it asks the backend to continue a
prefix of the canary and flags a completion that reproduces it. The canary has never been
published, so a model that can complete it was trained on this repository's evaluator assets.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

from ..kernel.values import render
from ..tasks.families import Task
from ..tasks.generator import CANARY

POLICY_ID = "holdout-1.0.0"
#: The roadmap's figure: "reserve ~30% of tests, capped, as inaccessible holdout" (EvilGenie).
DEFAULT_SEALED_FRACTION = 0.3
#: A feedback-minus-sealed pass-rate gap at or above this is flagged. Declared here so the
#: threshold is fixed before any run reads it.
DEFAULT_GAP_THRESHOLD = 0.10
#: Renderings shorter than this are too common to be evidence of a leak (`3`, `[]`).
MIN_LEAK_RENDER_LENGTH = 6


@dataclass(frozen=True, slots=True)
class HoldoutPolicy:
    policy_id: str = POLICY_ID
    sealed_fraction: float = DEFAULT_SEALED_FRACTION
    gap_threshold: float = DEFAULT_GAP_THRESHOLD

    def __post_init__(self) -> None:
        if not 0.0 < self.sealed_fraction < 1.0:
            raise ValueError("sealed_fraction must lie strictly between 0 and 1")

    def sealed_indices(self, task: Task) -> frozenset[int]:
        """Which positions of `task.hidden_inputs` are sealed. Deterministic in the task id and
        this policy, and never empty when there are at least two hidden inputs."""
        n = len(task.hidden_inputs)
        if n < 2:
            return frozenset()
        count = max(1, math.ceil(n * self.sealed_fraction))
        rng = random.Random(f"{self.policy_id}:{self.sealed_fraction}:{task.task_id}")
        order = list(range(n))
        rng.shuffle(order)
        return frozenset(order[:count])

    def split(self, task: Task) -> tuple[tuple[tuple[Any, ...], ...], tuple[tuple[Any, ...], ...]]:
        """`(feedback_tier, sealed_tier)` in the task's own input order."""
        sealed = self.sealed_indices(task)
        feedback = tuple(inp for i, inp in enumerate(task.hidden_inputs) if i not in sealed)
        held = tuple(inp for i, inp in enumerate(task.hidden_inputs) if i in sealed)
        return feedback, held

    def to_record(self) -> dict:
        return asdict(self)


DEFAULT_HOLDOUT = HoldoutPolicy()


def render_inputs(inputs: Sequence[Any]) -> str:
    return ", ".join(render(v) for v in inputs)


def transcript_leak_findings(
    text: str,
    tasks: Sequence[Task],
    *,
    policy: HoldoutPolicy = DEFAULT_HOLDOUT,
    surface: str = "transcript",
) -> list[dict]:
    """Integrity findings for a candidate-visible surface (spec §40.1, C4).

    Fatal: the canary, or a sealed hidden input, appears verbatim. The check is by rendering,
    so it catches an input pasted into a prompt or echoed by the model; it cannot catch a
    paraphrase, and does not claim to.
    """
    findings: list[dict] = []
    if CANARY in text:
        findings.append({"kind": "canary_leak", "detail": f"{surface} contains the canary",
                         "fatal": True})
    # A sealed input that happens to coincide with some task's *visible* example is legitimately
    # on the surface; flagging it would abort an honest run on a sampling coincidence.
    visible = {render_inputs(inputs) for task in tasks for inputs in task.train_inputs}
    for task in tasks:
        _, sealed = policy.split(task)
        for inputs in sealed:
            rendered = render_inputs(inputs)
            if rendered in visible:
                continue
            if len(rendered) >= MIN_LEAK_RENDER_LENGTH and rendered in text:
                findings.append({
                    "kind": "sealed_input_leak",
                    "detail": f"{surface} contains sealed hidden input {rendered!r} of "
                              f"task {task.task_id}",
                    "fatal": True,
                })
    return findings


@dataclass(frozen=True, slots=True)
class TwinGap:
    feedback_tier_rate: float
    sealed_tier_rate: float
    gap: float
    threshold: float
    flagged: bool
    tasks: int

    def to_record(self) -> dict:
        return asdict(self)


def twin_gap(
    feedback_passed: int, feedback_total: int, sealed_passed: int, sealed_total: int,
    *, tasks: int, policy: HoldoutPolicy = DEFAULT_HOLDOUT,
) -> TwinGap:
    """The public-versus-held-out probe, over aggregated per-input counts."""
    fb = feedback_passed / feedback_total if feedback_total else 0.0
    sd = sealed_passed / sealed_total if sealed_total else 0.0
    gap = fb - sd
    return TwinGap(fb, sd, gap, policy.gap_threshold, gap >= policy.gap_threshold, tasks)


def contamination_probe(
    complete: Callable[[str], str], *, prefix_length: int = 15
) -> dict:
    """Ask a model to continue the canary's prefix. A completion carrying the rest of the canary
    means the model saw this repository's hidden-evaluator assets in training (DyePack-style
    detection, roadmap §6), and the run's C4 residual must say so."""
    prefix = CANARY[:prefix_length]
    suffix = CANARY[prefix_length:]
    completion = complete(f"Continue this identifier exactly: {prefix}")
    reproduced = suffix in completion or CANARY in completion
    return {
        "probe": "canary_completion",
        "prefix_length": prefix_length,
        "reproduced_canary": reproduced,
        "fatal": reproduced,
    }
