# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格書中有 1:1 對應介面與 CLI 處理函式。
- [x] **邊界防護**：EC-01 ~ EC-05 具備本機檔案探針、平滑降級、Agent 剛性中斷與例外隔離策略。
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 指標約束，無外部網路隱式請求，檢索保持 sub-second 延遲。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 更新 8 大指令架構說明，淘汰 scan/bundle，補充 model 指令說明 |
| **專題手冊** | `docs/knowledge-db/retrieval.md` | Modify | 補充離線平滑降級與 Agent 防呆機制說明 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-KB-16]` 向量模型本機探針、平滑靜默降級與 AI Agent 剛性防呆引導 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本次 CLI 架構整併、多餘指令刪除與模型生命週期獨立管理 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若快取目錄下只有空資料夾或下載中途中斷的損毀檔案，探針是否會誤判？  
> [*] **防護解法**：探針不僅檢驗資料夾是否存在，更強制比對 fastembed 模型目錄下之關鍵模型檔案（例如 `model.onnx` / `onnx/model.onnx`）是否存在且大小大於 0；若檔案不全或為空則嚴格判定為「未就緒」。

> [?] **尖銳問題 2**：徹底移除 `scan` 與 `bundle` 是否會導致現有 150 個單元測試中斷？  
> [*] **防護解法**：同步重構 `test_cli.py`，徹底淘汰舊指令呼叫，改為驗證舊指令被正確攔截為未知指令 (exit 1)，並全面覆蓋 `status --scan`、`index` 與 `model` 新管線。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：`EmbeddingService` 實作 `is_model_downloaded()` 本地檔案探針、`download_model()` 顯式下載與 `_init_model()` 平滑靜默降級及 Agent `[GUARD]` 引導輸出。
- [ ] **TASK-02**：`KnowledgeDBEngine` 擴充 `status(scan=True)` 差異整合與 `model_*` 介面轉發。
- [ ] **TASK-03**：更新 `contributes/core.json` 徹底移除 `scan`/`bundle`，新增 `model` 指令群組，擴充 `status` 與 `index` 選項。
- [ ] **TASK-04**：更新 `scripts/cli.py` 移除舊函式，實作 `model` 路由與處理器，整併 `status` 與 `index`。
- [ ] **TASK-05**：更新 `tests/test_cli.py` 單元測試套件，覆蓋 FT-01 ~ FT-06、ET-01 與 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 權重完整性雙重檢驗**：探針檢查目錄存在性與核心 ONNX 權重檔案非空，杜絕因斷點下載引發的損毀載入。
- **[P04:DR-02] 零向下相容包袱**：舊指令直接自 contributes 清冊與 cli 進入點徹底除名，維護生態系架構之整潔性。
