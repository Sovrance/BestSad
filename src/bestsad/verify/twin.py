"""The Rust twin of K0 (`k0rs/`, BEST-VERIF-05, ADR-0020) as seen from Python.

The Python reference in `bestsad.kernel` is **normative**. The twin is a second implementation
that a bounded model checker (Kani) can say things about which no tool can say about the
Python; its *agreement* with the reference is a corroborated fact established by running both
over the same M1 corpus (`tests/verify/test_k0_twin.py`), never a proven one. If the two ever
disagree, the Python wins and the twin is fixed.

This module is deliberately thin:

* `find_binary` / `build_binary` / `probe` -- locate (or build with cargo) the `k0rs` binary and
  check that the hash it computes from its own op table equals `KERNEL_VERSION_HASH`. A twin
  with a different hash is not a twin of *this* kernel and is refused, whatever else it does.
* `TwinRunner` -- drive `k0rs run` over a JSON line protocol and hand back the reference's own
  `ExecutionResult` type so `same_outcome` compares the two implementations on the reference's
  definition of correctness (value equality or same trap kind). Step counts are carried too;
  the sweep compares them because the ADR-0008 cost model is the property the twin exists to
  make checkable. Trace hashes are *not* on the wire: they are an artefact of the Python
  evaluator's record order, not of K0.
* `kani_report_from_output` -- turn the text `cargo kani` prints into the narrow report shape
  `bestsad.verify.external.from_kani_report` ingests (Kani 0.67 has no JSON output format).

Nothing here imports from, or is imported by, `bestsad.kernel`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..kernel import KERNEL_VERSION_HASH, ExecutionResult, Program, Term
from ..kernel.traps import Trap, TrapKind
from ..kernel.values import NOTHING, Closure, Just, Pair

REPO_ROOT = Path(__file__).resolve().parents[3]
CRATE_DIR = REPO_ROOT / "k0rs"
MANIFEST = CRATE_DIR / "Cargo.toml"
ENV_BINARY = "K0RS_BIN"


class TwinUnavailable(RuntimeError):
    """The twin binary cannot be found, built, or does not compute this kernel's hash."""


class TwinProtocolError(RuntimeError):
    """The twin answered with a request-level error (not a K0 trap) or malformed output."""


# --- locating and checking the binary ---------------------------------------------------------


def find_binary() -> Path | None:
    """The `k0rs` binary: `$K0RS_BIN`, then `k0rs` on PATH, then the crate's own target dir."""
    override = os.environ.get(ENV_BINARY)
    if override:
        p = Path(override)
        return p if p.is_file() else None
    on_path = shutil.which("k0rs")
    if on_path:
        return Path(on_path)
    for profile in ("release", "debug"):
        candidate = CRATE_DIR / "target" / profile / "k0rs"
        if candidate.is_file():
            return candidate
    return None


