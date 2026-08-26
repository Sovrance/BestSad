"""The recording typechecker observes K0 inference without changing it (ADR 0016).

`_RecordingTypechecker` subclasses the kernel's `Typechecker` and overrides `infer`. That is
enough to see every subterm, because every recursive call inside the kernel already goes
through `self.infer` -- and it means `src/bestsad/kernel` is not modified at all, which
AGENTS.md invariant 1 requires.

An earlier version added an observer hook to `Typechecker.check_program` itself. It was
correct in behaviour and still wrong in kind: the rule is not "do not change kernel results",
it is "do not modify the trusted semantic kernel". These tests assert the property that makes
the subclass acceptable -- the kernel is untouched, and observation changes nothing.
"""

from __future__ import annotations

import random
import unittest
from pathlib import Path

from bestsad.bsir.typing import _RecordingTypechecker
from bestsad.kernel import BOOL, INT, Program, app, const_int, lam, var
from bestsad.kernel.random_programs import random_program
from bestsad.kernel.typecheck import TypeError_, Typechecker

REPO_ROOT = Path(__file__).resolve().parents[2]
KERNEL_TYPECHECK = REPO_ROOT / "src" / "bestsad" / "kernel" / "typecheck.py"


class TheKernelIsUntouched(unittest.TestCase):
    def test_the_kernel_typechecker_has_no_observation_machinery(self):
        """The point of ADR 0016's revision. If observation ever creeps back into the kernel,
        this fails and names the invariant it broke."""
        source = KERNEL_TYPECHECK.read_text(encoding="utf-8")
        for token in ("observe", "_seen", "Callable"):
            with self.subTest(token=token):
                self.assertNotIn(
                    token,
                    source,
                    f"{token!r} appears in the trusted kernel; observation belongs in bsir/",
                )

    def test_check_program_still_takes_only_a_program(self):
        import inspect

        parameters = list(inspect.signature(Typechecker.check_program).parameters)
        self.assertEqual(parameters, ["self", "program"])


class ObservationChangesNothing(unittest.TestCase):
    def _both_ways(self, program: Program):
        outcomes = []
        for checker in (Typechecker(), _RecordingTypechecker()):
            try:
                outcomes.append(("ok", str(checker.check_program(program))))
            except TypeError_ as exc:
                outcomes.append(("error", str(exc)))
        return outcomes

    def test_accepting_programs_infer_the_same_type(self):
        program = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        plain, recording = self._both_ways(program)
        self.assertEqual(plain, recording)
        self.assertEqual(plain, ("ok", "Int"))

    def test_rejecting_programs_fail_identically(self):
        program = Program((("x", BOOL),), app("add", var("x"), const_int(1)), INT)
        plain, recording = self._both_ways(program)
        self.assertEqual(plain[0], "error")
        self.assertEqual(plain, recording)

    def test_agreement_across_random_programs(self):
        for seed in range(200):
            program = random_program(random.Random(seed))
            with self.subTest(seed=seed):
                plain, recording = self._both_ways(program)
                self.assertEqual(plain, recording)


class WhatItRecords(unittest.TestCase):
    def test_every_subterm_occurrence_is_seen(self):
        program = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        checker = _RecordingTypechecker()
        checker.check_program(program)
        self.assertEqual(
            sorted(t.op for t, _ in checker.resolved_occurrences()),
            ["add", "const_int", "var"],
        )

    def test_recorded_types_are_fully_resolved(self):
        """A type recorded mid-inference can still be a type variable; resolution is deferred
        until inference finishes, so an unresolved 'T' must never reach a caller."""
        program = Program(
            (),
            app("map", lam((("u", INT),), app("mul", var("u"), const_int(2))),
                app("range", const_int(0), const_int(3))),
            None,
        )
        checker = _RecordingTypechecker()
        checker.check_program(program)
        for _, ty in checker.resolved_occurrences():
            with self.subTest(ty=str(ty)):
                self.assertNotIn("#", str(ty), "type variable leaked into a recorded type")

    def test_nothing_is_recorded_before_inference_runs(self):
        self.assertEqual(_RecordingTypechecker().resolved_occurrences(), [])


if __name__ == "__main__":
    unittest.main()
