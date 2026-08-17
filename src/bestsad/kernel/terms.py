"""K0 program terms.

A `Term` is an immutable, hashable node: an operation, its operand terms, and its attributes.
This is the kernel-level program representation. BSIR (spec §9) is built over it and adds the
canonical semantic hash, types, effects, and projections; the kernel itself only needs enough
structure to execute and typecheck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .ops import OPS_BY_NAME
from .types import Ty


@dataclass(frozen=True, slots=True)
class Term:
    op: str
    args: tuple["Term", ...] = ()
    attrs: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.op not in OPS_BY_NAME and not self.op.startswith("prim:"):
            raise ValueError(f"unknown operation {self.op!r}")
        # Attributes are stored sorted so that equal terms are `==` and hash alike.
        if tuple(sorted(self.attrs)) != self.attrs:
            object.__setattr__(self, "attrs", tuple(sorted(self.attrs)))

    def attr(self, key: str, default: Any = None) -> Any:
        for k, v in self.attrs:
            if k == key:
                return v
        return default

    def walk(self) -> Iterator["Term"]:
        yield self
        for a in self.args:
            yield from a.walk()

    def size(self) -> int:
        """Node count, the description-length proxy used throughout (§21.4 uses bits; this is
        the structural size the MDL coder is defined over)."""
        return 1 + sum(a.size() for a in self.args)

    def depth(self) -> int:
        return 1 + max((a.depth() for a in self.args), default=0)

    def ops_used(self) -> set[str]:
        return {t.op for t in self.walk()}

    def __str__(self) -> str:
        from ..bsir.projections import SExprProjection

        return SExprProjection().render(self)


# --- constructors -------------------------------------------------------------------------


def const_int(value: int) -> Term:
    return Term("const_int", (), (("value", int(value)),))


def const_bool(value: bool) -> Term:
    return Term("const_bool", (), (("value", bool(value)),))


def var(name: str) -> Term:
    return Term("var", (), (("name", name),))


def nil(elem_type: Ty) -> Term:
    return Term("nil", (), (("elem_type", elem_type),))


def none(elem_type: Ty) -> Term:
    return Term("none", (), (("elem_type", elem_type),))


def lam(params: tuple[tuple[str, Ty], ...], body: Term) -> Term:
    return Term("lam", (body,), (("params", tuple(params)),))


def app(op: str, *args: Term, **attrs: Any) -> Term:
    return Term(op, tuple(args), tuple(attrs.items()))


@dataclass(frozen=True, slots=True)
class Program:
    """A K0 program: a typed parameter list and a body term."""

    params: tuple[tuple[str, Ty], ...]
    body: Term
    result_type: Ty = field(default=None)  # type: ignore[assignment]

    def size(self) -> int:
        return self.body.size()

    def param_names(self) -> tuple[str, ...]:
        return tuple(n for n, _ in self.params)

    def __str__(self) -> str:
        sig = ", ".join(f"{n}: {t}" for n, t in self.params)
        return f"({sig}) -> {self.result_type} = {self.body}"
