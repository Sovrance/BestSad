# ADR 0021 — CI runners returned; `ci.yml` is live again and the local runner stays

**Status:** Accepted
**Date:** 2026-09-15
**Governs:** `.github/workflows/ci.yml`, `scripts/ci_local.py`,
`tests/integrity/test_local_gates_mirror_ci.py`
**Supersedes:** ADR-0018
**Decided by:** repository owner, 2026-09-15 ("Mark ADR-0018 superseded now that runners are
back")

## Context

ADR-0018 recorded that from ~2026-08-24 every GitHub Actions run in this repository completed
in seconds with no runner assigned, no steps and no logs, and that the owner would not pay for
runners. It made `scripts/ci_local.py` the thing that executes the gates and named its own
revisit trigger: "If runners return — paid, self-hosted, or otherwise — `ci.yml` resumes
working with no change and this ADR should be marked superseded."

On 2026-09-15 that trigger fired. The two Actions runs on PR #8 (35007331423 on head
`78b8a65`, 35007657549 on head `05c5be1`) executed every one of the seven `ci.yml` jobs with
real durations and real logs, and every job succeeded — including the evaluator-image gate,
which a machine without a Docker daemon cannot run. These were the first genuine runs since #27
on 2026-08-24. The PR was merged into `v1` on the strength of them.

## Decision

**ADR-0018 is superseded.** GitHub Actions is again the primary execution of the gates, and a
red check on a current head carries information: it is a finding, not runner starvation. The
runner-starvation signature ADR-0018 describes (`runner_id: 0`, zero steps, no logs) remains
the way to recognise the failure mode if it recurs, and if it does, ADR-0018's decision applies
again without needing to be rewritten.

**`scripts/ci_local.py` stays**, as ADR-0018 already anticipated, as the way a contributor or
an agent reproduces a CI result locally before pushing. Its UNAVAILABLE/INCOMPLETE distinction
stays with it: a gate whose tooling is missing locally is still reported as not run, never as
passed. `tests/integrity/test_local_gates_mirror_ci.py` stays too — a local runner that has
drifted from `ci.yml` reproduces the wrong thing.

**Claims about gates keep saying where they ran.** A local run is still the author checking
their own work (ADR-0018's independence point); a CI run on the pushed head is the second
opinion. A pull request should carry the CI result on its head, and a local run when CI could
not run a gate the local machine could.

## Consequences

- `docs/experiments/STATUS.md`, `CONTRIBUTING.md`, the `scripts/ci_local.py` docstring and the
  mirror test's docstring no longer state that runners are unavailable.
- The spec §27.2 assertion that the built evaluator image carries no hidden evaluation assets
  is verified again on every CI run, which ADR-0018 listed as the control carrying no evidence
  while runners were down.
- Nothing in the gates themselves changes: same seven jobs, same commands, same mirror.

## Revisit trigger

If the runner-starvation signature reappears, ADR-0018's decision is back in force: run the
gates with `scripts/ci_local.py`, say where they ran and which were UNAVAILABLE, and treat red
GitHub checks as carrying no information until runners return. Record that in a new ADR rather
than editing this one.
