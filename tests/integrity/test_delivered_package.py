"""The delivered v0.2 package has not been edited (`CONTRIBUTING.md`; spec §31.1).

`MANIFEST_SHA256.txt` pins the normative documents and schemas. Its purpose is to make it
impossible to quietly edit the specification to match the implementation — the direction of
drift a research instrument has to guard against, because it converts "the code is wrong" into
"the spec always said that" with no visible diff in the argument.

The manifest existed from the start and nothing verified it, so `README.md` drifted for a week
before a manual `sha256sum -c` caught it. A pinned hash that nothing checks is not a control,
which is what this test is for.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "MANIFEST_SHA256.txt"


def _manifest_entries() -> list[tuple[str, str]]:
    entries = []
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if len(digest) != 64 or not name:
            continue
        entries.append((digest, name.strip()))
    return entries


def test_the_manifest_is_present_and_non_empty():
    assert MANIFEST.exists(), "the delivered package's own checksum file is missing"
    # Nine root documents plus the eight v0.2 schemas, per CONTRIBUTING.md.
    assert len(_manifest_entries()) == 17


@pytest.mark.parametrize("digest,name", _manifest_entries(), ids=lambda v: Path(v).name)
def test_delivered_file_is_byte_identical(digest: str, name: str):
    """One test per file, so a failure names the document that changed."""
    path = REPO_ROOT / name
    assert path.exists(), f"delivered file {name} is missing"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == digest, (
        f"{name} differs from the delivered v0.2 package. New guidance goes in a new file "
        f"(REPOSITORY.md, docs/adr/, docs/architecture/), never by editing a delivered document."
    )
