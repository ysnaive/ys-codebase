# Knowledge-DB 深度實戰基準評測套件 (Benchmark 2)

本目錄包含針對 YS-Codebase 新版 `knowledge-db` 的第二代基準評測環境（Benchmark 2）。

相較於 Benchmark 1，本期評測**全面剔除了語法偏好型敘述**（如「查 callers」、「計算 impact 拓撲」等直接匹配特定 CLI 功能的題目），改採**下游使用者與核心開發者在真實開發、架構除錯與故障排查中常見的深層問題**。

---

## 🚀 Benchmark 2 核心演進亮點

1. **常規工程場景驅動**：
   - 題目聚焦於「為什麼修改會失效？」、「為什麼會拋出安全阻斷？」、「模組生命週期如何閉環？」等高頻工程實務。
2. **多模組地毯式架構覆蓋**：
   - 深度橫跨 `agents-workflow`（Stage 1~2 發布流水線、雙軌 Manifest）、`core`（2x2 組態矩陣、原子快照與回滾、微環境隔離）、`dev`（沙盒向上探測特徵、目錄保護）、`knowledge-db`（500ms 防抖守護進程、版本自我重啟、雙階增量指紋）。
3. **無偏好自然語言檢驗**：
   - 無論是實驗組 (Knowledge-DB) 或對照組 (傳統工具)，皆需先由業務現象推論架構根因，再進行代碼或文檔定位。

---

## 📁 目錄結構

```text
benchmark2/
├── README.md                  # 本指引文件 (評測理念、架構與操作指引)
├── QUESTIONS.md               # 評測題目集 (Level 1~3 共 9 題，含客觀 Ground Truth)
├── PROMPT_KNOWLEDGE_DB.md     # 實驗組 (Agent A) 提示詞：啟用 knowledge-db 專用工具鏈
├── PROMPT_TRADITIONAL.md      # 對照組 (Agent B) 提示詞：嚴格僅限傳統工具 (grep / view_file)
├── results_knowledge_db.md    # [待生成] 實驗組執行結果與指標統計
└── results_traditional.md     # [待生成] 對照組執行結果與指標統計
```

---

## 🎯 題目維度與情境清單

詳細題目描述與標準答案請參閱 [`QUESTIONS.md`](./QUESTIONS.md)：

1. **Level 1：帶有具體機制/架構實體定位之問題 (Deep Mechanism Queries)**
   - **Q1.1**：為什麼手動修改 `.agents/` 內的 workflow 檔案會在編譯或發布時被重置？（`ReleasePublisher` 4 步原子交易）
   - **Q1.2**：為什麼在專案根目錄下直接跑測會被 `SecurityError` 阻斷？（`YSCBTestCase.setUp` 沙盒向上探測特徵演算法）
   - **Q1.3**：為什麼在 `source/` 建立了新模組，`yscb` 卻找不到 CLI 命令？（`yscb.py` 路由機制與三態隔離物化閉環）

2. **Level 2：模組架構運作與組態/生命週期管理 (Architecture & Lifecycle Queries)**
   - **Q2.1**：2x2 組態矩陣深層合併、原子寫入與本機設定刪除降級機制（`ConfigManager`、`_deep_merge`）
   - **Q2.2**：現場交接快照 `handoff.md` 凍結、恢復與歸檔清理防護（`/Pause`、`/Continue` 與結案物理清理）
   - **Q2.3**：計畫封存 `plan archive` 的 4 重守門安全防護與 CHANGELOG 登載約束（`PlanArchiver.archive_plan`）

3. **Level 3：直白敘述/故障排查與系統效能保障 (Troubleshooting & Reliability)**
   - **Q3.1**：為什麼頻繁存檔時知識庫背景進程不會飆高 CPU？改版時如何自我修復？（`HotReloadServer` 防抖與版本自適應重啟）
   - **Q3.2**：為什麼代碼庫擴大至千檔規模時，搜尋依然能在毫秒級完成而無需全盤重掃？（雙階增量指紋比對與二進位快照）
   - **Q3.3**：安裝第三方套件如果中途失敗，系統是如何避免微環境損毀並自動復原的？（微環境隔離、事前快照與原子回滾）

---

## 🚀 評測執行流程 (Execution Guide)

1. **啟動 Agent A (Knowledge-DB 啟用組)**：
   - 開立全新 Agent Session，發送 [`benchmark2/PROMPT_KNOWLEDGE_DB.md`](./PROMPT_KNOWLEDGE_DB.md) 內容。
   - 等待其完成並寫入 `benchmark2/results_knowledge_db.md`。
2. **啟動 Agent B (傳統工具對照組)**：
   - 開立全新 Agent Session，發送 [`benchmark2/PROMPT_TRADITIONAL.md`](./PROMPT_TRADITIONAL.md) 內容。
   - 等待其完成並寫入 `benchmark2/results_traditional.md`。
3. **返回本 Session**：
   - 通知「已完成測評」，我將自動提取兩組的 `transcript.jsonl`，產出 Benchmark 2 深度評估對比報告！
