# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Draft  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `EmbeddingService.is_model_downloaded` | `knowledge_db/embedding.py` | Public | 本地權重檔案存在性探針，回傳模型權重是否已完整就緒 |
| `EmbeddingService.download_model` | `knowledge_db/embedding.py` | Public | 顯式執行 FastEmbed 模型權重下載，供離線環境前置準備 |
| `KnowledgeDBEngine.status` | `knowledge_db/engine.py` | Public | 空間狀態查詢，支援可選 `scan: bool` 整合增量指紋比對 |
| `KnowledgeDBEngine.model_status` | `knowledge_db/engine.py` | Public | 獲取本地模型狀態字典（模型名、路徑、維度、就緒狀態） |
| `KnowledgeDBEngine.model_download` | `knowledge_db/engine.py` | Public | 轉發執行向量模型權重下載 |
| `cli.status` | `scripts/cli.py` | CLI Entry | 支援 `--scan` / `--diff` 輸出空間指紋異動狀態 |
| `cli.index` | `scripts/cli.py` | CLI Entry | 一鍵全管線索引建置，支援 `--export <path>` 導出語意 Bundle |
| `cli.model` | `scripts/cli.py` | CLI Entry | `model status` 與 `model download` 之群組分發器 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class EmbeddingService:
    def is_model_downloaded(self) -> bool:
        """檢查本地快取目錄中特定模型權重目錄與檔案是否存在。

        Returns:
            bool: 若權重目錄存在且包含至少一個模型權重檔 (.onnx) 則回傳 True，否則 False。
        """

    def download_model(self, force: bool = False) -> bool:
        """顯式下載 FastEmbed 模型權重至本地快取。

        Args:
            force: 若為 True 則強制覆蓋現有權重重新下載。

        Returns:
            bool: 下載成功回傳 True。

        Raises:
            KnowledgeDBError: 下載失敗或網路不可達時拋出。
        """

    def _init_model(self) -> None:
        """本地探針先行：若本地未下載則平滑降級為 BM25，絕不發起隱式網路請求。

        若組態開啟向量檢索但本地無模型，額外輸出剛性提示至 sys.stderr:
        '[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？'
        """

class KnowledgeDBEngine:
    def status(self, space: Optional[str] = None, scan: bool = False, force_scan: bool = False) -> Dict[str, Any]:
        """查看知識庫狀態，並可選包含增量指紋掃描比對結果。"""

    def model_status(self) -> Dict[str, Any]:
        """回傳當前模型名稱、快取目錄、本地權重存在性與嵌入維度。"""

    def model_download(self, force: bool = False) -> bool:
        """下載或預熱向量模型權重。"""

# CLI 路由分發合約 (scripts/cli.py)
def model(cmd_bags: Any) -> int:
    """向量模型生命週期管理群組分發 (status / download)。"""

def model_status(cmd_bags: Any) -> int:
    """輸出模型快取目錄、檔案狀態與維度。"""

def model_download(cmd_bags: Any) -> int:
    """執行顯式模型下載並渲染進度與結果。"""
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 底層探針與服務] 
  └── EmbeddingService.is_model_downloaded & download_model (embedding.py)
        │
[Step 2: 引擎整合]
  └── KnowledgeDBEngine status(--scan) & model_* 擴充 (engine.py)
        │
[Step 3: 宣告契約更新]
  └── contributes/core.json (移除 scan/bundle, 新增 model, 擴充 status/index 選項)
        │
[Step 4: CLI 進入點整併]
  └── scripts/cli.py (實作 model 分發、改造 status 與 index、移除舊指令)
        │
[Step 5: 測試套件升級]
  └── tests/test_cli.py (驗證 8 大指令、model 子指令與無模型平滑降級)
```
