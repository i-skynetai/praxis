"""The one rule every adapter follows: its dependency is a pip extra, imported lazily, and a
missing one fails with the install line, not a traceback from deep inside a vendor SDK."""

from __future__ import annotations

import importlib
from types import ModuleType

DISTRIBUTION = "praxis-core"


def require(module: str, extra: str, purpose: str = "") -> ModuleType:
    """Import ``module`` or raise an ImportError naming the extra that provides it."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        what = f" for {purpose}" if purpose else ""
        raise ImportError(
            f'{module!r} is not installed{what}. Install the extra: pip install "{DISTRIBUTION}[{extra}]"'
        ) from exc
