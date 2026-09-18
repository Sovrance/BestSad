# ADR 0022 — "Agentic-first" is a measured property set, not a target; a fixed-weights model in the model role is the next lineage (EXP-002)

**Status:** Accepted (2026-09-18, on the acceptance tests under `tests/models/`,
`tests/integrity/test_model_boundary.py` and `tests/experiments/test_model_role.py` passing; the
owner's merge into `v1` is the acceptance)
**Date:** 2026-09-18
**Governs:** `src/bestsad/models/`, `src/bestsad/conditions/flops.py`,
`src/bestsad/evaluator/holdout.py`, the model-role wiring in `src/bestsad/experiments/exp001.py`,
`docs/preregistrations/EXP-00{2,3,4,5}.draft.*`, spec §17 (model-language interface), §26.6
(compute matching), §43 (staged gates), §45 (claims register)
**Relates to:** ADR-0002 (dependency discipline), ADR-0005 (the candidate boundary and its
residual), ADR-0007 (the enumerative stand-in and what it does not license), ADR-0019 and
ADR-0020 (adopt-not-build, bounded claims labelled bounded)
**Source:** the owner's research report *"BestSad Next-Steps Roadmap: Toward Discovering an
'Agentic-First' Programming Language"*, saved verbatim as
`docs/research/2026-09-18-roadmap-agentic-first-thesis.md`

## Context

EXP-001-DR ended H0-consistent (`docs/experiments/EXP-001-DR-report.md`): +0.0052 against a
+0.05 threshold, no control beaten, the human DSL ~9.5× better. ADR-0007 already said what that
result is not: evidence about any language model. The roadmap adjudicates the literature against
the thesis and reaches five findings that bear on what to build next:

1. Surface form perturbs model behaviour (TokDrift: 6.09% prediction flips under retokenisation)
   — a **confound to control**, not a capability lever.
2. Where a formal surface helps a model, the gain comes from the **verifier and the repair loop**
   (vericoding: Dafny 82% / Verus 44% / Lean 27%; natural-language descriptions add nothing;
   the self-healing loop turns near-0% into 80–90%), not from the representation.
3. Grammar-constrained decoding cuts syntax errors ~96% (SynCode) and costs 10–30% of reasoning
   (CRANE): a language that is easy to constrain can be hard to reason in.
4. LLM-prompted "libraries" are single-use (TroVE: 3 reuses in 3,201 questions; LEGO-Prover: one
   verbatim reuse in ~20,000 lemmas), while classic library learning with held-out ablations does
   transfer (DreamCoder, LILO, REGAL). **Direct-reuse rate must be a pre-registered endpoint.**
5. AlphaEvolve, FunSearch and SOAR discover verifiable novelty through **search + verifier +
   compute** with the base language held fixed — the confounds C1 and condition I exist for.

The roadmap's adjudication of the phrase "agentic-first": a marketing frame, not a scientific
construct. Of the properties it decomposes into, only the verifier/proof-obligation cluster has
empirical support for helping correctness, and even there the lever is the oracle. The property
most defensibly called agentic-first — *machine-checkable evidence obligations under a compute
budget* — is what this repository's assurance plane already implements.

Its highest-value recommendation is not to build a language. It is to **put a fixed-weights
language model in the model role and re-run the discovery loop under the existing F/H/I
controls**, because every untested hypothesis (H2, H13, H14, H15) is gated on that single
substitution — and to harden the evaluator *before* the first sample is drawn.

## Decision

### 1. The target does not move

The research thesis stays spec §2.1 as written. "Agentic-first" enters this repository only as
the roadmap's §2 property table, each row tagged with its evidence level and mapped to the
component that would measure it here. No document in this repository may describe BestSad as
pursuing an "agentic-first language"; the phrase names a property set, and a claim about it is a
claim about one of these rows:

| Property | Evidence for helping *capability* | Where it lives here |
|---|---|---|
| Verifier-in-the-loop / verification-carrying code | **(a)** shown to help correctness — via the oracle and the loop, not the surface form | K0 as oracle; the visible-example repair loop in `models/llm.py`; V0–V6 in `verify/` |
| Machine-checkable proof obligations attached to code | (a) for *assurance*; capability effect unmeasured | ADR-0014 lowering obligations; ADR-0019 solver tier; ADR-0020 twin proofs |
| Capability-safe / effect-typed side effects | (b) plausible, unmeasured; strong for containment | K0 has no effects (spec §8.2); `tool_interface = "none"` in `ModelIdentity` |
| Content-addressed code | (b) plausible for reproducibility; no capability evidence | semantic hashes in `bsir/canonicalize.py`; SRE content ids |
| Grammar-constrained / structured output | mixed: (a) validity, (c) can hurt reasoning | deliberately **not** used by the LLM adapter; recorded in `constrained_decoding=False` |
| Declarative intent specs | (a) for prompt optimisation, (c) as a language virtue | condition H measures exactly this confound |
| Budget/fuel metering and evidence requirements | (b) plausible for control; (a) hidden held-out tests catch gaming | K0 fuel; the sealed tier in `evaluator/holdout.py` |

### 2. Standing instructions, added to the claims register

The roadmap's §7 "do not" list is adopted as prohibited claims alongside spec §45, effective in
every artifact of this repository:

- Do not claim an "agentic-first language" as a validated construct.
- Do not claim any capability result until a real model is in the loop; EXP-001-DR results are
  Claim Level 0/E and saying "evolved representations don't help capability" is unlicensed — the
  run showed they do not help *a saturating enumerative searcher*.
- Do not treat compression gains as capability gains (H13).
- Do not cite AlphaEvolve, FunSearch or SOAR as evidence that "the language matters".
- Do not build M12 (MLIR / Alive2) or M14 (compiler-policy evolution) before a demonstrated,
  model-in-the-loop representation effect.
- Do not accept a library with no verbatim reuse as evidence of discovery; pre-register a
  minimum direct-reuse rate.
- Do not compute-match by sample count when arms differ in model size or search type; match
  FLOPs and report pass@C at fixed FLOPs.

### 3. The model role: `bestsad.models`

ADR-0007 bought the property that "adding a real model adapter is a new component behind the same
interface; nothing else in the instrument should need to change." That property is now cashed:

- **`ModelIdentity`** is the hashed record of everything that determines what the model role
  does — model id, weights digest or immutable snapshot id, tokenizer, parameter count,
  provider, mode (fixed-weights or fine-tuned, spec §17.3), supported projections, context
  budget, constrained-decoding and log-probability capability, tool interface, and the sampling
  controls. The ledger's `model_identity_hash`, the pre-registration's `model_identity` and the
  run manifest cite the hash. The enumerative stand-in has one too (`enumerative_identity`), so
  a checkpoint produced under one model is never served to another. "Fixed weights" is fixed
  relative to this record, which is the discipline K0's own hash receives (roadmap §6).
- **`EnumerativeAdapter`** wraps ADR-0007's synthesizer and returns exactly what it returned;
  `{"kind": "enumerative_search"}` is the default spec and every EXP-001-DR record is
  reproduced through it.
- **`LLMAdapter`** is a fixed-weights language model as a *proposer*: grammar description padded
  to the scaffolding target, a fixed number of worked examples, the task's visible examples;
  text out; the genome's projection parses it; the term is typechecked and run on the visible
  examples; a failing visible example is fed back for a declared number of repair rounds. The
  model never sees a hidden input. Real token counts replace the surface-token proxy in the
  ledger, with the proxy retained and labelled when a backend reports no usage.
- **Backends.** `ScriptedBackend` (deterministic, for tests), `HTTPBackend` (any
  OpenAI-compatible endpoint, standard library only per ADR-0002, API key from the environment),
  `RecordingBackend` and `ReplayBackend` over a content-hashed `Transcript`.
- **A model that needs the network is called outside the candidate boundary.** The sandbox
  denies network access, and that denial is correct. `Exp001Runner` therefore runs a proposal
  pass in the parent — recording every prompt and completion, checking the transcript for the
  canary and for sealed hidden inputs, saving it under the run's artifacts — and the condition
  job inside the boundary re-derives every scientific quantity from the transcript through
  `ReplayBackend`. The job-isolation record names `model_proposal` as an unisolated stage
  whenever this happens (spec §40.3). A transcript on disk for the same model, condition and
  seed is reused rather than re-queried.
- **Tool interface is `none`, and that is why "test-file-edit detection" is moot here.** The
  roadmap's reward-hacking defences assume a model that runs code and can touch tests. In this
  instrument the model emits text that a projection parses; there is no file it can edit, no
  scorer it can patch, and no execution it controls. The analogue that *does* apply is the
  transcript leak check (§5 below). Any future adapter with a tool interface other than `none`
  must add the file-edit and scorer-integrity detectors before it is used, and this ADR is the
  place that says so.

### 4. Compute matching in FLOPs for model arms

`conditions/flops.py` adds the accounting policy `flops-1.0.0`: model tokens at ~2 FLOPs per
parameter per token (Kaplan et al. 2020), CPU-side units at declared planning constants, all
published with every result and labelled as declared. `Exp001Runner` records total FLOPs per
`(condition, seed)`, a per-task `TaskAttempt` (compute spent, compute at solve) on the held-out
set so **pass@C at fixed FLOPs** can be read off the record, and a FLOP-denominated form of the
condition-I identity `compute(I) == compute(A) + compute(evolution)` next to the node-denominated
one. Condition I is funded in **samples** for a model arm (`Condition.sample_bonus`): the samples
discovery consumed, spread across the tasks it must cover, exactly as nodes are spread today.

### 5. The evaluator is hardened before the first sample (roadmap recommendation 2)

`evaluator/holdout.py`, all reported under confound C4:

- **Sealed tier.** `HoldoutPolicy` partitions each task's hidden inputs — 30%, at least one —
  into a feedback tier a scaffolding variant may surface and a sealed tier nothing may. The split
  is a pure function of the task id. **Correctness is unchanged** (invariant 1): a task is solved
  when every hidden input agrees; the tiers are diagnostic.
- **Transcript leak check.** Fatal findings for the canary or a sealed input on any surface the
  model saw or produced. Runs on every recorded transcript before it is replayed.
- **Twin-gap probe.** Feedback-tier pass rate minus sealed-tier pass rate, per condition, flagged
  at a declared 0.10.
- **Canary-completion probe.** Ask the model to continue the canary's prefix; a completion that
  reproduces it means the model saw this repository's evaluator assets in training.

### 6. Pre-registrations are drafted, not committed

`scripts/draft_preregistration.py` emits `docs/preregistrations/EXP-002.draft.{json,md}` and the
EXP-003, EXP-004 and EXP-005 drafts with the roadmap's thresholds fixed in advance: EXP-002 ≥
+0.05 held-out solve rate at fixed FLOPs with the human-DSL arm retained as a ceiling; EXP-003 a
representation main effect surviving a ≥ 50% mediation share after partialling out scaffolding;
EXP-004 a transfer delta ≥ +0.05 **and** a materially non-zero direct-reuse rate; EXP-005 a
pre-registered r ≈ 0 between compression and solve rate. Every draft carries `<<FILL>>` for the
model identity and hash, the evaluator image digest, the analysis code revision and the power
analysis, because those do not exist until a model is chosen and E0 is re-measured under it.
`Preregistration.is_complete()` reports the placeholders and `ReportGate` refuses confirmatory
certification against a draft — the same refusal ADR-0007 relied on.

### 7. What stays deferred

M13's gate (S2 and S3 passing) was written for the *adapted* model of spec §43 S4. The
fixed-weights adapter is not S4: it is the model role of S1–S3, which spec §17.2 always meant to
be a language model, and which ADR-0007 stood in for. M11 (equality saturation — adopt egg or
egglog, never build) is needed only by EXP-004's e-graph arm and waits for EXP-002. **M12 and M14
stay deferred** until EXP-002 or EXP-004 demonstrates a model-in-the-loop representation effect;
building either now would sink cost into an unproven thesis.

## What this ADR does not license

Nothing here is a run. No model has been put behind the interface, no E0 variance has been
measured under one, no pre-registration has been committed, and ADR-0007's claim limitation
stands in full: every number in this repository is still Claim Level 0/E with respect to H2,
H13, H14 and H15. What is licensed is the statement that the instrument can now *take* a
fixed-weights model, meter it in FLOPs, deliver matched scaffolding to it, seal a tier of hidden
inputs from it, and score it through the same path as the enumerator — each of which is pinned
by a test rather than asserted.

## Consequences and disclosed residuals

- **The proposal stage is unisolated** for a networked model, and the run record says so. The
  hidden inputs stay inside the boundary; what crosses out is the visible examples and the
  grammar, and what crosses back in is text. The leak check is the control on that channel.
- **A hosted model is not deterministic.** The transcript makes a *replay* deterministic and
  reproducible by digest; a fresh proposal pass may return different completions even at the
  same seed. The identity records the sampling controls, and a report must state whether its
  transcripts were recorded once or re-proposed.
- **FLOP constants are declared, not measured**, and the policy record says so. Replace the
  CPU-side constants with measured figures and bump the policy id when that is done.
- **Proxy token counts** are used, and labelled `proxy`, when a backend returns no usage.
- **Primitive symbols.** A model's projection renders `prim:<name>` as `prim_<name>` so the
  lexer can parse it back; the runner's own token-count proxy still uses the bare id. The two
  differ only in the proxy, which is already a disclosed residual (ADR-0007).
- **The draft pre-registrations are drafts.** Committing one is the owner's act, after the model
  and the compute are chosen.

## Revisit triggers

- A model identity and an endpoint are chosen: measure E0 under it (`stage_s1` with the model
  spec), fill and commit `EXP-002`, and record the measured FLOP calibration.
- EXP-002 ends with the treatment beating the K0 baseline by ≥ +0.05 held-out: escalate to
  EXP-004 and revisit M11.
- EXP-002 ends inside EXP-001-DR's interval with a model that has priors: explanation B (the
  searcher's missing prior) weakens; A, C and D come forward, exactly as the roadmap's §5 sets
  out.
- Any adapter with a tool interface other than `none`: add the file-edit and scorer-integrity
  detectors first.
