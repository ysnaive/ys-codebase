"""Gate 0 strict allowlist DAG, symtable, type-hint, Living-Spec parity, and multi-file self-audit."""

from __future__ import annotations

import ast
import builtins
import dataclasses
from dataclasses import dataclass, field
from enum import Enum, Flag
import inspect
import io
import os
from pathlib import Path
import pkgutil
import re
import subprocess
import symtable
import sys
import threading
import tokenize
import types
import typing
from typing import Final, Mapping, Optional, Sequence

import core
import core.execution.daemon as daemon_pkg
import core.execution.event as event_pkg
import core.execution.lifecycle as lifecycle_pkg
import core.execution.rpc as rpc_pkg
import core.execution.runtime as runtime_pkg
import core.filesystem.fs as fs_pkg
import core.filesystem.space as space_pkg
import core.filesystem.storage as storage_pkg
import core.filesystem.vfs as vfs_pkg
import core.foundation as foundation_pkg
import core.metadata.config as config_pkg
import core.metadata.contributes as contributes_pkg
import core.packaging.env as env_pkg
import core.packaging.installer as installer_pkg
import core.surface.bootstrap as bootstrap_pkg
import core.surface.cli as cli_pkg
import core.surface.sdk as sdk_pkg
from tests import CORE_SRC_ROOT, CORE_V2_ROOT, TESTS_ROOT
from tests._harness import EMBEDDED_MODULE_TEMPLATES, check

_IMMUTABLE_GLOBAL_CALLS: Final[frozenset[str]] = frozenset(
    {
        "frozenset",
        "tuple",
        "TypeVar",
        "NewType",
        "compile",
        "ModuleId",
        "TaskId",
        "EventId",
        "min",
        "max",
        "float",
        "int",
        "str",
        "bool",
        "bytes",
        "MappingProxyType",
        "WinDLL",
        "CDLL",
        "CFUNCTYPE",
        "WINFUNCTYPE",
        "POINTER",
        "Struct",
        "_resolve_msg_dontwait",
    }
)


def _is_mutable_global_expr(expr: Optional[ast.expr]) -> bool:
    if isinstance(expr, (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp, ast.SetComp)):
        return True
    if isinstance(expr, ast.Call):
        fn = expr.func
        callee = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
        return callee not in _IMMUTABLE_GLOBAL_CALLS
    return False


def _collect_descendant_free_names(table: symtable.SymbolTable) -> set[str]:
    names: set[str] = set()
    for ch in table.get_children():
        for s in ch.get_symbols():
            if s.is_free() or s.is_referenced():
                names.add(s.get_name())
        names.update(_collect_descendant_free_names(ch))
    return names


def _collect_comprehension_loads_by_lineno(src: str) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        loads: set[str] = set()
        stack: list[ast.AST] = list(node.body)
        while stack:
            cur = stack.pop()
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(cur, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for sub in ast.walk(cur):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        loads.add(sub.id)
                continue
            stack.extend(ast.iter_child_nodes(cur))
        if loads:
            out.setdefault(node.lineno, set()).update(loads)
    return out


def _verify_symtable_clean(src: str, rel_name: str) -> None:
    builtin_names = {k for k, _ in inspect.getmembers_static(builtins)} | {
        "__annotations__",
        "__file__",
        "__name__",
        "__package__",
        "__doc__",
        "__spec__",
        "__path__",
        "__cached__",
        "__builtins__",
        "__class__",
    }
    st = symtable.symtable(src, rel_name, "exec")
    comp_loads = _collect_comprehension_loads_by_lineno(src)

    def _walk(table: symtable.SymbolTable, enclosing: set[str]) -> None:
        defined = {
            s.get_name()
            for s in table.get_symbols()
            if s.is_assigned() or s.is_imported() or s.is_parameter() or s.is_namespace()
        }
        visible = enclosing | defined
        child_enc = enclosing if table.get_type() == "class" else visible
        desc_used = (
            (_collect_descendant_free_names(table) | comp_loads.get(table.get_lineno(), set()))
            if table.get_type() == "function"
            else set()
        )
        for sym in table.get_symbols():
            name = sym.get_name()
            if sym.is_referenced() and not (
                sym.is_assigned() or sym.is_imported() or sym.is_parameter() or sym.is_namespace()
            ):
                check(name in visible or name in builtin_names, lambda: f"Undefined symbol '{name}' in {rel_name}")
            if (
                table.get_type() == "function"
                and sym.is_local()
                and sym.is_assigned()
                and not (sym.is_parameter() or sym.is_imported() or sym.is_namespace() or sym.is_referenced())
                and not name.startswith("_")
            ):
                check(name in desc_used, lambda: f"Unused local variable '{name}' in {rel_name}:{table.get_name()}")
        for child in table.get_children():
            _walk(child, child_enc)

    _walk(st, set())


def _resolve_except_expr_obj(
    expr: ast.expr,
    ns: Mapping[str, object],
    bi_ns: Mapping[str, object],
) -> object:
    if isinstance(expr, ast.Name):
        return ns.get(expr.id, bi_ns.get(expr.id))
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        base = ns.get(expr.value.id, bi_ns.get(expr.value.id))
        if isinstance(base, types.ModuleType):
            return dict(inspect.getmembers(base)).get(expr.attr)
    return None


def _assert_valid_except_handlers(tree: ast.AST, mod_name: str, label: str) -> None:
    canon_mod = mod_name[:-9] if mod_name.endswith(".__init__") else mod_name
    mod_obj = sys.modules[canon_mod]
    ns = dict(inspect.getmembers(mod_obj))
    bi_ns = dict(inspect.getmembers(builtins))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        items = list(node.type.elts) if isinstance(node.type, ast.Tuple) else [node.type]
        for item in items:
            resolved = _resolve_except_expr_obj(item, ns, bi_ns)
            check(
                isinstance(resolved, type) and issubclass(resolved, BaseException),
                lambda: f"Non-BaseException in except handler at {label}:{node.lineno}: {ast.unparse(item)}",
            )


def _assert_no_unused_private_module_symbols(tree: ast.Module, label: str) -> None:
    defs: dict[str, int] = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and stmt.name.startswith("_") and not stmt.name.startswith("__"):
            defs[stmt.name] = stmt.lineno
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id.startswith("_") and not t.id.startswith("__"):
                    defs[t.id] = stmt.lineno
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id.startswith("_") and not stmt.target.id.startswith("__"):
            defs[stmt.target.id] = stmt.lineno
        elif isinstance(stmt, ast.If):
            for sub in stmt.body + stmt.orelse:
                if isinstance(sub, (ast.FunctionDef, ast.ClassDef)) and sub.name.startswith("_"):
                    defs[sub.name] = sub.lineno
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name) and t.id.startswith("_"):
                            defs[t.id] = sub.lineno
                elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and sub.target.id.startswith("_"):
                    defs[sub.target.id] = sub.lineno
    loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    attr_loads = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)} | loads
    for nm, ln in defs.items():
        check(nm in loads, lambda: f"Unused private module symbol '{nm}' in {label}:{ln}")
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            for ch in stmt.body:
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) and ch.name.startswith("_") and not ch.name.startswith("__"):
                    check(ch.name in attr_loads, lambda: f"Unused private class method '{stmt.name}.{ch.name}' in {label}:{ch.lineno}")


