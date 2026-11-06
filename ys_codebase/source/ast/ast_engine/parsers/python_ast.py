"""
Standard library `ast` fallback & standalone parser for Python (`PythonASTParser`).
Provides zero-external-dependency Python AST parsing when Tree-sitter is unavailable or explicitly bypassed.
"""

import _ast
import importlib.machinery
import importlib.util
from pathlib import Path
import re
import sys
import sysconfig
from typing import Any, Dict, List, Optional, Set, Union


def _load_stdlib_ast() -> Any:
    """Load the Python standard library `ast` module safely even if `module:ast` is in `sys.modules['ast']`."""
    existing = sys.modules.get("ast")
    if existing is not None and hasattr(existing, "FunctionDef") and hasattr(existing, "parse"):
        return existing
    stdlib_dir = sysconfig.get_path("stdlib")
    if stdlib_dir:
        ast_py = Path(stdlib_dir) / "ast.py"
        if ast_py.is_file():
            loader = importlib.machinery.SourceFileLoader("_stdlib_ast", str(ast_py))
            spec = importlib.util.spec_from_loader("_stdlib_ast", loader)
            if spec is not None:
                mod = importlib.util.module_from_spec(spec)
                loader.exec_module(mod)
                return mod
    import ast as fallback_ast

    return fallback_ast


py_ast = _load_stdlib_ast()


from ..dialects.python import PythonDialect
from ..schema import LanguageType, MemberInfo, SymbolCallSite, SymbolKind, UnifiedSymbol
from .base import BaseParser


