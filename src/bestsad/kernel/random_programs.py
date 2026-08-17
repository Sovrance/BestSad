"""Type-directed random program generator.

Used by the M1 differential/determinism sweep and by property tests elsewhere. It is a
*testing* instrument, not the task generator: `bestsad.tasks` generates the structured task
families F1–F12 with controlled composition depth. This one exists to hit odd corners of K0
that a structured generator would never produce.

Generation is type-directed, so every program it emits is well-typed by construction; a
regression that made it emit an ill-typed program would be caught by
`tests/kernel/test_random_programs.py`.
"""

from __future__ import annotations

import random
from typing import Any, Sequence

from .ops import LIST_LEN_LIMIT
from .terms import Program, Term, const_bool, const_int, lam, nil, none, var
from .types import BOOL, INT, TBool, TInt, TList, TOption, TTuple, Ty
from .values import Just, NOTHING, Pair

_SIMPLE_TYPES: tuple[Ty, ...] = (INT, BOOL)


def random_type(rng: random.Random, depth: int = 2) -> Ty:
    if depth <= 0:
        return rng.choice(_SIMPLE_TYPES)
    roll = rng.random()
    if roll < 0.40:
        return rng.choice(_SIMPLE_TYPES)
    if roll < 0.65:
        return TList(random_type(rng, depth - 1))
    if roll < 0.85:
        return TTuple(random_type(rng, depth - 1), random_type(rng, depth - 1))
    return TOption(random_type(rng, depth - 1))


