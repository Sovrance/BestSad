"""Validation of SRE-Core objects against the shared wire schemas.

The schemas in ``schemas/sre/`` are the cross-repository contract (ADR 0012). Validating here
is what makes "schema-compatible language-native libraries" a checked claim rather than an
intention: a Python object that would not survive a Go consumer fails in BestSad's own tests.

Validation is strict — every SRE schema sets ``additionalProperties: false`` — so a field this
implementation invents but the contract does not name is an error, not an extension.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

#: ``schemas/sre/`` relative to the repository root, located from this file rather than from
#: the working directory so the tests do not depend on where pytest was invoked.
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "sre"

#: Wire object name -> schema file.
SCHEMAS = {
    "ArtifactRef": "artifact-ref.schema.json",
    "Fact": "fact.schema.json",
    "EquivalenceResult": "equivalence-result.schema.json",
    "Counterexample": "counterexample.schema.json",
    "AnalyzerResult": "analyzer-result.schema.json",
}


class SchemaUnavailable(FileNotFoundError):
    """A shared schema file is missing.

    Raised rather than skipped: an unrun contract check is not a passing contract check, and
    the whole point of ADR 0012 is that agreement is verified locally.
    """


@lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    """Load one SRE schema by wire object name."""
    try:
        filename = SCHEMAS[name]
    except KeyError:
        raise KeyError(f"no SRE schema registered for {name!r}") from None
    path = SCHEMA_DIR / filename
    if not path.exists():
        raise SchemaUnavailable(f"missing SRE schema {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(name: str, payload: Mapping[str, Any]) -> None:
    """Validate a wire payload, raising ``jsonschema.ValidationError`` on failure."""
    jsonschema.validate(instance=dict(payload), schema=load(name))


def is_valid(name: str, payload: Mapping[str, Any]) -> bool:
    try:
        validate(name, payload)
    except jsonschema.ValidationError:
        return False
    return True
