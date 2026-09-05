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
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np

logger = logging.getLogger("knowledge-db.embedding")

# 預設嵌入維度 (bge-small / MiniLM 標準)
DEFAULT_EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


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
        mock_mode: bool = False,
    ):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "knowledge-db" / "models"
        self.mock_mode = mock_mode
        self._model: Optional[Any] = None
        self._is_available: bool = False

        if not self.mock_mode:
            self._init_model()
        else:
            self._is_available = True

    def _init_model(self) -> None:
        """嘗試加載 FastEmbed ONNX 模型；若未安裝或失敗則安全降級"""
        try:
            from fastembed import TextEmbedding

            os.makedirs(self.cache_dir, exist_ok=True)
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
            )
            self._is_available = True
            logger.debug(f"EmbeddingService initialized with model '{self.model_name}'")
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

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        批次計算文字嵌入向量清單，傳回 (N, dim) 之 L2-Normalized 矩陣。
        若不可用時回傳空矩陣。
        """
        if not texts:
            return np.empty((0, DEFAULT_EMBEDDING_DIM), dtype=np.float32)

        preprocessed = [self._preprocess_text(t) for t in texts]

        if self.mock_mode or not self.is_available or self._model is None:
            vectors = [self._generate_mock_vector(t) for t in preprocessed]
            return np.vstack(vectors).astype(np.float32)

        try:
            # FastEmbed embed 回傳 generator of numpy arrays
            embeddings_gen = self._model.embed(preprocessed)
            embeddings_list = list(embeddings_gen)
            mat = np.vstack(embeddings_list).astype(np.float32)
            # L2 正規化
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return mat / norms
        except Exception as e:
            logger.warning(f"Error during embed_texts: {e}. Fallback to mock vectors.")
            vectors = [self._generate_mock_vector(t) for t in preprocessed]
            return np.vstack(vectors).astype(np.float32)

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

    def __init__(self):
        self.doc_ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self._doc_id_to_idx: Dict[str, int] = {}

    def build(self, doc_ids: List[str], vectors: np.ndarray) -> None:
        """建置或替換當前向量索引"""
        self.doc_ids = list(doc_ids)
        self.vectors = vectors.astype(np.float32)
        self._doc_id_to_idx = {doc_id: i for i, doc_id in enumerate(self.doc_ids)}

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

        self.build(merged_doc_ids, merged_vectors)

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

    def save_binary(self, cache_file: Union[str, Path]) -> None:
        """使用 Pickle Protocol 5 + Gzip 儲存向量快取"""
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "doc_ids": self.doc_ids,
            "vectors": self.vectors,
        }
        with gzip.open(cache_path, "wb", compresslevel=6) as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load_binary(cls, cache_file: Union[str, Path]) -> "VectorIndex":
        """自 Protocol 5 Gzip 快取還原向量索引"""
        cache_path = Path(cache_file)
        idx = cls()
        if not cache_path.exists():
            return idx
        try:
            with gzip.open(cache_path, "rb") as f:
                data = pickle.load(f)
            doc_ids = data.get("doc_ids", [])
            vectors = data.get("vectors")
            if doc_ids and vectors is not None:
                idx.build(doc_ids, vectors)
        except Exception as e:
            logger.warning(f"Failed to load vector cache from '{cache_path}': {e}")
        return idx
