"""The model role (spec §17): adapters behind one interface, identified by hash.

`EnumerativeAdapter` is ADR-0007's stand-in. `LLMAdapter` is the fixed-weights language model
EXP-002 needs (ADR-0022). Both return the synthesizer's `SearchResult`, so the runner, the
evaluator and the ledger do not know which one they are talking to — which is the property
ADR-0007 was written to buy.
"""

from .adapter import (
    DEFAULT_MODEL_SPEC,
    EnumerativeAdapter,
    ModelAdapter,
    build_adapter,
    spec_identity,
    spec_requires_network,
)
from .identity import KINDS, MODES, ModelIdentity, enumerative_identity
from .llm import (
    Backend,
    Completion,
    HTTPBackend,
    LLMAdapter,
    RecordingBackend,
    ReplayBackend,
    SampleBudget,
    ScriptedBackend,
    Transcript,
    TranscriptMiss,
    build_llm_adapter,
    scaffolding_policy,
)

__all__ = [
    "DEFAULT_MODEL_SPEC",
    "KINDS",
    "MODES",
    "Backend",
    "Completion",
    "EnumerativeAdapter",
    "HTTPBackend",
    "LLMAdapter",
    "ModelAdapter",
    "ModelIdentity",
    "RecordingBackend",
    "ReplayBackend",
    "SampleBudget",
    "ScriptedBackend",
    "Transcript",
    "TranscriptMiss",
    "build_adapter",
    "build_llm_adapter",
    "enumerative_identity",
    "scaffolding_policy",
    "spec_identity",
    "spec_requires_network",
]
