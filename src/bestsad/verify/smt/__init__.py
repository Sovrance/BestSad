"""Symbolic equivalence over a bounded domain, with Z3 (ADR-0019).

Three modules, in dependency order:

* `bounds`  -- the declared `solver_scope`: list bound, integer bound, timeout, unrolling depth,
  and the assumptions those bounds imply. A proof is meaningless without it.
* `encode`  -- K0 term -> SMT encoding under K0 v1.0.0 semantics (ADR-0008). A second reading
  of the kernel; any disagreement with the reference interpreter is a bug here.
* `solver`  -- the Z3 adapter: probe, determinism settings, resource accounting, the
  counterexample discipline that keeps the encoder honest, and the Tier 2 entry point that
  `bsir/equivalence.py` calls.
"""

from .bounds import SolverScope
from .encode import Encoder, Unsupported
from .solver import (
    EncoderDivergence,
    SolverUnavailable,
    SymbolicExecutor,
    SymbolicResult,
    check_equivalence,
    probe,
    symbolic_execute,
    symbolic_tier,
)

__all__ = [
    "Encoder",
    "EncoderDivergence",
    "SolverScope",
    "SolverUnavailable",
    "SymbolicExecutor",
    "SymbolicResult",
    "Unsupported",
    "check_equivalence",
    "probe",
    "symbolic_execute",
    "symbolic_tier",
]
