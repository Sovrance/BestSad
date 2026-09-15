"""BEST-VERIF-02 acceptance test 3: `and`/`or` are strict; `if` is the only non-strict op
(ADR-0008 decision 4). Trap propagation is not short-circuited.
"""

from __future__ import annotations

from bestsad.bsir import equivalent
from bestsad.kernel import BOOL, INT, Kernel, Program, app, const_bool, const_int, var
from bestsad.kernel.traps import TrapKind
from bestsad.verify import symbolic_execute

from conftest import requires_solver

requires_solver()

DIV_BY_ZERO = app("div", const_int(1), const_int(0))


def test_and_false_with_a_trapping_operand_traps():
    program = Program((), app("and", const_bool(False), app("lt", DIV_BY_ZERO, const_int(1))), BOOL)
    encoded = symbolic_execute(program, ())
    assert encoded.trap is not None and encoded.trap.kind is TrapKind.DIVISION_BY_ZERO
    assert encoded.same_outcome(Kernel().execute(program, ()))


def test_or_true_with_a_trapping_operand_traps():
    program = Program((), app("or", const_bool(True), app("lt", DIV_BY_ZERO, const_int(1))), BOOL)
    encoded = symbolic_execute(program, ())
    assert encoded.trap is not None and encoded.trap.kind is TrapKind.DIVISION_BY_ZERO


def test_if_false_with_a_trapping_then_branch_is_a_value():
    program = Program((), app("if", const_bool(False), DIV_BY_ZERO, const_int(0)), INT)
    encoded = symbolic_execute(program, ())
    assert encoded.trap is None and encoded.value == 0
    assert encoded.same_outcome(Kernel().execute(program, ()))


def test_the_first_trap_wins_left_to_right():
    """`add(div(1,0), mul(2^40, 2^40))` traps division_by_zero; reversed, value_too_large.
    This is the exact pair `canonicalize.py` cites for refusing commutative reordering."""
    big = app("mul", const_int(2**40), const_int(2**40))
    left = Program((), app("add", DIV_BY_ZERO, big), INT)
    right = Program((), app("add", big, DIV_BY_ZERO), INT)
    assert symbolic_execute(left, ()).trap.kind is TrapKind.DIVISION_BY_ZERO
    assert symbolic_execute(right, ()).trap.kind is TrapKind.VALUE_TOO_LARGE


def test_strictness_is_visible_to_the_equivalence_tier(contract):
    """A short-circuiting reading would call these equal. K0 does not, and the solver must find
    the input on which they differ: any `x` at all, since the left always traps."""
    x = var("x")
    strict = Program((("x", INT),), app("and", const_bool(False), app("lt", app("div", x, const_int(0)), x)), BOOL)
    lazy = Program((("x", INT),), const_bool(False), BOOL)
    result = equivalent(strict, lazy, contract, require_proof=True)
    assert result.verdict == "NON_EQUIV"
    assert result.counterexample.kind == "DIVERGENT_TRAP"
    assert result.counterexample.left_outcome == {"trap": "division_by_zero"}


def test_guarded_division_is_provably_total(contract):
    """The reason `if` is non-strict: `if x = 0 then 0 else 100/x` never traps, and the solver
    can prove it equals a program that computes the same thing another way."""
    x = var("x")
    guarded = Program((("x", INT),), app("if", app("eq", x, const_int(0)), const_int(0),
                                          app("div", const_int(100), x)), INT)
    other = Program((("x", INT),), app("if", app("not", app("eq", x, const_int(0))),
                                        app("div", const_int(100), x), const_int(0)), INT)
    result = equivalent(guarded, other, contract, require_proof=True)
    assert result.verdict == "EQUIV_SYMBOLIC", result.detail
