"""
knowledge-db 統一門面 SDK (engine.py)
整合空間治理、雙階指紋比對、多語言解析、語意打包、BM25 檢索與二進位 Gzip 快取中心。
採用 Pipeline 與 Formatter 解耦架構，維持 100% 向下相容的薄 Facade 門面。
"""

from collections import defaultdict
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .bundler import SemanticBundle, SemanticBundler
from .embedding import EmbeddingService, VectorIndex
from .exceptions import KnowledgeDBError, SpaceNotFoundError
from .formatter import (
    AUTO_BUDGET_CHARS,
    AUTO_DECAY_START_CHARS,
    AUTO_DECAY_MIN_CHARS,
    AUTO_NO_SNIPPET_CHARS,
    AUTO_MAX_SNIPPET_LINES,
    AUTO_MIN_SNIPPET_LINES,
    AUTO_MIN_RENDERED_ITEMS,
    compute_dynamic_snippet_lines,
    ResultFormatter,
    UniversalRedundancyFilter,
)
from .graph import CallGraphIndex
from .hybrid import HybridSearchEngine
from .parsers.registry import ParserRegistry
from .pipeline import IndexingPipeline
from .retrieval import BM25Engine, CodeSnippet, InvertedIndex, QueryFilter, SearchResult, SnippetExtractor
from .scanner import FingerprintScanner, ScanDiffDetail, ScanDiffResult
from .schema import AggregatedFileResult, AggregatedItem, SymbolCallSite, UnifiedSymbol
from .space import SpaceManager
from .tokenizer import MultilingualTokenizer

logger = logging.getLogger("knowledge-db.engine")


