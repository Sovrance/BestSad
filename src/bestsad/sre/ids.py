"""Canonical serialization and content-addressed identity for SRE-Core objects.

Two implementations of SRE-Core have to agree on object identity byte for byte (ADR 0012), so
the serialization is pinned here rather than left to whatever each language's JSON encoder
does by default:

* keys sorted lexicographically, so field order in a struct is irrelevant;
* no insignificant whitespace, so a pretty-printer cannot change an id;
* UTF-8 with escapes disabled, so the same text is the same bytes in Go and Python;
* the ``id`` field excluded from its own digest, since it is the digest.

The ``sha256:`` prefix is required on the wire (ADR 0015). BestSad's native digests are bare
hex, so every crossing of that boundary goes through :func:`as_content_id` or
:func:`bare_digest` rather than through string formatting at the call site.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

#: A content id as it appears in SRE wire objects.
CONTENT_ID_RE = re.compile(r"^sha256:[a-f0-9]{64}$")

#: A BestSad-native digest: bare lowercase hex, as `hashlib.sha256(...).hexdigest()` returns.
BARE_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")

#: Excluded from an object's own digest — an id cannot contribute to computing itself.
_ID_FIELD = "id"


class ContentIdError(ValueError):
    """A digest or content id was not in the form its side of the boundary requires."""


def as_content_id(digest: str) -> str:
    """BestSad-native bare hex digest -> SRE wire content id.

    Rejects an already-prefixed value rather than returning it unchanged. Silently accepting
    both forms is how a `sha256:sha256:...` reaches a consumer.
    """
    if not BARE_DIGEST_RE.match(digest):
        raise ContentIdError(
            f"expected a bare 64-character lowercase hex digest, got {digest!r}"
        )
    return f"sha256:{digest}"


def bare_digest(content_id: str) -> str:
    """SRE wire content id -> BestSad-native bare hex digest.

    Rejects an unprefixed value. A bare digest arriving where a content id was expected means
    some producer skipped the boundary conversion, and passing it through would hide that.
    """
    if not CONTENT_ID_RE.match(content_id):
        raise ContentIdError(f"expected a 'sha256:'-prefixed content id, got {content_id!r}")
    return content_id.split(":", 1)[1]


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """The exact bytes an SRE object's digest is taken over."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_id(payload: Mapping[str, Any]) -> str:
    """Content-addressed id of an SRE object, ignoring any ``id`` already present."""
    body = {k: v for k, v in payload.items() if k != _ID_FIELD}
    return f"sha256:{hashlib.sha256(canonical_json(body)).hexdigest()}"


def with_content_id(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``payload`` with its ``id`` field set to its own content id."""
    return {**payload, _ID_FIELD: content_id(payload)}
