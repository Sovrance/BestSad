# ADR 0006 — Hand-written MDL abstraction extractor for condition C

**Status:** Accepted
**Date:** 2026-08-17 · **Amended:** 2026-08-24
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

## Amendment, 2026-08-24: both weaknesses fixed

This ADR was written Provisional because the first implementation had two weaknesses, recorded
so they would not be mistaken for design:

1. It ranked candidates *independently*. A genuinely MDL-optimal library is chosen jointly —
   abstractions compete for the same corpus mass, and picking the top-k independently overcounts
   overlapping savings.
2. The saving was counted in **nodes**, while SG-v2 (M7) counts **bits** under a declared prior.

Both made condition C *weaker than it should be*, which biases in favour of the treatment — the
wrong direction for a control. Option (a) of the revisit trigger has now been taken.

**The objective is now two-part MDL in bits:**

    minimise   L(corpus | library) + L(library)

computed with the same `CodingScheme` SG-v2 uses, so the control and the Semantic Gain metric
measure description length the same way rather than one counting bits and the other nodes.

**Selection is joint.** After each abstraction is chosen the corpus is *rewritten* to use it
(`abstraction/rewrite.py`) before the remaining candidates are re-scored. Two abstractions
covering the same subtree can no longer both claim the saving: once the first is applied, the
mass the second would have compressed is gone. A beam (default width 3) keeps several partial
libraries alive so one locally-best first pick cannot foreclose a jointly better pair, and
selection stops as soon as no remaining candidate reduces total bits — a library that costs more
to state than it saves is never selected, at any size.

`tests/abstraction/test_joint_mdl.py` pins both properties, including that the reported total
saving equals the sum of the per-step savings (no double counting) and that changing the coding
scheme's prior changes the result (the scheme is genuinely consulted).

### What this changes about the EXP-001-DR result

Condition C was re-run across all 32 seeds under the strengthened extractor
(`artifacts/C_joint_mdl.json`). The result is worth stating precisely, because it is more
informative than "no change":

- The joint search selects a **genuinely different and smaller** library — a median of 2–3
  abstractions per seed against the utility regime's 4, two seeds selecting none at all, and a
  language description 149 tokens against 156.
- The runs genuinely differ: per-seed reproducibility digests differ on **28 of 32 seeds**, and
  mean search nodes moved 204,152 → 204,175.
- The verified compositional OOD solve rate is **identical on all 32 seeds**: 0.2344 either way,
  same variance, and D-versus-C is unchanged to four decimals (+0.0078, p = 0.6487,
  95% CI −0.0260 to +0.0417).

So strengthening the control changed *what it selects* without changing *what it achieves*. The
limitation this ADR attached to the D-versus-C comparison is discharged: that comparison was not
an artefact of a weakened control, and the run's `h0_consistent` outcome does not depend on the
extractor's weaknesses. It also says something about the instrument — at this resolution the
choice of abstraction-selection objective does not move the endpoint at all, which is consistent
with the run's finding that the constraint lies in the candidate pool rather than in how
candidates are ranked.

## Still not done: option (b)

Adopting an external MDL extractor behind a validated BSIR translation remains unattempted, for
the reason in the Decision above: the translation would itself need to be trustworthy, on the
control arm, where an error is least likely to be noticed. Revisit if an extractor appears that
operates over a representation BSIR can be mapped to without a bespoke bridge.
