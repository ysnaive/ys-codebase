"""
knowledge-db 索引生命週期與流水線引擎 (pipeline.py)
職責：
1. 全域聯集倒排索引建置與原子二進位持久化 (build_unified_index)
2. 基於 AST 與 FQN 作用域的雙向調用圖譜建立 (CallGraphIndex)
3. 向量特徵嵌入建置與持久化 (VectorIndex)
4. 極速 JIT 增量熱自愈修補管線 (hot_patch_unified_index)
5. 空間倒排索引建置與快取清理 (clean)
6. 全域檢索編排 (search) 與拓撲查詢 (act_callers, act_callees, act_impact)
"""

from collections import defaultdict
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .bundler import SemanticBundle, SemanticBundler
from .embedding import EmbeddingService, VectorIndex
from .exceptions import KnowledgeDBError, SpaceNotFoundError
from .graph import CallGraphIndex
from .hybrid import HybridSearchEngine
from .linker import TopologyLinker
from .retrieval import BM25Engine, CodeSnippet, InvertedIndex, QueryFilter, SearchResult, SnippetExtractor
from .scanner import BinarySnapshotManager, FingerprintScanner, ScanDiffDetail
from .schema import AggregatedFileResult, AggregatedItem, SymbolCallSite, UnifiedSymbol
from .space import SpaceManager
from .tokenizer import MultilingualTokenizer

logger = logging.getLogger("knowledge-db.pipeline")


