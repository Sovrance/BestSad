# Bestsad v0.2 Research Package

Bestsad is a research program investigating whether machine intelligence improves when it is allowed to evolve its own executable computational representations, rather than being constrained to programming languages designed for humans.

**v0.2 supersedes v0.1.** It keeps the whole v0.1 architecture and adds a prior-art audit, a confound-control plane, and the statistical machinery needed to make the central claim provable — or, just as usefully, falsifiable.

**Evidence cutoff:** 2026-08-17.

## If you are a coding agent

Start with **`AGENTS.md`**. It lists the invariants you may not violate and the definition of done. Then `IMPLEMENTATION_PLAN_v0.2.md` for the work breakdown.

## Contents

| File | What it is |
|---|---|
| `AGENTS.md` | Entry point for an implementing agent: invariants, escalation triggers, done criteria |
| `BESTSAD_RESEARCH_ARCHITECTURE_EXPERIMENTAL_SPEC_v0.2.md` | The normative architecture and experiment specification |
| `BESTSAD_RESEARCH_COMPANION_v0.2.md` | Literature synthesis, evidence map, prior-art audit, adversarial review, annotated sources |
| `BESTSAD_PREREGISTRATION_EXP001_v0.2.md` | Pre-registration template and EXP-001 instance — must be committed before any evaluation run |
| `IMPLEMENTATION_PLAN_v0.2.md` | Milestones M0–M14 with acceptance tests, cheap falsifiers first |
| `CHANGELOG_v0.1_to_v0.2.md` | What changed and why |
| `BESTSAD_SOURCE_LEDGER_v0.2.csv` | Machine-readable source register (77 sources: S01–S77) |
| `BESTSAD_REFERENCES_v0.2.bib` | BibTeX bibliography |
| `schemas/` | JSON Schemas: genome, primitive, benchmark, experiment, plus v0.2 additions for pre-registration, experimental conditions, causal attribution, and compute ledger |
| `MANIFEST_SHA256.txt` | File hashes for integrity |

## The one-paragraph version

Most code-capable models inherit languages and tokenizers designed for people. Bestsad treats the representation of computation as an optimization target: everything may evolve **except** the trusted semantic kernel, the evaluator trust boundary, and the rules that decide whether a result is correct. The first experiment asks whether evolved, semantics-preserving abstractions improve verified compositional out-of-distribution synthesis for a fixed model — at matched compute, matched scaffolding, and against a compression-matched control.

## What v0.2 exists to fix

v0.1 established that the pieces exist and nobody has assembled them. The v0.2 audit found something less comfortable: the nearest published attempts to demonstrate learned-abstraction benefit **did not survive compute-controlled scrutiny**, with measured gains attributable to self-correction, self-consistency, or unaccounted compute rather than to the learned abstractions themselves.

So v0.2 adds the controls that would have caught those results:

- **Condition F** — compression-matched: is the gain just shorter tokens?
- **Condition G** — human-expert DSL: is it beating a real design, or only a bare kernel?
- **Condition H** — scaffolding-matched: is it representation, or prompt engineering?
- **Condition I** — compute-matched search-only: is it representation, or just more search?

Plus MDL-grounded Semantic Gain, per-primitive causal mediation with a gain-concentration stop rule, mandatory pre-registration with FDR control, and a re-ordered ablation ladder that finally separates tokenizer co-design from model adaptation.

## Standing honesty constraints

- The strong thesis — that evolved machine-native representations increase generalized computational capability — is **unproven and currently contested**. It is the hypothesis under test, never a premise.
- Bestsad's novelty claim is **integration plus methodology**. Per-component priority claims over existing extensible-IR frameworks, evolutionary coding agents, compiler-heuristic evolution, program-induction systems, or hand-designed LLM-oriented DSLs are not available.
- A negative EXP-001 is a real contribution. See spec §44.
- Prohibited claims are enumerated in spec §45. Read it before writing anything public.

## Assurance protocol

Every evolved primitive, genome, and experimental capability claim carries an explicit,
machine-enforced assurance lifecycle: `docs/architecture/BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md`.

The rule it exists to enforce is that **producers of evidence cannot promote their own
conclusions**. K0, BSIR, the evaluator, the sandbox policy, the MDL coding scheme and the
pre-registration are content-addressed roots; a change to any of them stales its descendants
automatically. Query it with `bestsad assure roots`, `bestsad assure stale`,
`bestsad primitive explain <id>`, and `bestsad report <run-id> --confirmatory`, which exits
non-zero when promotion dependencies do not hold.

## Licensing

**Proprietary. All rights reserved.** See `LICENSE`.

This repository contains unpublished research materials and is confidential. No license to use,
copy, modify, or distribute is granted except by separate written agreement with the owner.

The license does not relax the scientific reporting obligations recorded in this package — the
claims register (spec §45), the requirement that a capability claim carry conditions F, H and I,
and the requirement to preserve negative results all continue to bind any authorised user. A
license to use the instrument is not a license to misrepresent what it measured.

## Naming

**Bestsad** is an English coinage inspired by Diné/Navajo lexical roots (*béésh*, metal/technological; *saad*, word/speech) and by the history of the Navajo Code Talkers. It is **not** presented as a grammatically canonical Diné compound or an established Navajo word. Any public branding making a stronger linguistic claim should be reviewed by a qualified Diné speaker, linguist, or cultural advisor. See spec §1.
