"""BS-SRE-002 acceptance: descriptor-driven lowering into BSIR.

The Phase 1 gates this file covers:

* two surface-distinct programs lower to the same canonical BSIR;
* a deliberately incorrect lowering is caught by a counterexample fixture rather than trusted.
"""

from __future__ import annotations

import unittest

from bestsad.bsir import EquivalenceContract, equivalent, semantic_hash
from bestsad.kernel import INT, Kernel, Program, app, const_int, lam, var
from bestsad.languages import (
    LOWERING_EQUIVALENCE,
    DescriptorError,
    LoweringError,
    SourceProgram,
    check_lowering,
    descriptor_id,
    lower,
    parse,
    s,
    seal,
    slam,
)

CONTRACT = EquivalenceContract(input_domain_ref="int:small-enumerated")


def descriptor(operations: dict) -> "object":
    return parse(seal({"version": 1, "operations": operations}))


#: Language A: `zq(list, fn)` -- operands in the opposite order from K0's `map`.
LANG_A = descriptor(
    {
        "zq": {
            "operands": ["List<Int>", "Int"],
            "result": "List<Int>",
            "effects": ["Pure"],
            "lowers_to": {"op": "map", "args": ["$1", "$0"]},
        }
    }
)

#: Language B: `apply_each(fn, list)` -- same meaning, different name and operand order.
LANG_B = descriptor(
    {
        "apply_each": {
            "operands": ["Int", "List<Int>"],
            "result": "List<Int>",
            "effects": ["Pure"],
            "lowers_to": {"op": "map", "args": ["$0", "$1"]},
        }
    }
)


class DescriptorIdentity(unittest.TestCase):
    def test_language_id_is_the_content_address_of_the_body(self):
        body = {
            "version": 1,
            "operations": {
                "inc": {
                    "operands": ["Int"],
                    "result": "Int",
                    "effects": ["Pure"],
                    "lowers_to": {"op": "add", "args": ["$0", {"op": "const_int", "attrs": {"value": 1}}]},
                }
            },
        }
        sealed = seal(body)
        self.assertEqual(sealed["language_id"], descriptor_id(body))
        self.assertTrue(sealed["language_id"].startswith("lang:sha256:"))

    def test_a_forged_language_id_is_rejected(self):
        sealed = seal({"version": 1, "operations": LANG_A.operations and {
            "zq": {"operands": ["List<Int>", "Int"], "result": "List<Int>",
                   "effects": ["Pure"], "lowers_to": {"op": "map", "args": ["$1", "$0"]}}}})
        tampered = {**sealed, "language_id": "lang:sha256:" + "0" * 64}
        with self.assertRaises(DescriptorError):
            parse(tampered)

    def test_renaming_an_operation_changes_the_language_id(self):
        a = descriptor_id({"version": 1, "operations": {
            "zq": {"operands": ["Int"], "result": "Int", "effects": ["Pure"],
                   "lowers_to": {"op": "add", "args": ["$0", "$0"]}}}})
        b = descriptor_id({"version": 1, "operations": {
            "qz": {"operands": ["Int"], "result": "Int", "effects": ["Pure"],
                   "lowers_to": {"op": "add", "args": ["$0", "$0"]}}}})
        self.assertNotEqual(a, b)


