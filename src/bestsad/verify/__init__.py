"""The verification plane (spec §19, `docs/architecture/BESTSAD_VERIFICATION_PLANE_ENG_v0.1.md`).

This package is a **consumer** of `kernel/` and `bsir/`. It adds evidence *about* K0; it never
changes K0. Nothing in `kernel/`, `bsir/canonicalize.py`, `evaluator/` or `hidden_evaluator/`
imports from here, and `KERNEL_VERSION_HASH` is unchanged by anything in this package.

Trust posture (design §2.2): proposers of programs, specifications, harnesses and contracts
are untrusted, whoever they are. Checkers are trusted *for the property they check, within the
declared scope*. The arbiter of promotion is the assurance plane's policy gate, which this
package does not touch.

* `smt/` -- the symbolic equivalence tier (spec V4): Z3 driven over a bounded domain, checked
  against the K0 reference interpreter on every counterexample (BEST-VERIF-02).
* `external.py` -- ingestion of structured external prover results as evidence with external
  provenance that never promotes alone (BEST-VERIF-03).
* `vacuity.py` -- the non-vacuity control that makes agent-written contracts acceptable at all
  (BEST-VERIF-04).
"""

from .external import (
    ExternalResult,
    ExternalResultError,
    from_generic,
    from_kani_report,
    from_symbolic_result,
    to_evidence,
)
from .smt.bounds import SolverScope
from .smt.solver import (
    EncoderDivergence,
    SolverUnavailable,
    SymbolicExecutor,
    SymbolicResult,
    check_equivalence,
    probe,
    symbolic_execute,
)

__all__ = [
    "EncoderDivergence",
    "ExternalResult",
    "ExternalResultError",
    "from_generic",
    "from_kani_report",
    "from_symbolic_result",
    "to_evidence",
    "SolverScope",
    "SolverUnavailable",
    "SymbolicExecutor",
    "SymbolicResult",
    "check_equivalence",
    "probe",
    "symbolic_execute",
]
