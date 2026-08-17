# ADR 0006 — Hand-written MDL abstraction extractor for condition C

**Status:** Provisional
**Date:** 2026-08-17
**Governs:** spec §36 (adopt an existing MDL-optimal corpus abstraction tool); implementation
plan M6 ("condition C uses a real MDL-optimal extractor, not a strawman")

## Context

Spec §36 says condition C's implementation should be an existing MDL-optimal corpus abstraction
tool, so that the frequency/MDL control is a real baseline. The implementation plan repeats the
point in stronger terms, and for good reason: the companion's audit found that this family of
methods is where the *negative* results for learned libraries come from. A weak condition C
would hand condition D a win it did not earn, and that win would be the single most misleading
number the program could produce.

## Decision

Implement the extractor in-repo (`bestsad.abstraction.extract`, regime `"mdl"`) rather than
wrapping an external tool, for now.

Reason: the external tools in this family operate over their own program representations, and
Bestsad's object of study is BSIR with a canonical semantic hash. Wrapping one would mean
translating BSIR to that tool's language and its abstractions back, and the translation would
have to be semantics-preserving to be trustworthy — which is a translation-validation problem
of the same order as the extractor itself, on the *control* arm, where a subtle error is least
likely to be noticed and most damaging.

The implementation is the standard compression objective and nothing cleverer: for each
semantically-deduplicated candidate pattern, the corpus saving is

    occurrences × (pattern_size − (1 + arity)) − pattern_size

and candidates are ranked by it. Selection is over the same mined candidate set that conditions
B and D draw from, so the three regimes differ **only** in their selection rule. That is what
makes the comparison a comparison of selection criteria rather than of mining pipelines.

## Why this is provisional

Two known weaknesses, stated so they are not mistaken for design:

1. This ranks candidates *independently*. A genuinely MDL-optimal library is chosen jointly —
   abstractions compete for the same corpus mass, and picking the top-k independently
   overcounts overlapping savings. A joint/beam search over the library is the correct form.
2. The saving is counted in **nodes**, whereas SG-v2 (M7) counts **bits** under a declared
   prior. The two should agree on ordering in easy cases and can disagree at the margin.

Both weaknesses make condition C *weaker than it should be*, which biases in favour of the
treatment. That direction is the wrong one for a control, and it must be disclosed with any
result in which D beats C.

## Revisit trigger

Before EXP-001 is run as anything other than an instrument dry run, either (a) replace the
independent ranking with a joint library search and re-express the objective in bits, or
(b) adopt an external MDL extractor behind a validated BSIR translation. Until one of those
happens, any D-beats-C comparison carries this ADR as a stated limitation.
