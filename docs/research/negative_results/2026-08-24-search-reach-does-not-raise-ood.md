# Negative result: removing two search-reach defects does not raise OOD solve rate

**Recorded:** 2026-08-24
**Outcome class:** null on the primary-endpoint proxy
**Claim level:** instrument measurement, not a study result

Spec §44 and P7 make this a deliverable. It is recorded because the *expectation* was
explicit — standing residual 4 asserted that the synthesizer's closure limitation "lowers the
ceiling" — and the measurement does not support it.

## What was tested

Two defects that genuinely narrowed the synthesizer's reachable program set:

1. **No closure capture.** Closure bodies saw only their own parameters, so
   `filter (e -> ge e n) xs` was unreachable at *any* budget: no enumerated body could mention
   the enclosing program's `n`. This is the limitation named in residual 4.
2. **Probe aliasing.** `_probe_tuples` assigned `pool[i % len(pool)]` positionally, so every
   variable of the same type received an identical value in every probe row. Observational
   equivalence then could not distinguish two same-typed variables: `ge L0 n` collapses onto
   `ge n n`, the constant `true`, and is pruned as a duplicate of it. This one was *not* on the
   residuals list. It was found while testing the fix for the first.

Both are unreachability, not slowness — the affected programs are removed from the search space
regardless of budget. Both applied identically in every condition, so neither biased the A–I
comparison; both lowered the ceiling for all of them.

## Design

Four arms, ablating the two fixes independently, so the effect could be *attributed* rather than
merely observed. Two seeds, `per_family=2`, `max_nodes=250_000`, `max_size=6`.

| Arm | capture | probe fix | curriculum | held-out | wall clock |
|---|:--:|:--:|---:|---:|---:|
| baseline (`v1`) | ✗ | ✗ | 24/32 | **5/16** | 480s |
| capture only | ✓ | ✗ | 25/32 | **5/16** | 464s |
| probe fix only | ✗ | ✓ | 27/32 | **5/16** | 406s |
| both | ✓ | ✓ | 27/32 | **5/16** | 418s |

## Result

**Held-out solve rate is 5/16 in all four arms.** Nothing moved it.

Training-set solve rate moved 24/32 → 27/32, and the ablation attributes that entirely to the
probe fix: 27/32 with or without capture. **Closure capture contributes nothing measurable once
pruning works** — the +1 in the capture-only arm is what capture looked like while it was still
being pruned away.

The probe fix also made the search *faster* (406s vs 480s), which is the expected direction:
correct pruning finds solutions at smaller sizes instead of exhausting levels.

## What this does and does not say

**Does:** at fixture scale, on families F1–F12, the instrument's search reach was not what was
limiting generalization. A program the searcher could not previously express was not the thing
standing between it and the held-out set. This is consistent with the EXP-001-DR null being about
representation rather than about the searcher running out of room, and it removes one candidate
explanation for that null.

**Does not:** this is 2 seeds and 16 held-out tasks at fixture budget — an instrument
measurement, not a study. It is not evidence that closure capture is useless in general; it is
evidence that these task families contain no held-out task that needed it. Capture's reachability
gain is proven by construction in `tests/experiments/test_closure_capture.py`, not by this table.

## Why the fixes were kept anyway

Both are correctness fixes to the searcher and stand on their own. The probe fix removes a
soundness-adjacent defect — pruning on signatures that could not distinguish two variables — and
pays for itself on the training side and in wall clock. Capture is a strict generalization at
about 3% wall-clock cost, and keeping it lets residual 4 be discharged truthfully rather than
re-worded.

## Consequence for existing results

Both changes alter what the searcher can reach, so `SYNTHESIZER_VERSION` now participates in the
condition-job and discovery checkpoint fingerprints. Without that, a checkpoint written by the
old searcher would be served silently to the new one.

**EXP-001-DR was produced by the older, narrower searcher.** Its numbers are not directly
comparable to any future run. Nothing in this document changes a recorded result; a re-run under
the current searcher would be a new run.
