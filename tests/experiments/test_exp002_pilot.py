"""The EXP-002 pilot measures what the pre-registration needs and nothing it cannot (ADR-0023).

Driven here with the scripted oracle behind a local OpenAI-compatible server, so exchange
latencies exist and the token-rate fit runs; and with a non-networked backend, so the report
says the token rates are unmeasured rather than guessing them.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from bestsad.conditions import DeviceSecondsPolicy
from bestsad.experiments.exp001 import JobIsolation
from bestsad.solver import SearchBudget
from bestsad.tasks import adversarial_set, curriculum_set, held_out_set, in_family_ood_set

from tests.experiments.test_model_role import IDENTITY, SCRIPTED, TINY, _spec
from tests.models import scripts

REPO = Path(__file__).resolve().parents[2]


def _pilot():
    spec = importlib.util.spec_from_file_location("exp002_pilot", REPO / "scripts" / "exp002_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _register(seeds):
    for seed in seeds:
        for task_set in (curriculum_set(seed, 1), held_out_set(90210 + seed, 1),
                         in_family_ood_set(90212 + seed, 1), adversarial_set(90211 + seed, 1)):
            for task in task_set:
                scripts.register(task)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = scripts.oracle(body["messages"][0]["content"], int(body.get("seed", 0)))
        reply = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 120, "completion_tokens": 9}}
        payload = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # pragma: no cover - quiet
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _sizing():
    sizing = dict(TINY)
    budget = sizing.pop("budget")
    sizing.pop("per_family")
    return sizing, budget


def test_the_fit_recovers_two_rates_and_falls_back_when_it_cannot():
    pilot = _pilot()
    exchanges = [{"input_tokens": 100, "output_tokens": 10}, {"input_tokens": 300, "output_tokens": 50},
                 {"input_tokens": 50, "output_tokens": 80}]
    timings = [100 * 1e-4 + 10 * 2e-2, 300 * 1e-4 + 50 * 2e-2, 50 * 1e-4 + 80 * 2e-2]
    fit = pilot.fit_token_rates(exchanges, timings)
    assert fit["seconds_per_input_token"] == pytest.approx(1e-4)
    assert fit["seconds_per_output_token"] == pytest.approx(2e-2)
    assert fit["residual_rms_s"] == pytest.approx(0.0, abs=1e-9)
    # Every exchange the same shape: singular, so everything is priced as output tokens.
    same = [{"input_tokens": 100, "output_tokens": 10}] * 3
    fit = pilot.fit_token_rates(same, [0.5, 0.5, 0.5])
    assert fit["seconds_per_input_token"] == 0.0
    assert fit["seconds_per_output_token"] == pytest.approx(0.05)
    assert "fallback" in fit["method"]
    assert pilot.fit_token_rates([], [])["seconds_per_output_token"] is None


def test_cpu_rates_are_timed_on_this_host_and_attributed():
    pilot = _pilot()
    rates = pilot.measure_cpu_rates(TINY["budget"], repetitions=5)
    assert rates["seconds_per_kernel_step"] > 0 and rates["kernel_steps_timed"] > 0
    assert rates["seconds_per_search_node"] is not None and rates["seconds_per_search_node"] >= 0
    assert "kernel steps" in rates["attribution"]["verifier_steps"]


def test_the_pilot_calibrates_the_currency_from_a_served_model(server, tmp_path):
    pilot = _pilot()
    _register([1, 2])
    sizing, budget = _sizing()
    spec = _spec({"kind": "http", "endpoint": server, "model": "scripted-coder"})
    report = pilot.run_pilot(
        spec, [1, 2], hardware="test host", artifacts_dir=tmp_path / "artifacts",
        per_family=1, isolation=JobIsolation(enabled=False), budget=budget, sizing=sizing,
    )
    e0 = report["e0_under_model"]
    assert e0["per_seed_verified_ood_rate"] == [1.0, 1.0]     # the oracle answers everything
    assert e0["samples"] > 0 and e0["tokens_per_sample"] == pytest.approx(129.0)
    assert report["ceiling_check"]["saturating"] and "1.5B" in report["ceiling_check"]["action"]
    assert report["token_rate_fit"]["exchanges"] == e0["samples"]
    currency = DeviceSecondsPolicy(**{
        k: v for k, v in report["compute_currency"].items()
        if k not in ("calibrated", "missing_rates")
    })
    assert currency.calibrated and currency.hardware == "test host"
    assert currency.seconds_per_output_token is not None and currency.seconds_per_output_token >= 0
    assert report["per_task_device_seconds_condition_A"]["mean"] >= 0
    fill = report["preregistration_fill"]
    assert fill["model_identity.model_identity_hash"] == IDENTITY.hash()
    assert fill["model_identity.is_pinned"][0] is False
    assert fill["power_analysis.variance_estimate"] == e0["variance"]
    assert fill["seeds_per_condition"] == fill["power_analysis.required_seeds"]
    assert "Fixed:" in fill["stopping_rule"] and "<<FILL" not in fill["stopping_rule"]
    assert fill["minimum_interesting_effect.compute_budget.per_task_budget_C_device_seconds"] >= 0
    assert report["whole_design_flops_estimate"]["value"] > 0
    assert (tmp_path / "artifacts" / "transcripts" / "A_seed2.json").exists()


def test_without_a_served_model_the_token_rates_are_unmeasured_not_guessed(tmp_path):
    pilot = _pilot()
    _register([1])
    sizing, budget = _sizing()
    report = pilot.run_pilot(
        SCRIPTED, [1], hardware="test host", artifacts_dir=tmp_path / "artifacts",
        per_family=1, isolation=JobIsolation(enabled=False), budget=budget, sizing=sizing,
    )
    assert report["token_rate_fit"]["seconds_per_output_token"] is None
    assert "not networked" in report["token_rate_fit"]["method"]
    assert not report["compute_currency"]["calibrated"]
    assert {"seconds_per_input_token", "seconds_per_output_token"} <= set(
        report["compute_currency"]["missing_rates"])
    assert report["per_task_device_seconds_condition_A"] is None
    assert "uncalibrated" in report["preregistration_fill"][
        "minimum_interesting_effect.compute_budget.per_task_budget_C_device_seconds"]


def test_the_cli_writes_the_report(server, tmp_path, capsys):
    pilot = _pilot()
    _register([1])
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec({"kind": "http", "endpoint": server, "model": "m"})))
    # The CLI takes the runner's default sizing, which is too large for a test; drive it at the
    # smallest per-family count and the default budget only far enough to prove the plumbing.
    monkey = pilot.run_pilot

    def small(spec, seeds, **kwargs):
        sizing, budget = _sizing()
        kwargs.update(budget=budget, sizing=sizing)
        return monkey(spec, seeds, **kwargs)

    pilot.run_pilot = small
    assert pilot.main(["--spec", str(spec_path), "--seeds", "1", "--hardware", "h",
                       "--artifacts", str(tmp_path / "a"), "--no-isolation", "--per-family", "1"]) == 0
    out = json.loads((tmp_path / "a" / "pilot.json").read_text())
    assert out["hardware"] == "h" and "wrote" in capsys.readouterr().out
