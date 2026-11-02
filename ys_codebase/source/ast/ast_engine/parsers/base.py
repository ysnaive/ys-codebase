"""
Base abstract parser class (BaseParser) for module:ast.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Union

from ..schema import SymbolCallSite, UnifiedSymbol


class BaseParser(ABC):
    """Multi-language AST symbol parser abstract interface."""

    @abstractmethod
    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """Return True if this parser supports parsing `file_path`."""

    @abstractmethod
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """Parse `content` of `file_path` in `space` and return a list of UnifiedSymbol instances."""

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        """Extract symbol call sites from `content`."""
        return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """Extract file-level import/include alias mappings from `content`."""
        return {}
