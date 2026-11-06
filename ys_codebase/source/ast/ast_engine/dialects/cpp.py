"""
C++ dialect adapter for module:ast.
Supports `::` scope separator, access_specifier sibling inheritance, out-of-line `ClassName::method` resolution, and `#include`/`using` extraction.
"""

from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

from .base import DialectAdapter

_INCLUDE_RE = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE)
_USING_NS_RE = re.compile(r"^\s*using\s+namespace\s+([a-zA-Z0-9_:]+)\s*;", re.MULTILINE)
_USING_ALIAS_RE = re.compile(r"^\s*using\s+([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_:]+)\s*;", re.MULTILINE)


class CppDialect(DialectAdapter):
    language = "cpp"
    scope_separator = "::"
    supports_partial_aggregation = False

    @staticmethod
    def _strip_template_args(text: str) -> str:
        """Remove balanced `<...>` template parameter segments from C++ qualified names."""
        if "<" not in text:
            return text
        out: list[str] = []
        depth = 0
        for ch in text:
            if ch == "<":
                depth += 1
            elif ch == ">":
                depth = max(0, depth - 1)
            elif depth == 0:
                out.append(ch)
        return "".join(out).strip()

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
            cleaned_name = self._strip_template_args(name)
            cpp_parts = [p.strip() for p in cleaned_name.split("::") if p.strip()]
            if len(cpp_parts) >= 2:
                return cpp_parts[-1], cpp_parts[-2], "method"
        return name, parent_scope, kind

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        for m in _INCLUDE_RE.finditer(source_text):
            header = m.group(1).strip()
            stem = Path(header).stem
            imports[header] = header
            imports[stem] = header
        for m in _USING_NS_RE.finditer(source_text):
            ns = m.group(1).strip()
            last = ns.split("::")[-1]
            imports[last] = ns
        for m in _USING_ALIAS_RE.finditer(source_text):
            imports[m.group(1).strip()] = m.group(2).strip()
        return imports
