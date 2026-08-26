# ADR 0015 — SRE wire schemas keep cross-repo conventions, not BestSad-native ones

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** the `schemas/sre/` contracts
**Relates to:** ADR 0012

## Context

The v0.1 handoff package ships starter SRE schemas and states that they are design seeds which
"must be reviewed against each repository's canonicalization conventions before merging". This
is that review, and the two conventions do not match.

BestSad's sixteen existing schemas use `snake_case` field names, carry no `$id`, and hold
content ids as bare 64-character hex — `semantic_hash` is exactly
`hashlib.sha256(...).hexdigest()`. The SRE seeds use `camelCase`, carry a versioned `$id`, and
require ids matching `^sha256:[a-f0-9]{64}$`.

Adopting the seeds verbatim makes `schemas/sre/` inconsistent with everything beside it.
Rewriting the seeds into BestSad style makes the Python and Go implementations emit different
bytes for the same object, which breaks content-addressed agreement and with it the v0.1
definition of done ("cross-project schemas are versioned, content-addressed, and independently
validated in Python and Go").

Only one of those costs is recoverable.

## Decision

`schemas/sre/` keeps the cross-repo convention exactly as the seeds define it: `camelCase`
fields, versioned `$id`, `sha256:`-prefixed content ids. These are **wire contracts at a
boundary shared with another repository**, not BestSad-native objects.

BestSad's own schemas are untouched and keep `snake_case` with bare-hex ids. No existing
schema is migrated, and no existing field is renamed.

Conversion is explicit and lives in one place, `src/bestsad/sre/ids.py`:

- `as_content_id(hex_digest)` adds the `sha256:` prefix on the way out;
- `bare_digest(content_id)` strips it on the way in, and rejects anything that does not match
  the prefixed form rather than passing it through.

## Consequences

- Two conventions coexist in `schemas/`, which is a real readability cost. It is paid once, at
  a boundary that is named for what it is, rather than paid continuously as interoperability
  bugs.
- The prefix is not decoration. A bare 64-hex string is ambiguous about its hash function
  forever; `sha256:` makes a future second algorithm an additive change rather than a silent
  reinterpretation of existing data.
- Because conversion is a function rather than a formatting convention, "someone forgot the
  prefix" is a schema validation failure at the boundary, not a mismatched id discovered later
  by a Go consumer.
- Anyone reading `schemas/sre/*.json` next to `schemas/claim.schema.json` will notice the
  difference and, ideally, read this ADR.

## Revisit trigger

If SAISES adopts `snake_case` for its own protocol objects, or if SRE-Core stops being shared
across repositories, the boundary disappears and the SRE schemas should be migrated to match
BestSad's house style in one deliberate pass.
