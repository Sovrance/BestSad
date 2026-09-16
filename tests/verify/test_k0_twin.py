"""BEST-VERIF-05 acceptance: the Rust twin of K0 (`k0rs/`) agrees with the Python reference.

Agreement is *not* a Kani property (design doc §BEST-VERIF-05, ADR-0020): it is established
by running both implementations over the same corpus and requiring the identical
`Value | Trap(kind)` -- and, stricter than the M1 sweep asks, the identical step count, because
the ADR-0008 cost model is the property the twin exists to make checkable. Trace hashes are
not compared: they are an artefact of the Python evaluator's record order, not of K0.

Three layers, each against the reference:

1. the kernel hash the binary computes from its own op table equals `KERNEL_VERSION_HASH`;
2. one program per K0 operation over the enumerated small domain (the `PER_OP` table shared
   with the encoder differential test);
3. the M1 corpus: `random_program` / `random_inputs` from the M1 seed with `Kernel(fuel=20_000)`,
   exactly as `tests/kernel/test_differential.py::_sweep` draws them. The default sample runs
   everywhere; the full 10⁵ runs as `slow` in the K0 twin parity job.

If the two ever disagree, the Python reference wins and the twin is fixed (ADR-0002).

`BESTSAD_TWIN_SWEEP_N` overrides the default sample size.
"""

from __future__ import annotations

import os
import random

import pytest

from bestsad.bsir.equivalence import enumerate_domain
from bestsad.kernel import K0_OPS, KERNEL_VERSION_HASH, Kernel, Program
from bestsad.kernel.random_programs import random_inputs, random_program
from bestsad.verify import external, twin

from conftest import PER_OP, requires_twin

requires_twin()

DEFAULT_N = int(os.environ.get("BESTSAD_TWIN_SWEEP_N", "3000"))
FULL_N = 100_000
M1_SEED = 20260817
M1_FUEL = 20_000


def _explain(program: Program, inputs, reference, candidate) -> str:
    return (
        f"the twin disagrees with the reference on {program} at {inputs!r}: "
        f"reference {reference} in {reference.steps} steps, twin {candidate} in "
        f"{candidate.steps} steps. The Python reference is normative; fix k0rs/."
    )


def _same(reference, candidate) -> bool:
    return reference.same_outcome(candidate) and reference.steps == candidate.steps


@pytest.fixture(scope="module")
def runner():
    with twin.TwinRunner(fuel=M1_FUEL) as tw:
        yield tw


def test_the_twin_computes_the_reference_kernel_hash():
    binary = twin.locate()
    assert twin.twin_hash(binary) == KERNEL_VERSION_HASH


def test_the_per_op_table_still_covers_every_operation():
    assert set(PER_OP) == {o.op for o in K0_OPS}


@pytest.mark.parametrize("op", sorted(PER_OP))
def test_each_operation_agrees_with_the_reference_over_the_small_domain(op, runner):
    program = PER_OP[op]
    kernel = Kernel(fuel=M1_FUEL)
    cases = enumerate_domain(tuple(t for _, t in program.params), 200)
    assert cases, f"no enumerable domain for {op}"
    for inputs in cases:
        reference = kernel.execute(program, inputs)
        candidate = runner.execute(program, inputs)
        assert _same(reference, candidate), _explain(program, inputs, reference, candidate)


