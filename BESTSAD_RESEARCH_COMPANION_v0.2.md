# Bestsad Research Companion v0.2

**Document ID:** BESTSAD-RC-001  
**Project:** Bestsad  
**Version:** 0.1  
**Date:** 2026-08-17  
**Purpose:** Evidence record, literature synthesis, source annotations, limitations, and derivation trail for BESTSAD-RAES-001.

---

## 1. Research method

This companion records the primary-source literature and official technical documentation used to construct Bestsad Research Architecture & Experimental Specification v0.1.

### 1.1 Source policy

Priority was given to:

1. peer-reviewed papers where available;
2. original arXiv/preprint papers for 2025-2026 work not yet fully published;
3. official compiler/tool documentation;
4. official Navajo Nation and Smithsonian material for Code Talker history;
5. a lexical teaching source for the specific Diné word-root inspiration, with the explicit caveat that the project coinage is not asserted to be grammatically canonical Navajo.

Secondary summaries were not used as the basis for technical claims when a primary paper or official documentation was available.

### 1.2 Evidence labels

- **Established result:** directly demonstrated in a cited source.
- **Supported direction:** several sources make the design direction plausible, but Bestsad's exact mechanism is new.
- **Bestsad synthesis:** architectural combination proposed here; not a claim from any single source.
- **Open hypothesis:** should be tested and may fail.

---

## 2. What the literature already establishes

The literature does **not** yet establish that an LLM can autonomously invent a broadly superior general-purpose programming language and recursively improve itself with it. It establishes important pieces of that possibility.

### 2.1 Systems can learn reusable programming abstractions

**DreamCoder** learns domain-specific programming languages/libraries by alternating program search, library growth, and neural search-policy learning. It demonstrates that useful abstractions can be acquired rather than fixed by a human language designer.

**Stitch** improves the scalability of library learning by finding compressive abstractions from a program corpus much faster and with much less memory than prior deductive approaches in its evaluation.

**LILO** combines LLM-guided synthesis, Stitch-style compression, and automatic naming/documentation of learned abstractions. It supports the idea that learned abstractions can become both machine-useful and human-interpretable.

**Important caution:** *Library Learning Doesn't* shows that aggregate performance gains in some mathematical library-learning systems did not imply meaningful library reuse. In its studied systems, reuse was rare and self-correction/self-consistency explained much of the gain. Bestsad therefore measures primitive reuse explicitly and includes matched random/frequency controls.

**Architecture implication:** abstraction discovery is credible, but reuse must be directly measured and should not be inferred from benchmark accuracy.

---

## 3. AI-oriented syntax and representation

### 3.1 SimPy

*AI Coders Are Among Us* proposes an AI-oriented Python grammar called SimPy. SimPy preserves Python AST structure while reducing syntax/formatting overhead; the paper reports token reductions for CodeLlama and GPT-4 while maintaining or improving task performance in its experiments.

**Implication:** human-oriented syntax is not necessarily model-efficient.

**Limit:** SimPy is heuristic grammar redesign, not autonomous semantic language discovery.

### 3.2 CodeBPE

The CodeBPE/subtokenization study shows that source-code tokenizer choices materially change sequence length and can reduce it without downstream performance loss under evaluated settings.

**Implication:** tokenizer design is a confound and later optimization dimension.

### 3.3 ShortCoder and Token Sugar

ShortCoder applies AST-preserving simplification and training data construction to encourage shorter code generation. Token Sugar learns reversible shorthand for frequent token-heavy patterns and trains models with those shorthands.

**Implication:** syntax and shorthand can improve efficiency, but these results are not evidence that a new semantic language increases reasoning capability.

**Bestsad consequence:** E1 isolates projection/syntax improvements before semantic abstraction experiments.

---

## 4. Synthesizing the language, not only the program

### 4.1 Synthesizing DSLs for Few-Shot Learning

Krogmeier and Madhusudan formalize a DSL synthesis problem: given a base language and few-shot learning instances, synthesize a grammar/hypothesis class that makes small solutions found on training samples generalize to corresponding testing samples under specified conditions. They prove decidability for particular classes of languages/semantics.

**Established result:** language/hypothesis-class design can itself be formulated as a synthesis problem.

**Limit:** the theory operates over constrained symbolic settings with a fixed base language and semantics. It does not provide an end-to-end LLM language-evolution system.

**Bestsad synthesis:** use this conceptual inversion - search for a language that makes good programs easier to discover - while retaining a fixed semantic kernel in early phases.

---

## 5. Learned symbolic-like languages and interpreters

### 5.1 Neural Language Interpreter (NLI)

The 2026 NLI work is one of the closest technical precedents to Bestsad. It learns a discrete, symbolic-like programming language end-to-end and a differentiable neural executor that interprets variable-length sequences of learned primitives. Gumbel-Softmax enables optimization over discrete program choices, and the system refines programs at test time through gradients.

**Established result:** a neural architecture can discover a discrete primitive vocabulary and learn to execute sequences of those primitives rather than relying entirely on a hand-designed DSL.

**Limits relevant to Bestsad:** learned neural semantics are not automatically exact, formally specified, or suitable as trusted compiler semantics. The demonstrations are not a production general-purpose programming language.

**Architecture consequence:** Bestsad allows learned primitives only at `EXP` maturity until they have an explicit semantic bridge.

### 5.2 Differentiable Meta-Circular Interpreter (DMCI)

DMCI compiles a self-hosting subset of Scheme into differentiable computation graphs. It supports program-and-parameter co-search in which discrete program structures can be proposed externally while gradients optimize continuous parameters through an interpreter.

**Established result:** executable program structure and gradient-based parameter optimization can be combined in a meta-circular setting.

**Architecture consequence:** Bestsad's long-run search architecture should combine discrete evolutionary/symbolic mutations with gradient optimization where the search dimensions are continuous.

---

## 6. Primitive discovery as a research target

### 6.1 GrowLibm

GrowLibm reframes numerical superoptimization as **library learning**: rather than only optimizing programs against a fixed primitive set, it asks which new mathematical primitives would improve a workload. It mines candidate primitives from search, semantically deduplicates/generalizes them, and ranks them by counterfactual utility. The paper reports meaningful kernel and end-to-end gains after expert implementations are supplied.

**Established result:** the set of available primitives can itself be optimized according to counterfactual workload utility.

**Limit:** GrowLibm does not automatically implement arbitrary discovered primitives; expert implementation remains part of the evaluated workflow.

**Bestsad synthesis:** generalized primitive discovery should rank candidates by expected capability benefit, reuse, learning cost, and verification cost rather than frequency alone.

---

