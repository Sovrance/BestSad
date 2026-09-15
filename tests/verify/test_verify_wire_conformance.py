"""BEST-VERIF-02 acceptance test 8: every record the symbolic tier emits validates against the
shared schemas (ADR 0012, ADR 0015) -- `EquivalenceResult`, `AnalyzerResult`, `Fact`,
`Counterexample` -- and the verification score against `schemas/verification_score.schema.json`.

Mirrors `tests/sre/test_wire_conformance.py`; the basename differs only because pytest cannot
collect two rootless test modules with the same name.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from bestsad import sre
from bestsad.bsir import equivalent
from bestsad.kernel import INT, TList, app, const_int, lam, var
from bestsad.verify import check_equivalence

from conftest import prog, requires_solver

requires_solver()

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "verification_score.schema.json").read_text()
)
X = var("x")


def _pairs():
    inc = lam((("v", INT),), app("add", var("v"), const_int(1)))
    inc2 = lam((("v", INT),), app("add", const_int(1), var("v")))
    return {
        "equiv": (prog(app("add", X, const_int(1))), prog(app("add", const_int(1), X))),
        "non_equiv": (prog(app("add", X, const_int(1))), prog(app("add", X, const_int(2)))),
        "lists": (prog(app("map", inc, var("xs")), (("xs", TList(INT)),), TList(INT)),
                  prog(app("map", inc2, var("xs")), (("xs", TList(INT)),), TList(INT))),
    }


def test_equivalence_results_validate(contract):
    for name, (a, b) in _pairs().items():
        result = equivalent(a, b, contract, require_proof=True)
        wire = result.to_wire()
        sre.validate("EquivalenceResult", wire)
        assert wire["scope"]["solverScope"] == contract.solver_scope
        if result.counterexample is not None:
            sre.validate("Counterexample", result.counterexample.to_wire())
            assert wire["counterexampleRef"] == result.counterexample.id
        else:
            assert wire["counterexampleRef"] is None
        assert wire["evidenceRefs"], name


def test_analyzer_results_and_facts_validate(contract):
    for name, (a, b) in _pairs().items():
        result = check_equivalence(a, b, contract)
        sre.validate("AnalyzerResult", result.analyzer_result)
        sre.validate("Fact", result.fact)
        assert result.analyzer_result["id"] == result.analyzer_result_id
        assert result.fact["id"] in result.analyzer_result["facts"]
        coverage = result.analyzer_result["coverage"]
        assert coverage["smtlib2"].startswith(";") or "(" in coverage["smtlib2"]
        assert coverage["solverVersion"].startswith("z3-")
        assert coverage["wallSeconds"] >= 0 and coverage["cpuSeconds"] >= 0


def test_unknown_records_carry_the_open_obligation(contract):
    from bestsad.bsir import EquivalenceContract
    from bestsad.bsir.equivalence import SYMBOLIC_OBLIGATION

    bad = EquivalenceContract(input_domain_ref="d", solver_scope="list_bond=1")
    a, b = _pairs()["equiv"]
    result = check_equivalence(a, b, bad)
    sre.validate("AnalyzerResult", result.analyzer_result)
    assert result.analyzer_result["unresolved"][0]["obligation"] == SYMBOLIC_OBLIGATION


def test_verification_scores_validate(contract):
    for name, (a, b) in _pairs().items():
        result = equivalent(a, b, contract, require_proof=True)
        score = result.detail["verification_score"]
        jsonschema.validate(instance=score, schema=SCHEMA)
        assert score["verdict"] == result.verdict
        assert score["analyzer_result_ref"] in result.evidence_refs
        if name == "lists":
            assert 0 < score["verification_coverage"] < 1
        else:
            assert score["verification_coverage"] == 1.0


def test_the_score_schema_rejects_an_estimated_coverage_without_a_basis(contract):
    a, b = _pairs()["equiv"]
    score = dict(equivalent(a, b, contract, require_proof=True).detail["verification_score"])
    score["coverage_basis"] = ""
    try:
        jsonschema.validate(instance=score, schema=SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("a coverage figure with no stated basis validated")  # pragma: no cover
