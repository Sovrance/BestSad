"""M7 acceptance: MDL Semantic Gain (SG-v2), spec §21.4."""

from __future__ import annotations

import pytest

from bestsad.kernel import INT, Program, app, const_int, var
from bestsad.mdl import CodingScheme, PairedOutcome, compression_ratio, semantic_gain_v2

BASE_VOCAB = ["add", "mul", "sub", "const_int", "var", "fold", "map", "filter"]
WITH_PRIM = BASE_VOCAB + ["prim:p0"]


def _long(n: int) -> Program:
    """A program of roughly `n` addition nodes."""
    body = var("x")
    for i in range(n):
        body = app("add", body, const_int(i))
    return Program((("x", INT),), body, INT)


def _short() -> Program:
    from bestsad.kernel import Term

    return Program((("x", INT),), Term("prim:p0", (var("x"),)), INT)


def test_a_primitive_that_only_compresses_training_scores_at_most_zero():
    """M7 acceptance 1. This is H13 made executable: shortening the corpus the search already
    saw is not capability, and `kappa` subtracts that saving back out."""
    expansion = _long(6).body
    result = semantic_gain_v2(
        "prim:p0",
        # No change on held-out solutions...
        ood_with=[_long(6)],
        ood_without=[_long(6)],
        # ...but a large saving on the training corpus.
        train_with=[_short(), _short()],
        train_without=[_long(6), _long(6)],
        vocabulary_with=WITH_PRIM,
        vocabulary_without=BASE_VOCAB,
        primitive_expansion=expansion,
    )
    assert result.train_saving > 0, "fixture is wrong: no training saving to discount"
    assert result.semantic_gain <= 0


def test_a_primitive_that_shortens_held_out_solutions_scores_positive():
    """M7 acceptance 2: it must shorten held-out descriptions by more than it costs to state."""
    expansion = _long(8).body
    result = semantic_gain_v2(
        "prim:p0",
        ood_with=[_short(), _short(), _short(), _short()],
        ood_without=[_long(8), _long(8), _long(8), _long(8)],
        train_with=[_long(8)],
        train_without=[_long(8)],
        vocabulary_with=WITH_PRIM,
        vocabulary_without=BASE_VOCAB,
        primitive_expansion=expansion,
    )
    assert result.ood_saving > 0
    assert result.semantic_gain > 0


def test_a_primitive_costing_more_than_it_saves_scores_negative():
    """One held-out use of a large abstraction does not pay for stating it."""
    expansion = _long(14).body
    result = semantic_gain_v2(
        "prim:p0",
        ood_with=[_short()],
        ood_without=[_long(14)],
        train_with=[_long(3)],
        train_without=[_long(3)],
        vocabulary_with=WITH_PRIM,
        vocabulary_without=BASE_VOCAB,
        primitive_expansion=expansion,
    )
    assert result.primitive_cost > result.ood_saving
    assert result.semantic_gain < 0


def test_coding_scheme_is_hashable_and_stable():
    """Spec §21.4: the coding scheme and kappa must be committed before EXP-001 and hashed
    into the run manifest."""
    a, b = CodingScheme(), CodingScheme()
    assert a.content_hash() == b.content_hash()
    assert CodingScheme(kappa=0.5).content_hash() != a.content_hash()
    assert a.to_record()["kappa"] == 1.0


def test_growing_the_vocabulary_is_not_free_under_the_code():
    """A primitive receives less prior mass than a kernel operation, so adding one lengthens
    every program that does not use it. Without this, MDL degenerates into 'add every macro'."""
    scheme = CodingScheme()
    program = _long(5)
    short_vocab = scheme.program_length(program, BASE_VOCAB)
    long_vocab = scheme.program_length(program, WITH_PRIM)
    assert long_vocab > short_vocab


def test_compression_ratio_direction():
    """Ratio > 1 means the condition used fewer tokens than the baseline."""
    assert compression_ratio(1000, 500) == 2.0
    assert compression_ratio(500, 1000) == 0.5


def test_paired_outcome_classifies_efficiency_only_results():
    """Spec §21.6: compression up, capability inside the margin, is an efficiency result."""
    efficiency = PairedOutcome(compression_ratio=1.9, capability_delta=0.005,
                               non_inferiority_margin=0.02)
    assert efficiency.is_efficiency_only
    assert efficiency.to_record()["classification"] == "efficiency_only"

    capability = PairedOutcome(compression_ratio=1.9, capability_delta=0.09,
                               non_inferiority_margin=0.02)
    assert not capability.is_efficiency_only
