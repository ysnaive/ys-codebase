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

from contextlib import ExitStack, contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import time
import os
from typing import Any, Callable, Dict, FrozenSet, Iterator, List, Mapping, Optional, Sequence, Set, Tuple, Union

from core.context import (
    TaskCancelledError,
    cell_span,
    check_task_cancelled,
    get_env,
    get_runtime_context,
    get_virtual_cwd,
    is_foreground_active,
)
from core.log import ProgressReporter, log_debug, log_warn
from core.space import (
    ScanDiffDetail,
    ScanDiffResult,
    SpaceConfig,
    SpaceRegistry,
    SpaceScanner,
    consume_diff,
    get_default_registry,
    get_default_scanner,
    is_watcher_active,
    reset_cursor,
)

from .bundler import (
    SemanticBundler,
    _extract_unaggregated_partial_state,
    _is_partial_symbol,
    _preload_snap_entries,
    _resolve_default_ast_storage_dir,
    _space_logical_name,
    aggregate_partial_symbols,
    ensure_unique_overload_ids,
    restore_unaggregated_partial_symbol,
)
from .exceptions import ASTCorruptedError, ASTError, ASTIndexNotFoundError
from .formatter import ASTResultFormatter
from .graph import CallGraphIndex
from .io_utils import (
    normalize_source_bytes,
    read_normalized_source_file,
    atomic_save_gzip_pickle,
    is_dirty_file_match,
    load_gzip_pickle,
    normalize_dirty_paths,
    resolve_project_root,
)
from .linker import TopologyLinker, WorkspaceGraphLinker
from .parsers.base import compute_content_hash
from .parsers.registry import ParserRegistry
from .provisioner import GrammarProvisioner
from .resolver import (
    DeterministicSymbolResolver,
    SnippetExtractor,
    SymbolResolutionResult,
    _resolve_with_ftype_fallback,
    query_callees,
    query_callers,
    query_impact,
    select_workspace_nodes,
    traverse_workspace_edges,
)
from .schema import (
    ASTSnapshot,
    FileSymbolGraph,
    MemberInfo,
    OutlineNode,
    OutlineResult,
    Span,
    SymbolCallSite,
    SymbolKind,
    SymbolNode,
    UnifiedSymbol,
    WorkspaceSymbolGraph,
)

VALID_SLICE_PARTS: FrozenSet[str] = frozenset({
    "outer",
    "name",
    "signature",
    "parameters",
    "return_type",
    "doc",
    "body",
})

_ENGINE_LOCK = threading.RLock()


def _get_default_engine_instance() -> Optional["ASTEngine"]:
    return get_runtime_context().get_module_state("ast.engine.default_instance", lambda: None)