def test_traps_and_limits_agree_at_the_edges(runner):
    """The places the design doc names as where K0 breaks, with the twin's own fuel/depth."""
    from bestsad.kernel import INT, TList, app, const_int, var

    kernel = Kernel(fuel=M1_FUEL)
    cases = [
        (Program((("x", INT),), app("mul", app("mul", var("x"), var("x")),
                                   app("mul", var("x"), var("x"))), INT), [1 << 16]),
        (Program((("x", INT),), app("mul", app("mul", var("x"), var("x")),
                                   app("mul", var("x"), var("x"))), INT), [1 << 17]),
        (Program((("x", INT), ("y", INT)), app("range", var("x"), var("y")), TList(INT)),
         [0, 4096]),
        (Program((("x", INT), ("y", INT)), app("range", var("x"), var("y")), TList(INT)),
         [0, 4097]),
        (Program((("x", INT), ("y", INT)), app("div", var("x"), var("y")), INT), [-7, 2]),
        (Program((("x", INT), ("y", INT)), app("mod", var("x"), var("y")), INT), [7, -2]),
        (Program((("x", INT),), const_int(1 << 70), INT), [0]),
    ]
    # Depth: 300 nested negations exceed the default depth limit.
    deep = var("x")
    for _ in range(300):
        deep = app("neg", deep)
    cases.append((Program((("x", INT),), deep, INT), [1]))
    for program, inputs in cases:
        reference = kernel.execute(program, inputs)
        candidate = runner.execute(program, inputs)
        assert _same(reference, candidate), _explain(program, inputs, reference, candidate)
    # Fuel as a per-call override, as `Kernel.execute(fuel=)` takes it.
    add = Program((("x", INT), ("y", INT)), app("add", var("x"), var("y")), INT)
    for fuel in (0, 1, 2, 3):
        reference = kernel.execute(add, [1, 2], fuel=fuel)
        candidate = runner.execute(add, [1, 2], fuel=fuel)
        assert _same(reference, candidate), _explain(add, [1, 2], reference, candidate)


def _sweep(n: int, runner: twin.TwinRunner, seed: int = M1_SEED) -> dict:
    """Both implementations over the M1 corpus, drawn exactly as the M1 sweep draws it."""
    rng = random.Random(seed)
    kernel = Kernel(fuel=M1_FUEL)
    summary = {"n": 0, "values": 0, "traps": {}}
    for _ in range(n):
        program = random_program(rng)
        inputs = random_inputs(rng, program.params)
        reference = kernel.execute(program, inputs)
        candidate = runner.execute(program, inputs)
        assert _same(reference, candidate), _explain(program, inputs, reference, candidate)
        if reference.trap is None:
            summary["values"] += 1
        else:
            kind = reference.trap.kind.value
            summary["traps"][kind] = summary["traps"].get(kind, 0) + 1
        summary["n"] += 1
    return summary


def test_the_twin_matches_the_reference_over_the_m1_corpus_sample(runner):
    summary = _sweep(DEFAULT_N, runner)
    assert summary["n"] == DEFAULT_N
    assert summary["values"] > 0
    assert sum(summary["traps"].values()) > 0, "a corpus that never traps is not exercising K0"


@pytest.mark.slow
def test_the_twin_matches_the_reference_over_the_full_m1_corpus(runner):
    summary = _sweep(FULL_N, runner)
    assert summary["n"] == FULL_N


def test_kani_output_parses_into_the_external_result_shape():
    """The bridge from `cargo kani`'s text to `from_kani_report`; no verifier run needed."""
    text = (
        "Checking harness proofs::add_is_total_and_bounded...\n"
        "CBMC 6.x\nVERIFICATION:- SUCCESSFUL\nVerification Time: 1.2s\n"
        "Checking harness proofs::div_traps_on_zero...\n"
        "Failed Checks: ...\nVERIFICATION:- FAILED\n"
        "Checking harness proofs::never_finished...\n"
    )
    report = twin.kani_report_from_output(text, kani_version="0.67.0", unwind=8,
                                          assumptions=["bounded"])
    assert [h["status"] for h in report["harnesses"]] == ["SUCCESS", "FAILURE", "UNDETERMINED"]
    result = external.from_kani_report(report, kernel_version_hash=KERNEL_VERSION_HASH)
    assert result.verdict == "refuted"
    green = twin.kani_report_from_output(text.split("Checking harness proofs::div")[0],
                                         kani_version="0.67.0")
    assert external.from_kani_report(green, kernel_version_hash=KERNEL_VERSION_HASH).verdict == "proved"
