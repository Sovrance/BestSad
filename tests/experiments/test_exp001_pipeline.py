"""M10: end-to-end coverage of the EXP-001 staged pipeline.

Runs at a deliberately tiny budget — the point is that every stage wires together and the
control plane holds, not that the search finds anything. Scientific conclusions come from a
real run, not from these fixtures.
"""

from __future__ import annotations

import pytest

from bestsad.conditions import REQUIRED_CONTROLS, check_condition_f
from bestsad.experiments import Exp001Runner, analyse, certify
from bestsad.experiments.exp001 import expert_dsl_primitives
from bestsad.solver import SearchBudget

TINY = dict(
    per_family=1,
    in_family_per_family=1,
    adversarial_per_family=1,
    budget=SearchBudget(max_nodes=1500, max_size=4, lam_max_size=2, lam_bank_cap=20,
                        bank_cap=30),
)


@pytest.fixture(scope="module")
def s2():
    runner = Exp001Runner(run_id="test-s2", seeds=[1, 2], **TINY)
    return runner, runner.stage_s2()


def test_s1_measures_variance_and_reports_power(): 
    runner = Exp001Runner(run_id="test-s1", seeds=[1, 2], **TINY)
    result = runner.stage_s1(minimum_interesting_effect=0.10)
    payload = result.payload
    assert len(payload["per_seed_verified_ood_rate"]) == 2
    assert "variance" in payload and "power_analysis" in payload
    # Whatever the variance, the gate's verdict must follow from it rather than be assumed.
    assert result.passed == payload["power_analysis"]["powered"]


def test_s2_runs_every_condition_on_every_seed(s2):
    _, result = s2
    per_condition = result.payload["per_condition"]
    assert set(per_condition) == set("ABCDEFHI")
    for cid, records in per_condition.items():
        assert {r["seed"] for r in records} == {1, 2}, f"condition {cid} missing a seed"


def test_s2_reports_compute_reconciliation_for_condition_i(s2):
    _, result = s2
    reconciliations = result.payload["compute_reconciliation"]
    assert len(reconciliations) == 2
    for entry in reconciliations:
        assert "reconciled" in entry and "relative_residual" in entry


def test_s2_logs_delivered_scaffolding_and_its_residual(s2):
    """Condition H's whole point: the budget delivered is logged, not assumed."""
    _, result = s2
    for entry in result.payload["scaffolding"]:
        assert entry["target_tokens"] > 0
        assert "equalized to within" in entry["disclosure"]
        assert set(entry["residuals"]) >= set("ABCDEFGHI")


def test_s2_mines_abstractions_only_from_curriculum_families(s2):
    """An abstraction mined from held-out solutions would be fitted to the evaluation set."""
    from bestsad.tasks import CURRICULUM_FAMILIES

    _, result = s2
    for note in result.payload["discovery"]:
        assert set(note["families_in_corpus"]) <= set(CURRICULUM_FAMILIES)


def test_condition_f_carries_no_new_semantics_in_a_real_run(s2):
    """Re-derived from the actual genomes the run built, not from a fixture."""
    from bestsad.conditions import build_conditions
    from bestsad.kernel import KERNEL_VERSION

    runner, _ = s2
    primitives, evolution_nodes, _ = runner.discover(1)
    plane = build_conditions(
        kernel_version=KERNEL_VERSION,
        random_primitives=primitives["random"],
        mdl_primitives=primitives["mdl"],
        utility_primitives=primitives["utility"],
        expert_primitives=expert_dsl_primitives(),
        baseline_node_budget=1500,
        evolution_nodes=evolution_nodes,
    )
    report = check_condition_f(plane["F"], plane["A"])
    assert report["identical_primitive_semantics"]


def test_analysis_evaluates_control_gates_and_classifies_the_outcome(s2):
    _, result = s2
    analysis = analyse(result.payload["per_condition"])
    assert set(analysis.summaries) == set("ABCDEFHI")
    for control in REQUIRED_CONTROLS:
        assert control in analysis.control_gates
    assert analysis.outcome_class in {"positive", "efficiency_only", "null", "h0_consistent"}
    # Paired outcomes exist for both treatments, never one half alone.
    for tid in ("D", "E"):
        assert set(analysis.paired_outcomes[tid]) >= {"compression_ratio", "capability_delta"}


def test_certification_refuses_a_capability_claim_without_a_preregistration(s2):
    _, result = s2
    analysis = analyse(result.payload["per_condition"])
    analysis.outcome_class = "positive"  # force the strongest request the gate can receive
    certified = certify(
        analysis, None, experiment_id="test",
        conditions_run=tuple("ABCDEFHI"), concentration_passed=True, powered=True,
    )
    assert not certified["certified"]
    assert "pre-registration" in certified["refusal"]


