"""Canonicalization and the canonical semantic hash (spec §9.4).

The hash is taken over normalized BSIR, never over surface syntax. Normalization does exactly
two things, and deliberately not a third:

1. **Primitive expansion.** Genome primitives (`prim:*`) are macros over K0 (spec §5 P2/P9), so
   a primitive and its expansion denote the same semantic object and must hash alike. Without
   this, promoting an abstraction would change the identity of every program using it.

2. **Alpha-normalization.** Bound variable names are a projection artefact. Parameters are
   renamed by position and lambda-bound variables by binding depth, so programs differing only
   in variable naming hash identically.

**Not done: reordering the operands of commutative operations.** This looks like an obvious
normalization and is unsound in K0. K0's binary operations are strict and evaluate left to
right, and traps are distinguishable outcomes, so `add(div(1,0), mul(2^40, 2^40))` traps with
`division_by_zero` while the reversed form traps with `value_too_large`. The two terms are not
semantically equal, and a canonicalizer that merged them would let a rewrite silently change a
program's observable outcome. Stronger normalization requires trap-freedom evidence per operand
and belongs with the equality-saturation engine (M11), which can carry that evidence as a
proof obligation rather than assuming it.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from ..kernel.interpreter import Kernel
from ..kernel.terms import Program, Term
from ..kernel.types import Ty

CANONICAL_PARAM = "p"
CANONICAL_BOUND = "b"


def alpha_normalize(term: Term, renaming: Mapping[str, str], depth: int = 0) -> Term:
    """Rename bound variables canonically. `renaming` maps outer names to canonical ones."""
    if term.op == "var":
        name = term.attr("name")
        return Term("var", (), (("name", renaming.get(name, name)),))
    if term.op == "lam":
        params = term.attr("params")
        inner = dict(renaming)
        new_params = []
        for i, (name, ty) in enumerate(params):
            canonical = f"{CANONICAL_BOUND}{depth}_{i}"
            inner[name] = canonical
            new_params.append((canonical, ty))
        body = alpha_normalize(term.args[0], inner, depth + 1)
        return Term("lam", (body,), (("params", tuple(new_params)),))
    if not term.args:
        return term
    return Term(
        term.op,
        tuple(alpha_normalize(a, renaming, depth) for a in term.args),
        term.attrs,
    )


def canonical_program(program: Program, kernel: Kernel | None = None) -> Program:
    """Canonical form of a program: primitives expanded, variables alpha-normalized."""
    body = program.body
    if kernel is not None:
        body = kernel.expand(body)
    renaming = {name: f"{CANONICAL_PARAM}{i}" for i, (name, _) in enumerate(program.params)}
    body = alpha_normalize(body, renaming)
    params = tuple((f"{CANONICAL_PARAM}{i}", ty) for i, (_, ty) in enumerate(program.params))
    return Program(params=params, body=body, result_type=program.result_type)


def _encode_attr(value: Any) -> str:
    if isinstance(value, Ty):
        return f"T({value})"
    if isinstance(value, bool):
        return f"B({int(value)})"
    if isinstance(value, int):
        return f"I({value})"
    if isinstance(value, str):
        return f"S({value})"
    if isinstance(value, tuple):
        return "(" + ",".join(_encode_attr(v) for v in value) + ")"
    return f"O({value!r})"  # pragma: no cover - attributes are drawn from the above


def canonical_serialization(term: Term) -> str:
    """Injective, parenthesized serialization of a canonical term."""
    attrs = "".join(f"[{k}={_encode_attr(v)}]" for k, v in term.attrs)
    if not term.args:
        return f"{term.op}{attrs}"
    inner = " ".join(canonical_serialization(a) for a in term.args)
    return f"({term.op}{attrs} {inner})"


def program_serialization(program: Program) -> str:
    params = ",".join(f"{n}:{t}" for n, t in program.params)
    return f"<{params}|{program.result_type}>{canonical_serialization(program.body)}"


def semantic_hash(program: Program, kernel: Kernel | None = None) -> str:
    """Canonical semantic hash of a program (spec §9.4). 256-bit, hex-encoded."""
    canonical = canonical_program(program, kernel)
    return hashlib.sha256(program_serialization(canonical).encode()).hexdigest()


def term_semantic_hash(
    term: Term,
    params: tuple[tuple[str, Ty], ...] = (),
    kernel: Kernel | None = None,
) -> str:
    """Semantic hash of a bare term under a parameter list."""
    return semantic_hash(Program(params=params, body=term, result_type=None), kernel)


def structural_hash(term: Term) -> str:
    """Hash of the term *as written*, without expansion or alpha-normalization.

    Used only where surface identity is the question — for example, detecting that two
    candidates are literally the same text. Never use this where semantics are meant: that is
    what `semantic_hash` is for, and confusing the two is the P8 violation this module exists
    to prevent.
    """
    return hashlib.sha256(canonical_serialization(term).encode()).hexdigest()
