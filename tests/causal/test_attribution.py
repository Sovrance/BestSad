"""M8 acceptance: the causal attribution plane (spec §42)."""

from __future__ import annotations

import pytest

from bestsad.bsir import semantic_hash
from bestsad.causal import (
    PrimitiveEffect,
    ablate,
    concentration_test,
    expand_all,
    paired_ablation,
)
from bestsad.genomes import Primitive
from bestsad.kernel import INT, Kernel, Program, Term, app, const_int, var
from bestsad.stats import Interval


def _double() -> Primitive:
    return Primitive(
        primitive_id="prim:double",
        params=("a",),
        expansion=app("mul", var("a"), const_int(2)),
        input_types=(INT,),
        output_type=INT,
    )


def test_ablation_re_expands_call_sites_correctly():
    """M8 acceptance 1: verified by semantic-hash equality. An ablation that changed the
    program's meaning would make every direct effect meaningless."""
    primitive = _double()
    kernel = Kernel({primitive.primitive_id: (primitive.params, primitive.expansion)})

    with_prim = Program((("x", INT),), Term("prim:double", (var("x"),)), INT)
    ablated = ablate(with_prim, "prim:double", kernel)
    expected = Program((("x", INT),), app("mul", var("x"), const_int(2)), INT)

    assert semantic_hash(ablated) == semantic_hash(expected)
    assert "prim:double" not in {t.op for t in ablated.body.walk()}
    # And the semantic hash is unchanged from the original, since a primitive *is* its expansion.
    assert semantic_hash(ablated, kernel) == semantic_hash(with_prim, kernel)


def test_ablation_handles_nested_and_repeated_call_sites():
    primitive = _double()
    kernel = Kernel({primitive.primitive_id: (primitive.params, primitive.expansion)})
    body = app(
        "add",
        Term("prim:double", (var("x"),)),
        Term("prim:double", (Term("prim:double", (var("x"),)),)),
    )
    ablated = ablate(Program((("x", INT),), body, INT), "prim:double", kernel)
    assert not any(t.op.startswith("prim:") for t in ablated.body.walk())

    k = Kernel()
    for value in (0, 3, -7):
        original = kernel.execute(Program((("x", INT),), body, INT), [value])
        assert original.same_outcome(k.execute(ablated, [value]))


def test_expand_all_forces_every_call_site():
    primitive = _double()
    kernel = Kernel({primitive.primitive_id: (primitive.params, primitive.expansion)})
    program = Program((("x", INT),), Term("prim:double", (var("x"),)), INT)
    forced = expand_all(program, kernel)
    assert not any(t.op.startswith("prim:") for t in forced.body.walk())


# --- concentration test ---------------------------------------------------------------------


def _effect(pid: str, estimate: float, *, shortcut=False, compression=False, reuse=3):
    return PrimitiveEffect(
        primitive_id=pid,
        semantic_hash=pid,
        direct_effect=Interval(estimate, estimate - 0.01, estimate + 0.01),
        indirect_effect=Interval(0.0, -0.01, 0.01),
        cross_family_reuse=reuse,
        shortcut_shaped=shortcut,
        compression_shaped=compression,
        semantic_gain_v2=1.0,
    )


def test_concentration_stop_rule_fires_on_a_deliberately_concentrated_shortcut():
    """M8 acceptance 2: testable on synthetic data where the gain is deliberately concentrated
    in one shortcut primitive."""
    effects = [
        _effect("prim:shortcut", 0.90, shortcut=True, reuse=1),
        _effect("prim:a", 0.05),
        _effect("prim:b", 0.05),
    ]
    result = concentration_test(effects, threshold=0.80)
    assert not result.passed
    assert result.verdict == "h0_consistent_concentrated_shortcut"
    assert result.top1_share == pytest.approx(0.90)


def test_concentration_in_a_general_primitive_is_not_disqualifying():
    """Concentration alone is not the failure mode: one genuinely general abstraction carrying
    the result is a fine outcome. It is concentration *in a shortcut* that the rule targets."""
    effects = [
        _effect("prim:general", 0.90, shortcut=False, compression=False, reuse=4),
        _effect("prim:a", 0.05),
        _effect("prim:b", 0.05),
    ]
    result = concentration_test(effects, threshold=0.80)
    assert result.passed and result.verdict == "attributable"


def test_distributed_gain_passes():
    effects = [_effect(f"prim:{i}", 0.25) for i in range(4)]
    result = concentration_test(effects, threshold=0.80)
    assert result.passed
    assert result.top1_share == pytest.approx(0.25)


def test_concentration_test_handles_no_positive_gain():
    effects = [_effect("prim:a", -0.1), _effect("prim:b", 0.0)]
    result = concentration_test(effects)
    assert result.passed and "no positive" in result.rationale


def test_compression_shaped_carrier_also_trips_the_rule():
    effects = [
        _effect("prim:squeeze", 0.95, compression=True, reuse=1),
        _effect("prim:a", 0.05),
    ]
    assert not concentration_test(effects).passed


# --- reporting completeness --------------------------------------------------------------------


def test_attribution_table_reports_null_and_negative_primitives():
    """Spec §42.3: selective reporting of the primitives that worked is a protocol violation."""
    from bestsad.causal import AttributionTable

    table = AttributionTable("EXP-TEST")
    table.effects = [
        _effect("prim:good", 0.30),
        _effect("prim:null", 0.0),
        _effect("prim:bad", -0.12),
    ]
    record = table.to_record()
    reported = {e["primitive_id"] for e in record["primitive_effects"]}
    assert reported == {"prim:good", "prim:null", "prim:bad"}
    assert table.summary_counts() == {"total": 3, "positive": 1, "negative": 1, "null": 1}


def test_paired_ablation_detects_a_superadditive_interaction():
    """Removing both costs more than removing each alone: the two do something together."""
    result = paired_ablation(
        "prim:a",
        "prim:b",
        neither_removed=[0.50, 0.52, 0.51, 0.49],
        a_removed=[0.48, 0.50, 0.49, 0.47],
        b_removed=[0.48, 0.50, 0.49, 0.47],
        both_removed=[0.20, 0.22, 0.21, 0.19],
    )
    assert result["effect_both"] > result["effect_a"] + result["effect_b"]
    assert result["interaction"] > 0
