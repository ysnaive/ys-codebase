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
from .parsers.registry import ParserRegistry
from .retrieval import BM25Engine, CodeSnippet, InvertedIndex, QueryFilter, SearchResult, SnippetExtractor
from .scanner import BinarySnapshotManager, FingerprintScanner, ScanDiffResult
from .schema import AggregatedFileResult, AggregatedItem, UnifiedSymbol
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
        self.snippet_extractor = SnippetExtractor(workspace_root=self._get_workspace_root())

    def _get_workspace_root(self) -> Path:
        try:
            from core import uri
            host_dir = uri.get_host_dir()
            if host_dir:
                return Path(host_dir)
        except Exception:
            pass
        return Path.cwd()

    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str:
        """將路徑正規化為相對於 Workspace 根目錄之標準相對路徑 (forward slash)"""
        p = Path(file_path)
        ws = self._get_workspace_root().resolve()
        try:
            if p.is_absolute():
                rel = p.resolve().relative_to(ws)
                return str(rel).replace("\\", "/")
        except ValueError:
            pass
        s = str(file_path).replace("\\", "/")
        if ws.name == "ys_codebase" and s.startswith("ys_codebase/"):
            s = s[len("ys_codebase/"):]
        return s

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
        建置全專案空間聯集單一倒排索引，並原子持久化二進位 Gzip 快取 (unified.index.bin.gz)
        與二進位狀態快照 (unified.meta.bin) 至磁碟。
        """
        indices_dir = self._get_indices_dir()
        bin_file = indices_dir / "unified.index.bin.gz"
        meta_file = indices_dir / "unified.meta.bin"

        if not force and bin_file.exists() and meta_file.exists():
            try:
                idx = InvertedIndex.load_binary(bin_file)
                self._unified_index = idx
                return idx
            except Exception as e:
                logger.warning(f"Failed loading unified binary index, rebuilding: {e}")

        # 全域聯集去重打包
        bundle = self.bundler.bundle_union()
        idx = InvertedIndex(space_name="unified")
        idx.build_unified(bundle.symbols, tokenizer=self.tokenizer)

        # 原子持久化二進位 Gzip 索引
        try:
            idx.save_binary(bin_file)
        except Exception as e:
            raise KnowledgeDBError(f"Failed saving unified binary index: {e}")

        # 收集或使用現有檔案快照並持久化
        files_map = current_files
        if files_map is None:
            files_map = bundle.metadata.get("files_map", {})

        try:
            BinarySnapshotManager.save(meta_file, files_map)
        except Exception as e:
            logger.warning(f"Failed saving binary snapshot meta: {e}")

        self._unified_index = idx
        return idx

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
        meta_file = indices_dir / "unified.meta.bin"

        # 1. JIT 變更感知與自動熱自愈 (FR-03, FR-04)
        if auto_rebuild:
            is_dirty, scanned_count, reason, current_files = self.scanner.check_invalidation(
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
                self.build_unified_index(force=True, current_files=current_files)
                elapsed_ms = max(1, int((time.time() - t0) * 1000))
                if verbose:
                    print(
                        f"[knowledge-db:auto-rebuild] Index updated in {elapsed_ms}ms ({scanned_count} files).",
                        file=sys.stderr,
                        flush=True,
                    )

        # 2. 載入全域倒排索引
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

        # 4. 清理全域聯集索引與二進位快照
        for fn in ["unified.index.bin.gz", "unified.meta.bin"]:
            f_path = self.storage_dir / "indices" / fn
            if f_path.exists():
                try:
                    f_path.unlink()
                except OSError:
                    pass
        self._unified_index = None

