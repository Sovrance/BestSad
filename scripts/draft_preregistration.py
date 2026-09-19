#!/usr/bin/env python3
"""Emit the EXP-002..005 pre-registration drafts (roadmap §3; ADR-0022).

A pre-registration is committed — timestamped and hashed — *before the first evaluation run*
(spec §26.5). These are **drafts**: everything the roadmap fixes in advance is fixed here (the
conditions, the endpoints, the minimum interesting effects, the outcome interpretations, the
exclusion rules), and everything that cannot exist until a model is chosen is a `<<FILL>>`
placeholder — the model identity and its hash, the evaluator image digest, the analysis code
revision, and the power analysis from an E0 variance measured *under that model*. ADR-0023 chose
EXP-002's model, endpoint and compute currency, so its draft now names
`Qwen/Qwen2.5-Coder-7B-Instruct` with `<<FILL>>` only where the weights on disk or the pilot
are needed (revision, digest, vLLM version, hardware, the per-task budget C, the seed count).
`Preregistration.is_complete()` names every placeholder, and `ReportGate` refuses confirmatory
certification against a draft, so a draft cannot be mistaken for a commitment.

    python scripts/draft_preregistration.py            # write the drafts
    python scripts/draft_preregistration.py --check    # exit 1 if the files on disk drifted

Committing a draft is the owner's act: fill the placeholders, `Preregistration.commit()`, and
save the result as `EXP-00N.json` next to the draft, which then stays as the record of what
was fixed before the model was chosen.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from bestsad.kernel import KERNEL_VERSION  # noqa: E402
from bestsad.stats import Preregistration  # noqa: E402

OUT_DIR = REPO / "docs" / "preregistrations"
FILL = "<<FILL>>"

#: Placeholders EXP-003..005 share. ADR-0023 chose EXP-002's model; the later experiments
#: inherit that identity by default and fill it when each is committed, after EXP-002 reports.
MODEL_IDENTITY_FILL = {
    "model_id": FILL,
    "kind": "fixed_weights_llm",
    "weights_digest": f"{FILL}: sha256 of the weights, or the provider's immutable snapshot id",
    "tokenizer_id": FILL,
    "parameter_count": FILL,
    "provider": FILL,
    "mode": "fixed-weights",
    "supported_projections": ["sexpr", "compact"],
    "context_budget_tokens": FILL,
    "constrained_decoding": False,
    "logprob_access": FILL,
    "tool_interface": "none",
    "sampling": {"temperature": FILL, "max_output_tokens": FILL, "seed_policy": "per (seed, task, sample) hash"},
    "model_identity_hash": f"{FILL}: ModelIdentity.hash() of the record above",
    "claim_limitation": (
        "the model role is a fixed-weights language model (ADR-0022); results are Claim Level 1 "
        "at most until the evaluator is containerised and the assets relocated (ADR-0005)"
    ),
}
POWER_FILL = {
    "variance_source_run": f"{FILL}: E0 re-measured under the model (Exp001Runner.stage_s1 with the model spec)",
    "variance_estimate": FILL,
    "required_seeds": FILL,
    "achieved_power": FILL,
    "target_power": 0.8,
    "alpha": 0.05,
    "framing": "superiority",
    # False until an E0 variance measured under the model says otherwise; the schema types this
    # as a boolean, and `variance_source_run` above carries the placeholder.
    "powered": False,
}
COMMON_EXCLUSIONS = (
    "sandbox crash",
    "evaluator image mismatch",
    "ledger corruption",
    "a fatal transcript leak finding (canary or sealed input on a model-visible surface): the "
    "run is aborted and the finding recorded, never a silent exclusion",
    "Exclusion for unfavourable results is prohibited; all exclusions listed with cause.",
)
#: ADR-0023: EXP-002's model, pinned. What needs the weights on disk or the pilot stays `<<FILL>>`;
#: everything the decision fixes is fixed here, and `ModelIdentity.is_pinned()` names the rest.
EXP002_SERVING = {
    "engine": "vllm",
    "version": f"{FILL}: the pinned vLLM version, as `pip freeze` prints it",
    "api": "openai-chat-completions",
    "hardware": (
        f"{FILL}: one H100-class device, e.g. '1x NVIDIA H100 80GB SXM (Azure NC-H100 or "
        "equivalent)', with driver and CUDA versions"
    ),
    "nondeterminism_sources": [
        "vLLM continuous batching is not bit-reproducible across batch compositions; "
        "transcripts are recorded once and replayed, and verdicts are compared, never logits"
    ],
    "trust_boundary": (
        "candidate side: the server receives the grammar description and a task's visible "
        "examples only; OutboundGuard refuses any prompt carrying a task identifier, a sealed "
        "input, the canary or a hidden-asset path before it is sent "
        "(tests/integrity/test_model_boundary.py)"
    ),
}
EXP002_MODEL_IDENTITY = {
    "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "kind": "fixed_weights_llm",
    "revision": f"{FILL}: the Hugging Face commit id the weights were fetched at",
    "weights_digest": f"{FILL}: sha256 over the safetensors shards at that revision, in index order",
    "tokenizer_id": "Qwen/Qwen2.5-Coder-7B-Instruct (tokenizer at the same revision)",
    # Total parameters from the configuration at the pinned revision (ADR-0023 gives the
    # derivation); verified against the loaded weights at pin time.
    "parameter_count": 7_615_616_512,
    "provider": "self-hosted",
    "mode": "fixed-weights",
    "dtype": "bfloat16",
    "quantization": "none",
    "supported_projections": ["sexpr", "compact"],
    "context_budget_tokens": 32768,
    "constrained_decoding": False,
    "logprob_access": True,
    "tool_interface": "none",
    "sampling": {
        "temperature": 0.2, "top_p": 1.0, "max_output_tokens": 256,
        "seed_policy": "per (seed, task, sample) hash",
        "max_samples_per_task": f"{FILL}: from the pilot (planning figure 32)",
        "repair_rounds": 2,
    },
    "serving": EXP002_SERVING,
    "model_identity_hash": (
        f"{FILL}: ModelIdentity.hash() of the record above once revision, weights_digest, "
        "serving.version and serving.hardware are filled"
    ),
    "claim_limitation": (
        "the model role is a pinned, self-hosted fixed-weights language model (ADR-0023); "
        "results are Claim Level 1 at most until the evaluator is containerised and the assets "
        "relocated (ADR-0005)"
    ),
}
EXP002_COMPUTE_BUDGET = {
    "currency": (
        "device-seconds on the pinned hardware (device-seconds-1.0.0), reported alongside a "
        "FLOP estimate under flops-1.0.0; never the FLOP estimate alone"
    ),
    "hardware": f"{FILL}: the same string as model_identity.serving.hardware",
    "per_task_budget_C_device_seconds": (
        f"{FILL}: set from the two-seed E0 pilot (scripts/exp002_pilot.py), never from the "
        "planning estimate"
    ),
    "planning_estimate": (
        "for orientation only: 9 conditions x 32 seeds x ~96 tasks x 32 samples x ~1.7k tokens "
        "~= 2e19 FLOPs, one to three H100-days (ADR-0023); replaced by the pilot"
    ),
    "rates": f"{FILL}: the calibrated DeviceSecondsPolicy record the pilot wrote",
    "condition_I_conversion": (
        "pre-registered assumption: condition I's inherited discovery compute (kernel steps, "
        "search nodes, tokens) is converted to device-seconds through the pilot-measured rates "
        "on the same pinned hardware. There is no principled FLOP equivalence between an "
        "enumerator step and a decoded token; the identity compute(I) == compute(A) + "
        "compute(evolution) is reported in device-seconds, FLOPs and nodes side by side"
    ),
    "nondeterminism": "vLLM batching (named in model_identity.serving); verdicts, never logits",
}
EXP002_SEALED_HOLDOUT = {
    "policy": "holdout-1.0.0",
    "sealed_fraction": 0.3,
    "twin_gap_flag_threshold": 0.10,
    "note": "the reserved held-out fraction no feedback surface may carry (ADR-0022 §5)",
}
EXP002_SANITY_ARM = {
    "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "parameter_count": 1_543_714_304,
    "pinning": "as the primary: revision commit, weights sha256, bf16, same vLLM version and hardware",
    "design": (
        "condition A re-run under the 1.5B at the same per-task device-second budget C. It is "
        "a compute-matching sanity check, not a treatment: a smaller model at the same budget "
        "must not beat the 7B by the primary effect size, or the matching is measuring size, "
        "not representation"
    ),
    "fallbacks": (
        "ADR-0023: becomes the primary if the pilot shows the 7B near ceiling under K0 alone, "
        "or if the run must fit a 24 GB local GPU"
    ),
}
STOPPING_FILL = (
    f"Fixed: {FILL} seeds per condition (from the power analysis), all conditions run to "
    "completion. No interim analysis, no data-dependent stopping. Aborted runs are recorded "
    "with their cause, never silently discarded."
)


def _condition(cid, role, description, *, controls=None, semantics=True, human=False,
               blind=None, genome=None):
    return {
        "condition_id": cid,
        "role": role,
        "controls_confound": controls,
        "genome_id": genome or f"G-{cid}",
        "description": description,
        "human_authored": human,
        "author_blind_to_genomes": blind,
        "introduces_new_semantics": semantics,
    }


def exp001_conditions() -> list[dict]:
    """The nine conditions of EXP-001-DR, unchanged: EXP-002 is EXP-001 with a model."""
    dry_run = json.loads((OUT_DIR / "EXP-001-DR.json").read_text())
    return list(dry_run["conditions"])


def exp_002() -> Preregistration:
    return Preregistration(
        experiment_id="EXP-002",
        primary_endpoint=(
            "verified_ood_solve_rate_at_fixed_device_seconds on held-out compositional families "
            "F9-F12 (pass@C with C in device-seconds on the pinned hardware under "
            "device-seconds-1.0.0, reported alongside the FLOP estimate under flops-1.0.0; "
            "generator plus verifier time matched across arms)"
        ),
        conditions=tuple(exp001_conditions()),
        seeds_per_condition=1,   # schema minimum; is_complete() still demands >= 2
        minimum_interesting_effect={
            "absolute_solve_rate_points": 0.05,
            "at": (
                "fixed compute (pass@C in device-seconds, FLOPs alongside), not fixed sample "
                "count (OSCA caveat, arXiv 2410.22480)"
            ),
            "compute_budget": EXP002_COMPUTE_BUDGET,
            "sealed_holdout": EXP002_SEALED_HOLDOUT,
            "compute_matching_sanity_arm": EXP002_SANITY_ARM,
            "reference_class": "condition G (human-expert DSL) retained as a ceiling; D/E must not be dwarfed by it (spec S3 gate)",
            "note": (
                "Same threshold as EXP-001-DR, retained rather than relaxed. What a null rules "
                "out: that the enumerative searcher's lack of prior was the sole reason "
                "abstractions could not help (roadmap §5 explanation B). A null with a model "
                "that has priors implicates the task family (C) or the extractor (D)."
            ),
        },
        multiple_comparison_control={
            "method": "benjamini_hochberg",
            "level": 0.05,
            "family": [
                "in_family_ood_rate", "adversarial_rate", "generation_tokens",
                "model_input_tokens", "language_description_length", "train_only_rate",
                "direct_reuse_rate", "twin_gap",
            ],
        },
        stopping_rule=STOPPING_FILL,
        declared_outcome_interpretations={
            "positive": (
                "primary effect >= +0.05 at fixed FLOPs, FDR-corrected, F/H/I all beaten, "
                "concentration test passed, direct-reuse rate materially > 0 -> escalate to "
                "EXP-004 (mechanism bake-off) and revisit M11 (adopt egg/egglog)"
            ),
            "efficiency_only": (
                "compression improved with capability inside the non-inferiority margin -> "
                "reported as an efficiency result, never as a capability result (H13)"
            ),
            "null_result": (
                "effect inside EXP-001-DR's interval with a model that has priors -> recorded "
                "in docs/research/negative_results/; roadmap §5 explanation B weakens and A, C, "
                "D come forward; EXP-003 (scaffolding) and EXP-004 (mechanism) become the "
                "discriminators"
            ),
            "h0_consistent": (
                "any of F, H, I matches or beats the treatment, or the concentration test fails "
                "with shortcut-shaped primitives, or the twin gap is flagged in a treatment arm "
                "-> recorded as consistent with H0 regardless of the aggregate effect size"
            ),
        },
        secondary_endpoints=(
            "in_family_ood_rate", "adversarial_rate", "generation_tokens", "model_input_tokens",
            "language_description_length", "train_only_rate", "direct_reuse_rate", "twin_gap",
        ),
        exploratory_endpoints=(
            "primitive_reuse", "cross_family_reuse", "hardcoding_incidents",
            "parse_failure_rate", "per_compute_curve", "canary_completion_probe",
        ),
        exclusion_criteria=COMMON_EXCLUSIONS,
        kernel_version=KERNEL_VERSION,
        model_identity=json.loads(json.dumps(EXP002_MODEL_IDENTITY)),
        evaluator_image_digest=f"{FILL}: the image digest the run executes under (ADR-0005)",
        analysis_code_revision=f"{FILL}: see run manifest code_revision",
        power_analysis=dict(POWER_FILL),
    )


def exp_003() -> Preregistration:
    conditions = [
        _condition("A", "reference", "K0 baseline language, default scaffolding", semantics=False),
        _condition("D", "treatment", "K0 + utility-selected abstractions, default scaffolding"),
        _condition("S0", "confound_control", "D under zero-shot scaffolding (no worked examples)",
                   controls="C3_scaffolding"),
        _condition("S1", "confound_control", "D under k-shot scaffolding (k = 3 worked examples)",
                   controls="C3_scaffolding"),
        _condition("S2", "confound_control",
                   "D under k-shot scaffolding plus AutoDoc-style natural-language primitive "
                   "descriptions (LILO)", controls="C3_scaffolding"),
        _condition("A0", "confound_control", "A under zero-shot scaffolding", controls="C3_scaffolding",
                   semantics=False),
        _condition("A1", "confound_control", "A under k-shot scaffolding", controls="C3_scaffolding",
                   semantics=False),
        _condition("A2", "confound_control", "A under k-shot plus descriptions",
                   controls="C3_scaffolding", semantics=False),
    ]
    return Preregistration(
        experiment_id="EXP-003",
        primary_endpoint=(
            "representation_main_effect_after_partialling_out_scaffolding: the share of the "
            "D-versus-A held-out solve-rate delta (at fixed FLOPs) attributable to the "
            "representation once scaffolding is entered as a factor (per-primitive causal "
            "mediation, spec §42)"
        ),
        conditions=tuple(conditions),
        seeds_per_condition=1,   # schema minimum; is_complete() still demands >= 2
        minimum_interesting_effect={
            "mediation_share_minimum": 0.5,
            "note": (
                "H14: the representation effect must survive after partialling out scaffolding. "
                "A null rules out that an observed representation gain is a scaffolding "
                "artefact - the DSPy critique that gains are prompt optimisation. F and I are "
                "held fixed; H is the manipulated variable."
            ),
        },
        multiple_comparison_control={
            "method": "benjamini_hochberg", "level": 0.05,
            "family": ["scaffolding_main_effect", "interaction_representation_x_scaffolding",
                       "generation_tokens", "twin_gap"],
        },
        stopping_rule=STOPPING_FILL,
        declared_outcome_interpretations={
            "positive": "mediation share >= 0.5 with the representation main effect FDR-corrected -> H14 supported; downstream claims are immune to the scaffolding critique",
            "efficiency_only": "not applicable: no compression arm in this design",
            "null_result": "mediation share < 0.5 -> any EXP-002 gain is re-described as scaffolding-sensitive; recorded in the negative-result ledger",
            "h0_consistent": "the scaffolding main effect matches or exceeds the representation effect -> consistent with H0 for H14",
        },
        secondary_endpoints=("scaffolding_main_effect", "interaction_representation_x_scaffolding",
                             "generation_tokens", "twin_gap"),
        exploratory_endpoints=("parse_failure_rate", "per_compute_curve"),
        exclusion_criteria=COMMON_EXCLUSIONS,
        kernel_version=KERNEL_VERSION,
        model_identity=dict(MODEL_IDENTITY_FILL),
        evaluator_image_digest=f"{FILL}: the image digest the run executes under (ADR-0005)",
        analysis_code_revision=f"{FILL}: see run manifest code_revision",
        power_analysis=dict(POWER_FILL),
    )


def exp_004() -> Preregistration:
    conditions = [
        _condition("A", "reference", "K0 baseline, no library", semantics=False),
        _condition("B", "lower_bound_control", "K0 + random macros, count/size matched to M1"),
        _condition("M1", "treatment",
                   "evolutionary search over BSLD descriptors scored by verified OOD solve rate at fixed compute"),
        _condition("M2", "treatment", "LLM-proposed primitives (REGAL/LILO-style)"),
        _condition("M3", "treatment",
                   "e-graph / equality-saturation-derived abstractions (babble/Stitch-style; adopt egg or egglog, M11)"),
        _condition("F", "confound_control", "compression-matched, no new semantics",
                   controls="C2_compression", semantics=False),
        _condition("H", "confound_control", "scaffolding-matched variant of the best mechanism arm",
                   controls="C3_scaffolding"),
        _condition("I", "confound_control",
                   "A plus all compute the best mechanism arm's discovery consumed, spent on sampling",
                   controls="C1_compute", semantics=False),
    ]
    return Preregistration(
        experiment_id="EXP-004",
        primary_endpoint=(
            "held_out_transfer_delta: verified OOD solve rate with the discovered library minus "
            "the matched no-library baseline, at fixed FLOPs, per mechanism arm"
        ),
        conditions=tuple(conditions),
        seeds_per_condition=1,   # schema minimum; is_complete() still demands >= 2
        minimum_interesting_effect={
            "transfer_delta_minimum": 0.05,
            "direct_reuse_rate_minimum": 0.05,
            "note": (
                "A mechanism wins only if BOTH hold: transfer delta >= +0.05 AND direct-reuse "
                "rate materially > 0 (pre-registered floor 0.05 of held-out solutions reusing a "
                "library item verbatim). The second condition exists because LLM-prompted "
                "libraries are single-use (TroVE 3/3,201; LEGO-Prover one reuse in ~20,000 "
                "lemmas, arXiv 2410.20274) and a single-use artefact is not a discovered "
                "abstraction."
            ),
        },
        multiple_comparison_control={
            "method": "benjamini_hochberg", "level": 0.05,
            "family": ["direct_reuse_rate", "cross_family_reuse", "library_description_length",
                       "adversarial_rate", "twin_gap"],
        },
        stopping_rule=STOPPING_FILL,
        declared_outcome_interpretations={
            "positive": "at least one mechanism arm meets both thresholds, FDR-corrected, F/H/I beaten, concentration test passed -> that mechanism's abstractions are transferable; explanation D (extractor bottleneck) is confirmed if only M3 wins",
            "efficiency_only": "a mechanism improves library description length without a transfer delta -> reported as compression, never as discovery",
            "null_result": "no arm meets both thresholds -> the discovery loop produces single-use abstractions; the most damaging and most informative outcome, recorded with the search-space constraint it implies",
            "h0_consistent": "any of F, H, I matches or beats every mechanism arm -> consistent with H0",
        },
        secondary_endpoints=("direct_reuse_rate", "cross_family_reuse", "library_description_length",
                             "adversarial_rate", "twin_gap"),
        exploratory_endpoints=("primitive_reuse", "per_compute_curve", "egraph_saturation_cost"),
        exclusion_criteria=COMMON_EXCLUSIONS,
        kernel_version=KERNEL_VERSION,
        model_identity=dict(MODEL_IDENTITY_FILL),
        evaluator_image_digest=f"{FILL}: the image digest the run executes under (ADR-0005)",
        analysis_code_revision=f"{FILL}: see run manifest code_revision",
        power_analysis=dict(POWER_FILL),
    )


def exp_005() -> Preregistration:
    conditions = [
        _condition("A", "reference", "K0 baseline, sexpr projection, verifier loop fixed", semantics=False),
        _condition("R1", "confound_control", "identical semantics, compact projection (compression ratio ~1.6)",
                   controls="C2_compression", semantics=False),
        _condition("R2", "confound_control",
                   "identical semantics, a further-shortened projection (compression ratio target ~2.2)",
                   controls="C2_compression", semantics=False),
        _condition("R3", "confound_control",
                   "identical semantics, a deliberately verbose projection (compression ratio ~0.7)",
                   controls="C2_compression", semantics=False),
    ]
    return Preregistration(
        experiment_id="EXP-005",
        primary_endpoint=(
            "correlation between compression_ratio and verified_ood_solve_rate at fixed FLOPs "
            "across projection arms with identical semantics and a fixed verifier loop"
        ),
        conditions=tuple(conditions),
        seeds_per_condition=1,   # schema minimum; is_complete() still demands >= 2
        minimum_interesting_effect={
            "expected_correlation_r": 0.0,
            "h13_confirmed_if_abs_r_at_most": 0.1,
            "h13_refuted_if": "positive r whose 95% CI excludes 0",
            "note": (
                "H13 (compression is not capability), designed on the vericoding template: "
                "natural-language descriptions add nothing, the loop adds everything. Hold the "
                "K0 verifier loop fixed, vary only compressibility."
            ),
        },
        multiple_comparison_control={
            "method": "benjamini_hochberg", "level": 0.05,
            "family": ["generation_tokens", "parse_failure_rate", "twin_gap"],
        },
        stopping_rule=STOPPING_FILL,
        declared_outcome_interpretations={
            "positive": "|r| <= 0.1 with CI including 0 -> H13 supported: compression and capability decouple",
            "efficiency_only": "token savings reported per arm as efficiency, by construction never as capability",
            "null_result": "not applicable: a flat correlation is the confirmatory outcome here",
            "h0_consistent": "positive r with CI excluding 0 -> H13 refuted; compression must be treated as a candidate capability lever in later designs",
        },
        secondary_endpoints=("generation_tokens", "parse_failure_rate", "twin_gap"),
        exploratory_endpoints=("per_compute_curve",),
        exclusion_criteria=COMMON_EXCLUSIONS,
        kernel_version=KERNEL_VERSION,
        model_identity=dict(MODEL_IDENTITY_FILL),
        evaluator_image_digest=f"{FILL}: the image digest the run executes under (ADR-0005)",
        analysis_code_revision=f"{FILL}: see run manifest code_revision",
        power_analysis=dict(POWER_FILL),
    )


DRAFTS = {"EXP-002": exp_002, "EXP-003": exp_003, "EXP-004": exp_004, "EXP-005": exp_005}

QUESTIONS = {
    "EXP-002": "Does replacing the enumerative synthesizer with a fixed-weights language model change the sign or magnitude of the representation effect on held-out solve rate at fixed compute? (H2, the unblocking experiment; roadmap §3; model, endpoint and currency per ADR-0023)",
    "EXP-003": "Is the representation effect invariant to prompt and few-shot scaffolding? (H14; roadmap §3)",
    "EXP-004": "Do discovery mechanisms yield abstractions with different held-out transfer, and do equality-saturation-derived abstractions transfer at least as well as LLM-proposed ones at matched compute? (roadmap §3)",
    "EXP-005": "Does a more compressive representation raise capability once verifier feedback is held constant? (H13; roadmap §3)",
}
ORDER_NOTE = (
    "Ordering by information value per dollar (roadmap §3): EXP-002 unblocks every model "
    "hypothesis at once; EXP-003 protects every subsequent claim from the scaffolding confound; "
    "EXP-004 tests the discovery thesis and is where a null is most decisive; EXP-005 is a "
    "refinement."
)


def _render_items(mapping: dict, indent: int = 0) -> str:
    """Bulleted rendering of a possibly nested mapping (the budget, the holdout, the sanity arm)."""
    lines = []
    pad = "  " * indent
    for key, value in mapping.items():
        if isinstance(value, dict):
            lines.append(f"{pad}- **{key}:**")
            lines.append(_render_items(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{pad}- **{key}:** " + "; ".join(str(v) for v in value))
        else:
            lines.append(f"{pad}- **{key}:** {value}")
    return "\n".join(lines)


def render_markdown(prereg: Preregistration) -> str:
    rows = "\n".join(
        f"| {c['condition_id']} | {c['role']} | {c.get('controls_confound') or '—'} | {c['description']} |"
        for c in prereg.conditions
    )
    mie = _render_items(prereg.minimum_interesting_effect)
    outcomes = "\n".join(
        f"- **{k}:** {v}" for k, v in prereg.declared_outcome_interpretations.items()
    )
    exclusions = "\n".join(f"- {e}" for e in prereg.exclusion_criteria)
    complete, missing = prereg.is_complete()
    blockers = "\n".join(f"- `{m}`" for m in missing)
    return f"""# {prereg.experiment_id} — Pre-Registration **DRAFT**

