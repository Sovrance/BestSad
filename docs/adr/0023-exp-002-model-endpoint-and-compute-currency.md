# ADR 0023 — EXP-002 runs a pinned, self-hosted `Qwen2.5-Coder-7B-Instruct`; the model server sits on the candidate side of the boundary; device-seconds on the pinned hardware is the compute currency

**Status:** Accepted (2026-09-18, the owner's call; the acceptance tests under
`tests/integrity/test_model_boundary.py` ("the model server, on the candidate side"),
`tests/conditions/test_flops.py` (device-seconds) and `tests/experiments/test_exp002_pilot.py`
passing; the owner's merge into `v1` is the acceptance)
**Date:** 2026-09-18
**Governs:** the `model_identity` of `docs/preregistrations/EXP-002.draft.*`, the pinning
fields of `ModelIdentity`, `OutboundGuard` and the identifier check in
`src/bestsad/evaluator/holdout.py`, `DeviceSecondsPolicy` in `src/bestsad/conditions/flops.py`,
`scripts/exp002_pilot.py`, and BEST-EXP2-08 and its successors in
`docs/architecture/EXP002_READINESS_WORK_ORDERS.md`
**Relates to:** ADR-0005 (the candidate boundary and its residual), ADR-0007 (what the
enumerative stand-in does not license), ADR-0022 (the model role, FLOP matching, the hardened
evaluator, the drafts this ADR fills in)
**Source:** the owner's decision of 2026-09-18, recorded here in full

## Context

ADR-0022 left three things to the owner: which model fills the model role for EXP-002, where it
runs, and how much compute the experiment gets. Each has consequences the instrument must carry
before the first sample is drawn, and each is a decision that could have gone otherwise, so the
call and its reasons are recorded here rather than left in a chat log.

## Decision

### 1. The model: `Qwen/Qwen2.5-Coder-7B-Instruct`, bf16, unquantized, pinned

The primary model is `Qwen/Qwen2.5-Coder-7B-Instruct` served in bfloat16 without quantization,
**pinned to a specific Hugging Face revision commit and to a SHA-256 over the weight shards
actually loaded**, both recorded in the pre-registration's `model_identity` and therefore in the
identity hash the ledger cites. A secondary arm for compute-matching sanity is
`Qwen/Qwen2.5-Coder-1.5B-Instruct`, pinned the same way and run under condition A at the same
budget; it is not a treatment.

Why not a 2026 frontier open model: EXP-002 needs a **well-characterised fixed prior**, not
capability. A dense 7B has unambiguous FLOPs per token, which pass@C at fixed compute depends
on; the current top self-hosted coder is a mixture-of-experts (80B total, 3B active), which makes
FLOP accounting arguable. Qwen2.5-Coder is Apache-2.0, extensively benchmarked, and its training
cutoff predates this repository entirely — irrelevant for contamination, since the benchmark is
procedurally generated and the canary has never been published, but it removes an objection at
no cost. The objection this choice invites is "an old model cannot tell you about frontier
agents." Correct, and it is the point: H2 asks whether representation moves a *fixed* model at
all. If EXP-002 nulls on a 7B, running it on a frontier model is a separate lineage, not a retry.

The parameter counts the FLOP policy uses are the totals from the model configurations at the
pinned revisions and are verified against the loaded weights at pin time:

| Model | Parameters (total) | Derivation |
|---|---|---|
| `Qwen2.5-Coder-7B-Instruct` | 7,615,616,512 | 28 layers × 233,057,792 (hidden 3584, intermediate 18944, 28 query / 4 key-value heads of 128, q/k/v biases, two norms) + untied embedding and output matrices 2 × 152,064 × 3584 + final norm |
| `Qwen2.5-Coder-1.5B-Instruct` | 1,543,714,304 | 28 layers × 46,797,824 (hidden 1536, intermediate 8960, 12 / 2 heads) + one tied embedding matrix 151,936 × 1536 + final norm |

`flops-1.0.0` charges 2 FLOPs per parameter per token on the total; that over-counts the input
embedding lookup (about 7% for the 7B) and is disclosed as such. The count that matters for the
decision is the *dense* one: every token costs the same, which is what makes pass@C well defined.

`ModelIdentity` gains the pinning fields this needs — `revision`, `dtype`, `quantization` and
a `serving` record (engine, version, hardware, named nondeterminism sources) — all part of the
hash, because a different kernel library on different silicon is a different set of numerics
even when the weights file is the same. `ModelIdentity.is_pinned()` names what is missing, and
the pre-registration is not committable until it names nothing.

### 2. The endpoint: self-hosted vLLM on one pinned H100-class device, no vendor API

The model is served by a **pinned vLLM version behind its OpenAI-compatible API on one
H100-class VM (Azure NC-H100 or equivalent)**, with the sampling parameters pinned in the
identity. A hosted API model is a K0 that someone else can silently change — it breaks lineage
exactly the way editing K0 would — so no vendor API fills the model role.

**The endpoint lives on the candidate side of the trust boundary.** It is a process this
repository does not control, so it is treated as a candidate is: it may receive the grammar
description and a task's *visible* examples, and nothing else. Concretely:

- The replay stage runs behind `run_isolated` as before; the proposal pass runs in the parent
  because the sandbox denies the network (ADR-0022), and is the one unisolated stage the
  isolation record names.
- `OutboundGuard` now sits between the adapter and the wire in that pass. It runs the
  transcript leak check on every prompt **before** it is sent and raises `IntegrityViolation`
  with the prompt unsent if the prompt carries a sealed input, the canary, a hidden-asset path,
  or — new in this ADR — a benchmark **task identifier**. An identifier is the join key to the
  frozen benchmark; a server that has been told `F9-4009719e2c1c` has been told more than the
  visible examples say. The adapter's prompts never carry one, so an identifier on a
  model-visible surface is always a construction error or an exfiltration attempt.
- Gate G1 gains the vector: the runner's proposal pass is driven against a server that records
  every request, and the test audits what crossed — the request path, the payload's field set,
  the absence of every identifier and sealed input, the absence of the API key from the body
  (`tests/integrity/test_model_boundary.py`). The pre-existing vector — a networked backend is
  denied inside the sandbox — stands.

**vLLM batching is not bit-reproducible.** It is recorded in the identity's `serving` record as
the named source of nondeterminism. Transcripts are recorded once and replayed; the analysis
compares **verdicts, never logits**; and a report must say whether its transcripts were recorded
once or re-proposed (ADR-0022's residual, unchanged).

### 3. The compute budget: device-seconds on the pinned hardware, set from a pilot

**C is pre-registered in device-seconds on the declared hardware, reported alongside a FLOP
estimate** — and the number is set from a pilot, not from a planning figure.

The planning figure, for orientation only: nine conditions × 32 seeds × ~96 tasks × 32 samples
at ~1.7k tokens per sample is ≈ 9 × 10⁵ samples and ≈ 1.5 × 10⁹ tokens; at ~1.5 × 10¹⁰ FLOPs
per token that is ≈ 2 × 10¹⁹ FLOPs, on the order of one to three H100-days with prefix caching
and low hundreds of dollars at cloud rates. (The owner's note put the sample count at ≈ 4 × 10⁵;
the arithmetic above is the one this ADR records, and the order of magnitude is the same.)

The procedure is the one the instrument already has (spec §26.8, §43 S1): **run a two-seed E0
pilot under the model** (`scripts/exp002_pilot.py`), measure tokens per sample and the
across-seed variance of the solve rate, and let the power analysis fix the seed count and the
samples per task. The pilot also measures the rates that make device-seconds a currency —
seconds per input token and per output token from a least-squares fit over the recorded
exchange latencies, seconds per kernel step and per search node from timed runs of K0 and the
enumerator on the same host — and writes a calibrated `DeviceSecondsPolicy` (`device-seconds-
1.0.0`) whose record travels with every result. An uncalibrated policy refuses to convert;
nothing is estimated.

**The one conversion that cannot be dodged is condition I's.** Its inherited discovery compute
is metered in kernel steps, search nodes and — for a model arm — tokens; there is no principled
FLOP equivalence between an enumerator step and a decoded token. This ADR declares
device-seconds on the same pinned hardware as the common currency and **records the conversion
as a pre-registered assumption**: the identity `compute(I) == compute(A) + compute(evolution)`
is reported in device-seconds, in FLOPs and in nodes side by side, and the pilot-measured rates
that produced the device-second form are in the pre-registration.

### 4. Before the first run

`docs/preregistrations/EXP-002.draft.*` now carries the model identity above with `<<FILL>>` for
exactly the values that need the weights on disk or the pilot: the revision commit, the weights
digest, the vLLM version, the hardware string, the identity hash, the per-task budget C, the
seed count, and the power analysis. The +0.05 held-out threshold at fixed compute, the reserved
30% sealed tier (`holdout-1.0.0`) with its 0.10 twin-gap flag, the sampling parameters, the
named nondeterminism source and the condition-I conversion assumption are fixed in the draft.
Filling the placeholders, committing (`Preregistration.commit()`) and hashing happen after the
pilot and **before the first S2 job**; the report gate refuses anything else, which is correct.

## What would change this call

- A 24 GB local GPU and zero cloud spend: run the 1.5B as primary and accept a weaker prior.
- The pilot shows the 7B solving the curriculum near ceiling under K0 alone: drop to the 1.5B,
  because a saturating model reproduces the C1 problem EXP-001-DR already hit with the
  enumerator. `scripts/exp002_pilot.py` reports this check explicitly.

## Consequences and disclosed residuals

- **The token-time rates are fitted, not measured per token.** A two-parameter fit over exchange
  latencies attributes per-request overhead to the token rates; the pilot record carries the fit
  residual. Rates from one machine are not the currency on another, and the policy record names
  the machine.
- **Spend-at-solve in device-seconds scales the attempt's token time by the share of tokens up
  to the solving sample**, because the input/output split is not recorded per sample. The FLOP
  figure has the same property.
- **The parameter counts are derived from the published configurations** and are verified
  against the loaded weights at pin time; a mismatch is a pinning failure, not a rounding.
- **The identity hash of the enumerative stand-in changed** with the new fields. No committed
  artifact cites it; EXP-001-DR's pre-registration names the model by id.

## Revisit triggers

- The weights are pinned and the pilot has run: fill and commit `EXP-002`, then start S2.
- The pilot's ceiling check fires: switch the primary to the 1.5B and re-pilot.
- A vendor API becomes necessary for any reason: this ADR is superseded, and the lineage break
  is stated in the superseding ADR.
