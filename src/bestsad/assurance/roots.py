"""Content-addressed assumption roots (integration spec §1.6, §4).

K0, the reference interpreter, BSIR canonicalization, the evaluator, the hidden benchmark
manifest, the MDL coding scheme and `kappa`, and the pre-registration are the foundations
everything else rests on. Each is identified by a content id, so a change to any of them
*automatically* stales every descendant certificate — nobody has to notice and act.

This is the Atlas failure mode the integration spec names directly: regenerated outputs from
rejected foundational semantics could otherwise still look promotable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .objects import AssumptionObject, content_id

#: Root identifiers. These names appear in dependency edges, so they are part of the contract.
K0_ROOT = "root:k0_semantic_kernel"
BSIR_ROOT = "root:bsir_canonicalization"
EVALUATOR_ROOT = "root:evaluator_integrity"
BENCHMARK_ROOT = "root:hidden_benchmark_manifest"
CODING_SCHEME_ROOT = "root:mdl_coding_scheme"
PREREGISTRATION_ROOT = "root:preregistration"
SANDBOX_POLICY_ROOT = "root:sandbox_policy"

ALL_ROOTS: tuple[str, ...] = (
    K0_ROOT, BSIR_ROOT, EVALUATOR_ROOT, BENCHMARK_ROOT,
    CODING_SCHEME_ROOT, PREREGISTRATION_ROOT, SANDBOX_POLICY_ROOT,
)


def bsir_canonicalization_content_id() -> str:
    """Content id of the canonicalization *rules*, not of any particular graph.

    Derived from the rules themselves so that changing what canonicalization does — adding a
    normalization, or the commutative-operand reordering the canonicalizer deliberately does not
    do — moves the id and stales every semantic-equivalence certificate beneath it.
    """
    from ..bsir.canonicalize import CANONICAL_BOUND, CANONICAL_PARAM

    return content_id(
        {
            "canonical_param_prefix": CANONICAL_PARAM,
            "canonical_bound_prefix": CANONICAL_BOUND,
            "expands_primitives": True,
            "alpha_normalizes": True,
            "reorders_commutative_operands": False,
            "hash": "sha256-over-canonical-serialization",
        },
        "bsir",
    )


def sandbox_policy_content_id() -> str:
    from ..evaluator.sandbox import IMPORT_EVENTS, NETWORK_EVENTS, PROCESS_EVENTS

    return content_id(
        {
            "network_denied": sorted(NETWORK_EVENTS),
            "process_denied": sorted(PROCESS_EVENTS),
            "native_load_denied": sorted(IMPORT_EVENTS),
            "hidden_assets_readable": False,
            "writes_outside_scratch": False,
        },
        "sandbox",
    )


@dataclass(frozen=True, slots=True)
class SemanticRoots:
    """The active content id for every root, and the assumptions built from them."""

    values: Mapping[str, str]

    def assumptions(self) -> dict[str, AssumptionObject]:
        descriptions = {
            K0_ROOT: "K0 semantic kernel and reference interpreter (spec §8)",
            BSIR_ROOT: "BSIR canonicalization rules and semantic hash (spec §9.4)",
            EVALUATOR_ROOT: "evaluator integrity plane and scoring contract (spec §20)",
            BENCHMARK_ROOT: "frozen hidden benchmark manifest (spec §20.1 A)",
            CODING_SCHEME_ROOT: "MDL coding scheme and kappa (spec §21.4)",
            PREREGISTRATION_ROOT: "committed pre-registration (spec §26.5)",
            SANDBOX_POLICY_ROOT: "candidate sandbox policy (spec §27.1)",
        }
        return {
            root: AssumptionObject(
                assumption_id=root,
                content_id=value,
                scope="global",
                description=descriptions.get(root, ""),
            )
            for root, value in self.values.items()
        }

    def get(self, root: str) -> str:
        return self.values[root]

    def diff(self, other: "SemanticRoots") -> list[str]:
        """Roots whose content id has moved — exactly the set whose descendants go stale."""
        return sorted(
            root for root in set(self.values) | set(other.values)
            if self.values.get(root) != other.values.get(root)
        )


def current_roots(
    *,
    preregistration_hash: str | None = None,
    benchmark_manifest_id: str | None = None,
    evaluator_image_digest: str = "not-containerised-see-ADR-0005",
) -> SemanticRoots:
    """Read the live content id of every root from the running system.

    Deliberately *computed*, never stored: a stored root id can drift from the code it claims to
    describe, and a root that lies is worse than no root at all.
    """
    from ..evaluator.contract import SCORING_CONTRACT_VERSION
    from ..kernel.spec import KERNEL_VERSION, kernel_version_hash
    from ..mdl import CodingScheme
    from ..tasks.generator import GENERATOR_VERSION

    values = {
        K0_ROOT: content_id(
            {"kernel_version": KERNEL_VERSION, "kernel_hash": kernel_version_hash()}, "k0"
        ),
        BSIR_ROOT: bsir_canonicalization_content_id(),
        EVALUATOR_ROOT: content_id(
            {
                "scoring_contract": SCORING_CONTRACT_VERSION,
                "generator_version": GENERATOR_VERSION,
                "image_digest": evaluator_image_digest,
            },
            "eval",
        ),
        BENCHMARK_ROOT: benchmark_manifest_id or "bm:unset",
        CODING_SCHEME_ROOT: content_id(CodingScheme().to_record(), "mdl"),
        SANDBOX_POLICY_ROOT: sandbox_policy_content_id(),
    }
    if preregistration_hash:
        values[PREREGISTRATION_ROOT] = f"prereg:{preregistration_hash[:32]}"
    return SemanticRoots(values)
