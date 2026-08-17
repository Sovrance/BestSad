"""Trap taxonomy (spec §8.2: effect set is `Pure` and `Trap` only).

Trap behaviour must be **total**: every K0 program on every well-typed input produces either a
`Value` or a `Trap`, never an undefined result and never a host exception that escapes the
interpreter. `tests/kernel/test_totality.py` is the acceptance test for that property (M1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrapKind(str, Enum):
    """The closed set of traps. Adding one changes K0 semantics (spec §8.4)."""

    DIVISION_BY_ZERO = "division_by_zero"
    FUEL_EXHAUSTED = "fuel_exhausted"
    DEPTH_EXCEEDED = "depth_exceeded"
    VALUE_TOO_LARGE = "value_too_large"
    LIST_TOO_LONG = "list_too_long"
    MALFORMED_PROGRAM = "malformed_program"


@dataclass(frozen=True, slots=True)
class Trap:
    """A trapped execution outcome. Compared by kind only — never by message."""

    kind: TrapKind
    detail: str = ""

    def __str__(self) -> str:
        return f"Trap({self.kind.value})"

    def same_outcome(self, other: object) -> bool:
        return isinstance(other, Trap) and other.kind is self.kind


class TrapSignal(Exception):
    """Internal control-flow signal. Never escapes `Interpreter.execute`."""

    def __init__(self, kind: TrapKind, detail: str = "") -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.trap = Trap(kind, detail)
