"""
Python dialect adapter for module:ast.
"""

import re
from typing import Any, Dict, Optional

from .base import DialectAdapter

_IMPORT_RE = re.compile(r"^\s*import\s+([^\n]+)", re.MULTILINE)
_FROM_PARENS_RE = re.compile(
    r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s*\(([^)]*)\)",
    re.MULTILINE | re.DOTALL,
)
_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s+([^\n]+)", re.MULTILINE)


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
        if "def " in first_line:
            if "(" in first_line and first_line.count("(") <= first_line.count(")"):
                return first_line
            if captured_signature:
                prefix = first_line.split("(", 1)[0].strip()
                norm_params = " ".join(captured_signature.split())
                norm_params = re.sub(r"\(\s+", "(", re.sub(r",?\s+\)", ")", norm_params))
                return f"{prefix}{norm_params}"
            return first_line
        if "class " in first_line:
            return first_line
        return captured_signature or first_line

    def post_process_raw_item(self, item: Dict[str, Any], def_node: Any) -> None:
        ret_t = item.get("return_type", "")
        sig = item.get("signature", "")
        if ret_t and sig and "->" not in sig and item.get("kind") in ("function", "method"):
            item["signature"] = f"{sig} -> {ret_t}"

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
        for m in _IMPORT_RE.finditer(source_text):
            clause = m.group(1).split("#", 1)[0].strip().strip("()")
            for mod_item in clause.split(","):
                mod_item = mod_item.strip()
                if " as " in mod_item:
                    orig, alias = mod_item.split(" as ", 1)
                    imports[alias.strip()] = orig.strip()
                elif mod_item:
                    imports[mod_item] = mod_item

        for m in _FROM_PARENS_RE.finditer(source_text):
            base_mod = m.group(1).strip()
            cleaned_lines = [ln.split("#", 1)[0].strip() for ln in m.group(2).splitlines()]
            clause = " ".join(cleaned_lines)
            for t in clause.split(","):
                t = t.strip().strip("()")
                if " as " in t:
                    orig, alias = t.split(" as ", 1)
                    imports[alias.strip()] = f"{base_mod}.{orig.strip()}"
                elif t:
                    imports[t] = f"{base_mod}.{t}"

        for m in _FROM_IMPORT_RE.finditer(source_text):
            base_mod = m.group(1).strip()
            raw_clause = m.group(2).split("#", 1)[0].strip()
            if raw_clause.startswith("(") and ")" not in raw_clause:
                continue
            clause = raw_clause.strip("()")
            for t in clause.split(","):
                t = t.strip().strip("()")
                if " as " in t:
                    orig, alias = t.split(" as ", 1)
                    imports[alias.strip()] = f"{base_mod}.{orig.strip()}"
                elif t:
                    imports[t] = f"{base_mod}.{t}"
        return imports
