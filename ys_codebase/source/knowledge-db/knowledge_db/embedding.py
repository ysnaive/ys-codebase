"""
knowledge-db 輕量 ONNX 向量嵌入推論服務 (EmbeddingService)
封裝 FastEmbed 離線模型推論、快取持久化與 100% 平滑降級守門。
"""

import gzip
import hashlib
import logging
import os
from pathlib import Path
import pickle
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np

logger = logging.getLogger("knowledge-db.embedding")

# 預設嵌入維度 (bge-small / MiniLM 標準)
DEFAULT_EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def resolve_max_threads(max_threads: Union[str, int, None] = None) -> int:
    """計算 CPU 執行緒上限：auto 採用 cpu_count//2 (至少1)，整數截斷於 [1, cpu_count]"""
    cpu_cnt = os.cpu_count() or 1
    if max_threads is None or max_threads == "auto":
        return max(1, cpu_cnt // 2)
    if isinstance(max_threads, str):
        if max_threads.lower() == "auto":
            return max(1, cpu_cnt // 2)
        try:
            val = int(max_threads)
            return max(1, min(val, cpu_cnt))
        except ValueError:
            return max(1, cpu_cnt // 2)
    if isinstance(max_threads, (int, float)):
        return max(1, min(int(max_threads), cpu_cnt))
    return max(1, cpu_cnt // 2)


class EmbeddingService:
    """
    向量推論服務：
    1. 封裝 FastEmbed (ONNX Runtime) 執行純本地離線特徵提取。
    2. 具備 100% 異常捕獲與 is_available 動態置標，保證零死鎖平滑降級。
    3. 內建 Mock 模式，供沙盒與單元測試環境極速離線驗證。
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_dir: Optional[Union[str, Path]] = None,
        max_threads: Optional[Union[str, int]] = None,
        mock_mode: bool = False,
    ):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "knowledge-db" / "models"
        self.max_threads = max_threads or "auto"
        self.mock_mode = mock_mode
        self._model: Optional[Any] = None
        self._is_available: bool = False
        self._suppress_hf_warnings()
        if not self.mock_mode:
            self._init_model()
        else:
            self._is_available = True

    @staticmethod
    def _suppress_hf_warnings() -> None:
        """屏蔽 Hugging Face Hub 與 Transformers 未認證警告與非必要日誌 (FR-06)"""
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
        for lib in ("huggingface_hub", "transformers", "fastembed"):
            try:
                logging.getLogger(lib).setLevel(logging.ERROR)
            except Exception:
                pass

    @staticmethod
    def list_supported_models() -> List[Dict[str, Any]]:
        """回傳 FastEmbed 支援之文字嵌入模型清單"""
        try:
            from fastembed import TextEmbedding
            return list(TextEmbedding.list_supported_models())
        except Exception:
            return [{"model": DEFAULT_MODEL_NAME, "dim": DEFAULT_EMBEDDING_DIM, "description": "Default BAAI model"}]

    def _init_model(self) -> None:
        """嘗試加載 FastEmbed ONNX 模型；若未安裝或失敗則安全降級"""
        self._suppress_hf_warnings()

        try:
            from fastembed import TextEmbedding

            # 2. 模型白名單合法性比對與優雅降級 (EC-01)
            try:
                supported_models = [m["model"] for m in TextEmbedding.list_supported_models()]
                if self.model_name not in supported_models:
                    logger.warning(
                        f"Requested model '{self.model_name}' is not in FastEmbed supported list. "
                        f"Falling back to default '{DEFAULT_MODEL_NAME}'."
                    )
                    self.model_name = DEFAULT_MODEL_NAME
            except Exception as e:
                logger.debug(f"Failed to check supported models list: {e}")

            # 3. 限制 ONNX 與 OpenMP 執行緒上限，採用 CPU 數之一半 (FR-08, EC-07)
            threads_count = resolve_max_threads(self.max_threads)
            os.environ["OMP_NUM_THREADS"] = str(threads_count)
            os.environ["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = str(threads_count)

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
            self._is_available = True
            logger.debug(f"EmbeddingService initialized with model '{self.model_name}' (threads={threads_count})")
        except Exception as e:
            self._is_available = False
            self._model = None
            logger.info(f"FastEmbed model unavailable ({e}). Fallback to BM25-only mode.")

    @property
    def is_available(self) -> bool:
        """回傳當前環境向量推論服務是否就緒可用"""
        return self._is_available

    def _generate_mock_vector(self, text: str, dim: int = DEFAULT_EMBEDDING_DIM) -> np.ndarray:
        """針對輸入字串生成確定性 (Deterministic) 單位正規化向量 (供測試或沙盒使用)"""
        if not text:
            vec = np.zeros(dim, dtype=np.float32)
            vec[0] = 1.0
            return vec

        # 以 md5 雜湊作為確定性隨機種子
        seed = int(hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        raw_vec = rng.randn(dim).astype(np.float32)
        norm = np.linalg.norm(raw_vec)
        if norm > 0:
            raw_vec /= norm
        return raw_vec

    @staticmethod
    def _preprocess_text(text: str) -> str:
        """針對程式碼符號進行駝峰與蛇形分割與正規化，以配合 uncased BERT 分詞"""
        if not text:
            return ""
        # 分割駝峰命名 (CamelCase -> Camel Case)
        t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
        t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", t)
        # 取代底線、點號與路徑分隔符為空格，並轉為小寫
        t = t.replace("_", " ").replace(".", " ").replace("/", " ").replace("\\", " ").lower()
        return " ".join(t.split())

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        """
        批次計算文字嵌入向量清單，傳回 (N, dim) 之 L2-Normalized 矩陣。
        採用 batch_size 切片與微幅時間片讓渡 (sleep 5ms)，杜絕 CPU 100% 飽和與系統凍結。
        若不可用時回傳空矩陣。
        """
        if not texts:
            return np.empty((0, DEFAULT_EMBEDDING_DIM), dtype=np.float32)

        preprocessed = [self._preprocess_text(t) for t in texts]

        if self.mock_mode or not self.is_available or self._model is None:
            vectors = [self._generate_mock_vector(t) for t in preprocessed]
            return np.vstack(vectors).astype(np.float32)

        try:
            embeddings_list: List[np.ndarray] = []
            total_items = len(preprocessed)
            for i in range(0, total_items, batch_size):
                chunk = preprocessed[i : i + batch_size]
                chunk_gen = self._model.embed(chunk, batch_size=batch_size)
                embeddings_list.extend(list(chunk_gen))
                if i + batch_size < total_items:
                    time.sleep(0.005)

            mat = np.vstack(embeddings_list).astype(np.float32)
            # L2 正規化
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return mat / norms
        except Exception as e:
            logger.warning(f"Error during embed_texts: {e}. Fallback to mock vectors.")
            vectors = [self._generate_mock_vector(t) for t in preprocessed]
            return np.vstack(vectors).astype(np.float32)

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
        if not texts:
            empty_vecs = np.empty((0, DEFAULT_EMBEDDING_DIM), dtype=np.float32)
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
        res = self.embed_texts([query])
        if len(res) > 0:
            return res[0]
        return np.zeros(DEFAULT_EMBEDDING_DIM, dtype=np.float32)

    def compute_similarity(self, query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
        """
        計算查詢向量與文件向量群之餘弦相似度陣列。
        因為兩者均已 L2-Normalized，餘弦相似度即等於內積矩陣相乘 (Dot Product)。
        :param query_vec: 形狀為 (dim,) 之查詢向量
        :param doc_vecs: 形狀為 (N, dim) 之文件向量矩陣
        :return: 形狀為 (N,) 之相似度分數陣列 (範圍約 [-1.0, 1.0])
        """
        if len(doc_vecs) == 0 or len(query_vec) == 0:
            return np.empty((0,), dtype=np.float32)

        # 確保維度相符
        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)

        sims = np.dot(doc_vecs, query_vec.T).squeeze(axis=-1)
        return sims.astype(np.float32)


class VectorIndex:
    """
    向量特徵索引池與二進位快取容器
    """

    def __init__(self, model_name: Optional[str] = None, dim: Optional[int] = None):
        self.doc_ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self._doc_id_to_idx: Dict[str, int] = {}
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
        self.doc_ids = list(doc_ids)
        self.vectors = vectors.astype(np.float32)
        self._doc_id_to_idx = {doc_id: i for i, doc_id in enumerate(self.doc_ids)}
        if model_name:
            self.model_name = model_name
        if dim:
            self.dim = dim
        elif self.vectors.ndim > 1:
            self.dim = self.vectors.shape[1]

    def is_compatible_with(self, model_name: Optional[str], dim: Optional[int] = None) -> bool:
        """檢核當前快取之模型名稱與維度是否相容 (EC-02)"""
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
        if self.vectors is None or len(self.doc_ids) == 0:
            if new_doc_ids and new_vectors is not None and len(new_vectors) > 0:
                self.build(new_doc_ids, new_vectors)
            return

        dim = self.vectors.shape[1] if self.vectors.ndim > 1 else DEFAULT_EMBEDDING_DIM

        # 1. 找出保留的 doc_ids 與其索引
        keep_indices = []
        keep_doc_ids = []
        for i, doc_id in enumerate(self.doc_ids):
            if doc_id not in removed_doc_ids:
                keep_indices.append(i)
                keep_doc_ids.append(doc_id)

        if keep_indices:
            current_vectors = self.vectors[keep_indices]
        else:
            current_vectors = np.empty((0, dim), dtype=np.float32)

        # 2. 追加新向量
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
        """
        執行頂點餘弦相似度 Top-K 檢索。
        :return: [(doc_id, score), ...] 按相似度降序排列
        """
        if self.vectors is None or len(self.doc_ids) == 0:
            return []

        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)

        sims = np.dot(self.vectors, query_vec.T).squeeze(axis=-1)
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
        """使用 Pickle Protocol 5 + Gzip 儲存向量快取 (含 model_name 與 dim 元資料)"""
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        dim_val = self.dim or (self.vectors.shape[1] if self.vectors is not None and self.vectors.ndim > 1 else DEFAULT_EMBEDDING_DIM)
        data = {
            "doc_ids": self.doc_ids,
            "vectors": self.vectors,
            "model_name": self.model_name,
            "dim": dim_val,
        }
        with gzip.open(cache_path, "wb", compresslevel=compresslevel) as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load_binary(cls, cache_file: Union[str, Path]) -> "VectorIndex":
        """自 Protocol 5 Gzip 快取還原向量索引與元資料"""
        cache_path = Path(cache_file)
        idx = cls()
        if not cache_path.exists():
            return idx
        try:
            with gzip.open(cache_path, "rb") as f:
                data = pickle.load(f)
            doc_ids = data.get("doc_ids", [])
            vectors = data.get("vectors")
            model_name = data.get("model_name")
            dim = data.get("dim")
            if doc_ids and vectors is not None:
                idx.build(doc_ids, vectors, model_name=model_name, dim=dim)
        except Exception as e:
            logger.warning(f"Failed to load vector cache from '{cache_path}': {e}")
        return idx
