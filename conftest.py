"""Root pytest conftest — installs the synthetic ``kurosoden`` namespace.

The project has a FLAT layout (``shared/``, ``bots/``, ``nekofetch/``,
``tests/`` at the repo root) but all imports use the ``kurosoden.<sub>``
prefix. At runtime ``main.py`` forges that namespace before anything imports;
pytest never runs ``main.py``, so we replicate the same shim here. This module
lives at the repo root, so pytest imports it before collecting anything under
``tests/`` — meaning ``from kurosoden.tests.helpers import ...`` in
``tests/conftest.py`` resolves cleanly.

Keep this in lock-step with the shim block in ``main.py``.
"""

from __future__ import annotations

import sys
import types as _types
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Pick up top-level packages (``nekofetch``) exactly like main.py does.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ── ``kurosoden`` namespace alias ─────────────────────────────────────────────
# Register ``kurosoden`` and its top-level subpackages as lightweight
# ``ModuleType`` shims whose ``__path__`` points at the real directories, so
# ``kurosoden.<sub>.<mod>`` resolves via the normal importer. Idempotent: if
# main.py (or a prior import) already installed the namespace, leave it be.
if "kurosoden" not in sys.modules:
    _kage = _types.ModuleType("kurosoden")
    _kage.__path__ = [str(_HERE)]
    # Execute the real ``__init__.py`` into the shim so package metadata
    # (``__version__``, ``__doc__``) matches what ``import kurosoden`` would
    # yield at runtime. main.py skips this (it only needs import resolution),
    # but the package tests assert on that metadata.
    _init = _HERE / "__init__.py"
    if _init.is_file():
        _kage.__file__ = str(_init)
        exec(compile(_init.read_text(encoding="utf-8"), str(_init), "exec"), _kage.__dict__)
    sys.modules["kurosoden"] = _kage

for _sub in ("shared", "bots", "nekofetch", "tests"):
    _name = f"kurosoden.{_sub}"
    if _name not in sys.modules and (_HERE / _sub / "__init__.py").is_file():
        _shim = _types.ModuleType(_name)
        _shim.__path__ = [str(_HERE / _sub)]
        sys.modules[_name] = _shim
# ──────────────────────────────────────────────────────────────────────────────
