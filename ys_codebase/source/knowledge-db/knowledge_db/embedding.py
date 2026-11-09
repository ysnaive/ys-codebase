"""
knowledge-db 輕量 ONNX 向量嵌入推論服務 (EmbeddingService)
封裝 FastEmbed 離線模型推論、快取持久化與 100% 平滑降級守門。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union
import warnings

if TYPE_CHECKING:
    import numpy as np

from core.log import log, log_debug, log_info, log_warn

from .config import DEFAULT_EMBEDDING_MODEL, MODEL_SPECS, KnowledgeDBConfig, is_agents_workflow_installed, resolve_threads
from .exceptions import KnowledgeDBError
from .io_utils import atomic_save_gzip_pickle, load_gzip_pickle

MAX_SYMBOL_DOCSTRING_EMBED_CHARS = 400


def format_symbol_embedding_text(sym: Any, max_doc_chars: int = MAX_SYMBOL_DOCSTRING_EMBED_CHARS) -> str:
    """組裝符號嵌入文本，並對超長 Docstring 施加字元上限截斷以避免無效分詞開銷。"""
    name = getattr(sym, "name", "") or ""
    sig = getattr(sym, "signature", "") or ""
    doc = getattr(sym, "docstring", "") or ""
    if max_doc_chars > 0 and len(doc) > max_doc_chars:
        doc = doc[:max_doc_chars]
    return f"{name} {sig} {doc}".strip()


class EmbeddingService:
    """
    向量推論服務：
    1. 封裝 FastEmbed (ONNX Runtime) 執行純本地離線特徵提取。
    2. 具備 100% 異常捕獲與 is_available 動態置標，保證零死鎖平滑降級。
    3. 內建 Mock 模式，供沙盒與單元測試環境極速離線驗證。
    4. 統一以實際加載之模型實例屬性為維度唯一真理來源 (SSOT)。
    """

    @classmethod
    def normalize_model_name(cls, model_name: Optional[str]) -> str:
        """委派至 KnowledgeDBConfig.normalize_model_name"""
        return KnowledgeDBConfig.normalize_model_name(model_name)

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Optional[Union[str, Path]] = None,
        max_threads: Optional[Union[str, int]] = None,
        mock_mode: bool = False,
        enable_vector_search: bool = True,
    ):
        self.model_name = self.normalize_model_name(model_name)
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            from .pipeline import _resolve_default_knowledge_storage_dir

            self.cache_dir = _resolve_default_knowledge_storage_dir() / "models"
        self.max_threads = max_threads or "auto"
        self.mock_mode = mock_mode
        self.enable_vector_search = enable_vector_search
        self._model: Optional[Any] = None
        self._is_available: bool = False
        self._verified_onnx_path: Optional[Path] = None
        self._init_attempted: bool = False
        self._init_lock = threading.RLock()
        self._dimension: Optional[int] = None
        self.last_error: Optional[Dict[str, Any]] = None
        self.suppress_guard_prompt: bool = False
        self._suppress_hf_warnings()
        if self.mock_mode:
            self._is_available = True
            self._init_attempted = True
            self._resolve_dimension_mock()

    @staticmethod
    def _suppress_hf_warnings() -> None:
        """屏蔽 Hugging Face Hub 與 Transformers 未認證警告與非必要日誌"""
        warnings.filterwarnings("ignore", category=UserWarning, module=r"huggingface_hub.*")
        warnings.filterwarnings("ignore", category=FutureWarning, module=r"huggingface_hub.*")

    def _resolve_dimension_mock(self) -> int:
        """Mock 模式下優先從 config.MODEL_SPECS 查表，再以模型規格或名稱解析維度"""
        spec = MODEL_SPECS.get(self.model_name)
        if spec and isinstance(spec.get("dim"), int):
            self._dimension = int(spec["dim"])
            return self._dimension
        try:
            from fastembed import TextEmbedding
            dim = TextEmbedding.get_embedding_size(self.model_name)
            if isinstance(dim, int) and dim > 0:
                self._dimension = dim
                return dim
        except Exception:
            pass
        name = self.model_name.lower()
        if "large" in name:
            dim = 1024
        elif "base" in name:
            dim = 768
        elif "minilm" in name:
            dim = 384
        else:
            dim = 512
        self._dimension = dim
        return dim

    def has_local_model(self) -> bool:
        """
        < 1ms 純本地檔案系統探針：檢查 `self.cache_dir` 中目標模型 (`self.model_name`)
        之 ONNX 權重目錄與 `.onnx` 檔案是否已完整存在，零網路 I/O、零 `fastembed` 初始化。
        """
        model_short = self.model_name.split("/")[-1].lower()
        model_clean = self.model_name.replace("/", "--").lower()

        verified = getattr(self, "_verified_onnx_path", None)
        if verified is not None:
            try:
                v_str = str(verified).lower()
                if (
                    verified.is_file()
                    and verified.stat().st_size > 0
                    and (model_short in v_str or model_clean in v_str)
                ):
                    return True
            except OSError:
                pass
            self._verified_onnx_path = None

        if not self.cache_dir.exists():
            return False

        try:
            matching_dirs = [
                d for d in self.cache_dir.iterdir()
                if d.is_dir() and (model_short in d.name.lower() or model_clean in d.name.lower())
            ]
            if matching_dirs:
                for d in matching_dirs:
                    onnx_files = [f for f in d.rglob("*.onnx") if f.is_file() and f.stat().st_size > 0]
                    if onnx_files:
                        self._verified_onnx_path = onnx_files[0]
                        return True

            all_onnx = [f for f in self.cache_dir.rglob("*.onnx") if f.is_file() and f.stat().st_size > 0]
            for f in all_onnx:
                path_str = str(f).lower()
                if model_short in path_str or model_clean in path_str:
                    self._verified_onnx_path = f
                    return True
        except Exception as e:
            log_debug(f"Error while probing local model weights: {e}")

        return False

    def is_model_downloaded(self) -> bool:
        """檢查本地快取目錄中特定模型權重目錄與檔案是否存在 (委派至 has_local_model)。"""
        return self.has_local_model()

    def _load_fastembed_instance(self, validate_supported: bool = False) -> int:
        """在鎖保護下實例化 FastEmbed TextEmbedding 並解析模型維度 (SSOT)。"""
        from fastembed import TextEmbedding

        self.model_name = self.normalize_model_name(self.model_name)
        if validate_supported:
            try:
                supported_models = [m["model"] for m in TextEmbedding.list_supported_models()]
                if self.model_name not in supported_models:
                    matched = next(
                        (sm for sm in supported_models if sm.split("/")[-1].lower() == self.model_name.lower()),
                        None,
                    )
                    if matched:
                        self.model_name = matched
                    else:
                        log_warn(
                            f"Requested model '{self.model_name}' is not in FastEmbed supported list. "
                            f"Falling back to default '{DEFAULT_EMBEDDING_MODEL}'.",
                            stream="stderr",
                        )
                        self.model_name = DEFAULT_EMBEDDING_MODEL
            except Exception as e:
                log_debug(f"Failed to check supported models list: {e}")

        threads_count = resolve_threads(self.max_threads)
        os.makedirs(self.cache_dir, exist_ok=True)

        try:
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
                threads=threads_count,
            )
        except TypeError:
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
            )

        dim = getattr(self._model, "embedding_size", None)
        if dim is None or not isinstance(dim, int) or dim <= 0:
            try:
                sample_vec = next(self._model.embed(["probe"]))
                dim = int(len(sample_vec))
            except Exception:
                dim = TextEmbedding.get_embedding_size(self.model_name)
        self._dimension = int(dim)
        self._is_available = True
        self._init_attempted = True
        self.last_error = None
        return threads_count

    def download_model(self, force: bool = False) -> bool:
        """
        顯式下載 FastEmbed 模型權重至本地快取，具備執行緒鎖保護與異常封裝。
        """
        self._suppress_hf_warnings()
        with self._init_lock:
            if not force and self.is_model_downloaded():
                self._ensure_model()
                return True

            try:
                self._load_fastembed_instance(validate_supported=False)
                log_info(
                    f"Successfully downloaded/loaded FastEmbed model '{self.model_name}' (dim={self._dimension})",
                    stream="stderr",
                )
                return True
            except Exception as e:
                self._is_available = False
                self._model = None
                self.last_error = {
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "timestamp": time.time(),
                }
                raise KnowledgeDBError(f"Failed to download FastEmbed model '{self.model_name}': {e}") from e

    def _init_model(self) -> None:
        """嘗試加載 FastEmbed ONNX 模型；本地探針先行，若未下載則平滑降級為 BM25 模式。"""
        self._suppress_hf_warnings()

        if not self.is_model_downloaded():
            self._is_available = False
            self._model = None
            self.last_error = {
                "error_type": "ModelNotFoundLocally",
                "message": f"Vector model '{self.model_name}' not found locally in '{self.cache_dir}'",
                "timestamp": time.time(),
            }
            log_info(
                "[knowledge-db:embedding] Vector model not found locally. Gracefully fallback to BM25.",
                stream="stderr",
            )
            if self.enable_vector_search and not self.suppress_guard_prompt and is_agents_workflow_installed():
                log("[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？", stream="stderr", flush=True)
            return

        try:
            threads_count = self._load_fastembed_instance(validate_supported=True)
            log_debug(f"EmbeddingService initialized with model '{self.model_name}' (dim={self._dimension}, threads={threads_count})")
        except Exception as e:
            self._is_available = False
            self._model = None
            self.last_error = {
                "error_type": type(e).__name__,
                "message": str(e),
                "timestamp": time.time(),
            }
            log_info(
                f"[knowledge-db:embedding] Vector model unavailable ({type(e).__name__}: {e}). Gracefully fallback to BM25.",
                stream="stderr",
            )
            if self.enable_vector_search and not self.suppress_guard_prompt and is_agents_workflow_installed():
                log("[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？", stream="stderr", flush=True)

    @property
    def dimension(self) -> int:
        """回傳當前模型嵌入維度 (以實際加載之模型實例屬性為 SSOT)"""
        if self._dimension is not None:
            return self._dimension
        if self.mock_mode:
            return self._resolve_dimension_mock()
        self._ensure_model()
        if self._dimension is not None:
            return self._dimension
        return self._resolve_dimension_mock()

    def _ensure_model(self) -> None:
        """嘗試按需加載 FastEmbed ONNX 模型 (Lazy Loading)"""
        if self.mock_mode or self._model is not None:
            return
        if self._init_attempted:
            if self.last_error and self.last_error.get("error_type") == "ModelNotFoundLocally" and self.is_model_downloaded():
                with self._init_lock:
                    if self._model is None and self.is_model_downloaded():
                        self._init_model()
            return
        with self._init_lock:
            if self.mock_mode or self._model is not None or self._init_attempted:
                return
            self._init_attempted = True
            self._init_model()

    @property
    def is_available(self) -> bool:
        """回傳當前環境向量推論服務是否就緒可用 (按需惰性探測加載，若快取權重被刪除則重置狀態)"""
        if self.mock_mode:
            return self._is_available
        if self._is_available:
            if self._verified_onnx_path is not None and self._verified_onnx_path.is_file():
                return True
            if not self.is_model_downloaded():
                self._is_available = False
                self._model = None
                self._verified_onnx_path = None
                self._init_attempted = False
        if not self._is_available:
            self._ensure_model()
        return self._is_available

    def _generate_mock_vector(self, text: str, dim: Optional[int] = None) -> np.ndarray:
        """針對輸入字串生成確定性 (Deterministic) 單位正規化向量 (供測試或沙盒使用)"""
        import numpy as np

        target_dim = dim if dim is not None else self.dimension
        if not text:
            vec = np.zeros(target_dim, dtype=np.float32)
            vec[0] = 1.0
            return vec

        seed = int(hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        raw_vec = rng.randn(target_dim).astype(np.float32)
        norm = np.linalg.norm(raw_vec)
        if norm > 0:
            raw_vec /= norm
        return raw_vec

    @staticmethod
    def _preprocess_text(text: str) -> str:
        """針對程式碼符號進行駝峰與蛇形分割與正規化，以配合 uncased BERT 分詞"""
        if not text:
            return ""
        t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
        t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", t)
        t = t.replace("_", " ").replace(".", " ").replace("/", " ").replace("\\", " ").lower()
        return " ".join(t.split())

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        """
        批次計算文字嵌入向量清單，傳回 (N, dim) 之 L2-Normalized 矩陣。
        採用 batch_size 切片與微幅時間片讓渡 (sleep 5ms)，杜絕 CPU 100% 飽和與系統凍結。
        """
        import numpy as np

        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        try:
            eff_batch_size = max(1, int(batch_size)) if batch_size and int(batch_size) > 0 else 64
        except (TypeError, ValueError):
            eff_batch_size = 64

        preprocessed = [self._preprocess_text(t) for t in texts]

        if self.mock_mode:
            vectors = [self._generate_mock_vector(t) for t in preprocessed]
            return np.vstack(vectors).astype(np.float32)

        if not self.is_available or self._model is None:
            return np.empty((0, self.dimension), dtype=np.float32)

        try:
            embeddings_list: List[np.ndarray] = []
            total_items = len(preprocessed)
            for i in range(0, total_items, eff_batch_size):
                chunk = preprocessed[i : i + eff_batch_size]
                chunk_gen = self._model.embed(chunk, batch_size=eff_batch_size)
                embeddings_list.extend(list(chunk_gen))
                if i + eff_batch_size < total_items:
                    time.sleep(0.005)

            mat = np.vstack(embeddings_list).astype(np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return mat / norms
        except Exception as e:
            log_warn(f"Error during embed_texts: {e}.", stream="stderr")
            return np.empty((0, self.dimension), dtype=np.float32)

    def embed_texts_probe(
        self,
        texts: List[str],
        probe_size: int = 10,
        total_count: Optional[int] = None,
    ) -> Any:
        """
        執行前 probe_size 個文字之微基準推論探針。
        若指定 total_count，回傳 (probe_vectors, est_total)；
        若未指定 total_count，回傳 (probe_vectors, elapsed, unit_sec)。
        """
        import numpy as np

        if not texts:
            empty_vecs = np.empty((0, self.dimension), dtype=np.float32)
            return (empty_vecs, 0.0) if total_count is not None else (empty_vecs, 0.0, 0.0)

        probe_chunk = texts[:probe_size]
        t0 = time.perf_counter()
        probe_vectors = self.embed_texts(probe_chunk)
        elapsed = time.perf_counter() - t0
        unit_sec = (elapsed / len(probe_chunk)) if probe_chunk else 0.0

        if total_count is not None:
            est_total = unit_sec * total_count
            return probe_vectors, est_total
        return probe_vectors, elapsed, unit_sec

    def embed_query(self, query: str) -> np.ndarray:
        """計算單一查詢語句之特徵向量 (shape: (dim,))"""
        import numpy as np

        res = self.embed_texts([query])
        if len(res) > 0:
            return res[0]
        return np.zeros(self.dimension, dtype=np.float32)


class VectorIndex:
    """向量特徵索引池與二進位快取容器"""

    def __init__(self, model_name: Optional[str] = None, dim: Optional[int] = None):
        self.doc_ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self.model_name: Optional[str] = model_name
        self.dim: Optional[int] = dim

    def build(
        self,
        doc_ids: List[str],
        vectors: np.ndarray,
        model_name: Optional[str] = None,
        dim: Optional[int] = None,
    ) -> None:
        """建置或替換當前向量索引"""
        import numpy as np

        self.doc_ids = list(doc_ids)
        self.vectors = vectors.astype(np.float32)
        if model_name:
            self.model_name = model_name
        if dim:
            self.dim = dim
        elif self.vectors.ndim > 1:
            self.dim = self.vectors.shape[1]

    def is_compatible_with(self, model_name: Optional[str], dim: Optional[int] = None) -> bool:
        """檢核當前快取之模型名稱與維度是否相容"""
        if self.vectors is None:
            return False
        if self.model_name and model_name and self.model_name != model_name:
            return False
        if dim is not None and self.dim is not None and self.dim != dim:
            return False
        if dim is not None and self.vectors.ndim > 1 and self.vectors.shape[1] != dim:
            return False
        return True

    def patch_incremental(
        self,
        removed_doc_ids: Set[str],
        new_doc_ids: Optional[List[str]] = None,
        new_vectors: Optional[np.ndarray] = None,
    ) -> None:
        """增量修補向量索引：移除過期 doc_ids，追加新 doc_ids 與向量"""
        import numpy as np

        if self.vectors is None or len(self.doc_ids) == 0:
            if new_doc_ids and new_vectors is not None and len(new_vectors) > 0:
                self.build(new_doc_ids, new_vectors, model_name=self.model_name, dim=self.dim)
            return

        dim = self.vectors.shape[1] if (self.vectors is not None and self.vectors.ndim > 1) else (self.dim or 0)
        exclude_ids = set(removed_doc_ids) | set(new_doc_ids or ())

        keep_indices = []
        keep_doc_ids = []
        for i, doc_id in enumerate(self.doc_ids):
            if doc_id not in exclude_ids:
                keep_indices.append(i)
                keep_doc_ids.append(doc_id)

        if keep_indices:
            current_vectors = self.vectors[keep_indices]
        else:
            current_vectors = np.empty((0, dim), dtype=np.float32)

        if new_doc_ids and new_vectors is not None and len(new_vectors) > 0:
            if len(current_vectors) > 0:
                merged_vectors = np.vstack([current_vectors, new_vectors.astype(np.float32)])
            else:
                merged_vectors = new_vectors.astype(np.float32)
            merged_doc_ids = keep_doc_ids + list(new_doc_ids)
        else:
            merged_vectors = current_vectors
            merged_doc_ids = keep_doc_ids

        self.build(merged_doc_ids, merged_vectors, model_name=self.model_name, dim=self.dim)

    def search(self, query_vec: np.ndarray, top_k: int = 50) -> List[Tuple[str, float]]:
        """執行頂點餘弦相似度 Top-K 檢索。"""
        import numpy as np

        if self.vectors is None or len(self.doc_ids) == 0 or self.vectors.ndim != 2:
            return []

        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)
        elif query_vec.ndim != 2:
            return []

        if query_vec.shape[-1] != self.vectors.shape[1]:
            return []

        sims = np.dot(self.vectors, query_vec.T).reshape(-1)
        k = min(top_k, len(self.doc_ids))
        if k <= 0:
            return []

        top_indices = np.argpartition(-sims, k - 1)[:k]
        top_sorted = top_indices[np.argsort(-sims[top_indices])]

        results: List[Tuple[str, float]] = []
        for idx in top_sorted:
            results.append((self.doc_ids[idx], float(sims[idx])))
        return results

    def save_binary(self, cache_file: Union[str, Path], compresslevel: int = 1) -> None:
        """使用 io_utils 原子儲存向量快取"""
        dim_val = self.dim or (self.vectors.shape[1] if self.vectors is not None and self.vectors.ndim > 1 else None)
        data = {
            "doc_ids": self.doc_ids,
            "vectors": self.vectors,
            "model_name": self.model_name,
            "dim": dim_val,
        }
        atomic_save_gzip_pickle(cache_file, data, compresslevel=compresslevel)

    @classmethod
    def load_binary(cls, cache_file: Union[str, Path]) -> "VectorIndex":
        """使用 io_utils 還原向量索引與元資料"""
        idx = cls()
        data = load_gzip_pickle(cache_file, raise_on_missing=False)
        if not isinstance(data, dict):
            return idx
        doc_ids = data.get("doc_ids", [])
        vectors = data.get("vectors")
        model_name = data.get("model_name")
        dim = data.get("dim")
        if doc_ids and vectors is not None:
            idx.build(doc_ids, vectors, model_name=model_name, dim=dim)
        return idx
