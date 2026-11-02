"""
C# dialect adapter for module:ast.
Supports partial class/struct/interface aggregation, compound visibility modifiers, and using directives.
"""

import re
from typing import Any, Dict, Optional

from .base import DialectAdapter


class CSharpDialect(DialectAdapter):
    language = "c_sharp"
    scope_separator = "."
    supports_partial_aggregation = True

    def extract_visibility(
        self,
        node: Any,
        source_bytes: bytes = b"",
        parent_kind: Optional[str] = None,
        default_vis: str = "public",
        short_name: str = "",
        kind: str = "",
    ) -> str:
        mods = self.extract_modifiers(node)
        if "public" in mods:
            return "public"
        if "private" in mods and "protected" in mods:
            return "private"
        if "protected" in mods and "internal" in mods:
            return "protected"
        if "protected" in mods:
            return "protected"
        if "internal" in mods:
            return "internal"
        if "private" in mods:
            return "private"
        if parent_kind in ("interface", "enum"):
            return "public"
        if parent_kind in ("class", "struct"):
            return "private"
        if kind in ("class", "struct", "interface", "enum"):
            return "internal"
        return default_vis or "public"

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        using_alias = re.compile(r"^\s*using\s+([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_.]+);", re.MULTILINE)
        for m in using_alias.finditer(source_text):
            imports[m.group(1).strip()] = m.group(2).strip()
        using_re = re.compile(r"^\s*using\s+(?:static\s+)?([a-zA-Z0-9_.]+);", re.MULTILINE)
        for m in using_re.finditer(source_text):
            ns = m.group(1).strip()
            if "=" in ns:
                continue
            last = ns.split(".")[-1]
            imports[last] = ns
            imports[ns] = ns
        return imports