## 7. Search-state representation

### 7.1 GraphIR

GraphIR argues that executable source code is not always the best state representation for LLM-guided architecture evolution. It separates a computation skeleton, mutation surface, and validity envelope to make search edits structurally meaningful and constrained.

**Supported direction:** the object given to an evolutionary model should expose the dimensions it is allowed to change while making validity constraints explicit.

**Bestsad synthesis:** BSIR incorporates a semantic graph, mutation surface, and validity envelope, but Bestsad extends the concept from neural architecture search to executable language/representation evolution.

---

## 8. Evolutionary coding and self-improvement

### 8.1 AlphaEvolve

AlphaEvolve combines LLM proposals, code execution, evaluators, and evolutionary selection. Its published white paper reports improvements in scientific/algorithmic problems and computational infrastructure.

**Established result:** LLM-driven evolutionary search over executable code can discover nontrivial algorithmic improvements when objective evaluators are available.

**Architecture consequence:** evaluator-grounded evolution is a viable outer loop for Bestsad genomes.

### 8.2 SOAR

SOAR alternates evolutionary program search with hindsight fine-tuning on search traces, enabling the generating model to improve using experience collected during search.

**Established result:** search traces, including the structure of prior attempts, can be converted into training signal for future synthesis.

**Bestsad consequence:** failed and successful genome mutations should be retained as a learning corpus rather than discarded.

### 8.3 Magellan

Magellan applies an AlphaEvolve-style loop to compiler optimization heuristics, synthesizing executable decision logic for LLVM and other compiler contexts.

**Established result:** the compiler's optimization policy itself can be a target of agentic/evolutionary search.

**Bestsad consequence:** compiler-strategy evolution is justified as a later, separately controlled axis.

### 8.4 CodeEvolve and quality-diversity

Open evolutionary coding work uses island-model genetic search and crossover to preserve diversity and combine candidate strengths.

**Supported direction:** Bestsad should preserve multiple language species rather than converge immediately on one winner.

---

## 9. Equality saturation and equivalence-rich optimization

### 9.1 egg

The `egg` work demonstrates a fast/extensible e-graph implementation for equality saturation. E-graphs compactly represent congruence/equivalence classes of many expressions.

**Established result:** e-graphs are a practical substrate for rewrite-driven optimization and synthesis.

### 9.2 Scaling limitations

Sketch-guided equality saturation shows that naive EqSat may fail to scale to complex compiler optimizations because e-graphs can grow dramatically. Guidance can reduce resource usage by orders of magnitude in the evaluated problems.

**Architecture consequence:** Bestsad cannot simply “turn on equality saturation.” It needs budgets, guidance, and explicit strategy search.

### 9.3 EggMind / EqSat strategy synthesis

EggMind uses an explicit DSL for EqSat strategy and an LLM-guided workflow to synthesize strategy while controlling e-graph growth. The paper reports improved cost/resource tradeoffs on its evaluations.

**Established result:** rewrite strategy itself can be synthesized; directly evolving raw backend code is not necessarily the best search representation.

**Bestsad synthesis:** separate semantic rewrite rules from the strategy controlling their application.

### 9.4 Semantic foundations

Recent formal work develops a fixpoint semantics of equality saturation and relates it to tree automata/chase-like procedures.

**Architecture consequence:** Bestsad should preserve explicit semantics for equivalence engines rather than use e-graphs purely as heuristic optimizer data structures.

---

## 10. Compiler substrate and versioning

### 10.1 MLIR extensible/dynamic dialects

Official MLIR documentation states that extensible dialects can add operations and types at runtime, and dynamic dialects can be defined at runtime with dynamic operations, types, and attributes. Dynamic operations provide verifiers and may define custom parsers/printers/folding hooks.

**Established capability:** MLIR can host runtime-extensible language constructs without recompiling the entire compiler framework.

### 10.2 MLIR traits/interfaces and Transform dialect

MLIR's language reference and Transform dialect provide mechanisms for abstract semantic properties, verification constraints, and explicit transformation control.

**Architecture consequence:** MLIR is a strong execution/lowering substrate for Bestsad experimentation.

### 10.3 MLIR bytecode compatibility

The MLIR bytecode format is versioned and designed for stable compatibility, but its guarantees assume immutable dialect semantics. That caveat directly matters to Bestsad.

**Bestsad consequence:** Bestsad cannot rely on raw MLIR bytecode compatibility as the complete answer to evolving dialect semantics. Bestsad primitives need their own semantic IDs, migration rules, and kernel-version lineage.

---

## 11. Translation validation and verified compilers

### 11.1 Alive2

Alive2 is a translation-validation system for LLVM IR transformations. It provides a practical model for proving/refuting whether an optimization refines the source program under LLVM semantics.

**Architecture consequence:** Bestsad compiler changes should be independently validated where compatible with existing tooling rather than assumed correct because output compiles.

### 11.2 Verified Dafny compiler/VCG

The verified Dafny work demonstrates a mechanized semantics, verified verification-condition generator, and verified compiler for a meaningful subset, ultimately targeting CakeML.

### 11.3 RustCompCert

RustCompCert is ongoing work toward semantics preservation and borrow-checking guarantees for a sequential Rust subset via CompCert.

**Supported direction:** end-to-end compiler correctness is difficult but tractable for restricted languages. Bestsad should start with a small semantic kernel if it wants strong verification.

**Bestsad synthesis:** verification pressure is a fitness dimension, but full mechanized correctness is staged rather than required for every experimental macro.

---

## 12. Extracting algorithms from neural models

### 12.1 MIPS

MIPS trains neural networks on algorithmic tasks and then uses mechanistic-interpretability-driven program synthesis to distill learned behavior into Python programs.

### 12.2 Weights to Code / Discrete Transformer

2026 work extends algorithm-extraction ideas toward Transformer-like architectures designed to make executable algorithm extraction more tractable.

**Supported direction:** the neural/symbolic boundary can be traversed in both directions: programs can train models, and aspects of trained computation can sometimes be distilled back into programs.

**Bestsad hypothesis:** future primitive discovery may use model internals as evidence for candidate abstractions, but v0.1 does not depend on successful mechanistic extraction.

---

## 13. Emergent machine communication

### 13.1 Grounded compositional language

Mordatch and Abbeel demonstrated agents learning streams of discrete symbols with vocabulary/syntax-like structure in cooperative environments.

**Established result:** machine agents can develop task-driven discrete communication rather than relying only on human natural language.

### 13.2 CLSR symbolic communication

2026 CLSR work lets LLM agents invent and evolve compact symbolic protocols at test time and reports substantial token reductions on evaluated multi-agent reasoning tasks.

