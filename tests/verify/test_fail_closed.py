"""BEST-VERIF-02 acceptance test 6: everything the tier cannot settle is UNKNOWN with a reason.

An op outside `K0_OPS`, a program beyond the unroll bound, a solver timeout, an unsupported
observable, a malformed scope: each yields `UNKNOWN` with the obligation left open and the
reason recorded. None yields `EQUIV_*`, which is the only outcome that would be a bug here.
"""

from __future__ import annotations

import pytest

from bestsad.bsir import EquivalenceContract, equivalent
from bestsad.bsir.equivalence import SYMBOLIC_OBLIGATION
from bestsad.kernel import INT, Program, Term, TList, app, const_int, lam, var

from conftest import prog, requires_solver

requires_solver()

X = var("x")


def _assert_unknown(result, fragment: str):
    assert result.verdict == "UNKNOWN", result.verdict
    assert not result.is_equivalent
    assert SYMBOLIC_OBLIGATION in result.unresolved
    assert fragment in result.detail["reason"], result.detail["reason"]


def test_an_operation_outside_k0_is_refused(contract):
    """`Term` rejects unknown ops outright, so the only way in is a genome primitive the kernel
    cannot expand -- which is outside K0_OPS for every purpose that matters here."""
    a = prog(Term("prim:mystery", (X,)))
    b = prog(app("add", X, const_int(1)))
    _assert_unknown(equivalent(a, b, contract, require_proof=True), "prim:mystery")


def test_nesting_beyond_the_unroll_bound_is_refused(contract):
    # Four levels of higher-order nesting against the default unroll_depth=3.
    l4 = TList(TList(TList(TList(INT))))
    inc = lam((("d", INT),), app("add", var("d"), const_int(1)))
    level1 = lam((("c", TList(INT)),), app("map", inc, var("c")))
    level2 = lam((("b", TList(TList(INT))),), app("map", level1, var("b")))
    level3 = lam((("a", TList(TList(TList(INT)))),), app("map", level2, var("a")))
    program = Program((("xs", l4),), app("map", level3, var("xs")), l4)
    other = Program(program.params, var("xs"), l4)
    result = equivalent(program, other, contract, require_proof=True)
    _assert_unknown(result, "unroll_depth")

    # Raising the declared depth makes the same pair decidable -- and refutable.
    wider = EquivalenceContract(input_domain_ref="int:small-enumerated",
                                solver_scope="unroll_depth=4;list_bound=2")
    assert equivalent(program, other, wider, require_proof=True).verdict == "NON_EQUIV"


def test_a_solver_timeout_is_unknown_with_the_reason_recorded(contract, monkeypatch):
    import z3

    def timed_out(self):
        return z3.unknown

    monkeypatch.setattr(z3.Solver, "check", timed_out)
    monkeypatch.setattr(z3.Solver, "reason_unknown", lambda self: "timeout")
    # The probe itself uses the solver, so it must also be bypassed to reach the tier.
    monkeypatch.setattr("bestsad.verify.smt.solver.probe", lambda: True)
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", const_int(1), X))
    _assert_unknown(equivalent(a, b, contract, require_proof=True), "timeout")


def test_a_genuinely_short_budget_never_yields_a_proof():
    """A one-millisecond budget on a nonlinear query. The solver may or may not finish, and the
    only outcomes permitted are the honest ones."""
    contract = EquivalenceContract(input_domain_ref="int:small-enumerated", solver_scope="timeout_ms=1")
    y, z = var("y"), var("z")
    params = (("x", INT), ("y", INT), ("z", INT))
    a = Program(params, app("mul", app("mul", X, y), app("mul", z, app("mul", X, y))), INT)
    b = Program(params, app("mul", app("mul", z, y), app("mul", X, app("mul", y, X))), INT)
    result = equivalent(a, b, contract, require_proof=True)
    assert result.verdict in ("UNKNOWN", "EQUIV_SYMBOLIC")
    if result.verdict == "UNKNOWN":
        assert SYMBOLIC_OBLIGATION in result.unresolved


def test_an_unsupported_observable_is_refused():
    contract = EquivalenceContract(input_domain_ref="d", observable_contract_ref="outcome:trace-hash")
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", const_int(1), X))
    _assert_unknown(equivalent(a, b, contract, require_proof=True), "observable")


@pytest.mark.parametrize("scope", ["list_bond=4", "list_bound=0", "list_bound=99999", "timeout_ms=abc"])
def test_a_malformed_scope_is_refused_not_defaulted(scope):
    contract = EquivalenceContract(input_domain_ref="d", solver_scope=scope)
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", const_int(1), X))
    _assert_unknown(equivalent(a, b, contract, require_proof=True), "solver_scope")


def test_an_ill_typed_program_is_refused(contract):
    a = prog(app("add", X, app("lt", X, X)))  # Int + Bool
    b = prog(app("add", X, const_int(1)))
    _assert_unknown(equivalent(a, b, contract, require_proof=True), "ill-typed")


def test_a_witness_the_assumptions_exclude_is_unknown_not_a_verdict():
    """With `max_steps=0` every execution exhausts fuel, which v0.1 does not model. The solver
    finds a value-level witness; the reference fuel-traps on it; the honest answer is UNKNOWN.
    (This is also the hole BEST-VERIF-04's non-vacuity check exists to close.)"""
    contract = EquivalenceContract(input_domain_ref="d", max_steps=0)
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", X, const_int(2)))
    _assert_unknown(equivalent(a, b, contract, require_proof=True), "fuel_exhausted")
