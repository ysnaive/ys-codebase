"""
JavaScript dialect adapter for module:ast.
"""

import re
from typing import Any, Dict, Optional

from .base import DialectAdapter

_ES_IMPORT_RE = re.compile(
    r"\bimport\s+(?:type\s+)?([^\n;]+?)\s+from\s+['\"]([^'\"]+)['\"]"
)
_ES_EXPORT_ALL_RE = re.compile(
    r"\bexport\s+\*\s+from\s+['\"]([^'\"]+)['\"]"
)
_REQ_DESTRUCT_RE = re.compile(
    r"(?:const|let|var)\s+\{\s*([^}]+)\s*\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)"
)
_REQ_SINGLE_RE = re.compile(
    r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)"
)


class JavaScriptDialect(DialectAdapter):
    language = "javascript"
    scope_separator = "."
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
        for v in ("public", "protected", "private", "internal"):
            if v in mods:
                return v
        if short_name.startswith("#"):
            return "private"
        return default_vis or "public"

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        imports: Dict[str, str] = {}
        if not source_text:
            return imports
        for m in _ES_IMPORT_RE.finditer(source_text):
            clause = m.group(1).strip()
            src = m.group(2).strip()
            if "{" in clause and "}" in clause:
                b_start = clause.find("{")
                b_end = clause.rfind("}")
                before_brace = clause[:b_start].strip().rstrip(",").strip()
                if before_brace.startswith("type "):
                    before_brace = before_brace[5:].strip()
                if before_brace:
                    imports[before_brace] = src
                named_part = clause[b_start + 1 : b_end]
                for item in named_part.split(","):
                    item = item.strip()
                    if item.startswith("type "):
                        item = item[5:].strip()
                    if " as " in item:
                        orig, alias = item.split(" as ", 1)
                        imports[alias.strip()] = f"{src}.{orig.strip()}"
                    elif item:
                        imports[item] = f"{src}.{item}"
            else:
                for part in clause.split(","):
                    part = part.strip()
                    if part.startswith("type "):
                        part = part[5:].strip()
                    if part.startswith("* as "):
                        alias = part[5:].strip()
                        if alias:
                            imports[alias] = src
                    elif part:
                        imports[part] = src

        for m in _REQ_DESTRUCT_RE.finditer(source_text):
            src = m.group(2)
            for item in m.group(1).split(","):
                item = item.strip()
                if ":" in item:
                    orig, alias = item.split(":", 1)
                    imports[alias.strip()] = f"{src}.{orig.strip()}"
                elif item:
                    imports[item] = f"{src}.{item}"
        for m in _REQ_SINGLE_RE.finditer(source_text):
            imports[m.group(1).strip()] = m.group(2).strip()
        for m in _ES_EXPORT_ALL_RE.finditer(source_text):
            src = m.group(1).strip()
            imports[f"export*:{src}"] = f"{src}.*"
        return imports
