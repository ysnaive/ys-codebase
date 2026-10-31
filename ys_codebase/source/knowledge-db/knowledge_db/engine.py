"""
knowledge-db 統一門面 SDK (engine.py)
整合空間治理、雙階指紋比對、多語言解析、語意打包、BM25 檢索與二進位 Gzip 快取中心。
採用 Pipeline、TopologyQueryService 與 ResultFormatter 解耦架構。
"""

import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Union

from .bundler import SemanticBundle, SemanticBundler
from .embedding import EmbeddingService
from .formatter import ResultFormatter
from .hybrid import HybridSearchEngine
from .parsers.registry import ParserRegistry
from .pipeline import IndexingPipeline
from .retrieval import BM25Engine, InvertedIndex, SearchResult, SnippetExtractor
from .scanner import BinarySnapshotManager, FingerprintScanner, ScanDiffResult
from .schema import AggregatedFileResult
from .space import SpaceManager
from .tokenizer import MultilingualTokenizer

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
        embedding_mock_mode: Optional[bool] = None,
    ):
        self.space_manager = SpaceManager(
            config_dir=config_dir,
            storage_dir=storage_dir,
            contributes_data=contributes_data,
        )
        self.tokenizer = MultilingualTokenizer()
        self.parser_registry = ParserRegistry()
        self.scanner = FingerprintScanner(self.space_manager)
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
        )
        self.bm25_engine = BM25Engine(
            tokenizer=self.tokenizer,
            field_weights=field_weights,
        )

        from .config import KnowledgeDBConfig
        self.config = KnowledgeDBConfig.load(
            local_config=local_config,
            project_config=project_config,
        )

        models_dir = self.space_manager.storage_dir / "models" if hasattr(self.space_manager, "storage_dir") else None
        if embedding_mock_mode is not None:
            mock_mode = embedding_mock_mode
        else:
            mock_mode = (
                os.environ.get("KNOWLEDGE_DB_MOCK_EMBEDDING") == "1"
                or os.environ.get("YSCB_MOCK_EMBEDDING") == "1"
                or os.environ.get("YSCB_TEST_SANDBOX") == "1"
            )
        self.embedding_service = EmbeddingService(
            cache_dir=models_dir,
            mock_mode=mock_mode,
            model_name=self.config.embedding_model,
            max_threads=self.config.resolve_threads(),
            enable_vector_search=getattr(self.config, "enable_vector_search", True),
        )
        self.hybrid_engine = HybridSearchEngine(
            inverted_index=None,
            embedding_service=self.embedding_service,
            bm25_engine=self.bm25_engine,
        )
        self.formatter = ResultFormatter(
            space_manager=self.space_manager,
            workspace_root=Path.cwd().resolve(),
        )
        self.snippet_extractor = SnippetExtractor(
            workspace_root=self.formatter.get_workspace_root(),
            space_manager=self.space_manager,
        )

        self.pipeline = IndexingPipeline(
            space_manager=self.space_manager,
            bundler=self.bundler,
            scanner=self.scanner,
            tokenizer=self.tokenizer,
            bm25_engine=self.bm25_engine,
            embedding_service=self.embedding_service,
            hybrid_engine=self.hybrid_engine,
            snippet_extractor=self.snippet_extractor,
            config=self.config,
        )

    @property
    def storage_dir(self) -> Path:
        return self.space_manager.storage_dir

    # ----------------------------------------------------------------------
    # 路徑與 Markdown 標籤轉譯委派 (委派 ResultFormatter)
    # ----------------------------------------------------------------------

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
    # 呈現層格式化輸出委派
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
    # 索引流水線委派 (建置、清理)
    # ----------------------------------------------------------------------

    def build_unified_index(
        self,
        force: bool = False,
        current_files: Optional[Dict[str, Any]] = None,
        interactive: bool = False,
        progress_callback: Optional[Any] = None,
    ) -> InvertedIndex:
        return self.pipeline.build_unified_index(
            force=force,
            current_files=current_files,
            interactive=interactive,
            progress_callback=progress_callback,
        )

    def build_index(
        self,
        space: Optional[str] = None,
        force: bool = False,
        interactive: bool = False,
        export_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, InvertedIndex]:
        if export_path:
            self.bundle(space=space, export_path=export_path)
        return self.pipeline.build_index(space=space, force=force, interactive=interactive)

    def clean(self, space: Optional[str] = None) -> None:
        self.pipeline.clean(space=space)

    # ----------------------------------------------------------------------
    # 生命週期與空間操作
    # ----------------------------------------------------------------------

    def status(
        self,
        space: Optional[str] = None,
        scan: bool = False,
        force_scan: bool = False,
    ) -> Dict[str, Any]:
        """獲取全系統空間、指紋快取、全域倒排索引與向量快取統計摘要。"""
        spaces = self.space_manager.load_spaces()
        if space is not None:
            sp = self.space_manager.get_space(space)
            spaces = {sp.name: sp}
        indices_dir = self.pipeline.get_indices_dir()

        bin_unified = indices_dir / "unified.index.bin.gz"
        has_unified_index = bin_unified.exists()
        bin_vectors = indices_dir / "unified.vectors.bin.gz"
        has_vector_index = bin_vectors.exists()
        meta_bin = indices_dir / "unified.meta.bin"
        cached_snapshot = BinarySnapshotManager.load(meta_bin) if meta_bin.exists() else None

        space_details = {}
        for sp_name, sp in spaces.items():
            if cached_snapshot:
                cached_files = sum(
                    1 for p in cached_snapshot
                    if self.scanner._file_belongs_to_space(p, sp)
                )
            else:
                cached_files = 0

            bin_idx = indices_dir / f"{sp_name}.index.bin.gz"
            has_index = bin_idx.exists() or has_unified_index

            space_details[sp_name] = {
                "origin": sp.origin,
                "description": sp.description,
                "include": sp.include,
                "exclude": sp.exclude,
                "include_count": len(sp.include),
                "file_patterns": sp.file_patterns,
                "cached_files": cached_files,
                "has_index": has_index,
            }

        scan_diff = None
        if scan:
            scan_diff = self.scan(space=space, force=force_scan)

        return {
            "total_spaces": len(spaces),
            "spaces": space_details,
            "has_unified_index": has_unified_index,
            "has_vector_index": has_vector_index,
            "enable_vector_search": getattr(self.config, "enable_vector_search", True),
            "embedding_model": getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5"),
            "model_downloaded": self.embedding_service.is_model_downloaded(),
            "storage_dir": str(self.storage_dir),
            "scan_diff": scan_diff,
        }

    def model_status(self) -> Dict[str, Any]:
        """獲取當前向量推論模型狀態清冊。"""
        return {
            "model_name": self.embedding_service.model_name,
            "cache_dir": str(self.embedding_service.cache_dir),
            "is_downloaded": self.embedding_service.is_model_downloaded(),
            "is_available": self.embedding_service.is_available,
            "dimension": self.embedding_service.dimension,
            "enable_vector_search": getattr(self.config, "enable_vector_search", True),
        }

    def model_download(self, force: bool = False) -> bool:
        """顯式下載或預熱向量模型權重。"""
        return self.embedding_service.download_model(force=force)

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
    ) -> List[SemanticBundle]:
        """執行空間符號提取與 SemanticBundle 導出。"""
        targets = [self.space_manager.get_space(space)] if space is not None else self.space_manager.list_spaces()
        bundles = []
        for sp in targets:
            b = self.bundler.bundle_space(sp)
            self.bundler.export_bundle(b, target_path=export_path)
            bundles.append(b)
        return bundles

    # ----------------------------------------------------------------------
    # 符號搜尋與拓撲分析正統入口
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

    def callers(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """查詢特定目標符號的上游調用者清單與調用點"""
        return self.pipeline.callers(target_query, space=space, snippet=snippet, ftypes=ftypes)

    def callees(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """查詢特定目標符號內部調用的下游依賴清單"""
        return self.pipeline.callees(target_query, space=space, snippet=snippet, ftypes=ftypes)

    def impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[str] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """查詢特定目標符號的向上擴散調用影響面拓撲"""
        return self.pipeline.impact(target_query, depth=depth, space=space, ftypes=ftypes)

    @classmethod
    def pre_warm(cls, workspace_root: Optional[Union[str, Path]] = None) -> None:
        """響應 server_worker_warming 事件，預熱 FastEmbed 模型與索引快取。"""
        try:
            logger.info("Pre-warming knowledge-db engine...")
            engine = get_engine()
            engine.pipeline._ensure_indices_loaded(load_graph=True, load_vectors=True)
            if hasattr(engine, "embedding_service") and engine.embedding_service:
                if not getattr(engine.embedding_service, "mock_mode", False):
                    engine.embedding_service._ensure_model()
            logger.info("Knowledge-db engine pre-warmed successfully.")
        except Exception as e:
            logger.warning(f"Knowledge-db engine pre-warm warning: {e}")


_GLOBAL_ENGINE_INSTANCE: Optional[KnowledgeEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> KnowledgeEngine:
    """取得進程級唯一 KnowledgeEngine 單例，惰性初始化並全域複用。"""
    global _GLOBAL_ENGINE_INSTANCE
    if _GLOBAL_ENGINE_INSTANCE is None:
        with _ENGINE_LOCK:
            if _GLOBAL_ENGINE_INSTANCE is None:
                _GLOBAL_ENGINE_INSTANCE = KnowledgeEngine()
    else:
        try:
            from .config import KnowledgeDBConfig
            _GLOBAL_ENGINE_INSTANCE.config = KnowledgeDBConfig.load()
            _GLOBAL_ENGINE_INSTANCE.pipeline.config = _GLOBAL_ENGINE_INSTANCE.config
        except Exception:
            pass
    return _GLOBAL_ENGINE_INSTANCE
