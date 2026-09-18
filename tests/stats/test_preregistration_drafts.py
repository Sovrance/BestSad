"""The EXP-002..005 pre-registration drafts (roadmap §3; ADR-0022).

A draft fixes in advance everything the roadmap fixes — thresholds, endpoints, outcome
interpretations — and leaves a `<<FILL>>` wherever a value cannot exist until a model is chosen.
These tests hold the drafts to that: the thresholds are the roadmap's numbers, the placeholders
are the ones ADR-0022 names, the files on disk are what the script produces, and the gate
refuses to certify anything against a draft.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from bestsad.stats import ClaimRequest, Preregistration, PreregistrationError, ReportGate, ReportRefused

REPO = Path(__file__).resolve().parents[2]
DRAFTS = REPO / "docs" / "preregistrations"
SCRIPT = REPO / "scripts" / "draft_preregistration.py"
IDS = ("EXP-002", "EXP-003", "EXP-004", "EXP-005")


def _script():
    spec = importlib.util.spec_from_file_location("draft_preregistration", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(experiment_id: str) -> Preregistration:
    return Preregistration.load(DRAFTS / f"{experiment_id}.draft.json")


@pytest.mark.parametrize("experiment_id", IDS)
def test_a_draft_is_incomplete_for_exactly_the_reasons_adr_0022_names(experiment_id):
    draft = _load(experiment_id)
    complete, missing = draft.is_complete()
    assert not complete
    assert set(missing) == {"seeds_per_condition (>= 2)", "stopping_rule",
                            "unfilled <<FILL>> placeholders"}
    blob = json.dumps(draft.to_record())
    for placeholder in ("model_identity_hash", "evaluator_image_digest", "variance_source_run"):
        assert placeholder in blob
    assert draft.model_identity["model_identity_hash"].startswith("<<FILL>>")


@pytest.mark.parametrize("experiment_id", IDS)
def test_a_draft_is_not_committed_and_the_gate_refuses_it(experiment_id):
    draft = _load(experiment_id)
    assert draft.preregistration_hash == "" and draft.timestamp_utc == ""
    with pytest.raises(PreregistrationError):
        draft.verify()
    request = ClaimRequest(
        experiment_id=experiment_id, claim_kind="capability",
        conditions_run=draft.condition_ids(),
        treatment_beats={"F": True, "H": True, "I": True},
        compression_ratio=1.0, capability_delta=0.1, fdr_controlled=True,
        concentration_test_passed=True,
    )
    # An uncommitted document is refused before any claim is examined: the gate's first act is
    # `verify()`, and a draft has no hash to verify.
    with pytest.raises((ReportRefused, PreregistrationError)):
        ReportGate(draft).certify(request)


@pytest.mark.parametrize("experiment_id", IDS)
def test_a_draft_conforms_to_the_preregistration_schema(experiment_id):
    from tests.schemas.test_schema_conformance import _registry, load

    record = json.loads((DRAFTS / f"{experiment_id}.draft.json").read_text())
    jsonschema.Draft202012Validator(load("preregistration"), registry=_registry()).validate(record)


def test_the_files_on_disk_are_what_the_script_produces():
    rendered = _script().render_all()
    assert set(rendered) == {f"{i}.draft.{ext}" for i in IDS for ext in ("json", "md")}
    for name, text in rendered.items():
        assert (DRAFTS / name).read_text() == text, f"{name} drifted; regenerate it"


def test_exp_002_is_exp_001_with_a_model_and_the_roadmaps_thresholds():
    draft = _load("EXP-002")
    dry_run = json.loads((DRAFTS / "EXP-001-DR.json").read_text())
    assert list(draft.conditions) == dry_run["conditions"]
    assert draft.minimum_interesting_effect["absolute_solve_rate_points"] == 0.05
    assert "fixed_flops" in draft.primary_endpoint
    assert {"direct_reuse_rate", "twin_gap"} <= set(draft.secondary_endpoints)
    assert draft.model_identity["kind"] == "fixed_weights_llm"
    assert draft.model_identity["tool_interface"] == "none"
    assert "EXP-004" in draft.declared_outcome_interpretations["positive"]
    assert "transcript leak" in " ".join(draft.exclusion_criteria)


def test_exp_003_pre_registers_the_mediation_share():
    draft = _load("EXP-003")
    assert draft.minimum_interesting_effect["mediation_share_minimum"] == 0.5
    controls = [c for c in draft.conditions if c["controls_confound"] == "C3_scaffolding"]
    assert len(controls) == 6


def test_exp_004_requires_both_transfer_and_reuse():
    draft = _load("EXP-004")
    mie = draft.minimum_interesting_effect
    assert mie["transfer_delta_minimum"] == 0.05 and mie["direct_reuse_rate_minimum"] > 0
    assert {c["condition_id"] for c in draft.conditions} >= {"M1", "M2", "M3", "F", "H", "I"}
    assert "direct_reuse_rate" in draft.secondary_endpoints


def test_exp_005_expects_no_correlation():
    draft = _load("EXP-005")
    assert draft.minimum_interesting_effect["expected_correlation_r"] == 0.0
    assert all(c["introduces_new_semantics"] is False for c in draft.conditions)
