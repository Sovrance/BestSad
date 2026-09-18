"""The fixed-weights language model adapter (ADR-0022, EXP-002 readiness).

Everything here runs against scripted backends, so the tests prove the *loop* — prompt, parse,
typecheck, visible-example check, feedback, budget — and the transcript machinery, not any
model's ability. That is deliberate: the instrument must be shown to score a proposer correctly
before a proposer worth scoring is put behind it.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bestsad.bsir import get_projection
from bestsad.experiments.exp001 import BASE_VOCABULARY
from bestsad.genomes import Primitive
from bestsad.kernel import INT, Kernel, TList, app, lam, var
from bestsad.models import (
    HTTPBackend,
    LLMAdapter,
    ModelIdentity,
    RecordingBackend,
    ReplayBackend,
    SampleBudget,
    ScriptedBackend,
    Transcript,
    TranscriptMiss,
    build_adapter,
)
from bestsad.models.llm import (
    build_backend,
    extract_program_text,
    projection_for,
    render_inputs,
    resolve_script,
    scaffolding_policy,
)
from bestsad.solver import SearchBudget
from bestsad.tasks import generate_task

from . import scripts

IDENTITY = ModelIdentity(
    model_id="scripted-coder", kind="fixed_weights_llm", weights_digest="sha256:0",
    tokenizer_id="surface-token-proxy", parameter_count=7_000_000_000,
    context_budget_tokens=8192,
)


def _register(task) -> None:
    scripts.register(task)


def _adapter(backend, *, projection="sexpr", primitive_sigs=None, budget=None, seed=1,
             scaffolding=None, worked=(), identity=IDENTITY):
    return LLMAdapter(
        kernel=Kernel(), projection=projection_for(projection, primitive_sigs),
        vocabulary=BASE_VOCABULARY, primitive_sigs=primitive_sigs, identity=identity,
        backend=backend, budget=budget or SampleBudget(max_samples=4, repair_rounds=2),
        kernel_fuel=4000, seed=seed, scaffolding=scaffolding, worked_examples=worked,
    )


@pytest.fixture
def f9():
    task = generate_task("F9", 3)
    _register(task)
    return task


# --- the loop -------------------------------------------------------------------------------


def test_a_correct_proposal_is_accepted_on_the_first_sample(f9):
    result = _adapter(ScriptedBackend(scripts.oracle)).solve(f9)
    assert result.solved_train and result.program is not None
    assert result.samples == 1 and result.parse_failures == 0
    assert result.model_input_tokens > 0 and result.model_output_tokens > 0
    assert result.tokens_at_solve == result.model_input_tokens + result.model_output_tokens
    assert result.program.body == f9.reference.body


def test_a_wrong_proposal_gets_its_failing_visible_example_back(f9):
    seen: list[str] = []

    def spy(prompt, seed):
        seen.append(prompt)
        return scripts.wrong_then_right(prompt, seed)

    result = _adapter(ScriptedBackend(spy)).solve(f9)
    assert result.solved_train and result.samples == 2 and result.evaluations == 2
    assert "was wrong on" in seen[1]
    # Only visible inputs may ever be fed back.
    for inputs in f9.hidden_inputs:
        assert render_inputs(inputs) not in seen[1].split("Your answer")[1]


def test_unparseable_output_counts_as_a_parse_failure_and_exhausts_the_budget(f9):
    result = _adapter(ScriptedBackend(scripts.gibberish)).solve(f9)
    assert result.program is None and not result.solved_train
    assert result.samples == 4 and result.parse_failures == 4 and result.evaluations == 0


def test_feedback_is_bounded_by_repair_rounds_then_resets():
    task = generate_task("F9", 3)
    seen: list[str] = []
    backend = ScriptedBackend(lambda p, s: seen.append(p) or "(length xs)")
    _adapter(backend, budget=SampleBudget(max_samples=5, repair_rounds=2)).solve(task)
    counts = [p.count("Your answer") for p in seen]
    assert counts == [0, 1, 2, 0, 1]


def test_the_compact_projection_is_parsed_back_to_the_same_term(f9):
    result = _adapter(ScriptedBackend(scripts.oracle), projection="compact").solve(f9)
    assert result.solved_train and result.program.body == f9.reference.body


def test_a_genome_primitive_round_trips_through_the_compact_projection():
    body = app("fold", lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
               var("z"), var("xs"))
    prim = Primitive("prim:sumfrom", ("z", "xs"), body, (INT, TList(INT)), INT)
    projection = projection_for("compact", {prim.primitive_id: prim.signature})
    term = app("prim:sumfrom", app("add", var("x"), var("x")), var("xs"))
    assert projection.parse(projection.render(term)) == term


def test_a_model_that_does_not_support_the_projection_is_refused():
    identity = ModelIdentity(model_id="m", kind="fixed_weights_llm", weights_digest="d",
                             tokenizer_id="t", supported_projections=("sexpr",))
    with pytest.raises(ValueError, match="does not support projection"):
        _adapter(ScriptedBackend(scripts.oracle), projection="compact", identity=identity)


def test_context_budget_stops_sampling_rather_than_truncating(f9):
    tiny = ModelIdentity(model_id="m", kind="fixed_weights_llm", weights_digest="d",
                         tokenizer_id="t", context_budget_tokens=10)
    result = _adapter(ScriptedBackend(scripts.oracle), identity=tiny).solve(f9)
    assert result.samples == 0 and result.program is None


# --- scaffolding delivery (condition H) --------------------------------------------------------


def test_grammar_is_padded_to_the_scaffolding_target_with_neutral_filler(f9):
    plain = _adapter(ScriptedBackend(scripts.oracle))
    natural = plain.delivered_grammar_tokens()
    padded = _adapter(ScriptedBackend(scripts.oracle),
                      scaffolding={"grammar_description_tokens": natural + 57})
    assert padded.delivered_grammar_tokens() == natural + 57
    assert padded.contract()["delivered_grammar_tokens"] == natural + 57
    # A target below the natural size never truncates.
    short = _adapter(ScriptedBackend(scripts.oracle),
                     scaffolding={"grammar_description_tokens": 3})
    assert short.delivered_grammar_tokens() == natural


def test_worked_examples_are_limited_to_the_scaffolded_count():
    worked = [(t, t.reference) for t in (generate_task("F1", 1), generate_task("F2", 1))]
    adapter = _adapter(ScriptedBackend(scripts.oracle), worked=worked,
                       scaffolding={"worked_example_count": 1})
    assert adapter.prompt_header().count("Example task") == 1
    assert adapter.contract()["worked_examples"] == 2


def test_scaffolding_policy_describes_the_models_retry_and_decoding():
    policy = scaffolding_policy({"kind": "fixed_weights_llm", "budget": {"max_samples": 6,
                                                                          "repair_rounds": 1}})
    assert "6 samples" in policy["retry_policy"] and "1 failures" in policy["retry_policy"]
    assert "no grammar-constrained decoding" in policy["decoding_constraints"]
    assert scaffolding_policy(None) == {}


# --- transcripts --------------------------------------------------------------------------------


def test_a_recorded_transcript_replays_to_an_identical_result(f9, tmp_path):
    transcript = Transcript(IDENTITY.hash())
    live = _adapter(RecordingBackend(ScriptedBackend(scripts.wrong_then_right), transcript))
    first = live.solve(f9)
    assert len(transcript.exchanges) == 2
    path = transcript.save(tmp_path / "t.json")

    replayed = _adapter(ReplayBackend(Transcript.load(path))).solve(f9)
    assert replayed.program == first.program
    assert replayed.samples == first.samples
    assert replayed.model_input_tokens == first.model_input_tokens
    assert replayed.model_output_tokens == first.model_output_tokens


def test_a_replay_never_substitutes_a_completion_it_did_not_record(f9):
    transcript = Transcript(IDENTITY.hash())
    _adapter(RecordingBackend(ScriptedBackend(scripts.oracle), transcript)).solve(f9)
    other = generate_task("F10", 4)
    with pytest.raises(TranscriptMiss):
        _adapter(ReplayBackend(transcript)).solve(other)


def test_a_tampered_transcript_is_refused_on_load(tmp_path):
    transcript = Transcript("h")
    transcript.record(prompt="p", completion=ScriptedBackend(scripts.oracle).complete(
        "p", max_tokens=1, temperature=0, seed=0), context={"task_id": "t", "sample_index": 0})
    path = transcript.save(tmp_path / "t.json")
    data = json.loads(path.read_text())
    data["exchanges"][0]["response"] = "(add 1 2)"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="does not hash"):
        Transcript.load(path)


# --- specs and backends -----------------------------------------------------------------------


def test_build_adapter_from_a_json_spec_with_a_scripted_backend(f9):
    spec = {
        "kind": "fixed_weights_llm",
        "identity": IDENTITY.to_record(),
        "backend": {"kind": "scripted", "script": "tests.models.scripts:oracle"},
        "budget": {"max_samples": 2},
    }
    adapter = build_adapter(spec, kernel=Kernel(), vocabulary=BASE_VOCABULARY, primitive_sigs={},
                            budget=SearchBudget(), seed=1, projection_name="sexpr")
    assert isinstance(adapter, LLMAdapter)
    assert adapter.solve(f9).solved_train
    contract = adapter.contract()
    assert contract["backend"] == "scripted" and contract["requires_network"] is False
    assert contract["sample_budget"]["max_samples"] == 2


def test_backend_and_script_resolution_fail_loudly():
    with pytest.raises(ValueError, match="unknown backend kind"):
        build_backend({"kind": "carrier-pigeon"})
    with pytest.raises(ValueError, match="module:function"):
        resolve_script("nocolon")
    with pytest.raises(ValueError):
        SampleBudget(max_samples=0)


def test_extract_program_text_handles_fences_labels_and_noise():
    assert extract_program_text("Program: (add x 1)\nexplanation") == "(add x 1)"
    assert extract_program_text("Sure!\n```lisp\n(add x 1)\n```\n") == "(add x 1)"
    assert extract_program_text("\n\n  answer = (add x 1)  ") == "(add x 1)"
    assert extract_program_text("") == ""


class _Handler(BaseHTTPRequestHandler):
    usage = True

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][0]["content"]
        text = scripts.oracle(prompt, int(body.get("seed", 0)))
        reply = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
        if type(self).usage:
            reply["usage"] = {"prompt_tokens": 123, "completion_tokens": 45}
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
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_http_backend_speaks_the_openai_compatible_protocol(server, f9, monkeypatch):
    monkeypatch.delenv("BESTSAD_MODEL_API_KEY", raising=False)
    _Handler.usage = True
    backend = HTTPBackend(server, "scripted-coder")
    assert backend.requires_network
    result = _adapter(backend).solve(f9)
    assert result.solved_train
    assert (result.model_input_tokens, result.model_output_tokens) == (123, 45)


def test_http_backend_falls_back_to_proxy_counts_and_says_so(server, f9):
    _Handler.usage = False
    try:
        completion = HTTPBackend(server, "m").complete("hello", max_tokens=8,
                                                       temperature=0, seed=1)
    finally:
        _Handler.usage = True
    assert completion.usage_source == "proxy" and completion.input_tokens == 1
