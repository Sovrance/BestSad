"""v0.1 constraint 3: existing BestSad semantic hashes are preserved.

The semantic reconstruction work adds BSIR levels, an equivalence layer, a descriptor-driven
frontend and an SRE boundary. None of that is allowed to move `semantic_hash`, because the
hash is the identity of every program, primitive and certificate already recorded — a shifted
hash silently invalidates the assurance graph rather than failing loudly.

These digests are pinned literals captured from the pre-v0.1 implementation. If a change makes
this file fail, the change altered canonical semantics; re-pinning the values is not the fix.
"""

from __future__ import annotations

import unittest

from bestsad.bsir import semantic_hash, structural_hash
from bestsad.kernel import INT, Program, app, const_int, lam, var


class SemanticHashIsStable(unittest.TestCase):
    """Pinned against the implementation as of the v0.1 baseline."""

    def test_scalar_program(self):
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        self.assertEqual(
            semantic_hash(p),
            "0a3929ad19807bd1d9bc4b375f7945580bd3b787d94293f05a4a301685301d93",
        )

    def test_higher_order_program(self):
        p = Program(
            (("x", INT),),
            app(
                "map",
                lam((("u", INT),), app("mul", var("u"), const_int(2))),
                app("range", const_int(0), const_int(3)),
            ),
            None,
        )
        self.assertEqual(
            semantic_hash(p),
            "1890bd3afa277249c5a283d2923dec487c9dc83a53494689531286329e61a4ae",
        )

    def test_constant_program(self):
        p = Program((), const_int(42), INT)
        self.assertEqual(
            semantic_hash(p),
            "00ea038d9ccbee6d281a5ebfbf1be22563c5d00c7bb1892e674e36100530325d",
        )

    def test_structural_hash_is_also_stable(self):
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        self.assertEqual(
            structural_hash(p.body),
            "4a410cf9da85f792ac68cd500e622c8319928e628b663aada2a1f0d9bb5d7400",
        )

    def test_hashes_are_bare_hex_not_prefixed(self):
        """ADR 0015: BestSad-native digests stay bare; the prefix is added only at the SRE
        boundary. A prefix leaking into `semantic_hash` would change every stored id."""
        p = Program((("x", INT),), app("add", var("x"), const_int(1)), INT)
        h = semantic_hash(p)
        self.assertNotIn(":", h)
        self.assertEqual(len(h), 64)


if __name__ == "__main__":
    unittest.main()