class ProgramGenerator:
    """Generates well-typed K0 terms of a requested type."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def term(self, ty: Ty, env: dict[str, Ty], budget: int) -> Term:
        """A well-typed term of type `ty` using at most roughly `budget` nodes."""
        candidates = [v for v, t in env.items() if t == ty]
        if budget <= 1 or self.rng.random() < 0.18:
            if candidates and self.rng.random() < 0.7:
                return var(self.rng.choice(candidates))
            return self._leaf(ty, env, budget)
        if candidates and self.rng.random() < 0.25:
            return var(self.rng.choice(candidates))
        builders = self._builders(ty)
        self.rng.shuffle(builders)
        for build in builders:
            term = build(ty, env, budget)
            if term is not None:
                return term
        return self._leaf(ty, env, budget)  # pragma: no cover - builders always succeed

    # -- leaves --------------------------------------------------------------------------

    def _leaf(self, ty: Ty, env: dict[str, Ty], budget: int) -> Term:
        if isinstance(ty, TInt):
            return const_int(self.rng.randint(-12, 12))
        if isinstance(ty, TBool):
            return const_bool(self.rng.random() < 0.5)
        if isinstance(ty, TList):
            return nil(ty.elem)
        if isinstance(ty, TOption):
            return none(ty.elem)
        if isinstance(ty, TTuple):
            half = max(1, budget // 2)
            return Term(
                "tuple",
                (self.term(ty.fst, env, half), self.term(ty.snd, env, half)),
            )
        raise ValueError(f"no leaf for {ty}")  # pragma: no cover

    # -- builders ------------------------------------------------------------------------

    def _builders(self, ty: Ty) -> list:
        common = [self._b_if]
        if isinstance(ty, TInt):
            return common + [self._b_arith, self._b_length, self._b_option_get_or,
                             self._b_fold_int, self._b_fst_snd]
        if isinstance(ty, TBool):
            return common + [self._b_cmp, self._b_bool, self._b_eq, self._b_is_some,
                             self._b_fst_snd]
        if isinstance(ty, TList):
            return common + [self._b_cons, self._b_tail, self._b_append, self._b_map,
                             self._b_filter, self._b_range, self._b_fst_snd]
        if isinstance(ty, TOption):
            return common + [self._b_some, self._b_head, self._b_index, self._b_fst_snd]
        if isinstance(ty, TTuple):
            return common + [self._b_tuple, self._b_fst_snd]
        return common  # pragma: no cover

    def _b_if(self, ty, env, budget):
        third = max(1, budget // 3)
        return Term(
            "if",
            (
                self.term(BOOL, env, third),
                self.term(ty, env, third),
                self.term(ty, env, third),
            ),
        )

    def _b_arith(self, ty, env, budget):
        op = self.rng.choice(["add", "sub", "mul", "div", "mod", "min", "max", "neg", "abs"])
        half = max(1, budget // 2)
        if op in ("neg", "abs"):
            return Term(op, (self.term(INT, env, half),))
        return Term(op, (self.term(INT, env, half), self.term(INT, env, half)))

    def _b_cmp(self, ty, env, budget):
        op = self.rng.choice(["lt", "le", "gt", "ge"])
        half = max(1, budget // 2)
        return Term(op, (self.term(INT, env, half), self.term(INT, env, half)))

    def _b_eq(self, ty, env, budget):
        half = max(1, budget // 2)
        inner = self.rng.choice((INT, BOOL))
        return Term("eq", (self.term(inner, env, half), self.term(inner, env, half)))

    def _b_bool(self, ty, env, budget):
        op = self.rng.choice(["and", "or", "not"])
        half = max(1, budget // 2)
        if op == "not":
            return Term(op, (self.term(BOOL, env, half),))
        return Term(op, (self.term(BOOL, env, half), self.term(BOOL, env, half)))

    def _b_length(self, ty, env, budget):
        elem = random_type(self.rng, 1)
        return Term("length", (self.term(TList(elem), env, max(1, budget - 1)),))

    def _b_option_get_or(self, ty, env, budget):
        half = max(1, budget // 2)
        return Term(
            "option_get_or",
            (self.term(TOption(ty), env, half), self.term(ty, env, half)),
        )

    def _b_fold_int(self, ty, env, budget):
        if not isinstance(ty, TInt):
            return None
        third = max(1, budget // 3)
        elem = INT
        acc_name, x_name = self._fresh(env, 2)
        inner = dict(env)
        inner[acc_name] = INT
        inner[x_name] = elem
        body = self.term(INT, inner, third)
        return Term(
            "fold",
            (
                lam(((acc_name, INT), (x_name, elem)), body),
                self.term(INT, env, third),
                self.term(TList(elem), env, third),
            ),
        )

    def _b_fst_snd(self, ty, env, budget):
        other = random_type(self.rng, 1)
        if self.rng.random() < 0.5:
            return Term("fst", (self.term(TTuple(ty, other), env, max(1, budget - 1)),))
        return Term("snd", (self.term(TTuple(other, ty), env, max(1, budget - 1)),))

    def _b_is_some(self, ty, env, budget):
        elem = random_type(self.rng, 1)
        return Term("is_some", (self.term(TOption(elem), env, max(1, budget - 1)),))

    def _b_cons(self, ty, env, budget):
        half = max(1, budget // 2)
        return Term("cons", (self.term(ty.elem, env, half), self.term(ty, env, half)))

    def _b_tail(self, ty, env, budget):
        return Term("tail", (self.term(ty, env, max(1, budget - 1)),))

    def _b_append(self, ty, env, budget):
        half = max(1, budget // 2)
        return Term("append", (self.term(ty, env, half), self.term(ty, env, half)))

    def _b_range(self, ty, env, budget):
        if not isinstance(ty.elem, TInt):
            return None
        half = max(1, budget // 2)
        return Term("range", (self.term(INT, env, half), self.term(INT, env, half)))

    def _b_map(self, ty, env, budget):
        src_elem = random_type(self.rng, 1)
        half = max(1, budget // 2)
        (x_name,) = self._fresh(env, 1)
        inner = dict(env)
        inner[x_name] = src_elem
        body = self.term(ty.elem, inner, half)
        return Term(
            "map",
            (lam(((x_name, src_elem),), body), self.term(TList(src_elem), env, half)),
        )

    def _b_filter(self, ty, env, budget):
        half = max(1, budget // 2)
        (x_name,) = self._fresh(env, 1)
        inner = dict(env)
        inner[x_name] = ty.elem
        body = self.term(BOOL, inner, half)
        return Term(
            "filter",
            (lam(((x_name, ty.elem),), body), self.term(ty, env, half)),
        )

    def _b_some(self, ty, env, budget):
        return Term("some", (self.term(ty.elem, env, max(1, budget - 1)),))

    def _b_head(self, ty, env, budget):
        return Term("head", (self.term(TList(ty.elem), env, max(1, budget - 1)),))

    def _b_index(self, ty, env, budget):
        half = max(1, budget // 2)
        return Term(
            "index",
            (self.term(TList(ty.elem), env, half), self.term(INT, env, half)),
        )

    def _b_tuple(self, ty, env, budget):
        half = max(1, budget // 2)
        return Term("tuple", (self.term(ty.fst, env, half), self.term(ty.snd, env, half)))

    def _fresh(self, env: dict[str, Ty], count: int) -> tuple[str, ...]:
        names = []
        i = 0
        while len(names) < count:
            candidate = f"v{i}"
            if candidate not in env and candidate not in names:
                names.append(candidate)
            i += 1
        return tuple(names)


def random_program(rng: random.Random, *, max_params: int = 3, budget: int = 14) -> Program:
    gen = ProgramGenerator(rng)
    n_params = rng.randint(1, max_params)
    params = tuple((f"x{i}", random_type(rng, 2)) for i in range(n_params))
    result_type = random_type(rng, 2)
    body = gen.term(result_type, dict(params), budget)
    return Program(params=params, body=body, result_type=result_type)


def random_value(rng: random.Random, ty: Ty, depth: int = 0) -> Any:
    """A random inhabitant of `ty`, for differential and property testing."""
    if isinstance(ty, TInt):
        return rng.randint(-30, 30)
    if isinstance(ty, TBool):
        return rng.random() < 0.5
    if isinstance(ty, TList):
        n = 0 if depth > 2 else rng.randint(0, 6)
        return tuple(random_value(rng, ty.elem, depth + 1) for _ in range(n))
    if isinstance(ty, TTuple):
        return Pair(random_value(rng, ty.fst, depth + 1), random_value(rng, ty.snd, depth + 1))
    if isinstance(ty, TOption):
        if rng.random() < 0.3:
            return NOTHING
        return Just(random_value(rng, ty.elem, depth + 1))
    raise ValueError(f"cannot inhabit {ty}")  # pragma: no cover


def random_inputs(rng: random.Random, params: Sequence[tuple[str, Ty]]) -> list[Any]:
    return [random_value(rng, ty) for _, ty in params]


assert LIST_LEN_LIMIT > 0  # generator never intentionally exceeds the kernel list bound
