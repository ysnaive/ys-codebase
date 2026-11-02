"""
knowledge-db 統一門面 SDK (engine.py)
整合空間治理、雙階指紋比對、多語言解析、語意打包、BM25 檢索與二進位 Gzip 快取中心。
採用 Pipeline、TopologyQueryService 與 ResultFormatter 解耦架構。
"""

import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Union

from file_space import (
    FingerprintScanner,
    InvalidFileSpaceConfigError,
    FileSpaceConfig,
    FileSpaceManager,
    FileSpaceNotFoundError,
    consume_diff,
    reset_cursor,
)

from .bundler import SemanticBundle, SemanticBundler, _resolve_default_knowledge_storage_dir
from .embedding import EmbeddingService
from .exceptions import InvalidConfigError
from .formatter import ResultFormatter
from .hybrid import HybridSearchEngine
from .parsers.registry import ParserRegistry
from .pipeline import IndexingPipeline
from .retrieval import BM25Engine, InvertedIndex, SearchResult, SnippetExtractor
from .schema import AggregatedFileResult, validate_space_weights
from .service import (
    KnowledgeDBServiceWorker,
    get_worker_busy_ms,
    is_worker_running,
    read_worker_state,
    wait_until_worker_idle,
)
from .tokenizer import MultilingualTokenizer

logger = logging.getLogger("knowledge-db.engine")


