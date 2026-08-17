"""Statistics for the reporting pipeline (spec §26.7, §26.8; implementation plan M9).

Pure standard library, by ADR-0004: these run inside the hermetic evaluator image, they are all
short and exactly specified, and each is checked against a closed-form value in
`tests/stats/`.

Everything here is deterministic. The bootstrap takes an explicit seed and resamples with a
seeded PRNG, so a published confidence interval can be reproduced exactly rather than
approximately.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence


# --- descriptive -----------------------------------------------------------------------------


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    ordered = sorted(xs)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def variance(xs: Sequence[float]) -> float:
    """Sample variance (n-1). This is the quantity E0 must measure before power analysis is
    meaningful (spec §26.8: measured variance, not assumed)."""
    if len(xs) < 2:
        return 0.0
    mu = mean(xs)
    return sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)


def stdev(xs: Sequence[float]) -> float:
    return math.sqrt(variance(xs))


# --- normal / t distributions ------------------------------------------------------------------


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def normal_quantile(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.15e-9)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _t_cdf(t: float, df: float) -> float:
    """Student-t CDF via the regularized incomplete beta function."""
    if df <= 0:
        raise ValueError("df must be positive")
    x = df / (df + t * t)
    prob = 0.5 * _betainc(df / 2.0, 0.5, x)
    return prob if t <= 0 else 1.0 - prob


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b), by continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        a * math.log(x) + b * math.log(1 - x)
        + math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    )
    if x < (a + 1) / (a + b + 2):
        return front * _beta_cf(a, b, x) / a
    return 1.0 - front * _beta_cf(b, a, 1 - x) / b


def _beta_cf(a: float, b: float, x: float, iterations: int = 300, eps: float = 1e-12) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < eps:
        d = eps
    d = 1.0 / d
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < eps:
            d = eps
        c = 1.0 + aa / c
        if abs(c) < eps:
            c = eps
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < eps:
            d = eps
        c = 1.0 + aa / c
        if abs(c) < eps:
            c = eps
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


# --- tests ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TestResult:
    statistic: float
    p_value: float
    df: float
    effect: float
    label: str = ""


def welch_t_test(a: Sequence[float], b: Sequence[float], label: str = "") -> TestResult:
    """Two-sided Welch's t-test for the difference in means (a - b).

    Welch rather than Student because conditions are not guaranteed equal-variance: a treatment
    that helps some seeds and not others has *higher* variance than its baseline by
    construction, which is precisely when the equal-variance assumption misleads.
    """
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return TestResult(0.0, 1.0, 0.0, mean(a) - mean(b), label)
    va, vb = variance(a), variance(b)
    se2 = va / na + vb / nb
    effect = mean(a) - mean(b)
    if se2 <= 0:
        return TestResult(0.0, 1.0 if effect == 0 else 0.0, 0.0, effect, label)
    t = effect / math.sqrt(se2)
    df = se2**2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = 2.0 * (1.0 - _t_cdf(abs(t), df))
    return TestResult(t, min(1.0, max(0.0, p)), df, effect, label)


def non_inferiority_test(
    a: Sequence[float], b: Sequence[float], margin: float, label: str = ""
) -> TestResult:
    """One-sided non-inferiority: is `a` no worse than `b` by more than `margin`?

    H0: mean(a) - mean(b) <= -margin. Rejecting H0 supports non-inferiority.

    Spec §26.8 prefers this to an equivalence framing wherever the scientific question is
    genuinely "no worse", because equivalence needs materially larger samples at the same
    margin and power for no scientific gain.
    """
    na, nb = len(a), len(b)
    effect = mean(a) - mean(b)
    if na < 2 or nb < 2:
        return TestResult(0.0, 1.0, 0.0, effect, label)
    va, vb = variance(a), variance(b)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return TestResult(0.0, 0.0 if effect > -margin else 1.0, 0.0, effect, label)
    t = (effect + margin) / math.sqrt(se2)
    df = se2**2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = 1.0 - _t_cdf(t, df)
    return TestResult(t, min(1.0, max(0.0, p)), df, effect, label)


# --- multiple comparison control ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FDRResult:
    label: str
    p_value: float
    rank: int
    critical_value: float
    rejected: bool


def benjamini_hochberg(p_values: dict[str, float], q: float = 0.05) -> list[FDRResult]:
    """Benjamini-Hochberg FDR control (spec §26.7).

    Required because H1-H15 crossed with A0-A8 implies dozens of simultaneous comparisons, and
    without correction a five-point "win" turns up somewhere by chance alone. The comparison
    family must be declared in the pre-registration, not chosen after the fact — this function
    controls the error rate over whatever family it is given, and it cannot tell whether that
    family was declared in advance. That check lives in the pre-registration gate.
    """
    if not p_values:
        return []
    ordered = sorted(p_values.items(), key=lambda kv: (kv[1], kv[0]))
    m = len(ordered)
    results: list[FDRResult] = []
    largest_rejected = 0
    for index, (label, p) in enumerate(ordered, start=1):
        critical = q * index / m
        if p <= critical:
            largest_rejected = index
    for index, (label, p) in enumerate(ordered, start=1):
        results.append(
            FDRResult(
                label=label,
                p_value=p,
                rank=index,
                critical_value=q * index / m,
                rejected=index <= largest_rejected,
            )
        )
    return results


# --- bootstrap ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    low: float
    high: float
    level: float = 0.95

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high

    def to_record(self) -> dict:
        return {"estimate": self.point, "ci_low": self.low, "ci_high": self.high,
                "level": self.level}


def bootstrap_ci(
    values: Sequence[float],
    *,
    statistic=mean,
    resamples: int = 4000,
    level: float = 0.95,
    seed: int = 0,
) -> Interval:
    """Percentile bootstrap confidence interval, seeded for exact reproducibility."""
    if not values:
        return Interval(0.0, 0.0, 0.0, level)
    if len(values) == 1:
        only = float(values[0])
        return Interval(only, only, only, level)
    rng = random.Random(f"bootstrap:{seed}:{len(values)}")
    n = len(values)
    stats = []
    for _ in range(resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(statistic(sample))
    stats.sort()
    alpha = (1.0 - level) / 2.0
    low = stats[max(0, int(alpha * resamples) - 1)]
    high = stats[min(resamples - 1, int((1 - alpha) * resamples))]
    return Interval(statistic(values), low, high, level)


def bootstrap_difference_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    resamples: int = 4000,
    level: float = 0.95,
    seed: int = 0,
) -> Interval:
    """Bootstrap CI for mean(a) - mean(b)."""
    if not a or not b:
        return Interval(0.0, 0.0, 0.0, level)
    rng = random.Random(f"bootstrap-diff:{seed}:{len(a)}:{len(b)}")
    stats = []
    for _ in range(resamples):
        sa = [a[rng.randrange(len(a))] for _ in range(len(a))]
        sb = [b[rng.randrange(len(b))] for _ in range(len(b))]
        stats.append(mean(sa) - mean(sb))
    stats.sort()
    alpha = (1.0 - level) / 2.0
    return Interval(
        mean(a) - mean(b),
        stats[max(0, int(alpha * resamples) - 1)],
        stats[min(resamples - 1, int((1 - alpha) * resamples))],
        level,
    )


# --- power --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PowerAnalysis:
    effect_size: float
    variance_estimate: float
    seeds_per_condition: int
    alpha: float
    target_power: float
    achieved_power: float
    required_seeds: int
    framing: str

    @property
    def powered(self) -> bool:
        return self.achieved_power >= self.target_power

    def to_record(self) -> dict:
        return {
            "minimum_interesting_effect": self.effect_size,
            "variance_estimate": self.variance_estimate,
            "seeds_per_condition": self.seeds_per_condition,
            "alpha": self.alpha,
            "target_power": self.target_power,
            "achieved_power": self.achieved_power,
            "required_seeds_per_condition": self.required_seeds,
            "framing": self.framing,
            "powered": self.powered,
        }


def power_analysis(
    *,
    effect_size: float,
    variance_estimate: float,
    seeds_per_condition: int,
    alpha: float = 0.05,
    target_power: float = 0.80,
    framing: str = "superiority",
) -> PowerAnalysis:
    """Two-sample power for a difference in means, using **measured** variance (spec §26.8).

    Superiority is two-sided; non-inferiority is one-sided, which is why the same margin and
    power need fewer seeds under a non-inferiority framing — the reason spec §26.8 warns against
    reaching for an equivalence framing out of habit.

    If the achievable seed count cannot power the pre-registered effect, the correct action is
    to record that and re-scope, not to run underpowered and interpret the point estimate. The
    pre-registration gate refuses to certify a confirmatory run when `powered` is false.
    """
    if effect_size <= 0:
        return PowerAnalysis(effect_size, variance_estimate, seeds_per_condition, alpha,
                             target_power, 0.0, 0, framing)

    if variance_estimate <= 0:
        # Zero measured variance across seeds is almost never "infinite power". It means the
        # seeds did not vary anything the endpoint depends on, so there is no variance estimate
        # to power an analysis with. Treating it as powered would let a degenerate measurement
        # certify a confirmatory run, which is exactly what §26.8 forbids ("using variance
        # measured in E0 rather than assumed").
        return PowerAnalysis(effect_size, 0.0, seeds_per_condition, alpha, target_power,
                             0.0, 0, framing)

    z_alpha = normal_quantile(1 - alpha / 2) if framing == "superiority" else normal_quantile(1 - alpha)
    se = math.sqrt(2 * variance_estimate / seeds_per_condition) if seeds_per_condition else float("inf")
    achieved = 1.0 - normal_cdf(z_alpha - effect_size / se) if se > 0 else 1.0

    z_beta = normal_quantile(target_power)
    required = math.ceil(2 * variance_estimate * (z_alpha + z_beta) ** 2 / effect_size**2)

    return PowerAnalysis(
        effect_size=effect_size,
        variance_estimate=variance_estimate,
        seeds_per_condition=seeds_per_condition,
        alpha=alpha,
        target_power=target_power,
        achieved_power=min(1.0, max(0.0, achieved)),
        required_seeds=max(2, required),
        framing=framing,
    )
