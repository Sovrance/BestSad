"""M2 acceptance: canonical semantic hash (spec §9.4)."""

from __future__ import annotations

import random

from bestsad.bsir import get_projection, semantic_hash, structural_hash, term_semantic_hash
from bestsad.kernel import INT, Kernel, Program, Term, app, const_int, lam, var
from bestsad.kernel.random_programs import random_program


def prog(body: Term, params=(("x", INT),), result=INT) -> Program:
    return Program(params=params, body=body, result_type=result)


def test_programs_differing_only_in_projection_hash_identically():
    """M2 acceptance 1: semantically equivalent graphs that differ only in projection hash
    identically. A projection cannot change the hash, because the hash is not taken over
    surface syntax at all."""
    p = prog(app("add", var("x"), const_int(1)))
    hashes = set()
    for name in ("sexpr", "compact", "human", "graph"):
        projection = get_projection(name)
        text = projection.render(p.body)
        back = projection.parse(text)
        hashes.add(semantic_hash(prog(back)))
    assert len(hashes) == 1


def test_programs_differing_only_in_variable_names_hash_identically():
    a = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
    b = Program((("y", INT),), app("add", var("y"), const_int(1)), INT)
    assert semantic_hash(a) == semantic_hash(b)


def test_lambda_bound_names_are_alpha_normalized():
    lst = app("range", const_int(0), const_int(3))
    a = app("map", lam((("u", INT),), app("mul", var("u"), const_int(2))), lst)
    b = app("map", lam((("w", INT),), app("mul", var("w"), const_int(2))), lst)
    assert term_semantic_hash(a) == term_semantic_hash(b)


def test_semantically_distinct_programs_hash_differently():
    a = prog(app("add", var("x"), const_int(1)))
    b = prog(app("add", var("x"), const_int(2)))
    c = prog(app("sub", var("x"), const_int(1)))
    assert len({semantic_hash(a), semantic_hash(b), semantic_hash(c)}) == 3


def test_collision_rate_is_consistent_with_hash_width():
    """M2 acceptance 2. With SHA-256 and a few thousand distinct programs, the expected number
    of collisions is astronomically below 1; observing any at all would mean the serialization
    is not injective, which is the failure this test actually guards against."""
    seen: dict[str, str] = {}
    collisions = 0
    for i in range(4000):
        program = random_program(random.Random(i))
        h = semantic_hash(program)
        serialized = f"{program.params}|{program.body}"
        if h in seen and seen[h] != serialized:
            collisions += 1
        seen[h] = serialized
    assert collisions == 0


def test_operand_order_is_not_normalized_for_commutative_ops():
    """K0's binary operations are strict and left-to-right, and traps are distinguishable
    outcomes, so `add` is *not* commutative: swapping operands can change which trap fires.
    The canonicalizer must therefore not reorder them — if it did, a rewrite could silently
    change a program's observable result."""
    kernel = Kernel()
    left = app("add", app("div", const_int(1), const_int(0)),
               app("mul", const_int(2**40), const_int(2**40)))
    right = app("add", app("mul", const_int(2**40), const_int(2**40)),
                app("div", const_int(1), const_int(0)))

    assert term_semantic_hash(left) != term_semantic_hash(right)

    a = kernel.execute(Program((), left, INT), [])
    b = kernel.execute(Program((), right, INT), [])
    assert a.trap.kind.value == "division_by_zero"
    assert b.trap.kind.value == "value_too_large"
    assert not a.same_outcome(b)


def test_primitive_and_its_expansion_share_semantic_identity():
    """A genome primitive is a macro over K0 (P2/P9), so it must hash as its expansion —
    otherwise promoting an abstraction would change the identity of every program using it."""
    expansion = app("mul", var("a"), const_int(2))
    kernel = Kernel({"prim:double": (("a",), expansion)})
    with_prim = prog(Term("prim:double", (var("x"),)))
    without = prog(app("mul", var("x"), const_int(2)))
    assert semantic_hash(with_prim, kernel) == semantic_hash(without, kernel)
    # Without expansion the surface forms are of course different objects.
    assert structural_hash(with_prim.body) != structural_hash(without.body)
