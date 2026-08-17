"""K0 reference interpreter (spec §29.1).

`Kernel.execute(program, inputs)` returns a deterministic `Value | Trap` plus an execution
trace hash. This module is **trusted and frozen** (spec §6.1, `AGENTS.md` invariant 1).

Determinism properties, asserted by `tests/kernel/`:

* Same program + same inputs → same outcome and same trace hash, across runs and processes.
* Totality: every well-typed program yields `Value` or `Trap`; no host exception escapes.
* No ambient effects: no clock, randomness, I/O, or global mutable state is reachable.

Fuel and depth are metered so that non-terminating-shaped programs trap rather than hang.
K0 has no recursion or unbounded loops — iteration is only via `map`/`filter`/`fold` over
finite lists — so fuel exhaustion indicates a program that is large or quadratic, not one that
diverges. It is still a semantic outcome and is reported as a trap.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .ops import (
    DEFAULT_DEPTH_LIMIT,
    DEFAULT_FUEL,
    INT_ABS_LIMIT,
    LIST_LEN_LIMIT,
)
from .terms import Program, Term
from .traps import Trap, TrapKind, TrapSignal
from .values import Closure, Just, NOTHING, Pair, encode, value_equal


@dataclass(slots=True)
class ExecutionResult:
    """Outcome of one execution: a value or a trap, plus deterministic accounting."""

    value: Any = None
    trap: Trap | None = None
    trace_hash: str = ""
    steps: int = 0
    fuel_used: int = 0

    @property
    def ok(self) -> bool:
        return self.trap is None

    def same_outcome(self, other: "ExecutionResult") -> bool:
        """Outcome equality as the evaluator defines correctness: value equality, or the same
        trap kind. Trace hashes are *not* part of correctness — two different programs may
        compute the same function by different routes."""
        if self.trap is not None or other.trap is not None:
            return (
                self.trap is not None
                and other.trap is not None
                and self.trap.kind is other.trap.kind
            )
        return value_equal(self.value, other.value)

    def __str__(self) -> str:
        from .values import render

        return str(self.trap) if self.trap is not None else render(self.value)


@dataclass(slots=True)
class _State:
    fuel: int
    depth_limit: int
    steps: int = 0
    hasher: Any = field(default_factory=lambda: hashlib.blake2b(digest_size=16))

    def tick(self) -> None:
        self.steps += 1
        if self.steps > self.fuel:
            raise TrapSignal(TrapKind.FUEL_EXHAUSTED, f"fuel {self.fuel} exhausted")

    def charge(self, units: int) -> None:
        """Charge fuel proportional to work done.

        Every operation costs 1 (`tick`). Operations whose cost is proportional to the size of
        a list they build or traverse, or of a value they compare structurally, charge that
        size in addition. Without this, `range(0, 4096)` would cost the same as `add`, and fuel
        would not bound actual work — which matters twice over, because fuel decides which
        programs trap (semantics) and because search budgets are metered in kernel steps
        (spec §26.4).
        """
        if units <= 0:
            return
        self.steps += units
        if self.steps > self.fuel:
            raise TrapSignal(TrapKind.FUEL_EXHAUSTED, f"fuel {self.fuel} exhausted")

    def record(self, op: str, value: Any) -> None:
        self.hasher.update(op.encode())
        self.hasher.update(b"\x00")
        self.hasher.update(encode(value))
        self.hasher.update(b"\x01")


class Kernel:
    """The trusted K0 evaluator.

    `primitive_expansions` maps a genome primitive id (`prim:*`) to a `Closure`-like expansion
    `(param_names, body_term)`. Primitives are **macros over K0**: they are expanded here, so
    a genome can never introduce semantics K0 does not already have (spec §5 P2, P9).
    """

    def __init__(
        self,
        primitive_expansions: Mapping[str, tuple[tuple[str, ...], Term]] | None = None,
        *,
        fuel: int = DEFAULT_FUEL,
        depth_limit: int = DEFAULT_DEPTH_LIMIT,
    ) -> None:
        self.primitive_expansions = dict(primitive_expansions or {})
        self.fuel = fuel
        self.depth_limit = depth_limit

    # -- public API ------------------------------------------------------------------------

    def execute(
        self,
        program: Program,
        inputs: Sequence[Any],
        *,
        fuel: int | None = None,
    ) -> ExecutionResult:
        """Execute `program` on `inputs`. Never raises for a well-formed program."""
        names = program.param_names()
        if len(inputs) != len(names):
            return ExecutionResult(
                trap=Trap(TrapKind.MALFORMED_PROGRAM, "argument count mismatch"),
                trace_hash="",
            )
        env = dict(zip(names, inputs))
        state = _State(fuel=fuel if fuel is not None else self.fuel,
                       depth_limit=self.depth_limit)
        try:
            value = self._eval(program.body, env, state, 0)
            return ExecutionResult(
                value=value,
                trace_hash=state.hasher.hexdigest(),
                steps=state.steps,
                fuel_used=state.steps,
            )
        except TrapSignal as sig:
            return ExecutionResult(
                trap=sig.trap,
                trace_hash=state.hasher.hexdigest(),
                steps=state.steps,
                fuel_used=state.steps,
            )
        except RecursionError:
            return ExecutionResult(
                trap=Trap(TrapKind.DEPTH_EXCEEDED, "host recursion limit"),
                trace_hash=state.hasher.hexdigest(),
                steps=state.steps,
            )

    def expand(self, term: Term) -> Term:
        """Fully expand genome primitives into K0. Used by ablation (spec §42.1) and by the
        semantic-hash canonicalizer, which hashes the expanded form so that a macro and its
        expansion are the same semantic object."""
        if term.op.startswith("prim:"):
            if term.op not in self.primitive_expansions:
                raise TrapSignal(TrapKind.MALFORMED_PROGRAM, f"unknown primitive {term.op}")
            params, body = self.primitive_expansions[term.op]
            args = tuple(self.expand(a) for a in term.args)
            return self.expand(_substitute(body, dict(zip(params, args))))
        if not term.args:
            return term
        return Term(term.op, tuple(self.expand(a) for a in term.args), term.attrs)

    # -- evaluation ------------------------------------------------------------------------

    def _eval(self, term: Term, env: dict[str, Any], st: _State, depth: int) -> Any:
        if depth > st.depth_limit:
            raise TrapSignal(TrapKind.DEPTH_EXCEEDED, f"depth {depth}")
        st.tick()
        op = term.op

        # -- non-strict operation (the only one) --
        if op == "if":
            cond = self._eval(term.args[0], env, st, depth + 1)
            branch = term.args[1] if cond else term.args[2]
            value = self._eval(branch, env, st, depth + 1)
            st.record(op, value)
            return value

        if op == "lam":
            params = tuple(n for n, _ in term.attr("params"))
            value = Closure(params, term.args[0], tuple(sorted(env.items(), key=lambda kv: kv[0])))
            return value

        if op.startswith("prim:"):
            expansion = self.primitive_expansions.get(op)
            if expansion is None:
                raise TrapSignal(TrapKind.MALFORMED_PROGRAM, f"unknown primitive {op}")
            params, body = expansion
            args = [self._eval(a, env, st, depth + 1) for a in term.args]
            inner = dict(zip(params, args))
            value = self._eval(body, inner, st, depth + 1)
            st.record(op, value)
            return value

        # -- strict operations --
        args = [self._eval(a, env, st, depth + 1) for a in term.args]
        value = self._apply(op, args, term, env, st, depth)
        st.record(op, value)
        return value

    def _apply(
        self,
        op: str,
        a: list[Any],
        term: Term,
        env: dict[str, Any],
        st: _State,
        depth: int,
    ) -> Any:
        if op == "const_int":
            return _bounded(term.attr("value"))
        if op == "const_bool":
            return bool(term.attr("value"))
        if op == "var":
            name = term.attr("name")
            if name not in env:
                raise TrapSignal(TrapKind.MALFORMED_PROGRAM, f"unbound variable {name}")
            return env[name]

        # arithmetic
        if op == "add":
            return _bounded(a[0] + a[1])
        if op == "sub":
            return _bounded(a[0] - a[1])
        if op == "mul":
            return _bounded(a[0] * a[1])
        if op == "div":
            if a[1] == 0:
                raise TrapSignal(TrapKind.DIVISION_BY_ZERO, "div")
            return _bounded(_trunc_div(a[0], a[1]))
        if op == "mod":
            if a[1] == 0:
                raise TrapSignal(TrapKind.DIVISION_BY_ZERO, "mod")
            return _bounded(a[0] - _trunc_div(a[0], a[1]) * a[1])
        if op == "neg":
            return _bounded(-a[0])
        if op == "abs":
            return _bounded(abs(a[0]))
        if op == "min":
            return a[0] if a[0] <= a[1] else a[1]
        if op == "max":
            return a[0] if a[0] >= a[1] else a[1]

        # comparison
        if op == "eq":
            st.charge(_value_cost(a[0]) + _value_cost(a[1]))
            return value_equal(a[0], a[1])
        if op == "lt":
            return a[0] < a[1]
        if op == "le":
            return a[0] <= a[1]
        if op == "gt":
            return a[0] > a[1]
        if op == "ge":
            return a[0] >= a[1]

        # boolean
        if op == "and":
            return bool(a[0]) and bool(a[1])
        if op == "or":
            return bool(a[0]) or bool(a[1])
        if op == "not":
            return not bool(a[0])

        # tuples
        if op == "tuple":
            return Pair(a[0], a[1])
        if op == "fst":
            return a[0].fst
        if op == "snd":
            return a[0].snd

        # lists
        if op == "nil":
            return ()
        if op == "cons":
            st.charge(len(a[1]))
            return _bounded_list((a[0],) + a[1])
        if op == "head":
            return Just(a[0][0]) if a[0] else NOTHING
        if op == "tail":
            st.charge(max(0, len(a[0]) - 1))
            return a[0][1:]
        if op == "length":
            return len(a[0])
        if op == "index":
            idx = a[1]
            lst = a[0]
            return Just(lst[idx]) if 0 <= idx < len(lst) else NOTHING
        if op == "append":
            st.charge(len(a[0]) + len(a[1]))
            return _bounded_list(a[0] + a[1])
        if op == "range":
            lo, hi = a[0], a[1]
            if hi - lo > LIST_LEN_LIMIT:
                raise TrapSignal(TrapKind.LIST_TOO_LONG, "range")
            st.charge(max(0, hi - lo))
            return tuple(range(lo, hi)) if hi > lo else ()

        # options
        if op == "some":
            return Just(a[0])
        if op == "none":
            return NOTHING
        if op == "option_get_or":
            return a[0].value if isinstance(a[0], Just) else a[1]
        if op == "is_some":
            return isinstance(a[0], Just)

        # higher-order
        if op == "map":
            fn, lst = a[0], a[1]
            st.charge(len(lst))
            return _bounded_list(tuple(self._call(fn, (x,), st, depth) for x in lst))
        if op == "filter":
            fn, lst = a[0], a[1]
            st.charge(len(lst))
            return tuple(x for x in lst if self._call(fn, (x,), st, depth))
        if op == "fold":
            fn, acc, lst = a[0], a[1], a[2]
            st.charge(len(lst))
            for x in lst:
                acc = self._call(fn, (acc, x), st, depth)
            return acc

        raise TrapSignal(TrapKind.MALFORMED_PROGRAM, f"unhandled op {op}")  # pragma: no cover

    def _call(self, fn: Closure, args: tuple[Any, ...], st: _State, depth: int) -> Any:
        if not isinstance(fn, Closure):  # pragma: no cover - typechecker prevents this
            raise TrapSignal(TrapKind.MALFORMED_PROGRAM, "callee is not a closure")
        env = dict(fn.env)
        env.update(dict(zip(fn.params, args)))
        return self._eval(fn.body, env, st, depth + 1)


# -- helpers ---------------------------------------------------------------------------------


def _trunc_div(x: int, y: int) -> int:
    """Division truncated toward zero (K0 semantics), not Python's floor division."""
    q = abs(x) // abs(y)
    return q if (x >= 0) == (y >= 0) else -q


