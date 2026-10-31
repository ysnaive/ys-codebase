"""
knowledge-db 索引生命週期與流水線引擎 (pipeline.py)
職責：
1. 全域聯集倒排索引建置與原子二進位持久化 (build_unified_index)
2. 基於 AST 與 FQN 作用域的雙向調用圖譜建立 (CallGraphIndex)
3. 向量特徵嵌入建置與持久化 (VectorIndex)
4. 4 階段極速 JIT 增量熱自愈修補管線 (hot_patch_unified_index)
5. 3 階段全域混合檢索編排 (search) 與 TopologyQueryService 委派
"""

from collections import defaultdict
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .bundler import SemanticBundler
from .embedding import EmbeddingService, VectorIndex
from .exceptions import KnowledgeDBError
from .graph import CallGraphIndex
from .hybrid import HybridSearchEngine
from .linker import TopologyLinker
from .retrieval import BM25Engine, InvertedIndex, QueryFilter, SearchResult, SnippetExtractor
from .scanner import BinarySnapshotManager, FingerprintScanner, ScanDiffDetail
from .schema import AggregatedFileResult, AggregatedItem, SymbolCallSite, UnifiedSymbol
from .space import SpaceManager
from .tokenizer import MultilingualTokenizer
from .topology_query import TopologyQueryService

logger = logging.getLogger("knowledge-db.pipeline")

