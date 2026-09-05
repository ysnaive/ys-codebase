# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_multilingual_tokenizer_and_hybrid_search  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `MultilingualTokenizer` | `knowledge_db/tokenizer.py` | Public | 中英混雜、CJK 字符、駝峰/蛇形標識符分詞與程式碼標記切分 |
| `EmbeddingService` | `knowledge_db/embedding.py` | Public | ONNX 向量嵌入推論、特徵向量生成、餘弦相似度計算與降級感知 |
| `HybridSearchEngine` | `knowledge_db/hybrid.py` | Public | BM25 與向量排序之 RRF (Reciprocal Rank Fusion) 倒數排名融合 |
| `KnowledgeEngine.search` | `knowledge_db/engine.py` | Public | 高階檢索對外門面，支援 `--lexical-only` 與 `--json` 結構化輸出 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
from knowledge_db.schema import UnifiedSymbol, SearchResult

class MultilingualTokenizer:
    """多語言混雜分詞器：支援 CJK 區間切分與代碼標識符深層拆解"""

    def __init__(self, stop_words: Optional[Set[str]] = None): ...

    def tokenize(self, text: str) -> List[str]:
        """將中英混雜文字與代碼切分為正規化小寫 token 清單。"""
        ...

    def split_identifier(self, identifier: str) -> List[str]:
        """將駝峰命名 (CamelCase) 或蛇形命名 (snake_case) 拆解為個別詞素。"""
        ...


class EmbeddingService:
    """向量推論服務：封裝 FastEmbed 離線模型，具備 100% 異常攔截與平滑降級"""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        cache_dir: Optional[str] = None,
    ): ...

    @property
    def is_available(self) -> bool:
        """回傳當前環境 fastembed 是否就緒且模型是否可用。"""
        ...

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """批次將文本轉化為單位長度 (L2 Normalized) 之稠密向量矩陣。"""
        ...

    def embed_query(self, query: str) -> np.ndarray:
        """將查詢語句轉化為特徵向量 (shape: (dim,))。"""
        ...

    def compute_similarity(self, query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
        """計算查詢向量與文件向量之餘弦相似度得分矩陣。"""
        ...


class HybridSearchEngine:
    """複合檢索調度引擎：實作 RRF 排名融合與剛性 BM25 降級"""

    def __init__(
        self,
        inverted_index: Any,
        embedding_service: Optional[EmbeddingService] = None,
        rrf_k: int = 60,
        weight_lexical: float = 0.5,
        weight_vector: float = 0.5,
    ): ...

    def search(
        self,
        query: str,
        limit: int = 10,
        file_types: Optional[List[str]] = None,
        lexical_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        執行複合檢索：
        1. 若 lexical_only 或 embedding_service 不可用，100% 執行純 BM25 檢索。
        2. 否則並行獲取 BM25 候選排名與語意向量候選排名，執行 RRF 融合重排。
        """
        ...

    def compute_rrf(
        self,
        lexical_ranks: Dict[str, int],
        vector_ranks: Dict[str, int],
    ) -> Dict[str, float]:
        """依照公式 score(d) = w_lex / (k + rank_lex) + w_vec / (k + rank_vec) 融合得分。"""
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. MultilingualTokenizer (knowledge_db/tokenizer.py)  [基底無相依]
         |
         +---------------------------------------+
         |                                       |
         v                                       v
2. InvertedIndex (更新分詞調用)        3. EmbeddingService (knowledge_db/embedding.py)
         |                                       |
         +-------------------+-------------------+
                             |
                             v
              4. HybridSearchEngine (knowledge_db/hybrid.py)
                             |
                             v
              5. KnowledgeEngine (knowledge_db/engine.py 整合)
```
