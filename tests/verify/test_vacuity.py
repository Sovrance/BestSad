"""BEST-VERIF-04 acceptance: a contract that accepts everything proves nothing.

* a contract with a trivially-true observable -- `max_steps=0`, under which every execution
  fuel-traps and the symbolic tier's fuel exclusion covers the whole domain -- is detected as
  vacuous and the verdict is refused with reason `contract_vacuous`;
* a sound contract survives, with the refuting mutant named;
* the vacuity record is attached to the verdict's `evidenceRefs` and validates as an SRE Fact.
"""

from __future__ import annotations

import pytest

from bestsad import sre
from bestsad.bsir import EquivalenceContract, equivalent
from bestsad.bsir.canonicalize import semantic_hash
from bestsad.kernel import BOOL, INT, Program, TList, app, const_bool, const_int, lam, var
from bestsad.kernel.typecheck import is_well_typed
from bestsad.verify.vacuity import (
    REASON_VACUOUS,
    ContractVacuous,
    attach,
    mutants,
    non_vacuity,
    prove_non_vacuously,
)

from conftest import prog, requires_solver

requires_solver()

X, Y = var("x"), var("y")
COMMUTED = (prog(app("add", X, const_int(1))), prog(app("add", const_int(1), X)))


class TestMutants:
    def test_mutants_are_well_typed_and_distinct_from_the_original(self):
        program = Program((("x", INT), ("y", INT)),
                          app("if", app("lt", X, Y), app("add", X, const_int(1)), app("max", X, Y)), INT)
        found = mutants(program, seed=3, limit=20)
        assert found, "a program this rich must have mutants"
        original = semantic_hash(program)
        for mutant in found:
            assert is_well_typed(mutant.program), mutant.description
            assert semantic_hash(mutant.program) != original, mutant.description
        assert len({semantic_hash(m.program) for m in found}) == len(found)
        kinds = {m.description.split(" ")[0] for m in found}
        assert {"lt->le", "if-branches-swapped", "var", "const_int", "add->sub"} & kinds

    def test_mutation_is_deterministic_given_the_seed(self):
        program = COMMUTED[0]
        a = [m.description for m in mutants(program, seed=7)]
        b = [m.description for m in mutants(program, seed=7)]
        c = [m.description for m in mutants(program, seed=8, limit=50)]
        assert a == b
        assert set(a) <= set(c) and len(c) >= len(a)

    def test_an_ill_typed_swap_is_dropped(self):
        # `tuple(x, b)` swapped is `tuple(b, x)`, which no longer matches the result type.
        program = Program((("x", INT), ("b", BOOL)), app("fst", app("tuple", X, var("b"))), INT)
        assert all("tuple-operands-swapped" not in m.description for m in mutants(program, limit=50))

    def test_a_mutation_that_canonicalises_back_is_not_a_mutant(self):
        # x -> y where the program has one Int parameter: nothing to swap to.
        program = prog(X)
        assert all("var" not in m.description for m in mutants(program, limit=50))


