"""Independent Evaluation Plane (spec §20).

The candidate generator cannot modify hidden tests, scoring logic, evaluator dependencies, or
evaluator state (P3). The evaluator is the only component that reads hidden inputs.
"""

from .contract import (
    SCORING_CONTRACT_VERSION,
    BenchmarkManifest,
    Evaluator,
    ScoreReport,
    TaskScore,
    manifest_for,
)
from .integrity import (
    HardcodingReport,
    Quarantine,
    SuspicionReport,
    check_canary,
    detect_hardcoding,
    suspicious_primitive,
)
from .sandbox import (
    IntegrityMonitor,
    IntegrityViolation,
    SandboxPolicy,
    candidate_sandbox,
    default_policy,
)

__all__ = [
    "SCORING_CONTRACT_VERSION",
    "BenchmarkManifest",
    "Evaluator",
    "HardcodingReport",
    "IntegrityMonitor",
    "IntegrityViolation",
    "Quarantine",
    "SandboxPolicy",
    "ScoreReport",
    "SuspicionReport",
    "TaskScore",
    "candidate_sandbox",
    "check_canary",
    "default_policy",
    "detect_hardcoding",
    "manifest_for",
    "suspicious_primitive",
]
