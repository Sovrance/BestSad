# Repository front matter

`README.md` is part of the delivered v0.2 package and its hash is pinned in
`MANIFEST_SHA256.txt` (see `CONTRIBUTING.md`, "Do not modify the delivered v0.2 package").
Repository-specific notes therefore live here rather than being appended to it.

That rule was broken once, quietly, and this file is the repair: the licence and assurance
sections below were added directly to `README.md` in commits `0cd728e` and `02e3b79`, which
made `sha256sum -c MANIFEST_SHA256.txt` fail without anything noticing. The check now runs as
`tests/integrity/test_delivered_package.py`, so the next such edit fails a test instead of
drifting for a week. A pinned hash that nothing verifies is not a control.

## Licensing

**Proprietary. All rights reserved.** See `LICENSE`.

This repository contains unpublished research materials and is confidential. No license to use,
copy, modify, or distribute is granted except by separate written agreement with the owner.

The license does not relax the scientific reporting obligations recorded in this package — the
claims register (spec §45), the requirement that a capability claim carry conditions F, H and I,
and the requirement to preserve negative results all continue to bind any authorised user. A
license to use the instrument is not a license to misrepresent what it measured.

## Assurance protocol

Every evolved primitive, genome, and experimental capability claim carries an explicit,
machine-enforced assurance lifecycle:
`docs/architecture/BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md`.

The rule it exists to enforce is that **producers of evidence cannot promote their own
conclusions**. K0, BSIR, the evaluator, the sandbox policy, the MDL coding scheme and the
pre-registration are content-addressed roots; a change to any of them stales its descendants
automatically. Query it with `bestsad assure roots`, `bestsad assure stale`,
`bestsad primitive explain <id>`, and `bestsad report <run-id> --confirmatory`, which exits
non-zero when promotion dependencies do not hold.

## Where things are

| Path | What it holds |
|---|---|
| `*_v0.2.md`, `*_v0.2.csv`, `*_v0.2.bib`, `schemas/` | The delivered package. Read-only; hashes pinned. |
| `src/bestsad/` | The instrument. |
| `tests/` | Acceptance tests, named after the milestone or invariant they discharge. |
| `docs/adr/` | Architecture decisions, including every disclosed residual. |
| `docs/experiments/` | Run status and reports. |
| `docs/research/negative_results/` | Never deleted (P7, spec §44). |
| `docs/preregistrations/` | Hashed and committed before the run they govern. |
| `CONTRIBUTING.md` | Branch and pull-request workflow; the rules above. |
