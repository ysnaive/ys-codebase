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
from typing import Any, Dict, List, Optional, Tuple, Union


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

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyi"})

    def __init__(self) -> None:
        self._dialect = PythonDialect()
        self._last_ast_cache: Optional[Tuple[str, int, int, str, Any, List[str]]] = None

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def _get_tree_and_lines(self, normalized_path: str, content: str) -> Optional[Tuple[Any, List[str]]]:
        cached = self._last_ast_cache
        if (
            cached is not None
            and cached[0] == normalized_path
            and cached[1] == len(content)
            and (cached[2] == id(content) or cached[3] == content)
        ):
            return cached[4], cached[5]
        try:
            tree = py_ast.parse(content, filename=normalized_path)
        except Exception:
            return None
        lines = content.splitlines()
        self._last_ast_cache = (normalized_path, len(content), id(content), content, tree, lines)
        return tree, lines

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

    @staticmethod
    def _unroll_expr_str(expr: Any) -> str:
        if isinstance(expr, py_ast.Name):
            return expr.id
        if isinstance(expr, py_ast.Attribute):
            left = PythonASTParser._unroll_expr_str(expr.value)
            return f"{left}.{expr.attr}" if left else expr.attr
        return ""

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        if not content or not content.strip():
            return []

        parsed = self._get_tree_and_lines(normalized_path, content)
        if parsed is None:
            return []
        tree, lines = parsed
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
                        b_str = self._unroll_expr_str(b)
                        if b_str:
                            base_types.append(b_str)

                    members_list: List[MemberInfo] = []
                    seen_member_keys = set()
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
                            m_ln = getattr(item, "lineno", start_ln)
                            seen_member_keys.add(("method", item.name, m_ln))
                            members_list.append(
                                MemberInfo(
                                    name=item.name,
                                    kind=SymbolKind.METHOD.value,
                                    signature=m_sig,
                                    docstring=m_doc,
                                    visibility=m_vis,
                                    line_number=m_ln,
                                    is_static=m_static,
                                )
                            )
                            # Also extract self.<field> assignments inside methods
                            for sub in py_ast.walk(item):
                                if isinstance(sub, py_ast.AnnAssign) and isinstance(sub.target, py_ast.Attribute):
                                    if isinstance(sub.target.value, py_ast.Name) and sub.target.value.id == "self":
                                        f_name = sub.target.attr
                                        f_ln = getattr(sub, "lineno", m_ln)
                                        ann_str = self._unroll_expr_str(sub.annotation)
                                        if ann_str:
                                            field_types[f_name] = ann_str.split(".")[-1]
                                        if ("field", f_name) not in seen_member_keys:
                                            seen_member_keys.add(("field", f_name))
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
                                elif isinstance(sub, py_ast.Assign):
                                    for tgt in sub.targets:
                                        if (
                                            isinstance(tgt, py_ast.Attribute)
                                            and isinstance(tgt.value, py_ast.Name)
                                            and tgt.value.id == "self"
                                        ):
                                            f_name = tgt.attr
                                            f_ln = getattr(sub, "lineno", m_ln)
                                            if ("field", f_name) not in seen_member_keys:
                                                seen_member_keys.add(("field", f_name))
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
                        elif isinstance(item, py_ast.AnnAssign) and isinstance(item.target, py_ast.Name):
                            f_name = item.target.id
                            f_ln = getattr(item, "lineno", start_ln)
                            f_sig = lines[f_ln - 1].strip() if f_ln <= len(lines) else f_name
                            f_vis = self._dialect.extract_visibility(None, short_name=f_name, kind="field")
                            ann_str = self._unroll_expr_str(item.annotation)
                            if ann_str:
                                field_types[f_name] = ann_str.split(".")[-1]
                            if ("field", f_name) not in seen_member_keys:
                                seen_member_keys.add(("field", f_name))
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
                                    if ("field", f_name) not in seen_member_keys:
                                        seen_member_keys.add(("field", f_name))
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
                    ret_type_str = ""
                    if getattr(node, "returns", None) is not None:
                        try:
                            ret_type_str = py_ast.unparse(node.returns).strip()
                        except Exception:
                            ret_type_str = self._unroll_expr_str(node.returns)
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
                            return_type=ret_type_str,
                            search_payload=f"{fqn} {fn_name} {doc} {sig}".strip(),
                            visibility=fn_vis,
                            metadata=fn_meta,
                        )
                    )
                    _visit_block(node.body, fqn_parts, fn_id, kind_val)

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
        parsed = self._get_tree_and_lines(normalized_path, content)
        if parsed is None:
            return []
        tree, _ = parsed

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
                attr_parts: List[str] = []
                curr_val: Any = node.func.value
                while isinstance(curr_val, py_ast.Attribute):
                    attr_parts.insert(0, curr_val.attr)
                    curr_val = curr_val.value
                if isinstance(curr_val, py_ast.Name):
                    root_id = "base" if curr_val.id == "super" else ("self" if curr_val.id == "this" else curr_val.id)
                    attr_parts.insert(0, root_id)
                elif (
                    isinstance(curr_val, py_ast.Call)
                    and isinstance(curr_val.func, py_ast.Name)
                    and curr_val.func.id == "super"
                ):
                    if attr_parts:
                        attr_parts.insert(0, "self")
                    else:
                        attr_parts.insert(0, "base")
                prefix = ".".join(attr_parts)
            if not callee_name:
                continue

            caller_name = "<module>"
            caller_sym_id = ""
            enclosing = next(
                (
                    s
                    for s in sorted_target_symbols
                    if s.line_number <= line_no <= s.end_line
                    and s.kind in ("method", "function", "constructor", "class")
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
