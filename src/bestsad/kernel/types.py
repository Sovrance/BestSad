"""K0 type system (spec §8.2).

Types are immutable and hashable so that they can appear inside term attributes and inside
canonical hashes without a separate serialization step.

The type grammar is deliberately closed. Adding a type constructor changes K0 semantics and
therefore starts a new experiment lineage (spec §8.4) and requires an ADR (spec §31.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


class Ty:
    """Base class for K0 types."""

    def __str__(self) -> str:  # pragma: no cover - overridden by every subclass
        raise NotImplementedError

    def children(self) -> tuple["Ty", ...]:
        return ()


@dataclass(frozen=True, slots=True)
class TBool(Ty):
    def __str__(self) -> str:
        return "Bool"


@dataclass(frozen=True, slots=True)
class TInt(Ty):
    def __str__(self) -> str:
        return "Int"


@dataclass(frozen=True, slots=True)
class TList(Ty):
    elem: Ty

    def __str__(self) -> str:
        return f"List<{self.elem}>"

    def children(self) -> tuple[Ty, ...]:
        return (self.elem,)


@dataclass(frozen=True, slots=True)
class TTuple(Ty):
    fst: Ty
    snd: Ty

    def __str__(self) -> str:
        return f"Tuple<{self.fst},{self.snd}>"

    def children(self) -> tuple[Ty, ...]:
        return (self.fst, self.snd)


@dataclass(frozen=True, slots=True)
class TOption(Ty):
    elem: Ty

    def __str__(self) -> str:
        return f"Option<{self.elem}>"

    def children(self) -> tuple[Ty, ...]:
        return (self.elem,)


@dataclass(frozen=True, slots=True)
class TFun(Ty):
    """Constrained closure type (spec §8.3).

    Function types exist only so that `map`/`filter`/`fold` can take a body. K0 has no
    first-class function values outside those positions: a `lam` may appear only as a
    higher-order operand, which the typechecker enforces.
    """

    params: tuple[Ty, ...]
    ret: Ty

    def __str__(self) -> str:
        inner = ",".join(str(p) for p in self.params)
        return f"Fun<({inner})->{self.ret}>"

    def children(self) -> tuple[Ty, ...]:
        return (*self.params, self.ret)


@dataclass(frozen=True, slots=True)
class TVar(Ty):
    """Type variable, used only inside op signatures — never inside a checked program."""

    name: str

    def __str__(self) -> str:
        return f"'{self.name}"


BOOL = TBool()
INT = TInt()

#: The closed set of element types permitted inside `List<T>` at task-generation time
#: ("a small closed set of T", spec §8.2). The typechecker itself is not restricted to these;
#: this is the generator's palette.
GENERATOR_ELEM_TYPES: tuple[Ty, ...] = (INT, BOOL, TTuple(INT, INT), TList(INT))


def walk(ty: Ty) -> Iterator[Ty]:
    yield ty
    for child in ty.children():
        yield from walk(child)


def is_ground(ty: Ty) -> bool:
    """True when `ty` contains no type variables."""
    return not any(isinstance(t, TVar) for t in walk(ty))


def parse_type(text: str) -> Ty:
    """Parse the `str(Ty)` surface form back into a type.

    Used by schema round-trips and by the primitive registry, which stores types as strings
    (`primitive_record.schema.json` declares `input_types` as an array of strings).
    """
    ty, rest = _parse_type(text.strip())
    if rest.strip():
        raise ValueError(f"trailing text in type: {text!r}")
    return ty


def _parse_type(s: str) -> tuple[Ty, str]:
    s = s.lstrip()
    if s.startswith("Bool"):
        return BOOL, s[4:]
    if s.startswith("Int"):
        return INT, s[3:]
    if s.startswith("'"):
        i = 1
        while i < len(s) and (s[i].isalnum() or s[i] == "_"):
            i += 1
        return TVar(s[1:i]), s[i:]
    for name, ctor in (("List<", TList), ("Option<", TOption)):
        if s.startswith(name):
            inner, rest = _parse_type(s[len(name) :])
            rest = _expect(rest, ">")
            return ctor(inner), rest
    if s.startswith("Tuple<"):
        a, rest = _parse_type(s[6:])
        rest = _expect(rest, ",")
        b, rest = _parse_type(rest)
        rest = _expect(rest, ">")
        return TTuple(a, b), rest
    if s.startswith("Fun<("):
        rest = s[5:]
        params: list[Ty] = []
        rest = rest.lstrip()
        if rest.startswith(")"):
            rest = rest[1:]
        else:
            while True:
                p, rest = _parse_type(rest)
                params.append(p)
                rest = rest.lstrip()
                if rest.startswith(","):
                    rest = rest[1:]
                    continue
                rest = _expect(rest, ")")
                break
        rest = _expect(rest, "->")
        ret, rest = _parse_type(rest)
        rest = _expect(rest, ">")
        return TFun(tuple(params), ret), rest
    raise ValueError(f"cannot parse type at: {s!r}")


def _expect(s: str, token: str) -> str:
    s = s.lstrip()
    if not s.startswith(token):
        raise ValueError(f"expected {token!r} at {s!r}")
    return s[len(token) :]
