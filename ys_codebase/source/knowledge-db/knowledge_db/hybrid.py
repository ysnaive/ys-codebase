"""
knowledge-db 複合檢索與 RRF 倒數排名融合引擎 (HybridSearchEngine)
結合 BM25 關鍵字檢索與語意向量檢索，具備 100% 雙軌剛性降級保證。
"""

import logging
from typing import Any, Dict, List, Optional, Set

from .embedding import EmbeddingService, VectorIndex
from .schema import UnifiedSymbol

logger = logging.getLogger("knowledge-db.hybrid")

DEFAULT_RRF_K = 60
DEFAULT_WEIGHT_LEXICAL = 0.5
DEFAULT_WEIGHT_VECTOR = 0.5
DEFAULT_MIN_VECTOR_SIMILARITY = 0.70


class HybridSearchEngine:
    """
    BM25 + 向量 RRF (Reciprocal Rank Fusion) 複合檢索引擎
    """

    def __init__(
        self,
        inverted_index: Any = None,
        vector_index: Optional[VectorIndex] = None,
        embedding_service: Optional[EmbeddingService] = None,
        bm25_engine: Optional[Any] = None,
        rrf_k: int = DEFAULT_RRF_K,
        weight_lexical: float = DEFAULT_WEIGHT_LEXICAL,
        weight_vector: float = DEFAULT_WEIGHT_VECTOR,
        min_vector_similarity: float = DEFAULT_MIN_VECTOR_SIMILARITY,
    ):
        self.inverted_index = inverted_index
        self.vector_index = vector_index if vector_index is not None else VectorIndex()
        self.embedding_service = embedding_service
        self.bm25_engine = bm25_engine
        self.rrf_k = rrf_k
        self.weight_lexical = weight_lexical
        self.weight_vector = weight_vector
        self.min_vector_similarity = min_vector_similarity

    @property
    def is_vector_available(self) -> bool:
        """檢查向量檢索子系統是否完全就緒"""
        return (
            self.embedding_service is not None
            and self.embedding_service.is_available
            and self.vector_index is not None
            and len(self.vector_index.doc_ids) > 0
        )

    def compute_rrf(
        self,
        lexical_ranks: Dict[str, int],
        vector_ranks: Dict[str, int],
    ) -> Dict[str, float]:
        """
        標準 RRF 倒數排名融合演算法：
        Score(d) = w_lex / (k + rank_lex) + w_vec / (k + rank_vec)
        :param lexical_ranks: {doc_id: 1-indexed rank}
        :param vector_ranks: {doc_id: 1-indexed rank}
        :return: {doc_id: rrf_score}
        """
        all_doc_ids: Set[str] = set(lexical_ranks.keys()) | set(vector_ranks.keys())
        rrf_scores: Dict[str, float] = {}

        for doc_id in all_doc_ids:
            score = 0.0
            if doc_id in lexical_ranks:
                score += self.weight_lexical / (self.rrf_k + lexical_ranks[doc_id])
            if doc_id in vector_ranks:
                score += self.weight_vector / (self.rrf_k + vector_ranks[doc_id])
            rrf_scores[doc_id] = score

        return rrf_scores

    def search(
        self,
        query: str,
        limit: int = 10,
        file_types: Optional[List[str]] = None,
        lexical_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        執行複合檢索：
        1. 若 lexical_only 為 True 或向量服務未就緒，100% 平滑退化為純 BM25 檢索。
        2. 否則並行獲取 BM25 排名與向量語意排名，計算 RRF 融合分數並重排輸出。
        """
        if not query or not str(query).strip():
            return []

        # 1. 執行 BM25 倒排檢索 (擷取足夠候選集供融合)
        fetch_limit = max(limit * 3, 30)
        bm25_hits: List[Dict[str, Any]] = []
        if self.inverted_index is not None and hasattr(self.inverted_index, "search"):
            bm25_hits = self.inverted_index.search(
                query=query,
                limit=fetch_limit,
                file_types=file_types,
            )
        elif self.bm25_engine is not None and self.inverted_index is not None:
            from .retrieval import QueryFilter
            flt = QueryFilter(ftypes=file_types, limit=fetch_limit)
            raw_res = self.bm25_engine.search(query=query, index=self.inverted_index, filter_cfg=flt)
            bm25_hits = [
                {
                    "doc_id": r.symbol.id,
                    "score": r.score,
                    "matched_terms": r.matched_terms,
                }
                for r in raw_res
            ]

        symbols_map = getattr(self.inverted_index, "symbols", {}) if self.inverted_index else {}

        # 2. 若指定 lexical_only 或向量管線未就緒，執行 100% 剛性平滑降級
        if lexical_only or not self.is_vector_available:
            results = []
            for hit in bm25_hits[:limit]:
                doc_id = hit["doc_id"]
                sym = symbols_map.get(doc_id)
                results.append({
                    "symbol": sym,
                    "score": hit["score"],
                    "matched_terms": hit.get("matched_terms", []),
                    "mode": "lexical_bm25",
                })
            return results

        # 3. 執行語意向量檢索
        try:
            query_vec = self.embedding_service.embed_query(query)
            raw_vector_hits = self.vector_index.search(query_vec, top_k=fetch_limit)
        except Exception as e:
            logger.warning(f"Vector search failed ({e}), falling back to pure BM25.")
            results = []
            for hit in bm25_hits[:limit]:
                doc_id = hit["doc_id"]
                sym = symbols_map.get(doc_id)
                results.append({
                    "symbol": sym,
                    "score": hit["score"],
                    "matched_terms": hit.get("matched_terms", []),
                    "mode": "fallback_bm25",
                })
            return results

        # 依 file_types 與純語意相似度門檻過濾向量候選集
        filtered_vector_hits = []
        lexical_doc_ids = {hit["doc_id"] for hit in bm25_hits}
        for doc_id, sim in raw_vector_hits:
            sym = symbols_map.get(doc_id)
            if sym is None:
                continue
            if file_types:
                ext = sym.file_path.split(".")[-1].lower() if "." in sym.file_path else ""
                if ext not in file_types and f".{ext}" not in file_types:
                    continue
            # 若該符號無任何 BM25 關鍵字命中，必須達到純語意門檻才視為召回，避免小庫弱相關噪音誤報
            if doc_id not in lexical_doc_ids and sim < self.min_vector_similarity:
                continue
            filtered_vector_hits.append((doc_id, sim))

        # 4. 構建 1-indexed 排名字典
        lexical_ranks: Dict[str, int] = {
            hit["doc_id"]: rank for rank, hit in enumerate(bm25_hits, start=1)
        }
        vector_ranks: Dict[str, int] = {
            doc_id: rank for rank, (doc_id, _) in enumerate(filtered_vector_hits, start=1)
        }

        # 5. RRF 倒數排名融合
        rrf_scores = self.compute_rrf(lexical_ranks, vector_ranks)

        # 按 RRF 得分降序排序
        sorted_doc_ids = sorted(
            rrf_scores.keys(),
            key=lambda d: rrf_scores[d],
            reverse=True,
        )

        bm25_terms_map = {hit["doc_id"]: hit.get("matched_terms", []) for hit in bm25_hits}

        final_results = []
        for doc_id in sorted_doc_ids[:limit]:
            sym = symbols_map.get(doc_id)
            if sym is None:
                continue
            final_results.append({
                "symbol": sym,
                "score": float(rrf_scores[doc_id]),
                "matched_terms": bm25_terms_map.get(doc_id, []),
                "lexical_rank": lexical_ranks.get(doc_id),
                "vector_rank": vector_ranks.get(doc_id),
                "mode": "hybrid_rrf",
            })

        return final_results