**Status:** DRAFT — not committed. No hash, no timestamp. `Preregistration.is_complete()`
reports what is missing (below), and `ReportGate` refuses confirmatory certification against
this document. It becomes a pre-registration only when the placeholders are filled and
`Preregistration.commit()` is run **before the first evaluation run** (spec §26.5), after which
it is append-only.

Generated by `scripts/draft_preregistration.py`; do not edit by hand — edit the script, regenerate,
and let `tests/stats/test_preregistration_drafts.py` confirm the files match. The design follows
`docs/research/2026-09-18-roadmap-agentic-first-thesis.md` §3 as adjudicated in ADR-0022.

| Field | Value |
|---|---|
| Experiment ID | `{prereg.experiment_id}` |
| Pre-registration hash (SHA-256) | `<<FILL: on commit>>` |
| Timestamp (UTC) | `<<FILL: on commit>>` |
| Kernel version | `{prereg.kernel_version}` |
| Model identity | `{prereg.model_identity['model_id']}` (`{prereg.model_identity['kind']}`, `{prereg.model_identity['mode']}`), hash `{prereg.model_identity['model_identity_hash']}` |
| Evaluator image digest | `{prereg.evaluator_image_digest}` |
| Analysis code revision | `{prereg.analysis_code_revision}` |

