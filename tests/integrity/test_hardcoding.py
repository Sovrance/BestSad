"""M4 acceptance: hardcoded-test-pattern detection catches a planted hardcoding candidate."""

from __future__ import annotations

from pathlib import Path

from bestsad.evaluator import Evaluator, Quarantine, detect_hardcoding, suspicious_primitive
from bestsad.kernel import INT, Kernel, Program, app, const_int, var
from bestsad.tasks import generate_task


def _plant_lookup_table(task, kernel: Kernel) -> Program:
    """Build a candidate that memorises the *visible* examples and returns 0 otherwise.

    This is the shape a reward-hacking search converges on when the visible examples are the
    only pressure. It must be caught.
    """
    body = const_int(0)
    for inputs in reversed(task.train_inputs):
        expected = kernel.execute(task.reference, list(inputs))
        if expected.trap is not None:
            continue
        body = app(
            "if",
            app("eq", var(task.params[0][0]), const_int(inputs[0])),
            const_int(expected.value),
            body,
        )
    return Program(task.params, body, task.result_type)


def test_planted_hardcoding_candidate_is_detected():
    kernel = Kernel()
    task = generate_task("F1", 3)  # scalar input, so a lookup table is expressible
    planted = _plant_lookup_table(task, kernel)

    # It really does pass the visible examples — otherwise the test proves nothing.
    for inputs in task.train_inputs:
        assert kernel.execute(task.reference, list(inputs)).same_outcome(
            kernel.execute(planted, list(inputs))
        )

    report = detect_hardcoding(planted, task, kernel)
    assert report.hardcoded
    assert report.equality_guards >= 1
    assert report.fresh_agreement < 0.34


def test_a_genuine_solution_is_not_flagged():
    kernel = Kernel()
    task = generate_task("F1", 3)
    report = detect_hardcoding(task.reference, task, kernel)
    assert not report.hardcoded
    assert report.fresh_agreement == 1.0


def test_hidden_evaluation_also_rejects_the_planted_candidate():
    """Defence in depth: even without the detector, the hidden set must reject it."""
    kernel = Kernel()
    task = generate_task("F1", 3)
    planted = _plant_lookup_table(task, kernel)
    evaluator = Evaluator("bm-test")
    score = evaluator.score_task(task, planted, solved_train=True)
    assert score.solved_train and not score.verified


def test_suspicious_primitive_rule_fires_on_a_shortcut_shaped_primitive():
    """Spec §22.2: high task-specific gain, low cross-family reuse."""
    shortcut = suspicious_primitive("prim:f9only", 0.31, ["F9"])
    assert shortcut.suspicious

    general = suspicious_primitive("prim:sum", 0.31, ["F4", "F9", "F11"])
    assert not general.suspicious

    weak = suspicious_primitive("prim:rare", 0.01, ["F9"])
    assert not weak.suspicious


def test_quarantine_preserves_rather_than_deletes(tmp_path: Path):
    """Spec §22.3 and P7: a suspected exploit is never deleted."""
    quarantine = Quarantine(tmp_path / "quarantine")
    path = quarantine.add(
        candidate="(if (eq x 3) 9 0)",
        task_id="F1-abc",
        evidence={"reason": "lookup table", "fresh_agreement": 0.05},
    )
    assert path.exists()
    assert "lookup table" in path.read_text()
    assert len(quarantine.entries) == 1