def _bounded(value: int) -> int:
    if value > INT_ABS_LIMIT or value < -INT_ABS_LIMIT:
        raise TrapSignal(TrapKind.VALUE_TOO_LARGE, "int bound")
    return value


def _value_cost(value: Any) -> int:
    """Number of scalar cells in a value — the unit structural comparison is charged in."""
    if isinstance(value, tuple):
        return 1 + sum(_value_cost(v) for v in value)
    if isinstance(value, Pair):
        return 1 + _value_cost(value.fst) + _value_cost(value.snd)
    if isinstance(value, Just):
        return 1 + _value_cost(value.value)
    return 1


def _bounded_list(value: tuple) -> tuple:
    if len(value) > LIST_LEN_LIMIT:
        raise TrapSignal(TrapKind.LIST_TOO_LONG, f"len {len(value)}")
    return value


def _substitute(term: Term, bindings: Mapping[str, Term]) -> Term:
    """Capture-avoiding only in the weak sense K0 needs: `lam` parameter names shadow."""
    if term.op == "var":
        name = term.attr("name")
        return bindings.get(name, term)
    if term.op == "lam":
        shadowed = {n for n, _ in term.attr("params")}
        inner = {k: v for k, v in bindings.items() if k not in shadowed}
        return Term(term.op, (_substitute(term.args[0], inner),), term.attrs)
    if not term.args:
        return term
    return Term(term.op, tuple(_substitute(a, bindings) for a in term.args), term.attrs)
