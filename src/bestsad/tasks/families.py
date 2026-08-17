"""Task families F1–F12 (spec §24.2–§24.4).

The domain is synthetic typed list/scalar transformation tasks generated from K0, so the whole
benchmark is contamination-resistant by construction (spec §20.4, confound C4): instances do
not exist anywhere until a seed generates them.

**The split that matters.** F1–F8 are the curriculum families available to search. F9–F12 are
held out, and they are held out *structurally*, not merely by seed:

* F9  `filter -> map -> fold`, a three-stage pipeline. No curriculum family chains three
      stages; F2/F3/F4 each supply one.
* F10 nested `map` over `List<List<Int>>`. No curriculum family ever nests a higher-order
      operation inside another's body.
* F11 `fold` with a *tuple* accumulator, carrying two quantities at once. Curriculum folds all
      carry a scalar.
* F12 conditional dispatch: a predicate on the whole input selects between two different
      pipelines. Curriculum conditionals branch on scalars inside a body, never between
      composed pipelines.

That is what spec §20.3 means by family holdout rather than unseen instances, and it is where
spec §24.6 puts the primary endpoint — compositional OOD, where a token-compression artefact
should provide no help and a genuine representational advantage should.

**Adversarial siblings.** Each held-out family also has an adversarial variant (spec §24.4):
tasks that look near-identical to a curriculum task but where a shortcut primitive fitted to
the curriculum gives the wrong answer. They exist so that a shortcut-shaped primitive is
*caught* rather than rewarded.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..kernel import INT, BOOL, Kernel, Program, Term, TList, TTuple, Ty
from ..kernel.terms import app, const_bool, const_int, lam, nil, var


@dataclass(frozen=True, slots=True)
class Task:
    """One task instance.

    A task is defined by its *reference program*: correctness is "produces the same outcome as
    the reference on every hidden input", evaluated by the trusted K0 interpreter. The
    definition of correctness is frozen (`AGENTS.md` invariant 1) and lives here.
    """

    task_id: str
    family: str
    params: tuple[tuple[str, Ty], ...]
    result_type: Ty
    reference: Program
    train_inputs: tuple[tuple[Any, ...], ...]
    hidden_inputs: tuple[tuple[Any, ...], ...]
    seed: int
    composition_depth: int
    adversarial: bool = False
    notes: str = ""

    def reference_outputs(self, kernel: Kernel, inputs) -> tuple:
        return tuple(kernel.execute(self.reference, list(i)) for i in inputs)


@dataclass(frozen=True, slots=True)
class Family:
    """A task family: a builder plus its structural metadata."""

    family_id: str
    build: Callable[[random.Random], tuple[Program, str]]
    input_types: tuple[Ty, ...]
    result_type: Ty
    composition_depth: int
    held_out: bool = False
    description: str = ""
    ops_required: frozenset[str] = field(default_factory=frozenset)


#: Constants families draw from.
#:
#: Deliberately aligned with the synthesizer's constant pool (`solver.enumerative
#: .DEFAULT_CONSTANTS`). Without the alignment, whether a task is solvable at all would turn on
#: whether its randomly chosen constant happened to be guessable, and the experiment would
#: measure constant luck instead of composition. The palette is shared by every condition, so
#: it confers no advantage on any of them.
CONST_PALETTE: tuple[int, ...] = (0, 1, 2, 3, 10, -1)
SMALL_PALETTE: tuple[int, ...] = (1, 2, 3)


# --- input samplers ---------------------------------------------------------------------------


def _int_list(rng: random.Random, lo: int = -20, hi: int = 20, n: tuple[int, int] = (0, 8)):
    return tuple(rng.randint(lo, hi) for _ in range(rng.randint(*n)))


def _nested_int_list(rng: random.Random):
    return tuple(_int_list(rng, n=(0, 4)) for _ in range(rng.randint(0, 4)))


SAMPLERS: dict[str, Callable[[random.Random], Any]] = {
    str(INT): lambda rng: rng.randint(-30, 30),
    str(BOOL): lambda rng: rng.random() < 0.5,
    str(TList(INT)): _int_list,
    str(TList(TList(INT))): _nested_int_list,
}


def sample_input(rng: random.Random, ty: Ty) -> Any:
    sampler = SAMPLERS.get(str(ty))
    if sampler is None:  # pragma: no cover - families use only the types above
        raise KeyError(f"no sampler for {ty}")
    return sampler(rng)


# --- curriculum families F1–F8 -----------------------------------------------------------------


def _f1(rng: random.Random) -> tuple[Program, str]:
    """Scalar arithmetic pipeline on one integer."""
    a, b = rng.choice(SMALL_PALETTE), rng.choice(CONST_PALETTE)
    op = rng.choice(["add", "sub", "mul"])
    body = app("add", app(op, var("x"), const_int(a)), const_int(b))
    return Program((("x", INT),), body, INT), f"scalar {op} then add"


def _f2(rng: random.Random) -> tuple[Program, str]:
    """map with an arithmetic body."""
    k = rng.choice(SMALL_PALETTE)
    op = rng.choice(["add", "mul", "sub"])
    body = app("map", lam((("e", INT),), app(op, var("e"), const_int(k))), var("xs"))
    return Program((("xs", TList(INT)),), body, TList(INT)), f"map {op} {k}"


def _f3(rng: random.Random) -> tuple[Program, str]:
    """filter with a comparison predicate."""
    k = rng.choice(CONST_PALETTE)
    cmp = rng.choice(["lt", "gt", "le", "ge"])
    body = app("filter", lam((("e", INT),), app(cmp, var("e"), const_int(k))), var("xs"))
    return Program((("xs", TList(INT)),), body, TList(INT)), f"filter {cmp} {k}"


def _f4(rng: random.Random) -> tuple[Program, str]:
    """fold aggregation with a scalar accumulator."""
    # Initial values stay inside the shared constant palette. A sentinel like -999 would make
    # the instance unreachable for any search whose constant pool is the palette, so the task
    # would score zero in every condition and contribute nothing but noise.
    kind = rng.choice(["add", "max", "min"])
    init = {"add": 0, "max": 0, "min": 10}[kind]
    body = app(
        "fold",
        lam((("acc", INT), ("e", INT)), app(kind, var("acc"), var("e"))),
        const_int(init),
        var("xs"),
    )
    return Program((("xs", TList(INT)),), body, INT), f"fold {kind}"


def _f5(rng: random.Random) -> tuple[Program, str]:
    """Tuple pack / unpack."""
    k = rng.choice(SMALL_PALETTE)
    body = app(
        "add",
        app("fst", app("tuple", var("x"), const_int(k))),
        app("snd", app("tuple", const_int(k), var("x"))),
    )
    return Program((("x", INT),), body, INT), "tuple pack/unpack"


def _f6(rng: random.Random) -> tuple[Program, str]:
    """Option-safe access with a default."""
    default = rng.choice(CONST_PALETTE)
    use_head = rng.random() < 0.5
    src = (
        app("head", var("xs"))
        if use_head
        else app("index", var("xs"), const_int(rng.choice((0, 1, 2))))
    )
    body = app("option_get_or", src, const_int(default))
    return Program((("xs", TList(INT)),), body, INT), "option default"


def _f7(rng: random.Random) -> tuple[Program, str]:
    """List construction and append."""
    k = rng.choice(SMALL_PALETTE)
    body = app("append", var("xs"), app("cons", const_int(k), nil(INT)))
    return Program((("xs", TList(INT)),), body, TList(INT)), "append singleton"


def _f8(rng: random.Random) -> tuple[Program, str]:
    """Length-based conditional."""
    threshold = rng.choice(SMALL_PALETTE)
    body = app(
        "if",
        app("gt", app("length", var("xs")), const_int(threshold)),
        app("length", var("xs")),
        const_int(0),
    )
    return Program((("xs", TList(INT)),), body, INT), "length conditional"


# --- held-out compositional families F9–F12 -----------------------------------------------------


def _f9(rng: random.Random) -> tuple[Program, str]:
    """filter -> map -> fold: three composed stages. No curriculum family chains three."""
    threshold = rng.choice(CONST_PALETTE)
    factor = rng.choice(SMALL_PALETTE)
    kept = app("filter", lam((("e", INT),), app("gt", var("e"), const_int(threshold))), var("xs"))
    scaled = app("map", lam((("e", INT),), app("mul", var("e"), const_int(factor))), kept)
    body = app(
        "fold",
        lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
        const_int(0),
        scaled,
    )
    return Program((("xs", TList(INT)),), body, INT), "filter>map>fold"


def _f10(rng: random.Random) -> tuple[Program, str]:
    """Nested map over List<List<Int>>: a higher-order op inside another's body."""
    k = rng.choice(SMALL_PALETTE)
    inner = lam((("e", INT),), app("add", var("e"), const_int(k)))
    body = app(
        "map",
        lam((("row", TList(INT)),), app("map", inner, var("row"))),
        var("xss"),
    )
    return Program((("xss", TList(TList(INT))),), body, TList(TList(INT))), "nested map"


