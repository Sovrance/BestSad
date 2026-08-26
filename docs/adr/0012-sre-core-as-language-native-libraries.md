# ADR 0012 — SRE-Core is language-native libraries against shared schemas, not a service

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** SRE v0.1 ADR-SRE-002

## Context

SRE-Core is the small meta-model both systems share: `ArtifactRef`, `Fact`, `Assumption`,
`Observation`, `Trace`, `EquivalenceClass`, `AnalyzerResult`, `Counterexample`,
`CertificateRef`. Something has to guarantee that a Python `Fact` and a Go `Fact` are the same
object.

The obvious way to guarantee it is to have one implementation and call it over the network.

## Decision

SRE-Core v0.1 is implemented twice — natively in Python here, natively in Go in the SAISES
repository — against a single set of JSON Schema contracts held in `schemas/sre/`. There is no
SRE service, and no runtime dependency from either system on the other.

Agreement is enforced by both implementations validating against the same schema files and by
both computing the same content-addressed IDs from the same canonical serialization.

## Consequences

- Trust-critical paths gain no new availability dependency. A promotion decision in BestSad
  cannot become un-decidable because a shared service is down, and it cannot silently change
  meaning because that service was deployed on a different day than its callers.
- Version coupling is explicit and reviewable: it lives in a schema file with a version in its
  `$id`, not in whatever revision a server happens to be running.
- The cost is genuine duplication. Two implementations can drift, and nothing in this
  repository can detect drift in the other one on its own.
- That drift risk is what makes canonical-ID agreement a *test* obligation rather than an
  assumption: `tests/sre/test_canonical_ids.py` pins the exact byte serialization and the
  resulting digests as literals, so a Go implementation can be checked against the same
  vectors, and a change to either side that would break interoperability fails here first.

## Revisit trigger

If the two implementations drift in practice despite the pinned vectors — that is, if a real
interoperability failure reaches a certificate — the alternative to consider is not a service
but a generated implementation from a single source of truth.