def test_s3_runs_the_human_expert_reference_class():
    runner = Exp001Runner(run_id="test-s3", seeds=[1], **TINY)
    result = runner.stage_s3(None)
    records = result.payload["per_condition"]["G"]
    assert len(records) == 1 and records[0]["condition_id"] == "G"


def test_expert_dsl_is_frozen_and_human_authored():
    primitives = expert_dsl_primitives()
    assert len(primitives) == 3
    assert all(p.origin == "human_expert" for p in primitives)
    # Frozen: constructing it twice yields identical semantics.
    assert [p.semantic_id for p in primitives] == [
        p.semantic_id for p in expert_dsl_primitives()
    ]


def test_condition_records_are_reproducible_by_digest():
    """Gate G2's replay check: every scientific quantity is stable, timing is excluded."""
    from bestsad.conditions import Condition
    from bestsad.genomes import Genome
    from bestsad.kernel import KERNEL_VERSION

    runner = Exp001Runner(run_id="test-replay", seeds=[1], **TINY)
    genome = Genome("G-A", 0, KERNEL_VERSION, (), "sexpr")
    condition = Condition("A", "reference", genome, "baseline", node_budget=1500)
    first = runner._run_condition(condition, 1, runner._task_sets(1))
    second = runner._run_condition(condition, 1, runner._task_sets(1))
    assert first.reproducibility_digest() == second.reproducibility_digest()


def test_checkpoint_key_distinguishes_different_search_budgets(tmp_path):
    """A checkpoint keyed on the genome alone collides between configurations.

    Condition I's genome is empty and identical whatever budget it is given, so a genome-only
    key serves a record produced under a different budget — instantly, and wrongly. This was a
    real defect: a re-run of condition I with a corrected budget returned the stale record in
    zero seconds.
    """
    from bestsad.conditions import Condition
    from bestsad.genomes import Genome
    from bestsad.kernel import KERNEL_VERSION
    from bestsad.experiments.exp001 import _job

    genome = Genome("G-I", 0, KERNEL_VERSION, (), "sexpr")
    sizing = dict(TINY)
    run = lambda budget, bonus: _job((
        Condition("I", "confound_control", genome, "search-only",
                  controls_confound="C1_compute", node_budget=budget,
                  search_depth_bonus=bonus),
        1, sizing, "ckpt-test", str(tmp_path),
    ))

    first = run(1500, 0)
    written = sorted(p.name for p in tmp_path.glob("*.json"))
    assert len(written) == 1

    # A different budget must not reuse the first record.
    run(4000, 0)
    assert len(list(tmp_path.glob("*.json"))) == 2
    # Nor must a different search depth.
    run(1500, 1)
    assert len(list(tmp_path.glob("*.json"))) == 3
    # ...but an identical configuration must hit the cache rather than recompute.
    again = run(1500, 0)
    assert len(list(tmp_path.glob("*.json"))) == 3
    assert again["reproducibility_digest"] == first["reproducibility_digest"]


def test_discovery_checkpoint_key_covers_the_extractor_version(tmp_path):
    """Discovery output depends on the extractor that produced it.

    A key naming only the seed would serve abstractions selected under a different objective
    once the extractor changed — the same class of defect as the condition-I checkpoint
    collision, and harder to notice, because stale abstractions still look like abstractions.
    """
    from bestsad.experiments.exp001 import _discovery_job

    sizing = dict(TINY)
    _discovery_job((1, sizing, "ckpt", str(tmp_path)))
    written = sorted(p.name for p in tmp_path.glob("discovery_*.pkl"))
    assert len(written) == 1
    # The filename carries a fingerprint, not just the seed.
    assert written[0] != "discovery_seed1.pkl"
    assert written[0].endswith("_seed1.pkl")

    # An identical configuration hits the cache rather than recomputing.
    _discovery_job((1, sizing, "ckpt", str(tmp_path)))
    assert len(list(tmp_path.glob("discovery_*.pkl"))) == 1

    # A different budget must not reuse it.
    from bestsad.solver import SearchBudget

    other = dict(sizing)
    other["budget"] = SearchBudget(max_nodes=4321, max_size=4, lam_max_size=2,
                                   lam_bank_cap=20, bank_cap=30)
    _discovery_job((1, other, "ckpt", str(tmp_path)))
    assert len(list(tmp_path.glob("discovery_*.pkl"))) == 2
