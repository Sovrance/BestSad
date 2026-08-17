# Bestsad Research Architecture & Experimental Specification v0.2

**Document ID:** BESTSAD-RAES-001  
**Project:** Bestsad  
**Version:** 0.1  
**Date:** 2026-08-17  
**Status:** Launch research baseline  
**Evidence cutoff:** 2026-08-17  
**Companion:** `BESTSAD_RESEARCH_COMPANION_v0.1.md`

---

## 0. Executive definition

Bestsad is a research program for discovering whether machine intelligence can improve when it is allowed to evolve its own executable computational representations rather than being constrained to programming languages designed primarily for humans.

The project does **not** begin by attempting to invent a replacement for Python, Rust, or C++. It begins with a narrower and falsifiable scientific question:

> Can a fixed-capacity model, under controlled compute and evaluation conditions, achieve better verified out-of-distribution program synthesis and execution performance when it uses an evolved machine-native language/representation than when it uses a conventional or fixed baseline language?

The system jointly studies six coupled objects:

1. **Model interface** - how a model perceives and emits executable structure.
2. **Representation** - graph, symbolic, textual, or latent-like encodings used during search and reasoning.
3. **Language genome** - the evolving set of abstractions, primitives, syntax/projection rules, and transformation policies.
4. **Compiler** - lowering, rewriting, cost modeling, and backend selection.
5. **Verifier** - semantic, type, equivalence, execution, and translation checks.
6. **Evaluator** - independent, access-controlled benchmarks and fitness computation.

The central launch rule is:

> **Everything may evolve except the trusted semantic kernel, evaluator trust boundary, and the rules that determine whether a result counts as correct.**

This protects the research from semantic drift, benchmark gaming, and false gains.

---

## 1. Name and attribution

**Bestsad** is a coined project name inspired by Diné/Navajo lexical roots supplied for the project: **béésh**, associated with knife/metal and used in terms for metal or technological objects, and **saad**, approximating word/speech and participating in language terms such as *bizaad*.

The project name is inspired by the extraordinary history of the Navajo Code Talkers, who developed a specialized military code using Diné Bizaad during World War II. It should not be represented as a claim that **Bestsad** is itself a grammatically canonical Diné compound or established Navajo word. Any public branding that makes a stronger linguistic claim should be reviewed by a qualified Diné speaker/linguist or cultural advisor.

This distinction is deliberate: the project draws inspiration from a history of constructing an effective specialized coding system from a rich language, while avoiding an unsupported claim about Navajo grammar.

---

## 2. Research thesis

### 2.1 Core thesis

Most code-capable models inherit human-designed source languages and tokenizers. Those languages optimize for human readability, human editing, ecosystem compatibility, and historical compiler constraints. They are not known to be optimal representations for artificial models.

Bestsad treats the representation of computation as an optimization target.

Let:

- `M_t` = model at generation `t`
- `L_t` = language genome at generation `t`
- `R_t` = representation policy at generation `t`
- `C_t` = compiler/transformation system at generation `t`
- `V` = trusted verifier stack
- `E` = independent evaluator

The long-run research object is:

`(M_{t+1}, L_{t+1}, R_{t+1}, C_{t+1}) = Optimize(M_t, L_t, R_t, C_t | V, E)`

However, v0.1 deliberately **does not** evolve all four at once. It stages them so causality can be measured.

### 2.2 Null hypothesis

**H0:** After controlling for model, training budget, inference/search compute, compiler backend, and benchmark exposure, an evolved Bestsad representation provides no statistically reliable improvement in verified out-of-distribution capability over fixed-language baselines.

Bestsad is successful as a research program even if H0 survives. A negative result would establish useful limits on representation-driven capability gains.

---

## 3. Research hypotheses

### H1 - Representation efficiency
An AI-oriented representation can reduce model-side sequence/search cost without reducing semantic correctness.

### H2 - Abstraction discovery
Automatically discovered reusable abstractions can reduce synthesis depth and improve generalization when reuse is measured directly rather than inferred from aggregate task accuracy.

### H3 - Semantic-first evolution
Evolving semantic abstractions before surface syntax will produce more transferable improvements than optimizing syntax alone.

### H4 - Primitive discovery
A system can identify computational primitives whose addition improves a workload more than simply enlarging a conventional library at random.

### H5 - Hybrid search
Combining evolutionary, symbolic, and gradient-based search will outperform any single search family on mixed discrete/continuous language-design spaces.

### H6 - Equivalence-rich search
Representing many equivalent programs simultaneously can improve optimization and primitive discovery, provided e-graph growth is controlled.

### H7 - Verification pressure
Including verifiability in fitness will favor abstractions that are not only short or fast but easier to establish as semantically correct.

### H8 - Model-specific dialects
Different model architectures may prefer different surface representations while sharing the same semantic substrate.

### H9 - Cross-model transfer
A useful machine-native abstraction should provide measurable value when learned or consumed by a model that did not invent it.

### H10 - Curriculum coevolution
An evolving training curriculum can delay benchmark saturation, but only a frozen held-out evaluation can determine whether progress transfers.

### H11 - Compiler coevolution
Once the language is stable enough to measure, evolving transformation policies can create additional performance gains independent of language-level gains.

### H12 - Tokenizer interaction
Language benefits may depend materially on tokenization; tokenizer co-design may produce additional gains, but it must be introduced only after representation effects are isolated.

### H13 - Compression is not capability *(added v0.2)*
A representation that only shortens token sequences will improve throughput, effective context, and cost, but will **not** improve verified OOD solve rate at matched information. Any capability gain must survive a compression-matched control.

Motivation: tokenizer studies report large changes to generation speed, effective context length, and memory when the tokenizer changes, while downstream code-generation accuracy is far less sensitive. Bestsad therefore treats compression and capability as separate outcomes that must be measured separately, never as one axis.

### H14 - Scaffolding invariance *(added v0.2)*
Any measured advantage of an evolved language must persist when the in-context scaffolding (grammar description length, number and quality of worked examples, retry policy, decoding constraints) is equalized across conditions.

Motivation: current models can reach very high parse-validity on a never-before-seen DSL from prompt material alone. A naive comparison therefore risks measuring prompt engineering rather than representational merit.

### H15 - Representation beats extra search *(added v0.2)*
An evolved representation must beat a baseline that is given the *same total compute* spent on plain search in the baseline language. If additional search in a conventional language matches the evolved language, the representational claim fails.

Motivation: evolutionary code-search systems obtain strong results while leaving the language fixed. That family is Bestsad's most serious rival explanation and must appear as an explicit experimental condition, not as related work.

---

## 4. Non-goals for v0.1

Bestsad v0.1 is **not**:

- a general-purpose production programming language;
- a self-modifying compiler with unrestricted semantics;
- a new hardware ISA;
- a claim that opaque latent representations are automatically superior to symbolic ones;
- a benchmark-maximization contest;
- an attempt to remove human-readable projections;
- an attempt to let a model redefine what program correctness means;
- a proof that shorter code means greater intelligence.

Hardware co-design, self-hosting, mutable base semantics, unrestricted effects, and neural-only primitive semantics are later research phases and require separate gates.

---

## 5. Design principles

### P1. Meaning before spelling
A primitive is defined by semantics and proof obligations before it receives a compact textual or symbolic surface form.

### P2. Stable semantic anchor
Every v0.1 evolved construct must lower to a fixed trusted semantic kernel.

### P3. Independent evaluation
The candidate generator cannot modify hidden tests, scoring logic, evaluator dependencies, or evaluator state.

### P4. Multi-objective optimization
No scalar such as token count, runtime, or benchmark accuracy may dominate the project by itself.

### P5. Reproducible genealogy
Every language mutation has parents, a mutation record, benchmark generation, environment hash, and fitness vector.

