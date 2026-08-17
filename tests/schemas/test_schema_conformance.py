"""The records the instrument emits must validate against the shipped JSON Schemas.

The schemas in `schemas/` are the v0.2 data contracts (spec §30). They are only worth anything
if the code actually emits conforming records, which is what this suite checks — schema drift
otherwise shows up as an unreadable artifact months later.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from bestsad.abstraction import PromotionEvidence
from bestsad.conditions import ComputeLedger, build_conditions
from bestsad.causal import PrimitiveEffect, concentration_test
from bestsad.evaluator import manifest_for
from bestsad.genomes import Genome, Primitive
from bestsad.kernel import INT, KERNEL_VERSION, TList, app, const_int, lam, var
from bestsad.stats import Interval, Preregistration
from bestsad.tasks import held_out_set

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


def load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


def _registry():
    """Resolve the relative `$ref`s between the shipped schemas (preregistration references
    control_condition)."""
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for path in SCHEMA_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        resources.append(
            (path.name, Resource.from_contents(schema, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def validate(instance, schema) -> None:
    jsonschema.Draft202012Validator(schema, registry=_registry()).validate(instance)


def _primitive(name: str = "prim:sum") -> Primitive:
    body = app(
        "fold",
        lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
        const_int(0),
        var("xs"),
    )
    return Primitive(name, ("xs",), body, (TList(INT),), INT, origin="utility")


def test_all_schemas_are_valid_json_schema():
    for path in SCHEMA_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)


def test_primitive_record_conforms():
    record = _primitive().to_record(KERNEL_VERSION)
    jsonschema.validate(record, load("primitive_record"))
    assert record["maturity"] in ("EXP", "OBS", "SPEC", "VER", "CORE")


def test_language_genome_record_conforms():
    genome = Genome("G-D", 1, KERNEL_VERSION, (_primitive(),), "compact")
    genome.record_fitness({"verified_solve_rate": 0.42, "primitive_reuse_rate": 1.5})
    jsonschema.validate(genome.to_record(), load("language_genome"))


def test_compute_ledger_record_conforms():
    ledger = ComputeLedger("run-1", "D", 3, search_nodes=1000, kernel_steps=50_000,
                           evolution_nodes=400)
    record = ledger.to_record(compression_ratio=1.8, capability_delta=0.03)
    jsonschema.validate(record, load("compute_ledger"))
    # The paired outcome is required by the schema, which is the §21.6 rule made structural.
    assert set(load("compute_ledger")["properties"]["paired_outcomes"]["required"]) == {
        "compression_ratio", "capability_delta"
    }


def test_control_condition_records_conform():
    plane = build_conditions(
        kernel_version=KERNEL_VERSION,
        random_primitives=[_primitive("prim:r0")],
        mdl_primitives=[_primitive("prim:m0")],
        utility_primitives=[_primitive("prim:u0")],
        expert_primitives=[_primitive("prim:g0")],
        baseline_node_budget=50_000,
        evolution_nodes=10_000,
    )
    schema = load("control_condition")
    for condition in plane.values():
        jsonschema.validate(condition.to_record(), schema)


def test_benchmark_manifest_conforms():
    task_set = held_out_set(1, per_family=1)
    manifest = manifest_for(task_set, "frozen_hidden", ["F9", "F10", "F11", "F12"])
    jsonschema.validate(manifest.to_dict(), load("benchmark_manifest"))


def test_preregistration_record_conforms():
    prereg = Preregistration(
        experiment_id="EXP-001-DR",
        primary_endpoint="verified_ood_solve_rate_per_compute",
        conditions=tuple(
            {
                "condition_id": cid,
                "role": "treatment" if cid in ("D", "E") else "confound_control"
                if cid in ("F", "H", "I") else "reference",
                "genome_id": f"G-{cid}",
                "description": f"condition {cid}",
            }
            for cid in "ABCDEFGHI"
        ),
        seeds_per_condition=8,
        minimum_interesting_effect={"absolute_solve_rate_points": 0.05},
        multiple_comparison_control={
            "method": "benjamini_hochberg",
            "level": 0.05,
            "family": ["raw_verified_solve_rate", "search_nodes"],
        },
        stopping_rule="fixed 8 seeds, no interim analysis",
        declared_outcome_interpretations={
            "positive": "proceed to S4",
            "efficiency_only": "report as an efficiency result",
            "null_result": "record in the negative-result ledger",
            "h0_consistent": "record as consistent with H0",
        },
        # `variance_source_run` is required by the schema, and rightly so: §26.8 says the
        # power analysis must use variance *measured* in E0, so the pre-registration has to name
        # which run that variance came from.
        power_analysis={
            "variance_source_run": "E0-smoke-2026-08-17",
            "target_power": 0.8,
            "alpha": 0.05,
            "framing": "superiority",
            "powered": True,
        },
        kernel_version=KERNEL_VERSION,
    ).commit()
    validate(prereg.to_record(), load("preregistration"))


def test_causal_attribution_record_conforms():
    from bestsad.causal import AttributionTable

    table = AttributionTable("EXP-001-DR")
    table.effects = [
        PrimitiveEffect(
            primitive_id="prim:u0",
            semantic_hash="abc123",
            direct_effect=Interval(0.04, 0.01, 0.07),
            indirect_effect=Interval(0.01, -0.01, 0.03),
            cross_family_reuse=3,
            shortcut_shaped=False,
            compression_shaped=False,
            semantic_gain_v2=12.5,
        )
    ]
    table.concentration = concentration_test(table.effects)
    jsonschema.validate(table.to_record(), load("causal_attribution"))


def test_experiment_manifest_conforms():
    manifest = {
        "experiment_id": "EXP-001-DR",
        "hypothesis_ids": ["H2", "H13", "H14", "H15"],
        "kernel_version": KERNEL_VERSION,
        "benchmark_manifest_id": "bm-test",
        "conditions": [{"condition_id": cid} for cid in "ABCDEFGHI"],
        "seeds": [1, 2, 3],
        "code_revision": "0" * 40,
        "environment_hash": "e" * 64,
        "primary_metric": "verified_ood_solve_rate_per_compute",
        "model_id": "enumerative-search-v1",
        "secondary_metrics": ["raw_verified_solve_rate"],
    }
    jsonschema.validate(manifest, load("experiment_manifest"))


def test_promotion_evidence_covers_the_spec_11_1_list():
    """Spec §11.1's evidence list is also the answer to open question 13, so every item is
    recorded even when it does not gate the current step."""
    record = PromotionEvidence("prim:u0").to_record()
    for field in ("reuse_count", "reuse_diversity", "cross_family_utility",
                  "cross_model_transfer", "semantic_gain", "verification_cost",
                  "failure_rate", "runtime_benefit", "alias_collisions",
                  "adversarial_incidents"):
        assert field in record
