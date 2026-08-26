"""SRE v0.1: the CANONICAL maturity state (ADR 0017).

CANONICAL sits between VER and CORE and means the primitive's recovered semantic signature is
*proved* equivalent to its K0 expansion. The property under test throughout is that "proved"
is enforced -- sampled agreement, however broad, does not reach this state.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from bestsad.abstraction.lifecycle import ORDER, PromotionEvidence, promote
from bestsad.assurance.integration import ASSURANCE_TO_MATURITY, MATURITY_TO_ASSURANCE

REPO_ROOT = Path(__file__).resolve().parents[2]
SRE_SCHEMA = REPO_ROOT / "schemas" / "sre" / "primitive-record-sre-v0.1.schema.json"
DELIVERED_SCHEMA = REPO_ROOT / "schemas" / "primitive_record.schema.json"

SIGNATURE = "b" * 64


def _verified_evidence(**kw) -> PromotionEvidence:
    """Evidence sufficient for VER, so that only the canonical fields are under test."""
    base = dict(
        primitive_id="prim:example",
        reuse_count=5,
        reuse_diversity=3,
        semantic_gain=0.4,
        verification_cost=1.0,
        failure_rate=0.0,
    )
    base.update(kw)
    return PromotionEvidence(**base)


class StateOrdering(unittest.TestCase):
    def test_canonical_sits_between_ver_and_core(self):
        self.assertEqual(ORDER, ("EXP", "OBS", "SPEC", "VER", "CANONICAL", "CORE"))
        self.assertLess(ORDER.index("VER"), ORDER.index("CANONICAL"))
        self.assertLess(ORDER.index("CANONICAL"), ORDER.index("CORE"))


class PromotionRequiresAProof(unittest.TestCase):
    def test_a_canonical_tier_proof_reaches_canonical(self):
        state, rationale = promote(
            None,
            _verified_evidence(
                semantic_signature=SIGNATURE, equivalence_verdict="EQUIV_CANONICAL"
            ),
        )
        self.assertEqual(state, "CANONICAL")
        self.assertIn("canonical tier", rationale)

    def test_sampled_evidence_stays_at_ver(self):
        """The central rule. EQUIV_DYNAMIC is agreement on a tested domain, and CANONICAL is a
        claim about every domain."""
        state, rationale = promote(
            None,
            _verified_evidence(
                semantic_signature=SIGNATURE, equivalence_verdict="EQUIV_DYNAMIC"
            ),
        )
        self.assertEqual(state, "VER")
        self.assertIn("EQUIV_DYNAMIC", rationale)

    def test_every_non_canonical_verdict_stays_at_ver(self):
        for verdict in ("EQUIV_SYMBOLIC", "EQUIV_DYNAMIC", "NON_EQUIV", "UNKNOWN"):
            with self.subTest(verdict=verdict):
                state, _ = promote(
                    None,
                    _verified_evidence(
                        semantic_signature=SIGNATURE, equivalence_verdict=verdict
                    ),
                )
                self.assertEqual(state, "VER")

    def test_a_signature_without_a_verdict_is_not_enough(self):
        state, _ = promote(None, _verified_evidence(semantic_signature=SIGNATURE))
        self.assertEqual(state, "VER")

    def test_a_verdict_without_a_signature_is_not_enough(self):
        state, _ = promote(
            None, _verified_evidence(equivalence_verdict="EQUIV_CANONICAL")
        )
        self.assertEqual(state, "VER")

    def test_canonical_evidence_does_not_bypass_the_earlier_gates(self):
        """A proof of identity says nothing about reuse or semantic gain, so it must not
        shortcut the states that measure those."""
        proof = dict(semantic_signature=SIGNATURE, equivalence_verdict="EQUIV_CANONICAL")
        self.assertEqual(promote(None, _verified_evidence(reuse_count=1, **proof))[0], "EXP")
        self.assertEqual(
            promote(None, _verified_evidence(reuse_diversity=1, **proof))[0], "OBS"
        )
        self.assertEqual(promote(None, _verified_evidence(semantic_gain=0.0, **proof))[0], "OBS")
        self.assertEqual(
            promote(None, _verified_evidence(failure_rate=0.5, **proof))[0], "SPEC"
        )
        self.assertEqual(
            promote(None, _verified_evidence(adversarial_incidents=1, **proof))[0], "EXP"
        )

    def test_promote_still_never_returns_core(self):
        proof = dict(semantic_signature=SIGNATURE, equivalence_verdict="EQUIV_CANONICAL")
        self.assertNotEqual(promote(None, _verified_evidence(**proof))[0], "CORE")

    def test_evidence_is_recorded_in_the_promotion_record(self):
        record = _verified_evidence(
            semantic_signature=SIGNATURE, equivalence_verdict="EQUIV_CANONICAL"
        ).to_record()
        self.assertEqual(record["semantic_signature"], SIGNATURE)
        self.assertEqual(record["equivalence_verdict"], "EQUIV_CANONICAL")


class AssuranceLadderMapping(unittest.TestCase):
    def test_canonical_maps_to_core_eligible_not_core(self):
        self.assertEqual(MATURITY_TO_ASSURANCE["CANONICAL"], "CORE_ELIGIBLE")
        self.assertEqual(ASSURANCE_TO_MATURITY["CORE_ELIGIBLE"], "CANONICAL")
        self.assertNotEqual(MATURITY_TO_ASSURANCE["CANONICAL"], "CORE")

    def test_eligibility_is_still_not_promotion(self):
        from bestsad.assurance.integration import GATE_ONLY_LIFECYCLE_STEPS, LifecycleViolation, advance_lifecycle

        self.assertIn(("CORE_ELIGIBLE", "CORE"), GATE_ONLY_LIFECYCLE_STEPS)
        with self.assertRaises(LifecycleViolation):
            advance_lifecycle("CORE_ELIGIBLE", "CORE", actor_is_gate=False)


class SchemaExtension(unittest.TestCase):
    """ADR 0017: the rule is enforced by the schema too, not only by `promote`."""

    def setUp(self):
        self.schema = json.loads(SRE_SCHEMA.read_text(encoding="utf-8"))

    def test_the_delivered_schema_is_not_edited(self):
        delivered = json.loads(DELIVERED_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            delivered["properties"]["maturity"]["enum"],
            ["EXP", "OBS", "SPEC", "VER", "CORE"],
            "the delivered v0.2 schema must keep its original maturity enum",
        )

    def test_canonical_with_a_proof_validates(self):
        jsonschema.validate(
            {
                "maturity": "CANONICAL",
                "semantic_signature": SIGNATURE,
                "equivalence_verdict": "EQUIV_CANONICAL",
            },
            self.schema,
        )

    def test_a_hand_written_canonical_record_without_a_proof_is_refused(self):
        """The duplication with `promote` is the point: a record that never went through the
        promotion predicate cannot claim the state either."""
        for payload in (
            {"maturity": "CANONICAL"},
            {"maturity": "CANONICAL", "semantic_signature": SIGNATURE},
            {
                "maturity": "CANONICAL",
                "semantic_signature": SIGNATURE,
                "equivalence_verdict": "EQUIV_DYNAMIC",
            },
        ):
            with self.subTest(payload=sorted(payload)):
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(payload, self.schema)

    def test_a_prefixed_signature_is_refused(self):
        """ADR 0015: primitive records hold BestSad-native bare hex, not SRE content ids."""
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(
                {
                    "maturity": "CANONICAL",
                    "semantic_signature": f"sha256:{SIGNATURE}",
                    "equivalence_verdict": "EQUIV_CANONICAL",
                },
                self.schema,
            )

    def test_v02_states_still_validate(self):
        for state in ("EXP", "OBS", "SPEC", "VER", "CORE"):
            with self.subTest(state=state):
                jsonschema.validate({"maturity": state}, self.schema)


if __name__ == "__main__":
    unittest.main()


class PrimitivesCanHoldTheState(unittest.TestCase):
    """A promotion result no `Primitive` can carry is a state the system computes and then
    cannot store. `promote` returning CANONICAL therefore requires the registry to admit it."""

    def test_registry_maturities_match_the_lifecycle_order(self):
        from bestsad.genomes.registry import MATURITIES

        self.assertEqual(MATURITIES, ORDER)

    def test_a_primitive_can_be_constructed_at_canonical(self):
        from bestsad.kernel import INT, app, const_int, var
        from bestsad.genomes.registry import Primitive

        primitive = Primitive(
            primitive_id="prim:inc",
            params=("n",),
            expansion=app("add", var("n"), const_int(1)),
            input_types=(INT,),
            output_type=INT,
            maturity="CANONICAL",
        )
        self.assertEqual(primitive.maturity, "CANONICAL")

    def test_a_canonical_record_validates_against_the_sre_extension(self):
        from bestsad.kernel import INT, app, const_int, var
        from bestsad.genomes.registry import Primitive

        record = Primitive(
            primitive_id="prim:inc",
            params=("n",),
            expansion=app("add", var("n"), const_int(1)),
            input_types=(INT,),
            output_type=INT,
            maturity="CANONICAL",
        ).to_record("k0-v1.0.0")
        record["semantic_signature"] = SIGNATURE
        record["equivalence_verdict"] = "EQUIV_CANONICAL"
        jsonschema.validate(record, json.loads(SRE_SCHEMA.read_text(encoding="utf-8")))

    def test_an_unknown_maturity_is_still_rejected(self):
        from bestsad.kernel import INT, app, const_int, var
        from bestsad.genomes.registry import GenomeInvariantViolation, Primitive

        with self.assertRaises(GenomeInvariantViolation):
            Primitive(
                primitive_id="prim:inc",
                params=("n",),
                expansion=app("add", var("n"), const_int(1)),
                input_types=(INT,),
                output_type=INT,
                maturity="SUPERB",
            )
