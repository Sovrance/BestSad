# ADR 0007 — Enumerative synthesizer as the fixed "model" for the instrument dry run

**Status:** Accepted
**Date:** 2026-08-17
**Governs:** spec §17 (model-language interface), §24.5 (same model weights for A–I), §31.2
(claim levels), §45 (claims register)

## Context

EXP-001 asks whether evolved abstractions improve verified compositional OOD synthesis **for a
fixed model** — a language model, with fixed weights across conditions A–I (spec §24.5, §17.2).
The instrument needs *something* in the model role in order to be built, tested, and shown to
produce an honest answer before any model inference budget is spent.

## Decision

The model role is filled by `bestsad.solver.EnumerativeSynthesizer`: bottom-up enumerative
program synthesis with observational-equivalence pruning, type-directed, metered, and
deterministic given `(task, genome, seed)`.

It satisfies the structural requirements spec §17.1 places on a model adapter: it consumes a
genome's vocabulary and projection, emits candidate programs, has a declared budget, and reports
its compute into the ledger. And it provides a *real* mechanism by which an abstraction can help
or hurt — a primitive collapses a subtree into one vocabulary item, so a solution at enumeration
level 8 in plain K0 may sit at level 6 with the right abstraction, while a larger vocabulary
costs more per level, so an unhelpful abstraction genuinely hurts.

## What this licenses, and what it does not

**It licenses:** validating the instrument end to end. Whether the control plane reconciles,
whether the report gate refuses what it should, whether the concentration test fires on a
planted shortcut, whether a control can beat a treatment and be reported without special-casing.

**It does not license any claim about EXP-001's hypothesis.** H2 is a claim about a *model*.
Results obtained with an enumerative searcher say nothing about whether a language model
benefits from evolved abstractions, because the mechanisms differ in the way that matters:

- the synthesizer has no prior over programs; a language model's prior is the entire effect
  under study;
- the synthesizer is insensitive to surface form except through token counting, so H13
  (compression is not capability) and H14 (scaffolding invariance) are *untestable* here —
  conditions F and H can be constructed and reconciled, but they cannot be interpreted;
- `compression_ratio` is computed from a surface-token proxy, not a model tokenizer.

Consequently any run using this solver is **Claim Level 0/E — exploratory instrument
validation**, and must be described that way. It must not be reported as evidence for or against
H2, H13, H14 or H15, and spec §45's prohibited claims apply in full.

## Consequences

- A separate pre-registration is used for the dry run, with `model_identity =
  "enumerative-search-v1"` recorded, so no dry-run number can be mistaken for an EXP-001 number.
- `BESTSAD_PREREGISTRATION_EXP001_v0.2.md` stays a template with its `<<FILL>>` fields intact.
  The report gate refuses confirmatory certification against it, which is the correct behaviour
  and is itself worth testing.
- Adding a real model adapter is a new component behind the same interface; nothing else in the
  instrument should need to change, and that is the property this ADR is buying.


---

## Amendment, 2026-08-24 — the searcher's reach changed

Two defects that narrowed the reachable program set were fixed: closure bodies can now reference
the enclosing program's parameters, and observational-equivalence pruning can now distinguish two
variables of the same type (it previously could not, collapsing `ge L0 n` onto the constant
`true`). `SYNTHESIZER_VERSION` records this and participates in checkpoint fingerprints, so a
record produced by the old searcher can never be served silently to the new one.

Two consequences for this ADR:

1. **EXP-001-DR was produced by the older, narrower searcher.** Its numbers stand as recorded and
   are not directly comparable to a future run. Nothing was recomputed.
2. The measured effect of widening the searcher was **nil on the primary-endpoint proxy** — a
   four-arm ablation put held-out solve rate at 5/16 in every arm while training solve rate moved
   24/32 → 27/32. That is written up in
   `docs/research/negative_results/2026-08-24-search-reach-does-not-raise-ood.md`, and it removes
   one candidate explanation for the EXP-001-DR null: the searcher was not simply unable to
   express the programs it needed.

This does not change the ADR's decision. The model role is still a deterministic enumerative
synthesizer, conditions F and H still cannot be interpreted, and the instrument still cannot
produce a capability claim in its current configuration.