**Supported direction:** model-generated symbolic languages can be useful communication artifacts.

**Limit:** symbolic communication protocols are not equivalent to formally executable programming languages.

### 13.3 Latent communication literature

A 2026 latent-communication survey organizes methods where agents exchange embeddings, hidden states, or caches rather than text, highlighting efficiency and alignment questions.

A separate 2026 experimental paper reports that latent channels retained much more probe-accessible feature information than text under compression, but found no task-level advantage over text on its tested concept tasks and concluded that much lost information appeared surface-form-related.

**Critical negative evidence:** “latent” should not be equated with “more intelligent.”

**Bestsad consequence:** latent-like representations are a later controlled experiment, not the default canonical language.

---

## 14. Benchmark coevolution

### 14.1 Self-modifying Lean proof agents

2026 work coevolves a mutable Lean proof-agent workspace and an active benchmark curriculum while retaining a trusted Lean verifier. The paper reports higher held-out solve rates than its fixed-benchmark comparison in the reported experiment.

**Established result:** an evolving curriculum can sustain pressure while a trusted verifier anchors correctness.

**Critical design lesson:** changing training tasks makes raw generation-to-generation scores incomparable; held-out evaluation is needed.

### 14.2 TRACE self-evolving benchmark

TRACE proposes generating harder benchmark tasks accompanied by reproducible/validatable trajectories.

**Supported direction:** benchmarks themselves can evolve, but reproducibility and independent validation must evolve with them.

**Bestsad consequence:** curriculum may evolve, headline evaluation may not.

---

## 15. Reward hacking and benchmark integrity

This research area strongly affects Bestsad because a language evolution system could compress evaluator exploits into apparently useful primitives.

### 15.1 EvilGenie

EvilGenie constructs programming environments where agents can hardcode tests or edit testing files and evaluates detection strategies.

### 15.2 TRACE reward-hack detection

A separate 2026 TRACE benchmark studies detection of reward-hacking trajectories in code environments across a large taxonomy.

### 15.3 SpecBench

SpecBench uses separate visible validation and hidden specification-oriented evaluation for long-horizon coding tasks, explicitly measuring reward hacking.

### 15.4 Reward Hacking Benchmark / hack-verifiable environments

Other 2026 work introduces multi-step reward-hacking suites and environments where exploit behavior can be deterministically verified.

### 15.5 Benchmark-protocol audits

Recent audits argue that exposure and evaluation-protocol weaknesses can significantly inflate apparent agent scores.

**Bestsad architectural conclusion:** evaluator integrity is not just “security hardening”; it is part of experimental validity. The candidate generator and evaluator must be separate trust domains.

---

## 16. Why Bestsad separates semantics from representation

This architectural decision is a **Bestsad synthesis** built from several strands:

- SimPy/ShortCoder/Token Sugar show that surface form can change while semantics remain stable.
- DSL synthesis and DreamCoder show that the set of available abstractions/hypothesis classes matters.
- NLI shows that discrete primitive vocabularies can be learned.
- GraphIR shows that a mutation-oriented search representation can differ from executable source.
- MLIR shows that several language/IR layers can coexist and lower through a compiler stack.

The resulting architecture is:

`semantic identity -> BSIR -> one or more model/human projections -> MLIR/LLVM execution`

This lets Bestsad test syntax, graph serialization, and model-specific languages without changing the truth conditions of the program.

---

## 17. Why the trusted kernel is fixed at launch

A mutable semantic kernel would make early results uninterpretable. If both the meaning of operations and the language used to express them change, a better score could come from:

- richer built-in functionality;
- hidden benchmark knowledge;
- weaker correctness semantics;
- evaluator mismatch;
- genuine representation improvement.

The project would not know which.

The fixed kernel is therefore not a philosophical claim that semantics must always be immutable. It is an experimental control.

---

## 18. Why “shorter” is not the primary objective

Token-efficient code research provides evidence that representation can reduce cost. It does not establish that compression increases reasoning ability.

Bestsad therefore distinguishes:

- **compression gain** - fewer tokens/bytes;
- **search gain** - fewer candidate expansions or less inference needed;
- **capability gain** - more verified OOD problems solved;
- **runtime gain** - faster execution;
- **verification gain** - easier/cheaper correctness evidence.

A language can score well on one and poorly on another.

---

## 19. Why cross-model transfer is required

A model can learn arbitrary private codes. Such a code may be useful for that model without representing a generally valuable computational abstraction.

Bestsad therefore distinguishes:

- `private compression`: useful only to creator model;
- `learnable dialect`: another model can acquire it cheaply;
- `semantic abstraction`: value persists when surface representation changes;
- `universal candidate`: independently rediscovered or broadly transferable.

Cross-model transfer is a proposed Bestsad criterion, not a standard requirement in existing language-learning literature.

---

## 20. Convergent language evolution as evidence

A future high-value experiment is to run independent Bestsad populations with different seeds/models and compare discovered semantic abstractions.

If independent populations repeatedly discover semantically equivalent primitives, that would be stronger evidence that the abstraction reflects computational structure rather than an arbitrary naming accident.

This is an **open hypothesis** and should not be assumed.

---

## 21. Evidence-to-architecture matrix

| Bestsad component | Main evidence | Status |
|---|---|---|
| learned abstraction library | DreamCoder, Stitch, LILO | established precursor |
| explicit reuse metric | Library Learning Doesn't | corrective requirement |
| AI-oriented projection | SimPy, ShortCoder, Token Sugar | established precursor |
| tokenizer as variable | CodeBPE | established precursor |
| DSL synthesis objective | Krogmeier & Madhusudan | formal precursor |
| learned discrete primitive language | NLI | strong direct precursor |
| discrete + gradient co-search | DMCI | established precursor |
| primitive utility discovery | GrowLibm | strong direct precursor |
| mutation-oriented graph state | GraphIR | supported adaptation |
| evolutionary outer loop | AlphaEvolve, CodeEvolve | established precursor |
| search-to-training loop | SOAR | established precursor |
| compiler policy evolution | Magellan | established precursor |
| equivalence classes | egg/EqSat | established precursor |
| synthesized EqSat strategy | EggMind | established precursor |
| extensible compiler IR | MLIR docs | production capability |
| translation validation | Alive2 | production/research capability |
| verified restricted compilers | Dafny verified compiler, RustCompCert | feasibility evidence |
| neural -> program extraction | MIPS, Weights to Code | supported future direction |
| emergent symbolic communication | Mordatch & Abbeel, CLSR | supported future direction |
| latent communication | survey + Wenzel study | mixed/negative evidence |
| evolving curriculum | Lean coevolution, TRACE benchmark | established precursor |
| independent anti-gaming evaluator | reward-hacking benchmarks | critical requirement |
| unified model-language-compiler-verifier coevolution | no single source | **Bestsad synthesis** |
| Semantic Gain metric | no single source | **Bestsad proposal** |
| semantic maturity ladder EXP->CORE | no single source | **Bestsad proposal** |

