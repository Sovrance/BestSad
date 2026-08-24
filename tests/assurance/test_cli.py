"""`bestsad assure ...` CLI (integration spec §12).

The exit codes matter as much as the output: a pipeline gating on `bestsad report --confirmatory`
must *fail*, not print a warning, when promotion dependencies do not hold.
"""

from __future__ import annotations

import json

import pytest

from bestsad.assurance import (
    AssuranceCertificate,
    AssuranceLedger,
    ClaimState,
    K0_ROOT,
    PolicyGate,
    PromotionContext,
    Warrant,
    current_roots,
    make_claim,
    make_evidence,
)
from bestsad.assurance.claims import NEGATIVE_RESULT, SEMANTIC_EQUIVALENCE
from bestsad.cli import EXIT_NOT_FOUND, EXIT_OK, EXIT_REFUSED, main


@pytest.fixture
def ledger_path(tmp_path):
    ledger = AssuranceLedger()
    roots = current_roots()
    ev = make_evidence("semantic_hash", "bsir", "hash", Warrant.FORMAL, {"x": 1})
    ledger.add_evidence(ev)
    claim = make_claim(
        SEMANTIC_EQUIVALENCE, "P equals its expansion.", producer="extractor",
        warrant=Warrant.CORROBORATED, subject_refs=("prim:sum",), evidence=[ev],
        assumptions=[K0_ROOT], source_hashes={K0_ROOT: roots.get(K0_ROOT)},
    )
    ledger.add_claim(claim)

    report_ev = make_evidence("report", "docs", "report", Warrant.EMPIRICAL, {})
    ledger.add_evidence(report_ev)
    null_claim = make_claim(
        NEGATIVE_RESULT, "EXP-001-DR does not support the target effect.",
        producer="analysis", warrant=Warrant.EMPIRICAL, evidence=[report_ev],
        detail={"run_id": "RUN-1"},
    )
    ledger.add_claim(null_claim)
    ledger.add_certificate(
        AssuranceCertificate("cert:null", null_claim.claim_id, "v", "PASS", Warrant.EMPIRICAL)
    )
    gate = PolicyGate("policy-gate")
    _verdict, decision = gate.decide(
        null_claim,
        PromotionContext(certificate=ledger.certificate_for(null_claim.claim_id)),
    )
    assert decision is not None, "fixture must produce a promotable null claim"
    ledger.apply_decision(decision)

    path = tmp_path / "ledger.json"
    ledger.save(path)
    return path, claim, null_claim


def test_assure_roots_prints_live_content_ids(capsys):
    assert main(["assure", "roots"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert K0_ROOT in payload and payload[K0_ROOT].startswith("k0:")


def test_assure_claim_show(ledger_path, capsys):
    path, claim, _ = ledger_path
    assert main(["--ledger", str(path), "assure", "claim", "show", claim.claim_id]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["claim_class"] == SEMANTIC_EQUIVALENCE


def test_assure_claim_show_missing_claim_exits_not_found(ledger_path):
    path, _, _ = ledger_path
    assert main(["--ledger", str(path), "assure", "claim", "show", "claim:nope"]) == EXIT_NOT_FOUND


def test_assure_graph_shows_dependencies(ledger_path, capsys):
    path, claim, _ = ledger_path
    assert main(["--ledger", str(path), "assure", "graph", claim.claim_id]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert any(e["to_id"] == K0_ROOT for e in payload["depends_on"])


def test_assure_stale_exits_zero_when_nothing_is_stale(ledger_path):
    path, _, _ = ledger_path
    assert main(["--ledger", str(path), "assure", "stale"]) == EXIT_OK


def test_assure_stale_exits_nonzero_once_a_root_moves(tmp_path, ledger_path, capsys):
    """A pipeline can gate on this exit code."""
    path, claim, _ = ledger_path
    data = json.loads(path.read_text())
    data["claims"][claim.claim_id]["status"] = "STALE"
    path.write_text(json.dumps(data))
    assert main(["--ledger", str(path), "assure", "stale"]) == EXIT_REFUSED
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1


def test_assure_verify_detects_a_drifted_root(tmp_path, capsys):
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"source_hashes": {K0_ROOT: "k0:stale-value"}}))
    assert main(["assure", "verify", str(artifact)]) == EXIT_REFUSED
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "STALE"
    assert K0_ROOT in payload["drifted_roots"]


def test_assure_verify_passes_a_current_artifact(tmp_path, capsys):
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"source_hashes": {K0_ROOT: current_roots().get(K0_ROOT)}}))
    assert main(["assure", "verify", str(artifact)]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["verdict"] == "CURRENT"


def test_primitive_explain(ledger_path, capsys):
    path, _, _ = ledger_path
    assert main(["--ledger", str(path), "primitive", "explain", "prim:sum"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["claims"] and payload["evidence"]


def test_report_confirmatory_succeeds_on_a_promoted_claim(ledger_path, capsys):
    path, _, _ = ledger_path
    assert main(["--ledger", str(path), "report", "RUN-1", "--confirmatory"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["promoted_claims"]


def test_report_confirmatory_hard_fails_without_a_promoted_claim(tmp_path):
    """The §12 requirement, and the reason the command exists: it hard-fails."""
    ledger = AssuranceLedger()
    ev = make_evidence("report", "docs", "r", Warrant.EMPIRICAL, {})
    ledger.add_evidence(ev)
    ledger.add_claim(make_claim(
        NEGATIVE_RESULT, "unpromoted", producer="analysis", warrant=Warrant.EMPIRICAL,
        evidence=[ev], detail={"run_id": "RUN-2"},
    ))
    path = tmp_path / "l.json"
    ledger.save(path)
    assert main(["--ledger", str(path), "report", "RUN-2", "--confirmatory"]) == EXIT_REFUSED


def test_report_without_confirmatory_still_reports(tmp_path, capsys):
    ledger = AssuranceLedger()
    ev = make_evidence("report", "docs", "r", Warrant.EMPIRICAL, {})
    ledger.add_evidence(ev)
    ledger.add_claim(make_claim(
        NEGATIVE_RESULT, "unpromoted", producer="analysis", warrant=Warrant.EMPIRICAL,
        evidence=[ev], detail={"run_id": "RUN-2"},
    ))
    path = tmp_path / "l.json"
    ledger.save(path)
    assert main(["--ledger", str(path), "report", "RUN-2"]) == EXIT_OK
