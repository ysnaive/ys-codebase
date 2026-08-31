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
import tempfile
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .exceptions import KnowledgeDBError, SchemaValidationError
from .parsers.registry import ParserRegistry
from .scanner import FingerprintScanner, ScanDiffDetail
from .schema import SpaceConfig, SymbolCallSite, ThesaurusGroup, UnifiedSymbol
from .space import SpaceManager

logger = logging.getLogger("knowledge-db.bundler")

# 並發門檻常數
PARALLEL_BUNDLE_THRESHOLD = 10


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
        registry = ParserRegistry(register_defaults=True)
        with open(f_path_str, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        symbols = registry.parse_file(file_path=relpath, content=content, space=primary_space)
        results = []
        for sym in symbols:
            sym.metadata["spaces"] = sorted_spaces
            sym.metadata["space"] = primary_space
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
    thesaurus: List[ThesaurusGroup] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "space_name": self.space_name,
            "created_at": self.created_at,
            "symbol_count": len(self.symbols),
            "symbols": [s.to_dict() for s in self.symbols],
            "thesaurus": [list(g) for g in self.thesaurus],
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

        thesaurus_raw = data.get("thesaurus", [])
        thesaurus: List[ThesaurusGroup] = []
        for g in thesaurus_raw:
            if isinstance(g, list):
                thesaurus.append([str(w) for w in g])

        metadata = dict(data.get("metadata", {}))

        return cls(
            version=version,
            space_name=space_name,
            created_at=created_at,
            symbols=symbols,
            thesaurus=thesaurus,
            metadata=metadata,
        )


class SemanticBundler:
    """空間語意打包與導出/導入引擎 (支援動態門檻多進程並行打包)"""

    def __init__(
        self,
        space_manager: SpaceManager,
        parser_registry: Optional[ParserRegistry] = None,
        scanner: Optional[FingerprintScanner] = None,
    ):
        self.space_manager = space_manager
        self.parser_registry = parser_registry or ParserRegistry(register_defaults=True)
        self.scanner = scanner or FingerprintScanner(space_manager)
        self._file_symbols_cache: Dict[str, List[UnifiedSymbol]] = {}

    def clear_symbols_cache(self) -> None:
        """清空記憶體符號快取池"""
        self._file_symbols_cache.clear()

    def _get_project_relpath(self, f_path: Path, fallback_base: Path) -> str:
        """
        將檔案路徑轉譯為標準相對於 project:// 根目錄之路徑。
        若不在 project:// 目錄下或無法解析，則退回以 fallback_base 計算。
        """
        try:
            from core import uri
            p_res = uri.resolve("project://", interactive=False)
            if p_res:
                proj_root = Path(p_res).resolve()
                return os.path.relpath(str(f_path.resolve()), str(proj_root)).replace("\\", "/")
        except Exception:
            pass
        try:
            return os.path.relpath(str(f_path), str(fallback_base)).replace("\\", "/")
        except Exception:
            return f_path.name

    def bundle_space(
        self,
        space_config: SpaceConfig,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> SemanticBundle:
        """
        掃描並解析空間內所有有效來源檔案，提取符號與同義詞庫並封裝為 SemanticBundle。
        """
        space_name = space_config.name
        source_roots = self.space_manager.resolve_space_include(space_name)

        # 收集所有需解析的檔案路徑與相對路徑
        files_to_parse: List[tuple[Path, str]] = []  # (abs_path, relpath)

        for source_root in source_roots:
            if source_root.is_file():
                if space_config.is_file_included(source_root.name) and not FingerprintScanner._is_excluded(
                    source_root.name, space_config.exclude
                ):
                    relpath = self._get_project_relpath(source_root, source_root.parent)
                    files_to_parse.append((source_root, relpath))
            else:
                base_dir = source_root
                for root_dir, dirs, files in os.walk(str(source_root)):
                    rel_dir = os.path.relpath(root_dir, str(base_dir)).replace("\\", "/")
                    if rel_dir != "." and FingerprintScanner._is_excluded(rel_dir + "/", space_config.exclude):
                        dirs.clear()
                        continue

                    for f in files:
                        try:
                            f_path = Path(root_dir) / f
                            scan_rel = os.path.relpath(str(f_path), str(base_dir)).replace("\\", "/")
                            if not FingerprintScanner._is_excluded(scan_rel, space_config.exclude) and space_config.is_file_included(f):
                                relpath = self._get_project_relpath(f_path, base_dir)
                                files_to_parse.append((f_path, relpath))
                        except Exception:
                            pass

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

        thesaurus = self.space_manager.load_thesaurus()
        created_at = datetime.now(timezone.utc).isoformat()

        return SemanticBundle(
            version="1.0.0",
            space_name=space_name,
            created_at=created_at,
            symbols=all_symbols,
            thesaurus=thesaurus,
            metadata={
                "source_count": len(source_roots),
                "file_count": total_files,
                "origin": space_config.origin,
            },
        )

    def _collect_space_files(
        self, target_spaces: List[SpaceConfig]
    ) -> Dict[str, Tuple[Path, str, Set[str]]]:
        """收集所有實體檔案與其所屬空間集合: canonical_path -> (file_path, relpath, set_of_spaces)"""
        unique_files: Dict[str, Tuple[Path, str, Set[str]]] = {}

        for sp in target_spaces:
            space_name = sp.name
            source_roots = self.space_manager.resolve_space_include(space_name)

            for source_root in source_roots:
                if source_root.is_file():
                    if sp.is_file_included(source_root.name) and not FingerprintScanner._is_excluded(
                        source_root.name, sp.exclude
                    ):
                        c_key = str(source_root.resolve()).replace("\\", "/")
                        relpath = self._get_project_relpath(source_root, source_root.parent)
                        if c_key not in unique_files:
                            unique_files[c_key] = (source_root, relpath, {space_name})
                        else:
                            unique_files[c_key][2].add(space_name)
                else:
                    base_dir = source_root
                    files_to_check: List[Tuple[Path, str, os.stat_result]] = []
                    self.scanner._scan_entries_fast(base_dir, source_root, sp, files_to_check)
                    for f_path, scan_rel, _ in files_to_check:
                        c_key = str(f_path.resolve()).replace("\\", "/")
                        relpath = self._get_project_relpath(f_path, base_dir)
                        if c_key not in unique_files:
                            unique_files[c_key] = (f_path, relpath, {space_name})
                        else:
                            unique_files[c_key][2].add(space_name)

        return unique_files

    def bundle_union(
        self,
        spaces: Optional[List[SpaceConfig]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> SemanticBundle:
        """
        掃描全專案空間聯集 (Union Scope)，以實體檔案絕對路徑為唯一鍵去重，
        支援動態門檻多進程並行解析 AST (檔案數 >= 10 且 CPU > 1 啟用 ProcessPoolExecutor)。
        """
        target_spaces = spaces if spaces is not None else self.space_manager.get_union_spaces()
        unique_files = self._collect_space_files(target_spaces)

        total_files = len(unique_files)
        all_symbols: List[UnifiedSymbol] = []
        self._file_symbols_cache.clear()

        tasks: List[Tuple[str, str, str, List[str]]] = []
        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            sorted_spaces = sorted(list(sp_set))
            tasks.append((c_key, str(f_path), relpath, sorted_spaces))

        cpu_cnt = os.cpu_count() or 1
        use_parallel = (total_files >= PARALLEL_BUNDLE_THRESHOLD and cpu_cnt > 1)

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

        thesaurus = self.space_manager.load_thesaurus()
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
            thesaurus=thesaurus,
            metadata={
                "total_spaces": len(target_spaces),
                "total_files": total_files,
                "total_symbols": len(all_symbols),
                "files_map": files_map,
            },
        )

    def bundle_dirty_files(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[SpaceConfig]] = None,
    ) -> Tuple[Dict[str, List[UnifiedSymbol]], Set[str]]:
        """
        僅針對 dirty_diff 中 added 與 modified 的檔案執行 AST 解析，
        同步自 _file_symbols_cache 移除 deleted 與 modified 檔案的舊快取。
        """
        target_spaces = spaces if spaces is not None else self.space_manager.get_union_spaces()
        dirty_keys = dirty_diff.dirty_files

        # 1. 自快取中清除 deleted 與 modified 舊符號 (大小寫不敏感匹配)
        for d_key in dirty_diff.deleted | dirty_diff.modified:
            d_key_norm = d_key.replace("\\", "/").lower()
            keys_to_pop = [k for k in self._file_symbols_cache.keys() if k.replace("\\", "/").lower() == d_key_norm]
            for k in keys_to_pop:
                self._file_symbols_cache.pop(k, None)

        if not (dirty_diff.added or dirty_diff.modified):
            return {}, dirty_keys

        # 2. 收集空間對應
        space_files_map = self._collect_space_files(target_spaces)
        new_symbols_by_file: Dict[str, List[UnifiedSymbol]] = {}

        tasks: List[Tuple[str, str, str, List[str]]] = []
        for c_key in (dirty_diff.added | dirty_diff.modified):
            file_info = space_files_map.get(c_key)
            if not file_info:
                continue
            f_path, relpath, sp_set = file_info
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
        """
        以原子寫入方式導出 Bundle 為 JSON 檔案。
        """
        if target_path is not None:
            out_file = Path(target_path).resolve()
        else:
            storage_dir = self.space_manager.get_space_storage_dir(bundle.space_name)
            bundles_dir = storage_dir.parent.parent / "bundles"
            bundles_dir.mkdir(parents=True, exist_ok=True)
            out_file = bundles_dir / f"{bundle.space_name}.bundle.json"

        out_file.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(out_file.parent), prefix="bundle_tmp_", suffix=".json"
        )

        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(bundle.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(temp_path, str(out_file))
            logger.info(f"Successfully exported SemanticBundle for '{bundle.space_name}' to {out_file}")
            return out_file
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise KnowledgeDBError(f"Failed exporting bundle to {out_file}: {e}")

    def import_bundle(self, bundle_path: Union[str, Path]) -> SemanticBundle:
        """
        載入並反序列化 Bundle 檔案。
        """
        p = Path(bundle_path).resolve()
        if not p.exists():
            raise KnowledgeDBError(f"Bundle file not found at: {p}")

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            return SemanticBundle.from_dict(data)
        except Exception as e:
            raise KnowledgeDBError(f"Failed to import bundle from {p}: {e}")

    def extract_all_call_sites_and_imports(
        self,
        spaces: Optional[List[SpaceConfig]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        """
        掃描全專案空間聯集，提取所有檔案的 SymbolCallSite 清單與檔頭 Import 映射表。
        """
        target_spaces = spaces if spaces is not None else self.space_manager.get_union_spaces()
        unique_files = self._collect_space_files(target_spaces)

        all_call_sites: List[SymbolCallSite] = []
        all_imports: Dict[str, Dict[str, str]] = {}

        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            primary_space = sorted(list(sp_set))[0] if sp_set else "unified"
            try:
                with open(f_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                sites = self.parser_registry.extract_call_sites(
                    file_path=relpath, content=content, space=primary_space
                )
                imps = self.parser_registry.extract_imports(
                    file_path=relpath, content=content
                )
                all_call_sites.extend(sites)
                if imps:
                    all_imports[relpath] = imps
            except Exception as e:
                logger.debug(f"Error extracting call sites/imports from '{f_path}': {e}")

        return all_call_sites, all_imports

    def extract_dirty_call_sites_and_imports(
        self,
        dirty_diff: ScanDiffDetail,
        spaces: Optional[List[SpaceConfig]] = None,
    ) -> Tuple[List[SymbolCallSite], Dict[str, Dict[str, str]]]:
        """
        僅針對 dirty_diff 中 added 與 modified 檔案提取調用點與 Import 映射。
        """
        target_spaces = spaces if spaces is not None else self.space_manager.get_union_spaces()
        unique_files = self._collect_space_files(target_spaces)
        dirty_keys_norm = {k.replace("\\", "/").lower() for k in dirty_diff.dirty_files}

        dirty_call_sites: List[SymbolCallSite] = []
        dirty_imports: Dict[str, Dict[str, str]] = {}

        for c_key, (f_path, relpath, sp_set) in unique_files.items():
            c_key_norm = c_key.replace("\\", "/").lower()
            relpath_norm = relpath.replace("\\", "/").lower()

            is_dirty = any(
                c_key_norm == dk
                or c_key_norm.endswith("/" + dk)
                or relpath_norm == dk
                or relpath_norm.endswith("/" + dk)
                for dk in dirty_keys_norm
            )
            if not is_dirty:
                continue

            primary_space = sorted(list(sp_set))[0] if sp_set else "unified"
            try:
                with open(f_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                sites = self.parser_registry.extract_call_sites(
                    file_path=relpath, content=content, space=primary_space
                )
                imps = self.parser_registry.extract_imports(
                    file_path=relpath, content=content
                )
                dirty_call_sites.extend(sites)
                if imps:
                    dirty_imports[relpath] = imps
            except Exception as e:
                logger.debug(f"Error extracting dirty call sites/imports from '{f_path}': {e}")

        return dirty_call_sites, dirty_imports

