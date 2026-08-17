"""Bottom-up enumerative synthesizer with observational-equivalence pruning.

This is the fixed "model" of the instrument (ADR-0007). It plays the role spec §17 assigns to a
model adapter: it consumes a genome's vocabulary and projection, emits candidate programs, and
its compute is metered. It is **not** an LLM, and results obtained with it do not test the
EXP-001 hypothesis about a fixed language model — see ADR-0007 and the run report.

What it *does* give is a real, non-simulated mechanism by which an abstraction can help or
hurt: a genome primitive collapses a subtree into a single vocabulary item, so a solution that
sits at enumeration size 9 in plain K0 may sit at size 4 once the right abstraction exists.
Whether the *discovered* abstractions are the right ones is exactly what conditions B, C, D, E
and the controls F, H, I are there to decide. A bigger vocabulary also costs more per level,
so an unhelpful abstraction genuinely hurts — the instrument is not rigged to reward growth.

Search is deterministic given `(task, genome, seed)`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from ..kernel import (
    BOOL,
    INT,
    Kernel,
    OpSig,
    Program,
    Term,
    TFun,
    TList,
    TOption,
    TTuple,
    TVar,
    Ty,
)
from ..kernel.types import parse_type as _parse, walk as _walk
from ..kernel.ops import OPS_BY_NAME
from ..kernel.terms import const_bool, const_int, lam, nil, none, var
from ..kernel.typecheck import TypeError_, Typechecker, _Unifier
from ..kernel.values import encode
from ..tasks.families import Task

#: Types the enumerator will materialize. Bounding this keeps the search space finite; it is a
#: property of the *search*, not of K0, and is recorded in the run manifest.
ENUM_TYPES: tuple[Ty, ...] = (
    INT,
    BOOL,
    TList(INT),
    TTuple(INT, INT),
    TList(TList(INT)),
    TOption(INT),
)
_ENUM_KEYS = frozenset(str(t) for t in ENUM_TYPES)

DEFAULT_CONSTANTS: tuple[int, ...] = (0, 1, 2, -1, 3, 10)

#: Probe values used to give a closure an observational signature.
#:
#: The spread matters more than the count. An earlier probe set topped out at 7, which made
#: `ge(e, 10)` indistinguishable from the constant `false` — so every predicate thresholding
#: above the probe range was silently deduplicated away and the tasks needing them became
#: unsolvable. Probes therefore span the range the input samplers actually draw from (-20..20)
#: and separate every constant in the task palette.
_PROBES: dict[str, tuple] = {
    str(INT): (-20, -7, -1, 0, 1, 2, 3, 7, 10, 20),
    str(BOOL): (True, False),
    str(TList(INT)): ((), (1,), (1, 2, 3), (-2, 5), (10, -20, 3), (0, 0)),
    str(TTuple(INT, INT)): None,  # filled at import time below
}


@dataclass(slots=True)
class SearchBudget:
    """A search budget, in the units the compute ledger accounts in (spec §26.4)."""

    max_nodes: int = 300_000
    max_size: int = 6
    lam_max_size: int = 3
    kernel_fuel: int = 4_000
    bank_cap: int = 150
    lam_bank_cap: int = 60


@dataclass(slots=True)
class SearchResult:
    program: Program | None
    solved_train: bool
    nodes_expanded: int = 0
    kernel_steps: int = 0
    evaluations: int = 0
    emitted_size: int = 0
    candidates_considered: int = 0
    vocabulary_size: int = 0

    @property
    def found(self) -> bool:
        return self.program is not None


@dataclass(slots=True)
class _Bank:
    """Terms grouped by type *and size*, deduplicated by observational signature.

    Size stratification is what makes the enumeration affordable: at level n a term is built
    only from operand tuples whose sizes sum to n-1, so a combination already produced at a
    lower level is never re-derived. A flat bank re-expands its whole contents at every level
    and spends almost all of its budget rediscovering terms it already has.
    """

    cap: int
    by_size: dict[str, dict[int, list[Term]]] = field(default_factory=dict)
    seen: dict[str, set[bytes]] = field(default_factory=dict)
    index: dict[str, dict[bytes, Term]] = field(default_factory=dict)

    def add(self, ty: Ty, term: Term, size: int, signature: bytes) -> bool:
        """Admit a term unless an observationally identical one is already banked.

        The cap is per (type, size), not per type. A per-type cap lets the operations that
        happen to be enumerated first fill the bucket and starve everything after them — which
        silently made `filter` unreachable, because `cons`, `append` and `range` had already
        used up the `List<Int>` budget. A cap that depends on vocabulary *order* would also bias
        conditions against each other, since each genome orders its vocabulary differently.
        """
        key = str(ty)
        seen = self.seen.setdefault(key, set())
        if signature in seen:
            return False
        bucket = self.by_size.setdefault(key, {}).setdefault(size, [])
        if len(bucket) >= self.cap:
            return False
        seen.add(signature)
        bucket.append(term)
        self.index.setdefault(key, {})[signature] = term
        return True

    def bucket(self, ty: Ty | str, size: int) -> list[Term]:
        return self.by_size.get(str(ty), {}).get(size, [])

    def sizes(self, ty: Ty | str) -> list[int]:
        return sorted(self.by_size.get(str(ty), {}))

    def lookup(self, ty: Ty, signature: bytes) -> Term | None:
        return self.index.get(str(ty), {}).get(signature)


class EnumerativeSynthesizer:
    """The instrument's fixed synthesizer.

    `vocabulary` is the genome's operation set: K0 op names plus genome primitive ids. A
    primitive's signature comes from `primitive_sigs` and its expansion from the kernel, so the
    synthesizer never needs to know how a primitive was discovered.
    """

    def __init__(
        self,
        kernel: Kernel,
        vocabulary: Sequence[str],
        primitive_sigs: Mapping[str, OpSig] | None = None,
        budget: SearchBudget | None = None,
        seed: int = 0,
    ) -> None:
        self.kernel = kernel
        self.primitive_sigs = dict(primitive_sigs or {})
        # Seed-dependent vocabulary order. Enumeration order has to be *some* order, and a
        # fixed one is a systematic bias: whichever operation comes first gets the level's
        # budget first, and a genome's primitives sit at different positions in each condition's
        # vocabulary. Permuting per seed converts that fixed bias into measurable variance,
        # which is what spec §26.1 wants seeds to vary and what E0 must measure rather than
        # assume (§26.8). With a fixed order the across-seed variance is identically zero, and a
        # power analysis computed from it is vacuous.
        ordered = list(vocabulary)
        random.Random(f"vocab-order:{seed}").shuffle(ordered)
        self.vocabulary = tuple(ordered)
        self.budget = budget or SearchBudget()
        self.rng = random.Random(seed)
        self.seed = seed
        self._checker = Typechecker(self.primitive_sigs)
        self._lambda_bank: dict | None = None
        self._lambda_cost = 0
        self._instantiation_cache: dict[str, list] = {}

    # -- signatures -----------------------------------------------------------------------

    def signature_of(self, op: str) -> OpSig | None:
        return OPS_BY_NAME.get(op) or self.primitive_sigs.get(op)

    def _type_of(self, term: Term, env: Mapping[str, Ty]) -> Ty | None:
        try:
            return self._checker.infer(term, env, _Unifier({}), in_hof_operand=False)
        except (TypeError_, KeyError, IndexError, AttributeError):
            return None

    # -- public API -----------------------------------------------------------------------

    def solve(self, task: Task) -> SearchResult:
        """Search for a program matching the task's *training* examples.

        The synthesizer never sees hidden inputs. Generalization to the hidden set is decided
        by the evaluator, which is the only component that touches them.
        """
        result = SearchResult(program=None, solved_train=False)
        result.vocabulary_size = len(self.vocabulary)
        env = dict(task.params)

        expected = []
        for inputs in task.train_inputs:
            outcome = self.kernel.execute(
                task.reference, list(inputs), fuel=self.budget.kernel_fuel
            )
            result.kernel_steps += outcome.steps
            expected.append(_outcome_key(outcome))
        target = b"|".join(expected)

        lambda_bank = self._lambdas(result)

        bank = _Bank(cap=self.budget.bank_cap)
        for name, ty in task.params:
            self._offer(bank, var(name), ty, 1, task, result)
        for value in self._constant_pool():
            self._offer(bank, const_int(value), INT, 1, task, result)
        for flag in (True, False):
            self._offer(bank, const_bool(flag), BOOL, 1, task, result)
        for ty in (INT, BOOL, TList(INT), TTuple(INT, INT)):
            self._offer(bank, nil(ty), TList(ty), 1, task, result)
            self._offer(bank, none(ty), TOption(ty), 1, task, result)

        hit = bank.lookup(task.result_type, target)
        if hit is not None:
            return self._finish(result, hit, task)

        for level in range(2, self.budget.max_size + 1):
            grew = self._grow(bank, lambda_bank, task, result, level)
            hit = bank.lookup(task.result_type, target)
            if hit is not None:
                return self._finish(result, hit, task)
            if not grew or result.nodes_expanded >= self.budget.max_nodes:
                break

        return result

    # -- enumeration ----------------------------------------------------------------------

    def _constant_pool(self) -> tuple[int, ...]:
        """Constants available to the search. A seed-dependent extra makes different seeds
        explore slightly different spaces (spec §26.1), which is where per-seed variance in the
        primary endpoint comes from."""
        return DEFAULT_CONSTANTS + (self.rng.choice([4, 5, -2, 7]),)

    def _offer(
        self, bank: _Bank, term: Term, ty: Ty, size: int, task: Task, result: SearchResult
    ) -> bool:
        signature = self._signature(term, task, result)
        if signature is None:
            return False
        return bank.add(ty, term, size, signature)

    def _grow(
        self,
        bank: _Bank,
        lambda_bank: dict,
        task: Task,
        result: SearchResult,
        level: int,
    ) -> bool:
        """Build every well-typed term of exactly `level` nodes from smaller bank entries.

        Operations are consumed round-robin rather than one at a time to exhaustion. Draining
        each operation in turn means whichever operation happens to come first in the
        vocabulary spends the whole level budget, and everything after it never runs — which
        made `fold` unreachable even though its solution sat at a level the budget could
        afford. It would also bias conditions against each other, since a genome's primitives
        occupy different positions in its vocabulary: the control would be starved in a
        different place than the treatment, and the difference would look like a result.
        """
        grew = False
        streams = []
        for op in self.vocabulary:
            sig = self.signature_of(op)
            if sig is None or sig.arity == 0 or op == "lam":
                continue
            streams.append((op, self._candidates(op, sig, bank, lambda_bank, level)))

        while streams and result.nodes_expanded < self.budget.max_nodes:
            still_live = []
            for op, stream in streams:
                if result.nodes_expanded >= self.budget.max_nodes:
                    still_live.append((op, stream))
                    continue
                try:
                    args, out_ty = next(stream)
                except StopIteration:
                    continue
                result.nodes_expanded += 1
                if self._offer(bank, Term(op, args), out_ty, level, task, result):
                    grew = True
                still_live.append((op, stream))
            streams = still_live
        return grew

    def _candidates(
        self,
        op: str,
        sig: OpSig,
        bank: _Bank,
        lambda_bank: dict,
        level: int,
    ) -> Iterable[tuple[tuple[Term, ...], Ty]]:
        """Well-typed operand tuples for `op` at exactly `level` nodes, result type known.

        Type variables are instantiated to concrete types before enumeration rather than
        checked afterwards. Enumerating ill-typed candidates and rejecting them would burn most
        of the search budget on terms that were never legal — and it would burn a *different*
        amount in each condition, which would quietly corrupt the compute matching that
        condition I depends on.

        A closure counts as one node here: the cost of enumerating closure bodies was already
        charged, once, when the lambda bank was built.
        """
        remaining = level - 1
        if remaining < 1:
            return

        if op in ("map", "filter"):
            for (src, ret), closures in lambda_bank.items():
                if len(src) != 1 or (op == "filter" and ret != str(BOOL)):
                    continue
                out = TList(src[0]) if op == "filter" else TList(_parse(ret))
                if str(out) not in _ENUM_KEYS:
                    continue
                for lst in bank.bucket(TList(src[0]), remaining - 1):
                    for closure in closures:
                        yield (closure, lst), out
            return

        if op == "fold":
            for (src, ret), closures in lambda_bank.items():
                if len(src) != 2 or str(src[0]) != ret:
                    continue
                for init_size, lst_size in _compositions(remaining - 1, 2):
                    inits = bank.bucket(ret, init_size)
                    lists = bank.bucket(TList(src[1]), lst_size)
                    if not inits or not lists:
                        continue
                    for closure in closures:
                        for init in inits:
                            for lst in lists:
                                yield (closure, init, lst), src[0]
            return

        for params, out_ty in self._instantiations(sig):
            for split in _compositions(remaining, len(params)):
                pools = [bank.bucket(p, size) for p, size in zip(params, split)]
                if any(not pool for pool in pools):
                    continue
                for args in _product(pools):
                    yield args, out_ty

    def _instantiations(self, sig: OpSig) -> list[tuple[tuple[Ty, ...], Ty]]:
        """Concrete (param types, result type) pairs for a possibly polymorphic signature."""
        key = sig.op
        cached = self._instantiation_cache.get(key)
        if cached is not None:
            return cached

        variables = sorted(
            {t.name for p in (*sig.params, sig.ret) for t in _walk(p) if isinstance(t, TVar)}
        )
        out: list[tuple[tuple[Ty, ...], Ty]] = []
        if not variables:
            if all(str(p) in _ENUM_KEYS for p in sig.params) and str(sig.ret) in _ENUM_KEYS:
                out.append((tuple(sig.params), sig.ret))
        else:
            for assignment in _assignments(variables, ENUM_TYPES):
                params = tuple(_subst(p, assignment) for p in sig.params)
                ret = _subst(sig.ret, assignment)
                if any(isinstance(t, TFun) for p in params for t in _walk(p)):
                    continue
                if str(ret) not in _ENUM_KEYS:
                    continue
                if any(str(p) not in _ENUM_KEYS for p in params):
                    continue
                out.append((params, ret))
        self._instantiation_cache[key] = out
        return out

    # -- closures -------------------------------------------------------------------------

    def _lambdas(self, result: SearchResult) -> dict:
        """Enumerate small closures for the higher-order operations, once per solver.

        The bank depends on the *vocabulary*, so a genome with more primitives pays a larger
        one-off cost here. That cost is charged to the condition that owns the genome, which is
        what makes "a useless abstraction is not free" true in the instrument rather than only
        in the write-up.

        Closures are enumerated over their own parameters and the constant pool only — outer
        variables are not captured. That is a restriction on the search, not on K0, and it
        applies identically in every condition.
        """
        if self._lambda_bank is not None:
            result.nodes_expanded += 0  # already charged to the solver's first task
            return self._lambda_bank

        bank: dict = {}
        scalar_signatures = [
            ((INT,), INT),
            ((INT,), BOOL),
            ((INT, INT), INT),
            ((TTuple(INT, INT), INT), TTuple(INT, INT)),
        ]
        for params, ret in scalar_signatures:
            names = tuple(f"L{i}" for i in range(len(params)))
            env = dict(zip(names, params))
            bodies = self._enumerate_bodies(env, ret, result)
            bank[(tuple(params), str(ret))] = [
                lam(tuple(zip(names, params)), body) for body in bodies
            ]

        # Second pass: list-to-list closures, whose bodies may apply `map`/`filter` using the
        # scalar closures built above. Without this pass a closure body can never contain a
        # higher-order operation, which makes nested composition (family F10) unreachable in
        # every condition — an artefact of the search apparatus rather than a finding about
        # representation.
        list_params = (TList(INT),)
        list_env = {"L0": TList(INT)}
        list_bodies = list(self._enumerate_bodies(list_env, TList(INT), result))
        for inner in bank.get(((INT,), str(INT)), []):
            result.nodes_expanded += 1
            list_bodies.append(Term("map", (inner, var("L0"))))
        for predicate in bank.get(((INT,), str(BOOL)), []):
            result.nodes_expanded += 1
            list_bodies.append(Term("filter", (predicate, var("L0"))))
        bank[(list_params, str(TList(INT)))] = [
            lam((("L0", TList(INT)),), body) for body in list_bodies[: self.budget.lam_bank_cap * 3]
        ]

        self._lambda_bank = bank
        self._lambda_cost = result.nodes_expanded
        return bank

    def _enumerate_bodies(
        self, env: dict[str, Ty], want: Ty, result: SearchResult
    ) -> list[Term]:
        """Type-directed enumeration of closure bodies, pruned by observational equivalence
        over a fixed probe set."""
        probes = _probe_tuples(env)
        bank = _Bank(cap=self.budget.lam_bank_cap)

        def offer(ty: Ty, term: Term, size: int) -> bool:
            if str(ty) not in _ENUM_KEYS:
                return False
            signature = self._probe_signature(term, env, probes, result)
            if signature is None:
                return False
            return bank.add(ty, term, size, signature)

        for name, ty in env.items():
            offer(ty, var(name), 1)
        for value in DEFAULT_CONSTANTS:
            offer(INT, const_int(value), 1)
        offer(BOOL, const_bool(True), 1)
        offer(BOOL, const_bool(False), 1)

        body_ops = [
            op for op in self.vocabulary if op in _BODY_OPS or op in self.primitive_sigs
        ]

        for level in range(2, self.budget.lam_max_size + 1):
            for op in body_ops:
                sig = self.signature_of(op)
                if sig is None or sig.arity == 0 or op == "lam":
                    continue
                if result.nodes_expanded >= self.budget.max_nodes:
                    break
                for params, out_ty in self._instantiations(sig):
                    for split in _compositions(level - 1, len(params)):
                        pools = [bank.bucket(p, size) for p, size in zip(params, split)]
                        if any(not pool for pool in pools):
                            continue
                        for args in _product(pools, limit=2_000):
                            if result.nodes_expanded >= self.budget.max_nodes:
                                break
                            result.nodes_expanded += 1
                            offer(out_ty, Term(op, args), level)

        out: list[Term] = []
        for size in bank.sizes(want):
            out.extend(bank.bucket(want, size))
        return out

    def _probe_signature(
        self,
        term: Term,
        env: Mapping[str, Ty],
        probes: tuple[tuple, ...],
        result: SearchResult,
    ) -> bytes | None:
        params = tuple(env.items())
        program = Program(params, term, None)
        out: list[bytes] = []
        for probe in probes:
            outcome = self.kernel.execute(program, list(probe), fuel=self.budget.kernel_fuel)
            result.kernel_steps += outcome.steps
            result.evaluations += 1
            out.append(_outcome_key(outcome))
        return b"|".join(out)

    # -- evaluation -----------------------------------------------------------------------

    def _signature(self, term: Term, task: Task, result: SearchResult) -> bytes | None:
        """Observational signature: the term's outcomes on the training inputs.

        Two terms with the same signature are indistinguishable on the evidence available to
        the search, so only one is kept. Applied identically in every condition.
        """
        program = Program(task.params, term, None)
        out: list[bytes] = []
        for inputs in task.train_inputs:
            outcome = self.kernel.execute(program, list(inputs), fuel=self.budget.kernel_fuel)
            result.kernel_steps += outcome.steps
            result.evaluations += 1
            out.append(_outcome_key(outcome))
        return b"|".join(out)

    def _finish(self, result: SearchResult, term: Term, task: Task) -> SearchResult:
        result.program = Program(task.params, term, task.result_type)
        result.solved_train = True
        result.emitted_size = term.size()
        return result


# -- helpers ---------------------------------------------------------------------------------


_PROBES[str(TTuple(INT, INT))] = None


def _probe_values(ty: Ty) -> tuple:
    key = str(ty)
    if key == str(TTuple(INT, INT)):
        from ..kernel.values import Pair

        return (Pair(0, 0), Pair(3, 1), Pair(-2, 5))
    values = _PROBES.get(key)
    if values is None:  # pragma: no cover - closure params are drawn from the set above
        return (0,)
    return values


def _probe_tuples(env: Mapping[str, Ty]) -> tuple[tuple, ...]:
    pools = [_probe_values(ty) for ty in env.values()]
    out: list[tuple] = []
    width = max(len(p) for p in pools) if pools else 0
    for i in range(width):
        out.append(tuple(pool[i % len(pool)] for pool in pools))
    return tuple(out)


_BODY_OPS = frozenset({
    "add", "sub", "mul", "div", "mod", "min", "max", "neg", "abs",
    "eq", "lt", "le", "gt", "ge", "and", "or", "not",
    "tuple", "fst", "snd", "length", "if", "head", "option_get_or",
})


def _compositions(total: int, parts: int):
    """Every way to write `total` as an ordered sum of `parts` positive integers."""
    if parts == 1:
        if total >= 1:
            yield (total,)
        return
    for first in range(1, total - parts + 2):
        for rest in _compositions(total - first, parts - 1):
            yield (first, *rest)


def _subst(ty: Ty, mapping: Mapping[str, Ty]) -> Ty:
    """Substitute concrete types for type variables."""
    if isinstance(ty, TVar):
        return mapping.get(ty.name, ty)
    if isinstance(ty, TList):
        return TList(_subst(ty.elem, mapping))
    if isinstance(ty, TOption):
        return TOption(_subst(ty.elem, mapping))
    if isinstance(ty, TTuple):
        return TTuple(_subst(ty.fst, mapping), _subst(ty.snd, mapping))
    if isinstance(ty, TFun):
        return TFun(tuple(_subst(p, mapping) for p in ty.params), _subst(ty.ret, mapping))
    return ty


def _assignments(variables: Sequence[str], choices: Sequence[Ty]):
    """Every assignment of `choices` to `variables`."""
    if not variables:
        yield {}
        return
    head, *rest = variables
    for choice in choices:
        for tail in _assignments(rest, choices):
            yield {head: choice, **tail}


def _outcome_key(outcome) -> bytes:
    if outcome.trap is not None:
        return b"T:" + outcome.trap.kind.value.encode()
    return b"V:" + encode(outcome.value)


def _product(pools: Sequence[Sequence[Term]], limit: int = 40_000):
    """Bounded cartesian product. The bound keeps one wide operand pool from starving the rest
    of the vocabulary; it is applied identically in every condition."""
    if not pools:
        yield ()
        return
    if any(len(p) == 0 for p in pools):
        return
    count = 0
    indices = [0] * len(pools)
    while True:
        yield tuple(pools[i][indices[i]] for i in range(len(pools)))
        count += 1
        if count >= limit:
            return
        pos = len(pools) - 1
        while pos >= 0:
            indices[pos] += 1
            if indices[pos] < len(pools[pos]):
                break
            indices[pos] = 0
            pos -= 1
        if pos < 0:
            return
