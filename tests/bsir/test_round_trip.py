"""M2 acceptance: projection round-trips and the P8 non-canonicality rule."""

from __future__ import annotations

import random

import pytest

from bestsad.bsir import (
    from_graph,
    get_projection,
    semantic_hash,
    to_graph,
    token_count,
    verify,
)
from bestsad.bsir.projections import PROJECTIONS
from bestsad.kernel import Program
from bestsad.kernel.random_programs import random_program

PROJECTION_NAMES = sorted(PROJECTIONS)


@pytest.mark.parametrize("name", PROJECTION_NAMES)
def test_projection_round_trip_is_identity_on_the_canonical_hash(name):
    """M2 acceptance 3: BSIR -> projection -> BSIR is identity on the canonical hash.

    This is what separates a formatting experiment from a language experiment (spec §12.2). A
    projection that lost or added information would fail here."""
    projection = get_projection(name)
    for i in range(400):
        program = random_program(random.Random(i))
        text = projection.render(program.body)
        recovered = projection.parse(text)
        assert semantic_hash(Program(program.params, recovered, None)) == semantic_hash(
            Program(program.params, program.body, None)
        ), f"{name} failed to round-trip: {text[:160]}"


@pytest.mark.parametrize("name", PROJECTION_NAMES)
def test_projection_preserves_execution_outcome(name):
    """Stronger than hash equality: the recovered program must *run* the same."""
    from bestsad.kernel import Kernel
    from bestsad.kernel.random_programs import random_inputs

    kernel = Kernel()
    projection = get_projection(name)
    for i in range(150):
        program = random_program(random.Random(1000 + i))
        recovered = Program(
            program.params, projection.parse(projection.render(program.body)),
            program.result_type,
        )
        inputs = random_inputs(random.Random(i), program.params)
        assert kernel.execute(program, inputs).same_outcome(kernel.execute(recovered, inputs))


def test_graph_conversion_round_trips():
    for i in range(300):
        program = random_program(random.Random(i))
        graph = to_graph(program)
        rebuilt = from_graph(graph)
        assert semantic_hash(rebuilt) == semantic_hash(program)


def test_graph_is_a_dag_with_structure_sharing():
    """Content-addressed node ids mean identical subterms share a node."""
    from bestsad.kernel import INT, app, const_int, var

    body = app("add", app("mul", var("x"), const_int(2)), app("mul", var("x"), const_int(2)))
    graph = to_graph(Program((("x", INT),), body, INT))
    # add, mul, var, const — four distinct nodes, not six.
    assert len(graph) == 4


def test_compact_projection_is_shorter_than_the_sexpr_baseline():
    """Condition E's premise: the compact projection actually compresses. If it did not, E
    would be indistinguishable from D and condition F would have nothing to match."""
    sexpr = get_projection("sexpr")
    compact = get_projection("compact")
    sexpr_tokens = compact_tokens = 0
    for i in range(300):
        program = random_program(random.Random(i))
        sexpr_tokens += token_count(sexpr.render(program.body))
        compact_tokens += token_count(compact.render(program.body))
    assert compact_tokens < sexpr_tokens
    assert sexpr_tokens / compact_tokens > 1.2


@pytest.mark.parametrize("name", PROJECTION_NAMES)
def test_no_code_path_treats_a_projection_as_canonical_semantics(name):
    """M2 acceptance 4 / design principle P8.

    Two checks. First, structurally: the canonicalizer's serialization must not contain any
    projection-specific lexeme, so a hash can never depend on how a term was written. Second,
    by construction: programs rendered in *different* projections and read back must be the
    same semantic object.
    """
    from bestsad.bsir.canonicalize import canonical_serialization

    projection = get_projection(name)
    program = random_program(random.Random(42))
    canonical = canonical_serialization(program.body)

    # The canonical form is written in K0 op names, never in projection symbols.
    for op, symbol in projection.symbols.items():
        if symbol != op and symbol not in {"(", ")"}:
            token = f"{symbol} "
            assert token not in canonical, (
                f"canonical serialization leaked the {name} lexeme {symbol!r}"
            )

    others = [get_projection(other) for other in PROJECTION_NAMES]
    hashes = {
        semantic_hash(Program(program.params, p.parse(p.render(program.body)), None))
        for p in others
    }
    assert len(hashes) == 1, "semantic identity depends on the projection used — P8 violated"


def test_verify_rejects_ill_typed_programs():
    from bestsad.kernel import BOOL, INT, app, const_bool, const_int

    good = Program((), app("add", const_int(1), const_int(2)), INT)
    assert verify(good).ok

    bad = Program((), app("add", const_int(1), const_bool(True)), INT)
    report = verify(bad)
    assert not report.ok and report.layer == "V1"


def test_verify_rejects_unregistered_primitives():
    from bestsad.kernel import INT, Term, var

    bad = Program((("x", INT),), Term("prim:unknown", (var("x"),)), INT)
    report = verify(bad)
    assert not report.ok and report.layer == "V0"


def test_verify_rejects_lambda_outside_a_higher_order_position():
    """K0 has no first-class function values (spec §8.3, constrained closures)."""
    from bestsad.kernel import INT, lam, var

    bad = Program((("x", INT),), lam((("y", INT),), var("y")), INT)
    assert not verify(bad).ok
