# EXP-002 readiness — work-order status

Tracks the roadmap `docs/research/2026-09-18-roadmap-agentic-first-thesis.md` (its
recommendations §1–§6) against what is built, as adjudicated in ADR-0022, and the owner's
decision on the model, the endpoint and the compute currency, recorded in ADR-0023.
Last updated: 2026-09-18 (ADR-0023).

The roadmap's one-line verdict: BestSad's highest-value next move is not to build an
"agentic-first" language; it is to put a real fixed-weights language model in the model role and
re-run the discovery loop under the existing F/H/I controls, hardening the evaluator first. Every
work order below serves that, and none of them is a run.

| WO | Pri | Deliverable | Gate | State |
|---|---|---|---|---|
| BEST-EXP2-01 | P0 | ADR-0022: "agentic-first" fixed as the §2 property table; the §7 standing instructions added to the claims register; M12/M14 stay deferred | ADR accepted; the roadmap saved verbatim | **Done** — `docs/adr/0022-agentic-first-is-a-property-table-exp-002-next.md`; `docs/research/2026-09-18-roadmap-agentic-first-thesis.md` |
| BEST-EXP2-02 | P0 | Model role behind one interface: hashed `ModelIdentity` (spec §17.1 fields plus weights digest and parameter count), `ModelAdapter` protocol, `EnumerativeAdapter` | The wrapped enumerator returns exactly what the synthesizer returns; a checkpoint key distinguishes models | **Done** — `src/bestsad/models/{identity,adapter}.py`; `tests/models/test_adapter.py`; `tests/experiments/test_model_role.py::test_checkpoint_key_distinguishes_models` |
| BEST-EXP2-03 | P0 | `LLMAdapter`: a fixed-weights model as a proposer over the genome's projection, scaffolding delivered, visible-example repair loop, real token counts; `Scripted`/`HTTP`/`Recording`/`Replay` backends over a content-hashed `Transcript` | A correct proposal is accepted; feedback carries only visible examples; a recorded transcript replays to an identical result; a replay never substitutes; a networked backend is denied inside the sandbox | **Done** — `src/bestsad/models/llm.py`; `tests/models/test_llm_adapter.py` (incl. an OpenAI-compatible server round trip); `tests/integrity/test_model_boundary.py::test_a_network_backend_is_denied_inside_the_candidate_sandbox` |
| BEST-EXP2-04 | P0 | Compute matching in FLOPs: policy `flops-1.0.0`, per-task `TaskAttempt`, pass@C at fixed FLOPs, `matched_flops`; condition I funded in samples for a model arm; FLOP-denominated condition-I reconciliation in the S2 payload | The identity `compute(I) == compute(A) + compute(evolution)` reported in FLOPs next to nodes; pass@C counts only tasks solved within the budget | **Done** — `src/bestsad/conditions/flops.py`; `Condition.sample_bonus`; `tests/conditions/test_flops.py`; `tests/experiments/test_model_role.py::test_stage_s2_delivers_scaffolding_and_funds_condition_i_in_samples` |
| BEST-EXP2-05 | P0 | Evaluator hardening before the first sample: sealed 30% tier, transcript leak check, twin-gap probe (flag at 0.10), canary-completion probe; correctness unchanged | Every vector attempted and caught (Gate G1 extended) | **Done** — `src/bestsad/evaluator/holdout.py`; `TaskScore`/`ScoreReport` tier fields; `tests/integrity/test_model_boundary.py` |
| BEST-EXP2-06 | P0 | `Exp001Runner(model_spec=...)`: adapter built per condition, scaffolding delivered through `Condition.scaffolding`, matcher describes the model's retry/decoding policy, discovery metered in samples and tokens, proposal pass outside the boundary with replay inside, isolation record names `model_proposal` | A scripted model is scored through the same path as the enumerator; records reproducible by digest; a hosted model's transcript is recorded once and replayed; every EXP-001-DR pipeline test unchanged | **Done** — `src/bestsad/experiments/exp001.py`; `tests/experiments/test_model_role.py`; `tests/experiments/test_exp001_pipeline.py` (unchanged, passing) |
| BEST-EXP2-07 | P1 | Pre-registration drafts for EXP-002, EXP-003, EXP-004, EXP-005 with the roadmap's thresholds fixed and `<<FILL>>` for what needs a model | Drafts incomplete for exactly the declared reasons; the gate refuses them; files match the generator | **Done** — `scripts/draft_preregistration.py`; `docs/preregistrations/EXP-00{2,3,4,5}.draft.{json,md}`; `tests/stats/test_preregistration_drafts.py` |
| BEST-EXP2-08 | P1 | **Run EXP-002.** Fill and commit `EXP-002`; run S2/S3 with transcripts recorded; analyse at fixed device-seconds with FLOPs alongside | Pre-registration committed before the first evaluation run; every job green; residuals disclosed | **Decided, not started.** ADR-0023 chose the model (`Qwen/Qwen2.5-Coder-7B-Instruct`, bf16, pinned; 1.5B sanity arm), the endpoint (self-hosted vLLM on one H100-class device, on the candidate side of the boundary) and the currency (device-seconds on that hardware, C set by the pilot). Blocked on BEST-EXP2-11 and BEST-EXP2-14, which need the weights and the machine |
| BEST-EXP2-09 | P2 | M11: adopt egg or egglog for EXP-004's e-graph arm (never build) | EXP-002 positive, or EXP-004 authorised | **Deferred** — behind EXP-002 |
| BEST-EXP2-10 | P2 | Measured FLOP calibration replacing the declared CPU-side constants; policy id bumped | Constants measured on the run's hardware and recorded in the ledger | **Folded into BEST-EXP2-14** — the pilot measures the CPU-side rates in seconds; the FLOP constants stay declared and the FLOP figure is reported alongside, never instead (ADR-0023 §3) |
| BEST-EXP2-11 | P0 | **Pin the model** (ADR-0023 §1): fetch `Qwen/Qwen2.5-Coder-7B-Instruct` and `-1.5B-Instruct` at a named revision commit; SHA-256 over the loaded shards; verify the parameter counts against the loaded weights; fill `revision`, `weights_digest`, `serving.version`, `serving.hardware`; the identity hash | `ModelIdentity.is_pinned()` returns `(True, [])` for both; the hash is in the spec and the draft | **Not started — needs the weights on disk.** `ModelIdentity` carries the fields (`revision`, `dtype`, `quantization`, `serving`) and `is_pinned()` names what is missing; `tests/models/test_adapter.py` |
| BEST-EXP2-12 | P0 | **The endpoint on the candidate side** (ADR-0023 §2): `OutboundGuard` leak-checks every prompt before it is sent; task identifiers and hidden-asset paths are fatal findings; G1 gains the vector that drives the proposal pass against a recording server and audits what crossed | Every vector attempted and caught; the transcript names the guard | **Done** — `src/bestsad/evaluator/holdout.py`; `Exp001Runner._live_backend`; `tests/integrity/test_model_boundary.py` ("the model server, on the candidate side") |
| BEST-EXP2-13 | P0 | **Device-seconds as the currency** (ADR-0023 §3): `DeviceSecondsPolicy` (`device-seconds-1.0.0`) with pilot-measured rates or a refusal; per-task device-seconds on `TaskAttempt`; pass@C in device-seconds; the S2 payload carries the policy record | An uncalibrated policy converts nothing; an enumerator and a model are priced in one unit | **Done** — `src/bestsad/conditions/flops.py`; `Exp001Runner(compute_currency=...)`; `tests/conditions/test_flops.py` |
| BEST-EXP2-14 | P0 | **The E0 pilot** (ADR-0023 §3): two seeds under the pinned model on the pinned hardware; variance and power; tokens per sample; the token-rate fit and the CPU-side rates; the ceiling check; the `preregistration_fill` block | Report written; C and the seed count read from it, not from the planning estimate | **Script done, run not made** — `scripts/exp002_pilot.py`; `tests/experiments/test_exp002_pilot.py`. The run needs the machine |

