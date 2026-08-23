"""M5 acceptance: the confound control plane (spec §40)."""

from __future__ import annotations

import pytest

from bestsad.conditions import (
    ComputeLedger,
    Condition,
    ConditionPlaneError,
    REQUIRED_CONTROLS,
    ScaffoldingMatcher,
    build_conditions,
    check_condition_f,
    matched_budget,
    reconcile_search_only,
    scaffolding_is_equalized,
)
from bestsad.genomes import Primitive
from bestsad.kernel import INT, KERNEL_VERSION, app, const_int, var


def _primitive(name: str, factor: int) -> Primitive:
    return Primitive(
        primitive_id=f"prim:{name}",
        params=("a",),
        expansion=app("mul", var("a"), const_int(factor)),
        input_types=(INT,),
        output_type=INT,
    )


def _plane(**overrides):
    base = dict(
        kernel_version=KERNEL_VERSION,
        random_primitives=[_primitive("r0", 5)],
        mdl_primitives=[_primitive("m0", 3)],
        utility_primitives=[_primitive("u0", 2)],
        expert_primitives=[_primitive("e0", 7)],
        baseline_node_budget=100_000,
        evolution_nodes=40_000,
    )
    base.update(overrides)
    return build_conditions(**base)


def test_all_nine_conditions_are_defined_with_their_declared_roles():
    plane = _plane()
    assert set(plane) == set("ABCDEFGHI")
    assert plane["A"].role == "reference"
    assert plane["D"].role == "treatment" and plane["E"].role == "treatment"
    assert plane["G"].role == "reference_class"
    assert {plane[c].role for c in "BC"} == {"lower_bound_control"}
    assert {plane[c].role for c in "FHI"} == {"confound_control"}


def test_each_confound_control_declares_the_confound_it_controls():
    plane = _plane()
    assert plane["F"].controls_confound == "C2_compression"
    assert plane["H"].controls_confound == "C3_scaffolding"
    assert plane["I"].controls_confound == "C1_compute"


def test_condition_f_provably_introduces_no_new_semantics():
    """M5 acceptance 3: F's primitive set is identical to A's under semantic hash."""
    plane = _plane()
    report = check_condition_f(plane["F"], plane["A"])
    assert report["identical_primitive_semantics"]
    assert report["projection_differs"], "F must differ from A in projection, or it is just A"


def test_a_condition_f_carrying_semantics_is_rejected():
    """If F were allowed new semantics it would be a second treatment, and the compression
    control would silently vanish."""
    plane = _plane()
    broken = Condition(
        condition_id="F",
        role="confound_control",
        controls_confound="C2_compression",
        genome=plane["D"].genome,  # carries utility primitives
        description="broken F",
    )
    with pytest.raises(ConditionPlaneError, match="introduces semantics"):
        check_condition_f(broken, plane["A"])


def test_condition_i_receives_the_baseline_budget_plus_evolution_compute():
    plane = _plane()
    assert plane["I"].node_budget == 100_000 + 40_000
    assert plane["I"].inherited_evolution_compute_from == "D"
    assert matched_budget(100_000, 40_000) == 140_000


def test_compute_meter_reconciles_condition_i():
    """M5 acceptance 1: compute(I) == compute(A) + compute(evolution in D) within tolerance."""
    baseline = ComputeLedger("run", "A", 0, search_nodes=100_000)
    treatment = ComputeLedger("run", "D", 0, search_nodes=100_000, evolution_nodes=40_000)
    search_only = ComputeLedger("run", "I", 0, search_nodes=140_000)

    result = reconcile_search_only(
        baseline=baseline, treatment=treatment, search_only=search_only
    )
    assert result["reconciled"]
    assert result["relative_residual"] < 0.001


def test_compute_reconciliation_fails_loudly_when_condition_i_is_underfunded():
    """An underfunded I is not the control it claims to be, and the reconciliation must say so
    rather than quietly passing."""
    baseline = ComputeLedger("run", "A", 0, search_nodes=100_000)
    treatment = ComputeLedger("run", "D", 0, search_nodes=100_000, evolution_nodes=40_000)
    starved = ComputeLedger("run", "I", 0, search_nodes=100_000)

    result = reconcile_search_only(baseline=baseline, treatment=treatment, search_only=starved)
    assert not result["reconciled"]
    assert result["relative_residual"] > 0.2


def test_ledger_refuses_to_emit_one_half_of_the_paired_outcome():
    """`to_record` requires both halves as keyword arguments, so there is no code path that
    produces one without the other (spec §21.6)."""
    ledger = ComputeLedger("run", "E", 0, search_nodes=10)
    with pytest.raises(TypeError):
        ledger.to_record(compression_ratio=1.5)  # type: ignore[call-arg]
    record = ledger.to_record(compression_ratio=1.5, capability_delta=0.02)
    assert set(record["paired_outcomes"]) == {"compression_ratio", "capability_delta"}


# --- scaffolding (condition H) ---------------------------------------------------------------


def test_scaffolding_is_equalized_and_the_delivered_budget_is_logged():
    """M5 acceptance 2: the matcher reports the residual difference in tokens per condition,
    and logs what was actually delivered rather than assuming equality."""
    matcher = ScaffoldingMatcher()
    report = matcher.equalize({"A": 1200, "D": 1310, "E": 1180, "F": 1195})
    assert scaffolding_is_equalized(report)
    assert report.target_tokens == 1310
    assert all(s.grammar_description_tokens == 1310 for s in report.delivered.values())
    # E is the furthest below target, so it is the disclosed worst case.
    assert report.residuals["E"].value == -130
    assert report.max_absolute_residual_tokens == 130


def test_scaffolding_pads_rather_than_truncates():
    """Truncating a longer grammar description would turn a scaffolding control into a
    capability handicap."""
    report = ScaffoldingMatcher().equalize({"A": 100, "D": 900})
    assert report.target_tokens == 900
    assert report.delivered["A"].grammar_description_tokens == 900


def test_scaffolding_residual_is_disclosed_in_words():
    """Spec §40.3: an undisclosed residual is a protocol violation, so the report carries the
    sentence rather than leaving it to the write-up."""
    report = ScaffoldingMatcher().equalize({"A": 1200, "E": 1180})
    disclosure = report.disclosure()
    assert "equalized to within 20 tokens" in disclosure
    assert "%" in disclosure


def test_required_controls_are_the_three_from_invariant_three():
    assert REQUIRED_CONTROLS == ("F", "H", "I")


def test_condition_i_spreads_inherited_evolution_compute_across_tasks():
    """`node_budget` is a per-task budget; inherited evolution compute is a total.

    Adding the total to every task hands condition I one full extra evolution budget per task,
    and the §26.6 identity compute(I) == compute(A) + compute(evolution in D) fails outright.
    The reconciliation check caught exactly this in the first full run, which is what it is for.
    """
    plane = _plane(baseline_node_budget=25_000, evolution_nodes=260_000)
    # Without spreading, I's per-task budget would be 285,000.
    assert plane["I"].node_budget == 25_000 + 260_000

    spread = build_conditions(
        kernel_version=KERNEL_VERSION,
        random_primitives=[], mdl_primitives=[], utility_primitives=[], expert_primitives=[],
        baseline_node_budget=25_000,
        evolution_nodes=260_000,
        tasks_per_seed=26,
    )
    assert spread["I"].node_budget == 25_000 + 10_000
    assert spread["I"].node_budget < plane["I"].node_budget
