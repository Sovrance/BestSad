"""Descriptor-driven lowering from a described language into BSIR (design §7.2, ADR 0014).

Lowering is a substitution, not an interpretation. Each source operation names a template, the
template's `$n` slots are filled with the already-lowered operands, and the result is a K0 term.
There is no evaluation and no descriptor-supplied code, so the worst a hostile descriptor can
do is produce a K0 term that means something other than it claimed — which is precisely what
the proof obligations are for.

The obligations travel with the result. `LoweringResult.open_obligations` lists what has not
been discharged, and nothing here ever discharges an obligation on the descriptor's say-so:
`discharge_with` takes an `EquivalenceResult` and accepts it only if that result is actually an
equivalence at a tier the caller asked for. A descriptor asserting `lowering_semantic_equivalence`
in its own `proof_obligations` list does not make it true; it only names the debt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..bsir.canonicalize import semantic_hash
from ..bsir.equivalence import EquivalenceResult
from ..bsir.graph import to_graph
from ..bsir.nodes import Graph
from ..kernel.ops import OPS_BY_NAME
from ..kernel.terms import Program, Term
from .descriptor import (
    LOWERING_EQUIVALENCE,
    DescriptorError,
    LanguageDescriptor,
    LoweringTemplate,
)
from .source import SourceProgram, SourceTerm


class LoweringError(DescriptorError):
    """A source program cannot be lowered through this descriptor."""


@dataclass(frozen=True, slots=True)
class LoweringResult:
    """A lowered program plus the debts the lowering incurred."""

    program: Program
    graph: Graph
    semantic_root: str
    language_id: str
    open_obligations: tuple[str, ...] = ()
    discharged: Mapping[str, str] = field(default_factory=dict)
    lowered_ops: tuple[str, ...] = ()

    @property
    def is_fully_discharged(self) -> bool:
        return not self.open_obligations

    def discharge_with(
        self,
        obligation: str,
        evidence: EquivalenceResult,
        *,
        require_proof: bool = False,
    ) -> "LoweringResult":
        """Discharge `obligation` using an equivalence result, or refuse to.

        Three independent checks, and the third is the one that matters most:

        1. the evidence must be an equivalence verdict at all;
        2. it must be a proof, when the caller asked for one;
        3. **it must be about this lowering** -- one of its two semantic roots has to be the
           root this lowering produced.

        Without (3) the whole obligation mechanism is decorative. Any `EQUIV_CANONICAL` result
        would discharge any obligation, so `equivalent(reference, reference, contract)` --
        trivially true and about two programs that have nothing to do with the descriptor --
        would certify a lowering known to be wrong. Evidence that is not *about* the thing it
        certifies is not evidence.

        Raising rather than returning unchanged is deliberate: a caller that believes an
        obligation was met is worse off than one that gets an error.
        """
        if obligation not in self.open_obligations:
            raise LoweringError(f"{obligation!r} is not open on this lowering")
        if not evidence.is_equivalent:
            raise LoweringError(
                f"cannot discharge {obligation!r} with a {evidence.verdict} verdict"
            )
        if require_proof and not evidence.is_proof:
            raise LoweringError(
                f"cannot discharge {obligation!r} with sampled evidence "
                f"({evidence.verdict}); a proof was required"
            )
        roots = (evidence.left_semantic_root, evidence.right_semantic_root)
        if self.semantic_root not in roots:
            raise LoweringError(
                f"cannot discharge {obligation!r} with evidence about a different program: "
                f"this lowering is {self.semantic_root}, the evidence compares "
                f"{roots[0]} and {roots[1]}"
            )
        return LoweringResult(
            program=self.program,
            graph=self.graph,
            semantic_root=self.semantic_root,
            language_id=self.language_id,
            open_obligations=tuple(o for o in self.open_obligations if o != obligation),
            discharged={**self.discharged, obligation: evidence.verdict},
            lowered_ops=self.lowered_ops,
        )


def _instantiate(template: LoweringTemplate, operands: tuple[Term, ...]) -> Term:
    """Fill a template's `$n` slots with lowered operands."""
    args: list[Term] = []
    for arg in template.args:
        if isinstance(arg, str):
            index = int(arg[1:])
            try:
                args.append(operands[index])
            except IndexError:  # pragma: no cover - `parse` rejects this at descriptor load
                raise LoweringError(f"template references ${index} with {len(operands)} operands")
        else:
            args.append(_instantiate(arg, operands))
    return Term(template.op, tuple(args), template.attrs)


def lower_term(
    term: SourceTerm,
    descriptor: LanguageDescriptor,
    obligations: set[str],
    used: set[str],
) -> Term:
    """Lower one source term into K0. Binders and K0 operations keep their shape.

    The return type changing from `SourceTerm` to `Term` is the point of the function: this is
    the single crossing from surface vocabulary into canonical semantics.
    """
    if term.op == "lam":
        # A binder's body is source too, but the binder itself is structural: templates cannot
        # synthesize one, so a lam only ever arrives from the source program.
        body = lower_term(term.args[0], descriptor, obligations, used)
        return Term("lam", (body,), term.attrs)

    lowered_args = tuple(lower_term(a, descriptor, obligations, used) for a in term.args)

    if term.op in descriptor.operations:
        spec = descriptor.operation(term.op)
        if len(lowered_args) != spec.arity:
            raise LoweringError(
                f"{term.op} expects {spec.arity} operand(s), got {len(lowered_args)}"
            )
        obligations.update(spec.proof_obligations)
        used.add(term.op)
        return _instantiate(spec.lowers_to, lowered_args)

    if term.op in OPS_BY_NAME or term.op.startswith("prim:"):
        # Already K0 (or a genome primitive): a described language may use kernel operations
        # directly, and doing so incurs no lowering obligation because nothing was translated.
        return Term(term.op, lowered_args, term.attrs)

    raise LoweringError(
        f"{term.op!r} is neither an operation of language {descriptor.language_id} "
        "nor a K0 operation"
    )


def lower(
    source: SourceProgram,
    descriptor: LanguageDescriptor,
    *,
    kernel: Any | None = None,
) -> LoweringResult:
    """Lower a source program written in `descriptor`'s language into BSIR.

    The returned obligations are the union of those declared by every operation actually used,
    plus the descriptor's own. An operation that was never used contributes no debt.
    """
    obligations: set[str] = set()
    used: set[str] = set()
    body = lower_term(source.body, descriptor, obligations, used)
    program = Program(params=source.params, body=body, result_type=source.result_type)

    if used:
        obligations.update(descriptor.proof_obligations)

    return LoweringResult(
        program=program,
        graph=to_graph(program, kernel),
        semantic_root=semantic_hash(program, kernel),
        language_id=descriptor.language_id,
        open_obligations=tuple(sorted(obligations)),
        lowered_ops=tuple(sorted(used)),
    )


def check_lowering(
    descriptor: LanguageDescriptor,
    operation: str,
    reference: Program,
    sample: SourceProgram,
    contract: Any,
    *,
    kernel: Any | None = None,
) -> EquivalenceResult:
    """Compare a descriptor's lowering of `operation` against a reference implementation.

    This is how `lowering_semantic_equivalence` is actually settled (ADR 0014): the descriptor
    is asked to lower a sample program, and the result is compared against an independently
    written reference. A descriptor that lowers to the wrong K0 operation produces a
    `NON_EQUIV` with a concrete witness rather than a passing assertion.
    """
    from ..bsir.equivalence import equivalent

    lowered = lower(sample, descriptor, kernel=kernel)
    return equivalent(lowered.program, reference, contract, kernel=kernel)