def _audit_single_kernel_ast(
    py_f: Path,
    rel_posix: str,
    rel_mod: str,
    forbidden_by_prefix: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    noise_re = re.compile(
        r"\b(?:FR-\d+|EC-\d+|DR-\d+|P[0-3](?:-\d+)?|D[1-5]|S[1-6]|RC-\d+|N-\d+|"
        r"R[1-9]\d*|AUD-\d+|TASK-\d+|OPT-\d+|TODO|FIXME|HACK|XXX)\b|#\s*Step\s+\d+"
    )
    src = py_f.read_text(encoding="utf-8")
    m_noise = noise_re.search(src)
    check(m_noise is None, lambda: f"Forbidden audit/ticket tag '{m_noise.group(0)}' in {rel_posix}")
    check(("# type" + ": ignore") not in src, lambda: f"Forbidden type-ignore comment in {rel_posix}")
    _verify_symtable_clean(src, rel_posix)
    tree = ast.parse(src, filename=rel_posix)
    _assert_no_unused_top_imports(tree, rel_posix)
    _assert_no_unused_private_module_symbols(tree, rel_posix)
    _assert_no_duplicate_defs(tree, rel_posix)
    _assert_valid_except_handlers(tree, rel_mod, rel_posix)
    _assert_no_stateless_private_methods(tree, rel_posix)
    _assert_no_cross_collaborator_private_calls(tree, rel_posix)

    for stmt in tree.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and _is_mutable_global_expr(stmt.value):
            raise AssertionError(f"Mutable module-level global forbidden in {rel_posix}:{stmt.lineno}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            raise AssertionError(f"Type erasure 'Any' forbidden in {rel_posix}:{node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr in {"Any", "getattr", "setattr", "hasattr", "delattr", "eval", "exec"}:
            raise AssertionError(f"Forbidden attribute '{node.attr}' in {rel_posix}:{node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            check(node.func.id != "print", lambda: f"Bare print() forbidden in {rel_posix}:{node.lineno}")
            check(node.func.id not in {"getattr", "setattr", "hasattr", "delattr", "__import__", "vars", "dir", "eval", "exec"}, lambda: f"Dynamic {node.func.id} forbidden in {rel_posix}:{node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            check(not (isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "getcwd"), lambda: f"os.getcwd() forbidden in {rel_posix}:{node.lineno}")
            check(node.func.attr not in {"abspath", "cwd"}, lambda: f"Implicit cwd call .{node.func.attr}() forbidden in {rel_posix}:{node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr in {"__dict__", "import_module"}:
            _assert_allowed_kernel_reflection(tree, rel_posix, node)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in {"environ", "getenv", "putenv", "unsetenv"}
        ):
            check(
                rel_posix in _ALLOWED_KERNEL_ENVIRON_FILES,
                lambda: f"Unauthorized os.{node.attr} access in kernel {rel_posix}:{node.lineno}",
            )
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for imp_al in node.names:
                check(
                    imp_al.name not in {"environ", "getenv", "putenv", "unsetenv"}
                    or rel_posix in _ALLOWED_KERNEL_ENVIRON_FILES,
                    lambda: f"Unauthorized os.{imp_al.name} import in kernel {rel_posix}:{node.lineno}",
                )
        if isinstance(node, ast.Assert):
            raise AssertionError(f"Bare assert forbidden in kernel {rel_posix}:{node.lineno}")
        if isinstance(node, ast.Lambda) and isinstance(node.body, ast.Tuple) and len(node.body.elts) >= 3:
            raise AssertionError(f"Wide 3+ tuple lambda forbidden in {rel_posix}:{node.lineno}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _assert_no_local_imports(node, rel_posix)
            _assert_no_wide_tuple_params(node, rel_posix)
            _assert_no_unused_function_params(node, rel_posix)
        _check_dag_imports(node, rel_mod, forbidden_by_prefix)


_ALLOWED_KERNEL_ENVIRON_FILES: Final[frozenset[str]] = frozenset(
    {
        "core/foundation/proc.py",
        "core/execution/runtime/worker_entry.py",
        "core/execution/runtime/worker_pool.py",
        "core/surface/cli/caller_mode.py",
        "core/surface/cli/entrypoint.py",
    }
)

_ALLOWED_KERNEL_REFLECTION_FUNCS: Final[dict[str, frozenset[str]]] = {
    "core/foundation/codec.py": frozenset(
        {
            "_populate_module_and_outer_classes",
            "_populate_qualname_and_closure_ns",
            "_populate_single_mro_base",
            "_resolve_single_class_hints",
            "_needs_localns_for_forward_ref",
            "_resolve_forward_ref",
        }
    ),
    "core/execution/runtime/module_slot.py": frozenset(
        {"_make_scoped_builtins", "exec_module", "_ensure_finder", "_deactivate_finder_if_empty_locked", "load_module_artifact"}
    ),
}


def _assert_allowed_kernel_reflection(tree: ast.AST, rel_posix: str, attr_node: ast.Attribute) -> None:
    allowed_fns = _ALLOWED_KERNEL_REFLECTION_FUNCS.get(rel_posix, frozenset())
    check(allowed_fns, lambda: f"Reflection {attr_node.attr} forbidden in {rel_posix}:{attr_node.lineno}")
    if attr_node.attr == "import_module":
        check(rel_posix == "core/execution/runtime/module_slot.py", lambda: f"import_module forbidden in {rel_posix}:{attr_node.lineno}")
    enclosing = [
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and fn.lineno <= attr_node.lineno <= (fn.end_lineno or fn.lineno)
        and any(sub is attr_node for sub in ast.walk(fn))
    ]
    check(any(nm in allowed_fns for nm in enclosing), lambda: f"Reflection {attr_node.attr} outside allowlisted functions in {rel_posix}:{attr_node.lineno}")


def _is_wide_tuple_subscript(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"tuple", "Tuple"}
        and isinstance(node.slice, ast.Tuple)
        and len(node.slice.elts) >= 3
    )


_TUPLE_RETURN_COMPAT_NAMES: Final[frozenset[str]] = frozenset(
    {"tuple", "Tuple", "Sequence", "Iterable", "object", "JsonValue", "JsonArray", "ScopedHop"}
)


def _iter_direct_fn_returns(stmts: Sequence[ast.stmt]) -> list[ast.Return]:
    found: list[ast.Return] = []
    for st in stmts:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(st, ast.Return):
            found.append(st)
        for ch in ast.iter_child_nodes(st):
            if isinstance(ch, ast.stmt):
                found.extend(_iter_direct_fn_returns((ch,)))
    return found


def _assert_no_wide_tuple_params(fn_node: ast.FunctionDef | ast.AsyncFunctionDef, label: str) -> None:
    if fn_node.name.startswith("_"):
        if (
            fn_node.returns is not None
            and isinstance(fn_node.returns, ast.Subscript)
            and isinstance(fn_node.returns.value, ast.Name)
            and fn_node.returns.value.id in {"tuple", "Tuple"}
            and isinstance(fn_node.returns.slice, ast.Tuple)
            and len(fn_node.returns.slice.elts) >= 4
        ):
            raise AssertionError(f"Wide 4+-tuple return annotation forbidden in private {label}:{fn_node.name}")
        return
    for arg in (*fn_node.args.posonlyargs, *fn_node.args.args, *fn_node.args.kwonlyargs):
        if arg.annotation is not None and any(_is_wide_tuple_subscript(s) for s in ast.walk(arg.annotation)):
            raise AssertionError(f"Anonymous 3+-tuple parameter '{arg.arg}' forbidden in {label}:{fn_node.name}")
    if fn_node.returns is not None and any(_is_wide_tuple_subscript(s) for s in ast.walk(fn_node.returns)):
        raise AssertionError(f"Anonymous 3+-tuple return annotation forbidden in {label}:{fn_node.name}")
    allows_tuple = fn_node.returns is None or any(
        isinstance(n, ast.Name) and n.id in _TUPLE_RETURN_COMPAT_NAMES for n in ast.walk(fn_node.returns)
    )
    is_homog_seq = isinstance(fn_node.returns, ast.Subscript) and (
        (isinstance(fn_node.returns.value, ast.Name) and fn_node.returns.value.id == "Sequence")
        or (
            isinstance(fn_node.returns.value, ast.Name)
            and fn_node.returns.value.id in {"tuple", "Tuple"}
            and isinstance(fn_node.returns.slice, ast.Tuple)
            and len(fn_node.returns.slice.elts) == 2
            and isinstance(fn_node.returns.slice.elts[1], ast.Constant)
            and fn_node.returns.slice.elts[1].value is Ellipsis
        )
    )
    for ret in _iter_direct_fn_returns(fn_node.body):
        if isinstance(ret.value, ast.Tuple):
            if not is_homog_seq and not any(isinstance(e, ast.Starred) for e in ret.value.elts) and len(ret.value.elts) >= 3:
                raise AssertionError(f"Anonymous 3+-tuple return literal forbidden in {label}:{fn_node.name}:{ret.lineno}")
            if not allows_tuple:
                raise AssertionError(f"Tuple return literal mismatches annotation in {label}:{fn_node.name}:{ret.lineno}")


def _resolve_import_from_base(node: ast.ImportFrom, rel_mod: str) -> str:
    pkg_parts = rel_mod.split(".")[:-1]
    if node.level > 0:
        keep = max(0, len(pkg_parts) - (node.level - 1))
        base = ".".join(pkg_parts[:keep])
        if node.module:
            return f"{base}.{node.module}" if base else node.module
        return base
    return node.module or ""


def _assert_rpc_readonly_fs_import(node: ast.AST, bound_targets: Sequence[str], rel_mod: str) -> None:
    if isinstance(node, ast.Import):
        for imp in bound_targets:
            if imp == "core" or imp.startswith("core.filesystem"):
                raise AssertionError(f"Forbidden bare filesystem/core import in {rel_mod}: {imp}")
        return
    for imp in bound_targets:
        if imp.startswith("core.filesystem") and imp != "core.filesystem.fs.read_json_dict":
            raise AssertionError(f"Non-readonly filesystem import in {rel_mod}: {imp}")


_ALLOWED_CORE_IMPORTS_BY_PREFIX: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("core.__init__", ()),
    ("core.filesystem.__init__", ()),
    ("core.metadata.__init__", ()),
    ("core.packaging.__init__", ()),
    ("core.execution.__init__", ()),
    ("core.surface.__init__", ()),
    ("core.foundation.__init__", ("core.foundation",)),
    ("core.foundation.primitives", ("core.foundation.primitives",)),
    ("core.foundation.errors", ("core.foundation.errors", "core.foundation.primitives")),
    ("core.foundation.codec", ("core.foundation.codec", "core.foundation.primitives", "core.foundation.errors")),
    ("core.foundation.observability", ("core.foundation.observability", "core.foundation.primitives", "core.foundation.errors")),
    (
        "core.foundation.profiler",
        (
            "core.foundation.profiler",
            "core.foundation.observability",
            "core.foundation.primitives",
            "core.foundation.errors",
        ),
    ),
    ("core.foundation.proc", ("core.foundation.proc", "core.foundation.primitives", "core.foundation.errors")),
    (
        "core.filesystem.fs",
        (
            "core.filesystem.fs",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.observability",
            "core.foundation.proc",
        ),
    ),
    (
        "core.filesystem.vfs",
        (
            "core.filesystem.vfs",
            "core.filesystem.fs",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.codec",
        ),
    ),
    (
        "core.filesystem.storage",
        (
            "core.filesystem.storage",
            "core.filesystem.vfs",
            "core.filesystem.fs",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.observability",
            "core.foundation.profiler",
        ),
    ),
    (
        "core.filesystem.space",
        (
            "core.filesystem.space",
            "core.filesystem.storage",
            "core.filesystem.vfs",
            "core.filesystem.fs",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.codec",
            "core.foundation.observability",
            "core.foundation.profiler",
        ),
    ),
    (
        "core.metadata.config",
        (
            "core.metadata.config",
            "core.filesystem.fs",
            "core.foundation",
        ),
    ),
    (
        "core.metadata.contributes",
        (
            "core.metadata.contributes",
            "core.metadata.config",
            "core.filesystem.fs",
            "core.foundation",
        ),
    ),
    (
        "core.packaging.env",
        (
            "core.packaging.env",
            "core.metadata.config",
            "core.filesystem.vfs",
            "core.filesystem.fs",
            "core.foundation",
        ),
    ),
    (
        "core.packaging.installer",
        (
            "core.packaging.installer",
            "core.packaging.env",
            "core.metadata.contributes",
            "core.metadata.config",
            "core.filesystem.vfs",
            "core.filesystem.fs",
            "core.foundation",
        ),
    ),
    (
        "core.execution.event",
        (
            "core.execution.event",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.codec",
        ),
    ),
    (
        "core.execution.lifecycle",
        (
            "core.execution.lifecycle",
            "core.execution.event",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.observability",
        ),
    ),
    (
        "core.execution.rpc",
        (
            "core.execution.rpc",
            "core.filesystem.fs.read_json_dict",
            "core.foundation.primitives",
            "core.foundation.errors",
            "core.foundation.observability",
            "core.foundation.proc",
        ),
    ),
    (
        "core.execution.runtime",
        (
            "core.execution.runtime",
            "core.execution.event",
            "core.execution.lifecycle",
            "core.execution.rpc",
            "core.filesystem.fs",
            "core.filesystem.vfs",
            "core.filesystem.space",
            "core.metadata.config",
            "core.metadata.contributes",
            "core.foundation",
        ),
    ),
    (
        "core.execution.daemon",
        (
            "core.execution.daemon",
            "core.execution.runtime",
            "core.execution.lifecycle",
            "core.execution.rpc",
            "core.filesystem.fs",
            "core.foundation",
        ),
    ),
    (
        "core.surface.sdk",
        (
            "core.surface.sdk",
            "core.execution.runtime",
            "core.execution.rpc",
            "core.execution.event",
            "core.execution.lifecycle",
            "core.filesystem.vfs",
            "core.filesystem.storage",
            "core.filesystem.space",
            "core.metadata.config",
            "core.metadata.contributes",
            "core.foundation",
        ),
    ),
    (
        "core.surface.cli",
        (
            "core.surface.cli",
            "core.surface.sdk",
            "core.execution.runtime",
            "core.execution.rpc",
            "core.execution.event",
            "core.execution.lifecycle",
            "core.packaging.installer",
            "core.metadata.config",
            "core.filesystem.fs",
            "core.filesystem.vfs",
            "core.foundation",
        ),
    ),
    (
        "core.surface.bootstrap",
        (
            "core.surface.bootstrap",
            "core.surface.cli",
            "core.surface.sdk",
            "core.execution.daemon",
            "core.execution.runtime",
            "core.execution.rpc",
            "core.execution.lifecycle",
            "core.execution.event",
            "core.packaging.installer",
            "core.packaging.env",
            "core.metadata.contributes",
            "core.metadata.config",
            "core.filesystem.space",
            "core.filesystem.storage",
            "core.filesystem.vfs",
            "core.filesystem.fs",
            "core.foundation",
        ),
    ),
)


def _lookup_allowed_core_prefixes(rel_mod: str) -> Optional[tuple[str, ...]]:
    for mod_pfx, allowed in _ALLOWED_CORE_IMPORTS_BY_PREFIX:
        if rel_mod == mod_pfx or rel_mod.startswith(f"{mod_pfx}."):
            return allowed
    return None


def _check_dag_imports(
    node: ast.AST,
    rel_mod: str,
    forbidden_by_prefix: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    bound_targets: list[str] = []
    all_targets: list[str] = []
    base = ""
    if isinstance(node, ast.Import):
        bound_targets = [alias.name for alias in node.names]
        all_targets = list(bound_targets)
    elif isinstance(node, ast.ImportFrom):
        base = _resolve_import_from_base(node, rel_mod)
        bound_targets = [f"{base}.{a.name}" if base else a.name for a in node.names]
        all_targets = [base, *bound_targets] if base else list(bound_targets)
    if not all_targets:
        return
    if rel_mod.startswith("core.execution.rpc"):
        _assert_rpc_readonly_fs_import(node, bound_targets, rel_mod)
    applicable_bad = [bad for mod_p, bads in forbidden_by_prefix if rel_mod.startswith(mod_p) for bad in bads]
    for imp in all_targets:
        if any(imp.startswith(bad) for bad in applicable_bad):
            raise AssertionError(f"Illegal reverse import in {rel_mod}: {imp}")
    allowed_core_prefixes = _lookup_allowed_core_prefixes(rel_mod)
    if allowed_core_prefixes is None:
        raise AssertionError(f"Module '{rel_mod}' missing from explicit DAG allowlist")
    for b_imp in bound_targets:
        if b_imp == "core" or b_imp.startswith("core."):
            if not any(b_imp == pfx or b_imp.startswith(f"{pfx}.") for pfx in allowed_core_prefixes):
                raise AssertionError(f"Import '{b_imp}' not in explicit DAG allowlist for {rel_mod}")
    if (
        isinstance(node, ast.ImportFrom)
        and base == "core.foundation"
        and any(bad.startswith("core.foundation.") for bad in applicable_bad)
    ):
        raise AssertionError(f"Illegal barrel import from core.foundation in {rel_mod}")
    for b_imp in bound_targets:
        if any(bad.startswith(f"{b_imp}.") for bad in applicable_bad):
            raise AssertionError(f"Illegal parent-package umbrella import in {rel_mod}: {b_imp}")


def _assert_no_local_imports(fn_node: ast.FunctionDef | ast.AsyncFunctionDef, label: str) -> None:
    for sub in ast.walk(fn_node):
        if isinstance(sub, (ast.Import, ast.ImportFrom)):
            raise AssertionError(f"Function-local import forbidden in {label}:{fn_node.name}:{sub.lineno}")


def _collect_ast_and_str_ann_loads(tree: ast.AST) -> set[str]:
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    for n in ast.walk(tree):
        if isinstance(n, ast.AnnAssign) and isinstance(n.annotation, ast.Constant) and isinstance(n.annotation.value, str):
            try:
                ann_t = ast.parse(n.annotation.value, mode="eval")
                used.update(sn.id for sn in ast.walk(ann_t) if isinstance(sn, ast.Name))
            except SyntaxError:
                pass
    return used


def _assert_all_ann_assign_symbols_resolve(tree: ast.AST, label: str) -> None:
    if not isinstance(tree, ast.Module):
        return
    known = {k for k, _ in inspect.getmembers_static(builtins)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            known.update(al.asname or al.name.split(".")[0] for al in node.names)
        elif isinstance(node, ast.ImportFrom):
            known.update(al.asname or al.name for al in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            known.add(node.name)
        elif isinstance(node, ast.arg):
            known.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            known.add(node.id)
    ann_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AnnAssign) and n.annotation is not None]
    for node in ann_nodes:
        for sub in ast.walk(node.annotation):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                check(
                    sub.id in known,
                    lambda s=sub.id, ln=node.lineno: f"Unimported annotation symbol {s!r} in {label}:{ln}",
                )


def _assert_no_unused_top_imports(tree: ast.AST, label: str) -> None:
    _assert_all_ann_assign_symbols_resolve(tree, label)
    if not isinstance(tree, ast.Module):
        return
    seen_bound: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for al in stmt.names:
                nm = al.asname or al.name.split(".")[0]
                check(nm not in seen_bound, lambda: f"Duplicate top-level import '{nm}' in {label}:{stmt.lineno}")
                seen_bound.add(nm)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module != "__future__":
            for al in stmt.names:
                nm = al.asname or al.name
                check(nm not in seen_bound, lambda: f"Duplicate top-level import '{nm}' in {label}:{stmt.lineno}")
                seen_bound.add(nm)
    if label.endswith("__init__.py"):
        return
    used = _collect_ast_and_str_ann_loads(tree)
    for nm in seen_bound:
        check(nm in used, lambda: f"Unused import '{nm}' in {label}")


def _assert_no_stateless_private_methods(tree: ast.AST, label: str) -> None:
    for cls_node in ast.walk(tree):
        if not isinstance(cls_node, ast.ClassDef):
            continue
        for ch in cls_node.body:
            if not isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not ch.name.startswith("_") or ch.name.startswith("__") or _is_stub_ellipsis_fn(ch):
                continue
            decs = {
                d.id if isinstance(d, ast.Name) else (d.attr if isinstance(d, ast.Attribute) else "")
                for d in ch.decorator_list
            }
            if decs & {"staticmethod", "abstractmethod", "overload"}:
                continue
            pos_args = [*ch.args.posonlyargs, *ch.args.args]
            expected_rcvr = "cls" if "classmethod" in decs else "self"
            if not pos_args or pos_args[0].arg != expected_rcvr:
                continue
            used = {
                sub.id
                for st in ch.body
                for sub in ast.walk(st)
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
            }
            check(expected_rcvr in used, lambda: f"Stateless private method '{cls_node.name}.{ch.name}' in {label}:{ch.lineno}")


def _assert_no_cross_collaborator_private_calls(tree: ast.AST, label: str) -> None:
    cls_privs: dict[str, set[str]] = {}
    for cnode in ast.walk(tree):
        if not isinstance(cnode, ast.ClassDef):
            continue
        own: set[str] = set()
        for ch in cnode.body:
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                own.add(ch.name)
            elif isinstance(ch, ast.Assign):
                for tgt in ch.targets:
                    if isinstance(tgt, ast.Name):
                        own.add(tgt.id)
            elif isinstance(ch, ast.AnnAssign) and isinstance(ch.target, ast.Name):
                own.add(ch.target.id)
        for sub in ast.walk(cnode):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id in {"self", "cls"}:
                own.add(sub.attr)
        cls_privs[cnode.name] = own

    cls_stack: list[str] = []

    def _visit(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            cls_stack.append(node.name)
            for ch in node.body:
                _visit(ch)
            cls_stack.pop()
            return
        if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
            val = node.value
            allowed = False
            if isinstance(val, ast.Name) and (val.id in {"self", "cls"} or val.id in cls_stack):
                allowed = True
            elif cls_stack and node.attr in cls_privs.get(cls_stack[-1], set()):
                allowed = True
            elif label.endswith("foundation/codec.py") and isinstance(val, ast.Name) and val.id == "typing" and node.attr == "_cleanups":
                allowed = True
            if not allowed:
                raise AssertionError(
                    f"Cross-collaborator private access '{ast.unparse(val)}.{node.attr}' forbidden in {label}:{node.lineno}"
                )
        for ch in ast.iter_child_nodes(node):
            _visit(ch)

    _visit(tree)


def _assert_no_duplicate_defs(tree: ast.AST, label: str) -> None:
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.Module, ast.ClassDef)):
            continue
        seen_names: set[str] = set()
        for ch in scope.body:
            if not isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_ov = any(
                (isinstance(d, ast.Name) and d.id == "overload")
                or (isinstance(d, ast.Attribute) and d.attr == "overload")
                for d in ch.decorator_list
            )
            if is_ov:
                continue
            check(ch.name not in seen_names, lambda: f"Duplicate function/method {ch.name} in {label}:{ch.lineno}")
            seen_names.add(ch.name)


def _is_stub_ellipsis_fn(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if any(
        (isinstance(d, ast.Name) and d.id in {"overload", "abstractmethod"})
        or (isinstance(d, ast.Attribute) and d.attr in {"overload", "abstractmethod"})
        for d in node.decorator_list
    ):
        return True
    stmts = node.body
    if len(stmts) == 1 and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant):
        return stmts[0].value.value is Ellipsis
    if (
        len(stmts) == 2
        and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, ast.Constant)
        and isinstance(stmts[0].value.value, str)
        and isinstance(stmts[1], ast.Expr)
        and isinstance(stmts[1].value, ast.Constant)
    ):
        return stmts[1].value.value is Ellipsis
    return False


def _assert_no_unused_function_params(node: ast.FunctionDef | ast.AsyncFunctionDef, label: str) -> None:
    if _is_stub_ellipsis_fn(node):
        return
    if (label.startswith("embedded:") or label.startswith("inline_py_")) and node.name in {"run", "on_start", "on_init"}:
        return
    used = {
        sub.id
        for stmt in node.body
        for sub in ast.walk(stmt)
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
    }
    all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg is not None:
        all_args.append(node.args.vararg)
    if node.args.kwarg is not None:
        all_args.append(node.args.kwarg)
    for idx, arg in enumerate(all_args):
        if (idx == 0 and arg.arg in {"self", "cls"}) or arg.arg.startswith("_"):
            continue
        if arg.arg not in used:
            raise AssertionError(f"Unused parameter '{arg.arg}' in {label}:{node.name} (line {node.lineno})")


_ROUND_SYM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|_)(?:round\d+|rig_\d+|r[1-9]\d*(?!c\d))(?:_|[A-Z]|$)", re.IGNORECASE
)
_LOCAL_RIG_NUM_RE: Final[re.Pattern[str]] = re.compile(r"^_?rig_\d+$", re.IGNORECASE)


def _assert_zero_round_symbol_names(tree: ast.AST, label: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and _ROUND_SYM_RE.search(node.name):
            raise AssertionError(f"Round-numbered symbol '{node.name}' forbidden in {label}:{node.lineno}")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if _LOCAL_RIG_NUM_RE.match(node.id) or (len(node.id) >= 4 and _ROUND_SYM_RE.search(node.id)):
                raise AssertionError(f"Round/lineno-numbered variable '{node.id}' forbidden in {label}:{node.lineno}")


def _audit_ast_tree_metrics(tree: ast.AST, label: str, *, allow_import_module: bool = False) -> None:
    _assert_no_unused_top_imports(tree, label)
    _assert_no_duplicate_defs(tree, label)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            raise AssertionError(f"Any forbidden in {label}:{node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr in {"Any", "getattr", "setattr", "hasattr", "delattr"}:
            raise AssertionError(f"Forbidden attribute '{node.attr}' in {label}:{node.lineno}")
        if isinstance(node, ast.Attribute):
            check(node.attr != "__dict__", lambda: f"Direct .__dict__ reflection forbidden in {label}:{node.lineno}")
            if not allow_import_module:
                check(node.attr != "import_module", lambda: f"Runtime import_module forbidden in {label}:{node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            check(node.func.id != "print", lambda: f"Bare print() forbidden in {label}:{node.lineno}")
            check(node.func.id not in {"getattr", "setattr", "hasattr", "delattr", "__import__", "vars", "dir"}, lambda: f"Dynamic {node.func.id} forbidden in {label}")
        if isinstance(node, ast.Assert):
            raise AssertionError(f"Bare assert forbidden under -O in {label}:{node.lineno}")
        if isinstance(node, ast.Lambda) and isinstance(node.body, ast.Tuple) and len(node.body.elts) >= 3:
            raise AssertionError(f"Wide 3+ tuple lambda forbidden in {label}:{node.lineno}")
        if isinstance(node, ast.Import):
            for al in node.names:
                check(al.name != "pickle", lambda: f"Forbidden pickle import in {label}:{node.lineno}")
        if isinstance(node, ast.ImportFrom):
            check(node.module != "pickle", lambda: f"Forbidden pickle import in {label}:{node.lineno}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _assert_no_local_imports(node, label)
            _assert_no_wide_tuple_params(node, label)
            _assert_no_unused_function_params(node, label)


def _assert_zero_comment_noise_bytes(raw_bytes: bytes, label: str) -> None:
    comment_noise_re = re.compile(
        r"\b(?:FR-\d+|DR-\d+|EC-\d+|AUD-[A-Z0-9_-]+|P[0-3](?:-\d+)?|D[1-5]|S[1-6]|RC-\d+|N-\d+|"
        r"R[1-9]\d*(?:-[A-Z0-9]+)?|Issue-\d+|TODO|FIXME)\b|#\s*Step\s+\d+|#\s*Sub-path\s+\d+|\bProbe\s+[A-Z0-9]|^#\s*[-=]{3,}",
        re.IGNORECASE,
    )
    lines = raw_bytes.splitlines(keepends=True)
    it = iter(lines)
    for tok in tokenize.tokenize(lambda: next(it, b"")):
        if tok.type == tokenize.COMMENT:
            m = comment_noise_re.search(tok.string)
            check(m is None, lambda: f"Forbidden comment noise '{m.group(0)}' in {label}:{tok.start[0]}")


def _assert_zero_comment_noise(py_path: Path) -> None:
    _assert_zero_comment_noise_bytes(py_path.read_bytes(), py_path.name)


_ROUND_STR_NOISE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:blind[-_ ]?review|\bround[-_ ]?\d+\b|(?:_|-)r[1-9]\d*(?:$|[/_-]))",
    re.IGNORECASE,
)


def _assert_zero_round_string_literals(tree: ast.AST, label: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            m = _ROUND_STR_NOISE_RE.search(node.value)
            check(m is None, lambda: f"Forbidden round/review string noise {m.group(0)!r} in {label}:{node.lineno}")


_PUBLIC_DOMAIN_ROOTS: Final[dict[str, object]] = {
    "core": core,
    "core.foundation": foundation_pkg,
    "core.filesystem.fs": fs_pkg,
    "core.filesystem.vfs": vfs_pkg,
    "core.filesystem.storage": storage_pkg,
    "core.filesystem.space": space_pkg,
    "core.metadata.config": config_pkg,
    "core.metadata.contributes": contributes_pkg,
    "core.packaging.env": env_pkg,
    "core.packaging.installer": installer_pkg,
    "core.execution.event": event_pkg,
    "core.execution.lifecycle": lifecycle_pkg,
    "core.execution.rpc": rpc_pkg,
    "core.execution.runtime": runtime_pkg,
    "core.execution.daemon": daemon_pkg,
    "core.surface.sdk": sdk_pkg,
    "core.surface.cli": cli_pkg,
    "core.surface.bootstrap": bootstrap_pkg,
}


def _assert_zero_whitebox_private_access_in_tests(tree: ast.AST, label: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("core") and alias.name not in _PUBLIC_DOMAIN_ROOTS:
                    raise AssertionError(f"Internal submodule import '{alias.name}' forbidden in {label}:{node.lineno}")
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("core"):
            dom_mod = _PUBLIC_DOMAIN_ROOTS.get(node.module)
            if dom_mod is None:
                raise AssertionError(f"Internal submodule import 'from {node.module}' forbidden in {label}:{node.lineno}")
            pub_all = set(dict(inspect.getmembers_static(dom_mod)).get("__all__", ()))
            for alias in node.names:
                check(
                    not alias.name.startswith("_") and (node.module == "core" or alias.name in pub_all),
                    lambda nm=alias.name, md=node.module, ln=node.lineno: f"Unexported import '{md}.{nm}' forbidden in {label}:{ln}",
                )
        if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
            if isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"}:
                continue
            raise AssertionError(f"Whitebox private attribute access '.{node.attr}' forbidden in {label}:{node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os"
                and node.func.value.attr == "environ"
                and node.func.attr in {"pop", "setdefault", "update", "clear"}
            ):
                raise AssertionError(f"Global os.environ.{node.func.attr}() mutation forbidden in {label}:{node.lineno}")
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr in {"putenv", "unsetenv"}:
                raise AssertionError(f"Global os.{node.func.attr}() mutation forbidden in {label}:{node.lineno}")
        if isinstance(node, (ast.Assign, ast.Delete)):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Attribute)
                    and isinstance(tgt.value.value, ast.Name)
                    and tgt.value.value.id == "os"
                    and tgt.value.attr == "environ"
                ):
                    raise AssertionError(f"Global os.environ[...] mutation forbidden in {label}:{node.lineno}")
    forbidden_toks = ("YSCB_" + "WORKER_AUTH_TOKEN", "_" + "yscb_v2_mod_", "_" + "ScopedModuleFinder")
    gate0_exempt_fns = {"verify_gate0_ast_architecture", "_assert_zero_whitebox_private_access_in_tests"}
    for top_stmt in tree.body if isinstance(tree, ast.Module) else ():
        is_exempt_fn = isinstance(top_stmt, ast.FunctionDef) and top_stmt.name in gate0_exempt_fns
        for fn_n in ast.walk(top_stmt):
            if isinstance(fn_n, ast.Constant) and isinstance(fn_n.value, str):
                for bad_tok in forbidden_toks:
                    check(bad_tok not in fn_n.value, lambda bt=bad_tok, ln=fn_n.lineno: f"Whitebox internal literal {bt!r} forbidden in {label}:{ln}")
                if not is_exempt_fn and fn_n.value == "core.execution.runtime.worker_entry":
                    raise AssertionError(f"Direct internal module CLI string forbidden in {label}:{fn_n.lineno}")


def _target_expr_writes_py(expr: ast.AST) -> bool:
    for sub in ast.walk(expr):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.endswith(".py"):
            return True
    return False


def _placeholder_for_joined_interp(prev_chunk: str) -> str:
    if prev_chunk.endswith("."):
        return "X"
    if prev_chunk.endswith(("'", '"')):
        return "x"
    if prev_chunk.endswith(("=", "(", ",", " ", ":")):
        return "1"
    return "X"


def _extract_const_str_or_joined_lines(expr: Optional[ast.AST]) -> Optional[str]:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, (ast.Tuple, ast.List)) and expr.elts and all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in expr.elts
    ):
        return "\n".join(e.value for e in expr.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        left_s = _extract_const_str_or_joined_lines(expr.left)
        right_s = _extract_const_str_or_joined_lines(expr.right)
        return (left_s + right_s) if (left_s is not None and right_s is not None) else None
    if isinstance(expr, ast.JoinedStr):
        parts: list[str] = []
        for val in expr.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                parts.append(val.value)
            elif isinstance(val, ast.FormattedValue):
                parts.append(_placeholder_for_joined_interp(parts[-1] if parts else ""))
        return "".join(parts)
    return None


def _collect_inline_py_snippets(self_tree: ast.AST) -> list[tuple[int, str]]:
    snippets: list[tuple[int, str]] = []
    for node in ast.walk(self_tree):
        val_expr = node.value if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Return)) else None
        cand_txt = _extract_const_str_or_joined_lines(val_expr)
        if cand_txt is not None and "def create_module(" in cand_txt:
            snippets.append((node.lineno, cand_txt))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write_text"
            and bool(node.args)
        ):
            w_txt = _extract_const_str_or_joined_lines(node.args[0])
            if w_txt is not None and ("def create_module(" in w_txt or _target_expr_writes_py(node.func.value)):
                snippets.append((node.lineno, w_txt))
    return snippets