### P6. Explicit maturity
Learned or inferred primitives carry maturity levels; experimental behavior is never silently promoted to trusted semantics.

### P7. Negative-result preservation
Failed mutations and failed hypotheses are first-class research artifacts because they train search policies and prevent rediscovery of dead ends.

### P8. Human projection is not canonical semantics
Human-readable syntax is a view over the semantic object, not necessarily the canonical machine representation.

### P9. No hidden semantic widening
A compact primitive may not acquire extra behavior that is absent from its declared lowering.

### P10. Controlled coevolution
Only one major causal dimension is unfrozen at a time during core experiments.

---

## 6. Trust and mutability model

### 6.1 Trusted / frozen in v0.1

- Semantic Kernel K0 specification
- K0 reference interpreter
- Benchmark answer semantics
- Hidden benchmark generator seeds
- Evaluator scoring code
- Sandbox policy
- Artifact hashing/signing procedure
- Reproducibility metadata schema

### 6.2 Mutable under controlled experiments

- learned abstractions/macros
- language genome
- surface syntax/projection
- semantic-graph layout
- model prompt/interface adapter
- rewrite strategy
- e-graph extraction policy
- search policy
- curriculum tasks (not frozen evaluation)
- cost models
- later: model weights, tokenizer, compiler heuristics

### 6.3 Forbidden in v0.1

- direct edits to evaluator or hidden tests
- network access by candidate programs
- candidate writes outside scratch sandbox
- dynamic native library loading
- arbitrary machine code
- mutation of K0 semantics
- mutation of result-validity rules
- benchmark-specific hidden-condition primitives

---

## 7. High-level architecture

```text
                          BESTSAD
                             |
             +---------------+----------------+
             |                                |
       Trusted Plane                     Evolution Plane
             |                                |
     Semantic Kernel K0                 Language Genome
     Reference Interpreter                  |
     Evaluator Contract          +-----------+-----------+
             |                   |           |           |
             |              primitives   projection   strategy
             |                   |           |           |
             +---------+---------+-----------+-----------+
                       |
                 Bestsad Semantic IR
                       |
          +------------+-------------+
          |            |             |
       types/effects  graph       equivalences
          |            |             |
          +------------+-------------+
                       |
              Equivalence Engine
              e-graphs / proofs
                       |
                Verification Plane
        +--------------+---------------+
        |              |               |
     static         execution       translation
    checks          oracles         validation
        |              |               |
        +--------------+---------------+
                       |
                   MLIR layer
                       |
                     LLVM
                       |
                 CPU/GPU backend

Independent Evaluation Plane (isolated from candidate mutation)
  - frozen hidden benchmark
  - evolving curriculum benchmark
  - adversarial anti-gaming benchmark
  - OOD family holdouts
  - cross-model transfer tests
```

---

## 8. Semantic Kernel K0

### 8.1 Purpose

K0 is not intended to be elegant or expressive. It is intended to be **small, deterministic, executable, and stable enough that all early Bestsad gains can be traced to representation and abstraction rather than new semantics**.

### 8.2 K0 computational model

For the first experiments, K0 should use a pure, typed, deterministic functional/dataflow subset with explicit traps and no ambient side effects.

Recommended initial types:

- `Bool`
- `Int` - mathematical integer in the reference semantics; backend lowering may use bounded integers only when equivalence is explicitly established
- `List<T>` for a small closed set of `T`
- `Tuple<A,B>`
- `Option<T>`
- `Result<Value, Trap>` as evaluator outcome

Recommended effect set:

- `Pure`
- `Trap` only

No file I/O, clock, randomness, threads, network, mutable global state, FFI, or reflection in K0.

### 8.3 Primitive families

The exact K0 primitive list is versioned. v0.1 should cover approximately 24-40 operations across:

- constants and argument access
- scalar arithmetic
- scalar comparison
- Boolean logic
- conditional selection
- tuple construction/projection
- list construction/deconstruction
- list length and safe indexing
- structured higher-order iteration (`map`, `filter`, `fold`) or equivalent region-based forms
- function application / lambda or a constrained closure representation

The project should prefer total operations when feasible. Partial operations return `Option` or explicit `Trap` rather than inheriting host-language undefined behavior.

### 8.4 Kernel versioning

Every artifact records `kernel_version`. A change to K0 semantics starts a **new experiment lineage**; it cannot be mixed with previous fitness results as though the search space were unchanged.

---

## 9. Bestsad Semantic IR (BSIR)

### 9.1 Role

BSIR is the stable scientific representation above MLIR. MLIR is the execution/compiler substrate; BSIR is the canonical Bestsad semantic object.

### 9.2 Required properties

BSIR must be:

- typed;
- explicit about control/data dependencies;
- serializable in a canonical representation;
- hashable;
- transformable;
- capable of representing discovered abstractions without changing K0;
- linked to proof/equivalence artifacts;
- capable of multiple projections.

### 9.3 Core node model

Each node carries at least:

- `node_id`
- `op_semantic_id`
- `operands`
- `result_types`
- `effect_set`
- `region_ids` if structured control is used
- `attributes`
- `source_projection` metadata
- `semantic_hash`
- `proof_obligation_ids`

### 9.4 Canonical semantic hash

The semantic hash should be derived from normalized BSIR, not surface syntax. Two surface forms that normalize to the same BSIR should receive the same content identity when their semantics are identical.

### 9.5 Mutation surface

Inspired by architecture-oriented search-state work, BSIR should expose a **mutation surface** distinct from the entire executable graph. Candidate mutation should operate on semantically meaningful editable regions while preserving interface contracts.

### 9.6 Validity envelope

Every mutation region carries:

- input/output types
- shape/arity constraints
- effect limits
- cost budget
- permitted semantic references
- downstream dependencies

A candidate violating the validity envelope is rejected before expensive evaluation.

---

## 10. Language Genome

The Language Genome is the unit of evolution.

### 10.1 Required fields

See `schemas/language_genome.schema.json`. Conceptually:

```text
LanguageGenome
  genome_id
  parent_genome_ids[]
  generation
  kernel_version
  primitive_set[]
  projection_policy
  representation_policy
  rewrite_strategy
  compiler_strategy
  tokenizer_adapter_version
  model_adapter_version
  benchmark_generation
  fitness_vector
  novelty_vector
  lineage_events[]
  proof_artifacts[]
  environment_hash
  created_at
```

### 10.2 Genome invariants

1. Every primitive references a K0 lowering or a previously verified primitive expansion.
2. No cyclic macro expansion without an explicit recursive semantic form.
3. Every changed semantic mapping produces a new semantic identifier.
4. Surface aliases may change without semantic identifier changes.
5. Fitness is immutable once recorded for a specific environment and benchmark manifest.

---

## 11. Primitive lifecycle

Bestsad primitives have explicit maturity states:

- **EXP - Experimental:** candidate abstraction; may be supported only by examples and lowering.
- **OBS - Observed:** repeated successful use across multiple tasks/seeds.
- **SPEC - Specified:** formal input/output/effect semantics and canonical lowering recorded.
- **VER - Verified:** equivalence/translation claims satisfy the configured formal or exhaustive verifier for the supported domain.
- **CORE - Trusted core:** promoted into a future semantic kernel only through an explicit governance/research decision, never automatically.

### 11.1 Promotion evidence

Promotion should consider:

- reuse count and reuse diversity
- cross-family utility
- cross-model transfer
- semantic gain
- verification cost
- failure rate
- implementation/runtime benefit
- ambiguity / alias collision
- adversarial benchmark behavior

### 11.2 No automatic CORE promotion

Automated search may propose CORE candidates, but a kernel change invalidates controlled comparisons and therefore requires a new research phase and explicit review.

