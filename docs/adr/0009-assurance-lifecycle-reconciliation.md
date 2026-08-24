# ADR 0009 — Reconciling the assurance lifecycle with spec §11 maturity

**Status:** Accepted
**Date:** 2026-08-23
**Governs:** spec §11 (primitive lifecycle), §31.1 (primitive maturity definitions require an ADR);
assurance integration §5

## Context

The assurance integration spec §5 defines a primitive lifecycle:

    DISCOVERED -> CANDIDATE -> SEMANTICS_VERIFIED -> EXPERIMENTALLY_SUPPORTED
                -> CORE_ELIGIBLE -> CORE

The architecture spec §11 already defines one:

    EXP -> OBS -> SPEC -> VER -> CORE

These are not the same ladder. They were designed for different purposes and their joints fall
in different places. §5 is nonetheless explicit that assurance must "integrate with the existing
primitive lifecycle rather than creating a second promotion system" — so having both run
independently is the one outcome ruled out.

Changing primitive maturity definitions requires an ADR (spec §31.1). This is that ADR.

## Decision

**Spec §11's ladder remains normative.** `Primitive.maturity` keeps its `EXP/OBS/SPEC/VER/CORE`
values, `primitive_record.schema.json` is unchanged, and `abstraction.lifecycle.promote()` keeps
its behaviour. The assurance lifecycle is a *view* over the same object, held in the `assurance`
envelope (§3), with an explicit mapping in `bestsad.assurance.integration`.

The mapping is deliberately **not a bijection**:

| Assurance state | Spec §11 maturity | Note |
|---|---|---|
| DISCOVERED | EXP | proposed, no evidence yet |
| CANDIDATE | EXP | evidence attached, nothing verified |
| SEMANTICS_VERIFIED | VER | equivalence to K0 established |
| EXPERIMENTALLY_SUPPORTED | VER | equivalence *plus* measured utility |
| CORE_ELIGIBLE | VER | all evidence in; awaiting governance |
| CORE | CORE | kernel change; new experiment lineage |

Three assurance states collapse onto `VER`. That is the informative part of the mapping, not a
defect in it: spec §11's `VER` means "equivalence claims satisfy the verifier", which says
nothing about whether the primitive was ever shown to *help*. The assurance ladder separates
"semantics preserved" from "experimentally supported", and that separation is the entire point
of the integration — it is the difference between a primitive that is correct and one that has
earned its place.

Going the other way, `OBS` maps to `CANDIDATE`: repeated successful use is evidence, but it is
not verification, and the assurance ladder declines to treat frequency as if it were.

## Consequences

- Existing records and tests are untouched; `tests/abstraction/test_discovery.py` still passes
  unmodified.
- A reader asking "is this primitive verified?" gets the §11 answer; a reader asking "may this
  primitive be relied on for a capability claim?" gets the assurance answer. Those were always
  different questions and now have different answers.
- `advance_lifecycle` enforces §5's rule that the last three steps require a promotion gate, so
  an evolution agent can attach any amount of evidence and still cannot reach CORE_ELIGIBLE.
- Anything wanting a single scalar "how good is this primitive" will not find one. That is
  intentional: the two ladders disagree precisely where the disagreement is meaningful.

## Alternative rejected

Replacing §11's ladder outright. It would have been cleaner in the code and worse everywhere
else: §11 is normative in a specification this repository does not own, the maturity values are
written into a shipped schema, and a rename would have invalidated the primitive records already
produced by the EXP-001-DR run for no scientific gain.
