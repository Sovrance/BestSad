"""Process isolation for candidate execution (spec §27.1; ADR-0005).

`sandbox.py` supplies the in-process audit hook. It defends against a component that *reaches*
for the hidden assets, and ADR-0005 is explicit that it is not a kernel boundary: it cannot cap
CPU or memory, cannot stop a candidate crashing the evaluator with it, and native code can walk
past it.

This module adds the layer spec §27.1 actually asks for — "process isolation … CPU/memory/time
limits … no access to host credentials" — by running candidate-side work in a **separate
process** with:

* `RLIMIT_AS`      — an address-space cap, so a runaway allocation dies instead of taking the
                     evaluator with it;
* `RLIMIT_CPU`     — a CPU-seconds cap, enforced by the kernel rather than by cooperative fuel
                     accounting, so a candidate that escapes K0's metering is still bounded;
* `RLIMIT_FSIZE`   — a write-size cap;
* `RLIMIT_CORE`    — no core dumps, which would otherwise write process memory to disk;
* a **cleared environment**, so host credentials and configuration are not inherited;
* a working directory pinned to ephemeral scratch;
* the audit-hook policy from `sandbox.py`, still installed inside the child.

A child that dies from a limit is reported as a *contained failure*, not an evaluator crash.
That distinction is the point: the evaluator must survive a hostile or merely broken candidate,
because an evaluator that dies mid-run cannot score anything, and a run that silently loses
candidates is not a controlled experiment.

One caveat worth stating rather than discovering: `run_isolated` forks, and `sandbox.py`'s audit
hook denies `os.fork`. So this is the *outer* layer — the parent calls `run_isolated`, and the
audit hook is installed by the child, inside it. Calling `run_isolated` from within an already
active `candidate_sandbox` is denied by design, and the denial is the correct answer: a
candidate-side component must not be able to spawn its own less-restricted processes.

**What this still is not.** No seccomp filter, no namespace or chroot isolation, no read-only
base filesystem. Those need the container the evaluator image provides; the `Dockerfile` in this
directory is the deployment half. ADR-0005 records the full gap and what production must add.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .sandbox import SandboxPolicy, candidate_sandbox

try:  # pragma: no cover - platform probe
    import resource
except ImportError:  # pragma: no cover - non-POSIX
    resource = None  # type: ignore[assignment]

#: True where the isolation layer can actually be enforced. Callers that need the guarantee must
#: check this rather than assume it: a silent fallback to in-process execution would turn a
#: containment failure into an evaluator crash, which is exactly the outcome this module exists
#: to prevent.
ISOLATION_AVAILABLE = resource is not None and "fork" in mp.get_all_start_methods()

#: Defaults sized for candidate evaluation, not for the evaluator itself. Generous enough that a
#: legitimate candidate never trips them, tight enough that a runaway dies quickly.
DEFAULT_CPU_SECONDS = 30
DEFAULT_ADDRESS_SPACE = 1024 * 1024 * 1024   # 1 GiB
DEFAULT_FILE_SIZE = 16 * 1024 * 1024         # 16 MiB


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Kernel-enforced limits applied inside the child before any candidate code runs."""

    cpu_seconds: int = DEFAULT_CPU_SECONDS
    address_space_bytes: int = DEFAULT_ADDRESS_SPACE
    file_size_bytes: int = DEFAULT_FILE_SIZE
    core_dump_bytes: int = 0

    def apply(self) -> None:
        """Install the limits. Called in the child, never in the parent."""
        core = (self.core_dump_bytes, self.core_dump_bytes)
        resource.setrlimit(resource.RLIMIT_CORE, core)
        # Soft below hard, deliberately: the kernel raises SIGXCPU at the soft limit and SIGKILL
        # at the hard one. Setting them equal makes both arrive at the same instant, SIGKILL
        # wins, and the run records "killed" where it should record "exceeded the CPU limit".
        # A one-second gap keeps the diagnosis and keeps SIGKILL as the backstop.
        resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_seconds, self.cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (self.file_size_bytes, self.file_size_bytes))
        # Address space last: once it is set, allocation failures can occur in this function
        # itself, and a partially-applied limit set is worse than none.
        space = (self.address_space_bytes, self.address_space_bytes)
        resource.setrlimit(resource.RLIMIT_AS, space)

    def to_record(self) -> dict:
        return {
            "cpu_seconds": self.cpu_seconds,
            "address_space_bytes": self.address_space_bytes,
            "file_size_bytes": self.file_size_bytes,
            "core_dump_bytes": self.core_dump_bytes,
        }


