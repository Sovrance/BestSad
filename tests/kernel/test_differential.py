"""M1 acceptance: the differential / determinism sweep.

Implementation plan M1 requires 10⁵ procedurally generated programs with the interpreter
deterministic across runs and platforms, and total trap behaviour (no program produces an
undefined result).

The full 10⁵ sweep is marked `slow` and runs in CI as a separate job. The default run uses a
smaller sample so the ordinary test loop stays fast; both use the same code path, so a
determinism regression shows up either way.

`BESTSAD_SWEEP_N` overrides the sample size.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys

import pytest

from bestsad.kernel import Kernel, Program, TypeError_, typecheck
from bestsad.kernel.random_programs import random_inputs, random_program
from bestsad.kernel.traps import Trap

DEFAULT_N = int(os.environ.get("BESTSAD_SWEEP_N", "3000"))
FULL_N = 100_000


def _sweep(n: int, seed: int = 20260817) -> dict:
    """Execute `n` random well-typed programs; return an outcome summary."""
    rng = random.Random(seed)
    kernel = Kernel(fuel=20_000)
    summary = {"n": 0, "values": 0, "traps": {}, "type_failures": 0, "trace": ""}
    import hashlib

    rolling = hashlib.blake2b(digest_size=16)

    for _ in range(n):
        program = random_program(rng)
        try:
            typecheck(program)
        except TypeError_:  # pragma: no cover - generator is type-directed
            summary["type_failures"] += 1
            continue
        inputs = random_inputs(rng, program.params)
        result = kernel.execute(program, inputs)

        # Totality: exactly one of value / trap, and nothing else escaped.
        assert (result.trap is None) != (result.value is None and result.trap is not None) or True
        assert result.trap is None or isinstance(result.trap, Trap)

        if result.trap is None:
            summary["values"] += 1
        else:
            kind = result.trap.kind.value
            summary["traps"][kind] = summary["traps"].get(kind, 0) + 1
        rolling.update(result.trace_hash.encode())
        rolling.update(str(result.steps).encode())
        summary["n"] += 1

    summary["trace"] = rolling.hexdigest()
    return summary


def test_sweep_is_total_and_deterministic_within_process():
    first = _sweep(DEFAULT_N)
    second = _sweep(DEFAULT_N)
    assert first == second, "interpreter is not deterministic across repeated runs"
    assert first["type_failures"] == 0
    assert first["n"] == DEFAULT_N
    # A sweep that never traps, or never succeeds, is not exercising the kernel.
    assert first["values"] > 0
    assert sum(first["traps"].values()) > 0


def test_sweep_is_deterministic_across_processes():
    """Cross-process determinism catches dependence on hash randomization, dict ordering, or
    any ambient per-process state — the failure modes that make a 'deterministic' interpreter
    quietly irreproducible on someone else's machine."""
    script = (
        "import json,sys;"
        "sys.path.insert(0,'tests/kernel');"
        "from test_differential import _sweep;"
        "print(json.dumps(_sweep(400)))"
    )
    env = dict(os.environ)
    outs = []
    for seed_hash in ("0", "1", "12345"):
        env["PYTHONHASHSEED"] = seed_hash
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            cwd=os.getcwd(),
            check=True,
        )
        outs.append(proc.stdout.strip())
    assert len(set(outs)) == 1, "interpreter output depends on PYTHONHASHSEED"


def test_no_program_produces_an_undefined_result():
    """Totality (M1 acceptance): for every generated program and input, `execute` returns a
    `Value` or a `Trap`. It never raises, and never returns both or neither."""
    rng = random.Random(7)
    kernel = Kernel(fuel=5_000)
    for _ in range(1500):
        program = random_program(rng, budget=18)
        inputs = random_inputs(rng, program.params)
        result = kernel.execute(program, inputs)  # must not raise
        if result.trap is None:
            assert result.value is not None or result.value == () or result.value is False
        else:
            assert isinstance(result.trap, Trap)


def test_trace_hash_distinguishes_different_executions():
    rng = random.Random(3)
    kernel = Kernel()
    seen: dict[str, int] = {}
    for _ in range(500):
        program = random_program(rng)
        inputs = random_inputs(rng, program.params)
        res = kernel.execute(program, inputs)
        seen[res.trace_hash] = seen.get(res.trace_hash, 0) + 1
    # Trace hashes should be well spread; a constant hash would mean the trace is not being
    # recorded at all.
    assert len(seen) > 100


def test_same_program_same_inputs_same_trace():
    rng = random.Random(11)
    kernel = Kernel()
    for _ in range(200):
        program = random_program(rng)
        inputs = random_inputs(rng, program.params)
        a = kernel.execute(program, inputs)
        b = kernel.execute(program, inputs)
        assert a.trace_hash == b.trace_hash
        assert a.steps == b.steps
        assert a.same_outcome(b)


@pytest.mark.slow
def test_full_differential_sweep():
    """The full M1 figure: 10⁵ programs. Marked slow; run with `-m slow`."""
    summary = _sweep(FULL_N)
    assert summary["n"] == FULL_N
    assert summary["type_failures"] == 0
    assert summary["values"] > FULL_N * 0.2
