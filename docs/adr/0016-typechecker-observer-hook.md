# ADR 0016 — A read-only observer hook on the typechecker, and what to do when node types disagree

**Status:** Accepted
**Date:** 2026-08-26
**Governs:** `src/bestsad/kernel/typecheck.py`, `src/bestsad/bsir/typing.py`
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
3. Add a read-only recording hook to the existing inference. Chosen.

## Decision

`Typechecker.check_program` accepts an optional `observe` callback, and `infer` accepts an
optional `_seen` accumulator. Both default to off, and with them off the code path is the
original one.

The hook is constrained in three ways that make it not a semantics change:

- `_seen` is append-only and is never read during inference, so it cannot influence
  unification;
- observation is delivered *after* inference completes, with types resolved against the final
  substitution, so it reports what the program means rather than an intermediate guess;
- `tests/kernel/test_observer_is_read_only.py` asserts that inference with and without an
  observer yields identical results and identical failures.

No operation signature, no unification rule, and no acceptance/rejection decision changes. The
K0 operation table is untouched.

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
- An analyzer that needs a per-occurrence type cannot get it from the graph, by construction.
  It must work from the term, and that limitation is honest about what a shared-node DAG can
  represent.
- The ambiguity is reported, so it can be measured. If it turns out to be common in practice
  rather than a corner case, splitting nodes by type becomes worth reconsidering — but that
  would be a deliberate change to node identity, with its own ADR.

## Revisit trigger

If `TypingReport.ambiguous` is non-empty for a material fraction of real candidate programs,
reopen the node-identity question.
