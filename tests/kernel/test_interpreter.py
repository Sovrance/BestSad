"""Unit semantics for the K0 reference interpreter."""

from __future__ import annotations

import pytest

from bestsad.kernel import (
    BOOL,
    INT,
    Just,
    Kernel,
    NOTHING,
    Pair,
    Program,
    Term,
    TList,
    TOption,
    TTuple,
    TrapKind,
    app,
    const_bool,
    const_int,
    lam,
    nil,
    none,
    var,
)


@pytest.fixture
def k() -> Kernel:
    return Kernel()


def run(k: Kernel, body: Term, params=(), inputs=(), result_type=INT):
    return k.execute(Program(params=params, body=body, result_type=result_type), inputs)


def test_arithmetic(k):
    assert run(k, app("add", const_int(2), const_int(3))).value == 5
    assert run(k, app("sub", const_int(2), const_int(3))).value == -1
    assert run(k, app("mul", const_int(4), const_int(3))).value == 12
    assert run(k, app("neg", const_int(7))).value == -7
    assert run(k, app("abs", const_int(-7))).value == 7
    assert run(k, app("min", const_int(4), const_int(9))).value == 4
    assert run(k, app("max", const_int(4), const_int(9))).value == 9


@pytest.mark.parametrize(
    "x,y,q,r",
    [
        (7, 2, 3, 1),
        (-7, 2, -3, -1),
        (7, -2, -3, 1),
        (-7, -2, 3, -1),
    ],
)
def test_division_truncates_toward_zero(k, x, y, q, r):
    """K0 div/mod truncate toward zero. Python's // floors, so this is a real difference and
    is pinned deliberately: it is kernel semantics (ADR-0008)."""
    assert run(k, app("div", const_int(x), const_int(y))).value == q
    assert run(k, app("mod", const_int(x), const_int(y))).value == r


def test_division_by_zero_traps(k):
    for op in ("div", "mod"):
        res = run(k, app(op, const_int(1), const_int(0)))
        assert res.trap is not None
        assert res.trap.kind is TrapKind.DIVISION_BY_ZERO


def test_if_is_non_strict(k):
    """The untaken branch must not be evaluated: otherwise a guarded division traps."""
    body = app(
        "if",
        app("eq", var("x"), const_int(0)),
        const_int(0),
        app("div", const_int(100), var("x")),
    )
    prog = Program((("x", INT),), body, INT)
    assert k.execute(prog, [0]).value == 0
    assert k.execute(prog, [4]).value == 25


def test_boolean_ops_are_strict(k):
    """`and`/`or` are strict in K0: a trapping operand traps the whole expression even when
    the other operand would short-circuit the result in a lazy language."""
    body = app("and", const_bool(False), app("eq", app("div", const_int(1), const_int(0)),
                                             const_int(0)))
    res = run(k, body, result_type=BOOL)
    assert res.trap is not None and res.trap.kind is TrapKind.DIVISION_BY_ZERO


def test_list_operations_are_total(k):
    empty = nil(INT)
    assert run(k, app("head", empty), result_type=TOption(INT)).value is NOTHING
    assert run(k, app("tail", empty), result_type=TList(INT)).value == ()
    assert run(k, app("length", empty)).value == 0
    assert run(k, app("index", empty, const_int(0)), result_type=TOption(INT)).value is NOTHING
    lst = app("cons", const_int(1), app("cons", const_int(2), nil(INT)))
    assert run(k, app("head", lst), result_type=TOption(INT)).value == Just(1)
    assert run(k, app("index", lst, const_int(-1)), result_type=TOption(INT)).value is NOTHING
    assert run(k, app("index", lst, const_int(5)), result_type=TOption(INT)).value is NOTHING
    assert run(k, app("length", lst)).value == 2


def test_range_and_append(k):
    r = run(k, app("range", const_int(2), const_int(6)), result_type=TList(INT))
    assert r.value == (2, 3, 4, 5)
    empty = run(k, app("range", const_int(6), const_int(2)), result_type=TList(INT))
    assert empty.value == ()
    both = run(
        k,
        app("append", app("range", const_int(0), const_int(2)),
            app("range", const_int(5), const_int(7))),
        result_type=TList(INT),
    )
    assert both.value == (0, 1, 5, 6)


def test_options(k):
    assert run(k, app("is_some", app("some", const_int(1))), result_type=BOOL).value is True
    assert run(k, app("is_some", none(INT)), result_type=BOOL).value is False
    assert run(k, app("option_get_or", none(INT), const_int(9))).value == 9
    assert run(k, app("option_get_or", app("some", const_int(1)), const_int(9))).value == 1


def test_tuples(k):
    t = app("tuple", const_int(1), const_bool(True))
    assert run(k, t, result_type=TTuple(INT, BOOL)).value == Pair(1, True)
    assert run(k, app("fst", t)).value == 1
    assert run(k, app("snd", t), result_type=BOOL).value is True


def test_map_filter_fold(k):
    lst = app("range", const_int(0), const_int(5))
    doubled = app("map", lam((("y", INT),), app("mul", var("y"), const_int(2))), lst)
    assert run(k, doubled, result_type=TList(INT)).value == (0, 2, 4, 6, 8)

    evens = app("filter", lam((("y", INT),), app("eq", app("mod", var("y"), const_int(2)),
                                                 const_int(0))), lst)
    assert run(k, evens, result_type=TList(INT)).value == (0, 2, 4)

    total = app(
        "fold",
        lam((("acc", INT), ("y", INT)), app("add", var("acc"), var("y"))),
        const_int(0),
        lst,
    )
    assert run(k, total).value == 10


def test_fold_is_left_associative(k):
    """fold(f, init, [a, b]) = f(f(init, a), b) — pinned because a right fold would silently
    change every F4/F9/F11 reference solution."""
    lst = app("cons", const_int(1), app("cons", const_int(2), nil(INT)))
    body = app(
        "fold",
        lam((("acc", INT), ("y", INT)), app("sub", var("acc"), var("y"))),
        const_int(10),
        lst,
    )
    assert run(k, body).value == 7  # (10-1)-2, not 10-(1-2)


def test_structural_equality_distinguishes_bool_from_int(k):
    """Python's bool <: int would make `eq(1, true)` true if equality were naive."""
    from bestsad.kernel.values import value_equal

    assert not value_equal(1, True)
    assert not value_equal(0, False)
    assert value_equal((1, 2), (1, 2))
    assert value_equal(Just(Pair(1, ())), Just(Pair(1, ())))


def test_value_bound_traps(k):
    body = app("mul", const_int(2**40), const_int(2**40))
    res = run(k, body)
    assert res.trap is not None and res.trap.kind is TrapKind.VALUE_TOO_LARGE


def test_list_bound_traps(k):
    res = run(k, app("range", const_int(0), const_int(100_000)), result_type=TList(INT))
    assert res.trap is not None and res.trap.kind is TrapKind.LIST_TOO_LONG


def test_fuel_exhaustion_traps(k):
    prog = Program((), app("range", const_int(0), const_int(100)), TList(INT))
    res = Kernel(fuel=3).execute(prog, [])
    assert res.trap is not None and res.trap.kind is TrapKind.FUEL_EXHAUSTED


def test_argument_count_mismatch_is_a_trap_not_an_exception(k):
    prog = Program((("x", INT),), var("x"), INT)
    res = k.execute(prog, [])
    assert res.trap is not None and res.trap.kind is TrapKind.MALFORMED_PROGRAM
