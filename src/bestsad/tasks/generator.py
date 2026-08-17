"""Procedural task generation with fresh seeds (spec §20.4, §24.3).

Generation is a pure function of `(family, seed)`, so a benchmark is reproducible from its
manifest alone and no instance needs to be stored — which is what makes the frozen hidden
benchmark cheap to keep genuinely hidden.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..kernel import Kernel, Program
from ..kernel.terms import var
from .families import (
    ADVERSARIAL_FAMILIES,
    CURRICULUM_FAMILIES,
    FAMILIES,
    HELD_OUT_FAMILIES,
    Task,
    sample_input,
)

GENERATOR_VERSION = "taskgen-1.0.0"

#: Canary string. Must never appear on any candidate-visible surface (spec §40.1, C4). Its
#: presence in a model's output would be evidence of hidden-asset leakage.
CANARY = "BESTSAD-CANARY-9f2c1a77-DO-NOT-REPRODUCE"


def _task_id(family: str, seed: int) -> str:
    return f"{family}-{hashlib.blake2b(f'{family}:{seed}'.encode(), digest_size=6).hexdigest()}"


def generate_task(
    family_id: str,
    seed: int,
    *,
    n_train: int = 4,
    n_hidden: int = 12,
    kernel: Kernel | None = None,
) -> Task:
    """Generate one task instance. Deterministic in `(family_id, seed)`."""
    family = FAMILIES[family_id]
    kernel = kernel or Kernel()

    # Re-roll degenerate instances (see `_is_degenerate`). Deterministic: the salt is derived
    # from the seed, so the same (family, seed) always yields the same task.
    for salt in range(24):
        rng = random.Random(f"{GENERATOR_VERSION}:{family_id}:{seed}:{salt}")
        reference, notes = family.build(rng)
        train = _sample_inputs(rng, family.input_types, n_train, reference, kernel)
        hidden = _sample_inputs(rng, family.input_types, n_hidden, reference, kernel)
        if not _is_degenerate(reference, train + hidden, kernel):
            break
    else:  # pragma: no cover - every family has non-degenerate instances
        raise RuntimeError(f"{family_id} produced only degenerate instances at seed {seed}")

    return Task(
        task_id=_task_id(family_id, seed),
        family=family_id,
        params=reference.params,
        result_type=reference.result_type,
        reference=reference,
        train_inputs=train,
        hidden_inputs=hidden,
        seed=seed,
        composition_depth=family.composition_depth,
        adversarial=family_id in ADVERSARIAL_FAMILIES,
        notes=notes,
    )


def _is_degenerate(reference: Program, inputs: tuple[tuple, ...], kernel: Kernel) -> bool:
    """True when the reference is extensionally trivial on its own inputs.

    A family can randomly produce an instance that happens to be the identity (`map(e => e*1)`)
    or a constant. Such an instance is solved at size 1 by returning a parameter, which
    measures nothing about composition and — worse — is solved equally by every condition, so
    it dilutes the very effect the experiment is trying to detect. These are re-rolled rather
    than scored.
    """
    outcomes = [kernel.execute(reference, list(i)) for i in inputs]
    keys = [(o.trap.kind if o.trap else None, None if o.trap else o.value) for o in outcomes]

    # Constant function?
    if len({_freeze(k) for k in keys}) <= 1:
        return True

    # Identity on some parameter?
    for position, (name, _ty) in enumerate(reference.params):
        identity = Program(reference.params, var(name), reference.result_type)
        matches = all(
            kernel.execute(identity, list(inp)).same_outcome(out)
            for inp, out in zip(inputs, outcomes)
        )
        if matches:
            return True
    return False


def _freeze(key) -> str:
    return repr(key)


def _sample_inputs(
    rng: random.Random,
    types: Sequence,
    count: int,
    reference: Program,
    kernel: Kernel,
) -> tuple[tuple, ...]:
    """Sample inputs on which the reference does not trap.

    A task whose reference traps on its own inputs would score every candidate on trap
    equality rather than on computing the right answer, which is not the intended difficulty.
    Trap behaviour is exercised deliberately elsewhere (the K0 differential sweep), not
    accidentally here.
    """
    out: list[tuple] = []
    attempts = 0
    while len(out) < count and attempts < count * 40:
        attempts += 1
        candidate = tuple(sample_input(rng, ty) for ty in types)
        if kernel.execute(reference, list(candidate)).ok:
            out.append(candidate)
    if len(out) < count:  # pragma: no cover - families are chosen to be trap-free
        raise RuntimeError("could not sample enough non-trapping inputs")
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TaskSet:
    """A named collection of tasks with its generation provenance."""

    name: str
    tasks: tuple[Task, ...]
    families: tuple[str, ...]
    seed_base: int
    generator_version: str = GENERATOR_VERSION

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self) -> Iterable[Task]:
        return iter(self.tasks)

    def by_family(self) -> dict[str, list[Task]]:
        out: dict[str, list[Task]] = {}
        for task in self.tasks:
            out.setdefault(task.family, []).append(task)
        return out


def generate_task_set(
    name: str,
    families: Sequence[str],
    seed_base: int,
    per_family: int,
    **kwargs,
) -> TaskSet:
    tasks = [
        generate_task(family, seed_base * 1000 + i, **kwargs)
        for family in families
        for i in range(per_family)
    ]
    return TaskSet(name=name, tasks=tuple(tasks), families=tuple(families), seed_base=seed_base)


def curriculum_set(seed_base: int, per_family: int = 6, **kwargs) -> TaskSet:
    """Training/curriculum tasks: families F1–F8 (spec §24.3)."""
    return generate_task_set("curriculum", CURRICULUM_FAMILIES, seed_base, per_family, **kwargs)


def held_out_set(seed_base: int, per_family: int = 6, **kwargs) -> TaskSet:
    """The primary endpoint's terrain: held-out compositional families F9–F12 (spec §24.6)."""
    return generate_task_set("held_out", HELD_OUT_FAMILIES, seed_base, per_family, **kwargs)


def in_family_ood_set(seed_base: int, per_family: int = 6, **kwargs) -> TaskSet:
    """Unseen seeds from F1–F8 — a *secondary* outcome only (spec §24.6)."""
    return generate_task_set("in_family_ood", CURRICULUM_FAMILIES, seed_base, per_family, **kwargs)


def adversarial_set(seed_base: int, per_family: int = 6, **kwargs) -> TaskSet:
    """Adversarially similar tasks where a shortcut primitive should fail (spec §24.4)."""
    return generate_task_set("adversarial", ADVERSARIAL_FAMILIES, seed_base, per_family, **kwargs)
