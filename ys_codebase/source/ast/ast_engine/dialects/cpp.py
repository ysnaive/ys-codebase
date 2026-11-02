"""
C++ dialect adapter for module:ast.
Supports `::` scope separator, access_specifier sibling inheritance, out-of-line `ClassName::method` resolution, and `#include`/`using` extraction.
"""

from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

from .base import DialectAdapter


class CppDialect(DialectAdapter):
    language = "cpp"
    scope_separator = "::"
    supports_partial_aggregation = False

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
        for v in ("public", "protected", "private"):
            if v in mods:
                return v
        if node is not None:
            try:
                curr = node.prev_named_sibling
                while curr is not None:
                    if curr.type == "access_specifier":
                        spec_txt = curr.text.decode("utf-8", errors="replace").strip().rstrip(":").strip().lower()
                        if spec_txt in ("public", "protected", "private"):
                            return spec_txt
                        break
                    curr = curr.prev_named_sibling
            except Exception:
                pass
        if parent_kind == "class":
            return "private"
        return default_vis or "public"

    def resolve_out_of_line_scope(
        self,
        name: str,
        parent_scope: str,
        kind: str = "",
    ) -> Tuple[str, str, str]:
        if "::" in name and kind in ("function", "method", ""):
            cpp_parts = name.split("::")
            return cpp_parts[-1], cpp_parts[-2], "method"
        return name, parent_scope, kind

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        inc_re = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE)
        for m in inc_re.finditer(source_text):
            header = m.group(1).strip()
            stem = Path(header).stem
            imports[header] = header
            imports[stem] = header
        using_ns = re.compile(r"^\s*using\s+namespace\s+([a-zA-Z0-9_:]+);", re.MULTILINE)
        for m in using_ns.finditer(source_text):
            ns = m.group(1).strip()
            last = ns.split("::")[-1]
            imports[last] = ns
        using_alias = re.compile(r"^\s*using\s+([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_:]+);", re.MULTILINE)
        for m in using_alias.finditer(source_text):
            imports[m.group(1).strip()] = m.group(2).strip()
        return imports
