"""Source terms for a described language.

A K0 `Term` refuses any operation the kernel does not know — deliberately, since it is the
kernel's program representation and the kernel's vocabulary is frozen. A BSLD source program
is written in a *different* vocabulary, so it is not a `Term` and must not pretend to be one.

Keeping the two types apart is ADR 0013 made structural rather than merely stated: a source
term is a surface, a `Term` is canonical semantics, and the only way from one to the other is
`lowering.lower`. Nothing can accidentally hash, execute, or typecheck a source term, because
every one of those functions takes a `Term` and a `SourceTerm` is not one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from ..kernel.types import Ty


@dataclass(frozen=True, slots=True)
class SourceTerm:
    """One node of a program written in a described language.

    Unlike `Term` this validates nothing about `op`: which operations exist is a property of
    the descriptor, and it is `lowering.lower` that checks membership. A source term whose
    operation no descriptor defines is not malformed, merely un-lowerable, and the difference
    matters when the descriptor is chosen after the program is parsed.
    """

    op: str
    args: tuple["SourceTerm", ...] = ()
    attrs: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if tuple(sorted(self.attrs, key=lambda kv: kv[0])) != self.attrs:
            object.__setattr__(
                self, "attrs", tuple(sorted(self.attrs, key=lambda kv: kv[0]))
            )

    def attr(self, key: str, default: Any = None) -> Any:
        for k, v in self.attrs:
            if k == key:
                return v
        return default

    def walk(self) -> Iterator["SourceTerm"]:
        yield self
        for a in self.args:
            yield from a.walk()

    def ops_used(self) -> set[str]:
        return {t.op for t in self.walk()}


@dataclass(frozen=True, slots=True)
class SourceProgram:
    """A program in a described language: typed parameters and a source body."""

    params: tuple[tuple[str, Ty], ...] = ()
    body: SourceTerm = SourceTerm("nil")
    result_type: Ty | None = None


def s(op: str, *args: SourceTerm, **attrs: Any) -> SourceTerm:
    """Terse constructor for source terms, for fixtures and descriptor authors."""
    return SourceTerm(op, tuple(args), tuple(sorted(attrs.items())))


def slam(params: tuple[tuple[str, Ty], ...], body: SourceTerm) -> SourceTerm:
    """A binder in source position.

    Templates cannot synthesize binders (ADR 0014), so every lambda in a lowered program came
    from the source program, and this is how it gets there.
    """
    return SourceTerm("lam", (body,), (("params", params),))
