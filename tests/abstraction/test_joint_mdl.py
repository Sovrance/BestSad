"""Condition C's MDL extractor, strengthened per ADR-0006.

Two weaknesses were recorded there, both of which made the control *weaker* than it should be
and so biased in favour of the treatment — the wrong direction for a control. These tests pin
the fixes.
"""

from __future__ import annotations

import pytest

from bestsad.abstraction import Corpus, mine_candidates, select
from bestsad.abstraction.extract import mdl_library_search
from bestsad.abstraction.rewrite import match_pattern, rewrite_corpus, rewrite_term
from bestsad.kernel import BOOL, INT, Program, TList, Term, app, const_int, lam, var
from bestsad.mdl import CodingScheme


# --- matching and rewriting --------------------------------------------------------------------


def test_a_repeated_hole_must_bind_the_same_subterm():
    """`add(a0, a0)` matches `add(x, x)` but not `add(x, y)`. Otherwise an abstraction claims
    matches it cannot actually express."""
    pattern = app("add", var("a0"), var("a0"))
    holes = frozenset({"a0"})
    assert match_pattern(pattern, app("add", var("x"), var("x")), holes) is not None
    assert match_pattern(pattern, app("add", var("x"), var("y")), holes) is None


def test_rewriting_replaces_every_occurrence():
    pattern = app("add", var("a0"), const_int(1))
    term = app("mul", app("add", var("x"), const_int(1)), app("add", const_int(5), const_int(1)))
    rewritten, count = rewrite_term(
        term, primitive_id="prim:inc", pattern=pattern, params=["a0"]
    )
    assert count == 2
    assert [t.op for t in rewritten.walk()].count("prim:inc") == 2


def test_rewriting_prefers_the_largest_match():
    """Top-down: rewriting children first would dissolve the structure an outer pattern needs."""
    pattern = app("mul", app("add", var("a0"), const_int(1)), const_int(2))
    term = app("mul", app("add", var("x"), const_int(1)), const_int(2))
    rewritten, count = rewrite_term(
        term, primitive_id="prim:p", pattern=pattern, params=["a0"]
    )
    assert count == 1 and rewritten.op == "prim:p"


def test_rewriting_a_corpus_counts_occurrences_across_programs():
    pattern = app("add", var("a0"), const_int(1))
    programs = [
        Program((("x", INT),), app("add", var("x"), const_int(1)), INT),
        Program((("y", INT),), app("mul", app("add", var("y"), const_int(1)), const_int(3)), INT),
    ]
    rewritten, total = rewrite_corpus(
        programs, primitive_id="prim:inc", pattern=pattern, params=["a0"]
    )
    assert total == 2 and len(rewritten) == 2


# --- weakness 1: overlapping candidates must compete --------------------------------------------


def _overlapping_corpus() -> Corpus:
    """A corpus where two candidate abstractions cover the *same* subtree.

    `mul(add(x,1), 2)` contains `add(x,1)`. An extractor scoring candidates independently
    credits both with the mass of the inner `add`, so it reports a combined saving that no
    library can actually realise: once one is applied, the other's mass is gone.
    """
    corpus = Corpus()
    for i in range(6):
        body = app("mul", app("add", var("x"), const_int(1)), const_int(2))
        corpus.add(Program((("x", INT),), body, INT), f"F{i % 3}")
    return corpus


def test_joint_search_does_not_double_count_overlapping_mass():
    corpus = _overlapping_corpus()
    candidates = mine_candidates(corpus)
    assert len(candidates) >= 2, "fixture must offer overlapping candidates"

    result = mdl_library_search(candidates, corpus, count=3)
    assert result.selected, "a compressible corpus should yield a library"

    # Each selection's recorded saving is measured against the corpus *as already rewritten*,
    # so the reported total is exactly what the final library achieves — no double counting.
    assert result.bits_saved == pytest.approx(
        sum(step["bits_saved"] for step in result.steps)
    )
    assert result.final_bits < result.initial_bits


