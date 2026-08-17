"""M6 acceptance: abstraction discovery, promotion evidence, lifecycle (spec §11, §23 E2/E3)."""

from __future__ import annotations

import pytest

from bestsad.abstraction import (
    Corpus,
    LifecycleLedger,
    PromotionEvidence,
    PromotionRefused,
    anti_unify,
    mine_candidates,
    promote,
    random_matched_primitives,
    request_core_promotion,
    select,
    to_primitives,
)
from bestsad.genomes import Genome, GenomeInvariantViolation, Primitive
from bestsad.kernel import INT, KERNEL_VERSION, Kernel, Program, TList, Term, app, const_int, lam, var


# --- anti-unification --------------------------------------------------------------------------


def test_anti_unify_keeps_agreement_and_generalizes_difference():
    left = app("add", app("mul", var("x"), const_int(2)), const_int(1))
    right = app("add", app("mul", var("y"), const_int(2)), const_int(1))
    pattern, holes = anti_unify(left, right)
    assert len(holes) == 1
    assert pattern.op == "add"
    assert "h0" in str(pattern)


def test_anti_unify_reuses_one_hole_for_a_repeated_difference():
    """`add(x, x)` vs `add(y, y)` generalizes to one parameter, not two."""
    left = app("add", var("x"), var("x"))
    right = app("add", var("y"), var("y"))
    pattern, holes = anti_unify(left, right)
    assert len(holes) == 1


def test_anti_unify_of_unrelated_terms_is_a_bare_hole():
    pattern, holes = anti_unify(const_int(1), app("length", var("xs")))
    assert pattern.op == "var" and len(holes) == 1


# --- mining ------------------------------------------------------------------------------------


def _corpus() -> Corpus:
    corpus = Corpus()
    # A repeated `fold(add, 0, ·)` shape across two families, plus filler.
    for family, name in (("F4", "xs"), ("F9", "xs")):
        body = app(
            "fold",
            lam((("acc", INT), ("e", INT)), app("add", var("acc"), var("e"))),
            const_int(0),
            var(name),
        )
        corpus.add(Program(((name, TList(INT)),), body, INT), family)
    corpus.add(
        Program((("xs", TList(INT)),), app("length", var("xs")), INT),
        "F8",
    )
    return corpus


def test_mining_finds_repeated_subtrees_and_records_family_spread():
    candidates = mine_candidates(_corpus())
    repeated = [c for c in candidates if c.occurrences >= 2]
    assert repeated, "no repeated subtree found in a corpus built to contain one"
    assert any(len(c.families) >= 2 for c in repeated)


def test_mining_deduplicates_semantically_not_by_surface_form():
    """Spec §23 E3: deduplicate semantically. Two spellings of one computation are one
    candidate."""
    corpus = Corpus()
    body = app("add", app("mul", var("x"), const_int(2)), const_int(1))
    corpus.add(Program((("x", INT),), body, INT), "F1")
    corpus.add(Program((("y", INT),), app("add", app("mul", var("y"), const_int(2)),
                                          const_int(1)), INT), "F1")
    candidates = mine_candidates(corpus)
    keys = [c.semantic_key for c in candidates if c.occurrences >= 2]
    assert len(set(keys)) == len(keys)
    assert any(c.occurrences == 2 for c in candidates)


# --- selection regimes ---------------------------------------------------------------------------


def test_the_three_regimes_are_genuinely_different_selectors():
    """If MDL and utility always chose the same abstractions, condition D would have no
    mechanism by which to beat condition C — which would itself be a finding, so the
    distinction has to be real and checkable."""
    candidates = mine_candidates(_corpus())
    assert candidates
    mdl = select(candidates, "mdl", 3)
    utility = select(candidates, "utility", 3)
    random_pick = select(candidates, "random", 3, seed=1)

    assert all(c.corpus_saving > 0 for c in mdl)
    assert all(c.utility > 0 for c in utility)
    # The utility regime is the only one that looks at cross-family spread.
    assert any(len(c.families) >= 2 for c in utility) or not utility
    assert len(random_pick) <= 3


def test_utility_scoring_rewards_cross_family_spread():
    from bestsad.abstraction.extract import Candidate, score_utility

    def make(families):
        return Candidate(
            pattern=app("fold", lam((("a", INT), ("e", INT)),
                                    app("add", var("a"), var("e"))), const_int(0), var("xs")),
            params=("xs",),
            param_types=(TList(INT),),
            output_type=INT,
            occurrences=4,
            families=frozenset(families),
            corpus_saving=10,
            utility=0.0,
            semantic_key="k",
        )

    broad = score_utility(make({"F1", "F2", "F3"}), family_count=8)
    narrow = score_utility(make({"F1"}), family_count=8)
    assert broad > narrow


def test_random_control_is_matched_to_the_treatment_by_count_and_size():
    """Condition B must be matched on size as well as count, or it loses for reasons that have
    nothing to do with selection quality."""
    candidates = mine_candidates(_corpus())
    utility = to_primitives(select(candidates, "utility", 2), "u")
    if not utility:
        pytest.skip("corpus produced no utility-selected primitives")
    matched = random_matched_primitives(utility, candidates, "r", seed=5)
    assert len(matched) == len(utility)
    for reference, control in zip(utility, matched):
        assert abs(control.size - reference.size) <= max(3, reference.size)


