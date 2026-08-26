"""BS-SRE-001 acceptance: tiered equivalence never reports false equality (design §7.3).

The Phase 1 acceptance gates are:

* two syntactically different programs lower to the same canonical BSIR and report
  EQUIV_CANONICAL;
* different programs report NON_EQUIV or UNKNOWN, never false equality.
"""

from __future__ import annotations

import unittest

from bestsad.bsir import EquivalenceContract, canonical_equivalent, equivalent, get_projection
from bestsad.bsir.equivalence import SYMBOLIC_OBLIGATION
from bestsad.kernel import BOOL, INT, Kernel, Program, app, const_int, lam, var

CONTRACT = EquivalenceContract(input_domain_ref="int:small-enumerated")


def prog(body, params=(("x", INT),), result=INT) -> Program:
    return Program(params=params, body=body, result_type=result)


class CanonicalTier(unittest.TestCase):
    def test_alpha_variants_are_canonically_equivalent(self):
        a = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        b = Program((("y", INT),), app("add", var("y"), const_int(1)), INT)
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "EQUIV_CANONICAL")
        self.assertTrue(r.is_proof)
        self.assertTrue(r.is_equivalent)

    def test_surface_distinct_projections_reach_the_same_canonical_bsir(self):
        """Acceptance gate 1. Four different surface renderings of one program, parsed back
        and compared: all one canonical semantic root."""
        p = prog(app("add", var("x"), const_int(1)))
        roots = set()
        for name in ("sexpr", "compact", "human", "graph"):
            projection = get_projection(name)
            back = projection.parse(projection.render(p.body))
            roots.add(equivalent(p, prog(back), CONTRACT).left_semantic_root)
            self.assertEqual(equivalent(p, prog(back), CONTRACT).verdict, "EQUIV_CANONICAL")
        self.assertEqual(len(roots), 1)

    def test_primitive_and_its_expansion_are_canonically_equivalent(self):
        """Primitives are macros over K0, so a primitive and its expansion are one semantic
        object -- otherwise promoting an abstraction would re-identify every program using it."""
        kernel = Kernel({"prim:inc": (("n",), app("add", var("n"), const_int(1)))})
        a = prog(app("prim:inc", var("x")))
        b = prog(app("add", var("x"), const_int(1)))
        self.assertTrue(canonical_equivalent(a, b, kernel))
        self.assertEqual(equivalent(a, b, CONTRACT, kernel=kernel).verdict, "EQUIV_CANONICAL")


class NonEquivalenceCarriesAWitness(unittest.TestCase):
    def test_different_programs_are_non_equiv_with_a_counterexample(self):
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", var("x"), const_int(2)))
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "NON_EQUIV")
        self.assertFalse(r.is_equivalent)
        self.assertIsNotNone(r.counterexample)
        self.assertEqual(r.counterexample.kind, "DIVERGENT_RESULT")
        self.assertIn("inputs", r.counterexample.witness)

    def test_a_trap_difference_is_classified_as_a_trap_divergence(self):
        # div traps on zero; the constant does not. The witness must say so.
        a = prog(app("div", const_int(1), var("x")))
        b = prog(const_int(0))
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "NON_EQUIV")
        self.assertEqual(r.counterexample.kind, "DIVERGENT_TRAP")

    def test_the_witness_actually_distinguishes_the_two_programs(self):
        """A counterexample that does not reproduce is worse than none, so it is replayed."""
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("mul", var("x"), const_int(3)))
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "NON_EQUIV")
        inputs = tuple(int(i) for i in r.counterexample.witness["inputs"])
        kernel = Kernel()
        self.assertFalse(
            kernel.execute(a, inputs).same_outcome(kernel.execute(b, inputs)),
            "the reported witness does not distinguish the programs",
        )


class DynamicTierIsNotAProof(unittest.TestCase):
    def test_commuted_operands_sample_as_dynamic_not_canonical(self):
        """`add(x,1)` and `add(1,x)` agree on every input, but canonicalization deliberately
        does not reorder commutative operands (strict left-to-right evaluation makes it unsound
        in general). The verdict must therefore be EQUIV_DYNAMIC -- equivalent, but on sampled
        evidence, and explicitly not a proof."""
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", const_int(1), var("x")))
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "EQUIV_DYNAMIC")
        self.assertTrue(r.is_equivalent)
        self.assertFalse(r.is_proof, "sampled agreement must not be reported as proof")
        self.assertIn(SYMBOLIC_OBLIGATION, r.unresolved)
        self.assertGreater(r.detail["cases"], 0)

    def test_requiring_proof_returns_unknown_rather_than_downgrading_silently(self):
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", const_int(1), var("x")))
        r = equivalent(a, b, CONTRACT, require_proof=True)
        self.assertEqual(r.verdict, "UNKNOWN")
        self.assertFalse(r.is_equivalent)
        self.assertIn(SYMBOLIC_OBLIGATION, r.unresolved)


