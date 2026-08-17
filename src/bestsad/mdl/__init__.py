"""MDL Semantic Gain, SG-v2 (spec §21.4)."""

from .semantic_gain import (
    CODING_SCHEME_VERSION,
    DEFAULT_KAPPA,
    CodingScheme,
    PairedOutcome,
    SemanticGainResult,
    compression_ratio,
    semantic_gain_v2,
)

__all__ = [
    "CODING_SCHEME_VERSION",
    "DEFAULT_KAPPA",
    "CodingScheme",
    "PairedOutcome",
    "SemanticGainResult",
    "compression_ratio",
    "semantic_gain_v2",
]
