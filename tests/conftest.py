"""Root conftest: make `tests` importable as a package however pytest is invoked.

`tests/models/scripts.py` holds scripted model behaviours that a model spec names as
`tests.models.scripts:<function>` so the name can cross the process boundary and sit in a
checkpoint key. `python -m pytest` puts the repository root on `sys.path` and the name resolves;
a bare `pytest` (what `ci.yml` runs) does not. Because `tests/` is a package, pytest imports this
file as `tests.conftest` and prepends the repository root to `sys.path` before collecting any
test module, which makes the two invocations behave the same.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
