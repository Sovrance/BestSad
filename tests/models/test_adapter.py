"""The model role behind one interface (spec §17.1; ADR-0007; ADR-0022).

ADR-0007 bought the property that a real model adapter is a new component behind the same
interface and nothing else needs to change. These tests hold the interface to that: the
wrapped enumerator is the enumerator, the identity is a hash, and a spec names a model without
holding a client.
"""

from __future__ import annotations

import dataclasses

import pytest

from bestsad.experiments.exp001 import BASE_VOCABULARY
from bestsad.kernel import Kernel
from bestsad.models import (
    DEFAULT_MODEL_SPEC,
    EnumerativeAdapter,
    ModelAdapter,
    ModelIdentity,
    build_adapter,
    enumerative_identity,
    spec_identity,
    spec_requires_network,
)
from bestsad.solver import EnumerativeSynthesizer, SearchBudget
from bestsad.solver.enumerative import SYNTHESIZER_VERSION
from bestsad.tasks import generate_task

TINY = SearchBudget(max_nodes=1500, max_size=4, lam_max_size=2, lam_bank_cap=20, bank_cap=30)


def _llm_identity(**overrides) -> ModelIdentity:
    base = dict(
        model_id="test-coder-7b", kind="fixed_weights_llm", weights_digest="sha256:abc",
        tokenizer_id="tok-v1", parameter_count=7_000_000_000, context_budget_tokens=4096,
        sampling={"temperature": 0.2},
    )
    base.update(overrides)
    return ModelIdentity(**base)


# --- identity -------------------------------------------------------------------------------


def test_identity_hash_is_stable_and_covers_every_field():
    a, b = _llm_identity(), _llm_identity()
    assert a.hash() == b.hash()
    for field, value in (
        ("weights_digest", "sha256:def"),
        ("sampling", {"temperature": 0.7}),
        ("tokenizer_id", "tok-v2"),
        ("parameter_count", 8_000_000_000),
        ("mode", "fine-tuned"),
    ):
        assert _llm_identity(**{field: value}).hash() != a.hash(), field


def test_identity_record_round_trips_and_an_edited_record_is_refused():
    identity = _llm_identity()
    record = identity.to_record()
    assert record["model_identity_hash"] == identity.hash()
    assert ModelIdentity.from_record(record) == identity
    record["parameter_count"] = 1
    with pytest.raises(ValueError, match="does not hash"):
        ModelIdentity.from_record(record)


def test_identity_rejects_unknown_kinds_and_modes():
    with pytest.raises(ValueError):
        _llm_identity(kind="oracle")
    with pytest.raises(ValueError):
        _llm_identity(mode="distilled")
    with pytest.raises(ValueError):
        _llm_identity(weights_digest="")


def test_the_enumerative_stand_in_is_identified_by_its_reach():
    identity = enumerative_identity(SYNTHESIZER_VERSION)
    assert identity.kind == "enumerative_search"
    assert identity.weights_digest == SYNTHESIZER_VERSION
    assert identity.model_id == "enumerative-search-v1"
    assert not identity.is_language_model
    assert identity.tool_interface == "none"


# --- the wrapped enumerator is the enumerator -----------------------------------------------


def test_enumerative_adapter_returns_exactly_what_the_synthesizer_returns():
    task = generate_task("F2", 5)
    direct = EnumerativeSynthesizer(Kernel(), BASE_VOCABULARY, {}, budget=TINY, seed=1).solve(task)
    wrapped = EnumerativeAdapter(Kernel(), BASE_VOCABULARY, {}, budget=TINY, seed=1).solve(task)
    assert dataclasses.asdict(direct) == dataclasses.asdict(wrapped)
    assert wrapped.model_input_tokens == wrapped.model_output_tokens == wrapped.samples == 0


def test_build_adapter_defaults_to_the_enumerative_stand_in():
    adapter = build_adapter(None, kernel=Kernel(), vocabulary=BASE_VOCABULARY,
                            primitive_sigs={}, budget=TINY, seed=0)
    assert isinstance(adapter, EnumerativeAdapter)
    assert isinstance(adapter, ModelAdapter)
    assert adapter.identity == spec_identity(DEFAULT_MODEL_SPEC)
    assert adapter.contract()["tool_interface"] == "none"
    assert "ADR-0007" in adapter.contract()["claim_limitation"]


def test_build_adapter_refuses_an_unknown_kind():
    with pytest.raises(ValueError, match="unknown model kind"):
        build_adapter({"kind": "telepathy"}, kernel=Kernel(), vocabulary=BASE_VOCABULARY,
                      primitive_sigs={}, budget=TINY, seed=0)


def test_spec_identity_names_a_model_without_building_a_client():
    identity = _llm_identity()
    spec = {"kind": "fixed_weights_llm", "identity": identity.to_record(),
            "backend": {"kind": "http", "endpoint": "http://127.0.0.1:1", "model": "x"}}
    assert spec_identity(spec) == identity
    assert spec_requires_network(spec)
    assert not spec_requires_network({**spec, "backend": {"kind": "scripted", "script": "m:f"}})
    assert not spec_requires_network(None)
