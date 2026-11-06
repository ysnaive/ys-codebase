"""
C# dialect adapter for module:ast.
Supports partial class/struct/interface aggregation, compound visibility modifiers, and using directives.
"""

import re
from typing import Any, Dict, List, Optional

from .base import DialectAdapter

_USING_ALIAS_RE = re.compile(
    r"^\s*(?:global\s+)?using\s+([a-zA-Z0-9_]+)\s*=\s*([a-zA-Z0-9_.]+)\s*;",
    re.MULTILINE,
)
_USING_RE = re.compile(
    r"^\s*(?:global\s+)?using\s+(?:static\s+)?([a-zA-Z0-9_.]+)\s*;",
    re.MULTILINE,
)


class CSharpDialect(DialectAdapter):
    language = "c_sharp"
    scope_separator = "."
    supports_partial_aggregation = True

    def post_process_raw_item(self, item: Dict[str, Any], def_node: Any) -> None:
        if def_node is not None and getattr(def_node, "type", "") == "file_scoped_namespace_declaration":
            item["is_file_scoped_namespace"] = True
            root_node = def_node
            while getattr(root_node, "parent", None) is not None:
                root_node = root_node.parent
            if getattr(root_node, "end_byte", 0) > item.get("end_byte", 0):
                item["end_byte"] = root_node.end_byte

    def finalize_raw_items(self, raw_items: List[Dict[str, Any]], lines: List[str]) -> List[Dict[str, Any]]:
        if not raw_items:
            return raw_items
        max_end_byte = max((int(it.get("end_byte", 0)) for it in raw_items), default=0)
        total_lines = max(len(lines), max((int(it.get("end_line", 0)) for it in raw_items), default=0))
        for item in raw_items:
            if item.get("is_file_scoped_namespace"):
                item["end_line"] = max(int(item.get("end_line", 0)), total_lines)
                item["end_byte"] = max(int(item.get("end_byte", 0)), max_end_byte)
        return raw_items

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
        for m in _USING_ALIAS_RE.finditer(source_text):
            imports[m.group(1).strip()] = m.group(2).strip()
        for m in _USING_RE.finditer(source_text):
            ns = m.group(1).strip()
            if "=" in ns:
                continue
            last = ns.split(".")[-1]
            imports[last] = ns
            imports[ns] = ns
        return imports