---

## 12. Representation Lab

Bestsad should test multiple projections over common BSIR semantics.

### 12.1 Projection classes

1. **Human textual projection** - descriptive names, explicit typing, debuggable formatting.
2. **Compact symbolic projection** - short model-oriented tokens/symbols.
3. **S-expression projection** - structurally regular symbolic baseline.
4. **Graph serialization** - node/edge ordering optimized for model input/output.
5. **Structured binary/token IDs** - later phase, only after semantic benefits are established.
6. **Latent-like model interface** - research-only later phase; cannot replace the canonical semantic representation.

### 12.2 Critical rule

Representation experiments must preserve semantic identity. If a representation changes available semantics, it is a language experiment, not a formatting experiment, and must be labeled accordingly.

### 12.3 Model-specific views

The architecture permits Model A and Model B to use different projections of the same semantic program. Cross-model experiments therefore test both:

- shared representation transfer;
- shared semantics with model-specific representation.

---

## 13. Evolution Engine

### 13.1 Population model

Use an island/speciation strategy rather than a single global winner.

Recommended initial islands:

- compression-oriented
- generalization-oriented
- verification-oriented
- runtime-oriented
- novelty-oriented

Migration between islands occurs on a fixed schedule. The archive retains Pareto-optimal and high-novelty genomes.

### 13.2 Mutation operators

#### Abstraction mutations
- extract repeated subtree/subgraph
- anti-unify related structures into a parameterized primitive
- merge two abstractions
- split an overloaded abstraction
- specialize a broad primitive
- generalize a narrow primitive

#### Representation mutations
- rename/recode primitive tokens
- reorder graph serialization
- alter delimiter/arity encoding
- introduce structured shorthand
- change projection granularity

#### Rewrite mutations
- add/remove equivalence rule
- change rule scheduling
- partition rulesets
- alter extraction cost weights

#### Search-policy mutations
- change proposal mix
- change exploration/exploitation ratio
- adjust island migration
- cache motifs
- alter novelty pressure

### 13.3 Recombination

Crossovers may combine:

- primitive libraries
- rewrite strategies
- representation policies
- compiler strategies

Semantic conflicts are rejected unless a deterministic reconciliation rule exists.

### 13.4 Quality-diversity preservation

The archive should preserve multiple high-performing languages with different structural characteristics to avoid premature convergence and to enable research on convergent evolution.

---

## 14. Hybrid search

Bestsad should treat language design as a mixed search space.

### 14.1 Evolutionary search
Best for discrete structural changes: primitives, grammar/projection, graph topology, rewrite schedules.

### 14.2 Symbolic search
Best for exact abstraction extraction, equivalence discovery, program synthesis, and rewrite generation.

### 14.3 Gradient search
Later phases can optimize continuous constants, embeddings, neural executors, and model adapters while discrete program structure remains externally represented.

### 14.4 Search causal isolation
The first experiments should compare these search families independently before enabling a hybrid loop, so a gain can be attributed.

---

## 15. Equivalence Engine

### 15.1 Purpose

Instead of treating one implementation as canonical, Bestsad should represent semantic equivalence classes where possible.

A discovered primitive `P` may denote an equivalence class of implementations:

```text
P
  -> reference K0 expansion
  -> vectorized lowering
  -> fused lowering
  -> backend-specific lowering
```

All implementations must refine the same declared semantics.

### 15.2 E-graphs

Equality saturation is an appropriate mechanism for compactly representing many equivalent terms. However, uncontrolled saturation can explode in memory/time. Bestsad therefore requires:

- bounded e-graph resources
- strategy synthesis separate from rule semantics
- proof/rewrite motif caching
- extraction cost models
- sketch or tractability guidance when needed

### 15.3 Equality evidence

An equivalence edge records:

- rule identifier
- proof method
- preconditions
- source/target semantic hashes
- verifier version
- success/failure

---

## 16. Type and effect system

### 16.1 v0.1 objective

The type/effect system is a correctness boundary, not an evolutionary target at launch.

### 16.2 Evolution later

Later Bestsad generations may explore type constructors or effect refinements, but only as conservative extensions whose lowering to the trusted kernel is explicit.

### 16.3 Desired future research

Potential machine-discovered type/effect abstractions may encode:

- shape
- ownership/aliasing
- purity
- determinism
- resource bounds
- approximation/error tolerance
- parallel safety
- device placement
- proof obligations

These are future experiments, not assumptions that such a discovered system will outperform human designs.

---

## 17. Model-language interface

### 17.1 Adapter contract

Each model adapter exposes:

- supported projection(s)
- context budget
- tokenizer identity
- constrained-decoding capability
- log-probability access if available
- training/fine-tuning mode
- deterministic generation controls
- tool/execution interface

### 17.2 Same-model controls

The primary v0.1 comparison must use the **same model weights** for baseline and Bestsad representation conditions wherever technically possible.

### 17.3 Fine-tuning phase

Only after fixed-weight representation effects are measured should Bestsad train/fine-tune models on the evolved language. This separates:

`representation advantage` from `adaptation advantage`.

### 17.4 Cross-model transfer

A primitive/dialect invented using Model A should be taught to Model B with a fixed exposure budget and evaluated on held-out tasks. This yields a transfer coefficient instead of merely testing creator-model performance.

---

## 18. Compiler architecture

### 18.1 Initial path

```text
Bestsad projection
      |
     BSIR
      |
 verified lowering
      |
  MLIR dialect(s)
      |
  MLIR transforms
      |
     LLVM IR
      |
 native execution
```

### 18.2 Why MLIR

MLIR provides extensible and dynamic dialect infrastructure, runtime-definable operations/types/attributes, verification hooks, transformation infrastructure, and lowering paths toward LLVM. This makes it suitable as an experimental execution substrate without making MLIR the canonical definition of Bestsad semantics.

### 18.3 Dynamic dialect use

Early Bestsad primitives should normally lower to a stable Bestsad MLIR dialect rather than dynamically create arbitrary backend semantics. Dynamic/extensible dialect features can later support experiments in automatically registering new operations while preserving verifiers and lowerings.

### 18.4 Transformation evolution

Compiler strategy evolution is a separate axis. Magellan-like experiments motivate evolving optimization heuristics, but Bestsad must not conflate language gains with compiler gains.

---

## 19. Verification Plane

Verification is layered because no single method is sufficient.

### V0 - Parse/structural validity
- schema validation
- arity
- identifiers
- graph well-formedness

### V1 - Static semantics
- types
- effects
- region constraints
- primitive maturity requirements

### V2 - Reference execution
- BSIR executes in trusted K0 interpreter
- deterministic result/trap comparison

### V3 - Differential/property testing
- random generated inputs
- metamorphic properties
- source/lowering differential execution

### V4 - Symbolic/bounded equivalence
- SMT or exhaustive bounded checks when supported

### V5 - IR translation validation
- compare pre/post lowering semantics where tooling permits
- Alive2-like validation for appropriate LLVM transformations

### V6 - Mechanized proof
- selected high-value semantics in Lean/HOL/Coq/CakeML/CompCert-family tooling as the project matures

### 19.1 Verification score

Fitness should record both:

- **verification coverage** - fraction of relevant transformations/inputs covered by strong evidence;
- **verification cost** - compute/time/complexity of establishing that evidence.

---

## 20. Independent Evaluation Plane

### 20.1 Three benchmark classes

#### A. Frozen hidden benchmark
Never modified by candidate agents. Used for research claims and generation-to-generation comparability.

#### B. Evolving curriculum benchmark
May become harder as the system improves. Used to maintain training pressure, not as the sole claim metric.

#### C. Adversarial integrity benchmark
Contains traps for benchmark-specific hardcoding, evaluator tampering, test leakage, semantic shortcuts, environment exploitation, and non-general solutions.

