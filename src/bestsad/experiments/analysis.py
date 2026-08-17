"""Analysis and report assembly for EXP-001 (spec §26, §40, §42, §44).

Everything that could turn into an overclaim passes through `ReportGate`. The analysis produces
evidence; the gate decides what may be said about it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..conditions import REQUIRED_CONTROLS
from ..mdl import PairedOutcome, compression_ratio
from ..stats import (
    ClaimRequest,
    Preregistration,
    ReportGate,
    ReportRefused,
    benjamini_hochberg,
    bootstrap_difference_ci,
    mean,
    non_inferiority_test,
    welch_t_test,
)

#: Secondary endpoints, declared here and mirrored into the pre-registration's family. Chosen in
#: advance; spec §26.7 requires the comparison family to be declared rather than picked later.
SECONDARY_FAMILY: tuple[str, ...] = (
    "raw_verified_solve_rate",
    "in_family_ood_rate",
    "adversarial_rate",
    "search_nodes",
    "generation_tokens",
    "language_description_length",
    "train_only_rate",
)


def _series(records: Sequence[dict], key: str) -> list[float]:
    return [float(r[key]) for r in records]


@dataclass(slots=True)
class ConditionSummary:
    condition_id: str
    n_seeds: int
    primary_mean: float
    primary_per_seed: list[float]
    verified_ood_mean: float
    verified_ood_per_seed: list[float]
    model_tokens: float
    search_nodes: float
    language_description_tokens: float
    adversarial_rate: float
    train_only_rate: float
    hardcoding_incidents: int

    def to_record(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "n_seeds": self.n_seeds,
            "primary_mean": self.primary_mean,
            "primary_per_seed": self.primary_per_seed,
            "verified_ood_mean": self.verified_ood_mean,
            "verified_ood_per_seed": self.verified_ood_per_seed,
            "model_tokens": self.model_tokens,
            "search_nodes": self.search_nodes,
            "language_description_tokens": self.language_description_tokens,
            "adversarial_rate": self.adversarial_rate,
            "train_only_rate": self.train_only_rate,
            "hardcoding_incidents": self.hardcoding_incidents,
        }


def summarize(condition_id: str, records: Sequence[dict]) -> ConditionSummary:
    return ConditionSummary(
        condition_id=condition_id,
        n_seeds=len(records),
        primary_mean=mean(_series(records, "primary")),
        primary_per_seed=_series(records, "primary"),
        verified_ood_mean=mean(_series(records, "verified_ood_rate")),
        verified_ood_per_seed=_series(records, "verified_ood_rate"),
        model_tokens=mean(_series(records, "model_tokens")),
        search_nodes=mean(_series(records, "search_nodes")),
        language_description_tokens=mean(_series(records, "language_description_tokens")),
        adversarial_rate=mean(_series(records, "verified_adversarial_rate")),
        train_only_rate=mean(_series(records, "train_only_rate")),
        hardcoding_incidents=sum(int(r["hardcoding_incidents"]) for r in records),
    )


@dataclass(slots=True)
class Analysis:
    summaries: dict[str, ConditionSummary] = field(default_factory=dict)
    primary_tests: dict[str, dict] = field(default_factory=dict)
    control_gates: dict[str, dict] = field(default_factory=dict)
    secondary: list[dict] = field(default_factory=list)
    paired_outcomes: dict[str, dict] = field(default_factory=dict)
    outcome_class: str = "null"
    notes: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "summaries": {k: v.to_record() for k, v in self.summaries.items()},
            "primary_tests": self.primary_tests,
            "control_gates": self.control_gates,
            "secondary_fdr": self.secondary,
            "paired_outcomes": self.paired_outcomes,
            "outcome_class": self.outcome_class,
            "notes": self.notes,
        }


def analyse(
    per_condition: Mapping[str, Sequence[dict]],
    *,
    minimum_interesting_effect: float = 0.05,
    non_inferiority_margin: float = 0.02,
    treatment_ids: Sequence[str] = ("D", "E"),
    seed: int = 0,
) -> Analysis:
    """Run the pre-registered analysis plan (pre-registration §8).

    Order matters and is fixed in advance: the control gates are evaluated **before** any claim,
    so a treatment that beats A but not I never reaches the point of being described as a
    capability result.
    """
    analysis = Analysis()
    for cid, records in per_condition.items():
        if records:
            analysis.summaries[cid] = summarize(cid, list(records))

    if "A" not in analysis.summaries:
        analysis.notes.append("no baseline condition A: nothing can be interpreted")
        return analysis

    baseline = analysis.summaries["A"].verified_ood_per_seed

    # -- primary: D and E versus A, at matched compute --
    for tid in treatment_ids:
        if tid not in analysis.summaries:
            continue
        treatment = analysis.summaries[tid].verified_ood_per_seed
        test = welch_t_test(treatment, baseline, label=f"{tid} vs A")
        interval = bootstrap_difference_ci(treatment, baseline, seed=seed)
        analysis.primary_tests[tid] = {
            "comparison": f"{tid} vs A",
            "effect": test.effect,
            "p_value": test.p_value,
            "ci": interval.to_record(),
            "meets_minimum_interesting_effect": test.effect >= minimum_interesting_effect,
        }

    # -- control gates: the treatment must beat F, H and I --
    best_treatment = max(
        (tid for tid in treatment_ids if tid in analysis.summaries),
        key=lambda tid: analysis.summaries[tid].verified_ood_mean,
        default=None,
    )
    if best_treatment is not None:
        treatment_values = analysis.summaries[best_treatment].verified_ood_per_seed
        for control in REQUIRED_CONTROLS:
            if control not in analysis.summaries:
                analysis.control_gates[control] = {
                    "present": False,
                    "beaten": False,
                    "detail": "condition not run",
                }
                continue
            control_values = analysis.summaries[control].verified_ood_per_seed
            test = welch_t_test(treatment_values, control_values,
                                label=f"{best_treatment} vs {control}")
            beaten = test.effect > 0 and test.p_value < 0.05
            analysis.control_gates[control] = {
                "present": True,
                "beaten": beaten,
                "effect": test.effect,
                "p_value": test.p_value,
                "ci": bootstrap_difference_ci(treatment_values, control_values,
                                              seed=seed).to_record(),
                "detail": (
                    f"{best_treatment} beats {control}" if beaten
                    else f"{control} matches or beats {best_treatment} — no capability claim"
                ),
            }

        # -- lower-bound controls, reported alongside --
        for control in ("B", "C"):
            if control in analysis.summaries:
                test = welch_t_test(
                    treatment_values, analysis.summaries[control].verified_ood_per_seed,
                    label=f"{best_treatment} vs {control}",
                )
                analysis.control_gates[control] = {
                    "present": True,
                    "beaten": test.effect > 0 and test.p_value < 0.05,
                    "effect": test.effect,
                    "p_value": test.p_value,
                    "detail": f"lower-bound control {control}",
                }

        # -- reference class G, reported alongside D/E vs A (spec §40.2) --
        if "G" in analysis.summaries:
            g_test = welch_t_test(
                analysis.summaries["G"].verified_ood_per_seed, treatment_values,
                label=f"G vs {best_treatment}",
            )
            analysis.control_gates["G"] = {
                "present": True,
                "beaten": None,
                "effect": g_test.effect,
                "p_value": g_test.p_value,
                "detail": (
                    "reference class: G's margin over the treatment, reported together with "
                    "the treatment's margin over A (spec §40.2)"
                ),
            }

        # -- paired compression/capability outcome (spec §21.6) --
        for tid in treatment_ids:
            if tid not in analysis.summaries:
                continue
            paired = PairedOutcome(
                compression_ratio=compression_ratio(
                    int(analysis.summaries["A"].model_tokens),
                    int(analysis.summaries[tid].model_tokens),
                ),
                capability_delta=(
                    analysis.summaries[tid].verified_ood_mean
                    - analysis.summaries["A"].verified_ood_mean
                ),
                non_inferiority_margin=non_inferiority_margin,
            )
            analysis.paired_outcomes[tid] = paired.to_record()

        # -- secondary family, FDR-controlled --
        p_values: dict[str, float] = {}
        secondary_map = {
            "in_family_ood_rate": "verified_in_family_rate",
            "adversarial_rate": "verified_adversarial_rate",
            "search_nodes": "search_nodes",
            "generation_tokens": "model_tokens",
            "language_description_length": "language_description_tokens",
            "train_only_rate": "train_only_rate",
        }
        for label, key in secondary_map.items():
            treatment_series = _series(list(per_condition[best_treatment]), key)
            baseline_series = _series(list(per_condition["A"]), key)
            p_values[label] = welch_t_test(treatment_series, baseline_series).p_value
        analysis.secondary = [
            {
                "endpoint": r.label,
                "p_value": r.p_value,
                "rank": r.rank,
                "critical_value": r.critical_value,
                "rejected_after_fdr": r.rejected,
            }
            for r in benjamini_hochberg(p_values, q=0.05)
        ]

        # -- declared outcome classification (pre-registration §12) --
        analysis.outcome_class = _classify(analysis, best_treatment, minimum_interesting_effect)

    return analysis


def _classify(analysis: Analysis, treatment: str, mie: float) -> str:
    """Apply the pre-registered outcome interpretations. Committed in advance so the result
    cannot be re-narrated afterwards (pre-registration §12)."""
    gates = analysis.control_gates
    unbeaten = [c for c in REQUIRED_CONTROLS
                if not gates.get(c, {}).get("present") or not gates.get(c, {}).get("beaten")]
    primary = analysis.primary_tests.get(treatment, {})
    paired = analysis.paired_outcomes.get(treatment, {})

    if unbeaten:
        return "h0_consistent"
    if primary.get("meets_minimum_interesting_effect") and primary.get("p_value", 1.0) < 0.05:
        return "positive"
    if paired.get("classification") == "efficiency_only":
        return "efficiency_only"
    return "null"


def certify(
    analysis: Analysis,
    preregistration: Preregistration | None,
    *,
    experiment_id: str,
    conditions_run: Sequence[str],
    concentration_passed: bool | None,
    powered: bool,
) -> dict:
    """Ask the gate what may be claimed. A refusal is recorded as the outcome, not raised past
    the caller: a refused claim *is* the finding."""
    kind = {
        "positive": "capability",
        "efficiency_only": "efficiency",
        "null": "null",
        "h0_consistent": "h0_consistent",
    }[analysis.outcome_class]

    treatment = "E" if "E" in analysis.paired_outcomes else "D"
    paired = analysis.paired_outcomes.get(treatment, {})
    request = ClaimRequest(
        experiment_id=experiment_id,
        claim_kind=kind,
        conditions_run=tuple(conditions_run),
        treatment_beats={
            c: bool(analysis.control_gates.get(c, {}).get("beaten")) for c in REQUIRED_CONTROLS
        },
        compression_ratio=paired.get("compression_ratio"),
        capability_delta=paired.get("capability_delta"),
        fdr_controlled=bool(analysis.secondary),
        concentration_test_passed=concentration_passed,
        powered=powered,
    )
    gate = ReportGate(preregistration)
    try:
        return gate.certify(request)
    except ReportRefused as refusal:
        return {
            "certified": False,
            "claim_kind": kind,
            "refusal": str(refusal),
            "claim_level": "E",
        }
