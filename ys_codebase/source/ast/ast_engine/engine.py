"""
AST & Call Topology Engine (`ASTEngine`) for `module:ast@1.0.0.0`.
Coordinates:
- Multi-space fingerprint scanning and transactional cursor consumption (`consumer_id="ast"`).
- Persisted `ASTSnapshot` (`unified.symbols.bin.gz`) and `CallGraphIndex` (`unified.graph.bin.gz`).
- Incremental hot-patching (`hot_patch_index`) with C# `partial class/struct/interface` restoration
  (`restore_unaggregated_partial_symbol`) and external incoming call-edge reconnection (`get_external_incoming_edges`).
- Single-file physical vs. cross-file merged AST `outline`.
- Deterministic symbol resolution & overload grouping (`callers`, `callees`, `impact`).
"""

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Union

from file_space import (
    FileSpaceConfig,
    FileSpaceManager,
    FingerprintScanner,
    ScanDiffDetail,
    ScanDiffResult,
    consume_diff,
    reset_cursor,
)

from .bundler import (
    SemanticBundler,
    _extract_unaggregated_partial_state,
    _is_partial_symbol,
    _resolve_default_ast_storage_dir,
    aggregate_partial_symbols,
    ensure_unique_overload_ids,
    restore_unaggregated_partial_symbol,
)
from .exceptions import ASTCorruptedError, ASTIndexNotFoundError
from .formatter import ASTResultFormatter
from .graph import CallGraphIndex
from .io_utils import (
    atomic_save_gzip_pickle,
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
    resolve_project_root,
)
from .linker import TopologyLinker
from .parsers.registry import ParserRegistry
from .provisioner import GrammarProvisioner
from .resolver import (
    SnippetExtractor,
    query_callees,
    query_callers,
    query_impact,
)
from .schema import ASTSnapshot, MemberInfo, OutlineNode, OutlineResult, SymbolCallSite, UnifiedSymbol

logger = logging.getLogger("ast.engine")

_DEFAULT_ENGINE_INSTANCE: Optional["ASTEngine"] = None
_ENGINE_LOCK = threading.RLock()


def _cs_partial_type_key(sym: UnifiedSymbol) -> Optional[Tuple[str, str, str]]:
    """Return `(spaces_key, kind, fqn_or_name)` for C# partial classes/structs/interfaces."""
    if (sym.language in ("c_sharp", "csharp") or _is_partial_symbol(sym)) and sym.kind in (
        "class",
        "struct",
        "interface",
    ):
        sp_key = ",".join(sorted(sym.spaces)) if sym.spaces else ""
        return (sp_key, sym.kind, sym.fqn or sym.name)
    return None


def _infer_static_flag(sig_str: str, explicit_static: bool = False) -> bool:
    """Determine if a symbol or member signature denotes a static member."""
    if explicit_static:
        return True
    if sig_str and re.search(r"(?:^|\s|@)(?:static|staticmethod|classmethod)\b", sig_str):
        return True
    return False


def _member_to_outline_node(member: Any, default_line: int = 1) -> OutlineNode:
    """Convert a `MemberInfo`, dict, or `UnifiedSymbol` into an `OutlineNode`."""
    if isinstance(member, MemberInfo):
        is_st = _infer_static_flag(member.signature, bool(getattr(member, "is_static", False)))
        return OutlineNode(
            name=member.name,
            kind=member.kind,
            line_number=member.line_number or default_line,
            end_line=member.line_number or default_line,
            signature=member.signature,
            visibility=member.visibility,
            docstring=member.docstring,
            fqn=member.name,
            is_static=is_st,
        )
    if isinstance(member, dict):
        sig_s = str(member.get("signature", ""))
        is_st = _infer_static_flag(sig_s, bool(member.get("is_static", False)))
        return OutlineNode(
            name=str(member.get("name", "")),
            kind=str(member.get("kind", "member")),
            line_number=int(member.get("line_number", default_line)),
            end_line=int(member.get("end_line", member.get("line_number", default_line))),
            signature=sig_s,
            visibility=str(member.get("visibility", "public")),
            docstring=str(member.get("docstring", "")),
            fqn=str(member.get("fqn") or member.get("name", "")),
            is_static=is_st,
        )
    if isinstance(member, UnifiedSymbol):
        return _sym_to_outline_node(member, {}, None, "", False, {})
    return OutlineNode(name=str(member), kind="member", line_number=default_line, end_line=default_line)


def _sym_to_outline_node(
    sym: UnifiedSymbol,
    children_by_parent_id: Dict[str, List[UnifiedSymbol]],
    snapshot: Optional[ASTSnapshot],
    rel_path: str,
    merged: bool,
    partial_siblings_map: Dict[str, List[Dict[str, Any]]],
    snap_by_kind_fqn: Optional[Dict[Tuple[str, str], List[UnifiedSymbol]]] = None,
) -> OutlineNode:
    """Recursively convert a `UnifiedSymbol` and its child declarations into an `OutlineNode`."""
    is_part = _is_partial_symbol(sym)
    is_st = _infer_static_flag(sym.signature, bool((sym.metadata or {}).get("is_static", False)))
    fqn_key = sym.fqn or sym.name
    short_n = (sym.metadata or {}).get("short_name") or sym.name
    node_meta: Dict[str, Any] = {}
    if is_st:
        node_meta["is_static"] = True

    direct_child_syms = children_by_parent_id.get(sym.id, [])
    child_nodes: List[OutlineNode] = [
        _sym_to_outline_node(
            c,
            children_by_parent_id,
            snapshot,
            rel_path,
            merged,
            partial_siblings_map,
            snap_by_kind_fqn=snap_by_kind_fqn,
        )
        for c in direct_child_syms
    ]
    existing_child_keys = {(c.name, c.kind, c.signature) for c in child_nodes}

    own_members_raw, _, _, _ = _extract_unaggregated_partial_state(sym)
    for m in own_members_raw:
        m_node = _member_to_outline_node(m, default_line=sym.line_number)
        if (m_node.name, m_node.kind, m_node.signature) not in existing_child_keys:
            existing_child_keys.add((m_node.name, m_node.kind, m_node.signature))
            child_nodes.append(m_node)

    if is_part and snapshot is not None:
        siblings: List[Dict[str, Any]] = []
        norm_this_path = rel_path.replace("\\", "/").lower()
        candidates = (
            snap_by_kind_fqn.get((sym.kind, fqn_key), [])
            if snap_by_kind_fqn is not None
            else [
                s
                for s in snapshot.symbols.values()
                if s.kind == sym.kind and (s.fqn or s.name) == fqn_key
            ]
        )
        sym_spaces = set(sym.spaces) if sym.spaces else set()
        for snap_sym in candidates:
            if sym_spaces and snap_sym.spaces and not sym_spaces.intersection(snap_sym.spaces):
                continue
            snap_meta = snap_sym.metadata or {}
            locs = snap_meta.get("partial_locations") or []
            if locs:
                for loc in locs:
                    loc_fp = str(loc.get("file_path", "")).replace("\\", "/")
                    if loc_fp.lower() != norm_this_path or int(loc.get("line_number", 0)) != sym.line_number:
                        sib_item = {
                            "file_path": loc_fp,
                            "line_number": int(loc.get("line_number", 1)),
                            "end_line": int(loc.get("end_line", loc.get("line_number", 1))),
                            "member_count": int(loc.get("member_count", 0)),
                        }
                        if sib_item not in siblings:
                            siblings.append(sib_item)
            elif snap_sym.file_path.replace("\\", "/").lower() != norm_this_path:
                s_own, _, _, _ = _extract_unaggregated_partial_state(snap_sym)
                sib_item = {
                    "file_path": snap_sym.file_path,
                    "line_number": snap_sym.line_number,
                    "end_line": snap_sym.end_line,
                    "member_count": len(s_own),
                }
                if sib_item not in siblings:
                    siblings.append(sib_item)

            if merged:
                for m in snap_sym.members:
                    m_node = _member_to_outline_node(m, default_line=snap_sym.line_number)
                    if (m_node.name, m_node.kind, m_node.signature) not in existing_child_keys:
                        existing_child_keys.add((m_node.name, m_node.kind, m_node.signature))
                        child_nodes.append(m_node)

        if siblings:
            partial_siblings_map[fqn_key] = siblings
            node_meta["partial_siblings"] = siblings

    child_nodes.sort(key=lambda c: (c.line_number, c.name))
    return OutlineNode(
        name=short_n,
        kind=sym.kind,
        line_number=sym.line_number,
        end_line=sym.end_line,
        signature=sym.signature,
        visibility=sym.visibility,
        docstring=sym.docstring,
        fqn=fqn_key,
        is_partial=is_part,
        is_static=is_st,
        children=child_nodes,
        metadata=node_meta,
    )


