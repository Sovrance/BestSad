"""Report assembly for EXP-001 (spec §26, §40.3, §44, §45).

The analysis produces evidence; `ReportGate` decides what may be said about it; this module
writes down both, including the refusal when there is one. A refused claim is not an error state
to be worked around — it is the finding, and it is recorded as such.

Two things this module always emits, whatever the outcome:

* the **residual confound disclosure** (spec §40.3) — undisclosed residuals are a protocol
  violation, so they are part of the report template rather than an optional appendix;
* a **negative-result record** (spec §44) whenever the outcome is null or H0-consistent,
  carrying the search-space constraint the result implies. Gate G6 is not satisfied if the
  ledger is empty after a stage completes with null findings.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

from ..causal import AttributionTable
from ..conditions import REQUIRED_CONTROLS
from ..stats import Preregistration, mean, median
from .analysis import Analysis


def residual_disclosure(
    *,
    scaffolding: Sequence[dict],
    reconciliations: Sequence[dict],
    analysis: Analysis,
) -> dict:
    """Quantify each confound's residual (spec §40.3)."""
    worst_scaffold = max(
        (abs(r["value"]) for entry in scaffolding for r in entry["residuals"].values()),
        default=0.0,
    )
    worst_compute = max((r["relative_residual"] for r in reconciliations), default=0.0)
    all_reconciled = all(r["reconciled"] for r in reconciliations) if reconciliations else False

    compression = {
        tid: outcome.get("compression_ratio") for tid, outcome in analysis.paired_outcomes.items()
    }
    return {
        "C1_compute": {
            "control": "condition I",
            "residual": f"compute reconciliation within {worst_compute:.1%} of the expected "
                        f"identity compute(I) == compute(A) + compute(evolution in D)",
            "reconciled": all_reconciled,
        },
        "C2_compression": {
            "control": "condition F",
            "residual": "condition F carries a primitive set identical to A's under semantic "
                        "hash, so it introduces no new semantics; measured compression ratios "
                        f"per treatment: {compression}",
        },
        "C3_scaffolding": {
            "control": "condition H",
            "residual": f"scaffolding equalized to within {worst_scaffold:.0f} tokens of the "
                        "common target; delivered budget logged per condition, not assumed",
        },
        "C4_contamination": {
            "control": "frozen hidden benchmark, procedurally generated instances with fresh "
                       "seeds, structural family holdouts, canary strings",
            "residual": "abstractions are mined only from curriculum solutions (F1-F8); "
                        "held-out families F9-F12 are structurally disjoint, not merely unseen "
                        "seeds. Tasks do not exist until a seed generates them.",
        },
        "standing_residuals": [
            "ADR-0005: the candidate sandbox is an in-process audit hook, not a kernel sandbox, "
            "and hidden_evaluator/ shares a checkout. No result above Claim Level 1 until the "
            "evaluator is containerised and the assets relocated.",
            "ADR-0006: condition C's MDL extractor ranks candidates independently rather than "
            "searching for a jointly optimal library, and counts nodes rather than bits. This "
            "makes the control weaker than it should be, biasing toward the treatment.",
            "ADR-0007: the model role is a deterministic enumerative synthesizer, so "
            "compression_ratio uses a surface-token proxy and conditions F and H cannot be "
            "interpreted even though they can be constructed.",
            "The synthesizer cannot capture outer variables in closures, lowering the ceiling "
            "equally in every condition.",
        ],
    }


def build_report(
    *,
    run_id: str,
    analysis: Analysis,
    certification: Mapping,
    preregistration: Preregistration | None,
    s2_payload: Mapping,
    s3_payload: Mapping | None,
    attribution: AttributionTable | None,
    stability: Mapping | None,
    e0: Mapping,
) -> dict:
    report = {
        "run_id": run_id,
        "experiment_id": "EXP-001-DR",
        "claim_level": certification.get("claim_level", "E"),
        "certified": certification.get("certified", False),
        "certification": dict(certification),
        "preregistration_hash": (
            preregistration.preregistration_hash if preregistration else None
        ),
        "e0_variance_measurement": dict(e0),
        "analysis": analysis.to_record(),
        "residual_confounds": residual_disclosure(
            scaffolding=s2_payload.get("scaffolding", []),
            reconciliations=s2_payload.get("compute_reconciliation", []),
            analysis=analysis,
        ),
        "per_seed_published": {
            cid: summary.verified_ood_per_seed
            for cid, summary in analysis.summaries.items()
        },
        "cross_seed_abstraction_stability": dict(stability) if stability else None,
        "causal_attribution": attribution.to_record() if attribution else None,
        "prohibited_claims_reminder": (
            "Spec §45 applies in full. In particular this run may not be described as evidence "
            "that evolved machine-native languages improve generalized computational "
            "capability, nor as evidence about any language model."
        ),
    }
    return report


NEGATIVE_TEMPLATE = """# Negative result: {experiment_id} ({run_id})

**Recorded:** {timestamp}
**Outcome class:** `{outcome_class}`
**Claim level:** {claim_level}
**Pre-registration hash:** `{prereg_hash}`

Spec §44 makes this record a deliverable, not a courtesy. Gate G6 is not satisfied if the
negative-result ledger is empty after a stage completes with null findings.

## Hypothesis under test

{hypothesis}

## Conditions run

{conditions}

Seeds per condition: **{seeds}**. Per-seed values are published in the run report rather than
summarised away.

## Result

{result_summary}

## Confound controls satisfied

{controls}

## Why this is not a failure of the instrument

{instrument_note}

## Search-space constraint this implies

{constraint}

## What would change the answer

{next_steps}
"""


def write_negative_result(
    path: Path,
    *,
    run_id: str,
    experiment_id: str,
    outcome_class: str,
    claim_level: str,
    prereg_hash: str | None,
    hypothesis: str,
    conditions: Sequence[str],
    seeds: int,
    result_summary: str,
    controls: str,
    instrument_note: str,
    constraint: str,
    next_steps: str,
    timestamp: str,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        NEGATIVE_TEMPLATE.format(
            experiment_id=experiment_id,
            run_id=run_id,
            timestamp=timestamp,
            outcome_class=outcome_class,
            claim_level=claim_level,
            prereg_hash=prereg_hash or "none",
            hypothesis=hypothesis,
            conditions=", ".join(conditions),
            seeds=seeds,
            result_summary=result_summary,
            controls=controls,
            instrument_note=instrument_note,
            constraint=constraint,
            next_steps=next_steps,
        )
    )
    return path