## What is built, in one paragraph

The instrument can now *take* a fixed-weights language model. `bestsad.models` puts the model
role behind one interface: the enumerative stand-in of ADR-0007 and a language-model adapter
both return the synthesizer's `SearchResult`, both carry a hashed `ModelIdentity` cited by the
ledger, and `Exp001Runner` builds whichever a JSON spec names. A model that needs the network is
proposed outside the candidate boundary into a content-hashed, leak-checked transcript and
replayed inside it, so the run record says exactly which stage was unisolated. Model arms are
metered in FLOPs (`flops-1.0.0`), reported as pass@C at a fixed budget, and condition I is
funded in samples. The evaluator seals 30% of every task's hidden inputs from any feedback
surface, checks every transcript for the canary and sealed inputs, and reports a twin gap per
condition. Four pre-registrations are drafted with the roadmap's thresholds fixed and everything
that needs a model left as `<<FILL>>`.

## What is not built, and why

- **No run.** Nothing here is evidence about any model; ADR-0007's claim limitation stands
  until EXP-002's pre-registration is committed and the run is done (ADR-0022, "What this ADR
  does not license"). The model, endpoint and currency are decided (ADR-0023); the weights are
  not pinned and the pilot has not run, because both need the machine.
- **No "agentic-first language."** The roadmap's adjudication is that the phrase is a marketing
  frame; the target stays spec §2.1, and the property table in ADR-0022 §1 is the only sense in
  which the phrase is admitted.
