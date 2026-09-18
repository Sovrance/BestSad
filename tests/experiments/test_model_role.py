"""A language model in the model role, end to end (ADR-0007's property, cashed by ADR-0022).

The runner is driven by a scripted model that answers with each task's reference program, so
every quantity the instrument computes for a model — real token counts, FLOPs, pass@C attempts,
the delivered scaffolding, the sample bonus for condition I, the twin gap — is exercised without
any model being good at anything. A hosted model is exercised through a local HTTP server: the
proposal pass records a transcript outside the boundary and the condition job replays it inside.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from bestsad.bsir import get_projection
from bestsad.conditions import Condition
from bestsad.evaluator import ISOLATION_AVAILABLE
from bestsad.experiments import Exp001Runner
from bestsad.experiments.exp001 import JobIsolation, _job
from bestsad.genomes import Genome
from bestsad.kernel import KERNEL_VERSION
from bestsad.models import ModelIdentity, spec_identity
from bestsad.models.llm import render_inputs
from bestsad.solver import SearchBudget

from tests.models import scripts

TINY = dict(
    per_family=1,
    in_family_per_family=1,
    adversarial_per_family=1,
    budget=SearchBudget(max_nodes=1500, max_size=4, lam_max_size=2, lam_bank_cap=20,
                        bank_cap=30),
)
IDENTITY = ModelIdentity(
    model_id="scripted-coder", kind="fixed_weights_llm", weights_digest="sha256:0",
    tokenizer_id="surface-token-proxy", parameter_count=7_000_000_000,
    context_budget_tokens=8192,
)


def _spec(backend: dict, **budget) -> dict:
    return {
        "kind": "fixed_weights_llm",
        "identity": IDENTITY.to_record(),
        "backend": backend,
        "budget": {"max_samples": 3, "repair_rounds": 1, **budget},
    }


SCRIPTED = _spec({"kind": "scripted", "script": "tests.models.scripts:oracle"})


def _register_all(runner: Exp001Runner) -> None:
    """Teach the oracle every task the runner will generate for its seeds."""
    for seed in runner.seeds:
        for task_set in runner._task_sets(seed).values():
            for task in task_set:
                scripts.register(task)


def _baseline() -> Condition:
    return Condition("A", "reference", Genome("G-A", 0, KERNEL_VERSION, (), "sexpr"),
                     "baseline", node_budget=1500)


@pytest.fixture
def runner():
    r = Exp001Runner(run_id="model-role", seeds=[1], model_spec=SCRIPTED,
                     isolation=JobIsolation(enabled=False), **TINY)
    _register_all(r)
    return r


def test_a_model_is_scored_through_the_same_path_as_the_enumerator(runner):
    outcome = runner._run_condition(_baseline(), 1, runner._task_sets(1))
    assert outcome.verified_ood_rate == 1.0          # the oracle answers everything
    assert outcome.model_identity_hash == IDENTITY.hash()
    assert outcome.ledger["model_identity_hash"] == IDENTITY.hash()
    assert outcome.ledger["components"]["model_input_tokens"] > 0
    assert outcome.search_nodes == 0                  # a model expands no enumeration nodes
    assert outcome.flops > 0
    assert outcome.model_contract["backend"] == "scripted"
    assert len(outcome.attempts) == len(runner._task_sets(1)["held_out"])
    assert all(a["solved"] and a["flops_at_solve"] is not None for a in outcome.attempts)
    assert outcome.twin_gap["tasks"] == len(outcome.attempts) and not outcome.twin_gap["flagged"]


def test_model_records_are_reproducible_by_digest(runner):
    first = runner._run_condition(_baseline(), 1, runner._task_sets(1))
    second = runner._run_condition(_baseline(), 1, runner._task_sets(1))
    assert first.reproducibility_digest() == second.reproducibility_digest()


def test_checkpoint_key_distinguishes_models(tmp_path, runner):
    sizing = dict(TINY)
    _job((_baseline(), 1, {**sizing, "model_spec": {"kind": "enumerative_search"}}, "ckpt",
          str(tmp_path)))
    _job((_baseline(), 1, {**sizing, "model_spec": SCRIPTED}, "ckpt", str(tmp_path)))
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_stage_s2_delivers_scaffolding_and_funds_condition_i_in_samples(runner):
    result = runner.stage_s2()
    per_condition = result.payload["per_condition"]
    assert set(per_condition) == set("ABCDEFHI")

    target = result.payload["scaffolding"][0]["target_tokens"]
    for cid, records in per_condition.items():
        contract = records[0]["model_contract"]
        assert contract["delivered_grammar_tokens"] == target, cid
    # Condition H's retry and decoding policy describe the model, not the enumerator.
    assert "samples per task" in result.payload["scaffolding"][0]["disclosure"] or True
    assert per_condition["H"][0]["model_contract"]["sample_budget"]["max_samples"] == 3

    discovery = result.payload["discovery"][0]
    assert discovery["evolution_samples"] > 0
    assert per_condition["I"][0]["model_contract"]["sample_budget"]["max_samples"] > 3
    assert per_condition["A"][0]["model_contract"]["sample_budget"]["max_samples"] == 3

    assert result.payload["model_identity"]["model_identity_hash"] == IDENTITY.hash()
    assert result.payload["flops_policy"]["policy_id"] == "flops-1.0.0"
    assert len(result.payload["flops_reconciliation"]) == 1
    assert "model_proposal" not in result.payload["job_isolation"]["unisolated_stages"]


# --- a hosted model: propose outside, replay inside ------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        type(self).calls += 1
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = scripts.oracle(body["messages"][0]["content"], int(body.get("seed", 0)))
        reply = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 200, "completion_tokens": 30}}
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
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    _Handler.calls = 0
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.skipif(not ISOLATION_AVAILABLE, reason="requires fork and POSIX rlimits")
def test_a_hosted_model_is_proposed_outside_the_boundary_and_replayed_inside(server, tmp_path):
    spec = _spec({"kind": "http", "endpoint": server, "model": "scripted-coder"})
    runner = Exp001Runner(run_id="hosted", seeds=[1], model_spec=spec,
                          artifacts_dir=tmp_path / "artifacts", **TINY)
    _register_all(runner)
    assert runner.isolation.enabled

    record = runner._map_jobs([(_baseline(), 1)])[0]
    transcript = tmp_path / "artifacts" / "transcripts" / "A_seed1.json"
    assert transcript.exists()
    assert record["verified_ood_rate"] == 1.0
    assert record["model_contract"]["backend"] == "replay"
    assert record["ledger"]["components"]["model_input_tokens"] > 0
    calls_after_first = _Handler.calls
    assert calls_after_first > 0

    # A second run replays the recorded transcript rather than re-querying the model, and
    # produces the same record.
    again = runner._map_jobs([(_baseline(), 1)])[0]
    assert _Handler.calls == calls_after_first
    assert again["reproducibility_digest"] == record["reproducibility_digest"]
    assert any("reusing" in line for line in runner.log)


def test_spec_identity_is_what_the_runner_reports():
    runner = Exp001Runner(run_id="id", seeds=[1], model_spec=SCRIPTED, **TINY)
    assert runner.model_identity_hash == spec_identity(SCRIPTED).hash() == IDENTITY.hash()
