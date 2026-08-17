"""Causal attribution plane (spec §42)."""

from .attribution import (
    AttributionTable,
    ConcentrationTest,
    PrimitiveEffect,
    ablate,
    build_attribution,
    concentration_test,
    expand_all,
    paired_ablation,
)

__all__ = [
    "AttributionTable",
    "ConcentrationTest",
    "PrimitiveEffect",
    "ablate",
    "build_attribution",
    "concentration_test",
    "expand_all",
    "paired_ablation",
]
