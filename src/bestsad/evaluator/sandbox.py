"""Candidate sandbox (spec §27.1) and the trust boundary it enforces.

Two layers, because they defend different things:

1. **K0 itself.** A candidate *program* is a K0 term, and K0 has no I/O, network, clock,
   randomness, FFI, or reflection (spec §8.2). A candidate program therefore cannot read hidden
   tests no matter what it contains — not because it is filtered, but because the vocabulary
   has no operation that could. This is the strong guarantee, and `tests/integrity/` asserts it
   by construction rather than by blocklist.

2. **The process running the search.** Everything around the candidate — the search loop, the
   abstraction extractor — is ordinary Python and *could* touch the filesystem. That is what
   this module restricts: a Python audit hook denies filesystem reads outside the scratch
   directory, all network access, and subprocess creation, and an integrity monitor records
   every attempt.

**What this is not.** An in-process audit hook is not a kernel sandbox. It defends against a
component that reaches for the hidden assets — the realistic failure here, where the "attacker"
is a bug or an over-helpful heuristic — and not against hostile native code, which can bypass
it. Spec §27.1 asks for process isolation, a read-only base filesystem, and syscall
restrictions; those belong to the container the evaluator image provides. ADR-0005 records the
gap and what production must add.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

#: Audit events that constitute a boundary violation if a candidate-side component raises them.
NETWORK_EVENTS = frozenset({
    "socket.__new__", "socket.bind", "socket.connect", "socket.getaddrinfo",
    "socket.gethostbyname", "urllib.Request", "ftplib.connect", "smtplib.connect",
})
PROCESS_EVENTS = frozenset({
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.spawn",
    "pty.spawn",
})
IMPORT_EVENTS = frozenset({"ctypes.dlopen", "ctypes.dlsym", "ctypes.cdata"})


class IntegrityViolation(Exception):
    """Raised when a candidate-side component crosses the evaluator trust boundary.

    `AGENTS.md` invariant 2: if you find such a path, stop and report it as an integrity
    finding. This exception is that report, and the monitor records it rather than swallowing
    it.
    """


@dataclass
class IntegrityMonitor:
    """Records attempted boundary crossings (spec §22.1, 'separate integrity monitor')."""

    findings: list[dict] = field(default_factory=list)

    def record(self, kind: str, detail: str, *, fatal: bool = True) -> None:
        self.findings.append({"kind": kind, "detail": detail, "fatal": fatal})

    def fired(self) -> bool:
        return bool(self.findings)

    def fatal_findings(self) -> list[dict]:
        return [f for f in self.findings if f["fatal"]]

    def clear(self) -> None:
        self.findings.clear()


@dataclass
class SandboxPolicy:
    """The policy a candidate-side component runs under (spec §27.1)."""

    scratch_dir: Path
    protected_paths: tuple[Path, ...] = ()
    allow_network: bool = False
    allow_subprocess: bool = False
    allow_writes_outside_scratch: bool = False

    def normalized_protected(self) -> tuple[str, ...]:
        return tuple(str(p.resolve()) for p in self.protected_paths)


_ACTIVE: list[tuple[SandboxPolicy, IntegrityMonitor]] = []
_HOOK_INSTALLED = False


def _audit(event: str, args) -> None:
    if not _ACTIVE:
        return
    policy, monitor = _ACTIVE[-1]

    if event in NETWORK_EVENTS and not policy.allow_network:
        monitor.record("network", f"{event}")
        raise IntegrityViolation(f"network access denied: {event}")

    if any(event.startswith(prefix) for prefix in PROCESS_EVENTS) and not policy.allow_subprocess:
        monitor.record("subprocess", f"{event}")
        raise IntegrityViolation(f"subprocess creation denied: {event}")

    if event in IMPORT_EVENTS:
        monitor.record("native_load", f"{event}")
        raise IntegrityViolation(f"dynamic native loading denied: {event}")

    if event == "open":
        path, mode = args[0], args[1]
        if path is None:
            return
        try:
            resolved = str(Path(os.fsdecode(path)).resolve())
        except (ValueError, OSError):  # pragma: no cover - unresolvable paths
            return
        for protected in policy.normalized_protected():
            if resolved == protected or resolved.startswith(protected + os.sep):
                monitor.record("hidden_asset_read", resolved)
                raise IntegrityViolation(f"hidden evaluation asset is not readable: {resolved}")
        if mode and any(flag in str(mode) for flag in ("w", "a", "+", "x")):
            if not policy.allow_writes_outside_scratch:
                scratch = str(policy.scratch_dir.resolve())
                if not resolved.startswith(scratch + os.sep) and resolved != scratch:
                    monitor.record("write_outside_scratch", resolved)
                    raise IntegrityViolation(f"write outside scratch denied: {resolved}")


def _install_hook() -> None:
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit)
        _HOOK_INSTALLED = True


@contextmanager
def candidate_sandbox(
    policy: SandboxPolicy, monitor: IntegrityMonitor | None = None
) -> Iterator[IntegrityMonitor]:
    """Run candidate-side code under `policy`.

    The audit hook cannot be uninstalled once added — that is a Python guarantee, and a useful
    one here: a candidate-side component cannot remove its own supervision. Nesting is handled
    by a policy stack, and the hook is inert when the stack is empty.
    """
    monitor = monitor or IntegrityMonitor()
    policy.scratch_dir.mkdir(parents=True, exist_ok=True)
    _install_hook()
    _ACTIVE.append((policy, monitor))
    try:
        yield monitor
    finally:
        _ACTIVE.pop()


#: Environment variable naming where the frozen evaluation assets are mounted. The container
#: puts them somewhere unrelated to the source tree (see this package's `Dockerfile`), so a
#: policy that knows only the in-repo path protects nothing in the deployment the image exists
#: to provide.
HIDDEN_ROOT_ENV = "BESTSAD_HIDDEN_ROOT"


def default_policy(scratch_dir: Path, repo_root: Path | None = None) -> SandboxPolicy:
    """The standard policy: hidden evaluator assets are unreadable, no network, no subprocess.

    Both the in-repo `hidden_evaluator/` and any path named by `$BESTSAD_HIDDEN_ROOT` are
    protected. Resolve this in the *parent*: `run_isolated` clears the child's environment, so a
    policy built inside the child would find the variable gone and silently protect less.
    """
    root = repo_root or Path(__file__).resolve().parents[3]
    protected = [root / "hidden_evaluator"]
    configured = os.environ.get(HIDDEN_ROOT_ENV)
    if configured:
        mounted = Path(configured)
        if mounted not in protected:
            protected.append(mounted)
    return SandboxPolicy(
        scratch_dir=scratch_dir,
        protected_paths=tuple(protected),
    )
