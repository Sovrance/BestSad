"""Confound control plane (spec §40): conditions A-I, scaffolding matching, compute accounting."""

from .compute import (
    ACCOUNTING_POLICY_ID,
    WEIGHTS,
    ComputeLedger,
    ComputeMatchError,
    matched_budget,
    reconcile_search_only,
)
from .plane import (
    CONFOUNDS,
    REQUIRED_CONTROLS,
    ROLES,
    Condition,
    ConditionPlaneError,
    ResidualConfound,
    build_conditions,
    check_condition_f,
)
from .scaffolding import (
    Scaffolding,
    ScaffoldingMatcher,
    ScaffoldingReport,
    ScaffoldingResidual,
    scaffolding_is_equalized,
)

__all__ = [
    "ACCOUNTING_POLICY_ID",
    "CONFOUNDS",
    "REQUIRED_CONTROLS",
    "ROLES",
    "WEIGHTS",
    "ComputeLedger",
    "ComputeMatchError",
    "Condition",
    "ConditionPlaneError",
    "ResidualConfound",
    "Scaffolding",
    "ScaffoldingMatcher",
    "ScaffoldingReport",
    "ScaffoldingResidual",
    "build_conditions",
    "check_condition_f",
    "matched_budget",
    "reconcile_search_only",
    "scaffolding_is_equalized",
]
