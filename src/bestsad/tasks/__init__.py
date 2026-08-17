"""Procedural task generation: families F1-F12 (spec §24.2-§24.4)."""

from .families import (
    ADVERSARIAL_FAMILIES,
    CURRICULUM_FAMILIES,
    FAMILIES,
    HELD_OUT_FAMILIES,
    Family,
    Task,
)
from .generator import (
    CANARY,
    GENERATOR_VERSION,
    TaskSet,
    adversarial_set,
    curriculum_set,
    generate_task,
    generate_task_set,
    held_out_set,
    in_family_ood_set,
)

__all__ = [
    "ADVERSARIAL_FAMILIES",
    "CANARY",
    "CURRICULUM_FAMILIES",
    "FAMILIES",
    "GENERATOR_VERSION",
    "Family",
    "HELD_OUT_FAMILIES",
    "Task",
    "TaskSet",
    "adversarial_set",
    "curriculum_set",
    "generate_task",
    "generate_task_set",
    "held_out_set",
    "in_family_ood_set",
]