---

## 22. What is still missing in the field

> **v0.2 status:** re-audited at the v0.2 cutoff. The ten-part gap **still holds as an integration claim**, but items 3, 6, 7 and 10 now each have credible standalone instantiations elsewhere, and items 1 and 4 have near-misses (see Section 29). The gap is narrowing. Treat this list as decaying evidence and re-run the sweep before every Gate transition.

As of the evidence cutoff, this research pass did not identify a mature system that simultaneously:

1. evolves a machine-native executable language;
2. separates canonical semantics from model-specific projections;
3. discovers primitives based on transfer/counterfactual utility;
4. evolves compiler transformation policy;
5. can optionally adapt the model to the evolved language;
6. preserves proof/equivalence lineage;
7. uses independent anti-gaming evaluation;
8. measures cross-model language transfer;
9. maintains language genealogy/speciation;
10. isolates causal gains through staged ablations.

This absence is not proof that no such project exists. It is the gap identified by this search and should be revisited continuously.

---

## 23. Risks and counterarguments

### 23.1 Human languages may already be close to model-optimal
Large code corpora and model pretraining may make conventional languages unusually strong priors. Bestsad could spend substantial search compute rediscovering functional abstractions humans already know.

### 23.2 Search cost may exceed representation benefit
A language that saves inference tokens but requires enormous evolutionary search to discover may be economically inferior.

### 23.3 Learned abstractions may overfit domains
DSL specialization is useful precisely because it narrows a hypothesis class. The same property may hurt transfer.

### 23.4 Private codes may look impressive but be brittle
Compact symbolic protocols can be efficient while being uninterpretable, model-specific, or difficult to transfer.

### 23.5 Verification can constrain innovation
Strict exact semantics may exclude useful approximate/neural operations. Bestsad addresses this with maturity levels rather than pretending every useful learned operator is exact.

### 23.6 Evolution can game metrics
Reward-hacking literature demonstrates that executable agents can exploit evaluation environments. Bestsad's evaluator isolation is therefore essential.

### 23.7 Language growth can become library bloat
Without complexity penalties and reuse metrics, the easiest “language” is one primitive per task. DSL-synthesis theory and Bestsad's controls explicitly guard against this trivial solution.

---

## 24. Naming research record

Official Navajo Nation material states that the Navajo Code Talkers developed an unbreakable code using Diné Bizaad during World War II. Smithsonian/National Museum of the American Indian material describes Code Talkers as communications specialists and notes that some groups developed special codes within their Native languages.

For the lexical inspiration, Navajo Word of the Day describes **béésh** literally as knife and explains its use in expressions involving metal objects/technology; its entry for **bizaad** explains `saad` as approximating words/speech and `bizaad` as language.

Therefore the project record should say:

> Bestsad is an English project coinage inspired by Diné/Navajo lexical roots *béésh* and *saad*, and by the historical example of the Navajo Code Talkers developing a specialized military code using Diné Bizaad. It is not asserted to be a canonical Navajo compound without qualified linguistic validation.

---

## 25. Research source annotations

The machine-readable source ledger is `BESTSAD_SOURCE_LEDGER_v0.1.csv`. Key sources are summarized below.

### S01 DreamCoder
**URL:** https://arxiv.org/abs/2006.08381  
**Use:** learned languages/libraries, wake-sleep program induction.  
**Key relevance:** demonstrates iterative acquisition of symbolic abstractions and neural search guidance.

### S02 Stitch
**URL:** https://arxiv.org/abs/2211.16605  
**Use:** scalable abstraction/library extraction.  
**Key relevance:** corpus-guided synthesis can extract reusable abstractions far more efficiently than older deductive library learning in its evaluation.

### S03 LILO
**URL:** https://arxiv.org/abs/2310.19791  
**Use:** LLM + symbolic library learning + auto-documentation.  
**Key relevance:** supports readable learned abstractions and language-guided use.

### S04 Library Learning Doesn't
**URL:** https://arxiv.org/abs/2410.20274  
**Use:** negative/corrective evidence.  
**Key relevance:** warns that performance gains do not prove library reuse.

### S05 SimPy
**URL:** https://arxiv.org/abs/2404.16333  
**Use:** AI-oriented syntax.  
**Key relevance:** semantics-preserving grammar redesign can reduce model tokens.

### S06 CodeBPE
**URL:** https://arxiv.org/abs/2308.00683  
**Use:** tokenizer confound.  
**Key relevance:** subtokenization choices change code sequence length without necessarily changing downstream quality.

### S07 ShortCoder
**URL:** https://arxiv.org/abs/2601.09703  
**Use:** token-efficient source transformation/training.  
**Key relevance:** reinforces projection optimization as a distinct research axis.

### S08 Token Sugar
**URL:** https://arxiv.org/abs/2512.08266  
**Use:** reversible learned shorthand.  
**Key relevance:** frequent semantic-ish patterns can be assigned token-efficient code shorthands.

### S09 Synthesizing DSLs for Few-Shot Learning
**URL:** https://arxiv.org/abs/2508.16063  
**Use:** formal language synthesis framing.  
**Key relevance:** makes the hypothesis class/DSL itself a synthesis target.

### S10 Neural Language Interpreter
**URL:** https://arxiv.org/abs/2604.18907  
**Use:** learned discrete language + executor.  
**Key relevance:** closest direct evidence that a neural system can learn a discrete symbolic-like programming vocabulary end-to-end.

### S11 Differentiable Meta-Circular Interpreter
**URL:** https://arxiv.org/abs/2606.09930  
**Use:** hybrid discrete/gradient search.  
**Key relevance:** executable program structure can participate in differentiable optimization through an interpreter.

### S12 GrowLibm
**URL:** https://arxiv.org/abs/2603.24812  
**Use:** primitive discovery.  
**Key relevance:** asks which primitives should exist and ranks them by counterfactual workload utility.

### S13 GraphIR
**URL:** https://arxiv.org/abs/2608.01633  
**Use:** mutation-oriented search state.  
**Key relevance:** separates computation skeleton, mutation surface, and validity envelope for LLM-guided evolution.

