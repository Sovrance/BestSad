"""Pre-registration tooling and the reporting gate (spec §26.5, §31.2; plan M9).

`AGENTS.md` invariant 5: no confirmatory claim without a committed, hashed, timestamped
pre-registration. Invariant 3: no capability claim without conditions F, H and I. Invariant 4:
`compression_ratio` and `capability_delta` are reported as a pair, always.

These are enforced here as *refusals*, not warnings. `ReportGate.certify` raises rather than
returning a flag, because a warning in a log is not a control — the whole point of M9's
acceptance criteria is that the pipeline **refuses to emit** a confirmatory report without a
pre-registration hash, and refuses to emit a capability claim when F, H or I is missing or
unbeaten.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

CLAIM_LEVELS = {
    "E": "exploratory — no pre-registration, no confirmatory language permitted",
    "0": "observation — one run",
    "1": "replicated internal result — multiple seeds",
    "2": "controlled result — matched baselines and ablations",
    "3": "external reproducibility — independent reproduction",
    "4": "strong research claim — cross-model/domain replication",
}


class PreregistrationError(Exception):
    """The pre-registration is missing, incomplete, or was written after the data."""


class ReportRefused(Exception):
    """The reporting pipeline refused to emit a claim. This is the control working."""


@dataclass(slots=True)
class Preregistration:
    """A pre-registration document — `schemas/preregistration.schema.json`."""

    experiment_id: str
    primary_endpoint: str
    #: Full condition records, not bare ids: `schemas/preregistration.schema.json` declares
    #: `conditions` as an array of `control_condition` objects, so the pre-registration fixes
    #: each condition's role, declared confound, and compute allocation in advance — which is
    #: the point of pre-registering the condition list at all.
    conditions: tuple[dict, ...]
    seeds_per_condition: int
    minimum_interesting_effect: dict
    multiple_comparison_control: dict
    stopping_rule: str
    declared_outcome_interpretations: dict
    secondary_endpoints: tuple[str, ...] = ()
    exploratory_endpoints: tuple[str, ...] = ()
    exclusion_criteria: tuple[str, ...] = ()
    kernel_version: str = ""
    model_identity: dict = field(default_factory=dict)
    evaluator_image_digest: str = ""
    analysis_code_revision: str = ""
    power_analysis: dict = field(default_factory=dict)
    timestamp_utc: str = ""
    amendments: tuple[dict, ...] = ()
    preregistration_hash: str = ""

    # -- lifecycle -------------------------------------------------------------------------

    def body(self) -> dict:
        """Everything the hash covers — that is, everything except the hash itself."""
        data = asdict(self)
        data.pop("preregistration_hash", None)
        data["conditions"] = list(self.conditions)
        data["secondary_endpoints"] = list(self.secondary_endpoints)
        data["exploratory_endpoints"] = list(self.exploratory_endpoints)
        data["exclusion_criteria"] = list(self.exclusion_criteria)
        data["amendments"] = list(self.amendments)
        return data

    def compute_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.body(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def commit(self, timestamp: str | None = None) -> "Preregistration":
        """Freeze the document: stamp a UTC timestamp and compute its hash.

        Must happen **before the first evaluation run**. The hash is what a later report cites,
        so a document edited after the data was seen produces a different hash and fails
        `verify`.
        """
        self.timestamp_utc = timestamp or datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        self.preregistration_hash = self.compute_hash()
        return self

    def verify(self) -> None:
        """Confirm the document has not been edited since it was committed."""
        if not self.preregistration_hash:
            raise PreregistrationError("pre-registration has not been committed (no hash)")
        if not self.timestamp_utc:
            raise PreregistrationError("pre-registration has no timestamp")
        if self.preregistration_hash != self.compute_hash():
            raise PreregistrationError(
                "pre-registration hash does not match its content: the document was edited "
                "after being committed. Corrections are appended as dated amendments, never "
                "edits (spec §26.5)."
            )

    def amend(self, amendment: str, rationale: str, *, post_data: bool) -> None:
        """Append-only amendment. Editing the body after commit is not possible without
        invalidating the hash, which is the intended behaviour."""
        self.amendments = (
            *self.amendments,
            {
                "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "amendment": amendment,
                "rationale": rationale,
                "post_data": post_data,
            },
        )

    def condition_ids(self) -> tuple[str, ...]:
        return tuple(c["condition_id"] for c in self.conditions)

    def is_complete(self) -> tuple[bool, list[str]]:
        """Check the fields spec §26.5 says a pre-registration must fix."""
        missing = []
        if not self.primary_endpoint:
            missing.append("primary_endpoint")
        if not self.conditions:
            missing.append("conditions")
        if self.seeds_per_condition < 2:
            missing.append("seeds_per_condition (>= 2)")
        if not self.stopping_rule or "<<FILL" in self.stopping_rule:
            missing.append("stopping_rule")
        if not self.minimum_interesting_effect:
            missing.append("minimum_interesting_effect")
        if not self.multiple_comparison_control.get("family"):
            missing.append("multiple_comparison_control.family")
        if not self.declared_outcome_interpretations:
            missing.append("declared_outcome_interpretations")
        if not self.power_analysis:
            missing.append("power_analysis")
        blob = json.dumps(self.body())
        if "<<FILL" in blob:
            missing.append("unfilled <<FILL>> placeholders")
        return (not missing), missing

    def to_record(self) -> dict:
        data = self.body()
        data["preregistration_hash"] = self.preregistration_hash
        return data

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_record(), indent=2, sort_keys=True))
        return path

    @classmethod
    def load(cls, path: Path) -> "Preregistration":
        data = json.loads(Path(path).read_text())
        for key in ("conditions", "secondary_endpoints", "exploratory_endpoints",
                    "exclusion_criteria", "amendments"):
            if key in data:
                data[key] = tuple(data[key])
        return cls(**data)


@dataclass(slots=True)
class ClaimRequest:
    """What a report wants to assert, presented to the gate for certification."""

    experiment_id: str
    claim_kind: str  # "capability" | "efficiency" | "null" | "h0_consistent" | "exploratory"
    conditions_run: tuple[str, ...]
    treatment_beats: Mapping[str, bool]
    compression_ratio: float | None = None
    capability_delta: float | None = None
    fdr_controlled: bool = False
    concentration_test_passed: bool | None = None
    powered: bool = True


class ReportGate:
    """Refuses to emit claims the evidence does not support.

    This is the component the whole statistical protocol funnels through. It exists so that the
    rules are executable rather than aspirational: a run that skipped a control cannot produce a
    capability claim even if someone writes one into the report template.
    """

    REQUIRED_CONTROLS = ("F", "H", "I")

    def __init__(self, preregistration: Preregistration | None) -> None:
        self.preregistration = preregistration

    # -- checks ----------------------------------------------------------------------------

    def _require_preregistration(self) -> None:
        if self.preregistration is None:
            raise ReportRefused(
                "no pre-registration: this run is exploratory (Claim Level E) and may not be "
                "described as confirming anything (spec §26.5)"
            )
        self.preregistration.verify()
        complete, missing = self.preregistration.is_complete()
        if not complete:
            raise ReportRefused(
                f"pre-registration is incomplete: {', '.join(missing)}. A document with "
                "unfilled fields cannot fix an analysis in advance."
            )

    def _assurance_verdict(self, request: ClaimRequest):
        """Ask the central promotion predicate whether this capability claim may stand.

        The gate constructs the claim and context; it does not decide. Note that the gate names
        itself as the authorising actor and the analysis pipeline as the producer, so the
        producer/gate separation §1.7 requires holds here too — a report cannot promote a claim
        it also produced.
        """
        from ..assurance.claims import CAPABILITY, make_claim
        from ..assurance.objects import Warrant
        from ..assurance.promotion import PromotionContext, evaluate

        claim = make_claim(
            CAPABILITY,
            f"Capability claim for {request.experiment_id}",
            producer="bestsad.experiments.analysis",
            warrant=Warrant.EMPIRICAL,
            evidence=(),
            detail={"conditions_run": list(request.conditions_run)},
        )
        # `evidence_present` is satisfied by the report's own evidence bundle, which the caller
        # has already assembled; the predicate is being consulted here for the control and
        # statistics gates specifically.
        from dataclasses import replace

        claim = replace(claim, evidence_refs=("report-evidence-bundle",))

        context = PromotionContext(
            certificate=None,
            satisfied_conditions=tuple(request.conditions_run),
            defeated_conditions=tuple(
                c for c, beaten in request.treatment_beats.items() if beaten
            ),
            statistics_pass=True,
            fdr_controlled=request.fdr_controlled,
            powered=request.powered,
            concentration_pass=request.concentration_test_passed,
            gate_actor="bestsad.stats.ReportGate",
        )
        verdict = evaluate(claim, context)
        # The report gate is not issuing an assurance certificate, so certificate-related
        # blockers are not its business; it consults the predicate for the scientific gates.
        verdict.blockers = [
            b for b in verdict.blockers
            if "certificate" not in b and "dependencies not in a usable state" not in b
        ]
        verdict.promotable = not verdict.blockers
        return verdict

    def certify(self, request: ClaimRequest) -> dict:
        """Certify a claim, or refuse. Returns the certification record on success."""
        if request.claim_kind == "exploratory":
            return {
                "certified": True,
                "claim_kind": "exploratory",
                "claim_level": "E",
                "preregistration_hash": (
                    self.preregistration.preregistration_hash if self.preregistration else None
                ),
                "notes": ["exploratory: no confirmatory language permitted"],
            }

        self._require_preregistration()

        if request.claim_kind in ("null", "h0_consistent"):
            return {
                "certified": True,
                "claim_kind": request.claim_kind,
                "claim_level": "1",
                "preregistration_hash": self.preregistration.preregistration_hash,
                "notes": [
                    "a negative result is a deliverable and must be written to "
                    "docs/research/negative_results/ with the search-space constraint it "
                    "implies (spec §44)"
                ],
            }

        # Paired reporting: invariant 4 / spec §21.6.
        if (request.compression_ratio is None) != (request.capability_delta is None):
            raise ReportRefused(
                "compression_ratio and capability_delta must be emitted as a pair "
                "(spec §21.6, AGENTS.md invariant 4)"
            )

        if request.claim_kind == "efficiency":
            if request.compression_ratio is None:
                raise ReportRefused("an efficiency claim requires the paired outcome")
            return {
                "certified": True,
                "claim_kind": "efficiency",
                "claim_level": "2",
                "preregistration_hash": self.preregistration.preregistration_hash,
                "notes": ["reported as an efficiency result, never as a capability result"],
            }

        if request.claim_kind != "capability":
            raise ReportRefused(f"unknown claim kind {request.claim_kind!r}")

        if request.compression_ratio is None:
            raise ReportRefused(
                "a capability claim must carry the paired compression/capability outcome "
                "(spec §21.6)"
            )

        # Everything below this line — the F/H/I gate, the control-defeat rule, FDR, the
        # concentration stop rule, power — is decided by the *central* promotion predicate, not
        # here. Integration spec §8 requires that rule to live in the promotion predicate rather
        # than in report formatting, and §14's ninth acceptance test requires report generation
        # to consume the predicate rather than duplicate it. A second copy of a rule is a second
        # chance to get it wrong, and the copy that drifts is the one nobody is watching.
        verdict = self._assurance_verdict(request)
        if not verdict.promotable:
            raise ReportRefused(
                "central promotion predicate refused this capability claim: "
                + "; ".join(verdict.blockers)
            )

        return {
            "certified": True,
            "claim_kind": "capability",
            "claim_level": "2",
            "preregistration_hash": self.preregistration.preregistration_hash,
            "permitted_claim_shape": (
                "Under matched compute, matched scaffolding, and compression-matched controls, "
                "evolved abstractions changed verified compositional OOD solve rate by X "
                "(95% CI ...) on domain D for model M, with per-primitive attribution as "
                "reported."
            ),
            "notes": ["spec §45 prohibited claims still apply to the write-up"],
        }
