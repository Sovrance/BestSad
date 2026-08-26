"""Every SRE object this implementation emits must satisfy the shared schema (ADR 0012).

The schemas set ``additionalProperties: false``, so these tests also catch the opposite
failure: a field invented here that the cross-repository contract does not define.
"""

from __future__ import annotations

import unittest

import jsonschema

from bestsad import sre


class WireConformance(unittest.TestCase):
    def test_artifact_ref(self):
        ref = sre.ArtifactRef(
            kind="bsir-graph",
            digest=sre.as_content_id("1" * 64),
            media_type="application/json",
            uri="memory://fixture",
            metadata={"note": "fixture"},
        )
        sre.validate("ArtifactRef", ref.to_wire())

    def test_fact_with_and_without_optional_fields(self):
        minimal = sre.Fact("p", "UNKNOWN", sre.Producer("analyzer.x", "0.1.0"))
        sre.validate("Fact", minimal.to_wire())

        full = sre.Fact(
            predicate="lowering_semantic_equivalence",
            status="SUPPORTED",
            producer=sre.Producer("bsld.lowering", "0.1.0"),
            inputs=(sre.as_content_id("2" * 64),),
            assumptions=("assumption:kernel-frozen",),
            evidence_refs=(sre.as_content_id("3" * 64),),
            detail={"cases": 128},
        )
        sre.validate("Fact", full.to_wire())

    def test_every_fact_status_is_accepted_by_the_schema(self):
        for status in ("SUPPORTED", "CONTRADICTED", "UNKNOWN", "AMBIGUOUS", "INDETERMINATE"):
            with self.subTest(status=status):
                sre.validate("Fact", sre.Fact("p", status, sre.Producer("a", "1")).to_wire())

    def test_counterexample(self):
        cx = sre.Counterexample(
            kind="DIVERGENT_TRAP",
            witness={"args": [1, 0]},
            left_outcome={"trap": "division_by_zero"},
            right_outcome={"value": 0},
        )
        sre.validate("Counterexample", cx.to_wire())

    def test_analyzer_result(self):
        result = sre.AnalyzerResult(
            producer=sre.Producer("bsir.equivalence", "0.1.0"),
            inputs=(sre.as_content_id("4" * 64),),
            facts=(sre.as_content_id("5" * 64),),
            coverage={"nodes_visited": 12, "nodes_total": 12},
        )
        sre.validate("AnalyzerResult", result.to_wire())

    def test_unknown_field_is_rejected_not_ignored(self):
        payload = dict(sre.Fact("p", "UNKNOWN", sre.Producer("a", "1")).to_wire())
        payload["inventedByPython"] = True
        with self.assertRaises(jsonschema.ValidationError):
            sre.validate("Fact", payload)

    def test_bare_digest_id_is_rejected_by_the_schema(self):
        # ADR 0015: the prefix is load-bearing, and the schema is where that is enforced.
        payload = dict(sre.Fact("p", "UNKNOWN", sre.Producer("a", "1")).to_wire())
        payload["id"] = "a" * 64
        with self.assertRaises(jsonschema.ValidationError):
            sre.validate("Fact", payload)


class SchemaAvailability(unittest.TestCase):
    def test_all_registered_schemas_load(self):
        for name in sre.schema.SCHEMAS:
            with self.subTest(name=name):
                self.assertIn("$id", sre.load(name))

    def test_a_missing_schema_raises_rather_than_passing_quietly(self):
        with self.assertRaises(KeyError):
            sre.load("NoSuchObject")


if __name__ == "__main__":
    unittest.main()
