"""FLOP-denominated compute matching (roadmap §3; ADR-0022).

The instrument's native unit is the search node; a language model's is the token. Neither is
commensurable with the other, so a model arm is matched in FLOPs — declared per-unit costs,
published with every result — and its solve rate is reported at a fixed FLOP budget rather than
at whatever it happened to spend.
"""

from __future__ import annotations

import pytest

from bestsad.conditions import (
    DEFAULT_FLOPS_POLICY,
    ComputeLedger,
    FlopsPolicy,
    TaskAttempt,
    matched_flops,
    pass_at_c_curve,
    solve_rate_at_fixed_flops,
)


def test_model_tokens_cost_two_flops_per_parameter_each():
    policy = FlopsPolicy()
    ledger = ComputeLedger("r", "A", 1, model_input_tokens=100, model_output_tokens=50)
    assert policy.flops(ledger, parameter_count=7_000_000_000) == pytest.approx(
        2.0 * 7e9 * 150
    )


def test_cpu_side_quantities_are_charged_at_the_declared_rates():
    policy = FlopsPolicy(search_node_flops=10.0, kernel_step_flops=1.0, verifier_step_flops=1.0,
                         evolution_node_flops=10.0)
    ledger = ComputeLedger("r", "I", 1, search_nodes=5, kernel_steps=7, verifier_steps=3,
                           evolution_nodes=2)
    assert policy.flops(ledger, parameter_count=0) == 50 + 7 + 3 + 20


def test_the_policy_is_published_with_its_id_and_calibration_note():
    record = DEFAULT_FLOPS_POLICY.to_record()
    assert record["policy_id"] == "flops-1.0.0"
    assert "Kaplan" in record["calibration"]
    assert record["forward_flops_per_parameter_per_token"] == 2.0


def test_pass_at_c_counts_only_tasks_solved_within_the_budget():
    attempts = [
        TaskAttempt("t1", True, 10.0, 10.0),
        TaskAttempt("t2", True, 30.0, 30.0),
        TaskAttempt("t3", False, 40.0, None),
        TaskAttempt("t4", True, 5.0, 5.0),
    ]
    assert solve_rate_at_fixed_flops(attempts, 10.0) == 0.5
    assert solve_rate_at_fixed_flops(attempts, 30.0) == 0.75
    assert solve_rate_at_fixed_flops(attempts, 1.0) == 0.0
    assert solve_rate_at_fixed_flops([], 10.0) == 0.0
    curve = pass_at_c_curve(attempts, [1.0, 10.0, 30.0, 100.0])
    assert [p["solve_rate"] for p in curve] == [0.0, 0.5, 0.75, 0.75]


def test_matched_flops_reports_the_residual_per_arm():
    report = matched_flops({"A": 100.0, "I": 103.0, "D": 120.0}, tolerance=0.05)
    assert report.per_arm["I"]["matched"] and not report.per_arm["D"]["matched"]
    assert not report.matched
    assert report.per_arm["D"]["relative_residual"] == pytest.approx(0.2)
    assert report.to_record()["reference"] == "A"
    with pytest.raises(KeyError):
        matched_flops({"I": 1.0})
