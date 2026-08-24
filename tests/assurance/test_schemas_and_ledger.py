"""Assurance records conform to the shipped schemas (§3.1), and the ledger holds its invariants."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from bestsad.assurance import (
    AssuranceCertificate,
    AssuranceLedger,
    ClaimState,
    DependencyEdge,
    DependencyType,
    K0_ROOT,
    LedgerViolation,
    PolicyGate,
    PromotionContext,
    Warrant,
    current_roots,
    make_claim,
    make_evidence,
    missing_evidence_kinds,
    primitive_envelope,
    genome_envelope,
    experiment_envelope,
)
from bestsad.assurance.claims import CLAIM_CLASSES, SEMANTIC_EQUIVALENCE
from bestsad.genomes import Genome, Primitive
from bestsad.kernel import INT, KERNEL_VERSION, TList, app, const_int, lam, var

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


def load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


def _primitive() -> Primitive:
    body = app("fold", lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
               const_int(0), var("xs"))
    return Primitive("prim:sum", ("xs",), body, (TList(INT),), INT, origin="utility")


def _claim():
    ev = make_evidence("semantic_hash", "bsir", "canonical hash", Warrant.FORMAL, {"a": 1})
    return make_claim(
        SEMANTIC_EQUIVALENCE, "P equals its K0 expansion.", producer="extractor",
        warrant=Warrant.CORROBORATED, subject_refs=("prim:sum",), evidence=[ev],
        assumptions=[K0_ROOT], source_hashes={K0_ROOT: "k0:abc"},
    ), ev


def test_claim_record_conforms():
    claim, _ = _claim()
    jsonschema.validate(claim.to_record(), load("claim"))


def test_evidence_record_conforms():
    _, ev = _claim()
    jsonschema.validate(ev.to_record(), load("evidence"))


def test_dependency_edge_record_conforms():
    edge = DependencyEdge("a", "b", DependencyType.SEMANTIC_ROOT)
    jsonschema.validate(edge.to_record(), load("dependency-edge"))


def test_assumption_records_conform():
    schema = load("assumption")
    for assumption in current_roots().assumptions().values():
        jsonschema.validate(assumption.to_record(), schema)


def test_certificate_record_conforms():
    cert = AssuranceCertificate("cert:1", "claim:1", "verifier", "PASS", Warrant.FORMAL)
    jsonschema.validate(cert.to_record(), load("assurance-certificate"))


def test_promotion_decision_record_conforms():
    claim, ev = _claim()
    ledger = AssuranceLedger()
    ledger.add_evidence(ev)
    ledger.add_claim(claim)
    ledger.add_certificate(AssuranceCertificate("cert:1", claim.claim_id, "v", "PASS",
                                                Warrant.CORROBORATED))
    gate = PolicyGate("policy-gate")
    roots = current_roots()
    _verdict, decision = gate.decide(
        claim,
        PromotionContext(
            certificate=ledger.certificate_for(claim.claim_id),
            active_assumptions={K0_ROOT: "k0:abc"},
            current_source_hashes={K0_ROOT: "k0:abc"},
        ),
    )
    assert decision is not None
    jsonschema.validate(decision.to_record(), load("promotion-decision"))


def test_every_claim_class_is_representable_in_the_schema():
    """The schema's enum and the code's registry must not drift apart."""
    schema_classes = set(load("claim")["properties"]["claim_class"]["enum"])
    assert schema_classes == set(CLAIM_CLASSES)


def test_every_lifecycle_state_is_representable_in_the_schema():
    schema_states = set(load("claim")["properties"]["status"]["enum"])
    assert schema_states == {s.value for s in ClaimState}


def test_every_warrant_is_representable_in_the_schema():
    schema_warrants = set(load("evidence")["properties"]["warrant"]["enum"])
    assert schema_warrants == {w.value for w in Warrant}


# --- envelopes (§3) ------------------------------------------------------------------------------


def test_assurance_envelopes_do_not_replace_the_existing_records():
    """§3: "Do not replace the existing genome/primitive/experiment schemas." """
    primitive = _primitive()
    roots = current_roots()
    record = primitive.to_record(KERNEL_VERSION)
    jsonschema.validate(record, load("primitive_record"))
    envelope = primitive_envelope(primitive, roots=roots)
    assert "assurance" not in record, "the envelope sits alongside, not inside"
    assert envelope["kernel_content_id"] == roots.get(K0_ROOT)
    assert envelope["declared_maturity"] == primitive.maturity

    genome = Genome("G", 1, KERNEL_VERSION, (primitive,), "sexpr")
    jsonschema.validate(genome.to_record(), load("language_genome"))
    assert genome_envelope(genome, roots=roots)["semantic_root"] == roots.get(K0_ROOT)

    exp = experiment_envelope(roots=roots, preregistration_content_id="p",
                              condition_manifest_id="c", compute_ledger_id="l")
    assert exp["preregistration_content_id"] == "p"


def test_missing_evidence_kinds_is_reported_per_claim_class():
    claim, ev = _claim()
    missing = missing_evidence_kinds(claim, [ev])
    assert "differential_test" in missing
    assert "semantic_hash" not in missing


# --- ledger invariants -----------------------------------------------------------------------------


def test_a_claim_cannot_be_edited_only_superseded():
    """Content-addressed identity: an edited claim is a different claim (§1.6)."""
    ledger = AssuranceLedger()
    claim, ev = _claim()
    ledger.add_evidence(ev)
    ledger.add_claim(claim)
    with pytest.raises(LedgerViolation, match="already exists"):
        ledger.add_claim(claim)


def test_evidence_cannot_be_swapped_under_a_recorded_id():
    from dataclasses import replace

    ledger = AssuranceLedger()
    _, ev = _claim()
    ledger.add_evidence(ev)
    tampered = replace(ev, content_hash="different")
    with pytest.raises(LedgerViolation, match="different content hash"):
        ledger.add_evidence(tampered)


def test_a_certificate_for_an_unknown_claim_is_refused():
    ledger = AssuranceLedger()
    with pytest.raises(LedgerViolation, match="unknown claim"):
        ledger.add_certificate(
            AssuranceCertificate("cert:x", "claim:nope", "v", "PASS", Warrant.FORMAL)
        )


def test_a_certificate_on_disk_does_not_imply_trust():
    """§1.7: "A certificate file existing on disk never implies the claim is trusted." """
    from bestsad.assurance import evaluate

    ledger = AssuranceLedger()
    claim, ev = _claim()
    ledger.add_evidence(ev)
    ledger.add_claim(claim)
    cert = AssuranceCertificate("cert:1", claim.claim_id, "v", "PASS", Warrant.CORROBORATED)
    ledger.add_certificate(cert)
    # Certificate present and passing — but no gate actor, so promotion is still refused.
    verdict = evaluate(claim, PromotionContext(certificate=cert,
                                               active_assumptions={K0_ROOT: "k0:abc"},
                                               current_source_hashes={K0_ROOT: "k0:abc"}))
    assert not verdict.promotable
    assert any("no policy gate actor" in b for b in verdict.blockers)


def test_history_survives_invalidation_and_the_ledger_round_trips(tmp_path):
    ledger = AssuranceLedger()
    claim, ev = _claim()
    ledger.add_evidence(ev)
    ledger.add_claim(claim)
    ledger.invalidate_from(K0_ROOT, reason="kernel bumped")
    assert ledger.claims[claim.claim_id].status is ClaimState.STALE
    assert ledger.stale()

    path = ledger.save(tmp_path / "ledger.json")
    data = json.loads(path.read_text())
    assert claim.claim_id in data["claims"]
    assert any(e["kind"] == "invalidation_propagated" for e in data["events"])
    # The proposal event is still there: history is not rewritten.
    assert any(e["kind"] == "claim_proposed" for e in data["events"])


def test_explain_gives_a_path_from_claim_to_roots():
    """§1.7: "Every promoted claim has an explainable dependency path to evidence and active
    assumptions." """
    ledger = AssuranceLedger()
    claim, ev = _claim()
    ledger.add_evidence(ev)
    ledger.add_claim(claim)
    explanation = ledger.explain(claim.claim_id)
    assert explanation["claim"]["claim_id"] == claim.claim_id
    assert explanation["evidence"] and explanation["evidence"][0]["kind"] == "semantic_hash"
    assert K0_ROOT in explanation["roots"]
    assert explanation["history"]
