"""BEST-VERIF-02 acceptance test 9: solver time is compute (spec §26.4, design §2.5).

A proof attempt charges solver wall and CPU seconds and a call, and a counterexample's
re-execution charges the kernel steps it spent, through the same path the dynamic tier uses.
A Tier 1 hit charges zero solver time, preserving the existing rule in `equivalence.py` that the
canonical tier executes nothing and charges nothing.
"""

from __future__ import annotations

from bestsad.bsir import equivalent
from bestsad.conditions import ComputeLedger
from bestsad.kernel import app, const_int, var

from conftest import prog, requires_solver

requires_solver()

X = var("x")


def _ledger():
    return ComputeLedger(run_id="r", condition_id="c", seed=0)


def test_a_proof_charges_solver_time_and_no_kernel_steps(contract):
    ledger = _ledger()
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", const_int(1), X))
    result = equivalent(a, b, contract, require_proof=True, ledger=ledger)
    assert result.verdict == "EQUIV_SYMBOLIC"
    assert ledger.solver_calls == 1
    assert ledger.solver_wall_s > 0
    assert ledger.verifier_time_s == ledger.solver_wall_s, "solver time reaches the wire field"
    assert ledger.kernel_steps == 0, "a proof executes nothing on the reference"


def test_a_counterexample_charges_the_re_execution(contract):
    ledger = _ledger()
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", X, const_int(2)))
    result = equivalent(a, b, contract, require_proof=True, ledger=ledger)
    assert result.verdict == "NON_EQUIV"
    assert ledger.solver_calls == 1
    assert ledger.kernel_steps > 0
    assert ledger.verifier_steps == 2 and ledger.candidate_evaluations == 2
    assert result.detail["verification_score"]["verification_cost"]["kernel_steps"] == ledger.kernel_steps


def test_a_tier_one_hit_charges_zero_solver_time(contract):
    ledger = _ledger()
    a = prog(app("add", X, const_int(1)))
    assert equivalent(a, a, contract, require_proof=True, ledger=ledger).verdict == "EQUIV_CANONICAL"
    assert ledger.solver_calls == 0
    assert ledger.solver_wall_s == 0.0
    assert ledger.kernel_steps == 0


def test_an_unknown_still_charges_the_time_it_spent(contract):
    ledger = _ledger()
    from bestsad.kernel import Term

    a = prog(Term("prim:mystery", (X,)))
    b = prog(app("add", X, const_int(1)))
    assert equivalent(a, b, contract, require_proof=True, ledger=ledger).verdict == "UNKNOWN"
    assert ledger.solver_wall_s > 0, "the attempt was made and its time is accounted for"
    assert ledger.solver_calls == 0, "but no solver ran, and the counter says so"


def test_omitting_the_ledger_still_works(contract):
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", const_int(1), X))
    assert equivalent(a, b, contract, require_proof=True).verdict == "EQUIV_SYMBOLIC"
