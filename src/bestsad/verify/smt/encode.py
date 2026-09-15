"""K0 term -> SMT encoding under K0 v1.0.0 semantics (ADR-0008; design §2.3).

This module is a **second reading of K0**. The first is `kernel/interpreter.py`, which is
normative (ADR-0002). Wherever the two disagree the encoder is wrong, and the two controls that
find such disagreements are `tests/verify/test_encoder_agrees_with_reference.py` and the
counterexample discipline in `solver.py`, which re-executes every model on the reference.

The encoding decisions, each pinned by a test, are:

* `Int` is the SMT integer theory, never a bit-vector -- wraparound would be a semantic lie.
  Every arithmetic result carries the trap guard `|r| > 2^64` (`VALUE_TOO_LARGE`), and so does an
  integer literal, because the reference bounds those too.
* `div` and `mod` truncate toward zero with the dividend's sign on `mod`. Z3's own `div`/`mod`
  are Euclidean and are **not** used directly; the reference's `q = ±(|a| div |b|)` is encoded
  literally, and `mod` as `a - q*b`.
* Every operation except `if` is strict, operands are evaluated left to right, and the *first*
  trap wins: `and(false, div(1, 0))` traps. `if` evaluates its condition, then exactly one
  branch.
* Lists are `(length, N element slots)` under the declared bound `N`. An operation whose result
  would exceed `N` either traps `LIST_TOO_LONG` (when `N == LIST_LEN_LIMIT`, which is the K0
  rule exactly) or excludes that input from the verified domain (when `N` is smaller), and the
  exclusion is recorded so the verdict can say so. `head`, `tail` and `index` are total.
* `eq` is structural equality directed by the operand type.
* `lam` is legal only as a higher-order operand and is inlined at every unrolled position; K0
  has no recursion, so no fixed point is needed. Nesting beyond the declared `unroll_depth`
  is refused.
* Fuel and depth are not modelled (ADR-0019). The encoder never produces `FUEL_EXHAUSTED` or
  `DEPTH_EXCEEDED`; the verdict carries that as an assumption.

Anything the encoder cannot represent raises `Unsupported`, which the adapter turns into
`UNKNOWN` with the reason recorded. It never guesses.

Every domain side-condition (an input bound, a list capped at `N`) is emitted under a *guard*
saying the evaluation it constrains actually happens. Without the guard a `cons` inside an
untaken `if` branch, or inside a `fold` step after an earlier trap, would exclude inputs from
the domain for a reason that never executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ...kernel.ops import HIGHER_ORDER_OPS, INT_ABS_LIMIT, OPS_BY_NAME
from ...kernel.terms import Program, Term
from ...kernel.traps import Trap, TrapKind
from ...kernel.types import TBool, TFun, TInt, TList, TOption, TTuple, TVar, Ty
from ...kernel.values import Just, NOTHING, Pair
from .bounds import SolverScope


class Unsupported(Exception):
    """The encoder cannot represent this program under this scope. The caller reports UNKNOWN."""


#: Trap kinds are encoded as integer indices into the closed ADR-0008 set, in `TrapKind` order.
TRAP_INDEX: dict[TrapKind, int] = {kind: i for i, kind in enumerate(TrapKind)}
TRAP_BY_INDEX: dict[int, TrapKind] = {i: kind for kind, i in TRAP_INDEX.items()}

#: `observable_contract_ref` this encoder implements: the outcome sum type `Value | Trap(kind)`.
OBSERVABLE = "outcome:value-or-trap-kind"


# -- symbolic values ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SymList:
    """A K0 list under the bound: a symbolic length and `N` element slots.

    Slots at or beyond `length` are don't-care. Every consumer (`equal`, `concretize`, the
    element selectors) reads only slots below the length.
    """

    length: Any
    elems: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class SymTuple:
    fst: Any
    snd: Any


@dataclass(frozen=True, slots=True)
class SymOption:
    is_some: Any
    value: Any


@dataclass(frozen=True, slots=True)
class Outcome:
    """The encoded outcome of one evaluation: `Value(value) | Trap(kind)`.

    `kind` is meaningful only where `trapped` holds; `value` only where it does not.
    """

    trapped: Any
    kind: Any
    value: Any
    ty: Ty


@dataclass(frozen=True, slots=True)
class _Closure:
    params: tuple[tuple[str, Ty], ...]
    body: Term
    env: Mapping[str, tuple[Any, Ty]]


class Encoder:
    """Type-directed encoder for K0 programs. One instance per query; not reusable."""

    def __init__(self, scope: SolverScope, z3: Any) -> None:
        self.scope = scope
        self.z3 = z3
        self.N = scope.list_bound
        #: Side conditions on the domain: input bounds and, below `LIST_LEN_LIMIT`, list caps.
        self.constraints: list[Any] = []
        #: True once any list was capped at `N`; the verdict's coverage must then say so.
        self.list_bound_applied = False
        self._hof_depth = 0
        self._fresh = 0

    # -- small z3 helpers -------------------------------------------------------------------

    def _int(self, v: int) -> Any:
        return self.z3.IntVal(v)

    def _bool(self, v: bool) -> Any:
        return self.z3.BoolVal(v)

    def _or(self, *xs: Any) -> Any:
        xs = tuple(x for x in xs if x is not None)
        if not xs:
            return self._bool(False)
        return xs[0] if len(xs) == 1 else self.z3.Or(*xs)

    def _and(self, *xs: Any) -> Any:
        xs = tuple(x for x in xs if x is not None)
        if not xs:
            return self._bool(True)
        return xs[0] if len(xs) == 1 else self.z3.And(*xs)

    def _kind(self, kind: TrapKind) -> Any:
        return self._int(TRAP_INDEX[kind])

    def _name(self, stem: str) -> str:
        self._fresh += 1
        return f"{stem}#{self._fresh}"

    # -- values by type ----------------------------------------------------------------------

    def zero(self, ty: Ty) -> Any:
        """A canonical inhabitant, used for don't-care slots so the encoding stays deterministic."""
        if isinstance(ty, TInt):
            return self._int(0)
        if isinstance(ty, TBool):
            return self._bool(False)
        if isinstance(ty, TList):
            return SymList(self._int(0), tuple(self.zero(ty.elem) for _ in range(self.N)))
        if isinstance(ty, TTuple):
            return SymTuple(self.zero(ty.fst), self.zero(ty.snd))
        if isinstance(ty, TOption):
            return SymOption(self._bool(False), self.zero(ty.elem))
        raise Unsupported(f"no symbolic value for type {ty}")

    def fresh_input(self, name: str, ty: Ty) -> Any:
        """A symbolic inhabitant of `ty` constrained to the declared domain."""
        z3 = self.z3
        if isinstance(ty, TInt):
            x = z3.Int(name)
            limit = self.scope.int_abs_limit
            self.constraints.append(z3.And(x >= -limit, x <= limit))
            return x
        if isinstance(ty, TBool):
            return z3.Bool(name)
        if isinstance(ty, TList):
            length = z3.Int(f"{name}.len")
            self.constraints.append(z3.And(length >= 0, length <= self.N))
            elems = tuple(self.fresh_input(f"{name}.{i}", ty.elem) for i in range(self.N))
            return SymList(length, elems)
        if isinstance(ty, TTuple):
            return SymTuple(self.fresh_input(f"{name}.fst", ty.fst),
                            self.fresh_input(f"{name}.snd", ty.snd))
        if isinstance(ty, TOption):
            return SymOption(z3.Bool(f"{name}.some"), self.fresh_input(f"{name}.val", ty.elem))
        if isinstance(ty, (TFun, TVar)):
            raise Unsupported(f"parameter type {ty} is not enumerable symbolically")
        raise Unsupported(f"unknown type {ty}")  # pragma: no cover

    def inputs(self, params: Sequence[tuple[str, Ty]]) -> dict[str, tuple[Any, Ty]]:
        return {name: (self.fresh_input(f"in.{name}", ty), ty) for name, ty in params}

    def ite(self, cond: Any, a: Any, b: Any, ty: Ty) -> Any:
        """Structural if-then-else over symbolic values."""
        z3 = self.z3
        if isinstance(ty, (TInt, TBool)):
            return z3.If(cond, a, b)
        if isinstance(ty, TList):
            return SymList(
                z3.If(cond, a.length, b.length),
                tuple(self.ite(cond, x, y, ty.elem) for x, y in zip(a.elems, b.elems)),
            )
        if isinstance(ty, TTuple):
            return SymTuple(self.ite(cond, a.fst, b.fst, ty.fst), self.ite(cond, a.snd, b.snd, ty.snd))
        if isinstance(ty, TOption):
            return SymOption(z3.If(cond, a.is_some, b.is_some),
                             self.ite(cond, a.value, b.value, ty.elem))
        raise Unsupported(f"cannot select over type {ty}")

    def equal(self, a: Any, b: Any, ty: Ty) -> Any:
        """Structural equality at a ground type -- what `eq` and the outcome comparison use."""
        z3 = self.z3
        if isinstance(ty, (TInt, TBool)):
            return a == b
        if isinstance(ty, TList):
            per_slot = [
                z3.Implies(self._int(i) < a.length, self.equal(x, y, ty.elem))
                for i, (x, y) in enumerate(zip(a.elems, b.elems))
            ]
            return self._and(a.length == b.length, *per_slot)
        if isinstance(ty, TTuple):
            return self._and(self.equal(a.fst, b.fst, ty.fst), self.equal(a.snd, b.snd, ty.snd))
        if isinstance(ty, TOption):
            return self._and(a.is_some == b.is_some,
                             z3.Implies(a.is_some, self.equal(a.value, b.value, ty.elem)))
        raise Unsupported(f"no structural equality at type {ty}")

    # -- between the model and K0 values -----------------------------------------------------

    def concretize(self, model: Any, sym: Any, ty: Ty) -> Any:
        """Read a K0 value of type `ty` out of a Z3 model."""
        z3 = self.z3
        if isinstance(ty, TInt):
            return model.eval(sym, model_completion=True).as_long()
        if isinstance(ty, TBool):
            return z3.is_true(model.eval(sym, model_completion=True))
        if isinstance(ty, TList):
            n = model.eval(sym.length, model_completion=True).as_long()
            if not 0 <= n <= self.N:
                raise Unsupported(f"model assigns a list length {n} outside [0, {self.N}]")
            return tuple(self.concretize(model, sym.elems[i], ty.elem) for i in range(n))
        if isinstance(ty, TTuple):
            return Pair(self.concretize(model, sym.fst, ty.fst), self.concretize(model, sym.snd, ty.snd))
        if isinstance(ty, TOption):
            if z3.is_true(model.eval(sym.is_some, model_completion=True)):
                return Just(self.concretize(model, sym.value, ty.elem))
            return NOTHING
        raise Unsupported(f"cannot concretize type {ty}")

    def pin(self, sym: Any, value: Any, ty: Ty) -> list[Any] | None:
        """Constraints fixing `sym` to a concrete K0 value, or None if the value exceeds the bound."""
        z3 = self.z3
        if isinstance(ty, TInt):
            return [sym == self._int(int(value))]
        if isinstance(ty, TBool):
            return [sym == self._bool(bool(value))]
        if isinstance(ty, TList):
            if len(value) > self.N:
                return None
            out = [sym.length == self._int(len(value))]
            for i, item in enumerate(value):
                inner = self.pin(sym.elems[i], item, ty.elem)
                if inner is None:
                    return None
                out.extend(inner)
            return out
        if isinstance(ty, TTuple):
            a = self.pin(sym.fst, value.fst, ty.fst)
            b = self.pin(sym.snd, value.snd, ty.snd)
            return None if a is None or b is None else a + b
        if isinstance(ty, TOption):
            if isinstance(value, Just):
                inner = self.pin(sym.value, value.value, ty.elem)
                return None if inner is None else [sym.is_some] + inner
            return [z3.Not(sym.is_some)]
        raise Unsupported(f"cannot pin type {ty}")

    def read_outcome(self, model: Any, outcome: Outcome) -> tuple[Trap | None, Any]:
        """`(trap, value)` for an outcome under a model; exactly one of the two is meaningful."""
        z3 = self.z3
        if z3.is_true(model.eval(outcome.trapped, model_completion=True)):
            index = model.eval(outcome.kind, model_completion=True).as_long()
            return Trap(TRAP_BY_INDEX[index], "symbolic"), None
        return None, self.concretize(model, outcome.value, outcome.ty)

    # -- the outcome algebra -----------------------------------------------------------------

    def _value(self, value: Any, ty: Ty) -> Outcome:
        return Outcome(self._bool(False), self._int(0), value, ty)

    def _combine(
        self,
        args: Sequence[Outcome],
        own: Sequence[tuple[Any, TrapKind]],
        value: Any,
        ty: Ty,
    ) -> Outcome:
        """Strict-operation outcome: the first trapping operand wins, then the op's own traps in
        the order the reference checks them, then the value."""
        z3 = self.z3
        kind = self._int(0)
        for cond, k in reversed(list(own)):
            kind = z3.If(cond, self._kind(k), kind)
        for a in reversed(list(args)):
            kind = z3.If(a.trapped, a.kind, kind)
        trapped = self._or(*[a.trapped for a in args], *[c for c, _ in own])
        return Outcome(trapped, kind, value, ty)

    def _bounded_int(self, r: Any) -> tuple[Any, TrapKind]:
        limit = self._int(INT_ABS_LIMIT)
        return self.z3.Or(r > limit, r < -limit), TrapKind.VALUE_TOO_LARGE

    def _cap(self, guard: Any, length: Any) -> list[tuple[Any, TrapKind]]:
        """A list whose length is `length` is about to be built under `guard`.

        Exact mode (`N == LIST_LEN_LIMIT`): exceeding `N` is the K0 trap. Bounded mode: exceeding
        `N` cannot be represented, so the input is excluded from the domain -- under the guard,
        so an unexecuted branch excludes nothing -- and the exclusion is recorded.
        """
        z3 = self.z3
        over = length > self._int(self.N)
        if self.scope.lists_exact:
            return [(over, TrapKind.LIST_TOO_LONG)]
        self.list_bound_applied = True
        self.constraints.append(z3.Implies(guard, z3.Not(over)))
        return []

    def same_outcome(self, left: Outcome, right: Outcome) -> Any:
        """The equivalence observable: equal trap kind, or equal value (design §2.4)."""
        if left.ty != right.ty:
            raise Unsupported(f"result types differ: {left.ty} vs {right.ty}")
        z3 = self.z3
        return z3.Or(
            z3.And(left.trapped, right.trapped, left.kind == right.kind),
            z3.And(z3.Not(left.trapped), z3.Not(right.trapped),
                   self.equal(left.value, right.value, left.ty)),
        )

    # -- programs and terms ------------------------------------------------------------------

    def program(self, program: Program, env: Mapping[str, tuple[Any, Ty]]) -> Outcome:
        return self.term(program.body, env, self._bool(True))

    def term(self, term: Term, env: Mapping[str, tuple[Any, Ty]], guard: Any) -> Outcome:
        """Encode one term. `guard` holds exactly when the reference would evaluate it."""
        z3 = self.z3
        op = term.op

        if op.startswith("prim:"):
            raise Unsupported(f"unexpanded primitive {op}; expand through the kernel first")
        if op not in OPS_BY_NAME:
            raise Unsupported(f"operation {op!r} is not in K0_OPS")

        if op == "var":
            name = term.attr("name")
            if name not in env:
                raise Unsupported(f"unbound variable {name!r}")
            value, ty = env[name]
            return self._value(value, ty)

        if op == "const_int":
            c = term.attr("value")
            if not isinstance(c, int) or isinstance(c, bool):
                raise Unsupported("const_int without an integer value")
            # The reference bounds literals too (`_bounded(term.attr("value"))`).
            trapped = abs(c) > INT_ABS_LIMIT
            return Outcome(self._bool(trapped), self._kind(TrapKind.VALUE_TOO_LARGE),
                           self._int(c), TInt())

        if op == "const_bool":
            return self._value(self._bool(bool(term.attr("value"))), TBool())

        if op == "nil":
            elem = term.attr("elem_type")
            if not isinstance(elem, Ty):
                raise Unsupported("nil without an elem_type")
            return self._value(self.zero(TList(elem)), TList(elem))

        if op == "none":
            elem = term.attr("elem_type")
            if not isinstance(elem, Ty):
                raise Unsupported("none without an elem_type")
            return self._value(SymOption(self._bool(False), self.zero(elem)), TOption(elem))

        if op == "lam":
            raise Unsupported("lam outside a higher-order operand position")

        if op == "if":
            c = self.term(term.args[0], env, guard)
            live = z3.And(guard, z3.Not(c.trapped))
            t = self.term(term.args[1], env, z3.And(live, c.value))
            e = self.term(term.args[2], env, z3.And(live, z3.Not(c.value)))
            if t.ty != e.ty:
                raise Unsupported(f"if branches have different types: {t.ty} vs {e.ty}")
            trapped = z3.Or(c.trapped, z3.If(c.value, t.trapped, e.trapped))
            kind = z3.If(c.trapped, c.kind, z3.If(c.value, t.kind, e.kind))
            return Outcome(trapped, kind, self.ite(c.value, t.value, e.value, t.ty), t.ty)

        if op in HIGHER_ORDER_OPS:
            return self._hof(op, term, env, guard)

        # -- strict operations: operands left to right, each guarded by the ones before --
        args: list[Outcome] = []
        blocked: Any = None
        for arg in term.args:
            arg_guard = guard if blocked is None else z3.And(guard, z3.Not(blocked))
            out = self.term(arg, env, arg_guard)
            args.append(out)
            blocked = out.trapped if blocked is None else z3.Or(blocked, out.trapped)
        live = guard if blocked is None else z3.And(guard, z3.Not(blocked))
        return self._strict(op, args, live)

    def _strict(self, op: str, a: list[Outcome], live: Any) -> Outcome:
        z3 = self.z3
        v = [x.value for x in a]

        # arithmetic
        if op in ("add", "sub", "mul"):
            r = v[0] + v[1] if op == "add" else v[0] - v[1] if op == "sub" else v[0] * v[1]
            return self._combine(a, [self._bounded_int(r)], r, TInt())
        if op in ("div", "mod"):
            x, y = v
            ax = z3.If(x >= 0, x, -x)
            ay = z3.If(y >= 0, y, -y)
            # SMT-LIB `div` on non-negative operands is truncation; the sign is re-applied
            # exactly as the reference's `_trunc_div` does.
            q = z3.If((x >= 0) == (y >= 0), ax / ay, -(ax / ay))
            r = q if op == "div" else x - q * y
            own = [(y == self._int(0), TrapKind.DIVISION_BY_ZERO), self._bounded_int(r)]
            return self._combine(a, own, r, TInt())
        if op == "neg":
            return self._combine(a, [self._bounded_int(-v[0])], -v[0], TInt())
        if op == "abs":
            r = z3.If(v[0] >= 0, v[0], -v[0])
            return self._combine(a, [self._bounded_int(r)], r, TInt())
        if op == "min":
            return self._combine(a, [], z3.If(v[0] <= v[1], v[0], v[1]), TInt())
        if op == "max":
            return self._combine(a, [], z3.If(v[0] >= v[1], v[0], v[1]), TInt())

        # comparison
        if op == "eq":
            if a[0].ty != a[1].ty:
                raise Unsupported(f"eq over different types: {a[0].ty} vs {a[1].ty}")
            return self._combine(a, [], self.equal(v[0], v[1], a[0].ty), TBool())
        if op in ("lt", "le", "gt", "ge"):
            r = {"lt": v[0] < v[1], "le": v[0] <= v[1], "gt": v[0] > v[1], "ge": v[0] >= v[1]}[op]
            return self._combine(a, [], r, TBool())

        # boolean: strict, so both operands' traps have already been folded in by `_combine`
        if op == "and":
            return self._combine(a, [], z3.And(v[0], v[1]), TBool())
        if op == "or":
            return self._combine(a, [], z3.Or(v[0], v[1]), TBool())
        if op == "not":
            return self._combine(a, [], z3.Not(v[0]), TBool())

        # tuples
        if op == "tuple":
            return self._combine(a, [], SymTuple(v[0], v[1]), TTuple(a[0].ty, a[1].ty))
        if op == "fst":
            return self._combine(a, [], v[0].fst, a[0].ty.fst)
        if op == "snd":
            return self._combine(a, [], v[0].snd, a[0].ty.snd)

        # lists
        if op == "cons":
            xs: SymList = v[1]
            length = xs.length + 1
            elems = (v[0],) + xs.elems[:-1]
            return self._combine(a, self._cap(live, length), SymList(length, elems), a[1].ty)
        if op == "head":
            xs = v[0]
            elem = a[0].ty.elem
            return self._combine(a, [], SymOption(xs.length > 0, xs.elems[0]), TOption(elem))
        if op == "tail":
            xs = v[0]
            elem = a[0].ty.elem
            length = z3.If(xs.length > 0, xs.length - 1, self._int(0))
            elems = xs.elems[1:] + (self.zero(elem),)
            return self._combine(a, [], SymList(length, elems), a[0].ty)
        if op == "length":
            return self._combine(a, [], v[0].length, TInt())
        if op == "index":
            xs, i = v
            elem = a[0].ty.elem
            is_some = z3.And(i >= 0, i < xs.length)
            picked = xs.elems[-1]
            for k in reversed(range(self.N - 1)):
                picked = self.ite(i == self._int(k), xs.elems[k], picked, elem)
            return self._combine(a, [], SymOption(is_some, picked), TOption(elem))
        if op == "append":
            xs, ys = v
            elem = a[0].ty.elem
            length = xs.length + ys.length
            elems = []
            for i in range(self.N):
                slot = xs.elems[i]
                # Slot i holds xs[i] when i < len(xs), else ys[i - len(xs)].
                for k in range(i + 1):
                    slot = self.ite(xs.length == self._int(k), ys.elems[i - k], slot, elem)
                elems.append(slot)
            return self._combine(a, self._cap(live, length), SymList(length, tuple(elems)), a[0].ty)
        if op == "range":
            lo, hi = v
            span = hi - lo
            length = z3.If(hi > lo, span, self._int(0))
            elems = tuple(lo + self._int(i) for i in range(self.N))
            # The reference checks `hi - lo > LIST_LEN_LIMIT` before building anything.
            return self._combine(a, self._cap(live, span), SymList(length, elems), TList(TInt()))

        # options
        if op == "some":
            return self._combine(a, [], SymOption(self._bool(True), v[0]), TOption(a[0].ty))
        if op == "option_get_or":
            o: SymOption = v[0]
            return self._combine(a, [], self.ite(o.is_some, o.value, v[1], a[1].ty), a[1].ty)
        if op == "is_some":
            return self._combine(a, [], v[0].is_some, TBool())

        raise Unsupported(f"no encoding for operation {op!r}")  # pragma: no cover

    # -- higher-order iteration --------------------------------------------------------------

    def _closure(self, fn: Term, env: Mapping[str, tuple[Any, Ty]]) -> _Closure:
        if fn.op != "lam":
            raise Unsupported("higher-order operand is not a lam")
        params = fn.attr("params")
        if not isinstance(params, tuple):
            raise Unsupported("lam without params")
        return _Closure(tuple(params), fn.args[0], dict(env))

    def _call(self, fn: _Closure, args: Sequence[tuple[Any, Ty]], guard: Any) -> Outcome:
        inner = dict(fn.env)
        for (name, ty), (value, _) in zip(fn.params, args):
            inner[name] = (value, ty)
        return self.term(fn.body, inner, guard)

    def _hof(self, op: str, term: Term, env: Mapping[str, tuple[Any, Ty]], guard: Any) -> Outcome:
        z3 = self.z3
        self._hof_depth += 1
        try:
            if self._hof_depth > self.scope.unroll_depth:
                raise Unsupported(
                    f"higher-order nesting exceeds unroll_depth={self.scope.unroll_depth}"
                )
            fn = self._closure(term.args[0], env)
            # Strict operands after the closure, in order: fold's init before its list.
            operands: list[Outcome] = []
            blocked: Any = None
            for arg in term.args[1:]:
                arg_guard = guard if blocked is None else z3.And(guard, z3.Not(blocked))
                out = self.term(arg, env, arg_guard)
                operands.append(out)
                blocked = out.trapped if blocked is None else z3.Or(blocked, out.trapped)
            live = guard if blocked is None else z3.And(guard, z3.Not(blocked))

            xs_out = operands[-1]
            xs: SymList = xs_out.value
            elem_ty = xs_out.ty.elem
            length = xs.length

            steps: list[Outcome] = []
            step_traps: list[Any] = []
            earlier: Any = None
            acc_ty: Ty | None = None
            acc: Any = None
            if op == "fold":
                acc_ty = operands[0].ty
                acc = operands[0].value

            for i in range(self.N):
                active = z3.And(live, self._int(i) < length)
                if earlier is not None:
                    active = z3.And(active, z3.Not(earlier))
                call_args = [(xs.elems[i], elem_ty)]
                if op == "fold":
                    call_args = [(acc, acc_ty), (xs.elems[i], elem_ty)]
                step = self._call(fn, call_args, active)
                steps.append(step)
                trap_here = z3.And(self._int(i) < length, step.trapped)
                step_traps.append(trap_here)
                earlier = trap_here if earlier is None else z3.Or(earlier, trap_here)
                if op == "fold":
                    acc = self.ite(self._int(i) < length, step.value, acc, acc_ty)

            # Element evaluation order is the trap order: the first trapping element wins.
            own_kind = self._int(0)
            for trap_here, step in reversed(list(zip(step_traps, steps))):
                own_kind = z3.If(trap_here, step.kind, own_kind)
            own_trapped = self._or(*step_traps)

            if op == "map":
                out_ty = TList(steps[0].ty)
                value: Any = SymList(length, tuple(s.value for s in steps))
            elif op == "filter":
                out_ty = xs_out.ty
                kept = [z3.And(self._int(i) < length, s.value) for i, s in enumerate(steps)]
                counts = [self._int(0)]
                for k in kept:
                    counts.append(counts[-1] + z3.If(k, self._int(1), self._int(0)))
                slots = []
                for j in range(self.N):
                    slot = self.zero(elem_ty)
                    for i in reversed(range(self.N)):
                        slot = self.ite(z3.And(kept[i], counts[i] == self._int(j)),
                                        xs.elems[i], slot, elem_ty)
                    slots.append(slot)
                value = SymList(counts[-1], tuple(slots))
            else:  # fold
                out_ty = acc_ty
                value = acc

            # Operand traps come first: the reference evaluates the list before any call.
            base = self._combine(operands, [], value, out_ty)
            trapped = z3.Or(base.trapped, own_trapped)
            kind = z3.If(base.trapped, base.kind, own_kind)
            return Outcome(trapped, kind, value, out_ty)
        finally:
            self._hof_depth -= 1
