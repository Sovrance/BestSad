"""BSLD — the Bestsad Semantic Language Description (design §7.2, ADR 0014).

A descriptor declares an evolved language: its operations, their operand and result types,
their effects, and how each lowers into BSIR. It is **data**. There is no place in a descriptor
to put code, which is the property that lets BestSad accept a language it did not write without
trusting a compiler it did not write.

The descriptor's identity is the content address of its own body, so "which language was this
program written in" has an answer that cannot be forged by renaming.

What a descriptor cannot do is make its lowering true by asserting it. Every operation carries
proof obligations, `lowering_semantic_equivalence` foremost, and those are discharged by
evidence elsewhere (`bsir/equivalence.py`) or else recorded as open. See `lowering.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from ..kernel.types import BOOL, INT, TList, TOption, TTuple, Ty
from ..sre.ids import canonical_json, content_id

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "bsld-descriptor.schema.json"

#: The obligation every descriptor operation carries: that its lowering means what it says.
LOWERING_EQUIVALENCE = "lowering_semantic_equivalence"


class DescriptorError(ValueError):
    """A descriptor is malformed, or claims something the frontend will not accept."""


def _parse_type(text: str) -> Ty:
    """Parse a descriptor type expression.

    Deliberately small: `Int`, `Bool`, `List<T>`, `Option<T>`, `Tuple<A,B>`. A descriptor that
    needs more expressive types than this is asking for a v0.1 extension with matching
    obligation checking, not for a looser parser.
    """
    text = text.strip()
    if text == "Int":
        return INT
    if text == "Bool":
        return BOOL
    for name, ctor in (("List", TList), ("Option", TOption)):
        prefix = f"{name}<"
        if text.startswith(prefix) and text.endswith(">"):
            return ctor(_parse_type(text[len(prefix):-1]))
    if text.startswith("Tuple<") and text.endswith(">"):
        inner = text[len("Tuple<"):-1]
        depth = 0
        for i, ch in enumerate(inner):
            if ch == "<":
                depth += 1
            elif ch == ">":
                depth -= 1
            elif ch == "," and depth == 0:
                return TTuple(_parse_type(inner[:i]), _parse_type(inner[i + 1:]))
        raise DescriptorError(f"Tuple type needs two parameters: {text!r}")
    raise DescriptorError(f"unsupported descriptor type {text!r}")


@dataclass(frozen=True, slots=True)
class LoweringTemplate:
    """How one descriptor operation becomes BSIR.

    `args` holds either `"$n"` positional references to the source operation's operands, or
    nested templates. That is the whole language: no conditionals, no repetition, no recursion.
    """

    op: str
    args: tuple[Any, ...] = ()
    attrs: tuple[tuple[str, Any], ...] = ()

    @staticmethod
    def from_wire(payload: Mapping[str, Any]) -> "LoweringTemplate":
        args: list[Any] = []
        for arg in payload.get("args", ()):
            if isinstance(arg, str):
                args.append(arg)
            elif isinstance(arg, Mapping):
                args.append(LoweringTemplate.from_wire(arg))
            else:
                raise DescriptorError(f"malformed lowering argument {arg!r}")
        attrs = tuple(sorted((payload.get("attrs") or {}).items()))
        return LoweringTemplate(op=payload["op"], args=tuple(args), attrs=attrs)

    def operand_indices(self) -> set[int]:
        """Every `$n` this template (and its nested templates) references."""
        found: set[int] = set()
        for arg in self.args:
            if isinstance(arg, str):
                found.add(int(arg[1:]))
            else:
                found |= arg.operand_indices()
        return found


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """One declared operation of a described language."""

    name: str
    operands: tuple[Ty, ...]
    result: Ty
    effects: frozenset[str]
    lowers_to: LoweringTemplate
    proof_obligations: tuple[str, ...] = (LOWERING_EQUIVALENCE,)

    @property
    def arity(self) -> int:
        return len(self.operands)


@dataclass(frozen=True, slots=True)
class LanguageDescriptor:
    """A complete BSLD descriptor."""

    language_id: str
    version: int
    operations: Mapping[str, OperationSpec]
    surface: Mapping[str, Any] = field(default_factory=dict)
    proof_obligations: tuple[str, ...] = ()

    def operation(self, name: str) -> OperationSpec:
        try:
            return self.operations[name]
        except KeyError:
            raise DescriptorError(
                f"{name!r} is not an operation of language {self.language_id}"
            ) from None


def _schema() -> dict[str, Any]:
    if not SCHEMA_PATH.exists():  # pragma: no cover - packaging error, not a code path
        raise DescriptorError(f"missing BSLD schema at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def descriptor_id(payload: Mapping[str, Any]) -> str:
    """Content address of a descriptor body, excluding its own `language_id`."""
    body = {k: v for k, v in payload.items() if k != "language_id"}
    return "lang:" + content_id(body)


def parse(payload: Mapping[str, Any], *, validate: bool = True) -> LanguageDescriptor:
    """Build a `LanguageDescriptor` from descriptor data.

    Validation is on by default and checks two different things: that the descriptor matches
    the schema, and that each lowering template is *coherent with its own declaration* — that
    it references only operands the operation actually has, and none of them out of range. A
    schema cannot express that second check, and it is exactly the kind of mistake a generated
    descriptor makes.
    """
    if validate:
        try:
            jsonschema.validate(instance=dict(payload), schema=_schema())
        except jsonschema.ValidationError as exc:
            raise DescriptorError(f"descriptor does not match the BSLD schema: {exc.message}") from exc

    operations: dict[str, OperationSpec] = {}
    for name, spec in payload["operations"].items():
        template = LoweringTemplate.from_wire(spec["lowers_to"])
        operands = tuple(_parse_type(t) for t in spec["operands"])

        referenced = template.operand_indices()
        out_of_range = {i for i in referenced if i >= len(operands)}
        if out_of_range:
            raise DescriptorError(
                f"operation {name!r} lowers using operand(s) "
                f"{sorted(out_of_range)} but declares only {len(operands)}"
            )

        operations[name] = OperationSpec(
            name=name,
            operands=operands,
            result=_parse_type(spec["result"]),
            effects=frozenset(spec.get("effects") or ()),
            lowers_to=template,
            proof_obligations=tuple(spec.get("proof_obligations") or (LOWERING_EQUIVALENCE,)),
        )

    declared = payload["language_id"]
    computed = descriptor_id(payload)
    if declared != computed:
        raise DescriptorError(
            f"descriptor language_id {declared} does not match its content address {computed}"
        )

    return LanguageDescriptor(
        language_id=declared,
        version=payload["version"],
        operations=operations,
        surface=dict(payload.get("surface") or {}),
        proof_obligations=tuple(payload.get("proof_obligations") or ()),
    )


def seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return `payload` with `language_id` set to its own content address."""
    body = {k: v for k, v in payload.items() if k != "language_id"}
    return {**body, "language_id": descriptor_id(body)}


def load(path: str | Path) -> LanguageDescriptor:
    return parse(json.loads(Path(path).read_text(encoding="utf-8")))


def serialize(descriptor_payload: Mapping[str, Any]) -> bytes:
    """Canonical bytes of a descriptor, for storage or hashing."""
    return canonical_json(descriptor_payload)
