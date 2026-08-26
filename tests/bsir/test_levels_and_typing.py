"""BS-SRE-001: BSIR levels stay outside identity, and node typing records ambiguity.

Two properties matter here and both are load-bearing:

1. Annotating a graph with a level cannot change its hash (ADR 0013). If it could, improving
   an analyzer would re-identify existing programs and invalidate their certificates.
2. A node whose occurrences disagree about type is left untyped and reported, never guessed
   (ADR 0016).
"""

from __future__ import annotations

import unittest

from bestsad.bsir import (
    BSIRLevel,
    annotate,
    infer_level,
    semantic_hash,
    to_graph,
    type_graph,
    typed_graph,
)
from bestsad.kernel import BOOL, INT, Kernel, Program, app, const_int, lam, var


class LevelsAreOutsideIdentity(unittest.TestCase):
    def test_annotating_does_not_change_the_graph_hash(self):
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        graph = to_graph(p)
        before = graph.semantic_hash
        before_nodes = dict(graph.nodes)

        annotation = annotate(graph, BSIRLevel.STRUCTURAL, "motif-miner/0.1.0")

        self.assertEqual(graph.semantic_hash, before)
        self.assertEqual(graph.nodes, before_nodes)
        self.assertEqual(semantic_hash(p), before)
        self.assertTrue(annotation.verify_binding(graph))

    def test_an_annotation_from_another_graph_does_not_verify(self):
        a = to_graph(Program((("x", INT),), app("add", var("x"), const_int(1)), INT))
        b = to_graph(Program((("x", INT),), app("add", var("x"), const_int(2)), INT))
        self.assertFalse(annotate(a, BSIRLevel.KERNEL, "x").verify_binding(b))

    def test_levels_are_ordered(self):
        self.assertLess(BSIRLevel.KERNEL, BSIRLevel.TYPED)
        self.assertLess(BSIRLevel.TYPED, BSIRLevel.STRUCTURAL)
        self.assertLess(BSIRLevel.STRUCTURAL, BSIRLevel.ABSTRACTION)
        self.assertLess(BSIRLevel.ABSTRACTION, BSIRLevel.LANGUAGE)
        self.assertEqual(BSIRLevel.LANGUAGE.label, "BSIR-4")

    def test_a_graph_with_primitives_infers_at_least_the_abstraction_level(self):
        # Built without a kernel, so `prim:inc` is left unexpanded and visible in the graph.
        p = Program((("x", INT),), app("prim:inc", var("x")), INT)
        self.assertEqual(infer_level(to_graph(p)), BSIRLevel.ABSTRACTION)


class NodeTyping(unittest.TestCase):
    def test_a_well_typed_program_types_every_node(self):
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        graph, report = typed_graph(p)
        self.assertTrue(report.complete)
        self.assertEqual(report.typed_nodes, report.total_nodes)
        self.assertEqual(report.ambiguous, {})
        self.assertEqual(infer_level(graph), BSIRLevel.TYPED)
        for node in graph.nodes.values():
            self.assertEqual(len(node.result_types), 1)

    def test_effects_distinguish_trapping_operations(self):
        graph, _ = typed_graph(Program((("x", INT),), app("div", const_int(1), var("x")), INT))
        effects = {n.op_semantic_id: n.effect_set for n in graph.nodes.values()}
        self.assertEqual(effects["div"], frozenset({"Trap"}))
        self.assertEqual(effects["var"], frozenset({"Pure"}))

    def test_conflicting_occurrences_are_recorded_not_guessed(self):
        """Both lambdas bind `v`, so both bodies share one content-addressed node -- typed
        Bool at one occurrence and Int at the others. ADR 0016: record, do not pick."""
        p = Program(
            (),
            app(
                "map",
                lam((("v", BOOL),), var("v")),
                app(
                    "map",
                    lam((("v", INT),), app("eq", var("v"), var("v"))),
                    app("range", const_int(0), const_int(3)),
                ),
            ),
            None,
        )
        graph, report = typed_graph(p)

        self.assertFalse(report.complete)
        self.assertEqual(len(report.ambiguous), 1)
        (node_id, observed), = report.ambiguous.items()
        self.assertEqual(observed, ("Bool", "Int"))

        # The ambiguous node carries no type at all rather than a plausible-looking wrong one.
        self.assertEqual(graph.nodes[node_id].result_types, ())
        self.assertEqual(graph.nodes[node_id].op_semantic_id, "var")

        # And the graph must not claim to be BSIR-1 while a node is untyped.
        self.assertEqual(infer_level(graph), BSIRLevel.KERNEL)

    def test_an_ill_typed_program_reports_failure_and_invents_no_types(self):
        p = Program((("x", BOOL),), app("add", var("x"), const_int(1)), INT)
        graph, report = typed_graph(p)
        self.assertIsNotNone(report.failure)
        self.assertFalse(report.complete)
        self.assertEqual(report.typed_nodes, 0)
        for node in graph.nodes.values():
            self.assertEqual(node.result_types, ())

    def test_typing_does_not_move_the_graph_hash(self):
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        graph = to_graph(p)
        before = graph.semantic_hash
        before_ids = set(graph.nodes)
        type_graph(graph, p)
        self.assertEqual(graph.semantic_hash, before)
        self.assertEqual(set(graph.nodes), before_ids)

    def test_coverage_is_reported_in_the_shape_sre_expects(self):
        from bestsad import sre

        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        _, report = typed_graph(p)
        result = sre.AnalyzerResult(
            producer=sre.Producer("bsir.typing", "0.1.0"),
            inputs=(sre.as_content_id(semantic_hash(p)),),
            facts=(),
            coverage=report.coverage,
        )
        sre.validate("AnalyzerResult", result.to_wire())


if __name__ == "__main__":
    unittest.main()
