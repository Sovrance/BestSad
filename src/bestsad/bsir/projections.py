"""Projection classes over common BSIR semantics (spec §12).

A projection is a **view**, not the semantics (P8). Four projections are implemented:

* `HumanProjection`    — descriptive call syntax, explicit typing, debuggable
* `SExprProjection`    — structurally regular symbolic baseline
* `CompactProjection`  — short model-oriented tokens (condition E's surface)
* `GraphProjection`    — node/edge serialization, one assignment per line

Spec §12.2 is the critical rule: representation experiments must preserve semantic identity.
Every projection here round-trips — `parse(render(t))` yields a term with the same canonical
semantic hash — and `tests/bsir/test_round_trip.py` enforces it across random programs. A
projection that failed to round-trip would be a *language* experiment wearing a formatting
experiment's label, which is exactly the confusion §12.2 forbids.

Token counts come from `token_count`, a deterministic surface-token proxy. It is a proxy, not
a model tokenizer: the real `compression_ratio` for an LLM condition must come from that
model's tokenizer (ADR-0007 records this limitation).
"""

from __future__ import annotations

import re
from typing import Iterable, Iterator

from ..kernel.ops import OPS_BY_NAME
from ..kernel.terms import Program, Term
from ..kernel.types import Ty, parse_type

