"""Semantic Kernel K0 — the trusted, frozen semantic anchor (spec §8).

Nothing in this package may be modified to make a downstream component easier
(`AGENTS.md` invariant 1). Widening K0 is the one shortcut that invalidates every comparison
built on top of it.
"""

from .interpreter import ExecutionResult, Kernel
from .ops import K0_OPS, OPS_BY_NAME, OpSig
from .spec import KERNEL_VERSION, KERNEL_VERSION_HASH, kernel_descriptor
from .terms import Program, Term, app, const_bool, const_int, lam, nil, none, var
from .traps import Trap, TrapKind
from .typecheck import TypeError_, Typechecker, is_well_typed, typecheck
from .types import (
    BOOL,
    INT,
    TBool,
    TFun,
    TInt,
    TList,
    TOption,
    TTuple,
    TVar,
    Ty,
    parse_type,
)
from .values import Closure, Just, NOTHING, Pair, render, value_equal

__all__ = [
    "BOOL",
    "INT",
    "Closure",
    "ExecutionResult",
    "Just",
    "K0_OPS",
    "KERNEL_VERSION",
    "KERNEL_VERSION_HASH",
    "Kernel",
    "NOTHING",
    "OPS_BY_NAME",
    "OpSig",
    "Pair",
    "Program",
    "TBool",
    "TFun",
    "TInt",
    "TList",
    "TOption",
    "TTuple",
    "TVar",
    "Term",
    "Trap",
    "TrapKind",
    "Ty",
    "TypeError_",
    "Typechecker",
    "app",
    "const_bool",
    "const_int",
    "is_well_typed",
    "kernel_descriptor",
    "lam",
    "nil",
    "none",
    "parse_type",
    "render",
    "typecheck",
    "value_equal",
    "var",
]
