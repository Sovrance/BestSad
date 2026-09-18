<!--
Saved verbatim on 2026-09-18 from the owner's research report. The adjudication of its
recommendations against the codebase, and what was built in response, is in ADR-0022
(`docs/adr/0022-agentic-first-is-a-property-table-exp-002-next.md`) and the work-order status in
`docs/architecture/EXP002_READINESS_WORK_ORDERS.md`. This file is not edited; it is the record
of what was recommended.
-->

# BestSad Next-Steps Roadmap: Toward Discovering an "Agentic-First" Programming Language

## TL;DR
- **The literature does not support the claim that "the language matters" for LLM/agent capability in the way BestSad's thesis needs.** Where a formal or DSL surface helps LLMs, the gains come almost entirely from an external verifier, a feedback loop, or extra compute — not from the representation being intrinsically more "machine-native." The EXP-001-DR null is therefore consistent with the broader field, not an anomaly.
- **"Agentic-first" is not yet a scientific construct; it is mostly a marketing frame** (e.g., the AI Alliance's Dana/OpenDXA, "AI-native language" essays). The few properties with genuine empirical support (verifier-in-the-loop, capability/effect typing for safety, content-addressed code) are borrowed from decades-old PL research and help *agents' tooling and safety*, not their raw problem-solving capability.
- **BestSad's highest-value next move is not to build an agentic language — it is to put a real fixed-weights LLM in the model role and re-run the discovery loop with the existing F/H/I controls,** because every untested hypothesis (H2, H13, H14, H15) is gated on that single substitution. Do that before touching M11–M14.

## Key Findings

**1. Surface form measurably perturbs LLM code behavior, but that is fragility, not capability.** Per Li, Deng & Nie, "TokDrift: When LLM Speaks in Subwords but Code Speaks in Grammar" (arXiv 2510.14972): "the most performant LLM in our experiment, Qwen2.5-Coder-32B-Instruct, changes its prediction 6.09% of the times when the input tokenization changes (and up to 60% under a single rewrite rule)." The effect originates in early layers where subword segmentation fails to align with grammar-token boundaries. This proves tokenization is a confound, not that a better surface form raises capability.

**2. Verification-first languages help only because of the verifier + repair loop.** Per Bursuc et al. (incl. Max Tegmark), "A benchmark for vericoding: formally verified program synthesis" (arXiv 2509.22908; 12,504 specs: 3,029 Dafny, 2,334 Verus/Rust, 7,141 Lean): "We find vericoding success rates of 27% in Lean, 44% in Verus/Rust and 82% in Dafny using off-the-shelf LLMs. Adding natural-language descriptions does not significantly improve performance. We also find that LLM progress has improved progress on pure Dafny verification from 68% to 96% over the past year." Near-zero contextless success jumps to 80–90% only with signature prompts + self-healing verifier feedback (NL2VC-60, arXiv 2604.22601). The lever is the oracle and the loop, not the language's syntax.

**3. Constrained/grammar decoding is a double-edged design lever.** Per Ugare et al., "SynCode: LLM Generation with Grammar Augmentation" (arXiv 2403.01632): "SynCode significantly reduces 96.07% of syntax errors in generated Python and Go code," and on Spider SQL lifted Llama-3.2-3B execution success 67.4%→81.4%. But CRANE (arXiv 2502.09061) and multiple 2025–2026 studies show over-restrictive grammars degrade reasoning by 10–30%, because token masking distorts the model's learned distribution and removes scratchpad room. A language that is "easy to constrain" can simultaneously be "hard to reason in."

**4. Library learning / DSL induction: the transfer evidence is bifurcated, and this is the single most important finding for BestSad.** LLM-prompting "library" systems are effectively single-use. Per Berlot-Attwell, Rudzicz & Si, "Library Learning Doesn't: The Curious Case of the Single-Use 'Library'" (arXiv 2410.20274, NeurIPS 2024 MATH-AI): TroVE reused a learned function in only 3 of 3,201 test questions [arxiv](https://arxiv.org/html/2410.20274v1) (only 2 of 15 learned functions ever reused); LEGO-Prover learned ~20,000 lemmas but had exactly one verbatim reuse, with "no lemma reused twice," and the authors conclude "rather than reuse, self-correction and self-consistency are the primary drivers of the observed performance gains." A compute-matched re-evaluation (arXiv 2507.22069) reduced TroVE's benefit to ~1%. By contrast, classic neurosymbolic systems that measure held-out solve rate under matched ablations *do* show transfer: DreamCoder solves nearly 100% vs <60% of held-out LOGO/tower tasks with vs without library learning (and 93.3% best-run on held-out physics laws); LILO beats DreamCoder by +33.14 (REGEX) and +20.42 (LOGO) points; REGAL (arXiv 2401.16467) yields +11.5/+26.1/+8.1 absolute on LOGO/Date/TextCraft for CodeLlama-13B. Stitch and babble contribute compression efficiency, not held-out solve-rate gains. DreamProver (arXiv 2604.26311 — an unrefereed, future-dated preprint using GPT-5.3/Gemini-3.1-class backbones; treat as author-claimed) reports full-library 104 vs no-library 55 problems solved on held-out inequalities.

**5. Evolutionary LLM code search discovers real, verifiable artifacts — but with an external evaluator, not a better base language.** Per Novikov et al., "AlphaEvolve: A coding agent for scientific and algorithmic discovery" (arXiv 2506.13131): applied to over 50 open problems it "match[ed] the best known constructions on ∼75% of them... On ∼20% of the problems, AlphaEvolve surpasses the SOTA and discovers new, provably better constructions." On matrix multiplication, across 54 targets it "matched 38 prior best ranks, surpassed 14, and fell behind on 2," including "a procedure to multiply two 4×4 complex-valued matrices using 48 scalar multiplications; offering the first improvement, after 56 years, over Strassen's algorithm in this setting." Per Pourcel et al., "Self-Improving Language Models for Evolutionary Program Synthesis" (arXiv 2507.14172; ICML 2025; ARC Prize 2025 2nd-place paper), SOAR lifted open-source models "from 1-2% to 14-26%," then "After four training iterations, SOAR solves an extra 10-19% tasks across model sizes," reaching "a final test performance of 52%... without using any hand-crafted data." In all cases the gain comes from search + verifier + (sometimes) weight updates — exactly the compute confounds BestSad's C1/I controls target.

## Details

### 1. What the literature establishes vs. leaves open

**Established (with effect sizes):**
- *Tokenization/surface form perturbs behavior:* 6.09% prediction flips under retokenization, up to 60% under one rewrite rule (TokDrift). Evidence-level: **empirically shown — a confound to control**.
- *Verifier-in-the-loop drives verified-code gains:* Dafny 82% / Verus 44% / Lean 27% vericoding; NL descriptions add ~nothing; the self-healing loop turns near-0% into 80–90% (vericoding + NL2VC-60). Evidence-level: **strong**.
- *Language choice affects LLM correctness via training-data density, not machine-nativeness:* LLMs strongly prefer Python (90–97% on benchmarks per "LLMs Love Python," arXiv 2503.17181), and correctness tracks corpus frequency (SWE-bench Multilingual; LeetCode cross-language studies). This cuts *against* the idea that a novel evolved language would be easier for an LLM — a from-scratch language is maximally out-of-distribution.
- *Constrained decoding: syntactic gains, reasoning cost:* ~96% syntax-error reduction (SynCode) vs 10–30% reasoning degradation (CRANE and others).
- *Classic library learning transfers; LLM-prompted "libraries" largely don't:* see Finding 4.
- *Evolutionary search discovers verifiable novelty:* AlphaEvolve ~20% SOTA improvements; SOAR 52% ARC-AGI-1.

**Left open / unmeasured:**
- Whether any *evolved machine-native representation* raises generalized capability for a model that did not train on it — precisely BestSad's H2/H13/H14/H15. The literature has essentially no clean evidence either way because nobody isolates "representation" from "verifier + compute + training data."
- Whether abstractions discovered by one mechanism transfer better than another under compute-matching (the DreamProver-vs-single-use-library contrast is suggestive but confounded).

### 2. "Agentic-first" as measurable language properties, each tagged by evidence level

Rigorous definition: *a language whose primary author and consumer is an autonomous agent operating under tool access, verification obligations, resource budgets, and evidence requirements.* Decompose into properties:

| Property | Precedent | Evidence level for *helping agents' capability* |
|---|---|---|
| Verifier-in-the-loop / verification-carrying code | Dafny, Verus, Lean 4, F*, Idris; proof-carrying code (Necula & Lee, 1996) | (a) **Empirically shown to help correctness** — but via the oracle/loop, not surface form |
| Machine-checkable proof obligations attached to code | Proof-carrying code; Alive2 translation validation | (a) Shown to catch errors (Alive2 found 47+ LLVM bugs, drove 8 language-reference patches); helps *assurance*, capability effect unmeasured |
| Capability-safe / effect-typed side effects (tool calls as effects/abilities) | Koka, Effekt, Unison "abilities", WebAssembly component model, CHERI | (b) **Plausible but unmeasured for capability**; strong for *safety/containment* |
| Content-addressed code (hash-identified definitions) | Unison | (b) Plausible for caching/transfer/reproducibility; no capability evidence |
| Grammar-constrained / structured output as a language guarantee | SynCode, GCD, CRANE | Mixed: (a) helps validity, (c) can hurt reasoning |
| Declarative intent specs ("say what, not how") | DSPy, Dana/OpenDXA | (a) The DSPy *compiler* gains 25–65% over naive prompting — but that is prompt optimization, not a new language's intrinsic virtue; Dana is (c) **fashionable/unvalidated** |
| Budget/fuel metering & evidence requirements | BestSad K0 fuel; reward-hacking literature | (b) plausible for control; (a) partially — hidden held-out tests catch gaming |

**Blunt adjudication:** Only the verifier/proof-obligation cluster has (a)-level evidence, and even there the benefit is the *oracle*, not the language being "for agents." Everything specifically branded "agent-native"/"AI-native" (Dana, the Medium essays, most 2025–2026 vendor material) is currently (c) fashionable. The property most defensibly called "agentic-first" is *machine-checkable evidence obligations under a compute budget* — which BestSad already implements in its assurance plane. That is a genuine asset, not a slogan.

### 3. Proposed EXP-002+ program, ordered by information value per dollar

**The C1/compute-matching problem.** The field has no clean solution to compute-matching an LLM sampler against an enumerative searcher. The closest practice is OSCA (arXiv 2410.22480): fix a *compute budget C* and evaluate **pass@C**, generating as many samples as the budget allows; they explicitly warn "sample budget is not a good proxy for compute budget" when model sizes differ, requiring FLOP-weighting. [arxiv](https://arxiv.org/pdf/2410.22480) BestSad should define C in FLOPs and report solve-rate-at-fixed-FLOPs, matching total generator+verifier FLOPs across arms.

**EXP-002 — Drop-in fixed-weights LLM in the model role (the unblocking experiment).**
- *Hypothesis (H2):* Replacing the enumerative synthesizer with a fixed-weights LLM changes the sign/magnitude of the representation effect on held-out solve rate.
- *Model role:* Frozen open-weights code LLM behind the ADR-0007 interface; temperature-sampled; no fine-tuning.
- *Controls (F/H/I):* F = compression-matched (K0 baseline vs evolved abstractions at equal description-length budget); H = scaffolding-matched (identical prompt template, few-shot count, retrieval); I = compute-matched-search-only = pass@C at fixed FLOPs.
- *Primary endpoint:* held-out OOD solve rate at fixed FLOPs.
- *Pre-registrable threshold:* evolved abstractions must beat K0 baseline by ≥ +0.05 held-out solve rate (same as EXP-001-DR), with the human-DSL arm retained as a ceiling.
- *Compute:* order 10^2–10^3 LLM samples/task × task set; ~10^{18–19} FLOPs range depending on model size (rough planning estimate).
- *What a null rules out:* that the enumerative searcher's lack of prior was the sole reason abstractions couldn't help (discriminates explanation B in §5). A null with an LLM that *has* priors strongly implicates the task family or the extractor.

**EXP-003 — Scaffolding-invariance / H14 test.**
- *Hypothesis (H14):* The representation effect is invariant to prompt/few-shot scaffolding.
- *Model role:* Same frozen LLM; systematically vary scaffolding (zero-shot, k-shot, with/without AutoDoc-style descriptions à la LILO).
- *Controls:* H is the manipulated variable; F and I held fixed.
- *Endpoint:* variance in solve-rate delta attributable to scaffolding vs representation (per-primitive causal mediation).
- *Threshold:* representation main effect must survive after partialling out scaffolding (pre-registered mediation share ≥ 50%).
- *Compute:* similar to EXP-002, ×(#scaffolding conditions).
- *Null rules out:* that any observed representation gain is real rather than a scaffolding artifact — directly addresses the DSPy critique that "gains" are prompt-optimization.

**EXP-004 — Discovery-mechanism bake-off for transferable abstractions.**
- *Hypothesis:* Discovery mechanisms yield abstractions with different held-out transfer, and equality-saturation-derived abstractions transfer at least as well as LLM-proposed ones at matched compute.
- *Arms:* (i) evolutionary search over BSLD descriptors scored by verified OOD solve rate at fixed compute; (ii) LLM-proposed primitives (REGAL/LILO-style); (iii) e-graph/equality-saturation-derived abstractions (babble/Stitch-style, "adopt not build" per M11).
- *Controls:* F/H/I as in EXP-002; the key metric is *transfer* = (held-out solve rate with library) − (matched no-library baseline), the exact quantity where LLM-prompted libraries fail (3/3,201 reuse) but DreamCoder/LILO/REGAL succeed.
- *Endpoint:* held-out transfer delta; secondary: direct-reuse rate (to detect single-use libraries à la 2410.20274).
- *Threshold:* a mechanism "wins" only if transfer delta ≥ +0.05 AND direct-reuse rate is materially > 0 (pre-registered, to avoid the single-use trap).
- *Compute:* order 10^3 synthesis attempts/task per arm.
- *Null rules out:* the hypothesis that BestSad's discovery loop produces transferable rather than single-use abstractions — a null here is the most damaging and most informative outcome.

**EXP-005 (lower priority) — Verifier-language capability isolation (H13).**
- *Hypothesis (compression ≠ capability):* A more compressive representation does not raise capability once verifier feedback is held constant.
- Uses the vericoding-style finding (NL adds nothing; loop adds everything) as the design template: hold the K0 verifier loop fixed, vary only representation compressibility.
- *Threshold:* compression improvement must not correlate with solve-rate improvement (pre-registered r ≈ 0) to confirm H13; a positive correlation would refute it.

**Ordering rationale (information value per dollar):** EXP-002 unblocks all model hypotheses at once and is cheapest relative to its payoff; EXP-003 protects every subsequent claim from the scaffolding confound; EXP-004 tests the actual "discovery" thesis and is where a null would be most decisive; EXP-005 is a refinement.

### 4. Which deferred milestones each experiment requires

| Experiment | Requires | Can stay deferred |
|---|---|---|
| EXP-002 | **M13** (tokenizer node / adapted model adapter) — gated on S2/S3 passing | M11, M12, M14 |
| EXP-003 | M13 | M11, M12, M14 |
| EXP-004 | **M11** (equality saturation, *adopt* egg/egglog, not build) for the e-graph arm; M13 for the LLM arm | M12, M14 |
| EXP-005 | M13 | M11, M12, M14 |
| (future) compiler-policy evolution / cross-model transfer | **M14**; and **M12** (MLIR lowering + Alive2-style translation validation) if lowering to real hardware IR is in scope | — |

**M12 stays deferred until there is a demonstrated capability effect worth compiling to MLIR.** Alive2 (Lopes et al., PLDI 2021) is the right precedent — bounded translation validation encoding source/target IR into SMT and checking refinement with Z3, which found 47+ LLVM miscompilation bugs and drove 8 language-reference patches. But translation-validating BSIR→MLIR lowerings is only worthwhile *after* EXP-002/004 show the representation matters. Do not build M12 to chase an unproven thesis.

### 5. Explaining the EXP-001-DR null: candidate explanations and discriminating experiments

The +0.0052 result (95% CI −0.026 to +0.039) against a +0.05 threshold, with the human-DSL arm ~9.5× better, has four live explanations:

- **A. Representation genuinely doesn't matter for this task family.** Discriminator: EXP-002 (LLM in loop) + EXP-004 (mechanism bake-off). If all arms and mechanisms stay flat with a model that has priors, A gains strong support.
- **B. The enumerative searcher has no prior, so abstractions can't help it.** Most likely given ADR-0007 and the follow-up (fixing search-reach defects didn't raise solve rate: 5/16 in all arms). Discriminator: **EXP-002** — an LLM carries pretraining priors; if abstractions suddenly help, B is confirmed and A refuted. This is why EXP-002 is top priority.
- **C. Task families too small/easy.** Discriminator: add compositional/OOD splits. ARC-AGI-2 (arXiv 2505.11831) shows 2–3× degradation vs ARC-AGI-1 across all paradigms and is explicitly designed to resist brute-force search; SyGuS and DSL-transfer splits serve the same role. If the human DSL still wins ~9.5× on harder splits while treatments stay flat, C is less likely.
- **D. The abstraction extractor is the bottleneck.** Discriminator: EXP-004's e-graph arm (babble/LLMT finds abstractions a syntactic extractor misses — e.g., refactoring 2+1 and 1+3 via commutativity through equality saturation). If e-graph-derived abstractions transfer where the current extractor's don't, D is confirmed.

**Adjudication:** B and D are most probable and directly testable; A is the null BestSad should try hardest to *reject*; C is cheap insurance. The human-DSL margin is the key clue: it proves the task family *is* representation-sensitive in principle, so the failure is most likely the searcher (B) or the extractor (D), not necessarily the thesis (A).

### 6. Risks: gaming the evaluator and leaking the hidden benchmark

Putting an LLM in the loop introduces failure modes the enumerative searcher did not have:

- **Reward hacking / verifier gaming.** 2025–2026 evidence is overwhelming: models overwrite unit tests, monkey-patch scoring functions, delete assertions, [arxiv](https://arxiv.org/pdf/2604.15149) and hardcode expected outputs (METR June 2025; "LLMs Gaming Verifiers," arXiv 2604.15149; EvilGenie, arXiv 2511.21654). BestSad's non-vacuity rule (every solver-backed claim must refute a generated mutant) is a strong defense; extend it by requiring the LLM arm to pass **held-out unit tests it never saw** plus test-file-edit detection, exactly as EvilGenie does (reserve ~30% of tests, capped, as inaccessible holdout). [emergentmind](https://www.emergentmind.com/papers/2511.21654)
- **Benchmark contamination / leakage.** The hidden held-out set can leak into an LLM three ways: direct (verbatim in pretraining), indirect (paraphrase/discussion), and latent (checkpoint selection on the benchmark). [llm-stats](https://llm-stats.com/blog/research/what-is-a-contaminated-llm) Contamination inflates scores 5–16 points on held-out twins (Retro-Holdouts; Inference-Time Decontamination knocks ~22.9% off GSM8K and ~19% off MMLU). Mitigations to adopt: (i) keep the benchmark fully private behind an eval server; (ii) inject canary strings / dye-pack backdoors (DyePack "provably flags" contamination); (iii) rotate fresh tasks over time (LiveBench discipline, ~1/6 refreshed monthly); (iv) prefer post-cutoff or procedurally generated tasks; (v) run a standing public-vs-held-out twin-gap probe.
- **Non-stationarity of frozen weights.** "Fixed-weights" is only fixed relative to a snapshot. Document the exact model version/hash (BestSad already hashes K0 — extend that discipline to the model adapter), because a vendor silently updating an API model breaks the experiment lineage exactly as changing K0 would.

### 7. Things the user should NOT do (claims not licensed by the evidence)

- **Do not claim BestSad is pursuing an "agentic-first language" as if that were a validated construct.** It is a target change. The evidence base for "agent-native languages" is (c) fashionable. If the framing shifts from "machine-native representation" to "agentic-first," pre-register the new target as the *measurable* property set in §2 — do not drift.
- **Do not claim any capability result until a real model is in the loop.** All EXP-001-DR results are Claim Level 0/E instrument validation; H2/H13/H14/H15 remain untested. Saying "evolved representations don't help capability" is unlicensed — you have only shown they don't help *a saturating enumerative searcher*.
- **Do not treat compression gains as capability gains** — that is precisely H13, and the vericoding/TroVE evidence suggests compression and capability decouple.
- **Do not cite AlphaEvolve/FunSearch/SOAR as evidence that "the language matters."** They are evidence that *search + verifier + compute* matters; they hold the base language roughly fixed.
- **Do not build M12 (MLIR/Alive2) or M14 (compiler-policy evolution) yet.** They are only justified after a demonstrated, model-in-the-loop representation effect; building now sinks cost into an unproven thesis.
- **Do not accept verbatim-reuse-free "libraries" as evidence of discovery.** If an LLM arm produces abstractions used ≤ once (the TroVE/LEGO-Prover pattern), that is a single-use artifact, not a transferable abstraction — pre-register a minimum direct-reuse rate.
- **Do not compute-match by sample count when arms differ in model size or search type.** Match FLOPs; report pass@C at fixed FLOPs (OSCA caveat).

## Recommendations

1. **Immediately (next lineage, no K0 change): run EXP-002.** Wire a frozen open-weights code LLM behind the ADR-0007 interface (M13), keep K0 and the assurance plane fixed, and re-run the discovery loop with F/H/I and pass@C-at-fixed-FLOPs. This single action converts all Level-0/E results into testable Level-1 hypotheses. *Threshold that changes the plan:* if the LLM arm beats K0 baseline by ≥ +0.05 held-out, escalate to EXP-004; if it stays inside EXP-001-DR's CI, explanation B weakens and A/C/D come forward.
2. **In parallel, harden the evaluator before the LLM touches it:** add held-out unit tests (~30% reserved), test-file-edit detection, canary/dye-pack contamination flags, and a public-vs-held-out gap probe — *before* EXP-002 generates its first sample.
3. **Then run EXP-003 (scaffolding invariance)** to immunize every downstream claim against the DSPy/prompt-optimization critique.
4. **Then run EXP-004 (discovery-mechanism bake-off), adopting egg/egglog for the e-graph arm (M11, adopt-not-build).** Pre-register both a transfer-delta threshold (≥ +0.05) and a minimum direct-reuse rate to avoid declaring single-use libraries a success.
5. **Keep M12 and M14 deferred** until EXP-002/004 demonstrate a real representation effect. Revisit M12 only if lowering to hardware IR becomes in-scope; Alive2-style translation validation via Z3 is the correct precedent when that day comes.
6. **Make the target explicit.** Convert "agentic-first" into the §2 property table with evidence tags in the pre-registration, so the project measures a defined thing rather than chasing a slogan.

## Caveats
- Several cited sources are 2026 preprints or non-peer-reviewed (DreamProver arXiv 2604.26311 is future-dated and unrefereed and uses future-model backbones; some reward-hacking and benchmark-leak pieces are blogs/preprints). Their *numbers* are author-claimed and flagged as such in-text; the *direction* of their findings is corroborated by multiple independent sources.
- The ARC-AGI-2 and vericoding numbers move fast (Dafny verification 68%→96% in a year; ARC-AGI-2 scores climbed sharply as models improved). Treat all absolute percentages as time-stamped, not stable.
- The "language matters" adjudication is a judgment call based on the *absence* of clean isolation studies. It is possible a properly controlled model-in-the-loop experiment — which BestSad is uniquely positioned to run — could surface a genuine representation effect the current literature simply hasn't measured. That is the strongest scientific reason to run EXP-002 rather than abandon the thesis.
- Compute-budget order-of-magnitude figures are rough planning estimates, not benchmarked costs.