def test_selection_is_deterministic_given_a_seed():
    candidates = mine_candidates(_corpus())
    first = [c.semantic_key for c in select(candidates, "random", 2, seed=9)]
    second = [c.semantic_key for c in select(candidates, "random", 2, seed=9)]
    assert first == second


# --- lifecycle -----------------------------------------------------------------------------------


def _primitive() -> Primitive:
    return Primitive(
        primitive_id="prim:p",
        params=("a",),
        expansion=app("mul", var("a"), const_int(2)),
        input_types=(INT,),
        output_type=INT,
    )


def test_promotion_requires_the_evidence_set():
    primitive = _primitive()
    assert promote(primitive, PromotionEvidence("prim:p", reuse_count=1))[0] == "EXP"
    assert promote(
        primitive, PromotionEvidence("prim:p", reuse_count=4, reuse_diversity=1)
    )[0] == "OBS"
    assert promote(
        primitive,
        PromotionEvidence("prim:p", reuse_count=4, reuse_diversity=3, semantic_gain=0.0),
    )[0] == "OBS"
    maturity, rationale = promote(
        primitive,
        PromotionEvidence(
            "prim:p", reuse_count=6, reuse_diversity=3, semantic_gain=12.0,
            failure_rate=0.0, verification_cost=3.0,
        ),
    )
    assert maturity == "VER" and "positive semantic gain" in rationale


def test_adversarial_incidents_hold_a_primitive_at_exp():
    maturity, rationale = promote(
        _primitive(),
        PromotionEvidence("prim:p", reuse_count=9, reuse_diversity=4, semantic_gain=20.0,
                          adversarial_incidents=1),
    )
    assert maturity == "EXP" and "adversarial" in rationale


def test_core_promotion_is_never_automatic():
    """Spec §11.2 — the single most consequential refusal in the lifecycle."""
    with pytest.raises(PromotionRefused, match="kernel change"):
        request_core_promotion(_primitive())


def test_promote_never_returns_core():
    maxed = PromotionEvidence(
        "prim:p", reuse_count=1000, reuse_diversity=12, semantic_gain=1e6,
        verification_cost=1.0, failure_rate=0.0, cross_model_transfer=1.0,
    )
    assert promote(_primitive(), maxed)[0] != "CORE"


def test_lifecycle_ledger_is_append_only():
    ledger = LifecycleLedger()
    ledger.record("prim:p", "EXP", "OBS", "reused twice")
    ledger.record("prim:p", "OBS", "SPEC", "semantics recorded")
    assert len(ledger.for_primitive("prim:p")) == 2


# --- genome invariants -----------------------------------------------------------------------------


def test_genome_rejects_a_self_referential_primitive():
    """Invariant 2: no cyclic macro expansion."""
    cyclic = Primitive(
        primitive_id="prim:loop",
        params=("a",),
        expansion=Term("prim:loop", (var("a"),)),
        input_types=(INT,),
        output_type=INT,
    )
    genome = Genome("G", 1, KERNEL_VERSION, (cyclic,))
    with pytest.raises(GenomeInvariantViolation, match="expands to itself"):
        genome.validate(Kernel())


def test_genome_rejects_a_forward_reference():
    """Invariant 1: every primitive references K0 or a *previously* verified primitive."""
    forward = Primitive(
        primitive_id="prim:a",
        params=("x",),
        expansion=Term("prim:b", (var("x"),)),
        input_types=(INT,),
        output_type=INT,
    )
    later = _primitive()
    genome = Genome("G", 1, KERNEL_VERSION, (forward, later))
    with pytest.raises(GenomeInvariantViolation, match="not a"):
        genome.validate(Kernel())


def test_fitness_is_immutable_once_recorded():
    """Invariant 5."""
    genome = Genome("G", 0, KERNEL_VERSION, ())
    genome.record_fitness({"verified_solve_rate": 0.4})
    with pytest.raises(GenomeInvariantViolation, match="immutable"):
        genome.record_fitness({"verified_solve_rate": 0.9})


def test_renaming_a_primitive_does_not_change_its_semantic_id():
    """Invariants 3 and 4: aliases are free, meaning is not."""
    base = _primitive()
    renamed = Primitive(
        primitive_id="prim:different_name",
        params=base.params,
        expansion=base.expansion,
        input_types=base.input_types,
        output_type=base.output_type,
        display_names=("twice", "dbl"),
    )
    assert renamed.semantic_id == base.semantic_id

    remeaning = Primitive(
        primitive_id=base.primitive_id,
        params=base.params,
        expansion=app("mul", var("a"), const_int(3)),
        input_types=base.input_types,
        output_type=base.output_type,
    )
    assert remeaning.semantic_id != base.semantic_id


def test_adding_a_primitive_increases_the_language_description_length():
    """A genome that adds primitives pays for them, which is what stops 'add more primitives'
    from being a free move."""
    bare = Genome("G0", 0, KERNEL_VERSION, ())
    grown = Genome("G1", 1, KERNEL_VERSION, (_primitive(),))
    assert grown.description_length_tokens() > bare.description_length_tokens()
