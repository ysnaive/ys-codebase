# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `UniversalRedundancyFilter` 自動剔除與 Docstring 重複之註解、與 Token 重複之 Markdown Header、版權樣板與空行，保留純代碼 | FR-06 | `dev test knowledge-db -k test_redundancy_filter` |
| **FT-02** | 單元測試 | 驗證 8,000 字元動態衰減計算器各階行數精確性 (<3500: 30, 3500~6000: 30->10, 6000~7000: 10, >=7000: 0) | FR-06 | `dev test knowledge-db -k test_8000_char_budget_decay` |
| **FT-03** | 單元測試 | 驗證 `ResultFormatter` 各格式化器 (`format_search_output`、`format_callers` 等) 輸出正確性，確認字元數嚴格受 8,000 限制 | FR-01, FR-06 | `dev test knowledge-db -k test_formatter_search_output` |
| **FT-04** | 單元測試 | 驗證 `IndexingPipeline` 倒排與向量索引建置、增量熱補丁與快取讀寫邏輯 | FR-02 | `dev test knowledge-db -k test_indexing_pipeline` |
| **FT-05** | 回歸測試 | 驗證 `KnowledgeEngine` 解耦瘦身至 $\le 450$ 行後，現有 121 個單元測試 100% 通過（0 邏輯破壞、0 Unknown） | FR-03, NFR-02 | `python yscb.py dev test knowledge-db --quiet` |
| **FT-06** | 契約測試 | 驗證 CLI 門面命令（`search`、`callers`、`callees`、`impact`、`status`）之純文字與 `--json` 格式相容性 | FR-04 | `dev test knowledge-db -k test_cli` |
| **FT-07** | 單元測試 | 驗證 `EmbeddingService` 分批推論切片與 ONNX 執行緒上限保護，以及 `TreeSitterDriver` 調用點符號重用避免二次解析 | NFR-01, NFR-02 | `dev test knowledge-db -k test_batching_and_thread_capping` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `UniversalRedundancyFilter` 正確剔除 Docstring、重疊 Heading、License 樣板與連續空白行 | 2026-09-05 15:38 |
| **FT-02** | `Passed` | 8,000 字元預算階梯衰減曲線精確通過所有邊界斷言 (0, 2500, 3500, 4750, 6000, 7000, 8000) | 2026-09-05 15:38 |
| **FT-03** | `Passed` | `ResultFormatter` 各格式輸出均受 8,000 字元與保底 5 項目守門防護，截斷提示正常 | 2026-09-05 15:38 |
| **FT-04** | `Passed` | `IndexingPipeline` 倒排/向量/圖譜索引建置、JIT 嗅探與快取委派運作正常 | 2026-09-05 15:38 |
| **FT-05** | `Passed` | `dev test knowledge-db --quiet` 全套件 123/123 100% 通過（0 Fail, 0 Skip, 0 Unknown） | 2026-09-05 15:38 |
| **FT-06** | `Passed` | `TestCLI` 100% 通過，實機核驗 `status`、`search`、`callers`、`callees`、`impact` 及 `--json` 完全相容 | 2026-09-05 15:41 |
| **FT-07** | `Passed` | `EmbeddingService` 分批推論 (batch_size=32) 正常運作，ONNX 執行緒上限設定正確，調用點 AST 符號重用一致性 100% 通過 | 2026-09-05 16:06 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py install knowledge-db@build --force` 完成本地物化更新，實機執行 `python yscb.py knowledge-db search KnowledgeEngine -s`，確認輸出總長度 $\le 8000$ 字元且切片無重複 Docstring/Header 雜訊 | `[測試通過]` | 實機核驗通過：hot-rebuild 231 個檔案僅耗時 10.4 秒，ONNX 執行緒與分批讓渡運作平穩零卡死；熱快取搜尋 sub-2s；輸出 $\le 8000$ 字元且 Docstring 切片純化正常 |