def _audit_inline_module_entry_literals(self_tree: ast.AST) -> None:
    for idx, (lineno, txt) in enumerate(_collect_inline_py_snippets(self_tree), 1):
        lbl = f"inline_py_{idx}:L{lineno}"
        parsed = ast.parse(txt, filename=lbl)
        _assert_zero_comment_noise_bytes(txt.encode("utf-8"), lbl)
        _verify_symtable_clean(txt, lbl)
        _assert_zero_round_symbol_names(parsed, lbl)
        _audit_ast_tree_metrics(parsed, lbl, allow_import_module=True)


def audit_self_test_ast(include_runner: bool = True) -> None:
    test_files = sorted(TESTS_ROOT.glob("*.py"))
    check(test_files, "No test files found under core_v2/tests/")
    runner_path = CORE_V2_ROOT / "verify_execution_live.py"
    py_paths = [*test_files, runner_path] if (include_runner and runner_path.is_file()) else list(test_files)
    for py_path in py_paths:
        src = py_path.read_text(encoding="utf-8")
        check(("# type" + ": ignore") not in src, f"Test suite must not suppress static type checks: {py_path.name}")
        _assert_zero_comment_noise(py_path)
        _verify_symtable_clean(src, py_path.name)
        tree = ast.parse(src, filename=py_path.name)
        _assert_zero_round_symbol_names(tree, py_path.name)
        _assert_zero_round_string_literals(tree, py_path.name)
        _assert_zero_whitebox_private_access_in_tests(tree, py_path.name)
        _audit_ast_tree_metrics(tree, py_path.name)
        _audit_inline_module_entry_literals(tree)
    audited_paths = {p.resolve() for p in py_paths}
    for mod_name, mod_obj in list(sys.modules.items()):
        if not (mod_name == "tests" or mod_name.startswith("tests.") or mod_name in {"__main__", "verify_execution_live"}):
            continue
        if not inspect.ismodule(mod_obj):
            continue
        try:
            src_f = inspect.getsourcefile(mod_obj)
        except TypeError:
            src_f = None
        if src_f is not None and Path(src_f).resolve() in audited_paths:
            _verify_module_runtime_type_hints(mod_name)
    for tpl_name, tpl_src in EMBEDDED_MODULE_TEMPLATES:
        label = f"embedded:{tpl_name}"
        _verify_symtable_clean(tpl_src, label)
        tpl_tree = ast.parse(tpl_src, filename=label)
        _assert_zero_round_symbol_names(tpl_tree, label)
        _assert_zero_round_string_literals(tpl_tree, label)
        _assert_zero_whitebox_private_access_in_tests(tpl_tree, label)
        _audit_ast_tree_metrics(tpl_tree, label)


