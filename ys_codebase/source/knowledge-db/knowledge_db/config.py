"""
Configuration Loader for Knowledge-DB (`KnowledgeDBConfig`).

Provides multi-layer config merging (`local` > `project` > defaults),
thread budget resolution, and embedding model name normalization.
"""

import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Optional, Union

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

MODEL_SPECS: Any = MappingProxyType({
    "BAAI/bge-small-zh-v1.5": MappingProxyType({"dim": 512, "max_length": 512}),
    "bge-small-zh-v1.5": MappingProxyType({"dim": 512, "max_length": 512}),
    "BAAI/bge-small-en-v1.5": MappingProxyType({"dim": 384, "max_length": 512}),
    "bge-small-en-v1.5": MappingProxyType({"dim": 384, "max_length": 512}),
    "sentence-transformers/all-MiniLM-L6-v2": MappingProxyType({"dim": 384, "max_length": 256}),
    "all-MiniLM-L6-v2": MappingProxyType({"dim": 384, "max_length": 256}),
})

MODEL_SHORT_NAME_ALIASES: Any = MappingProxyType({
    "bge-small-zh-v1.5": "BAAI/bge-small-zh-v1.5",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
})


from core.context import get_or_compute_cell_state


def is_agents_workflow_installed() -> bool:
    """檢查當前環境是否已安裝 agents-workflow 模組 (用於判定是否注入 AI Agent 專屬導引提示)。"""

    def _probe() -> bool:
        try:
            from core import uri, vfs

            if vfs.is_dir("module://agents-workflow"):
                return True
            yscb_root = uri.resolve_yscb_root()
            if yscb_root:
                cand = Path(yscb_root).resolve() / ".modules" / "agents-workflow"
                if cand.exists():
                    return True
        except Exception:
            pass
        return False

    return bool(get_or_compute_cell_state("kdb.aw_installed", _probe))


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

    if isinstance(target, bool):
        return auto_threads

    if isinstance(target, str):
        val_str = target.strip().lower()
        if val_str in ("auto", "0", ""):
            return auto_threads
        try:
            val = int(float(val_str))
        except ValueError:
            return auto_threads
    elif isinstance(target, (int, float)):
        val = int(target)
    else:
        return auto_threads

    return max(1, min(val, cpu_cnt)) if val > 0 else auto_threads


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
        enable_vector_search: Any = True,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        jit_vector_timeout_ms: Optional[Any] = None,
        jit_vector_timeout_seconds: Optional[Any] = None,
        vector_batch_size: Any = 32,
        max_threads: Any = 0,
    ) -> None:
        if isinstance(enable_vector_search, bool):
            self.enable_vector_search = enable_vector_search
        else:
            self.enable_vector_search = str(enable_vector_search).strip().lower() not in ("false", "0", "no", "off", "")

        self.embedding_model = str(embedding_model or DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL

        timeout_ms = 3000
        if jit_vector_timeout_ms is not None and not isinstance(jit_vector_timeout_ms, bool):
            try:
                timeout_ms = int(float(jit_vector_timeout_ms))
            except (TypeError, ValueError):
                timeout_ms = 3000
        elif jit_vector_timeout_seconds is not None and not isinstance(jit_vector_timeout_seconds, bool):
            try:
                timeout_ms = int(round(float(jit_vector_timeout_seconds) * 1000.0))
            except (TypeError, ValueError):
                timeout_ms = 3000
        self.jit_vector_timeout_ms = max(0, timeout_ms)

        batch_val = 32
        if vector_batch_size is not None and not isinstance(vector_batch_size, bool):
            try:
                parsed_b = int(float(vector_batch_size))
                batch_val = max(1, parsed_b) if parsed_b > 0 else 32
            except (TypeError, ValueError):
                batch_val = 32
        self.vector_batch_size = batch_val

        if isinstance(max_threads, str) and max_threads.strip().lower() == "auto":
            self.max_threads = "auto"
        elif isinstance(max_threads, bool) or max_threads is None:
            self.max_threads = 0
        else:
            try:
                self.max_threads = max(0, int(float(max_threads)))
            except (TypeError, ValueError):
                self.max_threads = 0

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

    @staticmethod
    def _extract_config_section(source: Optional[Union[str, Path, Dict[str, Any]]]) -> Dict[str, Any]:
        """Extract configuration dictionary from a dict, Path, or JSON file path string."""
        if source is None:
            return {}
        raw: Optional[Dict[str, Any]] = None
        if isinstance(source, dict):
            raw = source
        elif isinstance(source, (str, Path)):
            p = Path(source)
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        raw = loaded
                except Exception:
                    return {}
        if not isinstance(raw, dict):
            return {}
        sec = raw.get("knowledge-db", raw.get("knowledge_db", raw))
        return dict(sec) if isinstance(sec, dict) else {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDBConfig":
        """Construct KnowledgeDBConfig from a raw dictionary."""
        sec = cls._extract_config_section(data)
        if not sec:
            return cls()
        return cls(
            enable_vector_search=sec.get("enable_vector_search", True),
            embedding_model=sec.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
            jit_vector_timeout_ms=sec.get("jit_vector_timeout_ms"),
            jit_vector_timeout_seconds=sec.get("jit_vector_timeout_seconds"),
            vector_batch_size=sec.get("vector_batch_size", 32),
            max_threads=sec.get("max_threads", 0),
        )

    @classmethod
    def load(
        cls,
        project_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
        local_config: Optional[Union[str, Path, Dict[str, Any]]] = None,
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
                    merged.update(cls._extract_config_section(p))
            return cls.from_dict(merged)

        merged.update(cls._extract_config_section(project_config))
        merged.update(cls._extract_config_section(local_config))
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
