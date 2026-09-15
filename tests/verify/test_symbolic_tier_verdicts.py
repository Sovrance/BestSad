"""BEST-VERIF-02 acceptance test 5: the symbolic tier's verdicts, and what each one carries.

* identical canonical hashes still short-circuit at Tier 1 (unchanged);
* two syntactically different, semantically equal programs -- commutative reordering, which
  `canonicalize.py` deliberately does not normalise -- reach `EQUIV_SYMBOLIC` with the bounded
  assumptions listed and no dynamic fallback;
* a planted incorrect pair yields `NON_EQUIV` with a counterexample that re-executes;
* an ADR-0014 lowering obligation that sampled evidence could not discharge under
  `require_proof=True` now can, because the proof exists.
"""

from __future__ import annotations

from bestsad.bsir import EquivalenceContract, equivalent
from bestsad.bsir.equivalence import SYMBOLIC_OBLIGATION
from bestsad.kernel import BOOL, INT, Kernel, Program, TList, app, const_int, lam, var
from bestsad.verify.smt.bounds import FUEL_ASSUMPTION

from conftest import prog, requires_solver

requires_solver()

X = var("x")


def test_identical_hashes_short_circuit_at_tier_one(contract):
    a = prog(app("add", X, const_int(1)))
    b = Program((("y", INT),), app("add", var("y"), const_int(1)), INT)
    result = equivalent(a, b, contract, require_proof=True)
    assert result.verdict == "EQUIV_CANONICAL"
    assert "verification_score" not in result.detail, "Tier 1 ran no solver"


def test_commuted_operands_are_proved_equivalent_with_the_bounds_listed(contract):
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", const_int(1), X))
    result = equivalent(a, b, contract, require_proof=True)
    assert result.verdict == "EQUIV_SYMBOLIC"
    assert result.is_proof and result.is_equivalent
    assert FUEL_ASSUMPTION in result.assumptions
    assert "list_length_le_8" in result.assumptions
    assert SYMBOLIC_OBLIGATION not in result.unresolved, "the obligation is discharged"
    assert result.evidence_refs, "the analyzer-result record must be referenced"
    assert result.left_semantic_root != result.right_semantic_root


def test_an_integer_only_proof_is_exhaustive_and_a_list_proof_is_bounded(contract):
    ints = equivalent(prog(app("add", X, const_int(1))), prog(app("add", const_int(1), X)),
                      contract, require_proof=True)
    assert ints.detail["verification_score"]["verification_coverage"] == 1.0

    inc = lam((("v", INT),), app("add", var("v"), const_int(1)))
    inc2 = lam((("v", INT),), app("add", const_int(1), var("v")))
    xs = var("xs")
    lists = equivalent(
        Program((("xs", TList(INT)),), app("map", inc, xs), TList(INT)),
        Program((("xs", TList(INT)),), app("map", inc2, xs), TList(INT)),
        contract, require_proof=True,
    )
    assert lists.verdict == "EQUIV_SYMBOLIC"
    assert lists.detail["verification_score"]["verification_coverage"] == 8 / 4096
    assert "list_bound" in lists.detail["verification_score"]["coverage_basis"]


def test_a_planted_incorrect_pair_yields_a_witness_that_reproduces(contract):
    a = prog(app("add", X, const_int(1)))
    b = prog(app("add", X, const_int(2)))
    result = equivalent(a, b, contract, require_proof=True)
    assert result.verdict == "NON_EQUIV"
    assert result.counterexample is not None
    assert result.counterexample.kind == "DIVERGENT_RESULT"
    assert result.counterexample.detail["reExecutedOnReference"] is True
    inputs = tuple(int(i) for i in result.counterexample.witness["inputs"])
    kernel = Kernel()
    assert not kernel.execute(a, inputs).same_outcome(kernel.execute(b, inputs))


def test_a_proof_is_never_downgraded_to_sampling(contract):
    """With a proof demanded and the solver unable to help, the answer is UNKNOWN -- not the
    dynamic verdict relabelled."""
    from bestsad.kernel.types import TFun

    a = Program((("f", TFun((INT,), INT)),), const_int(1), INT)
    b = Program((("f", TFun((INT,), INT)),), const_int(1), INT)
    b = Program((("f", TFun((INT,), INT)),), app("add", const_int(0), const_int(1)), INT)
    result = equivalent(a, b, contract, require_proof=True)
    assert result.verdict == "UNKNOWN"
    assert SYMBOLIC_OBLIGATION in result.unresolved


def test_the_lowering_obligation_that_sampling_could_not_discharge_now_can():
    """ADR-0014: the commuted descriptor in `tests/languages/test_bsld_lowering.py` agrees with
    its reference on every input, but `discharge_with(require_proof=True)` refused the sampled
    evidence. With the symbolic tier the obligation is discharged by a proof."""
    from bestsad.languages import LOWERING_EQUIVALENCE, SourceProgram, lower, parse, s, seal

    commuted = parse(seal({"version": 1, "operations": {
        "inc": {
            "operands": ["Int"], "result": "Int", "effects": ["Pure"],
            "lowers_to": {"op": "add", "args": [{"op": "const_int", "attrs": {"value": 1}}, "$0"]},
            "proof_obligations": [LOWERING_EQUIVALENCE],
        }
    }}))
    contract = EquivalenceContract(input_domain_ref="int:small-enumerated")
    source = SourceProgram((("x", INT),), s("inc", s("var", name="x")), INT)
    reference = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)

    lowered = lower(source, commuted)
    proof = equivalent(lowered.program, reference, contract, require_proof=True)
    assert proof.verdict == "EQUIV_SYMBOLIC"
    settled = lowered.discharge_with(LOWERING_EQUIVALENCE, proof, require_proof=True)
    assert settled.is_fully_discharged
    assert settled.discharged[LOWERING_EQUIVALENCE] == "EQUIV_SYMBOLIC"


def test_the_lying_descriptor_is_still_caught_by_the_symbolic_tier():
    from bestsad.languages import LOWERING_EQUIVALENCE, LoweringError, SourceProgram, lower, parse, s, seal

    lying = parse(seal({"version": 1, "operations": {
        "inc": {
            "operands": ["Int"], "result": "Int", "effects": ["Pure"],
            "lowers_to": {"op": "sub", "args": ["$0", {"op": "const_int", "attrs": {"value": 1}}]},
            "proof_obligations": [LOWERING_EQUIVALENCE],
        }
    }}))
    contract = EquivalenceContract(input_domain_ref="int:small-enumerated")
    source = SourceProgram((("x", INT),), s("inc", s("var", name="x")), INT)
    reference = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
    lowered = lower(source, lying)
    verdict = equivalent(lowered.program, reference, contract, require_proof=True)
    assert verdict.verdict == "NON_EQUIV"
    try:
        lowered.discharge_with(LOWERING_EQUIVALENCE, verdict, require_proof=True)
    except LoweringError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a NON_EQUIV verdict discharged an obligation")


def test_bool_only_domains_are_exhaustive(contract):
    b = var("b")
    a = Program((("b", BOOL),), app("and", b, b), BOOL)
    c = Program((("b", BOOL),), app("or", b, b), BOOL)
    result = equivalent(a, c, contract, require_proof=True)
    assert result.verdict == "EQUIV_SYMBOLIC"
    assert result.detail["verification_score"]["verification_coverage"] == 1.0
