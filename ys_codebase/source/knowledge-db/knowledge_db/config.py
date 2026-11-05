"""
Configuration Loader for Knowledge-DB (`KnowledgeDBConfig`).

Provides multi-layer config merging (`local` > `project` > defaults),
thread budget resolution, and embedding model name normalization.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

MODEL_SPECS: Dict[str, Dict[str, Any]] = {
    "BAAI/bge-small-zh-v1.5": {"dim": 512, "max_length": 512},
    "bge-small-zh-v1.5": {"dim": 512, "max_length": 512},
    "BAAI/bge-small-en-v1.5": {"dim": 384, "max_length": 512},
    "bge-small-en-v1.5": {"dim": 384, "max_length": 512},
    "sentence-transformers/all-MiniLM-L6-v2": {"dim": 384, "max_length": 256},
    "all-MiniLM-L6-v2": {"dim": 384, "max_length": 256},
}

MODEL_SHORT_NAME_ALIASES: Dict[str, str] = {
    "bge-small-zh-v1.5": "BAAI/bge-small-zh-v1.5",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
}


def is_agents_workflow_installed() -> bool:
    """檢查當前環境是否已安裝 agents-workflow 模組 (用於判定是否注入 AI Agent 專屬導引提示)。"""
    try:
        from core.uri import resolve
        resolved = resolve("module://agents-workflow", interactive=False)
        if resolved and Path(resolved).exists():
            return True
        proj_res = resolve("project://", interactive=False)
        if proj_res:
            cand = Path(proj_res) / ".modules" / "agents-workflow"
            if cand.exists():
                return True
    except Exception:
        pass
    return False


def normalize_model_name(name: str) -> str:
    """Normalize short model names to HuggingFace / FastEmbed canonical names."""
    if not name or not str(name).strip():
        return DEFAULT_EMBEDDING_MODEL
    cleaned = str(name).strip()
    return MODEL_SHORT_NAME_ALIASES.get(cleaned, cleaned)


def resolve_threads(explicit_threads: Optional[Union[int, str]] = None) -> int:
    """Resolve CPU thread budget for ONNX/indexing operations (`0` or `'auto'` -> `min(4, max(1, cpu_count // 2))`)."""
    cpu_cnt = os.cpu_count() or 1
    auto_threads = max(1, min(4, cpu_cnt // 2))
    target: Any = explicit_threads
    if target is None:
        try:
            cfg = KnowledgeDBConfig.load()
            target = cfg.max_threads
        except Exception:
            return auto_threads

    if isinstance(target, str):
        val_str = target.strip().lower()
        if val_str in ("auto", "0", ""):
            return auto_threads
        try:
            val = int(val_str)
            if val > 0:
                return max(1, min(val, cpu_cnt))
            return auto_threads
        except ValueError:
            return auto_threads
    elif isinstance(target, (int, float)):
        val = int(target)
        if val > 0:
            return max(1, min(val, cpu_cnt))
        return auto_threads
    return auto_threads


@dataclass
class KnowledgeDBConfig:
    """
    Knowledge-DB runtime configuration.
    """

    enable_vector_search: bool = True
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    jit_vector_timeout_ms: int = 3000
    vector_batch_size: int = 32
    max_threads: Any = 0

    def __init__(
        self,
        enable_vector_search: bool = True,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        jit_vector_timeout_ms: Optional[int] = None,
        jit_vector_timeout_seconds: Optional[float] = None,
        vector_batch_size: int = 32,
        max_threads: Any = 0,
    ) -> None:
        self.enable_vector_search = bool(enable_vector_search)
        self.embedding_model = str(embedding_model or DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL
        if jit_vector_timeout_ms is not None:
            self.jit_vector_timeout_ms = max(0, int(jit_vector_timeout_ms))
        elif jit_vector_timeout_seconds is not None:
            self.jit_vector_timeout_ms = max(0, int(round(float(jit_vector_timeout_seconds) * 1000.0)))
        else:
            self.jit_vector_timeout_ms = 3000
        self.vector_batch_size = max(1, int(vector_batch_size)) if vector_batch_size else 32
        self.max_threads = max_threads

    @property
    def jit_vector_timeout_seconds(self) -> float:
        """Read/write compatibility property converting milliseconds to seconds."""
        return float(self.jit_vector_timeout_ms) / 1000.0

    @jit_vector_timeout_seconds.setter
    def jit_vector_timeout_seconds(self, value: float) -> None:
        self.jit_vector_timeout_ms = max(0, int(round(float(value) * 1000.0)))

    @staticmethod
    def normalize_model_name(name: Optional[str]) -> str:
        """Normalize short model names to HuggingFace / FastEmbed canonical names."""
        return normalize_model_name(name or DEFAULT_EMBEDDING_MODEL)

    def resolve_threads(self, explicit_threads: Optional[Union[int, str]] = None) -> int:
        """Resolve effective thread count (`0` or `'auto'` -> `min(4, max(1, cpu_count // 2))`)."""
        return resolve_threads(explicit_threads if explicit_threads is not None else self.max_threads)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDBConfig":
        """Construct KnowledgeDBConfig from a raw dictionary."""
        if not isinstance(data, dict):
            return cls()

        sec = data.get("knowledge-db", data.get("knowledge_db", data))
        if not isinstance(sec, dict):
            sec = data

        enable_vec = sec.get("enable_vector_search", True)
        if not isinstance(enable_vec, bool):
            enable_vec = str(enable_vec).lower() not in ("false", "0", "no", "off")

        model = str(sec.get("embedding_model", DEFAULT_EMBEDDING_MODEL)).strip() or DEFAULT_EMBEDDING_MODEL

        timeout_ms = 3000
        if "jit_vector_timeout_ms" in sec and sec["jit_vector_timeout_ms"] is not None:
            try:
                timeout_ms = int(float(sec["jit_vector_timeout_ms"]))
            except (TypeError, ValueError):
                timeout_ms = 3000
        elif "jit_vector_timeout_seconds" in sec and sec["jit_vector_timeout_seconds"] is not None:
            try:
                timeout_ms = int(round(float(sec["jit_vector_timeout_seconds"]) * 1000.0))
            except (TypeError, ValueError):
                timeout_ms = 3000

        batch_size = 32
        if "vector_batch_size" in sec and sec["vector_batch_size"] is not None:
            try:
                batch_size = max(1, int(sec["vector_batch_size"]))
            except (TypeError, ValueError):
                batch_size = 32

        try:
            threads = int(sec.get("max_threads", 0))
        except (TypeError, ValueError):
            threads = 0

        return cls(
            enable_vector_search=enable_vec,
            embedding_model=model,
            jit_vector_timeout_ms=max(0, timeout_ms),
            vector_batch_size=batch_size,
            max_threads=max(0, threads),
        )

    @classmethod
    def load(
        cls,
        project_config: Optional[Dict[str, Any]] = None,
        local_config: Optional[Dict[str, Any]] = None,
    ) -> "KnowledgeDBConfig":
        """Load configuration with precedence: `local` > `project` > defaults."""
        merged: Dict[str, Any] = {}

        if project_config is None and local_config is None:
            try:
                import core.config as core_cfg_mod
                cfg_cls = getattr(core_cfg_mod, "ConfigManager", None)
                if cfg_cls is not None:
                    mgr = cfg_cls()
                    if hasattr(mgr, "get"):
                        val = mgr.get("knowledge-db")
                        if isinstance(val, dict):
                            return cls.from_dict(val)
            except Exception:
                pass

            for uri_str in ("config://knowledge-db/config.project.json", "config.local://knowledge-db/config.local.json"):
                p = cls._resolve_config_uri(uri_str)
                if p and p.exists():
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        if isinstance(raw, dict):
                            sec = raw.get("knowledge-db", raw.get("knowledge_db", {}))
                            if isinstance(sec, dict):
                                merged.update(sec)
                    except Exception:
                        pass
            return cls.from_dict(merged)

        if isinstance(project_config, dict):
            sec = project_config.get("knowledge-db", project_config.get("knowledge_db", project_config))
            if isinstance(sec, dict):
                merged.update(sec)

        if isinstance(local_config, dict):
            sec = local_config.get("knowledge-db", local_config.get("knowledge_db", local_config))
            if isinstance(sec, dict):
                merged.update(sec)

        return cls.from_dict(merged)

    @staticmethod
    def _resolve_config_uri(uri_str: str) -> Optional[Path]:
        try:
            from core.uri import resolve
            res = resolve(uri_str)
            if res:
                return Path(res)
        except Exception:
            pass
        return None
