# ADR 0001 — Record architecture decisions

**Status:** Accepted
**Date:** 2026-08-17
**Governs:** spec §31.1

## Context

Spec §31.1 requires an ADR for any change to K0 semantics, the primary metric, the
hidden-evaluation protocol, primitive maturity definitions, the trust boundary, allowed
mutation permissions, or benchmark family definitions. `AGENTS.md` additionally requires an
ADR whenever an implementer is unsure, and whenever a component is hand-written that exists
in mature form (the build-versus-adopt rule, spec §36).

Without a written record, those decisions get made silently inside commits, and the reason a
constraint exists is lost by the time someone wants to relax it. In a program whose entire
value rests on not having quietly weakened a control, that is the failure mode to design
against.

## Decision

Architecture decisions are recorded as numbered Markdown files in `docs/adr/`, named
`NNNN-short-title.md`, using the sections: Context, Decision, Consequences, and — where the
decision is provisional — a Revisit trigger.

Statuses: `Proposed`, `Accepted`, `Provisional`, `Superseded by ADR-NNNN`, `Rejected`.

`Provisional` is a first-class status. `AGENTS.md` instructs an implementer who is unsure to
state the options and mark the decision provisional rather than choosing silently; a
provisional ADR must name what evidence would settle it.

ADRs are append-only in spirit: a superseded ADR is marked superseded, never deleted or
rewritten, for the same reason negative results are never deleted (P7, spec §44).

## Consequences

- Every constraint in the codebase is traceable to a stated reason.
- Relaxing a control requires writing down that you are relaxing it, which is the point.
- ADR count grows; that is acceptable, and the index below is maintained by hand.

## Index

| ADR | Title | Status |
|---|---|---|
| 0001 | Record architecture decisions | Accepted |
| 0002 | Python-first implementation for the research instrument | Provisional |
| 0003 | Repository layout maps spec §28 onto a `src/` package | Accepted |
| 0004 | Hand-written statistics rather than SciPy | Provisional |
| 0005 | In-process audit-hook sandbox for the candidate boundary | Provisional |
| 0006 | Hand-written MDL abstraction extractor for condition C | Accepted (amended 2026-08-24) |
| 0007 | Enumerative synthesizer as the fixed "model" for the instrument dry run | Accepted |
| 0008 | K0 v1.0.0 semantics: bounded integers, fuel, and total operations | Accepted |
| 0009 | Reconciling the assurance lifecycle with spec §11 maturity | Accepted |
| 0010 | One promotion predicate, consumed by the report gate | Accepted |
| 0011 | BSIR and SCIR remain separate IRs | Accepted |
| 0012 | SRE-Core is language-native libraries against shared schemas, not a service | Accepted |
| 0013 | BSIR is canonical semantics; projections are never authoritative | Accepted |
| 0014 | BSLD is declarative and its lowering is evidence-bound | Accepted |
| 0015 | SRE wire schemas keep cross-repo conventions, not BestSad-native ones | Accepted |