def build_binary(*, timeout_s: float = 900.0) -> Path | None:
    """Build the crate with cargo (release profile). None if cargo is absent or the build fails.

    `build.rs` refuses to compile the crate unless its hash equals the Python constant, so a
    successful build is already the first half of `probe`.
    """
    cargo = shutil.which("cargo")
    if cargo is None or not MANIFEST.is_file():
        return None
    try:
        done = subprocess.run(
            [cargo, "build", "--release", "--quiet", "--manifest-path", str(MANIFEST)],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    candidate = CRATE_DIR / "target" / "release" / "k0rs"
    return candidate if candidate.is_file() else None


def twin_hash(binary: Path) -> str | None:
    """What the binary says its kernel hash is, or None if it cannot say."""
    try:
        done = subprocess.run([str(binary), "hash"], capture_output=True, text=True,
                              timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def locate(*, build: bool = True) -> Path:
    """A binary whose hash equals `KERNEL_VERSION_HASH`, building it if allowed and needed."""
    binary = find_binary()
    if binary is None and build:
        binary = build_binary()
    if binary is None:
        raise TwinUnavailable(
            f"no k0rs binary: set ${ENV_BINARY}, put k0rs on PATH, or build {MANIFEST}"
        )
    found = twin_hash(binary)
    if found != KERNEL_VERSION_HASH:
        raise TwinUnavailable(
            f"{binary} computes kernel hash {found!r}, the reference is {KERNEL_VERSION_HASH!r}"
        )
    return binary


def probe(*, build: bool = True) -> bool:
    """True iff a hash-matching twin binary is usable. Never raises."""
    try:
        locate(build=build)
    except TwinUnavailable:
        return False
    return True


# --- the wire ---------------------------------------------------------------------------------


def term_to_wire(term: Term) -> dict[str, Any]:
    """The `WireTerm` shape `k0rs::wire` deserialises. Integers travel as decimal strings."""
    attrs: dict[str, Any] = {}
    if term.op == "const_int":
        attrs["value"] = str(int(term.attr("value")))
    elif term.op == "const_bool":
        attrs["value"] = bool(term.attr("value"))
    elif term.op == "var":
        attrs["name"] = term.attr("name")
    elif term.op == "lam":
        attrs["params"] = [[name, str(ty)] for name, ty in term.attr("params")]
    elif term.op in ("nil", "none"):
        attrs["elem_type"] = str(term.attr("elem_type"))
    out: dict[str, Any] = {"op": term.op, "args": [term_to_wire(a) for a in term.args]}
    if attrs:
        out["attrs"] = attrs
    return out


def value_to_wire(value: Any) -> Any:
    if isinstance(value, bool):
        return {"Bool": value}
    if isinstance(value, int):
        return {"Int": str(value)}
    if isinstance(value, (tuple, list)):
        return {"List": [value_to_wire(v) for v in value]}
    if isinstance(value, Pair):
        return {"Pair": [value_to_wire(value.fst), value_to_wire(value.snd)]}
    if isinstance(value, Just):
        return {"Some": value_to_wire(value.value)}
    if value is NOTHING or value == NOTHING:
        return "None"
    if isinstance(value, Closure):
        raise TwinProtocolError("a closure is not a data value and cannot cross the wire")
    raise TwinProtocolError(f"cannot encode {type(value).__name__} for the twin")


def value_from_wire(w: Any) -> Any:
    if w == "None":
        return NOTHING
    if not isinstance(w, dict) or len(w) != 1:
        raise TwinProtocolError(f"malformed wire value {w!r}")
    (tag, payload), = w.items()
    if tag == "Int":
        return int(payload)
    if tag == "Bool":
        return bool(payload)
    if tag == "List":
        return tuple(value_from_wire(v) for v in payload)
    if tag == "Pair":
        a, b = payload
        return Pair(value_from_wire(a), value_from_wire(b))
    if tag == "Some":
        return Just(value_from_wire(payload))
    raise TwinProtocolError(f"unknown wire value tag {tag!r}")


def request(program: Program, inputs: Sequence[Any], *, fuel: int | None = None,
            depth_limit: int | None = None) -> dict[str, Any]:
    req: dict[str, Any] = {
        "params": [[name, str(ty)] for name, ty in program.params],
        "body": term_to_wire(program.body),
        "inputs": [value_to_wire(v) for v in inputs],
    }
    if fuel is not None:
        req["fuel"] = int(fuel)
    if depth_limit is not None:
        req["depth_limit"] = int(depth_limit)
    return req


def result_from_response(resp: dict[str, Any]) -> ExecutionResult:
    if resp.get("error") is not None:
        raise TwinProtocolError(str(resp["error"]))
    steps = int(resp.get("steps", 0))
    if resp.get("trap") is not None:
        return ExecutionResult(trap=Trap(TrapKind(resp["trap"])), steps=steps, fuel_used=steps)
    return ExecutionResult(value=value_from_wire(resp.get("ok")), steps=steps, fuel_used=steps)


# --- the runner -------------------------------------------------------------------------------


@dataclass
class TwinRunner:
    """One long-lived `k0rs run` process; `execute` mirrors `Kernel.execute`'s signature.

    Use as a context manager. `fuel` and `depth_limit` are the runner's defaults, as on
    `Kernel(...)`; a per-call `fuel=` overrides, as on `Kernel.execute`.
    """

    fuel: int | None = None
    depth_limit: int | None = None
    binary: Path | None = None
    build: bool = True

    def __post_init__(self) -> None:
        if self.binary is None:
            self.binary = locate(build=self.build)
        self._proc: subprocess.Popen[str] | None = None

    def __enter__(self) -> "TwinRunner":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        if self._proc is None:
            self._proc = subprocess.Popen(
                [str(self.binary), "run"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1,
            )

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()
        for stream in (proc.stdout, proc.stderr):
            if stream:
                stream.close()

    def execute(self, program: Program, inputs: Sequence[Any], *,
                fuel: int | None = None) -> ExecutionResult:
        if self._proc is None:
            self.start()
        proc = self._proc
        assert proc is not None and proc.stdin is not None and proc.stdout is not None
        line = json.dumps(
            request(program, inputs, fuel=fuel if fuel is not None else self.fuel,
                    depth_limit=self.depth_limit),
            separators=(",", ":"),
        )
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            answer = proc.stdout.readline()
        except (OSError, ValueError) as exc:
            raise TwinProtocolError(f"twin process died: {exc}") from None
        if not answer:
            err = proc.stderr.read() if proc.stderr else ""
            self.close()
            raise TwinProtocolError(f"twin closed the stream: {err.strip()}")
        try:
            resp = json.loads(answer)
        except json.JSONDecodeError as exc:
            raise TwinProtocolError(f"twin answered non-JSON: {answer!r} ({exc})") from None
        return result_from_response(resp)


def execute(program: Program, inputs: Sequence[Any], *, fuel: int | None = None) -> ExecutionResult:
    """One-shot convenience: spawn the twin, run once, close it."""
    with TwinRunner() as twin:
        return twin.execute(program, inputs, fuel=fuel)


# --- Kani output -> the external-result report shape ------------------------------------------

_HARNESS_LINE = re.compile(r"^Checking harness (?P<name>\S+?)\.\.\.\s*$")
_VERDICT_LINE = re.compile(r"^VERIFICATION:-\s*(?P<verdict>SUCCESSFUL|FAILED|UNDETERMINED)")
_UNWIND_LINE = re.compile(r"kani::unwind\((?P<n>\d+)\)")


def kani_report_from_output(text: str, *, kani_version: str, unwind: int | None = None,
                            assumptions: Sequence[str] = ()) -> dict[str, Any]:
    """Parse `cargo kani` (regular output format) into the shape `from_kani_report` accepts.

    Each `Checking harness NAME...` block ends in a `VERIFICATION:- SUCCESSFUL|FAILED` line;
    a harness whose block never reached a verdict (killed, timed out) is `UNDETERMINED`, which
    `from_kani_report` maps to `unknown`, never to `proved`.
    """
    harnesses: list[dict[str, str]] = []
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _HARNESS_LINE.match(line)
        if m:
            if current is not None:
                harnesses.append({"name": current, "status": "UNDETERMINED"})
            current = m.group("name")
            continue
        v = _VERDICT_LINE.match(line)
        if v and current is not None:
            status = {"SUCCESSFUL": "SUCCESS", "FAILED": "FAILURE"}.get(v.group("verdict"),
                                                                       "UNDETERMINED")
            harnesses.append({"name": current, "status": status})
            current = None
    if current is not None:
        harnesses.append({"name": current, "status": "UNDETERMINED"})
    report: dict[str, Any] = {"harnesses": harnesses, "kani_version": kani_version}
    if unwind is not None:
        report["unwind"] = int(unwind)
    if assumptions:
        report["assumptions"] = list(assumptions)
    return report


__all__ = [
    "CRATE_DIR",
    "ENV_BINARY",
    "MANIFEST",
    "TwinProtocolError",
    "TwinRunner",
    "TwinUnavailable",
    "build_binary",
    "execute",
    "find_binary",
    "kani_report_from_output",
    "locate",
    "probe",
    "request",
    "result_from_response",
    "term_to_wire",
    "twin_hash",
    "value_from_wire",
    "value_to_wire",
]
