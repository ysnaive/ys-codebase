"""
knowledge-db 索引生命週期與流水線引擎 (pipeline.py)
職責：
1. 單次解析共享 (Single-Parse Symbol Sharing)：透過 `ast_engine.ensure_jit_synced()` 取得 `ASTSnapshot`，零重複解析建置 BM25 倒排索引 (`build_unified_index`)
2. 向量特徵嵌入建置與持久化 (`VectorIndex`)
3. 雙水位線 (`ast_generation` vs `acked_ast_generation`) 極速 JIT 增量熱自癒修補管線 (`hot_patch_unified_index` / `sync_incremental_changes`)
4. 3 階段全域混合檢索編排 (`search`)
"""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from ast_engine import ASTEngine, SemanticBundler, get_engine as get_ast_engine
from core.context import (
    TaskCancelledError,
    cell_span,
    check_task_cancelled,
    get_runtime_context,
    get_virtual_cwd,
)
from core.log import ProgressReporter, log, log_debug, log_warn
from core.space import (
    ScanDiffDetail,
    ScanDiffResult,
    SpaceConfig,
    SpaceError,
    SpaceFileEntry,
    SpaceNotFoundError,
    SpaceRegistry,
    SpaceScanner,
    consume_diff,
    get_default_registry,
    get_default_scanner,
    is_watcher_active,
    reset_cursor,
    resolve_semantic_or_rel_path,
)

from .embedding import EmbeddingService, VectorIndex, format_symbol_embedding_text
from .exceptions import KnowledgeDBError
from .hybrid import HybridSearchEngine
from .io_utils import is_dirty_file_match, normalize_dirty_paths
from .retrieval import (
    BM25Engine,
    InvertedIndex,
    QueryFilter,
    SearchResult,
    SnippetExtractor,
    aggregate_ranked_symbol_hits,
    format_symbol_summary,
    normalize_ftypes,
)
from .schema import AggregatedFileResult, AggregatedItem, UnifiedSymbol
from .service import (
    clear_worker_state,
    get_active_worker,
    get_worker_busy_ms,
    is_worker_running,
    read_worker_state,
    wait_until_worker_idle,
)
from .tokenizer import MultilingualTokenizer


def _resolve_default_knowledge_storage_dir(project_root: Optional[Path] = None) -> Path:
    """解析 knowledge-db 預設持久儲存目錄 (`knowledge.storage://` 或 `.storage.local/knowledge-db`)"""
    from core import uri

    for scheme in ("knowledge.storage://", "storage.local://knowledge-db/"):
        try:
            res = uri.resolve(scheme, interactive=False)
            if res and not str(res).startswith("!undefined"):
                return Path(str(res)).resolve()
        except Exception:
            pass
    try:
        yscb_root = uri.resolve_yscb_root()
        if yscb_root:
            return Path(yscb_root).resolve() / ".storage.local" / "knowledge-db"
    except Exception:
        pass
    base = project_root.resolve() if project_root else Path(get_virtual_cwd()).resolve()
    return base / ".storage.local" / "knowledge-db"


def _normalize_ftypes(ftypes: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    norm = sorted(normalize_ftypes(ftypes))
    return norm or None


_CACHE_LOCK = threading.RLock()


def get_index_cache() -> Dict[str, Any]:
    """取得 RuntimeContext 綁定之統一索引快取字典（含 vector_dirty 跨實例同步標記）。"""
    ctx = get_runtime_context()
    cache = ctx.get_module_state("knowledge_db.pipeline.index_cache")
    if not isinstance(cache, dict):
        cache = {
            "storage_dir": None,
            "unified_index": None,
            "unified_mtime": 0.0,
            "vector_index": None,
            "vector_mtime": 0.0,
            "vector_dirty": False,
        }
        ctx.set_module_state("knowledge_db.pipeline.index_cache", cache)
    else:
        cache.setdefault("vector_dirty", False)
    return cache


_get_index_cache = get_index_cache


@dataclass(frozen=True)
class HotPatchResult:
    """
    標準熱修補結果資料模型
    """
    success: bool
    patched_count: int = 0
    vector_degraded: bool = False
    degrade_notice: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.success)


def _symbol_matches_filters(
    sym: Optional[UnifiedSymbol],
    score: float,
    target_spaces: Optional[List[str]],
    kinds: Optional[List[str]],
    languages: Optional[List[str]],
) -> bool:
    """無狀態純函式：檢驗符號是否通過搜尋過濾條件"""
    if sym is None or score <= 0:
        return False
    if target_spaces:
        sym_spaces = getattr(sym, "spaces", []) or []
        target_shorts = {t.split("/")[-1] for t in target_spaces}
        if not any(s in target_spaces or s.split("/")[-1] in target_shorts for s in sym_spaces):
            return False
    if kinds and sym.kind not in kinds:
        return False
    if languages and sym.language not in languages:
        return False
    return True