class SurfaceDistinctProgramsAgree(unittest.TestCase):
    """Acceptance gate: two languages, two surfaces, one canonical BSIR."""

    def _doubler(self):
        return slam((("u", INT),), s("mul", s("var", name="u"), s("const_int", value=2)))

    def _list(self):
        return s("range", s("const_int", value=0), s("const_int", value=4))

    def _k0_doubler(self):
        return lam((("u", INT),), app("mul", var("u"), const_int(2)))

    def _k0_list(self):
        return app("range", const_int(0), const_int(4))

    def test_two_languages_lower_to_identical_canonical_bsir(self):
        a_src = SourceProgram((), s("zq", self._list(), self._doubler()), None)
        b_src = SourceProgram((), s("apply_each", self._doubler(), self._list()), None)

        a = lower(a_src, LANG_A)
        b = lower(b_src, LANG_B)

        self.assertEqual(a.semantic_root, b.semantic_root)
        self.assertEqual(
            equivalent(a.program, b.program, CONTRACT).verdict, "EQUIV_CANONICAL"
        )

    def test_the_lowered_form_matches_a_hand_written_k0_program(self):
        a_src = SourceProgram((), s("zq", self._list(), self._doubler()), None)
        reference = Program((), app("map", self._k0_doubler(), self._k0_list()), None)
        self.assertEqual(lower(a_src, LANG_A).semantic_root, semantic_hash(reference))

    def test_the_language_id_is_not_part_of_the_semantic_root(self):
        """Two languages produce the same semantic root for the same meaning -- identity binds
        to the lowered semantics, not to which surface produced it (ADR 0013)."""
        a = lower(SourceProgram((), s("zq", self._list(), self._doubler()), None), LANG_A)
        b = lower(
            SourceProgram((), s("apply_each", self._doubler(), self._list()), None), LANG_B
        )
        self.assertNotEqual(a.language_id, b.language_id)
        self.assertEqual(a.semantic_root, b.semantic_root)


class IncorrectLoweringIsCaught(unittest.TestCase):
    """Acceptance gate: a descriptor cannot make a false lowering true by declaring it."""

    #: Claims to increment. Lowers to a decrement.
    LYING = descriptor(
        {
            "inc": {
                "operands": ["Int"],
                "result": "Int",
                "effects": ["Pure"],
                "lowers_to": {
                    "op": "sub",
                    "args": ["$0", {"op": "const_int", "attrs": {"value": 1}}],
                },
                "proof_obligations": [LOWERING_EQUIVALENCE],
            }
        }
    )

    HONEST = descriptor(
        {
            "inc": {
                "operands": ["Int"],
                "result": "Int",
                "effects": ["Pure"],
                "lowers_to": {
                    "op": "add",
                    "args": ["$0", {"op": "const_int", "attrs": {"value": 1}}],
                },
                "proof_obligations": [LOWERING_EQUIVALENCE],
            }
        }
    )

    def _sample(self):
        return SourceProgram((("x", INT),), s("inc", s("var", name="x")), INT)

    def _reference(self):
        return Program((("x", INT),), app("add", var("x"), const_int(1)), INT)

    def test_the_lying_descriptor_produces_a_counterexample(self):
        verdict = check_lowering(
            self.LYING, "inc", self._reference(), self._sample(), CONTRACT
        )
        self.assertEqual(verdict.verdict, "NON_EQUIV")
        self.assertIsNotNone(verdict.counterexample)
        self.assertEqual(verdict.counterexample.kind, "DIVERGENT_RESULT")

    def test_the_honest_descriptor_checks_out(self):
        verdict = check_lowering(
            self.HONEST, "inc", self._reference(), self._sample(), CONTRACT
        )
        self.assertEqual(verdict.verdict, "EQUIV_CANONICAL")

    def test_the_obligation_cannot_be_discharged_by_a_failing_verdict(self):
        lowered = lower(self._sample(), self.LYING)
        self.assertIn(LOWERING_EQUIVALENCE, lowered.open_obligations)
        bad = check_lowering(self.LYING, "inc", self._reference(), self._sample(), CONTRACT)
        with self.assertRaises(LoweringError):
            lowered.discharge_with(LOWERING_EQUIVALENCE, bad)
        self.assertFalse(lowered.is_fully_discharged)

    def test_a_correct_lowering_discharges_its_obligation(self):
        lowered = lower(self._sample(), self.HONEST)
        self.assertIn(LOWERING_EQUIVALENCE, lowered.open_obligations)
        good = check_lowering(self.HONEST, "inc", self._reference(), self._sample(), CONTRACT)
        settled = lowered.discharge_with(LOWERING_EQUIVALENCE, good, require_proof=True)
        self.assertTrue(settled.is_fully_discharged)
        self.assertEqual(settled.discharged[LOWERING_EQUIVALENCE], "EQUIV_CANONICAL")

    def test_sampled_evidence_cannot_discharge_when_a_proof_is_required(self):
        """A descriptor whose lowering only agrees on sampled inputs is not proven correct,
        and asking for a proof must not silently accept the weaker tier."""
        commuted = descriptor(
            {
                "inc": {
                    "operands": ["Int"],
                    "result": "Int",
                    "effects": ["Pure"],
                    "lowers_to": {
                        "op": "add",
                        "args": [{"op": "const_int", "attrs": {"value": 1}}, "$0"],
                    },
                }
            }
        )
        lowered = lower(self._sample(), commuted)
        evidence = check_lowering(commuted, "inc", self._reference(), self._sample(), CONTRACT)
        self.assertEqual(evidence.verdict, "EQUIV_DYNAMIC")

        with self.assertRaises(LoweringError):
            lowered.discharge_with(LOWERING_EQUIVALENCE, evidence, require_proof=True)

        # ...but it is acceptable evidence when a proof was not demanded.
        self.assertTrue(
            lowered.discharge_with(LOWERING_EQUIVALENCE, evidence).is_fully_discharged
        )