- **No M11, M12, M14.** M11 waits for EXP-004; M12 and M14 wait for a demonstrated
  model-in-the-loop representation effect, per roadmap §4 and §7.
- **No file-edit or scorer-integrity detector.** The model's tool interface is `none`: it emits
  text a projection parses, and there is no file it can edit. ADR-0022 §3 makes those detectors
  a precondition for any adapter with a different tool interface.

## How to start BEST-EXP2-08

The order is fixed by what each step needs (ADR-0023 §4):

```
# 1. BEST-EXP2-11 — pin the model, on the machine that will serve it.
#    Fetch both Qwen2.5-Coder checkpoints at a named revision; sha256 the loaded shards;
#    fill revision, weights_digest, serving.version, serving.hardware in the spec below and in
#    docs/preregistrations/EXP-002.draft.json; ModelIdentity.is_pinned() must return (True, []).
# 2. Serve it: a pinned vLLM behind its OpenAI-compatible API, bf16, no quantization, the
#    sampling parameters of the draft. The key, if any, is read from the environment.
export BESTSAD_MODEL_API_KEY=...
# 3. BEST-EXP2-14 — the pilot, on the pinned hardware. Two seeds, E0 under the model.
python scripts/exp002_pilot.py --spec spec.json --seeds 1 2 \
    --hardware "1x NVIDIA H100 80GB SXM, vLLM <version>" --out artifacts/exp002-pilot/pilot.json
#    Read preregistration_fill from the report: the seed count, the stopping rule, the
#    variance, the calibrated currency, the per-task budget C. If ceiling_check.saturating,
#    switch the primary to the 1.5B and re-run the pilot.
# 4. Fill and commit EXP-002 (Preregistration.commit()) as EXP-002.json BEFORE any S2/S3 job.
# 5. Run S2/S3 with the spec and the calibrated DeviceSecondsPolicy; transcripts land under
#    artifacts/<run>/transcripts/ and the S2 payload carries compute_currency,
#    flops_reconciliation, model_identity and job_isolation.
```

A spec, for reference (the identity record is the draft's, with its placeholders filled):

```json
{
  "kind": "fixed_weights_llm",
  "identity": {
    "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct", "kind": "fixed_weights_llm",
    "revision": "<hf commit>", "weights_digest": "sha256:<shards>",
    "tokenizer_id": "Qwen/Qwen2.5-Coder-7B-Instruct (tokenizer at the same revision)",
    "parameter_count": 7615616512, "provider": "self-hosted", "mode": "fixed-weights",
    "dtype": "bfloat16", "quantization": "none",
    "supported_projections": ["sexpr", "compact"], "context_budget_tokens": 32768,
    "constrained_decoding": false, "logprob_access": true, "tool_interface": "none",
    "sampling": {"temperature": 0.2, "top_p": 1.0, "max_output_tokens": 256,
                 "seed_policy": "per (seed, task, sample) hash",
                 "max_samples_per_task": 32, "repair_rounds": 2},
    "serving": {"engine": "vllm", "version": "<pinned>", "api": "openai-chat-completions",
                "hardware": "1x NVIDIA H100 80GB SXM (...)",
                "nondeterminism_sources": ["vLLM continuous batching ..."],
                "trust_boundary": "candidate side ..."},
    "model_identity_hash": "<ModelIdentity.hash()>"
  },
  "backend": { "kind": "http", "endpoint": "http://127.0.0.1:8000", "model": "<served name>" },
  "budget": { "max_samples": 32, "repair_rounds": 2, "max_output_tokens": 256, "temperature": 0.2 }
}
```

Roadmap recommendation 1's threshold, restated so it cannot drift: if the model arm beats the K0
baseline by ≥ +0.05 held-out at fixed compute (device-seconds on the pinned hardware, FLOPs
alongside), escalate to EXP-004; if it stays inside EXP-001-DR's interval, explanation B weakens
and A/C/D come forward.
