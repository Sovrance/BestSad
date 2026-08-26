"""BSLD: declarative descriptions of evolved languages, and their lowering into BSIR.

A described language is a surface, and surfaces are never authoritative (ADR 0013). What makes
a descriptor usable is not that BestSad trusts it but that its lowering carries proof
obligations which are discharged by evidence (ADR 0014).
"""

from .descriptor import (
    LOWERING_EQUIVALENCE,
    DescriptorError,
    LanguageDescriptor,
    LoweringTemplate,
    OperationSpec,
    descriptor_id,
    load,
    parse,
    seal,
    serialize,
)
from .lowering import LoweringError, LoweringResult, check_lowering, lower
from .source import SourceProgram, SourceTerm, s, slam

__all__ = [
    "DescriptorError",
    "LOWERING_EQUIVALENCE",
    "LanguageDescriptor",
    "LoweringError",
    "LoweringResult",
    "LoweringTemplate",
    "OperationSpec",
    "SourceProgram",
    "SourceTerm",
    "check_lowering",
    "descriptor_id",
    "load",
    "lower",
    "parse",
    "seal",
    "s",
    "serialize",
    "slam",
]
