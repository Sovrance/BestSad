# ADR 0005 — In-process audit-hook sandbox for the candidate boundary

**Status:** Provisional
**Date:** 2026-08-17 (amended 2026-08-24)
**Governs:** spec §27.1 (candidate sandbox), §20.2 (access controls), `AGENTS.md` invariant 2

## Context

Spec §27.1 requires process isolation, no network, a read-only base filesystem, writable
ephemeral scratch only, CPU/memory/time limits, syscall restrictions, and no access to hidden
evaluation assets. Spec §27.2 requires the evaluator to run outside the candidate-controlled
namespace.

Those are container and kernel properties. The instrument as it stands runs in a single Python
process during development, and the M4 acceptance test — "a deliberately malicious candidate
fails on every vector, and the integrity monitor fires" — must be executable now.

## Decision

Two layers, with different strengths, and the distinction stated rather than blurred:

**Layer 1 — the structural guarantee (strong).** A candidate *program* is a K0 term. K0 has no
operation with any effect other than trapping: no I/O, network, clock, randomness, FFI, or
reflection (spec §8.2). A candidate program therefore cannot read hidden tests, tamper with the
evaluator, or persist state — not because something filters it, but because the vocabulary
contains no operation that could. `tests/integrity/test_trust_boundary.py` asserts this over the
whole op table rather than over a blocklist. This is the layer that actually secures the
experiment, and it does not depend on any runtime policy.

**Layer 2 — the process policy (weak, and honestly labelled).** The code *around* the candidate
— the search loop, the abstraction extractor, the analysis — is ordinary Python and could touch
the filesystem. `bestsad.evaluator.sandbox` installs a `sys.addaudithook` hook that denies reads
under `hidden_evaluator/`, denies all network and subprocess creation, denies writes outside the
scratch directory, and records every attempt in an integrity monitor.

## What this is not

An in-process audit hook is **not** a kernel sandbox:

- native code and `ctypes` can bypass it (the hook denies `ctypes.dlopen`, which raises the bar
  but is not a proof);
- it does not enforce CPU or memory limits;
- it does not provide process isolation or a read-only base filesystem;
- keeping `hidden_evaluator/` in the same checkout means anyone with filesystem access has the
  assets (ADR-0003 records this residual too).

It defends against the realistic failure mode *at this stage*: a component that reaches for the
hidden assets because of a bug or an over-helpful heuristic. It does not defend against hostile
native code, and no test here should be read as claiming otherwise.

## Production requirement

Before any result is treated above Claim Level 1, the deployment must add: an immutable
evaluator container image, the candidate sandbox as a separate process with seccomp/syscall
restrictions and rlimits, a read-only base filesystem with an ephemeral scratch mount, and
`hidden_evaluator/` relocated to a separate repository or protected service namespace. Until
then, this residual is disclosed in the run's residual-confound section — undisclosed residuals
are a protocol violation (spec §40.3).

## Revisit trigger

Re-open when the evaluator image lands, and downgrade layer 2 from "the boundary" to
"defence in depth behind the container".

---

## Amendment, 2026-08-24 — layer 3 lands, and what it does not settle

The "What this is not" list above is now partly closed. Two of its four bullets were the ones
that mattered operationally, and both are addressed; the other two are not, and the ceiling this
ADR places on claims is unchanged as a result.

### What is now enforced

**`bestsad.evaluator.isolation.run_isolated`** runs candidate-side work in a separate forked
process with kernel-enforced limits applied *before* any candidate code runs:

| Bullet from "What this is not" | State |
|---|---|
| "does not enforce CPU or memory limits" | **Closed.** `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, `RLIMIT_CORE`. |
| "does not provide process isolation" | **Closed for the process half.** Separate process, cleared environment, cwd pinned to ephemeral scratch. |
| "does not provide … a read-only base filesystem" | **Open in the run path.** The image provides it; the experiment runner does not yet execute inside the image. |
| "`ctypes` and native code can bypass it" | **Open.** No seccomp allowlist. Docker's default profile is not one the program has declared. |
| "`hidden_evaluator/` in the same checkout" | **Open.** Unchanged; ADR-0003's residual stands. |

The CPU limit is set with the soft bound one second below the hard bound. Setting them equal was
the first implementation, and it was wrong in an instructive way: both signals arrive in the same
instant, `SIGKILL` wins the race, and the run records "killed" where it should record "exceeded
the CPU limit". A limit that fires without saying which limit fired is a limit you cannot audit.

A child that dies to a limit is reported as `contained=True` — distinct from a candidate raising
an exception, which is a bug to fix rather than a boundary doing its job. `MemoryError` under
`RLIMIT_AS` is classified as containment for the same reason. The distinction is not cosmetic:
an evaluator that dies mid-run cannot score anything, and a run that silently loses candidates is
not a controlled experiment.

`tests/integrity/test_process_isolation.py` is the red team for this: fifteen tests, each
attempting the failure it names — runaway allocation, unbounded CPU, a blocking candidate that
burns no CPU at all, abrupt child death, inherited credentials, an escape attempt that tries to
spawn its own less-restricted process. In every case the passing result is that the *evaluator*
survives with a recorded outcome.

**`src/bestsad/evaluator/Dockerfile`** is the deployment half: a two-stage build that ships a
wheel rather than the source tree, runs as uid 10001, and mounts scratch rather than baking it.
It deliberately does **not** contain `hidden_evaluator/` — baking the assets in would make
ADR-0003's residual permanent and shippable. The `evaluator-image` CI job builds it and asserts
the two properties that matter: no hidden assets inside, and it starts under `--read-only
--network none --cap-drop ALL`. A Dockerfile that is only ever read is documentation with a
misleading filename.

### What this does not settle

The production requirement above is **not** met, and no claim ceiling moves:

1. The image exists and is CI-verified to build and start correctly. **No experiment has been run
   inside it.** EXP-001-DR ran on the host. Until a run's provenance records the image digest it
   executed under, the read-only-filesystem property is available rather than used.
2. There is still no seccomp allowlist of the program's own. Native code remains outside what any
   of these three layers proves anything about.
3. `hidden_evaluator/` still shares a checkout. This is the residual that most directly bounds
   claims, and process isolation does nothing about it: a separate process on the same host reads
   the same disk. Only relocation fixes it.

Layer 1 — K0 having no operation with any effect other than trapping — remains the layer that
actually secures the experiment, and remains independent of all of this.

**The Claim Level 1 ceiling in `docs/experiments/STATUS.md` therefore stands.** What changes is
the size of the residual, not its existence, and the residual as restated there is now (3) plus
(2) rather than the whole original list.

### Revisit trigger, restated

Re-open when either (a) the experiment runner executes inside the image and records its digest in
run provenance, or (b) `hidden_evaluator/` is relocated out of the checkout. Either one narrows
the residual further; both together, plus a declared seccomp profile, are what this ADR needs to
move from Provisional to Accepted.
