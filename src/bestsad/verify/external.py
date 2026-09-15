"""External prover results as assurance evidence (BEST-VERIF-03; closes BEST-ASSURE-10).

A prover result -- Z3 driven by this package, a Kani report on the K0 twin when BEST-VERIF-05
gates in, an Alive2 or Lean verdict when M12/V6 arrive -- becomes an `EvidenceObject` with
`warrant=FORMAL`, `is_external=True` (its `source` carries the `external:` prefix), a `method`
naming the tool and version, and `content_hash` of the raw artifact.

What this module does **not** do is make such evidence sufficient. The assurance plane's rule
(§1.7, `NEVER_SUFFICIENT_ALONE`) is that external corroboration is never silently upgraded to
internal proof, and the promotion predicate enforces it: a semantic-equivalence claim whose
proof is external is promotable only with the Tier 3 dynamic result on the same contract
attached as internal corroboration (`assurance/promotion.py`). Z3 counts as external even when
BestSad drives it -- the engine is third-party, and the encoder it checks is a second reading
of K0 rather than K0 itself (ADR-0019).

Every result carries the K0 version hash it was produced against. A result about a different
kernel is stale by construction: the claim built from it records the stale root, and the
predicate's source-hash check refuses it (the pattern of acceptance test 10).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from ..assurance.claims import make_evidence
from ..assurance.objects import EvidenceObject, Warrant
from ..kernel.spec import KERNEL_VERSION_HASH
from ..sre.ids import BARE_DIGEST_RE

PROVENANCE_INTERNAL_SOLVER = "internal-solver"
PROVENANCE_KANI = "kani"
PROVENANCE_GENERIC = "generic"

Verdict = Literal["proved", "refuted", "unknown"]
_VERDICTS = ("proved", "refuted", "unknown")


class ExternalResultError(ValueError):
    """A prover result could not be ingested. Raised rather than approximated: an artifact the
    adapter cannot read is not evidence of anything."""


@dataclass(frozen=True, slots=True)
class ExternalResult:
    """A structured prover result, whatever produced it."""

    tool: str
    version: str
    verdict: Verdict
    #: Bare hex sha256 of the raw artifact (SMT-LIB2 text, the Kani report, ...).
    artifact_sha256: str
    scope: dict[str, Any]
    assumptions: tuple[str, ...]
    provenance: str
    #: The K0 hash the result was produced against. Compared to the live kernel at claim time.
    kernel_version_hash: str
    subject_refs: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verdict not in _VERDICTS:
            raise ExternalResultError(f"verdict must be one of {_VERDICTS}, got {self.verdict!r}")
        if not BARE_DIGEST_RE.match(self.artifact_sha256):
            raise ExternalResultError("artifact_sha256 must be a bare 64-character hex digest")
        if not BARE_DIGEST_RE.match(self.kernel_version_hash):
            raise ExternalResultError("kernel_version_hash must be a bare 64-character hex digest")
        if not self.tool or not self.version:
            raise ExternalResultError("tool and version are required; anonymous proofs are not evidence")

    @property
    def is_stale(self) -> bool:
        """True when the result was produced against a K0 other than the one running now."""
        return self.kernel_version_hash != KERNEL_VERSION_HASH

    def to_record(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "version": self.version,
            "verdict": self.verdict,
            "artifact_sha256": self.artifact_sha256,
            "scope": dict(self.scope),
            "assumptions": list(self.assumptions),
            "provenance": self.provenance,
            "kernel_version_hash": self.kernel_version_hash,
            "subject_refs": list(self.subject_refs),
            "detail": dict(self.detail),
        }


# -- ingestion ----------------------------------------------------------------------------------


def from_symbolic_result(result: Any, *, kernel_version_hash: str = KERNEL_VERSION_HASH) -> ExternalResult:
    """The BestSad SMT analyzer result (BEST-VERIF-02) as an external result.

    Provenance `internal-solver`, and still external: the engine is Z3 (ADR-0019 §"what is
    lost", point 4).
    """
    status = result.status
    verdict: Verdict = {"equiv": "proved", "non_equiv": "refuted", "unknown": "unknown"}[status]
    smt2 = result.analyzer_result.get("coverage", {}).get("smtlib2", "") if result.analyzer_result else ""
    return ExternalResult(
        tool="z3",
        version=result.solver_version or "unknown",
        verdict=verdict,
        artifact_sha256=hashlib.sha256(smt2.encode("utf-8")).hexdigest(),
        scope=dict(result.scope),
        assumptions=tuple(result.assumptions),
        provenance=PROVENANCE_INTERNAL_SOLVER,
        kernel_version_hash=kernel_version_hash,
        subject_refs=tuple(result.analyzer_result.get("inputs", ())) if result.analyzer_result else (),
        detail={
            "analyzer_result_ref": result.analyzer_result_id,
            "verification_coverage": result.verification_coverage,
            "coverage_basis": result.coverage_basis,
            "reason": result.reason,
        },
    )


#: Harness statuses a Kani report may carry, and what they mean here.
_KANI_STATUS = {"SUCCESS": "proved", "FAILURE": "refuted", "UNDETERMINED": "unknown",
                "UNREACHABLE": "unknown"}


def from_kani_report(
    report: str | Mapping[str, Any],
    *,
    kernel_version_hash: str,
    kani_version: str | None = None,
) -> ExternalResult:
    """A Kani JSON report as an external result (provenance `kani`).

    The shape accepted is deliberately narrow and stated here, because no Kani run exists yet
    to calibrate against (BEST-VERIF-05 is gated): a mapping with `harnesses`, a list of
    `{name, status}` entries whose status is one of SUCCESS / FAILURE / UNDETERMINED /
    UNREACHABLE, optionally `kani_version`, `unwind` (the `kani::unwind(N)` bound) and
    `assumptions`. The verdict is `proved` only if every harness succeeded, `refuted` if any
    failed, `unknown` otherwise. Anything else is refused rather than guessed.
    """
    raw = report if isinstance(report, str) else json.dumps(report, sort_keys=True, separators=(",", ":"))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalResultError(f"Kani report is not JSON: {exc}") from None
    if not isinstance(data, Mapping) or not isinstance(data.get("harnesses"), list) or not data["harnesses"]:
        raise ExternalResultError("Kani report must carry a non-empty `harnesses` list")
    statuses: list[str] = []
    names: list[str] = []
    for entry in data["harnesses"]:
        if not isinstance(entry, Mapping) or "name" not in entry or "status" not in entry:
            raise ExternalResultError("each Kani harness entry needs `name` and `status`")
        status = str(entry["status"]).upper()
        if status not in _KANI_STATUS:
            raise ExternalResultError(f"unknown Kani harness status {entry['status']!r}")
        statuses.append(status)
        names.append(str(entry["name"]))
    if all(s == "SUCCESS" for s in statuses):
        verdict: Verdict = "proved"
    elif any(s == "FAILURE" for s in statuses):
        verdict = "refuted"
    else:
        verdict = "unknown"
    version = kani_version or str(data.get("kani_version") or "")
    if not version:
        raise ExternalResultError("Kani report does not state its version; pass kani_version=")
    assumptions = ["kani_bounded_unwinding"]
    if "unwind" in data:
        assumptions.append(f"unwind_le_{int(data['unwind'])}")
    assumptions.extend(str(a) for a in data.get("assumptions", ()))
    return ExternalResult(
        tool="kani",
        version=version,
        verdict=verdict,
        artifact_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        scope={"harnesses": names, "unwind": data.get("unwind")},
        assumptions=tuple(assumptions),
        provenance=PROVENANCE_KANI,
        kernel_version_hash=kernel_version_hash,
        subject_refs=tuple(names),
        detail={"statuses": dict(zip(names, statuses))},
    )


def from_generic(payload: Mapping[str, Any]) -> ExternalResult:
    """`{tool, version, verdict, artifact_sha256, scope, assumptions, kernel_version_hash}` --
    the shape for Alive2 or Lean outputs when M12/V6 arrive."""
    required = ("tool", "version", "verdict", "artifact_sha256", "kernel_version_hash")
    missing = [k for k in required if k not in payload]
    if missing:
        raise ExternalResultError(f"generic prover result is missing {missing}")
    return ExternalResult(
        tool=str(payload["tool"]),
        version=str(payload["version"]),
        verdict=payload["verdict"],
        artifact_sha256=str(payload["artifact_sha256"]),
        scope=dict(payload.get("scope") or {}),
        assumptions=tuple(str(a) for a in payload.get("assumptions") or ()),
        provenance=str(payload.get("provenance") or PROVENANCE_GENERIC),
        kernel_version_hash=str(payload["kernel_version_hash"]),
        subject_refs=tuple(str(s) for s in payload.get("subject_refs") or ()),
        detail=dict(payload.get("detail") or {}),
    )


# -- into the assurance plane -----------------------------------------------------------------


def to_evidence(result: ExternalResult) -> EvidenceObject:
    """An `EvidenceObject` for a proved or refuted result. `unknown` is not evidence of anything
    and is refused."""
    if result.verdict == "unknown":
        raise ExternalResultError("an inconclusive prover result is not evidence; nothing to attach")
    kind = "proof_artifact" if result.verdict == "proved" else "refutation"
    evidence = make_evidence(
        kind=kind,
        source=f"external:{result.tool}",
        method=f"{result.tool} {result.version} ({result.provenance}); bounded: "
               + (", ".join(result.assumptions) or "no assumptions stated"),
        warrant=Warrant.FORMAL,
        payload={
            "artifact_sha256": result.artifact_sha256,
            "verdict": result.verdict,
            "scope": dict(result.scope),
            "assumptions": list(result.assumptions),
            "kernel_version_hash": result.kernel_version_hash,
            "subject_refs": list(result.subject_refs),
            "provenance": result.provenance,
        },
    )
    # The content hash names the artifact, not the payload wrapper around it.
    from dataclasses import replace

    return replace(evidence, content_hash=f"sha256:{result.artifact_sha256}")
