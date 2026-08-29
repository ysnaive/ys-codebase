"""
knowledge-db Python 語意解析器 (基於 Python 原生 ast 模組)
"""

import ast
import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Set, Union

from ..schema import LanguageType, MemberInfo, SymbolKind, UnifiedSymbol
from .base import BaseParser

logger = logging.getLogger("knowledge-db.parsers.python")


def _get_arg_str(arg: ast.arg) -> str:
    """轉換 ast.arg 為字串表示 (含型別標註)"""
    res = arg.arg
    if arg.annotation is not None:
        try:
            res += f": {ast.unparse(arg.annotation)}"
        except Exception:
            pass
    return res


def _build_func_signature(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
    """構建函式/方法之簽名字串"""
    args = node.args
    arg_strs = []

    # posonlyargs
    for a in getattr(args, "posonlyargs", []):
        arg_strs.append(_get_arg_str(a))
    if getattr(args, "posonlyargs", []):
        arg_strs.append("/")

    # regular args
    # defaults are right-aligned to args
    num_defaults = len(args.defaults)
    num_args = len(args.args)
    for i, a in enumerate(args.args):
        a_str = _get_arg_str(a)
        default_idx = i - (num_args - num_defaults)
        if default_idx >= 0:
            try:
                def_val = ast.unparse(args.defaults[default_idx])
                a_str += f" = {def_val}"
            except Exception:
                pass
        arg_strs.append(a_str)

    # vararg (*args)
    if args.vararg is not None:
        arg_strs.append(f"*{_get_arg_str(args.vararg)}")

    # kwonlyargs
    for i, a in enumerate(args.kwonlyargs):
        a_str = _get_arg_str(a)
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            try:
                def_val = ast.unparse(args.kw_defaults[i])
                a_str += f" = {def_val}"
            except Exception:
                pass
        arg_strs.append(a_str)

    # kwarg (**kwargs)
    if args.kwarg is not None:
        arg_strs.append(f"**{_get_arg_str(args.kwarg)}")

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    ret_str = ""
    if node.returns is not None:
        try:
            ret_str = f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    return f"{prefix} {node.name}({', '.join(arg_strs)}){ret_str}"


class PythonParser(BaseParser):
    """Python 原始碼語法樹 (AST) 符號解析器"""

    SUPPORTED_EXTENSIONS: Set[str] = {".py", ".pyi"}

    def can_parse(self, file_path: Union[str, Path]) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        normalized_path = file_path.replace("\\", "/")
        try:
            tree = ast.parse(content, filename=normalized_path)
        except SyntaxError as e:
            logger.warning(f"PythonParser: SyntaxError in '{normalized_path}': {e} (EC-01: Skipping gracefully)")
            return []
        except Exception as e:
            logger.warning(f"PythonParser: Error parsing '{normalized_path}': {e}")
            return []

        symbols: List[UnifiedSymbol] = []

        for node in tree.body:
            # 1. 類別定義
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                docstring = ast.get_docstring(node) or ""
                bases = []
                for b in node.bases:
                    try:
                        bases.append(ast.unparse(b))
                    except Exception:
                        pass
                sig = f"class {class_name}({', '.join(bases)})" if bases else f"class {class_name}"

                members: List[MemberInfo] = []
                decorators = []
                for dec in node.decorator_list:
                    try:
                        decorators.append(ast.unparse(dec))
                    except Exception:
                        pass

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_doc = ast.get_docstring(item) or ""
                        m_sig = _build_func_signature(item)
                        m_name = item.name
                        if m_name.startswith("__") and not m_name.endswith("__"):
                            vis = "private"
                        elif m_name.startswith("_"):
                            vis = "protected"
                        else:
                            vis = "public"

                        members.append(
                            MemberInfo(
                                name=m_name,
                                kind="method",
                                signature=m_sig,
                                docstring=m_doc,
                                visibility=vis,
                                line_number=item.lineno,
                            )
                        )
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        # 類別欄位型別標註
                        f_name = item.target.id
                        try:
                            f_sig = f"{f_name}: {ast.unparse(item.annotation)}"
                        except Exception:
                            f_sig = f_name
                        vis = "protected" if f_name.startswith("_") else "public"
                        members.append(
                            MemberInfo(
                                name=f_name,
                                kind="field",
                                signature=f_sig,
                                docstring="",
                                visibility=vis,
                                line_number=item.lineno,
                            )
                        )

                class_end_line = getattr(node, "end_lineno", node.lineno)
                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=class_name,
                    kind=SymbolKind.CLASS.value,
                    line_number=node.lineno,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=class_name,
                        kind=SymbolKind.CLASS.value,
                        file_path=normalized_path,
                        line_number=node.lineno,
                        end_line=class_end_line,
                        language=LanguageType.PYTHON.value,
                        docstring=docstring,
                        signature=sig,
                        members=members,
                        metadata={
                            "end_line": class_end_line,
                            "decorators": decorators,
                            "bases": bases,
                        },
                    )
                )

                # 將類別內部之 Methods 亦物化為獨立一級 UnifiedSymbol (FR-01)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_doc = ast.get_docstring(item) or ""
                        m_sig = _build_func_signature(item)
                        m_name = item.name
                        m_end_line = getattr(item, "end_lineno", item.lineno)
                        m_dec = []
                        for d in item.decorator_list:
                            try:
                                m_dec.append(ast.unparse(d))
                            except Exception:
                                pass

                        method_sym_id = UnifiedSymbol.compute_id(
                            space=space,
                            file_path=normalized_path,
                            name=f"{class_name}.{m_name}",
                            kind=SymbolKind.METHOD.value,
                            line_number=item.lineno,
                        )
                        symbols.append(
                            UnifiedSymbol(
                                id=method_sym_id,
                                name=f"{class_name}.{m_name}",
                                kind=SymbolKind.METHOD.value,
                                file_path=normalized_path,
                                line_number=item.lineno,
                                end_line=m_end_line,
                                language=LanguageType.PYTHON.value,
                                docstring=m_doc,
                                signature=m_sig,
                                members=[],
                                metadata={
                                    "parent_scope": class_name,
                                    "method_name": m_name,
                                    "end_line": m_end_line,
                                    "decorators": m_dec,
                                    "is_async": isinstance(item, ast.AsyncFunctionDef),
                                },
                            )
                        )

            # 2. 頂層函式定義
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = node.name
                docstring = ast.get_docstring(node) or ""
                sig = _build_func_signature(node)
                func_end_line = getattr(node, "end_lineno", node.lineno)
                decorators = []
                for dec in node.decorator_list:
                    try:
                        decorators.append(ast.unparse(dec))
                    except Exception:
                        pass

                sym_id = UnifiedSymbol.compute_id(
                    space=space,
                    file_path=normalized_path,
                    name=func_name,
                    kind=SymbolKind.FUNCTION.value,
                    line_number=node.lineno,
                )
                symbols.append(
                    UnifiedSymbol(
                        id=sym_id,
                        name=func_name,
                        kind=SymbolKind.FUNCTION.value,
                        file_path=normalized_path,
                        line_number=node.lineno,
                        end_line=func_end_line,
                        language=LanguageType.PYTHON.value,
                        docstring=docstring,
                        signature=sig,
                        members=[],
                        metadata={
                            "end_line": func_end_line,
                            "decorators": decorators,
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                        },
                    )
                )

        return symbols