def _walk_runtime_type_hints(container: object, mod_name: str, seen: set[int]) -> None:
    oid = id(container)
    if oid in seen:
        return
    seen.add(oid)
    for attr_name, val in inspect.getmembers_static(container):
        if attr_name.startswith("__") and attr_name not in {"__init__", "__call__"}:
            continue
        if isinstance(val, property):
            if val.fget is not None and val.fget.__module__ == mod_name:
                typing.get_type_hints(val.fget, include_extras=True)
            continue
        if isinstance(val, (staticmethod, classmethod)):
            fn = val.__func__
            if fn.__module__ == mod_name:
                typing.get_type_hints(fn, include_extras=True)
            continue
        if inspect.isclass(val) and val.__module__ == mod_name:
            typing.get_type_hints(val, include_extras=True)
            _walk_runtime_type_hints(val, mod_name, seen)
        elif inspect.isfunction(val) and val.__module__ == mod_name:
            typing.get_type_hints(val, include_extras=True)


def _assert_module_class_self_attrs(mod: object, mod_name: str) -> None:
    src_file = inspect.getsourcefile(mod) if inspect.ismodule(mod) else None
    if src_file is None:
        return
    tree = ast.parse(Path(src_file).read_text(encoding="utf-8"), filename=mod_name)
    cls_map = {k: v for k, v in inspect.getmembers_static(mod) if inspect.isclass(v) and v.__module__ == mod_name}
    ast_cls_map = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in cls_map:
            continue
        defined = {k for k, _ in inspect.getmembers_static(cls_map[node.name])}
        for base_c in cls_map[node.name].__mro__:
            defined.update(k for k, _ in inspect.getmembers_static(base_c))
            base_ast = ast_cls_map.get(base_c.__name__)
            if base_ast is not None:
                defined.update(
                    sub.attr
                    for sub in ast.walk(base_ast)
                    if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "self" and isinstance(sub.ctx, ast.Store)
                )
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "self" and isinstance(sub.ctx, ast.Load):
                check(sub.attr in defined, lambda: f"Undefined self.{sub.attr} in {mod_name}.{node.name}:{sub.lineno}")
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "self"
            ):
                _assert_self_method_call_arity(cls_map[node.name], sub, f"{mod_name}.{node.name}")


