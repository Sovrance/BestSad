"""MDL Semantic Gain, SG-v2 (spec §21.4; implementation plan M7).

    SG_v2(p) = [ L(S_ood | G_without_p) - L(S_ood | G_with_p) ]
             - [ L(S_train | G_without_p) - L(S_train | G_with_p) ] * kappa
             - L(p | G_without_p)

`L(S | G)` is the description length in bits of a solution set under genome `G`, computed with a
**fixed, pre-registered code**. The coding scheme and `kappa` must be committed before EXP-001
and hashed into the run manifest (spec §21.4), so both live in `CodingScheme` and both are
serialized into the manifest rather than being implicit in the code.

The point of the reformulation is that SG-v1 rewarded corpus compression, which H13 declines to
count as capability. Under SG-v2 a primitive that only shortens the *training* corpus scores at
most zero, because that saving is subtracted back out at weight `kappa`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..kernel import OPS_BY_NAME, Program, Term

#: Default discount on training-corpus savings. `kappa = 1.0` removes them entirely.
DEFAULT_KAPPA = 1.0

CODING_SCHEME_VERSION = "mdl-code-1.0.0"


@dataclass(frozen=True, slots=True)
class CodingScheme:
    """A fixed prefix code over genome vocabulary, pre-registered before any run.

    Each node costs `-log2(prior(op))` bits, where the prior is the genome's declared
    distribution over its vocabulary. Literals additionally pay for their value, and variables
    for their index. This is an arithmetic-coding-style cost against a declared prior, as
    spec §21.4 requires, rather than a raw token count — which is exactly the distinction
    H13 turns on.
    """

    version: str = CODING_SCHEME_VERSION
    kappa: float = DEFAULT_KAPPA
    literal_bits: float = 6.0
    variable_bits: float = 3.0
    #: Weight of a primitive in the declared prior relative to a K0 operation. Below 1.0 means a
    #: primitive is *a priori* less likely than a kernel operation, so adding one to the genome
    #: costs description length everywhere it is not used. Without this, growing the vocabulary
    #: would be free under the code and MDL would degenerate into "add every macro".
    primitive_prior_weight: float = 0.6

    def content_hash(self) -> str:
        payload = json.dumps(
            {
                "version": self.version,
                "kappa": self.kappa,
                "literal_bits": self.literal_bits,
                "variable_bits": self.variable_bits,
                "primitive_prior_weight": self.primitive_prior_weight,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_record(self) -> dict:
        return {
            "coding_scheme_version": self.version,
            "kappa": self.kappa,
            "literal_bits": self.literal_bits,
            "variable_bits": self.variable_bits,
            "primitive_prior_weight": self.primitive_prior_weight,
            "coding_scheme_hash": self.content_hash(),
        }

    # -- the code itself -------------------------------------------------------------------

    def op_costs(self, vocabulary: Sequence[str]) -> dict[str, float]:
        """Bits per operation under the declared prior."""
        weights = {
            op: (self.primitive_prior_weight if op.startswith("prim:") else 1.0)
            for op in vocabulary
        }
        total = sum(weights.values())
        if total <= 0:  # pragma: no cover - a genome always has a vocabulary
            return {}
        return {op: -math.log2(weight / total) for op, weight in weights.items()}

    def description_length(self, term: Term, vocabulary: Sequence[str]) -> float:
        """`L(t | G)` in bits."""
        costs = self.op_costs(vocabulary)
        # An operation outside the vocabulary is not codeable under this genome; charge the
        # cost of the rarest codeable symbol plus a penalty so the term is finite but dominated.
        fallback = (max(costs.values()) if costs else 8.0) + 8.0
        total = 0.0
        for node in term.walk():
            total += costs.get(node.op, fallback)
            if node.op in ("const_int", "const_bool"):
                total += self.literal_bits
            elif node.op == "var":
                total += self.variable_bits
        return total

    def program_length(self, program: Program, vocabulary: Sequence[str]) -> float:
        return self.description_length(program.body, vocabulary)

    def set_length(self, programs: Sequence[Program], vocabulary: Sequence[str]) -> float:
        return sum(self.program_length(p, vocabulary) for p in programs)


@dataclass(frozen=True, slots=True)
class SemanticGainResult:
    primitive_id: str
    semantic_gain: float
    ood_saving: float
    train_saving: float
    primitive_cost: float
    kappa: float

    @property
    def positive(self) -> bool:
        return self.semantic_gain > 0

    def to_record(self) -> dict:
        return {
            "primitive_id": self.primitive_id,
            "semantic_gain_v2": self.semantic_gain,
            "ood_description_saving_bits": self.ood_saving,
            "train_description_saving_bits": self.train_saving,
            "primitive_cost_bits": self.primitive_cost,
            "kappa": self.kappa,
        }


def semantic_gain_v2(
    primitive_id: str,
    *,
    ood_with: Sequence[Program],
    ood_without: Sequence[Program],
    train_with: Sequence[Program],
    train_without: Sequence[Program],
    vocabulary_with: Sequence[str],
    vocabulary_without: Sequence[str],
    primitive_expansion: Term,
    scheme: CodingScheme | None = None,
) -> SemanticGainResult:
    """Compute SG-v2 for one primitive.

    The `_with` / `_without` solution sets are the *same tasks* solved under the two genomes.
    Where a task is solved under one genome and not the other, pass the solved form for both —
    the metric is about description length, and mixing in a solve-rate difference here would
    double-count the very effect the primary endpoint measures.
    """
    scheme = scheme or CodingScheme()

    ood_saving = scheme.set_length(ood_without, vocabulary_without) - scheme.set_length(
        ood_with, vocabulary_with
    )
    train_saving = scheme.set_length(train_without, vocabulary_without) - scheme.set_length(
        train_with, vocabulary_with
    )
    primitive_cost = scheme.description_length(primitive_expansion, vocabulary_without)

    gain = ood_saving - train_saving * scheme.kappa - primitive_cost
    return SemanticGainResult(
        primitive_id=primitive_id,
        semantic_gain=gain,
        ood_saving=ood_saving,
        train_saving=train_saving,
        primitive_cost=primitive_cost,
        kappa=scheme.kappa,
    )


def compression_ratio(baseline_tokens: int, condition_tokens: int) -> float:
    """`compression_ratio` = baseline model-side tokens / condition model-side tokens."""
    if condition_tokens <= 0:
        return 0.0
    return baseline_tokens / condition_tokens


@dataclass(frozen=True, slots=True)
class PairedOutcome:
    """`compression_ratio` and `capability_delta`, which may only be emitted together.

    Spec §21.6 makes conflating them a reportable protocol violation, and `AGENTS.md`
    invariant 4 forbids it outright. Binding them into one object means there is no code path
    that produces one without the other.
    """

    compression_ratio: float
    capability_delta: float
    non_inferiority_margin: float

    @property
    def is_efficiency_only(self) -> bool:
        """True when compression improved and capability is inside the non-inferiority margin.

        Such a result is reported as an **efficiency result**, never as a capability result.
        """
        return (
            self.compression_ratio > 1.0
            and abs(self.capability_delta) <= self.non_inferiority_margin
        )

    def to_record(self) -> dict:
        return {
            "compression_ratio": self.compression_ratio,
            "capability_delta": self.capability_delta,
            "non_inferiority_margin": self.non_inferiority_margin,
            "classification": "efficiency_only" if self.is_efficiency_only else "capability_candidate",
        }