class IndexingPipeline:
    """多空間索引建置、JIT 增量熱補丁、持久化與混合檢索流水線"""

    def __init__(
        self,
        space_manager: SpaceRegistry,
        bundler: SemanticBundler,
        scanner: SpaceScanner,
        tokenizer: MultilingualTokenizer,
        bm25_engine: BM25Engine,
        embedding_service: EmbeddingService,
        hybrid_engine: HybridSearchEngine,
        ast_engine: Optional[ASTEngine] = None,
        snippet_extractor: Optional[SnippetExtractor] = None,
        config: Optional[Any] = None,
        storage_dir: Optional[Union[str, Path]] = None,
        space_weights_provider: Optional[Callable[[], Dict[str, float]]] = None,
        custom_storage_dir: Optional[bool] = None,
    ):
        self.space_manager = space_manager
        self.bundler = bundler
        self.scanner = scanner
        self.tokenizer = tokenizer
        self.bm25_engine = bm25_engine
        self.embedding_service = embedding_service
        self.hybrid_engine = hybrid_engine
        self.snippet_extractor = snippet_extractor or SnippetExtractor(space_manager=space_manager)
        self._space_weights_provider = space_weights_provider

        self._custom_storage_dir = (storage_dir is not None) if custom_storage_dir is None else bool(custom_storage_dir)
        if storage_dir is not None:
            self._storage_dir = Path(storage_dir).resolve()
        elif hasattr(bundler, "storage_dir") and bundler.storage_dir is not None:
            self._storage_dir = Path(bundler.storage_dir).resolve()
        else:
            proj_root = getattr(space_manager, "project_root", None)
            self._storage_dir = _resolve_default_knowledge_storage_dir(proj_root)

        if ast_engine is not None:
            self.ast_engine = ast_engine
        elif not self._custom_storage_dir and getattr(space_manager, "_raw_spaces", None) is None:
            self.ast_engine = get_ast_engine()
        else:
            self.ast_engine = ASTEngine(
                project_root=getattr(space_manager, "project_root", None),
                storage_dir=self._storage_dir / "ast" if self._custom_storage_dir else None,
                space_manager=space_manager,
                scanner=scanner,
            )

        if config is None:
            try:
                from .config import KnowledgeDBConfig
                config = KnowledgeDBConfig.load()
            except Exception:
                config = None
        self.config = config
        self._vector_degraded: bool = False
        self._last_degrade_notice: Optional[str] = None
        self._vector_index_dirty: bool = False

        self._unified_index: Optional[InvertedIndex] = None
        self._index_lock = threading.RLock()

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    def _storage_cache_key(self) -> str:
        try:
            return os.path.normcase(os.path.realpath(str(self._storage_dir)))
        except OSError:
            return os.path.normcase(str(self._storage_dir))

    @property
    def unified_index(self) -> Optional[InvertedIndex]:
        return self._unified_index

    @unified_index.setter
    def unified_index(self, val: Optional[InvertedIndex]) -> None:
        self._unified_index = val

    def get_indices_dir(self) -> Path:
        p = self.storage_dir / "indices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_meta_index_path(self) -> Path:
        return self.get_indices_dir() / "unified.meta.json"

    def _compute_vector_deficit_from_objects(
        self,
        idx: Optional[InvertedIndex],
        vec_idx: Optional[VectorIndex],
    ) -> Dict[str, Any]:
        total_syms = len(idx.symbols) if (idx is not None and idx.symbols) else 0
        expected_model = getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5")
        if getattr(vec_idx, "dim", None):
            expected_dim = int(vec_idx.dim)  # type: ignore[arg-type]
        elif getattr(self.embedding_service, "_dimension", None) is not None:
            expected_dim = int(self.embedding_service._dimension)  # type: ignore[arg-type]
        else:
            expected_dim = int(self.embedding_service._resolve_dimension_mock())
        if total_syms == 0:
            return {
                "total_symbols": 0,
                "embedded_count": 0,
                "missing_count": 0,
                "stale_count": 0,
                "coverage_pct": 100.0,
                "compatible": True,
                "dimension": expected_dim,
                "model_name": getattr(vec_idx, "model_name", None) or expected_model,
            }
        if vec_idx is None or vec_idx.vectors is None or len(vec_idx.doc_ids) == 0:
            return {
                "total_symbols": total_syms,
                "embedded_count": 0,
                "missing_count": total_syms,
                "stale_count": 0,
                "coverage_pct": 0.0,
                "compatible": False,
                "dimension": expected_dim,
                "model_name": getattr(vec_idx, "model_name", None) or expected_model,
            }
        if hasattr(vec_idx, "is_compatible_with") and not vec_idx.is_compatible_with(expected_model, expected_dim):
            return {
                "total_symbols": total_syms,
                "embedded_count": 0,
                "missing_count": total_syms,
                "stale_count": len(vec_idx.doc_ids),
                "coverage_pct": 0.0,
                "compatible": False,
                "dimension": expected_dim,
                "model_name": getattr(vec_idx, "model_name", None) or expected_model,
            }
        assert idx is not None
        sym_ids = set(idx.symbols.keys())
        vec_ids = set(vec_idx.doc_ids)
        missing_ids = sym_ids - vec_ids
        stale_ids = vec_ids - sym_ids
        valid_embedded = len(sym_ids & vec_ids)
        cov_pct = round((valid_embedded / total_syms) * 100.0, 1) if total_syms > 0 else 100.0
        return {
            "total_symbols": total_syms,
            "embedded_count": valid_embedded,
            "missing_count": len(missing_ids),
            "stale_count": len(stale_ids),
            "coverage_pct": cov_pct,
            "compatible": True,
            "dimension": expected_dim,
            "model_name": getattr(vec_idx, "model_name", None) or expected_model,
        }

    def _write_unified_meta(
        self,
        idx: Optional[InvertedIndex] = None,
        vec_idx: Optional[VectorIndex] = None,
    ) -> None:
        """Atomically persist lightweight `unified.meta.json` for O(1) `KnowledgeEngine.status()`."""
        eff_idx = idx if idx is not None else self._unified_index
        if eff_idx is None:
            return
        try:
            from core import vfs

            indices_dir = self.get_indices_dir()
            bin_file = indices_dir / "unified.index.bin.gz"
            vector_file = indices_dir / "unified.vectors.bin.gz"
            if not bin_file.exists():
                return
            b_st = bin_file.stat()
            v_mtime_ns = 0
            v_size = 0
            if vector_file.exists():
                v_st = vector_file.stat()
                v_mtime_ns = int(v_st.st_mtime_ns)
                v_size = int(v_st.st_size)

            eff_vec = vec_idx if vec_idx is not None else getattr(self.hybrid_engine, "vector_index", None)
            if (eff_vec is None or getattr(eff_vec, "vectors", None) is None) and vector_file.exists():
                # Preserve existing vector meta if vectors were not loaded into memory during skip_vectors patch
                prev_meta = None
                meta_p = self.get_meta_index_path()
                if meta_p.exists():
                    try:
                        prev_meta = json.loads(meta_p.read_text(encoding="utf-8"))
                    except Exception:
                        prev_meta = None
                if (
                    isinstance(prev_meta, dict)
                    and prev_meta.get("vectors_mtime_ns") == v_mtime_ns
                    and prev_meta.get("vectors_size") == v_size
                    and int(prev_meta.get("embedded_count", 0)) > 0
                ):
                    total_s = int(getattr(eff_idx, "doc_count", 0) or len(eff_idx.symbols))
                    emb_c = min(total_s, int(prev_meta.get("embedded_count", 0)))
                    miss_c = max(0, total_s - emb_c)
                    cov_p = round((emb_c / total_s) * 100.0, 1) if total_s > 0 else 100.0
                    vec_info = {
                        "embedded_count": emb_c,
                        "missing_count": miss_c,
                        "stale_count": int(prev_meta.get("stale_count", 0)),
                        "coverage_pct": cov_p,
                        "compatible": bool(prev_meta.get("vector_compatible", True)),
                        "dimension": int(prev_meta.get("vector_dim", 512)),
                        "model_name": str(prev_meta.get("vector_model_name", getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5"))),
                    }
                else:
                    vec_info = self._compute_vector_deficit_from_objects(eff_idx, eff_vec)
            else:
                vec_info = self._compute_vector_deficit_from_objects(eff_idx, eff_vec)

            space_sym_counts: Dict[str, int] = {}
            for s_obj in eff_idx.symbols.values():
                for sp_tag in (getattr(s_obj, "spaces", None) or ()):
                    space_sym_counts[sp_tag] = space_sym_counts.get(sp_tag, 0) + 1

            symbol_count = int(getattr(eff_idx, "doc_count", 0) or len(eff_idx.symbols))
            term_count = len(eff_idx.index) if hasattr(eff_idx, "index") else 0
            acked_ast_gen = int(getattr(eff_idx, "acked_ast_generation", 0) or 0)

            payload = {
                "symbol_count": symbol_count,
                "term_count": term_count,
                "acked_ast_generation": acked_ast_gen,
                "space_symbol_counts": space_sym_counts,
                "unified_mtime_ns": int(b_st.st_mtime_ns),
                "unified_size": int(b_st.st_size),
                "vectors_mtime_ns": v_mtime_ns,
                "vectors_size": v_size,
                "embedded_count": int(vec_info["embedded_count"]),
                "missing_count": int(vec_info["missing_count"]),
                "stale_count": int(vec_info["stale_count"]),
                "coverage_pct": float(vec_info["coverage_pct"]),
                "vector_compatible": bool(vec_info["compatible"]),
                "vector_dim": int(vec_info["dimension"]),
                "vector_model_name": str(vec_info["model_name"]),
            }
            vfs.write_json(str(self.get_meta_index_path()), payload, indent=2, atomic=True)
        except Exception as exc:
            log_debug(f"Failed writing knowledge-db unified.meta.json: {exc}")

    def get_persisted_meta(self) -> Optional[Dict[str, Any]]:
        """Read lightweight `unified.meta.json` if fresh against binary index mtimes/sizes (zero unpickle)."""
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"
        meta_file = indices_dir / "unified.meta.json"
        if not bin_file.exists() or not meta_file.exists():
            return None
        try:
            b_st = bin_file.stat()
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                return None
            if (
                meta.get("unified_mtime_ns") != int(b_st.st_mtime_ns)
                or meta.get("unified_size") != int(b_st.st_size)
            ):
                return None
            if vector_file.exists():
                v_st = vector_file.stat()
                if (
                    meta.get("vectors_mtime_ns") != int(v_st.st_mtime_ns)
                    or meta.get("vectors_size") != int(v_st.st_size)
                ):
                    return None
            elif int(meta.get("vectors_size", 0) or 0) != 0:
                return None
            return meta
        except Exception:
            return None

    def _reset_consumer_cursor(self, space_name: Optional[str] = None, consumer_id: str = "knowledge-db") -> None:
        """重置消費者增量游標"""
        if self.scanner is not None and hasattr(self.scanner, "reset_cursor"):
            self.scanner.reset_cursor(space_name, consumer_id=consumer_id)
        else:
            reset_cursor(space_name, consumer_id=consumer_id)

    @contextmanager
    def _consume_space_diff(
        self,
        space_name: Optional[str] = None,
        consumer_id: str = "knowledge-db",
        auto_refresh: Optional[bool] = None,
    ) -> Iterator[ScanDiffResult]:
        """以交易式 Context Manager 消費空間指紋差異並於無異常時自動推進游標"""
        if self.scanner is not None and hasattr(self.scanner, "consume_diff"):
            if auto_refresh is not None:
                with self.scanner.consume_diff(
                    space_name, consumer_id=consumer_id, auto_refresh=auto_refresh
                ) as diff_res:
                    yield diff_res
            else:
                with self.scanner.consume_diff(space_name, consumer_id=consumer_id) as diff_res:
                    yield diff_res
        else:
            with consume_diff(
                space_name, consumer_id=consumer_id, auto_refresh=auto_refresh
            ) as diff_res:
                yield diff_res

    def _has_pending_space_changes(self, auto_refresh: Optional[bool] = None) -> bool:
        """無副作用探測是否存在未消費之空間變更或 AST 水位線落差"""
        try:
            eff_refresh = (
                False
                if (
                    auto_refresh is False
                    or (
                        not self._custom_storage_dir
                        and getattr(self.space_manager, "_raw_spaces", None) is None
                        and is_watcher_active(project_root=getattr(self.space_manager, "project_root", None))
                    )
                )
                else True
            )
            if self.scanner is not None and hasattr(self.scanner, "diff"):
                indexed_qnames = self._get_indexed_space_qnames()
                if indexed_qnames:
                    for q_sp in indexed_qnames:
                        if self.scanner.diff(
                            q_sp, consumer_id="knowledge-db", auto_refresh=eff_refresh
                        ).has_changes:
                            return True
                elif self.scanner.diff(
                    consumer_id="knowledge-db", auto_refresh=eff_refresh
                ).has_changes:
                    return True
            if self._unified_index is not None:
                ast_gen = self.get_current_ast_generation()
                if ast_gen is not None and int(getattr(self._unified_index, "acked_ast_generation", 0) or 0) != ast_gen:
                    return True
        except Exception:
            pass
        return False

    def _align_index_symbols_with_ast_snapshot(self, idx: Optional[InvertedIndex]) -> None:
        """
        將反序列化之 InvertedIndex.symbols 與記憶體中已載入之 ASTEngine._snapshot.symbols 共享 UnifiedSymbol 參照，
        消除常駐進程中 6,800+ 個重複符號實例之雙份 Heap 佔用（若空間權重過濾後 spaces 不同則保留輕量淺拷貝）。
        """
        if idx is None or not idx.symbols or self.ast_engine is None:
            return
        try:
            snap = getattr(self.ast_engine, "_snapshot", None)
            if snap is None and hasattr(self.ast_engine, "_ensure_symbols_loaded"):
                self.ast_engine._ensure_symbols_loaded()
                snap = getattr(self.ast_engine, "_snapshot", None)
            if snap is None or not getattr(snap, "symbols", None):
                return
            indexed_spaces = self._get_indexed_space_names()
            weights = self._resolve_space_weights()
            snap_symbols = snap.symbols
            for doc_id in list(idx.symbols.keys()):
                ast_sym = snap_symbols.get(doc_id)
                if ast_sym is not None:
                    shared_sym = self._filter_symbol_for_indexed_spaces(ast_sym, indexed_spaces, weights=weights)
                    if shared_sym is not None:
                        idx.symbols[doc_id] = shared_sym
        except Exception as exc:
            log_debug(f"Aligning index symbols with AST snapshot skipped: {exc}")

    def _ensure_indices_loaded(
        self,
        load_vectors: bool = True,
        force_reload: bool = False,
        trim_memory: bool = True,
        **kwargs: Any,
    ) -> None:
        """微秒級比對磁碟快照 mtime，自動熱更新記憶體快取或從磁碟載入（保護記憶體中較新之未持久化微批次向量）。"""
        cache = _get_index_cache()
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"
        storage_key = self._storage_cache_key()

        with _CACHE_LOCK:
            if cache.get("storage_dir") != storage_key:
                cache["storage_dir"] = storage_key
                cache["unified_index"] = None
                cache["unified_mtime"] = 0.0
                cache["vector_index"] = None
                cache["vector_mtime"] = 0.0
                cache["vector_dirty"] = False

        if bin_file.exists():
            try:
                mtime = bin_file.stat().st_mtime
                with _CACHE_LOCK:
                    if force_reload or cache["unified_index"] is None or mtime > cache["unified_mtime"]:
                        loaded_idx = InvertedIndex.load_binary(bin_file, trim_memory=trim_memory)
                        self._align_index_symbols_with_ast_snapshot(loaded_idx)
                        cache["unified_index"] = loaded_idx
                        cache["unified_mtime"] = mtime
                    self._unified_index = cache["unified_index"]
            except Exception as e:
                log_warn(f"Failed loading unified index cache: {e}", stream="stderr")
        else:
            with _CACHE_LOCK:
                if cache["unified_mtime"] > 0.0:
                    cache["unified_index"] = None
                    cache["unified_mtime"] = 0.0
                    self._unified_index = None

        if load_vectors:
            if vector_file.exists():
                try:
                    mtime = vector_file.stat().st_mtime
                    with _CACHE_LOCK:
                        is_dirty = bool(
                            getattr(self, "_vector_index_dirty", False)
                            or cache.get("vector_dirty", False)
                        )
                        cur_mem_vec = cache.get("vector_index") or getattr(self.hybrid_engine, "vector_index", None)
                        has_dirty_in_mem = (
                            is_dirty
                            and cur_mem_vec is not None
                            and getattr(cur_mem_vec, "vectors", None) is not None
                            and len(getattr(cur_mem_vec, "doc_ids", ())) > 0
                        )
                        if not has_dirty_in_mem and (
                            force_reload or cache["vector_index"] is None or mtime > cache["vector_mtime"]
                        ):
                            loaded_vec = VectorIndex.load_binary(vector_file)
                            if (
                                force_reload
                                and cur_mem_vec is not None
                                and getattr(cur_mem_vec, "vectors", None) is not None
                                and mtime <= cache["vector_mtime"]
                                and len(getattr(cur_mem_vec, "doc_ids", ())) >= len(loaded_vec.doc_ids)
                            ):
                                cache["vector_index"] = cur_mem_vec
                            else:
                                cache["vector_index"] = loaded_vec
                                cache["vector_mtime"] = mtime
                        elif has_dirty_in_mem and cache.get("vector_index") is None:
                            cache["vector_index"] = cur_mem_vec
                        if cache["vector_index"] is not None:
                            self.hybrid_engine.vector_index = cache["vector_index"]
                except Exception as e:
                    log_warn(f"Failed loading vector index cache: {e}", stream="stderr")
            else:
                with _CACHE_LOCK:
                    is_dirty = bool(
                        getattr(self, "_vector_index_dirty", False)
                        or cache.get("vector_dirty", False)
                    )
                    if not is_dirty:
                        if cache["vector_mtime"] > 0.0 or cache["vector_index"] is not None:
                            cache["vector_index"] = None
                            cache["vector_mtime"] = 0.0
                            cache["vector_dirty"] = False
                            self.hybrid_engine.vector_index = VectorIndex()
                    elif cache.get("vector_index") is not None:
                        self.hybrid_engine.vector_index = cache["vector_index"]

    def _sync_ast_snapshot(self, force: bool = False, allow_parallel: bool = True) -> Any:
        """同步並取得最新 ASTSnapshot（僅於無磁碟快取或存在未消費變更時才強制重建）。"""
        ast_has_disk = (
            self.ast_engine._ensure_symbols_loaded()
            if hasattr(self.ast_engine, "_ensure_symbols_loaded")
            else self.ast_engine._ensure_loaded_from_disk()
        )
        has_ast_diff = False
        try:
            if self.scanner is not None and hasattr(self.scanner, "diff"):
                target_spaces = (
                    self.ast_engine.get_target_spaces()
                    if hasattr(self.ast_engine, "get_target_spaces")
                    else []
                )
                if target_spaces:
                    has_ast_diff = any(
                        bool(self.scanner.diff(sp_name, consumer_id="ast", auto_refresh=False).has_changes)
                        for sp_name in target_spaces
                    )
                else:
                    has_ast_diff = bool(self.scanner.diff(consumer_id="ast", auto_refresh=False).has_changes)
        except Exception:
            has_ast_diff = True
        ast_force = bool(force and (not ast_has_disk or has_ast_diff))
        try:
            return self.ast_engine.ensure_jit_synced(force=ast_force, allow_parallel=allow_parallel)
        except TypeError:
            return self.ast_engine.ensure_jit_synced(force=ast_force)

    def get_current_ast_generation(self) -> Optional[int]:
        """優先透過輕量 get_persisted_meta() 讀取當前 AST 快照世代水位，回退至 _ensure_loaded_from_disk()。"""
        try:
            if hasattr(self.ast_engine, "get_persisted_meta"):
                meta = self.ast_engine.get_persisted_meta()
                if isinstance(meta, dict) and "ast_generation" in meta:
                    return int(meta.get("ast_generation", 0) or 0)
            if self.ast_engine is not None and self.ast_engine._ensure_loaded_from_disk() and self.ast_engine._snapshot is not None:
                return int(self.ast_engine._snapshot.ast_generation)
        except Exception:
            pass
        return None

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
        allow_parallel: bool = True,
        skip_vectors: bool = False,
    ) -> InvertedIndex:
        """建置全專案空間聯集單一倒排索引與向量索引，並原子持久化至磁碟。"""
        with self._index_lock:
            return self._build_unified_index_locked(
                force=force,
                interactive=interactive,
                progress_callback=progress_callback,
                allow_parallel=allow_parallel,
                skip_vectors=skip_vectors,
            )

    def _build_unified_index_locked(
        self,
        force: bool = False,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
        allow_parallel: bool = True,
        skip_vectors: bool = False,
    ) -> InvertedIndex:
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"

        def _report(stage: int, name: str, elapsed_ms: float):
            if progress_callback:
                try:
                    progress_callback(stage, name, elapsed_ms)
                except Exception:
                    pass
            if interactive:
                log(f"[{stage}/4] {name} (耗時 {elapsed_ms:.1f}ms)", stream="stderr", flush=True)

        if not force and bin_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._align_index_symbols_with_ast_snapshot(idx)
                self._unified_index = idx
                if vector_file.exists():
                    try:
                        self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                    except Exception as ve:
                        log_warn(f"Failed loading unified vector index: {ve}", stream="stderr")

                if self._has_pending_space_changes():
                    sync_res = self.sync_incremental_changes(
                        skip_vectors=skip_vectors,
                        allow_parallel=allow_parallel,
                    )
                    if sync_res.get("status") in ("patched", "rebuilt") and self._unified_index is not None:
                        idx = self._unified_index

                ast_gen = self.get_current_ast_generation()
                gen_matched = (
                    ast_gen is None
                    or int(getattr(idx, "acked_ast_generation", 0) or 0) == ast_gen
                )
                enable_vec = getattr(self.config, "enable_vector_search", True)
                vec_ready = True
                if not skip_vectors and enable_vec and self.embedding_service.is_available:
                    deficit = self.get_vector_deficit_info()
                    if deficit.get("missing_count", 0) > 0 or not vector_file.exists():
                        vec_ready = False

                if gen_matched and vec_ready:
                    cache = _get_index_cache()
                    with _CACHE_LOCK:
                        cache["storage_dir"] = self._storage_cache_key()
                        cache["unified_index"] = idx
                        cache["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
                        if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                            cache["vector_index"] = self.hybrid_engine.vector_index
                            cache["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()
                    return idx
            except Exception as e:
                log_warn(f"Failed loading unified binary index, rebuilding: {e}", stream="stderr")

        t_all_start = time.time()
        prog = ProgressReporter(
            "knowledge-db",
            "正在建置知識庫索引",
            total_stages=4,
            enabled=False if interactive else None,
        )

        # Stage 1: Single-Parse Symbol Sharing via ASTEngine
        t0 = time.time()
        prog.stage(1, "同步 AST 符號快照")
        snapshot = self._sync_ast_snapshot(force=force, allow_parallel=allow_parallel)
        _report(1, f"AST 快照同步與符號共享 (gen={snapshot.ast_generation})", (time.time() - t0) * 1000)

        # Stage 2: Build BM25 InvertedIndex directly from ASTSnapshot.symbols (filtered to weighted spaces)
        t0 = time.time()
        indexed_spaces = self._get_indexed_space_names()
        weights = self._resolve_space_weights()
        filtered_symbols = [
            fs for fs in (
                self._filter_symbol_for_indexed_spaces(sym, indexed_spaces, weights=weights)
                for sym in snapshot.symbols.values()
            )
            if fs is not None
        ]
        prog.stage(2, "建置 BM25 倒排索引", 0, len(filtered_symbols))
        idx = InvertedIndex(space_name="unified")
        idx.build(
            filtered_symbols,
            tokenizer=self.tokenizer,
            space="unified",
            pre_aggregated=True,
        )
        idx.acked_ast_generation = snapshot.ast_generation
        prog.advance(len(filtered_symbols), len(filtered_symbols))
        _report(2, f"BM25 倒排索引建置 ({idx.doc_count} 符號)", (time.time() - t0) * 1000)

        # Stage 3: Build VectorIndex
        t0 = time.time()
        enable_vec = getattr(self.config, "enable_vector_search", True)
        built_vec_idx: Optional[VectorIndex] = None
        if skip_vectors:
            _report(3, "向量特徵嵌入 (交由背景 Stage 2 微批次同步，略過)", (time.time() - t0) * 1000)
        elif not enable_vec:
            _report(3, "向量特徵嵌入 (已依組態停用，略過)", (time.time() - t0) * 1000)
        elif self.embedding_service.is_available:
            try:
                sym_items = list(idx.symbols.items())
                doc_ids = [k for k, _ in sym_items]
                texts = [
                    format_symbol_embedding_text(sym)
                    for _, sym in sym_items
                ]
                model_name = getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5")
                prog.stage(3, "計算向量特徵嵌入", 0, len(texts))
                if texts:
                    if len(texts) > 128:
                        import numpy as np

                        vec_chunks = []
                        step_sz = 64
                        for v_off in range(0, len(texts), step_sz):
                            sub_t = texts[v_off : v_off + step_sz]
                            chunk_v = self.embedding_service.embed_texts(sub_t, batch_size=step_sz)
                            if getattr(chunk_v, "ndim", 0) != 2 or chunk_v.shape[0] != len(sub_t):
                                raise RuntimeError(
                                    f"Embedding batch returned {getattr(chunk_v, 'shape', None)} for {len(sub_t)} texts"
                                )
                            vec_chunks.append(chunk_v)
                            prog.advance(min(len(texts), v_off + len(sub_t)), len(texts))
                        vectors = np.vstack(vec_chunks).astype(np.float32)
                    else:
                        vectors = self.embedding_service.embed_texts(texts)
                        if getattr(vectors, "ndim", 0) != 2 or vectors.shape[0] != len(texts):
                            raise RuntimeError(
                                f"Embedding returned {getattr(vectors, 'shape', None)} for {len(texts)} texts"
                            )
                        prog.advance(len(texts), len(texts))
                    dim = vectors.shape[1] if hasattr(vectors, "shape") and len(vectors.shape) > 1 else None
                else:
                    import numpy as np
                    dim = self.embedding_service.dimension
                    vectors = np.zeros((0, dim), dtype=np.float32)
                vec_idx = VectorIndex(model_name=model_name, dim=dim)
                vec_idx.build(doc_ids, vectors)
                with self._kdb_index_file_lock():
                    vec_idx.save_binary(vector_file)
                self.hybrid_engine.vector_index = vec_idx
                built_vec_idx = vec_idx
                self._vector_index_dirty = False
                _report(3, f"向量特徵嵌入建置 ({len(doc_ids)} 符號向量)", (time.time() - t0) * 1000)
            except Exception as e:
                log_warn(f"Failed building/saving vector index: {e}", stream="stderr")
                _report(3, f"向量特徵嵌入建置失敗: {e}", (time.time() - t0) * 1000)
        else:
            reason_str = ""
            last_err = getattr(self.embedding_service, "last_error", None)
            if last_err and isinstance(last_err, dict):
                reason_str = f" ({last_err.get('error_type')}: {last_err.get('message')})"
            _report(3, f"向量特徵嵌入 (FastEmbed 不可用{reason_str}，略過)", (time.time() - t0) * 1000)

        # Stage 4: Atomic binary persistence & cursor alignment
        t0 = time.time()
        prog.stage(4, "持久化索引快照與同步游標")
        try:
            with self._kdb_index_file_lock():
                idx.save_binary(bin_file, compresslevel=1)
                self._write_unified_meta(idx=idx, vec_idx=built_vec_idx)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving unified binary index: {e}") from e

        self._align_space_watermarks()

        _report(4, "二進位索引原子持久化與游標同步", (time.time() - t0) * 1000)
        prog.finish(f"知識庫索引建置完成 (共 {idx.doc_count} 符號)")

        if interactive:
            total_elapsed = (time.time() - t_all_start) * 1000
            log(f"[knowledge-db] 全域索引建置完成，總耗時 {total_elapsed:.1f}ms", stream="stderr", flush=True)

        self._unified_index = idx
        self._vector_degraded = False
        self._last_degrade_notice = None
        cache = _get_index_cache()
        with _CACHE_LOCK:
            cache["storage_dir"] = self._storage_cache_key()
            cache["unified_index"] = idx
            cache["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
            if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                cache["vector_index"] = self.hybrid_engine.vector_index
                cache["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()
                if not skip_vectors:
                    cache["vector_dirty"] = False
        return idx

    def _align_space_watermarks(self, fast_ack_only: bool = False) -> None:
        """對齊空間增量游標與 AST 世代水位線"""
        try:
            if fast_ack_only or (
                not self._custom_storage_dir
                and getattr(self.space_manager, "_raw_spaces", None) is None
                and is_watcher_active(project_root=getattr(self.space_manager, "project_root", None))
            ):
                indexed_qnames = self._get_indexed_space_qnames()
                if indexed_qnames:
                    for q_sp in indexed_qnames:
                        with self._consume_space_diff(
                            space_name=q_sp, consumer_id="knowledge-db", auto_refresh=False
                        ):
                            pass
                     
                    if self.scanner is not None and hasattr(self.scanner, "ack"):
                        self.scanner.ack(None, consumer_id="knowledge-db")
                else:
                    with self._consume_space_diff(consumer_id="knowledge-db", auto_refresh=False):
                        pass
            else:
                with self._consume_space_diff(consumer_id="knowledge-db"):
                    pass
        except Exception as e:
            log_debug(f"Cursor alignment skipped: {e}")

    # ----------------------------------------------------------------------
    # 增量熱修補管線 (Single-Parse Symbol Sharing)
    # ----------------------------------------------------------------------

    def _resolve_index_lock_path(self) -> Path:
        if self._custom_storage_dir:
            return self.get_indices_dir() / ".kdb_index.lock"
        for scheme in ("knowledge.cache://.kdb_index.lock", "cache://knowledge-db/.kdb_index.lock"):
            try:
                from core import uri

                res = uri.resolve(scheme, interactive=False)
                if res and not str(res).startswith("!undefined"):
                    lock_path = Path(str(res)).resolve()
                    lock_path.parent.mkdir(parents=True, exist_ok=True)
                    return lock_path
            except Exception:
                pass
        try:
            from core import uri

            yscb_root = uri.resolve_yscb_root()
            if yscb_root:
                fallback = Path(yscb_root).resolve() / ".cache" / "knowledge-db" / ".kdb_index.lock"
                fallback.parent.mkdir(parents=True, exist_ok=True)
                return fallback
        except Exception:
            pass
        fallback = self.get_indices_dir() / ".kdb_index.lock"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

    @contextmanager
    def _kdb_index_file_lock(self) -> Iterator[None]:
        """Acquire a cross-process file lock before persisting binary index files."""
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            yield

    def sync_incremental_changes(
        self,
        *,
        space_name: Optional[str] = None,
        target_spaces: Optional[List[str]] = None,
        auto_refresh: Optional[bool] = None,
        skip_vectors: bool = False,
        allow_parallel: bool = True,
        require_vectors: bool = False,
        verbose: bool = False,
        consume_fn: Optional[Callable[..., Any]] = None,
    ) -> Dict[str, Any]:
        """
        統一增量同步管線：
        於 `self._index_lock` 與 `ExitStack` 交易保護下，保持所有目標空間之 `consume_ctx` 開啟，
        直到 `hot_patch_unified_index` 或 `build_unified_index` 完成落盤後才一次性 ACK 空間游標。
        """
        with self._index_lock:
            indices_dir = self.get_indices_dir()
            bin_file = indices_dir / "unified.index.bin.gz"
            self._ensure_indices_loaded(load_vectors=require_vectors)
            consume_ctx = consume_fn or self._consume_space_diff
            spaces_to_consume: List[Optional[str]] = (
                list(target_spaces) if target_spaces else [space_name]
            )

            def _invoke_rebuild() -> None:
                if skip_vectors:
                    self.build_unified_index(
                        force=True,
                        allow_parallel=allow_parallel,
                        skip_vectors=True,
                    )
                else:
                    self.build_unified_index(
                        force=True,
                        allow_parallel=allow_parallel,
                    )

            with ExitStack() as stack:
                merged_added: Set[str] = set()
                merged_modified: Set[str] = set()
                merged_deleted: Set[str] = set()
                unchanged_total = 0
                last_to_gen = 0
                for q_sp in spaces_to_consume:
                    diff_res = stack.enter_context(
                        consume_ctx(
                            space_name=q_sp,
                            consumer_id="knowledge-db",
                            auto_refresh=auto_refresh,
                        )
                    )
                    if diff_res:
                        last_to_gen = max(
                            last_to_gen, int(getattr(diff_res, "to_generation", 0) or 0)
                        )
                        unchanged_total += int(getattr(diff_res, "unchanged_count", 0) or 0)
                        if diff_res.has_changes:
                            merged_added.update(diff_res.detail.added)
                            merged_modified.update(diff_res.detail.modified)
                            merged_deleted.update(diff_res.detail.deleted)

                has_diff_changes = bool(merged_added or merged_modified or merged_deleted)
                if not bin_file.exists() and self._unified_index is None:
                    _invoke_rebuild()
                    return {
                        "status": "rebuilt",
                        "patched_count": len(merged_added | merged_modified | merged_deleted),
                        "vector_degraded": False,
                        "degrade_notice": None,
                        "to_generation": last_to_gen,
                    }

                if not has_diff_changes:
                    self._ensure_indices_loaded(load_vectors=require_vectors)
                    if self._unified_index is not None:
                        ast_gen_now = self.get_current_ast_generation()
                        if (
                            ast_gen_now is not None
                            and int(getattr(self._unified_index, "acked_ast_generation", 0) or 0) != ast_gen_now
                        ):
                            _invoke_rebuild()
                            return {
                                "status": "rebuilt",
                                "patched_count": 0,
                                "vector_degraded": False,
                                "degrade_notice": None,
                                "to_generation": last_to_gen,
                            }
                    return {
                        "status": "noop",
                        "patched_count": 0,
                        "vector_degraded": False,
                        "degrade_notice": None,
                        "to_generation": last_to_gen,
                    }

                combined_detail = ScanDiffDetail(
                    added=merged_added,
                    modified=merged_modified,
                    deleted=merged_deleted,
                )
                if verbose:
                    log(
                        f"[knowledge-db:auto-rebuild] Detected changes (+{len(merged_added)} ~{len(merged_modified)} -{len(merged_deleted)}), hot-rebuilding index...",
                        stream="stderr",
                        flush=True,
                    )
                t0 = time.time()
                patched = False
                patched_count = len(combined_detail.dirty_files)
                vec_deg = False
                degrade_notice = None
                if self._unified_index is not None:
                    res = self.hot_patch_unified_index(combined_detail, skip_vectors=skip_vectors)
                    patched = bool(res.success)
                    if patched:
                        patched_count = res.patched_count
                        vec_deg = res.vector_degraded
                        degrade_notice = res.degrade_notice

                if not patched:
                    _invoke_rebuild()

                elapsed_ms = max(1, int((time.time() - t0) * 1000))
                if verbose:
                    total_files = (
                        len(merged_added)
                        + len(merged_modified)
                        + len(merged_deleted)
                        + unchanged_total
                    )
                    log(
                        f"[knowledge-db:auto-rebuild] Index updated in {elapsed_ms}ms ({total_files} files).",
                        stream="stderr",
                        flush=True,
                    )
                if degrade_notice:
                    log(degrade_notice, stream="stderr", flush=True)

                return {
                    "status": "patched" if patched else "rebuilt",
                    "patched_count": patched_count,
                    "vector_degraded": vec_deg,
                    "degrade_notice": degrade_notice,
                    "to_generation": last_to_gen,
                }

    sync_lexical_index = sync_incremental_changes

    def hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Optional[Dict[str, Tuple[float, int]]] = None,
        timeout_seconds: Optional[float] = None,
        skip_vectors: bool = False,
    ) -> HotPatchResult:
        with self._index_lock:
            return self._hot_patch_unified_index_locked(
                diff_detail=diff_detail,
                timeout_seconds=timeout_seconds,
                skip_vectors=skip_vectors,
            )

    def _collect_all_dirty_files(
        self, diff_detail: ScanDiffDetail
    ) -> Tuple[List[UnifiedSymbol], Set[str], int]:
        """
        熱修補階段 1 (Single-Parse Symbol Sharing)：
        1. 透過 `self.ast_engine.ensure_jit_synced()` 讓 `ASTEngine` 依其 `"ast"` 游標完成單次增量解析與游標推進；
           若呼叫方直接傳入未經 `scanner` 消費之合成 `diff_detail`（致使 `ast_generation` 未推進），
           則補充執行 `self.ast_engine.hot_patch_index(detail)` 並對齊 `"ast"` 游標。
        2. 兩階段計算 `dirty_keys` 閉包（僅在含 `.cs` 變更時展開 C# `partial class` 跨檔閉包），
           再單次走訪 `ASTSnapshot.symbols` 收集所有受影響檔案之完整符號，防止未修改主檔之非 partial 符號被抹除。
        """
        detail = self.ast_engine._coerce_diff_detail(diff_detail)
        indexed_spaces = self._get_indexed_space_names()
        weights = self._resolve_space_weights()
        all_target_spaces = self.bundler._resolve_target_spaces(None)
        target_spaces = (
            [
                sp
                for sp in all_target_spaces
                if sp.short_name in indexed_spaces or sp.qualified_name in indexed_spaces
            ]
            if indexed_spaces
            else all_target_spaces
        )
        expanded_added_mod = self.bundler._normalize_space_dirty_paths(
            detail.dirty_files, target_spaces, prefer_missing=False
        )
        expanded_deleted = self.bundler._normalize_space_dirty_paths(
            detail.deleted, target_spaces, prefer_missing=True
        )
        dirty_keys: Set[str] = set(expanded_added_mod | expanded_deleted)

        current_acked_gen = int(getattr(self._unified_index, "acked_ast_generation", 0) or 0) if self._unified_index else 0
        parser_reg = getattr(self.ast_engine, "parser_registry", None) or getattr(self.bundler, "parser_registry", None)
        has_ast_parseable_dirty = True
        if parser_reg is not None and hasattr(parser_reg, "get_parser"):
            all_dirty_candidates = set(detail.dirty_files) | set(detail.deleted)
            if all_dirty_candidates:
                has_ast_parseable_dirty = any(
                    parser_reg.get_parser(str(p)) is not None for p in all_dirty_candidates
                )
            else:
                has_ast_parseable_dirty = False

        gen_before_sync = self.get_current_ast_generation() or 0
        snapshot = self.ast_engine.ensure_jit_synced(allow_parallel=False)
        ast_did_sync = snapshot.ast_generation > gen_before_sync
        if (
            not ast_did_sync
            and snapshot.ast_generation <= current_acked_gen
            and (detail.dirty_files or detail.deleted)
            and has_ast_parseable_dirty
        ):
            snapshot = self.ast_engine.hot_patch_index(detail)
        elif (
            not ast_did_sync
            and current_acked_gen > 0
            and (snapshot.ast_generation - current_acked_gen) > 1
            and (detail.dirty_files or detail.deleted)
            and has_ast_parseable_dirty
        ):
            known_snap_files = set(snapshot.file_to_symbol_ids.keys()) | set(snapshot.file_graphs.keys())
            need_synthetic_patch = bool(
                (expanded_added_mod - known_snap_files)
                or (expanded_deleted & known_snap_files)
            )
            if need_synthetic_patch:
                snapshot = self.ast_engine.hot_patch_index(detail)

        # If ASTEngine jumped multiple generations ahead of acked_ast_generation, reconcile all symbol diffs
        if (
            self._unified_index is not None
            and current_acked_gen > 0
            and (snapshot.ast_generation - current_acked_gen) > 1
        ):
            old_syms_map = self._unified_index.symbols
            new_syms_map = snapshot.symbols
            for sid, old_s in old_syms_map.items():
                new_s = new_syms_map.get(sid)
                if new_s is None or (
                    new_s.signature != old_s.signature
                    or new_s.docstring != old_s.docstring
                    or new_s.line_number != old_s.line_number
                ):
                    if old_s.file_path:
                        dirty_keys.add(old_s.file_path)
            for sid, new_s in new_syms_map.items():
                if sid not in old_syms_map and new_s.file_path:
                    if self._filter_symbol_for_indexed_spaces(new_s, indexed_spaces, weights=weights) is not None:
                        dirty_keys.add(new_s.file_path)

        dirty_paths_norm = normalize_dirty_paths(dirty_keys)

        # Pass 1: Expand dirty_keys closure across existing _unified_index and new snapshot.symbols for C# partial groups
        has_cs_dirty = any(str(k).lower().endswith(".cs") for k in dirty_keys)
        if has_cs_dirty:
            affected_cs_keys: Set[Tuple[str, str, str]] = set()
            if self._unified_index is not None:
                for old_sym in self._unified_index.symbols.values():
                    old_pf = (old_sym.metadata or {}).get("partial_files") or []
                    if is_dirty_file_match(old_sym.file_path, dirty_paths_norm) or any(
                        is_dirty_file_match(str(pf), dirty_paths_norm) for pf in old_pf
                    ):
                        dirty_keys.add(old_sym.file_path)
                        for pf in old_pf:
                            dirty_keys.add(str(pf))
                        if old_sym.language in ("c_sharp", "csharp") and old_sym.kind in ("class", "struct", "interface"):
                            sp_key = ",".join(sorted(old_sym.spaces)) if old_sym.spaces else ""
                            affected_cs_keys.add((sp_key, old_sym.kind, old_sym.fqn or old_sym.name))

            dirty_paths_norm = normalize_dirty_paths(dirty_keys)
            for raw_sym in snapshot.symbols.values():
                partial_files = (raw_sym.metadata or {}).get("partial_files") or []
                cs_key = (
                    (",".join(sorted(raw_sym.spaces)) if raw_sym.spaces else "", raw_sym.kind, raw_sym.fqn or raw_sym.name)
                    if raw_sym.language in ("c_sharp", "csharp") and raw_sym.kind in ("class", "struct", "interface")
                    else None
                )
                if (
                    is_dirty_file_match(raw_sym.file_path, dirty_paths_norm)
                    or any(is_dirty_file_match(str(pf), dirty_paths_norm) for pf in partial_files)
                    or (cs_key is not None and cs_key in affected_cs_keys)
                ):
                    dirty_keys.add(raw_sym.file_path)
                    for pf in partial_files:
                        dirty_keys.add(str(pf))
                    if cs_key is not None:
                        affected_cs_keys.add(cs_key)
            dirty_paths_norm = normalize_dirty_paths(dirty_keys)

        # Pass 2: Collect all symbols belonging to the expanded dirty_paths_norm closure
        all_new_symbols: List[UnifiedSymbol] = []
        seen_ids: Set[str] = set()
        for raw_sym in snapshot.symbols.values():
            sym = self._filter_symbol_for_indexed_spaces(raw_sym, indexed_spaces, weights=weights)
            if sym is None:
                continue
            partial_files = (sym.metadata or {}).get("partial_files") or []
            if is_dirty_file_match(sym.file_path, dirty_paths_norm) or any(
                is_dirty_file_match(str(pf), dirty_paths_norm) for pf in partial_files
            ):
                if sym.id not in seen_ids:
                    seen_ids.add(sym.id)
                    all_new_symbols.append(sym)

        return all_new_symbols, dirty_keys, snapshot.ast_generation

    def _evict_dirty_file_artifacts(
        self, dirty_keys: Set[str]
    ) -> Set[str]:
        """識別屬於 dirty_keys 之舊符號 doc_id 集合"""
        old_doc_ids: Set[str] = set()
        if self._unified_index is None:
            return old_doc_ids

        dirty_paths_norm = normalize_dirty_paths(dirty_keys)
        for doc_id, sym in list(self._unified_index.symbols.items()):
            if is_dirty_file_match(sym.file_path, dirty_paths_norm):
                old_doc_ids.add(doc_id)
        return old_doc_ids

    def _patch_vector_index_with_probe(
        self,
        all_new_symbols: List[UnifiedSymbol],
        old_doc_ids: Set[str],
        vector_file: Path,
        timeout_seconds: Optional[float],
    ) -> Tuple[bool, Optional[str]]:
        """執行向量索引增量修補與 10 符號動態探針熔斷"""
        enable_vec = getattr(self.config, "enable_vector_search", True)
        if not enable_vec:
            return False, None

        if (
            (self.hybrid_engine.vector_index is None or self.hybrid_engine.vector_index.vectors is None)
            and vector_file.exists()
        ):
            try:
                self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
            except Exception as ve:
                log_warn(f"Failed loading vector index for hot patch: {ve}", stream="stderr")

        vec_idx = self.hybrid_engine.vector_index
        expected_model = getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5")
        expected_dim = getattr(self.embedding_service, "dimension", getattr(vec_idx, "dim", 512))

        if vec_idx is None or vec_idx.vectors is None or not vector_file.exists():
            return True, (
                "[knowledge-db:notice] 向量索引未建立已降級（本次使用純 BM25 模式）。"
                "請執行 `python yscb.py knowledge-db index` 重建向量索引，"
                "或執行 `python yscb.py config set knowledge-db enable_vector_search false` 關閉向量語意搜尋。"
            )
        if hasattr(vec_idx, "is_compatible_with") and not vec_idx.is_compatible_with(expected_model, expected_dim):
            return True, (
                f"[knowledge-db:notice] 向量快取與當前模型 '{expected_model}' (維度要求: {expected_dim}) 不相容已降級（本次使用純 BM25 模式）。"
                "請執行 `python yscb.py knowledge-db index --force` 重建向量索引，"
                "或執行 `python yscb.py config set knowledge-db enable_vector_search false` 關閉向量語意搜尋。"
            )
        if not self.embedding_service.is_available:
            return False, None

        new_texts = [format_symbol_embedding_text(sym) for sym in all_new_symbols]
        num_symbols = len(new_texts)
        if num_symbols == 0:
            vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=[], new_vectors=None)
            try:
                with self._kdb_index_file_lock():
                    vec_idx.save_binary(vector_file)
                self._vector_index_dirty = False
            except Exception as ve:
                log_warn(f"Failed saving patched vector index: {ve}", stream="stderr")
            return False, None

        if num_symbols <= 10:
            try:
                new_vecs = self.embedding_service.embed_texts(new_texts)
                new_ids = [sym.id for sym in all_new_symbols]
                if getattr(new_vecs, "ndim", 0) != 2 or new_vecs.shape[0] != len(new_ids):
                    raise RuntimeError(f"Embedding returned {getattr(new_vecs, 'shape', None)} for {len(new_ids)} symbols")
                vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=new_ids, new_vectors=new_vecs)
                with self._kdb_index_file_lock():
                    vec_idx.save_binary(vector_file)
                self._vector_index_dirty = False
                return False, None
            except Exception as ve:
                log_warn(f"Failed patching vector index for <=10 symbols: {ve}", stream="stderr")
                return True, f"[knowledge-db:notice] 向量更新失敗已降級為純 BM25 模式: {ve}"

        try:
            probe_texts = new_texts[:10]
            probe_vecs, est_total = self.embedding_service.embed_texts_probe(probe_texts, total_count=num_symbols)
            if getattr(probe_vecs, "ndim", 0) != 2 or probe_vecs.shape[0] != len(probe_texts):
                raise RuntimeError(f"Probe embedding returned {getattr(probe_vecs, 'shape', None)} for {len(probe_texts)} symbols")
            if timeout_seconds is not None and est_total > timeout_seconds:
                return True, (
                    f"[knowledge-db:notice] 待向量化符號過多（{num_symbols} 個，預估耗時 {est_total:.1f}s > {timeout_seconds:.1f}s）已熔斷降級（本次使用純 BM25 模式）。"
                    "請執行 `python yscb.py knowledge-db index` 重建/更新向量索引，"
                    "或執行 `python yscb.py config set knowledge-db enable_vector_search false` 關閉向量語意搜尋。"
                )

            remaining_texts = new_texts[10:]
            remaining_vecs = self.embedding_service.embed_texts(remaining_texts) if remaining_texts else None
            if remaining_texts and (
                remaining_vecs is None
                or getattr(remaining_vecs, "ndim", 0) != 2
                or remaining_vecs.shape[0] != len(remaining_texts)
            ):
                raise RuntimeError(
                    f"Remaining embedding returned {getattr(remaining_vecs, 'shape', None)} for {len(remaining_texts)} symbols"
                )
            import numpy as np
            if remaining_vecs is not None:
                full_vecs = np.vstack([probe_vecs, remaining_vecs])
            else:
                full_vecs = probe_vecs

            new_ids = [sym.id for sym in all_new_symbols]
            vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=new_ids, new_vectors=full_vecs)
            with self._kdb_index_file_lock():
                vec_idx.save_binary(vector_file)
            self._vector_index_dirty = False
            return False, None
        except Exception as ve:
            log_warn(f"Dynamic probe or inference failed: {ve}", stream="stderr")
            return True, f"[knowledge-db:notice] 向量推論異常已降級為純 BM25 模式: {ve}"

    def _persist_patched_indices(
        self,
        bin_file: Path,
        vector_file: Path,
    ) -> None:
        """熱修補階段 4：原子持久化更新後之二進位索引與全域快取同步"""
        if self._unified_index is not None:
            with self._kdb_index_file_lock():
                self._unified_index.save_binary(bin_file, compresslevel=1)
                self._write_unified_meta(idx=self._unified_index)
        cache = _get_index_cache()
        with _CACHE_LOCK:
            cache["storage_dir"] = self._storage_cache_key()
            cache["unified_index"] = self._unified_index
            cache["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
            if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                cache["vector_index"] = self.hybrid_engine.vector_index
                if not getattr(self, "_vector_index_dirty", False):
                    cache["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()
                    cache["vector_dirty"] = False

    def _hot_patch_unified_index_locked(
        self,
        diff_detail: ScanDiffDetail,
        timeout_seconds: Optional[float] = None,
        skip_vectors: bool = False,
    ) -> HotPatchResult:
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"

        if self._unified_index is None and bin_file.exists():
            try:
                loaded_idx = InvertedIndex.load_binary(bin_file)
                self._align_index_symbols_with_ast_snapshot(loaded_idx)
                self._unified_index = loaded_idx
            except Exception as e:
                log_warn(f"Failed loading binary inverted index for hot patch: {e}", stream="stderr")

        if self._unified_index is None:
            return HotPatchResult(success=False, patched_count=0)

        if timeout_seconds is None:
            timeout_ms = getattr(self.config, "jit_vector_timeout_ms", None)
            if timeout_ms is not None:
                timeout_seconds = float(timeout_ms) / 1000.0
            else:
                timeout_seconds = getattr(self.config, "jit_vector_timeout_seconds", 3.0)

        persisted = False
        try:
            all_new_symbols, dirty_keys, new_ast_gen = self._collect_all_dirty_files(diff_detail)
            patched_removed = self._unified_index.patch_incremental(
                dirty_file_paths=dirty_keys,
                new_symbols=all_new_symbols,
                tokenizer=self.tokenizer,
                pre_aggregated=True,
            )
            old_doc_ids = set(patched_removed) if isinstance(patched_removed, (set, list, tuple)) else set()
            self._unified_index.acked_ast_generation = new_ast_gen

            if skip_vectors:
                if old_doc_ids and vector_file.exists():
                    try:
                        if (
                            self.hybrid_engine.vector_index is None
                            or self.hybrid_engine.vector_index.vectors is None
                        ):
                            self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                        vec_idx = self.hybrid_engine.vector_index
                        if vec_idx is not None and vec_idx.vectors is not None:
                            vec_idx.patch_incremental(
                                removed_doc_ids=old_doc_ids,
                                new_doc_ids=[],
                                new_vectors=None,
                            )
                            with self._kdb_index_file_lock():
                                vec_idx.save_binary(vector_file)
                            self._vector_index_dirty = False
                    except Exception as ve:
                        log_warn(f"Failed evicting old vectors during skip_vectors hot patch: {ve}", stream="stderr")
                vector_degraded = False
                degrade_notice = None
            else:
                vector_degraded, degrade_notice = self._patch_vector_index_with_probe(
                    all_new_symbols, old_doc_ids, vector_file, timeout_seconds
                )
            self._persist_patched_indices(bin_file, vector_file)
            persisted = True

            self._vector_degraded = vector_degraded
            self._last_degrade_notice = degrade_notice
            return HotPatchResult(
                success=True,
                patched_count=len(dirty_keys),
                vector_degraded=vector_degraded,
                degrade_notice=degrade_notice,
            )
        except TaskCancelledError:
            raise
        except Exception as e:
            log_warn(f"Incremental hot patch failed: {e}, falling back to full rebuild.", stream="stderr")
            self._vector_degraded = False
            self._last_degrade_notice = None
            return HotPatchResult(success=False, patched_count=0)
        finally:
            if not persisted:
                self._unified_index = None
                self.hybrid_engine.vector_index = VectorIndex()
                self._vector_index_dirty = False
                with _CACHE_LOCK:
                    c = _get_index_cache()
                    c["unified_index"] = None
                    c["unified_mtime"] = 0.0
                    c["vector_index"] = None
                    c["vector_mtime"] = 0.0
                    c["vector_dirty"] = False

    def get_vector_deficit_info(self) -> Dict[str, Any]:
        """比對 unified_index.symbols 與 vector_index.doc_ids，回傳向量差集與覆蓋率統計（零模型載入開銷）。"""
        with self._index_lock:
            self._ensure_indices_loaded(load_vectors=True, trim_memory=False)
            info = self._compute_vector_deficit_from_objects(
                self._unified_index,
                getattr(self.hybrid_engine, "vector_index", None),
            )
            return {
                "total_symbols": info["total_symbols"],
                "embedded_count": info["embedded_count"],
                "missing_count": info["missing_count"],
                "stale_count": info["stale_count"],
                "coverage_pct": info["coverage_pct"],
                "compatible": info["compatible"],
            }

    def flush_vector_index(self) -> bool:
        """原子持久化記憶體中之 vector_index 至 unified.vectors.bin.gz 並同步快取。"""
        with self._index_lock:
            vec_idx = getattr(self.hybrid_engine, "vector_index", None)
            if vec_idx is None or getattr(vec_idx, "vectors", None) is None:
                self._vector_index_dirty = False
                with _CACHE_LOCK:
                    _get_index_cache()["vector_dirty"] = False
                return False
            indices_dir = self.get_indices_dir()
            vector_file = indices_dir / "unified.vectors.bin.gz"
            with self._kdb_index_file_lock():
                vec_idx.save_binary(vector_file)
                eff_idx = self._unified_index or _get_index_cache().get("unified_index")
                if eff_idx is None and (indices_dir / "unified.index.bin.gz").exists():
                    try:
                        self._ensure_indices_loaded(load_vectors=False, trim_memory=False)
                        eff_idx = self._unified_index
                    except Exception:
                        eff_idx = None
                if eff_idx is not None:
                    self._write_unified_meta(idx=eff_idx, vec_idx=vec_idx)
            self._vector_index_dirty = False
            with _CACHE_LOCK:
                cache = _get_index_cache()
                cache["storage_dir"] = self._storage_cache_key()
                cache["vector_index"] = vec_idx
                cache["vector_mtime"] = (
                    vector_file.stat().st_mtime if vector_file.exists() else time.time()
                )
                cache["vector_dirty"] = False
            return True

    def sync_vector_deficit_step(self, batch_size: int = 32, persist: bool = True) -> Dict[str, int]:
        """
        執行單步微批次（Micro-batch）向量差集自癒：
        1. 鎖內選取待淘汰之陳舊 doc_ids 與前 batch_size 個缺少向量之符號文本。
        2. 鎖外執行 embedding_service.embed_texts()，避免阻塞前景檢索。
        3. 重新進入鎖內二次確認存活符號、更新記憶體 vector_index，並依 persist 參數或完成狀態原子持久化。
        回傳 {"embedded_in_step": int, "removed_stale": int, "remaining": int, "total_symbols": int}。
        """
        with self._index_lock:
            self._ensure_indices_loaded(load_vectors=True)

            idx = self._unified_index
            if idx is None or not idx.symbols:
                return {"embedded_in_step": 0, "removed_stale": 0, "remaining": 0, "total_symbols": 0}

            if not self.embedding_service.is_available:
                return {
                    "embedded_in_step": 0,
                    "removed_stale": 0,
                    "remaining": len(idx.symbols),
                    "total_symbols": len(idx.symbols),
                }

            expected_model = getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5")
            expected_dim = self.embedding_service.dimension
            vec_idx = getattr(self.hybrid_engine, "vector_index", None)

            if (
                vec_idx is None
                or vec_idx.vectors is None
                or (hasattr(vec_idx, "is_compatible_with") and not vec_idx.is_compatible_with(expected_model, expected_dim))
            ):
                vec_idx = VectorIndex(model_name=expected_model, dim=expected_dim)
                self.hybrid_engine.vector_index = vec_idx

            sym_ids_ordered = list(idx.symbols.keys())
            sym_ids_set = set(sym_ids_ordered)
            vec_ids_set = set(vec_idx.doc_ids)

            stale_ids = vec_ids_set - sym_ids_set
            missing_ids = [sid for sid in sym_ids_ordered if sid not in vec_ids_set]

            if not stale_ids and not missing_ids:
                if (getattr(self, "_vector_index_dirty", False) or _get_index_cache().get("vector_dirty", False)) and persist:
                    self.flush_vector_index()
                self._vector_degraded = False
                self._last_degrade_notice = None
                return {
                    "embedded_in_step": 0,
                    "removed_stale": 0,
                    "remaining": 0,
                    "total_symbols": len(sym_ids_ordered),
                }

            batch_ids = missing_ids[: max(1, int(batch_size))]
            batch_texts = [format_symbol_embedding_text(idx.symbols[sid]) for sid in batch_ids] if batch_ids else []

        new_vecs = None
        if batch_ids:
            new_vecs = self.embedding_service.embed_texts(batch_texts, batch_size=len(batch_texts))
            if new_vecs is None or len(new_vecs) != len(batch_ids):
                return {
                    "embedded_in_step": 0,
                    "removed_stale": 0,
                    "remaining": len(missing_ids),
                    "total_symbols": len(sym_ids_ordered),
                }

        with self._index_lock:
            idx = self._unified_index
            vec_idx = getattr(self.hybrid_engine, "vector_index", None)
            if idx is None or not idx.symbols or vec_idx is None:
                return {"embedded_in_step": 0, "removed_stale": 0, "remaining": 0, "total_symbols": 0}

            current_sym_ids = set(idx.symbols.keys())
            valid_batch_ids: List[str] = []
            valid_indices: List[int] = []
            if batch_ids and new_vecs is not None:
                for pos, sid in enumerate(batch_ids):
                    if sid in current_sym_ids:
                        valid_batch_ids.append(sid)
                        valid_indices.append(pos)

            valid_new_vecs = None
            if valid_batch_ids and new_vecs is not None:
                if len(valid_indices) == len(batch_ids):
                    valid_new_vecs = new_vecs
                else:
                    import numpy as np

                    arr = np.asarray(new_vecs, dtype=np.float32)
                    valid_new_vecs = arr[valid_indices]

            current_stale_ids = set(vec_idx.doc_ids) - current_sym_ids
            all_stale_to_remove = stale_ids | current_stale_ids

            vec_idx.model_name = expected_model
            vec_idx.dim = expected_dim
            vec_idx.patch_incremental(
                removed_doc_ids=all_stale_to_remove,
                new_doc_ids=valid_batch_ids,
                new_vectors=valid_new_vecs,
            )
            self.hybrid_engine.vector_index = vec_idx
            self._vector_index_dirty = True

            updated_vec_ids = set(vec_idx.doc_ids)
            remaining = len(current_sym_ids - updated_vec_ids)
            if remaining == 0:
                self._vector_degraded = False
                self._last_degrade_notice = None

            if persist or remaining == 0:
                self.flush_vector_index()
            else:
                with _CACHE_LOCK:
                    cache = _get_index_cache()
                    cache["storage_dir"] = self._storage_cache_key()
                    cache["vector_index"] = vec_idx
                    cache["vector_dirty"] = True

            return {
                "embedded_in_step": len(valid_batch_ids),
                "removed_stale": len(all_stale_to_remove),
                "remaining": remaining,
                "total_symbols": len(current_sym_ids),
            }

    def build_index(
        self,
        space: Optional[str] = None,
        force: bool = False,
        interactive: bool = False,
    ) -> Dict[str, InvertedIndex]:
        """
        建置統一倒排與向量索引；若指定 space 則自統一索引篩選該空間符號建構並回傳視圖
        （保持對外回傳結構相容，不再寫入孤兒單空間 .index.bin.gz）。
        """
        if space is not None:
            resolved_list = self.space_manager.resolve_spaces(space)
            sp = resolved_list[0]
        else:
            sp = None

        unified_idx = self.build_unified_index(force=force, interactive=interactive)
        if space is None or sp is None:
            return {"unified": unified_idx}

        weights = self._resolve_space_weights()
        if space in weights:
            sp_name = space
        elif sp.short_name in weights:
            sp_name = sp.short_name
        elif sp.qualified_name in weights:
            sp_name = sp.qualified_name
        else:
            sp_name = sp.short_name or sp.qualified_name

        match_keys = {space, sp_name, sp.short_name, sp.qualified_name}
        space_symbols = [
            sym for sym in unified_idx.symbols.values()
            if not sym.spaces or any(s in match_keys for s in sym.spaces)
        ]
        sp_idx = InvertedIndex(space_name=sp_name)
        sp_idx.build(
            space_symbols,
            tokenizer=self.tokenizer,
            space=sp_name,
            pre_aggregated=True,
        )
        sp_idx.acked_ast_generation = unified_idx.acked_ast_generation
        return {sp_name: sp_idx}

    def clean(self, space: Optional[str] = None) -> None:
        """清理指定空間或全空間之 Bundle 檔案與倒排索引快取。"""
        with self._index_lock:
            self._clean_locked(space=space)

    def _clean_locked(self, space: Optional[str] = None) -> None:
        if space is not None:
            targets = self.space_manager.resolve_spaces(space)
        else:
            targets = list(self.space_manager.list_spaces())
        for sp in targets:
            for candidate_name in {sp.short_name, sp.qualified_name.replace("/", "_")}:
                if not candidate_name:
                    continue
                bundle_file = self.storage_dir / "bundles" / f"{candidate_name}.bundle.json"
                if bundle_file.exists():
                    try:
                        bundle_file.unlink()
                    except OSError:
                        pass

                idx_file = self.storage_dir / "indices" / f"{candidate_name}.index.bin.gz"
                if idx_file.exists():
                    try:
                        idx_file.unlink()
                    except OSError:
                        pass

        indices_dir = self.storage_dir / "indices"
        worker_still_running = is_worker_running(indices_dir)
        with self._kdb_index_file_lock():
            for fn in [
                "unified.index.bin.gz",
                "unified.vectors.bin.gz",
                "unified.meta.json",
            ]:
                f_path = indices_dir / fn
                if f_path.exists():
                    try:
                        f_path.unlink()
                    except OSError:
                        pass
        try:
            clear_worker_state(indices_dir, worker_running=worker_still_running)
        except Exception:
            pass
        self._unified_index = None
        self._vector_index_dirty = False
        self.hybrid_engine.vector_index = VectorIndex()
        cache = _get_index_cache()
        with _CACHE_LOCK:
            cache["storage_dir"] = None
            cache["unified_index"] = None
            cache["unified_mtime"] = 0.0
            cache["vector_index"] = None
            cache["vector_mtime"] = 0.0
            cache["vector_dirty"] = False
        try:
            if space is not None:
                self._reset_consumer_cursor(space_name=space, consumer_id="knowledge-db")
            self._reset_consumer_cursor(space_name=None, consumer_id="knowledge-db")
        except Exception:
            pass

    # ----------------------------------------------------------------------
    # 3 階段檢索編排
    # ----------------------------------------------------------------------

    def _ensure_jit_index_ready(
        self,
        require_vectors: bool = False,
        auto_rebuild: bool = True,
        verbose: bool = False,
    ) -> InvertedIndex:
        with cell_span("kdb.jit_sync"):
            indices_dir = self.get_indices_dir()
            bin_file = indices_dir / "unified.index.bin.gz"
            worker_st = read_worker_state(indices_dir)
            worker_phase = str(worker_st.get("phase", "") or "")
            worker_active = is_worker_running(indices_dir)
            worker_busy = get_worker_busy_ms(indices_dir) > 0
            emb_svc = getattr(self, "embedding_service", None)
            has_local_model = True
            if emb_svc is not None and not getattr(emb_svc, "mock_mode", False):
                has_local_model = (
                    emb_svc.has_local_model()
                    if hasattr(emb_svc, "has_local_model")
                    else emb_svc.is_model_downloaded()
                )
            eff_require_vectors = bool(require_vectors and has_local_model)

            if bin_file.exists() or self._unified_index is not None:
                if worker_busy or (
                    worker_active
                    and (
                        worker_phase == "yielded_to_foreground"
                        or not auto_rebuild
                        or not self._has_pending_space_changes()
                    )
                ):
                    if worker_active:
                        active_w = get_active_worker()
                        if active_w is not None:
                            active_w.notify_space_changed()
                    load_vecs_fast = bool(
                        eff_require_vectors
                        and (not worker_busy or _get_index_cache().get("vector_index") is not None)
                    )
                    self._ensure_indices_loaded(load_vectors=load_vecs_fast)
                    if self._unified_index is not None:
                        return self._unified_index
                acquired = self._index_lock.acquire(blocking=False)
                if not acquired:
                    self._ensure_indices_loaded(load_vectors=eff_require_vectors)
                    if self._unified_index is not None:
                        return self._unified_index
                    with self._index_lock:
                        return self._ensure_jit_index_ready_locked(
                            require_vectors=eff_require_vectors,
                            auto_rebuild=auto_rebuild,
                            verbose=verbose,
                        )
                try:
                    return self._ensure_jit_index_ready_locked(
                        require_vectors=eff_require_vectors,
                        auto_rebuild=auto_rebuild,
                        verbose=verbose,
                    )
                finally:
                    self._index_lock.release()

            with self._index_lock:
                return self._ensure_jit_index_ready_locked(
                    require_vectors=eff_require_vectors,
                    auto_rebuild=auto_rebuild,
                    verbose=verbose,
                )

    def _ensure_jit_index_ready_locked(
        self,
        require_vectors: bool = False,
        auto_rebuild: bool = True,
        verbose: bool = False,
    ) -> InvertedIndex:
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"

        self._ensure_indices_loaded(load_vectors=require_vectors)

        if not bin_file.exists():
            if auto_rebuild:
                if verbose:
                    log(
                        "[knowledge-db:auto-rebuild] Unified index missing, building index...",
                        stream="stderr",
                        flush=True,
                    )
                self._reset_consumer_cursor(consumer_id="knowledge-db")
                self.build_unified_index(force=True)
            return self._unified_index  # type: ignore[return-value]

        if auto_rebuild:
            use_non_blocking_diff = bool(
                not self._custom_storage_dir
                and getattr(self.space_manager, "_raw_spaces", None) is None
                and is_watcher_active(project_root=getattr(self.space_manager, "project_root", None))
            )
            indexed_qnames = self._get_indexed_space_qnames() if use_non_blocking_diff else []
            self.sync_incremental_changes(
                target_spaces=indexed_qnames if indexed_qnames else None,
                auto_refresh=False if indexed_qnames else None,
                require_vectors=require_vectors,
                verbose=verbose,
            )

        if self._unified_index is None:
            self._ensure_indices_loaded(load_vectors=require_vectors, force_reload=True)
            if self._unified_index is None:
                self.build_unified_index(force=True)

        return self._unified_index

    def _resolve_space_weights(self) -> Dict[str, float]:
        """取得各空間之檢索加權係數"""
        if self._space_weights_provider is not None:
            try:
                return dict(self._space_weights_provider())
            except Exception:
                pass
        if hasattr(self.hybrid_engine, "space_weights") and self.hybrid_engine.space_weights is not None:
            return dict(self.hybrid_engine.space_weights)
        return {}

    def _get_indexed_space_names(self) -> Set[str]:
        """取得已宣告 `space_weights` 之受索引空間名稱集合（含 short_name 與 qualified_name）。"""
        weights = self._resolve_space_weights()
        names = set(weights.keys())
        try:
            for sp in self.space_manager.list_spaces():
                if sp.qualified_name in weights or sp.short_name in weights:
                    if sp.short_name:
                        names.add(sp.short_name)
                    if sp.qualified_name:
                        names.add(sp.qualified_name)
        except Exception:
            pass
        return names

    def _get_indexed_space_qnames(self) -> List[str]:
        """取得已宣告 `space_weights` 之受索引空間正規化 `qualified_name` 列表。"""
        weights = self._resolve_space_weights()
        qnames: List[str] = []
        try:
            for sp in self.space_manager.list_spaces(include_synthetic=False):
                if sp.qualified_name in weights or sp.short_name in weights:
                    q_name = sp.qualified_name or sp.short_name
                    if q_name and q_name not in qnames:
                        qnames.append(q_name)
        except Exception:
            pass
        return qnames

    def _filter_symbol_for_indexed_spaces(
        self,
        sym: UnifiedSymbol,
        indexed_spaces: Set[str],
        weights: Optional[Dict[str, float]] = None,
    ) -> Optional[UnifiedSymbol]:
        """過濾未納入 `space_weights` 之空間符號；若為跨空間符號則僅保留受索引空間標籤。"""
        if not indexed_spaces:
            return sym
        raw_spaces = list(getattr(sym, "spaces", []) or [])
        if not raw_spaces:
            return sym
        eff_weights = weights if weights is not None else self._resolve_space_weights()
        valid_spaces: List[str] = []
        for s in raw_spaces:
            s_short = s.split("/")[-1]
            if s in indexed_spaces or s_short in indexed_spaces:
                norm_s = s if s in eff_weights else (s_short if s_short in eff_weights else s_short)
                if norm_s not in valid_spaces:
                    valid_spaces.append(norm_s)
        if not valid_spaces:
            return None
        if valid_spaces == raw_spaces:
            return sym
        new_meta = dict(sym.metadata or {})
        new_meta["spaces"] = valid_spaces
        return replace(sym, metadata=new_meta)

    def _resolve_vector_availability_with_worker_tolerance(
        self,
        want_vectors: bool,
    ) -> bool:
        """
        根據後台 Worker 忙碌毫秒數 (`is_worker_busy() -> int`) 與 `jit_vector_timeout_ms`
        動態判定是否等待剩餘容差或立即降級為純 BM25。
        """
        if not want_vectors:
            return False

        indices_dir = self.get_indices_dir()
        worker_st = read_worker_state(indices_dir)
        worker_phase = str(worker_st.get("phase", "") or "")
        worker_active = is_worker_running(indices_dir)
        emb_svc = getattr(self, "embedding_service", None)

        if emb_svc is not None and not getattr(emb_svc, "mock_mode", False):
            has_local = (
                emb_svc.has_local_model()
                if hasattr(emb_svc, "has_local_model")
                else emb_svc.is_model_downloaded()
            )
            if not has_local:
                if worker_active or worker_phase == "downloading_model":
                    active_w = get_active_worker()
                    if active_w is not None:
                        active_w.notify_space_changed()
                    log("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", stream="stderr", flush=True)
                    return False
                if hasattr(emb_svc, "emit_missing_model_guard_if_needed"):
                    emb_svc.emit_missing_model_guard_if_needed()
                elif hasattr(emb_svc, "check_availability"):
                    emb_svc.check_availability(interactive=True)
                return False

        if worker_phase in ("downloading_model", "degraded_offline"):
            if worker_phase == "downloading_model" or bool(worker_st.get("busy", False)):
                log("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", stream="stderr", flush=True)
            return False

        timeout_ms = int(getattr(self.config, "jit_vector_timeout_ms", 3000) or 0)
        elapsed_ms = get_worker_busy_ms(indices_dir)

        if elapsed_ms > 0:
            if elapsed_ms >= timeout_ms:
                log("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", stream="stderr", flush=True)
                return False

            remain_ms = max(0, timeout_ms - elapsed_ms)
            became_idle = wait_until_worker_idle(indices_dir, remain_ms)
            if not became_idle:
                log("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", stream="stderr", flush=True)
                return False
            post_st = read_worker_state(indices_dir)
            post_phase = str(post_st.get("phase", "") or "")
            self._ensure_indices_loaded(
                load_vectors=True,
                force_reload=(post_phase != "yielded_to_foreground"),
            )

        if worker_active and not self.hybrid_engine.is_vector_available:
            active_w = get_active_worker()
            if active_w is not None:
                active_w.notify_space_changed()
            log("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]", stream="stderr", flush=True)
            return False

        return bool(self.hybrid_engine.is_vector_available)

    def _prepare_search_context_and_filters(
        self,
        space: Optional[Union[str, List[str]]],
        kinds: Optional[List[str]],
        languages: Optional[List[str]],
        ftypes: Optional[Union[str, List[str]]],
        min_score: float,
        limit: int,
        lexical_only: bool,
        auto_rebuild: bool,
        verbose: bool,
    ) -> Tuple[Optional[InvertedIndex], QueryFilter, Optional[List[str]], Optional[List[str]], bool]:
        """檢索階段 1：準備索引上下文、過濾器與向量可用性判定"""
        enable_vec = getattr(self.config, "enable_vector_search", True)
        want_vectors = enable_vec and not lexical_only

        self._vector_degraded = False

        unified_index = self._ensure_jit_index_ready(
            require_vectors=want_vectors,
            auto_rebuild=auto_rebuild,
            verbose=verbose,
        )
        target_spaces = [space] if isinstance(space, str) else list(space) if space else None
        target_ftypes = _normalize_ftypes(ftypes)
        space_weights = self._resolve_space_weights()
        if hasattr(self, "hybrid_engine") and self.hybrid_engine is not None:
            self.hybrid_engine.space_weights = space_weights
        flt = QueryFilter(
            spaces=target_spaces,
            languages=languages,
            kinds=kinds,
            ftypes=target_ftypes,
            min_score=min_score,
            limit=limit,
            space_weights=space_weights if space_weights else None,
        )
        effective_want_vectors = want_vectors and not getattr(self, "_vector_degraded", False)
        can_use_vector = self._resolve_vector_availability_with_worker_tolerance(effective_want_vectors)
        return unified_index, flt, target_spaces, target_ftypes, can_use_vector

    def _execute_lexical_and_vector_retrieval(
        self,
        query: str,
        unified_index: InvertedIndex,
        flt: QueryFilter,
        target_spaces: Optional[List[str]],
        target_ftypes: Optional[List[str]],
        kinds: Optional[List[str]],
        languages: Optional[List[str]],
        limit: int,
        aggregate: bool,
        can_use_vector: bool,
    ) -> Union[List[AggregatedFileResult], List[SearchResult]]:
        """檢索階段 2：執行混合 RRF 或純 BM25 檢索與檔案聚合"""
        if not aggregate:
            if can_use_vector:
                self.hybrid_engine.inverted_index = unified_index
                self.hybrid_engine.bm25_engine = self.bm25_engine
                hybrid_hits = self.hybrid_engine.search(
                    query=query,
                    limit=limit,
                    file_types=target_ftypes,
                    spaces=target_spaces,
                    kinds=kinds,
                    languages=languages,
                    lexical_only=False,
                    min_score=flt.min_score,
                )
                raw_results: List[SearchResult] = []
                for h in hybrid_hits:
                    sym = h["symbol"]
                    if sym is None or h["score"] <= 0:
                        continue
                    raw_results.append(
                        SearchResult(
                            symbol=sym,
                            score=h["score"],
                            matched_terms=h.get("matched_terms", []),
                            space=sym.spaces[0] if getattr(sym, "spaces", None) else "",
                            snippet=format_symbol_summary(sym),
                        )
                    )
                return raw_results
            return self.bm25_engine.search(query=query, index=unified_index, filter_cfg=flt)

        if can_use_vector:
            self.hybrid_engine.inverted_index = unified_index
            self.hybrid_engine.bm25_engine = self.bm25_engine
            sym_pool_cap = max(limit * 32, min(len(unified_index.symbols), 1000), 60)
            hybrid_agg_hits = self.hybrid_engine.search(
                query=query,
                limit=sym_pool_cap,
                file_types=target_ftypes,
                spaces=target_spaces,
                kinds=kinds,
                languages=languages,
                lexical_only=False,
                min_score=flt.min_score,
            )
            ranked_tuples = [
                (
                    h["symbol"],
                    float(h["score"]),
                    h.get("matched_terms", []),
                    getattr(h["symbol"], "spaces", ()),
                )
                for h in hybrid_agg_hits
                if h["symbol"] is not None and h["score"] > 0
            ]
            return aggregate_ranked_symbol_hits(ranked_tuples, limit=limit, alpha=0.2, top_k_items_per_file=3)

        return self.bm25_engine.search_aggregated(query=query, index=unified_index, filter_cfg=flt)

    def _enrich_snippets_and_expand_ast(
        self,
        raw_results: Union[List[AggregatedFileResult], List[SearchResult]],
        aggregate: bool,
        snippet: bool,
        context_lines: int = 3,
    ) -> Union[List[AggregatedFileResult], List[SearchResult]]:
        """檢索階段 3：為命中符號或聚合項目延遲提取原始碼切片"""
        if not snippet:
            return raw_results

        ctx_before = max(0, context_lines)
        ctx_after = max(ctx_before, 8)

        if not aggregate:
            results_with_snippets: List[SearchResult] = []
            for r in raw_results:  # type: ignore[union-attr]
                snip = self.snippet_extractor.extract(
                    file_path=r.symbol.file_path,
                    line_number=r.symbol.line_number,
                    end_line=r.symbol.end_line,
                    context_before=ctx_before,
                    context_after=ctx_after,
                    docstring=r.symbol.docstring,
                    space=r.space,
                )
                results_with_snippets.append(
                    SearchResult(
                        symbol=r.symbol,
                        score=r.score,
                        matched_terms=r.matched_terms,
                        space=r.space,
                        snippet=r.snippet,
                        code_snippet=snip,
                    )
                )
            return results_with_snippets

        agg_with_snippets: List[AggregatedFileResult] = []
        for file_res in raw_results:  # type: ignore[union-attr]
            updated_items: List[AggregatedItem] = []
            for itm in file_res.items:
                snip = self.snippet_extractor.extract(
                    file_path=itm.symbol.file_path,
                    line_number=itm.symbol.line_number,
                    end_line=itm.symbol.end_line,
                    context_before=ctx_before,
                    context_after=ctx_after,
                    docstring=itm.symbol.docstring,
                    space=file_res.spaces[0] if file_res.spaces else None,
                )
                updated_items.append(
                    AggregatedItem(
                        symbol=itm.symbol,
                        score=itm.score,
                        matched_terms=itm.matched_terms,
                        snippet=itm.snippet,
                        code_snippet=snip,
                    )
                )
            agg_with_snippets.append(
                AggregatedFileResult(
                    file_path=file_res.file_path,
                    total_score=file_res.total_score,
                    items=updated_items,
                    spaces=file_res.spaces,
                    language=file_res.language,
                )
            )
        return agg_with_snippets

    def search(
        self,
        query: str,
        space: Optional[Union[str, List[str]]] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
        min_score: float = 0.0,
        limit: int = 10,
        snippet: bool = False,
        context_lines: int = 3,
        auto_rebuild: bool = True,
        verbose: bool = False,
        aggregate: bool = True,
        lexical_only: bool = False,
        adaptive_limit: bool = False,
    ) -> Union[List[AggregatedFileResult], List[SearchResult]]:
        """全域聯集多欄位加權語意檢索"""
        if not query or not query.strip():
            return []

        unified_index, flt, target_spaces, target_ftypes, can_use_vector = self._prepare_search_context_and_filters(
            space=space,
            kinds=kinds,
            languages=languages,
            ftypes=ftypes,
            min_score=min_score,
            limit=limit,
            lexical_only=lexical_only,
            auto_rebuild=auto_rebuild,
            verbose=verbose,
        )
        if not unified_index or unified_index.doc_count == 0:
            return []

        with cell_span("kdb.search"):
            raw_results = self._execute_lexical_and_vector_retrieval(
                query=query,
                unified_index=unified_index,
                flt=flt,
                target_spaces=target_spaces,
                target_ftypes=target_ftypes,
                kinds=kinds,
                languages=languages,
                limit=limit,
                aggregate=aggregate,
                can_use_vector=can_use_vector,
            )
            if adaptive_limit and aggregate and len(raw_results) > 3:
                top_score = raw_results[0].total_score  # type: ignore[union-attr]
                if top_score > 0:
                    cutoff_results = list(raw_results[:3])
                    for idx_r in range(3, len(raw_results)):
                        curr_r = raw_results[idx_r]
                        prev_r = raw_results[idx_r - 1]
                        if (
                            curr_r.total_score < top_score * 0.38  # type: ignore[union-attr]
                            or curr_r.total_score < prev_r.total_score * 0.55  # type: ignore[union-attr]
                        ):
                            break
                        cutoff_results.append(curr_r)
                    raw_results = cutoff_results
            return self._enrich_snippets_and_expand_ast(
                raw_results,
                aggregate=aggregate,
                snippet=snippet,
                context_lines=context_lines,
            )