@dataclass(slots=True)
class IsolatedResult:
    """Outcome of an isolated run.

    `contained` distinguishes "the candidate hit a limit and the child died" from "the candidate
    raised an exception". Both are failures of the candidate; neither is a failure of the
    evaluator, and the ledger records them differently.
    """

    ok: bool
    value: Any = None
    error: str = ""
    contained: bool = False
    exit_code: int | None = None
    signal: int | None = None
    findings: list[dict] = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "ok": self.ok,
            "error": self.error,
            "contained": self.contained,
            "exit_code": self.exit_code,
            "signal": self.signal,
            "findings": list(self.findings),
        }


def _child(conn, fn, args, kwargs, policy: SandboxPolicy, limits: ResourceLimits) -> None:
    """Child entry point. Everything here runs after the fork and before candidate code."""
    try:
        limits.apply()
        os.environ.clear()          # no inherited host credentials or configuration
        os.chdir(policy.scratch_dir)
        with candidate_sandbox(policy) as monitor:
            try:
                value = fn(*args, **kwargs)
                conn.send({"ok": True, "value": value, "findings": monitor.findings})
            except BaseException as exc:  # noqa: BLE001 - the boundary must catch everything
                # MemoryError under RLIMIT_AS is the limit doing its job, not a candidate bug:
                # report it as containment so the ledger does not read it as a code defect.
                conn.send(
                    {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}".rstrip(": "),
                        "traceback": traceback.format_exc(limit=5),
                        "contained": isinstance(exc, MemoryError),
                        "findings": monitor.findings,
                    }
                )
    except BaseException as exc:  # noqa: BLE001 - failure to *install* the sandbox
        try:
            conn.send({"ok": False, "error": f"sandbox setup failed: {exc}", "findings": []})
        except Exception:  # pragma: no cover - pipe already broken
            pass
    finally:
        conn.close()


def run_isolated(
    fn: Callable[..., Any],
    *args,
    scratch_dir: Path,
    policy: SandboxPolicy | None = None,
    limits: ResourceLimits | None = None,
    timeout: float = 60.0,
    **kwargs,
) -> IsolatedResult:
    """Run `fn` in a separate, resource-limited, environment-cleared process.

    The return value must be picklable. A child killed by a limit, or by the wall-clock timeout,
    yields `contained=True` rather than propagating — the evaluator survives, and the run records
    what happened.
    """
    from .sandbox import default_policy

    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    policy = policy or default_policy(scratch_dir)
    limits = limits or ResourceLimits()

    context = mp.get_context("fork")
    parent_conn, child_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_child, args=(child_conn, fn, args, kwargs, policy, limits), daemon=True
    )
    process.start()
    child_conn.close()

    payload = None
    if parent_conn.poll(timeout):
        try:
            payload = parent_conn.recv()
        except EOFError:
            payload = None
    process.join(timeout=max(1.0, timeout / 10))

    if process.is_alive():
        process.kill()
        process.join(timeout=5)
        return IsolatedResult(
            ok=False,
            error=f"candidate exceeded the {timeout}s wall-clock limit and was killed",
            contained=True,
            exit_code=process.exitcode,
        )

    exit_code = process.exitcode
    if payload is None:
        # The child died without reporting: a resource limit, or a signal.
        signal_number = -exit_code if exit_code is not None and exit_code < 0 else None
        return IsolatedResult(
            ok=False,
            error=_describe_death(exit_code, signal_number, limits),
            contained=True,
            exit_code=exit_code,
            signal=signal_number,
        )

    if payload.get("ok"):
        return IsolatedResult(
            ok=True, value=payload.get("value"), exit_code=exit_code,
            findings=payload.get("findings", []),
        )
    return IsolatedResult(
        ok=False,
        error=payload.get("error", "candidate failed"),
        contained=bool(payload.get("contained", False)),
        exit_code=exit_code,
        findings=payload.get("findings", []),
    )


def _describe_death(exit_code: int | None, signal_number: int | None,
                    limits: ResourceLimits) -> str:
    import signal as signal_module

    if signal_number == signal_module.SIGXCPU:
        return f"candidate exceeded the {limits.cpu_seconds}s CPU limit (SIGXCPU)"
    if signal_number == signal_module.SIGKILL:
        return "candidate was killed (SIGKILL), typically an address-space or OOM limit"
    if signal_number == signal_module.SIGXFSZ:
        return f"candidate exceeded the {limits.file_size_bytes}-byte write limit (SIGXFSZ)"
    if signal_number is not None:
        return f"candidate died on signal {signal_number}"
    return f"candidate exited with code {exit_code} without reporting a result"