def _assert_self_method_call_arity(cls_obj: type[object], call_node: ast.Call, label: str) -> None:
    check(isinstance(call_node.func, ast.Attribute))
    m_name = call_node.func.attr
    raw_member = dict(inspect.getmembers_static(cls_obj)).get(m_name)
    if raw_member is None:
        return
    if isinstance(raw_member, property):
        raise AssertionError(f"Property self.{m_name} called as method in {label}:{call_node.lineno}")
    target_fn = raw_member.__func__ if isinstance(raw_member, (staticmethod, classmethod)) else raw_member
    if not inspect.isfunction(target_fn):
        return
    if any(isinstance(a, ast.Starred) for a in call_node.args) or any(k.arg is None for k in call_node.keywords):
        return
    sig = inspect.signature(target_fn)
    params = list(sig.parameters.values())
    if not isinstance(raw_member, staticmethod) and params:
        params = params[1:]
    bound_sig = sig.replace(parameters=params)
    dummy_pos = [None] * len(call_node.args)
    dummy_kw = {k.arg: None for k in call_node.keywords if k.arg is not None}
    try:
        bound_sig.bind(*dummy_pos, **dummy_kw)
    except TypeError as exc:
        raise AssertionError(f"Arity/kw mismatch calling self.{m_name} in {label}:{call_node.lineno}: {exc}") from exc


def _verify_module_runtime_type_hints(mod_name: str) -> None:
    mod = sys.modules[mod_name]
    _walk_runtime_type_hints(mod, mod_name, set())
    _assert_module_class_self_attrs(mod, mod_name)
    src_file = inspect.getsourcefile(mod) if inspect.ismodule(mod) else None
    if src_file is None:
        return
    tree = ast.parse(Path(src_file).read_text(encoding="utf-8"), filename=mod_name)
    ns_classes = {k: v for k, v in inspect.getmembers_static(mod) if inspect.isclass(v)}
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and isinstance(sub.ctx, ast.Load):
            target_cls = ns_classes.get(sub.value.id)
            if target_cls is None:
                continue
            valid = {k for base_c in target_cls.__mro__ for k, _ in inspect.getmembers_static(base_c)}
            check(sub.attr in valid, lambda: f"Undefined {sub.value.id}.{sub.attr} in {mod_name}:{sub.lineno}")


def _is_overload_decorated(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        (isinstance(d, ast.Name) and d.id == "overload") or (isinstance(d, ast.Attribute) and d.attr == "overload")
        for d in fn_node.decorator_list
    )


def _is_property_decorated(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "property" for d in fn_node.decorator_list)


def _method_decorator_tags(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    tags: set[str] = set()
    for dec in fn_node.decorator_list:
        nm = dec.id if isinstance(dec, ast.Name) else (dec.attr if isinstance(dec, ast.Attribute) else "")
        if nm in {"property", "staticmethod", "classmethod", "contextmanager", "abstractmethod"}:
            tags.add(nm)
    return tags


def _strip_ann_quotes(expr: ast.expr) -> ast.expr:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        try:
            return _strip_ann_quotes(ast.parse(expr.value, mode="eval").body)
        except SyntaxError:
            return expr
    if isinstance(expr, ast.Subscript):
        if isinstance(expr.value, ast.Name) and expr.value.id == "Literal":
            return expr
        return ast.Subscript(value=_strip_ann_quotes(expr.value), slice=_strip_ann_quotes(expr.slice), ctx=expr.ctx)
    if isinstance(expr, ast.Tuple):
        return ast.Tuple(elts=[_strip_ann_quotes(e) for e in expr.elts], ctx=expr.ctx)
    if isinstance(expr, ast.List):
        return ast.List(elts=[_strip_ann_quotes(e) for e in expr.elts], ctx=expr.ctx)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        return ast.BinOp(left=_strip_ann_quotes(expr.left), op=expr.op, right=_strip_ann_quotes(expr.right))
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and expr.value.id in {"typing", "cabc"}:
        return ast.Name(id=expr.attr, ctx=ast.Load())
    return expr


def _norm_ann_ast(node: Optional[ast.expr], alias_map: Mapping[str, str] = {}) -> str:
    if node is None:
        return "<missing>"
    cleaned = _strip_ann_quotes(node)
    if (
        isinstance(cleaned, ast.Subscript)
        and isinstance(cleaned.value, ast.Name)
        and cleaned.value.id == "Optional"
    ):
        inner = _norm_ann_ast(cleaned.slice, alias_map)
        return f"Optional[{inner}]"
    if isinstance(cleaned, ast.BinOp) and isinstance(cleaned.op, ast.BitOr):
        left_s = _norm_ann_ast(cleaned.left, alias_map)
        right_s = _norm_ann_ast(cleaned.right, alias_map)
        if right_s == "None":
            return f"Optional[{left_s}]"
    txt = ast.unparse(cleaned)
    for k, v in alias_map.items():
        if txt == k:
            return v
    return txt


def _norm_dflt_ast(node: Optional[ast.expr]) -> Optional[str]:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and node.value is Ellipsis:
        return "<has_default>"
    return ast.unparse(node)


@dataclass(frozen=True, slots=True)
class _AstParamSig:
    name: str
    kind: str
    ann: str
    default: Optional[str]


def _ast_full_param_sig(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    drop_self: bool,
    alias_map: Mapping[str, str] = {},
) -> list[_AstParamSig]:
    posonly = [(a, "posonly") for a in fn_node.args.posonlyargs]
    reg_pos = [(a, "pos") for a in fn_node.args.args]
    combined = [*posonly, *reg_pos]
    pad = len(combined) - len(fn_node.args.defaults)
    pos_dflts: list[Optional[ast.expr]] = [None] * pad + list(fn_node.args.defaults)
    out: list[_AstParamSig] = []
    for idx, ((arg, kind), dflt) in enumerate(zip(combined, pos_dflts)):
        if drop_self and idx == 0 and arg.arg in {"self", "cls"}:
            continue
        out.append(_AstParamSig(arg.arg, kind, _norm_ann_ast(arg.annotation, alias_map), _norm_dflt_ast(dflt)))
    if fn_node.args.vararg is not None:
        va = fn_node.args.vararg
        out.append(_AstParamSig(va.arg, "vararg", _norm_ann_ast(va.annotation, alias_map), None))
    for kw_arg, kw_dflt in zip(fn_node.args.kwonlyargs, fn_node.args.kw_defaults):
        out.append(_AstParamSig(kw_arg.arg, "kw", _norm_ann_ast(kw_arg.annotation, alias_map), _norm_dflt_ast(kw_dflt)))
    if fn_node.args.kwarg is not None:
        ka = fn_node.args.kwarg
        out.append(_AstParamSig(ka.arg, "kwarg", _norm_ann_ast(ka.annotation, alias_map), None))
    return out


def _resolve_ast_expr_value(node: ast.expr, ns: Mapping[str, object]) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_resolve_ast_expr_value(e, ns) for e in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        val = node.operand.value
        check(isinstance(val, (int, float)))
        return -val
    if isinstance(node, ast.Name):
        if node.id == "frozenset":
            return frozenset
        check(node.id in ns, lambda: f"Unresolved default symbol {node.id!r}")
        return ns[node.id]
    if isinstance(node, ast.Attribute):
        base = _resolve_ast_expr_value(node.value, ns)
        return dict(inspect.getmembers_static(base))[node.attr]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _resolve_ast_expr_value(node.left, ns)
        right = _resolve_ast_expr_value(node.right, ns)
        check(isinstance(left, Flag) and isinstance(right, Flag))
        return left | right
    if isinstance(node, ast.Call) and not node.args and not node.keywords:
        fn = _resolve_ast_expr_value(node.func, ns)
        check(callable(fn))
        return fn()
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MappingProxyType"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Dict)
        and not node.args[0].keys
    ):
        return types.MappingProxyType({})
    raise AssertionError(f"Unsupported spec default AST expression: {ast.unparse(node)}")


def _assert_default_matches_runtime(
    label: str,
    dflt_node: Optional[ast.expr],
    rt_default: object,
    ns: Mapping[str, object],
) -> None:
    if dflt_node is None:
        check(rt_default is inspect.Parameter.empty, lambda: f"Unexpected runtime default on {label}: {rt_default!r}")
        return
    check(rt_default is not inspect.Parameter.empty, lambda: f"Missing runtime default on {label}")
    if isinstance(dflt_node, ast.Constant) and dflt_node.value is Ellipsis:
        return
    exp_val = _resolve_ast_expr_value(dflt_node, ns)
    check(type(exp_val) is type(rt_default) and exp_val == rt_default, lambda: f"Default value drift on {label}: spec={exp_val!r} vs runtime={rt_default!r}")