class KnowledgeEngine:
    """
    knowledge-db 模組頂層統一門面 Facade SDK。
    提供一站式呼叫空間狀態查詢、增量掃描、語意打包、倒排索引建置、語意檢索與快取清理。
    內部將呈現層輸出格式化委派予 ResultFormatter，索引與檢索生命週期委派予 IndexingPipeline。
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
        self.snippet_extractor = SnippetExtractor(
            workspace_root=self._get_workspace_root(),
            space_manager=self.space_manager,
        )

        # 解耦之核心流水線與呈現層中樞
        self.pipeline = IndexingPipeline(
            space_manager=self.space_manager,
            bundler=self.bundler,
            scanner=self.scanner,
            tokenizer=self.tokenizer,
            bm25_engine=self.bm25_engine,
            embedding_service=self.embedding_service,
            hybrid_engine=self.hybrid_engine,
            snippet_extractor=self.snippet_extractor,
        )
        self.formatter = ResultFormatter(
            space_manager=self.space_manager,
            workspace_root=self._get_workspace_root(),
        )

    # ----------------------------------------------------------------------
    # 屬性轉發 (向後相容契約)
    # ----------------------------------------------------------------------

    @property
    def storage_dir(self) -> Path:
        return self.space_manager.storage_dir

    @property
    def _indices_dir(self) -> Path:
        return self.pipeline.get_indices_dir()

    def _get_indices_dir(self) -> Path:
        return self.pipeline.get_indices_dir()

    @property
    def _unified_index(self) -> Optional[InvertedIndex]:
        return self.pipeline.unified_index

    @_unified_index.setter
    def _unified_index(self, val: Optional[InvertedIndex]) -> None:
        self.pipeline.unified_index = val

    @property
    def _call_graph_index(self) -> Optional[CallGraphIndex]:
        return self.pipeline.call_graph_index

    @_call_graph_index.setter
    def _call_graph_index(self, val: Optional[CallGraphIndex]) -> None:
        self.pipeline.call_graph_index = val

    @property
    def _index_cache(self) -> Dict[str, InvertedIndex]:
        return self.pipeline.index_cache

    # ----------------------------------------------------------------------
    # 路徑與 Markdown 標籤轉譯委派 (委派 ResultFormatter)
    # ----------------------------------------------------------------------

    def _get_workspace_root(self) -> Path:
        return self.formatter._get_workspace_root() if hasattr(self, "formatter") else Path.cwd().resolve()

    def normalize_workspace_path(self, file_path: Union[str, Path]) -> str:
        return self.formatter.normalize_workspace_path(file_path)

    def to_file_uri(self, file_path: Union[str, Path], line: Optional[int] = None) -> str:
        return self.formatter.to_file_uri(file_path, line=line)

    def format_file_link(
        self,
        file_path: Union[str, Path],
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        use_basename: bool = True,
    ) -> str:
        return self.formatter.format_file_link(file_path, line=line, end_line=end_line, use_basename=use_basename)

    # ----------------------------------------------------------------------
    # 呈現層格式化輸出委派 (8000 字元預算 + 全域重複資訊剔除)
    # ----------------------------------------------------------------------

    def format_search_output(self, *args, **kwargs) -> str:
        return self.formatter.format_search_output(*args, **kwargs)

    def format_callers_output(self, *args, **kwargs) -> str:
        return self.formatter.format_callers_output(*args, **kwargs)

    def format_callees_output(self, *args, **kwargs) -> str:
        return self.formatter.format_callees_output(*args, **kwargs)

    def format_impact_output(self, *args, **kwargs) -> str:
        return self.formatter.format_impact_output(*args, **kwargs)

    # ----------------------------------------------------------------------
    # 索引流水線委派 (建置、增量熱補丁、清理)
    # ----------------------------------------------------------------------

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Tuple[float, int]]] = None,
    ) -> InvertedIndex:
        return self.pipeline.build_unified_index(force=force, current_files=current_files)

    def _hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Dict[str, Tuple[float, int]],
    ) -> bool:
        return self.pipeline.hot_patch_unified_index(diff_detail, full_files_map)

    def build_index(
        self,
        space: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, InvertedIndex]:
        return self.pipeline.build_index(space=space, force=force)

    def clean(self, space: Optional[str] = None) -> None:
        self.pipeline.clean(space=space)

    # ----------------------------------------------------------------------
    # 生命週期與空間操作
    # ----------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """獲取全系統空間、指紋快取、同義詞與倒排索引統計摘要。"""
        spaces = self.space_manager.load_spaces()
        thesaurus_groups = self.space_manager.load_thesaurus()
        indices_dir = self.pipeline.get_indices_dir()

        space_details = {}
        for sp_name, sp in spaces.items():
            fps = self.scanner.load_fingerprints(sp_name)
            cached_files = len(fps)

            bin_idx = indices_dir / f"{sp_name}.index.bin.gz"
            json_idx = indices_dir / f"{sp_name}.index.json"
            has_index = bin_idx.exists() or json_idx.exists()

            space_details[sp_name] = {
                "origin": sp.origin,
                "description": sp.description,
                "include": sp.include,
                "exclude": sp.exclude,
                "include_count": len(sp.include),
                "file_patterns": sp.file_patterns,
                "cached_files": cached_files,
                "fingerprint_cached_files": cached_files,
                "has_index": has_index,
            }

        bin_unified = indices_dir / "unified.index.bin.gz"
        json_unified = indices_dir / "unified.index.json"
        has_unified_index = bin_unified.exists() or json_unified.exists()

        return {
            "total_spaces": len(spaces),
            "spaces": space_details,
            "has_unified_index": has_unified_index,
            "thesaurus_groups": len(thesaurus_groups),
            "storage_dir": str(self.storage_dir),
        }

    def scan(self, space: Optional[str] = None, force: bool = False) -> Dict[str, ScanDiffResult]:
        """執行指紋增量掃描，回傳各空間之檔案變更統計差異清冊。"""
        if space is not None:
            sp = self.space_manager.get_space(space)
            diff = self.scanner.scan_space(sp, force=force)
            return {sp.name: diff}
        return self.scanner.scan_all_spaces(force=force)

    def bundle(
        self,
        space: Optional[str] = None,
        export_path: Optional[Union[str, Path]] = None,
        pretty: bool = False,
    ) -> List[SemanticBundle]:
        """執行空間符號提取與 SemanticBundle 導出。"""
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.get_union_spaces()
        bundles = []
        for sp in targets:
            b = self.bundler.bundle_space(sp)
            self.bundler.export_bundle(b, target_path=export_path)
            bundles.append(b)
        return bundles

    # ----------------------------------------------------------------------
    # 符號搜尋與拓撲分析委派 (委派 IndexingPipeline)
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
        return self.pipeline.search(
            query=query,
            space=space,
            kinds=kinds,
            languages=languages,
            ftypes=ftypes,
            min_score=min_score,
            limit=limit,
            snippet=snippet,
            context_lines=context_lines,
            auto_rebuild=auto_rebuild,
            verbose=verbose,
            aggregate=aggregate,
            lexical_only=lexical_only,
        )

    def get_call_graph(self) -> CallGraphIndex:
        return self.pipeline.get_call_graph()

    def _find_target_symbol(self, query: str, space: Optional[str] = None) -> Optional[UnifiedSymbol]:
        return self.pipeline.find_target_symbol(query, space=space)

    def act_callers(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
    ) -> Dict[str, Any]:
        return self.pipeline.act_callers(target_query, space=space, snippet=snippet)

    def act_callees(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
    ) -> Dict[str, Any]:
        return self.pipeline.act_callees(target_query, space=space, snippet=snippet)

    def act_impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.pipeline.act_impact(target_query, depth=depth, space=space)
