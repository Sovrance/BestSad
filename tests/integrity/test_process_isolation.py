"""M4 hardening: process isolation for candidate execution (spec §27.1; ADR-0005).

ADR-0005 recorded that the candidate boundary was an in-process audit hook, which "does not
enforce CPU or memory limits" and "does not provide process isolation". These tests are the
red team for the layer that closes those two clauses: each one attempts the failure it names
and requires the *evaluator* to survive it with a recorded outcome.

The distinction under test throughout is between a candidate failing and the evaluator failing.
An evaluator that dies mid-run cannot score anything, and a run that silently loses candidates
is not a controlled experiment — so "the child died and we know why" is the passing result,
and "the exception reached the parent" is the failure.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from bestsad.evaluator import (
    ISOLATION_AVAILABLE,
    IntegrityViolation,
    ResourceLimits,
    candidate_sandbox,
    default_policy,
    run_isolated,
)

pytestmark = pytest.mark.skipif(
    not ISOLATION_AVAILABLE,
    reason="process isolation requires POSIX rlimits and a fork start method",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HIDDEN = REPO_ROOT / "hidden_evaluator"


# --- candidate-side payloads ------------------------------------------------------------------
# Module level so the failure modes read as named behaviours rather than as inline lambdas.


def _well_behaved(a: int, b: int) -> int:
    return a + b


def _allocate_a_gigabyte() -> int:
    return len(bytearray(1024 * 1024 * 1024))


def _spin_forever() -> None:
    counter = 0
    while True:
        counter += 1


def _report_environment() -> dict:
    return dict(os.environ)


def _report_cwd() -> str:
    return os.getcwd()


def _exit_abruptly() -> None:
    os._exit(7)


def _read_hidden_asset() -> str:
    return (HIDDEN / "README.md").read_text()


def _open_a_socket() -> None:
    import socket

    socket.socket()


def _write_a_large_file() -> int:
    with open("big.bin", "wb") as handle:
        return handle.write(b"\x00" * (4 * 1024 * 1024))


def _raise_value_error() -> None:
    raise ValueError("ordinary candidate bug")


# --- the isolation layer does its job ----------------------------------------------------------


def test_a_well_behaved_candidate_returns_its_value(tmp_path):
    result = run_isolated(_well_behaved, 2, 3, scratch_dir=tmp_path)
    assert result.ok
    assert result.value == 5
    assert result.exit_code == 0
    assert result.findings == []


def test_address_space_cap_contains_a_runaway_allocation(tmp_path):
    """The failure ADR-0005 named first: without a cap this takes the evaluator down with it."""
    result = run_isolated(
        _allocate_a_gigabyte,
        scratch_dir=tmp_path,
        limits=ResourceLimits(address_space_bytes=256 * 1024 * 1024),
        timeout=60,
    )
    assert not result.ok
    assert result.contained, "an allocation stopped by RLIMIT_AS is containment, not a code bug"
    assert "MemoryError" in result.error
    # And the evaluator is still here to assert it.
    assert run_isolated(_well_behaved, 1, 1, scratch_dir=tmp_path).value == 2


def test_cpu_cap_stops_a_candidate_that_escapes_fuel_accounting(tmp_path):
    """K0's fuel is cooperative. This is the kernel-enforced backstop for anything that isn't K0."""
    result = run_isolated(
        _spin_forever, scratch_dir=tmp_path, limits=ResourceLimits(cpu_seconds=1), timeout=60
    )
    assert not result.ok
    assert result.contained
    assert result.signal == signal.SIGXCPU, (
        "soft limit must sit below hard, or SIGKILL arrives first and the diagnosis is lost"
    )
    assert "CPU limit" in result.error


def test_wall_clock_timeout_kills_a_child_that_blocks_without_burning_cpu(tmp_path):
    """A sleeping candidate never trips RLIMIT_CPU, so the wall clock is a separate limit."""
    import time

    result = run_isolated(time.sleep, 30, scratch_dir=tmp_path, timeout=1.0)
    assert not result.ok
    assert result.contained
    assert "wall-clock" in result.error


def test_an_abrupt_child_death_is_contained_rather_than_propagated(tmp_path):
    result = run_isolated(_exit_abruptly, scratch_dir=tmp_path)
    assert not result.ok
    assert result.contained
    assert result.exit_code == 7


def test_an_ordinary_candidate_exception_is_not_labelled_containment(tmp_path):
    """The two must stay distinguishable: one is a limit firing, the other is a bug to fix."""
    result = run_isolated(_raise_value_error, scratch_dir=tmp_path)
    assert not result.ok
    assert not result.contained
    assert "ValueError: ordinary candidate bug" in result.error


# --- host credentials and the filesystem --------------------------------------------------------


def test_the_child_inherits_no_environment(monkeypatch, tmp_path):
    """Spec §27.1, 'no access to host credentials'. Inherited env is the usual leak path."""
    monkeypatch.setenv("BESTSAD_FAKE_TOKEN", "sk-do-not-inherit")
    inherited = run_isolated(_report_environment, scratch_dir=tmp_path).value
    assert inherited == {}


def test_the_child_runs_in_the_ephemeral_scratch_directory(tmp_path):
    cwd = run_isolated(_report_cwd, scratch_dir=tmp_path).value
    assert Path(cwd).resolve() == tmp_path.resolve()


def test_the_audit_hook_is_still_installed_inside_the_child(tmp_path):
    """Process isolation replaces nothing: the hidden assets stay unreadable in the child too."""
    result = run_isolated(_read_hidden_asset, scratch_dir=tmp_path)
    assert not result.ok
    assert "hidden evaluation asset is not readable" in result.error


def test_network_denial_survives_the_process_boundary(tmp_path):
    result = run_isolated(_open_a_socket, scratch_dir=tmp_path)
    assert not result.ok
    assert "network access denied" in result.error


def test_integrity_findings_are_carried_back_across_the_pipe(tmp_path):
    """The monitor lives in the child. If its findings are not transported, an attempted
    boundary crossing becomes invisible to the run — which is worse than no isolation at all."""
    result = run_isolated(_read_hidden_asset, scratch_dir=tmp_path)
    assert [f["kind"] for f in result.findings] == ["hidden_asset_read"]
    assert result.to_record()["findings"][0]["fatal"] is True


def test_file_size_cap_bounds_what_a_candidate_can_write(tmp_path):
    result = run_isolated(
        _write_a_large_file,
        scratch_dir=tmp_path,
        limits=ResourceLimits(file_size_bytes=64 * 1024),
        timeout=60,
    )
    assert not result.ok


# --- the boundary cannot be used to escape itself -----------------------------------------------


def test_a_sandboxed_component_cannot_spawn_its_own_isolated_process(tmp_path):
    """`run_isolated` forks, and forking is denied inside the sandbox. That denial is the
    intended behaviour: candidate-side code must not be able to launch a less-restricted child."""
    with candidate_sandbox(default_policy(tmp_path)):
        with pytest.raises(IntegrityViolation, match="subprocess creation denied"):
            run_isolated(_well_behaved, 1, 1, scratch_dir=tmp_path)


def test_limits_are_applied_in_the_child_only(tmp_path):
    """A limit leaking into the parent would throttle the evaluator itself."""
    import resource

    before = resource.getrlimit(resource.RLIMIT_AS)
    run_isolated(
        _well_behaved, 1, 1, scratch_dir=tmp_path,
        limits=ResourceLimits(address_space_bytes=256 * 1024 * 1024),
    )
    assert resource.getrlimit(resource.RLIMIT_AS) == before


def test_limits_are_recorded_for_the_run_record(tmp_path):
    """Spec §40.3: a residual that is not written down does not travel with the result."""
    record = ResourceLimits().to_record()
    assert set(record) == {
        "cpu_seconds", "address_space_bytes", "file_size_bytes", "core_dump_bytes"
    }
    assert record["core_dump_bytes"] == 0, "a core dump writes process memory to disk"


# --- red team: escapes found in review (Codex P1 findings on PR #4) -----------------------------
# Each of these was a real, demonstrated hole in the first version of this module. They are kept
# as tests rather than as a changelog entry because the fix for each is a single line that a
# later refactor could quietly drop.


def _read_inherited_descriptor(number: int) -> str:
    """Read a descriptor the child never opened — no `open` call, so no audit event."""
    os.lseek(number, 0, os.SEEK_SET)
    return os.read(number, 64).decode(errors="replace")


class _HostileResult:
    """A result object whose *unpickling* runs code. `__reduce__` fires in the receiver."""

    def __init__(self, marker: str) -> None:
        self.marker = marker

    def __reduce__(self):
        return (exec, (f"import pathlib; pathlib.Path({self.marker!r}).write_text('escaped')",))


def _return_hostile_result(marker: str) -> _HostileResult:
    return _HostileResult(marker)


def _read_path(path: str) -> str:
    return open(path).read()


@pytest.mark.skipif(not (HIDDEN / "README.md").exists(), reason="hidden assets not present")
def test_a_descriptor_open_in_the_evaluator_is_not_inherited_by_the_candidate(tmp_path):
    """`fork` duplicates open descriptors. If the evaluator holds a hidden-benchmark file open,
    the candidate can `os.read()` that number directly — no `open`, no audit event, no finding.
    That is a read path to the frozen benchmark, which invariant 2 forbids outright."""
    with open(HIDDEN / "README.md", "rb") as handle:
        result = run_isolated(_read_inherited_descriptor, handle.fileno(), scratch_dir=tmp_path)
    assert not result.ok, "hidden benchmark content reached the candidate through a stale fd"


def test_a_hostile_result_object_cannot_execute_in_the_evaluator(tmp_path):
    """The result travels as JSON, not pickle. Pickling would let a candidate's `__reduce__` run
    in the parent — outside every audit hook and resource limit this module installs, making the
    isolation boundary itself the delivery mechanism for the escape."""
    marker = tmp_path / "escaped"
    result = run_isolated(_return_hostile_result, str(marker), scratch_dir=tmp_path)
    assert not marker.exists(), "candidate code executed inside the evaluator process"
    assert not result.ok


def test_the_configured_hidden_mount_is_protected_not_just_the_in_repo_path(tmp_path, monkeypatch):
    """The container mounts the frozen assets outside the source tree. A policy that knows only
    `<repo>/hidden_evaluator` protects nothing in the deployment the image exists to provide."""
    mount = tmp_path / "mounted-hidden"
    mount.mkdir()
    (mount / "frozen.json").write_text('{"expected": "outputs"}')
    monkeypatch.setenv("BESTSAD_HIDDEN_ROOT", str(mount))

    result = run_isolated(_read_path, str(mount / "frozen.json"), scratch_dir=tmp_path)
    assert not result.ok
    assert "hidden evaluation asset is not readable" in result.error
    assert [f["kind"] for f in result.findings] == ["hidden_asset_read"]


def test_an_oversized_result_cannot_exhaust_the_evaluator(tmp_path):
    """A bounded read: the parent must not allocate whatever the candidate decides to send."""
    from bestsad.evaluator.isolation import MAX_RESULT_BYTES

    assert MAX_RESULT_BYTES <= 64 * 1024 * 1024
