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
    #: The same two quantities in the common currency of ADR-0023, filled only when the run's
    #: `DeviceSecondsPolicy` was calibrated; None otherwise, and never estimated.
    device_seconds_spent: float | None = None
    device_seconds_at_solve: float | None = None

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


# --- device-seconds: the common currency across an enumerator and a model (ADR-0023) ------------

CURRENCY_ID = "device-seconds-1.0.0"


@dataclass(frozen=True, slots=True)
class DeviceSecondsPolicy:
    """Compute as device-seconds on one pinned piece of hardware.

    There is no principled FLOP equivalence between an enumerator step and a decoded token: the
    2N-per-token figure is a model of a dense forward pass, and the CPU-side constants in
    `FlopsPolicy` are declared. What *is* commensurable is time on the same machine. ADR-0023
    therefore declares device-seconds on the pinned hardware as the common currency for an
    experiment with a model in the model role, reported alongside the FLOP estimate, and makes
    the conversion of condition I's kernel-step budget into that currency a pre-registered
    assumption rather than a silent one.

    Every rate here is **measured**, in the E0 pilot on the pinned hardware, or it is `None`.
    An uncalibrated policy refuses to convert rather than guess, and its record says which
    rates are missing. Changing a rate changes what "matched" means, so the policy is versioned
    and the rates travel with every result that used them.
    """

    policy_id: str = CURRENCY_ID
    #: The pinned hardware every rate was measured on, e.g. "1x NVIDIA H100 80GB SXM, vLLM
    #: <version>". Rates from one machine are not the currency on another.
    hardware: str = "unpinned"
    #: Seconds per unit on `hardware`, from the pilot. Input (prefill) and output (decode)
    #: tokens are priced separately: prefill is batched and cheap, decode is sequential.
    seconds_per_input_token: float | None = None
    seconds_per_output_token: float | None = None
    seconds_per_search_node: float | None = None
    seconds_per_kernel_step: float | None = None
    seconds_per_verifier_step: float | None = None
    seconds_per_evolution_node: float | None = None
    #: For the FLOP estimate reported alongside: the sustained dense-bf16 throughput the pilot
    #: observed (tokens per second times FLOPs per token), not a vendor peak.
    flops_per_device_second: float | None = None
    calibration: str = (
        "rates are pilot-measured on the pinned hardware or absent; an absent rate makes the "
        "policy refuse to convert (ADR-0023)"
    )

    _RATES = (
        ("seconds_per_input_token", "model_input_tokens"),
        ("seconds_per_output_token", "model_output_tokens"),
        ("seconds_per_search_node", "search_nodes"),
        ("seconds_per_kernel_step", "kernel_steps"),
        ("seconds_per_verifier_step", "verifier_steps"),
        ("seconds_per_evolution_node", "evolution_nodes"),
    )

    def missing_rates(self, ledger: ComputeLedger | None = None) -> list[str]:
        """Rates the policy needs and does not have. With a ledger, only the rates for
        quantities the ledger actually spent count as needed."""
        missing = []
        for rate, quantity in self._RATES:
            if getattr(self, rate) is None and (
                ledger is None or getattr(ledger, quantity) > 0
            ):
                missing.append(rate)
        return missing

    @property
    def calibrated(self) -> bool:
        return self.hardware != "unpinned" and not self.missing_rates()

    def device_seconds(self, ledger: ComputeLedger) -> float:
        """Device-seconds for one `(condition, seed)` ledger entry, or a refusal."""
        missing = self.missing_rates(ledger)
        if missing or self.hardware == "unpinned":
            raise ValueError(
                "device-seconds policy is not calibrated for this ledger: "
                + (f"hardware unpinned; " if self.hardware == "unpinned" else "")
                + f"unmeasured rates {missing}"
            )
        return sum(
            float(getattr(self, rate)) * getattr(ledger, quantity)
            for rate, quantity in self._RATES
            if getattr(ledger, quantity) > 0
        )

    def components(
        self, *, input_tokens: int = 0, output_tokens: int = 0, search_nodes: int = 0,
        kernel_steps: int = 0, verifier_steps: int = 0, evolution_nodes: int = 0,
    ) -> float:
        """Device-seconds for a bundle of component quantities (one task attempt)."""
        return self.device_seconds(ComputeLedger(
            "-", "-", 0, model_input_tokens=input_tokens, model_output_tokens=output_tokens,
            search_nodes=search_nodes, kernel_steps=kernel_steps, verifier_steps=verifier_steps,
            evolution_nodes=evolution_nodes,
        ))

    def flops_estimate(self, device_seconds: float) -> float | None:
        """The FLOP figure reported *alongside* a device-second budget, never instead of it."""
        if self.flops_per_device_second is None:
            return None
        return device_seconds * self.flops_per_device_second

    def to_record(self) -> dict:
        data = asdict(self)
        data["calibrated"] = self.calibrated
        data["missing_rates"] = self.missing_rates()
        return data


DEFAULT_CURRENCY = DeviceSecondsPolicy()


def solve_rate_at_fixed_device_seconds(
    attempts: Sequence["TaskAttempt"], budget_device_seconds: float
) -> float:
    """pass@C with C in device-seconds: the fraction of tasks solved within the budget each.

    Attempts that carry no device-second accounting (an uncalibrated run) count as unsolved
    at every budget, so an uncalibrated run cannot report a device-second solve rate by
    accident.
    """
    if not attempts:
        return 0.0
    solved = sum(
        1 for a in attempts
        if a.solved and a.device_seconds_at_solve is not None
        and a.device_seconds_at_solve <= budget_device_seconds
    )
    return solved / len(attempts)
