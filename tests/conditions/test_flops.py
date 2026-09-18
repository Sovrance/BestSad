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


# --- device-seconds, the common currency (ADR-0023) ---------------------------------------------


def _calibrated(**overrides):
    from bestsad.conditions import DeviceSecondsPolicy

    rates = dict(
        hardware="1x NVIDIA H100 80GB SXM, vLLM 0.x (test)",
        seconds_per_input_token=1e-5, seconds_per_output_token=1e-3,
        seconds_per_search_node=2e-6, seconds_per_kernel_step=1e-7,
        seconds_per_verifier_step=1e-7, seconds_per_evolution_node=2e-6,
        flops_per_device_second=2e14,
    )
    rates.update(overrides)
    return DeviceSecondsPolicy(**rates)


def test_the_default_currency_is_uncalibrated_and_refuses_to_convert():
    from bestsad.conditions import DEFAULT_CURRENCY

    assert not DEFAULT_CURRENCY.calibrated
    record = DEFAULT_CURRENCY.to_record()
    assert record["policy_id"] == "device-seconds-1.0.0"
    assert record["hardware"] == "unpinned" and record["calibrated"] is False
    assert "seconds_per_output_token" in record["missing_rates"]
    with pytest.raises(ValueError, match="not calibrated"):
        DEFAULT_CURRENCY.device_seconds(ComputeLedger("r", "A", 1, model_output_tokens=1))


def test_a_missing_rate_only_matters_for_a_quantity_the_ledger_spent():
    policy = _calibrated(seconds_per_evolution_node=None)
    assert not policy.calibrated
    search_only = ComputeLedger("r", "A", 1, model_input_tokens=100, model_output_tokens=10)
    assert policy.device_seconds(search_only) == pytest.approx(100 * 1e-5 + 10 * 1e-3)
    with pytest.raises(ValueError, match="seconds_per_evolution_node"):
        policy.device_seconds(ComputeLedger("r", "I", 1, evolution_nodes=5))


def test_an_enumerator_and_a_model_are_priced_in_the_same_unit():
    policy = _calibrated()
    enumerator = ComputeLedger("r", "A", 1, search_nodes=1_000_000, kernel_steps=5_000_000)
    model = ComputeLedger("r", "A", 1, model_input_tokens=200_000, model_output_tokens=2_000)
    assert policy.device_seconds(enumerator) == pytest.approx(2.0 + 0.5)
    assert policy.device_seconds(model) == pytest.approx(2.0 + 2.0)
    assert policy.components(output_tokens=1_000) == pytest.approx(1.0)
    assert policy.flops_estimate(2.5) == pytest.approx(5e14)
    assert _calibrated(flops_per_device_second=None).flops_estimate(1.0) is None


def test_pass_at_c_in_device_seconds_counts_only_accounted_solves():
    attempts = [
        TaskAttempt("t1", True, 10.0, 5.0, device_seconds_spent=3.0, device_seconds_at_solve=1.0),
        TaskAttempt("t2", True, 10.0, 5.0, device_seconds_spent=3.0, device_seconds_at_solve=2.5),
        TaskAttempt("t3", False, 10.0, None, device_seconds_spent=3.0),
        # Solved, but from an uncalibrated run: no device-second figure, so not solved at any C.
        TaskAttempt("t4", True, 10.0, 5.0),
    ]
    from bestsad.conditions import solve_rate_at_fixed_device_seconds

    assert solve_rate_at_fixed_device_seconds(attempts, 2.0) == pytest.approx(0.25)
    assert solve_rate_at_fixed_device_seconds(attempts, 3.0) == pytest.approx(0.5)
    assert solve_rate_at_fixed_device_seconds([], 1.0) == 0.0
    assert attempts[3].to_record()["device_seconds_at_solve"] is None
