"""Scripted model behaviours for the adapter tests, nameable as `module:function` so a spec
can carry them across the process boundary (`bestsad.models.llm.resolve_script`).

`ANSWERS` maps the rendering of a task's first visible example to that task's reference program
in the `sexpr` projection; `oracle` re-renders it in whichever projection the prompt names, so
one registration serves every condition.
"""

from __future__ import annotations

import re

from bestsad.bsir import get_projection

#: `answer_key(task)` -> reference program body, rendered in `sexpr`.
ANSWERS: dict[str, str] = {}

_PROJECTION = re.compile(r"in the `([a-z]+)` projection")
_EXAMPLE = re.compile(r"^  (.*) -> ", re.M)


def _projection_name(prompt: str) -> str:
    match = _PROJECTION.search(prompt)
    return match.group(1) if match else "sexpr"


def answer_key(task) -> str:
    """Every visible input of a task, rendered — exact, so no task's key is a substring of
    another's examples."""
    from bestsad.models.llm import render_inputs

    return " | ".join(render_inputs(inputs) for inputs in task.train_inputs)


def register(task) -> None:
    ANSWERS[answer_key(task)] = get_projection("sexpr").render(task.reference.body)


def oracle(prompt: str, seed: int) -> str:
    """Answer with the registered reference program, in the prompt's projection."""
    # The task block follows the header, so a worked example cannot be mistaken for the task.
    task_block = prompt.rsplit("Task (", 1)[-1].split("Program:")[0]
    key = " | ".join(_EXAMPLE.findall(task_block))
    program = ANSWERS.get(key)
    if program is None:
        return "Program: (add 1 1)"
    term = get_projection("sexpr").parse(program)
    return f"Program: {get_projection(_projection_name(prompt)).render(term)}"


def wrong_then_right(prompt: str, seed: int) -> str:
    """A well-typed wrong program first; the right one once feedback names the failure."""
    if "Your answer" in prompt:
        return oracle(prompt, seed)
    projection = get_projection(_projection_name(prompt))
    return projection.render(get_projection("sexpr").parse("(length xs)"))


def gibberish(prompt: str, seed: int) -> str:
    return "this is not a program ((("


def echo_canary(prompt: str, seed: int) -> str:
    return "BESTSAD-CANARY-9f2c1a77-DO-NOT-REPRODUCE"


def never_solves(prompt: str, seed: int) -> str:
    return "Program: (add 1 1)"
