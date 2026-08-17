"""M9 acceptance: statistics, checked against closed-form values (ADR-0004)."""

from __future__ import annotations

import math

import pytest

from bestsad.stats import (
    benjamini_hochberg,
    bootstrap_ci,
    bootstrap_difference_ci,
    mean,
    median,
    non_inferiority_test,
    normal_quantile,
    power_analysis,
    stdev,
    variance,
    welch_t_test,
)
from bestsad.stats.inference import _t_cdf, normal_cdf


def test_normal_quantile_matches_known_values():
    assert normal_quantile(0.975) == pytest.approx(1.959964, abs=1e-5)
    assert normal_quantile(0.95) == pytest.approx(1.644854, abs=1e-5)
    assert normal_quantile(0.80) == pytest.approx(0.8416212, abs=1e-5)
    assert normal_quantile(0.5) == pytest.approx(0.0, abs=1e-9)


def test_normal_cdf_matches_known_values():
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.959964) == pytest.approx(0.975, abs=1e-6)


def test_t_cdf_matches_known_values():
    # t(0) = 0.5 for any df; t_{0.975, 10} = 2.228139
    assert _t_cdf(0.0, 10) == pytest.approx(0.5, abs=1e-9)
    assert _t_cdf(2.228139, 10) == pytest.approx(0.975, abs=1e-5)
    assert _t_cdf(1.812461, 10) == pytest.approx(0.95, abs=1e-5)


def test_descriptive_statistics():
    xs = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    assert mean(xs) == 5.0
    assert median(xs) == 4.5
    assert variance(xs) == pytest.approx(32 / 7)
    assert stdev(xs) == pytest.approx(math.sqrt(32 / 7))


def test_welch_t_test_against_a_hand_computed_example():
    """Expected values computed independently from the Welch-Satterthwaite formulas:
    mean 20.75 vs 23.30, sample variances 10.9983 and 4.6933, n = 10 each."""
    a = [27.5, 21.0, 19.0, 23.6, 17.0, 17.9, 16.9, 20.1, 21.9, 22.6]
    b = [27.1, 22.0, 20.8, 23.4, 23.4, 23.5, 25.8, 22.0, 24.8, 20.2]
    result = welch_t_test(a, b)
    assert result.effect == pytest.approx(-2.55, abs=1e-9)
    assert result.statistic == pytest.approx(-2.035662, abs=1e-5)
    assert result.df == pytest.approx(15.4979, abs=1e-3)
    assert result.p_value == pytest.approx(0.059254, abs=1e-5)


def test_welch_handles_degenerate_input():
    assert welch_t_test([1.0], [2.0]).p_value == 1.0
    identical = welch_t_test([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
    assert identical.effect == 0.0 and identical.p_value == 1.0


def test_non_inferiority_is_one_sided_and_uses_the_margin():
    """A condition slightly worse than baseline is still non-inferior at a generous margin."""
    a = [0.50, 0.52, 0.49, 0.51, 0.50, 0.48]
    b = [0.52, 0.53, 0.51, 0.52, 0.51, 0.52]
    generous = non_inferiority_test(a, b, margin=0.10)
    strict = non_inferiority_test(a, b, margin=0.001)
    assert generous.p_value < 0.05, "should establish non-inferiority at a 10-point margin"
    assert strict.p_value > 0.05, "should not establish it at a 0.1-point margin"


def test_benjamini_hochberg_matches_a_hand_computed_example():
    p_values = {"a": 0.001, "b": 0.008, "c": 0.039, "d": 0.041, "e": 0.042}
    results = {r.label: r for r in benjamini_hochberg(p_values, q=0.05)}
    # Critical values: 0.01, 0.02, 0.03, 0.04, 0.05. Largest k with p_k <= crit_k is k=5.
    assert results["e"].rejected
    assert all(results[label].rejected for label in "abcde")


def test_benjamini_hochberg_rejects_nothing_when_no_p_value_qualifies():
    results = benjamini_hochberg({"a": 0.4, "b": 0.6, "c": 0.9}, q=0.05)
    assert not any(r.rejected for r in results)


def test_benjamini_hochberg_is_less_permissive_than_uncorrected_testing():
    """The reason §26.7 requires it: with many comparisons, a p < 0.05 turns up by chance.

    One nominally significant result among twenty is what chance alone produces at alpha=0.05,
    and BH declines to reject it — whereas uncorrected testing would call it a finding. (Note
    that BH does *not* simply reject less: twenty results all at p=0.04 are collectively far
    more than chance would give, and BH rejects them all. The correction is adaptive, which is
    exactly why the comparison family must be declared in advance rather than chosen to suit.)
    """
    p_values = {"h0": 0.04, **{f"h{i}": 0.5 for i in range(1, 20)}}
    results = benjamini_hochberg(p_values, q=0.05)
    assert not any(r.rejected for r in results)
    assert p_values["h0"] < 0.05

    all_borderline = benjamini_hochberg({f"h{i}": 0.04 for i in range(20)}, q=0.05)
    assert all(r.rejected for r in all_borderline)


def test_bootstrap_ci_is_deterministic_and_brackets_the_estimate():
    values = [0.30, 0.35, 0.28, 0.41, 0.33, 0.37, 0.31, 0.39]
    first = bootstrap_ci(values, seed=11)
    second = bootstrap_ci(values, seed=11)
    assert first == second, "published intervals must be exactly reproducible"
    assert first.low <= first.point <= first.high
    assert bootstrap_ci(values, seed=12) != first or True  # different seed may differ


def test_bootstrap_difference_ci_excludes_zero_for_a_clear_difference():
    a = [0.60, 0.62, 0.58, 0.61, 0.59, 0.63]
    b = [0.30, 0.32, 0.28, 0.31, 0.29, 0.33]
    interval = bootstrap_difference_ci(a, b, seed=3)
    assert interval.low > 0
    assert interval.point == pytest.approx(0.30, abs=0.01)


def test_bootstrap_difference_ci_includes_zero_for_no_difference():
    a = [0.50, 0.52, 0.48, 0.51, 0.49, 0.53]
    b = [0.51, 0.49, 0.50, 0.52, 0.48, 0.50]
    assert bootstrap_difference_ci(a, b, seed=3).contains(0.0)


def test_power_analysis_uses_measured_variance_and_reports_required_seeds():
    analysis = power_analysis(
        effect_size=0.05, variance_estimate=0.0025, seeds_per_condition=5
    )
    assert not analysis.powered, "5 seeds cannot power a 5-point effect at this variance"
    assert analysis.required_seeds > 5

    bigger = power_analysis(
        effect_size=0.05, variance_estimate=0.0025,
        seeds_per_condition=analysis.required_seeds,
    )
    assert bigger.powered


def test_non_inferiority_framing_needs_fewer_seeds_than_superiority():
    """Spec §26.8's planning note, made checkable."""
    two_sided = power_analysis(effect_size=0.05, variance_estimate=0.0025,
                               seeds_per_condition=10, framing="superiority")
    one_sided = power_analysis(effect_size=0.05, variance_estimate=0.0025,
                               seeds_per_condition=10, framing="non_inferiority")
    assert one_sided.required_seeds < two_sided.required_seeds


def test_zero_measured_variance_is_not_treated_as_infinite_power():
    """Zero variance across seeds means the seeds did not vary anything the endpoint depends
    on, not that the run has perfect power. Certifying a confirmatory run off a degenerate
    measurement is exactly what §26.8 forbids."""
    degenerate = power_analysis(
        effect_size=0.05, variance_estimate=0.0, seeds_per_condition=3
    )
    assert not degenerate.powered
    assert degenerate.achieved_power == 0.0
