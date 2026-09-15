"""BEST-VERIF-02 acceptance test 2: `div` and `mod` truncate toward zero (ADR-0008 decision 2).

Z3's own integer division is Euclidean and disagrees with K0 on negative operands. The encoder
must not use it directly, and this file is the pin: all four sign combinations and the zero
divisor, symbolically versus the reference, plus two identities the solver has to *prove*.
"""

from __future__ import annotations

import itertools

from bestsad.bsir import equivalent
from bestsad.kernel import INT, Kernel, Program, app, const_int, var
from bestsad.kernel.traps import TrapKind
from bestsad.verify import symbolic_execute

from conftest import requires_solver

requires_solver()

X, Y = var("x"), var("y")
OPERANDS = (-7, -3, -1, 0, 1, 3, 7, 2**40)


def _program(op: str) -> Program:
    return Program((("x", INT), ("y", INT)), app(op, X, Y), INT)


def test_every_sign_combination_and_the_zero_divisor_match_the_reference():
    kernel = Kernel()
    for op in ("div", "mod"):
        program = _program(op)
        for a, b in itertools.product(OPERANDS, OPERANDS):
            reference = kernel.execute(program, (a, b))
            encoded = symbolic_execute(program, (a, b))
            assert encoded is not None
            assert encoded.same_outcome(reference), (
                f"{op}({a}, {b}): encoder {encoded}, reference {reference}"
            )
            if b == 0:
                assert reference.trap is not None
                assert reference.trap.kind is TrapKind.DIVISION_BY_ZERO


def test_the_truncation_direction_is_pinned_explicitly():
    """The concrete values a floor-division encoding would get wrong."""
    div, mod = _program("div"), _program("mod")
    assert symbolic_execute(div, (-7, 2)).value == -3      # floor would give -4
    assert symbolic_execute(div, (7, -2)).value == -3
    assert symbolic_execute(mod, (-7, 2)).value == -1      # sign of the dividend; floor gives 1
    assert symbolic_execute(mod, (7, -2)).value == 1


def test_the_solver_proves_the_mod_identity(contract):
    """`mod(a, b) ≡ a - div(a, b) * b`, which is how the reference computes it."""
    lhs = _program("mod")
    rhs = Program((("x", INT), ("y", INT)),
                  app("sub", X, app("mul", app("div", X, Y), Y)), INT)
    result = equivalent(lhs, rhs, contract, require_proof=True)
    assert result.verdict == "EQUIV_SYMBOLIC", result.detail


def test_the_solver_proves_truncation_is_odd_in_the_dividend(contract):
    """`div(-a, b) ≡ -div(a, b)` holds for truncation and fails for floor division."""
    lhs = Program((("x", INT), ("y", INT)), app("div", app("neg", X), Y), INT)
    rhs = Program((("x", INT), ("y", INT)), app("neg", app("div", X, Y)), INT)
    result = equivalent(lhs, rhs, contract, require_proof=True)
    assert result.verdict == "EQUIV_SYMBOLIC", result.detail


def test_a_wrong_rounding_is_refuted_with_a_witness(contract):
    """`div(x, 2)` is not `mod`-free rounding down: the solver must find a negative odd witness."""
    lhs = Program((("x", INT),), app("div", X, const_int(2)), INT)
    # Floor division by 2, written in K0: (x - mod(x,2)) / 2 differs from trunc on negative odds
    # only when mod is negative, i.e. rhs = div(sub(x, mod(x, 2)), 2) is the *truncating* form
    # again; use an explicitly floor-shaped candidate instead.
    rhs = Program((("x", INT),), app("if", app("lt", X, const_int(0)),
                                        app("div", app("sub", X, const_int(1)), const_int(2)),
                                        app("div", X, const_int(2))), INT)
    result = equivalent(lhs, rhs, contract, require_proof=True)
    assert result.verdict == "NON_EQUIV"
    (witness,) = (int(v) for v in result.counterexample.witness["inputs"])
    assert witness < 0 and witness % 2 != 0
