"""
Semantic Bundler & Partial Class Aggregator for `module:ast`.
Provides two-tier C# `partial class/struct/interface` member isolation (`_own_members` vs aggregated `members`)
and deterministic overload ID disambiguation.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import copy
import dataclasses
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from core.context import get_env, get_runtime_context, get_virtual_cwd
from core.log import log_debug, log_warn
from core.space import (
    ScanDiffDetail,
    SpaceConfig,
    SpaceFileEntry,
    SpaceRegistry,
    SpaceScanner,
    get_default_scanner,
)
from core.vfs import write_bytes

from .exceptions import ASTError
from .io_utils import compute_project_relpath, is_dirty_file_match, normalize_dirty_paths
from .parsers.base import is_partial_declaration
from .parsers.registry import ParserRegistry
from .schema import FileSymbolGraph, MemberInfo, SemanticBundle, SymbolCallSite, SymbolNode, UnifiedSymbol

PARALLEL_BUNDLE_THRESHOLD = 10


def _get_worker_registry_state() -> Optional[ParserRegistry]:
    return get_runtime_context().get_module_state("ast.bundler.worker_registry", lambda: None)


def _set_worker_registry_state(val: Optional[ParserRegistry]) -> None:
    get_runtime_context().set_module_state("ast.bundler.worker_registry", val)


def reset_worker_registry() -> None:
    """Reset the worker-process `ParserRegistry` cache in the current runtime context."""
    _set_worker_registry_state(None)


def _safe_resolve_path(p: Union[str, Path]) -> Path:
    p_obj = Path(p)
    try:
        return p_obj.resolve()
    except OSError:
        return p_obj


def _safe_resolve_str(p: Union[str, Path]) -> str:
    p_obj = Path(p)
    try:
        return str(p_obj.resolve()).replace("\\", "/")
    except OSError:
        return str(p_obj).replace("\\", "/")


def _safe_exists(p: Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def _safe_is_file(p: Path) -> bool:
    try:
        return p.is_file()
    except OSError:
        return False


def _safe_mtime_ns(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def ensure_unique_overload_ids(
    symbols: List[UnifiedSymbol],
    default_space: str = "project",
) -> List[UnifiedSymbol]:
    """
    Ensure that same-file method overloads (symbols sharing `(file_path, scope_path_or_parent_scope, name, kind)`)
    always receive distinct `UnifiedSymbol.id` values by passing `(line_number, signature)` to `compute_id`,
    and synchronize `parent_id` on any same-file child symbols whose parent ID was remapped.
    """
    if not symbols:
        return symbols

    groups: Dict[Tuple[str, str, str, str], List[int]] = defaultdict(list)
    for idx, sym in enumerate(symbols):
        scope_key = sym.scope_path or str((sym.metadata or {}).get("parent_scope") or "")
        short_name = (sym.metadata or {}).get("short_name") or sym.name
        groups[(sym.file_path, str(scope_key), str(short_name), str(sym.kind))].append(idx)

    updated = list(symbols)
    seen_ids: Set[str] = set()
    id_remap: Dict[Tuple[str, str], str] = {}

    for (_, _, _, _), indices in groups.items():
        if len(indices) > 1:
            group_ids = {updated[i].id for i in indices}
            if len(group_ids) == len(indices):
                continue
            for overload_pos, i in enumerate(indices):
                sym = updated[i]
                sp = sym.spaces[0] if sym.spaces else default_space
                sig_hint = (sym.signature or "").strip() or f"overload_{overload_pos}_{sym.line_number}"
                new_id = UnifiedSymbol.compute_id(
                    space=sp,
                    file_path=sym.file_path,
                    name=sym.fqn or sym.name,
                    kind=sym.kind,
                    line_number=sym.line_number,
                    signature_hint=sig_hint,
                )
                if new_id != sym.id:
                    id_remap[(sym.file_path, sym.id)] = new_id
                    updated[i] = dataclasses.replace(
                        sym,
                        id=new_id,
                        children=tuple(sym.children),
                        members=tuple(sym.members),
                        metadata=dict(sym.metadata),
                    )

    for idx, sym in enumerate(updated):
        if sym.id in seen_ids:
            sp = sym.spaces[0] if sym.spaces else default_space
            sig_hint = f"{sym.signature or ''}:{sym.line_number}:{idx}"
            new_id = UnifiedSymbol.compute_id(
                space=sp,
                file_path=sym.file_path,
                name=sym.fqn or sym.name,
                kind=sym.kind,
                line_number=sym.line_number,
                signature_hint=sig_hint,
            )
            orig_id = symbols[idx].id
            id_remap[(sym.file_path, orig_id)] = new_id
            id_remap[(sym.file_path, sym.id)] = new_id
            updated[idx] = dataclasses.replace(
                sym,
                id=new_id,
                children=tuple(sym.children),
                members=tuple(sym.members),
                metadata=dict(sym.metadata),
            )
        seen_ids.add(updated[idx].id)

    if id_remap:
        for idx, sym in enumerate(updated):
            if sym.parent_id and (sym.file_path, sym.parent_id) in id_remap:
                new_parent_id = id_remap[(sym.file_path, sym.parent_id)]
                if new_parent_id != sym.parent_id:
                    updated[idx] = dataclasses.replace(
                        sym,
                        parent_id=new_parent_id,
                        children=tuple(sym.children),
                        members=tuple(sym.members),
                        metadata=dict(sym.metadata),
                    )

    return updated


def project_file_artifacts_from_graph(
    fg: FileSymbolGraph,
    default_space: str = "unified",
    spaces: Optional[List[str]] = None,
) -> Tuple[List[UnifiedSymbol], List[SymbolCallSite], Dict[str, str]]:
    """
    Project legacy `UnifiedSymbol`, `SymbolCallSite`, and `imports` directly from a single-pass
    `FileSymbolGraph` without re-running parser extraction.
    """
    sorted_spaces = list(spaces) if spaces else ([default_space] if default_space else ["unified"])
    primary_space = sorted_spaces[0]
    norm_path = fg.file_path.replace("\\", "/")
    type_container_kinds = ("class", "struct", "interface", "enum", "namespace", "module")
    callable_kinds = ("constructor", "method", "function")
    field_like_kinds = ("property", "field", "variable", "constant")
    priority_order = (*type_container_kinds, *callable_kinds, *field_like_kinds)

    def _primary_kind(kinds: Iterable[str]) -> str:
        k_set = set(kinds)
        for pk in priority_order:
            if pk in k_set:
                return pk
        return sorted(k_set)[0] if k_set else "variable"

    symbols: List[UnifiedSymbol] = []
    node_id_to_sym: Dict[str, UnifiedSymbol] = {}

    def _walk_node(node: SymbolNode, parent_sym_id: Optional[str]) -> None:
        p_kind = _primary_kind(node.kinds)
        if p_kind == "field" and parent_sym_id is not None:
            return

        sep = str(node.facets.get("scope_separator") or ".")
        fqn_str = node.fqn
        short_name_val = node.name
        parent_scope_val = node.scope_path[-1] if node.scope_path else ""
        sig_str = str(node.facets.get("signature") or "")
        doc_str = str(node.facets.get("docstring") or "")
        ret_str = str(node.facets.get("return_type") or "")
        vis_str = str(node.facets.get("visibility") or "public")
        is_st = bool(node.facets.get("is_static", False))

        members_list: List[MemberInfo] = []
        for ch in node.children:
            ch_kind = _primary_kind(ch.kinds)
            members_list.append(
                MemberInfo(
                    name=ch.name,
                    kind=ch_kind,
                    signature=str(ch.facets.get("signature") or ""),
                    docstring=str(ch.facets.get("docstring") or ""),
                    visibility=str(ch.facets.get("visibility") or "public"),
                    line_number=ch.span.start_line,
                    is_static=bool(ch.facets.get("is_static", False)),
                )
            )

        sym_id = UnifiedSymbol.compute_id(
            space=primary_space,
            file_path=norm_path,
            name=fqn_str,
            kind=p_kind,
            line_number=node.span.start_line,
        )
        sym_name = fqn_str if parent_sym_id is not None else short_name_val
        search_payload = f"{fqn_str} {short_name_val} {doc_str} {sig_str}".strip()

        meta: Dict[str, Any] = {
            "short_name": short_name_val,
            "parent_scope": parent_scope_val,
            "end_line": node.span.end_line,
            "scope_path": list(node.scope_path),
            "start_byte": node.span.start_byte,
            "end_byte": node.span.end_byte,
            "spaces": list(sorted_spaces),
        }
        if node.facets.get("base_types"):
            meta["base_types"] = list(node.facets["base_types"])
        if is_partial_declaration(node.kinds, sig_str, node.facets):
            meta["is_partial"] = True
        if is_st:
            meta["is_static"] = True
        if node.facets.get("field_types"):
            meta["field_types"] = dict(node.facets["field_types"])
        if node.facets.get("fallback"):
            meta["fallback"] = True

        sym_obj = UnifiedSymbol(
            id=sym_id,
            name=sym_name,
            kind=p_kind,
            file_path=norm_path,
            line_number=node.span.start_line,
            end_line=node.span.end_line,
            language=node.language or fg.language,
            docstring=doc_str,
            signature=sig_str,
            fqn=fqn_str,
            scope_path=sep.join(node.scope_path),
            parent_id=parent_sym_id,
            children=tuple(members_list),
            parameters=(),
            return_type=ret_str,
            search_payload=search_payload,
            visibility=vis_str,
            members=tuple(members_list),
            metadata=meta,
        )
        symbols.append(sym_obj)
        node_id_to_sym[node.id] = sym_obj
        for ch in node.children:
            _walk_node(ch, sym_id)

    for rnode in fg.root_nodes:
        _walk_node(rnode, None)

    symbols = ensure_unique_overload_ids(symbols, default_space=primary_space)
    for s in symbols:
        s.metadata["spaces"] = list(sorted_spaces)

    # Remap node_id_to_sym after ensure_unique_overload_ids
    by_line_and_fqn: Dict[Tuple[int, str], UnifiedSymbol] = {
        (s.line_number, s.fqn or s.name): s for s in symbols
    }
    for nid, n_obj in fg.all_nodes_by_id.items():
        if (n_obj.span.start_line, n_obj.fqn) in by_line_and_fqn:
            node_id_to_sym[nid] = by_line_and_fqn[(n_obj.span.start_line, n_obj.fqn)]

    call_sites: List[SymbolCallSite] = []
    imports_dict: Dict[str, str] = {}
    for edge in fg.outgoing_edges:
        if edge.edge_kind == "imports":
            expr = edge.target_expr.strip()
            if not expr:
                continue
            if expr.startswith("export*="):
                target_str = expr.split("=", 1)[1].strip()
                imports_dict[f"export*:{target_str}"] = target_str
            elif expr.startswith("*="):
                target_str = expr.split("=", 1)[1].strip()
                imports_dict[f"*:{target_str}"] = target_str
            elif "=" in expr:
                alias_s, target_s = (p.strip() for p in expr.split("=", 1))
                imports_dict[alias_s] = target_s
            else:
                imports_dict[expr] = expr
        elif edge.edge_kind == "calls":
            expr = edge.target_expr.strip()
            if not expr:
                continue
            prefix, callee_name = (expr.rsplit(".", 1) if "." in expr else ("", expr))
            caller_sym = node_id_to_sym.get(edge.source_id)
            caller_id = caller_sym.id if caller_sym is not None else ""
            caller_name = "<module>"
            if caller_sym is not None:
                if caller_sym.kind in ("method", "function", "constructor", "property"):
                    if caller_sym.metadata.get("parent_scope"):
                        caller_name = f"{caller_sym.metadata['parent_scope']}.{caller_sym.metadata.get('short_name', caller_sym.name)}"
                    else:
                        caller_name = caller_sym.name
                else:
                    caller_name = caller_sym.metadata.get("short_name") or caller_sym.name
            call_sites.append(
                SymbolCallSite(
                    callee_name=callee_name,
                    line_number=edge.span.start_line,
                    caller_symbol_id=caller_id,
                    caller_member_name=caller_name,
                    context_prefix=prefix,
                    file_path=norm_path,
                    space=primary_space,
                )
            )

    return symbols, call_sites, imports_dict


def _clone_member_item(m: Any) -> Any:
    if isinstance(m, MemberInfo):
        return MemberInfo.from_dict(m.to_dict())
    if isinstance(m, dict):
        return MemberInfo.from_dict(m)
    return copy.deepcopy(m)


def _extract_unaggregated_partial_state(
    sym: UnifiedSymbol,
) -> Tuple[List[Any], List[str], Dict[str, str], str]:
    """
    Extract or restore a partial symbol's single-file unaggregated attributes:
    `(own_members, own_base_types, own_field_types, own_docstring)`.
    """
    meta = sym.metadata or {}
    if "_own_members" in meta:
        raw_own = meta["_own_members"]
        own_members = [_clone_member_item(m) for m in raw_own]
    else:
        own_members = [_clone_member_item(m) for m in sym.members]

    own_bases = [str(b) for b in meta.get("_own_base_types", meta.get("base_types", []))]
    own_fields = {
        str(k): str(v)
        for k, v in dict(meta.get("_own_field_types", meta.get("field_types", {}))).items()
    }
    own_doc = str(meta.get("_own_docstring", sym.docstring or ""))
    return own_members, own_bases, own_fields, own_doc


def restore_unaggregated_partial_symbol(sym: UnifiedSymbol) -> UnifiedSymbol:
    """
    Restore an already-aggregated C# `partial` symbol back to its single-file baseline state
    for incremental re-aggregation or single-file degeneration without mutating the input symbol.
    """
    if "_own_members" not in (sym.metadata or {}):
        cloned_members = tuple(_clone_member_item(m) for m in sym.members)
        cloned_children = tuple(_clone_member_item(c) for c in sym.children)
        return dataclasses.replace(
            sym,
            children=cloned_children,
            members=cloned_members,
            metadata=copy.deepcopy(dict(sym.metadata or {})),
        )
    own_members, own_bases, own_fields, own_doc = _extract_unaggregated_partial_state(sym)
    new_meta = copy.deepcopy(dict(sym.metadata))
    for k in (
        "_own_members",
        "_own_base_types",
        "_own_field_types",
        "_own_docstring",
        "partial_files",
        "partial_locations",
        "partial_siblings",
        "is_primary_partial",
    ):
        new_meta.pop(k, None)
    if own_bases:
        new_meta["base_types"] = list(own_bases)
    else:
        new_meta.pop("base_types", None)
    if own_fields:
        new_meta["field_types"] = dict(own_fields)
    else:
        new_meta.pop("field_types", None)
    search_payload = f"{sym.fqn} {new_meta.get('short_name', sym.name)} {own_doc} {sym.signature}".strip()
    return dataclasses.replace(
        sym,
        docstring=own_doc,
        children=tuple(own_members),
        search_payload=search_payload,
        members=tuple(own_members),
        metadata=new_meta,
    )


def _is_partial_symbol(sym: UnifiedSymbol) -> bool:
    """Check whether `sym` is a C# `partial class/struct/interface`."""
    return is_partial_declaration(sym.kind, sym.signature or "", sym.metadata)