### S14 AlphaEvolve
**URL:** https://arxiv.org/abs/2506.13131  
**Use:** evolutionary executable-code loop.  
**Key relevance:** objective evaluators can guide LLM-based evolutionary discovery.

### S15 SOAR
**URL:** https://arxiv.org/abs/2507.14172  
**Use:** self-improving program synthesis.  
**Key relevance:** search experience can be converted into model improvement.

### S16 Magellan
**URL:** https://arxiv.org/abs/2601.21096  
**Use:** compiler-policy evolution.  
**Key relevance:** compiler heuristics can be synthesized/evolved against macro-benchmarks.

### S17 CodeEvolve
**URL:** https://arxiv.org/abs/2510.14150  
**Use:** island-model evolutionary coding.  
**Key relevance:** motivates speciation/diversity mechanisms.

### S18 egg
**URL:** https://arxiv.org/abs/2004.03082  
**Use:** e-graphs/equality saturation.  
**Key relevance:** efficient representation of many equivalent expressions.

### S19 Sketch-Guided Equality Saturation
**URL:** https://arxiv.org/abs/2111.13040  
**Use:** EqSat scaling limitations.  
**Key relevance:** unguided saturation can be intractable; search guidance matters.

### S20 EggMind
**URL:** https://arxiv.org/abs/2604.17364  
**Use:** LLM-synthesized EqSat strategy.  
**Key relevance:** strategy DSL + tractability guidance provides a template for separating rewrite semantics from search policy.

### S21 Semantic Foundations of Equality Saturation
**URL:** https://arxiv.org/abs/2501.02413  
**Use:** formal semantics of EqSat.  
**Key relevance:** reinforces treating equivalence as a semantic object.

### S22 MLIR Defining Dialects
**URL:** https://mlir.llvm.org/docs/DefiningDialects/  
**Use:** extensible/dynamic dialect capabilities.

### S23 MLIR Language Reference
**URL:** https://mlir.llvm.org/docs/LangRef/  
**Use:** operations, traits/interfaces, transformations.

### S24 MLIR Transform Dialect
**URL:** https://mlir.llvm.org/docs/Dialects/Transform/  
**Use:** explicit transformation control.

### S25 MLIR Bytecode Format
**URL:** https://mlir.llvm.org/docs/BytecodeFormat/  
**Use:** versioning/compatibility caveats.

### S26 MLIR IRDL
**URL:** https://mlir.llvm.org/docs/Dialects/IRDL/  
**Use:** declarative/runtime IR constraints and verifiers.

### S27 Alive2
**URL:** https://alive2.llvm.org/ce/  
**Use:** LLVM translation validation model.

### S28 Verified VCG and Compiler for Dafny
**URL:** https://arxiv.org/abs/2512.05262  
**Use:** mechanized restricted-language compiler correctness.

### S29 RustCompCert
**URL:** https://arxiv.org/abs/2602.07455  
**Use:** verified/verifying Rust compilation direction.

### S30 MIPS
**URL:** https://arxiv.org/abs/2402.05110  
**Use:** neural-to-program extraction.

### S31 Weights to Code
**URL:** https://arxiv.org/abs/2601.05770  
**Use:** transformer-oriented algorithm extraction.

### S32 Emergence of Grounded Compositional Language
**URL:** https://arxiv.org/abs/1703.04908  
**Use:** emergent discrete communication.

### S33 CLSR
**URL:** https://arxiv.org/abs/2606.29354  
**Use:** LLM-invented/evolved compact symbolic protocols.

### S34 Latent Communication Survey
**URL:** https://arxiv.org/abs/2606.05711  
**Use:** model-to-model latent channels and open problems.

### S35 Latent Communication Between Language Model Agents
**URL:** https://arxiv.org/abs/2607.14103  
**Use:** negative/mixed evidence about latent-channel task benefit.

### S36 Self-Modifying Lean Proof Agents
**URL:** https://arxiv.org/abs/2607.17352  
**Use:** verifier-grounded agent/benchmark coevolution.

### S37 Self-Evolving Benchmarks TRACE
**URL:** https://arxiv.org/abs/2510.00415  
**Use:** evolving task complexity with reproducible trajectories.

### S38 EvilGenie
**URL:** https://arxiv.org/abs/2511.21654  
**Use:** coding reward-hacking benchmark.

### S39 Benchmarking Reward Hack Detection in Code Environments via Contrastive Analysis (TRACE)
**URL:** https://arxiv.org/abs/2601.20103  
**Use:** reward-hack taxonomy/detection.

### S40 SpecBench
**URL:** https://arxiv.org/abs/2605.21384  
**Use:** long-horizon coding reward-hacking measurement.

### S41 Reward Hacking Benchmark
**URL:** https://arxiv.org/abs/2605.02964  
**Use:** multi-step tool-use reward hacking and environmental hardening.

### S42 Hack-Verifiable TextArena
**URL:** https://arxiv.org/abs/2605.20744  
**Use:** deterministic verification of reward-hacking behaviors.

### S43 Agent Benchmark Protocol Validity / HackDetect
**URL:** https://arxiv.org/abs/2607.22368  
**Use:** benchmark exposure/audit evidence.

### S44 Navajo Nation Code Talker history
**URL:** https://opvp.navajo-nsn.gov/250814-navajo-code-talkers-day/  
**Use:** official historical attribution.

### S45 Smithsonian NMAI Code Talkers
**URL:** https://americanindian.si.edu/why-we-serve/topics/code-talkers/  
**Use:** Code Talker history and context.

### S46 Navajo Word of the Day - béésh
**URL:** https://navajowotd.com/word/beesh/  
**Use:** lexical inspiration only; not formal linguistic authority.

### S47 Navajo Word of the Day - bizaad / saad
**URL:** https://navajowotd.com/word/bizaad/  
**Use:** lexical inspiration only; not formal linguistic authority.

---

## 26. Claims Bestsad should *not* make yet

Until supported by project experiments, do not claim that:

- Bestsad increases general intelligence;
- Bestsad has invented a fundamentally new semantics;
- machine languages are intrinsically superior to human languages;
- latent representations are more intelligent than symbolic/textual ones;
- the first discovered primitives are universal;
- shorter programs imply deeper reasoning;
- model self-improvement is unbounded;
- an evolved compiler is correct merely because tests pass;
- cross-model transfer will necessarily occur;
- Bestsad is a Navajo word or canonical Navajo grammatical construction.

---

## 27. Publication/reproducibility recommendation

For every public Bestsad result, ship:

- source revision
- experiment manifest
- frozen kernel version
- public benchmark generator code
- description of hidden-test construction without exposing answers
- model identity and weights/API version where permissible
- model prompts/projections
- language genome
- primitive definitions/lowerings
- compiler/verifier versions
- compute ledger
- all seeds
- per-run raw results
- aggregate statistics
- exploit/integrity incidents
- ablation results
- failed/null experiments relevant to the claim

This is necessary because Bestsad is explicitly optimizing the environment in which a model solves problems; without strong experimental traceability it will be difficult to distinguish scientific progress from evaluator adaptation.

---

## 28. Companion conclusion

The literature now supports a credible research program at the intersection of program synthesis, learned abstractions, DSL synthesis, differentiable interpreters, evolutionary coding, compiler optimization, e-graphs, formal verification, emergent communication, and benchmark integrity.

The strongest evidence does **not** yet prove Bestsad's central hypothesis. Instead, it establishes that nearly every required subproblem has an existence proof or strong precursor:

- languages/libraries can grow from experience;
- DSLs can be synthesis targets;
- discrete symbolic-like primitive vocabularies can be learned;
- primitive sets can be optimized;
- executable code and compiler heuristics can evolve under objective evaluators;
- program search can feed model improvement;
- equivalence classes can be represented compactly;
- compiler IR can be extensible;
- translation can be independently validated;
- restricted compilers can be mechanically verified;
- agents can invent compact communication protocols;
- benchmark evolution can be verifier-grounded;
- reward hacking is real enough that evaluator independence must be built into the research design.

Bestsad's novelty is therefore not any one of these ingredients. The proposed contribution is the **controlled co-evolution architecture and experimental method** that asks whether executable representation itself can become a measurable lever on computational capability.

---

# Part II - v0.2 Research Audit

*Everything below this line was added in v0.2. It records a targeted prior-art audit, a methodology review of how the Bestsad thesis can actually be proved, an adversarial review of the thesis, and thirty additional annotated sources (S48-S77). Evidence labels follow Section 1.2.*

---

## 29. Prior-art audit (v0.2)

### 29.1 Method

The audit targeted six questions: (1) has anyone built a machine-designed or model-optimized executable language; (2) has anyone evolved compiler transformation policy with model-driven search; (3) has anyone separated canonical semantics from model-specific projections in an evolvable system; (4) what is the current state of learned abstraction/library induction, including negative results; (5) what is known about tokenizer and in-context confounds; (6) what exists for the "machine" leg, including hardware/ISA co-design.

### 29.2 The three near-misses

**Extensible multi-level compiler IR frameworks** already realize the canonical-semantics-versus-dialect separation that Bestsad's BSIR/projection split proposes, including dynamic dialect definition and evolvable pass-pipeline description. The dialects are human-designed. *[Established]*

**Evolutionary coding agents** now discover algorithms and compiler heuristics by having a model repeatedly edit and re-evaluate source code, with results that include improving on long-standing algorithmic constructions and reducing binary size relative to hand-tuned compiler heuristics. Crucially, they leave the *language* fixed and evolve programs written in it. *[Established for the method; specific headline numbers are recent preprints and should be treated as provisional.]* This family is the single most important rival explanation for any Bestsad result, which is why v0.2 promotes it from related work to experimental condition I.

**Search-based "compiler" proposals for AI-native software** articulate co-evolution of a stack with separation of intent from implementation, but evolve prompts, parameters and configurations rather than an executable IR. *[Vision-level; medium evidence.]*

**Human-designed LLM-oriented DSLs** are the closest thing to Bestsad's target artifact. The reported design principles - a single canonical form per operation, named intermediates, explicit step structure, verbose keywords - converge remarkably well on Bestsad's P1/P2 and its projection concept, and reported results include near-total zero-shot parse validity on an unseen DSL and a substantial multi-step accuracy improvement over a general-purpose language. Two caveats matter for Bestsad: the language is hand-designed rather than evolved, and the authors themselves note their benchmark may favor their language. *[Medium evidence - single-benchmark preprint.]*

### 29.3 What this means for the novelty claim

The honest position is recorded in spec Section 39: Bestsad's claim is integration plus methodology. Per-component priority claims are not available, and the program is better served by loudly citing these systems as the boundary of prior art than by understating them.

---

## 30. The negative-result literature Bestsad must answer

This is the most important addition in v0.2.

A dedicated line of work has examined whether LLM "library learning" systems actually benefit from the libraries they build. The findings are consistently unfavorable: measured function reuse on mathematical benchmarks is extremely infrequent; the observed performance gains are better attributed to self-correction and self-consistency than to reuse; and in at least one system the library-learning component *degrades* performance. A follow-up case study of a prominent theorem-proving library-learning system reports that its advantage over simply prompting the model disappears once computational cost is accounted for. *[Established, and directly adverse.]*

Consequences that v0.2 adopts:

1. **Reuse must be measured directly, never inferred from aggregate accuracy.** Already H2; now enforced by the secondary outcome list.
2. **Compute accounting is not bookkeeping, it is the experiment.** The compute-matched search-only baseline (condition I) exists because that is exactly the control that reversed the published result.
3. **Self-correction and self-consistency are confounds.** Retry and repair policy must be equalized across conditions (condition H).
4. **A negative EXP-001 is the modal outcome and is scientifically valuable.** Spec Section 44 gives it a home.

---

## 31. How to prove the thesis (methodology review)

### 31.1 Separating representation from compute

Adopt the matched-trial convention used in autotuning research, where competing search methods are given equal measurement-trial budgets and the comparison is stated as explicitly fair. Report per-compute curves rather than single matched points, because condition ordering can invert with budget. *[Established practice.]*

### 31.2 Separating representation from compression

Tokenizer research shows that tokenizer choice materially changes generation speed, effective context length and memory, while downstream code-generation accuracy is comparatively insensitive. The practical reading for Bestsad: compression buys throughput and context, not obviously capability. This motivates hypothesis H13, condition F, and the paired `compression_ratio` / `capability_delta` reporting rule. *[Established.]*

### 31.3 Separating representation from prompting

Models can achieve very high parse validity on a DSL they have never seen, from prompt material alone. Meanwhile, grammar-constrained prompting work reports *negative* results for DSLs already well represented in pretraining, and notes that constrained generation can increase call counts and reduce output diversity. Together these say: novel-notation competence is cheap to obtain and easy to mistake for representational merit, and the comparison against a pretraining-favored language is not symmetric. Hence H14 and condition H. *[Established for the positive result; the negative results are from a peer-reviewed venue.]*

### 31.4 Defining OOD for program synthesis