_GLOBAL_INDEX_CACHE: Dict[str, Any] = {
    "unified_index": None,
    "unified_mtime": 0.0,
    "graph_index": None,
    "graph_mtime": 0.0,
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
    if target_spaces and not any(s in target_spaces for s in getattr(sym, "spaces", [])):
        return False
    if kinds and sym.kind not in kinds:
        return False
    if languages and sym.language not in languages:
        return False
    return True


class IndexingPipeline:
    """多空間索引建置、JIT 增量熱補丁、持久化與檢索拓撲流水線"""

    def __init__(
        self,
        space_manager: SpaceManager,
        bundler: SemanticBundler,
        scanner: FingerprintScanner,
        tokenizer: MultilingualTokenizer,
        bm25_engine: BM25Engine,
        embedding_service: EmbeddingService,
        hybrid_engine: HybridSearchEngine,
        snippet_extractor: Optional[SnippetExtractor] = None,
        config: Optional[Any] = None,
    ):
        self.space_manager = space_manager
        self.bundler = bundler
        self.scanner = scanner
        self.tokenizer = tokenizer
        self.bm25_engine = bm25_engine
        self.embedding_service = embedding_service
        self.hybrid_engine = hybrid_engine
        self.snippet_extractor = snippet_extractor or SnippetExtractor(space_manager=space_manager)

        if config is None:
            try:
                from .config import KnowledgeDBConfig
                config = KnowledgeDBConfig.load()
            except Exception:
                config = None
        self.config = config
        self._vector_degraded: bool = False
        self._last_degrade_notice: Optional[str] = None

        self._index_cache: Dict[str, InvertedIndex] = {}
        self._unified_index: Optional[InvertedIndex] = None
        self._call_graph_index: Optional[CallGraphIndex] = None
        self._index_lock = threading.RLock()

        self.topology_query = TopologyQueryService(
            ensure_index_fn=lambda: self._ensure_jit_index_ready(require_vectors=False, auto_rebuild=True) or self.build_unified_index(),
            get_graph_fn=self.get_call_graph,
            bm25_engine=self.bm25_engine,
            snippet_extractor=self.snippet_extractor,
        )

    @property
    def storage_dir(self) -> Path:
        return self.space_manager.storage_dir

    @property
    def unified_index(self) -> Optional[InvertedIndex]:
        return self._unified_index

    @unified_index.setter
    def unified_index(self, val: Optional[InvertedIndex]) -> None:
        self._unified_index = val

    @property
    def call_graph_index(self) -> Optional[CallGraphIndex]:
        return self._call_graph_index

    @call_graph_index.setter
    def call_graph_index(self, val: Optional[CallGraphIndex]) -> None:
        self._call_graph_index = val

    @property
    def index_cache(self) -> Dict[str, InvertedIndex]:
        return self._index_cache

    def get_indices_dir(self) -> Path:
        p = self.storage_dir / "indices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _ensure_indices_loaded(
        self,
        load_graph: bool = True,
        load_vectors: bool = True,
        force_reload: bool = False,
    ) -> None:
        """微秒級比對磁碟快照 mtime，自動熱更新記憶體快取或從磁碟載入。"""
        global _GLOBAL_INDEX_CACHE
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"

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

        if load_graph and graph_file.exists():
            try:
                mtime = graph_file.stat().st_mtime
                with _CACHE_LOCK:
                    if force_reload or _GLOBAL_INDEX_CACHE["graph_index"] is None or mtime > _GLOBAL_INDEX_CACHE["graph_mtime"]:
                        _GLOBAL_INDEX_CACHE["graph_index"] = CallGraphIndex.load_binary(graph_file)
                        _GLOBAL_INDEX_CACHE["graph_mtime"] = mtime
                    self._call_graph_index = _GLOBAL_INDEX_CACHE["graph_index"]
            except Exception as e:
                logger.warning(f"Failed loading graph index cache: {e}")

        if load_vectors and vector_file.exists():
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

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
        allow_parallel: bool = True,
    ) -> InvertedIndex:
        """建置全專案空間聯集單一倒排索引與雙向調用圖譜索引，並原子持久化至磁碟。"""
        with self._index_lock:
            return self._build_unified_index_locked(
                force=force,
                current_files=current_files,
                interactive=interactive,
                progress_callback=progress_callback,
                allow_parallel=allow_parallel,
            )

    def _build_unified_index_locked(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
        allow_parallel: bool = True,
    ) -> InvertedIndex:
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"

        def _report(stage: int, name: str, elapsed_ms: float):
            if progress_callback:
                try:
                    progress_callback(stage, name, elapsed_ms)
                except Exception:
                    pass
            if interactive:
                print(f"[{stage}/5] {name} (耗時 {elapsed_ms:.1f}ms)", file=sys.stderr, flush=True)

        if not force and bin_file.exists() and meta_file.exists() and graph_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._unified_index = idx
                try:
                    self._call_graph_index = CallGraphIndex.load_binary(graph_file)
                except Exception as ge:
                    logger.warning(f"Failed loading unified graph index: {ge}")
                vector_file = indices_dir / "unified.vectors.bin.gz"
                if vector_file.exists():
                    try:
                        self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                    except Exception as ve:
                        logger.warning(f"Failed loading unified vector index: {ve}")
                if self._call_graph_index is not None:
                    return idx
            except Exception as e:
                logger.warning(f"Failed loading unified binary index, rebuilding: {e}")

        t_all_start = time.time()

        t0 = time.time()
        bundle = self.bundler.bundle_union(allow_parallel=allow_parallel)
        _report(1, "AST 符號解析與全域打包", (time.time() - t0) * 1000)

        t0 = time.time()
        idx = InvertedIndex(space_name="unified")
        idx.build(bundle.symbols, tokenizer=self.tokenizer, space="unified")
        _report(2, f"BM25 倒排索引建置 ({idx.doc_count} 符號)", (time.time() - t0) * 1000)

        t0 = time.time()
        call_sites, imports_map = self.bundler.extract_all_call_sites_and_imports()
        linker = TopologyLinker(
            symbols_map=idx.symbols,
        )
        edges = linker.link_call_sites(call_sites, imports_map)
        graph_idx = CallGraphIndex()
        for caller_id, callee_id, site in edges:
            graph_idx.add_edge(caller_id, callee_id, site)
        _report(3, f"雙向調用圖譜建置 ({len(edges)} 條調用邊)", (time.time() - t0) * 1000)

        t0 = time.time()
        vector_file = indices_dir / "unified.vectors.bin.gz"
        enable_vec = getattr(self.config, "enable_vector_search", True)
        if not enable_vec:
            _report(4, "向量特徵嵌入 (已依組態停用，略過)", (time.time() - t0) * 1000)
        elif self.embedding_service.is_available:
            try:
                sym_items = list(idx.symbols.items())
                doc_ids = [k for k, _ in sym_items]
                texts = [
                    f"{sym.name} {sym.signature} {sym.docstring}".strip()
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
                vec_idx.save_binary(vector_file)
                self.hybrid_engine.vector_index = vec_idx
                _report(4, f"向量特徵嵌入建置 ({len(doc_ids)} 符號向量)", (time.time() - t0) * 1000)
            except Exception as e:
                logger.warning(f"Failed building/saving vector index: {e}")
                _report(4, f"向量特徵嵌入建置失敗: {e}", (time.time() - t0) * 1000)
        else:
            reason_str = ""
            last_err = getattr(self.embedding_service, "last_error", None)
            if last_err and isinstance(last_err, dict):
                reason_str = f" ({last_err.get('error_type')}: {last_err.get('message')})"
            _report(4, f"向量特徵嵌入 (FastEmbed 不可用{reason_str}，略過)", (time.time() - t0) * 1000)

        t0 = time.time()
        try:
            idx.save_binary(bin_file, compresslevel=1)
            graph_idx.save_binary(graph_file, compresslevel=1)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving unified binary index/graph: {e}")

        files_map = current_files if current_files is not None else bundle.metadata.get("files_map", {})
        try:
            BinarySnapshotManager.save(meta_file, files_map)
        except Exception as e:
            logger.warning(f"Failed saving binary snapshot meta: {e}")
        _report(5, "二進位索引與快照原子持久化", (time.time() - t0) * 1000)

        if interactive:
            total_elapsed = (time.time() - t_all_start) * 1000
            print(f"[knowledge-db] 全域索引建置完成，總耗時 {total_elapsed:.1f}ms", file=sys.stderr, flush=True)

        self._unified_index = idx
        self._call_graph_index = graph_idx
        with _CACHE_LOCK:
            _GLOBAL_INDEX_CACHE["unified_index"] = idx
            _GLOBAL_INDEX_CACHE["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
            _GLOBAL_INDEX_CACHE["graph_index"] = graph_idx
            _GLOBAL_INDEX_CACHE["graph_mtime"] = graph_file.stat().st_mtime if graph_file.exists() else time.time()
            if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                _GLOBAL_INDEX_CACHE["vector_index"] = self.hybrid_engine.vector_index
                _GLOBAL_INDEX_CACHE["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()
        return idx

    # ----------------------------------------------------------------------
    # 4 階段增量熱修補管線
    # ----------------------------------------------------------------------

    def hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
        timeout_seconds: Optional[float] = None,
    ) -> HotPatchResult:
        with self._index_lock:
            return self._hot_patch_unified_index_locked(
                diff_detail=diff_detail,
                full_files_map=full_files_map,
                timeout_seconds=timeout_seconds,
            )

    def _collect_all_dirty_files(
        self, diff_detail: ScanDiffDetail
    ) -> Tuple[List[UnifiedSymbol], Set[str]]:
        """熱修補階段 1：解析所有變更檔案並收集新符號與 dirty_keys"""
        new_symbols_by_file, dirty_keys = self.bundler.bundle_dirty_files(diff_detail)
        all_new_symbols: List[UnifiedSymbol] = []
        for syms in new_symbols_by_file.values():
            all_new_symbols.extend(syms)
        return all_new_symbols, dirty_keys

    def _evict_dirty_file_artifacts(
        self, dirty_keys: Set[str]
    ) -> Tuple[Set[str], Dict[str, Tuple[str, str, str]]]:
        """熱修補階段 2：識別將被淘汰之舊符號 doc_id 與身份映射資訊"""
        old_doc_ids: Set[str] = set()
        old_symbol_info: Dict[str, Tuple[str, str, str]] = {}
        if self._unified_index is None:
            return old_doc_ids, old_symbol_info

        dirty_paths_norm = {p.replace("\\", "/").lower() for p in dirty_keys}
        for doc_id, sym in list(self._unified_index.symbols.items()):
            sym_path_norm = sym.file_path.replace("\\", "/").lower()
            sym_fn = Path(sym_path_norm).name
            matched = False
            for p in dirty_paths_norm:
                if sym_path_norm == p or p.endswith("/" + sym_path_norm) or sym_path_norm.endswith("/" + p):
                    matched = True
                    break
                if "/" not in p and sym_fn == p:
                    matched = True
                    break
            if matched:
                old_doc_ids.add(doc_id)
                old_symbol_info[doc_id] = (
                    sym.file_path,
                    sym.name,
                    getattr(sym, "qualified_name", sym.name),
                )
        return old_doc_ids, old_symbol_info

    def _reparse_and_relink_dirty_files(
        self,
        diff_detail: ScanDiffDetail,
        dirty_keys: Set[str],
        all_new_symbols: List[UnifiedSymbol],
        old_doc_ids: Set[str],
        old_symbol_info: Dict[str, Tuple[str, str, str]],
        graph_file: Path,
    ) -> None:
        """熱修補階段 3：更新倒排索引與雙階入度重鏈接調用圖譜"""
        if self._unified_index is None:
            return

        self._unified_index.patch_incremental(
            dirty_file_paths=dirty_keys,
            new_symbols=all_new_symbols,
            tokenizer=self.tokenizer,
        )

        if self._call_graph_index is not None:
            incoming_edges = self._call_graph_index.get_external_incoming_edges(old_doc_ids)
            dirty_sites, dirty_imports = self.bundler.extract_dirty_call_sites_and_imports(diff_detail)
            linker = TopologyLinker(
                symbols_map=self._unified_index.symbols,
            )
            new_edges = linker.link_call_sites(dirty_sites, dirty_imports)

            reconnected_incoming_edges: List[Tuple[str, str, Optional[SymbolCallSite]]] = []
            new_syms_by_identity: Dict[Tuple[str, str], UnifiedSymbol] = {}
            for sym in all_new_symbols:
                norm_p = sym.file_path.replace("\\", "/").lower()
                new_syms_by_identity[(norm_p, sym.name)] = sym
                if getattr(sym, "qualified_name", None):
                    new_syms_by_identity[(norm_p, sym.qualified_name)] = sym

            for caller_id, old_callee_id, site in incoming_edges:
                target_new_id = None
                if old_callee_id in old_symbol_info:
                    old_p, old_name, old_qname = old_symbol_info[old_callee_id]
                    old_norm_p = old_p.replace("\\", "/").lower()
                    new_sym = new_syms_by_identity.get((old_norm_p, old_name)) or new_syms_by_identity.get((old_norm_p, old_qname))
                    if new_sym is not None:
                        target_new_id = new_sym.id

                if not target_new_id and site is not None:
                    try:
                        resolved_id = linker.resolve_call_site(site)
                        if resolved_id and resolved_id in self._unified_index.symbols:
                            target_new_id = resolved_id
                    except Exception as e:
                        logger.debug(f"TopologyLinker fallback resolution failed for site {site}: {e}")

                if target_new_id:
                    reconnected_incoming_edges.append((caller_id, target_new_id, site))

            self._call_graph_index.patch_incremental(
                new_edges=new_edges + reconnected_incoming_edges,
                old_symbol_ids=old_doc_ids,
            )
            self._call_graph_index.save_binary(graph_file, compresslevel=1)

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

        new_texts = [f"{sym.name} {sym.signature} {sym.docstring}".strip() for sym in all_new_symbols]
        num_symbols = len(new_texts)
        if num_symbols == 0:
            vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=[], new_vectors=None)
            try:
                vec_idx.save_binary(vector_file)
            except Exception as ve:
                logger.warning(f"Failed saving patched vector index: {ve}")
            return False, None

        if num_symbols <= 10:
            try:
                new_vecs = self.embedding_service.embed_texts(new_texts)
                new_ids = [sym.id for sym in all_new_symbols]
                vec_idx.patch_incremental(removed_doc_ids=old_doc_ids, new_doc_ids=new_ids, new_vectors=new_vecs)
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
            vec_idx.save_binary(vector_file)
            return False, None
        except Exception as ve:
            logger.warning(f"Dynamic probe or inference failed: {ve}")
            return True, f"[knowledge-db:notice] 向量推論異常已降級為純 BM25 模式: {ve}"

    def _persist_patched_indices(
        self,
        bin_file: Path,
        graph_file: Path,
        vector_file: Path,
        meta_file: Path,
        full_files_map: Dict[str, Tuple[float, int]],
    ) -> None:
        """熱修補階段 4：原子持久化更新後之二進位索引與全域快取同步"""
        if self._unified_index is not None:
            self._unified_index.save_binary(bin_file, compresslevel=1)
        BinarySnapshotManager.save(meta_file, full_files_map)
        with _CACHE_LOCK:
            _GLOBAL_INDEX_CACHE["unified_index"] = self._unified_index
            _GLOBAL_INDEX_CACHE["unified_mtime"] = bin_file.stat().st_mtime if bin_file.exists() else time.time()
            _GLOBAL_INDEX_CACHE["graph_index"] = self._call_graph_index
            _GLOBAL_INDEX_CACHE["graph_mtime"] = graph_file.stat().st_mtime if graph_file.exists() else time.time()
            if hasattr(self.hybrid_engine, "vector_index") and self.hybrid_engine.vector_index:
                _GLOBAL_INDEX_CACHE["vector_index"] = self.hybrid_engine.vector_index
                _GLOBAL_INDEX_CACHE["vector_mtime"] = vector_file.stat().st_mtime if vector_file.exists() else time.time()

    def _hot_patch_unified_index_locked(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
        timeout_seconds: Optional[float] = None,
    ) -> HotPatchResult:
        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        vector_file = indices_dir / "unified.vectors.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"

        if self._unified_index is None and bin_file.exists():
            try:
                self._unified_index = InvertedIndex.load_binary(bin_file)
            except Exception as e:
                logger.warning(f"Failed loading binary inverted index for hot patch: {e}")

        if self._unified_index is None:
            return HotPatchResult(success=False, patched_count=0)

        if timeout_seconds is None:
            timeout_seconds = getattr(self.config, "jit_vector_timeout_seconds", 5.0)

        if self._call_graph_index is None and graph_file.exists():
            try:
                self._call_graph_index = CallGraphIndex.load_binary(graph_file)
            except Exception:
                pass

        try:
            all_new_symbols, dirty_keys = self._collect_all_dirty_files(diff_detail)
            old_doc_ids, old_symbol_info = self._evict_dirty_file_artifacts(dirty_keys)
            self._reparse_and_relink_dirty_files(
                diff_detail, dirty_keys, all_new_symbols, old_doc_ids, old_symbol_info, graph_file
            )
            vector_degraded, degrade_notice = self._patch_vector_index_with_probe(
                all_new_symbols, old_doc_ids, vector_file, timeout_seconds
            )
            self._persist_patched_indices(bin_file, graph_file, vector_file, meta_file, full_files_map)

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

        sp = self.space_manager.get_space(space)
        indices_dir = self.get_indices_dir()
        sp_name = sp.name
        bin_file = indices_dir / f"{sp_name}.index.bin.gz"

        if not force and bin_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._index_cache[sp_name] = idx
                return {sp_name: idx}
            except Exception as e:
                logger.warning(f"Failed loading binary cached index for '{sp_name}', rebuilding: {e}")

        bundle = self.bundler.bundle_space(sp)
        idx = InvertedIndex(space_name=sp_name)
        idx.build(bundle.symbols, tokenizer=self.tokenizer, space=sp_name)

        try:
            idx.save_binary(bin_file)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving binary index cache for '{sp_name}': {e}")

        self._index_cache[sp_name] = idx
        return {sp_name: idx}

    def clean(self, space: Optional[str] = None) -> None:
        """清理指定空間或全空間之 Bundle 檔案與倒排索引快取。"""
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.list_spaces()
        for sp in targets:
            sp_name = sp.name
            bundle_file = self.storage_dir / "bundles" / f"{sp_name}.bundle.json"
            if bundle_file.exists():
                try:
                    bundle_file.unlink()
                except OSError:
                    pass

            idx_file = self.storage_dir / "indices" / f"{sp_name}.index.bin.gz"
            if idx_file.exists():
                try:
                    idx_file.unlink()
                except OSError:
                    pass

            self._index_cache.pop(sp_name, None)

        for fn in [
            "unified.index.bin.gz",
            "unified.graph.bin.gz",
            "unified.meta.bin",
            "unified.vectors.bin.gz",
        ]:
            f_path = self.storage_dir / "indices" / fn
            if f_path.exists():
                try:
                    f_path.unlink()
                except OSError:
                    pass
        self._unified_index = None
        self._call_graph_index = None
        self.hybrid_engine.vector_index = VectorIndex()
        _GLOBAL_INDEX_CACHE.clear()

    # ----------------------------------------------------------------------
    # 3 階段檢索編排與 TopologyQueryService 委派
    # ----------------------------------------------------------------------

    def _is_watcher_active(self) -> bool:
        """檢查是否有背景 Watcher 正在守護檔案系統。"""
        indices_dir = self.get_indices_dir()
        active_file = indices_dir / ".watcher_active"
        if not active_file.exists():
            return False
        try:
            with open(active_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            pid = data.get("pid", 0)
            if not pid:
                return False
            from core.platform import is_process_alive
            return is_process_alive(pid)
        except Exception:
            return False

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
        meta_file = indices_dir / "unified.meta.bin"
        vector_file = indices_dir / "unified.vectors.bin.gz"

        self._ensure_indices_loaded(load_graph=True, load_vectors=require_vectors)

        if auto_rebuild:
            watcher_active = self._is_watcher_active()
            skip_full_stat = watcher_active and bin_file.exists() and self._unified_index is not None

            if not skip_full_stat:
                is_dirty, scanned_count, reason, full_files_map, diff_detail = self.scanner.check_invalidation(
                    snapshot_path=meta_file
                )
                if not bin_file.exists():
                    is_dirty = True
                    reason = "Unified index missing"

                if is_dirty:
                    if verbose:
                        print(
                            f"[knowledge-db:auto-rebuild] Detected changes ({reason}), hot-rebuilding index...",
                            file=sys.stderr,
                            flush=True,
                        )
                    t0 = time.time()
                    patched = False
                    degrade_notice = None
                    if bin_file.exists() and self._unified_index is not None and diff_detail.has_changes:
                        res = self.hot_patch_unified_index(diff_detail, full_files_map)
                        patched = bool(res.success)
                        degrade_notice = res.degrade_notice

                    if not patched:
                        self.build_unified_index(force=True, current_files=full_files_map)

                    elapsed_ms = max(1, int((time.time() - t0) * 1000))
                    if verbose:
                        print(
                            f"[knowledge-db:auto-rebuild] Index updated in {elapsed_ms}ms ({scanned_count} files).",
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
        want_vectors = enable_vec and not getattr(self, "_vector_degraded", False) and not lexical_only

        unified_index = self._ensure_jit_index_ready(
            require_vectors=want_vectors,
            auto_rebuild=auto_rebuild,
            verbose=verbose,
        )
        target_spaces = [space] if isinstance(space, str) else list(space) if space else None
        target_ftypes = TopologyQueryService.normalize_ftypes(ftypes)
        flt = QueryFilter(
            spaces=target_spaces,
            languages=languages,
            kinds=kinds,
            ftypes=target_ftypes,
            min_score=min_score,
            limit=limit,
        )
        can_use_vector = want_vectors and self.hybrid_engine.is_vector_available
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
                            snippet=sym.docstring or "",
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
                            snippet=sym.docstring or "",
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
        return self._enrich_snippets_and_expand_ast(
            raw_results,
            aggregate=aggregate,
            snippet=snippet,
            context_lines=context_lines,
        )

    def get_call_graph(self) -> CallGraphIndex:
        """獲取已載入之全域雙向調用圖譜索引 (若未建置則自動觸發 JIT 構建)"""
        self._ensure_indices_loaded(load_graph=True, load_vectors=False)
        if self._call_graph_index is None or self._unified_index is None:
            self.build_unified_index(force=True)
        return self._call_graph_index  # type: ignore[return-value]

    def callers(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        return self.topology_query.callers(target_query, space=space, snippet=snippet, ftypes=ftypes)

    def callees(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        return self.topology_query.callees(target_query, space=space, snippet=snippet, ftypes=ftypes)

    def impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[str] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        return self.topology_query.impact(target_query, depth=depth, space=space, ftypes=ftypes)