def _set_default_engine_instance(val: Optional["ASTEngine"]) -> None:
    get_runtime_context().set_module_state("ast.engine.default_instance", val)


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
        group_candidates = [
            s
            for s in candidates
            if not (sym_spaces and s.spaces and not sym_spaces.intersection(s.spaces))
        ]
        # Ensure current file symbol is included in aggregation pool if not already present
        if not any(
            s.file_path.replace("\\", "/").lower() == norm_this_path and s.line_number == sym.line_number
            for s in group_candidates
        ):
            group_candidates.append(sym)
        aggregated_group = aggregate_partial_symbols(group_candidates)
        matched_agg = next(
            (
                s
                for s in aggregated_group
                if s.file_path.replace("\\", "/").lower() == norm_this_path and s.line_number == sym.line_number
            ),
            aggregated_group[0] if aggregated_group else None,
        )
        if matched_agg is not None:
            agg_meta = matched_agg.metadata or {}
            siblings = [
                dict(loc)
                for loc in (agg_meta.get("partial_locations") or [])
                if str(loc.get("file_path", "")).replace("\\", "/").lower() != norm_this_path
                or int(loc.get("line_number", 0)) != sym.line_number
            ]
            if merged:
                for m in matched_agg.members:
                    m_node = _member_to_outline_node(m, default_line=matched_agg.line_number)
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
        space_manager: Optional[SpaceRegistry] = None,
        scanner: Optional[SpaceScanner] = None,
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
        self.build_state_path = self.indices_dir / ".ast_build_state.json"

        use_isolated_scanner = False
        if space_manager is not None:
            self.space_manager = space_manager
            if self._custom_storage_dir:
                use_isolated_scanner = True
        else:
            sm_kwargs: Dict[str, Any] = {"project_root": self.project_root}
            if custom_spaces:
                norm_spaces: Dict[str, Any] = {}
                for k, v in custom_spaces.items():
                    if isinstance(v, SpaceConfig):
                        norm_spaces[k] = {
                            "entries": [str(p) for p in v.entries],
                            "include": list(v.include),
                            "exclude": list(v.exclude),
                        }
                    elif isinstance(v, dict):
                        ents = (
                            v.get("entries")
                            or v.get("include")
                            or ([str(v["root"])] if "root" in v else [str(self.project_root)])
                        )
                        norm_spaces[k] = {
                            "entries": [str(p) for p in ents],
                            "include": list(v.get("patterns") or ["**/*"]),
                            "exclude": list(v.get("exclude") or []),
                        }
                    else:
                        norm_spaces[k] = {"entries": [str(v)]}
                sm_kwargs["raw_spaces"] = norm_spaces
                use_isolated_scanner = True
                self.space_manager = SpaceRegistry(**sm_kwargs)
            elif project_root is not None:
                default_sp_cfg: Dict[str, Any] = {
                    "entries": [str(self.project_root)],
                    "exclude": [".ast_store*", ".ast_index.lock"],
                }
                try:
                    rel_st = self.storage_dir.resolve().relative_to(self.project_root.resolve()).as_posix()
                    if rel_st and rel_st != ".":
                        default_sp_cfg["exclude"].extend([rel_st, f"{rel_st}/**", f"**/{rel_st}/**"])
                except ValueError:
                    pass
                sm_kwargs["raw_spaces"] = {"default": default_sp_cfg}
                use_isolated_scanner = True
                self.space_manager = SpaceRegistry(**sm_kwargs)
            else:
                self.space_manager = get_default_registry(project_root=self.project_root)

        if scanner is not None:
            self.scanner = scanner
        elif use_isolated_scanner or self._custom_storage_dir:
            self.scanner = SpaceScanner(
                registry=self.space_manager,
                storage_root=self.storage_dir / "space",
            )
        elif space_manager is None and not custom_spaces and project_root is None:
            self.scanner = get_default_scanner(project_root=self.project_root)
        else:
            self.scanner = SpaceScanner(registry=self.space_manager)

        self.parser_registry = parser_registry or ParserRegistry(
            register_defaults=True,
            contributes_data=contributes_data,
            space_manager=self.space_manager,
        )
        if getattr(self.parser_registry, "_space_manager", None) is None:
            self.parser_registry._space_manager = self.space_manager
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
            scanner=self.scanner,
            storage_dir=self.storage_dir,
            contributes_data=contributes_data,
        )
        self.snippet_extractor = SnippetExtractor(
            space_manager=self.space_manager,
            project_root=self.project_root,
        )
        self.formatter = ASTResultFormatter(workspace_root=self.project_root)

        self._snapshot: Optional[ASTSnapshot] = None
        self._graph: Optional[CallGraphIndex] = None
        self._last_workspace_graph: Optional[WorkspaceSymbolGraph] = None
        self._symbols_mtime: float = 0.0
        self._graph_mtime: float = 0.0
        self._lock = threading.RLock()
        self._bg_persist_lock = threading.Lock()
        self._bg_persist_pending: Optional[Tuple[ASTSnapshot, CallGraphIndex, int]] = None
        self._bg_persist_seq: int = 0
        self._bg_persist_executor: Optional[Any] = None
        self._bg_persist_running: bool = False
        self._build_state_lock = threading.Lock()
        self._build_state: Dict[str, Any] = {
            "building": False,
            "phase": "idle",
            "progress": "",
            "started_at": 0.0,
        }

    def register_spaces(self, spaces: Any) -> List[str]:
        """Register one or more target `core.space` names into this `ASTEngine` instance."""
        if isinstance(spaces, str):
            spaces = [s.strip() for s in spaces.split(",") if s.strip()]
        return self.bundler.register_spaces(spaces)

    def get_target_spaces(self) -> List[str]:
        """Return deduplicated logical/qualified target space names managed by `ASTEngine`."""
        return self.bundler.get_target_space_names()

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
                    space_name,
                    consumer_id=self.CONSUMER_ID,
                    auto_refresh=auto_refresh,
                ) as diff_res:
                    yield diff_res
            else:
                with self.scanner.consume_diff(
                    space_name,
                    consumer_id=self.CONSUMER_ID,
                ) as diff_res:
                    yield diff_res
        else:
            with consume_diff(space_name, consumer_id=self.CONSUMER_ID) as diff_res:
                yield diff_res

    def _align_consumer_cursors(self, spaces: Optional[List[str]] = None) -> None:
        """Align `core.space` consumer cursors for `spaces` (only acknowledging `None` when `spaces is None`)."""
        try:
            use_non_blocking_diff = bool(
                not self._custom_storage_dir
                and getattr(self.bundler.space_manager, "_raw_spaces", None) is None
                and is_watcher_active(project_root=self.project_root)
            )
            target_cfgs = self.bundler._resolve_target_spaces(spaces)
            target_qnames = (
                [sp.qualified_name or sp.short_name for sp in target_cfgs if (sp.qualified_name or sp.short_name)]
                if use_non_blocking_diff
                else []
            )
            if not target_qnames:
                if spaces is None:
                    with self._consume_space_diff(space_name=None):
                        pass
                    if self.scanner is not None and hasattr(self.scanner, "ack"):
                        for sp in target_cfgs:
                            for sp_k in {sp.qualified_name, sp.short_name}:
                                if sp_k:
                                    self.scanner.ack(sp_k, consumer_id=self.CONSUMER_ID)
                else:
                    for sp_name in spaces:
                        with self._consume_space_diff(space_name=sp_name):
                            pass
            else:
                batch_ctx = (
                    self.scanner.cursor_store.batch_cursor_updates(self.CONSUMER_ID)
                    if (
                        self.scanner is not None
                        and hasattr(self.scanner, "cursor_store")
                        and hasattr(self.scanner.cursor_store, "batch_cursor_updates")
                    )
                    else nullcontext()
                )
                with batch_ctx:
                    for q_sp in target_qnames:
                        with self._consume_space_diff(space_name=q_sp, auto_refresh=False):
                            pass
                    if self.scanner is not None and hasattr(self.scanner, "ack"):
                        for sp in target_cfgs:
                            if sp.short_name and sp.short_name != sp.qualified_name:
                                self.scanner.ack(sp.short_name, consumer_id=self.CONSUMER_ID)
                        if spaces is None:
                            self.scanner.ack(None, consumer_id=self.CONSUMER_ID)
        except Exception as exc:
            log_debug(f"Cursor alignment skipped: {exc}")

    def _reset_consumer_cursor(self, space_name: Optional[str] = None) -> None:
        try:
            if self.scanner is not None and hasattr(self.scanner, "reset_cursor"):
                self.scanner.reset_cursor(space_name, consumer_id=self.CONSUMER_ID)
            else:
                reset_cursor(space_name, consumer_id=self.CONSUMER_ID)
        except Exception as exc:
            log_debug(f"Reset cursor for consumer='{self.CONSUMER_ID}' skipped: {exc}")

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
        target_snap: Optional[ASTSnapshot] = None,
    ) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
        space_gens: Dict[str, int] = {}
        files_map: Dict[str, List[str]] = {}
        try:
            target_cfgs = self.bundler._resolve_target_spaces(spaces)
            cached_unique = getattr(self.bundler, "_last_bundle_unique_files", None)
            cached_spaces = getattr(self.bundler, "_last_bundle_spaces", set())
            snap_ref = target_snap if target_snap is not None else self._snapshot
            existing_files_map = snap_ref.files_map if snap_ref is not None else {}

            for sp_cfg in target_cfgs:
                sp_name = _space_logical_name(sp_cfg)
                q_name = sp_cfg.qualified_name or sp_name
                snap_entries = None
                snap_gen = 1
                need_entries_from_snap = not (
                    incremental_detail is not None and sp_name in existing_files_map
                )
                if self.scanner is not None:
                    if not need_entries_from_snap and hasattr(self.scanner, "get_snapshot_summary"):
                        try:
                            head_g, _ = self.scanner.get_snapshot_summary(q_name)
                            if head_g > 0:
                                snap_gen = int(head_g)
                        except Exception:
                            pass
                    elif hasattr(self.scanner, "_load_snapshot_state"):
                        try:
                            st = self.scanner._load_snapshot_state(q_name)
                            if st is not None:
                                snap_entries = getattr(st, "entries", None)
                                snap_gen = int(
                                    getattr(st, "head_generation", 0)
                                    or getattr(st, "generation", 0)
                                    or 0
                                )
                        except Exception:
                            snap_entries = None
                    if need_entries_from_snap and not snap_entries and hasattr(self.scanner, "snapshot"):
                        try:
                            snap_entries = self.scanner.snapshot(q_name, refresh_first=False)
                        except Exception:
                            snap_entries = None

                rel_files: Optional[List[str]] = None
                if incremental_detail is not None:
                    if sp_name in existing_files_map:
                        base_set = set(existing_files_map[sp_name])
                        if incremental_detail.deleted:
                            expanded_del = self.bundler._normalize_space_dirty_paths(
                                incremental_detail.deleted,
                                [sp_cfg],
                                prefer_missing=True,
                                known_indexed_files=base_set,
                            )
                            del_norm = normalize_dirty_paths(expanded_del | set(incremental_detail.deleted))
                            if del_norm:
                                base_set = {p for p in base_set if not is_dirty_file_match(p, del_norm)}
                        if incremental_detail.added:
                            added_map = self.bundler._resolve_dirty_files_only(incremental_detail.added, [sp_cfg])
                            for _, (_, relp, sp_set) in added_map.items():
                                if sp_name in sp_set:
                                    base_set.add(relp)
                        rel_files = sorted(base_set)
                    elif snap_entries:
                        rel_from_snap: List[str] = []
                        for rel_k, fp_rec in snap_entries.items():
                            if getattr(fp_rec, "is_deleted", False):
                                continue
                            src_root_str = getattr(fp_rec, "entry_path", "") or getattr(fp_rec, "source_root", "")
                            if src_root_str:
                                src_root = Path(src_root_str)
                                rel_from_snap.append(self.bundler._get_project_relpath(src_root / rel_k, src_root))
                            else:
                                rel_from_snap.append(str(rel_k).replace("\\", "/"))
                        rel_files = sorted(set(rel_from_snap))

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
                if self.scanner is not None and hasattr(self.scanner, "cursor_store"):
                    try:
                        acked_raw = self.scanner.cursor_store.get_cursor(q_name, self.CONSUMER_ID)
                        if isinstance(acked_raw, dict):
                            acked_gen = int(
                                acked_raw.get("acked_generation", acked_raw.get("acked_gen", 0)) or 0
                            )
                        else:
                            acked_gen = int(acked_raw or 0)
                        space_gens[sp_name] = int(snap_gen or acked_gen or 1)
                        continue
                    except Exception:
                        pass
                space_gens[sp_name] = int(snap_gen or 1)
        except Exception as exc:
            log_debug(f"Collecting space generations fallback: {exc}")
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

    def _compute_ast_config_hash(self) -> str:
        """Compute deterministic fingerprint covering AST schema version and parser language configurations."""
        try:
            lang_cfgs = getattr(self.parser_registry, "language_configs", {}) or {}
            items = []
            for k in sorted(lang_cfgs.keys()):
                cfg = lang_cfgs[k]
                exts = sorted(getattr(cfg, "extensions", ()) or ())
                sps = sorted(getattr(cfg, "spaces", ()) or ())
                q_file = str(getattr(cfg, "query_file", "") or "")
                items.append((str(k), exts, sps, q_file))
            raw = json.dumps({"schema": 2, "langs": items}, sort_keys=True, separators=(",", ":"))
            return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()
        except Exception:
            return "v2"

    def _build_meta_payload(
        self,
        snapshot: ASTSnapshot,
        graph: Optional[CallGraphIndex] = None,
    ) -> Dict[str, Any]:
        sym_mtime_ns = 0
        sym_size = 0
        if self.symbols_index_path.exists():
            st = self.symbols_index_path.stat()
            sym_mtime_ns = int(st.st_mtime_ns)
            sym_size = int(st.st_size)
        graph_mtime_ns = 0
        graph_size = 0
        if self.graph_index_path.exists():
            gst = self.graph_index_path.stat()
            graph_mtime_ns = int(gst.st_mtime_ns)
            graph_size = int(gst.st_size)
        eff_graph = graph if graph is not None else self._graph
        total_edges = int(eff_graph.graph.number_of_edges()) if eff_graph is not None else 0
        space_symbol_counts: Dict[str, int] = {}
        for sym in snapshot.symbols.values():
            for sp in (sym.spaces or ()):
                space_symbol_counts[sp] = space_symbol_counts.get(sp, 0) + 1
        space_file_counts: Dict[str, int] = {
            sp: len(files) for sp, files in snapshot.files_map.items()
        }
        return {
            "ast_generation": int(snapshot.ast_generation),
            "space_generations": dict(snapshot.space_generations),
            "total_symbols": len(snapshot.symbols),
            "total_files": len(snapshot.file_to_symbol_ids),
            "total_edges": total_edges,
            "space_symbol_counts": space_symbol_counts,
            "space_file_counts": space_file_counts,
            "symbols_mtime_ns": sym_mtime_ns,
            "symbols_size": sym_size,
            "graph_mtime_ns": graph_mtime_ns,
            "graph_size": graph_size,
            "schema_version": int(getattr(snapshot, "schema_version", 2)),
            "config_hash": str(getattr(snapshot, "config_hash", "") or self._compute_ast_config_hash()),
        }

    def _atomic_write_meta(self, meta_payload: Dict[str, Any]) -> None:
        from core import vfs

        vfs.write_json(str(self.meta_index_path), meta_payload, indent=2, atomic=True)

    def _persist_snapshot_and_graph_to_disk(self, snapshot: ASTSnapshot, graph: CallGraphIndex, seq: int = 0) -> None:
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            if seq > 0 and seq != self._bg_persist_seq:
                return
            atomic_save_gzip_pickle(self.symbols_index_path, snapshot.to_dict(), compresslevel=1)
            graph.save_binary(self.graph_index_path, compresslevel=1)
            try:
                meta_payload = self._build_meta_payload(snapshot, graph=graph)
                self._atomic_write_meta(meta_payload)
            except Exception as exc:
                log_debug(f"Failed writing AST meta index: {exc}")
        with self._bg_persist_lock:
            if seq == 0 or seq == self._bg_persist_seq:
                if self.symbols_index_path.exists():
                    self._symbols_mtime = self.symbols_index_path.stat().st_mtime
                if self.graph_index_path.exists():
                    self._graph_mtime = self.graph_index_path.stat().st_mtime

    def _run_bg_persist_loop(self) -> None:
        while True:
            time.sleep(0.05)
            with self._bg_persist_lock:
                if self._bg_persist_pending is None:
                    self._bg_persist_running = False
                    return
            try:
                if is_foreground_active():
                    continue
            except Exception:
                pass
            with self._bg_persist_lock:
                pending = self._bg_persist_pending
                if pending is None:
                    self._bg_persist_running = False
                    return
                self._bg_persist_pending = None
            snap_p, graph_p, seq_p = pending
            try:
                self._persist_snapshot_and_graph_to_disk(snap_p, graph_p, seq=seq_p)
            except Exception as exc:
                log_debug(f"Background AST snapshot persist skipped: {exc}")

    def _save_snapshot_and_graph(
        self,
        snapshot: ASTSnapshot,
        graph: CallGraphIndex,
        allow_async_in_worker: bool = False,
    ) -> None:
        if not getattr(snapshot, "config_hash", ""):
            snapshot.config_hash = self._compute_ast_config_hash()
        snapshot.schema_version = 2
        graph.ast_generation = int(snapshot.ast_generation)
        self._snapshot = snapshot
        self._graph = graph
        if graph.workspace_graph is not None:
            self._last_workspace_graph = graph.workspace_graph

        if (
            allow_async_in_worker
            and not self._custom_storage_dir
            and get_env("YSCB_IN_SERVER_WORKER") == "1"
            and self.symbols_index_path.exists()
            and self.graph_index_path.exists()
        ):
            from concurrent.futures import ThreadPoolExecutor

            far_future = time.time() + 3600.0
            self._symbols_mtime = far_future
            self._graph_mtime = far_future
            with self._bg_persist_lock:
                self._bg_persist_seq += 1
                self._bg_persist_pending = (snapshot, graph, self._bg_persist_seq)
                if not self._bg_persist_running:
                    self._bg_persist_running = True
                    if self._bg_persist_executor is None:
                        self._bg_persist_executor = ThreadPoolExecutor(
                            max_workers=1,
                            thread_name_prefix="AST-BgPersist",
                        )
                    self._bg_persist_executor.submit(self._run_bg_persist_loop)
            return

        with self._bg_persist_lock:
            self._bg_persist_seq += 1
            self._bg_persist_pending = None
        self._persist_snapshot_and_graph_to_disk(snapshot, graph, seq=0)

    def _set_build_progress(self, building: bool, phase: str = "idle", progress: str = "") -> None:
        now = time.time()
        with self._build_state_lock:
            started = float(self._build_state.get("started_at", 0.0) or 0.0) if building else 0.0
            if building and started <= 0.0:
                started = now
            self._build_state = {
                "building": bool(building),
                "phase": str(phase if building else "idle"),
                "progress": str(progress if building else ""),
                "started_at": started,
            }
        try:
            from core import vfs

            if building:
                vfs.write_json(
                    str(self.build_state_path),
                    {
                        "building": True,
                        "pid": os.getpid(),
                        "phase": str(phase),
                        "progress": str(progress),
                        "started_at": started,
                        "updated_at": now,
                    },
                    indent=None,
                    atomic=True,
                )
            elif self.build_state_path.exists():
                vfs.remove(str(self.build_state_path), missing_ok=True)
        except Exception:
            pass

    def _probe_build_in_progress(self) -> Tuple[bool, str, str]:
        with self._build_state_lock:
            if self._build_state.get("building"):
                return (
                    True,
                    str(self._build_state.get("phase") or "building"),
                    str(self._build_state.get("progress") or ""),
                )
        if not self._lock.acquire(blocking=False):
            return (True, "building", "持有引擎鎖建構中")
        self._lock.release()
        if self.build_state_path.is_file():
            try:
                from core import vfs
                from core.platform import is_process_alive

                raw_bs = vfs.read_json(str(self.build_state_path))
                if isinstance(raw_bs, dict) and raw_bs.get("building"):
                    pid = int(raw_bs.get("pid", 0) or 0)
                    if pid > 0 and (pid == os.getpid() or is_process_alive(pid)):
                        return (
                            True,
                            str(raw_bs.get("phase") or "building"),
                            str(raw_bs.get("progress") or ""),
                        )
                    vfs.remove(str(self.build_state_path), missing_ok=True)
            except Exception:
                pass
        try:
            from core.platform.lock import InterProcessLock

            lock_p = self._resolve_index_lock_path()
            if lock_p.is_file():
                probe = InterProcessLock(str(lock_p), timeout=0.0)
                if not probe.acquire(blocking=False):
                    return (True, "persisting", "正在原子寫入 AST 索引快照")
                probe.release()
        except Exception:
            pass
        return (False, "idle", "")

    def _load_symbols_unlocked(self, force_reload: bool = False) -> bool:
        if not self.symbols_index_path.exists():
            self._snapshot = None
            self._symbols_mtime = 0.0
            return False
        try:
            s_mtime = self.symbols_index_path.stat().st_mtime
            if force_reload or self._snapshot is None or s_mtime > self._symbols_mtime:
                raw = load_gzip_pickle(self.symbols_index_path, raise_on_missing=True)
                if not isinstance(raw, dict):
                    raise ASTCorruptedError("Corrupted ASTSnapshot payload")
                self._snapshot = ASTSnapshot.from_dict(raw)
                self._symbols_mtime = s_mtime
                if self._graph is not None and self._snapshot is not None and self._snapshot.file_graphs:
                    self._graph.attach_file_graphs(self._snapshot.file_graphs)
            return self._snapshot is not None
        except Exception as exc:
            log_warn(f"Failed loading AST snapshot from disk: {exc}", stream="stderr")
            return False

    def _load_graph_unlocked(self, force_reload: bool = False) -> bool:
        if not self.graph_index_path.exists():
            self._graph = None
            self._graph_mtime = 0.0
            return False
        try:
            g_mtime = self.graph_index_path.stat().st_mtime
            if force_reload or self._graph is None or g_mtime > self._graph_mtime:
                snap_fgs = self._snapshot.file_graphs if self._snapshot is not None else None
                self._graph = CallGraphIndex.load_binary(self.graph_index_path, file_graphs=snap_fgs)
                self._graph_mtime = g_mtime
            elif self._graph is not None and self._snapshot is not None and self._snapshot.file_graphs:
                self._graph.attach_file_graphs(self._snapshot.file_graphs)
            if self._graph is not None and self._graph.workspace_graph is not None:
                self._last_workspace_graph = self._graph.workspace_graph
            return self._graph is not None
        except Exception as exc:
            log_warn(f"Failed loading AST call graph from disk: {exc}", stream="stderr")
            return False

    def _ensure_symbols_loaded(self, force_reload: bool = False) -> bool:
        if not self.symbols_index_path.exists():
            self._snapshot = None
            self._symbols_mtime = 0.0
            return False
        try:
            s_mtime = self.symbols_index_path.stat().st_mtime
        except OSError:
            return False
        if not (force_reload or self._snapshot is None or s_mtime > self._symbols_mtime):
            return True
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            return self._load_symbols_unlocked(force_reload=force_reload)

    def _ensure_graph_loaded(self, force_reload: bool = False) -> bool:
        if not self.graph_index_path.exists():
            self._graph = None
            self._graph_mtime = 0.0
            return False
        try:
            g_mtime = self.graph_index_path.stat().st_mtime
        except OSError:
            return False
        need_graph = force_reload or self._graph is None or g_mtime > self._graph_mtime
        need_gen_sync = (
            self._snapshot is not None
            and self._graph is not None
            and getattr(self._graph, "ast_generation", 0) > 0
            and int(self._graph.ast_generation) != int(self._snapshot.ast_generation)
        )
        if not (need_graph or need_gen_sync):
            if self._graph is not None and self._snapshot is not None and self._snapshot.file_graphs:
                self._graph.attach_file_graphs(self._snapshot.file_graphs)
            return True
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            if not self._load_graph_unlocked(force_reload=force_reload or need_gen_sync):
                return False
            if (
                self._snapshot is not None
                and self._graph is not None
                and getattr(self._graph, "ast_generation", 0) > 0
                and int(self._graph.ast_generation) != int(self._snapshot.ast_generation)
            ):
                self._load_symbols_unlocked(force_reload=True)
                self._load_graph_unlocked(force_reload=True)
                if (
                    self._snapshot is not None
                    and self._graph is not None
                    and getattr(self._graph, "ast_generation", 0) > 0
                    and int(self._graph.ast_generation) != int(self._snapshot.ast_generation)
                ):
                    self._graph = None
                    return False
            return self._graph is not None

    def _ensure_loaded_from_disk(self, force_reload: bool = False) -> bool:
        if not self.symbols_index_path.exists() or not self.graph_index_path.exists():
            if self._symbols_mtime > 0.0 or self._graph_mtime > 0.0:
                self._snapshot = None
                self._graph = None
                self._symbols_mtime = 0.0
                self._graph_mtime = 0.0
            return False
        try:
            s_mtime = self.symbols_index_path.stat().st_mtime
            g_mtime = self.graph_index_path.stat().st_mtime
        except OSError:
            return False
        gen_mismatch = (
            self._snapshot is not None
            and self._graph is not None
            and getattr(self._graph, "ast_generation", 0) > 0
            and int(self._graph.ast_generation) != int(self._snapshot.ast_generation)
        )
        need_load = (
            force_reload
            or self._snapshot is None
            or self._graph is None
            or s_mtime > self._symbols_mtime
            or g_mtime > self._graph_mtime
            or gen_mismatch
        )
        if not need_load:
            return True
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            ok_s = self._load_symbols_unlocked(force_reload=force_reload or gen_mismatch)
            ok_g = self._load_graph_unlocked(force_reload=force_reload or gen_mismatch)
            if not (ok_s and ok_g):
                return False
            if (
                self._snapshot is not None
                and self._graph is not None
                and getattr(self._graph, "ast_generation", 0) > 0
                and int(self._graph.ast_generation) != int(self._snapshot.ast_generation)
            ):
                self._graph = None
                return False
            return True

    def get_persisted_meta(self) -> Optional[Dict[str, Any]]:
        """Read lightweight AST generation/metadata without mutating disk files (lock-free fast path)."""
        if not self.symbols_index_path.exists():
            return None
        try:
            sym_st = self.symbols_index_path.stat()
            snap_ref = self._snapshot
            if snap_ref is not None and sym_st.st_mtime <= self._symbols_mtime:
                return self._build_meta_payload(snap_ref, graph=self._graph)
            if self.meta_index_path.exists():
                meta = json.loads(self.meta_index_path.read_text(encoding="utf-8"))
                if (
                    isinstance(meta, dict)
                    and meta.get("symbols_mtime_ns") == int(sym_st.st_mtime_ns)
                    and meta.get("symbols_size") == int(sym_st.st_size)
                ):
                    return meta
            if self._lock.acquire(blocking=False):
                try:
                    if self._ensure_symbols_loaded() and self._snapshot is not None:
                        return self._build_meta_payload(self._snapshot, graph=self._graph)
                finally:
                    self._lock.release()
        except Exception as exc:
            log_debug(f"get_persisted_meta fallback skipped: {exc}")
        return None

    def build_index(
        self,
        spaces: Optional[List[str]] = None,
        allow_parallel: bool = True,
    ) -> ASTSnapshot:
        """
        Full AST index build across all (or specified) spaces:
        1. Parse files & aggregate C# `partial` symbols via `SemanticBundler`.
        2. Extract call sites & imports and build `CallGraphIndex` via `TopologyLinker` + `WorkspaceGraphLinker`.
        3. Increment `ast_generation`, align `file-space` cursor (`consumer="ast"`), and persist binaries.
        """
        with self._lock:
            prog = ProgressReporter("ast", "正在建構 AST 符號與呼叫圖譜", total_stages=3)
            self._set_build_progress(True, "parsing", "準備掃描並解析檔案")
            try:
                prev_gen = 0
                if self._snapshot is not None:
                    prev_gen = self._snapshot.ast_generation
                elif self.meta_index_path.exists():
                    try:
                        prev_gen = int(json.loads(self.meta_index_path.read_text(encoding="utf-8")).get("ast_generation", 0))
                    except Exception:
                        prev_gen = 0
                elif self.symbols_index_path.exists():
                    try:
                        old_raw = load_gzip_pickle(self.symbols_index_path, raise_on_missing=False)
                        if isinstance(old_raw, dict):
                            prev_gen = int(old_raw.get("ast_generation", 0))
                    except Exception:
                        prev_gen = 0
                gen_floor_file = self.indices_dir / ".ast_generation_floor"
                if gen_floor_file.exists():
                    try:
                        prev_gen = max(prev_gen, int(gen_floor_file.read_text(encoding="utf-8").strip() or "0"))
                    except Exception:
                        pass

                prog.stage(1, "解析檔案")

                def _on_parse_prog(rel_p: str, cur: int, tot: int) -> None:
                    prog.advance(cur, tot)
                    if cur == 1 or cur == tot or (cur & 31) == 0:
                        self._set_build_progress(True, "parsing", f"解析檔案 {cur}/{tot}")

                bundle = self.bundler.bundle_union(
                    spaces=spaces,
                    progress_callback=_on_parse_prog,
                    allow_parallel=allow_parallel,
                )
                symbols_map: Dict[str, UnifiedSymbol] = {s.id: s for s in bundle.symbols}
                file_graphs = self.bundler.extract_all_file_graphs(spaces=spaces)

                prog.stage(2, "連結呼叫與型別拓撲", 0, len(file_graphs))
                self._set_build_progress(True, "linking", f"連結跨檔拓撲 (共 {len(symbols_map)} 符號)")
                call_sites, imports_map = self.bundler.extract_all_call_sites_and_imports(spaces=spaces)
                linker = TopologyLinker(symbols_map=symbols_map)
                graph_idx = linker.build_graph(call_sites=call_sites, imports_map=imports_map)
                try:
                    ws_linker = WorkspaceGraphLinker(
                        file_graphs=file_graphs.values(),
                        language_configs=self.parser_registry.language_configs,
                        module_resolvers=self.parser_registry.module_resolvers,
                        edge_refiners=self.parser_registry.edge_refiners,
                    )

                    def _on_link_prog(cur_fg: int, tot_fg: int) -> None:
                        prog.advance(cur_fg, tot_fg)
                        if cur_fg == 1 or cur_fg == tot_fg or (cur_fg & 31) == 0:
                            self._set_build_progress(True, "linking", f"連結呼叫圖譜 {cur_fg}/{tot_fg}")

                    graph_idx.workspace_graph = ws_linker.link_workspace(progress_callback=_on_link_prog)
                except Exception as ws_exc:
                    log_debug(f"WorkspaceGraphLinker in build_index skipped: {ws_exc}")

                prog.stage(3, "持久化索引快照與同步游標")
                self._set_build_progress(True, "persisting", "寫入索引快照與元數據")
                space_gens, files_map = self._collect_space_generations_and_files_map(spaces=spaces)
                self.bundler.clear_transient_caches()
                file_to_sids = self._build_file_to_symbol_ids(symbols_map)
                snapshot = ASTSnapshot(
                    ast_generation=prev_gen + 1,
                    space_generations=space_gens,
                    symbols=symbols_map,
                    file_to_symbol_ids=file_to_sids,
                    files_map=files_map,
                    created_at=time.time(),
                    file_graphs=file_graphs,
                )
                self._save_snapshot_and_graph(snapshot, graph_idx)
                self._align_consumer_cursors(spaces=spaces)
                prog.finish(f"AST 圖譜建構完成 (共 {len(file_to_sids)} 檔, {len(symbols_map)} 符號)")
                return snapshot
            finally:
                self.bundler.clear_transient_caches()
                self._set_build_progress(False)

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
        if isinstance(diff_input, (list, tuple, set, frozenset)):
            return ScanDiffDetail(modified={str(p) for p in diff_input if p})
        return ScanDiffDetail(
            added=set(getattr(diff_input, "added", []) or []),
            modified=set(getattr(diff_input, "modified", []) or []),
            deleted=set(getattr(diff_input, "deleted", []) or []),
        )

    def _evict_dirty_and_reaggregate_partials(
        self,
        detail: ScanDiffDetail,
        spaces: Optional[List[str]] = None,
        known_indexed_files: Optional[Set[str]] = None,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        target_snap: Optional[ASTSnapshot] = None,
        target_graph: Optional[CallGraphIndex] = None,
    ) -> Tuple[
        List[UnifiedSymbol],
        Set[str],
        Dict[str, Tuple[str, str, str]],
        List[Tuple[str, str, Optional[SymbolCallSite]]],
        Set[str],
        Set[str],
    ]:
        """
        Parse dirty files, capture incoming edges before eviction, restore surviving C# partial siblings,
        evict old symbols, and re-aggregate partial types into `target_snap.symbols`.
        """
        snap_obj = target_snap if target_snap is not None else self._snapshot
        graph_obj = target_graph if target_graph is not None else self._graph
        assert snap_obj is not None
        assert graph_obj is not None

        if known_indexed_files is None:
            known_indexed_files = set(snap_obj.file_to_symbol_ids.keys()) | set(snap_obj.file_graphs.keys())

        new_symbols_by_file, dirty_keys = self.bundler.bundle_dirty_files(
            detail,
            spaces=spaces,
            known_indexed_files=known_indexed_files,
            snap_entries_by_space=snap_entries_by_space,
            progress_callback=progress_callback,
        )
        all_new_symbols: List[UnifiedSymbol] = []
        for syms in new_symbols_by_file.values():
            all_new_symbols.extend(syms)

        dirty_paths_norm = normalize_dirty_paths(dirty_keys)
        old_doc_ids: Set[str] = set()
        old_symbol_info: Dict[str, Tuple[str, str, str]] = {}

        if snap_obj.file_to_symbol_ids:
            for f_path_key, sids in list(snap_obj.file_to_symbol_ids.items()):
                if is_dirty_file_match(f_path_key, dirty_paths_norm):
                    for doc_id in sids:
                        sym = snap_obj.symbols.get(doc_id)
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
                    snap_obj.file_to_symbol_ids.pop(f_path_key, None)
        else:
            for doc_id, sym in list(snap_obj.symbols.items()):
                if is_dirty_file_match(sym.file_path, dirty_paths_norm):
                    old_doc_ids.add(doc_id)
                    old_symbol_info[doc_id] = (
                        sym.file_path,
                        sym.name,
                        sym.fqn or sym.name,
                    )

        affected_cs_keys: Set[Tuple[str, str, str]] = set()
        for doc_id in old_doc_ids:
            sym_old = snap_obj.symbols.get(doc_id)
            if sym_old:
                ck = _cs_partial_type_key(sym_old)
                if ck:
                    affected_cs_keys.add(ck)
        for sym_new in all_new_symbols:
            ck = _cs_partial_type_key(sym_new)
            if ck:
                affected_cs_keys.add(ck)

        surviving_partials: List[UnifiedSymbol] = []
        surviving_sibling_files: Set[str] = set()
        if affected_cs_keys:
            for doc_id, sym_rem in list(snap_obj.symbols.items()):
                if doc_id in old_doc_ids:
                    continue
                ck = _cs_partial_type_key(sym_rem)
                if ck and ck in affected_cs_keys:
                    surviving_partials.append(restore_unaggregated_partial_symbol(sym_rem))
                    if sym_rem.file_path:
                        surviving_sibling_files.add(sym_rem.file_path)

        # Include symbols in surviving partial sibling files so their outgoing call edges are refreshed
        if surviving_sibling_files:
            sib_norm = normalize_dirty_paths(surviving_sibling_files)
            for doc_id, sym_s in snap_obj.symbols.items():
                if doc_id not in old_doc_ids and is_dirty_file_match(sym_s.file_path, sib_norm):
                    old_doc_ids.add(doc_id)
                    old_symbol_info[doc_id] = (
                        sym_s.file_path,
                        sym_s.name,
                        sym_s.fqn or sym_s.name,
                    )

        incoming_edges = graph_obj.get_external_incoming_edges(old_doc_ids)

        for doc_id in old_doc_ids:
            # Only pop symbols that belong to dirty files (keep surviving_partials & sibling symbols in snapshot)
            if doc_id in snap_obj.symbols and is_dirty_file_match(
                snap_obj.symbols[doc_id].file_path, dirty_paths_norm
            ):
                snap_obj.symbols.pop(doc_id, None)

        if affected_cs_keys:
            reaggregated = aggregate_partial_symbols(surviving_partials + list(all_new_symbols))
            for sym in reaggregated:
                snap_obj.symbols[sym.id] = sym
            all_new_symbols = reaggregated
        else:
            for sym in all_new_symbols:
                snap_obj.symbols[sym.id] = sym

        for sym in all_new_symbols:
            if sym.file_path:
                f_list = snap_obj.file_to_symbol_ids.setdefault(sym.file_path, [])
                if sym.id not in f_list:
                    f_list.append(sym.id)

        # Also include surviving sibling symbols in `all_new_symbols` so incoming edges to them reconnect cleanly
        if surviving_sibling_files:
            sib_norm = normalize_dirty_paths(surviving_sibling_files)
            existing_new_ids = {s.id for s in all_new_symbols}
            for s_id, s_obj in snap_obj.symbols.items():
                if s_id not in existing_new_ids and is_dirty_file_match(s_obj.file_path, sib_norm):
                    all_new_symbols.append(s_obj)

        return (
            all_new_symbols,
            old_doc_ids,
            old_symbol_info,
            incoming_edges,
            dirty_keys,
            surviving_sibling_files,
        )

    def _relink_and_reconnect_edges(
        self,
        detail: ScanDiffDetail,
        all_new_symbols: List[UnifiedSymbol],
        old_doc_ids: Set[str],
        old_symbol_info: Dict[str, Tuple[str, str, str]],
        incoming_edges: List[Tuple[str, str, Optional[SymbolCallSite]]],
        spaces: Optional[List[str]] = None,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
        surviving_sibling_files: Optional[Set[str]] = None,
        target_snap: Optional[ASTSnapshot] = None,
        target_graph: Optional[CallGraphIndex] = None,
    ) -> None:
        """Relink dirty call sites and reconnect preserved external incoming call edges in `target_graph`."""
        snap_obj = target_snap if target_snap is not None else self._snapshot
        graph_obj = target_graph if target_graph is not None else self._graph
        assert snap_obj is not None
        assert graph_obj is not None

        relink_detail = (
            ScanDiffDetail(
                added=set(detail.added),
                modified=set(detail.modified) | set(surviving_sibling_files),
                deleted=set(detail.deleted),
            )
            if surviving_sibling_files
            else detail
        )
        dirty_sites, dirty_imports = self.bundler.extract_dirty_call_sites_and_imports(
            relink_detail,
            spaces=spaces,
            snap_entries_by_space=snap_entries_by_space,
        )
        linker = TopologyLinker(symbols_map=snap_obj.symbols)
        new_edges = linker.link_call_sites(dirty_sites, dirty_imports)

        reconnected_incoming_edges: List[Tuple[str, str, Optional[SymbolCallSite]]] = []
        new_syms_by_identity: Dict[Tuple[str, str], List[UnifiedSymbol]] = {}
        for sym in all_new_symbols:
            norm_p = sym.file_path.replace("\\", "/").lower()
            new_syms_by_identity.setdefault((norm_p, sym.name), []).append(sym)
            if sym.fqn:
                new_syms_by_identity.setdefault((norm_p, sym.fqn), []).append(sym)

        for caller_id, old_callee_id, site in incoming_edges:
            if caller_id not in snap_obj.symbols:
                continue
            target_new_id: Optional[str] = None
            if old_callee_id in snap_obj.symbols:
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

            if not target_new_id and site is not None and old_callee_id not in old_symbol_info:
                # Only attempt same-file/import-aware resolution when the old callee was not explicitly deleted
                # from its defining file (prevents grafting calls to deleted symbols onto unrelated same-name functions).
                try:
                    resolved_id = linker.resolve_call_site(site)
                    if resolved_id and resolved_id in snap_obj.symbols:
                        target_new_id = resolved_id
                except Exception:
                    pass

            if target_new_id:
                if caller_id == target_new_id:
                    caller_sym = snap_obj.symbols.get(caller_id)
                    caller_kind = (
                        caller_sym.kind.value
                        if caller_sym and isinstance(caller_sym.kind, SymbolKind)
                        else (str(caller_sym.kind) if caller_sym else "")
                    )
                    if caller_kind not in ("function", "method", "constructor"):
                        continue
                reconnected_incoming_edges.append((caller_id, target_new_id, site))

        graph_obj.patch_incremental(
            new_edges=new_edges + reconnected_incoming_edges,
            old_symbol_ids=old_doc_ids,
        )

    def hot_patch_index(
        self,
        diff_detail: Union[ScanDiffDetail, ScanDiffResult, Dict[str, Any]],
        spaces: Optional[List[str]] = None,
        _cursor_already_consumed: bool = False,
        _hydrate_workspace_graph: bool = False,
    ) -> ASTSnapshot:
        """
        Incremental Hot-Patching Pipeline:
        1. Evict dirty symbols, restore surviving C# partial siblings, and re-aggregate partial types.
        2. Relink dirty call sites and reconnect preserved external incoming edges.
        3. Increment `ast_generation`, align cursor, and atomically persist `ASTSnapshot` and `CallGraphIndex`.
        """
        # Disk load and disk persistence acquire .ast_index.lock internally; avoid holding the file lock
        # across Copy-on-Write parsing or cursor alignment to prevent lock-order inversions.
        with self._lock:
            if not self._ensure_loaded_from_disk():
                return self.build_index(spaces=spaces, allow_parallel=False)

            assert self._snapshot is not None
            assert self._graph is not None

            detail = self._coerce_diff_detail(diff_detail)
            if not detail.dirty_files and not detail.deleted:
                return self._snapshot

            # True Copy-on-Write clones: keep self._snapshot and self._graph untouched until atomic publication
            orig_snap_ref = self._snapshot
            if self._graph.workspace_graph is not None:
                self._last_workspace_graph = self._graph.workspace_graph
            working_snap = ASTSnapshot(
                ast_generation=orig_snap_ref.ast_generation,
                space_generations=dict(orig_snap_ref.space_generations),
                symbols=dict(orig_snap_ref.symbols),
                file_to_symbol_ids={k: list(v) for k, v in orig_snap_ref.file_to_symbol_ids.items()},
                files_map={k: list(v) for k, v in orig_snap_ref.files_map.items()},
                created_at=orig_snap_ref.created_at,
                file_graphs=dict(orig_snap_ref.file_graphs),
                schema_version=2,
                config_hash=self._compute_ast_config_hash(),
            )
            working_graph = self._graph.clone_shallow()

            prog = ProgressReporter("ast", "正在增量熱修補 AST 圖譜", total_stages=2)
            dirty_est = len(detail.dirty_files) + len(detail.deleted)
            self._set_build_progress(True, "hot_patching", f"增量修補 {dirty_est} 個變更檔案")
            persisted = False
            try:
                prog.stage(1, "解析變更檔案", 0, max(1, len(detail.dirty_files)))
                with cell_span("ast.hp_preload"):
                    target_cfgs = self.bundler._resolve_target_spaces(spaces)
                    snap_entries_by_space = _preload_snap_entries(self.scanner, target_cfgs)
                    known_indexed_files = set(working_snap.file_to_symbol_ids.keys()) | set(working_snap.file_graphs.keys())

                with cell_span("ast.hp_evict"):
                    (
                        all_new_symbols,
                        old_doc_ids,
                        old_symbol_info,
                        incoming_edges,
                        dirty_keys,
                        surviving_sibling_files,
                    ) = self._evict_dirty_and_reaggregate_partials(
                        detail,
                        spaces=spaces,
                        known_indexed_files=known_indexed_files,
                        snap_entries_by_space=snap_entries_by_space,
                        progress_callback=lambda _rel, cur, tot: prog.advance(cur, tot),
                        target_snap=working_snap,
                        target_graph=working_graph,
                    )
                prog.stage(2, "重連呼叫邊與更新工作區圖譜")
                with cell_span("ast.hp_relink"):
                    self._relink_and_reconnect_edges(
                        detail=detail,
                        all_new_symbols=all_new_symbols,
                        old_doc_ids=old_doc_ids,
                        old_symbol_info=old_symbol_info,
                        incoming_edges=incoming_edges,
                        spaces=spaces,
                        snap_entries_by_space=snap_entries_by_space,
                        surviving_sibling_files=surviving_sibling_files,
                        target_snap=working_snap,
                        target_graph=working_graph,
                    )
                try:
                    with cell_span("ast.hp_dirty_fg"):
                        dirty_fgs, dirty_fg_keys = self.bundler.extract_dirty_file_graphs(
                            detail,
                            spaces=spaces,
                            known_indexed_files=known_indexed_files,
                            snap_entries_by_space=snap_entries_by_space,
                        )
                        dirty_fg_norm = normalize_dirty_paths(dirty_fg_keys | dirty_keys)
                        for fg_key in list(working_snap.file_graphs.keys()):
                            if is_dirty_file_match(fg_key, dirty_fg_norm):
                                working_snap.file_graphs.pop(fg_key, None)
                        working_snap.file_graphs.update(dirty_fgs)
                        working_graph.attach_file_graphs(working_snap.file_graphs)
                    if _hydrate_workspace_graph and working_snap.file_graphs:
                        with cell_span("ast.hp_ws_link"):
                            ws_linker = WorkspaceGraphLinker(
                                file_graphs=working_snap.file_graphs.values(),
                                language_configs=self.parser_registry.language_configs,
                                module_resolvers=self.parser_registry.module_resolvers,
                                edge_refiners=self.parser_registry.edge_refiners,
                                prev_workspace_graph=self._last_workspace_graph,
                            )
                            ws_graph = ws_linker.link_workspace()
                            working_graph.workspace_graph = ws_graph
                            self._last_workspace_graph = ws_graph
                    else:
                        working_graph.workspace_graph = None
                except Exception as ws_exc:
                    log_debug(f"FileSymbolGraph update in hot_patch_index skipped: {ws_exc}")

                with cell_span("ast.hp_space_gens"):
                    space_gens, files_map = self._collect_space_generations_and_files_map(
                        spaces=spaces, incremental_detail=detail, target_snap=working_snap
                    )
                self.bundler.clear_transient_caches()
                working_snap.ast_generation += 1
                working_snap.space_generations.update(space_gens)
                working_snap.files_map.update(files_map)
                if not working_snap.file_to_symbol_ids:
                    working_snap.file_to_symbol_ids = self._build_file_to_symbol_ids(working_snap.symbols)
                working_snap.created_at = time.time()

                with cell_span("ast.hp_save"):
                    self._save_snapshot_and_graph(
                        working_snap,
                        working_graph,
                        allow_async_in_worker=True,
                    )
                persisted = True
                if not _cursor_already_consumed:
                    self._align_consumer_cursors(spaces=spaces)
                prog.finish(f"AST 增量熱修補完成 (變更 {len(dirty_keys)} 項)")
                return self._snapshot
            except Exception as exc:
                self._snapshot = None
                self._graph = None
                self._symbols_mtime = 0.0
                self._graph_mtime = 0.0
                log_warn(f"Hot-patch failed ({exc}), falling back to full build_index.", stream="stderr")
                rebuilt = self.build_index(spaces=spaces, allow_parallel=False)
                persisted = True
                return rebuilt
            finally:
                if not persisted:
                    self._snapshot = None
                    self._graph = None
                    self._symbols_mtime = 0.0
                    self._graph_mtime = 0.0
                self.bundler.clear_transient_caches()
                self._set_build_progress(False)


    def ensure_jit_synced(
        self,
        spaces: Optional[Union[str, List[str]]] = None,
        force: bool = False,
        allow_parallel: bool = True,
        _hydrate_workspace_graph: bool = False,
    ) -> ASTSnapshot:
        """
        Ensure the AST snapshot and call graph are JIT synchronized:
        - If `force=True` or snapshot files do not exist, runs full `build_index()`.
        - Otherwise consumes incremental diff via `scanner.consume_diff(consumer_id="ast")`
          strictly across target spaces and applies `hot_patch_index()` inside the transactional
          consumption scope so the cursor is only committed after patching succeeds.
        """
        with cell_span("ast.jit_sync"), self._lock:
            norm_spaces: Optional[List[str]] = None
            if isinstance(spaces, str) and spaces.strip():
                norm_spaces = [s.strip() for s in spaces.split(",") if s.strip()]
            elif isinstance(spaces, (list, tuple)):
                norm_spaces = [str(s).strip() for s in spaces if str(s).strip()]

            all_configured_cfgs: List[SpaceConfig] = []
            try:
                all_configured_cfgs = list(self.bundler._resolve_target_spaces(None) or [])
            except Exception:
                all_configured_cfgs = []
            full_build_spaces = None if all_configured_cfgs else norm_spaces

            if force or not (self.symbols_index_path.exists() and self.graph_index_path.exists()) or not self._ensure_symbols_loaded():
                return self.build_index(spaces=full_build_spaces, allow_parallel=allow_parallel)

            expected_cfg_hash = self._compute_ast_config_hash()
            if self._snapshot is not None and getattr(self._snapshot, "config_hash", "") not in ("", expected_cfg_hash):
                return self.build_index(spaces=full_build_spaces, allow_parallel=allow_parallel)

            try:
                req_cfgs = self.bundler._resolve_target_spaces(norm_spaces) if norm_spaces else all_configured_cfgs
                combined_cfgs = list(all_configured_cfgs) + [
                    sp for sp in (req_cfgs or []) if sp not in all_configured_cfgs
                ]
                if self._snapshot is not None and isinstance(self._snapshot.space_generations, dict) and combined_cfgs:
                    expected_keys: Set[str] = set()
                    for sp in combined_cfgs:
                        if sp.short_name:
                            expected_keys.add(sp.short_name)
                        if sp.qualified_name:
                            expected_keys.add(sp.qualified_name)
                    stale_space_keys = [
                        k for k in self._snapshot.space_generations.keys() if k not in expected_keys
                    ]
                    missing_cfg_space = bool(
                        norm_spaces is None
                        and all_configured_cfgs
                        and any(
                            (sp.short_name not in self._snapshot.space_generations)
                            and (sp.qualified_name not in self._snapshot.space_generations)
                            for sp in all_configured_cfgs
                        )
                    )
                    if stale_space_keys or missing_cfg_space:
                        return self.build_index(spaces=full_build_spaces, allow_parallel=allow_parallel)
            except Exception:
                pass

            use_non_blocking_diff = bool(
                not self._custom_storage_dir
                and getattr(self.bundler.space_manager, "_raw_spaces", None) is None
                and is_watcher_active(project_root=self.project_root)
            )
            try:
                target_cfgs = self.bundler._resolve_target_spaces(norm_spaces)
                target_qnames = (
                    [
                        sp.qualified_name or sp.short_name
                        for sp in target_cfgs
                        if (sp.qualified_name or sp.short_name)
                    ]
                    if use_non_blocking_diff
                    else []
                )
                eff_auto_refresh = False if use_non_blocking_diff else None
                merged_added: Set[str] = set()
                merged_modified: Set[str] = set()
                merged_deleted: Set[str] = set()

                with ExitStack() as diff_stack:
                    if (
                        self.scanner is not None
                        and hasattr(self.scanner, "cursor_store")
                        and hasattr(self.scanner.cursor_store, "batch_cursor_updates")
                    ):
                        diff_stack.enter_context(
                            self.scanner.cursor_store.batch_cursor_updates(self.CONSUMER_ID)
                        )
                    if not target_qnames:
                        if norm_spaces is None:
                            diff_res = diff_stack.enter_context(
                                self._consume_space_diff(
                                    space_name=None,
                                    auto_refresh=eff_auto_refresh,
                                )
                            )
                            if diff_res and getattr(diff_res, "has_changes", False):
                                merged_added.update(diff_res.detail.added)
                                merged_modified.update(diff_res.detail.modified)
                                merged_deleted.update(diff_res.detail.deleted)
                        else:
                            for sp_n in norm_spaces:
                                diff_res = diff_stack.enter_context(
                                    self._consume_space_diff(
                                        space_name=sp_n,
                                        auto_refresh=eff_auto_refresh,
                                    )
                                )
                                if diff_res and getattr(diff_res, "has_changes", False):
                                    merged_added.update(diff_res.detail.added)
                                    merged_modified.update(diff_res.detail.modified)
                                    merged_deleted.update(diff_res.detail.deleted)
                    else:
                        with cell_span("ast.diff_loop"):
                            if self.scanner is not None and hasattr(
                                self.scanner, "_flush_in_process_watcher"
                            ):
                                self.scanner._flush_in_process_watcher(target_qnames)
                            for q_sp in target_qnames:
                                diff_res = diff_stack.enter_context(
                                    self._consume_space_diff(
                                        space_name=q_sp,
                                        auto_refresh=eff_auto_refresh,
                                    )
                                )
                                if diff_res and getattr(diff_res, "has_changes", False):
                                    merged_added.update(diff_res.detail.added)
                                    merged_modified.update(diff_res.detail.modified)
                                    merged_deleted.update(diff_res.detail.deleted)

                    all_dirty = merged_added | merged_modified | merged_deleted
                    if all_dirty:
                        if self._snapshot is not None:
                            raw_known_files: Set[str] = (
                                set(self._snapshot.file_to_symbol_ids.keys())
                                | set(self._snapshot.file_graphs.keys())
                            )
                            for flist in (self._snapshot.files_map or {}).values():
                                if flist:
                                    raw_known_files.update(flist)
                            known_norm = normalize_dirty_paths(raw_known_files)
                        else:
                            known_norm = set()
                        has_parseable = any(
                            self.parser_registry.get_parser(str(p)) is not None
                            or (known_norm and is_dirty_file_match(str(p), known_norm))
                            for p in all_dirty
                        )
                        if has_parseable:
                            combined_detail = ScanDiffDetail(
                                added=merged_added,
                                modified=merged_modified,
                                deleted=merged_deleted,
                            )
                            with cell_span("ast.hot_patch"):
                                patched_snap = self.hot_patch_index(
                                    combined_detail,
                                    spaces=full_build_spaces,
                                    _cursor_already_consumed=True,
                                    _hydrate_workspace_graph=_hydrate_workspace_graph,
                                )
                            with cell_span("ast.align_cursors"):
                                if self.scanner is not None and hasattr(self.scanner, "ack"):
                                    for sp in target_cfgs:
                                        if sp.short_name and sp.short_name not in target_qnames:
                                            self.scanner.ack(sp.short_name, consumer_id=self.CONSUMER_ID)
                                        if sp.qualified_name and sp.qualified_name not in target_qnames:
                                            self.scanner.ack(sp.qualified_name, consumer_id=self.CONSUMER_ID)
                                    if full_build_spaces is None:
                                        self.scanner.ack(None, consumer_id=self.CONSUMER_ID)
                            return patched_snap
                    if self.scanner is not None and hasattr(self.scanner, "ack"):
                        for sp in target_cfgs:
                            if sp.short_name and sp.short_name not in target_qnames:
                                self.scanner.ack(sp.short_name, consumer_id=self.CONSUMER_ID)
                            if sp.qualified_name and sp.qualified_name not in target_qnames:
                                self.scanner.ack(sp.qualified_name, consumer_id=self.CONSUMER_ID)
                        if norm_spaces is None:
                            self.scanner.ack(None, consumer_id=self.CONSUMER_ID)
            except TaskCancelledError:
                raise
            except Exception as exc:
                log_debug(f"JIT diff check skipped: {exc}")

            if self._snapshot is None:
                return self.build_index(spaces=full_build_spaces, allow_parallel=allow_parallel)
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

    def get_workspace_graph(self, auto_sync: bool = True) -> WorkspaceSymbolGraph:
        """L1 Primitive: Return the current immutable `WorkspaceSymbolGraph`."""
        with self._lock:
            if auto_sync:
                self.ensure_jit_synced(_hydrate_workspace_graph=True)
                if not self._ensure_graph_loaded():
                    raise ASTIndexNotFoundError(f"AST call graph not found at {self.graph_index_path}")
            else:
                self._ensure_loaded_from_disk()
                if self._snapshot is None:
                    raise ASTIndexNotFoundError(f"AST index not found at {self.graph_index_path}")
                if self._graph is None:
                    self._graph = CallGraphIndex()
            assert self._snapshot is not None
            assert self._graph is not None
            if self._graph.workspace_graph is not None:
                if self._snapshot.file_graphs and not self._graph.workspace_graph.file_graphs:
                    self._graph.attach_file_graphs(self._snapshot.file_graphs)
                return self._graph.workspace_graph
            pre_sym_mtime = self._symbols_mtime
            pre_graph_mtime = self._graph_mtime
            extracted_fresh_fgs = False
            file_graphs = self._snapshot.file_graphs
            if not file_graphs and auto_sync:
                file_graphs = self.bundler.extract_all_file_graphs()
                self._snapshot.file_graphs = file_graphs
                extracted_fresh_fgs = True
            ws_linker = WorkspaceGraphLinker(
                file_graphs=file_graphs.values(),
                language_configs=self.parser_registry.language_configs,
                module_resolvers=self.parser_registry.module_resolvers,
                edge_refiners=self.parser_registry.edge_refiners,
                prev_workspace_graph=self._last_workspace_graph,
            )
            prog = ProgressReporter("ast", "正在建立全域語意圖譜 (4-Pass Linking)", total_stages=1)
            total_fgs = max(1, len(file_graphs))
            prog.stage(1, "解析跨檔案匯入與呼叫拓撲", 0, total_fgs)
            try:
                ws_graph = ws_linker.link_workspace(
                    progress_callback=lambda cur, tot: prog.advance(cur, tot)
                )
                prog.finish(f"全域語意圖譜建立完成 ({len(file_graphs)} 檔案)")
            except Exception:
                prog.finish()
                raise
            self._graph.workspace_graph = ws_graph
            self._last_workspace_graph = ws_graph
            self._graph.ast_generation = int(self._snapshot.ast_generation)
            if self.symbols_index_path.exists() and self.graph_index_path.exists():
                try:
                    from core.platform.lock import InterProcessLock

                    lock_file = str(self._resolve_index_lock_path())
                    with InterProcessLock(lock_file, timeout=5.0):
                        cur_sym_mtime = self.symbols_index_path.stat().st_mtime if self.symbols_index_path.exists() else -1.0
                        cur_graph_mtime = self.graph_index_path.stat().st_mtime if self.graph_index_path.exists() else -1.0
                        if cur_sym_mtime == pre_sym_mtime and cur_graph_mtime == pre_graph_mtime:
                            if auto_sync and extracted_fresh_fgs and self._snapshot is not None:
                                if not getattr(self._snapshot, "config_hash", ""):
                                    self._snapshot.config_hash = self._compute_ast_config_hash()
                                self._snapshot.schema_version = 2
                                atomic_save_gzip_pickle(self.symbols_index_path, self._snapshot.to_dict(), compresslevel=1)
                                if self.symbols_index_path.exists():
                                    self._symbols_mtime = self.symbols_index_path.stat().st_mtime
                            self._graph.save_binary(self.graph_index_path, compresslevel=1)
                            if self.graph_index_path.exists():
                                self._graph_mtime = self.graph_index_path.stat().st_mtime
                            if self._snapshot is not None:
                                self._atomic_write_meta(self._build_meta_payload(self._snapshot, graph=self._graph))
                except Exception as save_exc:
                    log_debug(f"Persist upgraded workspace_graph skipped: {save_exc}")
            return ws_graph

    def parse_file(
        self,
        file_or_uri: Union[str, Path],
        *,
        content: Optional[Union[str, bytes]] = None,
        space: Optional[str] = None,
    ) -> FileSymbolGraph:
        """
        L0 Primitive: Stateless single-file extraction returning an immutable `FileSymbolGraph`
        without reading or mutating any persisted workspace index cache.
        """
        with cell_span("ast.parse_file"):
            raw_target = str(file_or_uri or "").strip()
            if not raw_target:
                raise FileNotFoundError("Empty file path provided to parse_file().")
            if content is not None:
                text_str, _ = normalize_source_bytes(content)
                norm_rel = raw_target.replace("\\", "/")
                if "://" in norm_rel:
                    _, rest = norm_rel.split("://", 1)
                    norm_rel = rest.lstrip("/")
                try:
                    p_cand = Path(norm_rel)
                    if p_cand.is_absolute():
                        norm_rel = self.bundler._get_project_relpath(p_cand, self.project_root)
                except Exception:
                    pass
                return self.parser_registry.extract_file_graph(
                    file_path=norm_rel,
                    content=text_str,
                    space=space or "project",
                )

            abs_path, rel_path, resolved_space = self._resolve_target_file(raw_target)
            text_str, _ = read_normalized_source_file(abs_path)
            return self.parser_registry.extract_file_graph(
                file_path=rel_path,
                content=text_str,
                space=space or resolved_space,
            )

    @staticmethod
    def _match_node_in_file_graph(
        fg: FileSymbolGraph,
        target_fqn: str,
        *,
        raw_query: str = "",
        line_number: Optional[int] = None,
        short_name: Optional[str] = None,
    ) -> Optional[SymbolNode]:
        if raw_query and raw_query in fg.all_nodes_by_id:
            return fg.all_nodes_by_id[raw_query]
        canonical_id = SymbolNode.compute_canonical_id(fg.file_path, target_fqn)
        if canonical_id in fg.all_nodes_by_id:
            return fg.all_nodes_by_id[canonical_id]
        if line_number is not None:
            for cand in fg.all_nodes_by_id.values():
                if cand.span.start_line == line_number and (
                    cand.fqn == target_fqn or (short_name and cand.name == short_name)
                ):
                    return cand
        norm_target = target_fqn.replace("::", ".")
        exact_fqn = [
            c for c in fg.all_nodes_by_id.values()
            if c.fqn == target_fqn or c.fqn.replace("::", ".") == norm_target
        ]
        if len(exact_fqn) == 1:
            return exact_fqn[0]
        if len(exact_fqn) > 1:
            exact_fqn.sort(key=lambda n: (n.span.start_byte, n.id))
            return exact_fqn[0]
        by_name = [c for c in fg.all_nodes_by_id.values() if c.name == target_fqn]
        if len(by_name) == 1:
            return by_name[0]
        if len(by_name) > 1:
            raise ASTError(f"Ambiguous symbol selector for slice_part: {raw_query or target_fqn!r}")
        return None

    def _resolve_symbol_node_and_bytes_for_slice(
        self,
        symbol_or_id: Union[SymbolNode, UnifiedSymbol, str],
        space: Optional[Union[str, Sequence[str]]] = None,
        file_bytes: Optional[Union[bytes, str]] = None,
    ) -> Tuple[SymbolNode, Optional[bytes]]:
        if isinstance(symbol_or_id, SymbolNode):
            return symbol_or_id, None

        if isinstance(symbol_or_id, UnifiedSymbol):
            norm_fp = symbol_or_id.file_path.replace("\\", "/")
            fg: Optional[FileSymbolGraph] = None
            raw_b: Optional[bytes] = None
            try:
                if file_bytes is not None:
                    _, raw_b = normalize_source_bytes(file_bytes)
                    fg = self.parse_file(symbol_or_id.file_path, content=raw_b)
                else:
                    abs_p, rel_p, sp_n = self._resolve_target_file(symbol_or_id.file_path)
                    _, raw_b = read_normalized_source_file(abs_p)
                    ws_mem = (
                        self._graph.workspace_graph
                        if (self._graph is not None and self.graph_index_path.exists())
                        else None
                    )
                    if ws_mem is not None:
                        cand_fg = ws_mem.file_graphs.get(symbol_or_id.file_path) or ws_mem.file_graphs.get(norm_fp)
                        if cand_fg is not None and cand_fg.content_hash == compute_content_hash(raw_b):
                            fg = cand_fg
                    if fg is None:
                        fg = self.parse_file(rel_p, content=raw_b, space=sp_n)
            except Exception:
                fg = None
            target_fqn = symbol_or_id.fqn or symbol_or_id.name
            short_name = (symbol_or_id.metadata or {}).get("short_name") or re.split(r"[.:]+", symbol_or_id.name)[-1]
            if fg is not None:
                matched = self._match_node_in_file_graph(
                    fg,
                    target_fqn,
                    line_number=symbol_or_id.line_number,
                    short_name=short_name,
                )
                if matched is not None:
                    return matched, raw_b
            ws_graph = self.get_workspace_graph(auto_sync=True)
            canonical_id = SymbolNode.compute_canonical_id(symbol_or_id.file_path, target_fqn)
            if canonical_id in ws_graph.nodes_by_id:
                return ws_graph.nodes_by_id[canonical_id], raw_b
            raise ASTError(f"SymbolNode not found for UnifiedSymbol '{target_fqn}'")

        q_str = str(symbol_or_id or "").strip()
        if not q_str:
            raise ASTError("Empty symbol_or_id provided to slice_part().")

        # L0 Fast Path: `<rel_path>::<fqn>` single-file O(1) parse without loading/building workspace graph!
        if "::" in q_str:
            cand_file_part, cand_fqn_part = q_str.split("::", 1)
            cand_file_part = cand_file_part.strip()
            cand_fqn_part = cand_fqn_part.strip()
            if cand_file_part and cand_fqn_part:
                resolved_target: Optional[Tuple[Path, str, str]] = None
                try:
                    resolved_target = self._resolve_target_file(cand_file_part)
                except (FileNotFoundError, OSError):
                    resolved_target = None
                if resolved_target is not None:
                    abs_p, rel_p, sp_n = resolved_target
                    if file_bytes is not None:
                        _, eff_b = normalize_source_bytes(file_bytes)
                    else:
                        _, eff_b = read_normalized_source_file(abs_p)
                    fg_single = self.parse_file(rel_p, content=eff_b, space=sp_n)
                    matched_single = self._match_node_in_file_graph(
                        fg_single,
                        cand_fqn_part,
                        raw_query=q_str,
                    )
                    if matched_single is not None:
                        return matched_single, eff_b
                    if "/" in cand_file_part or "\\" in cand_file_part or Path(cand_file_part).suffix:
                        raise ASTError(f"Symbol not found for slice_part: {q_str!r}")

        # Check already-loaded in-memory workspace_graph if available and fresh on disk
        ws_mem = (
            self._graph.workspace_graph
            if (self._graph is not None and self.graph_index_path.exists())
            else None
        )
        if ws_mem is not None and q_str in ws_mem.nodes_by_id:
            cand_n = ws_mem.nodes_by_id[q_str]
            fg_mem = ws_mem.file_graphs.get(cand_n.file_path)
            if fg_mem is not None and file_bytes is None:
                try:
                    abs_chk, _, _ = self._resolve_target_file(cand_n.file_path)
                    _, chk_b = read_normalized_source_file(abs_chk)
                    if fg_mem.content_hash == compute_content_hash(chk_b):
                        return cand_n, chk_b
                except Exception:
                    pass

        # Resolve selector via symbol table (avoids full 4-pass WorkspaceGraphLinker when unnecessary)
        res = self.resolve(q_str, spaces=space)
        if res.status == "ambiguous":
            raise ASTError(f"Ambiguous symbol selector for slice_part: {q_str!r}")
        if res.status != "not_found" and res.targets:
            return self._resolve_symbol_node_and_bytes_for_slice(
                res.targets[0],
                space=space,
                file_bytes=file_bytes,
            )

        ws_graph = self.get_workspace_graph(auto_sync=True)
        if q_str in ws_graph.nodes_by_id:
            return ws_graph.nodes_by_id[q_str], None
        for cand_node in ws_graph.nodes_by_id.values():
            if cand_node.fqn == q_str or cand_node.name == q_str:
                return cand_node, None
        raise ASTError(f"Symbol not found for slice_part: {q_str!r}")

    def _resolve_symbol_node_for_slice(
        self,
        symbol_or_id: Union[SymbolNode, UnifiedSymbol, str],
        space: Optional[Union[str, Sequence[str]]] = None,
    ) -> SymbolNode:
        """
        Resolve `symbol_or_id` to a `SymbolNode` for `slice_part()` / `traverse_edges()`.
        Supported string forms:
        - Structured `SymbolSelector`: `[kind] [scope.]name[(param_types...)]` (e.g. `"ASTEngine.slice_part"`).
        - Canonical `SymbolNode.id`: `<project_rel_path>::<fqn>` (double-colon `::`; single-colon `<path>:<fqn>` is not valid).
        """
        node, _ = self._resolve_symbol_node_and_bytes_for_slice(symbol_or_id, space=space)
        return node

    def slice_part(
        self,
        symbol_or_id: Union[SymbolNode, UnifiedSymbol, str],
        part: str = "outer",
        *,
        file_bytes: Optional[Union[bytes, str]] = None,
        space: Optional[Union[str, List[str]]] = None,
    ) -> str:
        """
        L0 Primitive: O(1) lossless UTF-8 byte slicing of a symbol's structural part
        (`"outer"`, `"name"`, `"signature"`, `"parameters"`, `"return_type"`, `"doc"`, `"body"`).

        `symbol_or_id` accepts a `SymbolNode`, `UnifiedSymbol`, structured `SymbolSelector`
        (`"[kind] [scope.]name[(param_types...)]"`), or canonical node ID (`"<rel_path>::<fqn>"`).
        """
        part_norm = str(part or "outer").strip().lower()
        if part_norm not in VALID_SLICE_PARTS:
            raise ASTError(
                f"Unsupported slice part: {part!r} (expected one of {sorted(VALID_SLICE_PARTS)})"
            )
        node, preloaded_bytes = self._resolve_symbol_node_and_bytes_for_slice(
            symbol_or_id,
            space=space,
            file_bytes=file_bytes,
        )
        target_span: Optional[Span] = node.span if part_norm == "outer" else node.parts.get(part_norm)
        if target_span is None:
            return ""

        if file_bytes is not None:
            _, raw_bytes = normalize_source_bytes(file_bytes)
        elif preloaded_bytes is not None:
            raw_bytes = preloaded_bytes
        else:
            abs_p = self.snippet_extractor._resolve_abs_path(node.file_path)
            if abs_p is None or not abs_p.is_file():
                abs_p, _, _ = self._resolve_target_file(node.file_path)
            _, raw_bytes = read_normalized_source_file(abs_p)

        return target_span.slice_text(raw_bytes)

    def resolve(
        self,
        selector_expr: str,
        *,
        spaces: Optional[Union[str, Sequence[str]]] = None,
        kinds: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        ftypes: Optional[Union[str, Sequence[str]]] = None,
    ) -> SymbolResolutionResult:
        """L1 Primitive: Deterministically resolve `selector_expr` across workspace symbols."""
        with cell_span("ast.resolve"), self._lock:
            eff_spaces: Optional[List[str]] = None
            if isinstance(spaces, str) and spaces.strip():
                eff_spaces = [s.strip() for s in spaces.split(",") if s.strip()]
            elif isinstance(spaces, (list, tuple, set, frozenset)):
                eff_spaces = [str(s).strip() for s in spaces if str(s).strip()]
            snapshot = self.ensure_jit_synced(spaces=eff_spaces)
            resolver = DeterministicSymbolResolver(snapshot.symbols)
            norm_ftypes = resolver.normalize_ftypes(list(ftypes) if isinstance(ftypes, (list, tuple, set, frozenset)) else ftypes)
            if kinds is not None:
                return resolver.resolve(
                    selector_expr,
                    space=eff_spaces,
                    ftypes=norm_ftypes,
                    kinds=kinds,
                )
            return _resolve_with_ftype_fallback(resolver, selector_expr, eff_spaces, norm_ftypes)

    def select_nodes(
        self,
        *,
        spaces: Optional[Union[str, Sequence[str]]] = None,
        kinds: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        visibility: Optional[Union[str, Sequence[str]]] = None,
        facets: Optional[Mapping[str, Any]] = None,
        ftypes: Optional[Union[str, Sequence[str]]] = None,
    ) -> Tuple[SymbolNode, ...]:
        """L1 Primitive: Batch filter `SymbolNode` instances across `WorkspaceSymbolGraph`."""
        with cell_span("ast.select_nodes"), self._lock:
            ws_graph = self.get_workspace_graph(auto_sync=True)
            symbols_map = self._snapshot.symbols if self._snapshot is not None else None
            return select_workspace_nodes(
                ws_graph,
                spaces=spaces,
                kinds=kinds,
                visibility=visibility,
                facets=facets,
                ftypes=ftypes,
                symbols_map=symbols_map,
            )

    def traverse_edges(
        self,
        seed_ids: Union[str, Sequence[str], Set[str], FrozenSet[str]],
        *,
        edge_kinds: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        direction: str = "out",
        depth: int = 1,
        status_filter: Optional[Union[str, Sequence[str], Set[str], FrozenSet[str]]] = None,
        spaces: Optional[Union[str, Sequence[str]]] = None,
    ) -> Dict[str, Any]:
        """
        L1 Primitive: General directed BFS graph traversal across `WorkspaceSymbolGraph` supporting
        arbitrary `edge_kinds`, `direction` (`"out"` | `"in"` | `"both"`), `depth`, and `status_filter`.
        """
        with cell_span("ast.traverse_edges"), self._lock:
            ws_graph = self.get_workspace_graph(auto_sync=True)
            raw_list = [seed_ids] if isinstance(seed_ids, str) else list(seed_ids or ())
            resolved_seeds: List[str] = []
            for item in raw_list:
                s_str = str(item or "").strip()
                if not s_str:
                    continue
                norm_s = s_str.replace("\\", "/") if "::" in s_str else s_str
                if norm_s in ws_graph.nodes_by_id:
                    if norm_s not in resolved_seeds:
                        resolved_seeds.append(norm_s)
                    continue
                res = self.resolve(s_str, spaces=spaces)
                if res.targets:
                    for tsym in res.targets:
                        try:
                            snode = self._resolve_symbol_node_for_slice(tsym, space=spaces)
                            if snode.id not in resolved_seeds:
                                resolved_seeds.append(snode.id)
                        except Exception:
                            pass
                else:
                    for cand in ws_graph.nodes_by_id.values():
                        if cand.fqn == s_str or cand.name == s_str:
                            if cand.id not in resolved_seeds:
                                resolved_seeds.append(cand.id)
            return traverse_workspace_edges(
                ws_graph,
                resolved_seeds,
                edge_kinds=edge_kinds,
                direction=direction,
                depth=depth,
                status_filter=status_filter,
            )

    def _resolve_target_file(self, file_or_uri: str) -> Tuple[Path, str, str]:
        """Resolve `file_or_uri` to `(abs_path, rel_path, space_name)`."""
        raw = (file_or_uri or "").strip()
        if not raw:
            raise FileNotFoundError("Empty file path provided to outline().")

        loaded_spaces: Dict[str, SpaceConfig] = {}
        for sp in self.space_manager.list_spaces():
            if sp.qualified_name:
                loaded_spaces[sp.qualified_name] = sp
            if sp.short_name and sp.short_name not in loaded_spaces:
                loaded_spaces[sp.short_name] = sp

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

        norm_raw = raw.replace("\\", "/")
        p = Path(norm_raw)
        if not p.is_absolute():
            cand = (self.project_root / p).resolve()
            if not cand.is_file():
                cand_cwd = (Path(get_virtual_cwd()) / p).resolve()
                if cand_cwd.is_file():
                    cand = cand_cwd
            p = cand
        else:
            p = p.resolve()

        if not p.is_file():
            raise FileNotFoundError(f"Target file not found: '{file_or_uri}' (resolved: '{p}')")

        # Determine owning space (preferring the deepest / most specific matching entry root)
        rel_path = self.bundler._get_project_relpath(p, self.project_root)
        matched_space = "project"
        best_depth = -1
        try:
            for sp_cfg in self.space_manager.list_spaces():
                sp_label = _space_logical_name(sp_cfg)
                for _, inc_root, exists in sp_cfg.resolve_entries(self.project_root):
                    if inc_root is None or not exists:
                        continue
                    try:
                        resolved_inc = Path(inc_root).resolve()
                        p.relative_to(resolved_inc)
                        depth = len(resolved_inc.parts)
                        if depth > best_depth:
                            best_depth = depth
                            matched_space = sp_label
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
        with cell_span("ast.outline"):
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
                if merged:
                    try:
                        with self._lock:
                            snapshot = self.ensure_jit_synced()
                    except Exception as exc:
                        log_debug(f"Outline JIT sync skipped: {exc}")
                else:
                    sym_exists = self.symbols_index_path.exists()
                    if not sym_exists:
                        snapshot = None
                    else:
                        snapshot = self._snapshot
                        needs_reload = snapshot is None
                        if not needs_reload and self._symbols_mtime > 0.0:
                            try:
                                needs_reload = self.symbols_index_path.stat().st_mtime > self._symbols_mtime
                            except OSError:
                                needs_reload = True
                        if needs_reload and self._lock.acquire(blocking=False):
                            try:
                                if self._ensure_symbols_loaded():
                                    snapshot = self._snapshot
                            except Exception as exc:
                                log_debug(f"Outline non-blocking symbols load skipped: {exc}")
                            finally:
                                self._lock.release()

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
            snapshot = self.ensure_jit_synced(spaces=eff_space, _hydrate_workspace_graph=True)
            graph = self.get_call_graph(auto_sync=False)
            if graph.workspace_graph is None and snapshot.file_graphs:
                try:
                    self.get_workspace_graph(auto_sync=False)
                except Exception as ws_err:
                    log_debug(f"Lazy WorkspaceSymbolGraph hydration in callers skipped: {ws_err}")
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
            snapshot = self.ensure_jit_synced(spaces=eff_space, _hydrate_workspace_graph=True)
            graph = self.get_call_graph(auto_sync=False)
            if graph.workspace_graph is None and snapshot.file_graphs:
                try:
                    self.get_workspace_graph(auto_sync=False)
                except Exception as ws_err:
                    log_debug(f"Lazy WorkspaceSymbolGraph hydration in callees skipped: {ws_err}")
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
            snapshot = self.ensure_jit_synced(spaces=eff_space, _hydrate_workspace_graph=True)
            graph = self.get_call_graph(auto_sync=False)
            if graph.workspace_graph is None and snapshot.file_graphs:
                try:
                    self.get_workspace_graph(auto_sync=False)
                except Exception as ws_err:
                    log_debug(f"Lazy WorkspaceSymbolGraph hydration in impact skipped: {ws_err}")
            return query_impact(
                target_query=target_query,
                symbols_map=snapshot.symbols,
                graph=graph,
                depth=depth,
                space=eff_space,
                ftypes=ftypes,
            )

    def status(self, space: Optional[str] = None, space_name: Optional[str] = None) -> Dict[str, Any]:
        """Return AST index health, generation numbers, symbol/edge counts, and registered parsers (lock-free fast path)."""
        target_space = space or space_name
        has_symbols = self.symbols_index_path.exists()
        has_graph = self.graph_index_path.exists()

        ast_gen = 0
        space_gens: Dict[str, int] = {}
        total_symbols = 0
        total_files = 0
        total_edges = 0

        if not (has_symbols and has_graph) and self._symbols_mtime > 0.0:
            with self._bg_persist_lock:
                self._bg_persist_seq += 1
                self._bg_persist_pending = None
            self._snapshot = None
            self._graph = None
            self._symbols_mtime = 0.0
            self._graph_mtime = 0.0

        if has_symbols and has_graph:
            populated = False
            try:
                sym_st = self.symbols_index_path.stat()
                graph_st = self.graph_index_path.stat()
                snap_ref = self._snapshot
                graph_ref = self._graph
                if (
                    snap_ref is not None
                    and graph_ref is not None
                    and sym_st.st_mtime <= self._symbols_mtime
                    and graph_st.st_mtime <= self._graph_mtime
                ):
                    ast_gen = snap_ref.ast_generation
                    space_gens = dict(snap_ref.space_generations)
                    if target_space:
                        space_gens = {k: v for k, v in space_gens.items() if k == target_space}
                        total_symbols = sum(
                            1 for s in snap_ref.symbols.values() if target_space in (s.spaces or [])
                        )
                        total_files = len(snap_ref.files_map.get(target_space, []))
                    else:
                        total_symbols = len(snap_ref.symbols)
                        total_files = len(snap_ref.file_to_symbol_ids)
                    total_edges = graph_ref.graph.number_of_edges()
                    populated = True
                elif self.meta_index_path.exists():
                    meta = json.loads(self.meta_index_path.read_text(encoding="utf-8"))
                    if (
                        isinstance(meta, dict)
                        and meta.get("symbols_mtime_ns") == int(sym_st.st_mtime_ns)
                        and meta.get("symbols_size") == int(sym_st.st_size)
                        and meta.get("graph_mtime_ns") == int(graph_st.st_mtime_ns)
                        and meta.get("graph_size") == int(graph_st.st_size)
                        and "total_edges" in meta
                    ):
                        sp_sym_map = meta.get("space_symbol_counts")
                        sp_file_map = meta.get("space_file_counts")
                        if not target_space or (isinstance(sp_sym_map, dict) and isinstance(sp_file_map, dict)):
                            ast_gen = int(meta.get("ast_generation", 0))
                            raw_sg = meta.get("space_generations", {})
                            space_gens = dict(raw_sg) if isinstance(raw_sg, dict) else {}
                            if target_space:
                                space_gens = {k: v for k, v in space_gens.items() if k == target_space}
                                total_symbols = int(sp_sym_map.get(target_space, 0))  # type: ignore[union-attr]
                                total_files = int(sp_file_map.get(target_space, 0))  # type: ignore[union-attr]
                            else:
                                total_symbols = int(meta.get("total_symbols", 0))
                                total_files = int(meta.get("total_files", 0))
                            total_edges = int(meta.get("total_edges", 0))
                            populated = True
            except Exception as exc:
                log_debug(f"status fast-path fallback: {exc}")

            if not populated:
                is_b_now, _, _ = self._probe_build_in_progress()
                if not is_b_now and self._lock.acquire(blocking=False):
                    try:
                        if self._ensure_loaded_from_disk():
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
                    finally:
                        self._lock.release()

        building_active, build_phase, build_progress = self._probe_build_in_progress()

        return {
            "storage_dir": str(self.storage_dir),
            "index_exists": bool(has_symbols and has_graph),
            "snapshot_exists": bool(has_symbols and has_graph),
            "has_symbols_index": has_symbols,
            "has_graph_index": has_graph,
            "building_in_progress": building_active,
            "build_phase": build_phase,
            "build_progress": build_progress,
            "ast_generation": ast_gen,
            "space_generations": space_gens,
            "total_symbols": total_symbols,
            "total_files": total_files,
            "total_edges": total_edges,
            "registered_languages": sorted(list(self.parser_registry.language_configs.keys())),
            "parser_load_errors": dict(self.parser_registry.load_errors),
        }

    def clean(self, space: Optional[str] = None, space_name: Optional[str] = None) -> Dict[str, Any]:
        """Remove persisted AST snapshot/graph caches and reset `core.space` cursor (`consumer='ast'`)."""
        from core.platform.lock import InterProcessLock
        from .linker import reset_linker_cache

        target_space = space or space_name
        removed: List[str] = []
        resolved_cfgs = []
        if target_space:
            resolved_cfgs = self.bundler.space_manager.resolve_spaces(target_space)

        lock_path = self._resolve_index_lock_path()
        gen_floor_file = self.indices_dir / ".ast_generation_floor"
        protected_names = {lock_path.name, ".ast_generation_floor"}

        with self._lock, InterProcessLock(str(lock_path), timeout=15.0):
            # Preserve monotonic ast_generation watermark floor across clean -> rebuild cycles
            max_known_gen = 0
            if self._snapshot is not None:
                max_known_gen = max(max_known_gen, int(self._snapshot.ast_generation))
            if self.meta_index_path.exists():
                try:
                    max_known_gen = max(
                        max_known_gen,
                        int(json.loads(self.meta_index_path.read_text(encoding="utf-8")).get("ast_generation", 0)),
                    )
                except Exception:
                    pass
            if gen_floor_file.exists():
                try:
                    max_known_gen = max(max_known_gen, int(gen_floor_file.read_text(encoding="utf-8").strip() or "0"))
                except Exception:
                    pass
            if max_known_gen > 0:
                try:
                    self.indices_dir.mkdir(parents=True, exist_ok=True)
                    gen_floor_file.write_text(f"{max_known_gen}\n", encoding="utf-8")
                except OSError:
                    pass

            with self._bg_persist_lock:
                self._bg_persist_seq += 1
                self._bg_persist_pending = None
            self._snapshot = None
            self._graph = None
            self._symbols_mtime = 0.0
            self._graph_mtime = 0.0
            self.bundler.clear_transient_caches()
            reset_linker_cache()

            if target_space:
                bundle_names = {target_space, target_space.replace("/", "_")}
                for scfg in resolved_cfgs:
                    if scfg.short_name:
                        bundle_names.add(scfg.short_name)
                    if scfg.qualified_name:
                        bundle_names.add(scfg.qualified_name.replace("/", "_"))
                for b_name in sorted(bundle_names):
                    b_file = self.bundles_dir / f"{b_name}.bundle.json"
                    if b_file.exists():
                        try:
                            b_file.unlink()
                            removed.append(str(b_file))
                        except OSError:
                            pass
                for u_f in (self.symbols_index_path, self.graph_index_path, self.meta_index_path, self.build_state_path):
                    if u_f.exists():
                        try:
                            u_f.unlink()
                            removed.append(str(u_f))
                        except OSError:
                            pass
            else:
                for d in (self.indices_dir, self.bundles_dir):
                    if d.is_dir():
                        for item in d.iterdir():
                            if item.name in protected_names:
                                continue
                            if item.is_file():
                                try:
                                    item.unlink()
                                    removed.append(str(item))
                                except OSError:
                                    pass
                            elif item.is_dir():
                                shutil.rmtree(item, ignore_errors=True)
                                removed.append(str(item))

            if target_space:
                self._reset_consumer_cursor(space_name=target_space)
                self._reset_consumer_cursor(space_name=None)
                for scfg in resolved_cfgs:
                    if scfg.qualified_name:
                        self._reset_consumer_cursor(space_name=scfg.qualified_name)
                    if scfg.short_name:
                        self._reset_consumer_cursor(space_name=scfg.short_name)
            else:
                self._reset_consumer_cursor(space_name=None)

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
    if project_root is not None or storage_dir is not None or force_new:
        return ASTEngine(project_root=project_root, storage_dir=storage_dir)
    with _ENGINE_LOCK:
        inst = _get_default_engine_instance()
        expected_root = resolve_project_root()
        if inst is None or getattr(inst, "project_root", None) != expected_root:
            inst = ASTEngine()
            _set_default_engine_instance(inst)
        return inst


def reset_default_engine() -> None:
    """Clear the process-level singleton `ASTEngine` instance."""
    with _ENGINE_LOCK:
        _set_default_engine_instance(None)


__all__ = [
    "ASTEngine",
    "VALID_SLICE_PARTS",
    "_build_outline_tree",
    "_filter_outline_nodes",
    "_member_to_outline_node",
    "get_engine",
    "reset_default_engine",
]
