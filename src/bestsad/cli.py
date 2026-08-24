"""`bestsad` command line (integration spec §12).

    bestsad assure claim show <id>
    bestsad assure graph <id>
    bestsad assure verify <artifact>
    bestsad assure stale
    bestsad assure roots
    bestsad primitive explain <id>
    bestsad experiment claims <run-id>
    bestsad report --confirmatory <run-id>   # hard-fails if promotion dependencies fail

`report --confirmatory` exits non-zero when the promotion predicate refuses. That is the point:
a build step or CI job invoking it cannot accidentally publish a confirmatory claim whose
controls did not hold, because the command fails rather than printing a warning nobody reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .assurance import (
    AssuranceLedger,
    ClaimState,
    current_roots,
)

DEFAULT_LEDGER = Path("artifacts/assurance_ledger.json")

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_NOT_FOUND = 3


def _load_ledger(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"no assurance ledger at {path}")
    return json.loads(path.read_text())


def _emit(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


# --- assure ------------------------------------------------------------------------------------


def cmd_assure_claim_show(args) -> int:
    data = _load_ledger(args.ledger)
    claim = data["claims"].get(args.claim_id)
    if claim is None:
        print(f"no such claim: {args.claim_id}", file=sys.stderr)
        return EXIT_NOT_FOUND
    _emit(claim)
    return EXIT_OK


def cmd_assure_graph(args) -> int:
    data = _load_ledger(args.ledger)
    edges = [e for e in data["dependency_edges"] if e["from_id"] == args.node]
    dependents = [e["from_id"] for e in data["dependency_edges"] if e["to_id"] == args.node]
    _emit({"node": args.node, "depends_on": edges, "dependents": sorted(set(dependents))})
    return EXIT_OK


def cmd_assure_stale(args) -> int:
    """List claims that must not silently enter an execution context (§1.7)."""
    data = _load_ledger(args.ledger)
    blocked = {
        cid: claim for cid, claim in data["claims"].items()
        if claim["status"] in ("STALE", "QUARANTINED", "INVALIDATED")
    }
    _emit({"count": len(blocked), "claims": blocked})
    # Non-zero when anything is stale, so a pipeline can gate on it.
    return EXIT_REFUSED if blocked else EXIT_OK


def cmd_assure_roots(args) -> int:
    """Print the live content id of every semantic root (§1.6, §4)."""
    roots = current_roots()
    _emit(roots.values)
    return EXIT_OK


def cmd_assure_verify(args) -> int:
    """Check an artifact's recorded source hashes against the live roots.

    A drifted root means every certificate beneath it is stale, whether or not anything has
    re-checked it — which is exactly the Atlas failure mode this protocol exists to close.
    """
    artifact = json.loads(Path(args.artifact).read_text())
    recorded = artifact.get("source_hashes") or artifact.get("assurance", {}).get(
        "source_hashes", {}
    )
    if not recorded:
        print("artifact carries no source hashes to verify", file=sys.stderr)
        return EXIT_NOT_FOUND
    live = current_roots().values
    drifted = {
        name: {"recorded": value, "live": live.get(name)}
        for name, value in recorded.items()
        if name in live and live[name] != value
    }
    _emit({"artifact": args.artifact, "drifted_roots": drifted,
           "verdict": "STALE" if drifted else "CURRENT"})
    return EXIT_REFUSED if drifted else EXIT_OK


# --- primitive / experiment ---------------------------------------------------------------------


def cmd_primitive_explain(args) -> int:
    """The explainable dependency path from a primitive to its evidence and roots (§1.7)."""
    data = _load_ledger(args.ledger)
    claims = {
        cid: c for cid, c in data["claims"].items()
        if args.primitive_id in (c.get("subject_refs") or [])
    }
    if not claims:
        print(f"no claims reference primitive {args.primitive_id}", file=sys.stderr)
        return EXIT_NOT_FOUND
    evidence = {
        eid: e for eid, e in data["evidence"].items()
        if any(eid in (c.get("evidence_refs") or []) for c in claims.values())
    }
    _emit({"primitive_id": args.primitive_id, "claims": claims, "evidence": evidence})
    return EXIT_OK


def cmd_experiment_claims(args) -> int:
    data = _load_ledger(args.ledger)
    claims = {
        cid: c for cid, c in data["claims"].items()
        if c.get("scope", {}).get("run_id") == args.run_id
        or args.run_id in (c.get("subject_refs") or [])
        or c.get("detail", {}).get("run_id") == args.run_id
    }
    _emit({"run_id": args.run_id, "claims": claims})
    return EXIT_OK


def cmd_report(args) -> int:
    """Emit a report, hard-failing when promotion dependencies do not hold."""
    data = _load_ledger(args.ledger)
    claims = [
        c for c in data["claims"].values()
        if c.get("claim_class") in ("capability", "negative_result")
        and (c.get("detail", {}).get("run_id") == args.run_id or args.run_id in
             (c.get("subject_refs") or []) or not args.run_id)
    ]
    promoted = [c for c in claims if c["status"] == "PROMOTED"]
    blocked = [c for c in claims if c["status"] in ("STALE", "QUARANTINED", "INVALIDATED")]

    if args.confirmatory and not promoted:
        print(
            "refusing to emit a confirmatory report: no promoted claim for this run. "
            "A confirmatory report is generated only from promoted top-level claims "
            "(integration spec §15, M9).",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    if args.confirmatory and blocked:
        print(
            f"refusing to emit a confirmatory report: {len(blocked)} claim(s) are stale, "
            "quarantined or invalidated.",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    _emit({"run_id": args.run_id, "confirmatory": args.confirmatory,
           "promoted_claims": promoted, "blocked_claims": blocked})
    return EXIT_OK


# --- parser --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bestsad", description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                        help=f"path to the assurance ledger (default: {DEFAULT_LEDGER})")
    sub = parser.add_subparsers(dest="group", required=True)

    assure = sub.add_parser("assure", help="assurance ledger queries").add_subparsers(
        dest="action", required=True
    )

    claim = assure.add_parser("claim", help="claim operations").add_subparsers(
        dest="claim_action", required=True
    )
    show = claim.add_parser("show", help="show a claim")
    show.add_argument("claim_id")
    show.set_defaults(func=cmd_assure_claim_show)

    graph = assure.add_parser("graph", help="show a node's dependency neighbourhood")
    graph.add_argument("node")
    graph.set_defaults(func=cmd_assure_graph)

    verify = assure.add_parser("verify", help="check an artifact's roots against live values")
    verify.add_argument("artifact")
    verify.set_defaults(func=cmd_assure_verify)

    stale = assure.add_parser("stale", help="list stale/quarantined/invalidated claims")
    stale.set_defaults(func=cmd_assure_stale)

    roots = assure.add_parser("roots", help="print live semantic root content ids")
    roots.set_defaults(func=cmd_assure_roots)

    primitive = sub.add_parser("primitive", help="primitive operations").add_subparsers(
        dest="action", required=True
    )
    explain = primitive.add_parser("explain", help="explain a primitive's assurance path")
    explain.add_argument("primitive_id")
    explain.set_defaults(func=cmd_primitive_explain)

    experiment = sub.add_parser("experiment", help="experiment operations").add_subparsers(
        dest="action", required=True
    )
    claims = experiment.add_parser("claims", help="claims for a run")
    claims.add_argument("run_id")
    claims.set_defaults(func=cmd_experiment_claims)

    report = sub.add_parser("report", help="emit a report")
    report.add_argument("run_id", nargs="?", default="")
    report.add_argument("--confirmatory", action="store_true",
                        help="hard-fail if promotion dependencies do not hold")
    report.set_defaults(func=cmd_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
