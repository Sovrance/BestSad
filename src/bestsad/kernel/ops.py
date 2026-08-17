"""The frozen K0 v1.0.0 operation table (spec §8.3).

40 operations across the families spec §8.3 enumerates. This table is **trusted and frozen**:
invariant 1 of `AGENTS.md` forbids modifying it. Its content is hashed into
`bestsad.kernel.spec.KERNEL_VERSION_HASH`, and a test asserts the hash has not moved, so an
accidental edit fails CI rather than silently starting an uncomparable experiment lineage.

Every operation is total or explicitly trapping. No operation inherits host undefined
behaviour (spec §8.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import BOOL, INT, TFun, TList, TOption, TTuple, TVar, Ty

T = TVar("T")
U = TVar("U")
ACC = TVar("Acc")


@dataclass(frozen=True, slots=True)
class OpSig:
    """Signature of a K0 operation.

    `params` may contain type variables; `attrs` names the attribute keys the op requires.
    `strict` is False only for `if`, the single non-strict operation in K0.
    """

    op: str
    params: tuple[Ty, ...]
    ret: Ty
    family: str
    attrs: tuple[str, ...] = ()
    strict: bool = True
    traps: tuple[str, ...] = ()
    doc: str = ""

    @property
    def arity(self) -> int:
        return len(self.params)


def _sig(op: str, params, ret, family, **kw) -> OpSig:
    return OpSig(op=op, params=tuple(params), ret=ret, family=family, **kw)


#: The K0 operation table. Order is significant: it is part of the kernel version hash.
K0_OPS: tuple[OpSig, ...] = (
    # --- constants and argument access (3) ---
    _sig("const_int", (), INT, "const", attrs=("value",), doc="integer literal"),
    _sig("const_bool", (), BOOL, "const", attrs=("value",), doc="boolean literal"),
    _sig("var", (), TVar("V"), "const", attrs=("name",), doc="argument / bound-variable access"),
    # --- scalar arithmetic (9) ---
    _sig("add", (INT, INT), INT, "arith", traps=("value_too_large",)),
    _sig("sub", (INT, INT), INT, "arith", traps=("value_too_large",)),
    _sig("mul", (INT, INT), INT, "arith", traps=("value_too_large",)),
    _sig("div", (INT, INT), INT, "arith", traps=("division_by_zero",),
         doc="truncated-toward-zero division; traps on a zero divisor"),
    _sig("mod", (INT, INT), INT, "arith", traps=("division_by_zero",),
         doc="remainder with the sign of the dividend; traps on a zero divisor"),
    _sig("neg", (INT,), INT, "arith", traps=("value_too_large",)),
    _sig("abs", (INT,), INT, "arith", traps=("value_too_large",)),
    _sig("min", (INT, INT), INT, "arith"),
    _sig("max", (INT, INT), INT, "arith"),
    # --- comparison (5) ---
    _sig("eq", (T, T), BOOL, "cmp", doc="structural equality at any single ground type"),
    _sig("lt", (INT, INT), BOOL, "cmp"),
    _sig("le", (INT, INT), BOOL, "cmp"),
    _sig("gt", (INT, INT), BOOL, "cmp"),
    _sig("ge", (INT, INT), BOOL, "cmp"),
    # --- boolean logic (3) ---
    _sig("and", (BOOL, BOOL), BOOL, "bool", doc="strict conjunction (see §K0.3 on strictness)"),
    _sig("or", (BOOL, BOOL), BOOL, "bool", doc="strict disjunction"),
    _sig("not", (BOOL,), BOOL, "bool"),
    # --- conditional selection (1) ---
    _sig("if", (BOOL, T, T), T, "cond", strict=False,
         doc="the only non-strict K0 operation: exactly one branch is evaluated"),
    # --- tuples (3) ---
    _sig("tuple", (T, U), TTuple(T, U), "tuple"),
    _sig("fst", (TTuple(T, U),), T, "tuple"),
    _sig("snd", (TTuple(T, U),), U, "tuple"),
    # --- lists (8) ---
    _sig("nil", (), TList(T), "list", attrs=("elem_type",)),
    _sig("cons", (T, TList(T)), TList(T), "list", traps=("list_too_long",)),
    _sig("head", (TList(T),), TOption(T), "list", doc="total: empty list yields None"),
    _sig("tail", (TList(T),), TList(T), "list", doc="total: tail of the empty list is empty"),
    _sig("length", (TList(T),), INT, "list"),
    _sig("index", (TList(T), INT), TOption(T), "list",
         doc="total: out-of-range and negative indices yield None"),
    _sig("append", (TList(T), TList(T)), TList(T), "list", traps=("list_too_long",)),
    _sig("range", (INT, INT), TList(INT), "list", traps=("list_too_long",),
         doc="half-open [lo, hi); empty when hi <= lo"),
    # --- options (4) ---
    _sig("some", (T,), TOption(T), "option"),
    _sig("none", (), TOption(T), "option", attrs=("elem_type",)),
    _sig("option_get_or", (TOption(T), T), T, "option"),
    _sig("is_some", (TOption(T),), BOOL, "option"),
    # --- structured higher-order iteration (3) ---
    _sig("map", (TFun((T,), U), TList(T)), TList(U), "hof"),
    _sig("filter", (TFun((T,), BOOL), TList(T)), TList(T), "hof"),
    _sig("fold", (TFun((ACC, T), ACC), ACC, TList(T)), ACC, "hof",
         doc="left fold: fold(f, init, [a,b]) = f(f(init,a),b)"),
    # --- constrained closure introduction (1) ---
    _sig("lam", (TVar("Body"),), TVar("F"), "lam", attrs=("params",),
         doc="lambda; legal only in a higher-order operand position"),
)

OPS_BY_NAME: dict[str, OpSig] = {o.op: o for o in K0_OPS}

#: Operations that may not appear outside a higher-order operand position.
HIGHER_ORDER_OPS: frozenset[str] = frozenset({"map", "filter", "fold"})

#: Resource limits. These are **semantics**, not tuning knobs: they determine which programs
#: trap, so changing one changes K0 (ADR-0008).
INT_ABS_LIMIT = 2**64
LIST_LEN_LIMIT = 4096
DEFAULT_FUEL = 100_000
DEFAULT_DEPTH_LIMIT = 256


def op_families() -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in K0_OPS:
        counts[o.family] = counts.get(o.family, 0) + 1
    return counts