def aggregate_partial_symbols(symbols: List[UnifiedSymbol]) -> List[UnifiedSymbol]:
    """
    Aggregate C# `partial class / struct / interface` symbols sharing the same `(spaces, kind, fqn)`.
    Preserves each file's physical declarations in `metadata["_own_members"]` while merging
    cross-file `members`/`children`, `base_types`, `field_types`, `partial_files`, `partial_locations`,
    and `partial_siblings`.
    """
    if not symbols:
        return symbols

    groups: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
    for idx, sym in enumerate(symbols):
        if (sym.language in ("c_sharp", "csharp") or _is_partial_symbol(sym)) and sym.kind in (
            "class",
            "struct",
            "interface",
        ):
            sp_key = ",".join(sorted(sym.spaces)) if sym.spaces else ""
            fqn_key = sym.fqn or sym.name
            groups[(sp_key, sym.kind, fqn_key)].append(idx)

    updated = list(symbols)
    for _, indices in groups.items():
        if len(indices) <= 1:
            if len(indices) == 1:
                only_sym = symbols[indices[0]]
                if "_own_members" in only_sym.metadata:
                    only_sym = restore_unaggregated_partial_symbol(only_sym)
                if _is_partial_symbol(only_sym):
                    own_m, own_b, own_f, own_d = _extract_unaggregated_partial_state(only_sym)
                    new_meta = dict(only_sym.metadata)
                    new_meta["is_partial"] = True
                    new_meta["_own_members"] = list(own_m)
                    new_meta["_own_base_types"] = list(own_b)
                    new_meta["_own_field_types"] = dict(own_f)
                    new_meta["_own_docstring"] = own_d
                    new_meta["partial_files"] = [only_sym.file_path]
                    new_meta["partial_locations"] = [
                        {
                            "file_path": only_sym.file_path,
                            "line_number": only_sym.line_number,
                            "end_line": only_sym.end_line,
                            "member_count": len(own_m),
                        }
                    ]
                    new_meta["partial_siblings"] = []
                    updated[indices[0]] = dataclasses.replace(
                        only_sym,
                        children=tuple(only_sym.children),
                        members=tuple(only_sym.members),
                        metadata=new_meta,
                    )
                else:
                    updated[indices[0]] = only_sym
            continue

        group_syms = [symbols[i] for i in indices]
        if not any(_is_partial_symbol(s) for s in group_syms):
            continue

        merged_members: List[Any] = []
        seen_members = set()
        merged_bases: List[str] = []
        merged_fields: Dict[str, str] = {}
        partial_files: List[str] = []
        partial_locations: List[Dict[str, Any]] = []
        merged_docs: List[str] = []
        own_states = []

        for s in group_syms:
            own_m, own_b, own_f, own_d = _extract_unaggregated_partial_state(s)
            own_states.append((own_m, own_b, own_f, own_d))
            if s.file_path not in partial_files:
                partial_files.append(s.file_path)
            partial_locations.append(
                {
                    "file_path": s.file_path,
                    "line_number": s.line_number,
                    "end_line": s.end_line,
                    "member_count": len(own_m),
                }
            )
            if own_d and own_d not in merged_docs:
                merged_docs.append(own_d)
            for m in own_m:
                m_name = m.name if hasattr(m, "name") else str(m)
                m_kind = m.kind if hasattr(m, "kind") else ""
                m_sig = m.signature if hasattr(m, "signature") else ""
                m_key = (m_name, m_kind, m_sig)
                if m_key not in seen_members:
                    seen_members.add(m_key)
                    merged_members.append(m)
            for bt in own_b:
                if bt and bt not in merged_bases:
                    merged_bases.append(str(bt))
            for fn, ft in own_f.items():
                if fn and ft:
                    merged_fields[fn] = str(ft)

        combined_doc = "\n".join(merged_docs).strip()
        primary_pos = next((pos for pos, (_, ob, _, _) in enumerate(own_states) if ob), 0)

        for pos, i in enumerate(indices):
            orig = symbols[i]
            own_m, own_b, own_f, own_d = own_states[pos]
            new_meta = dict(orig.metadata)
            new_meta["is_partial"] = True
            new_meta["is_primary_partial"] = pos == primary_pos
            new_meta["partial_files"] = list(partial_files)
            new_meta["partial_locations"] = [dict(loc) for loc in partial_locations]
            new_meta["partial_siblings"] = [
                dict(loc)
                for loc in partial_locations
                if not (loc["file_path"] == orig.file_path and loc["line_number"] == orig.line_number)
            ]
            new_meta["_own_members"] = list(own_m)
            new_meta["_own_base_types"] = list(own_b)
            new_meta["_own_field_types"] = dict(own_f)
            new_meta["_own_docstring"] = own_d
            if merged_bases:
                new_meta["base_types"] = list(merged_bases)
            elif "base_types" in new_meta:
                del new_meta["base_types"]
            if merged_fields:
                new_meta["field_types"] = dict(merged_fields)
            elif "field_types" in new_meta:
                del new_meta["field_types"]
            doc_to_use = own_d or combined_doc
            search_payload = f"{orig.fqn} {new_meta.get('short_name', orig.name)} {doc_to_use} {orig.signature}".strip()
            updated[i] = dataclasses.replace(
                orig,
                docstring=doc_to_use,
                children=tuple(merged_members),
                search_payload=search_payload,
                members=tuple(merged_members),
                metadata=new_meta,
            )

    return updated


