"""Closure bodies may reference the enclosing program's parameters.

The fourth standing residual said the synthesizer "cannot capture outer variables in closures,
so some tasks are unreachable in *every* condition... it lowers the ceiling." These tests pin
the capability, and the probe soundness that had to come with it.

Whether removing the limitation actually *raises* the ceiling is a measured question, answered
in `docs/research/negative_results/`. It does not, on the endpoint that carries the study.
"""

from __future__ import annotations

import pytest

from bestsad.experiments.exp001 import BASE_VOCABULARY
from bestsad.kernel import INT, Kernel, Program, TList
from bestsad.kernel.terms import app, const_int, lam, var
from bestsad.solver import EnumerativeSynthesizer, SearchBudget
from bestsad.solver.enumerative import SYNTHESIZER_VERSION, can_probe
from bestsad.tasks.families import Task

BUDGET = SearchBudget(max_nodes=40_000, max_size=4, lam_max_size=3, lam_bank_cap=60,
                      bank_cap=200)


def _capture_task() -> Task:
    """`filter (e -> ge e n) xs` — solvable only if the closure can see `n`.

    `n` is a parameter of the enclosing program, not of the lambda, so before capture no
    enumerated closure body could mention it and this shape was unreachable at any budget.
    """
    body = app("filter", lam((("e", INT),), app("ge", var("e"), var("n"))), var("xs"))
    reference = Program((("xs", TList(INT)), ("n", INT)), body, None)
    inputs = (
        ((1, 5, 9), 4),
        ((-3, 0, 7, 2), 1),
        ((10, 20), 15),
    )
    return Task(
        task_id="capture-probe", family="F-capture",
        params=(("xs", TList(INT)), ("n", INT)), result_type=TList(INT),
        reference=reference, train_inputs=inputs, hidden_inputs=inputs,
        seed=1, composition_depth=2,
    )


def test_a_closure_can_reference_an_enclosing_parameter():
    synthesizer = EnumerativeSynthesizer(
        Kernel(fuel=100_000), BASE_VOCABULARY, {}, budget=BUDGET, seed=1
    )
    assert synthesizer.solve(_capture_task()).solved_train


def test_capture_is_restricted_to_types_that_can_be_probed():
    """A type with no probe values cannot be pruned by observational equivalence. Leaving it
    out of scope costs reach; capturing it would mean pruning on signatures computed from a
    stand-in value, which is unsound in a way no test downstream would catch."""
    from bestsad.kernel import BOOL, TOption

    assert can_probe(INT) and can_probe(BOOL) and can_probe(TList(INT))
    assert not can_probe(TOption(INT))

    env = EnumerativeSynthesizer._closure_env(
        ("L0",), (INT,), {"xs": TList(INT), "opt": TOption(INT), "n": INT}
    )
    assert "opt" not in env, "an unprobeable outer variable must not enter closure scope"
    assert env["n"] == INT and env["L0"] == INT


def test_an_unprobeable_type_raises_rather_than_defaulting():
    """The old fallback returned integer 0 for any unlisted type — feeding an int where a list
    was expected, and giving the term a signature computed from the wrong value."""
    from bestsad.kernel import TOption
    from bestsad.solver.enumerative import _probe_values

    with pytest.raises(KeyError, match="cannot prune soundly"):
        _probe_values(TOption(INT))


def test_the_closure_shadows_an_outer_variable_of_the_same_name():
    """`L0` is bound by the lambda. Offering an outer `L0` would enumerate bodies whose meaning
    does not match what the term computes once evaluated."""
    env = EnumerativeSynthesizer._closure_env(("L0",), (INT,), {"L0": TList(INT)})
    assert env["L0"] == INT


def test_changing_what_the_searcher_reaches_bumps_its_version():
    """The fingerprint guard: a checkpoint written by one searcher must never be served to a
    different one. This is the same defect the genome and budget fields already prevent."""
    assert "closure-capture" in SYNTHESIZER_VERSION

    from bestsad.experiments import exp001

    assert exp001.SYNTHESIZER_VERSION == SYNTHESIZER_VERSION
