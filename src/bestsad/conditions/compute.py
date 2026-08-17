"""Compute ledger and the matching policy (spec §26.4, §26.6).

"Matched compute" means matched **total experimental compute** — the sum of model inference,
search, compilation, execution and verification. Genome-evolution compute counts against the
condition that produced the genome, and condition I exists to spend exactly that amount on the
baseline instead.

The accounting policy is versioned and hashed into every run manifest. Changing the weights
changes what "matched" means, so it is not a tuning knob.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

ACCOUNTING_POLICY_ID = "acct-1.0.0"

#: Weights converting each metered quantity into the common compute unit.
#:
#: For this instrument the natural unit is the search node, and everything else is expressed
#: relative to it by measured cost. They are *declared*, not discovered, and reported with every
#: result: a reader who disagrees with the weights can recompute from the per-component
#: quantities, which are published alongside the totals.
WEIGHTS: dict[str, float] = {
    "search_nodes": 1.0,
    "kernel_steps": 0.02,
    "model_input_tokens": 0.0,   # zero for the enumerative synthesizer; non-zero for an LLM
    "model_output_tokens": 0.0,
    "evolution_nodes": 1.0,      # evolution compute is search compute, charged to its owner
    "verifier_steps": 0.02,
}


@dataclass(slots=True)
class ComputeLedger:
    """One ledger entry per (condition, seed) — `schemas/compute_ledger.schema.json`."""

    run_id: str
    condition_id: str
    seed: int
    model_identity_hash: str = ""
    accelerator_type: str = "cpu"

    search_nodes: int = 0
    kernel_steps: int = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    evolution_nodes: int = 0
    verifier_steps: int = 0
    candidate_evaluations: int = 0
    wall_clock_s: float = 0.0
    compile_time_s: float = 0.0
    execution_time_s: float = 0.0
    verifier_time_s: float = 0.0

    best_of_n: int = 1
    candidates_evaluated: int = 0

    def add(self, **quantities) -> None:
        for key, value in quantities.items():
            if not hasattr(self, key):
                raise KeyError(f"{key} is not a metered quantity")
            setattr(self, key, getattr(self, key) + value)

    @property
    def total_experimental_compute(self) -> float:
        return sum(
            WEIGHTS[key] * getattr(self, key)
            for key in WEIGHTS
        )

    def to_record(self, *, compression_ratio: float, capability_delta: float) -> dict:
        """Serialize to the compute-ledger schema.

        `compression_ratio` and `capability_delta` are required together: spec §21.6 makes
        emitting one without the other a protocol violation, and the schema enforces the pair,
        so the only way to record a result is to record both.
        """
        return {
            "run_id": self.run_id,
            "condition_id": self.condition_id,
            "seed": self.seed,
            "model_identity_hash": self.model_identity_hash,
            "accelerator_type": self.accelerator_type,
            "components": {
                "model_input_tokens": self.model_input_tokens,
                "model_output_tokens": self.model_output_tokens,
                "search_compute": float(self.search_nodes),
                "evolution_compute": float(self.evolution_nodes),
                "compile_time_s": self.compile_time_s,
                "execution_time_s": self.execution_time_s,
                "verifier_time_s": self.verifier_time_s,
                "candidate_evaluations": self.candidate_evaluations,
                "wall_clock_s": self.wall_clock_s,
            },
            "totals": {
                "total_experimental_compute": self.total_experimental_compute,
                "accounting_policy_id": ACCOUNTING_POLICY_ID,
            },
            "paired_outcomes": {
                "compression_ratio": compression_ratio,
                "capability_delta": capability_delta,
            },
            "best_of_n_disclosure": {
                "n": self.best_of_n,
                "candidates_evaluated": self.candidates_evaluated,
            },
        }


class ComputeMatchError(Exception):
    """Compute matching failed its reconciliation check."""


def reconcile_search_only(
    *,
    baseline: ComputeLedger,
    treatment: ComputeLedger,
    search_only: ComputeLedger,
    tolerance: float = 0.05,
) -> dict:
    """Check condition I's defining identity (M5 acceptance).

        compute(I) == compute(A) + compute(evolution in D)

    within a stated tolerance. If this does not hold, condition I is not the control it claims
    to be, and any capability claim resting on it is void — so the reconciliation result is
    reported, not merely asserted.
    """
    expected = baseline.total_experimental_compute + treatment.evolution_nodes * WEIGHTS[
        "evolution_nodes"
    ]
    actual = search_only.total_experimental_compute
    denominator = max(expected, 1.0)
    residual = abs(actual - expected) / denominator
    return {
        "expected": expected,
        "actual": actual,
        "relative_residual": residual,
        "tolerance": tolerance,
        "reconciled": residual <= tolerance,
    }


def matched_budget(baseline_nodes: int, evolution_nodes: int) -> int:
    """The node budget condition I must be given: the baseline's plus D's evolution spend."""
    return int(baseline_nodes + evolution_nodes)
