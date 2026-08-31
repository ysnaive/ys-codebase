"""
knowledge-db 統一門面 SDK (engine.py)
整合空間治理、雙階指紋比對、多語言解析、語意打包、BM25 檢索與二進位 Gzip 快取中心。
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

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
from .thesaurus import ThesaurusEngine
from .tokenizer import CodeTokenizer

logger = logging.getLogger("knowledge-db.engine")


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
    ):
        self.space_manager = SpaceManager(
            config_dir=config_dir,
            storage_dir=storage_dir,
            contributes_data=contributes_data,
        )
        self.tokenizer = CodeTokenizer()
        self.thesaurus_engine = ThesaurusEngine(
            custom_groups=self.space_manager.load_thesaurus()
        )
        self.parser_registry = ParserRegistry()
        self.scanner = FingerprintScanner(self.space_manager)
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
        )
        self.bm25_engine = BM25Engine(
            tokenizer=self.tokenizer,
            thesaurus=self.thesaurus_engine,
            field_weights=field_weights,
        )
        self._index_cache: Dict[str, InvertedIndex] = {}
        self._unified_index: Optional[InvertedIndex] = None
        self._call_graph_index: Optional[CallGraphIndex] = None
        self.snippet_extractor = SnippetExtractor(workspace_root=self._get_workspace_root())

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
    ) -> str:
        """
        格式化為 IDE 相容之 Markdown 檔案超連結標籤: [rel_path:Lxx~Lyy](file:///abs_path#Lxx)

        :param file_path: 檔案路徑
        :param line: 起始行號 (可選)
        :param end_line: 結束行號 (可選)
        :return: Markdown 格式字串 (例: [src/engine.py:L10-20](file:///.../engine.py#L10))
        """
        rel_path = self.normalize_workspace_path(file_path)
        if line is not None:
            if end_line is not None and end_line > line:
                label = f"{rel_path}:L{line}-{end_line}"
            else:
                label = f"{rel_path}:L{line}"
        else:
            label = rel_path

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
            thesaurus=self.thesaurus_engine,
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
                    thesaurus=self.thesaurus_engine,
                    tokenizer=self.tokenizer,
                )
                new_edges = linker.link_call_sites(dirty_sites, dirty_imports)
                self._call_graph_index.patch_incremental(
                    dirty_file_paths=dirty_keys,
                    new_edges=new_edges,
                    old_symbol_ids=old_doc_ids,
                )
                self._call_graph_index.save_binary(graph_file, compresslevel=1)

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
            raw_results = self.bm25_engine.search(query=query, index=unified_index, filter_cfg=flt)
            if not snippet:
                return raw_results

            results_with_snippets: List[SearchResult] = []
            for r in raw_results:
                snip = self.snippet_extractor.extract(
                    file_path=r.symbol.file_path,
                    line_number=r.symbol.line_number,
                    context_before=2,
                    context_after=max(2, context_lines + 1),
                    docstring=r.symbol.docstring,
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
                    context_before=2,
                    context_after=max(2, context_lines + 1),
                    docstring=itm.symbol.docstring,
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
        精準或透過語意定位目標 UnifiedSymbol
        """
        idx = self.build_unified_index()
        query_clean = query.strip()
        candidates: List[UnifiedSymbol] = []
        for sym in idx.symbols.values():
            if space and space not in sym.spaces:
                continue
            if sym.name == query_clean:
                return sym
            if sym.name.endswith(f".{query_clean}") or query_clean.endswith(f".{sym.name}"):
                candidates.append(sym)

        if candidates:
            return candidates[0]

        # 透過 BM25 檢索尋找最高分符號
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
                    context_after=3,
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
                    context_before=2,
                    context_after=3,
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

    def format_callers_output(self, result: Dict[str, Any], snippet: bool = True) -> str:
        """格式化 callers 輸出為帶有 RFC 8089 可點擊連結的 Markdown 報告"""
        target = result.get("target_symbol")
        if not target:
            return f"[knowledge-db] 查無相符符號: '{result.get('target_query')}'"

        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)
        lines = [
            f"[knowledge-db] 符號 '{target.name}' 之上游調用者清單 (Callers - 共 {result.get('total_callers', 0)} 個調用來源):",
            "-" * 80,
            f"📍 目標符號: `{target.name}` ({target_link})",
        ]

        callers = result.get("callers", [])
        if not callers:
            lines.append("  (目前尚無靜態調用者)")
            return "\n".join(lines)

        for idx, item in enumerate(callers, start=1):
            sym = item["symbol"]
            sites = item.get("call_sites", [])
            line_num = sites[0]["line_number"] if sites else sym.line_number
            link_str = self.format_file_link(sym.file_path, line=line_num)
            is_last = (idx == len(callers))
            branch = "└──" if is_last else "├──"
            lines.append(f"{branch} 🔹 {link_str} (`{sym.name}`)")

            code_snip = item.get("code_snippet")
            if snippet and code_snip and code_snip.lines:
                sub_indent = "    " if is_last else "│   "
                lines.append(code_snip.format_text(prefix=sub_indent + "  "))

        return "\n".join(lines)

    def format_callees_output(self, result: Dict[str, Any], snippet: bool = True) -> str:
        """格式化 callees 輸出為帶有 RFC 8089 可點擊連結的 Markdown 報告"""
        target = result.get("target_symbol")
        if not target:
            return f"[knowledge-db] 查無相符符號: '{result.get('target_query')}'"

        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)
        lines = [
            f"[knowledge-db] 符號 '{target.name}' 內部調用之下游被調用者清單 (Callees - 共 {result.get('total_callees', 0)} 個被調用點):",
            "-" * 80,
            f"📍 來源符號: `{target.name}` ({target_link})",
        ]

        callees = result.get("callees", [])
        if not callees:
            lines.append("  (內部無跨符號調用點)")
            return "\n".join(lines)

        for idx, item in enumerate(callees, start=1):
            sym = item["symbol"]
            link_str = self.format_file_link(sym.file_path, line=sym.line_number)
            is_last = (idx == len(callees))
            branch = "└──" if is_last else "├──"
            lines.append(f"{branch} 🔹 {link_str} (`{sym.name}`)")

            code_snip = item.get("code_snippet")
            if snippet and code_snip and code_snip.lines:
                sub_indent = "    " if is_last else "│   "
                lines.append(code_snip.format_text(prefix=sub_indent + "  "))

        return "\n".join(lines)

    def format_impact_output(self, result: Dict[str, Any]) -> str:
        """格式化 impact 影響面分析輸出為階層樹狀圖"""
        target = result.get("target_symbol")
        if not target:
            return f"[knowledge-db] 查無相符符號: '{result.get('target_query')}'"

        target_link = self.format_file_link(target.file_path, line=target.line_number, end_line=target.end_line)
        depth = result.get("max_depth", 2)
        total_syms = result.get("total_impacted_symbols", 0)
        total_files = result.get("total_impacted_files", 0)

        lines = [
            f"[knowledge-db] 符號 '{target.name}' 重構影響面擴散拓撲 (Blast Radius: {depth} 階深度, 影響 {total_syms} 個符號 / {total_files} 個檔案):",
            "-" * 80,
            f"📍 目標核心符號: `{target.name}` ({target_link})",
        ]

        layers = result.get("layers", {})
        if not layers:
            lines.append("  (未發現上游依賴影響點，修改安全)")
            return "\n".join(lines)

        sorted_depths = sorted(layers.keys())
        for d_idx, d in enumerate(sorted_depths):
            syms = layers[d]
            is_last_depth = (d_idx == len(sorted_depths) - 1)
            depth_branch = "└──" if is_last_depth else "├──"
            tag = "🟢 1 階直接影響 (Direct Callers)" if d == 1 else f"🟡 {d} 階間接影響 (Transitive Callers Level {d})"
            lines.append(f"{depth_branch} {tag} - {len(syms)} 個符號:")

            sub_prefix = "    " if is_last_depth else "│   "
            for s_idx, s in enumerate(syms):
                is_last_sym = (s_idx == len(syms) - 1)
                sub_branch = "└──" if is_last_sym else "├──"
                link_str = self.format_file_link(s.file_path, line=s.line_number)
                lines.append(f"{sub_prefix}{sub_branch} {link_str} (`{s.name}`)")

        return "\n".join(lines)