class UnknownIsNotEquality(unittest.TestCase):
    def test_unenumerable_domain_is_unknown_not_equivalent(self):
        """Nothing was sampled, so nothing is known. The one outcome that must never appear
        here is an equivalence verdict."""
        from bestsad.kernel.types import TFun

        a = Program((("f", TFun((INT,), INT)),), const_int(1), INT)
        b = Program((("f", TFun((INT,), INT)),), const_int(2), INT)
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "UNKNOWN")
        self.assertFalse(r.is_equivalent)

    def test_mismatched_parameter_lists_are_unknown(self):
        a = Program((("x", INT),), const_int(1), INT)
        b = Program((("x", INT), ("y", INT)), const_int(1), INT)
        r = equivalent(a, b, CONTRACT)
        self.assertEqual(r.verdict, "UNKNOWN")
        self.assertFalse(r.is_equivalent)

    def test_no_verdict_claims_equality_without_evidence(self):
        """The sweep this whole module exists for: across a mixed batch, every EQUIV_* verdict
        must be backed by either identical canonical roots or an actual executed sample."""
        pairs = [
            (prog(app("add", var("x"), const_int(1))), prog(app("add", var("x"), const_int(1)))),
            (prog(app("add", var("x"), const_int(1))), prog(app("add", const_int(1), var("x")))),
            (prog(app("add", var("x"), const_int(1))), prog(app("sub", var("x"), const_int(1)))),
            (prog(app("mul", var("x"), const_int(0))), prog(const_int(0))),
            (prog(app("div", var("x"), const_int(0))), prog(const_int(0))),
        ]
        for left, right in pairs:
            r = equivalent(left, right, CONTRACT)
            with self.subTest(verdict=r.verdict):
                if r.verdict == "EQUIV_CANONICAL":
                    self.assertEqual(r.left_semantic_root, r.right_semantic_root)
                elif r.verdict == "EQUIV_DYNAMIC":
                    self.assertGreater(r.detail["cases"], 0)
                    self.assertNotEqual(r.left_semantic_root, r.right_semantic_root)
                else:
                    self.assertIn(r.verdict, ("NON_EQUIV", "UNKNOWN"))


class WireForm(unittest.TestCase):
    def test_result_validates_against_the_shared_schema(self):
        from bestsad import sre

        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", var("x"), const_int(2)))
        r = equivalent(a, b, CONTRACT)
        sre.validate("EquivalenceResult", r.to_wire())
        sre.validate("Counterexample", r.counterexample.to_wire())

    def test_counterexample_ref_is_null_when_there_is_no_counterexample(self):
        from bestsad import sre

        a = prog(app("add", var("x"), const_int(1)))
        r = equivalent(a, a, CONTRACT)
        wire = r.to_wire()
        self.assertIsNone(wire["counterexampleRef"])
        sre.validate("EquivalenceResult", wire)


if __name__ == "__main__":
    unittest.main()


class ComputeIsMetered(unittest.TestCase):
    """Codex review, P1: dynamic comparisons execute programs, and that compute must be
    charged. Unmetered, it sits outside total experimental compute and breaks the compute
    matching condition I depends on."""

    def test_dynamic_comparison_charges_kernel_steps(self):
        from bestsad.conditions import ComputeLedger

        ledger = ComputeLedger(run_id="r", condition_id="c", seed=0)
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", const_int(1), var("x")))
        result = equivalent(a, b, CONTRACT, ledger=ledger)

        self.assertEqual(result.verdict, "EQUIV_DYNAMIC")
        self.assertGreater(ledger.kernel_steps, 0)
        # Both sides run on every case.
        self.assertEqual(ledger.verifier_steps, 2 * result.detail["cases"])

    def test_a_counterexample_still_charges_the_steps_already_spent(self):
        from bestsad.conditions import ComputeLedger

        ledger = ComputeLedger(run_id="r", condition_id="c", seed=0)
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", var("x"), const_int(2)))
        result = equivalent(a, b, CONTRACT, ledger=ledger)

        self.assertEqual(result.verdict, "NON_EQUIV")
        self.assertGreater(ledger.kernel_steps, 0, "steps before a divergence are still spent")

    def test_the_canonical_tier_executes_nothing_and_charges_nothing(self):
        from bestsad.conditions import ComputeLedger

        ledger = ComputeLedger(run_id="r", condition_id="c", seed=0)
        a = prog(app("add", var("x"), const_int(1)))
        self.assertEqual(equivalent(a, a, CONTRACT, ledger=ledger).verdict, "EQUIV_CANONICAL")
        self.assertEqual(ledger.kernel_steps, 0)

    def test_omitting_the_ledger_still_works(self):
        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", const_int(1), var("x")))
        self.assertEqual(equivalent(a, b, CONTRACT).verdict, "EQUIV_DYNAMIC")


class WireCarriesTheStrengthOfTheEvidence(unittest.TestCase):
    """Codex review, P2: `scope.sampleSize` is a budget, not what ran."""

    def test_executed_case_count_reaches_the_wire(self):
        from bestsad import sre
        from bestsad.kernel import BOOL

        # One Bool parameter enumerates two cases against a default budget of 64.
        a = Program((("b", BOOL),), app("and", var("b"), var("b")), BOOL)
        b = Program((("b", BOOL),), app("or", var("b"), var("b")), BOOL)
        result = equivalent(a, b, CONTRACT)
        wire = result.to_wire()

        self.assertEqual(result.verdict, "EQUIV_DYNAMIC")
        self.assertEqual(wire["scope"]["sampleSize"], 64)
        self.assertEqual(wire["scope"]["casesExecuted"], 2)
        self.assertNotEqual(
            wire["scope"]["casesExecuted"], wire["scope"]["sampleSize"],
            "this fixture exists precisely because the two differ",
        )
        sre.validate("EquivalenceResult", wire)

    def test_open_obligations_reach_the_wire(self):
        from bestsad.bsir.equivalence import SYMBOLIC_OBLIGATION

        a = prog(app("add", var("x"), const_int(1)))
        b = prog(app("add", const_int(1), var("x")))
        wire = equivalent(a, b, CONTRACT).to_wire()
        self.assertIn(SYMBOLIC_OBLIGATION, wire["scope"]["unresolvedObligations"])

    def test_a_canonical_verdict_advertises_no_sampling(self):
        a = prog(app("add", var("x"), const_int(1)))
        wire = equivalent(a, a, CONTRACT).to_wire()
        self.assertNotIn("casesExecuted", wire["scope"])
        self.assertNotIn("unresolvedObligations", wire["scope"])
