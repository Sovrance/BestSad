"""The central promotion predicate and policy gate (integration spec §1.4, §1.7, §8).

    promotable(claim, certificate) iff
        certificate.status == PASS
        AND certificate.promotion_state == PROMOTED
        AND all required dependency states are satisfied
        AND all source/content hashes are current
        AND all required assumptions match active assumption IDs
        AND governing consent/security policy allows the claim
        AND no quarantine/invalidation event is active
        AND a policy gate distinct from the producer authorized promotion

This module is the **single** place that decides. Integration spec §8 is explicit that the
"refuse a capability claim without F, H and I" rule must move out of report formatting and into
this predicate, and §14's ninth acceptance test requires report generation to *consume* the
predicate rather than re-implement it. A second copy of a rule is a second chance to get it
wrong, and the copy that drifts is always the one nobody is looking at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .claims import CLAIM_CLASSES, ClaimClass
from .objects import (
    NEVER_SUFFICIENT_ALONE,
    AssuranceCertificate,
    ClaimObject,
    ClaimState,
    GATE_ONLY_TRANSITIONS,
    PRODUCER_TRANSITIONS,
    PromotionDecision,
    Warrant,
    content_id,
    utc_now,
)


class PromotionRefused(Exception):
    """A promotion was requested that the predicate does not permit."""


class SelfPromotionRefused(PromotionRefused):
    """The producer of the evidence tried to authorise its own promotion (§1.7)."""


@dataclass(slots=True)
class PromotionVerdict:
    """Why a claim may or may not be promoted. Always enumerates *every* failing check, so a
    caller fixing one blocker is not surprised by the next."""

    claim_id: str
    promotable: bool
    checks: dict[str, bool] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "promotable": self.promotable,
            "checks": dict(self.checks),
            "blockers": list(self.blockers),
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class PromotionContext:
    """Everything the predicate needs to decide, gathered by the caller.

    Passed in rather than looked up, so the predicate is a pure function of stated inputs and a
    test can construct any situation — including ones that should never occur — without mocking.
    """

    certificate: AssuranceCertificate | None = None
    dependency_states: Mapping[str, ClaimState | str] = field(default_factory=dict)
    active_assumptions: Mapping[str, str] = field(default_factory=dict)
    current_source_hashes: Mapping[str, str] = field(default_factory=dict)
    quarantine_events: Sequence[str] = ()
    policy_allows: bool = True
    policy_reason: str = ""
    gate_actor: str | None = None
    #: Conditions actually *run*. A required condition that was never run blocks promotion.
    satisfied_conditions: Sequence[str] = ()
    #: Conditions the treatment actually *beat*. §8: a control that matches the treatment blocks
    #: the capability claim just as firmly as one that was never run — "missing/failed F blocks
    #: representation-capability promotion".
    defeated_conditions: Sequence[str] = ()
    statistics_pass: bool = True
    fdr_controlled: bool = True
    powered: bool = True
    concentration_pass: bool | None = None


def evaluate(claim: ClaimObject, context: PromotionContext) -> PromotionVerdict:
    """The promotion predicate. Returns a verdict; never raises for an ordinary failure."""
    verdict = PromotionVerdict(claim_id=claim.claim_id, promotable=False)
    spec: ClaimClass | None = CLAIM_CLASSES.get(claim.claim_class)

    # -- certificate --
    certificate = context.certificate
    has_certificate = certificate is not None and certificate.claim_id == claim.claim_id
    verdict.checks["certificate_present"] = has_certificate
    if not has_certificate:
        verdict.blockers.append("no assurance certificate for this claim")
    else:
        verdict.checks["certificate_passed"] = certificate.passed
        if not certificate.passed:
            verdict.blockers.append(f"certificate status is {certificate.status}, not PASS")

    # -- warrant sufficiency, per claim class (§1.3) --
    if spec is None:
        verdict.checks["claim_class_known"] = False
        verdict.blockers.append(f"unknown claim class {claim.claim_class!r}")
    else:
        verdict.checks["claim_class_known"] = True
        sufficient = claim.warrant in spec.sufficient_warrants
        verdict.checks["warrant_sufficient"] = sufficient
        if not sufficient:
            verdict.blockers.append(
                f"warrant {claim.warrant.value} is not sufficient for claim class "
                f"{claim.claim_class}; accepted: "
                f"{', '.join(sorted(w.value for w in spec.sufficient_warrants))}"
            )
        if claim.warrant in NEVER_SUFFICIENT_ALONE:
            verdict.checks["warrant_not_heuristic_only"] = False
            verdict.blockers.append(
                f"{claim.warrant.value} can never on its own support a promotion "
                "(§1.7: external corroboration is not silently upgraded to internal proof)"
            )
        else:
            verdict.checks["warrant_not_heuristic_only"] = True

        # -- required conditions, e.g. F/H/I for a capability claim (§8) --
        #
        # This check is the reason the predicate exists. It used to live in report formatting,
        # where it could only refuse a *report*; here it refuses the promotion itself, so
        # nothing downstream — a compiler consuming a certificate, a later claim depending on
        # this one — can pick up a capability conclusion whose controls were never run.
        missing = [c for c in spec.required_conditions if c not in context.satisfied_conditions]
        verdict.checks["required_conditions_run"] = not missing
        if missing:
            verdict.blockers.append(
                f"required control(s) for claim class {claim.claim_class} were not run: "
                f"missing {', '.join(missing)}"
            )

        unbeaten = [
            c for c in spec.required_conditions
            if c in context.satisfied_conditions and c not in context.defeated_conditions
        ]
        verdict.checks["required_conditions_defeated"] = not unbeaten
        if unbeaten:
            verdict.blockers.append(
                f"control condition(s) {', '.join(unbeaten)} matched or beat the treatment; "
                "a control defeating a treatment is a finding, not a bug, and it blocks the "
                "capability claim regardless of the baseline comparison"
            )

        if spec.requires_statistics:
            verdict.checks["statistics_pass"] = context.statistics_pass
            if not context.statistics_pass:
                verdict.blockers.append("statistics gate did not pass")

            verdict.checks["fdr_controlled"] = context.fdr_controlled
            if not context.fdr_controlled:
                verdict.blockers.append(
                    "secondary endpoints were not FDR-corrected over the declared family "
                    "(spec §26.7)"
                )

            verdict.checks["powered"] = context.powered
            if not context.powered:
                verdict.blockers.append(
                    "the run is not powered for the pre-registered minimum interesting effect; "
                    "record that and re-scope rather than interpreting the point estimate "
                    "(spec §26.8)"
                )

        if spec.requires_concentration_test:
            passed = context.concentration_pass
            verdict.checks["concentration_test_pass"] = bool(passed)
            if passed is None:
                verdict.blockers.append("concentration test was not run")
            elif not passed:
                verdict.blockers.append(
                    "concentration test failed: gain is concentrated in fewer than two "
                    "shortcut- or compression-shaped primitives (spec §42.2)"
                )

        # -- required evidence kinds --
        if spec.required_evidence_kinds and not claim.evidence_refs:
            verdict.checks["evidence_present"] = False
            verdict.blockers.append("claim carries no evidence references")
        else:
            verdict.checks["evidence_present"] = True

    # -- dependencies --
    unsatisfied = [
        dep for dep in claim.dependency_refs
        if _state_of(context.dependency_states.get(dep)) not in ("active", "PROMOTED", "VERIFIED")
    ]
    verdict.checks["dependencies_satisfied"] = not unsatisfied
    if unsatisfied:
        verdict.blockers.append(
            "dependencies not in a usable state: "
            + ", ".join(f"{d}={_state_of(context.dependency_states.get(d))}" for d in unsatisfied)
        )

    # -- assumptions (content-addressed roots must match what is active) --
    drifted = [
        name for name, expected in claim.source_hashes.items()
        if context.current_source_hashes.get(name, expected) != expected
    ]
    verdict.checks["source_hashes_current"] = not drifted
    if drifted:
        verdict.blockers.append(
            "source/content hashes have moved since the claim was made: " + ", ".join(drifted)
        )

    missing_assumptions = [
        a for a in claim.assumption_refs if a not in context.active_assumptions
    ]
    verdict.checks["assumptions_active"] = not missing_assumptions
    if missing_assumptions:
        verdict.blockers.append(
            "required assumption(s) not active: " + ", ".join(missing_assumptions)
        )

    # -- quarantine / invalidation --
    quarantined = claim.claim_id in context.quarantine_events or claim.status in (
        ClaimState.QUARANTINED, ClaimState.INVALIDATED, ClaimState.STALE
    )
    verdict.checks["no_active_quarantine"] = not quarantined
    if quarantined:
        verdict.blockers.append(f"claim is under {claim.status.value} and cannot be promoted")

    # -- policy --
    verdict.checks["policy_allows"] = context.policy_allows
    if not context.policy_allows:
        verdict.blockers.append(f"policy gate denied: {context.policy_reason or 'no reason given'}")

    # -- separation of producer and gate (§1.7, the invariant the whole protocol exists for) --
    separate = context.gate_actor is not None and context.gate_actor != claim.producer
    verdict.checks["gate_distinct_from_producer"] = separate
    if context.gate_actor is None:
        verdict.blockers.append("no policy gate actor authorised this promotion")
    elif not separate:
        verdict.blockers.append(
            f"producer {claim.producer!r} attempted to authorise its own promotion; the gate "
            "must be a distinct actor (§1.7)"
        )

    verdict.promotable = not verdict.blockers
    return verdict


def _state_of(value) -> str:
    if value is None:
        return "missing"
    return value.value if isinstance(value, ClaimState) else str(value)


class PolicyGate:
    """Authorises promotions. Distinct from any evidence producer, by construction.

    The gate refuses to act for an actor that produced the claim, and refuses to make a
    gate-only transition on a producer's behalf. That is the whole point: an evolution agent may
    propose a primitive and attach all the evidence it likes, and still cannot write CORE
    eligibility (§5).
    """

    def __init__(self, actor: str, policy: str = "bestsad-assurance-policy-v1") -> None:
        self.actor = actor
        self.policy = policy

    def decide(
        self,
        claim: ClaimObject,
        context: PromotionContext,
        *,
        to_state: ClaimState = ClaimState.PROMOTED,
    ) -> tuple[PromotionVerdict, PromotionDecision | None]:
        """Evaluate and, if the predicate allows, issue an append-only promotion decision."""
        if claim.producer == self.actor:
            raise SelfPromotionRefused(
                f"{self.actor!r} produced this claim and may not authorise its own promotion "
                "(§1.7: evidence producers cannot set final promotion state)"
            )
        context.gate_actor = self.actor
        verdict = evaluate(claim, context)
        if not verdict.promotable:
            return verdict, None

        decision = PromotionDecision(
            decision_id=content_id(
                {"claim": claim.content_id(), "to": to_state.value, "actor": self.actor,
                 "at": utc_now()},
                "decision",
            ),
            claim_id=claim.claim_id,
            from_state=claim.status,
            to_state=to_state,
            reason="; ".join(verdict.notes) or "promotion predicate satisfied",
            actor=self.actor,
            policy=self.policy,
        )
        return verdict, decision


def producer_may_transition(from_state: ClaimState, to_state: ClaimState) -> bool:
    """Whether an evidence producer may make this transition unaided (§1.2, §1.7)."""
    if to_state in GATE_ONLY_TRANSITIONS:
        return False
    return to_state in PRODUCER_TRANSITIONS.get(from_state, frozenset())
