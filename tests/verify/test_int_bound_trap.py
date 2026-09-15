"""BEST-VERIF-02 acceptance test 4: the integer bound is semantics (ADR-0008 decision 1).

Integers are the SMT integer theory, so nothing wraps; every arithmetic result carries the
`|r| > 2^64` guard, and a `mul` chain that crosses it must trap `VALUE_TOO_LARGE` exactly where
the reference does. The solver must also be able to *find* such an input on its own.
"""

from __future__ import annotations

from bestsad.bsir import equivalent
from bestsad.kernel import INT, Kernel, Program, app, const_int, var
from bestsad.kernel.ops import INT_ABS_LIMIT
from bestsad.kernel.traps import TrapKind
from bestsad.verify import symbolic_execute

from conftest import requires_solver

requires_solver()

X = var("x")
SQUARE = app("mul", X, X)
FOURTH = app("mul", SQUARE, SQUARE)


def test_a_mul_chain_exceeding_the_bound_traps_value_too_large():
    program = Program((("x", INT),), FOURTH, INT)
    kernel = Kernel()
    for x in (2**16, 2**17, -(2**17), 2**30):
        encoded = symbolic_execute(program, (x,))
        reference = kernel.execute(program, (x,))
        assert encoded.same_outcome(reference), (x, encoded, reference)
    assert symbolic_execute(program, (2**16,)).value == 2**64          # exactly at the bound: ok
    assert symbolic_execute(program, (2**17,)).trap.kind is TrapKind.VALUE_TOO_LARGE


def test_a_literal_beyond_the_bound_traps_like_the_reference():
    program = Program((), const_int(INT_ABS_LIMIT + 1), INT)
    encoded = symbolic_execute(program, ())
    assert encoded.trap is not None and encoded.trap.kind is TrapKind.VALUE_TOO_LARGE
    assert encoded.same_outcome(Kernel().execute(program, ()))


def test_the_solver_finds_the_overflow_witness(contract):
    """`x*x - x*x` is zero wherever it does not trap, so a bounded-safe `0` agrees with it on
    every small input the dynamic tier would sample. Only a proof attempt finds |x| > 2^32."""
    left = Program((("x", INT),), app("sub", SQUARE, SQUARE), INT)
    right = Program((("x", INT),), const_int(0), INT)

    sampled = equivalent(left, right, contract)
    assert sampled.verdict == "EQUIV_DYNAMIC", "the fixture must be invisible to sampling"

    proved = equivalent(left, right, contract, require_proof=True)
    assert proved.verdict == "NON_EQUIV"
    assert proved.counterexample.kind == "DIVERGENT_TRAP"
    assert proved.counterexample.left_outcome == {"trap": "value_too_large"}
    (witness,) = (int(v) for v in proved.counterexample.witness["inputs"])
    assert abs(witness) > 2**32
    # The witness reproduces on the reference: that is what makes it a demonstration.
    assert Kernel().execute(left, (witness,)).trap.kind is TrapKind.VALUE_TOO_LARGE


def test_bit_vector_wraparound_would_be_caught(contract):
    """`add(x, 1)` versus the same thing: trivially equal. But `sub(add(x, 1), 1)` is *not*
    `x`, because at `x = 2^64` the addition traps. A bit-vector encoding would call them equal."""
    left = Program((("x", INT),), app("sub", app("add", X, const_int(1)), const_int(1)), INT)
    right = Program((("x", INT),), X, INT)
    result = equivalent(left, right, contract, require_proof=True)
    assert result.verdict == "NON_EQUIV"
    (witness,) = (int(v) for v in result.counterexample.witness["inputs"])
    assert witness == INT_ABS_LIMIT
