"""
knowledge-db 統一門面 SDK (engine.py)
整合空間治理、雙階指紋比對、多語言解析、語意打包、BM25 檢索與二進位 Gzip 快取中心。
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

from collections import defaultdict
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .bundler import SemanticBundle, SemanticBundler
from .exceptions import KnowledgeDBError, SpaceNotFoundError
from .graph import CallGraphIndex
from .linker import TopologyLinker
from .parsers.registry import ParserRegistry
from .retrieval import BM25Engine, CodeSnippet, InvertedIndex, QueryFilter, SearchResult, SnippetExtractor
from .scanner import BinarySnapshotManager, FingerprintScanner, ScanDiffDetail, ScanDiffResult
from .schema import AggregatedFileResult, AggregatedItem, SymbolCallSite, UnifiedSymbol
from .space import SpaceManager
from .embedding import EmbeddingService, VectorIndex
from .hybrid import HybridSearchEngine
from .tokenizer import CodeTokenizer, MultilingualTokenizer

logger = logging.getLogger("knowledge-db.engine")

AUTO_BUDGET_CHARS: int = 12500
AUTO_DECAY_START_CHARS: int = 5000
AUTO_DECAY_MIN_CHARS: int = 9000
AUTO_NO_SNIPPET_CHARS: int = 11000
AUTO_MAX_SNIPPET_LINES: int = 30
AUTO_MIN_SNIPPET_LINES: int = 10
AUTO_MIN_RENDERED_ITEMS: int = 5


def compute_dynamic_snippet_lines(
    current_chars: int,
    budget_limit: int = AUTO_BUDGET_CHARS,
    start_decay: int = AUTO_DECAY_START_CHARS,
    min_decay: int = AUTO_DECAY_MIN_CHARS,
    no_snippet_threshold: int = AUTO_NO_SNIPPET_CHARS,
    max_lines: int = AUTO_MAX_SNIPPET_LINES,
    min_lines: int = AUTO_MIN_SNIPPET_LINES,
) -> int:
    """
    計算 auto 模式下的動態切片行數預算。
    - < 5000 字元: 30 行
    - 5000 ~ 9000 字元: 30 -> 10 行線性遞減
    - 9000 ~ 11000 字元: 10 行
    - 11000 ~ 12500 字元: 0 行 (強制無切片)
    - >= 12500 字元: 0 行
    """
    if current_chars < start_decay:
        return max_lines
    elif current_chars < min_decay:
        ratio = (current_chars - start_decay) / (min_decay - start_decay)
        return max(min_lines, int(round(max_lines - ratio * (max_lines - min_lines))))
    elif current_chars < no_snippet_threshold:
        return min_lines
    else:
        return 0


class KnowledgeEngine:
    """
    knowledge-db 模組頂層統一門面 Facade SDK。
    提供一站式呼叫空間狀態查詢、增量掃描、語意打包、倒排索引建置、語意檢索與快取清理。
    """

    def __init__(
        self,
        storage_dir: Optional[Union[str, Path]] = None,
        config_dir: Optional[Union[str, Path]] = None,
        local_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        project_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
        field_weights: Optional[Dict[str, float]] = None,
        embedding_mock_mode: bool = False,
    ):
        self.space_manager = SpaceManager(
            config_dir=config_dir,
            storage_dir=storage_dir,
            contributes_data=contributes_data,
        )
        self.tokenizer = MultilingualTokenizer()
        self.thesaurus_engine = None
        self.parser_registry = ParserRegistry()
        self.scanner = FingerprintScanner(self.space_manager)
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
        )
        self.bm25_engine = BM25Engine(
            tokenizer=self.tokenizer,
            thesaurus=None,
            field_weights=field_weights,
        )
        models_dir = self.space_manager.storage_dir / "models" if hasattr(self.space_manager, "storage_dir") else None
        mock_mode = embedding_mock_mode
        self.embedding_service = EmbeddingService(cache_dir=models_dir, mock_mode=mock_mode)
        self.hybrid_engine = HybridSearchEngine(
            inverted_index=None,
            embedding_service=self.embedding_service,
            bm25_engine=self.bm25_engine,
        )
        self._index_cache: Dict[str, InvertedIndex] = {}
        self._unified_index: Optional[InvertedIndex] = None
        self._call_graph_index: Optional[CallGraphIndex] = None
        self.snippet_extractor = SnippetExtractor(
            workspace_root=self._get_workspace_root(),
            space_manager=self.space_manager,
        )

    def _get_workspace_root(self) -> Path:
        try:
            from core import uri
            p_res = uri.resolve("project://", interactive=False)
            if p_res:
                return Path(p_res).resolve()
        except Exception:
            pass
        try:
            from core import uri
            host_dir = uri.get_host_dir()
            if host_dir:
                return Path(host_dir).resolve()
        except Exception:
            pass
        return Path.cwd().resolve()

    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str:
        """將路徑正規化為相對於 Workspace/Project 根目錄之標準相對路徑 (forward slash)"""
        p = Path(file_path)
        ws = self._get_workspace_root()
        try:
            if p.is_absolute():
                rel = p.resolve().relative_to(ws)
                return str(rel).replace("\\", "/")
        except (ValueError, Exception):
            pass
        return str(file_path).replace("\\", "/")

    def to_file_uri(self, file_path: Union[str, Path], line: Optional[int] = None) -> str:
        """
        將指定檔案路徑轉譯為標準 RFC 8089 file:/// 協議 URI。

        :param file_path: 檔案路徑 (相對或絕對)
        :param line: 行號 (可選)
        :return: 標準 file:/// 格式字串 (例: file:///H:/path/file.py#L10)
        """
        p = Path(file_path)
        if not p.is_absolute():
            resolved = None
            try:
                from core import uri
                resolved = uri.resolve(f"project://{file_path}", interactive=False)
            except Exception:
                pass
            if resolved:
                p = Path(resolved).resolve()
            else:
                ws = self._get_workspace_root()
                p = (ws / p).resolve()
        else:
            p = p.resolve()

        posix_path = p.as_posix()
        if not posix_path.startswith("/"):
            posix_path = "/" + posix_path

        uri_str = f"file://{posix_path}"
        if line is not None:
            uri_str += f"#L{line}"
        return uri_str

    def format_file_link(
        self,
        file_path: Union[str, Path],
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        use_basename: bool = True,
    ) -> str:
        """
        格式化為 IDE 相容之 Markdown 檔案超連結標籤: [filename:Lxx~Lyy](file:///abs_path#Lxx)

        :param file_path: 檔案路徑
        :param line: 起始行號 (可選)
        :param end_line: 結束行號 (可選)
        :param use_basename: 是否僅顯示純檔案名稱與副檔名 (預設 True)
        :return: Markdown 格式字串 (例: [engine.py:L10-20](file:///.../engine.py#L10))
        """
        base_label = Path(file_path).name if use_basename else self.normalize_workspace_path(file_path)
        if line is not None:
            if end_line is not None and end_line > line:
                label = f"{base_label}:L{line}-{end_line}"
            else:
                label = f"{base_label}:L{line}"
        else:
            label = base_label

        uri_str = self.to_file_uri(file_path, line=line)
        return f"[{label}]({uri_str})"

    @property
    def storage_dir(self) -> Path:
        return self.space_manager.storage_dir

    def status(self) -> Dict[str, Any]:
        """
        獲取全系統空間、指紋快取、同義詞與倒排索引統計摘要。
        """
        spaces = self.space_manager.load_spaces()
        thesaurus_groups = self.space_manager.load_thesaurus()
        indices_dir = self._get_indices_dir()

        space_details = {}
        for sp_name, sp in spaces.items():
            fp_file = self.space_manager.get_space_storage_dir(sp_name) / "fingerprints.json"
            fp_count = 0
            if fp_file.exists():
                try:
                    with open(fp_file, "r", encoding="utf-8") as f:
                        fp_data = json.load(f)
                    fp_count = len(fp_data.get("fingerprints", {}))
                except Exception:
                    pass

            idx_bin = indices_dir / f"{sp_name}.index.bin.gz"
            idx_json = indices_dir / f"{sp_name}.index.json"
            idx_exists = idx_bin.exists() or idx_json.exists()

            space_details[sp_name] = {
                "description": sp.description,
                "origin": sp.origin,
                "include_count": len(sp.include),
                "exclude_count": len(sp.exclude),
                "file_patterns": sp.file_patterns,
                "fingerprint_cached_files": fp_count,
                "cached_files": fp_count,
                "index_cached": idx_exists,
                "has_index": idx_exists,
            }

        return {
            "total_spaces": len(spaces),
            "thesaurus_groups": len(thesaurus_groups),
            "storage_dir": str(self.storage_dir),
            "spaces": space_details,
        }

    def scan(self, space: Optional[str] = None, force: bool = False) -> Dict[str, ScanDiffResult]:
        """
        執行增量/全量指紋比對。
        :param space: 指定空間名稱 (若為 None 則掃描全空間聯集)
        :param force: 是否強制重新計算 SHA1
        """
        if space is not None:
            sp_cfg = self.space_manager.get_space(space)
            diff = self.scanner.scan_space(sp_cfg, force=force)
            return {space: diff}
        else:
            return self.scanner.scan_all_spaces(force=force)

    def bundle(
        self,
        space: Optional[str] = None,
        export_path: Optional[Union[str, Path]] = None,
    ) -> List[SemanticBundle]:
        """
        執行空間符號提取與 SemanticBundle 導出。
        """
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        bundles = []
        for sp in targets:
            b = self.bundler.bundle_space(sp)
            self.bundler.export_bundle(b, target_path=export_path)
            bundles.append(b)
        return bundles

    def _get_indices_dir(self) -> Path:
        p = self.storage_dir / "indices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
    ) -> InvertedIndex:
        """
        建置全專案空間聯集單一倒排索引與雙向調用圖譜索引，並原子持久化二進位 Gzip 快取
        (unified.index.bin.gz, unified.graph.bin.gz) 與二進位狀態快照 (unified.meta.bin) 至磁碟。
        """
        indices_dir = self._get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"

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

        # 全域聯集去重打包
        bundle = self.bundler.bundle_union()
        idx = InvertedIndex(space_name="unified")
        idx.build_unified(bundle.symbols, tokenizer=self.tokenizer)

        # 構建雙向調用圖譜索引 (FR-03, FR-04)
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

        # 原子持久化二進位 Gzip 索引與圖索引 (compresslevel=1 快速寫盤)
        try:
            idx.save_binary(bin_file, compresslevel=1)
            graph_idx.save_binary(graph_file, compresslevel=1)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving unified binary index/graph: {e}")

        # 若 EmbeddingService 可用，構建並持久化向量特徵索引
        vector_file = indices_dir / "unified.vectors.bin.gz"
        if self.embedding_service.is_available and idx.symbols:
            try:
                sym_items = list(idx.symbols.items())
                doc_ids = [k for k, _ in sym_items]
                texts = [
                    f"{sym.name} {sym.signature} {sym.docstring}".strip()
                    for _, sym in sym_items
                ]
                vectors = self.embedding_service.embed_texts(texts)
                vec_idx = VectorIndex()
                vec_idx.build(doc_ids, vectors)
                vec_idx.save_binary(vector_file)
                self.hybrid_engine.vector_index = vec_idx
            except Exception as e:
                logger.warning(f"Failed building/saving vector index: {e}")

        # 收集或使用現有檔案快照並持久化 (保證 100% 完整清冊)
        files_map = current_files
        if files_map is None:
            files_map = bundle.metadata.get("files_map", {})

        try:
            BinarySnapshotManager.save(meta_file, files_map)
        except Exception as e:
            logger.warning(f"Failed saving binary snapshot meta: {e}")

        self._unified_index = idx
        self._call_graph_index = graph_idx
        return idx

    def _hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
    ) -> bool:
        """
        執行極速增量熱自愈修補管線 (FR-03, FR-04, FR-05)：
        1. 若記憶體 _unified_index 為空，回傳 False 降級為全量建置。
        2. 僅對 dirty 檔案呼叫 AST 解析並更新符號快取池。
        3. 調用 _unified_index.patch_incremental 進行倒排差量打補丁。
        4. 調用 _call_graph_index.patch_incremental 進行調用圖譜差量修補。
        5. 快速原子持久化快照與二進位索引。
        :return: 若修補成功回傳 True，否則 False
        """
        if self._unified_index is None:
            return False

        indices_dir = self._get_indices_dir()
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

            # 找出需要移除的舊 doc_id 清單 (供圖索引差量拔除)
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

            # 差量修補向量索引
            vector_file = indices_dir / "unified.vectors.bin.gz"
            if (
                (self.hybrid_engine.vector_index is None or self.hybrid_engine.vector_index.vectors is None)
                and vector_file.exists()
            ):
                try:
                    self.hybrid_engine.vector_index = VectorIndex.load_binary(vector_file)
                except Exception as ve:
                    logger.warning(f"Failed loading vector index for hot patch: {ve}")

            if (
                self.hybrid_engine.vector_index is not None
                and self.hybrid_engine.vector_index.vectors is not None
                and self.embedding_service.is_available
            ):
                new_texts = [
                    f"{sym.name} {sym.signature} {sym.docstring}".strip()
                    for sym in all_new_symbols
                ]
                new_vecs = self.embedding_service.embed_texts(new_texts) if new_texts else None
                new_ids = [sym.id for sym in all_new_symbols]
                self.hybrid_engine.vector_index.patch_incremental(
                    removed_doc_ids=old_doc_ids,
                    new_doc_ids=new_ids,
                    new_vectors=new_vecs,
                )
                try:
                    self.hybrid_engine.vector_index.save_binary(vector_file)
                except Exception as ve:
                    logger.warning(f"Failed saving patched vector index: {ve}")

            # 快速原子持久化 (compresslevel=1)
            self._unified_index.save_binary(bin_file, compresslevel=1)
            BinarySnapshotManager.save(meta_file, full_files_map)
            return True
        except Exception as e:
            logger.warning(f"Incremental hot patch failed: {e}, falling back to full rebuild.")
            return False


    def build_index(
        self,
        space: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, InvertedIndex]:
        """
        建置空間倒排索引並原子持久化二進位 Gzip 快取至磁碟。
        若 space 為 None 則建置全域單一聯集索引 (unified.index.bin.gz)。
        """
        if space is None:
            idx = self.build_unified_index(force=force)
            return {"unified": idx}

        sp = self.space_manager.get_space(space)
        indices_dir = self._get_indices_dir()
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
        """
        全域聯集多欄位加權語意檢索 (支援 JIT 變更嗅探、自動背景熱自愈、空間與副檔名篩選、Top-N 檔案聚合與延遲代碼切片提取)。
        """
        if not query or not query.strip():
            return []

        indices_dir = self._get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        graph_file = indices_dir / "unified.graph.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"
        vector_file = indices_dir / "unified.vectors.bin.gz"

        # 預先載入快取以利增量修補
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

        # 1. JIT 變更感知與自動增量熱自愈 (FR-01, FR-03, FR-04, FR-05)
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
                if bin_file.exists() and self._unified_index is not None and diff_detail.has_changes:
                    patched = self._hot_patch_unified_index(diff_detail, full_files_map)

                if not patched:
                    self.build_unified_index(force=True, current_files=full_files_map)

                elapsed_ms = max(1, int((time.time() - t0) * 1000))
                if verbose:
                    print(
                        f"[knowledge-db:auto-rebuild] Index updated in {elapsed_ms}ms ({scanned_count} files).",
                        file=sys.stderr,
                        flush=True,
                    )

        # 2. 載入全域倒排索引 (若仍為 None 則建置)
        if self._unified_index is None:
            if bin_file.exists():
                try:
                    self._unified_index = InvertedIndex.load_binary(bin_file)
                    vector_file = indices_dir / "unified.vectors.bin.gz"
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

        # 3. 規格化空間與副檔名過濾清單
        target_spaces: Optional[List[str]] = None
        if space:
            target_spaces = [space] if isinstance(space, str) else list(space)

        target_ftypes: Optional[List[str]] = None
        if ftypes:
            target_ftypes = [ftypes] if isinstance(ftypes, str) else list(ftypes)

        flt = QueryFilter(
            spaces=target_spaces,
            languages=languages,
            kinds=kinds,
            ftypes=target_ftypes,
            min_score=min_score,
            limit=limit,
        )

        if not aggregate:
            if not lexical_only and self.hybrid_engine.is_vector_available:
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
                    if sym is None:
                        continue
                    if target_spaces and not any(s in target_spaces for s in getattr(sym, "spaces", [])):
                        continue
                    if kinds and sym.kind not in kinds:
                        continue
                    if languages and sym.language not in languages:
                        continue
                    if h["score"] <= 0:
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

        # 預設聚合模式 (FR-04, FR-05)
        if not lexical_only and self.hybrid_engine.is_vector_available:
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
                if sym is None:
                    continue
                if target_spaces and not any(s in target_spaces for s in getattr(sym, "spaces", [])):
                    continue
                if kinds and sym.kind not in kinds:
                    continue
                if languages and sym.language not in languages:
                    continue
                if h["score"] <= 0:
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

        # 4. 延遲提取代碼片段 (Top-K Lazy Fetching on Aggregated Items)
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

    def clean(self, space: Optional[str] = None) -> None:
        """
        清理指定空間或全空間之指紋快取、Bundle 檔案與倒排索引快取 (EC-03)。
        """
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        for sp in targets:
            sp_name = sp.name
            # 1. 清理指紋
            fp_file = self.space_manager.get_space_storage_dir(sp_name) / "fingerprints.json"
            if fp_file.exists():
                try:
                    fp_file.unlink()
                except OSError:
                    pass

            # 2. 清理 Bundle
            bundle_file = self.storage_dir / "bundles" / f"{sp_name}.bundle.json"
            if bundle_file.exists():
                try:
                    bundle_file.unlink()
                except OSError:
                    pass

            # 3. 清理二進位與舊版索引
            for ext in [".index.bin.gz", ".index.json"]:
                idx_file = self.storage_dir / "indices" / f"{sp_name}{ext}"
                if idx_file.exists():
                    try:
                        idx_file.unlink()
                    except OSError:
                        pass

            self._index_cache.pop(sp_name, None)

        # 4. 清理全域聯集索引、圖索引與二進位快照
        for fn in ["unified.index.bin.gz", "unified.graph.bin.gz", "unified.meta.bin"]:
            f_path = self.storage_dir / "indices" / fn
            if f_path.exists():
                try:
                    f_path.unlink()
                except OSError:
                    pass
        self._unified_index = None
        self._call_graph_index = None

    def get_call_graph(self) -> CallGraphIndex:
        """獲取已載入之全域雙向調用圖譜索引 (若未建置則自動觸發 JIT 構建)"""
        indices_dir = self._get_indices_dir()
        graph_file = indices_dir / "unified.graph.bin.gz"

        if self._call_graph_index is None and graph_file.exists():
            try:
                self._call_graph_index = CallGraphIndex.load_binary(graph_file)
            except Exception as ge:
                logger.warning(f"Failed loading graph index: {ge}")

        if self._call_graph_index is None or self._unified_index is None:
            self.build_unified_index(force=True)

        return self._call_graph_index

    def _find_target_symbol(self, query: str, space: Optional[str] = None) -> Optional[UnifiedSymbol]:
        """
        精準、透過 SymbolSelector 微型語法或語意定位目標 UnifiedSymbol
        """
        idx = self.build_unified_index()
        query_clean = query.strip()
        if not query_clean:
            return None

        # 1. 優先透過全方位 SymbolSelector 解析微型語法精準匹配 (FR-04)
        from .selector import SymbolSelector
        pool = [sym for sym in idx.symbols.values() if (not space or space in sym.spaces)]
        matches = SymbolSelector.find_matches(query_clean, pool)
        if matches:
            return matches[0]

        # 2. 既有相容後備比對
        candidates: List[UnifiedSymbol] = []
        for sym in pool:
            if sym.name == query_clean:
                return sym
            if sym.name.endswith(f".{query_clean}") or query_clean.endswith(f".{sym.name}"):
                candidates.append(sym)

        if candidates:
            return candidates[0]

        # 3. 透過 BM25 檢索尋找最高分符號
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
        """
        查詢指定符號之上游調用者清單 (Who calls me?) (FR-06)
        """
        self.search(query=target_query, space=space, limit=1)

        target_sym = self._find_target_symbol(target_query, space=space)
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
            caller_sym = self._unified_index.get_symbol(cid)
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
        """
        查詢指定符號內部調用之下游被調用者清單 (Whom do I call?) (FR-06)
        """
        self.search(query=target_query, space=space, limit=1)

        target_sym = self._find_target_symbol(target_query, space=space)
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
            callee_sym = self._unified_index.get_symbol(cid)
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
        """
        分析目標符號之重構影響面擴散拓撲 (Blast Radius Analysis) (FR-06)
        """
        self.search(query=target_query, space=space, limit=1)

        target_sym = self._find_target_symbol(target_query, space=space)
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
                sym = self._unified_index.get_symbol(sid)
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

    def format_callers_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """格式化 callers (調用源) 輸出為 ANSI 樹狀圖或 Markdown 格式"""
        target = result.get("target_symbol")
        is_md = (format_type == "md")
        if not target:
            if is_md:
                return f"### 🔍 調用源查詢: `{result.get('target_query')}` (未找到相符符號)"
            return f"[knowledge-db] 查無相符目標符號: '{result.get('target_query')}'"

        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        callers = result.get("callers", [])
        total_callers = len(callers)
        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)

        # 1. 限制模式處理
        filtered_callers = callers
        if isinstance(limit_mode, int) and limit_mode > 0:
            filtered_callers = callers[:limit_mode]

        # 2. Header
        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else ("預覽模式" if snippet else ""))
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 📞 調用源追蹤 (Callers): `{target.name}` (共找到 {total_callers} 個調用來源{desc_tag}):\n\n"
            header += f"- **📍 目標符號**: `{target.name}` ({target.kind}) 檔案: {target_link}"
            if target.signature:
                header += f"\n  - **簽名**: `{target.signature}`"
            lines = [header, ""]
        else:
            header = f"[knowledge-db] 符號 '{target.name}' 之上游調用者清單 (Callers - 共 {total_callers} 個來源{desc_tag}):"
            lines = [
                header,
                "-" * 85,
                f"📍 目標符號: `{target.name}` ({target.kind}) 檔案: {target_link}",
            ]
            if mode == "detail" and target.signature:
                lines.append(f"   簽名: {target.signature}")
            lines.append("")

        if not filtered_callers:
            empty_msg = "  (目前尚無靜態調用者依賴)" if not is_md else "> *(目前尚無靜態調用者依賴)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for idx, item in enumerate(filtered_callers, start=1):
            node_lines = []
            sym = item["symbol"]
            sites = item.get("call_sites", [])
            primary_line = sites[0]["line_number"] if sites else sym.line_number
            link_str = self.format_file_link(sym.file_path, line=primary_line)
            is_last = (idx == len(filtered_callers))
            branch = "└──" if is_last else "├──"
            pipe = "   " if is_last else "│  "
            code_snip = item.get("code_snippet")

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_callers) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            if is_md:
                # Markdown 格式
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" *(調用點: {', '.join(site_strs)})*" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
                elif mode == "detail":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**)")
                    if sym.signature:
                        node_lines.append(f"  - **簽名**: `{sym.signature}`")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: `{s['scope']}`)" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"  - **調用點**: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"  - **摘要**: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  - **調用代碼切片**:")
                            node_lines.append(f"    ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"    {mark} {ln:5d} | {code}")
                            node_lines.append("    ```")
                else:  # auto
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
            else:
                # Text / ANSI 格式
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" [調用點: {', '.join(site_strs)}]" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {link_str} ({sym.kind}:{sym.name}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)
                elif mode == "detail":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {link_str} ({sym.kind.upper()}: {sym.name})")
                    if sym.signature:
                        node_lines.append(f"{pipe}   簽名: {sym.signature}")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: {s['scope']})" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"{pipe}   調用位置: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"{pipe}   摘要: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(f"{pipe}   調用代碼切片:")
                            node_lines.append(formatted_snip)
                else:  # auto
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {link_str} ({sym.kind}:{sym.name}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)

            lines.extend(node_lines)
            rendered_nodes += 1

            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS:
                    budget_reached = True
                    remaining_count = len(filtered_callers) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個調用來源；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個調用來源；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)

    def format_callees_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        snippet: bool = True,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """格式化 callees (被調用者) 輸出為 ANSI 樹狀圖或 Markdown 格式"""
        target = result.get("target_symbol")
        is_md = (format_type == "md")
        if not target:
            if is_md:
                return f"### 🔍 被調用鏈查詢: `{result.get('target_query')}` (未找到相符符號)"
            return f"[knowledge-db] 查無相符來源符號: '{result.get('target_query')}'"

        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        callees = result.get("callees", [])
        total_callees = len(callees)
        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)

        # 1. 限制模式處理
        filtered_callees = callees
        if isinstance(limit_mode, int) and limit_mode > 0:
            filtered_callees = callees[:limit_mode]

        # 2. Header
        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else ("預覽模式" if snippet else ""))
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 📥 被調用鏈 (Callees): `{target.name}` (共找到 {total_callees} 個被調用符號{desc_tag}):\n\n"
            header += f"- **📍 來源符號**: `{target.name}` ({target.kind}) 檔案: {target_link}"
            if target.signature:
                header += f"\n  - **簽名**: `{target.signature}`"
            lines = [header, ""]
        else:
            header = f"[knowledge-db] 符號 '{target.name}' 內部調用之下游被調用者清單 (Callees - 共 {total_callees} 個項目{desc_tag}):"
            lines = [
                header,
                "-" * 85,
                f"📍 來源符號: `{target.name}` ({target.kind}) 檔案: {target_link}",
            ]
            if mode == "detail" and target.signature:
                lines.append(f"   簽名: {target.signature}")
            lines.append("")

        if not filtered_callees:
            empty_msg = "  (內部無跨符號調用點)" if not is_md else "> *(內部無跨符號調用點)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for idx, item in enumerate(filtered_callees, start=1):
            node_lines = []
            sym = item["symbol"]
            sites = item.get("call_sites", [])
            link_str = self.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
            is_last = (idx == len(filtered_callees))
            branch = "└──" if is_last else "├──"
            pipe = "   " if is_last else "│  "
            code_snip = item.get("code_snippet")

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_callees) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            if is_md:
                # Markdown 格式
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" *(調用點: {', '.join(site_strs)})*" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
                elif mode == "detail":
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**)")
                    if sym.signature:
                        node_lines.append(f"  - **簽名**: `{sym.signature}`")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: `{s['scope']}`)" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"  - **調用點**: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"  - **摘要**: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  - **目標實作切片**:")
                            node_lines.append(f"    ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"    {mark} {ln:5d} | {code}")
                            node_lines.append("    ```")
                else:  # auto
                    node_lines.append(f"- **#{idx:02d}** 檔案: {link_str} (`{sym.kind}`: **{sym.name}**){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        snip_lines = code_snip.get_lines(max_snip_lines)
                        if snip_lines:
                            node_lines.append(f"  ```{sym.language or ''}")
                            for ln, code in snip_lines:
                                mark = ">" if ln == code_snip.target_line else " "
                                node_lines.append(f"  {mark} {ln:5d} | {code}")
                            node_lines.append("  ```")
            else:
                # Text / ANSI 格式
                site_strs = [f"L{s['line_number']}" for s in sites if "line_number" in s]
                site_info = f" [調用點: {', '.join(site_strs)}]" if site_strs else ""
                if mode == "simple":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {link_str} ({sym.kind}:{sym.name}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)
                elif mode == "detail":
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {link_str} ({sym.kind.upper()}: {sym.name})")
                    if sym.signature:
                        node_lines.append(f"{pipe}   簽名: {sym.signature}")
                    if sites:
                        sites_desc = ", ".join(f"Line {s['line_number']}" + (f" (scope: {s['scope']})" if s.get("scope") else "") for s in sites)
                        node_lines.append(f"{pipe}   調用位置: {sites_desc}")
                    if code_snip and code_snip.docstring_summary:
                        node_lines.append(f"{pipe}   摘要: {code_snip.docstring_summary}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(f"{pipe}   目標實作切片:")
                            node_lines.append(formatted_snip)
                else:  # auto
                    node_lines.append(f"{branch} #{idx:02d} 檔案: {link_str} ({sym.kind}:{sym.name}){site_info}")
                    if snippet and code_snip and code_snip.lines and (max_snip_lines is None or max_snip_lines > 0):
                        formatted_snip = code_snip.format_text(prefix=f"{pipe}     ", max_lines=max_snip_lines)
                        if formatted_snip:
                            node_lines.append(formatted_snip)

            lines.extend(node_lines)
            rendered_nodes += 1

            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS:
                    budget_reached = True
                    remaining_count = len(filtered_callees) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個被調用項目；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個被調用項目；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)

    def format_impact_output(
        self,
        result: Dict[str, Any],
        detail_mode: str = "auto",
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """格式化 impact (重構影響面拓撲) 輸出為 ANSI 階層樹或 Markdown 格式"""
        target = result.get("target_symbol")
        is_md = (format_type == "md")
        if not target:
            if is_md:
                return f"### 💥 影響面拓撲查詢: `{result.get('target_query')}` (未找到相符符號)"
            return f"[knowledge-db] 查無相符目標符號: '{result.get('target_query')}'"

        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)
        depth = result.get("max_depth", 2)
        total_syms = result.get("total_impacted_symbols", 0)
        total_files = result.get("total_impacted_files", 0)

        mode_desc = "清單模式" if mode == "simple" else ("詳細模式" if mode == "detail" else "")
        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 💥 重構影響面擴散拓撲 (Impact Analysis): `{target.name}`{desc_tag}\n\n"
            header += f"- **📍 目標核心符號**: `{target.name}` ({target.kind}) 檔案: {target_link}\n"
            header += f"- **📊 影響半徑**: 擴散深度 `{depth}` 階，波及 `{total_syms}` 個符號 / `{total_files}` 個實體檔案"
            lines = [header, ""]
        else:
            header = f"[knowledge-db] 符號 '{target.name}' 重構影響面擴散拓撲 (Blast Radius: {depth} 階深度, 影響 {total_syms} 個符號 / {total_files} 個檔案{desc_tag}):"
            lines = [
                header,
                "-" * 85,
                f"📍 目標核心符號: `{target.name}` ({target.kind}) 檔案: {target_link}",
            ]
            if mode == "detail" and target.signature:
                lines.append(f"   簽名: {target.signature}")
            lines.append("")

        layers = result.get("layers", {})
        if not layers:
            empty_msg = "  (未發現上游依賴影響點，修改安全)" if not is_md else "> *(未發現上游依賴影響點，修改安全)*"
            lines.append(empty_msg)
            return "\n".join(lines)

        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0
        max_items = limit_mode if (isinstance(limit_mode, int) and limit_mode > 0) else None

        sorted_depths = sorted(layers.keys())
        for d_idx, d in enumerate(sorted_depths):
            syms = layers[d]
            is_last_depth = (d_idx == len(sorted_depths) - 1)
            depth_branch = "└──" if is_last_depth else "├──"
            tag_name = f"{d} 階直接影響 (Direct Callers)" if d == 1 else f"{d} 階間接影響 (Transitive Callers Level {d})"

            if is_md:
                lines.append(f"#### 階層 {d}：{tag_name} ({len(syms)} 個符號)")
            else:
                icon = "🟢" if d == 1 else "🟡"
                lines.append(f"{depth_branch} {icon} {tag_name} - {len(syms)} 個符號:")

            sub_prefix = "    " if is_last_depth else "│   "
            for s_idx, s in enumerate(syms):
                if max_items is not None and rendered_nodes >= max_items:
                    break

                is_last_sym = (s_idx == len(syms) - 1)
                sub_branch = "└──" if is_last_sym else "├──"
                sub_pipe = "   " if is_last_sym else "│  "
                link_str = self.format_file_link(s.file_path, line=s.line_number, end_line=s.end_line)

                if is_md:
                    if mode == "detail":
                        lines.append(f"- **#{rendered_nodes+1:02d}** 檔案: {link_str} (`{s.kind}`: **{s.name}**)")
                        if s.signature:
                            lines.append(f"  - **簽名**: `{s.signature}`")
                        if s.docstring:
                            doc_sum = s.docstring.strip().split("\n")[0]
                            lines.append(f"  - **摘要**: {doc_sum}")
                    else:
                        lines.append(f"- **#{rendered_nodes+1:02d}** 檔案: {link_str} (`{s.kind}`: **{s.name}**)")
                else:
                    if mode == "detail":
                        lines.append(f"{sub_prefix}{sub_branch} #{rendered_nodes+1:02d} 檔案: {link_str} ({s.kind.upper()}: {s.name})")
                        if s.signature:
                            lines.append(f"{sub_prefix}{sub_pipe}   簽名: {s.signature}")
                        if s.docstring:
                            doc_sum = s.docstring.strip().split("\n")[0]
                            lines.append(f"{sub_prefix}{sub_pipe}   摘要: {doc_sum}")
                    else:
                        lines.append(f"{sub_prefix}{sub_branch} #{rendered_nodes+1:02d} 檔案: {link_str} ({s.kind}:{s.name})")

                rendered_nodes += 1

                if limit_mode == "auto":
                    current_chars = sum(len(l) + 1 for l in lines)
                    if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                        budget_reached = True
                        remaining_count = total_syms - rendered_nodes
                        break

            if budget_reached or (max_items is not None and rendered_nodes >= max_items):
                break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個受影響符號；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個受影響符號；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)

    def format_search_output(
        self,
        results: List[AggregatedFileResult],
        query: str = "",
        detail_mode: str = "auto",
        snippet: bool = False,
        format_type: str = "text",
        limit_mode: Union[int, str] = "auto",
    ) -> str:
        """
        格式化 search 檢索結果為結構化終端或 Markdown 報告 (支援 auto 自適應斷層截斷與動態平滑衰減預算守門)。
        """
        if not results:
            if format_type == "md":
                return f"### 🔍 知識庫檢索: `{query}` (未找到符合的結果)"
            return f"[knowledge-db] 檢索查詢: '{query}' (未找到符合的結果)"

        # 1. 自適應分數斷層過濾 (Adaptive Score Cutoff)
        filtered_results: List[AggregatedFileResult] = list(results)
        if limit_mode == "auto":
            top_score = results[0].total_score
            min_thresh = top_score * 0.20 if top_score < 0.5 else max(0.5, top_score * 0.20)
            adapted = []
            for i, r in enumerate(results):
                if r.total_score < min_thresh:
                    break
                if i >= 3:
                    prev_score = results[i - 1].total_score
                    if r.total_score < prev_score * 0.40 or r.total_score < top_score * 0.15:
                        break
                adapted.append(r)
                if len(adapted) >= 15:
                    break
            filtered_results = adapted if adapted else [results[0]]
        elif isinstance(limit_mode, int) and limit_mode > 0:
            filtered_results = results[:limit_mode]

        total_nodes = len(filtered_results)
        is_md = (format_type == "md")
        mode = detail_mode.lower() if isinstance(detail_mode, str) else "auto"
        if mode not in ("simple", "detail"):
            mode = "auto"

        # 2. 決定 Header
        mode_desc = ""
        if mode == "simple":
            mode_desc = "清單模式"
        elif mode == "detail":
            mode_desc = "詳細模式"
        elif snippet:
            mode_desc = "預覽模式"

        desc_tag = f"，{mode_desc}" if mode_desc else ""

        if is_md:
            header = f"### 🔍 知識庫檢索: `{query}` (共找到 {total_nodes} 個檔案節點{desc_tag}):\n"
        else:
            header = f"[knowledge-db] 檢索查詢: '{query}' (共找到 {total_nodes} 個檔案節點{desc_tag}):"

        lines = [header]
        if not is_md and mode in ("detail", "auto") and snippet:
            lines.append("=" * 85)

        # 3. 逐檔案節點渲染 (含動態預算與衰減切片守門)
        rendered_nodes = 0
        budget_reached = False
        remaining_count = 0

        for rank, res in enumerate(filtered_results, start=1):
            node_lines = []
            first_sym = res.items[0].symbol if res.items else None
            first_line = first_sym.line_number if first_sym else None
            first_end = first_sym.end_line if first_sym else None
            file_link = self.format_file_link(res.file_path, line=first_line, end_line=first_end)

            max_snip_lines: Optional[int] = None
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_results) - rendered_nodes
                    break
                max_snip_lines = compute_dynamic_snippet_lines(current_chars)

            if is_md:
                # Markdown 格式
                if mode == "simple":
                    node_lines.append(f"- **#{rank:02d}** 檔案: {file_link}")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  - `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            snip_lines = itm.code_snippet.get_lines(max_snip_lines)
                            if snip_lines:
                                lang = res.language or ""
                                node_lines.append(f"    ```{lang}")
                                for ln, code in snip_lines:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"    {mark} {ln:5d} | {code}")
                                node_lines.append("    ```")
                elif mode == "detail":
                    node_lines.append(f"#### #{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} *({res.language}, {len(res.items)} 個命中項目)*")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"- **#{rank:02d}.{itm_idx}** [{itm.score:05.2f}] `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if sym.signature:
                            node_lines.append(f"  - **簽名**: `{sym.signature}`")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            node_lines.append(f"  - **摘要**: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            node_lines.append(f"  - **摘要**: {itm.snippet}")
                        if itm.matched_terms:
                            node_lines.append(f"  - **命中詞**: {', '.join(itm.matched_terms)}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            snip_lines = itm.code_snippet.get_lines(max_snip_lines)
                            if snip_lines:
                                lang = res.language or ""
                                node_lines.append(f"  - **代碼切片** ({line_range}):")
                                node_lines.append(f"    ```{lang}")
                                for ln, code in snip_lines:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"    {mark} {ln:5d} | {code}")
                                node_lines.append("    ```")
                else:  # auto
                    node_lines.append(f"- **#{rank:02d}** [{res.total_score:05.2f}] 檔案: {file_link} *({res.language})*")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  - **#{rank:02d}.{itm_idx}** [{itm.score:05.2f}] `{sym.kind.upper()}`: **{sym.name}** ({line_range})")
                        if sym.signature:
                            node_lines.append(f"    - **簽名**: `{sym.signature}`")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            node_lines.append(f"    - **摘要**: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            node_lines.append(f"    - **摘要**: {itm.snippet}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            snip_lines = itm.code_snippet.get_lines(max_snip_lines)
                            if snip_lines:
                                lang = res.language or ""
                                node_lines.append(f"    ```{lang}")
                                for ln, code in snip_lines:
                                    mark = ">" if ln == itm.code_snippet.target_line else " "
                                    node_lines.append(f"    {mark} {ln:5d} | {code}")
                                node_lines.append("    ```")
            else:
                # Text / ANSI 終端格式
                if mode == "simple":
                    node_lines.append(f"#{rank:02d} 檔案: {file_link}")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  {branch} {sym.kind.upper()}: {sym.name} ({line_range})")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            formatted_snip = itm.code_snippet.format_text(prefix=f"  {pipe}     ", max_lines=max_snip_lines)
                            if formatted_snip:
                                node_lines.append(formatted_snip)
                elif mode == "detail":
                    node_lines.append(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} ({len(res.items)} 個命中項目, {res.language})")
                    for itm_idx, itm in enumerate(res.items, start=1):
                        is_last = (itm_idx == len(res.items))
                        branch = "└──" if is_last else "├──"
                        pipe = "   " if is_last else "│  "
                        sym = itm.symbol
                        line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                        node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {sym.kind.upper()}: {sym.name} ({line_range})")
                        if sym.signature:
                            node_lines.append(f"  {pipe}   簽名: {sym.signature}")
                        if itm.code_snippet and itm.code_snippet.docstring_summary:
                            node_lines.append(f"  {pipe}   摘要: {itm.code_snippet.docstring_summary}")
                        elif itm.snippet:
                            node_lines.append(f"  {pipe}   摘要: {itm.snippet}")
                        if itm.matched_terms:
                            node_lines.append(f"  {pipe}   命中詞: {', '.join(itm.matched_terms)}")
                        if snippet and itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                            formatted_snip = itm.code_snippet.format_text(prefix=f"  {pipe}     ", max_lines=max_snip_lines)
                            if formatted_snip:
                                node_lines.append(f"  {pipe}   代碼切片 ({line_range}):")
                                node_lines.append(formatted_snip)
                    node_lines.append("-" * 85)
                else:  # auto
                    if snippet:
                        node_lines.append(f"#{rank:02d} [{res.total_score:05.2f}] 檔案: {file_link} ({len(res.items)} 個命中項目, {res.language})")
                        for itm_idx, itm in enumerate(res.items, start=1):
                            is_last = (itm_idx == len(res.items))
                            branch = "└──" if is_last else "├──"
                            pipe = "   " if is_last else "│  "
                            sym = itm.symbol
                            line_range = f"Lines {sym.line_number}~{sym.end_line}" if sym.end_line and sym.end_line > sym.line_number else f"Line {sym.line_number}"
                            node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} [{itm.score:05.2f}] {sym.kind.upper()}: {sym.name} ({line_range})")
                            if sym.signature:
                                node_lines.append(f"  {pipe}   簽名: {sym.signature}")
                            if itm.code_snippet and itm.code_snippet.docstring_summary:
                                node_lines.append(f"  {pipe}   摘要: {itm.code_snippet.docstring_summary}")
                            elif itm.snippet:
                                node_lines.append(f"  {pipe}   摘要: {itm.snippet}")
                            if itm.code_snippet and itm.code_snippet.lines and (max_snip_lines is None or max_snip_lines > 0):
                                formatted_snip = itm.code_snippet.format_text(prefix=f"  {pipe}     ", max_lines=max_snip_lines)
                                if formatted_snip:
                                    node_lines.append(f"  {pipe}   代碼切片 ({line_range}):")
                                    node_lines.append(formatted_snip)
                        node_lines.append("-" * 85)
                    else:
                        if len(res.items) == 1:
                            sym = res.items[0].symbol
                            sym_link = self.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
                            node_lines.append(f"#{rank:02d} 檔案: {sym_link} ({sym.kind}:{sym.name}) [{res.total_score:05.2f}]")
                        else:
                            node_lines.append(f"#{rank:02d} 檔案: {file_link} (總分: {res.total_score:05.2f}, {len(res.items)} 項命中):")
                            for itm_idx, itm in enumerate(res.items, start=1):
                                is_last = (itm_idx == len(res.items))
                                branch = "└──" if is_last else "├──"
                                sym = itm.symbol
                                sym_link = self.format_file_link(sym.file_path, line=sym.line_number, end_line=sym.end_line)
                                node_lines.append(f"  {branch} #{rank:02d}.{itm_idx} {sym_link} ({sym.kind}:{sym.name}) [{itm.score:05.2f}]")

            lines.extend(node_lines)
            rendered_nodes += 1

            # 檢查 20000 字元預算上限 (保底 5 個項目)
            if limit_mode == "auto":
                current_chars = sum(len(l) + 1 for l in lines)
                if current_chars >= AUTO_BUDGET_CHARS and rendered_nodes >= AUTO_MIN_RENDERED_ITEMS:
                    budget_reached = True
                    remaining_count = len(filtered_results) - rendered_nodes
                    break

        if budget_reached and remaining_count > 0:
            if is_md:
                lines.append(f"\n> 💡 *... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個檔案結果；可附加 `--limit=N` 查看更多)*")
            else:
                lines.append(f"\n... (已達 {AUTO_BUDGET_CHARS} 字元自適應上限，尚有 {remaining_count} 個檔案結果；可附加 --limit=<N> 查看完整輸出)")

        return "\n".join(lines)