class DescriptorValidation(unittest.TestCase):
    def test_a_template_referencing_a_missing_operand_is_rejected(self):
        """The schema cannot express this: it is a coherence check between an operation's
        declared arity and what its own template uses."""
        with self.assertRaises(DescriptorError) as ctx:
            descriptor(
                {
                    "bad": {
                        "operands": ["Int"],
                        "result": "Int",
                        "effects": ["Pure"],
                        "lowers_to": {"op": "add", "args": ["$0", "$3"]},
                    }
                }
            )
        self.assertIn("operand", str(ctx.exception))

    def test_an_unknown_operation_in_a_source_program_is_refused(self):
        unknown = SourceProgram((("x", INT),), s("nope", s("var", name="x")), INT)
        with self.assertRaises(LoweringError):
            lower(unknown, LANG_A)

    def test_k0_operations_pass_through_without_incurring_an_obligation(self):
        source = SourceProgram(
            (("x", INT),), s("add", s("var", name="x"), s("const_int", value=1)), INT
        )
        reference = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        result = lower(source, LANG_A)
        self.assertEqual(result.open_obligations, ())
        self.assertEqual(result.lowered_ops, ())
        self.assertEqual(result.semantic_root, semantic_hash(reference))

    def test_an_unsupported_descriptor_type_is_refused(self):
        with self.assertRaises(DescriptorError):
            descriptor(
                {
                    "weird": {
                        "operands": ["Matrix<Int>"],
                        "result": "Int",
                        "effects": ["Pure"],
                        "lowers_to": {"op": "length", "args": ["$0"]},
                    }
                }
            )

    def test_the_lowered_program_still_typechecks(self):
        from bestsad.kernel.typecheck import typecheck

        src = SourceProgram(
            (),
            s(
                "zq",
                s("range", s("const_int", value=0), s("const_int", value=4)),
                slam((("u", INT),), s("mul", s("var", name="u"), s("const_int", value=2))),
            ),
            None,
        )
        typecheck(lower(src, LANG_A).program)


if __name__ == "__main__":
    unittest.main()


class SourceIsNotSemantics(unittest.TestCase):
    """ADR 0013, made structural rather than merely stated.

    A source term is a surface. Nothing that means semantics should accept one, and here that
    is a property of the types rather than a convention someone has to remember.
    """

    def _source(self):
        return SourceProgram((("x", INT),), s("inc", s("var", name="x")), INT)

    def test_semantic_hash_refuses_a_source_program(self):
        with self.assertRaises(ValueError):
            semantic_hash(self._source())

    def test_the_graph_builder_refuses_a_source_program(self):
        from bestsad.bsir import to_graph

        with self.assertRaises(ValueError):
            to_graph(self._source())

    def test_the_typechecker_refuses_a_source_program(self):
        from bestsad.kernel.typecheck import TypeError_, typecheck

        with self.assertRaises(TypeError_):
            typecheck(self._source())

    def test_lowering_is_the_only_crossing(self):
        """The lowered result is a genuine K0 program, and everything above accepts it."""
        from bestsad.bsir import to_graph
        from bestsad.kernel.typecheck import typecheck

        lowered = lower(self._source(), IncorrectLoweringIsCaught.HONEST)
        self.assertEqual(typecheck(lowered.program), INT)
        self.assertEqual(len(to_graph(lowered.program).nodes), 3)
        self.assertEqual(semantic_hash(lowered.program), lowered.semantic_root)