# --- shared lexing --------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<comma>,)
  | (?P<colon>:)
  | (?P<arrow>=>|->|=)
  | (?P<lt><)
  | (?P<gt>>)
  | (?P<int>-?\d+)
  | (?P<sym>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op>[^\s()<>,:]+)
  | (?P<ws>\s+)
    """,
    re.VERBOSE,
)


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise ValueError(f"cannot lex at position {pos}: {text[pos:pos+20]!r}")
        pos = match.end()
        if match.lastgroup == "ws":
            continue
        out.append(match.group())
    return out


def token_count(text: str) -> int:
    """Deterministic surface-token count — the model-side cost proxy (spec §21.1)."""
    return len(tokenize(text))


class _Reader:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def next(self) -> str:
        if self.i >= len(self.tokens):
            raise ValueError("unexpected end of input")
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, tok: str) -> None:
        got = self.next()
        if got != tok:
            raise ValueError(f"expected {tok!r}, got {got!r}")

    def done(self) -> bool:
        return self.i >= len(self.tokens)


# --- projection base ------------------------------------------------------------------------


class Projection:
    """Base class. `name` identifies the projection in genomes and manifests."""

    name: str = "abstract"
    #: op -> surface symbol. Ops absent from the table keep their K0 name.
    symbols: dict[str, str] = {}

    def __init__(self, primitive_symbols: dict[str, str] | None = None) -> None:
        self.primitive_symbols = dict(primitive_symbols or {})

    # -- symbol tables --

    def symbol(self, op: str) -> str:
        if op in self.primitive_symbols:
            return self.primitive_symbols[op]
        return self.symbols.get(op, op)

    def op_for(self, symbol: str) -> str:
        for op, sym in self.primitive_symbols.items():
            if sym == symbol:
                return op
        for op, sym in self.symbols.items():
            if sym == symbol:
                return op
        return symbol

    # -- rendering / parsing --

    def render(self, term: Term) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def parse(self, text: str) -> Term:  # pragma: no cover - abstract
        raise NotImplementedError

    def render_program(self, program: Program) -> str:
        params = ", ".join(f"{n}: {t}" for n, t in program.params)
        return f"({params}) -> {program.result_type} = {self.render(program.body)}"

    def describe_grammar(self) -> str:
        """The grammar description delivered in-context. Its token count is what the
        scaffolding matcher (condition H) equalizes across conditions."""
        lines = [f"Projection `{self.name}`. Operations:"]
        for op in sorted(set(OPS_BY_NAME) | set(self.primitive_symbols)):
            lines.append(f"  {op} -> {self.symbol(op)}")
        return "\n".join(lines)


# --- s-expression family --------------------------------------------------------------------


class SExprProjection(Projection):
    """`(add x 1)` — structurally regular symbolic baseline (spec §12.1 class 3)."""

    name = "sexpr"
    symbols = {}

    def render(self, term: Term) -> str:
        op = term.op
        if op == "const_int":
            return str(term.attr("value"))
        if op == "const_bool":
            return "true" if term.attr("value") else "false"
        if op == "var":
            return str(term.attr("name"))
        if op in ("nil", "none"):
            return f"({self.symbol(op)} {term.attr('elem_type')})"
        if op == "lam":
            params = " ".join(f"{n}:{t}" for n, t in term.attr("params"))
            return f"({self.symbol(op)} ({params}) {self.render(term.args[0])})"
        if not term.args:
            return f"({self.symbol(op)})"  # pragma: no cover
        inner = " ".join(self.render(a) for a in term.args)
        return f"({self.symbol(op)} {inner})"

    def parse(self, text: str) -> Term:
        reader = _Reader(tokenize(text))
        term = self._parse(reader)
        if not reader.done():
            raise ValueError(f"trailing tokens: {reader.tokens[reader.i:]}")
        return term

    def _parse(self, r: _Reader) -> Term:
        tok = r.next()
        if tok == "(":
            symbol = r.next()
            op = self.op_for(symbol)
            if op in ("nil", "none"):
                ty = self._parse_type(r)
                r.expect(")")
                return Term(op, (), (("elem_type", ty),))
            if op == "lam":
                r.expect("(")
                params: list[tuple[str, Ty]] = []
                while r.peek() != ")":
                    name = r.next()
                    r.expect(":")
                    params.append((name, self._parse_type(r)))
                r.expect(")")
                body = self._parse(r)
                r.expect(")")
                return Term(op, (body,), (("params", tuple(params)),))
            args = []
            while r.peek() != ")":
                args.append(self._parse(r))
            r.expect(")")
            return Term(op, tuple(args))
        if re.fullmatch(r"-?\d+", tok):
            return Term("const_int", (), (("value", int(tok)),))
        if tok in ("true", "false"):
            return Term("const_bool", (), (("value", tok == "true"),))
        return Term("var", (), (("name", tok),))

    def _parse_type(self, r: _Reader) -> Ty:
        """Read a type, which may span several tokens (`List < Int >`)."""
        chunks: list[str] = []
        depth = 0
        while True:
            tok = r.peek()
            if tok is None:
                break
            if tok == "<":
                depth += 1
            elif tok == ">":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and tok in (")", ",", ":"):
                break
            elif depth == 0 and chunks and tok not in ("<", ">"):
                # A complete type has been read and the next token starts something else.
                break
            chunks.append(r.next())
            if depth == 0 and chunks:
                nxt = r.peek()
                if nxt != "<":
                    break
        return parse_type("".join(chunks))


class CompactProjection(Projection):
    """Parenthesis-free prefix notation with short symbols (spec §12.1 class 2).

    Condition E's surface form. Every K0 operation has a fixed arity, so the parentheses an
    s-expression needs carry no information: `(add x 1)` is four tokens, `+ x 1` is three, and
    the saving compounds with nesting. Semantics are identical to `SExprProjection` — this is a
    formatting experiment, not a language experiment (spec §12.2), and the round-trip test is
    what keeps it honest.

    This is also what makes condition F constructible: F is this same shortening applied over
    *plain K0*, delivering comparable token counts while introducing no new semantics at all.

    Symbols avoid the lexer's structural characters (`( ) , : < >`), since a symbol containing
    one would silently split into two tokens and corrupt both the parse and the token count.
    """

    name = "compact"
    symbols = {
        "add": "+", "sub": "-", "mul": "*", "div": "/", "mod": "%",
        "neg": "~", "abs": "A", "min": "N", "max": "X",
        "eq": "=", "lt": "L", "le": "l", "gt": "G", "ge": "g",
        "and": "&", "or": "|", "not": "!",
        "if": "?", "tuple": "@", "fst": "F", "snd": "S",
        "nil": "[]", "cons": ".", "head": "H", "tail": "T",
        "length": "#", "index": "I", "append": "++", "range": "..",
        "some": "J", "none": "Z", "option_get_or": "??", "is_some": "Q",
        "map": "M", "filter": "P", "fold": "R", "lam": "\\",
    }

    def arity(self, op: str) -> int:
        if op == "lam":
            return 1
        sig = OPS_BY_NAME.get(op)
        if sig is not None:
            return sig.arity
        return self._primitive_arity[op]

    def __init__(
        self,
        primitive_symbols: dict[str, str] | None = None,
        primitive_arity: dict[str, int] | None = None,
    ) -> None:
        super().__init__(primitive_symbols)
        self._primitive_arity = dict(primitive_arity or {})

    def render(self, term: Term) -> str:
        op = term.op
        if op == "const_int":
            return str(term.attr("value"))
        if op == "const_bool":
            return "true" if term.attr("value") else "false"
        if op == "var":
            return str(term.attr("name"))
        if op in ("nil", "none"):
            return f"{self.symbol(op)} {term.attr('elem_type')}"
        if op == "lam":
            params = term.attr("params")
            head = " ".join(f"{n}:{t}" for n, t in params)
            return f"{self.symbol(op)} {len(params)} {head} {self.render(term.args[0])}"
        if not term.args:
            return self.symbol(op)  # pragma: no cover
        return self.symbol(op) + " " + " ".join(self.render(a) for a in term.args)

    def parse(self, text: str) -> Term:
        reader = _Reader(tokenize(text))
        term = self._parse(reader)
        if not reader.done():
            raise ValueError(f"trailing tokens: {reader.tokens[reader.i:]}")
        return term

    def _parse(self, r: _Reader) -> Term:
        tok = r.next()
        if re.fullmatch(r"-?\d+", tok):
            return Term("const_int", (), (("value", int(tok)),))
        if tok in ("true", "false"):
            return Term("const_bool", (), (("value", tok == "true"),))
        op = self.op_for(tok)
        if op in ("nil", "none"):
            return Term(op, (), (("elem_type", self._read_type(r)),))
        if op == "lam":
            count = int(r.next())
            params: list[tuple[str, Ty]] = []
            for _ in range(count):
                name = r.next()
                r.expect(":")
                params.append((name, self._read_type(r)))
            body = self._parse(r)
            return Term(op, (body,), (("params", tuple(params)),))
        if op in OPS_BY_NAME or op in self._primitive_arity:
            args = tuple(self._parse(r) for _ in range(self.arity(op)))
            return Term(op, args)
        return Term("var", (), (("name", tok),))

    def _read_type(self, r: _Reader) -> Ty:
        """Types are written `List<Int>`; the lexer splits the brackets, so reassemble."""
        chunks = [r.next()]
        depth = 0
        while r.peek() == "<" or depth > 0:
            tok = r.next()
            if tok == "<":
                depth += 1
            elif tok == ">":
                depth -= 1
            chunks.append(tok)
        return parse_type("".join(chunks))


# --- human projection -----------------------------------------------------------------------


class HumanProjection(Projection):
    """`add(x, 1)` — descriptive names, explicit typing, debuggable (spec §12.1 class 1).

    P8: this is a view for humans. It is never the canonical semantics, and
    `tests/bsir/test_projection_is_not_canonical.py` asserts no code path treats it as such.
    """

    name = "human"

    def render(self, term: Term) -> str:
        op = term.op
        if op == "const_int":
            return str(term.attr("value"))
        if op == "const_bool":
            return "true" if term.attr("value") else "false"
        if op == "var":
            return str(term.attr("name"))
        if op == "nil":
            return f"emptyList<{term.attr('elem_type')}>"
        if op == "none":
            return f"noValue<{term.attr('elem_type')}>"
        if op == "lam":
            params = ", ".join(f"{n}: {t}" for n, t in term.attr("params"))
            return f"fn({params}) => {self.render(term.args[0])}"
        inner = ", ".join(self.render(a) for a in term.args)
        return f"{self.symbol(op)}({inner})"

    def parse(self, text: str) -> Term:
        reader = _Reader(tokenize(text))
        term = self._parse(reader)
        if not reader.done():
            raise ValueError(f"trailing tokens: {reader.tokens[reader.i:]}")
        return term

    def _parse(self, r: _Reader) -> Term:
        tok = r.next()
        if re.fullmatch(r"-?\d+", tok):
            return Term("const_int", (), (("value", int(tok)),))
        if tok in ("true", "false"):
            return Term("const_bool", (), (("value", tok == "true"),))
        if tok in ("emptyList", "noValue"):
            r.expect("<")
            ty = self._read_type_until_gt(r)
            return Term("nil" if tok == "emptyList" else "none", (), (("elem_type", ty),))
        if tok == "fn":
            r.expect("(")
            params: list[tuple[str, Ty]] = []
            while r.peek() != ")":
                if r.peek() == ",":
                    r.next()
                    continue
                name = r.next()
                r.expect(":")
                params.append((name, self._read_type_until(r, {",", ")"})))
            r.expect(")")
            r.expect("=>")
            body = self._parse(r)
            return Term("lam", (body,), (("params", tuple(params)),))
        if r.peek() == "(":
            r.expect("(")
            op = self.op_for(tok)
            args = []
            while r.peek() != ")":
                if r.peek() == ",":
                    r.next()
                    continue
                args.append(self._parse(r))
            r.expect(")")
            return Term(op, tuple(args))
        return Term("var", (), (("name", tok),))

    def _read_type_until_gt(self, r: _Reader) -> Ty:
        chunks: list[str] = []
        depth = 0
        while True:
            tok = r.next()
            if tok == ">" and depth == 0:
                break
            if tok == "<":
                depth += 1
            elif tok == ">":
                depth -= 1
            chunks.append(tok)
        return parse_type("".join(chunks))

    def _read_type_until(self, r: _Reader, stops: set[str]) -> Ty:
        chunks: list[str] = []
        depth = 0
        while True:
            tok = r.peek()
            if tok is None:
                break
            if depth == 0 and tok in stops:
                break
            tok = r.next()
            if tok == "<":
                depth += 1
            elif tok == ">":
                depth -= 1
            chunks.append(tok)
        return parse_type("".join(chunks))


# --- graph serialization --------------------------------------------------------------------


class GraphProjection(Projection):
    """Node/edge serialization (spec §12.1 class 4), one assignment per line.

    This is the surface ablation node A4 mutates over: an explicit node list makes structural
    edits addressable in a way nested text does not.
    """

    name = "graph"

    def render(self, term: Term) -> str:
        lines: list[str] = []
        ids: dict[int, str] = {}

        def emit(node: Term) -> str:
            key = id(node)
            if key in ids:
                return ids[key]
            operands = [emit(a) for a in node.args]
            name = f"n{len(lines)}"
            attrs = ""
            if node.op == "const_int":
                attrs = f" value={node.attr('value')}"
            elif node.op == "const_bool":
                attrs = f" value={'true' if node.attr('value') else 'false'}"
            elif node.op == "var":
                attrs = f" name={node.attr('name')}"
            elif node.op in ("nil", "none"):
                attrs = f" elem_type={node.attr('elem_type')}"
            elif node.op == "lam":
                params = ";".join(f"{n}:{t}" for n, t in node.attr("params"))
                attrs = f" params={params}"
            lines.append(f"{name} = {node.op}{attrs} " + " ".join(operands))
            ids[key] = name
            return name

        emit(term)
        return "\n".join(lines)

    def parse(self, text: str) -> Term:
        env: dict[str, Term] = {}
        last: Term | None = None
        for raw in text.strip().splitlines():
            line = raw.strip()
            if not line:
                continue
            name, _, rhs = line.partition(" = ")
            parts = rhs.split()
            op = parts[0]
            attrs: list[tuple[str, object]] = []
            operands: list[Term] = []
            for part in parts[1:]:
                if "=" in part and not part.startswith("n"):
                    key, _, value = part.partition("=")
                    attrs.append((key, self._decode_attr(op, key, value)))
                elif part in env:
                    operands.append(env[part])
                else:
                    key, _, value = part.partition("=")
                    attrs.append((key, self._decode_attr(op, key, value)))
            last = Term(op, tuple(operands), tuple(attrs))
            env[name] = last
        if last is None:
            raise ValueError("empty graph projection")
        return last

    @staticmethod
    def _decode_attr(op: str, key: str, value: str) -> object:
        if key == "value":
            if op == "const_bool":
                return value == "true"
            return int(value)
        if key == "elem_type":
            return parse_type(value)
        if key == "params":
            out = []
            for chunk in value.split(";"):
                name, _, ty = chunk.partition(":")
                out.append((name, parse_type(ty)))
            return tuple(out)
        return value


PROJECTIONS: dict[str, type[Projection]] = {
    "human": HumanProjection,
    "sexpr": SExprProjection,
    "compact": CompactProjection,
    "graph": GraphProjection,
}


def get_projection(name: str, primitive_symbols: dict[str, str] | None = None) -> Projection:
    if name not in PROJECTIONS:
        raise KeyError(f"unknown projection {name!r}; have {sorted(PROJECTIONS)}")
    return PROJECTIONS[name](primitive_symbols)


def all_projections(
    primitive_symbols: dict[str, str] | None = None,
) -> Iterator[Projection]:
    for name in PROJECTIONS:
        yield get_projection(name, primitive_symbols)


def iter_names() -> Iterable[str]:
    return PROJECTIONS.keys()
