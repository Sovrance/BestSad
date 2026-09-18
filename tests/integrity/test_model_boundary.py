"""Gate G1, extended for a language model in the model role (roadmap §6; ADR-0022).

The candidate sandbox stops a *process* reaching the hidden assets. A model in the loop adds two
surfaces the sandbox cannot see — the prompt and the completion — and one channel it must
still close: the network. Each test attempts the vector and requires it to fail or be caught.
"""

from __future__ import annotations

import dataclasses
import math

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
