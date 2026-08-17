# ADR 0005 — In-process audit-hook sandbox for the candidate boundary

**Status:** Provisional
**Date:** 2026-08-17
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
