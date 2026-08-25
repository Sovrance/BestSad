"""Condition jobs run behind the candidate boundary (spec §27.1; ADR-0005 revisit trigger (a)).

ADR-0005 recorded a boundary that existed and was tested but had no caller: `Exp001Runner`
invoked `_job` directly, so no experiment ever ran under a limit. These tests pin the wiring,
and — more importantly — pin the two properties that make it safe to leave on: it changes no
scientific quantity, and it never silently drops a `(condition, seed)` cell.
"""

from __future__ import annotations

import pytest

from bestsad.conditions import build_conditions
from bestsad.evaluator import ISOLATION_AVAILABLE, IntegrityViolation
from bestsad.experiments import Exp001Runner
from bestsad.experiments.exp001 import JobIsolation, _isolated_job
from bestsad.kernel import KERNEL_VERSION
from bestsad.solver import SearchBudget

TINY = dict(
    per_family=1,
    in_family_per_family=1,
    adversarial_per_family=1,
    budget=SearchBudget(max_nodes=1200, max_size=4, lam_max_size=2, lam_bank_cap=20,
                        bank_cap=30),
)


def _baseline_condition():
    return build_conditions(
        kernel_version=KERNEL_VERSION,
        random_primitives=[], mdl_primitives=[], utility_primitives=[],
        expert_primitives=[], baseline_node_budget=1200, evolution_nodes=0,
    )["A"]


def test_isolation_is_on_by_default():
    """The default matters more than the capability. A boundary that must be opted into is a
    boundary that will be off for the run that counts."""
    assert Exp001Runner(run_id="default-check", seeds=[1], **TINY).isolation.enabled


@pytest.mark.skipif(not ISOLATION_AVAILABLE, reason="requires fork and POSIX rlimits")
def test_isolation_changes_no_scientific_quantity():
    """The reproducibility digest covers every scientific quantity and no timing field. If
    isolation moved any of them, it would be unusable regardless of what it protects."""
    condition = _baseline_condition()
    plain = Exp001Runner(run_id="iso-off", seeds=[1], isolation=JobIsolation(enabled=False),
                         **TINY)._map_jobs([(condition, 1)])[0]
    isolated = Exp001Runner(run_id="iso-on", seeds=[1], **TINY)._map_jobs([(condition, 1)])[0]
    assert isolated["reproducibility_digest"] == plain["reproducibility_digest"]


def test_a_job_that_does_not_complete_stops_the_run(monkeypatch, tmp_path):
    """Never absorbed into a missing row. A dropped `(condition, seed)` cell does not average
    out — it silently reweights the comparison the study rests on.

    The limits firing is covered in `tests/integrity/test_process_isolation.py`; what matters
    here is what the *runner* does with a job that came back unfinished, which is pinned
    directly rather than by starving a fixture job until it happens to die.
    """
    from bestsad.evaluator import IsolatedResult

    monkeypatch.setattr(
        "bestsad.experiments.exp001.run_isolated",
        lambda *a, **k: IsolatedResult(
            ok=False, error="candidate exceeded the 1s CPU limit (SIGXCPU)", contained=True
        ),
    )
    payload = (_baseline_condition(), 1, {}, "iso-limit", None)
    with pytest.raises(RuntimeError, match="did not complete under isolation"):
        _isolated_job((payload, JobIsolation(), str(tmp_path), None))


def test_a_job_whose_integrity_monitor_fired_stops_the_run(monkeypatch, tmp_path):
    """`AGENTS.md` invariant 2: an attempted boundary crossing is reported, never counted as a
    result. A job that reached for the hidden assets and still produced a number is the single
    most dangerous thing this instrument could return."""
    from bestsad.evaluator import IsolatedResult

    monkeypatch.setattr(
        "bestsad.experiments.exp001.run_isolated",
        lambda *a, **k: IsolatedResult(
            ok=True, value={"condition_id": "A"},
            findings=[{"kind": "hidden_asset_read", "detail": "/hidden/frozen", "fatal": True}],
        ),
    )
    payload = (_baseline_condition(), 1, {}, "iso-finding", None)
    with pytest.raises(IntegrityViolation, match="integrity monitor fired"):
        _isolated_job((payload, JobIsolation(), str(tmp_path), None))


@pytest.mark.skipif(not ISOLATION_AVAILABLE, reason="requires fork and POSIX rlimits")
def test_the_job_may_write_its_checkpoint_but_nothing_else(tmp_path):
    """Checkpoints live outside scratch by design. The fix is to name that one directory, not
    to switch off the write restriction — which would give away the containment entirely."""
    condition = _baseline_condition()
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    runner = Exp001Runner(run_id="iso-ckpt", seeds=[1], checkpoint_dir=checkpoints, **TINY)

    records = runner._map_jobs([(condition, 1)])
    assert records and records[0]["condition_id"] == "A"
    assert list(checkpoints.glob("A_*_seed1.json")), "the job could not write its checkpoint"

    # And the write permission is scoped: the policy names the checkpoint directory only.
    from bestsad.evaluator import default_policy
    assert default_policy(tmp_path).writable_paths == ()


def test_provenance_states_which_stages_are_isolated():
    """Spec §40.3: "discovery is not isolated" must be stated, not inferred from source."""
    record = JobIsolation().to_record()
    assert record["isolated_stages"] == ["condition_jobs"]
    assert record["unisolated_stages"] == ["abstraction_discovery"]
    assert record["cpu_seconds"] > 60, "a cap tuned for unit tests would kill every real job"


def test_isolation_never_falls_back_silently(monkeypatch):
    """Running unisolated while provenance claims isolation would put a false statement in the
    run record — worse than refusing to run."""
    monkeypatch.setattr("bestsad.experiments.exp001.ISOLATION_AVAILABLE", False)
    runner = Exp001Runner(run_id="iso-unavailable", seeds=[1], **TINY)
    with pytest.raises(RuntimeError, match="no fork start method"):
        runner._map_jobs([(_baseline_condition(), 1)])
