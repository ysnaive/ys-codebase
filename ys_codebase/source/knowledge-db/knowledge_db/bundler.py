"""
knowledge-db 語意打包引擎 (SemanticBundler) 與 Bundle 資料結構
"""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from core.vfs import write_bytes
from file_space import FingerprintScanner, ScanDiffDetail, FileSpaceConfig, FileSpaceManager

from .exceptions import KnowledgeDBError, SchemaValidationError
from .io_utils import is_dirty_file_match, normalize_dirty_paths
from .parsers.registry import ParserRegistry
from .schema import SymbolCallSite, UnifiedSymbol

logger = logging.getLogger("knowledge-db.bundler")

PARALLEL_BUNDLE_THRESHOLD = 10

_worker_registry: Optional[ParserRegistry] = None


def _extract_unaggregated_partial_state(sym: UnifiedSymbol) -> Tuple[List[Any], List[str], Dict[str, str], str]:
    """提取或還原分部符號在跨檔聚合前的單檔原始屬性 (own_members, own_base_types, own_field_types, own_docstring)。"""
    from .schema import MemberInfo
    meta = sym.metadata
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
    """將曾經執行過跨檔聚合之分部符號還原為單檔原始狀態，供單一分部退化或增量重聚合使用。"""
    if "_own_members" not in sym.metadata:
        return sym
    own_members, own_bases, own_fields, own_doc = _extract_unaggregated_partial_state(sym)
    new_meta = dict(sym.metadata)
    for k in ("_own_members", "_own_base_types", "_own_field_types", "_own_docstring", "partial_files", "is_primary_partial"):
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


def aggregate_partial_symbols(symbols: List[UnifiedSymbol]) -> List[UnifiedSymbol]:
    """
    針對同空間、同命名空間 (相同 FQN) 之 C# partial class/struct/interface 進行跨檔案符號與成員聚合。
    合併各分部宣告之 members/children、base_types、field_types 與 partial_files，
    並透過保存單檔原始 `_own_members` 確保倒排索引僅索引該檔案自身定義成員（消除 N^2 重複索引膨脹）。
    """
    if not symbols:
        return symbols

    from collections import defaultdict
    groups: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
    for idx, sym in enumerate(symbols):
        if sym.language == "c_sharp" and sym.kind in ("class", "struct", "interface"):
            sp_key = ",".join(sorted(sym.spaces)) if sym.spaces else ""
            fqn_key = sym.fqn or sym.name
            groups[(sp_key, sym.kind, fqn_key)].append(idx)

    updated = list(symbols)
    for _, indices in groups.items():
        if len(indices) <= 1:
            if len(indices) == 1 and "_own_members" in symbols[indices[0]].metadata:
                updated[indices[0]] = restore_unaggregated_partial_symbol(symbols[indices[0]])
            continue
        group_syms = [symbols[i] for i in indices]
        if not any(s.metadata.get("is_partial") or "partial " in (s.signature or "") for s in group_syms):
            continue

        merged_members = []
        seen_members = set()
        merged_bases: List[str] = []
        merged_fields: Dict[str, str] = {}
        partial_files: List[str] = []
        merged_docs: List[str] = []
        own_states = []

        for s in group_syms:
            own_m, own_b, own_f, own_d = _extract_unaggregated_partial_state(s)
            own_states.append((own_m, own_b, own_f, own_d))
            if s.file_path not in partial_files:
                partial_files.append(s.file_path)
            if own_d and own_d not in merged_docs:
                merged_docs.append(own_d)
            for m in own_m:
                m_key = (m.name, m.kind, m.signature)
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
            new_meta["is_primary_partial"] = (pos == primary_pos)
            new_meta["partial_files"] = list(partial_files)
            new_meta["_own_members"] = [m.to_dict() if hasattr(m, "to_dict") else m for m in own_m]
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


def _get_worker_registry() -> ParserRegistry:
    """獲取或初始化工作進程專屬的單例 ParserRegistry，避免重複讀取與編譯 Tree-sitter S-Expression"""
    global _worker_registry
    if _worker_registry is None:
        _worker_registry = ParserRegistry(register_defaults=True)
    return _worker_registry


