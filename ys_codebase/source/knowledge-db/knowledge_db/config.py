"""
Configuration loader and schema for module:knowledge-db.
"""

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_ENABLE_VECTOR_SEARCH: bool = True
DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
DEFAULT_JIT_VECTOR_TIMEOUT_SECONDS: float = 5.0
DEFAULT_MAX_THREADS: str = "auto"


@dataclass
class KnowledgeDBConfig:
    enable_vector_search: bool = DEFAULT_ENABLE_VECTOR_SEARCH
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    jit_vector_timeout_seconds: float = DEFAULT_JIT_VECTOR_TIMEOUT_SECONDS
    max_threads: Union[str, int] = DEFAULT_MAX_THREADS

    @classmethod
    def load(
        cls,
        workspace_root: Optional[Union[str, Path]] = None,
        local_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        project_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
    ) -> "KnowledgeDBConfig":
        """
        載入 knowledge-db 專用組態。
        遵循四階層優先級：
        1. core.config (config://knowledge-db/config.local.json 優先於 config.project.json)
        2. yscb.config.local.json 中的 "knowledge-db" 區塊
        3. yscb.config.json 中的 "knowledge-db" 區塊
        4. 傳入之 local_config / project_config
        5. 內建預設值
        """
        root_path = Path(workspace_root) if workspace_root else Path(cls._find_workspace_root())

        merged_data: Dict[str, Any] = {}

        # 1. 嘗試透過 core.config 載入
        try:
            from core.config import Config
            core_cfg = Config.get_all("knowledge-db")
            if isinstance(core_cfg, dict):
                merged_data.update(core_cfg)
        except Exception:
            pass

        # 2. 搜尋實體目錄之 yscb.config.json 與 yscb.config.local.json
        for fname in ["yscb.config.json", "yscb.config.local.json"]:
            p = root_path / fname
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict):
                        kdb_sec = raw.get("knowledge-db")
                        if isinstance(kdb_sec, dict):
                            merged_data.update(kdb_sec)
                except Exception as e:
                    logger.debug(f"Failed to read {fname}: {e}")

        # 3. 支援外部傳入之 project_config 與 local_config
        def _parse_cfg_input(cfg_in: Any) -> Dict[str, Any]:
            if isinstance(cfg_in, dict):
                return cfg_in.get("knowledge-db", cfg_in)
            elif isinstance(cfg_in, (str, Path)):
                p = Path(cfg_in)
                if p.is_file():
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            return data.get("knowledge-db", data)
            return {}

        if project_config:
            merged_data.update(_parse_cfg_input(project_config))
        if local_config:
            merged_data.update(_parse_cfg_input(local_config))

        # 3. 解析型態防禦
        enable_vec = merged_data.get("enable_vector_search", DEFAULT_ENABLE_VECTOR_SEARCH)
        if isinstance(enable_vec, str):
            enable_vec = enable_vec.strip().lower() not in ("false", "0", "no", "off")
        else:
            enable_vec = bool(enable_vec)

        model_name = str(merged_data.get("embedding_model") or DEFAULT_EMBEDDING_MODEL).strip()
        if not model_name:
            model_name = DEFAULT_EMBEDDING_MODEL

        timeout_val = merged_data.get("jit_vector_timeout_seconds", DEFAULT_JIT_VECTOR_TIMEOUT_SECONDS)
        try:
            timeout_sec = float(timeout_val)
            if timeout_sec < 0:
                timeout_sec = DEFAULT_JIT_VECTOR_TIMEOUT_SECONDS
        except (ValueError, TypeError):
            timeout_sec = DEFAULT_JIT_VECTOR_TIMEOUT_SECONDS

        threads_val = merged_data.get("max_threads", DEFAULT_MAX_THREADS)
        if isinstance(threads_val, str):
            threads_val = threads_val.strip()
            if threads_val.isdigit():
                threads_val = int(threads_val)
        elif isinstance(threads_val, (int, float)):
            threads_val = int(threads_val)
        else:
            threads_val = DEFAULT_MAX_THREADS

        return cls(
            enable_vector_search=enable_vec,
            embedding_model=model_name,
            jit_vector_timeout_seconds=timeout_sec,
            max_threads=threads_val,
        )

    def resolve_threads(self) -> int:
        """解析 max_threads：auto 時返回 max(1, cpu_count // 2)，若 <= 0 亦回退至 auto，手動正整數截斷於 [1, cpu_count]"""
        cpu_cnt = os.cpu_count() or 1
        auto_threads = max(1, cpu_cnt // 2)
        if isinstance(self.max_threads, str):
            if self.max_threads.lower() == "auto":
                return auto_threads
            try:
                val = int(self.max_threads)
                if val <= 0:
                    return auto_threads
                return max(1, min(val, cpu_cnt))
            except ValueError:
                return auto_threads
        elif isinstance(self.max_threads, int):
            if self.max_threads <= 0:
                return auto_threads
            return max(1, min(self.max_threads, cpu_cnt))
        return auto_threads

    @staticmethod
    def _find_workspace_root() -> str:
        cur = Path.cwd().resolve()
        for p in [cur] + list(cur.parents):
            if (p / "yscb.py").is_file() or (p / "yscb.config.json").is_file():
                return str(p)
        return str(cur)
