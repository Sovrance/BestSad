"""M9 acceptance: the reporting pipeline refuses claims the evidence does not support.

These are the executable form of `AGENTS.md` invariants 3, 4 and 5. Each test asserts a
*refusal* — the control working — rather than a warning being logged somewhere.
"""

from __future__ import annotations

import pytest

from bestsad.stats import (
    ClaimRequest,
    Preregistration,
    PreregistrationError,
    ReportGate,
    ReportRefused,
)


def _prereg(**overrides) -> Preregistration:
    base = dict(
        experiment_id="EXP-TEST",
        primary_endpoint="verified_ood_solve_rate_per_compute",
        conditions=tuple(
            {
                "condition_id": cid,
                "role": "treatment" if cid in ("D", "E") else "confound_control"
                if cid in ("F", "H", "I") else "reference",
                "genome_id": f"G-{cid}",
                "description": f"condition {cid}",
            }
            for cid in "ABCDEFGHI"
        ),
        seeds_per_condition=8,
        minimum_interesting_effect={"absolute_solve_rate_points": 0.05},
        multiple_comparison_control={
            "method": "benjamini_hochberg",
            "level": 0.05,
            "family": ["raw_solve_rate", "generation_tokens"],
        },
        stopping_rule="fixed: 8 seeds per condition, no interim analysis",
        declared_outcome_interpretations={
            "positive": "proceed to S4",
            "efficiency_only": "report as efficiency",
            "null_result": "record in the negative-result ledger",
            "h0_consistent": "record as consistent with H0",
        },
        power_analysis={"powered": True, "target_power": 0.8},
    )
    base.update(overrides)
    return Preregistration(**base).commit()


def _request(**overrides) -> ClaimRequest:
    base = dict(
        experiment_id="EXP-TEST",
        claim_kind="capability",
        conditions_run=("A", "D", "E", "F", "H", "I"),
        treatment_beats={"F": True, "H": True, "I": True},
        compression_ratio=1.8,
        capability_delta=0.07,
        fdr_controlled=True,
        concentration_test_passed=True,
        powered=True,
    )
    base.update(overrides)
    return ClaimRequest(**base)


# --- invariant 5: no confirmatory claim without a pre-registration ----------------------------


def test_refuses_a_confirmatory_claim_without_a_preregistration():
    with pytest.raises(ReportRefused, match="no pre-registration"):
        ReportGate(None).certify(_request())


def test_refuses_when_the_preregistration_is_incomplete():
    incomplete = _prereg(stopping_rule="<<FILL>>")
    with pytest.raises(ReportRefused, match="incomplete"):
        ReportGate(incomplete).certify(_request())


def test_detects_a_preregistration_edited_after_commit():
    """The hash is what makes 'committed before the first run' checkable."""
    prereg = _prereg()
    prereg.verify()
    prereg.primary_endpoint = "something_more_favourable"
    with pytest.raises(PreregistrationError, match="edited after being committed"):
        prereg.verify()


def test_amendments_are_appended_not_edited():
    prereg = _prereg()
    original_hash = prereg.preregistration_hash
    prereg.amend("added a secondary endpoint", "reviewer request", post_data=False)
    assert len(prereg.amendments) == 1
    # The body changed, so the stored hash no longer matches — which is the point: an amended
    # document is a new document, and the amendment trail says so.
    assert prereg.compute_hash() != original_hash


def test_exploratory_claims_need_no_preregistration_but_are_labelled_level_e():
    result = ReportGate(None).certify(_request(claim_kind="exploratory"))
    assert result["certified"] and result["claim_level"] == "E"
    assert "no confirmatory language" in result["notes"][0]


# --- invariant 3: no capability claim without F, H, I -----------------------------------------


@pytest.mark.parametrize("missing", ["F", "H", "I"])
def test_refuses_a_capability_claim_when_a_required_control_was_not_run(missing):
    conditions = tuple(c for c in ("A", "D", "E", "F", "H", "I") if c != missing)
    with pytest.raises(ReportRefused, match=f"missing {missing}"):
        ReportGate(_prereg()).certify(_request(conditions_run=conditions))


@pytest.mark.parametrize("unbeaten", ["F", "H", "I"])
def test_refuses_a_capability_claim_when_a_control_matches_the_treatment(unbeaten):
    """A control defeating a treatment is a finding, not a bug — and it blocks the claim
    regardless of how the treatment compared against A."""
    beats = {"F": True, "H": True, "I": True, unbeaten: False}
    with pytest.raises(ReportRefused, match=f"{unbeaten}"):
        ReportGate(_prereg()).certify(_request(treatment_beats=beats))


# --- invariant 4: paired reporting ------------------------------------------------------------


def test_refuses_to_emit_compression_without_capability():
    with pytest.raises(ReportRefused, match="pair"):
        ReportGate(_prereg()).certify(_request(capability_delta=None))


def test_refuses_to_emit_capability_without_compression():
    with pytest.raises(ReportRefused, match="pair"):
        ReportGate(_prereg()).certify(_request(compression_ratio=None))


# --- other gates -------------------------------------------------------------------------------


def test_refuses_a_capability_claim_without_fdr_control():
    with pytest.raises(ReportRefused, match="FDR"):
        ReportGate(_prereg()).certify(_request(fdr_controlled=False))


def test_refuses_a_capability_claim_when_the_concentration_test_failed():
    with pytest.raises(ReportRefused, match="concentration"):
        ReportGate(_prereg()).certify(_request(concentration_test_passed=False))


def test_refuses_a_capability_claim_from_an_underpowered_run():
    with pytest.raises(ReportRefused, match="not powered"):
        ReportGate(_prereg()).certify(_request(powered=False))


# --- what the gate does allow -------------------------------------------------------------------


def test_certifies_a_capability_claim_when_every_control_is_satisfied():
    result = ReportGate(_prereg()).certify(_request())
    assert result["certified"]
    assert result["claim_kind"] == "capability"
    assert "matched compute" in result["permitted_claim_shape"]


def test_null_results_are_certifiable_and_route_to_the_negative_result_ledger():
    result = ReportGate(_prereg()).certify(_request(claim_kind="null"))
    assert result["certified"]
    assert "negative_results" in result["notes"][0]


def test_efficiency_claims_are_certifiable_and_labelled_as_such():
    result = ReportGate(_prereg()).certify(
        _request(claim_kind="efficiency", capability_delta=0.004)
    )
    assert result["claim_kind"] == "efficiency"
    assert "never as a capability result" in result["notes"][0]


def test_preregistration_round_trips_through_disk(tmp_path):
    prereg = _prereg()
    path = prereg.save(tmp_path / "prereg.json")
    loaded = Preregistration.load(path)
    loaded.verify()
    assert loaded.preregistration_hash == prereg.preregistration_hash
