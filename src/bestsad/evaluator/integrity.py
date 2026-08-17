"""Adversarial integrity plane (spec §20.1 class C, §22).

Reward hacking is a central research risk because language evolution can hide benchmark-specific
behaviour inside abstractions. This module supplies the detectors:

* `detect_hardcoding` — is the candidate a lookup table dressed as a program?
* `suspicious_primitive` — spec §22.2's rule: high task-specific gain, low cross-family reuse.
* `check_canary` — did a hidden-asset canary reach a candidate-visible surface?
* `quarantine` — spec §22.3: a suspected exploit is preserved with evidence, never deleted.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..kernel import Kernel, Program, Term
from ..tasks.families import Task, sample_input
from ..tasks.generator import CANARY


@dataclass(frozen=True, slots=True)
class HardcodingReport:
    hardcoded: bool
    reason: str
    equality_guards: int = 0
    fresh_agreement: float = 1.0


def detect_hardcoding(
    candidate: Program,
    task: Task,
    kernel: Kernel,
    *,
    probes: int = 40,
    seed: int = 0,
    agreement_floor: float = 0.34,
) -> HardcodingReport:
    """Detect a candidate that memorised its examples rather than computing the function.

    Two independent signals, because either alone is weak:

    * **Structural** — a chain of equality guards against constants, one per visible example, is
      the shape of a lookup table. Counting them catches the blatant form.
    * **Behavioural** — the candidate agrees with the reference on the visible examples but
      collapses on freshly drawn inputs. This catches the forms that are not shaped like a
      lookup table at all, which is why it is the signal that decides.

    Fresh inputs are drawn from the same distribution as the task's own, so this is not a
    difficulty test: a genuine solution scores near 1.0.
    """
    guards = _count_equality_guards(candidate.body)

    rng = random.Random(f"hardcode:{task.task_id}:{seed}")
    types = tuple(ty for _, ty in task.params)
    agree = total = 0
    for _ in range(probes):
        inputs = tuple(sample_input(rng, ty) for ty in types)
        expected = kernel.execute(task.reference, list(inputs))
        actual = kernel.execute(candidate, list(inputs))
        total += 1
        if expected.same_outcome(actual):
            agree += 1
    agreement = agree / total if total else 1.0

    if agreement < agreement_floor and guards >= max(1, len(task.train_inputs) - 1):
        return HardcodingReport(
            True,
            "equality-guard chain matching the visible examples, with agreement collapsing "
            "on fresh inputs",
            guards,
            agreement,
        )
    if agreement < agreement_floor:
        return HardcodingReport(
            True, "agreement collapses on freshly drawn inputs", guards, agreement
        )
    return HardcodingReport(False, "", guards, agreement)


def _count_equality_guards(term: Term) -> int:
    """Count `if (eq <x> <const>) ...` guards — the lookup-table shape."""
    count = 0
    for node in term.walk():
        if node.op != "if":
            continue
        condition = node.args[0]
        if condition.op == "eq" and any(
            arg.op in ("const_int", "const_bool") for arg in condition.args
        ):
            count += 1
    return count


@dataclass(frozen=True, slots=True)
class SuspicionReport:
    suspicious: bool
    primitive_id: str
    task_specific_gain: float
    cross_family_reuse: int
    reason: str = ""


def suspicious_primitive(
    primitive_id: str,
    task_specific_gain: float,
    families_used_in: Sequence[str],
    *,
    gain_threshold: float = 0.15,
    reuse_threshold: int = 2,
) -> SuspicionReport:
    """Spec §22.2: unusually high task-specific gain with low cross-family reuse is queued for
    adversarial inspection.

    This fires on a *pattern*, not on a verdict. A primitive that genuinely captures one family
    well will trip it, and that is intended: the rule exists to force a look, and
    `AGENTS.md` escalates the case to a human rather than resolving it automatically.
    """
    reuse = len(set(families_used_in))
    if task_specific_gain >= gain_threshold and reuse < reuse_threshold:
        return SuspicionReport(
            True,
            primitive_id,
            task_specific_gain,
            reuse,
            f"gain {task_specific_gain:.3f} concentrated in {reuse} family/families",
        )
    return SuspicionReport(False, primitive_id, task_specific_gain, reuse)


def check_canary(*surfaces: str) -> list[dict]:
    """Confirm the hidden-asset canary is absent from candidate-visible surfaces (spec §40.1)."""
    findings = []
    for index, surface in enumerate(surfaces):
        if CANARY in surface:
            findings.append(
                {"kind": "canary_leak", "detail": f"surface {index} contains the canary",
                 "fatal": True}
            )
    return findings


@dataclass
class Quarantine:
    """Spec §22.3: a candidate suspected of evaluator exploitation is quarantined with
    evidence, never deleted. P7 applies to exploits as much as to negative results — the
    failure mode is the thing the integrity suite learns from."""

    directory: Path
    entries: list[dict] = field(default_factory=list)

    def add(self, *, candidate: str, task_id: str, evidence: dict) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        index = len(list(self.directory.glob("*.json")))
        path = self.directory / f"quarantine-{index:04d}-{task_id}.json"
        record = {"candidate": candidate, "task_id": task_id, "evidence": evidence}
        path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str))
        self.entries.append(record)
        return path