def _f11(rng: random.Random) -> tuple[Program, str]:
    """fold with a tuple accumulator: two quantities carried at once."""
    body = app(
        "fold",
        lam(
            (("acc", TTuple(INT, INT)), ("e", INT)),
            app(
                "tuple",
                app("add", app("fst", var("acc")), var("e")),
                app("add", app("snd", var("acc")), const_int(1)),
            ),
        ),
        app("tuple", const_int(0), const_int(0)),
        var("xs"),
    )
    return Program((("xs", TList(INT)),), body, TTuple(INT, INT)), "fold with pair accumulator"


def _f12(rng: random.Random) -> tuple[Program, str]:
    """Conditional dispatch between two whole pipelines, chosen by a predicate on the input."""
    threshold = rng.choice(SMALL_PALETTE)
    factor = rng.choice(SMALL_PALETTE)
    pipeline_a = app("map", lam((("e", INT),), app("mul", var("e"), const_int(factor))), var("xs"))
    pipeline_b = app("filter", lam((("e", INT),), app("ge", var("e"), const_int(0))), var("xs"))
    body = app(
        "if",
        app("gt", app("length", var("xs")), const_int(threshold)),
        pipeline_a,
        pipeline_b,
    )
    return Program((("xs", TList(INT)),), body, TList(INT)), "pipeline dispatch"


