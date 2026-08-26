"""Tiered semantic equivalence (design §7.3).

The rule this module exists to enforce: **canonical-hash equality, solver proof, and sampled
agreement are three different claims and must never be reported as one.**

    EQUIV_CANONICAL   both programs normalize to identical trusted BSIR
    EQUIV_SYMBOLIC    a solver proved equal outcomes within a declared contract
    EQUIV_DYNAMIC     sampling found no divergence over a declared distribution
    NON_EQUIV         a concrete input distinguishes them -- with the witness attached
    UNKNOWN           resources, unsupported semantics, or ambiguity prevent resolution

`EQUIV_DYNAMIC` is evidence, not proof, and the object says so: it carries the sample size and
the domain it sampled, so a reader can see exactly how weak or strong the claim is. Anything
this module cannot settle is `UNKNOWN`, never a quiet upgrade to equality. The direction of
that bias matters — a false `NON_EQUIV` costs a wasted investigation, while a false
`EQUIV_CANONICAL` silently merges two different programs' identities.

`EQUIV_SYMBOLIC` is declared here but not produced: the solver adapter is P1 work
(`analysis/symbolic.py`). Until it exists, a request for symbolic evidence returns `UNKNOWN`
with the obligation left open rather than falling back to sampling and relabelling the result.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from ..kernel.interpreter import ExecutionResult, Kernel
from ..kernel.terms import Program
from ..kernel.types import BOOL, INT, TList, TOption, TTuple, Ty
from ..sre.ids import as_content_id, with_content_id
from ..sre.objects import Counterexample, Verdict
from .canonicalize import semantic_hash

#: The obligation a symbolic tier would have to discharge, recorded when it cannot.
SYMBOLIC_OBLIGATION = "symbolic_equivalence_unproven"


@dataclass(frozen=True, slots=True)
class EquivalenceContract:
    """The declared scope of an equivalence question (design §6, BestSad interface contracts).

    A verdict is meaningless without it: "these agree" is only a claim once you say on what
    inputs, observing what, and under what budget. `input_domain_ref` and
    `observable_contract_ref` are names of declared contracts rather than the contracts
    themselves, so a verdict can be re-checked against the same domain later.
    """

    input_domain_ref: str
    observable_contract_ref: str = "outcome:value-or-trap-kind"
    allowed_effects: frozenset[str] = frozenset({"Pure", "Trap"})
    max_steps: int | None = None
    solver_scope: str | None = None
    sample_size: int = 64

    def to_wire(self) -> dict[str, Any]:
        return {
            "inputDomainRef": self.input_domain_ref,
            "observableContractRef": self.observable_contract_ref,
            "allowedEffects": sorted(self.allowed_effects),
            "maxSteps": self.max_steps,
            "solverScope": self.solver_scope,
            "sampleSize": self.sample_size,
        }


@dataclass(frozen=True, slots=True)
class EquivalenceResult:
    """A verdict plus everything needed to judge how much it is worth."""

    left_semantic_root: str
    right_semantic_root: str
    verdict: Verdict
    contract: EquivalenceContract
    assumptions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    counterexample: Counterexample | None = None
    unresolved: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_equivalent(self) -> bool:
        """True only for a tier that actually asserts equivalence.

        `UNKNOWN` is not equivalence and neither is `NON_EQUIV`; both return False, and a
        caller wanting to distinguish "no" from "don't know" must read `verdict`.
        """
        return self.verdict in ("EQUIV_CANONICAL", "EQUIV_SYMBOLIC", "EQUIV_DYNAMIC")

    @property
    def is_proof(self) -> bool:
        """True only where the verdict is a proof rather than sampled evidence."""
        return self.verdict in ("EQUIV_CANONICAL", "EQUIV_SYMBOLIC")

    def to_wire(self) -> dict[str, Any]:
        # `scope.sampleSize` is the contract's *budget*, not what ran. The enumerated domain
        # is often smaller -- a single Bool parameter yields two cases against a budget of 64
        # -- so a consumer reading only the scope would badly overestimate the evidence. The
        # executed count and any open obligations therefore travel with the verdict.
        scope = dict(self.contract.to_wire())
        if "cases" in self.detail:
            scope["casesExecuted"] = self.detail["cases"]
        if self.unresolved:
            scope["unresolvedObligations"] = list(self.unresolved)
        payload: dict[str, Any] = {
            "left": as_content_id(self.left_semantic_root),
            "right": as_content_id(self.right_semantic_root),
            "verdict": self.verdict,
            "scope": scope,
            "evidenceRefs": list(self.evidence_refs),
        }
        if self.assumptions:
            payload["assumptions"] = list(self.assumptions)
        payload["counterexampleRef"] = (
            self.counterexample.id if self.counterexample is not None else None
        )
        return with_content_id(payload)

    @property
    def id(self) -> str:
        from ..sre.ids import content_id

        return content_id(self.to_wire())


# -- input domains ---------------------------------------------------------------------------


def _small_ints() -> Iterable[int]:
    """Values chosen for where K0 actually breaks: zero and one for divisors and identities,
    negatives for truncation direction, and a large magnitude for overflow traps."""
    return (0, 1, -1, 2, -2, 3, 7, -7, 10, 100, -100, 2**30, -(2**30))


def enumerate_domain(types: Sequence[Ty], limit: int) -> list[tuple[Any, ...]]:
    """Deterministic input tuples for a parameter list.

    Deterministic on purpose: an equivalence verdict has to be reproducible from the contract
    alone, and a randomly sampled domain makes "we found no divergence" un-recheckable.
    Returns an empty list for a type this enumerator does not cover, which the caller must
    treat as UNKNOWN rather than as agreement.
    """
    per_param: list[list[Any]] = []
    for ty in types:
        values = _values_for(ty)
        if not values:
            return []
        per_param.append(values)
    if not per_param:
        return [()]
    return list(itertools.islice(itertools.product(*per_param), limit))


def _values_for(ty: Ty) -> list[Any]:
    if ty == INT:
        return list(_small_ints())
    if ty == BOOL:
        return [True, False]
    if isinstance(ty, TList):
        elems = _values_for(ty.elem)
        if not elems:
            return []
        return [(), (elems[0],), tuple(elems[:3])]
    if isinstance(ty, TOption):
        from ..kernel.values import NOTHING, Just

        elems = _values_for(ty.elem)
        return [NOTHING] + ([Just(elems[0])] if elems else [])
    if isinstance(ty, TTuple):
        from ..kernel.values import Pair

        fst, snd = _values_for(ty.fst), _values_for(ty.snd)
        if not fst or not snd:
            return []
        return [Pair(fst[0], snd[0])]
    # TFun and TVar: not enumerable here. Empty means "cannot sample", not "no values".
    return []


# -- the tiers -------------------------------------------------------------------------------


def _outcome_wire(result: ExecutionResult) -> dict[str, Any]:
    from ..kernel.values import render

    if result.trap is not None:
        return {"trap": result.trap.kind.value}
    return {"value": render(result.value)}


def equivalent(
    left: Program,
    right: Program,
    contract: EquivalenceContract,
    *,
    kernel: Kernel | None = None,
    require_proof: bool = False,
    domain: Sequence[tuple[Any, ...]] | None = None,
    ledger: Any | None = None,
) -> EquivalenceResult:
    """Decide equivalence at the strongest tier the available evidence supports.

    Order is deliberate: canonical first because it is free and it is a proof; then, only if
    the caller did not demand a proof, dynamic sampling. A `NON_EQUIV` found during sampling
    always wins over `UNKNOWN`, because a witness is a fact regardless of what tier was being
    attempted.

    `ledger`, when given a `conditions.compute.ComputeLedger`, is charged for the kernel steps
    this verifier actually spends. The dynamic tier executes *both* programs on every sampled
    case, which is real compute: unmetered, it would sit outside total experimental compute and
    quietly break the compute matching that condition I depends on (AGENTS.md, definition of
    done). The canonical tier costs no kernel steps and charges nothing.
    """
    left_root = semantic_hash(left, kernel)
    right_root = semantic_hash(right, kernel)

    def result(verdict: Verdict, **kw: Any) -> EquivalenceResult:
        return EquivalenceResult(left_root, right_root, verdict, contract, **kw)

    # Tier 1: canonical. Identical normalized BSIR is identical semantics by construction.
    if left_root == right_root:
        return result("EQUIV_CANONICAL", detail={"basis": "identical canonical semantic hash"})

    # Differing hashes prove nothing on their own -- normalization is deliberately incomplete
    # (see canonicalize.py on commutative reordering), so two hashes can differ for programs
    # that agree everywhere. Fall through rather than concluding.

    if require_proof:
        # The symbolic tier is not implemented. Say so, and leave the obligation open, rather
        # than sampling and calling the result a proof.
        return result(
            "UNKNOWN",
            unresolved=(SYMBOLIC_OBLIGATION,),
            detail={"reason": "symbolic solver adapter is not implemented (P1)"},
        )

    # Tier 3: dynamic. Sampling can refute, and can support, but never proves.
    if left.params != right.params:
        return result(
            "UNKNOWN",
            detail={"reason": "parameter lists differ; no shared input domain"},
        )

    cases = list(domain) if domain is not None else enumerate_domain(
        tuple(t for _, t in left.params), contract.sample_size
    )
    if not cases:
        return result(
            "UNKNOWN",
            detail={"reason": "input domain is not enumerable for these parameter types"},
        )

    k = kernel if kernel is not None else Kernel()
    spent = 0
    executions = 0
    for inputs in cases:
        lr = k.execute(left, inputs, fuel=contract.max_steps)
        rr = k.execute(right, inputs, fuel=contract.max_steps)
        spent += lr.fuel_used + rr.fuel_used
        executions += 2
        if not lr.same_outcome(rr):
            _charge(ledger, spent, executions)
            kind = (
                "DIVERGENT_TRAP"
                if (lr.trap is not None or rr.trap is not None)
                else "DIVERGENT_RESULT"
            )
            witness = Counterexample(
                kind=kind,
                witness={"inputs": [repr(i) for i in inputs]},
                left_outcome=_outcome_wire(lr),
                right_outcome=_outcome_wire(rr),
            )
            return result(
                "NON_EQUIV",
                counterexample=witness,
                detail={"cases": cases.index(inputs) + 1, "kernel_steps": spent},
            )

    _charge(ledger, spent, executions)
    return result(
        "EQUIV_DYNAMIC",
        unresolved=(SYMBOLIC_OBLIGATION,),
        detail={
            "cases": len(cases),
            "kernel_steps": spent,
            "basis": "no divergence over the declared domain; evidence, not proof",
        },
    )


def _charge(ledger: Any | None, kernel_steps: int, executions: int) -> None:
    """Charge a dynamic comparison's kernel usage to a compute ledger, when one is supplied.

    Charged on every exit from the sampling loop, including the early one a counterexample
    takes -- steps spent before a divergence is found are spent all the same.
    """
    if ledger is None:
        return
    ledger.add(
        kernel_steps=kernel_steps,
        verifier_steps=executions,
        candidate_evaluations=executions,
    )


def canonical_equivalent(left: Program, right: Program, kernel: Kernel | None = None) -> bool:
    """The canonical tier alone, as a predicate.

    Callers that need a proof should use this rather than truth-testing an
    `EquivalenceResult`, so that a dynamic verdict cannot be mistaken for a canonical one.
    """
    return semantic_hash(left, kernel) == semantic_hash(right, kernel)