## Research question

{QUESTIONS[prereg.experiment_id]}

{ORDER_NOTE}

## Conditions

| ID | Role | Controls | Description |
|---|---|---|---|
{rows}

Model weights identical across all conditions (spec §17.2). Compute matched in
**device-seconds on the pinned hardware** (`device-seconds-1.0.0`, rates pilot-measured; ADR-0023)
with the FLOP estimate under `flops-1.0.0` reported alongside (`src/bestsad/conditions/flops.py`),
as solve rate at fixed C, never by sample count.

## Endpoints

**Primary (exactly one):** `{prereg.primary_endpoint}`

**Secondary family** (Benjamini–Hochberg FDR at q = {prereg.multiple_comparison_control['level']}), declared here and not chosen afterwards:
{', '.join(prereg.secondary_endpoints)}.

**Exploratory** (no inferential claims): {', '.join(prereg.exploratory_endpoints)}.

## Minimum interesting effect

{mie}

## Sample size and power

`<<FILL>>` — from an E0 variance measured **under the model** (`Exp001Runner.stage_s1` with the
model spec), never assumed and never carried over from the enumerative dry run. If the
achievable seed count cannot power the minimum interesting effect, record that and re-scope; do
not run underpowered and interpret the point estimate (spec §26.8).

## Analysis plan

