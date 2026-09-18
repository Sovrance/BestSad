"""Model identity: what sat in the model role, hashed (spec §17.1, §26.9; ADR-0022).

"Fixed weights" is only fixed relative to a snapshot. A vendor silently updating a hosted model
breaks an experiment's lineage exactly as changing K0 would, so the identity of the model is
recorded with the same discipline K0's own hash receives: every field that could change what the
model does is part of a canonical JSON document, and its SHA-256 is what the compute ledger, the
pre-registration and the run manifest cite. Two runs with different identity hashes are runs
against different models, whatever the marketing name says.

The fields are the adapter contract spec §17.1 lists — supported projections, context budget,
tokenizer identity, constrained-decoding capability, log-probability access, training mode,
deterministic generation controls, tool interface — plus the two the roadmap adds: a weights
digest (or the vendor's immutable snapshot id) and the parameter count the FLOP accounting policy
needs (`conditions/flops.py`) — and, since ADR-0023, the pinning a self-hosted model needs: the
source revision the weights were fetched at, the serving precision and quantization, and the
serving stack (engine, version, hardware), because a different kernel library on different
silicon is a different set of numerics even when the weights file is the same.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

#: The two kinds of thing that may fill the model role. `enumerative_search` is ADR-0007's
#: stand-in; `fixed_weights_llm` is what EXP-002 needs. There is deliberately no third kind: a
#: fine-tuned model is a *different* identity under the same kind with `mode="fine-tuned"`, and
#: spec §17.3 keeps its results separate from fixed-weight results.
KINDS = ("enumerative_search", "fixed_weights_llm")
MODES = ("fixed-weights", "fine-tuned")
#: Keys a `model_identity` record may carry that are *about* the identity rather than part of
#: it: the hash itself, and the claim limitation a pre-registration states next to it.
ANNOTATION_KEYS = ("model_identity_hash", "claim_limitation")


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Everything that determines what the model role does, hashed."""

    model_id: str
    kind: str
    #: SHA-256 of the weights file(s), or the provider's immutable snapshot identifier. For the
    #: enumerative stand-in this is `SYNTHESIZER_VERSION`, which is what identifies its reach.
    weights_digest: str
    tokenizer_id: str
    parameter_count: int = 0
    provider: str = "local"
    mode: str = "fixed-weights"
    supported_projections: tuple[str, ...] = ("sexpr", "compact")
    context_budget_tokens: int = 0
    constrained_decoding: bool = False
    logprob_access: bool = False
    #: Spec §17.1 "tool/execution interface". `none` means the model emits text that the
    #: projection parses and nothing else — no tool calls, no code execution, no channel by
    #: which it could reach the evaluator. The roadmap's "test-file-edit detection" is moot
    #: under `none` and required under anything else; see ADR-0022.
    tool_interface: str = "none"
    #: Deterministic generation controls (spec §17.1): temperature, top_p, seed policy, max
    #: output tokens. Part of the identity because two temperatures are two experiments.
    sampling: Mapping[str, Any] = field(default_factory=dict)
    #: Pinning for a self-hosted model (ADR-0023). `revision` is the immutable source revision
    #: the weights were fetched at (a Hugging Face commit id); `weights_digest` above is the
    #: SHA-256 of what was actually loaded. `dtype` and `quantization` say what precision the
    #: forward pass ran in. `serving` names the engine, its pinned version, the hardware it ran
    #: on, and the nondeterminism it is known to introduce (vLLM batching is not bit-
    #: reproducible; verdicts are compared, never logits). Empty for the enumerative stand-in.
    revision: str = ""
    dtype: str = ""
    quantization: str = "none"
    serving: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown model kind {self.kind!r}; expected one of {KINDS}")
        if self.mode not in MODES:
            raise ValueError(f"unknown model mode {self.mode!r}; expected one of {MODES}")
        if not self.model_id or not self.weights_digest or not self.tokenizer_id:
            raise ValueError("model_id, weights_digest and tokenizer_id are all required")
        if self.parameter_count < 0:
            raise ValueError("parameter_count cannot be negative")

    # -- identity --------------------------------------------------------------------------

    def canonical(self) -> str:
        data = asdict(self)
        data["supported_projections"] = list(self.supported_projections)
        data["sampling"] = dict(self.sampling)
        data["serving"] = dict(self.serving)
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)

    def hash(self) -> str:
        """The `model_identity_hash` every ledger entry and manifest cites."""
        return hashlib.sha256(self.canonical().encode()).hexdigest()

    @property
    def is_language_model(self) -> bool:
        return self.kind == "fixed_weights_llm"

    def is_pinned(self) -> tuple[bool, list[str]]:
        """Whether a language model is pinned well enough to be cited by a pre-registration.

        ADR-0023: a hosted model that a vendor can silently update is not a fixed prior. A
        pinned identity names its source revision, the digest of the weights that were loaded,
        the precision, and the serving engine with its version and hardware. The enumerative
        stand-in is pinned by its synthesizer version alone.
        """
        if not self.is_language_model:
            return True, []
        missing = []
        if not self.revision or "<<FILL" in self.revision:
            missing.append("revision")
        if "<<FILL" in self.weights_digest:
            missing.append("weights_digest")
        if not self.dtype:
            missing.append("dtype")
        for key in ("engine", "version", "hardware"):
            value = str(self.serving.get(key, ""))
            if not value or "<<FILL" in value:
                missing.append(f"serving.{key}")
        if self.parameter_count <= 0:
            missing.append("parameter_count")
        return (not missing), missing

    def to_record(self) -> dict:
        """The `model_identity` object a pre-registration or experiment manifest carries."""
        data = json.loads(self.canonical())
        data["model_identity_hash"] = self.hash()
        return data

    @classmethod
    def from_record(cls, data: Mapping[str, Any]) -> "ModelIdentity":
        fields = {k: v for k, v in data.items() if k not in ANNOTATION_KEYS}
        if "supported_projections" in fields:
            fields["supported_projections"] = tuple(fields["supported_projections"])
        identity = cls(**fields)
        expected = data.get("model_identity_hash")
        # A `<<FILL>>` placeholder is not a claim about the hash; a draft pre-registration's
        # identity record must still construct so `is_pinned()` can say what is missing.
        if expected and "<<FILL" not in expected and expected != identity.hash():
            raise ValueError(
                "model identity record does not hash to the value it carries: the record was "
                "edited, or the identity fields changed"
            )
        return identity


def enumerative_identity(synthesizer_version: str) -> ModelIdentity:
    """ADR-0007's stand-in, described in the same terms as a real model so the two are
    comparable field by field — and so the pre-registration's `model_identity` carries a hash
    for the dry run too, rather than a bare string."""
    return ModelIdentity(
        model_id="enumerative-search-v1",
        kind="enumerative_search",
        weights_digest=synthesizer_version,
        tokenizer_id="surface-token-proxy",
        parameter_count=0,
        provider="local",
        mode="fixed-weights",
        supported_projections=("sexpr", "compact"),
        context_budget_tokens=0,
        constrained_decoding=True,   # type-directed enumeration is the strongest constraint
        logprob_access=False,
        tool_interface="none",
        sampling={"deterministic": True, "seed_policy": "per-seed vocabulary permutation"},
    )
