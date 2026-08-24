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
from .isolation import (
    DEFAULT_ADDRESS_SPACE,
    DEFAULT_CPU_SECONDS,
    DEFAULT_FILE_SIZE,
    ISOLATION_AVAILABLE,
    IsolatedResult,
    ResourceLimits,
    run_isolated,
)
from .sandbox import (
    IntegrityMonitor,
    IntegrityViolation,
    SandboxPolicy,
    candidate_sandbox,
    default_policy,
)

__all__ = [
    "DEFAULT_ADDRESS_SPACE",
    "DEFAULT_CPU_SECONDS",
    "DEFAULT_FILE_SIZE",
    "ISOLATION_AVAILABLE",
    "IsolatedResult",
    "ResourceLimits",
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
    "run_isolated",
    "suspicious_primitive",
]
