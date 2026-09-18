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

Everything since has landed this way. PRs #8–#12 (2026-09-15 to 2026-09-16: the verification
plane, ADR-0021, the K0 twin, and the two status updates that recorded them) were each opened
as a draft by a coding agent, ran every `ci.yml` job to green on their merged head, and were
marked ready and merged by the owner. PRs #13–#16 (2026-09-17 to 2026-09-18) followed the same
path, one file each: this file (#13, `0aa37f2`), `REPOSITORY.md` with the agent guidance for
the twin (#14, `76ec5e4`; `AGENTS.md` is manifest-pinned, so the guidance could not go there),
`ASSURANCE_WORK_ORDERS.md` (#15, `ca30270`) and `STATUS.md` (#16, `670256e`). PRs #17–#19
(2026-09-18) recorded those in turn: this file (#17, `43eba75`), `ASSURANCE_WORK_ORDERS.md`
(#18, `b6d0993`) and `STATUS.md` (#19, `71253cf`; merged with three jobs still running, all of
which finished green on that head). The merge record, with heads and job counts, is in
`docs/experiments/STATUS.md`; work-order status is in
`docs/architecture/ASSURANCE_WORK_ORDERS.md`. A pull request that changes what those files say
is done updates them in the same pull request or the next one, not never.

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
(this one, `REPOSITORY.md`, `docs/adr/`, `docs/architecture/`), never by editing a delivered
document.

`tests/integrity/test_delivered_package.py` enforces this, one test per pinned file. It was
added after `README.md` drifted for a week: the manifest was pinned from the start and nothing
verified it, which is the same as not having pinned it. Repository-level front matter — licence
notice, assurance protocol, layout — is in `REPOSITORY.md` for exactly this reason.

## Before opening a pull request

```
pip install -e ".[dev,verify]"   # `verify` adds the optional Z3 solver (ADR-0019)
pytest -q                        # full suite
pytest -q -m slow tests/kernel   # the 10^5-program K0 differential sweep
pytest -q tests/verify/test_k0_twin.py   # twin parity, incl. the same 10^5 corpus (needs cargo)
python3 scripts/kani_gate.py     # every Kani harness on the twin within budget (needs cargo kani)
bestsad assure roots             # CLI smoke
python3 scripts/ci_local.py      # every gate, as CI runs them, reproduced locally (ADR-0021)
```

GitHub Actions runs the gates on every pull request (ADR-0021; between 2026-08-24 and
2026-09-15 there were no runners, ADR-0018). Every run since PR #8 has been genuine, with
real durations and logs; a red check on a current head is a finding, not runner noise.
`scripts/ci_local.py` reproduces the gates locally before a push; `--fresh-venv PATH`
reproduces CI's clean install. A gate whose tooling is missing locally reports `UNAVAILABLE`,
never `OK`, and a claim that gates passed must say where they ran and which gates did not run.

`ci.yml` describes nine jobs, and CodeQL runs alongside them for Python, Rust and the
workflow itself: tests, the trust-boundary suite (G1), the K0 sweep (G0), the assurance
acceptance suite, schema validation, the verification plane (G-V), the K0 twin parity and K0
twin proof jobs (BEST-VERIF-05, ADR-0020), and the evaluator image. The workflow token is
limited to `contents: read`; a new job that needs more says so in its own `permissions` block
rather than widening the default. The trust-boundary,
assurance and verification suites are separate jobs on purpose — a regression in any of them
should be visible as a named failing check rather than one line inside a long log. The `tests`
job installs no solver and no Rust toolchain, so the solver-backed and twin-backed tests skip
there; G-V and the twin jobs are where they run, each with a probe that reports `UNAVAILABLE`
locally if Z3 cannot solve, `cargo` cannot build the twin, or `cargo kani` is not installed.

The K0 twin (`k0rs/`) is a Rust crate outside the Python package. Building it needs a stable
Rust toolchain; its proofs need Kani (`cargo install --locked kani-verifier && cargo kani
setup`). `build.rs` refuses to compile a twin whose kernel hash differs from the Python
`KERNEL_VERSION_HASH`, and if the twin and the reference ever disagree the Python reference is
normative and the twin is fixed (ADR-0002, ADR-0020). Every Kani harness must verify within
60 s; a harness over budget is split, never loosened (`scripts/kani_gate.py`).

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