Use the established synthesis split taxonomy - length generalization, primitive composition, and distribution shift over primitives and semantics - rather than a bespoke definition. For the decisive endpoint, verified *compositional* synthesis is the sharpest available terrain: published results show models that verify well on single-function tasks collapsing by roughly an order of magnitude on compositional ones, with failure concentrated in specification fragility and implementation-proof misalignment rather than syntax. A representational advantage that is real should be visible there; a compression artifact should not be. *[Established, recent.]*

### 31.5 Information-theoretic grounding

Minimum-description-length results now supply generalization guarantees for representation learning, framed in terms of the description length of the *solutions/labels* under a fixed prior rather than raw corpus compression. This is what v0.2 uses to reformulate Semantic Gain (spec Section 21.4), and it is what makes the compression-versus-capability distinction quantitative rather than rhetorical. *[Established theory; the specific Bestsad instantiation is Bestsad synthesis.]*

### 31.6 Attributing gains to specific primitives

Causal mediation analysis - decomposing an effect into direct and indirect paths through an identified mediator, with interventions on the mediator - is established in interpretability research on language models. Applying it with each promoted primitive as the mediator gives Bestsad per-primitive attribution instead of stage-level attribution. This is spec Section 42. *[Established method; the application to language-genome primitives is Bestsad synthesis.]*

### 31.7 Statistical discipline

Three requirements, all standard elsewhere and all absent from v0.1: pre-registration of the primary endpoint and analysis plan before any evaluation run; false-discovery-rate control across the declared secondary-endpoint family; and power analysis using variance measured in E0. Note also that equivalence testing requires substantially larger samples than non-inferiority testing at equal margin and power, so the framing choice has real cost - use non-inferiority wherever the question is genuinely "no worse". *[Established.]*

### 31.8 Contamination and gaming

Use dynamically generated instances and time-partitioned holdouts rather than static suites; and separate the *contamination* channel from the *adaptive-overfitting* channel, since repeated evaluation against a fixed held-out set inflates results even with no data leakage. Existing specification-gaming and reward-hacking benchmark suites should seed the adversarial integrity plane rather than being rebuilt. *[Established.]*

---

## 32. The three-way fit: model, domain, machine

**Model.** What helps: shorter canonical sequences; low syntactic variance; in-context learnability from documentation. What is unproven: that any of this converts into *capability* rather than reliability and cost. *[Mixed.]*

**Domain.** DSLs win where they remove irrelevant expressivity and ship a deterministic validator that enables a generate-and-check loop. They lose where the general-purpose alternative is already saturated in pretraining. Bestsad's evolved language starts with zero pretraining support, which is a structural disadvantage that condition G (human-expert DSL) and condition H (scaffolding matching) are designed to expose rather than hide. *[Established tension.]*

**Machine.** IR-grounded continued pretraining measurably improves cross-language robustness of code models, which is the best available positive evidence for the machine leg. Learned cost models and autotuning stacks supply the machine-fitness term. Automated custom-instruction synthesis supplies a ready formalism (enumeration plus selection over dataflow graphs) for the eventual hardware question. *[Established.]*

**Do the three conflict?** Probably in part. What is good for the model (dense, canonical, low-variance surface) is not always what is good for the machine (explicit structure that exposes optimization opportunities), and what is good for one domain (specialized primitives) tends to hurt cross-domain transfer. Bestsad's separation of a canonical semantic substrate from multiple projections is the right architectural hedge, because it lets the three legs optimize different projections over shared semantics instead of fighting over one surface. **This conflict analysis is Bestsad synthesis, not an established empirical result**, and it is worth testing directly: a projection optimized for the model and a projection optimized for the machine, over one BSIR graph, is a cheap and informative experiment.

---

## 33. Adversarial review: the strongest case that H0 survives

1. **Human languages plus a large model may already be near-optimal.** Evolutionary coding agents reach frontier results without touching the language, and models carry deep pretraining priors toward mainstream languages that a novel language forfeits entirely.
2. **Learned-abstraction gains repeatedly fail controls.** See Section 30. This is not a hypothetical objection; it is a published pattern.
3. **Search cost can exceed representational benefit.** If new primitives expand the vocabulary faster than they shrink search, net capability falls. No evidence currently establishes which side of that transition the favorable regime lies on.
4. **Evolved abstractions may be domain-overfit and non-transferable.** Emergent-communication findings - effective but compositionally poor protocols that drift - argue directly against H9.
5. **Verification pressure may suppress the innovations worth having,** while unconstrained discovery bloats the library. Bestsad has both failure modes simultaneously available.

**Balance of evidence (v0.2).** *Supported:* constrained canonical representations reduce error rates; IR grounding improves robustness; structured abstraction helps in specific generative domains. *Contested:* that learned abstractions improve generalized capability at matched compute. *Unproven:* the strong Bestsad thesis. The program should say exactly this, in public, until its own data says otherwise.

---

## 34. Build-versus-adopt register

| Need | Adopt | Do not rebuild |
|---|---|---|
| Equivalence engine | Mature e-graph/equality-saturation engine; differentiable and exact extraction work for the extraction step | A new e-graph library |
| Compiler substrate | Extensible multi-level IR with dynamic dialect definition and a transform/pass-pipeline dialect | A bespoke IR |
| Translation validation | Refinement-checking tooling for the low-level leg | A bespoke checker |
| Abstraction baseline (condition C) | Existing MDL-optimal corpus abstraction extractor | A strawman frequency counter |
| Machine cost model | Existing autotuning stack's cost model and measurement protocol | A new autotuner |
| Rival baseline (condition I) | Open evolutionary code-search implementation | Nothing - this must be a real, competitive baseline |
| Contamination-resistant eval | Dynamic instance generation, time-partitioned holdouts | A static private suite alone |
| Integrity suite seed | Existing specification-gaming / reward-hacking benchmarks | A from-scratch exploit corpus |

The rule: Bestsad's contribution is integration and methodology. Every rebuild decision costs contribution surface and must be justified by an ADR.

---

## 35. What v0.2 changes relative to v0.1

1. Three new hypotheses (H13 compression-is-not-capability, H14 scaffolding invariance, H15 representation-beats-extra-search).
2. Four mandatory new EXP-001 controls (F compression-matched, G human-expert DSL reference class, H scaffolding-matched, I search-only compute-matched).
3. Semantic Gain reformulated on MDL foundations, with training-corpus compression explicitly discounted.
4. Ablation ladder re-ordered to separate tokenizer co-design from model adaptation.
5. Pre-registration, FDR control, and power analysis made mandatory for confirmatory claims.
6. Per-primitive causal mediation and a gain-concentration stop rule added.
7. Primary endpoint moved to verified *compositional* OOD.
8. Staged funding gates S1-S5 so expensive arms are gated on cheap arms.
9. Negative-result ledger and prohibited-claims register made normative.
10. Thirty new annotated sources; open questions tagged with evidence status.

