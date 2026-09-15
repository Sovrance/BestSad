"""Non-vacuity of specifications (BEST-VERIF-04; design §2.2).

The trust hole this closes: a contract is untrusted whoever wrote it -- a coding agent, an LLM,
a person -- and a proposer who can write the contract can write one that accepts everything.
`max_steps=0` is the simplest: every execution exhausts fuel, fuel is excluded from the
symbolic tier by assumption (ADR-0019), and the solver then proves any two programs equal
*under that assumption*, honestly and uselessly.

**Rule.** No solver-backed `EQUIV_SYMBOLIC` is promotable unless the *same contract* has
produced `NON_EQUIV` against at least one **mutant** of the program pair. Mutants are generated
deterministically from a seed by single-op substitution within the same type signature --
`lt -> le`, `add -> sub`, swapping the branches of an `if`, perturbing a literal, swapping two
parameters of one type -- and each must typecheck and must not canonicalise to the original.
If every mutant is also reported equivalent, the contract is **vacuous** and the claim is
refused with reason `contract_vacuous`.

Only `NON_EQUIV` counts as a refutation. `UNKNOWN` on a mutant -- a timeout, a witness the
assumptions exclude -- is not evidence that the contract can tell programs apart, and counting
it would let the very contracts this control exists to catch pass on the strength of their own
unanswerable questions.

This is ADR-0014's "a deliberately incorrect lowering is a testable fixture" generalised to
every solver-backed claim: the fixture is generated rather than hand-written, and it is run
before the verdict may be believed rather than once when the descriptor format was designed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Sequence

from ..bsir.canonicalize import semantic_hash
from ..bsir.equivalence import EquivalenceContract, EquivalenceResult, equivalent
from ..kernel.interpreter import Kernel
from ..kernel.terms import Program, Term, const_bool, const_int, var
from ..kernel.typecheck import is_well_typed
from ..sre.ids import as_content_id
from ..sre.objects import Fact, Producer

PRODUCER = Producer("bestsad.verify.vacuity", "0.1.0")
REASON_VACUOUS = "contract_vacuous"
PREDICATE = "contract_non_vacuous"

#: Same-signature substitutions. Every alternative has the operand and result types of the
#: original, so the mutant typechecks by construction wherever the original did.
SUBSTITUTIONS: dict[str, tuple[str, ...]] = {
    "add": ("sub", "mul"), "sub": ("add", "mul"), "mul": ("add", "sub"),
    "div": ("mod",), "mod": ("div",),
    "min": ("max",), "max": ("min",), "neg": ("abs",), "abs": ("neg",),
    "lt": ("le", "ge"), "le": ("lt", "gt"), "gt": ("ge", "le"), "ge": ("gt", "lt"),
    "and": ("or",), "or": ("and",),
}

#: Operations whose two operands may be swapped; the swap is typed-checked afterwards, so
#: `tuple`/`fst`/`snd` swaps survive only when both components share a type.
SWAPS: frozenset[str] = frozenset({"append", "tuple", "if"})


class ContractVacuous(Exception):
    """The contract accepts every mutant: it distinguishes nothing, so it proves nothing."""


@dataclass(frozen=True, slots=True)
class Mutant:
    description: str
    program: Program


@dataclass(frozen=True, slots=True)
class VacuityRecord:
    """What the check did and found. Serialises to an SRE `Fact` so it can be referenced from
    the claim's `evidenceRefs` and validated by any consumer."""

    non_vacuous: bool
    left_root: str
    right_root: str
    contract: EquivalenceContract
    seed: int
    verdicts: tuple[tuple[str, str], ...]
    refuting_mutant: str | None
    evidence_refs: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def mutants_tried(self) -> int:
        return len(self.verdicts)

    @property
    def reason(self) -> str | None:
        return None if self.non_vacuous else REASON_VACUOUS

    def to_fact(self) -> Fact:
        return Fact(
            predicate=PREDICATE,
            status="SUPPORTED" if self.non_vacuous else "CONTRADICTED",
            producer=PRODUCER,
            inputs=(as_content_id(self.left_root), as_content_id(self.right_root)),
            assumptions=(),
            evidence_refs=self.evidence_refs,
            detail={
                "contract": self.contract.to_wire(),
                "seed": self.seed,
                "mutantsTried": self.mutants_tried,
                "verdicts": [{"mutant": d, "verdict": v} for d, v in self.verdicts],
                "refutingMutant": self.refuting_mutant,
                **({"reason": REASON_VACUOUS} if not self.non_vacuous else {}),
                **self.detail,
            },
        )

    def to_wire(self) -> dict[str, Any]:
        return self.to_fact().to_wire()

    @property
    def id(self) -> str:
        return self.to_fact().id


# -- mutation -----------------------------------------------------------------------------------


def _replace_at(term: Term, path: tuple[int, ...], new: Term) -> Term:
    if not path:
        return new
    head, *rest = path
    args = list(term.args)
    args[head] = _replace_at(args[head], tuple(rest), new)
    return Term(term.op, tuple(args), term.attrs)


def _sites(term: Term, path: tuple[int, ...] = ()) -> Iterator[tuple[tuple[int, ...], Term]]:
    yield path, term
    for i, arg in enumerate(term.args):
        yield from _sites(arg, path + (i,))


