"""Abstraction discovery and the primitive lifecycle (spec §11, §23 E2/E3)."""

from .extract import (
    Candidate,
    Corpus,
    anti_unify,
    mine_candidates,
    random_matched_primitives,
    score_utility,
    select,
    to_primitives,
)
from .lifecycle import (
    LifecycleLedger,
    PromotionEvidence,
    PromotionRefused,
    promote,
    request_core_promotion,
)

__all__ = [
    "Candidate",
    "Corpus",
    "LifecycleLedger",
    "PromotionEvidence",
    "PromotionRefused",
    "anti_unify",
    "mine_candidates",
    "promote",
    "random_matched_primitives",
    "request_core_promotion",
    "score_utility",
    "select",
    "to_primitives",
]