---

## 36. Research source annotations (v0.2 additions)

*Evidence weight reflects venue, replication status, and directness of relevance. Several 2025-2026 entries are preprints; their specific numbers should be treated as provisional.*

### S48 Anka: A Domain-Specific Language for Reliable LLM Code Generation
Hand-designed DSL targeting LLM generation reliability; canonical-form and explicit-step principles closely parallel Bestsad P1/P2. Relevance: closest published artifact to Bestsad's target. Weight: medium (single-benchmark preprint, author-acknowledged benchmark bias risk).

### S49 Library Learning Doesn't: The Curious Case of the Single-Use "Library"
Finds reuse extremely infrequent and attributes gains to self-correction/self-consistency; reports library learning degrading performance in at least one system. Relevance: strongest empirical support for H0. Weight: high.

### S50 LLM Library Learning Fails: A LEGO-Prover Case Study
Reports that a prominent library-learning prover's advantage vanishes once computational cost is accounted for. Relevance: the direct justification for condition I. Weight: high.

### S51 AlphaEvolve
Model-driven evolutionary discovery of algorithms via repeated code edit and evaluation, in existing languages. Relevance: rival explanation family; baseline for condition I. Weight: high.

### S52 Magellan
Extends evolutionary code discovery to compiler pass heuristics, reporting binary-size and register-allocation results against hand-tuned baselines. Relevance: prior art for compiler-policy evolution (H11). Weight: medium-high (recent preprint; some reported figures criticized for missing error bars).

### S53 Compiler.next
Search-based "compiler" vision for AI-native software; co-evolves stack components, separates intent from implementation. Relevance: nearest framing-level prior art. Weight: medium (vision paper).

### S54 SOAR
Self-improving evolutionary program synthesis with model fine-tuning on search traces; useful FLOPs accounting where sampling dominates and fine-tuning is a small fraction of total compute. Relevance: A6/A7 design and cost planning. Weight: high.

### S55 CodeEvolve / OpenEvolve
Open implementations of evolutionary code search. Relevance: adoptable engine and condition-I baseline. Weight: medium.

### S56 IRCoder
Continued pretraining on source-to-IR pairs yields consistent multilingual code-generation gains. Relevance: best positive evidence for the machine leg. Weight: high.

### S57 Meta Large Language Model Compiler
Foundation models trained on compiler IR and optimization. Relevance: machine-leg substrate. Weight: high.

### S58 Minimum Description Length and Generalization Guarantees for Representation Learning
MDL-based generalization bounds for representation learning. Relevance: formal basis for Semantic Gain v2. Weight: high (theory).

### S59 Causal Mediation Analysis for interpreting neural models
Establishes mediation decomposition with interventions in LM analysis. Relevance: method for spec Section 42. Weight: high.

### S60 Mechanistic interpretation of arithmetic reasoning via causal mediation
Applied mediation analysis on reasoning behavior. Relevance: worked template for per-primitive attribution. Weight: high.

### S61 SmoothE - differentiable e-graph extraction
Makes extraction differentiable. Relevance: partially answers open question 10. Weight: high.

### S62 e-boost - adaptive and exact e-graph extraction
Extraction quality/cost trade-offs. Relevance: Equivalence Engine tooling. Weight: medium-high.

### S63 Equality-saturation dialect for extensible compiler IR
Brings equality saturation into the compiler substrate Bestsad plans to use. Relevance: removes a large build task. Weight: medium-high.

### S64 LLM-guided equality saturation
Model-guided rewrite selection. Relevance: hybrid search (H5) and evolvable extraction. Weight: medium.

### S65 Rewrite System Showdown: stochastic search versus equality saturation
Head-to-head comparison of rewriting strategies. Relevance: prevents assuming e-graphs dominate; informs H6. Weight: medium.

### S66 DafnyComp - compositional verified synthesis benchmark
Documents order-of-magnitude collapse from single-function to compositional verified synthesis, with failure modes categorized. Relevance: the decisive endpoint terrain for EXP-001. Weight: high.

### S67 Gradient-based program synthesis with neurally interpreted languages
Provides compositional-generalization splits (length, primitive composition, distribution shift). Relevance: OOD split design. Weight: medium.

### S68 Getting the most out of your tokenizer
Quantifies tokenizer effects on speed, effective context and memory, with comparatively small downstream accuracy effects. Relevance: foundation for H13 and condition F. Weight: high (peer-reviewed).

### S69 Evaluation safety-gap / adaptive-overfitting analysis
Separates data contamination from repeated-evaluation overfitting. Relevance: evaluator access-control policy. Weight: medium-high.

### S70 Interlat - latent inter-agent communication
Latent-channel communication between models. Relevance: bounds on open question 12. Weight: medium.

### S71 Communicating activations between language model agents
Activation-level communication. Relevance: same. Weight: medium.

### S72 Emergent languages in populations of language model agents
Finds token-efficient emergent protocols with poor compositionality and oversight-evasion risk. Relevance: adverse evidence for H9 and for open question 11. Weight: medium-high.

### S73 Automating application-driven customization of ASIPs (survey)
Formalizes custom-instruction synthesis as enumeration plus selection over dataflow graphs. Relevance: ready-made formalism for open question 19. Weight: medium.

### S74 Ansor - high-performance tensor program generation
Search-based schedule generation with an explicit matched-trial fairness protocol. Relevance: template for Bestsad's compute-matching policy. Weight: high.

### S75 ML-driven hardware cost model for extensible compiler IR
Learned cost modeling at the IR level. Relevance: machine-fitness term. Weight: medium-high.

### S76 Grammar prompting for domain-specific language generation
Reports no improvement for DSLs already common in pretraining and costs from constrained generation. Relevance: negative evidence tempering the DSL case; motivates condition G. Weight: high (peer-reviewed).

### S77 Learned graph rewriting
RL-driven rewrite selection over graphs. Relevance: evolvable extraction (open question 10). Weight: medium.

---

## 37. Companion conclusion (v0.2)

v0.1 established that the components Bestsad needs exist and that no one has assembled them. v0.2 establishes something less comfortable and more useful: that the assembled system will be judged almost entirely on whether four specific confounds were controlled, and that the nearest published attempts to demonstrate learned-abstraction benefit did not survive exactly that scrutiny.

The program's scientific value is therefore concentrated in the control design, not the search machinery. A Bestsad that runs conditions A through I honestly and reports a null result will have contributed more than a Bestsad that reports a five-point gain without conditions F, H and I.