### 20.2 Access controls

Candidate processes must not be able to:

- read hidden test data;
- infer hidden answers from filesystem metadata;
- edit scoring code;
- edit dependencies used by the evaluator;
- persist state into another candidate's run;
- obtain network assistance unless explicitly part of a later experiment.

### 20.3 Family holdouts

Procedural generation should support **task-family holdout**, not only unseen instances. For example, if training includes map/filter compositions, evaluation may include unseen recursive or nested compositions built from the same semantics but a held-out structural family.

### 20.4 Contamination control

Synthetic task generators should be versioned and seeded after model training cutoff where possible. Public benchmark use is supplementary, not sufficient for the primary claim.

---

## 21. Fitness and metrics

### 21.1 Fitness is a vector

Do not collapse fitness too early. Record at least:

- `verified_solve_rate`
- `ood_verified_solve_rate`
- `runtime_cost`
- `model_input_tokens`
- `model_output_tokens`
- `search_compute`
- `execution_compute`
- `compile_time`
- `language_description_length`
- `primitive_count`
- `primitive_reuse_rate`
- `cross_family_reuse`
- `cross_model_transfer`
- `verification_coverage`
- `verification_cost`
- `reward_hack_incidents`
- `novelty_score`

### 21.2 Primary research metric

The preferred primary metric is a capability-efficiency quantity such as:

`Verified OOD Problems Solved / Total Experimental Compute`

with total compute including model inference, search, compilation, and execution under a clearly documented accounting policy.

### 21.3 Non-inferiority metric

Representation-compression experiments may claim success when they reduce model-side cost while maintaining a pre-registered non-inferiority margin on verified solve rate.

### 21.4 Semantic Gain *(reformulated in v0.2)*

**Deprecated form (SG-v1, retained for lineage only):**

`SG_v1(p) = DeltaVerifiedCapability(p) / (DescriptionCost + LearningCost + VerificationCost)`

SG-v1 is ratio-shaped, unnormalized, and rewards corpus compression, which H13 explicitly declines to treat as capability.

**Canonical form (SG-v2, MDL-grounded):**