class KnowledgeEngine:
    """
    knowledge-db 模組頂層統一門面 Facade SDK。
    提供一站式呼叫空間狀態查詢、語意打包、倒排索引建置、語意檢索與快取清理。
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
        project_root: Optional[Union[str, Path]] = None,
        custom_spaces: Optional[Dict[str, Any]] = None,
        space_weights: Optional[Dict[str, float]] = None,
        space_manager: Optional[FileSpaceManager] = None,
        core_context: Optional[Any] = None,
    ):
        proj_root_path = Path(project_root).resolve() if project_root is not None else None
        if storage_dir is not None:
            self._storage_dir = Path(storage_dir).resolve()
            space_storage_dir: Optional[Path] = self._storage_dir / "file-space"
        else:
            self._storage_dir = _resolve_default_knowledge_storage_dir(proj_root_path)
            space_storage_dir = None

        self._storage_dir.mkdir(parents=True, exist_ok=True)

        merged_contributes = dict(contributes_data) if isinstance(contributes_data, dict) else None
        if custom_spaces is not None:
            if merged_contributes is None:
                merged_contributes = {"spaces": dict(custom_spaces)}
            else:
                merged_spaces = dict(merged_contributes.get("spaces", {}))
                merged_spaces.update(custom_spaces)
                merged_contributes["spaces"] = merged_spaces

        if space_manager is not None:
            self.space_manager = space_manager
        else:
            self.space_manager = FileSpaceManager(
                project_root=proj_root_path,
                config_dir=config_dir,
                storage_dir=space_storage_dir,
                contributes_data=merged_contributes,
                core_context=core_context,
            )

        self.space_weights: Dict[str, float] = self._load_and_merge_space_weights(
            config_dir=config_dir,
            contributes_data=merged_contributes,
            custom_spaces=custom_spaces,
            explicit_weights=space_weights,
            core_context=core_context,
        )

        self.tokenizer = MultilingualTokenizer()
        self.parser_registry = ParserRegistry()
        self.scanner = FingerprintScanner(self.space_manager)
        self.bundler = SemanticBundler(
            space_manager=self.space_manager,
            parser_registry=self.parser_registry,
            scanner=self.scanner,
            storage_dir=self._storage_dir,
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

        models_dir = self._storage_dir / "models"
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
            space_weights=self.space_weights,
        )
        workspace_root = proj_root_path or getattr(self.space_manager, "project_root", None) or Path.cwd().resolve()
        self.formatter = ResultFormatter(
            workspace_root=workspace_root,
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
            storage_dir=self._storage_dir,
            space_weights_provider=self.get_all_space_weights,
        )

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    def _load_and_merge_space_weights(
        self,
        config_dir: Optional[Union[str, Path]] = None,
        contributes_data: Optional[Dict[str, Any]] = None,
        custom_spaces: Optional[Dict[str, Any]] = None,
        explicit_weights: Optional[Dict[str, float]] = None,
        core_context: Optional[Any] = None,
    ) -> Dict[str, float]:
        """載入並合併各層級之空間檢索加權係數 (`space_weights`)"""
        weights: Dict[str, float] = {}

        # 1. 從 space_manager 已註冊空間提取基礎預設權重
        try:
            for sp_name, sp_cfg in self.space_manager.load_spaces().items():
                if hasattr(sp_cfg, "weight") and sp_cfg.weight is not None:
                    weights[sp_name] = float(sp_cfg.weight)
        except (InvalidFileSpaceConfigError, InvalidConfigError):
            raise
        except Exception:
            pass

        # 2. 從模組生態系 contributes.get("knowledge-db") 提取
        if contributes_data is None:
            try:
                from core import contributes as core_contributes
                raw_merged = core_contributes.get("knowledge-db")
                if isinstance(raw_merged, dict):
                    if isinstance(raw_merged.get("space_weights"), dict):
                        sw_clean = {
                            k: v for k, v in raw_merged["space_weights"].items()
                            if not str(k).startswith("_")
                        }
                        if sw_clean:
                            weights.update(validate_space_weights(sw_clean))
                elif isinstance(raw_merged, list):
                    for item in raw_merged:
                        data = item.get("data", item) if isinstance(item, dict) else {}
                        if isinstance(data, dict) and "space_weights" in data:
                            weights.update(validate_space_weights(data["space_weights"]))
            except (InvalidFileSpaceConfigError, InvalidConfigError):
                raise
            except Exception:
                pass

        # 3. 從專案或測試傳入之 config_dir / config://knowledge-db/contribute.json 提取
        cfg_candidates: List[Path] = []
        if config_dir is not None:
            cfg_dir_path = Path(config_dir).resolve()
            cfg_candidates.append(cfg_dir_path / "contribute.json")
            cfg_candidates.append(cfg_dir_path / "knowledge-db" / "contribute.json")
        else:
            try:
                from core import uri
                res = uri.resolve("config://knowledge-db/contribute.json", interactive=False)
                if res:
                    cfg_candidates.append(Path(res).resolve())
            except Exception:
                pass

        for cfg_file in cfg_candidates:
            if cfg_file.is_file():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        file_data = json.load(f)
                    if isinstance(file_data, dict):
                        if "space_weights" in file_data:
                            weights.update(validate_space_weights(file_data["space_weights"]))
                        if isinstance(file_data.get("spaces"), dict):
                            for s_name, s_val in file_data["spaces"].items():
                                if isinstance(s_val, dict) and "weight" in s_val and s_val["weight"] is not None:
                                    weights.update(validate_space_weights({s_name: s_val["weight"]}))
                except (InvalidFileSpaceConfigError, InvalidConfigError):
                    raise
                except Exception:
                    pass

        # 4. 從傳入之 contributes_data / custom_spaces / explicit_weights 提取覆寫
        for raw_dict in (contributes_data, {"spaces": custom_spaces} if custom_spaces else None):
            if isinstance(raw_dict, dict):
                if isinstance(raw_dict.get("spaces"), dict):
                    for s_name, s_val in raw_dict["spaces"].items():
                        if isinstance(s_val, FileSpaceConfig):
                            weights.update(validate_space_weights({s_name: s_val.weight}))
                        elif isinstance(s_val, dict) and "weight" in s_val and s_val["weight"] is not None:
                            weights.update(validate_space_weights({s_name: s_val["weight"]}))
                if "space_weights" in raw_dict and raw_dict["space_weights"] is not None:
                    weights.update(validate_space_weights(raw_dict["space_weights"]))

        if explicit_weights is not None:
            weights.update(validate_space_weights(explicit_weights))

        return weights

    def get_space_weight(self, space_name: str) -> float:
        """取得指定邏輯空間之檢索加權係數（預設為 1.0）"""
        if space_name in self.space_weights:
            return float(self.space_weights[space_name])
        try:
            sp = self.space_manager.get_space(space_name)
            if hasattr(sp, "weight") and sp.weight is not None:
                return float(sp.weight)
        except Exception:
            pass
        return 1.0

    def get_all_space_weights(self) -> Dict[str, float]:
        """獲取當前所有空間之檢索加權係數映射表"""
        result = dict(self.space_weights)
        try:
            for sp_name, sp_cfg in self.space_manager.load_spaces().items():
                if sp_name not in result:
                    result[sp_name] = float(getattr(sp_cfg, "weight", 1.0))
        except Exception:
            pass
        return result

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
        try:
            self.scanner.reset_cursor(space_name=space, consumer_id="knowledge-db")
        except Exception:
            pass
        try:
            reset_cursor(space_name=space, consumer_id="knowledge-db")
        except Exception:
            pass

    # ----------------------------------------------------------------------
    # 生命週期與空間操作
    # ----------------------------------------------------------------------

    def is_worker_busy(self) -> int:
        """
        回傳後台 Worker 當前連續忙碌之已運行毫秒數 (`int`, 單位 `ms`)。
        `0` 代表空閒（或 Worker 未運行）；`> 0` 代表已忙碌 `elapsed_ms` 毫秒。
        """
        return get_worker_busy_ms(self.pipeline.get_indices_dir())

    def wait_for_worker_idle(self, timeout_ms: Optional[int] = None) -> bool:
        """等待後台 Worker 轉為空閒，最多等待 `timeout_ms` 毫秒（預設取 `config.jit_vector_timeout_ms`）。"""
        budget = int(timeout_ms if timeout_ms is not None else getattr(self.config, "jit_vector_timeout_ms", 3000))
        return wait_until_worker_idle(self.pipeline.get_indices_dir(), budget)

    def sync_vector_deficit_step(self, batch_size: Optional[int] = None) -> Dict[str, int]:
        """執行單步微批次向量差集自癒，供背景 Worker 或測試呼叫。"""
        b_size = int(batch_size if batch_size is not None else getattr(self.config, "vector_batch_size", 32))
        return self.pipeline.sync_vector_deficit_step(batch_size=b_size)

    def status(
        self,
        space: Optional[str] = None,
    ) -> Dict[str, Any]:
        """獲取全系統空間、後台 Worker、三大核心索引、檢索模式、組態與空間游標同步詳盡統計摘要。"""
        spaces = self.space_manager.load_spaces()
        if space is not None:
            if space not in spaces:
                raise FileSpaceNotFoundError(space, list(spaces.keys()))
            sp = spaces[space]
            spaces = {sp.name: sp}
        indices_dir = self.pipeline.get_indices_dir()

        bin_unified = indices_dir / "unified.index.bin.gz"
        has_unified_index = bin_unified.exists()
        bin_graph = indices_dir / "unified.graph.bin.gz"
        has_graph_index = bin_graph.exists()
        bin_vectors = indices_dir / "unified.vectors.bin.gz"
        has_vector_index = bin_vectors.exists()

        # 載入最新磁碟索引至記憶體以便提取精確統計指標
        try:
            self.pipeline._ensure_indices_loaded(
                load_graph=has_graph_index,
                load_vectors=has_vector_index,
            )
        except Exception:
            pass

        unified_idx = self.pipeline.unified_index
        graph_idx = self.pipeline.call_graph_index
        vec_idx = getattr(self.hybrid_engine, "vector_index", None)

        symbol_count = int(getattr(unified_idx, "doc_count", 0) or (len(unified_idx.symbols) if unified_idx else 0))
        term_count = len(unified_idx.index) if (unified_idx and hasattr(unified_idx, "index")) else 0
        unified_size_kb = round(bin_unified.stat().st_size / 1024.0, 1) if has_unified_index else 0.0
        unified_mtime = round(bin_unified.stat().st_mtime, 2) if has_unified_index else None

        graph_nodes = 0
        graph_edges = 0
        if graph_idx is not None:
            nx_g = getattr(graph_idx, "graph", None)
            if nx_g is not None and hasattr(nx_g, "number_of_nodes"):
                graph_nodes = int(nx_g.number_of_nodes())
                graph_edges = int(nx_g.number_of_edges())
            else:
                out_map = getattr(graph_idx, "outgoing", {}) or {}
                in_map = getattr(graph_idx, "incoming", {}) or {}
                graph_nodes = len(set(out_map.keys()) | set(in_map.keys()))
                graph_edges = sum(len(v) for v in out_map.values())
        graph_size_kb = round(bin_graph.stat().st_size / 1024.0, 1) if has_graph_index else 0.0
        graph_mtime = round(bin_graph.stat().st_mtime, 2) if has_graph_index else None

        worker_st = read_worker_state(indices_dir)
        worker_running = is_worker_running(indices_dir)
        busy_ms = self.is_worker_busy()
        worker_phase = str(worker_st.get("phase", "idle") or "idle")
        worker_progress = str(worker_st.get("progress", "") or "")
        if hasattr(self, "embedding_service") and self.embedding_service is not None:
            self.embedding_service.suppress_guard_prompt = bool(worker_running)

        vec_deficit = self.pipeline.get_vector_deficit_info()
        embedded_count = int(vec_deficit.get("embedded_count", 0))
        missing_vectors = int(vec_deficit.get("missing_count", 0))
        stale_vectors = int(vec_deficit.get("stale_count", 0))
        coverage_pct = float(vec_deficit.get("coverage_pct", 0.0))
        vec_compatible = bool(vec_deficit.get("compatible", False))
        vec_size_kb = round(bin_vectors.stat().st_size / 1024.0, 1) if has_vector_index else 0.0
        vec_mtime = round(bin_vectors.stat().st_mtime, 2) if has_vector_index else None
        model_name = getattr(self.config, "embedding_model", "BAAI/bge-small-zh-v1.5")
        model_downloaded = bool(self.embedding_service.is_model_downloaded())
        if getattr(vec_idx, "dim", None):
            vec_dim = int(vec_idx.dim)
        elif model_downloaded or getattr(self.embedding_service, "mock_mode", False):
            vec_dim = int(self.embedding_service.dimension)
        else:
            vec_dim = int(self.embedding_service._resolve_dimension_mock())
        enable_vec = bool(getattr(self.config, "enable_vector_search", True))
        timeout_ms = int(getattr(self.config, "jit_vector_timeout_ms", 3000))
        batch_size = int(getattr(self.config, "vector_batch_size", 32))
        resolved_threads = int(self.config.resolve_threads())

        if not enable_vec:
            vec_status_label = "disabled"
            retrieval_mode = "lexical_bm25"
            retrieval_reason = "已於組態關閉向量檢索 (enable_vector_search=false)"
        elif busy_ms > 0:
            vec_status_label = "syncing"
            if busy_ms >= timeout_ms:
                retrieval_mode = "lexical_bm25"
                retrieval_reason = f"後台向量更新已運行 {busy_ms}ms (>= {timeout_ms}ms)，前台瞬時降級純 BM25"
            else:
                retrieval_mode = "hybrid_rrf (pending_worker)"
                retrieval_reason = f"後台更新中 (已運行 {busy_ms}ms)，前台搜尋最多容差等待 {timeout_ms - busy_ms}ms"
        elif not model_downloaded and not getattr(self.embedding_service, "mock_mode", False):
            vec_status_label = "missing_model"
            retrieval_mode = "lexical_bm25"
            retrieval_reason = (
                "本地缺少向量模型權重 (後台 Worker 將自動下載)"
                if worker_running
                else "本地缺少向量模型權重，已降級純 BM25"
            )
        elif not has_vector_index or embedded_count == 0:
            vec_status_label = "missing"
            retrieval_mode = "lexical_bm25"
            retrieval_reason = "向量索引尚未建立，暫以純 BM25 檢索"
        elif not vec_compatible:
            vec_status_label = "incompatible"
            retrieval_mode = "lexical_bm25"
            retrieval_reason = "向量索引與當前模型/維度不相容，待重建"
        elif missing_vectors > 0:
            vec_status_label = "partial"
            retrieval_mode = "hybrid_rrf"
            retrieval_reason = f"BM25 + 向量 RRF 混合檢索就緒 (向量覆蓋率 {coverage_pct}%，待補 {missing_vectors} 符號)"
        else:
            vec_status_label = "ready"
            retrieval_mode = "hybrid_rrf"
            retrieval_reason = "BM25 + 向量 RRF 混合檢索 100% 就緒"

        space_details = {}
        for sp_name, sp in spaces.items():
            try:
                file_count = sum(1 for _ in self.space_manager.iter_space_files(sp_name))
            except Exception:
                file_count = 0

            bin_idx = indices_dir / f"{sp_name}.index.bin.gz"
            has_index = bin_idx.exists() or has_unified_index

            head_gen = 0
            acked_gen = 0
            in_sync = False
            try:
                snap_path = self.scanner.get_snapshot_path(sp_name)
                if snap_path.exists():
                    snap_state = self.scanner.snapshot_mgr.load_state(snap_path)
                    head_gen = int(snap_state.head_generation)
                cur_data = self.scanner.cursor_store.get_cursor(sp_name, "knowledge-db")
                acked_gen = int(cur_data.get("acked_gen", cur_data.get("acked_generation", 0)) or 0)
                in_sync = (head_gen > 0 and acked_gen == head_gen) or (file_count == 0 and head_gen == acked_gen)
            except Exception:
                pass

            space_details[sp_name] = {
                "origin": getattr(sp.origin, "value", str(sp.origin)),
                "description": sp.description,
                "include": [p.as_posix() if isinstance(p, Path) else str(p) for p in sp.include],
                "exclude": list(sp.exclude),
                "include_count": len(sp.include),
                "file_patterns": list(sp.file_patterns) if sp.file_patterns else [],
                "weight": self.get_space_weight(sp_name),
                "cached_files": file_count,
                "has_index": has_index,
                "head_generation": head_gen,
                "acked_generation": acked_gen,
                "in_sync": in_sync,
                "watch": bool(getattr(sp, "watch", False)),
                "hash_policy": getattr(getattr(sp, "hash_policy", None), "value", str(getattr(sp, "hash_policy", "adaptive"))),
            }

        lang_cfgs = getattr(self.parser_registry, "_language_configs", {})
        registered_langs = sorted(lang_cfgs.keys()) if isinstance(lang_cfgs, dict) else []

        return {
            "total_spaces": len(spaces),
            "spaces": space_details,
            "has_unified_index": has_unified_index,
            "has_graph_index": has_graph_index,
            "has_vector_index": has_vector_index,
            "enable_vector_search": enable_vec,
            "embedding_model": model_name,
            "model_downloaded": model_downloaded,
            "jit_vector_timeout_ms": timeout_ms,
            "vector_batch_size": batch_size,
            "max_threads": resolved_threads,
            "retrieval_mode": retrieval_mode,
            "retrieval_reason": retrieval_reason,
            "worker": {
                "service_id": "knowledge-db-worker",
                "running": worker_running,
                "busy": busy_ms > 0,
                "busy_elapsed_ms": busy_ms,
                "phase": worker_phase,
                "progress": worker_progress,
                "pid": int(worker_st.get("pid", 0) or 0),
            },
            "indices": {
                "bm25": {
                    "file": "unified.index.bin.gz",
                    "ready": has_unified_index,
                    "symbol_count": symbol_count,
                    "term_count": term_count,
                    "size_kb": unified_size_kb,
                    "updated_at": unified_mtime,
                },
                "graph": {
                    "file": "unified.graph.bin.gz",
                    "ready": has_graph_index,
                    "node_count": graph_nodes,
                    "edge_count": graph_edges,
                    "size_kb": graph_size_kb,
                    "updated_at": graph_mtime,
                },
                "vector": {
                    "file": "unified.vectors.bin.gz",
                    "status": vec_status_label,
                    "ready": has_vector_index and embedded_count > 0 and vec_compatible,
                    "embedded_count": embedded_count,
                    "total_symbols": symbol_count,
                    "missing_count": missing_vectors,
                    "stale_count": stale_vectors,
                    "coverage_pct": coverage_pct,
                    "dimension": vec_dim,
                    "model_name": getattr(vec_idx, "model_name", None) or model_name,
                    "compatible": vec_compatible,
                    "size_kb": vec_size_kb,
                    "updated_at": vec_mtime,
                },
            },
            "registered_languages": registered_langs,
            "storage_dir": str(self.storage_dir),
            "parser_load_errors": dict(getattr(self.parser_registry, "load_errors", {})),
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

    def bundle(
        self,
        space: Optional[str] = None,
        export_path: Optional[Union[str, Path]] = None,
    ) -> List[SemanticBundle]:
        """執行空間符號提取與 SemanticBundle 導出。"""
        if space is not None:
            targets = [self.space_manager.get_space(space)]
        else:
            targets = list(self.space_manager.load_spaces().values())
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
            enable_vec = bool(getattr(engine.config, "enable_vector_search", True))
            engine.pipeline._ensure_indices_loaded(load_graph=True, load_vectors=enable_vec)
            if enable_vec and hasattr(engine, "embedding_service") and engine.embedding_service:
                engine.embedding_service.suppress_guard_prompt = True
                if not getattr(engine.embedding_service, "mock_mode", False) and engine.embedding_service.is_model_downloaded():
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
            if getattr(_GLOBAL_ENGINE_INSTANCE.parser_registry, "load_errors", None):
                _GLOBAL_ENGINE_INSTANCE.parser_registry = ParserRegistry()
                _GLOBAL_ENGINE_INSTANCE.bundler.parser_registry = _GLOBAL_ENGINE_INSTANCE.parser_registry
        except Exception:
            pass
    return _GLOBAL_ENGINE_INSTANCE


__all__ = [
    "KnowledgeEngine",
    "KnowledgeDBServiceWorker",
    "get_engine",
    "get_worker_busy_ms",
    "is_worker_running",
    "FileSpaceManager",
    "FingerprintScanner",
    "consume_diff",
    "reset_cursor",
    "FileSpaceNotFoundError",
    "InvalidFileSpaceConfigError",
]
