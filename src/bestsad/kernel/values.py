"""K0 runtime values and their canonical digests.

Values are immutable. `Pair`, `Just`/`NOTHING`, and `Closure` exist so that runtime type is
unambiguous — in particular so that `Bool` is never confused with `Int`, which Python's
`bool <: int` would otherwise make easy.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Pair:
    fst: Any
    snd: Any


@dataclass(frozen=True, slots=True)
class Just:
    value: Any


class _Nothing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "Nothing"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Nothing)

    def __hash__(self) -> int:
        return hash("k0.nothing")


NOTHING = _Nothing()


@dataclass(frozen=True, slots=True)
class Closure:
    """A K0 closure. Only ever constructed by `lam` in a higher-order operand position."""

    params: tuple[str, ...]
    body: Any  # Term; untyped here to avoid a circular import
    env: tuple[tuple[str, Any], ...]


def encode(value: Any) -> bytes:
    """Canonical byte encoding of a value.

    Injective across the K0 value domain: every distinct value encodes to distinct bytes.
    Used for the execution trace hash and for structural equality in `eq`.
    """
    out = bytearray()
    _encode_into(value, out)
    return bytes(out)


def _encode_into(value: Any, out: bytearray) -> None:
    # bool before int: bool is a subclass of int in Python.
    if isinstance(value, bool):
        out += b"b1" if value else b"b0"
    elif isinstance(value, int):
        out += b"i"
        out += str(value).encode()
        out += b";"
    elif isinstance(value, tuple):  # List
        out += b"l"
        out += str(len(value)).encode()
        out += b":"
        for item in value:
            _encode_into(item, out)
        out += b";"
    elif isinstance(value, Pair):
        out += b"p"
        _encode_into(value.fst, out)
        _encode_into(value.snd, out)
    elif isinstance(value, Just):
        out += b"s"
        _encode_into(value.value, out)
    elif isinstance(value, _Nothing):
        out += b"n"
    elif isinstance(value, Closure):
        # Closures are not comparable data; they are encoded by identity of their body hash so
        # that a trace containing one is still deterministic.
        out += b"f"
        out += repr(value.params).encode()
        out += b"@"
        out += hashlib.blake2b(repr(value.body).encode(), digest_size=8).digest()
    else:  # pragma: no cover - unreachable for well-typed programs
        raise TypeError(f"not a K0 value: {value!r}")


def value_equal(a: Any, b: Any) -> bool:
    """Structural equality, used by the `eq` operation."""
    return encode(a) == encode(b)


def digest(value: Any) -> str:
    return hashlib.blake2b(encode(value), digest_size=16).hexdigest()


def render(value: Any) -> str:
    """Human-readable rendering, for reports and failure messages only."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, tuple):
        return "[" + ", ".join(render(v) for v in value) + "]"
    if isinstance(value, Pair):
        return f"({render(value.fst)}, {render(value.snd)})"
    if isinstance(value, Just):
        return f"Some({render(value.value)})"
    if isinstance(value, _Nothing):
        return "None"
    if isinstance(value, Closure):
        return f"<fun/{len(value.params)}>"
    return repr(value)  # pragma: no cover