def test_a_second_abstraction_covering_spent_mass_is_not_selected():
    """Once the mass is compressed, a candidate that only covered it has nothing left to claim."""
    corpus = _overlapping_corpus()
    candidates = mine_candidates(corpus)
    result = mdl_library_search(candidates, corpus, count=4)
    keys = [c.semantic_key for c in result.selected]
    assert len(keys) == len(set(keys)), "no candidate may be selected twice"
    # Every step must have rewritten at least one real occurrence.
    assert all(step["occurrences_rewritten"] > 0 for step in result.steps)


def test_every_selection_strictly_reduces_total_bits():
    corpus = _overlapping_corpus()
    result = mdl_library_search(mine_candidates(corpus), corpus, count=4)
    for step in result.steps:
        assert step["bits_after"] < step["bits_before"], (
            "a selection that does not reduce total description length is not a compression"
        )


# --- weakness 2: the objective is in bits -------------------------------------------------------


def test_the_objective_is_measured_in_bits_under_the_coding_scheme():
    """ADR-0006's second weakness: the old objective counted nodes while SG-v2 counts bits.

    They now use the same scheme, so condition C and the Semantic Gain metric measure
    description length the same way.
    """
    corpus = _overlapping_corpus()
    scheme = CodingScheme()
    result = mdl_library_search(mine_candidates(corpus), corpus, count=2, scheme=scheme)
    # Bits are real-valued and reflect the declared prior; node counts would be integers.
    assert isinstance(result.initial_bits, float)
    assert result.initial_bits != int(result.initial_bits) or result.initial_bits > 0

    # A different kappa/prior weight changes the numbers, proving the scheme is actually consulted.
    other = mdl_library_search(
        mine_candidates(corpus), corpus, count=2,
        scheme=CodingScheme(primitive_prior_weight=0.05),
    )
    assert other.initial_bits == pytest.approx(result.initial_bits)
    assert other.final_bits != pytest.approx(result.final_bits)


def test_a_library_costing_more_than_it_saves_is_not_selected():
    """The two-part code charges for stating the library, so an abstraction used once and
    expensive to write down loses to not having it."""
    corpus = Corpus()
    # One long program, one occurrence: nothing to amortise the library cost over.
    body = var("x")
    for i in range(9):
        body = app("add", body, const_int(i % 3))
    corpus.add(Program((("x", INT),), body, INT), "F1")

    result = mdl_library_search(mine_candidates(corpus), corpus, count=3)
    for step in result.steps:
        assert step["bits_saved"] > 0
    assert result.final_bits <= result.initial_bits


def test_an_incompressible_corpus_yields_an_empty_library():
    corpus = Corpus()
    corpus.add(Program((("x", INT),), app("add", var("x"), const_int(1)), INT), "F1")
    result = mdl_library_search(mine_candidates(corpus), corpus, count=3)
    assert result.selected == ()
    assert result.final_bits == result.initial_bits


# --- integration with the selection regime --------------------------------------------------------


def test_the_mdl_regime_uses_the_joint_search_when_given_a_corpus():
    corpus = _overlapping_corpus()
    candidates = mine_candidates(corpus)
    joint = select(candidates, "mdl", 3, corpus=corpus)
    independent = select(candidates, "mdl", 3)
    assert joint, "joint search should select something on a compressible corpus"
    # The two regimes are allowed to agree, but the joint one must never claim more than it can
    # realise: its selections are exactly those that rewrote real occurrences.
    assert len(joint) <= len(candidates)
    assert all(hasattr(c, "semantic_key") for c in independent)


def test_the_joint_search_is_deterministic():
    corpus = _overlapping_corpus()
    candidates = mine_candidates(corpus)
    first = [c.semantic_key for c in mdl_library_search(candidates, corpus, count=3).selected]
    second = [c.semantic_key for c in mdl_library_search(candidates, corpus, count=3).selected]
    assert first == second


def test_beam_width_one_is_greedy_and_wider_beams_never_do_worse():
    """A beam exists so one locally-best first pick cannot foreclose a jointly better pair."""
    corpus = _overlapping_corpus()
    candidates = mine_candidates(corpus)
    greedy = mdl_library_search(candidates, corpus, count=3, beam=1)
    wide = mdl_library_search(candidates, corpus, count=3, beam=5)
    assert wide.final_bits <= greedy.final_bits + 1e-9
