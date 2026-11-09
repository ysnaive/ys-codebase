"""
Base DialectAdapter interface and shared AST/comment helpers for module:ast.
Isolates language-specific semantics from the generic TreeSitterDriver.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

_XML_TAG_RE = re.compile(r"</?[A-Za-z_][A-Za-z0-9_.:-]*(?:\s+[^<>,]*?)?/?>")
_STATIC_SIG_RE = re.compile(r"(?:^|\s|@)(?:static|staticmethod|classmethod)\b")
_GENERIC_CALL_RECEIVER_RE = re.compile(r"<\s*([A-Za-z_][A-Za-z0-9_.]*)\s*>\s*\([^)]*\)$")
_TRAILING_CALL_PARENS_RE = re.compile(r"\([^)]*\)$")
_GENERIC_ARGS_RE = re.compile(r"<[^>]+>")
_SUPER_CALL_PREFIX_RE = re.compile(r"^(?:super|base)\s*\([^)]*\)\.")


class DialectAdapter:
    """
    Base language dialect adapter.
    Encapsulates docstring cleaning, visibility resolution, out-of-line scope deduction,
    call receiver normalization, import extraction, and partial aggregation capability.
    """

    language: str = "generic"
    scope_separator: str = "."
    supports_partial_aggregation: bool = False

    def clean_docstring(self, raw_comment: str) -> str:
        """Strip comment delimiters and XML tags from a raw comment or docstring."""
        if not raw_comment:
            return ""
        text = raw_comment.strip()
        lines = text.splitlines()
        cleaned_lines: List[str] = []
        for line in lines:
            l = line.strip()
            if l.startswith("///"):
                l = l[3:].strip()
            elif l.startswith("//"):
                l = l[2:].strip()
            elif l.startswith("/*"):
                l = l[2:].strip()
            elif l.startswith("#"):
                l = l.lstrip("#").strip()
            if l.endswith("*/"):
                l = l[:-2].strip()
            if l.startswith("*"):
                l = l[1:].strip()
            l = _XML_TAG_RE.sub("", l).strip()
            if l:
                cleaned_lines.append(l)
        return "\n".join(cleaned_lines).strip()

    def extract_modifiers(self, def_node: Any) -> List[str]:
        """Extract declaration modifiers (e.g., public, private, protected, internal, partial, static) from an AST node."""
        mods: List[str] = []
        if def_node is None:
            return mods
        try:
            for child in def_node.children:
                if child.type in ("modifier", "accessibility_modifier", "storage_class_specifier", "type_qualifier"):
                    txt = child.text.decode("utf-8", errors="replace").strip().lower()
                    for tok in txt.split():
                        if tok and tok not in mods:
                            mods.append(tok)
                elif child.type in (
                    "public",
                    "private",
                    "protected",
                    "internal",
                    "partial",
                    "static",
                    "abstract",
                    "virtual",
                    "override",
                    "readonly",
                    "async",
                ):
                    tok = child.type.lower()
                    if tok not in mods:
                        mods.append(tok)
            if getattr(def_node, "parent", None) is not None and def_node.parent.type == "decorated_definition":
                for child in def_node.parent.children:
                    if child.type == "decorator":
                        dec_txt = child.text.decode("utf-8", errors="replace").strip()
                        if dec_txt.startswith("@staticmethod") or dec_txt.startswith("@classmethod"):
                            if "static" not in mods:
                                mods.append("static")
        except Exception:
            pass
        return mods

    def is_static_symbol(self, def_node: Any = None, signature: str = "", lines: Optional[List[str]] = None, start_line: int = 0) -> bool:
        """Determine whether a symbol or member is static (`static`, `@staticmethod`, `@classmethod`)."""
        mods = self.extract_modifiers(def_node)
        if "static" in mods:
            return True
        if signature and _STATIC_SIG_RE.search(signature):
            return True
        if lines and start_line > 1:
            idx = start_line - 2
            while idx >= 0 and idx >= start_line - 5:
                prev_ln = lines[idx].strip()
                if prev_ln.startswith("@staticmethod") or prev_ln.startswith("@classmethod"):
                    return True
                if not prev_ln.startswith("@") and prev_ln:
                    break
                idx -= 1
        return False

    def extract_visibility(
        self,
        node: Any,
        source_bytes: bytes = b"",
        parent_kind: Optional[str] = None,
        default_vis: str = "public",
        short_name: str = "",
        kind: str = "",
    ) -> str:
        """Resolve symbol or member visibility according to language rules."""
        return default_vis

    def resolve_out_of_line_scope(
        self,
        name: str,
        parent_scope: str,
        kind: str = "",
    ) -> Tuple[str, str, str]:
        """
        Resolve out-of-line method definitions (e.g. C++ `ClassName::method`).
        Returns `(short_name, parent_scope, effective_kind)`.
        """
        return name, parent_scope, kind

    def format_signature(
        self,
        first_line: str,
        captured_signature: str,
        name: str = "",
        def_kind: str = "",
    ) -> str:
        """Select or format the canonical symbol signature."""
        if captured_signature:
            return captured_signature
        return first_line

    def normalize_call_receiver(self, raw_prefix: str) -> str:
        """Normalize member call receiver expression into canonical prefix (`self`, `base`, or qualified path)."""
        if not raw_prefix:
            return ""
        prefix = raw_prefix.strip()
        for op in ("?.", "->", "::", "."):
            if prefix.endswith(op):
                prefix = prefix[: -len(op)].strip()
                break
        prefix = prefix.replace("?.", ".").replace("->", ".").replace("::", ".")
        if prefix.startswith("(") and prefix.endswith(")"):
            prefix = prefix[1:-1].strip()
        if prefix.endswith(")"):
            gen_m = _GENERIC_CALL_RECEIVER_RE.search(prefix)
            if gen_m:
                prefix = gen_m.group(1).strip()
            else:
                prefix = _TRAILING_CALL_PARENS_RE.sub("", prefix).strip()
        prefix = _SUPER_CALL_PREFIX_RE.sub("super.", prefix)
        prefix = _GENERIC_ARGS_RE.sub("", prefix).strip()

        if prefix == "this":
            return "self"
        if prefix in ("base", "super", "__super"):
            return "base"
        if prefix.startswith(("this.", "base.", "super.", "__super.")):
            return "self." + prefix.split(".", 1)[1]
        return prefix

    def extract_imports(self, source_text: str, file_path: str = "") -> Dict[str, str]:
        """Extract file-level import/include/using alias mappings `{alias_or_short: target_module_or_fqn}`."""
        return {}

    def post_process_raw_item(self, item: Dict[str, Any], def_node: Any) -> None:
        """Hook for dialect-specific adjustments on a raw definition item in Stage 1."""

    def finalize_raw_items(self, raw_items: List[Dict[str, Any]], lines: List[str]) -> List[Dict[str, Any]]:
        """Hook for dialect-specific post-processing across all raw items of a file."""
        return raw_items

    def fallback_symbols(self, normalized_path: str, lines: List[str], space: str) -> List[Any]:
        """Optional fallback symbol generation when no AST definitions match."""
        return []

    def extract_custom_call_sites(
        self,
        normalized_path: str,
        content: str,
        space: str,
    ) -> Optional[List[Any]]:
        """Optional custom call site extraction (returns None to use standard Tree-sitter call query)."""
        return None
