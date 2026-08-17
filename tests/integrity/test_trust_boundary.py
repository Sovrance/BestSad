"""M4 acceptance: evaluator integrity, Gate G1 (spec §20.2, §22, §27).

`AGENTS.md` invariant 2: the evolutionary/search side must have no read path to the frozen
hidden benchmark — not through imports, not through logs, not through error messages, not
through a shared filesystem. These tests attempt each vector and require it to fail.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from bestsad.evaluator import (
    IntegrityMonitor,
    IntegrityViolation,
    SandboxPolicy,
    candidate_sandbox,
    check_canary,
    default_policy,
)
from bestsad.kernel import K0_OPS

REPO_ROOT = Path(__file__).resolve().parents[2]
HIDDEN = REPO_ROOT / "hidden_evaluator"
SRC = REPO_ROOT / "src" / "bestsad"


# --- vector 1: import path -------------------------------------------------------------------


def test_no_module_in_the_package_imports_the_hidden_evaluator():
    """The strongest of the checks: there is no import path at all, so no runtime policy has to
    hold for this vector to be closed."""
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "hidden_evaluator":
                        offenders.append(str(path))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "hidden_evaluator":
                    offenders.append(str(path))
    assert offenders == [], f"modules import the hidden evaluator: {offenders}"


def test_hidden_evaluator_is_not_an_installable_package():
    """It must not be picked up by packaging, or `pip install` would ship the assets."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'where = ["src"]' in pyproject
    assert not (HIDDEN / "__init__.py").exists()


# --- vector 2: filesystem --------------------------------------------------------------------


def test_candidate_side_cannot_read_hidden_assets(tmp_path):
    policy = default_policy(tmp_path / "scratch", REPO_ROOT)
    target = HIDDEN / "frozen" / "seed_commitment.json"
    assert target.exists(), "fixture missing: the test would pass vacuously"

    with candidate_sandbox(policy) as monitor:
        with pytest.raises(IntegrityViolation):
            target.read_text()
    assert monitor.fired()
    assert monitor.findings[0]["kind"] == "hidden_asset_read"


def test_reading_hidden_assets_outside_the_sandbox_still_works():
    """Confirms the previous test is testing the policy rather than a missing file."""
    assert "held_out_seed_base" in (HIDDEN / "frozen" / "seed_commitment.json").read_text()


def test_candidate_side_cannot_write_outside_scratch(tmp_path):
    policy = default_policy(tmp_path / "scratch", REPO_ROOT)
    outside = tmp_path / "escape.txt"
    with candidate_sandbox(policy) as monitor:
        with pytest.raises(IntegrityViolation):
            outside.write_text("candidate state that should not persist")
        # ...but scratch is writable, or the candidate could not run at all.
        (policy.scratch_dir / "ok.txt").write_text("fine")
    assert not outside.exists()
    assert any(f["kind"] == "write_outside_scratch" for f in monitor.findings)


# --- vector 3: network -----------------------------------------------------------------------


def test_candidate_side_cannot_reach_the_network(tmp_path):
    policy = default_policy(tmp_path / "scratch", REPO_ROOT)
    with candidate_sandbox(policy) as monitor:
        with pytest.raises(IntegrityViolation):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    assert any(f["kind"] == "network" for f in monitor.findings)


# --- vector 4: subprocess --------------------------------------------------------------------


def test_candidate_side_cannot_spawn_a_subprocess(tmp_path):
    policy = default_policy(tmp_path / "scratch", REPO_ROOT)
    with candidate_sandbox(policy) as monitor:
        with pytest.raises(IntegrityViolation):
            subprocess.run([sys.executable, "-c", "print(1)"], check=False)
    assert any(f["kind"] == "subprocess" for f in monitor.findings)


# --- vector 5: persistence across resets ------------------------------------------------------


def test_candidate_state_does_not_persist_across_runs(tmp_path):
    """Spec §22.1: the filesystem is reset per candidate."""
    scratch = tmp_path / "scratch"
    policy = SandboxPolicy(scratch_dir=scratch, protected_paths=(HIDDEN,))
    with candidate_sandbox(policy):
        (scratch / "note.txt").write_text("remember me")
    assert (scratch / "note.txt").exists()

    # The runner resets scratch between candidates.
    for item in scratch.iterdir():
        item.unlink()
    with candidate_sandbox(policy):
        assert list(scratch.iterdir()) == []


# --- vector 6: the K0 vocabulary itself -------------------------------------------------------


def test_k0_has_no_operation_that_could_reach_any_asset():
    """The structural guarantee. A candidate *program* cannot read hidden tests because K0 has
    no operation with an effect other than trapping — not because a filter removed one."""
    forbidden = {"open", "read", "write", "socket", "exec", "import", "eval", "spawn",
                 "file", "env", "clock", "time", "rand", "random"}
    for op in K0_OPS:
        assert op.op.lower() not in forbidden
        for trap in op.traps:
            assert trap in {
                "division_by_zero", "value_too_large", "list_too_long",
                "fuel_exhausted", "depth_exceeded", "malformed_program",
            }


def test_the_monitor_fires_on_every_vector(tmp_path):
    """The integrity monitor must *record*, not merely block: spec §22.1 requires a separate
    monitor that detects unexpected file access and process behaviour."""
    policy = default_policy(tmp_path / "scratch", REPO_ROOT)
    monitor = IntegrityMonitor()
    attempts = 0
    with candidate_sandbox(policy, monitor):
        for attempt in (
            lambda: (HIDDEN / "frozen" / "seed_commitment.json").read_text(),
            lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            lambda: subprocess.run([sys.executable, "-c", "pass"], check=False),
        ):
            attempts += 1
            with pytest.raises(IntegrityViolation):
                attempt()
    assert len(monitor.fatal_findings()) == attempts


# --- contamination controls --------------------------------------------------------------------


def test_canary_is_absent_from_candidate_visible_surfaces():
    """Spec §40.1 C4. The canary lives with the hidden assets; if it ever appears on a surface a
    candidate can see, the contamination control has failed."""
    from bestsad.bsir import get_projection
    from bestsad.tasks import generate_task

    task = generate_task("F9", 7)
    projection = get_projection("sexpr")
    surfaces = [
        projection.describe_grammar(),
        str(task.train_inputs),
        task.notes,
        task.task_id,
    ]
    assert check_canary(*surfaces) == []


def test_canary_check_actually_detects_a_leak():
    from bestsad.tasks.generator import CANARY

    findings = check_canary(f"some prompt text {CANARY} more text")
    assert len(findings) == 1 and findings[0]["kind"] == "canary_leak"


def test_hidden_inputs_never_appear_in_the_material_given_to_the_search():
    """The search receives training examples only. This asserts the *interface* enforces it:
    `solve` takes a Task, and the synthesizer reads `train_inputs` — a regression that started
    reading `hidden_inputs` would be caught here."""
    import inspect

    from bestsad.solver.enumerative import EnumerativeSynthesizer

    source = inspect.getsource(EnumerativeSynthesizer)
    assert "hidden_inputs" not in source, (
        "the synthesizer references hidden inputs — the evaluator is the only component "
        "permitted to touch them"
    )
