# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `EmbeddingService` | `knowledge_db/embedding.py` | Public | 封裝 FastEmbed 推論、動態維度取得、異常暴露與向量生成 |
| `VectorIndex` | `knowledge_db/embedding.py` | Public | 向量二進位快取管理、相容性比對與 Top-K 檢索 |
| `SearchPipeline` | `knowledge_db/pipeline.py` | Internal | 混合搜尋排程、熱修補檢核與降級提示渲染 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class EmbeddingService:
    last_error: Optional[Dict[str, Any]]
    _dimension: Optional[int]

    @property
    def dimension(self) -> int:
        """
        回傳當前加載模型之真實嵌入維度 (SSOT)。
        若尚未載入則觸發 _ensure_model()；若加載失敗則根據模型定義探測或拋出詳細 last_error。
        """
        ...

    @classmethod
    def normalize_model_name(cls, model_name: Optional[str]) -> str:
        """
        歸一化模型名稱，支援省略前綴 (如 'bge-small-zh-v1.5' -> 'BAAI/bge-small-zh-v1.5')。
        """
        ...


class VectorIndex:
    dim: Optional[int]

    def is_compatible_with(self, model_name: Optional[str], dim: Optional[int] = None) -> bool:
        """
        比對模型名稱與維度。dim 為 None 時不強制比對維度；dim 指定時強制比對 self.dim 與 self.vectors.shape[1]。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: embedding.py]
  ├── 徹底清除 DEFAULT_EMBEDDING_DIM 常數
  ├── 改造 EmbeddingService.dimension 與 last_error
  └── 調整 VectorIndex 與空向量生成

[Step 2: pipeline.py]
  └── 對齊 expected_dim 呼叫並注入 last_error 診斷

[Step 3: test_retrieval.py]
  ├── 移除 DEFAULT_EMBEDDING_DIM 測試導入
  └── 追加 FT-10~13 動態契約與邊界測試
```
