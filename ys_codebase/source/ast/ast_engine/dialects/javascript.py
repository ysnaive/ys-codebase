"""
JavaScript dialect adapter for module:ast.
"""

import re
from typing import Any, Dict, Optional

from .base import DialectAdapter


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
        es_import = re.compile(r"import\s+(?:\{([^}]+)\}|([a-zA-Z0-9_$]+))\s+from\s+['\"]([^'\"]+)['\"]")
        for m in es_import.finditer(source_text):
            src = m.group(3)
            if m.group(2):
                imports[m.group(2).strip()] = src
            if m.group(1):
                for item in m.group(1).split(","):
                    item = item.strip()
                    if " as " in item:
                        orig, alias = item.split(" as ", 1)
                        imports[alias.strip()] = f"{src}.{orig.strip()}"
                    elif item:
                        imports[item] = f"{src}.{item}"
        req_destruct = re.compile(r"(?:const|let|var)\s+\{\s*([^}]+)\s*\}\s*=\s*require\(['\"]([^'\"]+)['\"]\)")
        for m in req_destruct.finditer(source_text):
            src = m.group(2)
            for item in m.group(1).split(","):
                item = item.strip()
                if ":" in item:
                    orig, alias = item.split(":", 1)
                    imports[alias.strip()] = f"{src}.{orig.strip()}"
                elif item:
                    imports[item] = f"{src}.{item}"
        req_single = re.compile(r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*require\(['\"]([^'\"]+)['\"]\)")
        for m in req_single.finditer(source_text):
            imports[m.group(1).strip()] = m.group(2).strip()
        return imports