# --- adversarial siblings ----------------------------------------------------------------------


def _f9_adv(rng: random.Random) -> tuple[Program, str]:
    """Looks like F9 but the map precedes the filter, so the threshold applies to *scaled*
    values. A primitive that memorised 'filter then scale then sum' answers this wrongly."""
    threshold = rng.choice(CONST_PALETTE)
    factor = rng.choice(SMALL_PALETTE)
    scaled = app("map", lam((("e", INT),), app("mul", var("e"), const_int(factor))), var("xs"))
    kept = app("filter", lam((("e", INT),), app("gt", var("e"), const_int(threshold))), scaled)
    body = app(
        "fold",
        lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
        const_int(0),
        kept,
    )
    return Program((("xs", TList(INT)),), body, INT), "map>filter>fold (order swapped)"


def _f11_adv(rng: random.Random) -> tuple[Program, str]:
    """Tuple-accumulator fold whose second component counts only *positive* elements, so a
    primitive that fused 'sum and count' unconditionally is wrong here."""
    body = app(
        "fold",
        lam(
            (("acc", TTuple(INT, INT)), ("e", INT)),
            app(
                "tuple",
                app("add", app("fst", var("acc")), var("e")),
                app(
                    "if",
                    app("gt", var("e"), const_int(0)),
                    app("add", app("snd", var("acc")), const_int(1)),
                    app("snd", var("acc")),
                ),
            ),
        ),
        app("tuple", const_int(0), const_int(0)),
        var("xs"),
    )
    return Program((("xs", TList(INT)),), body, TTuple(INT, INT)), "fold pair, conditional count"


def _f12_adv(rng: random.Random) -> tuple[Program, str]:
    """Dispatch with the branches exchanged relative to F12."""
    threshold = rng.choice(SMALL_PALETTE)
    factor = rng.choice(SMALL_PALETTE)
    pipeline_a = app("map", lam((("e", INT),), app("mul", var("e"), const_int(factor))), var("xs"))
    pipeline_b = app("filter", lam((("e", INT),), app("ge", var("e"), const_int(0))), var("xs"))
    body = app(
        "if",
        app("gt", app("length", var("xs")), const_int(threshold)),
        pipeline_b,
        pipeline_a,
    )
    return Program((("xs", TList(INT)),), body, TList(INT)), "pipeline dispatch (branches swapped)"


FAMILIES: dict[str, Family] = {
    "F1": Family("F1", _f1, (INT,), INT, 2, False, "scalar arithmetic pipeline"),
    "F2": Family("F2", _f2, (TList(INT),), TList(INT), 1, False, "map with arithmetic body"),
    "F3": Family("F3", _f3, (TList(INT),), TList(INT), 1, False, "filter with comparison"),
    "F4": Family("F4", _f4, (TList(INT),), INT, 1, False, "fold aggregation, scalar acc"),
    "F5": Family("F5", _f5, (INT,), INT, 2, False, "tuple pack/unpack"),
    "F6": Family("F6", _f6, (TList(INT),), INT, 2, False, "option-safe access"),
    "F7": Family("F7", _f7, (TList(INT),), TList(INT), 2, False, "list construction/append"),
    "F8": Family("F8", _f8, (TList(INT),), INT, 2, False, "length-based conditional"),
    "F9": Family("F9", _f9, (TList(INT),), INT, 3, True, "filter>map>fold composition"),
    "F10": Family("F10", _f10, (TList(TList(INT)),), TList(TList(INT)), 3, True, "nested map"),
    "F11": Family("F11", _f11, (TList(INT),), TTuple(INT, INT), 3, True, "fold, tuple acc"),
    "F12": Family("F12", _f12, (TList(INT),), TList(INT), 3, True, "pipeline dispatch"),
    "F9adv": Family("F9adv", _f9_adv, (TList(INT),), INT, 3, True, "F9 adversarial sibling"),
    "F11adv": Family("F11adv", _f11_adv, (TList(INT),), TTuple(INT, INT), 3, True,
                     "F11 adversarial sibling"),
    "F12adv": Family("F12adv", _f12_adv, (TList(INT),), TList(INT), 3, True,
                     "F12 adversarial sibling"),
}

CURRICULUM_FAMILIES: tuple[str, ...] = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")
HELD_OUT_FAMILIES: tuple[str, ...] = ("F9", "F10", "F11", "F12")
ADVERSARIAL_FAMILIES: tuple[str, ...] = ("F9adv", "F11adv", "F12adv")