class TestTheControl:
    def test_a_sound_contract_survives_with_the_refuting_mutant_named(self, contract):
        left, right = COMMUTED
        record = non_vacuity(left, right, contract)
        assert record.non_vacuous
        assert record.refuting_mutant is not None
        assert record.mutants_tried >= 1
        assert dict(record.verdicts)[record.refuting_mutant] == "NON_EQUIV"
        assert record.reason is None

    def test_a_vacuous_contract_is_detected_and_the_proof_refused(self):
        """`max_steps=0`: the solver still says EQUIV_SYMBOLIC under its fuel assumption, and
        that is the honest answer to the question asked. The control is what notices that the
        question was empty."""
        contract = EquivalenceContract(input_domain_ref="int:small-enumerated", max_steps=0)
        left, right = COMMUTED
        proof = equivalent(left, right, contract, require_proof=True)
        assert proof.verdict == "EQUIV_SYMBOLIC", "the fixture relies on the assumption-bounded proof"

        record = non_vacuity(left, right, contract)
        assert not record.non_vacuous
        assert record.reason == REASON_VACUOUS
        assert record.mutants_tried > 0, "vacuity was established by trying, not by default"
        assert all(v != "NON_EQUIV" for _, v in record.verdicts)

        with pytest.raises(ContractVacuous, match=REASON_VACUOUS):
            attach(proof, record)
        with pytest.raises(ContractVacuous, match=REASON_VACUOUS):
            prove_non_vacuously(left, right, contract)

    def test_the_record_is_attached_to_the_verdicts_evidence_and_validates(self, contract):
        left, right = COMMUTED
        guarded = prove_non_vacuously(left, right, contract)
        assert guarded.verdict == "EQUIV_SYMBOLIC"
        record_id = guarded.detail["vacuity"]["record"]
        assert record_id in guarded.evidence_refs
        assert guarded.detail["vacuity"]["non_vacuous"] is True

        record = non_vacuity(left, right, contract)
        # Only the verdicts are compared across runs: the record references the mutant analyzer
        # results, whose ids carry solver timing (ADR-0019 names that as the nondeterminism).
        assert record.verdicts == non_vacuity(left, right, contract).verdicts
        assert record.refuting_mutant is not None
        wire = record.to_wire()
        sre.validate("Fact", wire)
        assert wire["status"] == "SUPPORTED"
        assert wire["evidenceRefs"], "the mutant verdicts are referenced from the record"
        sre.validate("EquivalenceResult", guarded.to_wire())

    def test_a_vacuous_record_validates_too(self):
        contract = EquivalenceContract(input_domain_ref="d", max_steps=0)
        record = non_vacuity(*COMMUTED, contract)
        wire = record.to_wire()
        sre.validate("Fact", wire)
        assert wire["status"] == "CONTRADICTED"
        assert wire["detail"]["reason"] == REASON_VACUOUS

    def test_verdicts_that_claim_nothing_pass_through(self, contract):
        left = prog(app("add", X, const_int(1)))
        right = prog(app("add", X, const_int(2)))
        refuted = prove_non_vacuously(left, right, contract)
        assert refuted.verdict == "NON_EQUIV"
        assert "vacuity" not in refuted.detail, "nothing to guard"

        canonical = prove_non_vacuously(left, left, contract)
        assert canonical.verdict == "EQUIV_CANONICAL"

    def test_unknown_on_a_mutant_is_not_a_refutation(self, contract, monkeypatch):
        """A contract whose mutants all time out has not shown it can tell anything apart."""
        import z3

        monkeypatch.setattr(z3.Solver, "check", lambda self: z3.unknown)
        monkeypatch.setattr(z3.Solver, "reason_unknown", lambda self: "timeout")
        monkeypatch.setattr("bestsad.verify.smt.solver.probe", lambda: True)
        record = non_vacuity(*COMMUTED, contract)
        assert not record.non_vacuous
        assert all(v == "UNKNOWN" for _, v in record.verdicts)

    def test_list_contracts_are_guarded_the_same_way(self, contract):
        inc = lam((("v", INT),), app("add", var("v"), const_int(1)))
        inc2 = lam((("v", INT),), app("add", const_int(1), var("v")))
        xs = var("xs")
        left = Program((("xs", TList(INT)),), app("map", inc, xs), TList(INT))
        right = Program((("xs", TList(INT)),), app("map", inc2, xs), TList(INT))
        guarded = prove_non_vacuously(left, right, contract)
        assert guarded.verdict == "EQUIV_SYMBOLIC"
        assert guarded.detail["vacuity"]["non_vacuous"] is True

    def test_the_check_charges_the_ledger_for_every_mutant_it_ran(self, contract):
        from bestsad.conditions import ComputeLedger

        ledger = ComputeLedger(run_id="r", condition_id="c", seed=0)
        record = non_vacuity(*COMMUTED, contract, ledger=ledger)
        assert ledger.solver_calls == record.mutants_tried
