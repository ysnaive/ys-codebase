"""
knowledge-db 統一門面 SDK (engine.py)
整合空間治理、雙階指紋比對、多語言解析、語意打包、BM25 檢索與二進位 Gzip 快取中心。
100% 採用純 Python 原生標準庫 (Zero External Dependency)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from .bundler import SemanticBundle, SemanticBundler
from .exceptions import KnowledgeDBError, SpaceNotFoundError
from .parsers.registry import ParserRegistry
from .retrieval import BM25Engine, CodeSnippet, InvertedIndex, QueryFilter, SearchResult, SnippetExtractor
from .scanner import FingerprintScanner, ScanDiffResult
from .schema import UnifiedSymbol
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

    def build_index(
        self,
        space: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, InvertedIndex]:
        """
        建置空間倒排索引並原子持久化二進位 Gzip 快取 (.index.bin.gz) 至磁碟。
        """
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        indices_dir = self._get_indices_dir()
        result_indices = {}

        for sp in targets:
            sp_name = sp.name
            bin_file = indices_dir / f"{sp_name}.index.bin.gz"
            legacy_json = indices_dir / f"{sp_name}.index.json"

            if not force and bin_file.exists():
                try:
                    idx = InvertedIndex.load_binary(bin_file)
                    self._index_cache[sp_name] = idx
                    result_indices[sp_name] = idx
                    continue
                except Exception as e:
                    logger.warning(f"Failed loading binary cached index for '{sp_name}', rebuilding: {e}")
            elif not force and legacy_json.exists():
                try:
                    with open(legacy_json, "r", encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                    idx = InvertedIndex.from_dict(data)
                    idx.save_binary(bin_file)  # 自動升級轉換為二進位
                    self._index_cache[sp_name] = idx
                    result_indices[sp_name] = idx
                    continue
                except Exception as e:
                    logger.warning(f"Failed converting legacy JSON index for '{sp_name}', rebuilding: {e}")

            # 即時打包並構建倒排索引
            bundle = self.bundler.bundle_space(sp)
            idx = InvertedIndex(space_name=sp_name)
            idx.build(bundle.symbols, tokenizer=self.tokenizer, space=sp_name)

            # 原子持久化二進位 Gzip
            try:
                idx.save_binary(bin_file)
            except Exception as e:
                raise KnowledgeDBError(f"Failed saving binary index cache for '{sp_name}': {e}")

            self._index_cache[sp_name] = idx
            result_indices[sp_name] = idx

        return result_indices

    def search(
        self,
        query: str,
        space: Optional[str] = None,
        kinds: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        min_score: float = 0.01,
        limit: int = 10,
        snippet: bool = False,
        context_lines: int = 3,
    ) -> List[SearchResult]:
        """
        多空間多欄位加權語意檢索 (支援自動懶加載二進位快取、即時索引建置與延遲代碼片段提取)。
        """
        if not query or not query.strip():
            return []

        # 1. 確保目標空間已加載倒排索引 (Lazy Indexing, EC-01)
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()

        for sp in targets:
            sp_name = sp.name
            if sp_name not in self._index_cache:
                bin_file = self._get_indices_dir() / f"{sp_name}.index.bin.gz"
                legacy_json = self._get_indices_dir() / f"{sp_name}.index.json"

                if bin_file.exists():
                    try:
                        self._index_cache[sp_name] = InvertedIndex.load_binary(bin_file)
                    except Exception:
                        self.build_index(space=sp_name, force=True)
                elif legacy_json.exists():
                    try:
                        with open(legacy_json, "r", encoding="utf-8", errors="replace") as f:
                            data = json.load(f)
                        idx = InvertedIndex.from_dict(data)
                        idx.save_binary(bin_file)
                        self._index_cache[sp_name] = idx
                    except Exception:
                        self.build_index(space=sp_name, force=True)
                else:
                    self.build_index(space=sp_name, force=True)

        # 2. 構建全域查詢倒排索引 (零拷貝聚合 Posting 清單與符號池)
        merged_index = InvertedIndex(space_name="merged")
        for sp in targets:
            idx = self._index_cache.get(sp.name)
            if idx:
                for term, postings in idx.index.items():
                    merged_index.index[term].extend(postings)
                merged_index.doc_count += idx.doc_count
                for f in InvertedIndex.INDEXED_FIELDS:
                    merged_index.field_total_lengths[f] += idx.field_total_lengths.get(f, 0)
                merged_index.symbols.update(idx.symbols)

        if merged_index.doc_count > 0:
            for f in InvertedIndex.INDEXED_FIELDS:
                merged_index.field_avgdl[f] = max(
                    1.0, merged_index.field_total_lengths[f] / merged_index.doc_count
                )
        else:
            return []

        # 3. 執行檢索
        flt = QueryFilter(
            spaces=[space] if space else None,
            languages=languages,
            kinds=kinds,
            min_score=min_score,
            limit=limit,
        )

        raw_results = self.bm25_engine.search(query=query, index=merged_index, filter_cfg=flt)

        if not snippet:
            return raw_results

        # 4. 延遲提取代碼片段 (Top-K Lazy Fetching, FR-02)
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

            # 4. 清理記憶體快取
            self._index_cache.pop(sp_name, None)
