"""ADR 0016: the typechecker's observer hook cannot change what the typechecker decides.

The hook exists so BSIR can populate node result types. It touches kernel-adjacent code, so
the property that makes it acceptable under AGENTS.md invariant 1 -- that it is read-only --
is asserted rather than asserted-in-a-comment.
"""

from __future__ import annotations

import random
import unittest

from bestsad.kernel import BOOL, INT, Program, app, const_int, lam, var
from bestsad.kernel.random_programs import random_program
from bestsad.kernel.typecheck import TypeError_, Typechecker


class ObserverIsReadOnly(unittest.TestCase):
    def _both_ways(self, program: Program):
        """Return (result_or_error_without_observer, result_or_error_with_observer)."""
        outcomes = []
        for observe in (None, lambda term, ty: None):
            try:
                outcomes.append(("ok", str(Typechecker().check_program(program, observe))))
            except TypeError_ as exc:
                outcomes.append(("error", str(exc)))
        return outcomes

    def test_accepting_programs_infer_the_same_type(self):
        program = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        plain, observed = self._both_ways(program)
        self.assertEqual(plain, observed)
        self.assertEqual(plain, ("ok", "Int"))

    def test_rejecting_programs_fail_identically(self):
        # `add` on a Bool: rejected either way, with the same message.
        program = Program((("x", BOOL),), app("add", var("x"), const_int(1)), INT)
        plain, observed = self._both_ways(program)
        self.assertEqual(plain[0], "error")
        self.assertEqual(plain, observed)

    def test_agreement_across_random_programs(self):
        for seed in range(200):
            program = random_program(random.Random(seed))
            with self.subTest(seed=seed):
                plain, observed = self._both_ways(program)
                self.assertEqual(plain, observed)

    def test_observer_sees_every_subterm_occurrence(self):
        program = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        seen: list[str] = []
        Typechecker().check_program(program, lambda term, ty: seen.append(term.op))
        self.assertEqual(sorted(seen), ["add", "const_int", "var"])

    def test_observed_types_are_fully_resolved(self):
        """A type recorded mid-inference can still be a type variable; the hook must not
        report one. `nil`'s element type is fixed by its attribute, and `fold`'s accumulator
        by its seed, so an unresolved report here would show up as a bare 'T'."""
        program = Program(
            (),
            app("map", lam((("u", INT),), app("mul", var("u"), const_int(2))),
                app("range", const_int(0), const_int(3))),
            None,
        )
        types: list[str] = []
        Typechecker().check_program(program, lambda term, ty: types.append(str(ty)))
        for ty in types:
            with self.subTest(ty=ty):
                self.assertNotIn("#", ty, "type variable leaked into an observed type")


if __name__ == "__main__":
    unittest.main()
