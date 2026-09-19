"""Gate G1, extended for a language model in the model role (roadmap §6; ADR-0022).

The candidate sandbox stops a *process* reaching the hidden assets. A model in the loop adds two
surfaces the sandbox cannot see — the prompt and the completion — and one channel it must
still close: the network. Each test attempts the vector and requires it to fail or be caught.
"""

from __future__ import annotations

import dataclasses
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bestsad.evaluator import (
    DEFAULT_HOLDOUT,
    Evaluator,
    HoldoutPolicy,
    IntegrityViolation,
    candidate_sandbox,
    contamination_probe,
    default_policy,
    transcript_leak_findings,
    twin_gap,
)
from bestsad.experiments.exp001 import BASE_VOCABULARY
from bestsad.kernel import Kernel
from bestsad.models import HTTPBackend, LLMAdapter, ModelIdentity, SampleBudget, ScriptedBackend
from bestsad.models.llm import projection_for, render_inputs
from bestsad.tasks import CANARY, generate_task, held_out_set

from tests.models import scripts

IDENTITY = ModelIdentity(model_id="m", kind="fixed_weights_llm", weights_digest="d",
                         tokenizer_id="t", parameter_count=1)


# --- vector: the network, from inside the boundary ----------------------------------------------


def test_a_network_backend_is_denied_inside_the_candidate_sandbox(tmp_path):
    backend = HTTPBackend("http://127.0.0.1:1", "any-model")
    with candidate_sandbox(default_policy(tmp_path / "scratch")) as monitor:
        with pytest.raises(IntegrityViolation):
            backend.complete("Program:", max_tokens=8, temperature=0.0, seed=0)
    assert monitor.fired()
    assert monitor.findings[0]["kind"] == "network"


# --- the sealed tier ----------------------------------------------------------------------------


def test_the_sealed_tier_is_deterministic_disjoint_and_about_thirty_percent():
    task = generate_task("F9", 7)
    feedback, sealed = DEFAULT_HOLDOUT.split(task)
    assert len(sealed) == math.ceil(0.3 * len(task.hidden_inputs))
    assert len(feedback) + len(sealed) == len(task.hidden_inputs)
    assert set(feedback).isdisjoint(set(sealed))
    assert DEFAULT_HOLDOUT.sealed_indices(task) == HoldoutPolicy().sealed_indices(task)
    assert HoldoutPolicy(sealed_fraction=0.5).sealed_indices(task) != DEFAULT_HOLDOUT.sealed_indices(task)
    with pytest.raises(ValueError):
        HoldoutPolicy(sealed_fraction=1.0)


def test_sealing_changes_nothing_about_correctness_and_is_reported_per_tier():
    task = generate_task("F9", 7)
    score = Evaluator("bm").score_task(task, task.reference, solved_train=True)
    assert score.verified
    assert score.sealed_total + score.feedback_total == score.hidden_total
    assert score.sealed_passed == score.sealed_total
    assert score.feedback_passed == score.feedback_total


# --- vector: the prompt ----------------------------------------------------------------------


def test_the_adapters_prompt_carries_no_hidden_input():
    tasks = list(held_out_set(4242, 2))
    adapter = LLMAdapter(kernel=Kernel(), projection=projection_for("sexpr", {}),
                         vocabulary=BASE_VOCABULARY, primitive_sigs={}, identity=IDENTITY,
                         backend=ScriptedBackend(lambda p, s: "(length xs)"),
                         budget=SampleBudget(max_samples=1), kernel_fuel=4000, seed=1)
    kernel = Kernel()
    for task in tasks:
        expected = [kernel.execute(task.reference, list(i)) for i in task.train_inputs]
        prompt = adapter.prompt_header() + adapter.task_prompt(task, expected, [])
        assert transcript_leak_findings(prompt, tasks) == []
        visible = {render_inputs(i) for i in task.train_inputs}
        for inputs in task.hidden_inputs:
            rendered = render_inputs(inputs)
            if rendered not in visible and len(rendered) >= 6:
                assert rendered not in prompt


def test_a_sealed_input_or_the_canary_on_a_visible_surface_is_a_fatal_finding():
    task = generate_task("F9", 7)
    _, sealed = DEFAULT_HOLDOUT.split(task)
    planted = f"Task: ... {render_inputs(sealed[0])} -> 3\nProgram:"
    findings = transcript_leak_findings(planted, [task], surface="prompt")
    assert findings and findings[0]["kind"] == "sealed_input_leak" and findings[0]["fatal"]
    findings = transcript_leak_findings(f"Program: {CANARY}", [task])
    assert findings[0]["kind"] == "canary_leak"


def test_a_sealed_input_that_is_also_a_visible_example_is_not_a_false_positive():
    task = generate_task("F9", 7)
    _, sealed = DEFAULT_HOLDOUT.split(task)
    # Make the sealed input legitimately visible: another task whose visible example it is.
    twin = dataclasses.replace(task, task_id="twin", train_inputs=(sealed[0],))
    assert transcript_leak_findings(render_inputs(sealed[0]), [task, twin]) == []


# --- the twin-gap and contamination probes --------------------------------------------------------


def test_twin_gap_flags_a_model_that_does_better_on_what_it_could_see():
    gap = twin_gap(feedback_passed=9, feedback_total=10, sealed_passed=4, sealed_total=10,
                   tasks=3)
    assert gap.gap == pytest.approx(0.5) and gap.flagged
    fair = twin_gap(feedback_passed=8, feedback_total=10, sealed_passed=8, sealed_total=10,
                    tasks=3)
    assert not fair.flagged and fair.to_record()["threshold"] == 0.10


def test_contamination_probe_catches_a_model_that_can_complete_the_canary():
    assert contamination_probe(lambda prompt: CANARY)["fatal"]
    assert not contamination_probe(lambda prompt: "I cannot continue that.")["fatal"]


