# ADR 0010 — One promotion predicate, consumed by the report gate

**Status:** Accepted
**Date:** 2026-08-23
**Governs:** spec §40 (confound control plane), §26.5; `AGENTS.md` invariants 3–5;
assurance integration §1.4, §8, §14

## Context

Before this change, the rule "no capability claim without conditions F, H and I" lived in
`bestsad.stats.preregistration.ReportGate` — that is, in report generation. It worked, and
`tests/stats/test_report_gate.py` proved it worked.

The assurance integration spec §8 says it is nonetheless in the wrong place:

> The existing rule that reporting refuses a capability claim when F, H or I is missing should
> move from report formatting into the central promotion predicate.

And §14's ninth acceptance test makes it checkable:

> Report generation consumes the central promotion predicate rather than duplicating its own
> rules.

The reason is not tidiness. A rule that lives in the reporter can only refuse a *report*.
Anything else that consumes the result — a compiler asking whether a primitive certificate is
promotable, a later claim depending on this one, a runtime deciding whether a primitive may be
treated as CORE — would each need their own copy. Copies drift, and the copy that drifts is
always the one nobody is looking at.

## Decision

`bestsad.assurance.promotion.evaluate()` is the single place that decides whether a claim may be
promoted. It implements §1.4's predicate in full, including the F/H/I gate, the control-defeat
rule, FDR control, the concentration stop rule, power, dependency states, source-hash currency,
active assumptions, quarantine, policy, and the producer/gate separation.

`ReportGate.certify()` now:

1. performs its own domain checks — pre-registration present, committed, complete, unedited; and
   the compression/capability pairing, which is a *reporting* rule (spec §21.6);
2. builds a claim and a `PromotionContext` from the request, and asks the predicate;
3. raises `ReportRefused` carrying the predicate's blockers.

The refusal messages remain recognisable, so the existing tests continue to assert the same
behaviour through the new path — all 38 pass unchanged.

## Why the pre-registration checks stayed in the report gate

They are about whether a *document* was committed before a *run*, which is a property of the
reporting protocol rather than of a claim's dependency graph. Pushing them into the predicate
would have meant giving every claim a notion of "was there a document" that only experimental
claims have. The predicate instead consumes the outcome: a run without a valid pre-registration
never reaches it.

## Consequences

- One rule, one place. Adding a required control means editing `CLAIM_CLASSES` in
  `assurance/claims.py`, and every consumer inherits it.
- The rule now binds things that are not reports. A stale semantic certificate fails closed for
  compiler CORE use (§14 acceptance 10) through the same predicate that refuses a capability
  claim, rather than through a second implementation that happens to agree.
- `ReportGate` gained a dependency on `bestsad.assurance`. Acceptable: assurance depends on
  nothing in `stats`, so there is no cycle.
- A caller can now ask *why* something is unpromotable and get every blocker at once, rather
  than fixing one and discovering the next.
