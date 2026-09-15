"""BEST-VERIF-03: external prover results become evidence with external provenance.

The adapter accepts the BestSad SMT analyzer result, a Kani JSON report of a stated shape, and a
generic `{tool, version, verdict, artifact_sha256, ...}` record. Each becomes an `EvidenceObject`
with `warrant=FORMAL` and `is_external=True`; an inconclusive result becomes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from bestsad.assurance import Warrant
from bestsad.kernel.spec import KERNEL_VERSION_HASH
from bestsad.verify import (
    ExternalResultError,
    from_generic,
    from_kani_report,
    from_symbolic_result,
    to_evidence,
)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
EVIDENCE_SCHEMA = json.loads((SCHEMA_DIR / "evidence.schema.json").read_text())

KANI_REPORT = {
    "kani_version": "0.55.0",
    "unwind": 8,
    "harnesses": [
        {"name": "k0rs::ops::add_is_total", "status": "SUCCESS"},
        {"name": "k0rs::ops::int_bound_traps", "status": "SUCCESS"},
    ],
}


def _generic(**overrides):
    payload = {
        "tool": "alive2", "version": "2026.1", "verdict": "proved", "artifact_sha256": "ef" * 32,
        "scope": {"transform": "instcombine"}, "assumptions": ["bounded_bitwidth_64"],
        "kernel_version_hash": KERNEL_VERSION_HASH,
    }
    payload.update(overrides)
    return from_generic(payload)


def test_a_proved_result_becomes_formal_external_evidence():
    evidence = to_evidence(_generic())
    assert evidence.warrant is Warrant.FORMAL
    assert evidence.is_external
    assert evidence.kind == "proof_artifact"
    assert "alive2 2026.1" in evidence.method
    assert evidence.content_hash == "sha256:" + "ef" * 32, "the hash names the raw artifact"
    jsonschema.validate(evidence.to_record(), EVIDENCE_SCHEMA)


def test_a_refuted_result_is_formal_evidence_of_the_opposite():
    evidence = to_evidence(_generic(verdict="refuted"))
    assert evidence.kind == "refutation" and evidence.is_external


def test_an_inconclusive_result_is_not_evidence():
    with pytest.raises(ExternalResultError, match="not evidence"):
        to_evidence(_generic(verdict="unknown"))


@pytest.mark.parametrize("bad", [
    {"verdict": "maybe"}, {"artifact_sha256": "short"}, {"kernel_version_hash": "nope"},
    {"tool": ""},
])
def test_malformed_results_are_refused(bad):
    with pytest.raises(ExternalResultError):
        _generic(**bad)


def test_a_missing_generic_field_is_refused():
    with pytest.raises(ExternalResultError, match="missing"):
        from_generic({"tool": "x", "version": "1"})


def test_staleness_is_the_kernel_hash():
    assert not _generic().is_stale
    assert _generic(kernel_version_hash="0" * 64).is_stale


def test_a_kani_report_of_the_stated_shape_is_ingested():
    result = from_kani_report(KANI_REPORT, kernel_version_hash=KERNEL_VERSION_HASH)
    assert result.tool == "kani" and result.version == "0.55.0"
    assert result.verdict == "proved"
    assert result.provenance == "kani"
    assert "kani_bounded_unwinding" in result.assumptions and "unwind_le_8" in result.assumptions
    assert set(result.subject_refs) == {h["name"] for h in KANI_REPORT["harnesses"]}
    assert to_evidence(result).is_external
    # The same report as text hashes to the same artifact.
    as_text = from_kani_report(json.dumps(KANI_REPORT, sort_keys=True, separators=(",", ":")),
                               kernel_version_hash=KERNEL_VERSION_HASH)
    assert as_text.artifact_sha256 == result.artifact_sha256


def test_one_failing_kani_harness_refutes_and_one_undetermined_is_unknown():
    failing = {**KANI_REPORT, "harnesses": KANI_REPORT["harnesses"] + [{"name": "h", "status": "FAILURE"}]}
    assert from_kani_report(failing, kernel_version_hash=KERNEL_VERSION_HASH).verdict == "refuted"
    undetermined = {**KANI_REPORT, "harnesses": KANI_REPORT["harnesses"] + [{"name": "h", "status": "UNDETERMINED"}]}
    assert from_kani_report(undetermined, kernel_version_hash=KERNEL_VERSION_HASH).verdict == "unknown"


@pytest.mark.parametrize("report", [
    "not json", {"harnesses": []}, {"harnesses": [{"name": "h"}]},
    {"harnesses": [{"name": "h", "status": "MAYBE"}]},
    {"harnesses": [{"name": "h", "status": "SUCCESS"}]},  # no version anywhere
])
def test_a_kani_report_outside_the_stated_shape_is_refused(report):
    with pytest.raises(ExternalResultError):
        from_kani_report(report, kernel_version_hash=KERNEL_VERSION_HASH)


def test_the_bestsad_smt_result_is_external_with_internal_solver_provenance(contract):
    from conftest import prog
    from bestsad.kernel import app, const_int, var
    from bestsad.verify import check_equivalence, probe

    if not probe():
        pytest.skip("z3 is not installed or not usable")
    x = var("x")
    result = check_equivalence(prog(app("add", x, const_int(1))), prog(app("add", const_int(1), x)), contract)
    assert result.status == "equiv"
    external = from_symbolic_result(result)
    assert external.tool == "z3" and external.provenance == "internal-solver"
    assert external.verdict == "proved"
    assert not external.is_stale
    assert external.assumptions == result.assumptions
    evidence = to_evidence(external)
    assert evidence.is_external, "Z3 is external even when BestSad drives it (ADR-0019)"
    assert evidence.warrant is Warrant.FORMAL
    assert external.detail["analyzer_result_ref"] == result.analyzer_result_id
