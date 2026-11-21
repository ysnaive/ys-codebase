"""Test package configuration and path roots for Core 2.0 verification suites."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Final

TESTS_ROOT: Final[Path] = Path(__file__).resolve().parent
CORE_V2_ROOT: Final[Path] = TESTS_ROOT.parent
CORE_SRC_ROOT: Final[Path] = CORE_V2_ROOT / "source" / "core"

for _sys_entry in (str(CORE_V2_ROOT), str(CORE_SRC_ROOT)):
    if _sys_entry not in sys.path:
        sys.path.insert(0, _sys_entry)

__all__ = (
    "CORE_SRC_ROOT",
    "CORE_V2_ROOT",
    "TESTS_ROOT",
)
