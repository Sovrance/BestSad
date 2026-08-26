# ADR 0016 — Observing K0 inference from outside the kernel, and what to do when node types disagree

**Status:** Accepted (amended 2026-08-26, before merge)
**Date:** 2026-08-26
**Governs:** `src/bestsad/bsir/typing.py`
**Relates to:** AGENTS.md invariant 1; design §7.1 (BSIR-1 "complete result types")

## Context

BSIR-1 is defined as the typed graph: "current graph semantics plus complete result types,
effects, regions, proof obligations". Today `to_graph` builds every node with
`result_types=()`, so the level is aspirational — nothing populates it.

Populating it needs the type inferred at each subterm, and only the K0 typechecker knows that.
AGENTS.md invariant 1 forbids modifying the trusted semantic kernel, and the typechecker is
where K0's static semantics live, so the options were:

1. Re-implement inference inside `bsir/`. Rejected: two implementations of K0's static
   semantics is a far worse invariant risk than the one being avoided, and the copy would
   drift silently.
2. Call the existing `Typechecker` once per subterm. Rejected: a subterm's type depends on its
   environment and on constraints discovered elsewhere in the program. Per-subterm calls with
   fresh unifiers return unresolved type variables where the whole-program inference returns
   `Int` — that is, they return wrong answers.
3. Add a read-only recording hook *inside* `Typechecker`. **Attempted, then withdrawn** — see
   the amendment below.
4. Subclass `Typechecker` from outside the kernel and override `infer`. Chosen.

## Decision

`src/bestsad/bsir/typing.py` defines `_RecordingTypechecker`, a subclass of the kernel's
`Typechecker` that overrides `infer` to record `(occurrence, type)` before returning.

This works because of a property the kernel already has: every recursive call inside
`Typechecker.infer` goes through `self.infer`, so an override sees every subterm without the
kernel knowing anything about it. The unifier arrives as an argument, so recorded types are
resolved against the final substitution once inference finishes — deferred on purpose, since a
type read mid-inference may still be a type variable a later constraint pins down.

**`src/bestsad/kernel/` is not modified at all.** No signature, no operation table, no
unification rule, no acceptance decision.

`tests/bsir/test_recording_typechecker.py` asserts both halves: that the kernel typechecker
contains no observation machinery (a string check that fails if a hook ever creeps back in,
naming the invariant it broke), and that recording and plain inference agree on results and on
failures across 200 random programs.

## Amendment — the first version modified the kernel, and that was wrong

The version of this ADR merged into the first draft of this branch added an `observe` callback
to `Typechecker.check_program` and a `_seen` accumulator to `infer`. It argued the change was
acceptable because it was read-only, append-only, off by default, and provably result-identical.

Every one of those claims was true, and the change was still wrong, because AGENTS.md invariant
1 does not say "do not change what the kernel decides". It says **do not modify the trusted
semantic kernel**. A modification that is currently harmless still moves the frozen boundary,
and the value of a frozen boundary is precisely that it does not move for good reasons.

The original analysis listed three options and rejected two. It never considered subclassing —
which meets every requirement the hook met, at zero cost to the kernel. The lesson worth
keeping is not "the hook was unsafe" but that an argument for why a violation is acceptable is
a sign the option space was searched too shallowly.

## The harder half: nodes whose occurrences disagree

BSIR node ids are content-addressed over the term, so structurally identical subterms are one
node. Types are not a function of structure alone. This program is legal and ordinary:

```
map(lam(v: Bool). v,
    map(lam(v: Int). eq(v, v), range(0, 3)))
```

Both lambdas bind `v`, so both bodies serialize to `var[name=v]` and share a single node — but
that node is `Bool` at one occurrence and `Int` at the other two.

Three responses were available, and two are wrong:

- **Pick one** (first wins, or last wins). This writes a definite type onto a node that does
  not have one. Every consumer downstream then reads a confident answer that is false half the
  time.
- **Split the node by type**, giving `var[name=v]:Bool` a different id from `var[name=v]:Int`.
  This changes node identity, and node identity is derived from the same canonical
  serialization that backs `semantic_hash`. Not worth it for an annotation.

The decision is the third: **populate `result_types` only where every occurrence agrees, and
record disagreement as an explicit ambiguity.** A node with conflicting occurrences keeps
`result_types=()` and appears in `TypingReport.ambiguous` with all observed types listed.

This is design principle P3 — ambiguity is first-class — applied literally. `infer_level` then
reports `BSIRLevel.TYPED` only when *every* node carries a type, so a graph containing an
ambiguous node does not claim to be BSIR-1.

## Consequences

- `result_types` is trustworthy where it is populated, and its absence is informative rather
  than merely unfilled.
- The kernel's frozen boundary is intact, and a test now fails if observation returns to it.
- An analyzer that needs a per-occurrence type cannot get it from the graph, by construction.
  It must work from the term, and that limitation is honest about what a shared-node DAG can
  represent.
- The ambiguity is reported, so it can be measured. If it turns out to be common in practice
  rather than a corner case, splitting nodes by type becomes worth reconsidering — but that
  would be a deliberate change to node identity, with its own ADR.

## Revisit trigger

If `TypingReport.ambiguous` is non-empty for a material fraction of real candidate programs,
reopen the node-identity question.
