"""Pattern matching and corpus rewriting for library learning.

An abstraction only earns its place if using it makes the corpus *shorter*. Measuring that
requires actually rewriting programs to use it — which is what this module does — rather than
counting occurrences and assuming the savings add up. They do not add up when two abstractions
overlap: the same subtree cannot be compressed twice, and an extractor that scores candidates
independently double-counts exactly the mass they share.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..kernel import Program, Term


def match_pattern(
    pattern: Term, term: Term, holes: frozenset[str]
) -> dict[str, Term] | None:
    """Match `pattern` against `term`, binding `holes` to subterms.

    A hole appearing twice must bind the *same* subterm both times, so the pattern
    `add(a0, a0)` matches `add(x, x)` but not `add(x, y)`. Getting that wrong would let an
    abstraction claim matches it cannot actually express.
    """
    bindings: dict[str, Term] = {}

    def go(p: Term, t: Term) -> bool:
        if p.op == "var":
            name = p.attr("name")
            if name in holes:
                existing = bindings.get(name)
                if existing is not None:
                    return existing == t
                bindings[name] = t
                return True
        if p.op != t.op or p.attrs != t.attrs or len(p.args) != len(t.args):
            return False
        return all(go(pa, ta) for pa, ta in zip(p.args, t.args))

    return bindings if go(pattern, term) else None


def rewrite_term(
    term: Term,
    *,
    primitive_id: str,
    pattern: Term,
    params: Sequence[str],
) -> tuple[Term, int]:
    """Replace every occurrence of `pattern` in `term` with a call to `primitive_id`.

    Top-down, so the largest match at any position wins — rewriting the children first would
    dissolve the very structure the outer pattern is trying to match.
    """
    holes = frozenset(params)
    count = 0

    def go(node: Term) -> Term:
        nonlocal count
        bindings = match_pattern(pattern, node, holes)
        if bindings is not None and all(p in bindings for p in params):
            count += 1
            return Term(primitive_id, tuple(go(bindings[p]) for p in params))
        if not node.args:
            return node
        return Term(node.op, tuple(go(a) for a in node.args), node.attrs)

    return go(term), count


def rewrite_program(program: Program, **kwargs) -> tuple[Program, int]:
    body, count = rewrite_term(program.body, **kwargs)
    return Program(program.params, body, program.result_type), count


def rewrite_corpus(
    programs: Sequence[Program],
    *,
    primitive_id: str,
    pattern: Term,
    params: Sequence[str],
) -> tuple[list[Program], int]:
    """Rewrite a whole corpus, returning the new programs and the total occurrence count."""
    out: list[Program] = []
    total = 0
    for program in programs:
        rewritten, count = rewrite_program(
            program, primitive_id=primitive_id, pattern=pattern, params=params
        )
        out.append(rewritten)
        total += count
    return out, total
