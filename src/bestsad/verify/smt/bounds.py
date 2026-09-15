"""The bounded-domain policy a symbolic verdict is relative to (design §2.3, §2.4).

A solver proof over K0 is a proof over *some* domain, and the only honest verdict names it. The
`EquivalenceContract` already carries a `solver_scope` string; this module gives that string a
grammar and turns it into the assumptions and the coverage figure every `EQUIV_SYMBOLIC` result
must carry.

Two of the bounds are exact and two are not:

* the integer magnitude bound defaults to K0's own `INT_ABS_LIMIT`, so the integer domain is
  covered exhaustively unless a contract narrows it on purpose;
* the list-length bound `N` is a genuine restriction below `LIST_LEN_LIMIT`. Lists are unrolled
  into `N` element slots, so any input under which some list -- an input or an intermediate --
  would exceed `N` is outside the verified domain. With `N == LIST_LEN_LIMIT` the encoding is
  exact and "too long" is the K0 trap `list_too_long` rather than a domain exclusion;
* fuel and depth are not modelled at all in v0.1 (ADR-0019), which is an assumption rather
  than a bound.

Coverage is *stated*, never estimated: it is `1.0` when every bound is exact for the declared
types, and otherwise the product of the bound ratios that actually applied, with the basis
recorded beside the number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ...kernel.ops import INT_ABS_LIMIT, LIST_LEN_LIMIT
from ...kernel.types import TInt, TList, Ty, walk

#: The assumption every v0.1 symbolic verdict carries (ADR-0019: fuel excluded).
FUEL_ASSUMPTION = "fuel_and_depth_traps_excluded"

DEFAULT_LIST_BOUND = 8
DEFAULT_TIMEOUT_MS = 5_000
DEFAULT_UNROLL_DEPTH = 3

_KEYS = ("list_bound", "int_abs_limit", "timeout_ms", "unroll_depth")


@dataclass(frozen=True, slots=True)
class SolverScope:
    """The declared solver scope: what the proof ranges over and how long it may take."""

    list_bound: int = DEFAULT_LIST_BOUND
    int_abs_limit: int = INT_ABS_LIMIT
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    unroll_depth: int = DEFAULT_UNROLL_DEPTH

    def __post_init__(self) -> None:
        if not 1 <= self.list_bound <= LIST_LEN_LIMIT:
            raise ValueError(
                f"list_bound must be in [1, {LIST_LEN_LIMIT}], got {self.list_bound}"
            )
        if not 0 <= self.int_abs_limit <= INT_ABS_LIMIT:
            raise ValueError(
                f"int_abs_limit must be in [0, {INT_ABS_LIMIT}], got {self.int_abs_limit}"
            )
        if self.timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be positive, got {self.timeout_ms}")
        if self.unroll_depth < 1:
            raise ValueError(f"unroll_depth must be at least 1, got {self.unroll_depth}")

    # -- the contract string -----------------------------------------------------------------

    @classmethod
    def parse(cls, text: str | None) -> "SolverScope":
        """Parse `EquivalenceContract.solver_scope`: `key=value` pairs separated by `;`.

        `None` and the empty string mean the defaults. An unknown key is an error rather than
        being ignored: a contract that says `list_bond=4096` meant something, and silently
        proving over `N = 8` instead would report a narrower claim under a wider label.
        """
        if text is None or not text.strip():
            return cls()
        values: dict[str, int] = {}
        for item in text.split(";"):
            item = item.strip()
            if not item:
                continue
            key, sep, raw = item.partition("=")
            key = key.strip()
            if not sep or key not in _KEYS:
                raise ValueError(f"unknown solver_scope entry {item!r}; keys are {_KEYS}")
            try:
                values[key] = int(raw.strip())
            except ValueError:
                raise ValueError(f"solver_scope entry {item!r} is not an integer") from None
        return cls(**values)

    def render(self) -> str:
        return ";".join(f"{k}={getattr(self, k)}" for k in _KEYS)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in _KEYS}

    # -- what the bounds mean ----------------------------------------------------------------

    @property
    def lists_exact(self) -> bool:
        """With `N == LIST_LEN_LIMIT` no K0 list is excluded; over-length is the K0 trap."""
        return self.list_bound == LIST_LEN_LIMIT

    @property
    def ints_exact(self) -> bool:
        return self.int_abs_limit == INT_ABS_LIMIT

    def assumptions(self) -> tuple[str, ...]:
        """The assumptions an `EQUIV_SYMBOLIC` verdict under this scope carries, at minimum."""
        out = [FUEL_ASSUMPTION, f"list_length_le_{self.list_bound}"]
        if not self.ints_exact:
            out.append(f"int_abs_le_{self.int_abs_limit}")
        return tuple(out)

    def coverage(self, param_types: Iterable[Ty], *, list_bound_applied: bool) -> tuple[float, str]:
        """Verification coverage (spec §19.1) as a stated ratio, with its basis.

        `list_bound_applied` is reported by the encoder: True when any list -- an input or an
        intermediate such as a `range` result -- was capped at `N`. Integer-only and Bool-only
        programs under the exact integer bound are covered exhaustively.
        """
        types = list(param_types)
        has_list = list_bound_applied or any(
            isinstance(t, TList) for ty in types for t in walk(ty)
        )
        has_int = any(isinstance(t, TInt) for ty in types for t in walk(ty))
        ratio = 1.0
        basis: list[str] = []
        if has_list and not self.lists_exact:
            ratio *= self.list_bound / LIST_LEN_LIMIT
            basis.append(f"list_bound/LIST_LEN_LIMIT = {self.list_bound}/{LIST_LEN_LIMIT}")
        if has_int and not self.ints_exact:
            ratio *= self.int_abs_limit / INT_ABS_LIMIT
            basis.append(f"int_abs_limit/INT_ABS_LIMIT = {self.int_abs_limit}/{INT_ABS_LIMIT}")
        if not basis:
            basis.append("exhaustive over the declared types; every bound is exact")
        return ratio, "; ".join(basis)
