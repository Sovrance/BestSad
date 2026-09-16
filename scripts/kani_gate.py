#!/usr/bin/env python3
"""The K0 twin proof gate (BEST-VERIF-05, ADR-0020): `cargo kani` on `k0rs/`, held to the budget.

What "green" means here, in the design document's own words: *`cargo kani` green on all
harnesses within a 60 s per-harness budget (harnesses exceeding it are split, not loosened)*.
So this gate fails on any of:

* a harness that is not `VERIFICATION:- SUCCESSFUL`;
* a harness whose reported verification time exceeds the budget (`--budget-s`, default 60);
* a run that ends with fewer harnesses than the crate declares (`#[kani::proof]` count), which
  is what a crash or a kill looks like from the outside.

It then writes the run as the report shape `bestsad.verify.external.from_kani_report` accepts
(`--report`), and ingests that report itself, so the file the gate leaves behind is known to be
consumable as external FORMAL evidence rather than assumed to be. The verdict recorded there
is bounded by the harnesses' `kani::unwind` bounds and by `any_k0_int`'s assumption that
operands lie within the ADR-0008 integer bound; the report says so in `assumptions`.

Exit codes: 0 green; 1 a harness failed or ran over budget; 2 could not run (no `cargo kani`).
The local runner (`scripts/ci_local.py`) probes `cargo kani --version` first, so there the
"could not run" case reports UNAVAILABLE rather than reaching exit code 2.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CRATE = REPO / "k0rs"
PROOFS = CRATE / "src" / "proofs.rs"
sys.path.insert(0, str(REPO / "src"))

TIME_LINE = re.compile(r"^Verification Time:\s*(?P<secs>[0-9.]+)s", re.M)
HARNESS_LINE = re.compile(r"^Checking harness (?P<name>\S+?)\.\.\.", re.M)
ASSUMPTIONS = (
    "bounded: every loop is unwound to the kani::unwind(N) stated on its harness",
    "operands drawn by any_k0_int() lie within the ADR-0008 integer bound (|v| <= 2^64)",
    "unchecked: aliasing/provenance UB (Miri covers the Rust test loop), concurrency (none in K0)",
)


def declared_harnesses() -> int:
    return PROOFS.read_text(encoding="utf-8").count("#[kani::proof]")


def per_harness_times(output: str) -> list[tuple[str, float | None]]:
    """(harness, seconds) in run order; None when a harness never reported a time."""
    out: list[tuple[str, float | None]] = []
    blocks = HARNESS_LINE.split(output)
    # split() yields [preamble, name1, body1, name2, body2, ...]
    for i in range(1, len(blocks) - 1, 2):
        name, body = blocks[i], blocks[i + 1]
        m = TIME_LINE.search(body)
        out.append((name, float(m.group("secs")) if m else None))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--budget-s", type=float, default=60.0, help="per-harness budget (design doc: 60)")
    ap.add_argument("--report", type=Path, default=REPO / "k0rs" / "target" / "kani_report.json",
                    help="where to write the from_kani_report-shaped JSON")
    ap.add_argument("--kani-output", type=Path, default=None,
                    help="parse this saved `cargo kani` output instead of running it")
    args = ap.parse_args()

    if args.kani_output is not None:
        output = args.kani_output.read_text(encoding="utf-8")
        version = "unknown"
    else:
        if shutil.which("cargo") is None:
            print("kani gate: cargo is not installed", file=sys.stderr)
            return 2
        ver = subprocess.run(["cargo", "kani", "--version"], capture_output=True, text=True)
        if ver.returncode != 0:
            print("kani gate: `cargo kani` is not installed or not set up", file=sys.stderr)
            return 2
        version = ver.stdout.strip().split()[-1] if ver.stdout.strip() else "unknown"
        run = subprocess.run(["cargo", "kani", "--manifest-path", str(CRATE / "Cargo.toml")],
                             capture_output=True, text=True)
        output = run.stdout + "\n" + run.stderr
        sys.stdout.write(run.stdout)

    from bestsad.kernel import KERNEL_VERSION_HASH
    from bestsad.verify.external import from_kani_report
    from bestsad.verify.twin import kani_report_from_output

    report = kani_report_from_output(output, kani_version=version, assumptions=ASSUMPTIONS)
    times = dict(per_harness_times(output))
    for entry in report["harnesses"]:
        entry["seconds"] = times.get(entry["name"])

    problems: list[str] = []
    expected = declared_harnesses()
    if len(report["harnesses"]) != expected:
        problems.append(f"{len(report['harnesses'])} harnesses reported, {expected} declared in {PROOFS.name}")
    for entry in report["harnesses"]:
        secs = entry["seconds"]
        if entry["status"] != "SUCCESS":
            problems.append(f"{entry['name']}: {entry['status']}")
        elif secs is None:
            problems.append(f"{entry['name']}: no verification time reported")
        elif secs > args.budget_s:
            problems.append(f"{entry['name']}: {secs:.1f}s exceeds the {args.budget_s:.0f}s budget (split it, do not loosen it)")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ingested = from_kani_report(report, kernel_version_hash=KERNEL_VERSION_HASH)

    print()
    print(f"kani gate: {len(report['harnesses'])} harnesses, kani {version}, verdict as evidence: {ingested.verdict}")
    for entry in report["harnesses"]:
        secs = entry["seconds"]
        shown = f"{secs:6.1f}s" if secs is not None else "     -"
        print(f"  {shown}  {entry['status']:<12} {entry['name']}")
    print(f"  report: {args.report}")
    if problems:
        print("\nkani gate: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"\nkani gate: OK (every harness green within {args.budget_s:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
