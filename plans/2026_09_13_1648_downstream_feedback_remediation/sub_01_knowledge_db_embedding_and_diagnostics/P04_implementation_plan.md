# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 P03 API 規格書中均有精確對應介面與契約
- [x] **邊界防護**：EC-01 ~ EC-05 均已涵蓋於 `EmbeddingService` 異常捕獲與降級策略中
- [x] **依賴純淨**：零新增跨模組依賴，嚴格遵循 NFR-01~03 指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 補充 FastEmbed 模型維度動態解析說明與 Windows VC++ 執行期環境指引 |
| **發布日誌** | `plans/2026_09_13_1648_downstream_feedback_remediation/changelog.md` | Modify | 登記子計畫階段推進與決策紀錄 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若 FastEmbed 根本未安裝或底層 ONNX DLL 損毀，`service.dimension` 該回傳什麼？是否會拋出例外導致上游崩潰？  
> [*] **防護解法**：`_ensure_model()` 具備完整 `try/except` 保護，若載入失敗會將錯誤記錄至 `self.last_error`，並透過 FastEmbed 輕量類別元數據或安全兜底探測返回預期維度，保證查詢維度操作永不崩潰；同時置標 `is_available = False` 讓檢索平滑退回 BM25。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：重構 `embedding.py`，徹底淘汰 `DEFAULT_EMBEDDING_DIM`，落實以加載模型為 SSOT 之動態維度、`last_error` 與環境警告抑制
- [ ] **TASK-02**：調整 `pipeline.py` 與 CLI 輸出，注入結構化診斷資訊
- [ ] **TASK-03**：重構 `test_retrieval.py` 單元測試，移除過期常數並補齊 FT-10~13 測試案例
- [ ] **TASK-DOC**：更新 `docs/knowledge-db/README.md` 補充環境指引

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全生態系常數徹底淘汰定稿**：確認全模組全面移除 `DEFAULT_EMBEDDING_DIM`，單元測試全面依據實例屬性動態驗證。
- **[P04:DR-02] 驗證套件與沙盒守門定稿**：實施全量 `dev test knowledge-db`，達成 0 Warning 0 失敗。
