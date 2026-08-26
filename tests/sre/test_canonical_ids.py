"""Pinned canonical-serialization and content-id vectors (ADR 0012).

These literals are the interoperability contract. A Go implementation of SRE-Core must produce
exactly these bytes and exactly these digests for the same objects; if this file has to be
edited to make BestSad pass, the two implementations have diverged and the edit is the bug
report.
"""

from __future__ import annotations

import unittest

from bestsad.sre import ids


class CanonicalSerialization(unittest.TestCase):
    def test_keys_are_sorted_so_field_order_cannot_move_an_id(self):
        a = {"b": 1, "a": 2, "c": 3}
        b = {"c": 3, "a": 2, "b": 1}
        self.assertEqual(ids.canonical_json(a), ids.canonical_json(b))
        self.assertEqual(ids.content_id(a), ids.content_id(b))

    def test_serialization_has_no_insignificant_whitespace(self):
        self.assertEqual(
            ids.canonical_json({"a": 1, "b": [1, 2]}),
            b'{"a":1,"b":[1,2]}',
        )

    def test_non_ascii_is_utf8_not_escaped(self):
        # A Go encoder writes the rune; Python's default would write \uXXXX. Those are
        # different bytes and therefore different ids, so the encoder is pinned.
        self.assertEqual(ids.canonical_json({"k": "é"}), '{"k":"é"}'.encode("utf-8"))

    def test_nan_is_refused_rather_than_serialized(self):
        with self.assertRaises(ValueError):
            ids.canonical_json({"k": float("nan")})

    def test_id_field_is_excluded_from_its_own_digest(self):
        payload = {"kind": "bsir-graph", "digest": "sha256:" + "a" * 64}
        stamped = ids.with_content_id(payload)
        self.assertEqual(ids.content_id(stamped), stamped["id"])
        self.assertEqual(ids.content_id(payload), stamped["id"])


class PinnedVectors(unittest.TestCase):
    """Exact digests. Do not regenerate these to make a failing test pass."""

    def test_empty_object(self):
        self.assertEqual(
            ids.content_id({}),
            "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        )

    def test_artifact_ref_vector(self):
        payload = {"kind": "bsir-graph", "digest": "sha256:" + "0" * 64}
        self.assertEqual(
            ids.canonical_json(payload),
            b'{"digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000",'
            b'"kind":"bsir-graph"}',
        )
        self.assertEqual(
            ids.content_id(payload),
            "sha256:f8738fc1d39dd0b65a09c969a8c7f4c4c1c72abc2f547e0e384cdcb8f05eae1f",
        )


class BoundaryConversion(unittest.TestCase):
    """ADR 0015: BestSad-native bare hex on one side, prefixed content ids on the other."""

    HEX = "a" * 64

    def test_round_trip(self):
        self.assertEqual(ids.bare_digest(ids.as_content_id(self.HEX)), self.HEX)

    def test_as_content_id_refuses_an_already_prefixed_value(self):
        with self.assertRaises(ids.ContentIdError):
            ids.as_content_id(f"sha256:{self.HEX}")

    def test_bare_digest_refuses_an_unprefixed_value(self):
        # Passing this through would hide a producer that skipped the conversion.
        with self.assertRaises(ids.ContentIdError):
            ids.bare_digest(self.HEX)

    def test_uppercase_hex_is_refused_on_both_sides(self):
        with self.assertRaises(ids.ContentIdError):
            ids.as_content_id(self.HEX.upper())
        with self.assertRaises(ids.ContentIdError):
            ids.bare_digest(f"sha256:{self.HEX.upper()}")


if __name__ == "__main__":
    unittest.main()