def _init_bundle_worker(parent_sys_path: List[str]) -> None:
    """Ensure child processes spawned on Windows/macOS inherit dynamic module paths."""
    from core.platform import init_subprocess_sys_path

    init_subprocess_sys_path(parent_sys_path)


def _get_worker_registry() -> ParserRegistry:
    """Get or initialize worker-process singleton `ParserRegistry`."""
    reg = _get_worker_registry_state()
    if reg is None:
        reg = ParserRegistry(register_defaults=True)
        _set_worker_registry_state(reg)
    return reg


def _parse_file_task_worker(
    task: Tuple[str, str, str, List[str]],
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Top-level picklable worker function for `ProcessPoolExecutor` or serial execution.
    task: `(c_key, f_path_str, relpath, sorted_spaces)`
    return: `(c_key, [symbol.to_dict(), ...], [call_site.to_dict(), ...], imports_dict, file_graph_dict, error_message_or_None)`
    """
    c_key, f_path_str, relpath, sorted_spaces = task
    primary_space = sorted_spaces[0] if sorted_spaces else "unified"
    try:
        registry = _get_worker_registry()
        with open(f_path_str, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        fg = registry.extract_file_graph(file_path=relpath, content=content, space=primary_space)
        symbols, call_sites, imports = project_file_artifacts_from_graph(
            fg, default_space=primary_space, spaces=sorted_spaces
        )
        results = [sym.to_dict() for sym in symbols]
        site_dicts = [s.to_dict() for s in call_sites]
        return (c_key, results, site_dicts, dict(imports or {}), fg.to_dict(), None)
    except Exception as exc:
        return (c_key, [], [], {}, None, str(exc))


def _resolve_default_ast_storage_dir(project_root: Optional[Path] = None) -> Path:
    """Resolve `ast.storage://` -> `storage.local://ast/`."""
    from core import uri

    for scheme in ("ast.storage://", "storage.local://ast"):
        try:
            res = uri.resolve(scheme, interactive=False)
            if res and not str(res).startswith("!undefined"):
                return _safe_resolve_path(str(res))
        except Exception:
            pass
    try:
        yscb_root = uri.resolve_yscb_root()
        if yscb_root:
            return _safe_resolve_path(yscb_root) / ".storage.local" / "ast"
    except Exception:
        pass
    base = _safe_resolve_path(project_root) if project_root else _safe_resolve_path(get_virtual_cwd())
    return base / ".storage.local" / "ast"


def _space_logical_name(sp: SpaceConfig) -> str:
    """Return canonical logical space label (`short_name` if available, else `qualified_name`)."""
    return sp.short_name or sp.qualified_name


def _get_loaded_spaces(space_manager: Optional[SpaceRegistry]) -> Dict[str, SpaceConfig]:
    if space_manager is None:
        return {}
    mapping: Dict[str, SpaceConfig] = {}
    for sp in space_manager.list_spaces():
        if sp.qualified_name:
            mapping[sp.qualified_name] = sp
        if sp.short_name and sp.short_name not in mapping:
            mapping[sp.short_name] = sp
    return mapping


def _resolve_space_entry_roots(
    sp: SpaceConfig,
    space_manager: Optional[SpaceRegistry] = None,
) -> List[Path]:
    proj_root = getattr(space_manager, "project_root", None) if space_manager else None
    roots: List[Path] = []
    for _, abs_p, exists in sp.resolve_entries(proj_root):
        if abs_p is not None and exists:
            roots.append(_safe_resolve_path(abs_p))
        elif abs_p is not None:
            roots.append(_safe_resolve_path(abs_p))
    return roots


def _preload_snap_entries(
    scanner: Optional[SpaceScanner],
    target_spaces: Iterable[SpaceConfig],
) -> Dict[str, Dict[str, Any]]:
    snap_entries_by_space: Dict[str, Dict[str, Any]] = {}
    if scanner is not None and hasattr(scanner, "snapshot"):
        for sp in target_spaces:
            sp_key = _space_logical_name(sp)
            try:
                entries = scanner.snapshot(sp.qualified_name or sp_key, refresh_first=False)
                if entries:
                    snap_entries_by_space[sp_key] = entries
                    if sp.qualified_name:
                        snap_entries_by_space[sp.qualified_name] = entries
            except Exception:
                pass
    return snap_entries_by_space


def _normalize_space_dirty_paths(
    raw_paths: Iterable[str],
    target_spaces: List[SpaceConfig],
    space_manager: Optional[SpaceRegistry] = None,
    scanner: Optional[SpaceScanner] = None,
    file_symbols_cache: Optional[Dict[str, List[UnifiedSymbol]]] = None,
    prefer_missing: bool = False,
    snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    known_indexed_files: Optional[Set[str]] = None,
) -> Set[str]:
    """
    Normalize space-relative or absolute dirty paths into `project://`-relative and canonical absolute paths.
    """
    expanded: Set[str] = set()
    raw_list = [str(p).replace("\\", "/").strip("/") for p in raw_paths if p]
    if not raw_list:
        return expanded

    if snap_entries_by_space is None:
        snap_entries_by_space = _preload_snap_entries(scanner, target_spaces)

    proj_root = getattr(space_manager, "project_root", None) if space_manager else None
    known_norm = normalize_dirty_paths(known_indexed_files) if known_indexed_files else set()

    for raw_p in raw_list:
        p_obj = Path(raw_p)
        if p_obj.is_absolute():
            expanded.add(raw_p)
            try:
                c_abs = _safe_resolve_str(p_obj)
                expanded.add(c_abs)
                expanded.add(compute_project_relpath(p_obj, p_obj.parent, project_root=proj_root))
            except Exception:
                pass
            continue

        matched_from_snap = False
        snap_matches: List[Any] = []
        for sp in target_spaces:
            sp_key = _space_logical_name(sp)
            entries = snap_entries_by_space.get(sp_key) or snap_entries_by_space.get(sp.qualified_name, {})
            fp_rec = entries.get(raw_p)
            if fp_rec is not None and getattr(fp_rec, "entry_path", ""):
                snap_matches.append(fp_rec)

        if snap_matches:
            deleted_matches = [fp for fp in snap_matches if getattr(fp, "is_deleted", False)]
            if prefer_missing and deleted_matches:
                chosen_matches = deleted_matches
            elif not prefer_missing:
                active_matches = [fp for fp in snap_matches if not getattr(fp, "is_deleted", False)]
                pool = active_matches or snap_matches
                best_mtime_ns = max((int(getattr(fp, "mtime_ns", 0)) for fp in pool), default=0)
                chosen_matches = [fp for fp in pool if int(getattr(fp, "mtime_ns", 0)) >= best_mtime_ns]
            else:
                chosen_matches = deleted_matches or snap_matches
            for fp_rec in chosen_matches:
                src_root = Path(fp_rec.entry_path)
                cand_abs = src_root / raw_p
                c_abs = _safe_resolve_str(cand_abs)
                expanded.add(c_abs)
                expanded.add(compute_project_relpath(cand_abs, src_root, project_root=proj_root))
                matched_from_snap = True

        if matched_from_snap:
            continue

        matching_candidates: List[Tuple[Path, Path]] = []
        for sp in target_spaces:
            inc_roots = _resolve_space_entry_roots(sp, space_manager)
            for inc_root in inc_roots:
                cand_abs = Path(inc_root) / raw_p
                matching_candidates.append((cand_abs, Path(inc_root)))
            if proj_root is not None:
                cand_proj = Path(proj_root) / raw_p
                if _safe_exists(cand_proj):
                    matching_candidates.append((cand_proj, Path(proj_root)))

        existing_cands = [(c, r) for c, r in matching_candidates if _safe_exists(c)]
        missing_cands = [(c, r) for c, r in matching_candidates if not _safe_exists(c)]
        cache_ref = file_symbols_cache or {}
        if prefer_missing and missing_cands:
            if len(missing_cands) == 1:
                cands_to_use = missing_cands
            else:
                cached_missing = [
                    (c, r)
                    for c, r in missing_cands
                    if _safe_resolve_str(c) in cache_ref
                    or compute_project_relpath(c, r, project_root=proj_root) in cache_ref
                    or (
                        known_norm
                        and (
                            is_dirty_file_match(_safe_resolve_str(c), known_norm)
                            or is_dirty_file_match(compute_project_relpath(c, r, project_root=proj_root), known_norm)
                        )
                    )
                ]
                cands_to_use = cached_missing or missing_cands
        else:
            if len(existing_cands) > 1:
                max_mtime = max((_safe_mtime_ns(c) for c, _ in existing_cands), default=0)
                existing_cands = [(c, r) for c, r in existing_cands if _safe_mtime_ns(c) >= max_mtime]
            cands_to_use = (
                existing_cands
                if len(existing_cands) >= 1
                else (matching_candidates if len(matching_candidates) == 1 or "/" in raw_p else existing_cands)
            )
        if cands_to_use:
            for cand_abs, inc_root in cands_to_use:
                c_abs = _safe_resolve_str(cand_abs)
                expanded.add(c_abs)
                expanded.add(compute_project_relpath(cand_abs, inc_root, project_root=proj_root))
        else:
            expanded.add(raw_p)

    return expanded


class SemanticBundler:
    """Workspace semantic bundler and incremental dirty-file parser for `module:ast`."""

    def __init__(
        self,
        space_manager: SpaceRegistry,
        parser_registry: Optional[ParserRegistry] = None,
        scanner: Optional[SpaceScanner] = None,
        storage_dir: Optional[Union[str, Path]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
    ):
        self.space_manager = space_manager
        self.parser_registry = parser_registry or ParserRegistry(
            register_defaults=True,
            space_manager=space_manager,
        )
        if getattr(self.parser_registry, "_space_manager", None) is None:
            self.parser_registry._space_manager = space_manager
        self._contributes_data = contributes_data
        self._registered_spaces: List[str] = []
        self._target_spaces_initialized: bool = False
        if scanner is not None:
            self.scanner = scanner
        elif getattr(space_manager, "_raw_spaces", None) is None:
            self.scanner = get_default_scanner(
                project_root=getattr(space_manager, "project_root", None),
                yscb_dir=getattr(space_manager, "yscb_dir", None),
            )
        else:
            self.scanner = SpaceScanner(registry=space_manager)
        if storage_dir is not None:
            self.storage_dir = _safe_resolve_path(storage_dir)
        else:
            proj_root = getattr(self.space_manager, "project_root", None)
            self.storage_dir = _resolve_default_ast_storage_dir(proj_root)
        self._file_symbols_cache: Dict[str, List[UnifiedSymbol]] = {}
        self._file_call_sites_cache: Dict[str, List[SymbolCallSite]] = {}
        self._file_imports_cache: Dict[str, Dict[str, str]] = {}
        self._file_graphs_cache: Dict[str, FileSymbolGraph] = {}
        self._last_bundle_unique_files: Dict[str, Tuple[Path, str, Set[str]]] = {}
        self._last_bundle_spaces: Set[str] = set()

    @property
    def registry(self) -> ParserRegistry:
        """Compatibility alias for `parser_registry`."""
        return self.parser_registry

    def register_spaces(self, spaces: Iterable[Union[str, SpaceConfig]]) -> List[str]:
        """
        SDK / Hook injection entry point to register one or more target `core.space` names
        into `ASTEngine` / `SemanticBundler`.
        """
        for sp in spaces:
            name = (sp.qualified_name or sp.short_name) if isinstance(sp, SpaceConfig) else str(sp).strip()
            if name and not name.startswith("_") and name not in self._registered_spaces:
                self._registered_spaces.append(name)
        return list(self._registered_spaces)

    def _ensure_declared_spaces_loaded(self) -> None:
        """
        Load declarative target spaces from:
        1. `self._contributes_data` (if explicitly injected)
        2. `core.contributes.get("ast")` + `config://ast/contribute.json`
        3. `on_register_ast_spaces` hook broadcast (allowing downstream modules to inject spaces)
        """
        if self._target_spaces_initialized:
            return
        self._target_spaces_initialized = True

        def _extract_from_ast_dict(raw_dict: Any) -> None:
            if not isinstance(raw_dict, dict):
                return
            raw_sp = raw_dict.get("spaces")
            if isinstance(raw_sp, (list, tuple, set)):
                self.register_spaces(str(s) for s in raw_sp if str(s).strip())
            elif isinstance(raw_sp, dict):
                self.register_spaces(str(k) for k in raw_sp.keys() if not str(k).startswith("_"))

        if self._contributes_data is not None:
            _extract_from_ast_dict(self._contributes_data)
            return

        if getattr(self.space_manager, "_explicit_spaces", None) is not None or getattr(
            self.space_manager, "_raw_spaces", None
        ) is not None:
            return

        try:
            from core import contributes as core_contributes

            ast_contrib = core_contributes.get("ast")
            _extract_from_ast_dict(ast_contrib)
        except Exception:
            pass

        try:
            mod_contrib = Path(__file__).resolve().parents[1] / "contributes" / "ast.json"
            if mod_contrib.is_file():
                with open(mod_contrib, "r", encoding="utf-8") as f:
                    _extract_from_ast_dict(json.load(f))
        except Exception:
            pass

        try:
            from core import uri as core_uri

            cfg_res = core_uri.resolve("config://ast/contribute.json", interactive=False)
            if cfg_res and not str(cfg_res).startswith("!undefined"):
                cfg_p = Path(str(cfg_res)).resolve()
                if cfg_p.is_file():
                    with open(cfg_p, "r", encoding="utf-8") as f:
                        _extract_from_ast_dict(json.load(f))
        except Exception:
            pass

        try:
            from core import events as core_events

            hook_results = core_events.broadcast(
                "on_register_ast_spaces",
                {"bundler": self, "register_spaces": self.register_spaces},
                emit_module="ast",
            )
            if isinstance(hook_results, dict):
                for val in hook_results.values():
                    if isinstance(val, (list, tuple, set)):
                        self.register_spaces(str(x) for x in val if str(x).strip())
                    elif isinstance(val, dict) and isinstance(val.get("spaces"), (list, tuple, set)):
                        self.register_spaces(str(x) for x in val["spaces"] if str(x).strip())
        except Exception:
            pass

    def get_target_space_names(self) -> List[str]:
        """Return deduplicated canonical target space names (`qualified_name`) managed by `ASTEngine`."""
        resolved_cfgs = self._resolve_target_spaces(None)
        names: List[str] = []
        for sp in resolved_cfgs:
            q_name = sp.qualified_name or _space_logical_name(sp)
            if q_name and q_name not in names:
                names.append(q_name)
        return names

    def clear_transient_caches(self) -> None:
        """
        Release per-file transient parsing caches (`_file_symbols_cache`,
        `_file_call_sites_cache`, `_file_imports_cache`, `_last_bundle_unique_files`)
        once `ASTSnapshot` and `CallGraphIndex` construction/hot-patching completes.
        """
        self._file_symbols_cache.clear()
        self._file_call_sites_cache.clear()
        self._file_imports_cache.clear()
        self._file_graphs_cache.clear()
        self._last_bundle_unique_files.clear()
        self._last_bundle_spaces.clear()

    def _has_valid_space_entries(self, sp: SpaceConfig) -> bool:
        if hasattr(self.space_manager, "collect_all_entry_paths"):
            try:
                q_name = sp.qualified_name or sp.short_name
                if q_name:
                    return bool(self.space_manager.collect_all_entry_paths(q_name))
            except Exception:
                pass
        return bool(sp.entries or sp.compose)

    def _resolve_target_spaces(
        self, spaces: Optional[Iterable[Union[str, SpaceConfig]]] = None
    ) -> List[SpaceConfig]:
        if spaces is None:
            self._ensure_declared_spaces_loaded()
            all_spaces = [
                sp
                for sp in self.space_manager.list_spaces()
                if sp.owner != "" and self._has_valid_space_entries(sp)
            ]
            if self._registered_spaces:
                reg_set = set(self._registered_spaces)
                reg_shorts = {s.split("/", 1)[-1].lstrip("/") for s in self._registered_spaces}
                matched = [
                    sp
                    for sp in all_spaces
                    if sp.qualified_name in reg_set
                    or sp.short_name in reg_set
                    or sp.short_name in reg_shorts
                ]
                if matched:
                    return matched
            return [
                sp
                for sp in all_spaces
                if sp.short_name not in ("gitignore", "workspace")
                and not sp.qualified_name.endswith(("/gitignore", "/workspace"))
            ]
        resolved: List[SpaceConfig] = []
        seen_qnames: Set[str] = set()
        for sp in spaces:
            if isinstance(sp, str):
                for cfg in self.space_manager.resolve_spaces(sp):
                    if cfg.qualified_name not in seen_qnames:
                        seen_qnames.add(cfg.qualified_name)
                        resolved.append(cfg)
            else:
                q_key = sp.qualified_name or sp.short_name
                if q_key not in seen_qnames:
                    seen_qnames.add(q_key)
                    resolved.append(sp)
        return resolved

    def _iter_space_eligible_files(self, space_cfg: SpaceConfig) -> List[Tuple[str, Path, Path]]:
        loaded_spaces = _get_loaded_spaces(self.space_manager)
        query_name = space_cfg.qualified_name or space_cfg.short_name
        if query_name in loaded_spaces or space_cfg.short_name in loaded_spaces:
            entries = self.space_manager.iter_space_files(query_name)
        else:
            temp_reg = SpaceRegistry(
                project_root=getattr(self.space_manager, "project_root", None),
                raw_spaces={
                    space_cfg.short_name or "custom": {
                        "entries": list(space_cfg.entries),
                        "include": list(space_cfg.include),
                        "exclude": list(space_cfg.exclude),
                    }
                },
            )
            entries = temp_reg.iter_space_files(space_cfg.short_name or "custom")

        results: List[Tuple[str, Path, Path]] = []
        for item in entries:
            if isinstance(item, SpaceFileEntry):
                base_dir = Path(item.entry_path) if item.entry_path else item.abs_path.parent
                results.append((item.rel_path, item.abs_path, base_dir))
            else:
                rel_p, abs_p, base_dir = item[0], item[1], item[2]
                results.append((str(rel_p), Path(abs_p), Path(base_dir)))
        return results

    def _get_project_relpath(self, f_path: Path, fallback_base: Path) -> str:
        proj_root = getattr(self.space_manager, "project_root", None)
        return compute_project_relpath(f_path, fallback_base, project_root=proj_root)

    def _parse_file_full(
        self,
        f_path: Union[str, Path],
        relpath: str,
        sorted_spaces: List[str],
    ) -> Tuple[List[UnifiedSymbol], List[SymbolCallSite], Dict[str, str]]:
        """Read `f_path` once and extract `FileSymbolGraph` + projected `(symbols, call_sites, imports)` in a single pass."""
        primary_space = sorted_spaces[0] if sorted_spaces else "unified"
        with open(f_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        fg = self.parser_registry.extract_file_graph(
            file_path=relpath,
            content=content,
            space=primary_space,
        )
        c_key = _safe_resolve_str(f_path)
        self._file_graphs_cache[relpath] = fg
        self._file_graphs_cache[c_key] = fg

        parser = self.parser_registry.get_parser(relpath)
        base_hit = (
            self.parser_registry._match_base_extract_cache(parser, relpath, content, space=primary_space)
            if parser is not None
            else None
        )
        if base_hit is not None:
            file_symbols = [dataclasses.replace(s, metadata=dict(s.metadata)) for s in base_hit[5]]
            file_symbols = ensure_unique_overload_ids(file_symbols, default_space=primary_space)
            for sym in file_symbols:
                sym.metadata["spaces"] = sorted_spaces
            call_sites = list(base_hit[6])
            imports = dict(base_hit[7])
            return file_symbols, call_sites, imports

        file_symbols, call_sites, imports = project_file_artifacts_from_graph(
            fg, default_space=primary_space, spaces=sorted_spaces
        )
        return file_symbols, call_sites, imports

    def _collect_space_files(
        self, target_spaces: List[SpaceConfig]
    ) -> Dict[str, Tuple[Path, str, Set[str]]]:
        unique_files: Dict[str, Tuple[Path, str, Set[str]]] = {}

        for sp in target_spaces:
            space_name = _space_logical_name(sp)
            for _, f_path, base_dir in self._iter_space_eligible_files(sp):
                relpath = self._get_project_relpath(f_path, base_dir)
                if self.parser_registry.get_parser(relpath) is None:
                    continue
                c_key = _safe_resolve_str(f_path)
                if c_key not in unique_files:
                    unique_files[c_key] = (f_path, relpath, {space_name})
                else:
                    unique_files[c_key][2].add(space_name)

        return unique_files

    def _get_or_collect_space_files(
        self, target_spaces: List[SpaceConfig]
    ) -> Dict[str, Tuple[Path, str, Set[str]]]:
        target_space_names = {_space_logical_name(sp) for sp in target_spaces}
        if (
            self._last_bundle_unique_files
            and self._last_bundle_spaces == target_space_names
        ):
            return dict(self._last_bundle_unique_files)
        return self._collect_space_files(target_spaces)

    def _resolve_dirty_files_only(
        self,
        dirty_raw_paths: Iterable[str],
        target_spaces: List[SpaceConfig],
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Tuple[Path, str, Set[str]]]:
        """
        Resolve only `dirty_raw_paths` across `target_spaces` in O(|dirty|) without walking the entire repository.
        """
        raw_list = [str(p).replace("\\", "/").strip() for p in dirty_raw_paths if p]
        if not raw_list:
            return {}

        if snap_entries_by_space is None:
            snap_entries_by_space = _preload_snap_entries(self.scanner, target_spaces)

        proj_root = getattr(self.space_manager, "project_root", None)
        space_inc_roots: Dict[str, List[Path]] = {}
        for sp in target_spaces:
            sp_key = _space_logical_name(sp)
            space_inc_roots[sp_key] = _resolve_space_entry_roots(sp, self.space_manager)

        candidate_files: Dict[str, Tuple[Path, Path]] = {}

        def _add_candidate(f_path: Path, base_dir: Path) -> None:
            try:
                if not f_path.is_file():
                    return
                resolved_p = f_path.resolve()
                c_key = str(resolved_p).replace("\\", "/")
            except OSError:
                return
            if c_key not in candidate_files:
                candidate_files[c_key] = (resolved_p, base_dir)

        for raw_p in raw_list:
            p_obj = Path(raw_p)
            if p_obj.is_absolute():
                _add_candidate(p_obj, p_obj.parent)
                continue

            clean_p = raw_p.strip("/")
            matched_this = False
            snap_matches: List[Any] = []
            for sp in target_spaces:
                sp_key = _space_logical_name(sp)
                entries = snap_entries_by_space.get(sp_key) or snap_entries_by_space.get(sp.qualified_name, {})
                fp_rec = entries.get(clean_p)
                if fp_rec is not None and not getattr(fp_rec, "is_deleted", False) and getattr(fp_rec, "entry_path", ""):
                    snap_matches.append(fp_rec)

            if snap_matches:
                if len(snap_matches) > 1:
                    best_mtime_ns = max((int(getattr(fp, "mtime_ns", 0)) for fp in snap_matches), default=0)
                    snap_matches = [fp for fp in snap_matches if int(getattr(fp, "mtime_ns", 0)) >= best_mtime_ns]
                for fp_rec in snap_matches:
                    src_root = Path(fp_rec.entry_path)
                    _add_candidate(src_root / clean_p, src_root)
                    matched_this = True

            if not matched_this:
                inc_matches: List[Tuple[Path, Path]] = []
                for sp in target_spaces:
                    sp_key = _space_logical_name(sp)
                    for inc_root in space_inc_roots.get(sp_key, []):
                        cand = inc_root / clean_p
                        if _safe_is_file(cand):
                            inc_matches.append((cand, inc_root))
                if len(inc_matches) > 1:
                    max_mtime = max((_safe_mtime_ns(c) for c, _ in inc_matches), default=0)
                    inc_matches = [(c, r) for c, r in inc_matches if _safe_mtime_ns(c) >= max_mtime]
                for cand, inc_root in inc_matches:
                    _add_candidate(cand, inc_root)
                    matched_this = True

            if proj_root is not None:
                cand_proj = Path(proj_root) / clean_p
                if _safe_is_file(cand_proj):
                    _add_candidate(cand_proj, Path(proj_root))
                    matched_this = True

            if not matched_this:
                norm_single = normalize_dirty_paths([clean_p])
                for sp in target_spaces:
                    sp_key = _space_logical_name(sp)
                    entries = snap_entries_by_space.get(sp_key) or snap_entries_by_space.get(sp.qualified_name, {})
                    for rel_key, fp_rec in entries.items():
                        if getattr(fp_rec, "is_deleted", False) or not getattr(fp_rec, "entry_path", ""):
                            continue
                        if is_dirty_file_match(rel_key, norm_single):
                            src_root = Path(fp_rec.entry_path)
                            _add_candidate(src_root / rel_key, src_root)

        result: Dict[str, Tuple[Path, str, Set[str]]] = {}
        for c_key, (resolved_p, fallback_base) in candidate_files.items():
            matched_spaces: Set[str] = set()
            chosen_base = fallback_base
            for sp in target_spaces:
                sp_key = _space_logical_name(sp)
                entries = snap_entries_by_space.get(sp_key) or snap_entries_by_space.get(sp.qualified_name, {})
                for inc_root in space_inc_roots.get(sp_key, []):
                    try:
                        rel_to_inc = resolved_p.relative_to(inc_root).as_posix()
                    except ValueError:
                        continue
                    fp_rec = entries.get(rel_to_inc)
                    if fp_rec is not None and not getattr(fp_rec, "is_deleted", False):
                        matched_spaces.add(sp_key)
                        chosen_base = inc_root
                        break
                    matched_spaces.add(sp_key)
                    chosen_base = inc_root
                    break
            if not matched_spaces and target_spaces:
                matched_spaces.add(_space_logical_name(target_spaces[0]))
            if matched_spaces:
                relpath = self._get_project_relpath(resolved_p, chosen_base)
                if self.parser_registry.get_parser(relpath) is None:
                    continue
                result[c_key] = (resolved_p, relpath, matched_spaces)

        if not result and raw_list:
            # Fallback for custom/unindexed spaces when no candidate matched directly
            parse_norm = normalize_dirty_paths(raw_list)
            for c_key, (f_path, relpath, sp_set) in self._collect_space_files(target_spaces).items():
                if is_dirty_file_match(c_key, parse_norm) or is_dirty_file_match(relpath, parse_norm):
                    result[c_key] = (f_path, relpath, sp_set)

        return result

    def bundle_union(
        self,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        allow_parallel: bool = True,
    ) -> SemanticBundle:
        """Scan the union of all spaces, deduplicating physical files by canonical path."""
        target_spaces = self._resolve_target_spaces(spaces)
        unique_files = self._collect_space_files(target_spaces)
        self._last_bundle_unique_files = dict(unique_files)
        self._last_bundle_spaces = {_space_logical_name(sp) for sp in target_spaces}

        total_files = len(unique_files)
        all_symbols: List[UnifiedSymbol] = []
        self._file_symbols_cache.clear()
        self._file_call_sites_cache.clear()
        self._file_imports_cache.clear()
        self._file_graphs_cache.clear()

        tasks: List[Tuple[str, str, str, List[str]]] = []
        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            sorted_spaces = sorted(list(sp_set))
            tasks.append((c_key, str(f_path), relpath, sorted_spaces))

        from .parsers.registry import DEFAULT_LANGUAGES

        lang_cfgs = self.parser_registry.language_configs
        has_custom_configs = (
            self._contributes_data is not None
            or len(getattr(self.parser_registry, "_parsers", ())) > len(lang_cfgs)
            or any(
                lang_id not in DEFAULT_LANGUAGES
                or cfg.mode != DEFAULT_LANGUAGES[lang_id].get("mode", "tree_sitter")
                or cfg.grammar != DEFAULT_LANGUAGES[lang_id].get("grammar")
                or cfg.query_file != DEFAULT_LANGUAGES[lang_id].get("query_file")
                or tuple(cfg.query_files) != tuple(
                    DEFAULT_LANGUAGES[lang_id].get("query_files")
                    or (
                        [DEFAULT_LANGUAGES[lang_id]["query_file"]]
                        if DEFAULT_LANGUAGES[lang_id].get("query_file")
                        else ()
                    )
                )
                or tuple(cfg.spaces) != tuple(DEFAULT_LANGUAGES[lang_id].get("spaces", ()))
                or tuple(cfg.processors) != tuple(DEFAULT_LANGUAGES[lang_id].get("processors", ()))
                or cfg.module_resolver != DEFAULT_LANGUAGES[lang_id].get("module_resolver")
                or tuple(cfg.edge_refiners) != tuple(DEFAULT_LANGUAGES[lang_id].get("edge_refiners", ()))
                or cfg.parser_entry != DEFAULT_LANGUAGES[lang_id].get("parser_entry")
                or tuple(cfg.extensions) != tuple(DEFAULT_LANGUAGES[lang_id].get("extensions", ()))
                for lang_id, cfg in lang_cfgs.items()
            )
        )
        cpu_cnt = os.cpu_count() or 1
        in_server_worker = get_env("YSCB_IN_SERVER_WORKER") == "1"
        use_parallel = (
            allow_parallel
            and not in_server_worker
            and total_files >= PARALLEL_BUNDLE_THRESHOLD
            and cpu_cnt > 1
            and not has_custom_configs
        )

        if use_parallel:
            try:
                import sys

                workers = min(4, cpu_cnt)
                chunk_size = max(1, total_files // (workers * 4))
                with ProcessPoolExecutor(
                    max_workers=workers,
                    initializer=_init_bundle_worker,
                    initargs=(list(sys.path),),
                ) as pool:
                    results_iter = pool.map(_parse_file_task_worker, tasks, chunksize=chunk_size)
                    for idx, item in enumerate(results_iter, start=1):
                        fg_dict: Optional[Dict[str, Any]] = None
                        if len(item) == 6:
                            c_key, sym_dicts, site_dicts, imps, fg_dict, err = item
                        elif len(item) == 5:
                            c_key, sym_dicts, site_dicts, imps, err = item  # type: ignore[misc]
                        else:
                            c_key, sym_dicts, err = item  # type: ignore[misc]
                            site_dicts, imps = None, None
                        if progress_callback:
                            rel = unique_files[c_key][1]
                            progress_callback(rel, idx, total_files)
                        if err:
                            log_warn(f"Failed parsing file '{c_key}' during parallel bundle: {err}", stream="stderr")
                            self._file_symbols_cache[c_key] = []
                            self._file_call_sites_cache[c_key] = []
                            self._file_imports_cache[c_key] = {}
                            continue
                        file_symbols = [UnifiedSymbol.from_dict(d) for d in sym_dicts]
                        all_symbols.extend(file_symbols)
                        self._file_symbols_cache[c_key] = file_symbols
                        if site_dicts is not None:
                            self._file_call_sites_cache[c_key] = [SymbolCallSite.from_dict(s) for s in site_dicts]
                        if imps is not None:
                            self._file_imports_cache[c_key] = dict(imps)
                        if isinstance(fg_dict, dict):
                            try:
                                fg_obj = FileSymbolGraph.from_dict(fg_dict)
                                rel = unique_files[c_key][1]
                                self._file_graphs_cache[rel] = fg_obj
                                self._file_graphs_cache[c_key] = fg_obj
                            except Exception:
                                pass
            except Exception as pool_err:
                log_warn(f"ProcessPoolExecutor error, falling back to serial parsing: {pool_err}", stream="stderr")
                use_parallel = False

        if not use_parallel:
            for idx, (c_key, f_path_str, relpath, sorted_spaces) in enumerate(tasks, start=1):
                if progress_callback:
                    progress_callback(relpath, idx, total_files)
                try:
                    file_symbols, call_sites, imps = self._parse_file_full(f_path_str, relpath, sorted_spaces)
                    all_symbols.extend(file_symbols)
                    self._file_symbols_cache[c_key] = file_symbols
                    self._file_call_sites_cache[c_key] = call_sites
                    self._file_imports_cache[c_key] = imps
                except Exception as err:
                    log_warn(f"Failed parsing file '{c_key}' during serial bundle: {err}", stream="stderr")
                    self._file_symbols_cache[c_key] = []
                    self._file_call_sites_cache[c_key] = []
                    self._file_imports_cache[c_key] = {}

        all_symbols = aggregate_partial_symbols(all_symbols)
        created_at = datetime.now(timezone.utc).isoformat()
        files_map = {}
        for c_key, (f_path, _, _) in unique_files.items():
            try:
                st = f_path.stat()
                files_map[c_key] = (st.st_mtime, st.st_size)
            except OSError:
                pass

        return SemanticBundle(
            version="1.0.0",
            space_name="unified",
            created_at=created_at,
            symbols=all_symbols,
            metadata={
                "total_spaces": len(target_spaces),
                "total_files": total_files,
                "total_symbols": len(all_symbols),
                "files_map": files_map,
            },
        )

    def _normalize_space_dirty_paths(
        self,
        raw_paths: Iterable[str],
        target_spaces: List[SpaceConfig],
        prefer_missing: bool = False,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
        known_indexed_files: Optional[Set[str]] = None,
    ) -> Set[str]:
        return _normalize_space_dirty_paths(
            raw_paths=raw_paths,
            target_spaces=target_spaces,
            space_manager=self.space_manager,
            scanner=self.scanner,
            file_symbols_cache=self._file_symbols_cache,
            prefer_missing=prefer_missing,
            snap_entries_by_space=snap_entries_by_space,
            known_indexed_files=known_indexed_files,
        )

    def bundle_dirty_files(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
        known_indexed_files: Optional[Set[str]] = None,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, List[UnifiedSymbol]], Set[str]]:
        """Parse only added/modified files in `dirty_diff` and evict deleted/modified cache entries."""
        target_spaces = self._resolve_target_spaces(spaces)
        if snap_entries_by_space is None:
            snap_entries_by_space = _preload_snap_entries(self.scanner, target_spaces)
        expanded_added_mod = self._normalize_space_dirty_paths(
            dirty_diff.dirty_files,
            target_spaces,
            prefer_missing=False,
            snap_entries_by_space=snap_entries_by_space,
            known_indexed_files=known_indexed_files,
        )
        expanded_deleted = self._normalize_space_dirty_paths(
            dirty_diff.deleted,
            target_spaces,
            prefer_missing=True,
            snap_entries_by_space=snap_entries_by_space,
            known_indexed_files=known_indexed_files,
        )
        dirty_keys = set(expanded_added_mod | expanded_deleted)
        expanded_mod = self._normalize_space_dirty_paths(
            dirty_diff.modified,
            target_spaces,
            prefer_missing=False,
            snap_entries_by_space=snap_entries_by_space,
            known_indexed_files=known_indexed_files,
        )
        evict_norm = normalize_dirty_paths(expanded_deleted | expanded_mod)

        if evict_norm:
            all_cached_keys = (
                set(self._file_symbols_cache.keys())
                | set(self._file_call_sites_cache.keys())
                | set(self._file_imports_cache.keys())
                | set(self._file_graphs_cache.keys())
            )
            keys_to_pop = [k for k in all_cached_keys if is_dirty_file_match(k, evict_norm)]
            for k in keys_to_pop:
                self._file_symbols_cache.pop(k, None)
                self._file_call_sites_cache.pop(k, None)
                self._file_imports_cache.pop(k, None)
                self._file_graphs_cache.pop(k, None)

        parse_targets_norm = normalize_dirty_paths(expanded_added_mod)
        if not parse_targets_norm:
            return {}, dirty_keys

        dirty_files_map = self._resolve_dirty_files_only(
            dirty_diff.dirty_files,
            target_spaces,
            snap_entries_by_space=snap_entries_by_space,
        )
        new_symbols_by_file: Dict[str, List[UnifiedSymbol]] = {}

        for c_key, (f_path, relpath, sp_set) in dirty_files_map.items():
            if is_dirty_file_match(c_key, parse_targets_norm) or is_dirty_file_match(relpath, parse_targets_norm):
                dirty_keys.add(c_key)
                dirty_keys.add(relpath)
                sorted_spaces = sorted(list(sp_set))
                try:
                    file_symbols, call_sites, imps = self._parse_file_full(f_path, relpath, sorted_spaces)
                    self._file_symbols_cache[c_key] = file_symbols
                    self._file_call_sites_cache[c_key] = call_sites
                    self._file_imports_cache[c_key] = imps
                    new_symbols_by_file[c_key] = file_symbols
                except Exception as err:
                    log_warn(f"Failed parsing dirty file '{c_key}': {err}", stream="stderr")
                    self._file_symbols_cache[c_key] = []
                    self._file_call_sites_cache[c_key] = []
                    self._file_imports_cache[c_key] = {}

        return new_symbols_by_file, dirty_keys

    def export_bundle(
        self,
        bundle: SemanticBundle,
        target_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        if target_path is not None:
            out_file = _safe_resolve_path(target_path)
        else:
            bundles_dir = self.storage_dir / "bundles"
            bundles_dir.mkdir(parents=True, exist_ok=True)
            out_file = bundles_dir / f"{bundle.space_name}.bundle.json"

        out_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False).encode("utf-8")
            write_bytes(str(out_file), payload)
            return out_file
        except Exception as exc:
            raise ASTError(f"Failed exporting bundle to {out_file}: {exc}") from exc

    def _extract_call_sites_and_imports_core(
        self,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
        dirty_file_paths: Optional[Iterable[str]] = None,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        target_spaces = self._resolve_target_spaces(spaces)
        if dirty_file_paths is not None:
            unique_files = self._resolve_dirty_files_only(
                dirty_file_paths,
                target_spaces,
                snap_entries_by_space=snap_entries_by_space,
            )
        else:
            unique_files = self._get_or_collect_space_files(target_spaces)
        dirty_norm = normalize_dirty_paths(dirty_file_paths) if dirty_file_paths is not None else None

        call_sites: List[SymbolCallSite] = []
        imports_map: Dict[str, Dict[str, str]] = {}

        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            if dirty_norm is not None:
                if not (is_dirty_file_match(c_key, dirty_norm) or is_dirty_file_match(relpath, dirty_norm)):
                    continue

            if c_key in self._file_call_sites_cache and c_key in self._file_imports_cache:
                sites = self._file_call_sites_cache[c_key]
                imps = self._file_imports_cache[c_key]
                call_sites.extend(sites)
                if imps:
                    imports_map[relpath] = imps
                continue

            primary_space = sorted(list(sp_set))[0] if sp_set else "unified"
            cached_syms = self._file_symbols_cache.get(c_key)
            try:
                if cached_syms is None:
                    file_syms, sites, imps = self._parse_file_full(f_path, relpath, sorted(list(sp_set)))
                    self._file_symbols_cache[c_key] = file_syms
                else:
                    with open(f_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    sites = self.parser_registry.extract_call_sites(
                        file_path=relpath, content=content, space=primary_space, symbols=cached_syms
                    )
                    imps = self.parser_registry.extract_imports(
                        file_path=relpath, content=content
                    )
                self._file_call_sites_cache[c_key] = sites
                self._file_imports_cache[c_key] = dict(imps or {})
                call_sites.extend(sites)
                if imps:
                    imports_map[relpath] = imps
            except Exception as exc:
                log_debug(f"Error extracting call sites/imports from '{f_path}': {exc}")

        return call_sites, imports_map

    def extract_all_call_sites_and_imports(
        self,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        return self._extract_call_sites_and_imports_core(spaces=spaces, dirty_file_paths=None)

    def extract_dirty_call_sites_and_imports(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
        expanded_dirty_paths: Optional[Set[str]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        target_spaces = self._resolve_target_spaces(spaces)
        if snap_entries_by_space is None:
            snap_entries_by_space = _preload_snap_entries(self.scanner, target_spaces)
        expanded_dirty = (
            expanded_dirty_paths
            if expanded_dirty_paths is not None
            else self._normalize_space_dirty_paths(
                dirty_diff.dirty_files,
                target_spaces,
                prefer_missing=False,
                snap_entries_by_space=snap_entries_by_space,
            )
        )
        return self._extract_call_sites_and_imports_core(
            spaces=spaces,
            dirty_file_paths=expanded_dirty,
            snap_entries_by_space=snap_entries_by_space,
        )

    def extract_all_file_graphs(
        self,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
    ) -> Dict[str, FileSymbolGraph]:
        """Return `{relpath: FileSymbolGraph}` across all target spaces (reusing `_file_graphs_cache` when populated)."""
        target_spaces = self._resolve_target_spaces(spaces)
        unique_files = self._get_or_collect_space_files(target_spaces)
        out: Dict[str, FileSymbolGraph] = {}
        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            cached_fg = self._file_graphs_cache.get(relpath) or self._file_graphs_cache.get(c_key)
            if cached_fg is not None:
                out[relpath] = cached_fg
                continue
            primary_space = sorted(list(sp_set))[0] if sp_set else "unified"
            try:
                with open(f_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                fg = self.parser_registry.extract_file_graph(
                    file_path=relpath,
                    content=content,
                    space=primary_space,
                )
                self._file_graphs_cache[relpath] = fg
                self._file_graphs_cache[c_key] = fg
                out[relpath] = fg
            except Exception as exc:
                log_debug(f"Error extracting FileSymbolGraph from '{f_path}': {exc}")
        return out

    def extract_dirty_file_graphs(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, SpaceConfig]]] = None,
        known_indexed_files: Optional[Set[str]] = None,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, FileSymbolGraph], Set[str]]:
        """Return `(new_file_graphs_by_relpath, dirty_keys)` for added/modified files in `dirty_diff`."""
        target_spaces = self._resolve_target_spaces(spaces)
        if snap_entries_by_space is None:
            snap_entries_by_space = _preload_snap_entries(self.scanner, target_spaces)
        expanded_added_mod = self._normalize_space_dirty_paths(
            dirty_diff.dirty_files,
            target_spaces,
            prefer_missing=False,
            snap_entries_by_space=snap_entries_by_space,
            known_indexed_files=known_indexed_files,
        )
        expanded_deleted = self._normalize_space_dirty_paths(
            dirty_diff.deleted,
            target_spaces,
            prefer_missing=True,
            snap_entries_by_space=snap_entries_by_space,
            known_indexed_files=known_indexed_files,
        )
        dirty_keys = set(expanded_added_mod | expanded_deleted)
        parse_targets_norm = normalize_dirty_paths(expanded_added_mod)
        if not parse_targets_norm:
            return {}, dirty_keys

        dirty_files_map = self._resolve_dirty_files_only(
            dirty_diff.dirty_files,
            target_spaces,
            snap_entries_by_space=snap_entries_by_space,
        )
        new_fgs: Dict[str, FileSymbolGraph] = {}
        for c_key, (f_path, relpath, sp_set) in dirty_files_map.items():
            if is_dirty_file_match(c_key, parse_targets_norm) or is_dirty_file_match(relpath, parse_targets_norm):
                dirty_keys.add(c_key)
                dirty_keys.add(relpath)
                cached_fg = self._file_graphs_cache.get(relpath) or self._file_graphs_cache.get(c_key)
                if cached_fg is not None:
                    new_fgs[relpath] = cached_fg
                    continue
                primary_space = sorted(list(sp_set))[0] if sp_set else "unified"
                try:
                    with open(f_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    fg = self.parser_registry.extract_file_graph(
                        file_path=relpath,
                        content=content,
                        space=primary_space,
                    )
                    self._file_graphs_cache[relpath] = fg
                    self._file_graphs_cache[c_key] = fg
                    new_fgs[relpath] = fg
                except Exception as exc:
                    log_debug(f"Error extracting dirty FileSymbolGraph from '{f_path}': {exc}")
        return new_fgs, dirty_keys


__all__ = [
    "PARALLEL_BUNDLE_THRESHOLD",
    "SemanticBundle",
    "SemanticBundler",
    "_extract_unaggregated_partial_state",
    "_is_partial_symbol",
    "_normalize_space_dirty_paths",
    "_preload_snap_entries",
    "_resolve_default_ast_storage_dir",
    "aggregate_partial_symbols",
    "ensure_unique_overload_ids",
    "project_file_artifacts_from_graph",
    "reset_worker_registry",
    "restore_unaggregated_partial_symbol",
]
