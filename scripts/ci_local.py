#!/usr/bin/env python3
"""The CI gates from `.github/workflows/ci.yml`, runnable without GitHub Actions.

    python3 scripts/ci_local.py               # every gate
    python3 scripts/ci_local.py --gate tests  # one gate
    python3 scripts/ci_local.py --list

Why this exists
---------------
The repository's Actions runners are unavailable and, by owner decision, will not be paid
for (ADR 0018). Every job in `ci.yml` therefore completes in seconds with no runner assigned,
no steps executed, and no logs -- a red check that carries no information about the code.

`ci.yml` is deliberately left in place: it is correct, and it will work again if runners ever
return. But a gate that exists only as configuration for a system nobody invokes is not a
gate, so the same jobs are exposed here as something a person or an agent can actually run.

What this is not
----------------
This is not a replacement for CI, and the report says so. Two things are genuinely lost by
running gates on the same machine that wrote the code:

* **independence** -- CI is a second opinion from a machine with no stake in the change; this
  is the author checking their own work, which is weaker evidence and should be read that way;
* **environment isolation** -- CI starts from a clean image, so it catches "passes only
  because of something already installed here". `--fresh-venv` recovers part of that.

An unrun gate is never reported as a passing gate. A gate whose tooling is missing (Docker,
typically) is reported UNAVAILABLE and the overall result is INCOMPLETE, never OK -- silence
about a check that did not run is exactly how an unverified claim becomes a verified one.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Gate:
    """One job from `ci.yml`, with the command that job actually runs."""

    name: str
    ci_job: str
    command: list[str]
    #: A probe proving the gate's external tooling actually works, not merely that a binary
    #: is on PATH. `shutil.which("docker")` succeeds on a machine whose daemon is not
    #: running, and the gate then fails for a reason that has nothing to do with the code --
    #: which is the exact confusion between "did not run" and "ran and found a problem" that
    #: this script exists to keep apart.
    probe: tuple[str, list[str]] | None = None  # (tool name, command)
    note: str = ""


GATES: tuple[Gate, ...] = (
    Gate(
        "tests",
        "tests",
        [sys.executable, "-m", "pytest", "-q", "-m", "not slow"],
        note="the full suite minus the slow sweep, which is its own gate",
    ),
    Gate(
        "integrity",
        "evaluator integrity (Gate G1)",
        [sys.executable, "-m", "pytest", "-q", "tests/integrity"],
        note="trust boundary and anti-gaming; separate so a regression is its own failure",
    ),
    Gate(
        "kernel-sweep",
        "K0 differential sweep (Gate G0)",
        [sys.executable, "-m", "pytest", "-q", "-m", "slow", "tests/kernel"],
        note="the differential sweep required by implementation plan M1",
    ),
    Gate(
        "assurance",
        "assurance protocol (§14 acceptance)",
        [sys.executable, "-m", "pytest", "-q", "tests/assurance"],
        note="producers cannot promote themselves; controls bind promotion",
    ),
    Gate(
        "schemas",
        "schema validation",
        [sys.executable, "-m", "pytest", "-q", "tests/schemas"],
        note="emitted records validate against schemas/",
    ),
    Gate(
        "evaluator-image",
        "evaluator image (spec §27.1 deployment half)",
        ["bash", str(REPO / "scripts" / "evaluator_image_gate.sh")],
        probe=("docker", ["docker", "info"]),
        note=(
            "builds the evaluator image and then asserts what it does not contain and cannot "
            "do: no hidden evaluation assets, uid 10001, and a read-only start with no network "
            "and no capabilities. Building alone proves none of that -- the image's value is "
            "in the three checks after the build, so the gate runs all four steps or none."
        ),
    ),
)

BY_NAME = {g.name: g for g in GATES}

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"


def run_gate(gate: Gate, python: str | None = None) -> tuple[str, str]:
    """Run one gate. Returns `(status, detail)`."""
    if gate.probe is not None:
        tool, probe_command = gate.probe
        if shutil.which(probe_command[0]) is None:
            return UNAVAILABLE, f"{tool} is not installed on this machine"
        probed = subprocess.run(probe_command, capture_output=True, text=True)
        if probed.returncode != 0:
            reason = (probed.stderr or probed.stdout).strip().splitlines()
            detail = reason[-1] if reason else f"exit code {probed.returncode}"
            return UNAVAILABLE, f"{tool} is installed but not usable: {detail}"

    command = list(gate.command)
    if python is not None and command and command[0] == sys.executable:
        command[0] = python

    print(f"== {gate.name} ({gate.ci_job}) ==", flush=True)
    print(f"    $ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=str(REPO))
    if completed.returncode == 0:
        return PASS, ""
    return FAIL, f"exit code {completed.returncode}"


def fresh_venv(path: Path) -> str:
    """Build a clean virtualenv and install the project into it, as CI would.

    Recovers the part of CI this script otherwise loses: a gate passing only because of
    something already present in the working environment.
    """
    print(f"== preparing a fresh environment in {path} ==", flush=True)
    subprocess.run([sys.executable, "-m", "venv", str(path)], check=True)
    python = str(path / "bin" / "python")
    subprocess.run([python, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([python, "-m", "pip", "install", "-q", "-e", ".[dev]"],
                   cwd=str(REPO), check=True)
    print("   environment ready\n", flush=True)
    return python


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--gate", action="append", choices=[*BY_NAME], default=None)
    parser.add_argument("--list", action="store_true", help="list the gates and exit")
    parser.add_argument("--fresh-venv", metavar="PATH",
                        help="install into a clean virtualenv first, as CI does")
    args = parser.parse_args()

    if args.list:
        for gate in GATES:
            marker = f"  (needs {gate.probe[0]})" if gate.probe else ""
            print(f"  {gate.name:<16} {gate.ci_job}{marker}")
        return 0

    selected = [BY_NAME[n] for n in args.gate] if args.gate else list(GATES)
    python = fresh_venv(Path(args.fresh_venv)) if args.fresh_venv else None

    results: list[tuple[Gate, str, str]] = []
    for gate in selected:
        status, detail = run_gate(gate, python)
        results.append((gate, status, detail))
        print(flush=True)

    print("=" * 74)
    for gate, status, detail in results:
        suffix = f"  -- {detail}" if detail else ""
        print(f"  {status:<12} {gate.name:<16} {gate.ci_job}{suffix}")
    print("=" * 74)

    failed = [g.name for g, s, _ in results if s == FAIL]
    unavailable = [g.name for g, s, _ in results if s == UNAVAILABLE]

    if failed:
        print(f"\nLOCAL GATES: FAIL ({', '.join(failed)})", file=sys.stderr)
        return 1
    if unavailable:
        # Not OK. The distinction is the whole point: these gates did not run, and reporting
        # them as passing would turn missing tooling into evidence of correctness.
        print(f"\nLOCAL GATES: INCOMPLETE -- {len(unavailable)} gate(s) could not run "
              f"({', '.join(unavailable)}); the rest passed", file=sys.stderr)
        return 2
    print(f"\nLOCAL GATES: OK ({len(results)} gates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