def _assert_fn_ast_and_runtime_parity(
    label: str,
    spec_fn: ast.FunctionDef | ast.AsyncFunctionDef,
    impl_fn: ast.FunctionDef | ast.AsyncFunctionDef,
    rt_member: object,
    ctx_maps: tuple[Mapping[str, object], Mapping[str, str]],
    *,
    is_method: bool,
) -> None:
    ns, alias_map = ctx_maps
    if _is_property_decorated(spec_fn):
        check(isinstance(rt_member, property) and _is_property_decorated(impl_fn), lambda: f"{label} @property drift")
        check(_norm_ann_ast(spec_fn.returns, alias_map) == _norm_ann_ast(impl_fn.returns, alias_map), lambda: f"Property return type drift on {label}: {ast.unparse(spec_fn.returns or ast.Constant(None))} vs {ast.unparse(impl_fn.returns or ast.Constant(None))}")
        return
    is_static = isinstance(rt_member, staticmethod)
    drop_s = is_method and not is_static
    s_sig = _ast_full_param_sig(spec_fn, drop_self=drop_s, alias_map=alias_map)
    i_sig = _ast_full_param_sig(impl_fn, drop_self=drop_s, alias_map=alias_map)
    check(len(s_sig) == len(i_sig), lambda: f"Param count drift on {label}: {s_sig} vs {i_sig}")
    for sp_p, im_p in zip(s_sig, i_sig):
        check((sp_p.name, sp_p.kind) == (im_p.name, im_p.kind) and sp_p.ann == im_p.ann, lambda: f"Param type/kind drift on {label}: spec={sp_p} vs impl={im_p}")
        if sp_p.default != "<has_default>":
            check(sp_p.default == im_p.default, lambda: f"Param AST default drift on {label}.{sp_p.name}: spec={sp_p.default} vs impl={im_p.default}")
    s_ret = _norm_ann_ast(spec_fn.returns, alias_map)
    i_ret = _norm_ann_ast(impl_fn.returns, alias_map)
    check(s_ret == i_ret, lambda: f"Return type drift on {label}: spec={s_ret} vs impl={i_ret}")
    raw_fn = rt_member.__func__ if isinstance(rt_member, (staticmethod, classmethod)) else rt_member
    check(callable(raw_fn))
    rt_params = list(inspect.signature(raw_fn).parameters.values())
    if drop_s and rt_params and rt_params[0].name in {"self", "cls"}:
        rt_params = rt_params[1:]
    spec_dflts = _collect_spec_param_dflt_nodes(spec_fn, drop_self=drop_s)
    for (p_name, d_node), r_p in zip(spec_dflts, rt_params):
        _assert_default_matches_runtime(f"{label}.{p_name}", d_node, r_p.default, ns)


def _collect_spec_param_dflt_nodes(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    drop_self: bool,
) -> list[tuple[str, Optional[ast.expr]]]:
    comb = [*fn_node.args.posonlyargs, *fn_node.args.args]
    pos_d: list[Optional[ast.expr]] = [None] * (len(comb) - len(fn_node.args.defaults)) + list(fn_node.args.defaults)
    out: list[tuple[str, Optional[ast.expr]]] = []
    for idx, (a, d) in enumerate(zip(comb, pos_d)):
        if drop_self and idx == 0 and a.arg in {"self", "cls"}:
            continue
        out.append((a.arg, d))
    if fn_node.args.vararg is not None:
        out.append((fn_node.args.vararg.arg, None))
    for ka, kd in zip(fn_node.args.kwonlyargs, fn_node.args.kw_defaults):
        out.append((ka.arg, kd))
    if fn_node.args.kwarg is not None:
        out.append((fn_node.args.kwarg.arg, None))
    return out


@dataclass(slots=True)
class _ParsedModuleAstIndex:
    classes: dict[str, ast.ClassDef] = field(default_factory=dict)
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=dict)
    overloads: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = field(default_factory=dict)
    cls_methods: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]] = field(default_factory=dict)
    cls_overloads: dict[str, dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    exported_syms: set[str] = field(default_factory=set)
    value_exprs: dict[str, ast.expr] = field(default_factory=dict)
    imported_core_syms: set[str] = field(default_factory=set)
    explicit_all: Optional[tuple[str, ...]] = None


def _parse_explicit_all_tuple(value_node: ast.expr) -> tuple[str, ...]:
    raw_all = ast.literal_eval(value_node)
    check(isinstance(raw_all, tuple) and all(isinstance(item, str) for item in raw_all))
    return tuple(str(item) for item in raw_all)


def _is_public_or_spec_dunder(name: str) -> bool:
    if not name.startswith("_"):
        return True
    return name.startswith("__") and name.endswith("__") and name != "__post_init__"


def _index_single_class_ast(stmt: ast.ClassDef, idx: _ParsedModuleAstIndex) -> None:
    idx.exported_syms.add(stmt.name)
    idx.classes[stmt.name] = stmt
    m_map = idx.cls_methods.setdefault(stmt.name, {})
    ov_map = idx.cls_overloads.setdefault(stmt.name, {})
    for ch in stmt.body:
        if not isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_overload_decorated(ch):
            ov_map.setdefault(ch.name, []).append(ch)
        elif _is_public_or_spec_dunder(ch.name):
            m_map[ch.name] = ch


def _index_single_assign_ast(stmt: ast.Assign, idx: _ParsedModuleAstIndex, ignored: frozenset[str]) -> None:
    if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == "__all__":
        idx.explicit_all = _parse_explicit_all_tuple(stmt.value)
        return
    if isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == "TypeVar":
        return
    is_type_expr = isinstance(stmt.value, (ast.Name, ast.Subscript, ast.BinOp))
    for t in stmt.targets:
        if isinstance(t, ast.Name) and t.id not in ignored:
            idx.exported_syms.add(t.id)
            idx.value_exprs[t.id] = stmt.value
            if is_type_expr:
                idx.aliases[t.id] = _norm_ann_ast(stmt.value)


def _index_single_func_ast(
    stmt: ast.FunctionDef | ast.AsyncFunctionDef,
    idx: _ParsedModuleAstIndex,
    *,
    reject_collisions: bool,
) -> None:
    idx.exported_syms.add(stmt.name)
    if _is_overload_decorated(stmt):
        idx.overloads.setdefault(stmt.name, []).append(stmt)
        return
    if reject_collisions and not stmt.name.startswith("_"):
        check(stmt.name not in idx.functions, lambda: f"Duplicate kernel public function '{stmt.name}'")
    idx.functions[stmt.name] = stmt


def _index_ast_statements(
    stmts: Sequence[ast.stmt],
    idx: _ParsedModuleAstIndex,
    *,
    ignored: frozenset[str] = frozenset(),
    reject_collisions: bool = False,
) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.ClassDef):
            check(not reject_collisions or stmt.name not in idx.classes, lambda: f"Duplicate kernel class '{stmt.name}'")
            _index_single_class_ast(stmt, idx)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _index_single_func_ast(stmt, idx, reject_collisions=reject_collisions)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.module.startswith("core."):
            for al in stmt.names:
                if al.name != "*":
                    idx.imported_core_syms.add(al.asname or al.name)
        elif isinstance(stmt, ast.Assign):
            _index_single_assign_ast(stmt, idx, ignored)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id not in ignored:
            if stmt.target.id == "__all__":
                if stmt.value is not None:
                    idx.explicit_all = _parse_explicit_all_tuple(stmt.value)
                continue
            idx.exported_syms.add(stmt.target.id)
            if stmt.value is not None:
                idx.value_exprs[stmt.target.id] = stmt.value


def _build_kernel_ast_index() -> _ParsedModuleAstIndex:
    idx = _ParsedModuleAstIndex()
    py_all = sorted((CORE_SRC_ROOT / "core").rglob("*.py"))
    for py_f in py_all:
        if py_f.name != "__init__.py":
            tree = ast.parse(py_f.read_text(encoding="utf-8"), filename=py_f.name)
            _index_ast_statements(tree.body, idx, reject_collisions=True)
    for py_f in py_all:
        if py_f.name == "__init__.py":
            tree = ast.parse(py_f.read_text(encoding="utf-8"), filename=py_f.name)
            _index_ast_statements(tree.body, idx)
    return idx


_MD_OPEN_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"^[ ]{0,3}(`{3,})(.*)$")
_BARE_PY_DECL_RE: Final[re.Pattern[str]] = re.compile(r"^(?:async\s+def|def|class)\s+[A-Za-z_]")


def _find_spec_fence_violation(md_txt: str, fname: str) -> Optional[str]:
    fence_len: Optional[int] = None
    for lineno, raw_line in enumerate(md_txt.splitlines(), 1):
        if fence_len is None:
            m_open = _MD_OPEN_FENCE_RE.match(raw_line)
            if m_open is not None and "`" not in m_open.group(2):
                fence_len = len(m_open.group(1))
                continue
            if _BARE_PY_DECL_RE.match(raw_line) is not None:
                return f"Unfenced top-level Python declaration in {fname}:{lineno}: {raw_line.strip()!r}"
        else:
            stripped = raw_line.lstrip(" ")
            lead_spaces = len(raw_line) - len(stripped)
            trimmed = stripped.rstrip()
            if lead_spaces <= 3 and len(trimmed) >= fence_len and set(trimmed) == {"`"}:
                fence_len = None
    if fence_len is not None:
        return f"Unclosed markdown code fence in {fname}"
    return None


def _assert_living_spec_fence_hygiene(md_txt: str, fname: str) -> None:
    err = _find_spec_fence_violation(md_txt, fname)
    check(err is None, lambda: str(err))


def _build_spec_ast_index(md_path: Path) -> _ParsedModuleAstIndex:
    md_txt = md_path.read_text(encoding="utf-8")
    _assert_living_spec_fence_hygiene(md_txt, md_path.name)
    blocks = re.findall(r"```python\n(.*?)```", md_txt, flags=re.DOTALL)
    check(blocks, lambda: f"No python contract block found in {md_path.name}")
    ignored = frozenset({"TIn", "TOut", "TOut_co", "TPayload", "TReq", "TReqContra"})
    idx = _ParsedModuleAstIndex()
    for blk in blocks:
        _index_ast_statements(ast.parse(blk, filename=md_path.name).body, idx, ignored=ignored)
    return idx


def _lookup_mro_static_member(cls_obj: type[object], attr: str) -> object:
    for base in cls_obj.__mro__:
        for k, v in inspect.getmembers_static(base):
            if k == attr:
                return v
    raise AssertionError(f"Missing {cls_obj.__name__}.{attr}")


