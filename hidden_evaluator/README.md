# hidden_evaluator/

Stand-in for the **separate repository or protected service namespace** that spec §28 says
should hold the frozen hidden evaluator, so the evolutionary agent cannot inspect it.

## Rules

1. Nothing under `src/bestsad/` may import from this directory.
   `tests/integrity/test_trust_boundary.py` asserts it statically.
2. Candidate-side code runs under a sandbox policy that denies reads anywhere under this path
   (`bestsad.evaluator.sandbox.default_policy`).
3. The seed commitment for the frozen hidden benchmark lives in `frozen/`. The benchmark itself
   is *not* stored: tasks are a pure function of (family, seed), so the commitment is enough to
   regenerate them and nothing needs to sit on disk where it could leak.

## Disclosed residual

Keeping this directory in the same checkout is a development convenience with a real weakening
attached: anyone with filesystem access has the assets, and the audit-hook sandbox is not a
kernel boundary (ADR-0005). Before any result is treated above Claim Level 1, this must move to
a separate repository or service namespace. This is recorded in ADR-0003 and must be repeated
in the residual-confound disclosure of any run that relies on it.
