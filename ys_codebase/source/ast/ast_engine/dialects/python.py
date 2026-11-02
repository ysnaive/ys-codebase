"""
Python dialect adapter for module:ast.
"""

import re
from typing import Any, Dict, Optional

from .base import DialectAdapter


class PythonDialect(DialectAdapter):
    language = "python"
    scope_separator = "."
    supports_partial_aggregation = False

    def clean_docstring(self, raw_comment: str) -> str:
        if not raw_comment:
            return ""
        text = raw_comment.strip()
        for q in ('"""', "'''", '"', "'"):
            if text.startswith(q) and text.endswith(q) and len(text) >= 2 * len(q):
                return text[len(q) : -len(q)].strip()
        return super().clean_docstring(raw_comment)

    def format_signature(
        self,
        first_line: str,
        captured_signature: str,
        name: str = "",
        def_kind: str = "",
    ) -> str:
        if "def " in first_line or "class " in first_line:
            return first_line
        return captured_signature or first_line

    def extract_visibility(
        self,
        node: Any,
        source_bytes: bytes = b"",
        parent_kind: Optional[str] = None,
        default_vis: str = "public",
        short_name: str = "",
        kind: str = "",
    ) -> str:
        name_to_check = short_name
        if not name_to_check and node is not None:
            try:
                for child in node.children:
                    if child.type == "identifier":
                        name_to_check = child.text.decode("utf-8", errors="replace").strip()
                        break
            except Exception:
                pass
        if name_to_check.startswith("__") and name_to_check.endswith("__") and len(name_to_check) >= 4:
            return "public"
        if name_to_check.startswith("__") and not name_to_check.endswith("__"):
            return "private"
        if name_to_check.startswith("_"):
            return "protected"
        return default_vis or "public"

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        import_re = re.compile(r"^\s*import\s+([^\n]+)", re.MULTILINE)
        from_re = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s+([^\n]+)", re.MULTILINE)
        for m in import_re.finditer(source_text):
            for mod_item in m.group(1).split(","):
                mod_item = mod_item.strip()
                if " as " in mod_item:
                    orig, alias = mod_item.split(" as ", 1)
                    imports[alias.strip()] = orig.strip()
                elif mod_item:
                    imports[mod_item] = mod_item
        for m in from_re.finditer(source_text):
            base_mod = m.group(1).strip()
            for t in m.group(2).split(","):
                t = t.strip()
                if " as " in t:
                    orig, alias = t.split(" as ", 1)
                    imports[alias.strip()] = f"{base_mod}.{orig.strip()}"
                elif t:
                    imports[t] = f"{base_mod}.{t}"
        return imports