def _parse_file_task_worker(
    task: Tuple[str, str, str, List[str]]
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """
    頂層可序列化工作者函式 (供 ProcessPoolExecutor 或串行調用)：
    task: (c_key, f_path_str, relpath, sorted_spaces)
    return: (c_key, [symbol.to_dict(), ...], error_message_or_None)
    """
    c_key, f_path_str, relpath, sorted_spaces = task
    primary_space = sorted_spaces[0] if sorted_spaces else "unified"
    try:
        registry = _get_worker_registry()
        with open(f_path_str, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        symbols = registry.parse_file(file_path=relpath, content=content, space=primary_space)
        results = []
        for sym in symbols:
            sym.metadata["spaces"] = sorted_spaces
            results.append(sym.to_dict())
        return (c_key, results, None)
    except Exception as e:
        return (c_key, [], str(e))


@dataclass(frozen=True)
class SemanticBundle:
    """自包含語意發布包資料模型"""

    version: str
    space_name: str
    created_at: str
    symbols: List[UnifiedSymbol] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "space_name": self.space_name,
            "created_at": self.created_at,
            "symbol_count": len(self.symbols),
            "symbols": [s.to_dict() for s in self.symbols],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticBundle":
        if not isinstance(data, dict):
            raise SchemaValidationError("SemanticBundle data must be a dictionary.")

        version = str(data.get("version", "1.0.0"))
        space_name = str(data.get("space_name", "unknown"))
        created_at = str(data.get("created_at", datetime.now(timezone.utc).isoformat()))

        symbols_raw = data.get("symbols", [])
        symbols = [
            UnifiedSymbol.from_dict(s) if isinstance(s, dict) else s
            for s in symbols_raw
        ]

        metadata = dict(data.get("metadata", {}))

        return cls(
            version=version,
            space_name=space_name,
            created_at=created_at,
            symbols=symbols,
            metadata=metadata,
        )


def _resolve_default_knowledge_storage_dir(project_root: Optional[Path] = None) -> Path:
    """解析 knowledge-db 專屬快取儲存根目錄 (`knowledge.storage://` -> `cache://knowledge-db/`)"""
    try:
        from core import uri
        res = uri.resolve("knowledge.storage://", interactive=False)
        if res:
            return Path(res).resolve()
    except Exception:
        pass
    base = project_root.resolve() if project_root else Path.cwd().resolve()
    if (base / "ys_codebase").is_dir():
        return base / "ys_codebase" / ".cache" / "knowledge-db"
    return base / ".cache" / "knowledge-db"


class SemanticBundler:
    """空間語意打包與導出/導入引擎 (支援動態門檻多進程並行打包)"""

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
            self.storage_dir = _resolve_default_knowledge_storage_dir(proj_root)
        self._file_symbols_cache: Dict[str, List[UnifiedSymbol]] = {}

    def _resolve_target_spaces(
        self, spaces: Optional[Iterable[Union[str, FileSpaceConfig]]] = None
    ) -> List[FileSpaceConfig]:
        """將空間名稱或 FileSpaceConfig 清單正規化為 FileSpaceConfig 實體清單"""
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
        """委派 FileSpaceManager 列舉指定空間內受納管之有效檔案"""
        if space_cfg.name in self.space_manager.load_spaces():
            return list(self.space_manager.iter_space_files(space_cfg.name))
        temp_mgr = FileSpaceManager(
            project_root=getattr(self.space_manager, "project_root", None),
            storage_root=getattr(self.space_manager, "storage_root", None),
            spaces_config={space_cfg.name: space_cfg},
        )
        return list(temp_mgr.iter_space_files(space_cfg.name))

    def _get_project_relpath(self, f_path: Path, fallback_base: Path) -> str:
        """
        將檔案路徑轉譯為標準相對於 project:// 根目錄之路徑。
        若不在 project:// 目錄下或無法解析，則退回以 fallback_base 計算。
        """
        try:
            proj_root = getattr(self.space_manager, "project_root", None)
            if proj_root is not None:
                rel = os.path.relpath(str(f_path.resolve()), str(Path(proj_root).resolve())).replace("\\", "/")
                if not rel.startswith(".."):
                    return rel
        except Exception:
            pass
        try:
            from core import uri
            p_res = uri.resolve("project://", interactive=False)
            if p_res:
                proj_root = Path(p_res).resolve()
                rel = os.path.relpath(str(f_path.resolve()), str(proj_root)).replace("\\", "/")
                if not rel.startswith(".."):
                    return rel
        except Exception:
            pass
        try:
            rel = os.path.relpath(str(f_path), str(fallback_base)).replace("\\", "/")
            if not rel.startswith(".."):
                base_name = Path(fallback_base).name
                return f"{base_name}/{rel}" if base_name else rel
        except Exception:
            pass
        return f_path.name

    def bundle_space(
        self,
        space_config: Union[str, FileSpaceConfig],
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> SemanticBundle:
        """掃描並解析空間內所有有效來源檔案，提取符號並封裝為 SemanticBundle。"""
        sp_cfg = (
            self.space_manager.get_space(space_config)
            if isinstance(space_config, str)
            else space_config
        )
        space_name = sp_cfg.name
        if space_name in self.space_manager.load_spaces():
            source_roots = self.space_manager.resolve_space_include(space_name)
        else:
            source_roots = [Path(inc) for inc in sp_cfg.include]
        files_to_parse: List[Tuple[Path, str]] = []

        for _, f_path, base_dir in self._iter_space_eligible_files(sp_cfg):
            relpath = self._get_project_relpath(f_path, base_dir)
            files_to_parse.append((f_path, relpath))

        total_files = len(files_to_parse)
        all_symbols: List[UnifiedSymbol] = []

        for idx, (f_path, relpath) in enumerate(files_to_parse, start=1):
            if progress_callback:
                progress_callback(relpath, idx, total_files)
            try:
                with open(f_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                symbols = self.parser_registry.parse_file(
                    file_path=relpath, content=content, space=space_name
                )
                all_symbols.extend(symbols)
            except Exception as e:
                logger.warning(f"Failed parsing file '{f_path}' during bundle: {e}")

        all_symbols = aggregate_partial_symbols(all_symbols)
        created_at = datetime.now(timezone.utc).isoformat()
        return SemanticBundle(
            version="1.0.0",
            space_name=space_name,
            created_at=created_at,
            symbols=all_symbols,
            metadata={
                "source_count": len(source_roots),
                "file_count": total_files,
                "origin": sp_cfg.origin,
            },
        )

    def _collect_space_files(
        self, target_spaces: List[FileSpaceConfig]
    ) -> Dict[str, Tuple[Path, str, Set[str]]]:
        """收集所有實體檔案與其所屬空間集合: canonical_path -> (file_path, relpath, set_of_spaces)"""
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

    def bundle_union(
        self,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        allow_parallel: bool = True,
    ) -> SemanticBundle:
        """
        掃描全專案空間聯集 (Union Scope)，以實體檔案絕對路徑為唯一鍵去重，
        支援動態門檻多進程並行解析 AST。
        """
        target_spaces = self._resolve_target_spaces(spaces)
        unique_files = self._collect_space_files(target_spaces)

        total_files = len(unique_files)
        all_symbols: List[UnifiedSymbol] = []
        self._file_symbols_cache.clear()

        tasks: List[Tuple[str, str, str, List[str]]] = []
        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            sorted_spaces = sorted(list(sp_set))
            tasks.append((c_key, str(f_path), relpath, sorted_spaces))

        cpu_cnt = os.cpu_count() or 1
        use_parallel = (allow_parallel and total_files >= PARALLEL_BUNDLE_THRESHOLD and cpu_cnt > 1)

        if use_parallel:
            try:
                workers = min(4, cpu_cnt)
                chunk_size = max(1, total_files // (workers * 4))
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    results_iter = pool.map(_parse_file_task_worker, tasks, chunksize=chunk_size)
                    for idx, (c_key, sym_dicts, err) in enumerate(results_iter, start=1):
                        if progress_callback:
                            rel = unique_files[c_key][1]
                            progress_callback(rel, idx, total_files)
                        if err:
                            logger.warning(f"Failed parsing file '{c_key}' during parallel bundle: {err}")
                            self._file_symbols_cache[c_key] = []
                            continue
                        file_symbols = [UnifiedSymbol.from_dict(d) for d in sym_dicts]
                        all_symbols.extend(file_symbols)
                        self._file_symbols_cache[c_key] = file_symbols
            except Exception as pool_err:
                logger.warning(f"ProcessPoolExecutor error, falling back to serial parsing: {pool_err}")
                use_parallel = False

        if not use_parallel:
            for idx, task in enumerate(tasks, start=1):
                c_key, sym_dicts, err = _parse_file_task_worker(task)
                if progress_callback:
                    rel = unique_files[c_key][1]
                    progress_callback(rel, idx, total_files)
                if err:
                    logger.warning(f"Failed parsing file '{c_key}' during serial bundle: {err}")
                    self._file_symbols_cache[c_key] = []
                    continue
                file_symbols = [UnifiedSymbol.from_dict(d) for d in sym_dicts]
                all_symbols.extend(file_symbols)
                self._file_symbols_cache[c_key] = file_symbols

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
    ) -> Set[str]:
        """
        將空間相對路徑（或絕對路徑）透過空間快照 source_root 或 include 根目錄正規化為 project:// 相對路徑與絕對路徑。
        針對單一無 '/' 之空間頂層檔名，優先透過快照紀錄精確反查，避免無差別擴展至其他空間之同名頂層檔。
        """
        expanded: Set[str] = set()
        raw_list = [str(p).replace("\\", "/").strip("/") for p in raw_paths if p]
        if not raw_list:
            return expanded

        snap_entries_by_space: Dict[str, Dict[str, Any]] = {}
        if self.scanner is not None and hasattr(self.scanner, "_load_or_recover_state"):
            for sp in target_spaces:
                try:
                    st, _ = self.scanner._load_or_recover_state(sp.name)
                    if st and st.entries:
                        snap_entries_by_space[sp.name] = st.entries
                except Exception:
                    pass

        for raw_p in raw_list:
            p_obj = Path(raw_p)
            if p_obj.is_absolute():
                expanded.add(raw_p)
                try:
                    c_abs = str(p_obj.resolve()).replace("\\", "/")
                    expanded.add(c_abs)
                    expanded.add(self._get_project_relpath(p_obj, p_obj.parent))
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
                    chosen_matches = [
                        fp for fp in pool if int(getattr(fp, "mtime_ns", 0)) >= best_mtime_ns
                    ]
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
                    expanded.add(self._get_project_relpath(cand_abs, src_root))
                    matched_from_snap = True

            if matched_from_snap:
                continue

            matching_candidates: List[Tuple[Path, Path]] = []
            for sp in target_spaces:
                inc_roots = (
                    self.space_manager.resolve_space_include(sp.name)
                    if sp.name in self.space_manager.load_spaces()
                    else sp.resolved_include_paths
                )
                for inc_root in inc_roots:
                    cand_abs = inc_root / raw_p
                    matching_candidates.append((cand_abs, inc_root))

            existing_cands = [(c, r) for c, r in matching_candidates if c.exists()]
            missing_cands = [(c, r) for c, r in matching_candidates if not c.exists()]
            if prefer_missing and missing_cands:
                if len(missing_cands) == 1:
                    cands_to_use = missing_cands
                else:
                    cached_missing = [
                        (c, r)
                        for c, r in missing_cands
                        if str(c.resolve()).replace("\\", "/") in self._file_symbols_cache
                    ]
                    cands_to_use = cached_missing or missing_cands
            else:
                if len(existing_cands) > 1 and "/" not in raw_p:
                    max_mtime = max((c.stat().st_mtime_ns for c, _ in existing_cands), default=0)
                    existing_cands = [
                        (c, r) for c, r in existing_cands if c.stat().st_mtime_ns >= max_mtime
                    ]
                cands_to_use = existing_cands if len(existing_cands) >= 1 else (
                    matching_candidates if len(matching_candidates) == 1 or "/" in raw_p else existing_cands
                )
            if cands_to_use:
                for cand_abs, inc_root in cands_to_use:
                    try:
                        c_abs = str(cand_abs.resolve()).replace("\\", "/")
                    except OSError:
                        c_abs = str(cand_abs).replace("\\", "/")
                    expanded.add(c_abs)
                    expanded.add(self._get_project_relpath(cand_abs, inc_root))
            else:
                expanded.add(raw_p)

        return expanded

    def bundle_dirty_files(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
    ) -> Tuple[Dict[str, List[UnifiedSymbol]], Set[str]]:
        """
        僅針對 dirty_diff 中 added 與 modified 的檔案執行 AST 解析，
        同步自 _file_symbols_cache 移除 deleted 與 modified 檔案的舊快取。
        """
        target_spaces = self._resolve_target_spaces(spaces)
        expanded_added_mod = self._normalize_space_dirty_paths(
            dirty_diff.dirty_files, target_spaces, prefer_missing=False
        )
        expanded_deleted = self._normalize_space_dirty_paths(
            dirty_diff.deleted, target_spaces, prefer_missing=True
        )
        dirty_keys = set(expanded_added_mod | expanded_deleted)
        expanded_mod = self._normalize_space_dirty_paths(
            dirty_diff.modified, target_spaces, prefer_missing=False
        )
        evict_norm = normalize_dirty_paths(expanded_deleted | expanded_mod)

        if evict_norm:
            keys_to_pop = [
                k for k in list(self._file_symbols_cache.keys())
                if is_dirty_file_match(k, evict_norm)
            ]
            for k in keys_to_pop:
                self._file_symbols_cache.pop(k, None)

        parse_targets_norm = normalize_dirty_paths(expanded_added_mod)
        if not parse_targets_norm:
            return {}, dirty_keys

        space_files_map = self._collect_space_files(target_spaces)
        new_symbols_by_file: Dict[str, List[UnifiedSymbol]] = {}

        tasks: List[Tuple[str, str, str, List[str]]] = []
        for c_key, (f_path, relpath, sp_set) in space_files_map.items():
            if is_dirty_file_match(c_key, parse_targets_norm) or is_dirty_file_match(relpath, parse_targets_norm):
                dirty_keys.add(c_key)
                dirty_keys.add(relpath)
                tasks.append((c_key, str(f_path), relpath, sorted(list(sp_set))))

        for task in tasks:
            c_key, sym_dicts, err = _parse_file_task_worker(task)
            if err:
                logger.warning(f"Failed parsing dirty file '{c_key}': {err}")
                self._file_symbols_cache[c_key] = []
                continue
            file_symbols = [UnifiedSymbol.from_dict(d) for d in sym_dicts]
            self._file_symbols_cache[c_key] = file_symbols
            new_symbols_by_file[c_key] = file_symbols

        return new_symbols_by_file, dirty_keys

    def export_bundle(
        self,
        bundle: SemanticBundle,
        target_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """以原子寫入方式導出 Bundle 為 JSON 檔案。"""
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
            logger.info(f"Successfully exported SemanticBundle for '{bundle.space_name}' to {out_file}")
            return out_file
        except Exception as e:
            raise KnowledgeDBError(f"Failed exporting bundle to {out_file}: {e}") from e

    def import_bundle(self, bundle_path: Union[str, Path]) -> SemanticBundle:
        """載入並反序列化 Bundle 檔案。"""
        p = Path(bundle_path).resolve()
        if not p.exists():
            raise KnowledgeDBError(f"Bundle file not found at: {p}")

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            return SemanticBundle.from_dict(data)
        except Exception as e:
            raise KnowledgeDBError(f"Failed to import bundle from {p}: {e}") from e

    def _extract_call_sites_and_imports_core(
        self,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
        dirty_file_paths: Optional[Iterable[str]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        """掃描空間聯集（或僅過濾髒檔案子集），提取 SymbolCallSite 清單與檔頭 Import 映射表。"""
        target_spaces = self._resolve_target_spaces(spaces)
        unique_files = self._collect_space_files(target_spaces)
        dirty_norm = normalize_dirty_paths(dirty_file_paths) if dirty_file_paths is not None else None

        call_sites: List[SymbolCallSite] = []
        imports_map: Dict[str, Dict[str, str]] = {}

        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            if dirty_norm is not None:
                if not (is_dirty_file_match(c_key, dirty_norm) or is_dirty_file_match(relpath, dirty_norm)):
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
                call_sites.extend(sites)
                if imps:
                    imports_map[relpath] = imps
            except Exception as e:
                logger.debug(f"Error extracting call sites/imports from '{f_path}': {e}")

        return call_sites, imports_map

    def extract_all_call_sites_and_imports(
        self,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        """掃描全專案空間聯集，提取所有檔案的 SymbolCallSite 清單與檔頭 Import 映射表。"""
        return self._extract_call_sites_and_imports_core(spaces=spaces, dirty_file_paths=None)

    def extract_dirty_call_sites_and_imports(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[Union[str, FileSpaceConfig]]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        """僅針對 dirty_diff 中變更檔案提取調用點與 Import 映射。"""
        target_spaces = self._resolve_target_spaces(spaces)
        expanded_dirty = self._normalize_space_dirty_paths(
            dirty_diff.dirty_files, target_spaces, prefer_missing=False
        )
        return self._extract_call_sites_and_imports_core(
            spaces=spaces, dirty_file_paths=expanded_dirty
        )