def _lookup_mro_method_ast(
    cls_obj: type[object],
    attr: str,
    kernel_idx: _ParsedModuleAstIndex,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for base in cls_obj.__mro__:
        m_ast = kernel_idx.cls_methods.get(base.__name__, {}).get(attr)
        if m_ast is not None:
            return m_ast
    raise AssertionError(f"Missing kernel AST for {cls_obj.__name__}.{attr}")


def _dc_field_default_tag(val_node: Optional[ast.expr]) -> Optional[str]:
    if val_node is None:
        return None
    return _norm_dflt_ast(_strip_ann_quotes(val_node))


@dataclass(frozen=True, slots=True)
class _DcFieldSig:
    name: str
    ann: str
    default_tag: Optional[str]


def _extract_dc_field_sigs(
    cls_node: ast.ClassDef,
    alias_map: Mapping[str, str],
) -> list[_DcFieldSig]:
    out: list[_DcFieldSig] = []
    for ch in cls_node.body:
        if isinstance(ch, ast.AnnAssign) and isinstance(ch.target, ast.Name) and not ch.target.id.startswith("_"):
            out.append(_DcFieldSig(ch.target.id, _norm_ann_ast(ch.annotation, alias_map), _dc_field_default_tag(ch.value)))
    return out


def _assert_dc_fields_parity(
    label: str,
    spec_cls: ast.ClassDef,
    impl_cls: ast.ClassDef,
    alias_map: Mapping[str, str],
) -> None:
    s_dc = _extract_dc_field_sigs(spec_cls, alias_map)
    i_dc = _extract_dc_field_sigs(impl_cls, alias_map)
    if not s_dc:
        return
    check(len(s_dc) == len(i_dc), lambda: f"Dataclass field count drift on {label}: {s_dc} vs {i_dc}")
    for sf, imf in zip(s_dc, i_dc):
        check((sf.name, sf.ann) == (imf.name, imf.ann), lambda: f"Dataclass field type drift on {label}.{sf.name}: spec={sf.ann} vs impl={imf.ann}")
        if sf.default_tag not in {"<has_default>", "<field_factory>"} and imf.default_tag != "<field_factory>":
            check(sf.default_tag == imf.default_tag, lambda: f"Dataclass default drift on {label}.{sf.name}: spec={sf.default_tag} vs impl={imf.default_tag}")
        else:
            check((sf.default_tag is not None) == (imf.default_tag is not None), lambda: f"Dataclass default presence drift on {label}.{sf.name}")


def _extract_spec_dc_flags(spec_cls: ast.ClassDef) -> tuple[bool, bool]:
    for dec in spec_cls.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return (False, False)
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "dataclass":
            kw = {k.arg: bool(ast.literal_eval(k.value)) for k in dec.keywords if k.arg in {"frozen", "slots"}}
            return (kw.get("frozen", False), kw.get("slots", False))
    return (False, False)


def _assert_dc_decorator_flags_parity(label: str, cls_obj: type[object], spec_cls: ast.ClassDef) -> None:
    exp_frozen, exp_slots = _extract_spec_dc_flags(spec_cls)
    dc_params = dict(inspect.getmembers_static(cls_obj)).get("__dataclass_params__")
    rt_frozen = bool(dc_params is not None and dc_params.frozen is True)
    rt_slots = "__slots__" in dict(inspect.getmembers_static(cls_obj))
    check((rt_frozen, rt_slots) == (exp_frozen, exp_slots), lambda: f"Dataclass flags drift on {label}: impl=(frozen={rt_frozen}, slots={rt_slots}) vs spec=({exp_frozen}, {exp_slots})")


def _assert_class_bases_and_abstract_parity(label: str, cls_obj: type[object], spec_cls: ast.ClassDef) -> None:
    s_bases: list[str] = []
    for b in spec_cls.bases:
        nm = b.value.id if isinstance(b, ast.Subscript) and isinstance(b.value, ast.Name) else (b.id if isinstance(b, ast.Name) else "")
        if nm and nm != "Generic":
            s_bases.append(nm)
    rt_bases = [b.__name__ for b in cls_obj.__bases__ if b.__name__ not in {"object", "Generic"}]
    check(s_bases == rt_bases, lambda: f"Base class drift on {label}: spec={s_bases} vs impl={rt_bases}")
    s_abs = {
        ch.name
        for ch in spec_cls.body
        if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            (isinstance(d, ast.Name) and d.id == "abstractmethod")
            or (isinstance(d, ast.Attribute) and d.attr == "abstractmethod")
            for d in ch.decorator_list
        )
    }
    rt_abs = set(dict(inspect.getmembers_static(cls_obj)).get("__abstractmethods__", ()))
    check(s_abs == rt_abs, lambda: f"Abstract methods drift on {label}: spec={sorted(s_abs)} vs impl={sorted(rt_abs)}")


def _assert_spec_constants_parity(fname: str, spec_idx: _ParsedModuleAstIndex, kernel_idx: _ParsedModuleAstIndex, ns_map: Mapping[str, object]) -> None:
    for sym, s_expr in spec_idx.value_exprs.items():
        check(sym in ns_map, lambda: f"Missing constant/alias {fname}:{sym}")
        k_expr = kernel_idx.value_exprs.get(sym)
        check(k_expr is not None, lambda: f"Missing kernel assignment AST for {fname}:{sym}")
        check(_norm_ann_ast(s_expr) == _norm_ann_ast(k_expr), lambda: f"Constant/alias definition drift on {fname}:{sym}: spec={ast.unparse(s_expr)} vs impl={ast.unparse(k_expr)}")


def _assert_class_full_parity(
    label: str,
    cls_obj: type[object],
    spec_cls: ast.ClassDef,
    impl_cls: ast.ClassDef,
    spec_indices: tuple[_ParsedModuleAstIndex, _ParsedModuleAstIndex],
    kernel_idx: _ParsedModuleAstIndex,
) -> None:
    spec_idx, all_specs_idx = spec_indices
    alias_map = {**kernel_idx.aliases, **all_specs_idx.aliases, **spec_idx.aliases}
    if typing.Protocol not in cls_obj.__mro__ and not issubclass(cls_obj, Enum):
        init_priv = [p for p in inspect.signature(cls_obj).parameters if p.startswith("_")]
        check(not init_priv, lambda: f"Spec class {label} leaks private __init__ params: {init_priv}")
        impl_has_init = "__init__" in kernel_idx.cls_methods.get(impl_cls.name, {})
        spec_has_init = "__init__" in spec_idx.cls_methods.get(spec_cls.name, {})
        check(impl_has_init == spec_has_init, lambda: f"__init__ parity drift on {label}: impl={impl_has_init} vs spec={spec_has_init}")
    _assert_class_bases_and_abstract_parity(label, cls_obj, spec_cls)
    if dataclasses.is_dataclass(cls_obj):
        _assert_dc_decorator_flags_parity(label, cls_obj, spec_cls)
    if not issubclass(cls_obj, Enum):
        _assert_dc_fields_parity(label, spec_cls, impl_cls, alias_map)
    if issubclass(cls_obj, Enum):
        s_enum = {
            ch.targets[0].id: ast.literal_eval(ch.value)
            for ch in spec_cls.body
            if isinstance(ch, ast.Assign) and len(ch.targets) == 1 and isinstance(ch.targets[0], ast.Name)
        }
        if s_enum:
            check({nm: m.value for nm, m in cls_obj.__members__.items()} == s_enum, lambda: f"Enum drift on {label}")
    spec_own_m = set(spec_idx.cls_methods.get(spec_cls.name, {}).keys())
    impl_own_m = set(kernel_idx.cls_methods.get(impl_cls.name, {}).keys())
    check(impl_own_m == spec_own_m, lambda: f"Own method/dunder drift on {label}: impl={sorted(impl_own_m)} vs spec={sorted(spec_own_m)}")
    mro_spec_idx = _ParsedModuleAstIndex(
        cls_methods={**all_specs_idx.cls_methods, **spec_idx.cls_methods},
    )
    spec_pub_m = {
        mn
        for base_c in cls_obj.__mro__
        for mn in mro_spec_idx.cls_methods.get(base_c.__name__, {}).keys()
        if _is_public_or_spec_dunder(mn) and mn != "__init__"
    }
    impl_pub_m = {
        mn
        for base_c in cls_obj.__mro__
        for mn in kernel_idx.cls_methods.get(base_c.__name__, {}).keys()
        if _is_public_or_spec_dunder(mn) and mn != "__init__"
    }
    check(impl_pub_m == spec_pub_m, lambda: f"Public method surface drift on {label}: impl={sorted(impl_pub_m)} vs spec={sorted(spec_pub_m)}")
    for pub_m in spec_pub_m:
        s_m_ast = _lookup_mro_method_ast(cls_obj, pub_m, mro_spec_idx)
        i_m_ast = _lookup_mro_method_ast(cls_obj, pub_m, kernel_idx)
        check(
            _method_decorator_tags(s_m_ast) == _method_decorator_tags(i_m_ast),
            lambda: f"Method decorator drift on {label}.{pub_m}: spec={sorted(_method_decorator_tags(s_m_ast))} vs impl={sorted(_method_decorator_tags(i_m_ast))}",
        )
    for m_name, s_ovs in spec_idx.cls_overloads.get(spec_cls.name, {}).items():
        i_ovs = kernel_idx.cls_overloads.get(impl_cls.name, {}).get(m_name, [])
        check(len(s_ovs) == len(i_ovs), lambda: f"Overload count drift on {label}.{m_name}: {len(s_ovs)} vs {len(i_ovs)}")
        for ov_i, (s_ov, i_ov) in enumerate(zip(s_ovs, i_ovs)):
            check(
                _ast_full_param_sig(s_ov, drop_self=True, alias_map=alias_map)
                == _ast_full_param_sig(i_ov, drop_self=True, alias_map=alias_map),
                lambda: f"Overload #{ov_i} param drift on {label}.{m_name}",
            )
            check(_norm_ann_ast(s_ov.returns, alias_map) == _norm_ann_ast(i_ov.returns, alias_map), lambda: f"Overload #{ov_i} return drift on {label}.{m_name}")


def _build_spec_eval_ns(kernel_mods: Sequence[object]) -> dict[str, object]:
    merged: dict[str, object] = {
        "os": os,
        "sys": sys,
        "io": io,
        "threading": threading,
        "subprocess": subprocess,
        "Path": Path,
    }
    for mod in (
        foundation_pkg,
        fs_pkg,
        vfs_pkg,
        storage_pkg,
        space_pkg,
        config_pkg,
        contributes_pkg,
        env_pkg,
        installer_pkg,
        event_pkg,
        lifecycle_pkg,
        rpc_pkg,
        runtime_pkg,
        daemon_pkg,
        sdk_pkg,
        cli_pkg,
        bootstrap_pkg,
        *kernel_mods,
    ):
        merged.update(dict(inspect.getmembers_static(mod)))
    return merged


_DRAFT_SPECS: Final[frozenset[str]] = frozenset({
    "dev/dev.md",
})