1. Per-seed primary endpoint for every condition; per-seed values published.
2. Median, mean, bootstrap CIs, all seeded.
3. Primary test at matched FLOPs; per-compute curves (pass@C), not single points.
4. **Control gates before any claim:** the treatment must beat every confound control present
   (F, H, I where run). Failing any one means no capability claim.
5. Reference class G reported alongside, where run.
6. Secondary family with BH-FDR.
7. Per-primitive causal mediation with the concentration stop rule (80% / fewer than two
   primitives), and the direct-reuse rate reported wherever a library is involved.
8. Twin-gap probe (feedback tier minus sealed tier) reported per condition under C4; a flagged
   gap in a treatment arm is an H0-consistent outcome by declaration.
9. Transcript leak check on every recorded transcript before replay; a fatal finding aborts.

## Stopping rule

{prereg.stopping_rule}

## Exclusion criteria

{exclusions}

## Declared outcome interpretations

{outcomes}

## Residual confound disclosure

To be completed post-run for C1 (compute, in FLOPs), C2 (compression), C3 (scaffolding, with the
delivered budget per condition) and C4 (contamination: sealed tier, twin gap, canary-completion
probe, transcript leak check). Standing residuals: ADR-0005 (boundary), ADR-0022 (proposal stage
unisolated for a networked model; declared FLOP constants; hosted-model non-determinism).

## What blocks committing this draft

{blockers}
"""


def render_all() -> dict[str, str]:
    out: dict[str, str] = {}
    for experiment_id, build in DRAFTS.items():
        prereg = build()
        out[f"{experiment_id}.draft.json"] = json.dumps(prereg.to_record(), indent=2, sort_keys=True) + "\n"
        out[f"{experiment_id}.draft.md"] = render_markdown(prereg)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the files on disk match")
    args = parser.parse_args()
    rendered = render_all()
    if args.check:
        drifted = [n for n, text in rendered.items()
                   if not (OUT_DIR / n).exists() or (OUT_DIR / n).read_text() != text]
        if drifted:
            print("drafts drifted from the script: " + ", ".join(drifted), file=sys.stderr)
            return 1
        print(f"{len(rendered)} draft files match the script")
        return 0
    for name, text in rendered.items():
        (OUT_DIR / name).write_text(text)
        print(f"wrote {OUT_DIR / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
