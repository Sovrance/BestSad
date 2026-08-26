"""K0 static semantics — verification layer V1 (spec §19).

Checks types, arity, effect/region constraints (K0 has only `Pure`/`Trap`, so the effect check
reduces to structure), and the constrained-closure rule: a `lam` may appear only as the
function operand of `map`/`filter`/`fold`.

A program that fails this check is rejected before execution and before any expensive
evaluation (spec §9.6, validity envelope).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .ops import HIGHER_ORDER_OPS, OPS_BY_NAME, OpSig
from .terms import Program, Term
from .types import BOOL, INT, TFun, TList, TOption, TTuple, TVar, Ty


class TypeError_(Exception):
    """Static-semantics violation. Distinct from Python's builtin TypeError."""


@dataclass
class _Unifier:
    subst: dict[str, Ty]

    def resolve(self, ty: Ty) -> Ty:
        if isinstance(ty, TVar):
            seen = ty.name
            while isinstance(ty, TVar) and ty.name in self.subst:
                ty = self.subst[ty.name]
                if isinstance(ty, TVar) and ty.name == seen:
                    break
            return ty if not isinstance(ty, TVar) else ty
        if isinstance(ty, TList):
            return TList(self.resolve(ty.elem))
        if isinstance(ty, TOption):
            return TOption(self.resolve(ty.elem))
        if isinstance(ty, TTuple):
            return TTuple(self.resolve(ty.fst), self.resolve(ty.snd))
        if isinstance(ty, TFun):
            return TFun(tuple(self.resolve(p) for p in ty.params), self.resolve(ty.ret))
        return ty

    def unify(self, a: Ty, b: Ty) -> None:
        a, b = self.resolve(a), self.resolve(b)
        if isinstance(a, TVar):
            self.subst[a.name] = b
            return
        if isinstance(b, TVar):
            self.subst[b.name] = a
            return
        if type(a) is not type(b):
            raise TypeError_(f"cannot unify {a} with {b}")
        if isinstance(a, TList) and isinstance(b, TList):
            self.unify(a.elem, b.elem)
        elif isinstance(a, TOption) and isinstance(b, TOption):
            self.unify(a.elem, b.elem)
        elif isinstance(a, TTuple) and isinstance(b, TTuple):
            self.unify(a.fst, b.fst)
            self.unify(a.snd, b.snd)
        elif isinstance(a, TFun) and isinstance(b, TFun):
            if len(a.params) != len(b.params):
                raise TypeError_(f"arity mismatch: {a} vs {b}")
            for p, q in zip(a.params, b.params):
                self.unify(p, q)
            self.unify(a.ret, b.ret)


def _freshen(ty: Ty, tag: str) -> Ty:
    if isinstance(ty, TVar):
        return TVar(f"{ty.name}#{tag}")
    if isinstance(ty, TList):
        return TList(_freshen(ty.elem, tag))
    if isinstance(ty, TOption):
        return TOption(_freshen(ty.elem, tag))
    if isinstance(ty, TTuple):
        return TTuple(_freshen(ty.fst, tag), _freshen(ty.snd, tag))
    if isinstance(ty, TFun):
        return TFun(tuple(_freshen(p, tag) for p in ty.params), _freshen(ty.ret, tag))
    return ty


class Typechecker:
    """Infers the type of a term under an environment.

    `primitives` supplies signatures for genome primitives (`prim:*` ops), which lower to K0
    but are typed by their declared signature so a candidate can be checked without expanding
    every macro first.
    """

    def __init__(self, primitives: Mapping[str, OpSig] | None = None) -> None:
        self.primitives = dict(primitives or {})
        self._counter = 0

    def _tag(self) -> str:
        self._counter += 1
        return str(self._counter)

    def signature(self, op: str) -> OpSig:
        if op in OPS_BY_NAME:
            return OPS_BY_NAME[op]
        if op in self.primitives:
            return self.primitives[op]
        raise TypeError_(f"unknown operation {op!r}")

    def check_program(self, program: Program) -> Ty:
        env = dict(program.params)
        u = _Unifier({})
        ty = self.infer(program.body, env, u, in_hof_operand=False)
        ty = u.resolve(ty)
        if program.result_type is not None:
            u.unify(ty, program.result_type)
            ty = u.resolve(program.result_type)
        return ty

    def infer(
        self,
        term: Term,
        env: Mapping[str, Ty],
        u: _Unifier,
        *,
        in_hof_operand: bool,
    ) -> Ty:
        op = term.op

        if op == "var":
            name = term.attr("name")
            if name not in env:
                raise TypeError_(f"unbound variable {name!r}")
            return env[name]

        if op == "const_int":
            self._require_attr(term, "value", int)
            return INT

        if op == "const_bool":
            self._require_attr(term, "value", bool)
            return BOOL

        if op in ("nil", "none"):
            elem = term.attr("elem_type")
            if not isinstance(elem, Ty):
                raise TypeError_(f"{op} requires an `elem_type` attribute")
            return TList(elem) if op == "nil" else TOption(elem)

        if op == "lam":
            if not in_hof_operand:
                raise TypeError_(
                    "lam may appear only as the function operand of map/filter/fold "
                    "(constrained closure rule, spec §8.3)"
                )
            params = term.attr("params")
            if not isinstance(params, tuple) or not all(
                isinstance(p, tuple) and len(p) == 2 and isinstance(p[1], Ty) for p in params
            ):
                raise TypeError_("lam requires a `params` attribute of (name, Ty) pairs")
            inner = dict(env)
            for name, ty in params:
                inner[name] = ty
            body_ty = self.infer(term.args[0], inner, u, in_hof_operand=False)
            return TFun(tuple(t for _, t in params), body_ty)

        sig = self.signature(op)
        if len(term.args) != sig.arity:
            raise TypeError_(
                f"{op} expects {sig.arity} operand(s), got {len(term.args)}"
            )
        for key in sig.attrs:
            if term.attr(key) is None:
                raise TypeError_(f"{op} requires attribute {key!r}")

        tag = self._tag()
        params = tuple(_freshen(p, tag) for p in sig.params)
        ret = _freshen(sig.ret, tag)

        hof = op in HIGHER_ORDER_OPS
        for i, (arg, want) in enumerate(zip(term.args, params)):
            operand_is_fun = hof and i == 0
            if operand_is_fun and arg.op != "lam":
                raise TypeError_(
                    f"{op} operand 0 must be a `lam`; K0 has no first-class function values"
                )
            got = self.infer(arg, env, u, in_hof_operand=operand_is_fun)
            u.unify(want, got)

        return u.resolve(ret)

    @staticmethod
    def _require_attr(term: Term, key: str, kind: type) -> None:
        value = term.attr(key)
        if kind is int and isinstance(value, bool):
            raise TypeError_(f"{term.op} attribute {key!r} must be {kind.__name__}")
        if not isinstance(value, kind):
            raise TypeError_(f"{term.op} attribute {key!r} must be {kind.__name__}")


def typecheck(program: Program, primitives: Mapping[str, OpSig] | None = None) -> Ty:
    """Convenience entry point. Raises `TypeError_` on any static-semantics violation."""
    return Typechecker(primitives).check_program(program)


def is_well_typed(program: Program, primitives: Mapping[str, OpSig] | None = None) -> bool:
    try:
        typecheck(program, primitives)
        return True
    except TypeError_:
        return False
