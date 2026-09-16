"""BEST-VERIF-02 acceptance test 1: the encoder is a second reading of K0, checked against the
first (AGENTS.md "definition of done": differential tests against the K0 reference interpreter
wherever semantics are involved).

For every operation in `K0_OPS` a small program is evaluated over the enumerated small domain,
and for a corpus of random well-typed programs over random inputs, on both the reference
interpreter and the encoding -- the latter by solving for the output -- and the two must
produce the identical `Value | Trap(kind)`.

Inputs the bounded domain excludes (a list longer than `N`, an intermediate `range` that would
exceed it) are counted and skipped, never silently passed; a case where the reference exhausts
fuel or depth is outside the v0.1 assumptions (ADR-0019) and is likewise counted. The test
asserts that a material fraction of cases was actually compared.

`BESTSAD_VERIFY_SWEEP_N` overrides the random-program count; the full count runs as `slow`.
"""

from __future__ import annotations

import os
import random

import pytest

from bestsad.bsir.equivalence import enumerate_domain
from bestsad.kernel import K0_OPS, Kernel, Program
from bestsad.kernel.random_programs import random_inputs, random_program
from bestsad.kernel.traps import TrapKind
from bestsad.verify import SolverScope, SymbolicExecutor

from conftest import PER_OP, requires_solver

requires_solver()

DEFAULT_N = int(os.environ.get("BESTSAD_VERIFY_SWEEP_N", "250"))
FULL_N = 10_000
EXCLUDED = {TrapKind.FUEL_EXHAUSTED, TrapKind.DEPTH_EXCEEDED}


def _compare(program: Program, inputs, kernel: Kernel, executor: SymbolicExecutor) -> str:
    """One differential case. Returns 'compared', 'outside_domain' or 'excluded_trap'."""
    reference = kernel.execute(program, inputs)
    if reference.trap is not None and reference.trap.kind in EXCLUDED:
        return "excluded_trap"
    encoded = executor.run(inputs)
    if encoded is None:
        return "outside_domain"
    assert encoded.same_outcome(reference), (
        f"encoder disagrees with the reference on {program} at {inputs!r}: "
        f"encoded {encoded}, reference {reference}"
    )
    return "compared"


def test_the_table_covers_every_k0_operation():
    """Guards the guard: a K0 op with no differential fixture would go unchecked silently."""
    assert set(PER_OP) == {o.op for o in K0_OPS}


@pytest.mark.parametrize("op", sorted(PER_OP))
def test_each_operation_agrees_with_the_reference_over_the_small_domain(op):
    program = PER_OP[op]
    kernel = Kernel()
    scope = SolverScope()
    cases = enumerate_domain(tuple(t for _, t in program.params), 200)
    executor = SymbolicExecutor(program, scope)
    tallies = {"compared": 0, "outside_domain": 0, "excluded_trap": 0}
    for inputs in cases:
        tallies[_compare(program, inputs, kernel, executor)] += 1
    assert tallies["compared"] > 0, f"{op}: nothing was compared ({tallies})"


def _sweep(n: int, seed: int = 20260915, per_program: int = 3) -> dict:
    rng = random.Random(seed)
    kernel = Kernel()
    scope = SolverScope()
    tallies = {"compared": 0, "outside_domain": 0, "excluded_trap": 0, "programs": 0}
    for _ in range(n):
        program = random_program(rng)
        tallies["programs"] += 1
        executor = SymbolicExecutor(program, scope)
        for _ in range(per_program):
            inputs = random_inputs(rng, program.params)
            tallies[_compare(program, inputs, kernel, executor)] += 1
    return tallies


def test_random_programs_agree_with_the_reference():
    tallies = _sweep(DEFAULT_N)
    assert tallies["programs"] == DEFAULT_N
    total = tallies["compared"] + tallies["outside_domain"] + tallies["excluded_trap"]
    assert tallies["compared"] > 0.5 * total, f"too few cases were actually compared: {tallies}"


@pytest.mark.slow
def test_full_random_sweep_agrees_with_the_reference():
    """The full figure the work order names: 10^4 random programs."""
    tallies = _sweep(FULL_N)
    assert tallies["programs"] == FULL_N
    assert tallies["compared"] > FULL_N