# --- vector: the model server, on the candidate side of the boundary (ADR-0023) --------------------
#
# A self-hosted endpoint is a process this repository does not control. It may receive the
# grammar and a task's visible examples — nothing else. These vectors try to send it more.


def test_a_task_identifier_or_a_hidden_asset_path_on_a_visible_surface_is_fatal():
    tasks = list(held_out_set(4242, 1))
    findings = transcript_leak_findings(f"Task {tasks[0].task_id}:\nProgram:", tasks,
                                        surface="prompt")
    assert [f["kind"] for f in findings] == ["identifier_leak"] and findings[0]["fatal"]
    findings = transcript_leak_findings("see hidden_evaluator/benchmark.json", tasks)
    assert findings[0]["kind"] == "hidden_asset_reference" and findings[0]["fatal"]
    # The adapter's own prompts carry neither: identifiers are never a legitimate coincidence.
    adapter = LLMAdapter(kernel=Kernel(), projection=projection_for("sexpr", {}),
                         vocabulary=BASE_VOCABULARY, primitive_sigs={}, identity=IDENTITY,
                         backend=ScriptedBackend(lambda p, s: "(length xs)"),
                         budget=SampleBudget(max_samples=1), kernel_fuel=4000, seed=1)
    for task in tasks:
        expected = [Kernel().execute(task.reference, list(i)) for i in task.train_inputs]
        assert transcript_leak_findings(
            adapter.prompt_header() + adapter.task_prompt(task, expected, []), tasks) == []


def test_the_outbound_guard_refuses_before_the_send_not_after():
    from bestsad.evaluator import OutboundGuard

    tasks = list(held_out_set(4242, 1))
    sent = []
    inner = ScriptedBackend(lambda p, s: sent.append(p) or "(length xs)")
    guard = OutboundGuard(inner, tasks)
    assert guard.name == "guarded(scripted)" and not guard.requires_network
    ok = guard.complete("Task ((xs: List[Int]) -> Int):\n  [1, 2] -> 2\nProgram:",
                        max_tokens=8, temperature=0.0, seed=0)
    assert ok.text == "(length xs)" and len(sent) == 1
    _, sealed = DEFAULT_HOLDOUT.split(tasks[0])
    for planted in (f"note {tasks[0].task_id}\nProgram:", f"{render_inputs(sealed[0])} -> 1",
                    CANARY, "hidden_inputs"):
        with pytest.raises(IntegrityViolation, match="refusing to send"):
            guard.complete(planted, max_tokens=8, temperature=0.0, seed=0)
    assert len(sent) == 1 and guard.refused == 4


class _RecordingHandler(BaseHTTPRequestHandler):
    """An OpenAI-compatible server that keeps everything it was sent."""

    requests: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        text = scripts.oracle(body["messages"][0]["content"], int(body.get("seed", 0)))
        reply = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 50, "completion_tokens": 8}}
        payload = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # pragma: no cover - quiet
        pass


def test_the_model_server_receives_visible_examples_and_the_grammar_and_nothing_else(tmp_path, monkeypatch):
    """Run the runner's proposal pass against a server that records every request, then audit
    what crossed the boundary: no task identifier, no sealed input, no canary, no hidden-asset
    path, no field beyond the chat-completions call, and no secret in the payload."""
    from bestsad.conditions import Condition
    from bestsad.experiments import Exp001Runner
    from bestsad.genomes import Genome
    from bestsad.kernel import KERNEL_VERSION
    from bestsad.solver import SearchBudget

    monkeypatch.setenv("BESTSAD_MODEL_API_KEY", "not-a-real-key")
    _RecordingHandler.requests = []
    httpd = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        endpoint = f"http://127.0.0.1:{httpd.server_address[1]}"
        spec = {
            "kind": "fixed_weights_llm", "identity": IDENTITY.to_record(),
            "backend": {"kind": "http", "endpoint": endpoint, "model": "scripted-coder"},
            "budget": {"max_samples": 2, "repair_rounds": 1},
        }
        runner = Exp001Runner(
            run_id="boundary", seeds=[1], model_spec=spec, artifacts_dir=tmp_path,
            per_family=1, in_family_per_family=1, adversarial_per_family=1,
            budget=SearchBudget(max_nodes=500, max_size=4, lam_max_size=2, lam_bank_cap=20,
                                bank_cap=30),
        )
        task_sets = runner._task_sets(1)
        for task_set in task_sets.values():
            for task in task_set:
                scripts.register(task)
        condition = Condition("A", "reference", Genome("G-A", 0, KERNEL_VERSION, (), "sexpr"),
                              "baseline", node_budget=500)
        path = runner._propose(condition, 1, task_sets)
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert path.exists() and _RecordingHandler.requests
    benchmark = runner._benchmark_tasks(task_sets)
    visible = {render_inputs(i) for t in benchmark for i in t.train_inputs}
    for request in _RecordingHandler.requests:
        assert request["path"] == "/v1/chat/completions"
        assert set(request["body"]) == {"model", "messages", "temperature", "max_tokens", "seed"}
        assert request["body"]["model"] == "scripted-coder"
        content = request["body"]["messages"][0]["content"]
        assert transcript_leak_findings(content, benchmark, surface="wire") == []
        for task in benchmark:
            assert task.task_id not in content
            for inputs in task.hidden_inputs:
                rendered = render_inputs(inputs)
                if rendered not in visible and len(rendered) >= 6:
                    assert rendered not in content
        assert "not-a-real-key" not in json.dumps(request["body"])
        assert "not-a-real-key" not in request["path"]
    # The guard sat in front of the wire, and the transcript says so.
    assert "guarded(http)" in json.loads(path.read_text())["backend"]
