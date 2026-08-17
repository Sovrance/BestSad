"""Abstraction discovery (spec §11, §23 E2/E3; implementation plan M6).

Three selection regimes, corresponding to the experiment's conditions:

* **random** (condition B) — macros drawn at random from the corpus, matched to the treatment
  by count and size. The lower bound: if D cannot beat this, "discovered" means nothing.
* **mdl** (condition C) — the classic compression objective: pick the abstraction that shortens
  the corpus most, net of its own description cost. Implementation plan M6 requires this to be a
  *real* MDL extractor and not a strawman, since it is the control that has historically
  matched or beaten learned-library methods.
* **utility** (condition D) — counterfactual selection: how much does having this abstraction
  reduce the *search depth* needed, weighted by how many distinct task families it serves.
  This is the treatment, and it is the only regime that looks at cross-family spread.

The difference between `mdl` and `utility` is the experiment's core contrast. If they select the
same abstractions, D has no mechanism by which to beat C, and that is itself a finding.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..bsir.canonicalize import term_semantic_hash
from ..genomes.registry import Primitive
from ..kernel import INT, Kernel, OpSig, Program, Term, Ty
from ..kernel.terms import var
from ..kernel.typecheck import TypeError_, Typechecker, _Unifier

#: Subtrees smaller than this are not worth abstracting: the call site costs a node too.
MIN_PATTERN_SIZE = 3


@dataclass(frozen=True, slots=True)
class Candidate:
    """A proposed abstraction, before promotion."""

    pattern: Term
    params: tuple[str, ...]
    param_types: tuple[Ty, ...]
    output_type: Ty
    occurrences: int
    families: frozenset[str]
    corpus_saving: int
    utility: float
    semantic_key: str

    @property
    def size(self) -> int:
        return self.pattern.size()


@dataclass
class Corpus:
    """Solved programs available to abstraction discovery.

    Only *curriculum* solutions may enter: an abstraction mined from held-out solutions would be
    fitted to the evaluation set, which is contamination, not discovery.
    """

    entries: list[tuple[Program, str]] = field(default_factory=list)

    def add(self, program: Program, family: str) -> None:
        self.entries.append((program, family))

    def __len__(self) -> int:
        return len(self.entries)

    def families(self) -> set[str]:
        return {family for _, family in self.entries}


# --- anti-unification -------------------------------------------------------------------------


def anti_unify(left: Term, right: Term) -> tuple[Term, list[tuple[Term, Term]]]:
    """Least general generalization of two terms (spec §13.2, 'anti-unify related structures').

    Positions where the two terms agree are kept; positions where they differ become holes,
    which become the abstraction's parameters. Identical differing pairs map to the *same* hole,
    so `add(x, 1)` vs `add(y, 1)` generalizes to one parameter, not two.
    """
    holes: list[tuple[Term, Term]] = []
    generalized = _anti_unify(left, right, holes)
    return generalized, holes


def _anti_unify(left: Term, right: Term, holes: list[tuple[Term, Term]]) -> Term:
    if left.op == right.op and left.attrs == right.attrs and len(left.args) == len(right.args):
        if not left.args:
            return left
        return Term(
            left.op,
            tuple(_anti_unify(a, b, holes) for a, b in zip(left.args, right.args)),
            left.attrs,
        )
    for index, (existing_left, existing_right) in enumerate(holes):
        if existing_left == left and existing_right == right:
            return var(f"h{index}")
    holes.append((left, right))
    return var(f"h{len(holes) - 1}")


# --- mining -----------------------------------------------------------------------------------


def _subterms(term: Term):
    for node in term.walk():
        if node.size() >= MIN_PATTERN_SIZE and node.op != "lam":
            yield node


def _free_variables(term: Term, bound: frozenset[str] = frozenset()) -> set[str]:
    if term.op == "var":
        name = term.attr("name")
        return set() if name in bound else {name}
    if term.op == "lam":
        inner = bound | {n for n, _ in term.attr("params")}
        return _free_variables(term.args[0], inner)
    out: set[str] = set()
    for arg in term.args:
        out |= _free_variables(arg, bound)
    return out


def _abstract_over_free_variables(
    term: Term, env: Mapping[str, Ty]
) -> tuple[Term, tuple[str, ...], tuple[Ty, ...]] | None:
    """Turn a subterm's free variables into abstraction parameters."""
    free = sorted(_free_variables(term))
    if len(free) > 3:
        return None
    types: list[Ty] = []
    for name in free:
        ty = env.get(name)
        if ty is None:
            return None
        types.append(ty)
    renaming = {name: f"a{i}" for i, name in enumerate(free)}
    return _rename(term, renaming), tuple(renaming.values()), tuple(types)


def _rename(term: Term, mapping: Mapping[str, str]) -> Term:
    if term.op == "var":
        name = term.attr("name")
        return var(mapping.get(name, name))
    if term.op == "lam":
        shadowed = {n for n, _ in term.attr("params")}
        inner = {k: v for k, v in mapping.items() if k not in shadowed}
        return Term(term.op, (_rename(term.args[0], inner),), term.attrs)
    if not term.args:
        return term
    return Term(term.op, tuple(_rename(a, mapping) for a in term.args), term.attrs)


