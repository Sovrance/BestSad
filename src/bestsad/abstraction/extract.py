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
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from ..bsir.canonicalize import term_semantic_hash
from ..genomes.registry import Primitive
from ..kernel import INT, Kernel, OpSig, Program, Term, Ty
from ..kernel.terms import var
from ..kernel.typecheck import TypeError_, Typechecker, _Unifier
from .rewrite import rewrite_corpus

#: Subtrees smaller than this are not worth abstracting: the call site costs a node too.
MIN_PATTERN_SIZE = 3

#: Version of the selection machinery. Bumped whenever a regime's *objective* changes, so that
#: cached discovery output produced by an older extractor is not silently reused — the same
#: class of defect as the checkpoint-key collision that once served a stale condition I.
SELECTION_VERSION = "select-2.0.0-joint-mdl-bits"


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


@dataclass(frozen=True, slots=True)
class LibraryResult:
    """The outcome of a joint MDL library search."""

    selected: tuple[Candidate, ...]
    initial_bits: float
    final_bits: float
    steps: tuple[dict, ...]

    @property
    def bits_saved(self) -> float:
        return self.initial_bits - self.final_bits


def _library_cost_bits(selected: Sequence[Candidate], scheme, base_vocabulary) -> float:
    """Bits to *state* the library — the second half of the two-part MDL code."""
    return sum(
        scheme.description_length(c.pattern, base_vocabulary) for c in selected
    )


def mdl_library_search(
    candidates: Sequence[Candidate],
    corpus: Corpus,
    *,
    count: int,
    scheme=None,
    base_vocabulary: Sequence[str] | None = None,
    beam: int = 3,
) -> LibraryResult:
    """Choose a library jointly, by two-part MDL in bits (ADR-0006).

    Objective, minimised:

        L(corpus | library) + L(library)

    Both terms in **bits** under the pre-registered coding scheme, the same one SG-v2 uses — so
    condition C and the Semantic Gain metric now measure description length the same way rather
    than one counting bits and the other counting nodes.

    Candidates are selected one at a time, and after each selection the corpus is **rewritten**
    to use the chosen abstraction before the remaining candidates are re-scored. That is what
    makes the search joint: two abstractions covering the same subtree can no longer both claim
    the saving, because after the first is applied the mass it compressed is simply gone. Ranking
    candidates independently double-counts exactly that shared mass, which is what made this
    control weaker than it should have been.

    A beam keeps `beam` partial libraries alive, so one locally-best first pick cannot foreclose
    a jointly better pair. Selection stops when no remaining candidate reduces total bits — a
    library that costs more to state than it saves is not selected at any size.
    """
    from ..mdl import CodingScheme

    scheme = scheme or CodingScheme()
    base_vocabulary = list(base_vocabulary or _default_vocabulary())
    programs = [program for program, _family in corpus.entries]
    if not programs or not candidates:
        return LibraryResult((), 0.0, 0.0, ())

    initial = scheme.set_length(programs, base_vocabulary)

    # Each beam entry: (selected, rewritten programs, total bits, step log)
    beams: list[tuple[list[Candidate], list, float, list[dict]]] = [
        ([], programs, initial, [])
    ]

    for _round in range(count):
        expanded: list[tuple[list[Candidate], list, float, list[dict]]] = []
        for selected, current, current_bits, log in beams:
            chosen_keys = {c.semantic_key for c in selected}
            for candidate in candidates:
                if candidate.semantic_key in chosen_keys:
                    continue
                primitive_id = f"prim:m{len(selected)}"
                rewritten, occurrences = rewrite_corpus(
                    current,
                    primitive_id=primitive_id,
                    pattern=candidate.pattern,
                    params=candidate.params,
                )
                if occurrences == 0:
                    # Already compressed away by an earlier selection: no mass left to claim.
                    continue
                vocabulary = base_vocabulary + [
                    f"prim:m{i}" for i in range(len(selected) + 1)
                ]
                corpus_bits = scheme.set_length(rewritten, vocabulary)
                library_bits = _library_cost_bits(
                    [*selected, candidate], scheme, base_vocabulary
                )
                total = corpus_bits + library_bits
                if total >= current_bits:
                    continue
                expanded.append(
                    (
                        [*selected, candidate],
                        rewritten,
                        total,
                        [
                            *log,
                            {
                                "primitive_id": primitive_id,
                                "semantic_key": candidate.semantic_key,
                                "occurrences_rewritten": occurrences,
                                "bits_before": current_bits,
                                "bits_after": total,
                                "bits_saved": current_bits - total,
                            },
                        ],
                    )
                )
        if not expanded:
            break
        expanded.sort(key=lambda entry: (entry[2], entry[0][-1].semantic_key))
        beams = expanded[:beam]

    best = min(beams, key=lambda entry: (entry[2], [c.semantic_key for c in entry[0]]))
    return LibraryResult(
        selected=tuple(best[0]),
        initial_bits=initial,
        final_bits=best[2],
        steps=tuple(best[3]),
    )


def _default_vocabulary() -> list[str]:
    from ..kernel.ops import OPS_BY_NAME

    return list(OPS_BY_NAME)


def select(
    candidates: Sequence[Candidate],
    regime: str,
    count: int,
    *,
    family_count: int = 8,
    seed: int = 0,
    corpus: Corpus | None = None,
) -> list[Candidate]:
    """Select `count` abstractions under the named regime.

    `corpus` is required for the `mdl` regime to run its joint search; without it that regime
    falls back to independent ranking, which ADR-0006 records as the weaker form.
    """
    usable = [c for c in candidates if c.occurrences >= 2 and c.size >= MIN_PATTERN_SIZE]
    if not usable:
        return []

    if regime == "random":
        rng = random.Random(f"random-macros:{seed}")
        pool = sorted(usable, key=lambda c: c.semantic_key)
        return rng.sample(pool, min(count, len(pool)))

    if regime == "mdl":
        if corpus is not None:
            # Joint two-part MDL in bits (ADR-0006). The independent ranking below is retained
            # only for callers with no corpus to rewrite against, and is documented as the
            # weaker form it is.
            return list(mdl_library_search(usable, corpus, count=count).selected)
        ranked = sorted(usable, key=lambda c: (-c.corpus_saving, c.semantic_key))
        return [c for c in ranked if c.corpus_saving > 0][:count]

    if regime == "utility":
        scored = [
            replace(c, utility=score_utility(c, family_count=family_count)) for c in usable
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