class PythonASTParser(BaseParser):
    """Python AST parser powered by Python standard library `ast` module."""

    SUPPORTED_EXTENSIONS: Set[str] = {".py", ".pyi"}

    def __init__(self) -> None:
        self._dialect = PythonDialect()

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    @staticmethod
    def _format_func_signature(node: Union[py_ast.FunctionDef, py_ast.AsyncFunctionDef], lines: List[str]) -> str:
        start_idx = max(0, getattr(node, "lineno", 1) - 1)
        if start_idx < len(lines):
            body_nodes = getattr(node, "body", None) or []
            body_start_ln = getattr(body_nodes[0], "lineno", len(lines) + 1) if body_nodes else len(lines) + 1
            max_idx = min(len(lines), max(start_idx + 1, body_start_ln))
            header_parts: List[str] = []
            paren_depth = 0
            found_open = False
            for idx in range(start_idx, max_idx):
                code_part = lines[idx].split("#", 1)[0].strip()
                if not code_part:
                    continue
                header_parts.append(code_part)
                for ch in code_part:
                    if ch in "([{":
                        paren_depth += 1
                        if ch == "(":
                            found_open = True
                    elif ch in ")]}":
                        paren_depth = max(0, paren_depth - 1)
                if found_open and paren_depth == 0 and code_part.endswith(":"):
                    break
            joined = " ".join(header_parts).strip()
            if joined.endswith(":"):
                joined = joined[:-1].strip()
            joined = re.sub(r"\(\s+", "(", re.sub(r",?\s+\)", ")", joined))
            if "def " in joined and "(" in joined and ")" in joined:
                return joined
            first_line = lines[start_idx].strip()
            if first_line.endswith(":"):
                first_line = first_line[:-1].strip()
            if "def " in first_line and "(" in first_line and ")" in first_line:
                return first_line
        prefix = "async def" if isinstance(node, py_ast.AsyncFunctionDef) else "def"
        args_list = [a.arg for a in node.args.args]
        return f"{prefix} {node.name}({', '.join(args_list)})"

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []

        try:
            tree = py_ast.parse(content, filename=normalized_path)
        except SyntaxError:
            return []
        except Exception:
            return []

        lines = content.splitlines()
        symbols: List[UnifiedSymbol] = []

        def _visit_block(
            body_nodes: List[py_ast.stmt],
            scope_path: List[str],
            parent_id: Optional[str],
            parent_kind: Optional[str],
        ) -> None:
            for node in body_nodes:
                if isinstance(node, py_ast.ClassDef):
                    cls_name = node.name
                    fqn_parts = scope_path + [cls_name]
                    fqn = ".".join(fqn_parts)
                    start_ln = getattr(node, "lineno", 1)
                    end_ln = getattr(node, "end_lineno", start_ln) or start_ln
                    doc = (py_ast.get_docstring(node) or "").strip()
                    first_line = lines[start_ln - 1].strip().rstrip(":") if start_ln <= len(lines) else f"class {cls_name}"
                    cls_id = UnifiedSymbol.compute_id(
                        space=space,
                        file_path=normalized_path,
                        name=fqn,
                        kind=SymbolKind.CLASS.value,
                        line_number=start_ln,
                    )
                    base_types: List[str] = []
                    for b in node.bases:
                        if isinstance(b, py_ast.Name):
                            base_types.append(b.id)
                        elif isinstance(b, py_ast.Attribute):
                            base_types.append(b.attr)

                    members_list: List[MemberInfo] = []
                    field_types: Dict[str, str] = {}
                    for item in node.body:
                        if isinstance(item, (py_ast.FunctionDef, py_ast.AsyncFunctionDef)):
                            m_sig = self._format_func_signature(item, lines)
                            m_doc = (py_ast.get_docstring(item) or "").strip()
                            m_vis = self._dialect.extract_visibility(None, short_name=item.name, kind="method")
                            m_static = any(
                                (isinstance(d, py_ast.Name) and d.id in ("staticmethod", "classmethod"))
                                or (isinstance(d, py_ast.Attribute) and d.attr in ("staticmethod", "classmethod"))
                                for d in getattr(item, "decorator_list", [])
                            )
                            members_list.append(
                                MemberInfo(
                                    name=item.name,
                                    kind=SymbolKind.METHOD.value,
                                    signature=m_sig,
                                    docstring=m_doc,
                                    visibility=m_vis,
                                    line_number=getattr(item, "lineno", start_ln),
                                    is_static=m_static,
                                )
                            )
                        elif isinstance(item, py_ast.AnnAssign) and isinstance(item.target, py_ast.Name):
                            f_name = item.target.id
                            f_ln = getattr(item, "lineno", start_ln)
                            f_sig = lines[f_ln - 1].strip() if f_ln <= len(lines) else f_name
                            f_vis = self._dialect.extract_visibility(None, short_name=f_name, kind="field")
                            if isinstance(item.annotation, py_ast.Name):
                                field_types[f_name] = item.annotation.id
                            members_list.append(
                                MemberInfo(
                                    name=f_name,
                                    kind="field",
                                    signature=f_sig,
                                    docstring="",
                                    visibility=f_vis,
                                    line_number=f_ln,
                                )
                            )
                        elif isinstance(item, py_ast.Assign):
                            for tgt in item.targets:
                                if isinstance(tgt, py_ast.Name):
                                    f_name = tgt.id
                                    f_ln = getattr(item, "lineno", start_ln)
                                    f_sig = lines[f_ln - 1].strip() if f_ln <= len(lines) else f_name
                                    f_vis = self._dialect.extract_visibility(None, short_name=f_name, kind="field")
                                    members_list.append(
                                        MemberInfo(
                                            name=f_name,
                                            kind="field",
                                            signature=f_sig,
                                            docstring="",
                                            visibility=f_vis,
                                            line_number=f_ln,
                                        )
                                    )

                    cls_vis = self._dialect.extract_visibility(None, short_name=cls_name, kind="class")
                    meta: Dict[str, Any] = {
                        "short_name": cls_name,
                        "parent_scope": scope_path[-1] if scope_path else "",
                        "end_line": end_ln,
                        "scope_path": list(scope_path),
                    }
                    if base_types:
                        meta["base_types"] = base_types
                    if field_types:
                        meta["field_types"] = field_types

                    sym_name = fqn if parent_id else cls_name
                    symbols.append(
                        UnifiedSymbol(
                            id=cls_id,
                            name=sym_name,
                            kind=SymbolKind.CLASS.value,
                            file_path=normalized_path,
                            line_number=start_ln,
                            end_line=end_ln,
                            language=LanguageType.PYTHON.value,
                            docstring=doc,
                            signature=first_line,
                            fqn=fqn,
                            scope_path=".".join(scope_path),
                            parent_id=parent_id,
                            children=tuple(members_list),
                            members=tuple(members_list),
                            search_payload=f"{fqn} {cls_name} {doc} {first_line}".strip(),
                            visibility=cls_vis,
                            metadata=meta,
                        )
                    )
                    _visit_block(node.body, fqn_parts, cls_id, SymbolKind.CLASS.value)

                elif isinstance(node, (py_ast.FunctionDef, py_ast.AsyncFunctionDef)):
                    fn_name = node.name
                    fqn_parts = scope_path + [fn_name]
                    fqn = ".".join(fqn_parts)
                    start_ln = getattr(node, "lineno", 1)
                    end_ln = getattr(node, "end_lineno", start_ln) or start_ln
                    doc = (py_ast.get_docstring(node) or "").strip()
                    sig = self._format_func_signature(node, lines)
                    kind_val = (
                        SymbolKind.METHOD.value
                        if parent_kind == SymbolKind.CLASS.value
                        else SymbolKind.FUNCTION.value
                    )
                    fn_id = UnifiedSymbol.compute_id(
                        space=space,
                        file_path=normalized_path,
                        name=fqn,
                        kind=kind_val,
                        line_number=start_ln,
                    )
                    fn_vis = self._dialect.extract_visibility(None, short_name=fn_name, kind=kind_val)
                    fn_static = any(
                        (isinstance(d, py_ast.Name) and d.id in ("staticmethod", "classmethod"))
                        or (isinstance(d, py_ast.Attribute) and d.attr in ("staticmethod", "classmethod"))
                        for d in getattr(node, "decorator_list", [])
                    )
                    fn_meta: Dict[str, Any] = {
                        "short_name": fn_name,
                        "parent_scope": scope_path[-1] if scope_path else "",
                        "end_line": end_ln,
                        "scope_path": list(scope_path),
                    }
                    if fn_static:
                        fn_meta["is_static"] = True
                    sym_name = fqn if parent_id else fn_name
                    symbols.append(
                        UnifiedSymbol(
                            id=fn_id,
                            name=sym_name,
                            kind=kind_val,
                            file_path=normalized_path,
                            line_number=start_ln,
                            end_line=end_ln,
                            language=LanguageType.PYTHON.value,
                            docstring=doc,
                            signature=sig,
                            fqn=fqn,
                            scope_path=".".join(scope_path),
                            parent_id=parent_id,
                            children=(),
                            members=(),
                            search_payload=f"{fqn} {fn_name} {doc} {sig}".strip(),
                            visibility=fn_vis,
                            metadata=fn_meta,
                        )
                    )

        _visit_block(tree.body, [], None, None)
        return symbols

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []
        try:
            tree = py_ast.parse(content, filename=normalized_path)
        except Exception:
            return []

        target_symbols = (
            symbols if symbols is not None else self.parse(file_path=file_path, content=content, space=space)
        )
        sorted_target_symbols = sorted(target_symbols, key=lambda s: (s.end_line - s.line_number))
        sites: List[SymbolCallSite] = []

        for node in py_ast.walk(tree):
            if not isinstance(node, py_ast.Call):
                continue
            line_no = getattr(node, "lineno", 1)
            callee_name = ""
            prefix = ""
            if isinstance(node.func, py_ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, py_ast.Attribute):
                callee_name = node.func.attr
                if isinstance(node.func.value, py_ast.Name):
                    prefix = "base" if node.func.value.id == "super" else node.func.value.id
                elif (
                    isinstance(node.func.value, py_ast.Call)
                    and isinstance(node.func.value.func, py_ast.Name)
                    and node.func.value.func.id == "super"
                ):
                    prefix = "base"
                elif isinstance(node.func.value, py_ast.Attribute) and isinstance(node.func.value.value, py_ast.Name):
                    prefix = f"{node.func.value.value.id}.{node.func.value.attr}"
            if not callee_name:
                continue

            caller_name = "<module>"
            caller_sym_id = ""
            enclosing = next(
                (
                    s
                    for s in sorted_target_symbols
                    if s.line_number <= line_no <= s.end_line and s.kind in ("method", "function", "class")
                ),
                None,
            )
            if enclosing is not None:
                caller_sym_id = enclosing.id
                caller_name = enclosing.name

            sites.append(
                SymbolCallSite(
                    callee_name=callee_name,
                    line_number=line_no,
                    caller_symbol_id=caller_sym_id,
                    caller_member_name=caller_name,
                    context_prefix=prefix,
                    file_path=normalized_path,
                    space=space,
                )
            )
        return sites

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        return self._dialect.extract_imports(content, file_path=file_path)
