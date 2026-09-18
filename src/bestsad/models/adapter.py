"""The model role behind one interface (spec §17.1; ADR-0007; ADR-0022).

ADR-0007 bought one property: "adding a real model adapter is a new component behind the same
interface; nothing else in the instrument should need to change." This module is where that
property is cashed. Every adapter exposes

* `identity` — a hashed `ModelIdentity`, cited by the ledger and the pre-registration;
* `solve(task) -> SearchResult` — the same shape the enumerative synthesizer returns, so
  `Exp001Runner._run_condition` scores an LLM's proposals exactly as it scores the enumerator's;
* `contract()` — the spec §17.1 adapter contract as a record, so a run manifest can state what
  the model role could and could not do rather than leaving it to be inferred.

`build_adapter` turns a JSON-serialisable *spec* into an adapter. The spec is JSON on purpose:
condition jobs run behind a process boundary that carries JSON only, and a checkpoint key must
be able to name the model without holding a live client. `{"kind": "enumerative_search"}` is
the default and reproduces every EXP-001-DR record byte for byte.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..kernel import Kernel, OpSig
from ..kernel.terms import Program
from ..solver import EnumerativeSynthesizer, SearchBudget, SearchResult
from ..solver.enumerative import SYNTHESIZER_VERSION
from ..tasks.families import Task
from .identity import ModelIdentity, enumerative_identity

DEFAULT_MODEL_SPEC: dict = {"kind": "enumerative_search"}


@runtime_checkable
class ModelAdapter(Protocol):
    """What the runner needs from whatever fills the model role."""

    identity: ModelIdentity

    def solve(self, task: Task) -> SearchResult:  # pragma: no cover - protocol
        ...

    def contract(self) -> dict:  # pragma: no cover - protocol
        ...


class EnumerativeAdapter:
    """ADR-0007's stand-in, wrapped so it satisfies the same protocol as a language model."""

    def __init__(
        self,
        kernel: Kernel,
        vocabulary: Sequence[str],
        primitive_sigs: Mapping[str, OpSig] | None,
        *,
        budget: SearchBudget,
        seed: int,
    ) -> None:
        self._synthesizer = EnumerativeSynthesizer(
            kernel, vocabulary, primitive_sigs, budget=budget, seed=seed
        )
        self.identity = enumerative_identity(SYNTHESIZER_VERSION)
        self.budget = budget

    def solve(self, task: Task) -> SearchResult:
        return self._synthesizer.solve(task)

    def contract(self) -> dict:
        return {
            "kind": self.identity.kind,
            "model_identity_hash": self.identity.hash(),
            "supported_projections": list(self.identity.supported_projections),
            "context_budget_tokens": 0,
            "tokenizer_id": self.identity.tokenizer_id,
            "constrained_decoding": True,
            "logprob_access": False,
            "mode": self.identity.mode,
            "deterministic": True,
            "tool_interface": "none",
            "search_budget": asdict(self.budget),
            "claim_limitation": (
                "ADR-0007: results are Claim Level 0/E instrument validation and cannot bear "
                "on H2, H13, H14 or H15"
            ),
        }


def build_adapter(
    spec: Mapping[str, Any] | None,
    *,
    kernel: Kernel,
    vocabulary: Sequence[str],
    primitive_sigs: Mapping[str, OpSig] | None,
    budget: SearchBudget,
    seed: int,
    projection_name: str = "sexpr",
    scaffolding: Mapping[str, Any] | None = None,
    worked_examples: Sequence[tuple[Task, Program]] = (),
) -> ModelAdapter:
    """Construct the adapter a spec names.

    The enumerative kind ignores projection, scaffolding and worked examples, exactly as the
    synthesizer always has: it is insensitive to surface form except through token counting,
    which is why conditions F and H cannot be interpreted with it (ADR-0007). The language-model
    kind consumes all three, which is what makes those conditions interpretable for the first
    time.
    """
    spec = dict(spec or DEFAULT_MODEL_SPEC)
    kind = spec.get("kind", "enumerative_search")
    if kind == "enumerative_search":
        return EnumerativeAdapter(kernel, vocabulary, primitive_sigs, budget=budget, seed=seed)
    if kind == "fixed_weights_llm":
        from .llm import build_llm_adapter

        return build_llm_adapter(
            spec,
            kernel=kernel,
            vocabulary=vocabulary,
            primitive_sigs=primitive_sigs,
            budget=budget,
            seed=seed,
            projection_name=projection_name,
            scaffolding=scaffolding,
            worked_examples=worked_examples,
        )
    raise ValueError(f"unknown model kind {kind!r}")


def spec_identity(spec: Mapping[str, Any] | None) -> ModelIdentity:
    """The identity a spec names, without constructing a kernel or a client."""
    spec = dict(spec or DEFAULT_MODEL_SPEC)
    kind = spec.get("kind", "enumerative_search")
    if kind == "enumerative_search":
        return enumerative_identity(SYNTHESIZER_VERSION)
    if kind == "fixed_weights_llm":
        return ModelIdentity.from_record(spec["identity"])
    raise ValueError(f"unknown model kind {kind!r}")


def spec_requires_network(spec: Mapping[str, Any] | None) -> bool:
    """True when the spec's backend must reach a network endpoint.

    The candidate sandbox denies network access, so such a model cannot be called from inside a
    condition job. The runner proposes outside the boundary, records a transcript, and replays
    it inside (`Exp001Runner`); this predicate is how it knows to.
    """
    spec = dict(spec or DEFAULT_MODEL_SPEC)
    backend = spec.get("backend") or {}
    return spec.get("kind") == "fixed_weights_llm" and backend.get("kind") == "http"