def _build_outline_tree(
    file_symbols: List[UnifiedSymbol],
    snapshot: Optional[ASTSnapshot] = None,
    rel_path: str = "",
    merged: bool = False,
) -> Tuple[List[OutlineNode], Dict[str, List[Dict[str, Any]]]]:
    """Build hierarchical `OutlineNode` tree and `partial_siblings` map from parsed file symbols."""
    partial_siblings_map: Dict[str, List[Dict[str, Any]]] = {}
    sym_by_id: Dict[str, UnifiedSymbol] = {s.id: s for s in file_symbols}
    children_by_parent_id: Dict[str, List[UnifiedSymbol]] = {}
    top_level_syms: List[UnifiedSymbol] = []

    snap_by_kind_fqn: Optional[Dict[Tuple[str, str], List[UnifiedSymbol]]] = None
    if snapshot is not None and isinstance(snapshot.symbols, dict):
        snap_by_kind_fqn = {}
        for snap_sym in snapshot.symbols.values():
            snap_by_kind_fqn.setdefault((snap_sym.kind, snap_sym.fqn or snap_sym.name), []).append(snap_sym)

    for s in sorted(file_symbols, key=lambda x: (x.line_number, x.name)):
        if s.parent_id and s.parent_id in sym_by_id:
            children_by_parent_id.setdefault(s.parent_id, []).append(s)
        else:
            top_level_syms.append(s)

    def _collect_flattened(sym_list: List[UnifiedSymbol], acc: List[OutlineNode]) -> None:
        for s in sym_list:
            node = _sym_to_outline_node(
                s,
                children_by_parent_id,
                snapshot,
                rel_path,
                merged,
                partial_siblings_map,
                snap_by_kind_fqn=snap_by_kind_fqn,
            )
            if s.kind == "namespace":
                direct_children = children_by_parent_id.get(s.id, [])
                if direct_children:
                    _collect_flattened(direct_children, acc)
                else:
                    acc.append(node)
            else:
                acc.append(node)

    outline_nodes: List[OutlineNode] = []
    _collect_flattened(top_level_syms, outline_nodes)
    return outline_nodes, partial_siblings_map


def _filter_outline_nodes(
    nodes: List[OutlineNode],
    active_filters: Dict[str, str],
) -> List[OutlineNode]:
    """Filter hierarchical `OutlineNode` tree by `visibility`, `binding`, and `member_kind`."""
    if not active_filters:
        return nodes

    vis_filter = active_filters.get("visibility")
    bind_filter = active_filters.get("binding")
    kind_filter = active_filters.get("member_kind")
    type_kinds = {"class", "struct", "interface", "enum", "type_alias"}
    method_kinds = {"method", "function"}
    field_kinds = {"field", "property", "variable", "constant"}

    def _matches_visibility(node: OutlineNode) -> bool:
        if not vis_filter:
            return True
        v = (node.visibility or "public").lower()
        if vis_filter in ("non-private", "non_private", "api"):
            return v != "private"
        return v == vis_filter

    def _matches_binding(node: OutlineNode) -> bool:
        if not bind_filter:
            return True
        if bind_filter == "static":
            return bool(node.is_static)
        if bind_filter in ("non-static", "non_static", "nonstatic", "instance"):
            return not bool(node.is_static)
        return True

    def _matches_kind(node: OutlineNode) -> bool:
        if not kind_filter:
            return True
        k = (node.kind or "").lower()
        if kind_filter == "types":
            return k in type_kinds
        if kind_filter == "methods":
            return k in method_kinds
        if kind_filter == "fields":
            return k in field_kinds
        return True

    def _filter_single(node: OutlineNode) -> Optional[OutlineNode]:
        k = (node.kind or "").lower()
        is_container = k in type_kinds or bool(node.children)
        if kind_filter == "types":
            if k in type_kinds and _matches_visibility(node) and _matches_binding(node):
                nested_types = [fc for fc in (_filter_single(c) for c in node.children) if fc is not None]
                return OutlineNode(
                    name=node.name,
                    kind=node.kind,
                    line_number=node.line_number,
                    end_line=node.end_line,
                    signature=node.signature,
                    visibility=node.visibility,
                    docstring=node.docstring,
                    fqn=node.fqn,
                    is_partial=node.is_partial,
                    is_static=node.is_static,
                    children=nested_types,
                    metadata=dict(node.metadata),
                )
            return None

        filtered_children = [fc for fc in (_filter_single(c) for c in node.children) if fc is not None]
        self_matches = _matches_visibility(node) and _matches_binding(node) and _matches_kind(node)
        if self_matches or (is_container and filtered_children):
            return OutlineNode(
                name=node.name,
                kind=node.kind,
                line_number=node.line_number,
                end_line=node.end_line,
                signature=node.signature,
                visibility=node.visibility,
                docstring=node.docstring,
                fqn=node.fqn,
                is_partial=node.is_partial,
                is_static=node.is_static,
                children=filtered_children,
                metadata=dict(node.metadata),
            )
        return None

    return [fn for fn in (_filter_single(n) for n in nodes) if fn is not None]


