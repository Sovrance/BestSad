"""Shared fixtures for the verification plane tests.

The solver is an optional dependency (ADR-0019). Tests that need it skip with a named reason
when it is absent, so `pip install -e ".[dev]"` alone still runs the suite green; Gate G-V
(`scripts/ci_local.py --gate verify`) is where absence is reported UNAVAILABLE rather than
skipped, per ADR-0018.
"""

from __future__ import annotations

import pytest

from bestsad.bsir import EquivalenceContract
from bestsad.kernel import INT, Program


def requires_solver():
    """Module-level guard: skip a solver-backed test module when Z3 cannot be used."""
    from bestsad.verify.smt.solver import probe

    if not probe():
        pytest.skip("z3 is not installed or not usable; Gate G-V reports this as UNAVAILABLE",
                    allow_module_level=True)


@pytest.fixture
def contract() -> EquivalenceContract:
    return EquivalenceContract(input_domain_ref="int:small-enumerated")


def prog(body, params=(("x", INT),), result=INT) -> Program:
    return Program(params=params, body=body, result_type=result)
