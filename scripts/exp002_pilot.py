#!/usr/bin/env python3
"""The EXP-002 E0 pilot: the numbers the pre-registration needs, measured (ADR-0023 §3).

ADR-0023 sets the compute budget from a pilot, not from a planning figure, and declares
device-seconds on the pinned hardware as the currency in which an enumerator and a model can
be matched. This script is that pilot. It runs the E0 baseline under the model for a small
number of seeds (spec §43 S1: `Exp001Runner.stage_s1`) and measures:

* the across-seed variance of the verified held-out solve rate, and the power analysis that
  turns it into a seed count for the +0.05 effect;
* tokens per sample, from real token counts;
* the device-second rates a `DeviceSecondsPolicy` needs — seconds per input and per output
  token from a least-squares fit over the recorded exchange latencies, seconds per kernel step
  and per search node from timed runs of K0 and the enumerator on the same host;
* the ceiling check: a model that solves the curriculum near ceiling under K0 alone reproduces
  the C1 problem EXP-001-DR hit, and ADR-0023 says drop to the 1.5B when that happens.

It writes one JSON report whose `preregistration_fill` block lists, by field, what to copy into
`docs/preregistrations/EXP-002.draft.json` before `Preregistration.commit()`. Nothing here is
evidence about the hypothesis: it is instrument calibration, and the report says so.

    python scripts/exp002_pilot.py --spec spec.json --seeds 1 2 \\
        --hardware "1x NVIDIA H100 80GB SXM, vLLM <version>" --out artifacts/exp002-pilot/pilot.json

Run it on the pinned hardware: rates measured on one machine are not the currency on another.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from bestsad.conditions import DEFAULT_FLOPS_POLICY, DeviceSecondsPolicy  # noqa: E402
from bestsad.experiments import Exp001Runner  # noqa: E402
from bestsad.experiments.exp001 import BASE_VOCABULARY, JobIsolation  # noqa: E402
from bestsad.kernel import Kernel  # noqa: E402
from bestsad.models import EnumerativeAdapter, Transcript, spec_identity  # noqa: E402
from bestsad.solver import SearchBudget  # noqa: E402
from bestsad.tasks import curriculum_set  # noqa: E402

#: ADR-0023's ceiling: a model this good under K0 alone is a saturating searcher.
CEILING_RATE = 0.95
#: Planning figures used only to size the whole-design FLOP estimate the report carries
#: alongside the device-second numbers; the pre-registration takes its own from the pilot.
PLANNING_CONDITIONS = 9
PLANNING_SAMPLES_PER_TASK = 32


# --- rates -------------------------------------------------------------------------------------


def fit_token_rates(exchanges: Sequence[Mapping[str, Any]], timings: Sequence[float]) -> dict:
    """Seconds per input token and per output token from exchange latencies.

    A two-parameter least-squares fit, `latency = a * input_tokens + b * output_tokens`, with
    no intercept: per-request overhead lands in the rates, which is the conservative direction
    for a budget. When the fit is singular (every exchange has the same shape, or there is only
    one), everything is priced as output tokens and the record says so.
    """
    pairs = [
        (float(e["input_tokens"]), float(e["output_tokens"]), float(t))
        for e, t in zip(exchanges, timings)
    ]
    if not pairs:
        return {"seconds_per_input_token": None, "seconds_per_output_token": None,
                "exchanges": 0, "method": "no exchange latencies recorded"}
    sxx = sum(x * x for x, _, _ in pairs)
    syy = sum(y * y for _, y, _ in pairs)
    sxy = sum(x * y for x, y, _ in pairs)
    sxt = sum(x * t for x, _, t in pairs)
    syt = sum(y * t for _, y, t in pairs)
    det = sxx * syy - sxy * sxy
    total_out = sum(y for _, y, _ in pairs)
    if det > 1e-12 * max(1.0, sxx * syy):
        a = (sxt * syy - syt * sxy) / det
        b = (syt * sxx - sxt * sxy) / det
        method = "least squares, latency ~ a*input + b*output, no intercept"
        if a < 0 or b < 0:
            # A negative rate is a fit artefact, not a price; fall back to the one-rate form.
            a, b, method = 0.0, (sum(t for *_, t in pairs) / total_out if total_out else None), (
                "one-rate fallback: the two-rate fit went negative")
    elif total_out > 0:
        a, b = 0.0, sum(t for *_, t in pairs) / total_out
        method = "one-rate fallback: the two-rate fit is singular; everything priced as output"
    else:
        a, b, method = None, None, "no output tokens recorded"
    residual = None
    if a is not None and b is not None:
        residual = (sum((a * x + b * y - t) ** 2 for x, y, t in pairs) / len(pairs)) ** 0.5
    return {"seconds_per_input_token": a, "seconds_per_output_token": b,
            "exchanges": len(pairs), "method": method, "residual_rms_s": residual}


def measure_cpu_rates(budget: SearchBudget, *, seed: int = 1, repetitions: int = 200) -> dict:
    """Seconds per kernel step and per search node, timed on this host.

    Kernel steps: the reference program of one curriculum task executed on its visible inputs,
    repeated. Search nodes: the enumerator run on the same task under `budget`, with the kernel
    time its steps took subtracted. Verifier steps are K0 executions and are priced as kernel
    steps; evolution nodes are search nodes drawn during discovery and are priced as search
    nodes. Both attributions are recorded.
    """
    task = list(curriculum_set(seed, 1))[0]
    kernel = Kernel(fuel=budget.kernel_fuel)
    steps = 0
    started = time.perf_counter()
    for _ in range(repetitions):
        for inputs in task.train_inputs:
            steps += kernel.execute(task.reference, list(inputs)).steps
    kernel_elapsed = time.perf_counter() - started
    seconds_per_kernel_step = kernel_elapsed / steps if steps else None

    adapter = EnumerativeAdapter(kernel, BASE_VOCABULARY, None, budget=budget, seed=seed)
    started = time.perf_counter()
    result = adapter.solve(task)
    search_elapsed = time.perf_counter() - started
    kernel_share = (seconds_per_kernel_step or 0.0) * result.kernel_steps
    seconds_per_search_node = (
        max(0.0, search_elapsed - kernel_share) / result.nodes_expanded
        if result.nodes_expanded else None
    )
    return {
        "seconds_per_kernel_step": seconds_per_kernel_step,
        "seconds_per_search_node": seconds_per_search_node,
        "kernel_steps_timed": steps,
        "search_nodes_timed": result.nodes_expanded,
        "attribution": {
            "verifier_steps": "priced as kernel steps (verification is K0 execution)",
            "evolution_nodes": "priced as search nodes (discovery draws the same nodes)",
        },
    }


# --- the pilot ---------------------------------------------------------------------------------


def run_pilot(
    spec: Mapping[str, Any],
    seeds: Sequence[int],
    *,
    hardware: str,
    artifacts_dir: Path,
    per_family: int = 3,
    isolation: JobIsolation | None = None,
    budget: SearchBudget | None = None,
    minimum_effect: float = 0.05,
    sizing: Mapping[str, Any] | None = None,
) -> dict:
    """E0 under the model, the variance and power it implies, and the calibrated currency."""
    runner = Exp001Runner(
        run_id="exp002-pilot", seeds=list(seeds), model_spec=dict(spec),
        artifacts_dir=Path(artifacts_dir), per_family=per_family, isolation=isolation,
        budget=budget, **dict(sizing or {}),
    )
    identity = spec_identity(spec)
    s1 = runner.stage_s1(minimum_effect)
    outcomes = list(s1.payload["outcomes"])
    tasks_per_seed = runner.tasks_per_seed()

    input_tokens = sum(int(o["ledger"]["components"]["model_input_tokens"]) for o in outcomes)
    output_tokens = sum(int(o["ledger"]["components"]["model_output_tokens"]) for o in outcomes)
    samples = sum(int(o.get("model_samples", 0)) for o in outcomes)
    tokens_per_sample = (input_tokens + output_tokens) / samples if samples else None

    # Token rates from the recorded transcripts (a networked backend); absent otherwise.
    exchanges: list[dict] = []
    timings: list[float] = []
    for seed in seeds:
        path = Path(artifacts_dir) / "transcripts" / f"A_seed{seed}.json"
        if path.exists():
            transcript = Transcript.load(path)
            n = min(len(transcript.exchanges), len(transcript.timings))
            exchanges.extend(transcript.exchanges[:n])
            timings.extend(transcript.timings[:n])
    token_fit = fit_token_rates(exchanges, timings)
    if not exchanges:
        token_fit["method"] = (
            "no exchange latencies: the backend is not networked, so no transcript was "
            "recorded; token rates must come from a run against the served model"
        )
    cpu = measure_cpu_rates(runner.budget)

    per_token_flops = DEFAULT_FLOPS_POLICY.model_token_flops(identity.parameter_count)
    out_rate = token_fit["seconds_per_output_token"]
    flops_per_device_second = (per_token_flops / out_rate) if out_rate else None
    currency = DeviceSecondsPolicy(
        hardware=hardware,
        seconds_per_input_token=token_fit["seconds_per_input_token"],
        seconds_per_output_token=out_rate,
        seconds_per_search_node=cpu["seconds_per_search_node"],
        seconds_per_kernel_step=cpu["seconds_per_kernel_step"],
        seconds_per_verifier_step=cpu["seconds_per_kernel_step"],
        seconds_per_evolution_node=cpu["seconds_per_search_node"],
        flops_per_device_second=flops_per_device_second,
        calibration=(
            f"pilot-measured on {hardware!r} by scripts/exp002_pilot.py over seeds "
            f"{list(seeds)}; token rates: {token_fit['method']}"
        ),
    )

    # What condition A spent per task in the currency, which is where C is read from.
    per_task_device_seconds = None
    if currency.calibrated:
        from bestsad.conditions import ComputeLedger

        totals = []
        for o in outcomes:
            c = o["ledger"]["components"]
            ledger = ComputeLedger(
                "pilot", "A", int(o["seed"]),
                model_input_tokens=int(c["model_input_tokens"]),
                model_output_tokens=int(c["model_output_tokens"]),
                search_nodes=int(c["search_compute"]), kernel_steps=0,
            )
            totals.append(currency.device_seconds(ledger) / max(1, tasks_per_seed))
        per_task_device_seconds = {"mean": mean(totals), "per_seed": totals}

    rates = s1.payload["per_seed_verified_ood_rate"]
    power = s1.payload["power_analysis"]
    required_seeds = int(power.get("required_seeds") or 0)
    e0_mean = float(s1.payload["mean"])
    saturating = e0_mean >= CEILING_RATE
    planning_flops = (
        tokens_per_sample * PLANNING_SAMPLES_PER_TASK * tasks_per_seed
        * max(required_seeds, len(seeds)) * PLANNING_CONDITIONS * per_token_flops
        if tokens_per_sample else None
    )

    fill = {
        "model_identity.model_identity_hash": identity.hash(),
        "model_identity.is_pinned": identity.is_pinned(),
        "power_analysis.variance_source_run": "exp002-pilot (stage_s1 under the model)",
        "power_analysis.variance_estimate": s1.payload["variance"],
        "power_analysis.required_seeds": required_seeds,
        "power_analysis.achieved_power": power.get("achieved_power"),
        "seeds_per_condition": required_seeds,
        "stopping_rule": (
            f"Fixed: {required_seeds} seeds per condition (from the pilot's power analysis), "
            "all conditions run to completion. No interim analysis, no data-dependent "
            "stopping. Aborted runs are recorded with their cause, never silently discarded."
        ),
        "minimum_interesting_effect.compute_budget.hardware": hardware,
        "minimum_interesting_effect.compute_budget.rates": currency.to_record(),
        "minimum_interesting_effect.compute_budget.per_task_budget_C_device_seconds": (
            per_task_device_seconds["mean"] if per_task_device_seconds else
            "not computable: the currency is uncalibrated (see compute_currency.missing_rates)"
        ),
        "model_identity.sampling.max_samples_per_task": (
            spec.get("budget") or {}).get("max_samples", "as run"),
    }
    return {
        "purpose": "instrument calibration for EXP-002 (ADR-0023 §3); not evidence about H2",
        "hardware": hardware,
        "model_identity_hash": identity.hash(),
        "model_pinned": identity.is_pinned(),
        "seeds": list(seeds),
        "e0_under_model": {
            "per_seed_verified_ood_rate": rates,
            "mean": e0_mean,
            "variance": s1.payload["variance"],
            "bootstrap_ci": s1.payload["bootstrap_ci"],
            "power_analysis": power,
            "tasks_per_seed": tasks_per_seed,
            "samples": samples,
            "model_input_tokens": input_tokens,
            "model_output_tokens": output_tokens,
            "tokens_per_sample": tokens_per_sample,
        },
        "ceiling_check": {
            "threshold": CEILING_RATE,
            "saturating": saturating,
            "action": (
                "drop to Qwen2.5-Coder-1.5B-Instruct as primary (ADR-0023): a saturating model "
                "reproduces the C1 problem EXP-001-DR hit" if saturating else "keep the 7B"
            ),
        },
        "token_rate_fit": token_fit,
        "cpu_rates": cpu,
        "compute_currency": currency.to_record(),
        "per_task_device_seconds_condition_A": per_task_device_seconds,
        "whole_design_flops_estimate": {
            "value": planning_flops,
            "assumptions": {
                "conditions": PLANNING_CONDITIONS,
                "samples_per_task": PLANNING_SAMPLES_PER_TASK,
                "seeds": max(required_seeds, len(seeds)),
                "tasks_per_seed": tasks_per_seed,
                "tokens_per_sample": tokens_per_sample,
                "flops_per_token": per_token_flops,
            },
            "note": "reported alongside the device-second budget, never instead of it",
        },
        "preregistration_fill": fill,
        "log": list(runner.log),
    }


# --- CLI ---------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--spec", required=True, type=Path, help="model spec JSON (ADR-0022)")
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--hardware", required=True,
                        help="the pinned hardware and serving stack this pilot runs on")
    parser.add_argument("--per-family", type=int, default=3)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts") / "exp002-pilot")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--minimum-effect", type=float, default=0.05)
    parser.add_argument("--no-isolation", action="store_true",
                        help="run condition jobs in-process (platforms without fork/rlimits)")
    args = parser.parse_args(argv)

    spec = json.loads(args.spec.read_text())
    report = run_pilot(
        spec, args.seeds, hardware=args.hardware, artifacts_dir=args.artifacts,
        per_family=args.per_family,
        isolation=JobIsolation(enabled=False) if args.no_isolation else None,
        minimum_effect=args.minimum_effect,
    )
    out = args.out or (args.artifacts / "pilot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    e0 = report["e0_under_model"]
    print(f"E0 under the model: mean {e0['mean']:.3f}, variance {e0['variance']:.5f}, "
          f"required seeds {report['preregistration_fill']['power_analysis.required_seeds']}")
    print(f"tokens per sample: {e0['tokens_per_sample']}")
    print(f"currency calibrated: {report['compute_currency']['calibrated']} "
          f"(missing {report['compute_currency']['missing_rates']})")
    print(f"ceiling check: {report['ceiling_check']['action']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
