"""K0 kernel identity (spec §8.4).

Every artifact records `kernel_version`. A change to K0 semantics starts a new experiment
lineage and may not be mixed with previous fitness results.

`KERNEL_VERSION_HASH` is derived from the operation table *and* the resource limits, because
the limits determine which programs trap and are therefore semantics, not tuning (ADR-0008).
`tests/kernel/test_frozen.py` pins the hash: an accidental kernel edit fails CI instead of
silently invalidating every comparison downstream.
"""

from __future__ import annotations

import hashlib
import json

from .ops import (
    DEFAULT_DEPTH_LIMIT,
    DEFAULT_FUEL,
    INT_ABS_LIMIT,
    K0_OPS,
    LIST_LEN_LIMIT,
)

KERNEL_VERSION = "K0-1.0.0"


def kernel_descriptor() -> dict:
    """The canonical, serializable description of K0 that the version hash is taken over."""
    return {
        "kernel_version": KERNEL_VERSION,
        "operations": [
            {
                "op": o.op,
                "family": o.family,
                "params": [str(p) for p in o.params],
                "ret": str(o.ret),
                "attrs": list(o.attrs),
                "strict": o.strict,
                "traps": list(o.traps),
            }
            for o in K0_OPS
        ],
        "limits": {
            "int_abs_limit": INT_ABS_LIMIT,
            "list_len_limit": LIST_LEN_LIMIT,
            "default_fuel": DEFAULT_FUEL,
            "default_depth_limit": DEFAULT_DEPTH_LIMIT,
        },
    }


def kernel_version_hash() -> str:
    payload = json.dumps(kernel_descriptor(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


#: Pinned by `tests/kernel/test_frozen.py`. Changing K0 means updating this constant *and*
#: writing an ADR *and* starting a new experiment lineage — in that order.
KERNEL_VERSION_HASH = kernel_version_hash()