def _candidates(program: Program) -> Iterator[Mutant]:
    """Every single-site mutation, in a fixed order, untyped and unfiltered."""
    params = dict(program.params)
    for path, node in _sites(program.body):
        where = f"at {'/'.join(map(str, path)) or 'root'}"
        op = node.op
        for alternative in SUBSTITUTIONS.get(op, ()):
            yield Mutant(f"{op}->{alternative} {where}",
                         replace(program, body=_replace_at(program.body, path, Term(alternative, node.args, node.attrs))))
        if op in SWAPS and len(node.args) >= 2:
            if op == "if":
                swapped = Term("if", (node.args[0], node.args[2], node.args[1]), node.attrs)
                yield Mutant(f"if-branches-swapped {where}",
                             replace(program, body=_replace_at(program.body, path, swapped)))
            else:
                swapped = Term(op, (node.args[1], node.args[0]), node.attrs)
                yield Mutant(f"{op}-operands-swapped {where}",
                             replace(program, body=_replace_at(program.body, path, swapped)))
        if op == "const_int":
            value = node.attr("value")
            yield Mutant(f"const_int {value}->{value + 1} {where}",
                         replace(program, body=_replace_at(program.body, path, const_int(value + 1))))
        if op == "const_bool":
            value = node.attr("value")
            yield Mutant(f"const_bool {value}->{not value} {where}",
                         replace(program, body=_replace_at(program.body, path, const_bool(not value))))
        if op == "var":
            name = node.attr("name")
            if name in params:
                for other, ty in program.params:
                    if other != name and ty == params[name]:
                        yield Mutant(f"var {name}->{other} {where}",
                                     replace(program, body=_replace_at(program.body, path, var(other))))


def mutants(program: Program, *, seed: int = 0, limit: int = 6,
            kernel: Kernel | None = None) -> list[Mutant]:
    """Up to `limit` well-typed mutants of `program`, chosen deterministically from `seed`.

    A candidate that fails to typecheck, or that canonicalises to the original (`x + 0` with
    `add -> sub`, say), is not a mutant and is dropped.
    """
    original = semantic_hash(program, kernel)
    pool = list(_candidates(program))
    random.Random(seed).shuffle(pool)
    out: list[Mutant] = []
    seen: set[str] = set()
    for candidate in pool:
        if not is_well_typed(candidate.program):
            continue
        root = semantic_hash(candidate.program, kernel)
        if root == original or root in seen:
            continue
        seen.add(root)
        out.append(candidate)
        if len(out) >= limit:
            break
    return out


# -- the check ----------------------------------------------------------------------------------


def non_vacuity(
    left: Program,
    right: Program,
    contract: EquivalenceContract,
    *,
    kernel: Kernel | None = None,
    ledger: Any | None = None,
    seed: int = 0,
    limit: int = 6,
) -> VacuityRecord:
    """Try to refute mutants of the pair under the same contract, at the symbolic tier.

    Mutants of `left` are checked against `right`, then mutants of `right` against `left`. The
    first `NON_EQUIV` settles it; the remaining mutants are not run, since the question was
    whether the contract can distinguish *anything*, not how much.
    """
    left_root = semantic_hash(left, kernel)
    right_root = semantic_hash(right, kernel)
    verdicts: list[tuple[str, str]] = []
    evidence: list[str] = []
    refuting: str | None = None

    for side, (subject, other) in (("left", (left, right)), ("right", (right, left))):
        for mutant in mutants(subject, seed=seed, limit=limit, kernel=kernel):
            result = equivalent(mutant.program, other, contract, kernel=kernel,
                                require_proof=True, ledger=ledger)
            label = f"{side}: {mutant.description}"
            verdicts.append((label, result.verdict))
            evidence.append(result.id)
            if result.verdict == "NON_EQUIV":
                refuting = label
                break
        if refuting is not None:
            break

    return VacuityRecord(
        non_vacuous=refuting is not None,
        left_root=left_root,
        right_root=right_root,
        contract=contract,
        seed=seed,
        verdicts=tuple(verdicts),
        refuting_mutant=refuting,
        evidence_refs=tuple(evidence),
    )


def attach(result: EquivalenceResult, record: VacuityRecord) -> EquivalenceResult:
    """Attach the vacuity record to a solver-backed verdict, or refuse the verdict.

    Only `EQUIV_SYMBOLIC` needs the guard: a refutation or an `UNKNOWN` claims nothing that a
    vacuous contract could have handed out. Those pass through with the record attached.
    """
    if result.verdict == "EQUIV_SYMBOLIC" and not record.non_vacuous:
        raise ContractVacuous(
            f"{REASON_VACUOUS}: the contract reported every one of {record.mutants_tried} "
            f"mutant(s) equivalent as well ({', '.join(v for _, v in record.verdicts) or 'none tried'}); "
            "it distinguishes nothing, so its proof is not promotable"
        )
    return replace(
        result,
        evidence_refs=result.evidence_refs + (record.id,),
        detail={**result.detail, "vacuity": {
            "non_vacuous": record.non_vacuous,
            "mutants_tried": record.mutants_tried,
            "refuting_mutant": record.refuting_mutant,
            "record": record.id,
        }},
    )


def prove_non_vacuously(
    left: Program,
    right: Program,
    contract: EquivalenceContract,
    *,
    kernel: Kernel | None = None,
    ledger: Any | None = None,
    seed: int = 0,
    limit: int = 6,
) -> EquivalenceResult:
    """The entry point a promoter should use: a proof request, guarded.

    Runs the tiers with `require_proof=True`; on `EQUIV_SYMBOLIC`, runs the non-vacuity check
    under the same contract and either attaches its record or raises `ContractVacuous`. Any
    other verdict is returned as is -- a canonical proof needs no contract, and a refutation or
    an unknown asserts nothing a vacuous contract could have produced.
    """
    result = equivalent(left, right, contract, kernel=kernel, require_proof=True, ledger=ledger)
    if result.verdict != "EQUIV_SYMBOLIC":
        return result
    record = non_vacuity(left, right, contract, kernel=kernel, ledger=ledger, seed=seed, limit=limit)
    return attach(result, record)
