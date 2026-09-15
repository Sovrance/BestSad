"""BEST-VERIF-02 acceptance test 7: without Z3, Tier 2 says so and nothing escapes.

This module deliberately does **not** skip when the solver is absent: it is the one that has to
pass in the `pip install -e ".[dev]"` environment (ADR-0019 acceptance).
"""

from __future__ import annotations

import sys

from bestsad.bsir import equivalent
from bestsad.bsir.equivalence import SYMBOLIC_OBLIGATION
from bestsad.kernel import INT, app, const_int, var
from bestsad.verify.smt.solver import SOLVER_UNAVAILABLE, probe

from conftest import prog


def _hide_z3(monkeypatch):
    monkeypatch.setitem(sys.modules, "z3", None)  # makes `import z3` raise ImportError


def test_probe_is_false_when_z3_cannot_be_imported(monkeypatch):
    _hide_z3(monkeypatch)
    assert probe() is False


def test_tier_two_returns_unknown_solver_unavailable(contract, monkeypatch):
    _hide_z3(monkeypatch)
    a = prog(app("add", var("x"), const_int(1)))
    b = prog(app("add", const_int(1), var("x")))
    result = equivalent(a, b, contract, require_proof=True)   # must not raise
    assert result.verdict == "UNKNOWN"
    assert not result.is_equivalent
    assert SYMBOLIC_OBLIGATION in result.unresolved
    assert result.detail["reason"] == SOLVER_UNAVAILABLE


def test_the_dynamic_tier_is_unaffected_by_solver_absence(contract, monkeypatch):
    """Tier 3 never needed a solver; absence of one must not change its verdicts."""
    _hide_z3(monkeypatch)
    a = prog(app("add", var("x"), const_int(1)))
    b = prog(app("add", const_int(1), var("x")))
    assert equivalent(a, b, contract).verdict == "EQUIV_DYNAMIC"


def test_absence_still_charges_nothing_to_the_solver_counters(contract, monkeypatch):
    from bestsad.conditions import ComputeLedger

    _hide_z3(monkeypatch)
    ledger = ComputeLedger(run_id="r", condition_id="c", seed=0)
    a = prog(app("add", var("x"), const_int(1)))
    b = prog(app("add", const_int(1), var("x")))
    equivalent(a, b, contract, require_proof=True, ledger=ledger)
    assert ledger.solver_calls == 0
    assert ledger.kernel_steps == 0