class ASTEngine:
    """
    Core AST & Call Topology Engine (`module:ast`).
    """

    CONSUMER_ID = "ast"

    def __init__(
        self,
        project_root: Optional[Union[str, Path]] = None,
        storage_dir: Optional[Union[str, Path]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
        space_manager: Optional[FileSpaceManager] = None,
        scanner: Optional[FingerprintScanner] = None,
        parser_registry: Optional[ParserRegistry] = None,
        custom_spaces: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else self._resolve_default_project_root()
        self._custom_storage_dir = storage_dir is not None
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = _resolve_default_ast_storage_dir(self.project_root)

        self.indices_dir = self.storage_dir / "indices"
        self.bundles_dir = self.storage_dir / "bundles"
        self.indices_dir.mkdir(parents=True, exist_ok=True)
        self.bundles_dir.mkdir(parents=True, exist_ok=True)

        self.symbols_index_path = self.indices_dir / "unified.symbols.bin.gz"
        self.graph_index_path = self.indices_dir / "unified.graph.bin.gz"
        self.meta_index_path = self.indices_dir / "unified.meta.json"

        if space_manager is not None:
            self.space_manager = space_manager
        else:
            sm_kwargs: Dict[str, Any] = {"project_root": self.project_root}
            if custom_spaces:
                norm_spaces: Dict[str, Any] = {}
                for k, v in custom_spaces.items():
                    if isinstance(v, FileSpaceConfig):
                        norm_spaces[k] = {"include": [str(p) for p in v.include]}
                    elif isinstance(v, dict):
                        inc = v.get("include") or ([str(v["root"])] if "root" in v else [str(self.project_root)])
                        norm_spaces[k] = {"include": inc}
                    else:
                        norm_spaces[k] = {"include": [str(v)]}
                sm_kwargs["spaces_config"] = norm_spaces
            elif project_root is not None:
                default_proj = self._resolve_default_project_root()
                if self.project_root != default_proj:
                    default_sp_cfg: Dict[str, Any] = {"include": [str(self.project_root)]}
                    try:
                        rel_st = self.storage_dir.resolve().relative_to(self.project_root.resolve()).as_posix()
                        if rel_st and rel_st != ".":
                            default_sp_cfg["exclude"] = [f"{rel_st}/**", f"**/{rel_st}/**"]
                    except ValueError:
                        pass
                    sm_kwargs["spaces_config"] = {"default": default_sp_cfg}
                    sm_kwargs["contributed_spaces"] = {}
                    sm_kwargs["storage_root"] = self.storage_dir / "file_space"
            self.space_manager = FileSpaceManager(**sm_kwargs)

        self.scanner = scanner or FingerprintScanner(self.space_manager)
        self.parser_registry = parser_registry or ParserRegistry(
            register_defaults=True,
            contributes_data=contributes_data,
        )
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
            scanner=self.scanner,
            storage_dir=self.storage_dir,
        )
        self.snippet_extractor = SnippetExtractor(
            space_manager=self.space_manager,
            project_root=self.project_root,
        )
        self.formatter = ASTResultFormatter(workspace_root=self.project_root)

        self._snapshot: Optional[ASTSnapshot] = None
        self._graph: Optional[CallGraphIndex] = None
        self._symbols_mtime: float = 0.0
        self._graph_mtime: float = 0.0
        self._lock = threading.RLock()

    @staticmethod
    def _resolve_default_project_root() -> Path:
        return resolve_project_root()

    @contextmanager
    def _consume_space_diff(
        self,
        space_name: Optional[str] = None,
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]:
        if self.scanner is not None and hasattr(self.scanner, "consume_diff"):
            if auto_refresh is not None:
                with self.scanner.consume_diff(
                    space_name=space_name,
                    consumer_id=self.CONSUMER_ID,
                    auto_refresh=auto_refresh,
                ) as diff_res:
                    yield diff_res
            else:
                with self.scanner.consume_diff(
                    space_name=space_name,
                    consumer_id=self.CONSUMER_ID,
                ) as diff_res:
                    yield diff_res
        else:
            with consume_diff(space_name=space_name, consumer_id=self.CONSUMER_ID) as diff_res:
                yield diff_res

    def _reset_consumer_cursor(self, space_name: Optional[str] = None) -> None:
        try:
            if self.scanner is not None and hasattr(self.scanner, "reset_cursor"):
                self.scanner.reset_cursor(space_name=space_name, consumer_id=self.CONSUMER_ID)
            else:
                reset_cursor(space_name=space_name, consumer_id=self.CONSUMER_ID)
        except Exception as exc:
            logger.debug(f"Reset cursor for consumer='{self.CONSUMER_ID}' skipped: {exc}")

    @staticmethod
    def _build_file_to_symbol_ids(symbols: Dict[str, UnifiedSymbol]) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        for sid, sym in symbols.items():
            lst = mapping.setdefault(sym.file_path, [])
            if sid not in lst:
                lst.append(sid)
            for pf in (sym.metadata or {}).get("partial_files") or []:
                pf_lst = mapping.setdefault(str(pf), [])
                if sid not in pf_lst:
                    pf_lst.append(sid)
        return mapping

    def _collect_space_generations_and_files_map(
        self,
        spaces: Optional[List[str]] = None,
        incremental_detail: Optional[ScanDiffDetail] = None,
    ) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
        space_gens: Dict[str, int] = {}
        files_map: Dict[str, List[str]] = {}
        try:
            target_cfgs = self.bundler._resolve_target_spaces(spaces)
            cached_unique = getattr(self.bundler, "_last_bundle_unique_files", None)
            cached_spaces = getattr(self.bundler, "_last_bundle_spaces", set())
            existing_files_map = self._snapshot.files_map if self._snapshot is not None else {}

            for sp_cfg in target_cfgs:
                sp_name = sp_cfg.name
                snap_st = None
                if self.scanner is not None and hasattr(self.scanner, "_load_or_recover_state"):
                    try:
                        snap_st, _ = self.scanner._load_or_recover_state(sp_name)
                    except Exception:
                        snap_st = None

                rel_files: Optional[List[str]] = None
                if incremental_detail is not None:
                    if snap_st is not None and getattr(snap_st, "entries", None):
                        rel_from_snap: List[str] = []
                        for rel_k, fp_rec in snap_st.entries.items():
                            if getattr(fp_rec, "is_deleted", False):
                                continue
                            src_root_str = getattr(fp_rec, "source_root", "")
                            if src_root_str:
                                src_root = Path(src_root_str)
                                rel_from_snap.append(self.bundler._get_project_relpath(src_root / rel_k, src_root))
                            else:
                                rel_from_snap.append(str(rel_k).replace("\\", "/"))
                        rel_files = sorted(set(rel_from_snap))
                    elif sp_name in existing_files_map:
                        base_set = set(existing_files_map[sp_name])
                        del_norm = normalize_dirty_paths(incremental_detail.deleted)
                        if del_norm:
                            base_set = {p for p in base_set if not is_dirty_file_match(p, del_norm)}
                        if incremental_detail.added:
                            added_map = self.bundler._resolve_dirty_files_only(incremental_detail.added, [sp_cfg])
                            for _, (_, relp, sp_set) in added_map.items():
                                if sp_name in sp_set:
                                    base_set.add(relp)
                        rel_files = sorted(base_set)

                if rel_files is None and cached_unique is not None and sp_name in cached_spaces:
                    from_cache = [
                        relp for _, (_, relp, sp_set) in cached_unique.items() if sp_name in sp_set
                    ]
                    rel_files = sorted(set(from_cache))

                if rel_files is None:
                    walked = []
                    for _, f_path, base_dir in self.bundler._iter_space_eligible_files(sp_cfg):
                        walked.append(self.bundler._get_project_relpath(f_path, base_dir))
                    rel_files = sorted(set(walked))

                files_map[sp_name] = rel_files
                if self.scanner is not None and hasattr(self.scanner, "get_cursor_status"):
                    try:
                        st = self.scanner.get_cursor_status(sp_name, consumer_id=self.CONSUMER_ID)
                        if isinstance(st, dict):
                            space_gens[sp_name] = int(st.get("head_generation") or st.get("acked_generation") or 1)
                            continue
                    except Exception:
                        pass
                if snap_st is not None:
                    space_gens[sp_name] = int(
                        getattr(snap_st, "head_generation", getattr(snap_st, "generation", 1))
                    )
                    continue
                space_gens[sp_name] = 1
        except Exception as exc:
            logger.debug(f"Collecting space generations fallback: {exc}")
        return space_gens, files_map

    def _resolve_index_lock_path(self) -> Path:
        if self._custom_storage_dir:
            self.indices_dir.mkdir(parents=True, exist_ok=True)
            return self.indices_dir / ".ast_index.lock"
        from core import uri

        for scheme in ("ast.cache://.ast_index.lock", "cache://ast/.ast_index.lock"):
            try:
                res = uri.resolve(scheme, interactive=False)
                if res and not str(res).startswith("!undefined"):
                    lock_path = Path(str(res)).resolve()
                    lock_path.parent.mkdir(parents=True, exist_ok=True)
                    return lock_path
            except Exception:
                pass
        try:
            yscb_root = uri.resolve_yscb_root()
            if yscb_root:
                fallback = Path(yscb_root).resolve() / ".cache" / "ast" / ".ast_index.lock"
                fallback.parent.mkdir(parents=True, exist_ok=True)
                return fallback
        except Exception:
            pass
        fallback = self.indices_dir / ".ast_index.lock"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

    def _build_meta_payload(self, snapshot: ASTSnapshot) -> Dict[str, Any]:
        sym_mtime_ns = 0
        sym_size = 0
        if self.symbols_index_path.exists():
            st = self.symbols_index_path.stat()
            sym_mtime_ns = int(st.st_mtime_ns)
            sym_size = int(st.st_size)
        return {
            "ast_generation": int(snapshot.ast_generation),
            "space_generations": dict(snapshot.space_generations),
            "total_symbols": len(snapshot.symbols),
            "total_files": len(snapshot.file_to_symbol_ids),
            "symbols_mtime_ns": sym_mtime_ns,
            "symbols_size": sym_size,
        }

    def _atomic_write_meta(self, meta_payload: Dict[str, Any]) -> None:
        from core import vfs

        vfs.write_json(str(self.meta_index_path), meta_payload, indent=2, atomic=True)

    def _save_snapshot_and_graph(self, snapshot: ASTSnapshot, graph: CallGraphIndex) -> None:
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            atomic_save_gzip_pickle(self.symbols_index_path, snapshot.to_dict(), compresslevel=1)
            graph.save_binary(self.graph_index_path, compresslevel=1)
            try:
                meta_payload = self._build_meta_payload(snapshot)
                self._atomic_write_meta(meta_payload)
            except Exception as exc:
                logger.debug(f"Failed writing AST meta index: {exc}")
        self._snapshot = snapshot
        self._graph = graph
        if self.symbols_index_path.exists():
            self._symbols_mtime = self.symbols_index_path.stat().st_mtime
        if self.graph_index_path.exists():
            self._graph_mtime = self.graph_index_path.stat().st_mtime

    def _ensure_symbols_loaded(self, force_reload: bool = False) -> bool:
        if not self.symbols_index_path.exists():
            return False
        try:
            s_mtime = self.symbols_index_path.stat().st_mtime
            if force_reload or self._snapshot is None or s_mtime > self._symbols_mtime:
                raw = load_gzip_pickle(self.symbols_index_path, raise_on_missing=True)
                if not isinstance(raw, dict):
                    raise ASTCorruptedError("Corrupted ASTSnapshot payload")
                self._snapshot = ASTSnapshot.from_dict(raw)
                self._symbols_mtime = s_mtime
            return self._snapshot is not None
        except Exception as exc:
            logger.warning(f"Failed loading AST snapshot from disk: {exc}")
            return False

    def _ensure_graph_loaded(self, force_reload: bool = False) -> bool:
        if not self.graph_index_path.exists():
            return False
        try:
            g_mtime = self.graph_index_path.stat().st_mtime
            if force_reload or self._graph is None or g_mtime > self._graph_mtime:
                self._graph = CallGraphIndex.load_binary(self.graph_index_path)
                self._graph_mtime = g_mtime
            return self._graph is not None
        except Exception as exc:
            logger.warning(f"Failed loading AST call graph from disk: {exc}")
            return False

    def _ensure_loaded_from_disk(self, force_reload: bool = False) -> bool:
        if not self.symbols_index_path.exists() or not self.graph_index_path.exists():
            return False
        return self._ensure_symbols_loaded(force_reload=force_reload) and self._ensure_graph_loaded(
            force_reload=force_reload
        )

    def get_persisted_meta(self) -> Optional[Dict[str, Any]]:
        """Read lightweight AST generation/metadata without decompressing unified.symbols.bin.gz or unified.graph.bin.gz."""
        with self._lock:
            if not self.symbols_index_path.exists():
                return None
            try:
                sym_st = self.symbols_index_path.stat()
                if self._snapshot is not None and sym_st.st_mtime <= self._symbols_mtime:
                    return self._build_meta_payload(self._snapshot)
                if self.meta_index_path.exists():
                    meta = json.loads(self.meta_index_path.read_text(encoding="utf-8"))
                    if (
                        isinstance(meta, dict)
                        and meta.get("symbols_mtime_ns") == int(sym_st.st_mtime_ns)
                        and meta.get("symbols_size") == int(sym_st.st_size)
                    ):
                        return meta
                if self._ensure_symbols_loaded() and self._snapshot is not None:
                    meta_payload = self._build_meta_payload(self._snapshot)
                    try:
                        self._atomic_write_meta(meta_payload)
                    except Exception:
                        pass
                    return meta_payload
            except Exception as exc:
                logger.debug(f"get_persisted_meta fallback skipped: {exc}")
            return None

    def build_index(
        self,
        spaces: Optional[List[str]] = None,
        allow_parallel: bool = True,
    ) -> ASTSnapshot:
        """
        Full AST index build across all (or specified) spaces:
        1. Parse files & aggregate C# `partial` symbols via `SemanticBundler`.
        2. Extract call sites & imports and build `CallGraphIndex` via `TopologyLinker`.
        3. Increment `ast_generation`, align `file-space` cursor (`consumer="ast"`), and persist binaries.
        """
        with self._lock:
            prev_gen = 0
            if self._snapshot is not None:
                prev_gen = self._snapshot.ast_generation
            elif self.symbols_index_path.exists():
                try:
                    old_raw = load_gzip_pickle(self.symbols_index_path, raise_on_missing=False)
                    if isinstance(old_raw, dict):
                        prev_gen = int(old_raw.get("ast_generation", 0))
                except Exception:
                    prev_gen = 0

            bundle = self.bundler.bundle_union(spaces=spaces, allow_parallel=allow_parallel)
            symbols_map: Dict[str, UnifiedSymbol] = {s.id: s for s in bundle.symbols}

            call_sites, imports_map = self.bundler.extract_all_call_sites_and_imports(spaces=spaces)
            linker = TopologyLinker(symbols_map=symbols_map)
            graph_idx = linker.build_graph(call_sites=call_sites, imports_map=imports_map)

            try:
                target_sp = spaces[0] if (spaces and len(spaces) == 1) else None
                with self._consume_space_diff(space_name=target_sp):
                    pass
            except Exception as exc:
                logger.debug(f"Cursor alignment after build_index skipped: {exc}")

            space_gens, files_map = self._collect_space_generations_and_files_map(spaces=spaces)
            snapshot = ASTSnapshot(
                ast_generation=prev_gen + 1,
                space_generations=space_gens,
                symbols=symbols_map,
                file_to_symbol_ids=self._build_file_to_symbol_ids(symbols_map),
                files_map=files_map,
                created_at=time.time(),
            )
            self._save_snapshot_and_graph(snapshot, graph_idx)
            return snapshot

    @staticmethod
    def _coerce_diff_detail(diff_input: Any) -> ScanDiffDetail:
        if isinstance(diff_input, ScanDiffDetail):
            return ScanDiffDetail(
                added=set(diff_input.added),
                modified=set(diff_input.modified),
                deleted=set(diff_input.deleted),
            )
        if hasattr(diff_input, "detail") and isinstance(diff_input.detail, ScanDiffDetail):
            return ScanDiffDetail(
                added=set(diff_input.detail.added),
                modified=set(diff_input.detail.modified),
                deleted=set(diff_input.detail.deleted),
            )
        if isinstance(diff_input, dict):
            if "spaces" in diff_input and isinstance(diff_input["spaces"], dict):
                diff_input = diff_input["spaces"]
            # Support either `{added, modified, deleted}` or `{space_name: {added, modified, deleted}}`
            if any(k in diff_input for k in ("added", "modified", "deleted", "dirty_files")):
                added = set(diff_input.get("added") or [])
                modified = set(diff_input.get("modified") or [])
                deleted = set(diff_input.get("deleted") or [])
                return ScanDiffDetail(added=added, modified=modified, deleted=deleted)
            added_all: Set[str] = set()
            modified_all: Set[str] = set()
            deleted_all: Set[str] = set()
            for sub in diff_input.values():
                if isinstance(sub, dict):
                    added_all.update(sub.get("added") or [])
                    modified_all.update(sub.get("modified") or [])
                    deleted_all.update(sub.get("deleted") or [])
            return ScanDiffDetail(added=added_all, modified=modified_all, deleted=deleted_all)
        return ScanDiffDetail(
            added=set(getattr(diff_input, "added", []) or []),
            modified=set(getattr(diff_input, "modified", []) or []),
            deleted=set(getattr(diff_input, "deleted", []) or []),
        )

    def _evict_dirty_and_reaggregate_partials(
        self,
        detail: ScanDiffDetail,
        spaces: Optional[List[str]] = None,
    ) -> Tuple[List[UnifiedSymbol], Set[str], Dict[str, Tuple[str, str, str]], List[Tuple[str, str, Optional[SymbolCallSite]]]]:
        """
        Parse dirty files, capture incoming edges before eviction, restore surviving C# partial siblings,
        evict old symbols, and re-aggregate partial types into `self._snapshot.symbols`.
        """
        assert self._snapshot is not None
        assert self._graph is not None

        new_symbols_by_file, dirty_keys = self.bundler.bundle_dirty_files(detail, spaces=spaces)
        all_new_symbols: List[UnifiedSymbol] = []
        for syms in new_symbols_by_file.values():
            all_new_symbols.extend(syms)

        dirty_paths_norm = normalize_dirty_paths(dirty_keys)
        old_doc_ids: Set[str] = set()
        old_symbol_info: Dict[str, Tuple[str, str, str]] = {}

        if self._snapshot.file_to_symbol_ids:
            for f_path_key, sids in list(self._snapshot.file_to_symbol_ids.items()):
                if is_dirty_file_match(f_path_key, dirty_paths_norm):
                    for doc_id in sids:
                        sym = self._snapshot.symbols.get(doc_id)
                        if sym is not None:
                            if is_dirty_file_match(sym.file_path, dirty_paths_norm):
                                old_doc_ids.add(doc_id)
                                old_symbol_info[doc_id] = (
                                    sym.file_path,
                                    sym.name,
                                    sym.fqn or sym.name,
                                )
                        else:
                            old_doc_ids.add(doc_id)
                    self._snapshot.file_to_symbol_ids.pop(f_path_key, None)
        else:
            for doc_id, sym in list(self._snapshot.symbols.items()):
                if is_dirty_file_match(sym.file_path, dirty_paths_norm):
                    old_doc_ids.add(doc_id)
                    old_symbol_info[doc_id] = (
                        sym.file_path,
                        sym.name,
                        sym.fqn or sym.name,
                    )

        affected_cs_keys: Set[Tuple[str, str, str]] = set()
        for doc_id in old_doc_ids:
            sym_old = self._snapshot.symbols.get(doc_id)
            if sym_old:
                ck = _cs_partial_type_key(sym_old)
                if ck:
                    affected_cs_keys.add(ck)
        for sym_new in all_new_symbols:
            ck = _cs_partial_type_key(sym_new)
            if ck:
                affected_cs_keys.add(ck)

        incoming_edges = self._graph.get_external_incoming_edges(old_doc_ids)

        surviving_partials: List[UnifiedSymbol] = []
        if affected_cs_keys:
            for doc_id, sym_rem in list(self._snapshot.symbols.items()):
                if doc_id in old_doc_ids:
                    continue
                ck = _cs_partial_type_key(sym_rem)
                if ck and ck in affected_cs_keys:
                    surviving_partials.append(restore_unaggregated_partial_symbol(sym_rem))

        for doc_id in old_doc_ids:
            self._snapshot.symbols.pop(doc_id, None)

        if affected_cs_keys:
            reaggregated = aggregate_partial_symbols(surviving_partials + list(all_new_symbols))
            for sym in reaggregated:
                self._snapshot.symbols[sym.id] = sym
            all_new_symbols = reaggregated
        else:
            for sym in all_new_symbols:
                self._snapshot.symbols[sym.id] = sym

        return all_new_symbols, old_doc_ids, old_symbol_info, incoming_edges

    def _relink_and_reconnect_edges(
        self,
        detail: ScanDiffDetail,
        all_new_symbols: List[UnifiedSymbol],
        old_doc_ids: Set[str],
        old_symbol_info: Dict[str, Tuple[str, str, str]],
        incoming_edges: List[Tuple[str, str, Optional[SymbolCallSite]]],
        spaces: Optional[List[str]] = None,
    ) -> None:
        """Relink dirty call sites and reconnect preserved external incoming call edges in `self._graph`."""
        assert self._snapshot is not None
        assert self._graph is not None

        dirty_sites, dirty_imports = self.bundler.extract_dirty_call_sites_and_imports(detail, spaces=spaces)
        linker = TopologyLinker(symbols_map=self._snapshot.symbols)
        new_edges = linker.link_call_sites(dirty_sites, dirty_imports)

        reconnected_incoming_edges: List[Tuple[str, str, Optional[SymbolCallSite]]] = []
        new_syms_by_identity: Dict[Tuple[str, str], List[UnifiedSymbol]] = {}
        for sym in all_new_symbols:
            norm_p = sym.file_path.replace("\\", "/").lower()
            new_syms_by_identity.setdefault((norm_p, sym.name), []).append(sym)
            if sym.fqn:
                new_syms_by_identity.setdefault((norm_p, sym.fqn), []).append(sym)

        for caller_id, old_callee_id, site in incoming_edges:
            if caller_id not in self._snapshot.symbols:
                continue
            target_new_id: Optional[str] = None
            if old_callee_id in self._snapshot.symbols:
                target_new_id = old_callee_id
            elif old_callee_id in old_symbol_info:
                old_p, old_name, old_fqn = old_symbol_info[old_callee_id]
                old_norm_p = old_p.replace("\\", "/").lower()
                cands = (
                    new_syms_by_identity.get((old_norm_p, old_name))
                    or new_syms_by_identity.get((old_norm_p, old_fqn))
                    or []
                )
                if len(cands) == 1:
                    target_new_id = cands[0].id
                elif len(cands) > 1:
                    target_new_id = cands[0].id
                    if site is not None:
                        try:
                            resolved_id = linker.resolve_call_site(site)
                            if resolved_id and any(c.id == resolved_id for c in cands):
                                target_new_id = resolved_id
                        except Exception:
                            pass

            if not target_new_id and site is not None:
                try:
                    resolved_id = linker.resolve_call_site(site)
                    if resolved_id and resolved_id in self._snapshot.symbols:
                        target_new_id = resolved_id
                except Exception:
                    pass

            if target_new_id:
                reconnected_incoming_edges.append((caller_id, target_new_id, site))

        self._graph.patch_incremental(
            new_edges=new_edges + reconnected_incoming_edges,
            old_symbol_ids=old_doc_ids,
        )

    def hot_patch_index(
        self,
        diff_detail: Union[ScanDiffDetail, ScanDiffResult, Dict[str, Any]],
        spaces: Optional[List[str]] = None,
        _cursor_already_consumed: bool = False,
    ) -> ASTSnapshot:
        """
        Incremental Hot-Patching Pipeline:
        1. Evict dirty symbols, restore surviving C# partial siblings, and re-aggregate partial types.
        2. Relink dirty call sites and reconnect preserved external incoming edges.
        3. Increment `ast_generation`, align cursor, and atomically persist `ASTSnapshot` and `CallGraphIndex`.
        """
        with self._lock:
            if not self._ensure_loaded_from_disk():
                return self.build_index(spaces=spaces, allow_parallel=False)

            assert self._snapshot is not None
            assert self._graph is not None

            detail = self._coerce_diff_detail(diff_detail)
            if not detail.dirty_files and not detail.deleted:
                return self._snapshot

            try:
                all_new_symbols, old_doc_ids, old_symbol_info, incoming_edges = (
                    self._evict_dirty_and_reaggregate_partials(detail, spaces=spaces)
                )
                self._relink_and_reconnect_edges(
                    detail=detail,
                    all_new_symbols=all_new_symbols,
                    old_doc_ids=old_doc_ids,
                    old_symbol_info=old_symbol_info,
                    incoming_edges=incoming_edges,
                    spaces=spaces,
                )

                if not _cursor_already_consumed:
                    try:
                        target_sp = spaces[0] if (spaces and len(spaces) == 1) else None
                        with self._consume_space_diff(space_name=target_sp):
                            pass
                    except Exception as exc:
                        logger.debug(f"Cursor alignment after hot_patch_index skipped: {exc}")

                space_gens, files_map = self._collect_space_generations_and_files_map(
                    spaces=spaces, incremental_detail=detail
                )
                self._snapshot.ast_generation += 1
                self._snapshot.space_generations.update(space_gens)
                self._snapshot.files_map.update(files_map)
                self._snapshot.file_to_symbol_ids = self._build_file_to_symbol_ids(self._snapshot.symbols)
                self._snapshot.created_at = time.time()

                self._save_snapshot_and_graph(self._snapshot, self._graph)
                return self._snapshot
            except Exception as exc:
                logger.warning(f"Hot-patch failed ({exc}), falling back to full build_index.")
                return self.build_index(spaces=spaces, allow_parallel=False)

    def ensure_jit_synced(
        self,
        spaces: Optional[Union[str, List[str]]] = None,
        force: bool = False,
    ) -> ASTSnapshot:
        """
        Ensure the AST snapshot and call graph are JIT synchronized:
        - If `force=True` or snapshot files do not exist, runs full `build_index()`.
        - Otherwise consumes incremental diff via `scanner.consume_diff(consumer_id="ast")`
          and applies `hot_patch_index()` if any files changed.
        """
        with self._lock:
            norm_spaces: Optional[List[str]] = None
            if isinstance(spaces, str) and spaces.strip():
                norm_spaces = [s.strip() for s in spaces.split(",") if s.strip()]
            elif isinstance(spaces, (list, tuple)):
                norm_spaces = [str(s).strip() for s in spaces if str(s).strip()]

            if force or not (self.symbols_index_path.exists() and self.graph_index_path.exists()) or not self._ensure_symbols_loaded():
                return self.build_index(spaces=norm_spaces)

            target_sp = norm_spaces[0] if (norm_spaces and len(norm_spaces) == 1) else None
            try:
                with self._consume_space_diff(space_name=target_sp) as diff_res:
                    if diff_res and getattr(diff_res, "has_changes", False):
                        return self.hot_patch_index(
                            diff_res.detail,
                            spaces=norm_spaces,
                            _cursor_already_consumed=True,
                        )
            except Exception as exc:
                logger.debug(f"JIT diff check skipped: {exc}")

            assert self._snapshot is not None
            return self._snapshot

    def get_snapshot(self, auto_sync: bool = True) -> ASTSnapshot:
        """Return the current `ASTSnapshot` (triggering `ensure_jit_synced()` if `auto_sync=True`)."""
        with self._lock:
            if auto_sync:
                return self.ensure_jit_synced()
            if not self._ensure_symbols_loaded():
                raise ASTIndexNotFoundError(f"AST snapshot not found at {self.symbols_index_path}")
            assert self._snapshot is not None
            return self._snapshot

    def get_call_graph(self, auto_sync: bool = True) -> CallGraphIndex:
        """Return the current `CallGraphIndex`."""
        with self._lock:
            if auto_sync:
                self.ensure_jit_synced()
            if not self._ensure_graph_loaded():
                raise ASTIndexNotFoundError(f"AST call graph not found at {self.graph_index_path}")
            assert self._graph is not None
            return self._graph

    def _resolve_target_file(self, file_or_uri: str) -> Tuple[Path, str, str]:
        """Resolve `file_or_uri` to `(abs_path, rel_path, space_name)`."""
        raw = (file_or_uri or "").strip()
        if not raw:
            raise FileNotFoundError("Empty file path provided to outline().")

        loaded_spaces = (
            self.space_manager.get_all_spaces()
            if hasattr(self.space_manager, "get_all_spaces")
            else self.space_manager.load_spaces()
        )
        if "://" in raw:
            scheme, rest = raw.split("://", 1)
            rest_clean = rest.replace("\\", "/").lstrip("/")
            try:
                from core import uri

                resolved = uri.resolve(raw, interactive=False)
                if resolved and not str(resolved).startswith("!undefined"):
                    p = Path(str(resolved)).resolve()
                    if p.is_file():
                        rel = self.bundler._get_project_relpath(p, p.parent)
                        sp = scheme if scheme in loaded_spaces else "project"
                        return p, rel, sp
            except Exception:
                pass
            cand = (self.project_root / rest_clean).resolve()
            if cand.is_file():
                rel = self.bundler._get_project_relpath(cand, self.project_root)
                sp = scheme if scheme in loaded_spaces else "project"
                return cand, rel, sp

        p = Path(raw)
        if not p.is_absolute():
            cand = (self.project_root / p).resolve()
            if not cand.is_file():
                cand_cwd = (Path.cwd() / p).resolve()
                if cand_cwd.is_file():
                    cand = cand_cwd
            p = cand
        else:
            p = p.resolve()

        if not p.is_file():
            raise FileNotFoundError(f"Target file not found: '{file_or_uri}' (resolved: '{p}')")

        # Determine owning space and project-relative path
        rel_path = self.bundler._get_project_relpath(p, self.project_root)
        matched_space = "project"
        try:
            for sp_name, sp_cfg in loaded_spaces.items():
                for inc_root in self.space_manager.resolve_space_include(sp_name):
                    try:
                        p.relative_to(Path(inc_root).resolve())
                        matched_space = sp_name
                        break
                    except ValueError:
                        continue
        except Exception:
            pass

        return p, rel_path, matched_space

    def outline(
        self,
        file_or_uri: str,
        merged: bool = False,
        visibility: Optional[str] = None,
        binding: Optional[str] = None,
        member_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract hierarchical AST symbol outline for `file_or_uri` with optional orthogonal filters."""
        with self._lock:
            GrammarProvisioner.get_warnings(clear=True)
            active_filters = {
                k: str(v).strip().lower()
                for k, v in (("visibility", visibility), ("binding", binding), ("member_kind", member_kind))
                if v
            }
            try:
                abs_path, rel_path, space_name = self._resolve_target_file(file_or_uri)
            except FileNotFoundError:
                err_res: Dict[str, Any] = {
                    "file_path": str(file_or_uri), "language": "unknown", "merged": merged,
                    "symbols": [], "partial_siblings": {}, "warnings": [],
                    "error": f"File not found: {file_or_uri}",
                }
                if active_filters:
                    err_res["filters"] = active_filters
                return err_res

            content = abs_path.read_text(encoding="utf-8", errors="replace")
            file_symbols = self.parser_registry.parse_file(file_path=rel_path, content=content, space=space_name)
            file_symbols = ensure_unique_overload_ids(file_symbols, default_space=space_name)

            language = file_symbols[0].language if file_symbols else "unknown"
            if language == "unknown":
                ext = abs_path.suffix.lower()
                language = next((cfg.id for cfg in self.parser_registry.language_configs.values() if ext in cfg.extensions), "unknown")

            snapshot: Optional[ASTSnapshot] = None
            if any(_is_partial_symbol(s) for s in file_symbols):
                try:
                    snapshot = self.ensure_jit_synced()
                except Exception as exc:
                    logger.debug(f"Outline JIT sync skipped: {exc}")

            outline_nodes, partial_siblings_map = _build_outline_tree(
                file_symbols=file_symbols, snapshot=snapshot, rel_path=rel_path, merged=merged
            )
            outline_nodes = _filter_outline_nodes(outline_nodes, active_filters)

            return OutlineResult(
                file_path=rel_path, language=language, merged=merged,
                symbols=[n.to_dict() for n in outline_nodes],
                partial_siblings=partial_siblings_map,
                warnings=GrammarProvisioner.get_warnings(clear=False),
                filters=active_filters,
            ).to_dict()


    def callers(
        self,
        target_query: str,
        space: Optional[Union[str, List[str]]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
        snippet: bool = True,
        spaces: Optional[List[str]] = None,
        include_snippet: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Query upstream callers for `target_query` with automatic JIT synchronization."""
        with self._lock:
            eff_space = space if space is not None else spaces
            eff_snippet = include_snippet if include_snippet is not None else snippet
            snapshot = self.ensure_jit_synced(spaces=eff_space)
            graph = self.get_call_graph(auto_sync=False)
            return query_callers(
                target_query=target_query,
                symbols_map=snapshot.symbols,
                graph=graph,
                space=eff_space,
                ftypes=ftypes,
                snippet=eff_snippet,
                snippet_extractor=self.snippet_extractor,
            )

    def callees(
        self,
        target_query: str,
        space: Optional[Union[str, List[str]]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
        snippet: bool = True,
        spaces: Optional[List[str]] = None,
        include_snippet: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Query downstream callees for `target_query` with automatic JIT synchronization."""
        with self._lock:
            eff_space = space if space is not None else spaces
            eff_snippet = include_snippet if include_snippet is not None else snippet
            snapshot = self.ensure_jit_synced(spaces=eff_space)
            graph = self.get_call_graph(auto_sync=False)
            return query_callees(
                target_query=target_query,
                symbols_map=snapshot.symbols,
                graph=graph,
                space=eff_space,
                ftypes=ftypes,
                snippet=eff_snippet,
                snippet_extractor=self.snippet_extractor,
            )

    def impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[Union[str, List[str]]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
        spaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Perform N-hop reverse BFS impact analysis for `target_query` with automatic JIT synchronization."""
        with self._lock:
            eff_space = space if space is not None else spaces
            snapshot = self.ensure_jit_synced(spaces=eff_space)
            graph = self.get_call_graph(auto_sync=False)
            return query_impact(
                target_query=target_query,
                symbols_map=snapshot.symbols,
                graph=graph,
                depth=depth,
                space=eff_space,
                ftypes=ftypes,
            )

    def status(self, space: Optional[str] = None, space_name: Optional[str] = None) -> Dict[str, Any]:
        """Return AST index health, generation numbers, symbol/edge counts, and registered parsers."""
        with self._lock:
            target_space = space or space_name
            has_symbols = self.symbols_index_path.exists()
            has_graph = self.graph_index_path.exists()

            ast_gen = 0
            space_gens: Dict[str, int] = {}
            total_symbols = 0
            total_files = 0
            total_edges = 0

            if has_symbols and has_graph and self._ensure_loaded_from_disk():
                assert self._snapshot is not None
                assert self._graph is not None
                ast_gen = self._snapshot.ast_generation
                space_gens = dict(self._snapshot.space_generations)
                if target_space:
                    space_gens = {k: v for k, v in space_gens.items() if k == target_space}
                    total_symbols = sum(
                        1 for s in self._snapshot.symbols.values() if target_space in (s.spaces or [])
                    )
                    total_files = len(self._snapshot.files_map.get(target_space, []))
                else:
                    total_symbols = len(self._snapshot.symbols)
                    total_files = len(self._snapshot.file_to_symbol_ids)
                total_edges = self._graph.graph.number_of_edges()

            return {
                "storage_dir": str(self.storage_dir),
                "index_exists": bool(has_symbols and has_graph),
                "snapshot_exists": bool(has_symbols and has_graph),
                "has_symbols_index": has_symbols,
                "has_graph_index": has_graph,
                "ast_generation": ast_gen,
                "space_generations": space_gens,
                "total_symbols": total_symbols,
                "total_files": total_files,
                "total_edges": total_edges,
                "registered_languages": sorted(list(self.parser_registry.language_configs.keys())),
                "parser_load_errors": dict(self.parser_registry.load_errors),
            }

    def clean(self, space: Optional[str] = None, space_name: Optional[str] = None) -> Dict[str, Any]:
        """Remove persisted AST snapshot/graph caches and reset `file-space` cursor (`consumer='ast'`)."""
        target_space = space or space_name
        removed: List[str] = []

        with self._lock:
            self._snapshot = None
            self._graph = None
            self._symbols_mtime = 0.0
            self._graph_mtime = 0.0

            if target_space:
                b_file = self.bundles_dir / f"{target_space}.bundle.json"
                if b_file.exists():
                    b_file.unlink()
                    removed.append(str(b_file))
            else:
                for d in (self.indices_dir, self.bundles_dir):
                    if d.is_dir():
                        for item in d.iterdir():
                            if item.is_file():
                                item.unlink()
                                removed.append(str(item))
                            elif item.is_dir():
                                shutil.rmtree(item, ignore_errors=True)
                                removed.append(str(item))

            self._reset_consumer_cursor(space_name=target_space)

        return {
            "status": "cleaned",
            "space": target_space,
            "removed": removed,
        }


def get_engine(
    project_root: Optional[Union[str, Path]] = None,
    storage_dir: Optional[Union[str, Path]] = None,
    force_new: bool = False,
) -> ASTEngine:
    """Return process-level singleton `ASTEngine` (or create a new instance when custom paths are passed)."""
    global _DEFAULT_ENGINE_INSTANCE
    if not isinstance(ASTEngine, type):
        if project_root is not None or storage_dir is not None:
            return ASTEngine(project_root=project_root, storage_dir=storage_dir)
        return ASTEngine()
    if project_root is not None or storage_dir is not None or force_new:
        return ASTEngine(project_root=project_root, storage_dir=storage_dir)
    with _ENGINE_LOCK:
        if _DEFAULT_ENGINE_INSTANCE is None:
            _DEFAULT_ENGINE_INSTANCE = ASTEngine()
        return _DEFAULT_ENGINE_INSTANCE


def reset_default_engine() -> None:
    """Clear the process-level singleton `ASTEngine` instance."""
    global _DEFAULT_ENGINE_INSTANCE
    with _ENGINE_LOCK:
        _DEFAULT_ENGINE_INSTANCE = None


__all__ = [
    "ASTEngine",
    "_build_outline_tree",
    "_filter_outline_nodes",
    "_member_to_outline_node",
    "get_engine",
    "reset_default_engine",
]
