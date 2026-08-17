"""The kernel is frozen (spec §6.1, §8.4; `AGENTS.md` invariant 1).

These tests exist to make an accidental K0 edit fail loudly. A *deliberate* K0 change means:
write an ADR, bump `KERNEL_VERSION`, update the pin below, and start a new experiment lineage
— previous fitness results may not be mixed with results from the new kernel.
"""

from __future__ import annotations

from bestsad.kernel import K0_OPS, KERNEL_VERSION, kernel_descriptor
from bestsad.kernel.ops import op_families
from bestsad.kernel.spec import kernel_version_hash

#: Pinned K0 v1.0.0 identity. Do not "fix" this constant to make a test pass.
PINNED_KERNEL_VERSION = "K0-1.0.0"
PINNED_KERNEL_HASH = "9aa25728b3b00abc717011a72e9ca7f0a73095f14ceb8e6fc0abc4ded52b3165"


def test_kernel_version_is_pinned():
    assert KERNEL_VERSION == PINNED_KERNEL_VERSION


def test_kernel_hash_is_pinned():
    assert kernel_version_hash() == PINNED_KERNEL_HASH, (
        "K0 semantics changed. This is not a test to update casually: per spec §8.4 a kernel "
        "change starts a new experiment lineage and invalidates comparison with every "
        "previously recorded fitness result. Write an ADR first."
    )


def test_operation_count_is_within_the_specified_range():
    """Spec §8.3: 'approximately 24-40 operations'."""
    assert 24 <= len(K0_OPS) <= 40


def test_every_specified_primitive_family_is_covered():
    """Spec §8.3 enumerates the families K0 must cover."""
    families = op_families()
    for required in ("const", "arith", "cmp", "bool", "cond", "tuple", "list", "option",
                     "hof", "lam"):
        assert families.get(required, 0) > 0, f"K0 has no operations in family {required!r}"


def test_effect_set_is_pure_and_trap_only():
    """Spec §8.2: no file I/O, clock, randomness, threads, network, mutable global state,
    FFI, or reflection in K0. Enforced here by inspecting the op table for any operation
    declaring an effect beyond trapping."""
    descriptor = kernel_descriptor()
    for op in descriptor["operations"]:
        for trap in op["traps"]:
            assert trap in {
                "division_by_zero",
                "value_too_large",
                "list_too_long",
                "fuel_exhausted",
                "depth_exceeded",
                "malformed_program",
            }, f"{op['op']} declares an unknown effect {trap!r}"


def test_exactly_one_non_strict_operation():
    non_strict = [o.op for o in K0_OPS if not o.strict]
    assert non_strict == ["if"]
