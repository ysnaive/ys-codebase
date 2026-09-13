# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Draft  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 實際加載模型動態維度解析與常數徹底淘汰 | 徹底移除 `DEFAULT_EMBEDDING_DIM` 常數（零特例、零硬編碼維度）。統一以實際加載之 FastEmbed 模型實例原生屬性 `self._model.embedding_size`（或實際推論 shape 探針）為維度的唯一真理來源 (SSOT)。`EmbeddingService` 空向量、回退向量與 Mock 生成全面改由 `self.dimension` 動態屬性供給；清理冗餘模式分支；單元測試徹底淘汰 `DEFAULT_EMBEDDING_DIM`，改以動態 `self.service.dimension` 驗證。 | P0 | [P00:DR-01] |
| **FR-02** | 向量快取相容與平滑判定 | `VectorIndex.is_compatible_with` 與 `pipeline.py` 熱修補相容檢核必須對齊動態解析之維度與模型名稱。當模型為 `BAAI/bge-small-zh-v1.5` 且快取維度為 512 時判定相容通過，正常啟用向量特徵檢索；維度真實不符時輸出清晰重建指引。 | P0 | [P00:DR-01] |
| **FR-03** | FastEmbed 載入異常診斷暴露 | `EmbeddingService` 於載入或推論失敗時記錄原始異常（如 `ImportError`, `WinError 1114`）於 `last_error` 欄位；CLI `index` 與 `search` 在降級時輸出簡短錯誤類型與訊息提示，避免黑盒靜默吞掉。 | P1 | [P00:DR-02] |
| **FR-04** | Windows 環境警告與相容防護 | 進入 `embedding.py` 時設定 `os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")`，抑制 Windows 無符號連結權限之大段警告；更新文件說明 Windows Anaconda 環境所需 VC++ runtime $\ge 14.4x$。 | P1 | [P00:DR-02] |
| **FR-05** | 模型名歸一化健全化與 Help 既有合約確認 | (1) 排查確認：`core.commands.dispatcher` 派發前已全域攔截 `--help / -h` 並由 `HelpRenderer` 輸出說明，經實機驗證 1.0.2.x 穿透缺陷已於 1.1.0.0 徹底根除；(2) 規格聚焦：`normalize_model_name` 健全化，確保省略 vendor 前綴（如 `bge-small-zh-v1.5`）時能精確補齊為 `BAAI/bge-small-zh-v1.5`。 | P2 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | FastEmbed / ONNX 原生庫載入失敗 (WinError 1114 等) | 捕獲底層異常並存入 `last_error`，置標 `is_available = False`，降級為純 BM25，於 CLI 提示具體原因，嚴禁未處理異常拋出導致崩潰。 |
| **EC-02** | 既有向量快取維度與當前模型不匹配 (如舊 384 快取搭配 512 模型) | `is_compatible_with` 精確比對維度不符返回 `False`，輸出提示建議執行 `index --force` 重建向量索引，重建後自動切換為新維度並通過比對。 |
| **EC-03** | 自定義非標準模型名稱 (未在內建清單) | 優先自 FastEmbed 元數據動態查詢，若無則於模型加載後提取實際推論輸出形狀確定維度；Mock 模式下預設採用所設定模型之解析維度。 |
| **EC-04** | 沙盒與 Mock 模式下測試執行 | `EmbeddingService` 與 `_generate_mock_vector` 支援動態 dim 參數，沙盒測試環境維持零推論開銷與高確定性驗證。 |
| **EC-05** | 空文字或全空白輸入推論 | `embed_query("")` 回傳長度為 `self.dimension` (512) 之全零或第一維正規化向量，維度不可偏離。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 維度解析效能 | 模型維度查詢在靜態查表與記憶化快取下回應時間 $< 0.05\text{ms}$，杜絕每次請求重複探測之開銷。 |
| **NFR-02** | 測試回歸與合規 | `knowledge-db` 全套單元測試 100% 通過，`dev check knowledge-db` 0 警告 0 錯誤。 |
| **NFR-03** | 零跨模組非相容修改 | 維持 `EmbeddingService` 與 `VectorIndex` 之 Public 介面簽名向前相容，不破壞外部上游調用契約。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!NOTE]
  > FastEmbed 在 `BAAI/bge-small-zh-v1.5` 與 `BAAI/bge-base-zh-v1.5` 的推論維度分別為 512 與 768，而非 HuggingFace BERT 的 384。
- > [!CAUTION]
  > Windows 平台上 Anaconda 預裝之舊版 VC++ 執行期可能優先於系統目錄載入，引發 ONNX Runtime `WinError 1114`。代碼應防禦捕獲並明確指引使用者安裝 `vc14_runtime`。
