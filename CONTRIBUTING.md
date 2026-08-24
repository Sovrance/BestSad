# Contributing to Bestsad

## Branching and pull requests

`v1` is the default branch and the trunk. **Do not push to it directly.**

```
git fetch origin v1
git checkout -b <topic-branch> origin/v1
# ... work, commit ...
git push -u origin <topic-branch>
# open a draft pull request into v1
```

Every change lands through a pull request, opened as a draft. This includes work by coding
agents: an agent's changes are reviewable for the same reason a person's are, and more so, since
the reviewer was not watching the reasoning that produced them.

The commits already on `v1` predate this convention — the research package, milestones M0–M10,
the licence, and the assurance integration were pushed directly while `v1` was still a working
branch rather than the trunk. They are not a precedent.

## Do not modify the delivered v0.2 package

These files arrived as a unit and their hashes are pinned in `MANIFEST_SHA256.txt`:

```
AGENTS.md                                        BESTSAD_RESEARCH_COMPANION_v0.2.md
README.md                                        BESTSAD_PREREGISTRATION_EXP001_v0.2.md
BESTSAD_RESEARCH_ARCHITECTURE_EXPERIMENTAL_SPEC_v0.2.md   IMPLEMENTATION_PLAN_v0.2.md
CHANGELOG_v0.1_to_v0.2.md                        BESTSAD_SOURCE_LEDGER_v0.2.csv
BESTSAD_REFERENCES_v0.2.bib                      schemas/ (the eight v0.2 schemas)
```

`sha256sum -c MANIFEST_SHA256.txt` must keep passing. It is the evidence that the normative
specification has not been quietly edited to match the implementation — which is exactly the
direction of drift a research instrument has to guard against. New guidance goes in a new file
(this one, `docs/adr/`, `docs/architecture/`), never by editing a delivered document.

## Before opening a pull request

```
pip install -e ".[dev]"
pytest -q                     # full suite
pytest -q -m slow tests/kernel # the 10^5-program K0 differential sweep
bestsad assure roots           # CLI smoke
```

CI runs five jobs: tests, the trust-boundary suite, the K0 sweep, the assurance acceptance
suite, and schema validation. The trust-boundary and assurance suites are separate jobs on
purpose — a regression in either should be visible as a named failing check rather than one line
inside a long log.

## Changes that need an architecture decision record

Spec §31.1 and `AGENTS.md` require an ADR for changes to K0 semantics, the primary metric, the
hidden-evaluation protocol, primitive maturity definitions, the trust boundary, allowed mutation
permissions, or benchmark family definitions. Add it under `docs/adr/` and update the index in
ADR-0001.

Two rules worth stating plainly, because they are the ones a well-meaning change is most likely
to break:

- **Do not weaken a control to make something pass.** If a test that asserts a refusal starts
  failing, the question is whether the refusal was right, not how to get past it. The controls
  exist to make a wrong answer hard to produce.
- **Do not widen K0 to make a downstream component easier.** It is the one shortcut that
  invalidates every comparison built on top of it, and it starts a new experiment lineage
  (spec §8.4).

## Claims and evidence

Anything that produces a research conclusion goes through the assurance protocol
(`docs/architecture/BESTSAD_ATLAS_ASSURANCE_INTEGRATION_ENG_v0.1.md`). A component that produces
evidence may not promote its own conclusions; promotion is decided by
`bestsad.assurance.promotion.evaluate`, and there is exactly one such predicate. If you find
yourself re-implementing part of it, that is the bug.
