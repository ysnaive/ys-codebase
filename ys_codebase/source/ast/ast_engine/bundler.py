"""
Semantic Bundler & Partial Class Aggregator for `module:ast`.
Provides two-tier C# `partial class/struct/interface` member isolation (`_own_members` vs aggregated `members`)
and deterministic overload ID disambiguation.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from core.vfs import write_bytes
from file_space import FileSpaceConfig, FileSpaceManager, FingerprintScanner, ScanDiffDetail

from .exceptions import ASTError
from .io_utils import compute_project_relpath, is_dirty_file_match, normalize_dirty_paths
from .parsers.registry import ParserRegistry
from .schema import MemberInfo, SemanticBundle, SymbolCallSite, SymbolKind, UnifiedSymbol

logger = logging.getLogger("ast.bundler")

PARALLEL_BUNDLE_THRESHOLD = 10

_worker_registry: Optional[ParserRegistry] = None


def ensure_unique_overload_ids(
    symbols: List[UnifiedSymbol],
    default_space: str = "project",
) -> List[UnifiedSymbol]:
    """
    Ensure that same-file method overloads (symbols sharing `(file_path, parent_scope, name, kind)`)
    always receive distinct `UnifiedSymbol.id` values by passing `(line_number, signature)` to `compute_id`.
    """
    if not symbols:
        return symbols

    groups: Dict[Tuple[str, str, str, str], List[int]] = defaultdict(list)
    for idx, sym in enumerate(symbols):
        parent_scope = (sym.metadata or {}).get("parent_scope") or ""
        short_name = (sym.metadata or {}).get("short_name") or sym.name
        groups[(sym.file_path, str(parent_scope), str(short_name), str(sym.kind))].append(idx)

    updated = list(symbols)
    seen_ids: Set[str] = set()

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
                    updated[i] = UnifiedSymbol(
                        id=new_id,
                        name=sym.name,
                        kind=sym.kind,
                        file_path=sym.file_path,
                        line_number=sym.line_number,
                        end_line=sym.end_line,
                        language=sym.language,
                        docstring=sym.docstring,
                        signature=sym.signature,
                        fqn=sym.fqn,
                        scope_path=sym.scope_path,
                        parent_id=sym.parent_id,
                        children=sym.children,
                        parameters=sym.parameters,
                        return_type=sym.return_type,
                        search_payload=sym.search_payload,
                        visibility=sym.visibility,
                        members=sym.members,
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
            updated[idx] = UnifiedSymbol(
                id=new_id,
                name=sym.name,
                kind=sym.kind,
                file_path=sym.file_path,
                line_number=sym.line_number,
                end_line=sym.end_line,
                language=sym.language,
                docstring=sym.docstring,
                signature=sym.signature,
                fqn=sym.fqn,
                scope_path=sym.scope_path,
                parent_id=sym.parent_id,
                children=sym.children,
                parameters=sym.parameters,
                return_type=sym.return_type,
                search_payload=sym.search_payload,
                visibility=sym.visibility,
                members=sym.members,
                metadata=dict(sym.metadata),
            )
        seen_ids.add(updated[idx].id)

    return updated


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
        own_members = [
            MemberInfo.from_dict(m) if isinstance(m, dict) else m
            for m in raw_own
        ]
    else:
        own_members = list(sym.members)

    own_bases = list(meta.get("_own_base_types", meta.get("base_types", [])))
    own_fields = dict(meta.get("_own_field_types", meta.get("field_types", {})))
    own_doc = str(meta.get("_own_docstring", sym.docstring or ""))
    return own_members, own_bases, own_fields, own_doc


def restore_unaggregated_partial_symbol(sym: UnifiedSymbol) -> UnifiedSymbol:
    """
    Restore an already-aggregated C# `partial` symbol back to its single-file baseline state
    for incremental re-aggregation or single-file degeneration.
    """
    if "_own_members" not in (sym.metadata or {}):
        return sym
    own_members, own_bases, own_fields, own_doc = _extract_unaggregated_partial_state(sym)
    new_meta = dict(sym.metadata)
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
        new_meta["base_types"] = own_bases
    else:
        new_meta.pop("base_types", None)
    if own_fields:
        new_meta["field_types"] = own_fields
    else:
        new_meta.pop("field_types", None)
    search_payload = f"{sym.fqn} {new_meta.get('short_name', sym.name)} {own_doc} {sym.signature}".strip()
    return UnifiedSymbol(
        id=sym.id,
        name=sym.name,
        kind=sym.kind,
        file_path=sym.file_path,
        line_number=sym.line_number,
        end_line=sym.end_line,
        language=sym.language,
        docstring=own_doc,
        signature=sym.signature,
        fqn=sym.fqn,
        scope_path=sym.scope_path,
        parent_id=sym.parent_id,
        children=tuple(own_members),
        parameters=sym.parameters,
        return_type=sym.return_type,
        search_payload=search_payload,
        visibility=sym.visibility,
        members=tuple(own_members),
        metadata=new_meta,
    )


def _is_partial_symbol(sym: UnifiedSymbol) -> bool:
    """Check whether `sym` is a C# `partial class/struct/interface`."""
    if sym.kind not in (
        SymbolKind.CLASS.value,
        SymbolKind.STRUCT.value,
        SymbolKind.INTERFACE.value,
        "class",
        "struct",
        "interface",
    ):
        return False
    meta = sym.metadata or {}
    if meta.get("is_partial"):
        return True
    sig = sym.signature or ""
    if re.search(r"\bpartial\s+(?:class|struct|interface|record)\b", sig):
        return True
    return False


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
                    updated[indices[0]] = UnifiedSymbol(
                        id=only_sym.id,
                        name=only_sym.name,
                        kind=only_sym.kind,
                        file_path=only_sym.file_path,
                        line_number=only_sym.line_number,
                        end_line=only_sym.end_line,
                        language=only_sym.language,
                        docstring=only_sym.docstring,
                        signature=only_sym.signature,
                        fqn=only_sym.fqn,
                        scope_path=only_sym.scope_path,
                        parent_id=only_sym.parent_id,
                        children=only_sym.children,
                        parameters=only_sym.parameters,
                        return_type=only_sym.return_type,
                        search_payload=only_sym.search_payload,
                        visibility=only_sym.visibility,
                        members=only_sym.members,
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
            updated[i] = UnifiedSymbol(
                id=orig.id,
                name=orig.name,
                kind=orig.kind,
                file_path=orig.file_path,
                line_number=orig.line_number,
                end_line=orig.end_line,
                language=orig.language,
                docstring=doc_to_use,
                signature=orig.signature,
                fqn=orig.fqn,
                scope_path=orig.scope_path,
                parent_id=orig.parent_id,
                children=tuple(merged_members),
                parameters=orig.parameters,
                return_type=orig.return_type,
                search_payload=search_payload,
                visibility=orig.visibility,
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
    global _worker_registry
    if _worker_registry is None:
        _worker_registry = ParserRegistry(register_defaults=True)
    return _worker_registry


def _parse_file_task_worker(
    task: Tuple[str, str, str, List[str]],
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str], Optional[str]]:
    """
    Top-level picklable worker function for `ProcessPoolExecutor` or serial execution.
    task: `(c_key, f_path_str, relpath, sorted_spaces)`
    return: `(c_key, [symbol.to_dict(), ...], [call_site.to_dict(), ...], imports_dict, error_message_or_None)`
    """
    c_key, f_path_str, relpath, sorted_spaces = task
    primary_space = sorted_spaces[0] if sorted_spaces else "unified"
    try:
        registry = _get_worker_registry()
        with open(f_path_str, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        symbols = registry.parse_file(file_path=relpath, content=content, space=primary_space)
        symbols = ensure_unique_overload_ids(symbols, default_space=primary_space)
        results = []
        for sym in symbols:
            sym.metadata["spaces"] = sorted_spaces
            results.append(sym.to_dict())
        call_sites = registry.extract_call_sites(
            file_path=relpath, content=content, space=primary_space, symbols=symbols
        )
        site_dicts = [s.to_dict() for s in call_sites]
        imports = registry.extract_imports(file_path=relpath, content=content)
        return (c_key, results, site_dicts, dict(imports or {}), None)
    except Exception as exc:
        return (c_key, [], [], {}, str(exc))


def _resolve_default_ast_storage_dir(project_root: Optional[Path] = None) -> Path:
    """Resolve `ast.storage://` -> `cache://ast/`."""
    try:
        from core import uri

        res = uri.resolve("ast.storage://", interactive=False)
        if res and not str(res).startswith("!undefined"):
            return Path(str(res)).resolve()
    except Exception:
        pass
    try:
        from core import uri

        res_cache = uri.resolve("cache://ast", interactive=False)
        if res_cache and not str(res_cache).startswith("!undefined"):
            return Path(str(res_cache)).resolve()
    except Exception:
        pass
    base = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    if (base / "ys_codebase").is_dir():
        return base / "ys_codebase" / ".cache" / "ast"
    return base / ".cache" / "ast"


def _get_loaded_spaces(space_manager: Optional[FileSpaceManager]) -> Dict[str, Any]:
    if space_manager is None:
        return {}
    if hasattr(space_manager, "get_all_spaces"):
        return space_manager.get_all_spaces()
    return space_manager.load_spaces()


def _preload_snap_entries(
    scanner: Optional[FingerprintScanner],
    target_spaces: Iterable[FileSpaceConfig],
) -> Dict[str, Dict[str, Any]]:
    snap_entries_by_space: Dict[str, Dict[str, Any]] = {}
    if scanner is not None and hasattr(scanner, "_load_or_recover_state"):
        for sp in target_spaces:
            try:
                st, _ = scanner._load_or_recover_state(sp.name)
                if st and st.entries:
                    snap_entries_by_space[sp.name] = st.entries
            except Exception:
                pass
    return snap_entries_by_space


def _normalize_space_dirty_paths(
    raw_paths: Iterable[str],
    target_spaces: List[FileSpaceConfig],
    space_manager: Optional[FileSpaceManager] = None,
    scanner: Optional[FingerprintScanner] = None,
    file_symbols_cache: Optional[Dict[str, List[UnifiedSymbol]]] = None,
    prefer_missing: bool = False,
    snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
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
    loaded_spaces = _get_loaded_spaces(space_manager)

    for raw_p in raw_list:
        p_obj = Path(raw_p)
        if p_obj.is_absolute():
            expanded.add(raw_p)
            try:
                c_abs = str(p_obj.resolve()).replace("\\", "/")
                expanded.add(c_abs)
                expanded.add(compute_project_relpath(p_obj, p_obj.parent, project_root=proj_root))
            except Exception:
                pass
            continue

        matched_from_snap = False
        snap_matches: List[Any] = []
        for sp in target_spaces:
            entries = snap_entries_by_space.get(sp.name, {})
            fp_rec = entries.get(raw_p)
            if fp_rec is not None and getattr(fp_rec, "source_root", ""):
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
                src_root = Path(fp_rec.source_root)
                cand_abs = src_root / raw_p
                try:
                    c_abs = str(cand_abs.resolve()).replace("\\", "/")
                except OSError:
                    c_abs = str(cand_abs).replace("\\", "/")
                expanded.add(c_abs)
                expanded.add(compute_project_relpath(cand_abs, src_root, project_root=proj_root))
                matched_from_snap = True

        if matched_from_snap:
            continue

        matching_candidates: List[Tuple[Path, Path]] = []
        for sp in target_spaces:
            if space_manager is not None and sp.name in loaded_spaces:
                inc_roots = space_manager.resolve_space_include(sp.name)
            else:
                inc_roots = getattr(sp, "resolved_include_paths", [Path(inc) for inc in getattr(sp, "include", [])])
            for inc_root in inc_roots:
                cand_abs = Path(inc_root) / raw_p
                matching_candidates.append((cand_abs, Path(inc_root)))
            if proj_root is not None:
                cand_proj = Path(proj_root) / raw_p
                if cand_proj.exists():
                    matching_candidates.append((cand_proj, Path(proj_root)))

        existing_cands = [(c, r) for c, r in matching_candidates if c.exists()]
        missing_cands = [(c, r) for c, r in matching_candidates if not c.exists()]
        cache_ref = file_symbols_cache or {}
        if prefer_missing and missing_cands:
            if len(missing_cands) == 1:
                cands_to_use = missing_cands
            else:
                cached_missing = [
                    (c, r)
                    for c, r in missing_cands
                    if str(c.resolve()).replace("\\", "/") in cache_ref
                ]
                cands_to_use = cached_missing or missing_cands
        else:
            if len(existing_cands) > 1 and "/" not in raw_p:
                max_mtime = max((c.stat().st_mtime_ns for c, _ in existing_cands), default=0)
                existing_cands = [(c, r) for c, r in existing_cands if c.stat().st_mtime_ns >= max_mtime]
            cands_to_use = (
                existing_cands
                if len(existing_cands) >= 1
                else (matching_candidates if len(matching_candidates) == 1 or "/" in raw_p else existing_cands)
            )
        if cands_to_use:
            for cand_abs, inc_root in cands_to_use:
                try:
                    c_abs = str(cand_abs.resolve()).replace("\\", "/")
                except OSError:
                    c_abs = str(cand_abs).replace("\\", "/")
                expanded.add(c_abs)
                expanded.add(compute_project_relpath(cand_abs, inc_root, project_root=proj_root))
        else:
            expanded.add(raw_p)

    return expanded


class SemanticBundler:
    """Workspace semantic bundler and incremental dirty-file parser for `module:ast`."""

    def __init__(
        self,
        space_manager: FileSpaceManager,
        parser_registry: Optional[ParserRegistry] = None,
        scanner: Optional[FingerprintScanner] = None,
        storage_dir: Optional[Union[str, Path]] = None,
    ):
        self.space_manager = space_manager
        self.parser_registry = parser_registry or ParserRegistry(register_defaults=True)
        self.scanner = scanner or FingerprintScanner(space_manager)
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            proj_root = getattr(self.space_manager, "project_root", None)
            self.storage_dir = _resolve_default_ast_storage_dir(proj_root)
        self._file_symbols_cache: Dict[str, List[UnifiedSymbol]] = {}
        self._file_call_sites_cache: Dict[str, List[SymbolCallSite]] = {}
        self._file_imports_cache: Dict[str, Dict[str, str]] = {}
        self._last_bundle_unique_files: Dict[str, Tuple[Path, str, Set[str]]] = {}

    def _resolve_target_spaces(
        self, spaces: Optional[Iterable[Union[str, FileSpaceConfig]]] = None
    ) -> List[FileSpaceConfig]:
        if spaces is None:
            if hasattr(self.space_manager, "get_all_spaces"):
                return list(self.space_manager.get_all_spaces().values())
            raw_list = self.space_manager.list_spaces()
            return [
                self.space_manager.get_space(sp) if isinstance(sp, str) else sp
                for sp in raw_list
            ]
        resolved: List[FileSpaceConfig] = []
        for sp in spaces:
            if isinstance(sp, str):
                resolved.append(self.space_manager.get_space(sp))
            else:
                resolved.append(sp)
        return resolved

    def _iter_space_eligible_files(self, space_cfg: FileSpaceConfig) -> List[Tuple[str, Path, Path]]:
        if space_cfg.name in _get_loaded_spaces(self.space_manager):
            return list(self.space_manager.iter_space_files(space_cfg.name))
        temp_mgr = FileSpaceManager(
            project_root=getattr(self.space_manager, "project_root", None),
            storage_root=getattr(self.space_manager, "storage_root", None),
            spaces_config={space_cfg.name: space_cfg},
        )
        return list(temp_mgr.iter_space_files(space_cfg.name))

    def _get_project_relpath(self, f_path: Path, fallback_base: Path) -> str:
        proj_root = getattr(self.space_manager, "project_root", None)
        return compute_project_relpath(f_path, fallback_base, project_root=proj_root)

    def _parse_file_full(
        self,
        f_path: Union[str, Path],
        relpath: str,
        sorted_spaces: List[str],
    ) -> Tuple[List[UnifiedSymbol], List[SymbolCallSite], Dict[str, str]]:
        """Read `f_path` once and extract `(symbols, call_sites, imports)`."""
        primary_space = sorted_spaces[0] if sorted_spaces else "unified"
        with open(f_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        file_symbols = self.parser_registry.parse_file(
            file_path=relpath,
            content=content,
            space=primary_space,
        )
        file_symbols = ensure_unique_overload_ids(file_symbols, default_space=primary_space)
        for sym in file_symbols:
            sym.metadata["spaces"] = sorted_spaces
        call_sites = self.parser_registry.extract_call_sites(
            file_path=relpath,
            content=content,
            space=primary_space,
            symbols=file_symbols,
        )
        imports = self.parser_registry.extract_imports(
            file_path=relpath,
            content=content,
        )
        return file_symbols, call_sites, dict(imports or {})

    def _parse_and_dedup_file(
        self,
        f_path: Union[str, Path],
        relpath: str,
        sorted_spaces: List[str],
    ) -> List[UnifiedSymbol]:
        """Read `f_path`, parse symbols via `parser_registry`, disambiguate overload IDs, and attach `spaces` metadata."""
        primary_space = sorted_spaces[0] if sorted_spaces else "unified"
        with open(f_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        file_symbols = self.parser_registry.parse_file(
            file_path=relpath,
            content=content,
            space=primary_space,
        )
        file_symbols = ensure_unique_overload_ids(file_symbols, default_space=primary_space)
        for sym in file_symbols:
            sym.metadata["spaces"] = sorted_spaces
        return file_symbols

    def _collect_space_files(
        self, target_spaces: List[FileSpaceConfig]
    ) -> Dict[str, Tuple[Path, str, Set[str]]]:
        unique_files: Dict[str, Tuple[Path, str, Set[str]]] = {}

        for sp in target_spaces:
            space_name = sp.name
            for _, f_path, base_dir in self._iter_space_eligible_files(sp):
                try:
                    c_key = str(f_path.resolve()).replace("\\", "/")
                except OSError:
                    c_key = str(f_path).replace("\\", "/")
                relpath = self._get_project_relpath(f_path, base_dir)
                if c_key not in unique_files:
                    unique_files[c_key] = (f_path, relpath, {space_name})
                else:
                    unique_files[c_key][2].add(space_name)

        return unique_files

    def _resolve_dirty_files_only(
        self,
        dirty_raw_paths: Iterable[str],
        target_spaces: List[FileSpaceConfig],
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

        loaded_spaces = _get_loaded_spaces(self.space_manager)
        proj_root = getattr(self.space_manager, "project_root", None)
        space_inc_roots: Dict[str, List[Path]] = {}
        for sp in target_spaces:
            if self.space_manager is not None and sp.name in loaded_spaces:
                inc_roots = [Path(r).resolve() for r in self.space_manager.resolve_space_include(sp.name)]
            else:
                inc_roots = [
                    Path(r).resolve()
                    for r in getattr(
                        sp,
                        "resolved_include_paths",
                        [Path(inc) for inc in getattr(sp, "include", [])],
                    )
                ]
            space_inc_roots[sp.name] = inc_roots

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
            for sp in target_spaces:
                entries = snap_entries_by_space.get(sp.name, {})
                fp_rec = entries.get(clean_p)
                if fp_rec is not None and not getattr(fp_rec, "is_deleted", False) and getattr(fp_rec, "source_root", ""):
                    src_root = Path(fp_rec.source_root)
                    _add_candidate(src_root / clean_p, src_root)
                    matched_this = True

            for sp in target_spaces:
                for inc_root in space_inc_roots.get(sp.name, []):
                    cand = inc_root / clean_p
                    if cand.is_file():
                        _add_candidate(cand, inc_root)
                        matched_this = True

            if proj_root is not None:
                cand_proj = Path(proj_root) / clean_p
                if cand_proj.is_file():
                    _add_candidate(cand_proj, Path(proj_root))
                    matched_this = True

            if not matched_this:
                norm_single = normalize_dirty_paths([clean_p])
                for sp in target_spaces:
                    entries = snap_entries_by_space.get(sp.name, {})
                    for rel_key, fp_rec in entries.items():
                        if getattr(fp_rec, "is_deleted", False) or not getattr(fp_rec, "source_root", ""):
                            continue
                        if is_dirty_file_match(rel_key, norm_single):
                            src_root = Path(fp_rec.source_root)
                            _add_candidate(src_root / rel_key, src_root)

        result: Dict[str, Tuple[Path, str, Set[str]]] = {}
        for c_key, (resolved_p, fallback_base) in candidate_files.items():
            matched_spaces: Set[str] = set()
            chosen_base = fallback_base
            for sp in target_spaces:
                entries = snap_entries_by_space.get(sp.name, {})
                for inc_root in space_inc_roots.get(sp.name, []):
                    try:
                        rel_to_inc = resolved_p.relative_to(inc_root).as_posix()
                    except ValueError:
                        continue
                    fp_rec = entries.get(rel_to_inc)
                    if fp_rec is not None and not getattr(fp_rec, "is_deleted", False):
                        matched_spaces.add(sp.name)
                        chosen_base = inc_root
                        break
                    if hasattr(sp, "is_file_included"):
                        try:
                            if sp.is_file_included(rel_to_inc):
                                matched_spaces.add(sp.name)
                                chosen_base = inc_root
                                break
                        except Exception:
                            matched_spaces.add(sp.name)
                            chosen_base = inc_root
                            break
                    else:
                        matched_spaces.add(sp.name)
                        chosen_base = inc_root
                        break
            if not matched_spaces and target_spaces:
                matched_spaces.add(target_spaces[0].name)
            if matched_spaces:
                relpath = self._get_project_relpath(resolved_p, chosen_base)
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
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        allow_parallel: bool = True,
    ) -> SemanticBundle:
        """Scan the union of all spaces, deduplicating physical files by canonical path."""
        target_spaces = self._resolve_target_spaces(spaces)
        unique_files = self._collect_space_files(target_spaces)
        self._last_bundle_unique_files = dict(unique_files)

        total_files = len(unique_files)
        all_symbols: List[UnifiedSymbol] = []
        self._file_symbols_cache.clear()
        self._file_call_sites_cache.clear()
        self._file_imports_cache.clear()

        tasks: List[Tuple[str, str, str, List[str]]] = []
        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            sorted_spaces = sorted(list(sp_set))
            tasks.append((c_key, str(f_path), relpath, sorted_spaces))

        has_custom_configs = bool(self.parser_registry.language_configs)
        cpu_cnt = os.cpu_count() or 1
        use_parallel = (
            allow_parallel
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
                        if len(item) == 5:
                            c_key, sym_dicts, site_dicts, imps, err = item
                        else:
                            c_key, sym_dicts, err = item  # type: ignore[misc]
                            site_dicts, imps = None, None
                        if progress_callback:
                            rel = unique_files[c_key][1]
                            progress_callback(rel, idx, total_files)
                        if err:
                            logger.warning(f"Failed parsing file '{c_key}' during parallel bundle: {err}")
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
            except Exception as pool_err:
                logger.warning(f"ProcessPoolExecutor error, falling back to serial parsing: {pool_err}")
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
                    logger.warning(f"Failed parsing file '{c_key}' during serial bundle: {err}")
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
        target_spaces: List[FileSpaceConfig],
        prefer_missing: bool = False,
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Set[str]:
        return _normalize_space_dirty_paths(
            raw_paths=raw_paths,
            target_spaces=target_spaces,
            space_manager=self.space_manager,
            scanner=self.scanner,
            file_symbols_cache=self._file_symbols_cache,
            prefer_missing=prefer_missing,
            snap_entries_by_space=snap_entries_by_space,
        )

    def bundle_dirty_files(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
    ) -> Tuple[Dict[str, List[UnifiedSymbol]], Set[str]]:
        """Parse only added/modified files in `dirty_diff` and evict deleted/modified cache entries."""
        target_spaces = self._resolve_target_spaces(spaces)
        snap_entries_by_space = _preload_snap_entries(self.scanner, target_spaces)
        expanded_added_mod = self._normalize_space_dirty_paths(
            dirty_diff.dirty_files,
            target_spaces,
            prefer_missing=False,
            snap_entries_by_space=snap_entries_by_space,
        )
        expanded_deleted = self._normalize_space_dirty_paths(
            dirty_diff.deleted,
            target_spaces,
            prefer_missing=True,
            snap_entries_by_space=snap_entries_by_space,
        )
        dirty_keys = set(expanded_added_mod | expanded_deleted)
        expanded_mod = self._normalize_space_dirty_paths(
            dirty_diff.modified,
            target_spaces,
            prefer_missing=False,
            snap_entries_by_space=snap_entries_by_space,
        )
        evict_norm = normalize_dirty_paths(expanded_deleted | expanded_mod)

        if evict_norm:
            all_cached_keys = (
                set(self._file_symbols_cache.keys())
                | set(self._file_call_sites_cache.keys())
                | set(self._file_imports_cache.keys())
            )
            keys_to_pop = [k for k in all_cached_keys if is_dirty_file_match(k, evict_norm)]
            for k in keys_to_pop:
                self._file_symbols_cache.pop(k, None)
                self._file_call_sites_cache.pop(k, None)
                self._file_imports_cache.pop(k, None)

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
                    logger.warning(f"Failed parsing dirty file '{c_key}': {err}")
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
            out_file = Path(target_path).resolve()
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
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
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
            unique_files = self._collect_space_files(target_spaces)
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
                logger.debug(f"Error extracting call sites/imports from '{f_path}': {exc}")

        return call_sites, imports_map

    def extract_all_call_sites_and_imports(
        self,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        return self._extract_call_sites_and_imports_core(spaces=spaces, dirty_file_paths=None)

    def extract_dirty_call_sites_and_imports(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        target_spaces = self._resolve_target_spaces(spaces)
        snap_entries_by_space = _preload_snap_entries(self.scanner, target_spaces)
        expanded_dirty = self._normalize_space_dirty_paths(
            dirty_diff.dirty_files,
            target_spaces,
            prefer_missing=False,
            snap_entries_by_space=snap_entries_by_space,
        )
        return self._extract_call_sites_and_imports_core(
            spaces=spaces,
            dirty_file_paths=expanded_dirty,
            snap_entries_by_space=snap_entries_by_space,
        )


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
    "restore_unaggregated_partial_symbol",
]