class HotPatchResult(tuple):
    """
    熱修補結果元組 (success, vector_degraded, degrade_notice)
    繼承 tuple 支援解構 (success, degraded, notice)，
    同時實現 __bool__ 回傳 self[0]，支援 `if res:` 判斷。
    """
    def __new__(cls, success: bool, vector_degraded: bool = False, degrade_notice: Optional[str] = None):
        return super().__new__(cls, (bool(success), bool(vector_degraded), degrade_notice))

    @property
    def success(self) -> bool:
        return self[0]

    @property
    def vector_degraded(self) -> bool:
        return self[1]

    @property
    def degrade_notice(self) -> Optional[str]:
        return self[2]

    def __bool__(self) -> bool:
        return bool(self[0])


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

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
    ) -> InvertedIndex:
        """
        建置全專案空間聯集單一倒排索引與雙向調用圖譜索引，並原子持久化二進位 Gzip 快取
        (unified.index.bin.gz, unified.graph.bin.gz) 與二進位狀態快照 (unified.meta.bin) 至磁碟。
        支援 interactive=True 或 progress_callback 回報 5 階段進度與精確耗時。
        """
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

        # Stage 1: AST 解析與全域去重打包
        t0 = time.time()
        bundle = self.bundler.bundle_union()
        _report(1, "AST 符號解析與全域打包", (time.time() - t0) * 1000)

        # Stage 2: BM25 倒排索引建立
        t0 = time.time()
        idx = InvertedIndex(space_name="unified")
        idx.build_unified(bundle.symbols, tokenizer=self.tokenizer)
        _report(2, f"BM25 倒排索引建置 ({idx.doc_count} 符號)", (time.time() - t0) * 1000)

        # Stage 3: 雙向調用圖譜建立與符號鏈結
        t0 = time.time()
        call_sites, imports_map = self.bundler.extract_all_call_sites_and_imports()
        linker = TopologyLinker(
            symbols_map=idx.symbols,
            thesaurus=None,
            tokenizer=self.tokenizer,
        )
        edges = linker.link_call_sites(call_sites, imports_map)
        graph_idx = CallGraphIndex()
        for caller_id, callee_id, site in edges:
            graph_idx.add_edge(caller_id, callee_id, site)
        _report(3, f"雙向調用圖譜建置 ({len(edges)} 條調用邊)", (time.time() - t0) * 1000)

        # Stage 4: 向量特徵嵌入建置
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
                    dim = 384
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
            _report(4, "向量特徵嵌入 (FastEmbed 不可用，略過)", (time.time() - t0) * 1000)

        # Stage 5: 二進位索引與快照原子持久化
        t0 = time.time()
        try:
            idx.save_binary(bin_file, compresslevel=1)
            graph_idx.save_binary(graph_file, compresslevel=1)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving unified binary index/graph: {e}")

        files_map = current_files
        if files_map is None:
            files_map = bundle.metadata.get("files_map", {})

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
        return idx

    def hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
        timeout_seconds: Optional[float] = None,
    ) -> HotPatchResult:
        """
        執行極速增量熱自愈修補管線 (包含 JIT 10 符號動態探針與臨界值熔斷)：
        1. 若記憶體 _unified_index 為空，回傳 HotPatchResult(False) 降級為全量建置。
        2. 僅對 dirty 檔案呼叫 AST 解析並更新符號快取池。
        3. 調用 _unified_index.patch_incremental 進行倒排差量打補丁。
        4. 調用 _call_graph_index.patch_incremental 進行調用圖譜差量修補。
        5. 若啟用向量檢索：
           - 若向量快取遺失或與配置模型維度不符，安全熔斷降級回退純 BM25，輸出引導提示。
           - 若待向量化符號 N <= 10，直接推論並更新。
           - 若 N > 10，以首批 10 符號動態探針實測耗時，若預估 > timeout_seconds 立即熔斷降級回退純 BM25。
        6. 快速原子持久化快照與二進位索引。
        """
        if self._unified_index is None:
            return HotPatchResult(False, False, None)

        if timeout_seconds is None:
            if self.config and hasattr(self.config, "resolve_jit_vector_timeout"):
                timeout_seconds = self.config.resolve_jit_vector_timeout()
            else:
                timeout_seconds = getattr(self.config, "jit_vector_timeout_seconds", 5.0)

        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"

        if self._call_graph_index is None and graph_file.exists():
            try:
                self._call_graph_index = CallGraphIndex.load_binary(graph_file)
            except Exception:
                pass

        try:
            new_symbols_by_file, dirty_keys = self.bundler.bundle_dirty_files(diff_detail)
            all_new_symbols: List[UnifiedSymbol] = []
            for syms in new_symbols_by_file.values():
                all_new_symbols.extend(syms)

            old_doc_ids: Set[str] = set()
            dirty_paths_norm = {p.replace("\\", "/").lower() for p in dirty_keys}
            for doc_id, sym in list(self._unified_index.symbols.items()):
                sym_path_norm = sym.file_path.replace("\\", "/").lower()
                sym_fn = Path(sym_path_norm).name
                if any(
                    sym_path_norm == p
                    or p.endswith("/" + sym_path_norm)
                    or sym_path_norm.endswith("/" + p)
                    or Path(p).name == sym_fn
                    for p in dirty_paths_norm
                ):
                    old_doc_ids.add(doc_id)

            self._unified_index.patch_incremental(
                dirty_file_paths=dirty_keys,
                new_symbols=all_new_symbols,
                tokenizer=self.tokenizer,
            )

            # 差量修補調用圖譜
            if self._call_graph_index is not None:
                dirty_sites, dirty_imports = self.bundler.extract_dirty_call_sites_and_imports(diff_detail)
                linker = TopologyLinker(
                    symbols_map=self._unified_index.symbols,
                    thesaurus=None,
                    tokenizer=self.tokenizer,
                )
                new_edges = linker.link_call_sites(dirty_sites, dirty_imports)
                self._call_graph_index.patch_incremental(
                    dirty_file_paths=dirty_keys,
                    new_edges=new_edges,
                    old_symbol_ids=old_doc_ids,
                )
                self._call_graph_index.save_binary(graph_file, compresslevel=1)

            # 差量修補向量索引與 JIT 10 符號動態探針
            vector_file = indices_dir / "unified.vectors.bin.gz"
            vector_degraded = False
            degrade_notice: Optional[str] = None
            enable_vec = getattr(self.config, "enable_vector_search", True)

            if not enable_vec:
                # 向量語意檢索已停用，不執行向量更新與提示
                pass
            else:
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

                if vec_idx is None or vec_idx.vectors is None or not vector_file.exists():
                    vector_degraded = True
                    degrade_notice = (
                        "[knowledge-db:notice] 向量索引未建立已降級（本次使用純 BM25 模式）。"
                        "請執行 `python yscb.py knowledge-db index` 重建向量索引，"
                        "或於 yscb.config.json / yscb.config.local.json 設定 `knowledge-db.enable_vector_search: false` 關閉向量語意搜尋。"
                    )
                elif hasattr(vec_idx, "is_compatible_with") and not vec_idx.is_compatible_with(expected_model, getattr(vec_idx, "dim", 384)):
                    vector_degraded = True
                    degrade_notice = (
                        f"[knowledge-db:notice] 向量快取與當前模型 '{expected_model}' 不相容已降級（本次使用純 BM25 模式）。"
                        "請執行 `python yscb.py knowledge-db index` 重建向量索引，"
                        "或於 yscb.config.json / yscb.config.local.json 設定 `knowledge-db.enable_vector_search: false` 關閉向量語意搜尋。"
                    )
                elif self.embedding_service.is_available:
                    new_texts = [
                        f"{sym.name} {sym.signature} {sym.docstring}".strip()
                        for sym in all_new_symbols
                    ]
                    num_symbols = len(new_texts)
                    if num_symbols == 0:
                        vec_idx.patch_incremental(
                            removed_doc_ids=old_doc_ids,
                            new_doc_ids=[],
                            new_vectors=None,
                        )
                        try:
                            vec_idx.save_binary(vector_file)
                        except Exception as ve:
                            logger.warning(f"Failed saving patched vector index: {ve}")
                    elif num_symbols <= 10:
                        try:
                            new_vecs = self.embedding_service.embed_texts(new_texts)
                            new_ids = [sym.id for sym in all_new_symbols]
                            vec_idx.patch_incremental(
                                removed_doc_ids=old_doc_ids,
                                new_doc_ids=new_ids,
                                new_vectors=new_vecs,
                            )
                            vec_idx.save_binary(vector_file)
                        except Exception as ve:
                            logger.warning(f"Failed patching vector index for <=10 symbols: {ve}")
                            vector_degraded = True
                            degrade_notice = f"[knowledge-db:notice] 向量更新失敗已降級為純 BM25 模式: {ve}"
                    else:
                        # N > 10，執行 10 符號動態探針
                        try:
                            probe_texts = new_texts[:10]
                            probe_vecs, est_total = self.embedding_service.embed_texts_probe(probe_texts, total_count=num_symbols)
                            if timeout_seconds is not None and est_total > timeout_seconds:
                                vector_degraded = True
                                degrade_notice = (
                                    f"[knowledge-db:notice] 待向量化符號過多（{num_symbols} 個，預估耗時 {est_total:.1f}s > {timeout_seconds:.1f}s）已熔斷降級（本次使用純 BM25 模式）。"
                                    "請執行 `python yscb.py knowledge-db index` 重建/更新向量索引，"
                                    "或於 yscb.config.json / yscb.config.local.json 設定 `knowledge-db.enable_vector_search: false` 關閉向量語意搜尋。"
                                )
                                # 熔斷：不將不完整向量寫入磁碟，但完成 BM25 與圖譜更新
                            else:
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
                                vec_idx.patch_incremental(
                                    removed_doc_ids=old_doc_ids,
                                    new_doc_ids=new_ids,
                                    new_vectors=full_vecs,
                                )
                                vec_idx.save_binary(vector_file)
                        except Exception as ve:
                            logger.warning(f"Dynamic probe or inference failed: {ve}")
                            vector_degraded = True
                            degrade_notice = f"[knowledge-db:notice] 向量推論異常已降級為純 BM25 模式: {ve}"

            self._unified_index.save_binary(bin_file, compresslevel=1)
            BinarySnapshotManager.save(meta_file, full_files_map)
            self._vector_degraded = vector_degraded
            self._last_degrade_notice = degrade_notice
            return HotPatchResult(True, vector_degraded, degrade_notice)
        except Exception as e:
            logger.warning(f"Incremental hot patch failed: {e}, falling back to full rebuild.")
            self._vector_degraded = False
            self._last_degrade_notice = None
            return HotPatchResult(False, False, None)

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
        legacy_json = indices_dir / f"{sp_name}.index.json"

        if not force and bin_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._index_cache[sp_name] = idx
                return {sp_name: idx}
            except Exception as e:
                logger.warning(f"Failed loading binary cached index for '{sp_name}', rebuilding: {e}")
        elif not force and legacy_json.exists():
            try:
                with open(legacy_json, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                idx = InvertedIndex.from_dict(data)
                idx.save_binary(bin_file)
                self._index_cache[sp_name] = idx
                return {sp_name: idx}
            except Exception as e:
                logger.warning(f"Failed converting legacy JSON index for '{sp_name}', rebuilding: {e}")

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
        """清理指定空間或全空間之指紋快取、Bundle 檔案與倒排索引快取。"""
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        for sp in targets:
            sp_name = sp.name
            fp_file = self.space_manager.get_space_storage_dir(sp_name) / "fingerprints.json"
            if fp_file.exists():
                try:
                    fp_file.unlink()
                except OSError:
                    pass

            bundle_file = self.storage_dir / "bundles" / f"{sp_name}.bundle.json"
            if bundle_file.exists():
                try:
                    bundle_file.unlink()
                except OSError:
                    pass

            for ext in [".index.bin.gz", ".index.json"]:
                idx_file = self.storage_dir / "indices" / f"{sp_name}{ext}"
                if idx_file.exists():
                    try:
                        idx_file.unlink()
                    except OSError:
                        pass

            self._index_cache.pop(sp_name, None)

        for fn in ["unified.index.bin.gz", "unified.graph.bin.gz", "unified.meta.bin"]:
            f_path = self.storage_dir / "indices" / fn
            if f_path.exists():
                try:
                    f_path.unlink()
                except OSError:
                    pass
        self._unified_index = None
        self._call_graph_index = None

    # ----------------------------------------------------------------------
    # 檢索編排與拓撲分析 (Search & Graph Actions)
    # ----------------------------------------------------------------------

    def search(
        self,
        query: str,
        space: Optional[Union[str, List[str]]] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
        min_score: float = 0.01,
        limit: int = 10,
        snippet: bool = False,
        context_lines: int = 3,
        auto_rebuild: bool = True,
        verbose: bool = True,
        aggregate: bool = True,
        lexical_only: bool = False,
    ) -> Union[List[AggregatedFileResult], List[SearchResult]]:
        """全域聯集多欄位加權語意檢索 (支援 JIT 變更嗅探、自動背景熱自愈、空間與副檔名篩選)"""
        if not query or not query.strip():
            return []

        indices_dir = self.get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"
        vector_file = indices_dir / "unified.vectors.bin.gz"

        if self._unified_index is None and bin_file.exists() and meta_file.exists():
            try:
                self._unified_index = InvertedIndex.load_binary(bin_file)
            except Exception:
                pass
        if self._call_graph_index is None and graph_file.exists():
            try:
                self._call_graph_index = CallGraphIndex.load_binary(graph_file)
            except Exception:
                pass
        if self.hybrid_engine.vector_index is None or len(self.hybrid_engine.vector_index.doc_ids) == 0:
            if vector_file.exists():
                try:
                    self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                except Exception:
                    pass

        # 1. JIT 變更感知與自動增量熱自愈 [FR-12]
        if auto_rebuild:
            from .daemon import check_and_notify_hot_reload_server
            is_srv_running, srv_info = check_and_notify_hot_reload_server()
            if is_srv_running and srv_info is not None:
                auto_rebuild = False

        if auto_rebuild:
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
                vector_degraded = False
                degrade_notice = None
                if bin_file.exists() and self._unified_index is not None and diff_detail.has_changes:
                    res = self.hot_patch_unified_index(diff_detail, full_files_map)
                    if isinstance(res, tuple):
                        patched = res[0]
                        vector_degraded = res[1] if len(res) > 1 else False
                        degrade_notice = res[2] if len(res) > 2 else None
                    else:
                        patched = bool(res)

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
                    if vector_file.exists():
                        try:
                            self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                        except Exception as ve:
                            logger.warning(f"Failed loading unified vector index: {ve}")
                except Exception as e:
                    logger.warning(f"Failed loading unified binary index: {e}, rebuilding...")
                    self.build_unified_index(force=True)
            else:
                self.build_unified_index(force=True)

        unified_index = self._unified_index
        if not unified_index or unified_index.doc_count == 0:
            return []

        target_spaces = [space] if isinstance(space, str) else list(space) if space else None
        target_ftypes = [ftypes] if isinstance(ftypes, str) else list(ftypes) if ftypes else None

        flt = QueryFilter(
            spaces=target_spaces,
            languages=languages,
            kinds=kinds,
            ftypes=target_ftypes,
            min_score=min_score,
            limit=limit,
        )

        enable_vec = getattr(self.config, "enable_vector_search", True)
        can_use_vector = (
            enable_vec
            and not getattr(self, "_vector_degraded", False)
            and not lexical_only
            and self.hybrid_engine.is_vector_available
        )

        if not aggregate:
            if can_use_vector:
                self.hybrid_engine.inverted_index = unified_index
                self.hybrid_engine.bm25_engine = self.bm25_engine
                hybrid_hits = self.hybrid_engine.search(
                    query=query,
                    limit=limit,
                    file_types=target_ftypes,
                    lexical_only=False,
                )
                raw_results = []
                for h in hybrid_hits:
                    sym = h["symbol"]
                    if sym is None or h["score"] <= 0:
                        continue
                    if target_spaces and not any(s in target_spaces for s in getattr(sym, "spaces", [])):
                        continue
                    if kinds and sym.kind not in kinds:
                        continue
                    if languages and sym.language not in languages:
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
            else:
                raw_results = self.bm25_engine.search(query=query, index=unified_index, filter_cfg=flt)

            if not snippet:
                return raw_results

            results_with_snippets: List[SearchResult] = []
            for r in raw_results:
                snip = self.snippet_extractor.extract(
                    file_path=r.symbol.file_path,
                    line_number=r.symbol.line_number,
                    end_line=r.symbol.end_line,
                    context_before=2,
                    context_after=8,
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

        # 預設聚合模式
        if can_use_vector:
            self.hybrid_engine.inverted_index = unified_index
            self.hybrid_engine.bm25_engine = self.bm25_engine
            hybrid_agg_hits = self.hybrid_engine.search(
                query=query,
                limit=max(limit * 3, 30),
                file_types=target_ftypes,
                lexical_only=False,
            )
            file_items: Dict[str, List[AggregatedItem]] = defaultdict(list)
            file_scores: Dict[str, List[float]] = defaultdict(list)
            file_spaces: Dict[str, Set[str]] = defaultdict(set)
            file_lang: Dict[str, str] = {}

            for h in hybrid_agg_hits:
                sym = h["symbol"]
                if sym is None or h["score"] <= 0:
                    continue
                if target_spaces and not any(s in target_spaces for s in getattr(sym, "spaces", [])):
                    continue
                if kinds and sym.kind not in kinds:
                    continue
                if languages and sym.language not in languages:
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
            raw_agg_results = raw_agg_results[:limit]
        else:
            raw_agg_results = self.bm25_engine.search_aggregated(query=query, index=unified_index, filter_cfg=flt)

        if not snippet:
            return raw_agg_results

        agg_with_snippets: List[AggregatedFileResult] = []
        for file_res in raw_agg_results:
            updated_items: List[AggregatedItem] = []
            for itm in file_res.items:
                snip = self.snippet_extractor.extract(
                    file_path=itm.symbol.file_path,
                    line_number=itm.symbol.line_number,
                    end_line=itm.symbol.end_line,
                    context_before=2,
                    context_after=8,
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

    def get_call_graph(self) -> CallGraphIndex:
        """獲取已載入之全域雙向調用圖譜索引 (若未建置則自動觸發 JIT 構建)"""
        indices_dir = self.get_indices_dir()
        graph_file = indices_dir / "unified.graph.bin.gz"

        if self._call_graph_index is None and graph_file.exists():
            try:
                self._call_graph_index = CallGraphIndex.load_binary(graph_file)
            except Exception as ge:
                logger.warning(f"Failed loading graph index: {ge}")

        if self._call_graph_index is None or self._unified_index is None:
            self.build_unified_index(force=True)

        return self._call_graph_index

    def find_target_symbol(self, query: str, space: Optional[str] = None) -> Optional[UnifiedSymbol]:
        """精準、透過 SymbolSelector 微型語法或語意定位目標 UnifiedSymbol"""
        idx = self.build_unified_index()
        query_clean = query.strip()
        if not query_clean:
            return None

        from .selector import SymbolSelector
        pool = [sym for sym in idx.symbols.values() if (not space or space in sym.spaces)]
        matches = SymbolSelector.find_matches(query_clean, pool)
        if matches:
            return matches[0]

        candidates: List[UnifiedSymbol] = []
        for sym in pool:
            if sym.name == query_clean:
                return sym
            if sym.name.endswith(f".{query_clean}") or query_clean.endswith(f".{sym.name}"):
                candidates.append(sym)

        if candidates:
            return candidates[0]

        flt = QueryFilter(spaces=[space] if space else None, limit=5)
        raw_results = self.bm25_engine.search(query=query_clean, index=idx, filter_cfg=flt)
        if raw_results:
            return raw_results[0].symbol

        return None

    def act_callers(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
    ) -> Dict[str, Any]:
        """查詢指定符號之上游調用者清單 (Who calls me?)"""
        self.search(query=target_query, space=space, limit=1)

        target_sym = self.find_target_symbol(target_query, space=space)
        if not target_sym:
            return {
                "target_query": target_query,
                "target_symbol": None,
                "callers": [],
                "total_callers": 0,
            }

        graph = self.get_call_graph()
        caller_ids = graph.get_callers(target_sym.id)

        callers_detail = []
        for cid in caller_ids:
            caller_sym = self._unified_index.get_symbol(cid) if self._unified_index else None
            if not caller_sym:
                continue

            sites = graph.get_call_sites(cid, target_sym.id)
            code_snip = None
            if snippet:
                target_ln = sites[0].line_number if sites else caller_sym.line_number
                code_snip = self.snippet_extractor.extract(
                    file_path=caller_sym.file_path,
                    line_number=target_ln,
                    context_before=2,
                    context_after=5,
                    docstring=caller_sym.docstring,
                )

            callers_detail.append({
                "symbol": caller_sym,
                "call_sites": [s.to_dict() for s in sites],
                "code_snippet": code_snip,
            })

        return {
            "target_query": target_query,
            "target_symbol": target_sym,
            "callers": callers_detail,
            "total_callers": len(callers_detail),
        }

    def act_callees(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
    ) -> Dict[str, Any]:
        """查詢指定符號內部調用之下游被調用者清單 (Whom do I call?)"""
        self.search(query=target_query, space=space, limit=1)

        target_sym = self.find_target_symbol(target_query, space=space)
        if not target_sym:
            return {
                "target_query": target_query,
                "target_symbol": None,
                "callees": [],
                "total_callees": 0,
            }

        graph = self.get_call_graph()
        callee_ids = graph.get_callees(target_sym.id)

        callees_detail = []
        for cid in callee_ids:
            callee_sym = self._unified_index.get_symbol(cid) if self._unified_index else None
            if not callee_sym:
                continue

            sites = graph.get_call_sites(target_sym.id, cid)
            code_snip = None
            if snippet:
                code_snip = self.snippet_extractor.extract(
                    file_path=callee_sym.file_path,
                    line_number=callee_sym.line_number,
                    end_line=callee_sym.end_line,
                    context_before=2,
                    context_after=6,
                    docstring=callee_sym.docstring,
                )

            callees_detail.append({
                "symbol": callee_sym,
                "call_sites": [s.to_dict() for s in sites],
                "code_snippet": code_snip,
            })

        return {
            "target_query": target_query,
            "target_symbol": target_sym,
            "callees": callees_detail,
            "total_callees": len(callees_detail),
        }

    def act_impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分析目標符號之重構影響面擴散拓撲 (Blast Radius Analysis)"""
        self.search(query=target_query, space=space, limit=1)

        target_sym = self.find_target_symbol(target_query, space=space)
        if not target_sym:
            return {
                "target_query": target_query,
                "target_symbol": None,
                "max_depth": depth,
                "layers": {},
                "total_impacted_symbols": 0,
                "total_impacted_files": 0,
            }

        graph = self.get_call_graph()
        impact_raw = graph.query_impact(target_sym.id, max_depth=depth)

        layers_detail = {}
        all_files = set()

        for d, sids in impact_raw.get("layers", {}).items():
            layer_syms = []
            for sid in sids:
                sym = self._unified_index.get_symbol(sid) if self._unified_index else None
                if sym:
                    layer_syms.append(sym)
                    all_files.add(sym.file_path)
            layers_detail[d] = layer_syms

        return {
            "target_query": target_query,
            "target_symbol": target_sym,
            "max_depth": depth,
            "layers": layers_detail,
            "call_chains": impact_raw.get("call_chains", {}),
            "total_impacted_symbols": impact_raw.get("total_impacted_symbols", 0),
            "total_impacted_files": len(all_files),
        }
