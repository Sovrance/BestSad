"""Compute matching in FLOPs for model arms (spec §26.6; roadmap §3; ADR-0022).

`compute.py` accounts in search nodes, which is the natural unit for an enumerative searcher
and a meaningless one for a language model: a sampled token and an expanded node are not
commensurable, and the C1 control (condition I) cannot be reconciled across the two. The
roadmap's remedy, following OSCA (arXiv 2410.22480), is to fix a compute budget **C in FLOPs**
and report **solve rate at fixed FLOPs** — matching total generator-plus-verifier FLOPs across
arms rather than sample counts, because "sample budget is not a good proxy for compute budget"
when arms differ in model size or search type.

The per-unit costs here are **declared, not discovered**, in the same discipline as
`compute.WEIGHTS`: they are published with every result together with the per-component
quantities, so a reader who disagrees with a constant can recompute from the components. The
one physically grounded constant is the forward-pass estimate of ~2 FLOPs per parameter per
token (Kaplan et al. 2020, "Scaling Laws for Neural Language Models", §2.1); the CPU-side
constants are planning values to be replaced by measured figures, and `calibration` says so on
the record. Changing any constant changes what "matched" means, so the policy is versioned and
its id travels with the ledger entry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from .compute import ComputeLedger

POLICY_ID = "flops-1.0.0"


@dataclass(frozen=True, slots=True)
class FlopsPolicy:
    """Per-unit FLOP costs. Every field is reported with every result."""

    policy_id: str = POLICY_ID
    #: Kaplan et al. 2020: a forward pass costs ~2N FLOPs per token for an N-parameter model.
    #: Charged to input (prefill) and output (decode) tokens alike.
    forward_flops_per_parameter_per_token: float = 2.0
    #: CPU-side planning constants. One enumeration node is a typechecked term construction
    #: plus an observational-signature probe; one kernel step is one K0 reduction.
    search_node_flops: float = 2.0e5
    kernel_step_flops: float = 2.0e3
    verifier_step_flops: float = 2.0e3
    evolution_node_flops: float = 2.0e5
    calibration: str = (
        "declared planning constants; the model-token cost follows Kaplan et al. 2020 and the "
        "CPU-side costs are order-of-magnitude estimates to be replaced by measured figures "
        "recorded in the compute ledger (spec §43 cost note)"
    )

    def model_token_flops(self, parameter_count: int) -> float:
        return self.forward_flops_per_parameter_per_token * float(parameter_count)

    def flops(self, ledger: ComputeLedger, *, parameter_count: int) -> float:
        """Total generator-plus-verifier FLOPs for one `(condition, seed)` ledger entry."""
        per_token = self.model_token_flops(parameter_count)
        return (
            per_token * (ledger.model_input_tokens + ledger.model_output_tokens)
            + self.search_node_flops * ledger.search_nodes
            + self.kernel_step_flops * ledger.kernel_steps
            + self.verifier_step_flops * ledger.verifier_steps
            + self.evolution_node_flops * ledger.evolution_nodes
        )

    def to_record(self) -> dict:
        return asdict(self)


DEFAULT_POLICY = FlopsPolicy()


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    """One task's outcome with the compute it took, for pass@C at a fixed budget.

    `flops_at_solve` is the cumulative FLOPs spent on the task up to and including the sample
    that solved it, or None when it was never solved. A task solved after the budget is *not*
    solved at that budget — which is the whole point of reporting at fixed C rather than at
    whatever each arm happened to spend.
    """

    task_id: str
    solved: bool
    flops_spent: float
    flops_at_solve: float | None = None

    def solved_within(self, budget_flops: float) -> bool:
        return self.solved and self.flops_at_solve is not None and self.flops_at_solve <= budget_flops

    def to_record(self) -> dict:
        return asdict(self)


def solve_rate_at_fixed_flops(attempts: Sequence[TaskAttempt], budget_flops: float) -> float:
    """pass@C: the fraction of tasks solved within `budget_flops` each."""
    if not attempts:
        return 0.0
    return sum(1 for a in attempts if a.solved_within(budget_flops)) / len(attempts)


def pass_at_c_curve(
    attempts: Sequence[TaskAttempt], budgets: Sequence[float]
) -> list[dict]:
    """Per-compute curve, not a single point (pre-registration analysis plan item 8)."""
    return [
        {"budget_flops": float(c), "solve_rate": solve_rate_at_fixed_flops(attempts, c)}
        for c in budgets
    ]


@dataclass(slots=True)
class MatchReport:
    reference: str
    reference_flops: float
    per_arm: dict = field(default_factory=dict)
    tolerance: float = 0.05

    @property
    def matched(self) -> bool:
        return all(entry["matched"] for entry in self.per_arm.values())

    def to_record(self) -> dict:
        return {
            "reference": self.reference,
            "reference_flops": self.reference_flops,
            "tolerance": self.tolerance,
            "matched": self.matched,
            "per_arm": dict(self.per_arm),
        }


def matched_flops(
    arms: Mapping[str, float], *, reference: str = "A", tolerance: float = 0.05
) -> MatchReport:
    """Check that every arm spent the reference arm's FLOPs to within a tolerance.

    This is the FLOP-denominated form of `compute.reconcile_search_only`: reported, never merely
    asserted, because an arm that silently spent more compute than the baseline is not a
    representation comparison but a compute comparison wearing its clothes.
    """
    if reference not in arms:
        raise KeyError(f"reference arm {reference!r} has no FLOP total")
    ref = float(arms[reference])
    report = MatchReport(reference=reference, reference_flops=ref, tolerance=tolerance)
    for arm, spent in arms.items():
        residual = abs(float(spent) - ref) / max(ref, 1.0)
        report.per_arm[arm] = {
            "flops": float(spent),
            "relative_residual": residual,
            "matched": residual <= tolerance,
        }
    return report
