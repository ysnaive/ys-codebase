"""
knowledge-db 索引生命週期與流水線引擎 (pipeline.py)
職責：
1. 單次解析共享 (Single-Parse Symbol Sharing)：透過 `ast_engine.ensure_jit_synced()` 取得 `ASTSnapshot`，零重複解析建置 BM25 倒排索引 (`build_unified_index`)
2. 向量特徵嵌入建置與持久化 (`VectorIndex`)
3. 雙水位線 (`ast_generation` vs `acked_ast_generation`) 極速 JIT 增量熱自癒修補管線 (`hot_patch_unified_index`)
4. 3 階段全域混合檢索編排 (`search`)
"""

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from ast_engine import ASTEngine, SemanticBundler
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
    format_symbol_summary,
    normalize_ftypes,
)
from .schema import AggregatedFileResult, AggregatedItem, UnifiedSymbol
from .service import (
    clear_worker_state,
    get_active_worker,
    get_worker_busy_ms,
    is_worker_running,
    wait_until_worker_idle,
)
from .tokenizer import MultilingualTokenizer

logger = logging.getLogger("knowledge-db.pipeline")


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
    base = project_root.resolve() if project_root else Path.cwd().resolve()
    return base / ".storage.local" / "knowledge-db"


def _normalize_ftypes(ftypes: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    norm = sorted(normalize_ftypes(ftypes))
    return norm or None


_GLOBAL_INDEX_CACHE: Dict[str, Any] = {
    "storage_dir": None,
    "unified_index": None,
    "unified_mtime": 0.0,
    "vector_index": None,
    "vector_mtime": 0.0,
}
_CACHE_LOCK = threading.RLock()


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

        self._custom_storage_dir = storage_dir is not None
        if storage_dir is not None:
            self._storage_dir = Path(storage_dir).resolve()
        elif hasattr(bundler, "storage_dir") and bundler.storage_dir is not None:
            self._storage_dir = Path(bundler.storage_dir).resolve()
        else:
            proj_root = getattr(space_manager, "project_root", None)
            self._storage_dir = _resolve_default_knowledge_storage_dir(proj_root)

        if ast_engine is not None:
            self.ast_engine = ast_engine
        else:
            self.ast_engine = ASTEngine(
                project_root=getattr(space_manager, "project_root", None),
                storage_dir=self._storage_dir / "ast",
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

        self._index_cache: Dict[str, InvertedIndex] = {}
        self._unified_index: Optional[InvertedIndex] = None
        self._index_lock = threading.RLock()

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    @property
    def unified_index(self) -> Optional[InvertedIndex]:
        return self._unified_index

    @unified_index.setter
    def unified_index(self, val: Optional[InvertedIndex]) -> None:
        self._unified_index = val

    @property
    def index_cache(self) -> Dict[str, InvertedIndex]:
        return self._index_cache

    def get_indices_dir(self) -> Path:
        p = self.storage_dir / "indices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _reset_consumer_cursor(self, space_name: Optional[str] = None, consumer_id: str = "knowledge-db") -> None:
        """重置消費者增量游標"""
        if self.scanner is not None and hasattr(self.scanner, "reset_cursor"):
            self.scanner.reset_cursor(space_name, consumer_id=consumer_id)
        else:
            reset_cursor(space_name, consumer_id=consumer_id)

    @contextmanager
    def _consume_space_diff(
        self, space_name: Optional[str] = None, consumer_id: str = "knowledge-db"
    ) -> Iterator[ScanDiffResult]:
        """以交易式 Context Manager 消費空間指紋差異並於無異常時自動推進游標"""
        if self.scanner is not None and hasattr(self.scanner, "consume_diff"):
            with self.scanner.consume_diff(space_name, consumer_id=consumer_id) as diff_res:
                yield diff_res
        else:
            with consume_diff(space_name, consumer_id=consumer_id) as diff_res:
                yield diff_res

    def _ensure_indices_loaded(
        self,
        load_vectors: bool = True,
        force_reload: bool = False,
        **kwargs: Any,
    ) -> None:
        """微秒級比對磁碟快照 mtime，自動熱更新記憶體快取或從磁碟載入。"""
        global _GLOBAL_INDEX_CACHE
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"
        storage_key = str(self.storage_dir)

        with _CACHE_LOCK:
            if _GLOBAL_INDEX_CACHE.get("storage_dir") != storage_key:
                _GLOBAL_INDEX_CACHE["storage_dir"] = storage_key
                _GLOBAL_INDEX_CACHE["unified_index"] = None
                _GLOBAL_INDEX_CACHE["unified_mtime"] = 0.0
                _GLOBAL_INDEX_CACHE["vector_index"] = None
                _GLOBAL_INDEX_CACHE["vector_mtime"] = 0.0

        if bin_file.exists():
            try:
                mtime = bin_file.stat().st_mtime
                with _CACHE_LOCK:
                    if force_reload or _GLOBAL_INDEX_CACHE["unified_index"] is None or mtime > _GLOBAL_INDEX_CACHE["unified_mtime"]:
                        _GLOBAL_INDEX_CACHE["unified_index"] = InvertedIndex.load_binary(bin_file)
                        _GLOBAL_INDEX_CACHE["unified_mtime"] = mtime
                    self._unified_index = _GLOBAL_INDEX_CACHE["unified_index"]
            except Exception as e:
                logger.warning(f"Failed loading unified index cache: {e}")
        else:
            with _CACHE_LOCK:
                if _GLOBAL_INDEX_CACHE["unified_mtime"] > 0.0:
                    _GLOBAL_INDEX_CACHE["unified_index"] = None
                    _GLOBAL_INDEX_CACHE["unified_mtime"] = 0.0
                    self._unified_index = None

        if load_vectors:
            if vector_file.exists():
                try:
                    mtime = vector_file.stat().st_mtime
                    with _CACHE_LOCK:
                        if force_reload or _GLOBAL_INDEX_CACHE["vector_index"] is None or mtime > _GLOBAL_INDEX_CACHE["vector_mtime"]:
                            _GLOBAL_INDEX_CACHE["vector_index"] = VectorIndex.load_binary(vector_file)
                            _GLOBAL_INDEX_CACHE["vector_mtime"] = mtime
                        if _GLOBAL_INDEX_CACHE["vector_index"] is not None:
                            self.hybrid_engine.vector_index = _GLOBAL_INDEX_CACHE["vector_index"]
                except Exception as e:
                    logger.warning(f"Failed loading vector index cache: {e}")
            elif not getattr(self, "_vector_index_dirty", False):
                with _CACHE_LOCK:
                    if _GLOBAL_INDEX_CACHE["vector_mtime"] > 0.0 or _GLOBAL_INDEX_CACHE["vector_index"] is not None:
                        _GLOBAL_INDEX_CACHE["vector_index"] = None
                        _GLOBAL_INDEX_CACHE["vector_mtime"] = 0.0
                        self.hybrid_engine.vector_index = VectorIndex()

    def _sync_ast_snapshot(self, force: bool = False) -> Any:
        """同步並取得最新 ASTSnapshot（僅於無磁碟快取或存在未消費變更時才強制重建）。"""
        ast_has_disk = (
            self.ast_engine._ensure_symbols_loaded()
            if hasattr(self.ast_engine, "_ensure_symbols_loaded")
            else self.ast_engine._ensure_loaded_from_disk()
        )
        has_ast_diff = False
        try:
            if self.scanner is not None and hasattr(self.scanner, "diff"):
                has_ast_diff = bool(self.scanner.diff(consumer_id="ast", auto_refresh=False).has_changes)
        except Exception:
            has_ast_diff = True
        ast_force = bool(force and (not ast_has_disk or has_ast_diff))
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
                skip_vectors=skip_vectors,
            )

    def _build_unified_index_locked(
        self,
        force: bool = False,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
        skip_vectors: bool = False,
    ) -> InvertedIndex:
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"

        def _report(stage: int, name: str, elapsed_ms: float):
            if progress_callback:
                try:
                    progress_callback(stage, name, elapsed_ms)
                except Exception:
                    pass
            if interactive:
                print(f"[{stage}/4] {name} (耗時 {elapsed_ms:.1f}ms)", file=sys.stderr, flush=True)

        if not force and bin_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._unified_index = idx
                vector_file = indices_dir / "unified.vectors.bin.gz"
                if vector_file.exists():
                    try:
                        self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                    except Exception as ve:
                        logger.warning(f"Failed loading unified vector index: {ve}")
                return idx
            except Exception as e:
                logger.warning(f"Failed loading unified binary index, rebuilding: {e}")

        t_all_start = time.time()

        # Stage 1: Single-Parse Symbol Sharing via ASTEngine
        t0 = time.time()
        snapshot = self._sync_ast_snapshot(force=force)
        _report(1, f"AST 快照同步與符號共享 (gen={snapshot.ast_generation})", (time.time() - t0) * 1000)

        # Stage 2: Build BM25 InvertedIndex directly from ASTSnapshot.symbols (filtered to weighted spaces)
        t0 = time.time()
        indexed_spaces = self._get_indexed_space_names()
        filtered_symbols = [
            fs for fs in (
                self._filter_symbol_for_indexed_spaces(sym, indexed_spaces)
                for sym in snapshot.symbols.values()
            )
            if fs is not None
        ]
        idx = InvertedIndex(space_name="unified")
        idx.build(
            filtered_symbols,
            tokenizer=self.tokenizer,
            space="unified",
            pre_aggregated=True,
        )
        idx.acked_ast_generation = snapshot.ast_generation
        _report(2, f"BM25 倒排索引建置 ({idx.doc_count} 符號)", (time.time() - t0) * 1000)

        # Stage 3: Build VectorIndex
        t0 = time.time()
        vector_file = indices_dir / "unified.vectors.bin.gz"
        enable_vec = getattr(self.config, "enable_vector_search", True)
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
                if texts:
                    vectors = self.embedding_service.embed_texts(texts)
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
                _report(3, f"向量特徵嵌入建置 ({len(doc_ids)} 符號向量)", (time.time() - t0) * 1000)
            except Exception as e:
                logger.warning(f"Failed building/saving vector index: {e}")
                _report(3, f"向量特徵嵌入建置失敗: {e}", (time.time() - t0) * 1000)
        else:
            reason_str = ""
            last_err = getattr(self.embedding_service, "last_error", None)
            if last_err and isinstance(last_err, dict):
                reason_str = f" ({last_err.get('error_type')}: {last_err.get('message')})"
            _report(3, f"向量特徵嵌入 (FastEmbed 不可用{reason_str}，略過)", (time.time() - t0) * 1000)

        # Stage 4: Atomic binary persistence & cursor alignment
        t0 = time.time()
        try:
            with self._kdb_index_file_lock():
                idx.save_binary(bin_file, compresslevel=1)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving unified binary index: {e}") from e

        try:
            with self._consume_space_diff(consumer_id="knowledge-db"):
                pass
        except Exception as e:
            logger.debug(f"Cursor alignment after build_unified_index skipped: {e}")

        _report(4, "二進位索引原子持久化與游標同步", (time.time() - t0) * 1000)

        if interactive:
            total_elapsed = (time.time() - t_all_start) * 1000
            print(f"[knowledge-db] 全域索引建置完成，總耗時 {total_elapsed:.1f}ms", file=sys.stderr, flush=True)

        self._unified_index = idx
        self._vector_degraded = False
        self._last_degrade_notice = None
        with _CACHE_LOCK:
            _GLOBAL_INDEX_CACHE["storage_dir"] = str(self.storage_dir)
            _GLOBAL_INDEX_CACHE["unified_index"] = idx
            _GLOBAL_INDEX_CACHE["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
            if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                _GLOBAL_INDEX_CACHE["vector_index"] = self.hybrid_engine.vector_index
                _GLOBAL_INDEX_CACHE["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()
        return idx

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
        proj_root = getattr(self.space_manager, "project_root", None)
        base = Path(proj_root).resolve() if proj_root else Path.cwd().resolve()
        if (base / "ys_codebase").is_dir():
            fallback = base / "ys_codebase" / ".cache" / "knowledge-db" / ".kdb_index.lock"
        else:
            fallback = base / ".cache" / "knowledge-db" / ".kdb_index.lock"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

    @contextmanager
    def _kdb_index_file_lock(self) -> Iterator[None]:
        """Acquire a cross-process file lock before persisting binary index files."""
        from core.platform.lock import InterProcessLock

        lock_file = str(self._resolve_index_lock_path())
        with InterProcessLock(lock_file, timeout=15.0):
            yield

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
           若呼び出し方直接傳入未經 `scanner` 消費之合成 `diff_detail`（致使 `ast_generation` 未推進），
           則補充執行 `self.ast_engine.hot_patch_index(detail)` 並對齊 `"ast"` 游標。
        2. 透過 `bundler._normalize_space_dirty_paths` 將空間相對路徑展開為正規化路徑，
           並同步檢查舊 `InvertedIndex` 與新 `ASTSnapshot` 中受影響之 C# `partial class` 群組（含被刪除分部檔），
           直接從最新 `ASTSnapshot.symbols` 提取符號，零重複 Tree-sitter 解析。
        """
        detail = self.ast_engine._coerce_diff_detail(diff_detail)
        indexed_spaces = self._get_indexed_space_names()
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
        snapshot = self.ast_engine.ensure_jit_synced()
        if snapshot.ast_generation <= current_acked_gen and (detail.dirty_files or detail.deleted):
            snapshot = self.ast_engine.hot_patch_index(detail)

        dirty_paths_norm = normalize_dirty_paths(dirty_keys)

        # Check existing _unified_index symbols for C# partial groups affected by deleted/modified files
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
        all_new_symbols: List[UnifiedSymbol] = []
        seen_ids: Set[str] = set()
        for raw_sym in snapshot.symbols.values():
            sym = self._filter_symbol_for_indexed_spaces(raw_sym, indexed_spaces)
            if sym is None:
                continue
            sym_matched = is_dirty_file_match(sym.file_path, dirty_paths_norm)
            if not sym_matched:
                partial_files = (sym.metadata or {}).get("partial_files") or []
                if any(is_dirty_file_match(str(pf), dirty_paths_norm) for pf in partial_files):
                    sym_matched = True
                elif affected_cs_keys and sym.language in ("c_sharp", "csharp") and sym.kind in ("class", "struct", "interface"):
                    sp_key = ",".join(sorted(sym.spaces)) if sym.spaces else ""
                    if (sp_key, sym.kind, sym.fqn or sym.name) in affected_cs_keys:
                        sym_matched = True

            if sym_matched:
                if sym.id not in seen_ids:
                    seen_ids.add(sym.id)
                    all_new_symbols.append(sym)
                dirty_keys.add(sym.file_path)

        return all_new_symbols, dirty_keys, snapshot.ast_generation

    def _evict_dirty_file_artifacts(
        self, dirty_keys: Set[str]
    ) -> Set[str]:
        """熱修補階段 2：識別將被淘汰之舊符號 doc_id"""
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
                logger.warning(f"Failed loading vector index for hot patch: {ve}")

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
            except Exception as ve:
                logger.warning(f"Failed saving patched vector index: {ve}")
            return False, None

        if num_symbols <= 10:
            try:
                new_vecs = self.embedding_service.embed_texts(new_texts)
                new_ids = [sym.id for sym in all_new_symbols]
                vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=new_ids, new_vectors=new_vecs)
                with self._kdb_index_file_lock():
                    vec_idx.save_binary(vector_file)
                return False, None
            except Exception as ve:
                logger.warning(f"Failed patching vector index for <=10 symbols: {ve}")
                return True, f"[knowledge-db:notice] 向量更新失敗已降級為純 BM25 模式: {ve}"

        try:
            probe_texts = new_texts[:10]
            probe_vecs, est_total = self.embedding_service.embed_texts_probe(probe_texts, total_count=num_symbols)
            if timeout_seconds is not None and est_total > timeout_seconds:
                return True, (
                    f"[knowledge-db:notice] 待向量化符號過多（{num_symbols} 個，預估耗時 {est_total:.1f}s > {timeout_seconds:.1f}s）已熔斷降級（本次使用純 BM25 模式）。"
                    "請執行 `python yscb.py knowledge-db index` 重建/更新向量索引，"
                    "或執行 `python yscb.py config set knowledge-db enable_vector_search false` 關閉向量語意搜尋。"
                )

            remaining_texts = new_texts[10:]
            remaining_vecs = self.embedding_service.embed_texts(remaining_texts) if remaining_texts else None
            import numpy as np
            if probe_vecs is not None and remaining_vecs is not None:
                full_vecs = np.vstack([probe_vecs, remaining_vecs])
            elif probe_vecs is not None:
                full_vecs = probe_vecs
            else:
                full_vecs = remaining_vecs

            new_ids = [sym.id for sym in all_new_symbols]
            vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=new_ids, new_vectors=full_vecs)
            with self._kdb_index_file_lock():
                vec_idx.save_binary(vector_file)
            return False, None
        except Exception as ve:
            logger.warning(f"Dynamic probe or inference failed: {ve}")
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
        with _CACHE_LOCK:
            _GLOBAL_INDEX_CACHE["storage_dir"] = str(self.storage_dir)
            _GLOBAL_INDEX_CACHE["unified_index"] = self._unified_index
            _GLOBAL_INDEX_CACHE["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
            if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                _GLOBAL_INDEX_CACHE["vector_index"] = self.hybrid_engine.vector_index
                _GLOBAL_INDEX_CACHE["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()

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
                self._unified_index = InvertedIndex.load_binary(bin_file)
            except Exception as e:
                logger.warning(f"Failed loading binary inverted index for hot patch: {e}")

        if self._unified_index is None:
            return HotPatchResult(success=False, patched_count=0)

        if timeout_seconds is None:
            timeout_ms = getattr(self.config, "jit_vector_timeout_ms", None)
            if timeout_ms is not None:
                timeout_seconds = float(timeout_ms) / 1000.0
            else:
                timeout_seconds = getattr(self.config, "jit_vector_timeout_seconds", 3.0)

        try:
            all_new_symbols, dirty_keys, new_ast_gen = self._collect_all_dirty_files(diff_detail)
            old_doc_ids = self._evict_dirty_file_artifacts(dirty_keys)
            self._unified_index.patch_incremental(
                dirty_file_paths=dirty_keys,
                new_symbols=all_new_symbols,
                tokenizer=self.tokenizer,
                pre_aggregated=True,
            )
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
                    except Exception as ve:
                        logger.warning(f"Failed evicting old vectors during skip_vectors hot patch: {ve}")
                vector_degraded = False
                degrade_notice = None
            else:
                vector_degraded, degrade_notice = self._patch_vector_index_with_probe(
                    all_new_symbols, old_doc_ids, vector_file, timeout_seconds
                )
            self._persist_patched_indices(bin_file, vector_file)

            self._vector_degraded = vector_degraded
            self._last_degrade_notice = degrade_notice
            return HotPatchResult(
                success=True,
                patched_count=len(dirty_keys),
                vector_degraded=vector_degraded,
                degrade_notice=degrade_notice,
            )
        except Exception as e:
            logger.warning(f"Incremental hot patch failed: {e}, falling back to full rebuild.")
            self._vector_degraded = False
            self._last_degrade_notice = None
            return HotPatchResult(success=False, patched_count=0)

    def get_vector_deficit_info(self) -> Dict[str, Any]:
        """比對 unified_index.symbols 與 vector_index.doc_ids，回傳向量差集與覆蓋率統計。"""
        with self._index_lock:
            self._ensure_indices_loaded(load_vectors=True)
            idx = self._unified_index
            vec_idx = getattr(self.hybrid_engine, "vector_index", None)
            total_syms = len(idx.symbols) if (idx is not None and idx.symbols) else 0
            if total_syms == 0:
                return {
                    "total_symbols": 0,
                    "embedded_count": 0,
                    "missing_count": 0,
                    "stale_count": 0,
                    "coverage_pct": 100.0,
                    "compatible": True,
                }

            expected_model = getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5")
            if getattr(vec_idx, "dim", None):
                expected_dim = int(vec_idx.dim)
            elif getattr(self.embedding_service, "mock_mode", False) or self.embedding_service.is_model_downloaded():
                expected_dim = int(getattr(self.embedding_service, "dimension", 512))
            else:
                expected_dim = int(self.embedding_service._resolve_dimension_mock())
            if vec_idx is None or vec_idx.vectors is None or len(vec_idx.doc_ids) == 0:
                return {
                    "total_symbols": total_syms,
                    "embedded_count": 0,
                    "missing_count": total_syms,
                    "stale_count": 0,
                    "coverage_pct": 0.0,
                    "compatible": False,
                }

            compatible = True
            if hasattr(vec_idx, "is_compatible_with") and not vec_idx.is_compatible_with(expected_model, expected_dim):
                compatible = False
                return {
                    "total_symbols": total_syms,
                    "embedded_count": 0,
                    "missing_count": total_syms,
                    "stale_count": len(vec_idx.doc_ids),
                    "coverage_pct": 0.0,
                    "compatible": False,
                }

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
                "compatible": compatible,
            }

    def flush_vector_index(self) -> bool:
        """原子持久化記憶體中之 vector_index 至 unified.vectors.bin.gz 並同步 _GLOBAL_INDEX_CACHE。"""
        with self._index_lock:
            vec_idx = getattr(self.hybrid_engine, "vector_index", None)
            if vec_idx is None or getattr(vec_idx, "vectors", None) is None:
                self._vector_index_dirty = False
                return False
            indices_dir = self.get_indices_dir()
            vector_file = indices_dir / "unified.vectors.bin.gz"
            with self._kdb_index_file_lock():
                vec_idx.save_binary(vector_file)
            self._vector_index_dirty = False
            with _CACHE_LOCK:
                _GLOBAL_INDEX_CACHE["storage_dir"] = str(self.storage_dir)
                _GLOBAL_INDEX_CACHE["vector_index"] = vec_idx
                _GLOBAL_INDEX_CACHE["vector_mtime"] = (
                    vector_file.stat().st_mtime if vector_file.exists() else time.time()
                )
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
                if getattr(self, "_vector_index_dirty", False) and persist:
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
                    _GLOBAL_INDEX_CACHE["storage_dir"] = str(self.storage_dir)
                    _GLOBAL_INDEX_CACHE["vector_index"] = vec_idx

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
        """建置空間倒排索引並原子持久化二進位 Gzip 快取至磁碟。"""
        if space is None:
            idx = self.build_unified_index(force=force, interactive=interactive)
            return {"unified": idx}

        resolved_list = self.space_manager.resolve_spaces(space)
        sp = resolved_list[0]
        indices_dir = self.get_indices_dir()
        weights = self._resolve_space_weights()
        if space in weights:
            sp_name = space
        elif sp.short_name in weights:
            sp_name = sp.short_name
        elif sp.qualified_name in weights:
            sp_name = sp.qualified_name
        else:
            sp_name = sp.short_name or sp.qualified_name
        safe_name = sp_name.replace("/", "_")
        bin_file = indices_dir / f"{safe_name}.index.bin.gz"

        if not force and bin_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._index_cache[sp_name] = idx
                return {sp_name: idx}
            except Exception as e:
                logger.warning(f"Failed loading binary cached index for '{sp_name}', rebuilding: {e}")

        snapshot = self._sync_ast_snapshot(force=force)
        match_keys = {space, sp_name, sp.short_name, sp.qualified_name}
        space_symbols = [
            sym for sym in snapshot.symbols.values()
            if not sym.spaces or any(s in match_keys for s in sym.spaces)
        ]
        idx = InvertedIndex(space_name=sp_name)
        idx.build(
            space_symbols,
            tokenizer=self.tokenizer,
            space=sp_name,
            pre_aggregated=True,
        )
        idx.acked_ast_generation = snapshot.ast_generation

        try:
            with self._kdb_index_file_lock():
                idx.save_binary(bin_file)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving binary index cache for '{sp_name}': {e}") from e

        self._index_cache[sp_name] = idx
        return {sp_name: idx}

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

                self._index_cache.pop(candidate_name, None)
            self._index_cache.pop(sp.qualified_name, None)

        for fn in [
            "unified.index.bin.gz",
            "unified.vectors.bin.gz",
        ]:
            f_path = self.storage_dir / "indices" / fn
            if f_path.exists():
                try:
                    f_path.unlink()
                except OSError:
                    pass
        try:
            clear_worker_state(self.storage_dir / "indices", worker_running=False)
        except Exception:
            pass
        self._unified_index = None
        self._vector_index_dirty = False
        self.hybrid_engine.vector_index = VectorIndex()
        with _CACHE_LOCK:
            _GLOBAL_INDEX_CACHE["storage_dir"] = None
            _GLOBAL_INDEX_CACHE["unified_index"] = None
            _GLOBAL_INDEX_CACHE["unified_mtime"] = 0.0
            _GLOBAL_INDEX_CACHE["vector_index"] = None
            _GLOBAL_INDEX_CACHE["vector_mtime"] = 0.0
        try:
            if space is not None:
                self._reset_consumer_cursor(space_name=space, consumer_id="knowledge-db")
            self._reset_consumer_cursor(space_name=None, consumer_id="knowledge-db")
        except Exception:
            pass
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
        with self._index_lock:
            return self._ensure_jit_index_ready_locked(
                require_vectors=require_vectors,
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
        vector_file = indices_dir / "unified.vectors.bin.gz"

        self._ensure_indices_loaded(load_vectors=require_vectors)

        if not bin_file.exists():
            if auto_rebuild:
                if verbose:
                    print(
                        "[knowledge-db:auto-rebuild] Unified index missing, building index...",
                        file=sys.stderr,
                        flush=True,
                    )
                self._reset_consumer_cursor(consumer_id="knowledge-db")
                self.build_unified_index(force=True)
            return self._unified_index  # type: ignore[return-value]

        if auto_rebuild:
            with self._consume_space_diff(consumer_id="knowledge-db") as diff_res:
                if not diff_res.has_changes:
                    self._ensure_indices_loaded(load_vectors=require_vectors)
                    if self._unified_index is not None:
                        ast_gen_now = self.get_current_ast_generation()
                        if (
                            ast_gen_now is not None
                            and int(getattr(self._unified_index, "acked_ast_generation", 0) or 0) != ast_gen_now
                        ):
                            self.build_unified_index(force=True)
                    return self._unified_index  # type: ignore[return-value]

                if verbose:
                    print(
                        f"[knowledge-db:auto-rebuild] Detected changes (+{diff_res.added_count} ~{diff_res.modified_count} -{diff_res.deleted_count}), hot-rebuilding index...",
                        file=sys.stderr,
                        flush=True,
                    )
                t0 = time.time()
                patched = False
                degrade_notice = None
                if self._unified_index is not None:
                    res = self.hot_patch_unified_index(diff_res.detail)
                    patched = bool(res.success)
                    degrade_notice = res.degrade_notice

                if not patched:
                    self.build_unified_index(force=True)

                elapsed_ms = max(1, int((time.time() - t0) * 1000))
                if verbose:
                    total_files = (
                        diff_res.added_count
                        + diff_res.modified_count
                        + diff_res.deleted_count
                        + diff_res.unchanged_count
                    )
                    print(
                        f"[knowledge-db:auto-rebuild] Index updated in {elapsed_ms}ms ({total_files} files).",
                        file=sys.stderr,
                        flush=True,
                    )
                if degrade_notice:
                    print(degrade_notice, file=sys.stderr, flush=True)

        if self._unified_index is None:
            if bin_file.exists():
                try:
                    self._unified_index = InvertedIndex.load_binary(bin_file)
                    if require_vectors and vector_file.exists():
                        try:
                            self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                        except Exception as ve:
                            logger.warning(f"Failed loading unified vector index: {ve}")
                except Exception as e:
                    logger.warning(f"Failed loading unified binary index: {e}, rebuilding...")
                    self.build_unified_index(force=True)
            else:
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

    def _filter_symbol_for_indexed_spaces(
        self, sym: UnifiedSymbol, indexed_spaces: Set[str]
    ) -> Optional[UnifiedSymbol]:
        """過濾未納入 `space_weights` 之空間符號；若為跨空間符號則僅保留受索引空間標籤。"""
        from dataclasses import replace

        raw_spaces = list(getattr(sym, "spaces", []) or [])
        if not raw_spaces:
            return sym
        weights = self._resolve_space_weights()
        valid_spaces: List[str] = []
        for s in raw_spaces:
            s_short = s.split("/")[-1]
            if s in indexed_spaces or s_short in indexed_spaces:
                norm_s = s if s in weights else (s_short if s_short in weights else s_short)
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
        worker_active = is_worker_running(indices_dir)
        if hasattr(self, "embedding_service") and self.embedding_service is not None:
            self.embedding_service.suppress_guard_prompt = bool(worker_active)

        timeout_ms = int(getattr(self.config, "jit_vector_timeout_ms", 3000) or 0)
        elapsed_ms = get_worker_busy_ms(indices_dir)

        if elapsed_ms > 0:
            if elapsed_ms >= timeout_ms:
                sys.stderr.write("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]\n")
                sys.stderr.flush()
                return False

            remain_ms = max(0, timeout_ms - elapsed_ms)
            became_idle = wait_until_worker_idle(indices_dir, remain_ms)
            if not became_idle:
                sys.stderr.write("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]\n")
                sys.stderr.flush()
                return False
            self._ensure_indices_loaded(load_vectors=True, force_reload=True)

        if worker_active and not self.hybrid_engine.is_vector_available:
            active_w = get_active_worker()
            if active_w is not None:
                active_w.notify_space_changed()
            sys.stderr.write("[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]\n")
            sys.stderr.flush()
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

        indices_dir = self.get_indices_dir()
        if hasattr(self, "embedding_service") and self.embedding_service is not None:
            self.embedding_service.suppress_guard_prompt = bool(is_worker_running(indices_dir))

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
                )
                raw_results: List[SearchResult] = []
                for h in hybrid_hits:
                    sym = h["symbol"]
                    if not _symbol_matches_filters(sym, h["score"], target_spaces, kinds, languages):
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
            hybrid_agg_hits = self.hybrid_engine.search(
                query=query,
                limit=max(limit * 3, 30),
                file_types=target_ftypes,
                spaces=target_spaces,
                kinds=kinds,
                languages=languages,
                lexical_only=False,
            )
            file_items: Dict[str, List[AggregatedItem]] = defaultdict(list)
            file_scores: Dict[str, List[float]] = defaultdict(list)
            file_spaces: Dict[str, Set[str]] = defaultdict(set)
            file_lang: Dict[str, str] = {}

            for h in hybrid_agg_hits:
                sym = h["symbol"]
                if not _symbol_matches_filters(sym, h["score"], target_spaces, kinds, languages):
                    continue
                fp = sym.file_path
                file_scores[fp].append(h["score"])
                if len(file_items[fp]) < 3:
                    file_items[fp].append(
                        AggregatedItem(
                            symbol=sym,
                            score=h["score"],
                            matched_terms=h.get("matched_terms", []),
                            snippet=format_symbol_summary(sym),
                        )
                    )
                for sp in getattr(sym, "spaces", []):
                    file_spaces[fp].add(sp)
                if not file_lang.get(fp):
                    file_lang[fp] = sym.language

            raw_agg_results = []
            alpha = 0.2
            for fp, scores in file_scores.items():
                sorted_scores = sorted(scores, reverse=True)
                total_s = sorted_scores[0] + alpha * sum(sorted_scores[1:])
                raw_agg_results.append(
                    AggregatedFileResult(
                        file_path=fp,
                        total_score=total_s,
                        items=file_items[fp],
                        spaces=list(file_spaces[fp]),
                        language=file_lang.get(fp, ""),
                    )
                )
            raw_agg_results.sort(key=lambda x: x.total_score, reverse=True)
            return raw_agg_results[:limit]

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
