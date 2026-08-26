"""BS-SRE-001: the semantic diff answers a question about meaning, not about text."""

from __future__ import annotations

import unittest

from bestsad.bsir import diff, get_projection, to_graph, typed_graph
from bestsad.kernel import BOOL, INT, Program, app, const_int, var


def graph_of(body, params=(("x", INT),), result=INT):
    g, _ = typed_graph(Program(params=params, body=body, result_type=result))
    return g


class SemanticDiff(unittest.TestCase):
    def test_identical_programs_have_an_empty_diff(self):
        a = graph_of(app("add", var("x"), const_int(1)))
        b = graph_of(app("add", var("x"), const_int(1)))
        d = diff(a, b)
        self.assertTrue(d.is_empty)
        self.assertFalse(d.root_changed)
        self.assertEqual(d.added, ())
        self.assertEqual(d.removed, ())

    def test_reprojection_does_not_show_up_as_a_semantic_change(self):
        """The point of the module: rendering through a different projection and parsing back
        changes every character and no semantics, so the diff must be empty."""
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        a = graph_of(p.body)
        for name in ("sexpr", "compact", "human", "graph"):
            projection = get_projection(name)
            with self.subTest(projection=name):
                back = projection.parse(projection.render(p.body))
                self.assertTrue(diff(a, graph_of(back)).is_empty)

    def test_a_changed_constant_is_a_node_substitution(self):
        a = graph_of(app("add", var("x"), const_int(1)))
        b = graph_of(app("add", var("x"), const_int(2)))
        d = diff(a, b)
        self.assertFalse(d.is_empty)
        self.assertTrue(d.root_changed)
        self.assertEqual(d.added_ops, ("add", "const_int"))
        self.assertEqual(d.removed_ops, ("add", "const_int"))

    def test_introducing_a_trapping_operation_touches_the_effect_surface(self):
        # `eq` is one of K0's genuinely pure operations; `div` can trap.
        pure = graph_of(app("eq", var("x"), const_int(1)), result=BOOL)
        trapping = graph_of(app("div", const_int(1), var("x")))
        d = diff(pure, trapping)
        self.assertTrue(d.touches_effect_surface)
        self.assertIn("Trap", d.added_effects)
        self.assertIn("division_by_zero", d.added_trap_kinds)

    def test_swapping_one_trapping_op_for_another_changes_the_failure_mode(self):
        """`add` and `div` both carry the `Trap` effect, so K0's two-valued lattice reports no
        change -- while the way the program can fail has changed completely. The trap-kind
        delta is what catches it."""
        overflowing = graph_of(app("add", var("x"), const_int(1)))
        dividing = graph_of(app("div", const_int(1), var("x")))
        d = diff(overflowing, dividing)
        self.assertEqual(d.added_effects, frozenset())
        self.assertEqual(d.added_trap_kinds, frozenset({"division_by_zero"}))
        self.assertEqual(d.removed_trap_kinds, frozenset({"value_too_large"}))
        self.assertTrue(d.touches_effect_surface)

    def test_a_pure_to_pure_change_does_not_touch_the_effect_surface(self):
        a = graph_of(app("eq", var("x"), const_int(1)), result=BOOL)
        b = graph_of(app("eq", var("x"), const_int(2)), result=BOOL)
        self.assertFalse(diff(a, b).touches_effect_surface)

    def test_shared_subterms_are_reported_as_shared(self):
        a = graph_of(app("add", var("x"), const_int(1)))
        b = graph_of(app("mul", var("x"), const_int(1)))
        d = diff(a, b)
        shared_ops = {a.nodes[i].op_semantic_id for i in d.shared}
        self.assertEqual(shared_ops, {"var", "const_int"})

    def test_a_non_empty_diff_is_not_a_claim_of_non_equivalence(self):
        """`add(x,1)` and `add(1,x)` differ structurally and agree semantically. The diff
        reports the structural difference and says nothing about equivalence -- that is what
        the equivalence tiers are for."""
        from bestsad.bsir import EquivalenceContract, equivalent

        a_prog = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        b_prog = Program((("x", INT),), app("add", const_int(1), var("x")), INT)
        self.assertFalse(diff(graph_of(a_prog.body), graph_of(b_prog.body)).is_empty)
        verdict = equivalent(
            a_prog, b_prog, EquivalenceContract(input_domain_ref="int:small")
        ).verdict
        self.assertEqual(verdict, "EQUIV_DYNAMIC")


if __name__ == "__main__":
    unittest.main()