def mine_candidates(
    corpus: Corpus,
    *,
    primitives: Mapping[str, OpSig] | None = None,
) -> list[Candidate]:
    """Mine repeated, semantically deduplicated subtrees from the corpus.

    Deduplication is by *semantic* hash, not surface form (spec §23 E3, 'deduplicate
    semantically'), so two spellings of the same computation are one candidate.
    """
    occurrences: Counter[str] = Counter()
    families: dict[str, set[str]] = {}
    exemplar: dict[str, tuple[Term, tuple[str, ...], tuple[Ty, ...], Ty]] = {}
    checker = Typechecker(primitives or {})

    for program, family in corpus.entries:
        env = dict(program.params)
        seen_here: set[str] = set()
        for subterm in _subterms(program.body):
            abstracted = _abstract_over_free_variables(subterm, env)
            if abstracted is None:
                continue
            pattern, params, param_types = abstracted
            inner_env = dict(zip(params, param_types))
            try:
                output_type = checker.infer(pattern, inner_env, _Unifier({}),
                                            in_hof_operand=False)
            except (TypeError_, KeyError, IndexError, AttributeError):
                continue
            key = term_semantic_hash(pattern, tuple(zip(params, param_types)))
            occurrences[key] += 1
            families.setdefault(key, set()).add(family)
            seen_here.add(key)
            exemplar.setdefault(key, (pattern, params, param_types, output_type))

    candidates: list[Candidate] = []
    for key, count in occurrences.items():
        pattern, params, param_types, output_type = exemplar[key]
        # Corpus saving in nodes: each occurrence collapses to a single call node plus its
        # arguments, and the abstraction itself must be written down once.
        per_use = pattern.size() - (1 + len(params))
        saving = count * per_use - pattern.size()
        candidates.append(
            Candidate(
                pattern=pattern,
                params=params,
                param_types=param_types,
                output_type=output_type,
                occurrences=count,
                families=frozenset(families[key]),
                corpus_saving=saving,
                utility=0.0,
                semantic_key=key,
            )
        )
    return candidates


# --- selection regimes --------------------------------------------------------------------------


def score_utility(candidate: Candidate, *, family_count: int) -> float:
    """Counterfactual utility (condition D).

    Rewards abstractions that (a) remove real search depth per use, and (b) serve more than one
    task family. Cross-family spread is weighted deliberately: spec §22.2 treats concentrated,
    single-family gain as *suspicious* rather than valuable, and §42.2's concentration stop rule
    exists because a gain carried by one shortcut-shaped primitive is not the result the program
    is looking for.
    """
    depth_saved = max(0, candidate.pattern.size() - (1 + len(candidate.params)))
    spread = len(candidate.families) / max(1, family_count)
    frequency = min(candidate.occurrences, 8) / 8
    return depth_saved * (0.35 + 0.65 * spread) * (0.4 + 0.6 * frequency)


def select(
    candidates: Sequence[Candidate],
    regime: str,
    count: int,
    *,
    family_count: int = 8,
    seed: int = 0,
) -> list[Candidate]:
    """Select `count` abstractions under the named regime."""
    usable = [c for c in candidates if c.occurrences >= 2 and c.size >= MIN_PATTERN_SIZE]
    if not usable:
        return []

    if regime == "random":
        rng = random.Random(f"random-macros:{seed}")
        pool = sorted(usable, key=lambda c: c.semantic_key)
        return rng.sample(pool, min(count, len(pool)))

    if regime == "mdl":
        ranked = sorted(usable, key=lambda c: (-c.corpus_saving, c.semantic_key))
        return [c for c in ranked if c.corpus_saving > 0][:count]

    if regime == "utility":
        scored = [
            Candidate(**{**c.__dict__, "utility": score_utility(c, family_count=family_count)})
            for c in usable
        ]
        ranked = sorted(scored, key=lambda c: (-c.utility, c.semantic_key))
        return [c for c in ranked if c.utility > 0][:count]

    raise ValueError(f"unknown selection regime {regime!r}")


def to_primitives(candidates: Sequence[Candidate], prefix: str) -> list[Primitive]:
    return [
        Primitive(
            primitive_id=f"prim:{prefix}{index}",
            params=candidate.params,
            expansion=candidate.pattern,
            input_types=candidate.param_types,
            output_type=candidate.output_type,
            maturity="EXP",
            origin=prefix,
        )
        for index, candidate in enumerate(candidates)
    ]


def random_matched_primitives(
    reference: Sequence[Primitive],
    candidates: Sequence[Candidate],
    prefix: str,
    seed: int,
) -> list[Primitive]:
    """Condition B: random macros matched to `reference` by count *and* size.

    Matching on size as well as count matters. A random control made of trivially small macros
    would lose to the treatment for a reason that has nothing to do with selection quality, and
    the comparison would be worthless.
    """
    if not reference:
        return []
    rng = random.Random(f"matched-random:{seed}")
    pool = sorted(candidates, key=lambda c: c.semantic_key)
    chosen: list[Candidate] = []
    for target in reference:
        want = target.size
        remaining = [c for c in pool if c not in chosen]
        if not remaining:
            break
        remaining.sort(key=lambda c: (abs(c.size - want), c.semantic_key))
        # Draw from the closest-sized third, so size is matched without deterministically
        # picking the single nearest candidate (which would make B a deterministic function of
        # D rather than a random control).
        window = remaining[: max(1, len(remaining) // 3)]
        chosen.append(rng.choice(window))
    return to_primitives(chosen, prefix)