Let `L(S | G)` be the description length in bits of a *solution set* `S` under genome `G`, computed with a fixed, pre-registered code (arithmetic coding against the genome's declared prior). Let `S_ood` be solutions to held-out OOD tasks and `S_train` solutions to curriculum tasks.

```
SG_v2(p) = [ L(S_ood | G_without_p) - L(S_ood | G_with_p) ]
         - [ L(S_train | G_without_p) - L(S_train | G_with_p) ] * kappa
         - L(p | G_without_p)
```

where `L(p | G_without_p)` is the cost of writing the primitive itself and `kappa` is a pre-registered discount (default `kappa = 1.0`) penalizing primitives whose description-length savings are concentrated on tasks the search already saw.

Interpretation and rationale:

- A primitive that merely compresses the *training* corpus contributes nothing positive.
- A primitive earns positive Semantic Gain only when it shortens the description of solutions to problems it was not fitted on, by more than it costs to state.
- This aligns the metric with MDL-style generalization results, in which description length of the *labels/solutions* under a fixed prior bounds generalization, rather than with raw token counting.

`SG_v2` is still a project metric. It is not a literature-standard constant, and its `kappa` and coding scheme must be fixed before EXP-001 and reported with the result.

### 21.6 Compression/capability separation *(added v0.2)*

Every experiment reports the pair:

- `compression_ratio` = baseline model-side tokens / condition model-side tokens
- `capability_delta` = condition verified OOD solve rate - baseline verified OOD solve rate

A condition that improves `compression_ratio` with `capability_delta` inside the non-inferiority margin is reported as an **efficiency result**, never as a capability result. Conflating the two is a reportable protocol violation under Section 31.2.

### 21.5 Transfer coefficient

`TC(p, A->B) = Gain_B_with_p / Gain_A_with_p`

A primitive that only helps its inventor model but cannot be learned by another model may represent model-specific compression rather than a generally useful computational abstraction.

---

## 22. Anti-gaming design

Reward hacking is a central research risk because language evolution can hide benchmark-specific behavior inside abstractions.

### 22.1 Required defenses

- evaluator is read-only and separately packaged
- hidden tests are inaccessible
- no evaluator imports from candidate-controlled paths
- filesystem is reset per candidate
- process/environment variables are minimized
- generated programs have no network access
- immutable container image for evaluator
- separate integrity monitor detects unexpected file access and process behavior
- hardcoded test-pattern detection where applicable
- holdout structural families
- post-hoc semantic audit of high-fitness candidates

### 22.2 Suspicious primitive rule

Any primitive with unusually high task-specific gain and low cross-family reuse is automatically queued for adversarial inspection.

### 22.3 Fitness quarantine

A candidate suspected of evaluator exploitation is not deleted. It is quarantined with exploit evidence so the integrity suite can learn from the failure mode.

---

## 23. Experiment program

### E0 - Baseline construction

**Goal:** establish reproducible fixed-language and fixed-representation baselines.

Conditions:
- same model
- same task set
- same search budget
- same compiler/backend
- human-designed base representation

Deliverables:
- baseline solve curves
- compute accounting
- determinism/replay report
- evaluator integrity tests

Gate: variance across seeds is understood well enough to define confidence intervals.

### E1 - Syntax/projection optimization only

**Question:** can a semantics-preserving projection improve efficiency?

Allowed to evolve:
- surface tokens
- formatting
- reversible shorthand

Frozen:
- BSIR
- primitive set
- model weights
- tokenizer
- compiler

Compare against human syntax, SimPy-like compact syntax, and a regular S-expression baseline.

### E2 - Library abstraction discovery

**Question:** do automatically extracted abstractions improve synthesis beyond compression?

Allowed:
- macro primitives that expand entirely into K0

Required measurements:
- actual reuse frequency
- cross-family reuse
- ablation removing the library after discovery
- random-library control matched for primitive count

This experiment explicitly addresses evidence that some claimed library-learning gains can occur without meaningful function reuse.

### E3 - Semantic primitive discovery

**Question:** can Bestsad discover abstractions selected for counterfactual utility rather than only frequency?

Method:
- mine candidate repeated/equivalent subgraphs
- estimate workload benefit if primitive existed
- deduplicate semantically
- promote only with cross-task evidence

### E4 - Semantic graph representation

**Question:** does mutation/search over a graph-oriented state outperform direct source-code mutation?

Compare:
- text source mutation
- AST mutation
- BSIR graph/mutation-surface mutation

### E5 - Equivalence-rich optimization

**Question:** can e-graph/equality-saturation search improve extraction of useful implementations and abstractions within bounded resources?

Compare:
- sequential rewrites
- unrestricted bounded EqSat
- strategy-guided EqSat
- LLM/evolution synthesized strategies

### E6 - Model adaptation

**Question:** after a useful language is found with fixed weights, does fine-tuning on that language amplify or erase the advantage?

Conditions:
- matched training token/compute budget
- baseline fine-tuning on conventional representation
- Bestsad fine-tuning on evolved representation

### E7 - Cross-model language transfer

**Question:** does a discovered language help models that did not invent it?

Test at least two materially different model families/sizes when resources permit.

### E8 - Curriculum coevolution

**Question:** does an evolving training curriculum produce more transferable language evolution than a fixed curriculum?

Claim metric remains frozen hidden evaluation.

### E9 - Compiler strategy evolution

**Question:** after language effects are stable, can compiler policy evolution add independent gains?

Keep language fixed while evolving transformation schedules/heuristics.

### E10 - Tokenizer co-design

**Question:** does adapting tokenization to an already successful language provide additional benefit?

Only after E1-E7 establish language effects without tokenizer changes.

### E11 - Learned/neural primitive experiment

Research-only. A learned primitive may be used as an `EXP` primitive under behavioral evaluation but cannot be treated as exact trusted semantics without a formal/specification bridge.

### E12 - Hardware co-design

Long-term only. Promote frequently useful semantics to intrinsics/accelerators and test whether language-discovered abstractions reveal useful ISA opportunities.

---

## 24. Primary first experiment (Bestsad-EXP-001)

### 24.1 Research question

Can automatically evolved semantics-preserving abstractions improve verified OOD program synthesis for a fixed model and fixed semantic kernel?

### 24.2 Domain

Synthetic typed list/scalar transformation tasks generated from K0.

### 24.3 Train/curriculum split

- task families F1-F8 available to search/training
- instances procedurally generated with fresh seeds
- family-composition depth increases gradually

### 24.4 Frozen evaluation

- unseen seeds from F1-F8
- held-out compositional families F9-F12
- adversarially similar tasks where shortcut primitives should fail

### 24.5 Conditions

**Original v0.1 conditions (retained):**

A. K0 baseline language  
B. K0 + random macros matched by count/size  
C. K0 + frequency-only extracted macros  
D. K0 + Bestsad utility-selected abstractions  
E. K0 + Bestsad abstractions with compact projection  

**Mandatory additional controls (added v0.2). EXP-001 may not be reported without them.**

F. **Compression-matched control.** A representation engineered to match condition E's model-side token count as closely as feasible while adding *no* new semantic abstraction (e.g. pure surface-level shortening/renaming over K0). Isolates H13. If F matches E, the gain is compression, not semantics.

G. **Human-expert DSL upper bound.** A competent, human-designed DSL for the same task family, authored by a person blind to the evolved genomes and time-boxed in a pre-registered way. Answers the reviewer question "is the evolved language beating a real design, or only beating raw K0?" A result where D/E beats A but loses badly to G is a weak result and must be reported as such.

H. **Scaffolding-matched control.** Every condition receives equalized in-context scaffolding: same grammar-description budget in tokens, same count and difficulty of worked examples, same retry/repair policy, same decoding constraints. Isolates H14. Where exact equalization is impossible, the residual difference is reported as a bounded confound with its size in tokens.

I. **Search-only compute-matched baseline.** Condition A is given the *entire* compute consumed by genome evolution in condition D, spent instead on additional search/sampling in the baseline language. Isolates H15. This is the primary rival explanation and the single most important control in the experiment.

Same model weights for A-I. Search budget matched per Section 26.6. Conditions F-I are controls, not treatments: they exist to falsify, and a well-run EXP-001 may consist entirely of a control defeating the treatment.

### 24.6 Primary outcome

`verified_ood_solve_rate_per_compute`

Measured on **verified compositional OOD** tasks (held-out families F9-F12), not on in-family unseen seeds. In-family performance is a secondary outcome only.

Rationale for the choice of terrain: published results on compositional verified synthesis show a very large gap between single-unit success and compositional success, with strong single-function verification collapsing by an order of magnitude once tasks must compose. That gap is where a genuine representational advantage would be visible, and where token-level compression should provide no help. Bestsad therefore places its primary endpoint there deliberately, accepting a lower absolute solve rate in exchange for a more discriminating test.

### 24.7 Secondary outcomes

- raw verified solve rate
- search nodes expanded
- generation tokens
- primitive reuse
- cross-family primitive reuse
- verification cost
- language size
- `compression_ratio` and `capability_delta` reported as a pair (Section 21.6)
- per-primitive causal mediation estimates (Section 42)
- scaffolding token budget actually delivered per condition

### 24.8 Provisional minimum interesting effect

Before running the experiment, pre-register one or both of:

- >= 5 percentage-point absolute verified OOD solve-rate improvement at matched total compute; or
- >= 15% reduction in total experimental compute at a pre-registered non-inferior solve rate.

These are project operating thresholds, not literature-derived constants, and should be revisited after E0 variance is measured.

### 24.9 Falsification signal

Strong evidence against the near-term thesis would include:

- gains disappearing on held-out families;
- gains explained entirely by longer search or more training compute;
- no advantage over random/frequency-matched macro controls;
- low actual primitive reuse;
- benefits that vanish when surface token count is equalized;
- repeated evaluator exploitation rather than semantic improvement;
- condition F (compression-matched) matching conditions D/E;
- condition I (search-only, compute-matched) matching conditions D/E;
- gains that disappear once condition H equalizes in-context scaffolding;
- gains concentrated in fewer than two primitives under causal mediation analysis, where those primitives are shortcut- or compression-shaped;
- condition G (human-expert DSL) dominating D/E by a margin larger than D/E's margin over A.

---

## 25. Ablation matrix

| Condition | New abstractions | New projection | New tokenizer | Model fine-tune | Compiler evolution | Graph search |
|---|---:|---:|---:|---:|---:|---:|
| A0 Baseline | No | No | No | No | No | No |
| A1 Projection | No | Yes | No | No | No | No |
| A2 Abstraction | Yes | No | No | No | No | No |
| A3 Abstraction+Projection | Yes | Yes | No | No | No | No |
| A4 Graph | Yes | Yes | No | No | No | Yes |
| A5 Tokenizer only | Yes | Yes | Yes | No | No | Yes |
| A6 Adapted model only | Yes | Yes | No | Yes | No | Yes |
| A7 Tokenizer + adapted model | Yes | Yes | Yes | Yes | No | Yes |
| A8 Compiler | Yes | Yes | Yes | Yes | Yes | Yes |

**Change in v0.2:** the v0.1 ladder introduced model fine-tuning (old A5) *before* tokenizer change (old A6), which made the two inseparable: any tokenizer effect was measured only on an already-adapted model. The revised ladder splits them into A5 (tokenizer, frozen model) and A6 (adapted model, original tokenizer), with A7 as the combination. This is what makes open question 15 - "when is tokenizer co-design causally distinct from language co-design?" - answerable rather than confounded.

No headline claim should rely solely on A8 versus A0; intermediate conditions are required for attribution. Any claim about tokenizer contribution requires A5, A6, and A7 together, since the combination may be sub- or super-additive.

---

## 26. Statistical and reproducibility protocol

### 26.1 Seeds

Use multiple independent seeds for:

- candidate evolution
- task generation
- model sampling where stochastic
- evaluator randomized tests

### 26.2 Report distributions

Report median, mean, confidence intervals, and per-seed values rather than only best-run results.

### 26.3 Best-of-N disclosure

Any best-of-N or population selection must include the total search budget and number of candidates evaluated.

### 26.4 Compute ledger

Every run logs:

- model identity/hash
- model inference tokens
- accelerator type
- wall clock
- CPU/GPU time where measurable
- candidate evaluations
- compile time
- execution time
- verifier time
- task counts

### 26.5 Pre-registration requirement *(added v0.2)*

No Bestsad experiment may be reported as confirmatory unless a pre-registration document was committed, hashed, and timestamped **before** the first evaluation run. See `BESTSAD_PREREGISTRATION_EXP001_v0.2.md` for the canonical template and the EXP-001 instance.

The pre-registration fixes, at minimum: the primary endpoint; the condition list; the seed count and seed generation procedure; the stopping rule; the non-inferiority margins; the multiple-comparison correction; the exclusion criteria; and the analysis code path. Anything decided after data is seen is exploratory and must be labeled Level E under Section 31.2.

### 26.6 Compute matching policy *(added v0.2)*

"Matched compute" is defined as matched **total experimental compute**, accounted as the sum of model inference, search, compilation, execution, and verification, using the ledger in Section 26.4. Genome-evolution compute counts against the condition that produced the genome. Condition I exists precisely to spend that same amount on the baseline.

Report per-compute *curves*, not single points. A single matched-compute point is not sufficient evidence: the ordering of conditions can invert with budget, and the shape of the curve is itself the finding.

### 26.7 Multiple-comparison control *(added v0.2)*

The hypothesis set H1-H15 and the ablation ladder A0-A8 imply dozens of simultaneous comparisons. Without correction, a 5-percentage-point "win" is likely to appear somewhere by chance alone.

Required:

- exactly one pre-registered **primary** endpoint per experiment;
- all other endpoints declared secondary and reported with Benjamini-Hochberg FDR control at a pre-registered level (default q = 0.05) within a declared comparison family;
- the comparison family declared in the pre-registration, not chosen afterwards;
- per-seed values published so any reader can recompute.

### 26.8 Power and non-inferiority sizing *(added v0.2)*

Power analysis is required before the run, using variance measured in E0 rather than assumed.

Note for planning: two-sided **equivalence** designs require materially more samples than one-sided **non-inferiority** designs at the same margin and power. Bestsad's compression/projection arms should be framed as non-inferiority wherever the scientific question genuinely is "no worse," and only as equivalence where "no different in either direction" is actually required. Choosing equivalence framing casually inflates the required seed count for no scientific gain.

If the achievable seed count cannot power the pre-registered minimum interesting effect, the correct action is to say so in the pre-registration and re-scope, not to run underpowered and interpret the point estimate.

### 26.9 Artifact identity

Every run emits a manifest with hashes of:

- code revision
- container image
- kernel spec
- benchmark manifest
- genome
- compiler toolchain
- verifier toolchain

---

## 27. Security architecture

### 27.1 Candidate sandbox

Minimum:

- process isolation
- no network
- read-only base filesystem
- writable ephemeral scratch only
- CPU/memory/time limits
- syscall restrictions appropriate to runtime
- no access to host credentials
- no access to hidden evaluation assets

### 27.2 Evaluator isolation

Evaluator runs outside candidate-controlled namespace and receives only declared artifacts and inputs.

### 27.3 Supply-chain control

Pin compiler/verifier versions. Record hashes. Candidate-generated dependencies are forbidden in early phases.

### 27.4 Self-hosting gate

Bestsad may not compile its own trusted evaluator or semantic kernel during v0.1. Self-hosting is a later experiment because compiler trust attacks can survive bootstrap chains.

---

## 28. Repository architecture

```text
bestsad/
  README.md
  LICENSE
  pyproject.toml / Cargo.toml as appropriate
  docs/
    architecture/
    research/
    experiments/
    adr/
  kernel/
    k0_spec/
    reference_interpreter/
    tests/
  bsir/
    schema/
    parser/
    canonicalize/
    hash/
  genomes/
    schema/
    registry/
    lineage/
  evolution/
    operators/
    islands/
    novelty/
    archive/
  abstraction/
    extract/
    anti_unify/
    utility/
  eqsat/
    rules/
    strategy/
    proof_cache/
  compiler/
    mlir/
    llvm/
    cost_model/
  verification/
    static/
    differential/
    property/
    symbolic/
    translation/
  evaluator/
    public_contract/
    curriculum/
    adversarial/
    # frozen hidden assets maintained separately
  models/
    adapters/
    projections/
  experiments/
    manifests/
    runners/
    analysis/
  telemetry/
    compute_ledger/
    events/
  schemas/
  tests/
```

The hidden frozen evaluator should ideally live in a separate repository or protected service namespace so the evolutionary agent cannot inspect it.

---

## 29. Core service/API contracts

### 29.1 `Kernel.execute(program, inputs)`
Returns deterministic `Value | Trap` plus execution trace/hash.

### 29.2 `BSIR.verify(graph)`
Performs structural/type/effect validation.

### 29.3 `Genome.materialize(genome_id, model_adapter)`
Builds the active model projection and compiler mapping.

### 29.4 `Abstraction.propose(corpus, constraints)`
Returns candidate abstractions with semantic expansions and utility estimates.

### 29.5 `Equivalence.prove(a, b, assumptions)`
Returns proof status, method, conditions, and artifact reference.

### 29.6 `Compiler.lower(bsir, target)`
Returns target IR plus translation-validation obligations.

### 29.7 `Evaluator.score(candidate_artifact, benchmark_manifest)`
Runs isolated evaluation and returns a signed/hashed fitness vector.

### 29.8 `Evolution.step(population, evidence)`
Produces child genomes and immutable lineage events.

---

## 30. Data schemas

This package includes machine-readable drafts:

- `schemas/language_genome.schema.json`
- `schemas/primitive_record.schema.json`
- `schemas/experiment_manifest.schema.json`
- `schemas/benchmark_manifest.schema.json`

These are v0.1 contracts and should change only through versioned schema evolution.

---

## 31. Research governance and change control

### 31.1 Architecture Decision Records

Any change to these requires an ADR:

- K0 semantics
- primary metric
- hidden-evaluation protocol
- primitive maturity definitions
- trust boundary
- allowed mutation permissions
- benchmark family definitions

### 31.2 Claim levels

**Level 0 - observation:** one run / exploratory.  
**Level 1 - replicated internal result:** multiple seeds.  
**Level 2 - controlled result:** matched baselines and ablations.  
**Level 3 - external reproducibility:** independent reproduction.  
**Level 4 - strong research claim:** cross-model/domain replication plus transparent compute/evaluation record.

### 31.3 No anthropomorphic claim inflation

Terms such as “invented,” “discovered,” or “language” should be operationally defined in papers. A macro extractor discovering a repeated subtree is not the same result as discovering new semantics or a transferable machine communication protocol.

---

## 32. Twelve-month staged roadmap

### Phase 0 - Foundation (weeks 1-6)
- K0 spec and interpreter
- BSIR schema/canonicalization
- baseline generator/evaluator
- secure runner
- compute ledger
- first model adapter

Exit: E0 reproducible.

### Phase 1 - Representation and abstraction (weeks 7-14)
- compact projections
- S-expression baseline
- abstraction extractor
- random/frequency controls
- EXP-001

Exit: controlled E1/E2 evidence.

### Phase 2 - Utility and equivalence (weeks 15-24)
- semantic deduplication
- e-graph engine integration
- bounded strategy search
- counterfactual utility ranking
- primitive lineage UI/report

Exit: E3/E5 evidence.

### Phase 3 - Graph search and transfer (weeks 25-34)
- mutation-surface graph representation
- cross-model adapter
- transfer benchmarks
- speciation/island evolution

Exit: E4/E7 evidence.

### Phase 4 - Co-training and curriculum (weeks 35-44)
- controlled fine-tuning
- evolving curriculum separate from hidden benchmark
- anti-gaming stress tests

Exit: E6/E8 evidence.

### Phase 5 - Compiler evolution / publication package (weeks 45-52)
- fixed-language compiler-strategy evolution
- consolidated ablation
- external reproduction kit
- paper-ready evidence ledger

Exit: credible v0.1 research report; tokenizer/hardware phases gated by results.

---

## 33. Launch gates

### Gate G0 - Semantic anchor
- K0 spec frozen
- interpreter tests pass
- trap behavior defined

### Gate G1 - Evaluator integrity
- hidden assets inaccessible to candidates
- exploit tests demonstrate isolation
- evaluator artifacts hashed

### Gate G2 - Baseline reproducibility
- multiple seeds
- compute variance understood
- replay works

### Gate G3 - Abstraction controls
- random macro control
- frequency-only control
- actual reuse measurement

### Gate G4 - OOD validity
- family holdouts
- hidden generator
- no training overlap by construction

### Gate G5 - Verification
- every accepted program checked by trusted interpreter
- every primitive expansion recorded
- differential verifier operational

### Gate G6 - Research traceability
- genome lineage
- source commit
- benchmark manifest
- compute ledger
- result hashes

Only after G0-G6 should EXP-001 be used for a project-level scientific claim.

---

## 34. Open research questions

Each question is tagged in v0.2 with its evidence status as of the v0.2 cutoff:
**[OPEN]** no useful external evidence, **[PARTIAL]** literature constrains the answer but does not settle it,
**[LEAN-NEG]** available evidence leans against Bestsad's optimistic reading, **[TESTABLE-NOW]** answerable inside EXP-001 or its immediate successors.

1. Does a model benefit more from semantic abstraction or token compression? **[PARTIAL / TESTABLE-NOW]** - MDL theory supplies a discriminating measure (Section 21.4), and tokenizer studies indicate token compression alone can move speed and effective context without moving accuracy. Condition F operationalizes the test.
2. Are machine-discovered abstractions stable across seeds? **[OPEN / TESTABLE-NOW]** - library-learning results are known to be seed-sensitive; treat cross-seed abstraction identity as a first-class reported outcome, not a footnote.
3. Do different models independently converge on equivalent primitives? **[LEAN-NEG]** - emergent-communication work generally finds protocols that are effective but compositionally poor and prone to drift, which argues against spontaneous convergence. Bestsad should expect divergence and treat convergence as a surprising positive.
4. Does convergent evolution predict general usefulness? **[OPEN]** - contingent on question 3; do not build the promotion pipeline on the assumption that it does.
5. What is the best complexity penalty for language growth? **[PARTIAL]** - MDL supplies a principled family of penalties; the specific constant remains empirical.
6. How should verification cost enter multi-objective fitness? **[OPEN]**
7. Is there a phase transition where richer primitives reduce search enough to outweigh vocabulary learning cost? **[OPEN]** - and note that no current evidence establishes the transition falls on the favorable side. This is the crux of the whole program.
8. Can a discovered representation transfer across autoregressive and diffusion-like code models? **[OPEN]**
9. When does a graph representation outperform textual regularity? **[OPEN / TESTABLE-NOW]** - ablation node A4.
10. Can e-graph extraction itself become a learned/evolved language-design mechanism? **[PARTIAL - LARGELY YES]** - differentiable extraction and learned/RL-driven rewriting already demonstrate evolvable extraction in narrower settings. Bestsad should adopt rather than re-derive, and reframe the question as *which* extraction objective to evolve.
11. Do compact symbolic protocols retain enough interpretability for debugging and governance? **[LEAN-NEG]** - compactness and interpretability trade off in the emergent-communication literature; Bestsad's mandatory human projection (P8) is the mitigation, and its adequacy is itself an open question.
12. Can latent channels add capability once surface-form information is controlled, or are their gains mostly compression/alignment effects? **[LEAN-NEG / OPEN]** - active area, but no result yet demonstrates capability gains surviving surface-information controls. Remains a non-goal for v0.2.
13. Which primitive maturity evidence best predicts future reuse? **[OPEN / TESTABLE-NOW]** - this is the one question EXP-001 can answer cheaply as a by-product, by recording candidate maturity evidence and correlating with realized cross-family reuse.
14. Can model-language co-training create lock-in that hurts transfer? **[OPEN]** - gated behind A6/A7.
15. When is tokenizer co-design causally distinct from language co-design? **[TESTABLE-NOW]** - made answerable by the revised A5/A6/A7 split in Section 25.
16. Can verified-by-construction abstractions outperform unrestricted discovered macros under equal compute? **[OPEN / TESTABLE-NOW]** - a clean, high-value second experiment.
17. Do machine-native representations improve code reasoning tasks beyond program synthesis, such as proof planning or compiler optimization? **[PARTIAL]** - IR-grounded pretraining improves robustness on code generation, which is weak positive evidence for the machine leg but not for proof planning.
18. At what point does changing the type/effect system become more valuable than adding primitives? **[OPEN]**
19. Can hardware-level recurring patterns discovered by Bestsad justify new intrinsics or instructions? **[PARTIAL]** - automated custom-instruction synthesis already formalizes this as enumeration plus selection over dataflow graphs; Bestsad can inherit that formalism rather than invent one.
20. What negative results should permanently constrain future Bestsad search spaces? **[OPEN]** - the answer accretes; Section 44 defines where it is recorded.

---

## 35. Falsification and stop conditions

Bestsad should pause or redirect if, after adequately powered controlled experiments:

- all gains reduce to token shortening;
- no abstraction demonstrates real reuse or OOD transfer;
- fixed conventional DSLs match evolved languages under equal search effort;
- verification cost consistently overwhelms capability gains;
- cross-model transfer is near zero for all discovered abstractions;
- improvements only appear when the evaluator is visible or mutable;
- gains disappear under frozen hidden benchmarks;
- language complexity grows without improving capability efficiency.

A stop condition is a scientific success if it narrows the hypothesis space.

---

## 36. Recommended first implementation choices

These are engineering defaults, not immutable research conclusions:

- host implementation: Rust or a Rust/Python split for core + experiment orchestration
- canonical external serialization: JSON for schemas plus compact S-expression/text for debugging
- e-graph: `egg`/`egglog`-family concepts or equivalent; consider differentiable and exact-extraction work for the extraction step rather than writing a new extractor
- compiler substrate: MLIR -> LLVM; use IRDL/dynamic dialects for genome-defined operations and the Transform dialect for evolvable pass pipelines
- translation validation: an Alive2-style refinement checker on the LLVM leg rather than a bespoke checker
- property testing: language-appropriate property/fuzz framework
- symbolic checks: SMT for bounded subsets
- abstraction baseline: an existing MDL-optimal corpus abstraction tool as condition C's implementation, so the frequency/MDL control is a real baseline rather than a strawman
- machine-fitness cost model: an existing autotuning stack's measurement protocol and cost model rather than a new one
- rival baseline: an open evolutionary code-search implementation, run in the baseline language, as condition I
- contamination-resistant evaluation: dynamically generated task instances plus time-partitioned holdouts
- integrity suite: existing reward-hacking / specification-gaming benchmark suites as the seed corpus for the adversarial integrity plane
- experiment tracking: content-addressed run manifests plus append-only result ledger
- containers: immutable evaluator image and separate candidate sandbox

**Build-vs-adopt rule (v0.2):** Bestsad's contribution is the *integration* and the *proof methodology*, not any single component. Any proposal to hand-write a component that already exists in mature form requires an ADR justifying why the existing tool cannot be wrapped.

Do not introduce model fine-tuning, custom tokenizers, GPUs-as-semantics, or new hardware in the first causal experiment unless required to establish the baseline.

---

## 37. Canonical v0.1 thesis statement

> **Bestsad tests whether computational intelligence can be increased by allowing machines to discover and evolve executable representations, abstractions, and language structures that are optimized for machine reasoning while remaining anchored to independently verified semantics.**

The immediate target is not a new human programming language. It is empirical evidence about whether representation itself is a meaningful lever on computational intelligence.

---

## 38. Source dependency

All external research claims motivating this architecture are documented and annotated in `BESTSAD_RESEARCH_COMPANION_v0.1.md` and enumerated in `BESTSAD_SOURCE_LEDGER_v0.1.csv`. Architectural elements not directly established by cited research are marked in that companion as **Bestsad synthesis**, **proposed experiment**, or **inference**.

---

## 39. Prior-art positioning and novelty claim *(added v0.2)*

### 39.1 What Bestsad may claim

Bestsad's defensible claim is **integration novelty plus proof methodology**. As of the v0.2 evidence cutoff, no published system simultaneously (a) evolves a machine-native executable language, (b) maintains a canonical semantic substrate distinct from model-specific projections, and (c) co-evolves compiler transformation policy under independent anti-gaming evaluation.

### 39.2 What Bestsad may not claim

Every individual component has prior art, in several cases mature prior art:

| Component | Nearest prior art | Consequence for Bestsad |
|---|---|---|
| Canonical semantics vs surface dialects | Extensible multi-level compiler IR frameworks | No priority claim. Adopt the substrate. |
| Model-driven evolution of code/algorithms | Evolutionary coding agents that beat long-standing algorithmic records while leaving the language fixed | No priority claim, and this family is Bestsad's rival explanation (condition I). |
| Evolving compiler heuristics | Recent work evolving compiler pass heuristics with LLM-driven search | No priority claim on compiler policy evolution. |
| Learned libraries/abstractions | Wake-sleep program induction and MDL-optimal abstraction extraction | No priority claim; also the source of the strongest negative results. |
| Purpose-built LLM-oriented DSL | Human-designed DSLs reporting high zero-shot parse validity and multi-step accuracy gains over general-purpose languages | No priority claim on "a language designed for models"; the novelty is that Bestsad's is *evolved and semantically anchored*, not hand-designed. |
| Search-based stack co-optimization | Recent search-based "compiler for AI-native software" proposals | No priority claim on the co-evolution framing. |

### 39.3 Standing instruction

Section 22 of the companion (the ten-part gap) is an **absence-of-evidence** claim, not a proof of absence, and it decays with time. Re-run the prior-art sweep before every publication and before every Gate transition, and record the result as an ADR.

---

## 40. Confound control plane *(added v0.2)*

This section is normative. A run that does not satisfy it is exploratory, not confirmatory.

### 40.1 The four confounds

| # | Confound | Failure it produces | Control |
|---|---|---|---|
| C1 | Compute / search budget | "Evolved language wins" when it was simply given more total compute | Condition I; Section 26.6 per-compute curves |
| C2 | Token / information compression | Compression reported as capability | Condition F; Section 21.6 paired reporting; MDL Semantic Gain |
| C3 | In-context scaffolding | Prompt engineering reported as representation | Condition H; scaffolding token budget logged per condition |
| C4 | Training exposure / contamination | Memorization reported as generalization | Frozen hidden benchmark, procedurally generated instances with fresh seeds, family holdouts, canary strings, time-partitioned splits |

### 40.2 Reference-class control

Condition G (human-expert DSL) is not a confound control but a **reference class**. Its purpose is to prevent the weakest form of the Bestsad result: beating an intentionally impoverished baseline kernel. Report D/E versus A *and* D/E versus G, always together.

### 40.3 Residual confound disclosure

Where a confound cannot be fully controlled, the residual must be quantified and published (e.g. "scaffolding equalized to within 40 tokens; condition E received 3.1% more description budget"). Undisclosed residuals are a protocol violation.

---

## 41. Evidence taxonomy for the balance of evidence *(added v0.2)*

Bestsad must not represent its thesis as better supported than it is. The current external balance of evidence, as recorded in the companion:

- **Supported:** constrained, canonical, low-variance representations reduce model error rates on structured generation; IR grounding improves cross-language robustness; structured abstraction helps in specific generative domains.
- **Contested / frequently fails controls:** that automatically learned libraries and abstractions improve *generalized* capability at matched compute. Multiple published analyses find reuse is rare and that apparent gains are attributable to self-correction, self-consistency, or unaccounted compute.
- **Unproven:** the strong Bestsad thesis, that evolved machine-native representations increase generalized computational capability.

**Standing instruction:** the program's public framing is the narrow, falsifiable claim. The strong thesis is the hypothesis under test, never a premise of the writing.

---

## 42. Causal attribution plane *(added v0.2)*

Stage-level ablation (Section 25) answers "which stage carried the gain." It does not answer "which primitive carried the gain," which is the question a reviewer will ask and the question the promotion pipeline needs.

### 42.1 Per-primitive mediation

Treat each promoted primitive `p` as a mediator between the genome and the outcome. For each `p`:

- **Direct effect:** outcome change when `p` is ablated (removed and its call sites re-expanded to the K0 equivalent), holding search budget fixed.
- **Indirect effect:** outcome change when `p` is retained but its call sites are forced to the expanded form, isolating whether the benefit is the abstraction itself or its availability during search.
- **Interaction:** paired ablations for primitives that co-occur above a pre-registered threshold.

### 42.2 Concentration test

Compute the share of total measured gain attributable to the top-1 and top-2 primitives.

**Stop rule:** if more than a pre-registered share (default 80%) of the gain is carried by fewer than two primitives, *and* those primitives are shortcut-shaped or compression-shaped under the Section 22.2 suspicious-primitive rule, the result is recorded as consistent with H0 regardless of the aggregate effect size.

### 42.3 Reporting

Publish the full per-primitive effect table, including primitives with null and negative effects. Selective reporting of the primitives that worked is a protocol violation.

---

## 43. Staged funding gates for EXP-001 *(added v0.2)*

The expensive arms are gated on the cheap arms succeeding.

| Stage | Contents | Gate to proceed |
|---|---|---|
| S1 | E0 baseline + variance measurement | Variance measured; power analysis passes for the pre-registered minimum interesting effect |
| S2 | Conditions A-E plus controls F, H, I on ablation nodes A0-A4 | Pre-registered primary effect met, FDR-corrected, across the pre-registered seed count; no control matches treatment |
| S3 | Condition G reference class; per-primitive causal mediation | Concentration test passed; D/E margin over A not dwarfed by G's margin over D/E |
| S4 | A5 tokenizer / A6 adapted model / A7 combination | S2 and S3 both passed |
| S5 | A8 compiler evolution; cross-model transfer (H9) | S4 passed |

**Cost note (project inference, not a measured figure):** because the EXP-001 domain is synthetic and generated from K0, and because evolutionary search cost is dominated by inference sampling rather than training, S1-S3 are expected to be a moderate inference-bound budget on a small open-weight model across the pre-registered seed count, not a training-scale effort. S4 introduces fine-tuning and is the first materially expensive stage. Treat these as planning assumptions to be replaced by measured E0 numbers, and record the measured figures in the compute ledger.

---

## 44. Negative-result ledger *(added v0.2)*

Design principle P7 requires preserving negative results. v0.2 makes this concrete.

`docs/research/negative_results/` holds one append-only record per negative or null finding, containing: the hypothesis, the conditions run, the seed count, the effect size with interval, the confound controls that were satisfied, and - critically - **the search-space constraint the result implies** (open question 20).

A negative result is a deliverable. Gate G6 is not satisfied if the ledger is empty after a stage completes with null findings.

---

## 45. Claims register *(added v0.2)*

The following claims are **prohibited** in any Bestsad artifact, internal or external, until the corresponding evidence exists:

1. That evolved machine-native languages improve generalized computational capability. *(Unproven; this is the hypothesis under test.)*
2. Any priority claim over existing extensible-IR frameworks, evolutionary coding agents, compiler-heuristic evolution work, program-induction/library-learning systems, or hand-designed LLM-oriented DSLs.
3. That discovered primitives transfer across models. *(H9; current external evidence leans against.)*
4. That latent or non-symbolic channels add capability once surface-form information is controlled.
5. That shorter representation implies greater intelligence. *(Already a v0.1 non-goal; restated here because it is the most likely accidental claim.)*
6. That Bestsad is a Diné/Navajo word or grammatically canonical compound. *(See Section 1.)*

Permitted claim shape for the current stage:

> "Under matched compute, matched scaffolding, and compression-matched controls, evolved abstractions changed verified compositional OOD solve rate by X (95% CI ...) on domain D for model M, with per-primitive attribution as reported."

---