def _verify_execution_living_specs_parity() -> None:
    check(_find_spec_fence_violation("```python\nx = 1\n", "sample.md") is not None, "Fence guard must catch unclosed fence")
    check(
        _find_spec_fence_violation("```python\nx = 1\n```\nclass Orphan:\n    pass\n", "sample.md") is not None,
        "Fence guard must catch unfenced top-level class declaration",
    )
    design_root = CORE_V2_ROOT / "sub_module_design"
    root_orphans = sorted(p.name for p in design_root.glob("*.md"))
    check(not root_orphans, lambda: f"Orphan root spec files forbidden in sub_module_design/: {root_orphans}")
    kernel_idx = _build_kernel_ast_index()
    pairs: tuple[tuple[str, object], ...] = (
        ("foundation/foundation.md", foundation_pkg),
        ("filesystem/fs.md", fs_pkg),
        ("filesystem/vfs.md", vfs_pkg),
        ("filesystem/storage.md", storage_pkg),
        ("filesystem/space.md", space_pkg),
        ("metadata/config.md", config_pkg),
        ("metadata/contributes.md", contributes_pkg),
        ("packaging/env.md", env_pkg),
        ("packaging/installer.md", installer_pkg),
        ("execution/event.md", event_pkg),
        ("execution/lifecycle.md", lifecycle_pkg),
        ("execution/rpc.md", rpc_pkg),
        ("execution/runtime.md", runtime_pkg),
        ("execution/daemon.md", daemon_pkg),
        ("surface/sdk.md", sdk_pkg),
        ("surface/cli.md", cli_pkg),
        ("surface/composition_and_bootstrap.md", bootstrap_pkg),
    )
    actual_all_specs = {p.relative_to(design_root).as_posix() for p in design_root.rglob("*.md")}
    expected_all_specs = {rel_p for rel_p, _ in pairs}
    check(
        actual_all_specs == expected_all_specs | _DRAFT_SPECS,
        lambda: f"Orphan or missing living spec files: diff={sorted(actual_all_specs ^ (expected_all_specs | _DRAFT_SPECS))}",
    )
    for draft_rel in _DRAFT_SPECS:
        draft_txt = (design_root / draft_rel).read_text(encoding="utf-8")
        check("Draft" in draft_txt, lambda: f"Draft spec {draft_rel} missing 'Draft' status marker")
    eval_ns = _build_spec_eval_ns([m for _, m in pairs])
    spec_by_file = {fname: _build_spec_ast_index(design_root / fname) for fname, _ in pairs}
    all_specs_idx = _ParsedModuleAstIndex()
    for s_idx in spec_by_file.values():
        all_specs_idx.aliases.update(s_idx.aliases)
        for c_nm, c_ms in s_idx.cls_methods.items():
            all_specs_idx.cls_methods.setdefault(c_nm, {}).update(c_ms)
    for fname, mod in pairs:
        active_txt = (design_root / fname).read_text(encoding="utf-8")
        check("Active" in active_txt, lambda: f"Active living spec {fname} missing 'Active' status marker")
        spec_idx = spec_by_file[fname]
        alias_map = {**kernel_idx.aliases, **all_specs_idx.aliases, **spec_idx.aliases}
        ns_map = dict(inspect.getmembers_static(mod))
        all_tuple = ns_map.get("__all__")
        check(isinstance(all_tuple, tuple))
        if spec_idx.explicit_all is not None:
            check(spec_idx.explicit_all == all_tuple, lambda: f"Spec __all__ drift in {fname}: {spec_idx.explicit_all} vs {all_tuple}")
            reexported = set(spec_idx.explicit_all) - spec_idx.exported_syms
            check(
                spec_idx.exported_syms <= set(spec_idx.explicit_all),
                lambda: f"Extra definitions in {fname}: {sorted(spec_idx.exported_syms - set(spec_idx.explicit_all))}",
            )
            check(
                reexported <= spec_idx.imported_core_syms,
                lambda: f"Missing core import in {fname}: {sorted(reexported - spec_idx.imported_core_syms)}",
            )
            check(
                all(sym in ns_map for sym in reexported),
                lambda: f"Unresolved re-exports in {fname}: {sorted(s for s in reexported if s not in ns_map)}",
            )
        else:
            check(spec_idx.exported_syms == set(all_tuple), lambda: f"Spec drift in {fname}: diff={sorted(spec_idx.exported_syms ^ set(all_tuple))}")
        _assert_spec_constants_parity(fname, spec_idx, kernel_idx, ns_map)
        for fn_name, s_fn in spec_idx.functions.items():
            _assert_fn_ast_and_runtime_parity(
                f"{fname}:{fn_name}", s_fn, kernel_idx.functions[fn_name], ns_map[fn_name], (eval_ns, alias_map), is_method=False
            )
        for cname, m_dict in spec_idx.cls_methods.items():
            cls_obj = ns_map[cname]
            if not isinstance(cls_obj, type):
                continue
            impl_cls = kernel_idx.classes[cls_obj.__name__]
            _assert_class_full_parity(f"{fname}:{cname}", cls_obj, spec_idx.classes[cname], impl_cls, (spec_idx, all_specs_idx), kernel_idx)
            for m_name, s_m in m_dict.items():
                rt_m = _lookup_mro_static_member(cls_obj, m_name)
                i_m = _lookup_mro_method_ast(cls_obj, m_name, kernel_idx)
                _assert_fn_ast_and_runtime_parity(
                    f"{fname}:{cname}.{m_name}", s_m, i_m, rt_m, (eval_ns, alias_map), is_method=True
                )


def _verify_dag_guard_rejects_violations(
    forbidden_by_prefix: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    cases = (
        ("core.execution.runtime.dispatcher", "from core.execution import daemon"),
        ("core.execution.runtime.dispatcher", "from .. import daemon"),
        ("core.execution.runtime.dispatcher", "from core.surface import sdk"),
        ("core.foundation.primitives", "from core.surface.sdk import Module"),
        ("core.surface.sdk.client", "from core.execution.daemon import WorkspaceDaemon"),
        ("core.surface.sdk.client", "from core.packaging.env import ImmutableVenvPool"),
        ("core.surface.sdk.declarative", "from core.filesystem.fs import FileLock"),
        ("core.execution.event.engine", "from core.filesystem.fs import FileLock"),
        ("core.execution.rpc.channel", "from core.foundation.codec import DataclassCodec"),
        ("core.execution.rpc.channel", "from core.filesystem.fs import FileLock"),
        ("core.execution.rpc.channel", "import core.filesystem.fs as fs"),
        ("core.execution.runtime.dispatcher", "import core.execution as ex"),
        ("core.execution.event.engine", "from core import execution"),
        ("core.execution.event.engine", "from core.foundation import CancellationToken"),
        ("core.execution.rpc.channel", "from core.foundation import DataclassCodec"),
        ("core.foundation.proc", "from core.foundation.observability import clamp_wait_sec"),
        ("core.foundation.observability", "from core.foundation.proc import is_process_alive"),
        ("core.foundation.profiler", "from core.filesystem.fs import FileLock"),
        ("core.filesystem.vfs.mount", "from core.filesystem.space import SpaceRegistry"),
        ("core.filesystem.storage.database", "from core.filesystem.space import SpaceScanner"),
        ("core.filesystem.fs.atomic", "from core.filesystem.vfs import ScopedVfs"),
        ("core.metadata.config.matrix", "from core.filesystem.vfs import ScopedVfs"),
        ("core.metadata.config.matrix", "from core.metadata.contributes import MergeStrategy"),
        ("core.metadata.contributes.aggregator", "from core.packaging.env import EnvSpec"),
        ("core.packaging.env.pool", "from core.packaging.installer import MirrorStore"),
        ("core.packaging.installer.engine", "from core.execution.runtime import TaskId"),
        ("core.unknown.mod", "from core.foundation.primitives import HostPath"),
    )
    for mod_name, bad_stmt in cases:
        stmt_node = ast.parse(bad_stmt).body[0]
        caught = False
        try:
            _check_dag_imports(stmt_node, mod_name, forbidden_by_prefix)
        except AssertionError:
            caught = True
        if not caught:
            raise AssertionError(f"DAG guard failed to catch '{bad_stmt}' in {mod_name}")


def _verify_cross_package_public_exports(py_files: Sequence[Path]) -> None:
    core_pkg = CORE_SRC_ROOT / "core"
    facade_pairs = (
        ("core.foundation", foundation_pkg.__all__),
        ("core.filesystem.fs", fs_pkg.__all__),
        ("core.filesystem.vfs", vfs_pkg.__all__),
        ("core.filesystem.storage", storage_pkg.__all__),
        ("core.filesystem.space", space_pkg.__all__),
        ("core.metadata.config", config_pkg.__all__),
        ("core.metadata.contributes", contributes_pkg.__all__),
        ("core.packaging.env", env_pkg.__all__),
        ("core.packaging.installer", installer_pkg.__all__),
        ("core.execution.event", event_pkg.__all__),
        ("core.execution.lifecycle", lifecycle_pkg.__all__),
        ("core.execution.rpc", rpc_pkg.__all__),
        ("core.execution.runtime", runtime_pkg.__all__),
        ("core.execution.daemon", daemon_pkg.__all__),
        ("core.surface.sdk", sdk_pkg.__all__),
        ("core.surface.cli", cli_pkg.__all__),
        ("core.surface.bootstrap", bootstrap_pkg.__all__),
    )
    facades = tuple(name for name, _ in facade_pairs)
    pub_all = {name: set(exports) for name, exports in facade_pairs}
    for py_f in py_files:
        rel_mod = "core." + ".".join(py_f.relative_to(core_pkg).with_suffix("").parts)
        own_fac = next((f for f in facades if rel_mod.startswith(f + ".")), "")
        tree = ast.parse(py_f.read_text(encoding="utf-8"), filename=str(py_f))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                target_fac = next((f for f in facades if node.module == f or node.module.startswith(f + ".")), "")
                if target_fac and target_fac != own_fac:
                    for al in node.names:
                        check(
                            al.name in pub_all[target_fac],
                            f"{rel_mod} imports {node.module}.{al.name} bypassing {target_fac}.__all__",
                        )


def verify_gate0_ast_architecture(include_runner: bool = True) -> None:
    core_pkg = CORE_SRC_ROOT / "core"
    forbidden_by_prefix: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("core.foundation", ("core.filesystem", "core.metadata", "core.packaging", "core.execution", "core.surface")),
        ("core.filesystem", ("core.metadata", "core.packaging", "core.execution", "core.surface")),
        ("core.filesystem.fs", ("core.filesystem.vfs", "core.filesystem.storage", "core.filesystem.space")),
        ("core.filesystem.vfs", ("core.filesystem.storage", "core.filesystem.space")),
        ("core.filesystem.storage", ("core.filesystem.space",)),
        ("core.metadata", ("core.filesystem.vfs", "core.filesystem.storage", "core.filesystem.space", "core.packaging", "core.execution", "core.surface")),
        ("core.metadata.config", ("core.metadata.contributes",)),
        ("core.packaging", ("core.filesystem.storage", "core.filesystem.space", "core.execution", "core.surface")),
        ("core.packaging.env", ("core.metadata.contributes", "core.packaging.installer")),
        ("core.execution.event", ("core.filesystem", "core.foundation.observability", "core.foundation.proc", "core.execution.lifecycle", "core.execution.rpc", "core.execution.runtime", "core.execution.daemon", "core.surface")),
        ("core.execution.rpc", ("core.foundation.codec", "core.execution.event", "core.execution.lifecycle", "core.execution.runtime", "core.execution.daemon", "core.surface")),
        ("core.execution.lifecycle", ("core.execution.rpc", "core.execution.runtime", "core.execution.daemon", "core.surface")),
        ("core.execution.runtime", ("core.execution.daemon", "core.packaging", "core.surface")),
        ("core.execution.daemon", ("core.metadata", "core.packaging", "core.execution.event", "core.surface", "core.execution.runtime.contracts", "core.execution.runtime.coordinator", "core.execution.runtime.dispatcher", "core.execution.runtime.gates", "core.execution.runtime.module_slot", "core.execution.runtime.route_index", "core.execution.runtime.services", "core.execution.runtime.step_host", "core.execution.runtime.turn_session", "core.execution.runtime.wire", "core.execution.runtime.worker_entry", "core.execution.runtime.worker_pool")),
        ("core.surface.sdk", ("core.execution.daemon", "core.packaging", "core.filesystem.fs", "core.surface.cli", "core.surface.bootstrap")),
        ("core.surface.cli", ("core.execution.daemon", "core.surface.bootstrap")),
    )
    py_files = sorted(core_pkg.rglob("*.py"))
    check(len(py_files) >= 27)
    walked_mod_names = [mod_name for _, mod_name, _ in pkgutil.walk_packages(core.__path__, core.__name__ + ".")]
    for py_f in py_files:
        rel_posix = py_f.relative_to(CORE_SRC_ROOT).as_posix()
        rel_mod = "core." + ".".join(py_f.relative_to(core_pkg).with_suffix("").parts)
        _audit_single_kernel_ast(py_f, rel_posix, rel_mod, forbidden_by_prefix)

    for mod_name in walked_mod_names:
        _verify_module_runtime_type_hints(mod_name)
    _verify_cross_package_public_exports(py_files)
    _verify_dag_guard_rejects_violations(forbidden_by_prefix)
    _verify_execution_living_specs_parity()
    audit_self_test_ast(include_runner=include_runner)


__all__ = (
    "audit_self_test_ast",
    "verify_gate0_ast_architecture",
)


if __name__ == "__main__":
    verify_gate0_ast_architecture(include_runner=False)
