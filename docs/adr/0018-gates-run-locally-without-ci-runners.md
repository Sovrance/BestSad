# ADR 0018 — CI runners are unavailable; gates run locally, and the loss is stated

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** `scripts/ci_local.py`, `.github/workflows/ci.yml`
**Decided by:** repository owner, 2026-08-26 ("There are no runners and I will not be paying
for them")

## Context

Since roughly 2026-08-24 23:42 UTC every GitHub Actions run in this repository has completed
within seconds with no runner assigned: `runner_id: 0`, empty `runner_name`, zero steps
executed, and log download returning HTTP 404. The failure is not branch-specific — run #28 on
`v1` itself shows the same signature, as does every job of run #31 on both attempts. The last
run to genuinely execute was #27 on 2026-08-24 at 20:05 UTC, which took 61 seconds and passed.

The owner has decided that runners will not be paid for. This is therefore the steady state,
not an outage to wait out.

That leaves the repository in a specific and dangerous position: `ci.yml` describes six real
gates — including Gate G0 (K0 differential sweep) and Gate G1 (evaluator trust boundary) —
and every one of them is red for a reason unrelated to the code. A permanently red check is
worse than no check. It trains everyone to ignore the signal, and it hides a genuine failure
inside noise that everyone has already learned to skip past.

## Decision

**`ci.yml` stays.** It is correct, it costs nothing to keep, and it will work again unchanged
if runners ever return. Deleting it would destroy a working description of the gates in
exchange for nothing.

**The gates become runnable locally.** `scripts/ci_local.py` runs the same six jobs with the
same commands. The commands are mirrored from `ci.yml` rather than reinvented, and a check
confirms every job name and every `pytest` invocation in the workflow appears in the script,
so the two cannot silently drift.

**An unrun gate is never reported as a passing gate.** A gate whose tooling is missing reports
`UNAVAILABLE`, and the overall result is `INCOMPLETE` with exit code 2 — never `OK`. This is
not pedantry: on this machine `docker` is installed but its daemon is not running, so the
first version of the script ran the evaluator-image gate, got exit 1, and reported `FAIL`.
That would have read as "the evaluator image is broken" when the truth was "the gate did not
run". The script now probes whether a tool actually works rather than whether a binary is on
`PATH`, and distinguishes the two outcomes.

## What is lost, stated plainly

Running gates on the machine that wrote the code is weaker evidence than CI, in three ways
that anyone reading a "gates passed" claim should hold in mind:

1. **Independence.** CI is a second opinion from a machine with no stake in the change. A
   local run is the author checking their own work. For a research instrument whose entire
   value rests on not having quietly weakened a control, this is a real reduction in
   assurance, and no amount of local green recovers it.
2. **Environment isolation.** CI starts from a clean image and catches "passes only because
   of something already installed here". `--fresh-venv` recovers most of this by building a
   clean virtualenv and installing the project into it, which is what CI's install step does.
3. **Coverage.** The evaluator-image gate cannot run without a Docker daemon. On a machine
   without one it is simply not checked — and the spec §27.2 assertion it carries, that the
   built image contains no hidden evaluation assets, is exactly the kind of control that must
   not be assumed. It is reported `UNAVAILABLE` every time rather than quietly dropped.

Point 3 deserves emphasis. Gate G1 and the image probe exist because of AGENTS.md invariant 2
— no read path from the search side to the hidden benchmark. A local run covers the G1 test
suite but not the image probe, so the image half of that invariant is currently unverified on
any machine without Docker.

## Consequences

- A red GitHub check on this repository carries no information and should not be treated as a
  finding. The runner-starvation signature above is how to confirm that in one look.
- Claims that gates passed must say *where they ran* and *which gates did not run*. A summary
  that says "all gates green" without naming the unavailable one is the failure this ADR is
  written to prevent.
- If Docker becomes available, the evaluator-image gate should be run and the result recorded,
  since it is the one control currently carrying no evidence at all.

## Revisit trigger

If runners return — paid, self-hosted, or otherwise — `ci.yml` resumes working with no change
and this ADR should be marked superseded. `scripts/ci_local.py` is still worth keeping at that
point as the way a contributor reproduces a CI failure locally.
