"""Shared fixtures for the verification plane tests.

The solver is an optional dependency (ADR-0019). Tests that need it skip with a named reason
when it is absent, so `pip install -e ".[dev]"` alone still runs the suite green; Gate G-V
(`scripts/ci_local.py --gate verify`) is where absence is reported UNAVAILABLE rather than
skipped, per ADR-0018.
"""

from __future__ import annotations

import pytest

from bestsad.bsir import EquivalenceContract
from bestsad.kernel import BOOL, INT, Program, TList, TOption, TTuple, app
from bestsad.kernel import const_bool, const_int, lam, nil, none, var


def requires_twin():
    """Module-level guard: skip a twin-backed test module when the `k0rs` binary cannot be
    found or built, or computes a different kernel hash. The K0 twin gates in CI report this
    as a failure, not a skip: there the binary is built first."""
    from bestsad.verify.twin import probe

    if not probe():
        pytest.skip("the k0rs twin is not available (no binary, no cargo, or a hash mismatch); "
                    "the K0 twin gate reports this as UNAVAILABLE", allow_module_level=True)


def requires_solver():
    """Module-level guard: skip a solver-backed test module when Z3 cannot be used."""
    from bestsad.verify.smt.solver import probe

    if not probe():
        pytest.skip("z3 is not installed or not usable; Gate G-V reports this as UNAVAILABLE",
                    allow_module_level=True)


@pytest.fixture
def contract() -> EquivalenceContract:
    return EquivalenceContract(input_domain_ref="int:small-enumerated")


def prog(body, params=(("x", INT),), result=INT) -> Program:
    return Program(params=params, body=body, result_type=result)


L = TList(INT)
X, Y, XS, YS, B = var("x"), var("y"), var("xs"), var("ys"), var("b")


def _inc():
    return lam((("v", INT),), app("add", var("v"), const_int(1)))


def _pos():
    return lam((("v", INT),), app("gt", var("v"), const_int(0)))


def _sum():
    return lam((("acc", INT), ("v", INT)), app("add", var("acc"), var("v")))


#: One program per K0 operation, shared by the encoder differential test (BEST-VERIF-02) and the
#: twin differential test (BEST-VERIF-05). Inputs are enumerated from the same small domain the
#: dynamic tier samples, which was chosen for where K0 breaks: zero divisors, negatives, large
#: values.
PER_OP: dict[str, Program] = {
    "const_int": Program((), const_int(7), INT),
    "const_bool": Program((), const_bool(True), BOOL),
    "var": Program((("x", INT),), X, INT),
    "add": Program((("x", INT), ("y", INT)), app("add", X, Y), INT),
    "sub": Program((("x", INT), ("y", INT)), app("sub", X, Y), INT),
    "mul": Program((("x", INT), ("y", INT)), app("mul", app("mul", X, Y), app("mul", X, Y)), INT),
    "div": Program((("x", INT), ("y", INT)), app("div", X, Y), INT),
    "mod": Program((("x", INT), ("y", INT)), app("mod", X, Y), INT),
    "neg": Program((("x", INT),), app("neg", X), INT),
    "abs": Program((("x", INT),), app("abs", X), INT),
    "min": Program((("x", INT), ("y", INT)), app("min", X, Y), INT),
    "max": Program((("x", INT), ("y", INT)), app("max", X, Y), INT),
    "eq": Program((("xs", L), ("ys", L)), app("eq", XS, YS), BOOL),
    "lt": Program((("x", INT), ("y", INT)), app("lt", X, Y), BOOL),
    "le": Program((("x", INT), ("y", INT)), app("le", X, Y), BOOL),
    "gt": Program((("x", INT), ("y", INT)), app("gt", X, Y), BOOL),
    "ge": Program((("x", INT), ("y", INT)), app("ge", X, Y), BOOL),
    "and": Program((("b", BOOL), ("x", INT)), app("and", B, app("lt", app("div", const_int(1), X), const_int(1))), BOOL),
    "or": Program((("b", BOOL), ("x", INT)), app("or", B, app("lt", app("div", const_int(1), X), const_int(1))), BOOL),
    "not": Program((("b", BOOL),), app("not", B), BOOL),
    "if": Program((("b", BOOL), ("x", INT)), app("if", B, app("div", const_int(1), X), const_int(0)), INT),
    "tuple": Program((("x", INT), ("b", BOOL)), app("tuple", X, B), TTuple(INT, BOOL)),
    "fst": Program((("x", INT), ("b", BOOL)), app("fst", app("tuple", X, B)), INT),
    "snd": Program((("x", INT), ("b", BOOL)), app("snd", app("tuple", X, B)), BOOL),
    "nil": Program((), nil(INT), L),
    "cons": Program((("x", INT), ("xs", L)), app("cons", X, XS), L),
    "head": Program((("xs", L),), app("head", XS), TOption(INT)),
    "tail": Program((("xs", L),), app("tail", XS), L),
    "length": Program((("xs", L),), app("length", XS), INT),
    "index": Program((("xs", L), ("x", INT)), app("index", XS, X), TOption(INT)),
    "append": Program((("xs", L), ("ys", L)), app("append", XS, YS), L),
    "range": Program((("x", INT), ("y", INT)), app("range", X, Y), L),
    "some": Program((("x", INT),), app("some", X), TOption(INT)),
    "none": Program((), none(INT), TOption(INT)),
    "option_get_or": Program((("xs", L), ("x", INT)), app("option_get_or", app("head", XS), X), INT),
    "is_some": Program((("xs", L),), app("is_some", app("head", XS)), BOOL),
    "map": Program((("xs", L),), app("map", _inc(), XS), L),
    "filter": Program((("xs", L),), app("filter", _pos(), XS), L),
    "fold": Program((("xs", L), ("x", INT)), app("fold", _sum(), X, XS), INT),
    "lam": Program((("xs", L),), app("map", lam((("v", INT),), app("mul", var("v"), var("v"))), XS), L),
}
